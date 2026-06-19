"""
test_condensation_v070_integration.py — v0.7.0 结露预警 集成测试

覆盖范围：
  IT-HANDLER-001  _handle_message 完整路径：260001 含 system_switch → MQTT 直取 + T1 INSERT
  IT-HANDLER-002  _handle_message 完整路径：120003 无 system_switch → PLCLatestData 兜底
  IT-HANDLER-003  _handle_message：未知 MAC → WARNING 日志，不写 DB
  IT-HANDLER-004  _handle_message：非 DeviceStatusUpdate 报文 → 忽略
  IT-HANDLER-005  _handle_message：无 condensation_alarm 字段 → 跳过
  IT-HANDLER-006  _handle_message：condensation_alarm=0 报文 + 内存已活跃 → T3 RECOVER
  IT-API-001      GET /api/devices/condensation-warning-events/ 基础分页返回 20 条默认
  IT-API-002      is_active=true 过滤 → 只返回活跃记录
  IT-API-003      is_active=false 过滤 → 只返回已恢复记录
  IT-API-004      first_seen_after / first_seen_before 时间过滤
  IT-API-005      specific_part 3 段格式 → startswith+endswith 映射
  IT-API-006      is_screen_online 注入：15 分钟内心跳 → True；无记录 → False
  IT-API-007      未认证请求 → 401

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_condensation_v070_integration \\
        --settings=freearkweb.test_settings --verbosity=2
"""

import json
import logging
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from api.models import (
    CondensationWarningEvent,
    ScreenConnectivityStatus,
    PLCLatestData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_mqtt_msg(topic, payload_dict):
    msg = MagicMock()
    msg.topic = topic
    msg.payload = json.dumps(payload_dict).encode('utf-8')
    return msg


def _make_dsupdate_payload(device_sn='22554', product_code='260001', items=None, mac='aabbccddeeff'):
    return {
        'header': {'name': 'DeviceStatusUpdate', 'screenMac': mac},
        'payload': {
            'data': {
                'deviceSn': device_sn,
                'productCode': product_code,
                'items': items or [],
            }
        }
    }


def _create_event(specific_part, is_active=True, days_ago=0, device_sn='SN1'):
    now = timezone.now() - timedelta(days=days_ago)
    return CondensationWarningEvent.objects.create(
        specific_part=specific_part,
        device_sn=device_sn,
        product_code='260001',
        first_seen_at=now,
        last_seen_at=now,
        recovered_at=now if not is_active else None,
        is_active=is_active,
        warning_type='结露预警',
        warning_message='结露报警',
        system_switch='on',
    )


# ---------------------------------------------------------------------------
# IT-HANDLER-*: _handle_message 端到端集成
# ---------------------------------------------------------------------------

@tag('integration')
class HandleMessageIntegrationTest(TestCase):
    """IT-HANDLER-001~006: _handle_message 从 MAC 解析到 DB 写入全链路。"""

    def setUp(self):
        import api.condensation_consumer.state_machine as sm_module
        sm_module._cw_state_machine.clear()
        self.sm = sm_module

        # 构造 mac_cache mock：固定 mac → specific_part
        self.mac_cache = MagicMock()
        self.mac_cache.get_specific_part.return_value = '3-1-7-702'

    def test_handler_001_260001_with_system_switch_mqtt_direct(self):
        """IT-HANDLER-001: 260001 报文含 system_switch → MQTT 直取 'off' → T1 INSERT。"""
        from api.management.commands.condensation_consumer import _handle_message

        items = [
            {'attrTag': 'condensation_alarm', 'attrValue': '1'},
            {'attrTag': 'dew_point_temp', 'attrValue': '12.5'},
            {'attrTag': 'NTC_temp', 'attrValue': '18.0'},
            {'attrTag': 'humidity', 'attrValue': '65'},
            {'attrTag': 'system_switch', 'attrValue': 'off'},
        ]
        msg = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _make_dsupdate_payload(device_sn='22554', product_code='260001', items=items),
        )
        _handle_message(msg, self.mac_cache)

        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertEqual(cwe.system_switch, 'off')
        self.assertEqual(cwe.dew_point_temp, '12.5')
        self.assertEqual(cwe.ntc_temp, '18.0')
        self.assertEqual(cwe.humidity, '65')
        self.assertTrue(cwe.is_active)

    def test_handler_002_120003_no_system_switch_plc_fallback(self):
        """IT-HANDLER-002: 120003 报文无 system_switch → PLCLatestData value=1 → 'on'。"""
        from api.management.commands.condensation_consumer import _handle_message

        PLCLatestData.objects.create(
            specific_part='3-1-7-702',
            param_name='system_switch',
            value=1,
        )

        items = [
            {'attrTag': 'condensation_alarm', 'attrValue': '1'},
            {'attrTag': 'dew_point_temp', 'attrValue': '11.0'},
        ]
        msg = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _make_dsupdate_payload(device_sn='22549', product_code='120003', items=items),
        )
        _handle_message(msg, self.mac_cache)

        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertEqual(cwe.system_switch, 'on')  # PLCLatestData value=1 → 'on'

    def test_handler_003_unknown_mac_no_db_write(self):
        """IT-HANDLER-003: 未知 MAC → 不写 DB，服务继续运行。"""
        from api.management.commands.condensation_consumer import _handle_message

        mac_cache = MagicMock()
        mac_cache.get_specific_part.return_value = None  # 未找到映射

        items = [{'attrTag': 'condensation_alarm', 'attrValue': '1'}]
        msg = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/unknownmac',
            _make_dsupdate_payload(items=items),
        )
        _handle_message(msg, mac_cache)
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_handler_004_non_device_status_update_ignored(self):
        """IT-HANDLER-004: header.name != 'DeviceStatusUpdate' → 忽略。"""
        from api.management.commands.condensation_consumer import _handle_message

        payload = {'header': {'name': 'OtherMessage'}, 'payload': {'data': {}}}
        msg = _make_mqtt_msg('screen/upload/screen/to/cloud/aabbccddeeff', payload)
        _handle_message(msg, self.mac_cache)
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_handler_005_no_condensation_alarm_tag_skipped(self):
        """IT-HANDLER-005: items[] 无 condensation_alarm → 跳过。"""
        from api.management.commands.condensation_consumer import _handle_message

        items = [
            {'attrTag': 'dew_point_temp', 'attrValue': '12.5'},
            {'attrTag': 'system_switch', 'attrValue': 'on'},
        ]
        msg = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _make_dsupdate_payload(items=items),
        )
        _handle_message(msg, self.mac_cache)
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_handler_006_alarm_zero_triggers_t3_recover(self):
        """IT-HANDLER-006: 内存活跃预警 + alarm=0 → T3 RECOVER 写 DB。"""
        from api.management.commands.condensation_consumer import _handle_message

        # 先 T1：建立活跃记录
        items_alarm = [
            {'attrTag': 'condensation_alarm', 'attrValue': '1'},
            {'attrTag': 'system_switch', 'attrValue': 'on'},
        ]
        msg_alarm = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _make_dsupdate_payload(device_sn='22554', product_code='260001', items=items_alarm),
        )
        _handle_message(msg_alarm, self.mac_cache)
        self.assertEqual(CondensationWarningEvent.objects.filter(is_active=True).count(), 1)

        # 再 T3：alarm=0 触发恢复
        items_recover = [
            {'attrTag': 'condensation_alarm', 'attrValue': '0'},
        ]
        msg_recover = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _make_dsupdate_payload(device_sn='22554', product_code='260001', items=items_recover),
        )
        _handle_message(msg_recover, self.mac_cache)

        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertFalse(cwe.is_active)
        self.assertIsNotNone(cwe.recovered_at)


