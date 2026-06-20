"""
fault_consumer — 故障事件 MQTT 消费者（MOD-BE-FM-04，v0.6.0-FM）

Django Management Command，由 freeark-fault-consumer.service 管理。
运行方式：python manage.py fault_consumer

功能：
  1. 加载 broker 配置（复用 heartbeat_broker_config.json，独立 client_id）
  2. 启动时从 DB 重建进程内状态机
  3. 建立 paho-mqtt WSS 连接，订阅 /screen/upload/screen/to/cloud/+
  4. 解析 DeviceStatusUpdate 报文，驱动故障状态机（T1/T2/T3）
  5. loop_forever(retry_first_connection=True) 持续运行，systemd 托管重启

设计约束（ADR-FM-01）：
  - 独立于 freeark-screen-heartbeat，client_id='freeark-fault-consumer'
  - paho-mqtt 1.x API（与 screen_heartbeat_consumer 相同模式）
  - broker 密码不输出到日志（仅记录 host/port/protocol）
  - 报文内容截断前 256 字节后才记录 DEBUG 日志
"""

import json
import logging
import os
import time
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置文件路径（与 screen_heartbeat_consumer 相同路径）
# ---------------------------------------------------------------------------
# 本文件位于：backend/freearkweb/api/management/commands/
# dirname×5  → backend/
_HBC_CONFIG_PATH = os.path.join(
    os.path.dirname(
    os.path.dirname(
    os.path.dirname(
    os.path.dirname(
    os.path.dirname(
    os.path.abspath(__file__)))))),
    'heartbeat_broker_config.json',
)

_FALLBACK_CONFIG: dict = {
    'protocol': 'wss',
    'host': 'www.ttqingjiao.site',
    'port': 8084,
    'path': '/mqtt',
    'username': 'admin',
    'password': 'public',
    'topic': '/screen/upload/screen/to/cloud/#',
    'client_id': 'freeark-screen-heartbeat',
    'keepalive': 60,
    'fault_consumer_topic': '/screen/upload/screen/to/cloud/+',
    'fault_consumer_use_mac_list': False,
}

# MAC → specific_part 缓存刷新间隔（秒），与心跳服务一致
CACHE_REFRESH_INTERVAL = 300


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

def _load_fault_consumer_config() -> dict:
    """从 heartbeat_broker_config.json 加载配置，不存在时降级使用 fallback。"""
    try:
        with open(_HBC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        logger.info(
            '_load_fault_consumer_config: 已加载配置文件 protocol=%s host=%s port=%s',
            cfg.get('protocol'), cfg.get('host'), cfg.get('port'),
        )
        return cfg
    except FileNotFoundError:
        logger.warning(
            '_load_fault_consumer_config: 配置文件未找到 (%s)，使用默认配置',
            _HBC_CONFIG_PATH,
        )
        return dict(_FALLBACK_CONFIG)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            '_load_fault_consumer_config: 配置文件读取失败，使用默认配置: %s', exc,
        )
        return dict(_FALLBACK_CONFIG)


# ---------------------------------------------------------------------------
# MAC → specific_part 缓存（独立于心跳服务，不共享状态）
# ---------------------------------------------------------------------------

class _MacCache:
    """内存缓存：mac_str → specific_part，定期从 DB 刷新。"""

    def __init__(self):
        self._cache: dict = {}
        self._last_refresh: float = 0.0

    def _refresh(self):
        from api.models import OwnerInfo
        close_old_connections()
        try:
            mapping = {
                row['unique_id']: row['specific_part']
                for row in OwnerInfo.objects.filter(
                    unique_id__isnull=False
                ).exclude(unique_id='').values('unique_id', 'specific_part')
            }
            self._cache = mapping
            self._last_refresh = time.time()
            logger.info('_MacCache: 刷新完成，共 %d 条映射', len(self._cache))
        except Exception as exc:
            logger.warning('_MacCache: 刷新失败，继续使用旧缓存: %s', exc)

    def get_specific_part(self, mac: str) -> Optional[str]:
        if time.time() - self._last_refresh > CACHE_REFRESH_INTERVAL:
            self._refresh()
        return self._cache.get(mac)


# ---------------------------------------------------------------------------
# 报文处理
# ---------------------------------------------------------------------------

