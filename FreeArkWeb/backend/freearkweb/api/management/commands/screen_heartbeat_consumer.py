"""
screen_heartbeat_consumer — 大屏心跳 MQTT 消费者

订阅公网 Broker 的 /screen/upload/screen/to/cloud/# 主题，
每收到一条消息 → 解析 topic 末段 {mac} → 查找 OwnerInfo.unique_id → upsert
ScreenConnectivityStatus.last_seen_at。

运行方式（由 freeark-screen-heartbeat.service 管理）：
    python manage.py screen_heartbeat_consumer

设计约束：
- 每次 DB 操作前调用 django.db.close_old_connections()，防止长进程连接超时。
- 使用 loop_forever(retry_first_connection=True) 实现自动重连。
- MAC → specific_part 映射缓存在内存中（CACHE_REFRESH_INTERVAL 秒刷新一次）。
- v0.5.9: 连接参数从 heartbeat_broker_config.json 读取，支持 mqtt（TCP）和
  wss（WebSocket over TLS）两种传输协议。文件不存在时降级使用 fallback 常量。
- paho-mqtt 版本固定为 >=1.6.1,<2.0（requirements.txt），使用 1.x API。
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
# 配置文件路径
# ---------------------------------------------------------------------------
# 本文件位于：FreeArkWeb/backend/freearkweb/api/management/commands/
# __file__  = .../backend/freearkweb/api/management/commands/screen_heartbeat_consumer.py
# dirname×1 → .../backend/freearkweb/api/management/commands/
# dirname×2 → .../backend/freearkweb/api/management/
# dirname×3 → .../backend/freearkweb/api/
# dirname×4 → .../backend/freearkweb/
# dirname×5 → .../backend/                ← 配置文件所在目录
# 配置文件：backend/heartbeat_broker_config.json

_HBC_CONFIG_PATH = os.path.join(
    os.path.dirname(   # commands/ → parent
    os.path.dirname(   # management/
    os.path.dirname(   # api/
    os.path.dirname(   # freearkweb/
    os.path.dirname(   # backend/
    os.path.abspath(__file__)))))),
    'heartbeat_broker_config.json',
)

# ---------------------------------------------------------------------------
# Fallback 常量（与升级前硬编码值完全一致，确保零行为变化）
# ---------------------------------------------------------------------------

_FALLBACK_CONFIG: dict = {
    'protocol': 'mqtt',
    'host': '47.117.41.184',
    'port': 11883,
    'path': '/mqtt',
    'username': 'admin',
    'password': 'public',
    'topic': '/screen/upload/screen/to/cloud/#',
    'client_id': 'freeark-screen-heartbeat',
    'keepalive': 60,
}

# MAC → specific_part 缓存刷新间隔（秒）
CACHE_REFRESH_INTERVAL = 300  # 5 分钟


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

def _load_heartbeat_config() -> dict:
    """
    从 heartbeat_broker_config.json 加载 broker 连接配置。
    文件不存在或解析失败时降级使用 _FALLBACK_CONFIG，并记录 WARNING。
    """
    try:
        with open(_HBC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        logger.info(
            '_load_heartbeat_config: 已加载配置文件 protocol=%s host=%s port=%s',
            cfg.get('protocol'), cfg.get('host'), cfg.get('port'),
        )
        return cfg
    except FileNotFoundError:
        logger.warning(
            '_load_heartbeat_config: 配置文件未找到 (%s)，使用默认配置 mqtt/47.117.41.184/11883',
            _HBC_CONFIG_PATH,
        )
        return dict(_FALLBACK_CONFIG)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            '_load_heartbeat_config: 配置文件读取失败 (%s)，使用默认配置: %s',
            _HBC_CONFIG_PATH, exc,
        )
        return dict(_FALLBACK_CONFIG)


# ---------------------------------------------------------------------------
# 缓存管理
# ---------------------------------------------------------------------------

class MacCache:
    """内存缓存：mac_str → specific_part，定期从 DB 刷新。"""

    def __init__(self):
        self._cache: dict = {}
        self._last_refresh: float = 0.0

    def _refresh(self):
        """从 OwnerInfo 全量加载 unique_id → specific_part 映射。"""
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
            logger.info('MacCache: 刷新完成，共 %d 条映射', len(self._cache))
        except Exception as exc:
            logger.warning('MacCache: 刷新失败，继续使用旧缓存: %s', exc)

    def get_specific_part(self, mac: str) -> Optional[str]:
        """查询 mac 对应的 specific_part，必要时刷新缓存。"""
        if time.time() - self._last_refresh > CACHE_REFRESH_INTERVAL:
            self._refresh()
        return self._cache.get(mac)

    def invalidate(self):
        """强制使缓存失效（下次 get 时重新加载）。"""
        self._last_refresh = 0.0


# ---------------------------------------------------------------------------
# 心跳处理
# ---------------------------------------------------------------------------

def _upsert_last_seen(specific_part: str) -> None:
    """upsert ScreenConnectivityStatus.last_seen_at = now()。"""
    from api.models import ScreenConnectivityStatus
    close_old_connections()
    now = timezone.now()
    ScreenConnectivityStatus.objects.update_or_create(
        specific_part=specific_part,
        defaults={'last_seen_at': now},
    )
    logger.debug('心跳写入: specific_part=%s, last_seen_at=%s', specific_part, now)


# ---------------------------------------------------------------------------
# Management Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = '大屏心跳 MQTT 消费者（freeark-screen-heartbeat）'

    def handle(self, *args, **options):
        import paho.mqtt.client as mqtt

        # --- 加载配置（v0.5.9：替换原模块级硬编码常量）---
        cfg = _load_heartbeat_config()
        protocol  = cfg.get('protocol', 'mqtt')
        host      = cfg.get('host', '47.117.41.184')
        port      = int(cfg.get('port', 11883))
        path      = cfg.get('path', '/mqtt')
        username  = cfg.get('username', 'admin')
        password  = cfg.get('password', 'public')
        topic     = cfg.get('topic', '/screen/upload/screen/to/cloud/#')
        client_id = cfg.get('client_id', 'freeark-screen-heartbeat')
        keepalive = int(cfg.get('keepalive', 60))

        mac_cache = MacCache()

        # --- 回调（topic / host / port 引用局部变量，而非硬编码常量）---

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info('已连接 Broker %s:%d，订阅 %s', host, port, topic)
                client.subscribe(topic)
            else:
                logger.warning('Broker 连接失败，rc=%d', rc)

        def on_message(client, userdata, msg):
            """收到心跳消息的回调。

            topic 格式：/screen/upload/screen/to/cloud/{mac}
            """
            try:
                topic_parts = msg.topic.rstrip('/').split('/')
                mac = topic_parts[-1]
                if not mac:
                    logger.debug('忽略空 mac topic: %s', msg.topic)
                    return

                specific_part = mac_cache.get_specific_part(mac)
                if specific_part is None:
                    logger.debug('未找到 mac=%s 对应的 specific_part，跳过', mac)
                    return

                _upsert_last_seen(specific_part)

            except Exception as exc:
                logger.exception('on_message 处理异常: %s', exc)

        def on_disconnect(client, userdata, rc):
            if rc != 0:
                logger.warning('与 Broker 断开连接，rc=%d，paho 将自动重连', rc)

        # --- 根据协议初始化 paho client（paho 1.x API，无 CallbackAPIVersion）---
        if protocol == 'wss':
            client = mqtt.Client(client_id=client_id, transport='websockets')
            # OQ-002: broker 使用受信任 CA（Let's Encrypt），tls_set() 无参数即可
            client.tls_set()
            # wss path（如 "/mqtt"）
            client.ws_set_options(path=path)
            logger.info('使用 wss 传输: %s:%d%s', host, port, path)
        else:
            # protocol == "mqtt"（TCP）
            client = mqtt.Client(client_id=client_id, transport='tcp')
            logger.info('使用 mqtt TCP 传输: %s:%d', host, port)

        if username:
            client.username_pw_set(username, password)

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        client.connect(host, port, keepalive=keepalive)

        logger.info(
            'screen_heartbeat_consumer 启动，连接 %s:%d，topic=%s',
            host, port, topic,
        )

        # loop_forever 内置断线重连（retry_first_connection=True 确保首次连接也重试）
        client.loop_forever(retry_first_connection=True)
