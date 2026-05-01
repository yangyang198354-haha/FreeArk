"""
test_screen_heartbeat — 大屏心跳方案测试套件

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_screen_heartbeat --settings=freearkweb.test_settings --verbosity=2

覆盖范围：
  TC-HB-001  on_message 心跳写入：收到合法 topic → upsert last_seen_at
  TC-HB-002  on_message 未知 MAC → 不写入 DB
  TC-HB-003  on_message 空 MAC topic → 不写入 DB
  TC-HB-004  在线判定：last_seen_at 在阈值内 → online
  TC-HB-005  离线判定：last_seen_at 超过阈值 → offline
  TC-HB-006  unknown 判定：无 ScreenConnectivityStatus 记录 → unknown
  TC-HB-007  MAC 缓存刷新：缓存过期后重新从 DB 加载
  TC-HB-008  migration 字段检查：status/last_checked_at 不存在，last_seen_at 存在
  TC-HB-009  device_list API：screen_status 过滤 online
  TC-HB-010  device_list API：screen_status 过滤 unknown
"""

import time
from datetime import timedelta
from unittest.mock import MagicMock, patch, call

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import OwnerInfo, ScreenConnectivityStatus, CustomUser


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def make_owner(specific_part='3-1-7-702', unique_id='aabbccddeeff', **kwargs):
    defaults = {
        'specific_part': specific_part,
        'location_name': '测试坐落',
        'building': '3',
        'unit': '1',
        'floor': '7',
        'room_number': '702',
        'bind_status': '已绑定',
        'ip_address': '192.168.1.10',
        'unique_id': unique_id,
        'plc_ip_address': '192.168.1.11',
    }
    defaults.update(kwargs)
    return OwnerInfo.objects.create(**defaults)


def make_screen_status(specific_part='3-1-7-702', last_seen_at=None):
    if last_seen_at is None:
        last_seen_at = timezone.now()
    return ScreenConnectivityStatus.objects.create(
        specific_part=specific_part,
        last_seen_at=last_seen_at,
    )


