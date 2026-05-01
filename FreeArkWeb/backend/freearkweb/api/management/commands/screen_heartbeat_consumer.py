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
"""

import logging
import os
import sys
import time
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模块级常量
# ---------------------------------------------------------------------------

MQTT_HOST = '47.117.41.184'
MQTT_PORT = 11883
MQTT_USERNAME = 'admin'
MQTT_PASSWORD = 'public'
MQTT_TOPIC = '/screen/upload/screen/to/cloud/#'
MQTT_CLIENT_ID = 'freeark-screen-heartbeat'

# MAC → specific_part 缓存刷新间隔（秒）
CACHE_REFRESH_INTERVAL = 300  # 5 分钟


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

        mac_cache = MacCache()

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info('已连接 Broker %s:%d，订阅 %s', MQTT_HOST, MQTT_PORT, MQTT_TOPIC)
                client.subscribe(MQTT_TOPIC)
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

        client = mqtt.Client(client_id=MQTT_CLIENT_ID)
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

        logger.info(
            'screen_heartbeat_consumer 启动，连接 %s:%d，topic=%s',
            MQTT_HOST, MQTT_PORT, MQTT_TOPIC,
        )

        # loop_forever 内置断线重连（retry_first_connection=True 确保首次连接也重试）
        client.loop_forever(retry_first_connection=True)
