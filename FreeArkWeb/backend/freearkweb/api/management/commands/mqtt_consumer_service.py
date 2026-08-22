import os
import sys
import time
import schedule
from django.core.management.base import BaseCommand
from django.conf import settings
from api.mqtt_consumer import start_mqtt_consumer, stop_mqtt_consumer, get_consumer_health_snapshot
# 导入统一的日志工具
from .common import get_service_logger, log_service_start, log_service_stop, log_task_start, log_task_completion, log_error, log_warning

# 获取配置好的日志器
logger = get_service_logger('mqtt_consumer_service')

# 静默失聪自杀阈值：超过该秒数一条 MQTT 消息都没收到，就认为 broker 端订阅已经
# 悄悄失效（paho 连接仍 ESTABLISHED、on_connect rc=0，但 session 被 broker 清了）。
# 生产实测：采集侧 general/energy 消息最少每秒几十条，screen/schedule/ondemand 等
# 低频消息通常 30s 内也至少有一条，因此 120s 没消息 = 极大概率真的静默失聪。
SILENCE_SUICIDE_SECONDS = int(os.environ.get('FREAARK_MQTT_SILENCE_SUICIDE_SECONDS', '120'))
# 连续多少轮都判定失聪再自杀，避免偶发网络抖动误杀
SILENCE_SUICIDE_CONSECUTIVE_ROUNDS = int(
    os.environ.get('FREAARK_MQTT_SILENCE_SUICIDE_ROUNDS', '3'))


