"""
test_v100_dashboard_redesign.py — v1.0.0 系统看板重设计 + 设备列表凝露提醒列 测试

覆盖范围：
  UT-CL-01   device-list 响应含 has_active_condensation 字段，有活跃凝露时为 True
  UT-CL-02   device-list 响应无活跃凝露时 has_active_condensation 为 False
  UT-CL-04   凝露已恢复（is_active=False）时 has_active_condensation 为 False
  UT-FS-01   dashboard/fault-summary/ 返回 active_fault_count 正确
  UT-FS-02   dashboard/fault-summary/ 返回 affected_unit_count（specific_part 去重）
  UT-FS-03   dashboard/fault-summary/ 无故障时返回 0/0
  UT-DFS-01  dashboard/device-fault-summary/ 返回 4 类子设备键，含 total 和 fault_count
  UT-DFS-02  thermostat_panels 的 fault_count 包含 product_code=120003 和 260001
  UT-DFS-02c is_active=False 的故障不计入 fault_count
  UT-DFS-03  无设备/无故障时返回 0/0
  UT-AUTH-01 两个新接口要求认证，未认证返回 401

运行方式（FreeArkWeb/backend/freearkweb/ 目录下）：
    python manage.py test api.tests.test_v100_dashboard_redesign \
        --settings=freearkweb.test_settings --verbosity=2
"""

import datetime

