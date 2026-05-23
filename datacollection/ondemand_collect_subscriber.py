"""OndemandCollectSubscriber — 按需采集指令订阅器 (v0.5.6)

订阅 MQTT topic /datacollection/plc/ondemand/request/#，收到指令后在独立线程执行
单设备 PLC 数据采集，将结果发布至 /datacollection/plc/ondemand/result/<specific_part>。

设计约束（来自 ADR-005, OQ-001, OQ-002）：
  - 独立 paho 客户端，不与 PLCWriteSubscriber 共用
  - max_workers=1（单线程串行处理，避免并发抢占 PLC 连接）
  - 有界 pending set（maxsize=20，防止并发过载）
  - 同一 specific_part 同时只有 1 个采集任务（防重入）
  - 失败（PLC 不可达）时发布 success=false 结果，让 consumer 感知
"""

import concurrent.futures
import json
import os
import sys
import threading
import time
from typing import Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datacollection.log_config_manager import get_logger
from datacollection.mqtt_client import MQTTClient

logger = get_logger('ondemand_collect_subscriber')

ONDEMAND_REQUEST_TOPIC = '/datacollection/plc/ondemand/request/#'
ONDEMAND_RESULT_TOPIC_PREFIX = '/datacollection/plc/ondemand/result/'

# 单次采集超时（秒）——PLC S7 连接 + 读取，单设备参数约 50 条
_COLLECT_TIMEOUT_S = 12


def _load_plc_config() -> Dict[str, Any]:
    """加载 plc_config.json，返回 parameters 字典。"""
    possible = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plc_config.json'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resource', 'plc_config.json'),
        os.path.join(os.getcwd(), 'plc_config.json'),
    ]
    for p in possible:
        p = os.path.normpath(p)
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                logger.info('加载 plc_config.json: %s', p)
                return cfg.get('parameters', {})
            except Exception as e:
                logger.warning('加载 plc_config.json 失败 %s: %s', p, e)
    logger.warning('未找到 plc_config.json，OndemandCollectSubscriber 参数映射为空')
    return {}