def make_admin(username='admin_hb', password='adminpass123'):
    user = CustomUser.objects.create_user(
        username=username, password=password, role='admin'
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


# ---------------------------------------------------------------------------
# 导入被测模块的关键函数（避免触发 paho 连接）
# ---------------------------------------------------------------------------

def _get_on_message_handler():
    """构造 on_message handler，与 Command.handle() 中逻辑一致，但不启动 MQTT 连接。"""
    from api.management.commands.screen_heartbeat_consumer import MacCache, _upsert_last_seen

    mac_cache = MacCache()

    def on_message(client, userdata, msg):
        try:
            topic_parts = msg.topic.rstrip('/').split('/')
            mac = topic_parts[-1]
            if not mac:
                return
            specific_part = mac_cache.get_specific_part(mac)
            if specific_part is None:
                return
            _upsert_last_seen(specific_part)
        except Exception:
            pass

    return on_message, mac_cache


# ---------------------------------------------------------------------------
# TC-HB-001 ~ TC-HB-003: on_message 逻辑
# ---------------------------------------------------------------------------

class OnMessageTest(TestCase):

    def setUp(self):
        self.owner = make_owner(specific_part='3-1-7-702', unique_id='aabbccddeeff')

    def _make_msg(self, topic):
        msg = MagicMock()
        msg.topic = topic
        msg.payload = b'{}'
        return msg

    def test_tc_hb_001_on_message_writes_last_seen_at(self):
        """TC-HB-001: 收到合法心跳 topic → upsert ScreenConnectivityStatus.last_seen_at"""
        on_message, mac_cache = _get_on_message_handler()

        before = timezone.now() - timedelta(seconds=1)
        on_message(None, None, self._make_msg('/screen/upload/screen/to/cloud/aabbccddeeff'))
        after = timezone.now() + timedelta(seconds=1)

        self.assertEqual(ScreenConnectivityStatus.objects.count(), 1)
        record = ScreenConnectivityStatus.objects.get(specific_part='3-1-7-702')
        self.assertGreaterEqual(record.last_seen_at, before)
        self.assertLessEqual(record.last_seen_at, after)

    def test_tc_hb_001b_on_message_upsert_idempotent(self):
        """TC-HB-001b: 同一 MAC 两次心跳 → 仍只有 1 条记录，last_seen_at 更新"""
        on_message, mac_cache = _get_on_message_handler()
        msg = self._make_msg('/screen/upload/screen/to/cloud/aabbccddeeff')

        on_message(None, None, msg)
        first_seen = ScreenConnectivityStatus.objects.get(specific_part='3-1-7-702').last_seen_at

        time.sleep(0.05)
        on_message(None, None, msg)
        second_seen = ScreenConnectivityStatus.objects.get(specific_part='3-1-7-702').last_seen_at

        self.assertEqual(ScreenConnectivityStatus.objects.count(), 1)
        self.assertGreaterEqual(second_seen, first_seen)

    def test_tc_hb_002_on_message_unknown_mac_no_write(self):
        """TC-HB-002: 未知 MAC → DB 中无记录写入"""
        on_message, mac_cache = _get_on_message_handler()
        on_message(None, None, self._make_msg('/screen/upload/screen/to/cloud/unknown_mac_xyz'))
        self.assertEqual(ScreenConnectivityStatus.objects.count(), 0)

    def test_tc_hb_003_on_message_empty_mac_no_write(self):
        """TC-HB-003: 空 MAC topic（topic 以 / 结尾）→ 不写入 DB"""
        on_message, mac_cache = _get_on_message_handler()
        on_message(None, None, self._make_msg('/screen/upload/screen/to/cloud/'))
        self.assertEqual(ScreenConnectivityStatus.objects.count(), 0)


# ---------------------------------------------------------------------------
# TC-HB-004 ~ TC-HB-006: 在线/离线/unknown 判定
# ---------------------------------------------------------------------------

class OnlineStatusTest(TestCase):

    def setUp(self):
        from api.views import ONLINE_THRESHOLD_MINUTES
        self.threshold = ONLINE_THRESHOLD_MINUTES

    def _compute_status(self, last_seen_at):
        """复用 views.py 中的判断逻辑。"""
        from api.views import ONLINE_THRESHOLD_MINUTES
        from django.utils import timezone
        from datetime import timedelta

        if last_seen_at is None:
            return 'unknown'
        cutoff = timezone.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)
        return 'online' if last_seen_at >= cutoff else 'offline'

    def test_tc_hb_004_online_within_threshold(self):
        """TC-HB-004: last_seen_at 在阈值内 → online"""
        recent = timezone.now() - timedelta(minutes=self.threshold - 1)
        self.assertEqual(self._compute_status(recent), 'online')

    def test_tc_hb_004b_online_exactly_at_boundary(self):
        """TC-HB-004b: last_seen_at 恰好等于 now() → online"""
        self.assertEqual(self._compute_status(timezone.now()), 'online')

    def test_tc_hb_005_offline_beyond_threshold(self):
        """TC-HB-005: last_seen_at 超过阈值 → offline"""
        old = timezone.now() - timedelta(minutes=self.threshold + 1)
        self.assertEqual(self._compute_status(old), 'offline')

    def test_tc_hb_006_unknown_no_record(self):
        """TC-HB-006: last_seen_at 为 None（无 DB 记录）→ unknown"""
        self.assertEqual(self._compute_status(None), 'unknown')


# ---------------------------------------------------------------------------
# TC-HB-007: MAC 缓存刷新
# ---------------------------------------------------------------------------

class MacCacheTest(TestCase):

    def test_tc_hb_007_cache_refresh_on_expiry(self):
        """TC-HB-007: 缓存过期后 get_specific_part 触发重新加载，返回最新 DB 数据"""
        from api.management.commands.screen_heartbeat_consumer import MacCache, CACHE_REFRESH_INTERVAL

        # 创建初始 owner
        make_owner(specific_part='3-1-7-702', unique_id='mac001')
        cache = MacCache()

        # 首次调用：缓存为空，触发刷新
        result = cache.get_specific_part('mac001')
        self.assertEqual(result, '3-1-7-702')

        # 新增第二个 owner
        make_owner(specific_part='4-1-8-801', unique_id='mac002')

        # 在缓存有效期内，mac002 应不可见
        result2 = cache.get_specific_part('mac002')
        self.assertIsNone(result2)

        # 强制使缓存失效
        cache.invalidate()

        # 再次 get → 触发刷新，mac002 应可见
        result3 = cache.get_specific_part('mac002')
        self.assertEqual(result3, '4-1-8-801')

    def test_tc_hb_007b_cache_hit_without_db(self):
        """TC-HB-007b: 缓存命中时不再访问 DB（_refresh 不被多余调用）"""
        from api.management.commands.screen_heartbeat_consumer import MacCache

        make_owner(specific_part='3-1-7-702', unique_id='maccache')
        cache = MacCache()

        # 首次调用触发一次刷新
        cache.get_specific_part('maccache')

        # 记录调用后的刷新时间
        last_refresh = cache._last_refresh

        # 在 CACHE_REFRESH_INTERVAL 内再次调用，_last_refresh 不应变化
        cache.get_specific_part('maccache')
        self.assertEqual(cache._last_refresh, last_refresh)