def _handle_message(msg, mac_cache: _MacCache) -> None:
    """解析单条 MQTT 消息并驱动故障状态机。

    解析流程（ADR-FM-04 §4.1，hotfix BUG-FM-002 后实际报文字段）：
      1. JSON 解析，验证 header.name == "DeviceStatusUpdate"
      2. MAC → specific_part 映射（topic 末段或 header.screenMac）
      3. 从 payload.data 提取 deviceSn, productCode
      4. 遍历 items[]，对每个 fault_candidate 字段（attrTag）调用状态机

    实际报文结构（生产 EMQX 实测）：
      {"header": {"name": "DeviceStatusUpdate", "screenMac": "<mac>"},
       "payload": {"code": 200,
                   "data": {"deviceSn": <int>, "productCode": <int>,
                            "items": [{"attrTag": "<name>", "attrValue": "<v>"}]}}}
    """
    from api.fault_consumer.fault_classifier import (
        is_fault_candidate,
        is_fault_active,
        get_fault_type_and_severity,
        get_fault_message,
    )
    from api.fault_consumer.state_machine import process_fault_field

    received_at = timezone.now()

    # 1. JSON 解析
    try:
        root = json.loads(msg.payload.decode('utf-8', errors='replace'))
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning('JSON 解析失败，跳过: topic=%s err=%s', msg.topic, exc)
        return

    # 2. 验证报文类型
    header = root.get('header') or {}
    if header.get('name') != 'DeviceStatusUpdate':
        logger.debug('非 DeviceStatusUpdate 报文，跳过: topic=%s name=%s',
                     msg.topic, header.get('name'))
        return

    # 3. MAC → specific_part（优先 topic 末段，回退 header.screenMac）
    topic_parts = msg.topic.rstrip('/').split('/')
    mac = topic_parts[-1] if topic_parts else ''
    if not mac:
        mac = str(header.get('screenMac', '') or '')
    if not mac:
        logger.warning('无法解析 MAC: topic=%s', msg.topic)
        return

    specific_part = mac_cache.get_specific_part(mac)
    if specific_part is None:
        logger.debug('未找到 mac=%s 对应的 specific_part，跳过', mac)
        return

    # 4. 提取设备信息（嵌套在 root.payload.data 中，非 root.data）
    payload_obj = root.get('payload') or {}
    data = payload_obj.get('data') or {}
    # 兼容旧测试结构：若 root.data 存在则回退使用（仅老格式有效）
    if not data and 'data' in root:
        data = root.get('data') or {}
    device_sn = str(data.get('deviceSn', '') or '')
    product_code = str(data.get('productCode', '') or '')
    items = data.get('items') or []

    if not device_sn:
        logger.debug('报文缺少 deviceSn，跳过: topic=%s', msg.topic)
        return

    # 5. 遍历 items，处理故障字段（实际字段名 attrTag/attrValue）
    for item in items:
        if not isinstance(item, dict):
            continue
        # 优先 attrTag/attrValue（生产实际格式），回退 paramName/value（旧测试格式）
        param_name = str(item.get('attrTag') or item.get('paramName') or '')
        value = item.get('attrValue') if 'attrValue' in item else item.get('value')

        if not param_name:
            continue
        if not is_fault_candidate(param_name):
            continue

        active_now = is_fault_active(param_name, value)
        fault_type, severity = get_fault_type_and_severity(param_name)
        fault_msg = get_fault_message(param_name)

        try:
            process_fault_field(
                specific_part=specific_part,
                device_sn=device_sn,
                product_code=product_code,
                fault_code=param_name,
                fault_type=fault_type,
                severity=severity,
                fault_message=fault_msg,
                is_active_now=active_now,
                received_at=received_at,
            )
        except Exception as exc:
            logger.exception('process_fault_field 异常: param=%s err=%s', param_name, exc)


# ---------------------------------------------------------------------------
# Management Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = '故障事件 MQTT 消费者（freeark-fault-consumer）'

    def handle(self, *args, **options):
        import paho.mqtt.client as mqtt

        # 1. 加载配置
        cfg = _load_fault_consumer_config()
        protocol  = cfg.get('protocol', 'wss')
        host      = cfg.get('host', 'www.ttqingjiao.site')
        port      = int(cfg.get('port', 8084))
        path      = cfg.get('path', '/mqtt')
        username  = cfg.get('username', 'admin')
        password  = cfg.get('password', 'public')
        keepalive = int(cfg.get('keepalive', 60))
        # fault_consumer 使用固定 client_id，避免误用心跳服务 client_id
        client_id = 'freeark-fault-consumer'
        topic = cfg.get('fault_consumer_topic', '/screen/upload/screen/to/cloud/+')

        logger.info(
            'fault_consumer 启动: protocol=%s host=%s port=%s topic=%s',
            protocol, host, port, topic,
        )

        # 2. 重建状态机
        from api.fault_consumer.state_machine import rebuild_from_db, get_counters
        count = rebuild_from_db()
        logger.info('fault_consumer 状态机重建完成，活跃故障 %d 条', count)

        # 2.5 启动自愈看门狗（P0 防复发，2026-06-16 静默停写事故）
        from api.fault_consumer.watchdog import start_watchdog_thread
        start_watchdog_thread(get_counters)

        # 3. 初始化 MacCache
        mac_cache = _MacCache()

        # 4. paho-mqtt 回调
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info('已连接 Broker %s:%d，订阅 %s', host, port, topic)
                client.subscribe(topic)
            else:
                logger.warning('Broker 连接失败，rc=%d', rc)

        def on_message(client, userdata, msg):
            try:
                _handle_message(msg, mac_cache)
            except Exception as exc:
                logger.exception('on_message 未处理异常: %s', exc)

        def on_disconnect(client, userdata, rc):
            if rc != 0:
                logger.warning('与 Broker 断开连接，rc=%d，paho 将自动重连', rc)

        # 5. 初始化 paho client（paho 1.x API，无 CallbackAPIVersion）
        if protocol == 'wss':
            client = mqtt.Client(client_id=client_id, transport='websockets')
            client.tls_set()
            client.ws_set_options(path=path)
            logger.info('使用 wss 传输: %s:%d%s', host, port, path)
        else:
            client = mqtt.Client(client_id=client_id, transport='tcp')
            logger.info('使用 mqtt/tcp 传输: %s:%d', host, port)

        client.username_pw_set(username, password)
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        client.connect(host, port, keepalive)

        # 6. 持续运行（自动重连）
        logger.info('fault_consumer loop_forever 启动')
        client.loop_forever(retry_first_connection=True)