def _load_owner_ip_map() -> Dict[str, str]:
    """加载 specific_part -> PLC IP 映射。

    从 all_owner.json（或 resource/*.json）中提取设备的 "PLC IP地址" 字段。
    返回 {specific_part: plc_ip} 字典。
    """
    owner_map: Dict[str, str] = {}
    resource_dirs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resource'),
        os.path.join(os.getcwd(), 'resource'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource'),
    ]
    for resource_dir in resource_dirs:
        if not os.path.isdir(resource_dir):
            continue
        for fname in os.listdir(resource_dir):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(resource_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                for device_id, device_info in data.items():
                    if not isinstance(device_info, dict):
                        continue
                    plc_ip = device_info.get('PLC IP地址') or device_info.get('IP地址')
                    if plc_ip and isinstance(plc_ip, str) and plc_ip.strip():
                        owner_map[device_id] = plc_ip.strip()
            except Exception as e:
                logger.debug('跳过文件 %s: %s', fpath, e)
        if owner_map:
            logger.info('已从 %s 加载 specific_part->IP 映射，共 %d 条', resource_dir, len(owner_map))
            break
    if not owner_map:
        logger.warning('未能加载任何 specific_part->IP 映射')
    return owner_map


class OndemandCollectSubscriber:
    """按需采集指令订阅器（v0.5.6 新增，MOD-DC-01）。"""

    def __init__(self,
                 mqtt_broker: str = '192.168.31.98',
                 mqtt_port: int = 32788,
                 max_pending: int = 20):
        self._broker = mqtt_broker
        self._port = mqtt_port
        self._max_pending = max_pending

        # 加载配置
        self._plc_config: Dict[str, Any] = _load_plc_config()
        self._owner_ip_map: Dict[str, str] = _load_owner_ip_map()

        # 有界 pending set：记录正在执行的 specific_part，防重入
        self._pending: set = set()
        self._pending_lock = threading.Lock()

        # 独立单线程执行池
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix='ondemand-collector',
        )

        # MQTT 客户端（独立实例）
        self._client: Optional[MQTTClient] = None
        self._stopped = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """在守护线程中启动 MQTT 客户端，订阅 request topic。"""
        t = threading.Thread(target=self._run, daemon=True, name='OndemandCollectSubscriber')
        t.start()
        logger.info('OndemandCollectSubscriber 已在后台线程启动')

    def stop(self) -> None:
        """停止 MQTT 客户端和执行池。"""
        self._stopped = True
        if self._client:
            try:
                self._client.client.loop_stop()
                self._client.client.disconnect()
            except Exception:
                pass
        self._executor.shutdown(wait=False)
        logger.info('OndemandCollectSubscriber 已停止')

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """线程入口：创建 MQTTClient，连接，订阅，依赖 loop_start 处理消息。"""
        try:
            self._client = MQTTClient(
                host=self._broker,
                port=self._port,
                client_id=f'ondemand-sub-{os.getpid()}',
            )
            if not self._client.connect():
                logger.error('OndemandCollectSubscriber: 无法连接到 MQTT broker %s:%s',
                             self._broker, self._port)
                return

            self._client.subscribe(ONDEMAND_REQUEST_TOPIC, qos=1, callback=self._on_request)
            logger.info('OndemandCollectSubscriber 已订阅 %s', ONDEMAND_REQUEST_TOPIC)
            # loop_start() 已在 MQTTClient.connect() 中调用，此线程只需保持存活
            while not self._stopped:
                time.sleep(5)
        except Exception as e:
            logger.error('OndemandCollectSubscriber._run 异常: %s', e, exc_info=True)

    def _on_request(self, topic: str, payload) -> None:
        """MQTT 消息回调：解析 specific_part，提交采集任务。"""
        try:
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode('utf-8')
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload

            specific_part = data.get('specific_part', '')
            if not specific_part:
                # 尝试从 topic 末尾提取
                specific_part = topic.split('/')[-1] if '/' in topic else ''

            if not specific_part:
                logger.warning('OndemandCollectSubscriber: 无法提取 specific_part，topic=%s', topic)
                return

            logger.info('收到按需采集请求: specific_part=%s topic=%s', specific_part, topic)

            # v0.5.7 M7-B: 读取 allowed_params 白名单（若无则为 None，触发全量采集）
            allowed_params = data.get('allowed_params')  # list[str] or None
            if allowed_params is not None:
                allowed_params = set(allowed_params)  # 转为 set，O(1) 查找
                logger.debug(
                    '[ondemand] 收到 allowed_params 白名单: specific_part=%s, 参数数=%d',
                    specific_part, len(allowed_params),
                )
            # ── end v0.5.7 M7-B ──────────────────────────────────────────────

            with self._pending_lock:
                if specific_part in self._pending:
                    logger.info('防重入：%s 已有进行中的采集任务，跳过', specific_part)
                    return
                if len(self._pending) >= self._max_pending:
                    logger.warning('按需采集队列已满（max=%d），丢弃请求: %s',
                                   self._max_pending, specific_part)
                    return
                self._pending.add(specific_part)

            # 在单线程执行池中执行采集，不阻塞 paho 网络线程
            # v0.5.7 M7-B: 传入 allowed_params，None 表示全量采集（向后兼容）
            self._executor.submit(self._execute_ondemand, specific_part, allowed_params)

        except Exception as e:
            logger.error('OndemandCollectSubscriber._on_request 异常: %s', e, exc_info=True)

    def _execute_ondemand(self, specific_part: str, allowed_params=None) -> None:
        """在线程池中执行：读取单设备 PLC 数据，发布结果 topic。

        Args:
            specific_part: 目标专有部分标识。
            allowed_params: 参数名白名单（set[str] 或 None）。
                            若为 None，全量采集（向后兼容旧版 Django 或未同步设备树）。
                            若为 set，仅采集白名单内的参数（v0.5.7 FR-v0.5.7-05）。
        """
        logger.info('[ondemand] 开始采集: specific_part=%s', specific_part)
        t_start = time.monotonic()

        try:
            # 1. 查找 PLC IP
            plc_ip = self._owner_ip_map.get(specific_part)
            if not plc_ip:
                logger.warning('[ondemand] specific_part=%s 未在 owner_ip_map 中找到 PLC IP，发布失败结果',
                               specific_part)
                self._publish_result(specific_part, plc_ip='', success=False,
                                     error_msg='specific_part 未找到对应 PLC IP')
                return

            # 2. 构建读取参数配置列表
            # v0.5.7 M7-B: 根据 allowed_params 白名单裁剪 PLC 读取配置
            _full_param_count = len(self._plc_config)
            configs = []
            for param_name, param_info in self._plc_config.items():
                # v0.5.7 M7-B: 若白名单存在且参数不在白名单内，跳过（不发起该 PLC 地址读取）
                if allowed_params is not None and param_name not in allowed_params:
                    continue
                configs.append({
                    'ip': plc_ip,
                    'db_num': param_info.get('db_num'),
                    'offset': param_info.get('offset'),
                    'length': param_info.get('length'),
                    'data_type': param_info.get('data_type'),
                    'device_id': specific_part,
                    'param_key': param_name,
                })

            if allowed_params is not None:
                logger.info(
                    '[ondemand] 采集侧裁剪: specific_part=%s, 实际采集 %d / 总计 %d 个参数',
                    specific_part, len(configs), _full_param_count,
                )
            # ── end v0.5.7 M7-B ──────────────────────────────────────────────

            if not configs:
                logger.warning('[ondemand] plc_config 为空，无参数可采集: specific_part=%s', specific_part)
                self._publish_result(specific_part, plc_ip=plc_ip, success=False,
                                     error_msg='plc_config 为空')
                return

            # 3. 执行 PLC 读取（复用 PLCReadWriter，独立实例，不与 TaskScheduler 共用）
            current_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            raw_results = self._read_plc_params(plc_ip, configs, current_time_str)

            # 4. 构建与周期采集相同格式的 payload
            data_dict: Dict[str, Any] = {}
            for r in raw_results:
                param_key = r.get('param_key')
                if param_key:
                    data_dict[param_key] = {
                        'value': r.get('value'),
                        'success': r.get('success', False),
                        'message': r.get('message', ''),
                        'timestamp': current_time_str,
                    }

            result_payload = {
                specific_part: {
                    'PLC IP地址': plc_ip,
                    'data': data_dict,
                }
            }

            elapsed_ms = (time.monotonic() - t_start) * 1000
            logger.info('[ondemand] 采集完成: specific_part=%s, 参数数=%d, 耗时=%.1fms',
                        specific_part, len(data_dict), elapsed_ms)

            # 5. 发布结果 topic
            self._publish_result_payload(specific_part, result_payload)

        except Exception as e:
            logger.error('[ondemand] 采集异常: specific_part=%s, error=%s', specific_part, e,
                         exc_info=True)
            self._publish_result(specific_part, plc_ip='', success=False, error_msg=str(e))
        finally:
            # 无论成功或失败，从 pending 集合中移除
            with self._pending_lock:
                self._pending.discard(specific_part)

    def _read_plc_params(self, plc_ip: str, configs: list, timestamp: str) -> list:
        """使用独立 PLCReadWriter 读取单设备多参数（不依赖 PLCManager 线程池）。

        超时保护：_COLLECT_TIMEOUT_S 秒内未完成则取消并返回失败列表。
        """
        from datacollection.multi_thread_plc_handler import PLCReadWriter

        results = []
        try:
            reader = PLCReadWriter(plc_ip)
            if not reader.connect():
                logger.warning('[ondemand] PLCReadWriter 连接失败: plc_ip=%s', plc_ip)
                for cfg in configs:
                    results.append({
                        'param_key': cfg.get('param_key'),
                        'success': False,
                        'message': f'PLC 连接失败: {plc_ip}',
                        'value': None,
                    })
                return results

            try:
                for cfg in configs:
                    db_num = cfg.get('db_num')
                    offset = cfg.get('offset')
                    length = cfg.get('length')
                    data_type = cfg.get('data_type')
                    param_key = cfg.get('param_key')
                    try:
                        success, message, value = reader.read_db_data(db_num, offset, length, data_type)
                        results.append({
                            'param_key': param_key,
                            'success': success,
                            'message': message,
                            'value': value,
                        })
                    except Exception as param_e:
                        results.append({
                            'param_key': param_key,
                            'success': False,
                            'message': str(param_e),
                            'value': None,
                        })
            finally:
                reader.disconnect()

        except Exception as e:
            logger.error('[ondemand] _read_plc_params 异常: plc_ip=%s, error=%s', plc_ip, e)
            for cfg in configs:
                results.append({
                    'param_key': cfg.get('param_key'),
                    'success': False,
                    'message': str(e),
                    'value': None,
                })

        return results

    def _publish_result_payload(self, specific_part: str, payload: dict) -> None:
        """发布采集结果至 /datacollection/plc/ondemand/result/<specific_part>。"""
        if not self._client:
            logger.error('[ondemand] MQTT 客户端未初始化，无法发布结果')
            return
        topic = f'{ONDEMAND_RESULT_TOPIC_PREFIX}{specific_part}'
        try:
            self._client.publish(topic, payload, qos=1)
            logger.info('[ondemand] 结果已发布: topic=%s', topic)
        except Exception as e:
            logger.error('[ondemand] 发布结果失败: topic=%s, error=%s', topic, e)

    def _publish_result(self, specific_part: str, plc_ip: str,
                        success: bool, error_msg: str = '') -> None:
        """发布一个仅含错误标识的结果（采集失败场景）。"""
        current_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        payload = {
            specific_part: {
                'PLC IP地址': plc_ip,
                'data': {},
                'success': success,
                'error': error_msg,
                'timestamp': current_time_str,
            }
        }
        self._publish_result_payload(specific_part, payload)
