"""
device_param_history 定时清理服务

按主键 id 小步分批删除超过保留窗口的历史记录，避免大事务打爆 undo log / binlog。
参考已有 plc_data_clean_up_service 服务模式，保持风格一致。

用法示例：
  # 立即执行一次，保留近 7 天，批次大小 5000（安全预演，加 --dry-run 不真删）
  python manage.py dph_cleanup_service --once --days 7 --batch-size 5000 --dry-run

  # 正式执行一次
  python manage.py dph_cleanup_service --once --days 7 --batch-size 5000

  # 以 cron 模式持续运行（每天凌晨 3:00 执行）
  python manage.py dph_cleanup_service --days 7 --cron "0 3 * * *"

索引说明（安全性）：
  device_param_history 表在 collected_at 上有单列索引（db_index=True），
  在 created_at 上无独立索引。边界查询统一使用 collected_at，
  以确保 WHERE 子句走索引，避免全表扫描拖垮生产 DB。
"""

import time
from datetime import datetime, timedelta

import schedule
from django.core.management.base import BaseCommand
from django.db import connection, OperationalError

from .common import (
    get_service_logger,
    log_error,
    log_service_start,
    log_service_stop,
    log_task_completion,
    log_task_start,
    log_warning,
)

logger = get_service_logger('dph_cleanup_service')