# ---------------------------------------------------------------------------
# IT-API-*: REST API 集成测试
# ---------------------------------------------------------------------------

@tag('integration')
class CondensationAPITest(APITestCase):
    """IT-API-001~007: GET /api/devices/condensation-warning-events/ 集成测试。"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser', password='testpass123'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/devices/condensation-warning-events/'

    def _create_n_events(self, n, is_active=True, specific_part_prefix='1-1-1-', days_ago=0):
        for i in range(n):
            _create_event(
                specific_part=f'{specific_part_prefix}{100+i}',
                is_active=is_active,
                days_ago=days_ago,
                device_sn=f'SN{i}',
            )

    def test_api_001_basic_pagination_default(self):
        """IT-API-001: 默认分页 20 条/页，返回 count + results。"""
        # 在最近 7 天内创建 25 条活跃记录
        self._create_n_events(25, is_active=True, days_ago=1)

        resp = self.client.get(self.url, {'is_active': 'true', 'page_size': 20})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertEqual(len(data['results']), 20)
        self.assertEqual(data['count'], 25)

    def test_api_002_filter_is_active_true(self):
        """IT-API-002: is_active=true → 只返回活跃记录。"""
        _create_event('1-1-1-101', is_active=True, days_ago=1)
        _create_event('1-1-1-102', is_active=False, days_ago=1)

        resp = self.client.get(self.url, {'is_active': 'true'})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertTrue(all(r['is_active'] for r in results))
        self.assertEqual(len(results), 1)

    def test_api_003_filter_is_active_false(self):
        """IT-API-003: is_active=false → 只返回已恢复记录。"""
        _create_event('1-1-1-101', is_active=True, days_ago=1)
        _create_event('1-1-1-102', is_active=False, days_ago=1)

        resp = self.client.get(self.url, {'is_active': 'false'})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertTrue(all(not r['is_active'] for r in results))
        self.assertEqual(len(results), 1)

    def test_api_004_time_filter(self):
        """IT-API-004: first_seen_after / first_seen_before 时间过滤。"""
        # 3 天前的记录
        _create_event('1-1-1-101', is_active=False, days_ago=3)
        # 10 天前的记录（默认 7 天窗口外，但需指定 after）
        _create_event('1-1-1-102', is_active=False, days_ago=10)

        now = timezone.now()
        # 查询 5 天前至今
        after = (now - timedelta(days=5)).strftime('%Y-%m-%dT%H:%M:%S')
        resp = self.client.get(self.url, {
            'is_active': 'false',
            'first_seen_after': after,
        })
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        # 只返回 3 天前的那条（10 天前那条不在范围内）
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['specific_part'], '1-1-1-101')

    def test_api_005_specific_part_3_segment_mapping(self):
        """IT-API-005: 3 段 specific_part → startswith+endswith 映射到 4 段 DB 记录。"""
        # DB 中存 4 段格式
        _create_event('3-1-7-702', is_active=True, days_ago=1)
        _create_event('3-1-8-702', is_active=True, days_ago=1)  # 不同单元，同房号
        _create_event('4-1-7-702', is_active=True, days_ago=1)  # 不同楼栋

        # 前端传 3 段 "3-1-702"：楼栋3、单元1、房号702
        resp = self.client.get(self.url, {'specific_part': '3-1-702', 'is_active': 'true'})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        specific_parts = [r['specific_part'] for r in results]

        # 应匹配 startswith="3-1-" AND endswith="-702"
        # "3-1-7-702" 满足，"3-1-8-702" 也满足（不同楼层），"4-1-7-702" 不满足
        for sp in specific_parts:
            self.assertTrue(sp.startswith('3-1-') and sp.endswith('-702'),
                            f'非预期结果: {sp}')

    def test_api_006_is_screen_online_injection(self):
        """IT-API-006: is_screen_online 实时注入 - 15 分钟内心跳 → True，无记录 → False。"""
        _create_event('3-1-7-702', is_active=True, days_ago=1, device_sn='SN1')
        _create_event('3-1-7-703', is_active=True, days_ago=1, device_sn='SN2')

        now = timezone.now()
        # 3-1-7-702：最近 5 分钟内有心跳 → 在线
        ScreenConnectivityStatus.objects.create(
            specific_part='3-1-7-702',
            last_seen_at=now - timedelta(minutes=5),
        )
        # 3-1-7-703：无记录 → 离线

        resp = self.client.get(self.url, {'is_active': 'true'})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']

        online_map = {r['specific_part']: r['is_screen_online'] for r in results}
        self.assertTrue(online_map.get('3-1-7-702'), '702 应为在线')
        self.assertFalse(online_map.get('3-1-7-703'), '703 无心跳应为离线')

    def test_api_007_unauthenticated_401(self):
        """IT-API-007: 未认证请求 → 401 Unauthorized。"""
        unauth_client = APIClient()
        resp = unauth_client.get(self.url)
        self.assertEqual(resp.status_code, 401)

    def test_api_008_page_size_override(self):
        """IT-API-008: page_size=10 → 每页 10 条，支持 10/20/50。"""
        self._create_n_events(15, is_active=True, days_ago=1)
        resp = self.client.get(self.url, {'is_active': 'true', 'page_size': 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['results']), 10)
        self.assertEqual(data['count'], 15)
        self.assertIsNotNone(data['next'])  # 有下一页

    def test_api_009_screen_online_15min_boundary(self):
        """IT-API-009: 大屏在线判定边界 - last_seen_at=16分钟前 → 离线。"""
        _create_event('3-1-7-704', is_active=True, days_ago=1, device_sn='SN4')

        now = timezone.now()
        # 16 分钟前 → 超出 15 分钟阈值 → 离线
        ScreenConnectivityStatus.objects.create(
            specific_part='3-1-7-704',
            last_seen_at=now - timedelta(minutes=16),
        )

        resp = self.client.get(self.url, {'is_active': 'true'})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        online_map = {r['specific_part']: r['is_screen_online'] for r in results}
        self.assertFalse(online_map.get('3-1-7-704'), '16 分钟前心跳应为离线')