from django.test import TestCase, tag
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from ..models import (
    OwnerInfo,
    CondensationWarningEvent,
    FaultEvent,
    DeviceNode,
    DeviceFloor,
    DeviceRoom,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# 公共常量
# ---------------------------------------------------------------------------

# 项目 USE_TZ=False（见 settings.py），DB 使用 naive datetime，故此处不带 tzinfo，
# 与现有测试 timezone.now() 的行为一致。
_NOW = datetime.datetime(2026, 5, 30, 12, 0, 0)


# ---------------------------------------------------------------------------
# 辅助：创建测试用户并返回认证 APIClient
# ---------------------------------------------------------------------------

def _make_authed_client():
    user, _ = User.objects.get_or_create(
        username='testuser_v100',
        defaults={'role': 'admin'},
    )
    if not user.pk:
        user.set_password('testpass')
        user.save()
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _make_owner(specific_part, building='3', unit='1', room_number='101'):
    """创建 OwnerInfo 记录（设备列表数据源）。"""
    obj, _ = OwnerInfo.objects.get_or_create(
        specific_part=specific_part,
        defaults={
            'building': building,
            'unit': unit,
            'room_number': room_number,
        }
    )
    return obj


def _make_fault_event(specific_part, product_code, fault_code='F001',
                       fault_type='comm', is_active=True, device_sn=None):
    """创建 FaultEvent 记录（包含所有必填字段）。"""
    sn = device_sn or f'SN_{product_code}_{fault_code}'
    return FaultEvent.objects.create(
        specific_part=specific_part,
        device_sn=sn,
        product_code=product_code,
        fault_code=fault_code,
        fault_type=fault_type,
        fault_message=f'测试故障 {fault_code}',
        severity='error',
        first_seen_at=_NOW,
        last_seen_at=_NOW,
        is_active=is_active,
    )


def _make_condensation_event(specific_part, device_sn='COND_SN_001', is_active=True):
    """创建 CondensationWarningEvent 记录（包含所有必填字段）。"""
    return CondensationWarningEvent.objects.create(
        specific_part=specific_part,
        device_sn=device_sn,
        product_code='999999',
        first_seen_at=_NOW,
        last_seen_at=_NOW,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# UT-CL-*: device-list 凝露提醒字段
# ---------------------------------------------------------------------------

@tag('integration')
class DeviceListCondensationFieldTest(TestCase):
    """验证 GET /api/device-management/device-list/ 返回 has_active_condensation 字段。"""

    def setUp(self):
        self.client = _make_authed_client()
        self.sp1 = '3-1-1-101'
        self.sp2 = '3-1-1-102'
        _make_owner(self.sp1, building='3', unit='1', room_number='101')
        _make_owner(self.sp2, building='3', unit='1', room_number='102')

    def _get_row(self, response, specific_part):
        for row in response.data.get('results', []):
            if row.get('specific_part') == specific_part:
                return row
        return None

    def test_UT_CL_01_has_active_condensation_true(self):
        """UT-CL-01: sp1 有活跃凝露 → has_active_condensation=True。"""
        _make_condensation_event(self.sp1, is_active=True)
        resp = self.client.get('/api/device-management/device-list/')
        self.assertEqual(resp.status_code, 200)
        row = self._get_row(resp, self.sp1)
        self.assertIsNotNone(row, f'{self.sp1} 不在响应 results 中')
        self.assertTrue(
            row['has_active_condensation'],
            f'期望 has_active_condensation=True，实际: {row.get("has_active_condensation")}'
        )

    def test_UT_CL_02_has_active_condensation_false_no_record(self):
        """UT-CL-02: sp2 无凝露记录 → has_active_condensation=False。"""
        resp = self.client.get('/api/device-management/device-list/')
        self.assertEqual(resp.status_code, 200)
        row = self._get_row(resp, self.sp2)
        self.assertIsNotNone(row, f'{self.sp2} 不在响应 results 中')
        self.assertFalse(
            row['has_active_condensation'],
            f'期望 has_active_condensation=False，实际: {row.get("has_active_condensation")}'
        )

    def test_UT_CL_04_recovered_condensation_returns_false(self):
        """UT-CL-04: sp1 凝露已恢复（is_active=False） → has_active_condensation=False。"""
        _make_condensation_event(self.sp1, is_active=False)
        resp = self.client.get('/api/device-management/device-list/')
        self.assertEqual(resp.status_code, 200)
        row = self._get_row(resp, self.sp1)
        self.assertIsNotNone(row)
        self.assertFalse(
            row['has_active_condensation'],
            'is_active=False 的凝露记录不应使 has_active_condensation=True'
        )

    def test_UT_CL_field_always_present(self):
        """has_active_condensation 字段在每条 result 中都存在。"""
        resp = self.client.get('/api/device-management/device-list/')
        self.assertEqual(resp.status_code, 200)
        for row in resp.data.get('results', []):
            self.assertIn(
                'has_active_condensation', row,
                f'result 行中缺少 has_active_condensation 字段: {row.get("specific_part")}'
            )


# ---------------------------------------------------------------------------
# UT-FS-*: dashboard/fault-summary/
# ---------------------------------------------------------------------------

@tag('integration')
class FaultSummaryAPITest(TestCase):
    """验证 GET /api/dashboard/fault-summary/。"""

    def setUp(self):
        self.client = _make_authed_client()

    def test_UT_FS_01_active_fault_count(self):
        """UT-FS-01: active_fault_count 等于 is_active=True 的记录总条数。"""
        _make_fault_event('3-1-1-101', '100007', 'F001', is_active=True)
        _make_fault_event('3-1-1-101', '100007', 'F002', is_active=True)
        _make_fault_event('3-1-1-102', '130004', 'F001', is_active=True)
        _make_fault_event('3-1-1-103', '270001', 'F001', is_active=False)  # 不计入

        resp = self.client.get('/api/dashboard/fault-summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])
        self.assertEqual(
            resp.data['data']['active_fault_count'], 3,
            f'期望 active_fault_count=3，实际: {resp.data["data"]["active_fault_count"]}'
        )

    def test_UT_FS_02_affected_unit_count_distinct(self):
        """UT-FS-02: affected_unit_count 是 specific_part 去重计数。
        sp=101 有 2 条故障，应只计 1 户。
        """
        _make_fault_event('3-1-1-101', '100007', 'F001')
        _make_fault_event('3-1-1-101', '100007', 'F002', device_sn='SN100007_2')  # 同一 sp，第 2 条
        _make_fault_event('3-1-1-102', '130004', 'F001')

        resp = self.client.get('/api/dashboard/fault-summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.data['data']['affected_unit_count'], 2,
            f'期望 affected_unit_count=2（去重），实际: {resp.data["data"]["affected_unit_count"]}'
        )

    def test_UT_FS_03_no_fault_returns_zero(self):
        """UT-FS-03: 无活跃故障时返回 0/0。"""
        _make_fault_event('3-1-1-101', '100007', 'F001', is_active=False)  # 已恢复

        resp = self.client.get('/api/dashboard/fault-summary/')
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertEqual(data['active_fault_count'], 0)
        self.assertEqual(data['affected_unit_count'], 0)

    def test_UT_FS_response_structure(self):
        """fault-summary 响应包含 success=True 和 data 字典，data 含两个必要键。"""
        resp = self.client.get('/api/dashboard/fault-summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('success', resp.data)
        self.assertTrue(resp.data['success'])
        self.assertIn('data', resp.data)
        self.assertIn('active_fault_count', resp.data['data'])
        self.assertIn('affected_unit_count', resp.data['data'])


# ---------------------------------------------------------------------------
# UT-DFS-*: dashboard/device-fault-summary/
# ---------------------------------------------------------------------------

@tag('integration')
class DeviceFaultSummaryAPITest(TestCase):
    """验证 GET /api/dashboard/device-fault-summary/。"""

    def setUp(self):
        self.client = _make_authed_client()
        # 建立 DeviceNode 所需的 OwnerInfo → DeviceFloor → DeviceRoom 链
        self.owner, _ = OwnerInfo.objects.get_or_create(
            specific_part='3-1-1-999',
            defaults={'building': '3', 'unit': '1', 'room_number': '999'},
        )
        self.floor, _ = DeviceFloor.objects.get_or_create(
            owner=self.owner, floor_no=1,
            defaults={'floor_name': '第1层'},
        )
        self.room, _ = DeviceRoom.objects.get_or_create(
            floor=self.floor, ori_room_name='客厅',
            defaults={'room_name': '客厅', 'room_type': 1},
        )

    def _make_device_node(self, product_code, device_sn):
        node, _ = DeviceNode.objects.get_or_create(
            room=self.room, device_sn=device_sn,
            defaults={
                'device_name': f'设备_{product_code}',
                'system_flag': 1,
                'product_code': product_code,
                'category_code': 1,
            }
        )
        return node

    def test_UT_DFS_01_returns_four_categories(self):
        """UT-DFS-01: 响应包含 4 类子设备键，每键有 total 和 fault_count。"""
        resp = self.client.get('/api/dashboard/device-fault-summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])
        data = resp.data['data']
        for key in ('air_quality_sensor', 'thermostat_panels', 'fresh_air_unit', 'hydraulic_module'):
            self.assertIn(key, data, f'响应缺少键: {key}')
            self.assertIn('total', data[key], f'{key} 缺少 total 字段')
            self.assertIn('fault_count', data[key], f'{key} 缺少 fault_count 字段')

    def test_UT_DFS_01b_device_node_total(self):
        """UT-DFS-01b: total 按 product_code 统计 DeviceNode 数量。"""
        self._make_device_node('100007', device_sn=10001)
        resp = self.client.get('/api/dashboard/device-fault-summary/')
        self.assertEqual(resp.status_code, 200)
        aq_total = resp.data['data']['air_quality_sensor']['total']
        self.assertGreaterEqual(aq_total, 1,
                                f'air_quality_sensor total 应 >=1，实际: {aq_total}')

    def test_UT_DFS_02_thermostat_includes_product_code_260001_and_120003(self):
        """UT-DFS-02: thermostat_panels fault_count 包含 product_code 120003 和 260001。"""
        _make_fault_event('3-1-1-001', '260001', 'F001', fault_type='comm')   # 260001 = 客厅主温控
        _make_fault_event('3-1-1-001', '120003', 'F002', fault_type='sensor',
                          device_sn='SN120003_1')                              # 120003 = 各房间温控面板
        _make_fault_event('3-1-1-001', '100007', 'F003', fault_type='sensor',
                          device_sn='SN100007_X')  # 空气品质传感器，不计入 thermostat_panels

        resp = self.client.get('/api/dashboard/device-fault-summary/')
        self.assertEqual(resp.status_code, 200)
        thermostat_fc = resp.data['data']['thermostat_panels']['fault_count']
        self.assertEqual(thermostat_fc, 2,
                         f'thermostat_panels fault_count 期望 2（260001+120003），实际: {thermostat_fc}')

    def test_UT_DFS_02c_recovered_fault_not_counted(self):
        """UT-DFS-02c: is_active=False 的故障不计入 fault_count。"""
        _make_fault_event('3-1-1-001', '130004', 'F001', fault_type='fresh_air',
                          is_active=True, device_sn='SN130004A')
        _make_fault_event('3-1-1-001', '130004', 'F002', fault_type='fresh_air',
                          is_active=False, device_sn='SN130004B')  # 已恢复

        resp = self.client.get('/api/dashboard/device-fault-summary/')
        self.assertEqual(resp.status_code, 200)
        fa_fc = resp.data['data']['fresh_air_unit']['fault_count']
        self.assertEqual(fa_fc, 1,
                         f'fresh_air_unit fault_count 期望 1（排除已恢复），实际: {fa_fc}')

    def test_UT_DFS_03_empty_db_returns_zeros(self):
        """UT-DFS-03: 无故障时所有 fault_count 返回 0。"""
        resp = self.client.get('/api/dashboard/device-fault-summary/')
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        for key in ('air_quality_sensor', 'thermostat_panels', 'fresh_air_unit', 'hydraulic_module'):
            self.assertEqual(data[key]['fault_count'], 0, f'{key}.fault_count 应为 0')

    def test_UT_DFS_hydraulic_module_fault_count(self):
        """hydraulic_module (product_code=270001) fault_count 正确统计。"""
        _make_fault_event('3-1-1-001', '270001', 'F001', fault_type='other_error',
                          device_sn='SN270001A')
        _make_fault_event('3-1-1-001', '270001', 'F002', fault_type='other_error',
                          device_sn='SN270001B')

        resp = self.client.get('/api/dashboard/device-fault-summary/')
        self.assertEqual(resp.status_code, 200)
        hm_fc = resp.data['data']['hydraulic_module']['fault_count']
        self.assertEqual(hm_fc, 2, f'hydraulic_module fault_count 期望 2，实际: {hm_fc}')


# ---------------------------------------------------------------------------
# UT-AUTH-01: 认证要求
# ---------------------------------------------------------------------------

@tag('integration')
class NewAPIAuthTest(TestCase):
    """验证新增 API 端点要求认证。"""

    def setUp(self):
        self.anon_client = APIClient()  # 未认证

    def test_UT_AUTH_01a_fault_summary_requires_auth(self):
        """UT-AUTH-01a: /api/dashboard/fault-summary/ 未认证返回 401。"""
        resp = self.anon_client.get('/api/dashboard/fault-summary/')
        self.assertEqual(resp.status_code, 401,
                         f'期望 401，实际: {resp.status_code}')

    def test_UT_AUTH_01b_device_fault_summary_requires_auth(self):
        """UT-AUTH-01b: /api/dashboard/device-fault-summary/ 未认证返回 401。"""
        resp = self.anon_client.get('/api/dashboard/device-fault-summary/')
        self.assertEqual(resp.status_code, 401,
                         f'期望 401，实际: {resp.status_code}')