class Command(BaseCommand):
    help = '分批删除 device_param_history 超出保留窗口的记录，防止大事务拖垮数据库'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='保留最近多少天的数据（默认 7 天）',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=5000,
            help='每批删除的最大行数（默认 5000）。建议生产环境 2000~5000，避免长锁',
        )
        parser.add_argument(
            '--sleep-ms',
            type=int,
            default=200,
            help='两批之间的休眠毫秒数（默认 200ms），给 IO 喘息',
        )
        parser.add_argument(
            '--cron',
            type=str,
            default='0 3 * * *',
            help='cron 表达式，格式 "分 时 日 月 周"（默认每天凌晨 3:00）',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='仅立即执行一次后退出',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='演练模式：只查询不删除，输出预计删除行数',
        )

    def handle(self, *args, **options):
        days = options['days']
        batch_size = options['batch_size']
        sleep_ms = options['sleep_ms']
        cron_expr = options['cron']
        run_once = options['once']
        dry_run = options['dry_run']

        log_service_start(logger, 'device_param_history 清理服务', {
            'days_to_keep': days,
            'batch_size': batch_size,
            'sleep_ms': sleep_ms,
            'dry_run': dry_run,
        })

        if run_once:
            log_task_start(logger, '执行一次性清理')
            self._run_cleanup(days, batch_size, sleep_ms, dry_run)
            return

        # 常驻模式：按 cron 调度
        self._setup_schedule(cron_expr, days, batch_size, sleep_ms, dry_run)
        try:
            self.stdout.write(f'[dph_cleanup] 常驻模式启动，cron={cron_expr}，按 Ctrl+C 退出')
            while True:
                try:
                    schedule.run_pending()
                except Exception as exc:
                    # 防止 schedule 内部任何未被 _run_cleanup 捕获的异常冲出主循环。
                    # 正常情况下 _run_cleanup 已自行捕获所有异常，此处是最后一道防线。
                    log_error(logger, 'dph_cleanup schedule loop unexpected error', exc)
                    self.stderr.write(f'[dph_cleanup] 调度循环异常（已捕获，服务继续运行）: {exc}')
                time.sleep(1)
        except KeyboardInterrupt:
            log_service_stop(logger, 'device_param_history 清理服务')
            self.stdout.write('[dph_cleanup] 已停止')

    # ------------------------------------------------------------------
    # 核心清理逻辑
    # ------------------------------------------------------------------

    def _run_cleanup(self, days: int, batch_size: int, sleep_ms: int, dry_run: bool):
        """
        按主键 id 小步分批删除超出保留窗口的记录。

        策略：
          1. 用 collected_at 索引（单列，db_index=True）确定待删截止 id，
             避免使用无索引的 created_at 导致全表扫描。
          2. 每次 DELETE ... WHERE id >= :batch_start AND id <= :cutoff_id LIMIT batch_size
             — 利用主键范围扫描，每批产生的 undo log 可控。
          3. 两批之间 sleep sleep_ms 毫秒，让磁盘 I/O 和复制延迟有喘息空间。

        安全说明：
          device_param_history.collected_at 有单列索引（db_index=True）。
          device_param_history.created_at   无独立索引——禁止在 WHERE 子句中单独过滤。
          所有时间边界查询均使用 collected_at，保证走索引。

        异常处理：
          捕获 OperationalError（MySQL Lost connection / server gone away）和所有其他异常，
          记录完整错误日志后 return（不重新抛出），防止异常冲出调用方的 while True 调度循环
          导致进程崩溃。systemd Restart=on-failure 作为最终兜底。
        """
        cutoff_dt = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')

        self.stdout.write(
            f'[dph_cleanup] 开始清理 device_param_history，'
            f'保留 {days} 天，截止时间 = {cutoff_str}（基于 collected_at），'
            f'batch_size={batch_size}，dry_run={dry_run}'
        )

        try:
            with connection.cursor() as cur:
                # Step 1: 找出待删除的边界 id
                # 用 collected_at 索引做 backward index scan + LIMIT 1，只读 1 行即返回，
                # 避免 MAX(id) 聚合扫描整个 collected_at 索引区间（1700 万+ 行，
                # 会在仅 128MB 缓冲池的生产库上跑数十秒并触发 "Lost connection"）。
                # collected_at 与自增 id 单调相关，取「collected_at < cutoff 中
                # collected_at 最大的那行」的 id 作为删除上界已足够；
                # Step 3 的 DELETE 仍带 collected_at < cutoff 兜底，绝不会误删保留期数据。
                cur.execute(
                    'SELECT id FROM device_param_history '
                    'WHERE collected_at < %s '
                    'ORDER BY collected_at DESC LIMIT 1',
                    [cutoff_str],
                )
                row = cur.fetchone()
                max_delete_id = row[0] if row and row[0] is not None else None

                if max_delete_id is None:
                    self.stdout.write('[dph_cleanup] 无需删除（保留窗口内没有超期数据）')
                    log_task_completion(logger, 'dph_cleanup', {'deleted': 0, 'reason': '无超期数据'})
                    return

                # Step 2: 找出当前最小 id（主键 MIN，走主键索引，极快）
                cur.execute('SELECT MIN(id) FROM device_param_history')
                min_row = cur.fetchone()
                min_id = min_row[0] if min_row and min_row[0] is not None else 1

                self.stdout.write(
                    f'[dph_cleanup] 待删 id 范围: [{min_id}, {max_delete_id}]，'
                    f'预计约 {max_delete_id - min_id + 1} 行（含已保留行，实删行数取决于 collected_at）'
                )

                if dry_run:
                    # 演练：用 id 跨度估算待删行数，不做 COUNT(*) 扫描。
                    # COUNT(*) WHERE id<=max_delete_id 要扫 2000 万+ 聚簇索引行，
                    # 在 128MB 缓冲池的库上同样会超时断连；
                    # id 为自增主键、近似连续，(max_delete_id - min_id + 1) 是删除量的良好估计。
                    estimated = max_delete_id - min_id + 1
                    estimated_batches = (estimated + batch_size - 1) // batch_size if estimated > 0 else 0
                    self.stdout.write(
                        f'[dph_cleanup][DRY-RUN] 预计删除约 {estimated} 行'
                        f'（id 区间 [{min_id}, {max_delete_id}]，collected_at < {cutoff_str}；'
                        f'按 id 跨度估算，未做 COUNT 扫描），'
                        f'预计批次数 约 {estimated_batches}（batch_size={batch_size}）'
                    )
                    log_task_completion(logger, 'dph_cleanup dry-run', {
                        'estimated_rows': estimated,
                        'estimated_batches': estimated_batches,
                        'cutoff_collected_at': cutoff_str,
                        'max_delete_id': max_delete_id,
                        'min_id': min_id,
                    })
                    return

                # Step 3: 分批删除（collected_at < cutoff，主键范围推进）
                total_deleted = 0
                batch_num = 0
                current_min = min_id

                while current_min <= max_delete_id:
                    batch_num += 1
                    # 每批按主键范围删，同时过滤 collected_at 保证只删超期数据
                    # MySQL 走主键扫描（id 范围），undo log 可控
                    cur.execute(
                        '''DELETE FROM device_param_history
                           WHERE id >= %s AND id <= %s
                             AND collected_at < %s
                           LIMIT %s''',
                        [current_min, max_delete_id, cutoff_str, batch_size],
                    )
                    deleted_in_batch = cur.rowcount

                    if deleted_in_batch == 0:
                        # 该范围内全是保留期内数据（collected_at >= cutoff），跳出
                        break

                    total_deleted += deleted_in_batch
                    self.stdout.write(
                        f'[dph_cleanup] 批次 {batch_num}: 删除 {deleted_in_batch} 行，'
                        f'累计删除 {total_deleted} 行'
                    )
                    logger.info(
                        f'dph_cleanup batch={batch_num} deleted={deleted_in_batch} total={total_deleted}'
                    )

                    # 推进到下一批起始 id
                    # 当 rowcount < batch_size 时该段已删完，步进 batch_size 避免重复扫
                    if deleted_in_batch < batch_size:
                        current_min += batch_size

                    # 批次间休眠
                    if sleep_ms > 0:
                        time.sleep(sleep_ms / 1000.0)

            self.stdout.write(
                f'[dph_cleanup] 完成，共删除 {total_deleted} 行，共 {batch_num} 批次'
            )
            log_task_completion(logger, 'dph_cleanup', {
                'total_deleted': total_deleted,
                'batches': batch_num,
                'cutoff_collected_at': cutoff_str,
            })

        except OperationalError as exc:
            # MySQL "Lost connection to MySQL server during query" (errno 2013)
            # 或 "MySQL server has gone away" (errno 2006)。
            # 在表膨胀（3600 万行 / 11.6 GB）+ InnoDB buffer pool 仅 128 MB 的生产环境下，
            # Step 1 的边界查询可能阻塞 100s+ 后触发服务端连接超时。
            # 捕获后记录错误并 return，不重新抛出，防止异常冲出 cron 模式的 while True 主循环
            # 导致整个 dph_cleanup_service 进程崩溃。
            # systemd Restart=on-failure / RestartSec=30s 是进程崩溃时的最终兜底。
            err_msg = (
                f'[dph_cleanup] DB OperationalError（可能为 MySQL Lost connection 或超时）: {exc}。'
                f'本次清理轮次中止，等待下次调度。'
                f'根因：device_param_history 表膨胀导致边界查询超时；'
                f'建议缩表或调大 innodb_buffer_pool_size。'
            )
            log_error(logger, 'dph_cleanup OperationalError', exc)
            self.stderr.write(err_msg)
            # 关闭已损坏的数据库连接，避免后续请求复用坏连接
            connection.close()

        except Exception as exc:
            # 捕获所有其他未预期异常，同样防止进程崩溃
            err_msg = f'[dph_cleanup] 未预期异常: {exc}，本次清理轮次中止。'
            log_error(logger, 'dph_cleanup unexpected error', exc)
            self.stderr.write(err_msg)
            connection.close()

    # ------------------------------------------------------------------
    # 调度配置
    # ------------------------------------------------------------------

    def _setup_schedule(self, cron_expr: str, days: int, batch_size: int,
                        sleep_ms: int, dry_run: bool):
        """解析 cron 表达式，注册调度任务。仅支持简单数字 + * 通配格式。"""
        try:
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                raise ValueError('cron 表达式格式不正确，应为 "分 时 日 月 周"')

            minute_s, hour_s, _day, _month, weekday_s = parts
            scheduled_time = f'{int(hour_s):02d}:{int(minute_s):02d}'

            weekday_map = {
                '*': None,
                '0': 'sunday', '7': 'sunday',
                '1': 'monday', '2': 'tuesday', '3': 'wednesday',
                '4': 'thursday', '5': 'friday', '6': 'saturday',
            }

            def job():
                self._run_cleanup(days, batch_size, sleep_ms, dry_run)

            if weekday_s == '*':
                schedule.every().day.at(scheduled_time).do(job)
                self.stdout.write(f'[dph_cleanup] 调度: 每天 {scheduled_time}')
            elif weekday_s in weekday_map:
                day_name = weekday_map[weekday_s]
                getattr(schedule.every(), day_name).at(scheduled_time).do(job)
                self.stdout.write(f'[dph_cleanup] 调度: 每{day_name} {scheduled_time}')
            else:
                raise ValueError(f'不支持的星期值: {weekday_s}')

        except Exception as e:
            log_warning(logger, f'cron 解析失败: {e}，退回默认 每天 03:00')
            self.stdout.write(f'[dph_cleanup] cron 解析失败: {e}，使用默认每天 03:00')

            def job():
                self._run_cleanup(days, batch_size, sleep_ms, dry_run)

            schedule.every().day.at('03:00').do(job)