class Command(BaseCommand):
    """
    Django管理命令：运行MQTT消费者服务
    用于监听MQTT消息并将PLC数据保存到数据库
    使用schedule机制进行管理，保持服务持续运行

    健康监控（2026-06 broker 闪断 RCA 后启用）：
      - 每隔 MONITOR_INTERVAL 秒取一次 MQTT 消费者内部健康快照
      - 若连续 SILENCE_SUICIDE_CONSECUTIVE_ROUNDS 轮都满足「连接建立 >
        SILENCE_SUICIDE_SECONDS 秒且期间一条消息都没收到」，则进程自杀退出
        exitcode=3，由 systemd Restart=on-failure 拉起新进程；新进程走正常
        on_connect 重新订阅，broker 侧订阅关系彻底重置，零人工干预自愈。
    """
    help = '启动MQTT消费者服务，监听PLC数据并保存到数据库（使用schedule机制；含静默失聪自动重启）'

    def add_arguments(self, parser):
        # 添加监控间隔参数（秒）
        parser.add_argument(
            '--monitor-interval',
            type=int,
            default=60,
            help='服务监控间隔（秒），默认为60秒'
        )
        # 可选的自动重启功能
        parser.add_argument(
            '--auto-restart',
            action='store_true',
            default=False,
            help='当MQTT服务异常停止或静默失聪时自动退出（让 systemd 重启）'
        )

    def handle(self, *args, **options):
        """命令处理函数"""
        monitor_interval = options['monitor_interval']
        auto_restart = options['auto_restart']

        # 用于「连续 N 轮判定失聪才自杀」的计数器
        consecutive_silence_rounds = 0

        logger.info('🚀 正在启动MQTT消费者服务...')
        self.stdout.write(self.style.SUCCESS('🚀 正在启动MQTT消费者服务...'))
        # 使用统一的日志方法
        service_config = {
            'monitor_interval': f'{monitor_interval}秒',
            'auto_restart': auto_restart,
            'silence_suicide_seconds': SILENCE_SUICIDE_SECONDS,
            'silence_suicide_rounds': SILENCE_SUICIDE_CONSECUTIVE_ROUNDS,
        }
        log_service_start(logger, 'MQTT消费者服务', service_config)

        exit_code = 0

        try:
            # 启动MQTT消费者
            log_task_start(logger, 'MQTT消费者启动')
            if start_mqtt_consumer():
                success_msg = '✅ MQTT消费者服务已成功启动'
                log_task_completion(logger, 'MQTT消费者启动')
                self.stdout.write(self.style.SUCCESS(success_msg))

                topic_msg = '📝 正在监听主题: /datacollection/plc/to/collector/#'
                logger.info(topic_msg)
                self.stdout.write(topic_msg + '\n')

                warning_msg = '⚠️  按 Ctrl+C 停止服务'
                log_warning(logger, '按 Ctrl+C 停止服务')
                self.stdout.write(self.style.WARNING(warning_msg))

                # 设置监控任务：每次 tick 调一次 _monitor_service（含静默失聪判定）
                if auto_restart:
                    schedule.every(monitor_interval).seconds.do(
                        self._monitor_service, interval=monitor_interval)
                    logger.info(
                        '🔍 已设置服务监控，每%s秒检查一次（连续%s轮>%ss无消息会自杀）',
                        monitor_interval, SILENCE_SUICIDE_CONSECUTIVE_ROUNDS,
                        SILENCE_SUICIDE_SECONDS,
                    )
                # 即便没开 --auto-restart 也跑轻量健康快照日志，便于排障
                schedule.every(monitor_interval).seconds.do(
                    self._log_health_snapshot)

                # 保持命令运行
                try:
                    logger.info('🔄 服务已启动，进入调度循环')
                    while True:
                        # _monitor_service 如果判定必须自杀会抛 SystemExit，冒泡到外层
                        schedule.run_pending()
                        time.sleep(1)
                except KeyboardInterrupt:
                    stop_signal_msg = '🛑 收到停止信号...'
                    logger.info(stop_signal_msg)
                    self.stdout.write('\n' + stop_signal_msg)
                finally:
                    # 停止MQTT消费者
                    stopping_msg = '🔄 正在停止MQTT消费者服务...'
                    log_task_start(logger, 'MQTT消费者停止')
                    self.stdout.write(stopping_msg)

                    if stop_mqtt_consumer():
                        stop_success_msg = '✅ MQTT消费者服务已成功停止'
                        log_task_completion(logger, 'MQTT消费者停止')
                        self.stdout.write(self.style.SUCCESS(stop_success_msg))
                    else:
                        stop_fail_msg = '❌ MQTT消费者服务停止失败'
                        log_error(logger, 'MQTT消费者服务停止失败')
                        self.stdout.write(self.style.ERROR(stop_fail_msg))
                        exit_code = 1
            else:
                start_fail_msg = '❌ MQTT消费者服务启动失败'
                log_error(logger, 'MQTT消费者服务启动失败')
                self.stdout.write(self.style.ERROR(start_fail_msg))
                exit_code = 1

        except SystemExit as se:
            # _monitor_service 主动自杀：让 systemd 能识别为失败（非 0 exitcode）
            logger.warning('⚠️  MQTT 消费者因健康检查触发主动自杀退出: exitcode=%s', se.code)
            exit_code = se.code if isinstance(se.code, int) and se.code != 0 else 3
        except Exception as e:
            log_error(logger, '运行过程中发生错误', e)
            logger.error(f'运行MQTT消费者服务时发生错误: {str(e)}')
            import traceback
            logger.error(traceback.format_exc())
            self.stdout.write(self.style.ERROR(f'运行MQTT消费者服务时发生错误: {str(e)}'))
            exit_code = 1
        else:
            exit_code = 0

        logger.info(f'📋 服务退出，退出码: {exit_code}')
        return exit_code

    def _log_health_snapshot(self):
        """每隔 monitor_interval 秒打一行 INFO 级别健康快照，便于运维看 journal。"""
        try:
            snap = get_consumer_health_snapshot()
            msg = (
                f'[MQTT-health] running={snap.get("is_running")} '
                f'conn={snap.get("client_connected")} '
                f'idle={snap.get("seconds_since_last_msg")}s '
                f'(deadline {snap.get("seconds_until_idle_deadline")}s) '
                f'since_connect={snap.get("seconds_since_connect")}s '
                f'qsize(e/g/o)={snap.get("energy_qsize")}/'
                f'{snap.get("general_qsize")}/{snap.get("ondemand_qsize")}'
            )
            logger.info(msg)
        except Exception as exc:
            log_error(logger, '健康快照采集异常（不影响主流程）', exc)

    def _monitor_service(self, interval: int = 60):
        """
        真正的监控实现（接替之前的空实现示例）。

        判定逻辑：
          1. MQTT 消费者未启动 / client 未连接 → 先 log_error，让外层调度决定；
             （因为 paho 有自动重连，给它一两轮机会，还没连上再自杀退出）
          2. 已建立连接且 seconds_since_connect > SILENCE_SUICIDE_SECONDS，
             但 seconds_since_last_msg 仍然 None（从启到今一条没收到）或
             seconds_since_last_msg > SILENCE_SUICIDE_SECONDS：
             → 计数器 +1，累计到 SILENCE_SUICIDE_CONSECUTIVE_ROUNDS 时自杀。
          3. 只要有一条新消息进来，计数器清零。

        :param interval: 本次 tick 的间隔（仅用于日志展示）
        """
        nonlocal_ref = getattr(self, '_monitor_nonlocal', None)
        if nonlocal_ref is None:
            self._monitor_nonlocal = {'consecutive_silence_rounds': 0,
                                      'consecutive_disconnected_rounds': 0}
            nonlocal_ref = self._monitor_nonlocal

        logger.debug('🔍 监控服务状态 (interval=%ss)', interval)
        try:
            snap = get_consumer_health_snapshot()
        except Exception as exc:
            log_error(logger, '_monitor_service 取健康快照失败', exc)
            return

        running = bool(snap.get('is_running'))
        connected = bool(snap.get('client_connected'))
        sec_since_connect = snap.get('seconds_since_connect')    # None=未连过
        sec_since_msg = snap.get('seconds_since_last_msg')        # None=一条没收到过
        e_q = snap.get('energy_qsize', 0)
        g_q = snap.get('general_qsize', 0)
        o_q = snap.get('ondemand_qsize', 0)

        # --- 分支 A：根本没连上 / 进程内部 start() 返回 True 但 client 没 connected ---
        if (not running) or (not connected):
            nonlocal_ref['consecutive_disconnected_rounds'] += 1
            msg = (
                f'_monitor_service: running={running} connected={connected} '
                f'(连续 {nonlocal_ref["consecutive_disconnected_rounds"]} 轮)'
            )
            log_warning(logger, msg)
            # 连续 5 轮（默认 5*60s = 5 分钟）都连不上 → 自杀；让 systemd 重启清僵死状态
            if nonlocal_ref['consecutive_disconnected_rounds'] >= 5:
                log_error(logger, msg + '，连续未连接超过阈值，触发自杀退出')
                # exitcode=3 区分正常退出(0)和异常退出(1)，便于运维统计
                sys.exit(3)
            return
        else:
            nonlocal_ref['consecutive_disconnected_rounds'] = 0

        # --- 分支 B：已连上，但是否静默失聪？ ---
        # 如果连接刚建立还不足自杀阈值（进程刚启），不判定（因为第一批消息可能还没来）
        if sec_since_connect is None or sec_since_connect < SILENCE_SUICIDE_SECONDS:
            nonlocal_ref['consecutive_silence_rounds'] = 0
            logger.debug(
                '_monitor_service: 连接建立时间 %ss < %ss，跳过静默判定',
                sec_since_connect, SILENCE_SUICIDE_SECONDS,
            )
            return

        silence_secs = (sec_since_msg if sec_since_msg is not None
                        else sec_since_connect)
        silent = silence_secs >= SILENCE_SUICIDE_SECONDS

        if not silent:
            # 有消息：计数器清零
            if nonlocal_ref['consecutive_silence_rounds']:
                msg = (
                    f'_monitor_service: 静默判定解除（last_msg={sec_since_msg}s 前；'
                    f'阈值={SILENCE_SUICIDE_SECONDS}s），连续失聪计数从 '
                    f'{nonlocal_ref["consecutive_silence_rounds"]} 清零；'
                    f'qsize(e/g/o)={e_q}/{g_q}/{o_q}'
                )
                logger.info(msg)
                nonlocal_ref['consecutive_silence_rounds'] = 0
            return

        # --- 分支 C：确实静默失聪，连续多轮都这样就自杀 ---
        nonlocal_ref['consecutive_silence_rounds'] += 1
        msg = (
            f'_monitor_service 疑似静默失聪 '
            f'round={nonlocal_ref["consecutive_silence_rounds"]}/'
            f'{SILENCE_SUICIDE_CONSECUTIVE_ROUNDS}: '
            f'silence={silence_secs}s (>={SILENCE_SUICIDE_SECONDS}s), '
            f'last_msg={sec_since_msg}, since_connect={sec_since_connect}; '
            f'qsize(e/g/o)={e_q}/{g_q}/{o_q}'
        )
        log_warning(logger, msg)
        if nonlocal_ref['consecutive_silence_rounds'] >= SILENCE_SUICIDE_CONSECUTIVE_ROUNDS:
            err = (
                f'_monitor_service 连续 {SILENCE_SUICIDE_CONSECUTIVE_ROUNDS} 轮判定静默失聪'
                f'（last_msg={sec_since_msg} 前或未收到），触发进程主动自杀 exitcode=3，'
                f'systemd 会重启'
            )
            log_error(logger, err)
            sys.exit(3)