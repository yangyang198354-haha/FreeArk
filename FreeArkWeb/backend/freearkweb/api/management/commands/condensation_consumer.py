"""
condensation_consumer — 结露预警 MQTT 消费者（MOD-BE-CW-03，v0.7.0-CW）

Django Management Command，由 freeark-condensation-consumer.service 管理。
运行方式：python manage.py condensation_consumer

镜像 fault_consumer.py 设计（ADR-CW-06），差异：
  - client_id='freeark-condensation-consumer'（固定，不从配置文件读）
  - _handle_message 仅检测 condensation_alarm attrTag，不调用 fault_classifier
  - 同时提取快照字段：dew_point_temp, NTC_temp, humidity, system_switch
  - system_switch 优先级（RISK-CW-ARCH-01 已闭环）：
      * MQTT 直取：items[] 中含 system_switch attrTag → attrValue 已是字符串 "on"/"off"
        （生产抓包 sniff_2860fae9a34ab8a9_20260525_235217.ndjson 已核实）
        → 做 lower() + 规范化（非 "off" 非空 → "on"）
      * PLCLatestData 兜底：state_machine._get_system_switch_for_specific_part
        → value 为整数（0=off，非0=on）
      * 均无 → "unknown"

功能：
  1. 加载配置（复用 heartbeat_broker_config.json，独立 client_id）
  2. 启动时从 DB 重建进程内状态机
  3. 建立 paho-mqtt WSS 连接，订阅 /screen/upload/screen/to/cloud/+
  4. 解析 DeviceStatusUpdate 报文，提取 condensation_alarm 及快照字段，驱动状态机
  5. loop_forever(retry_first_connection=True) 持续运行，systemd 托管重启
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
# 配置文件路径（与 fault_consumer 完全相同路径）
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

# MAC → specific_part 缓存刷新间隔（秒），与 fault_consumer 一致
CACHE_REFRESH_INTERVAL = 300

# condensation_alarm attrTag 名称
_CONDENSATION_ALARM_TAG = 'condensation_alarm'

# 快照字段 attrTag 映射（attrTag → Python 字段名）
_SNAPSHOT_TAGS = {
    'dew_point_temp': 'dew_point_temp',
    'NTC_temp': 'ntc_temp',       # 大屏上报 NTC_temp（大写 NTC），映射到 ntc_temp 字段
    'ntc_temp': 'ntc_temp',       # 容错兼容小写
    'humidity': 'humidity',
}


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

def _load_condensation_consumer_config() -> dict:
    """从 heartbeat_broker_config.json 加载配置，不存在时降级使用 fallback。"""
    try:
        with open(_HBC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        logger.info(
            '_load_condensation_consumer_config: 已加载配置文件 protocol=%s host=%s port=%s',
            cfg.get('protocol'), cfg.get('host'), cfg.get('port'),
        )
        return cfg
    except FileNotFoundError:
        logger.warning(
            '_load_condensation_consumer_config: 配置文件未找到 (%s)，使用默认配置',
            _HBC_CONFIG_PATH,
        )
        return dict(_FALLBACK_CONFIG)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            '_load_condensation_consumer_config: 配置文件读取失败，使用默认配置: %s', exc,
        )
        return dict(_FALLBACK_CONFIG)


# ---------------------------------------------------------------------------
# MAC → specific_part 缓存（独立于 fault_consumer，不共享状态）
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
# system_switch 规范化（MQTT 直取路径，RISK-CW-ARCH-01 闭环）
# ---------------------------------------------------------------------------

def _normalize_system_switch_from_mqtt(raw_value) -> str:
    """将 MQTT items[] 中直取的 system_switch attrValue 规范化为 "on"/"off"/"unknown"。

    生产抓包已核实（sniff_2860fae9a34ab8a9_20260525_235217.ndjson）：
      - 260001 等水力模块同报文含 system_switch 时，attrValue 已是字符串 "on" 或 "off"
      - 做 lower() 容错（防止 "ON"/"OFF" 大写变体）

    规范化规则：
      - None / "" / 空白 → "unknown"
      - lower() == "off" → "off"
      - lower() == "on"  → "on"
      - 其他非空字符串   → "on"（保守处理：非 off 即 on，记 WARNING）
    """
    if raw_value is None:
        return 'unknown'
    s = str(raw_value).strip().lower()
    if not s:
        return 'unknown'
    if s == 'off':
        return 'off'
    if s == 'on':
        return 'on'
    # 非预期值（如 "0"/"1"）：非 "off" 非空 → "on"，记警告
    logger.warning(
        '_normalize_system_switch_from_mqtt: 非预期值 %r，按 "on" 处理（已核实生产格式为 on/off）',
        raw_value,
    )
    return 'on'


# ---------------------------------------------------------------------------
# 报文处理
# ---------------------------------------------------------------------------

def _handle_message(msg, mac_cache: _MacCache) -> None:
    """解析单条 MQTT 消息并驱动结露预警状态机。

    解析流程：
      1. JSON 解析，验证 header.name == "DeviceStatusUpdate"
      2. topic 末段取 MAC → mac_cache.get_specific_part(mac) → specific_part
      3. 提取 payload.data: deviceSn, productCode, items[]
      4. 扫描 items[]，寻找 condensation_alarm attrTag
         → 未找到 → 跳过本报文（非结露预警相关报文）
      5. 提取同 deviceSn 的快照字段（dew_point_temp, NTC_temp, humidity, system_switch）
      6. system_switch 优先级（RISK-CW-ARCH-01）：
         a. items[] 中有 system_switch attrTag → MQTT 直取（已是 on/off 字符串），做规范化
         b. items[] 中无 system_switch → state_machine 内部调 _get_system_switch_for_specific_part
            （PLCLatestData 方案 A，整数 0/非0 转 off/on）
         c. 均无 → "unknown"（由 state_machine 内部处理，此处传 None 触发路径 b）
      7. is_active_now = int(condensation_alarm_value) != 0
      8. 调用 process_condensation_alarm(...)
    """
    from api.condensation_consumer.state_machine import process_condensation_alarm

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

    # 4. 提取设备信息（嵌套在 root.payload.data 中）
    payload_obj = root.get('payload') or {}
    data = payload_obj.get('data') or {}
    # 兼容旧测试结构
    if not data and 'data' in root:
        data = root.get('data') or {}
    device_sn = str(data.get('deviceSn', '') or '')
    product_code = str(data.get('productCode', '') or '')
    items = data.get('items') or []

    if not device_sn:
        logger.debug('报文缺少 deviceSn，跳过: topic=%s', msg.topic)
        return

    # 5. 扫描 items[]，收集 condensation_alarm 及快照字段
    condensation_alarm_value = None
    dew_point_temp = None
    ntc_temp = None
    humidity = None
    system_switch_raw = None       # None 表示 items[] 中未找到 system_switch
    system_switch_found = False    # 标记是否从 MQTT 直取到 system_switch

    for item in items:
        if not isinstance(item, dict):
            continue
        attr_tag = str(item.get('attrTag') or item.get('paramName') or '')
        attr_value = item.get('attrValue') if 'attrValue' in item else item.get('value')

        if attr_tag == _CONDENSATION_ALARM_TAG:
            condensation_alarm_value = str(attr_value) if attr_value is not None else None
        elif attr_tag in _SNAPSHOT_TAGS:
            field = _SNAPSHOT_TAGS[attr_tag]
            if field == 'dew_point_temp' and attr_value is not None:
                dew_point_temp = str(attr_value)
            elif field == 'ntc_temp' and attr_value is not None:
                ntc_temp = str(attr_value)
            elif field == 'humidity' and attr_value is not None:
                humidity = str(attr_value)
        elif attr_tag == 'system_switch':
            # MQTT 直取路径（RISK-CW-ARCH-01 闭环）：
            # 生产抓包核实 260001 同报文 system_switch attrValue 为 "on"/"off" 字符串
            system_switch_raw = attr_value
            system_switch_found = True

    # 6. 检查是否有 condensation_alarm 字段（不含此字段则跳过）
    if condensation_alarm_value is None:
        logger.debug(
            '报文不含 condensation_alarm，跳过: topic=%s device_sn=%s product_code=%s',
            msg.topic, device_sn, product_code,
        )
        return

    # 7. 计算 is_active_now
    try:
        is_active_now = int(float(condensation_alarm_value)) != 0
    except (ValueError, TypeError):
        logger.warning(
            'condensation_alarm_value 无法转为数字，按正常态处理: value=%r device_sn=%s',
            condensation_alarm_value, device_sn,
        )
        is_active_now = False

    # 8. system_switch 规范化（MQTT 直取路径）
    # RISK-CW-ARCH-01：MQTT 直取的 attrValue 是 "on"/"off" 字符串，做 lower() 容错
    # 若 items[] 中无 system_switch → 传 None，state_machine 内部走 PLCLatestData 方案 A
    system_switch = None
    if system_switch_found:
        system_switch = _normalize_system_switch_from_mqtt(system_switch_raw)
        logger.debug(
            'system_switch MQTT 直取: device_sn=%s raw=%r normalized=%s',
            device_sn, system_switch_raw, system_switch,
        )
    # system_switch_found=False 时传 None，state_machine._t1_insert 内部调用 _get_system_switch_for_specific_part

    # 9. 驱动状态机
    logger.debug(
        '_handle_message: specific_part=%s device_sn=%s product_code=%s '
        'condensation_alarm=%s is_active=%s system_switch=%s',
        specific_part, device_sn, product_code,
        condensation_alarm_value, is_active_now, system_switch,
    )

    try:
        process_condensation_alarm(
            specific_part=specific_part,
            device_sn=device_sn,
            product_code=product_code,
            is_active_now=is_active_now,
            received_at=received_at,
            condensation_alarm_value=condensation_alarm_value,
            dew_point_temp=dew_point_temp,
            ntc_temp=ntc_temp,
            humidity=humidity,
            system_switch=system_switch,
        )
    except Exception as exc:
        logger.exception('process_condensation_alarm 异常: device_sn=%s err=%s', device_sn, exc)


# ---------------------------------------------------------------------------
# Management Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = '结露预警 MQTT 消费者（freeark-condensation-consumer）'

    def handle(self, *args, **options):
        import paho.mqtt.client as mqtt

        # 1. 加载配置
        cfg = _load_condensation_consumer_config()
        protocol  = cfg.get('protocol', 'wss')
        host      = cfg.get('host', 'www.ttqingjiao.site')
        port      = int(cfg.get('port', 8084))
        path      = cfg.get('path', '/mqtt')
        username  = cfg.get('username', 'admin')
        password  = cfg.get('password', 'public')
        keepalive = int(cfg.get('keepalive', 60))
        # 固定 client_id，不从配置文件读（防误用 fault_consumer 或心跳服务 client_id）
        client_id = 'freeark-condensation-consumer'
        topic = cfg.get('fault_consumer_topic', '/screen/upload/screen/to/cloud/+')

        logger.info(
            'condensation_consumer 启动: protocol=%s host=%s port=%s topic=%s',
            protocol, host, port, topic,
        )

        # 2. 重建状态机
        from api.condensation_consumer.state_machine import rebuild_from_db, get_counters
        count = rebuild_from_db()
        logger.info('condensation_consumer 状态机重建完成，活跃预警 %d 条', count)

        # 2.5 启动自愈看门狗（P0 防复发，2026-06-16 静默停写事故）
        from api.condensation_consumer.watchdog import start_watchdog_thread
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

        # 5. 初始化 paho client（paho 1.x API，与 fault_consumer 相同模式）
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
        logger.info('condensation_consumer loop_forever 启动')
        client.loop_forever(retry_first_connection=True)