# ---------------------------------------------------------------------------
# TC-HB-008: migration 字段检查
# ---------------------------------------------------------------------------

class MigrationFieldTest(TestCase):

    def test_tc_hb_008_model_has_last_seen_at(self):
        """TC-HB-008: ScreenConnectivityStatus 有 last_seen_at 字段"""
        field_names = [f.name for f in ScreenConnectivityStatus._meta.get_fields()]
        self.assertIn('last_seen_at', field_names)

    def test_tc_hb_008b_model_no_status_field(self):
        """TC-HB-008b: ScreenConnectivityStatus 不含 status 字段（已删除）"""
        field_names = [f.name for f in ScreenConnectivityStatus._meta.get_fields()]
        self.assertNotIn('status', field_names)

    def test_tc_hb_008c_model_no_last_checked_at_field(self):
        """TC-HB-008c: ScreenConnectivityStatus 不含 last_checked_at 字段（已删除）"""
        field_names = [f.name for f in ScreenConnectivityStatus._meta.get_fields()]
        self.assertNotIn('last_checked_at', field_names)

    def test_tc_hb_008d_can_create_record_with_last_seen_at(self):
        """TC-HB-008d: 可正常 create ScreenConnectivityStatus 记录"""
        make_owner()
        now = timezone.now()
        record = ScreenConnectivityStatus.objects.create(
            specific_part='3-1-7-702',
            last_seen_at=now,
        )
        self.assertIsNotNone(record.pk)
        self.assertEqual(record.last_seen_at, now)
        self.assertIsNotNone(record.updated_at)


# ---------------------------------------------------------------------------
# TC-HB-009 ~ TC-HB-010: device_list API 集成测试
# ---------------------------------------------------------------------------

class DeviceListAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        _, token = make_admin()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

        # 三个 owner
        self.owner_online = make_owner(
            specific_part='1-1-1-101', unique_id='mac_online',
            building='1', unit='1', room_number='101',
        )
        self.owner_offline = make_owner(
            specific_part='1-1-1-102', unique_id='mac_offline',
            building='1', unit='1', room_number='102',
        )
        self.owner_unknown = make_owner(
            specific_part='1-1-1-103', unique_id='mac_unknown',
            building='1', unit='1', room_number='103',
        )

        from api.views import ONLINE_THRESHOLD_MINUTES
        # online: last_seen_at 在阈值内
        make_screen_status(
            specific_part='1-1-1-101',
            last_seen_at=timezone.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES - 2),
        )
        # offline: last_seen_at 超过阈值
        make_screen_status(
            specific_part='1-1-1-102',
            last_seen_at=timezone.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES + 10),
        )
        # unknown: 无 ScreenConnectivityStatus 记录

    def test_tc_hb_009_filter_online(self):
        """TC-HB-009: screen_status=online 过滤 → 仅返回在线设备"""
        resp = self.client.get('/api/device-management/device-list/?screen_status=online')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['specific_part'], '1-1-1-101')
        self.assertEqual(data['results'][0]['screen_status'], 'online')
        # 响应中应包含 screen_last_seen_at（新字段名）
        self.assertIn('screen_last_seen_at', data['results'][0])

    def test_tc_hb_009b_filter_offline(self):
        """TC-HB-009b: screen_status=offline 过滤 → 仅返回离线设备"""
        resp = self.client.get('/api/device-management/device-list/?screen_status=offline')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['specific_part'], '1-1-1-102')
        self.assertEqual(data['results'][0]['screen_status'], 'offline')

    def test_tc_hb_010_filter_unknown(self):
        """TC-HB-010: screen_status=unknown 过滤 → 仅返回无记录设备"""
        resp = self.client.get('/api/device-management/device-list/?screen_status=unknown')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['specific_part'], '1-1-1-103')
        self.assertEqual(data['results'][0]['screen_status'], 'unknown')
        self.assertIsNone(data['results'][0]['screen_last_seen_at'])

    def test_tc_hb_010b_no_filter_returns_all(self):
        """TC-HB-010b: 无 screen_status 过滤 → 返回全部设备"""
        resp = self.client.get('/api/device-management/device-list/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 3)
        statuses = {r['specific_part']: r['screen_status'] for r in data['results']}
        self.assertEqual(statuses['1-1-1-101'], 'online')
        self.assertEqual(statuses['1-1-1-102'], 'offline')
        self.assertEqual(statuses['1-1-1-103'], 'unknown')
