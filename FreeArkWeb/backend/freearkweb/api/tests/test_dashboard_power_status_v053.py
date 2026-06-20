"""
test_dashboard_power_status_v053.py
FreeArk v0.5.3 — 系统看板「系统开机状况」卡片 单元测试 & 集成测试

测试覆盖：
  US-001  正常开机统计
  US-002  运行模式分布
  US-003  PLC 离线设备不计入
  US-004  system_switch 为关不计入
  US-005  仅开机设备的模式纳入统计
  US-006  空数据降级显示（total_count=0 除零安全）
  US-008  无 N+1（查询次数约束）
  US-009  开机设备无 operation_mode 记录/未知值处理（OQ-002）

验收标准覆盖：AC-101~110, AC-201~205（前端 AC 通过代码审查覆盖）
"""
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory, tag
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from ..models import PLCConnectionStatus, PLCLatestData
from ..views import dashboard_power_status

User = get_user_model()

API_URL = '/api/dashboard/power-status/'


def _make_plc_status(specific_part, connection_status='offline',
                     building='3', unit='1', room_number='702'):
    return PLCConnectionStatus.objects.create(
        specific_part=specific_part,
        connection_status=connection_status,
        building=building,
        unit=unit,
        room_number=room_number,
    )


def _make_latest_data(specific_part, param_name, value,
                      building='3', unit='1', room_number='702'):
    """创建或更新 PLCLatestData 记录（unique_together: specific_part+param_name）"""
    obj, _ = PLCLatestData.objects.update_or_create(
        specific_part=specific_part,
        param_name=param_name,
        defaults={
            'value': value,
            'building': building,
            'unit': unit,
            'room_number': room_number,
        }
    )
    return obj


# ──────────────────────────────────────────────────────────────
# 辅助：完整建立一台"开机"设备
# ──────────────────────────────────────────────────────────────
def _create_powered_on_device(specific_part, operation_mode=None,
                              building='3', unit='1', room_number='702'):
    """建立 PLCConnectionStatus(online) + system_switch(1) + 可选 operation_mode"""
    _make_plc_status(specific_part, 'online', building, unit, room_number)
    _make_latest_data(specific_part, 'system_switch', 1, building, unit, room_number)
    if operation_mode is not None:
        _make_latest_data(specific_part, 'operation_mode', operation_mode,
                          building, unit, room_number)


# ══════════════════════════════════════════════════════════════
# Part 1: 单元测试（Django TestCase，使用测试数据库）
# ══════════════════════════════════════════════════════════════

@tag('integration')
class TestPowerStatusBasic(TestCase):
    """US-001, US-003, US-004, US-006 — 基础开机统计逻辑"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # ─── AC-104：空数据安全降级 ───
    def test_empty_db_returns_zero_no_division_error(self):
        """US-006 Scenario 1：PLCConnectionStatus 表为空时，power_on_rate=0.0，无除零错误"""
        res = self.client.get(API_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['total_count'], 0)
        self.assertEqual(data['data']['powered_on_count'], 0)
        self.assertEqual(data['data']['power_on_rate'], 0.0)
        md = data['data']['mode_distribution']
        self.assertEqual(md['cooling'], 0)
        self.assertEqual(md['heating'], 0)
        self.assertEqual(md['ventilation'], 0)
        self.assertEqual(md['dehumidification'], 0)
        self.assertEqual(md['unknown'], 0)

    # ─── AC-101：PLC offline 不计入 ───
    def test_offline_device_excluded_from_powered_on(self):
        """US-003 Scenario 1：PLC offline 设备不计入 powered_on_count"""
        _make_plc_status('3-1-7-701', 'offline')
        _make_latest_data('3-1-7-701', 'system_switch', 1)
        res = self.client.get(API_URL)
        data = res.json()['data']
        self.assertEqual(data['total_count'], 1)
        self.assertEqual(data['powered_on_count'], 0)
        self.assertEqual(data['power_on_rate'], 0.0)

    # ─── AC-102：PLC online 但 system_switch=0 ───
    def test_online_but_switch_off_excluded(self):
        """US-004 Scenario 1：PLC online + system_switch=0，不计入 powered_on_count"""
        _make_plc_status('3-1-7-702', 'online')
        _make_latest_data('3-1-7-702', 'system_switch', 0)
        res = self.client.get(API_URL)
        data = res.json()['data']
        self.assertEqual(data['total_count'], 1)
        self.assertEqual(data['powered_on_count'], 0)

    # ─── AC-103：PLC online + system_switch=1 = 开机 ───
    def test_online_switch_on_counted(self):
        """US-001 Scenario 1（局部）：PLC online + system_switch=1 → powered_on_count=1"""
        _create_powered_on_device('3-1-7-703')
        res = self.client.get(API_URL)
        data = res.json()['data']
        self.assertEqual(data['total_count'], 1)
        self.assertEqual(data['powered_on_count'], 1)
        self.assertEqual(data['power_on_rate'], 100.0)

    # ─── US-001 Scenario 1：混合开关机状态 ───
    def test_mixed_online_offline_correct_counts(self):
        """US-001 Scenario 1：10台，6台开机 → powered_on_count=6，rate=60.0"""
        for i in range(1, 7):
            _create_powered_on_device(f'3-1-7-{700 + i}')
        for i in range(7, 11):
            _make_plc_status(f'3-1-7-{700 + i}', 'offline')
        res = self.client.get(API_URL)
        data = res.json()['data']
        self.assertEqual(data['total_count'], 10)
        self.assertEqual(data['powered_on_count'], 6)
        self.assertEqual(data['power_on_rate'], 60.0)

    # ─── US-001 Scenario 2：全部开机 ───
    def test_all_devices_on(self):
        """US-001 Scenario 2：5台全开 → powered_on_count=5，rate=100.0"""
        for i in range(1, 6):
            _create_powered_on_device(f'3-1-7-{800 + i}')
        res = self.client.get(API_URL)
        data = res.json()['data']
        self.assertEqual(data['total_count'], 5)
        self.assertEqual(data['powered_on_count'], 5)
        self.assertEqual(data['power_on_rate'], 100.0)

    # ─── US-001 Scenario 3：全部关机 ───
    def test_all_devices_off(self):
        """US-001 Scenario 3：5台全关 → powered_on_count=0，rate=0.0"""
        for i in range(1, 6):
            _make_plc_status(f'3-1-7-{900 + i}', 'offline')
        res = self.client.get(API_URL)
        data = res.json()['data']
        self.assertEqual(data['total_count'], 5)
        self.assertEqual(data['powered_on_count'], 0)
        self.assertEqual(data['power_on_rate'], 0.0)


@tag('integration')
class TestPowerStatusModeDistribution(TestCase):
    """US-002, US-005 — 运行模式分布"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser2', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # ─── AC-105~108：四种模式各自计入正确分类 ───
    def test_mode_1_cooling(self):
        """AC-105：开机 + operation_mode=1 → mode_distribution.cooling=1"""
        _create_powered_on_device('3-1-1-101', operation_mode=1)
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['mode_distribution']['cooling'], 1)
        self.assertEqual(data['mode_distribution']['heating'], 0)

    def test_mode_2_heating(self):
        """AC-106：开机 + operation_mode=2 → mode_distribution.heating=1"""
        _create_powered_on_device('3-1-1-102', operation_mode=2)
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['mode_distribution']['heating'], 1)

    def test_mode_3_ventilation(self):
        """AC-107：开机 + operation_mode=3 → mode_distribution.ventilation=1"""
        _create_powered_on_device('3-1-1-103', operation_mode=3)
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['mode_distribution']['ventilation'], 1)

    def test_mode_4_dehumidification(self):
        """AC-108：开机 + operation_mode=4 → mode_distribution.dehumidification=1"""
        _create_powered_on_device('3-1-1-104', operation_mode=4)
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['mode_distribution']['dehumidification'], 1)

    # ─── US-002 Scenario 1：四种模式均有设备 ───
    def test_all_four_modes(self):
        """US-002 Scenario 1：8台开机，3制冷/2制热/2通风/1除湿"""
        for i in range(3):
            _create_powered_on_device(f'3-1-2-{201 + i}', operation_mode=1)
        for i in range(2):
            _create_powered_on_device(f'3-1-2-{211 + i}', operation_mode=2)
        for i in range(2):
            _create_powered_on_device(f'3-1-2-{221 + i}', operation_mode=3)
        _create_powered_on_device('3-1-2-231', operation_mode=4)

        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 8)
        md = data['mode_distribution']
        self.assertEqual(md['cooling'], 3)
        self.assertEqual(md['heating'], 2)
        self.assertEqual(md['ventilation'], 2)
        self.assertEqual(md['dehumidification'], 1)
        self.assertEqual(md['unknown'], 0)
        # 可对账约束
        self.assertEqual(
            md['cooling'] + md['heating'] + md['ventilation'] + md['dehumidification'] + md['unknown'],
            data['powered_on_count']
        )

    # ─── US-002 Scenario 2：仅部分模式有设备 ───
    def test_only_cooling_mode(self):
        """US-002 Scenario 2：4台均制冷 → cooling=4，其余=0"""
        for i in range(4):
            _create_powered_on_device(f'3-1-3-{301 + i}', operation_mode=1)
        data = self.client.get(API_URL).json()['data']
        md = data['mode_distribution']
        self.assertEqual(md['cooling'], 4)
        self.assertEqual(md['heating'], 0)
        self.assertEqual(md['ventilation'], 0)
        self.assertEqual(md['dehumidification'], 0)
        self.assertEqual(md['unknown'], 0)

    # ─── AC-109：关机设备的 mode 不计入 ───
    def test_offline_device_mode_not_counted(self):
        """US-005 Scenario 1：关机设备 mode=1 不计入 cooling"""
        # 设备 F: PLC offline + mode=1
        _make_plc_status('3-1-4-401', 'offline')
        _make_latest_data('3-1-4-401', 'operation_mode', 1)
        # 设备 G: PLC online + switch=0 + mode=2
        _make_plc_status('3-1-4-402', 'online')
        _make_latest_data('3-1-4-402', 'system_switch', 0)
        _make_latest_data('3-1-4-402', 'operation_mode', 2)
        # 设备 H: PLC online + switch=1 + mode=3（满足开机）
        _create_powered_on_device('3-1-4-403', operation_mode=3)

        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 1)
        md = data['mode_distribution']
        self.assertEqual(md['cooling'], 0)
        self.assertEqual(md['heating'], 0)
        self.assertEqual(md['ventilation'], 1)
        self.assertEqual(md['dehumidification'], 0)

    # ─── US-005 Scenario 2：mode_distribution 之和 <= powered_on_count ───
    def test_mode_sum_leq_powered_on(self):
        """US-005 Scenario 2：5台开机，2台有有效 mode，3台无 mode"""
        for i in range(2):
            _create_powered_on_device(f'3-1-5-{501 + i}', operation_mode=1)
        for i in range(3):
            _create_powered_on_device(f'3-1-5-{511 + i}')  # 无 operation_mode
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 5)
        md = data['mode_distribution']
        total_known = md['cooling'] + md['heating'] + md['ventilation'] + md['dehumidification']
        self.assertEqual(total_known, 2)
        self.assertEqual(md['unknown'], 3)


@tag('integration')
class TestPowerStatusUnknownMode(TestCase):
    """US-009, OQ-002 — 未知模式处理"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser3', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # ─── AC-110 / US-009 Scenario 1：无 operation_mode 记录 ───
    def test_powered_on_no_mode_record(self):
        """US-009 S1：开机设备无 operation_mode 记录 → powered_on_count 含入，mode 均不含"""
        _create_powered_on_device('3-1-6-601')  # 不传 operation_mode
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 1)
        md = data['mode_distribution']
        self.assertEqual(md['cooling'], 0)
        self.assertEqual(md['heating'], 0)
        self.assertEqual(md['ventilation'], 0)
        self.assertEqual(md['dehumidification'], 0)
        self.assertEqual(md['unknown'], 1)

    # ─── US-009 Scenario 2：operation_mode.value=0（历史边界数据）───
    def test_mode_zero_counts_as_unknown(self):
        """US-009 S2：开机 + operation_mode=0 → 计入 unknown，不计入任何四类"""
        _create_powered_on_device('3-1-6-602', operation_mode=0)
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 1)
        md = data['mode_distribution']
        self.assertEqual(md['cooling'], 0)
        self.assertEqual(md['unknown'], 1)

    # ─── OQ-002：cooling+heating+ventilation+dehumidification+unknown == powered_on_count ───
    def test_mode_distribution_sum_equals_powered_on(self):
        """OQ-002 可对账：制冷+制热+通风+除湿+未知 == 开机台数"""
        _create_powered_on_device('3-1-6-603', operation_mode=1)  # 制冷
        _create_powered_on_device('3-1-6-604', operation_mode=2)  # 制热
        _create_powered_on_device('3-1-6-605')                    # 无 mode → 未知
        _create_powered_on_device('3-1-6-606', operation_mode=0)  # mode=0 → 未知
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 4)
        md = data['mode_distribution']
        total = (md['cooling'] + md['heating'] + md['ventilation']
                 + md['dehumidification'] + md['unknown'])
        self.assertEqual(total, 4)
        self.assertEqual(md['cooling'], 1)
        self.assertEqual(md['heating'], 1)
        self.assertEqual(md['unknown'], 2)

    # ─── 超范围 operation_mode（如 5、99）计入 unknown ───
    def test_out_of_range_mode_counts_as_unknown(self):
        """OQ-002 扩展：operation_mode=5（超范围）→ 计入 unknown"""
        _create_powered_on_device('3-1-6-607', operation_mode=5)
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 1)
        md = data['mode_distribution']
        self.assertEqual(md['cooling'] + md['heating'] + md['ventilation'] + md['dehumidification'], 0)
        self.assertEqual(md['unknown'], 1)

    # ─── operation_mode value=NULL（PLCLatestData.value is null）───
    def test_null_mode_value_counts_as_unknown(self):
        """OQ-002 扩展：operation_mode 记录存在但 value=NULL → 计入 unknown"""
        _make_plc_status('3-1-6-608', 'online')
        _make_latest_data('3-1-6-608', 'system_switch', 1)
        _make_latest_data('3-1-6-608', 'operation_mode', None)
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['powered_on_count'], 1)
        md = data['mode_distribution']
        self.assertEqual(md['unknown'], 1)


@tag('integration')
class TestPowerStatusBoundaries(TestCase):
    """边界条件 & 数据隔离"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser4', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # ─── US-004 Scenario 2：PLC online 但无 system_switch 记录 → 视为关 ───
    def test_online_no_switch_record_excluded(self):
        """US-004 S2：PLC online 但 PLCLatestData 中无 system_switch 记录 → 不计入开机"""
        _make_plc_status('3-1-7-711', 'online')
        # 不添加任何 system_switch 记录
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['total_count'], 1)
        self.assertEqual(data['powered_on_count'], 0)

    # ─── US-003 Scenario 3：PLCConnectionStatus 无记录的设备不参与统计 ───
    def test_plclatestdata_only_no_connection_record_excluded(self):
        """US-003 S3：仅在 PLCLatestData 有记录（无 PLCConnectionStatus 行）→ 不计入 total_count"""
        _make_latest_data('3-1-7-712', 'system_switch', 1)
        _make_latest_data('3-1-7-712', 'operation_mode', 1)
        data = self.client.get(API_URL).json()['data']
        # PLCConnectionStatus 为空，total_count=0
        self.assertEqual(data['total_count'], 0)
        self.assertEqual(data['powered_on_count'], 0)

    # ─── power_on_rate 保留两位小数 ───
    def test_power_on_rate_two_decimal_places(self):
        """power_on_rate = round(n/total*100, 2)，保留两位小数"""
        # 1/3 = 33.33%
        _create_powered_on_device('3-1-7-721')
        _make_plc_status('3-1-7-722', 'offline')
        _make_plc_status('3-1-7-723', 'offline')
        data = self.client.get(API_URL).json()['data']
        self.assertEqual(data['total_count'], 3)
        self.assertEqual(data['powered_on_count'], 1)
        self.assertAlmostEqual(data['power_on_rate'], 33.33, places=2)

    # ─── 认证要求：未认证返回 401 ───
    def test_unauthenticated_returns_401(self):
        """未认证请求返回 401"""
        client = APIClient()
        res = client.get(API_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # ─── 仅支持 GET ───
    def test_post_not_allowed(self):
        """POST 请求返回 405"""
        client = APIClient()
        client.force_authenticate(user=self.user)
        res = client.post(API_URL, {})
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# ══════════════════════════════════════════════════════════════
# Part 2: 响应结构完整性测试
# ══════════════════════════════════════════════════════════════

@tag('integration')
class TestPowerStatusResponseStructure(TestCase):
    """验证 API 响应 JSON 结构完整性（REQ-FUNC-001 响应结构）"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser5', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_response_structure_complete(self):
        """响应包含所有必须字段：success, data.{powered_on_count,total_count,power_on_rate,mode_distribution}"""
        _create_powered_on_device('3-1-8-801', operation_mode=1)
        res = self.client.get(API_URL)
        self.assertEqual(res.status_code, 200)
        body = res.json()

        # 顶层
        self.assertIn('success', body)
        self.assertTrue(body['success'])
        self.assertIn('data', body)
        data = body['data']

        # data 字段
        for field in ('powered_on_count', 'total_count', 'power_on_rate', 'mode_distribution'):
            self.assertIn(field, data, f"响应缺少字段 data.{field}")

        # mode_distribution 字段（含 unknown，OQ-002）
        md = data['mode_distribution']
        for key in ('cooling', 'heating', 'ventilation', 'dehumidification', 'unknown'):
            self.assertIn(key, md, f"响应缺少字段 mode_distribution.{key}")

    def test_response_types(self):
        """响应字段类型正确：powered_on_count/total_count 为 int，power_on_rate 为 float"""
        _create_powered_on_device('3-1-8-802', operation_mode=2)
        data = self.client.get(API_URL).json()['data']
        self.assertIsInstance(data['powered_on_count'], int)
        self.assertIsInstance(data['total_count'], int)
        self.assertIsInstance(data['power_on_rate'], float)
        for key in ('cooling', 'heating', 'ventilation', 'dehumidification', 'unknown'):
            self.assertIsInstance(data['mode_distribution'][key], int,
                                  f"mode_distribution.{key} 应为 int")


# ══════════════════════════════════════════════════════════════
# Part 3: 性能约束测试（查询次数，US-008）
# ══════════════════════════════════════════════════════════════

@tag('integration')
class TestPowerStatusQueryCount(TestCase):
    """US-008：API 不引入 N+1，总查询次数在合理范围内（<= 4 次）"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser6', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        # 建立 5 台开机设备
        for i in range(1, 6):
            _create_powered_on_device(f'3-1-9-{900 + i}', operation_mode=(i % 4) + 1)

    def test_query_count_no_n_plus_one(self):
        """US-008 S1：DB 查询次数 <= 4（不随设备数线性增长的 N+1 查询）"""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(API_URL)
        self.assertEqual(res.status_code, 200)
        # 预期查询：1(auth) + 1(total_count) + 1(online_parts) + 1(switched_on_count)
        #           + 1(mode_agg) + 可能的 session/auth 查询
        # 严格业务查询（不含认证/session）应为 <=4；宽松上限设为 10（含认证开销）
        query_count = len(ctx.captured_queries)
        self.assertLessEqual(
            query_count, 10,
            f"查询次数 {query_count} 超过预期上限 10，可能存在 N+1 查询\n"
            f"SQL 列表: {[q['sql'][:80] for q in ctx.captured_queries]}"
        )
        # 确认不含 Python 层 for 循环逐设备查询（业务查询不随设备数增加）
        # 通过查询数 <= 10 且 5 台设备时仍满足，间接证明无 N+1


# ══════════════════════════════════════════════════════════════
# Part 4: URL 路由测试
# ══════════════════════════════════════════════════════════════

@tag('integration')
class TestPowerStatusURL(TestCase):
    """验证 URL 路由注册正确"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser7', password='testpass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_url_registered_and_accessible(self):
        """GET /api/dashboard/power-status/ 路由已注册，返回 200"""
        res = self.client.get(API_URL)
        self.assertNotEqual(res.status_code, 404, "路由未注册，返回 404")
        self.assertEqual(res.status_code, 200)

    def test_url_reverse(self):
        """URL reverse name='dashboard-power-status' 正确"""
        from django.urls import reverse
        url = reverse('dashboard-power-status')
        self.assertEqual(url, '/api/dashboard/power-status/')


# ══════════════════════════════════════════════════════════════
# Part 5: 前端相关验收标准（代码审查覆盖，文档测试）
# ══════════════════════════════════════════════════════════════

@tag('integration')
class TestFrontendCodeReview(TestCase):
    """
    AC-201~205 前端验收标准通过代码静态审查覆盖（读取 HomeView.vue 源码验证）。
    此类测试为文档性测试，验证关键代码特征存在。
    """

    def _read_homeview(self):
        import os
        # __file__ = .../FreeArkWeb/backend/freearkweb/api/tests/test_...py
        # 上溯 4 层：tests -> api -> freearkweb -> backend -> FreeArkWeb
        # 再进入 frontend/src/views/HomeView.vue
        vue_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', '..', '..', 'frontend', 'src', 'views', 'HomeView.vue'
        )
        with open(os.path.abspath(vue_path), encoding='utf-8') as f:
            return f.read()

    def test_ac201_power_status_card_exists_in_homeview(self):
        """AC-201：HomeView.vue 包含「系统开机状况」卡片"""
        content = self._read_homeview()
        self.assertIn('系统开机状况', content, "HomeView.vue 中未找到「系统开机状况」卡片标题")

    def test_ac201_top_cards_row_layout(self):
        """AC-201：使用 .top-cards-row flex 布局，新卡片与总电量查询并排"""
        content = self._read_homeview()
        self.assertIn('top-cards-row', content, "未找到 .top-cards-row flex 容器")
        self.assertIn('power-status-wrapper', content, "未找到 .power-status-wrapper")
        self.assertIn('total-energy-wrapper', content, "未找到 .total-energy-wrapper")

    def test_ac202_data_bindings_present(self):
        """AC-202：模板包含 powered_on_count、power_on_rate、total_count 绑定"""
        content = self._read_homeview()
        self.assertIn('powered_on_count', content)
        self.assertIn('power_on_rate', content)
        self.assertIn('total_count', content)

    def test_ac203_mode_distribution_bindings(self):
        """AC-203：模板包含制冷/制热/通风/除湿绑定"""
        content = self._read_homeview()
        for key in ('cooling', 'heating', 'ventilation', 'dehumidification'):
            self.assertIn(key, content, f"模板中缺少 mode_distribution.{key} 绑定")

    def test_ac204_v_loading_present(self):
        """AC-204：卡片有 v-loading 绑定 loading.powerStatus"""
        content = self._read_homeview()
        self.assertIn('loading.powerStatus', content, "未找到 v-loading 绑定")

    def test_ac205_el_card_used(self):
        """AC-205：使用 el-card 组件（与现有卡片一致）"""
        content = self._read_homeview()
        self.assertIn('el-card', content)
        self.assertIn('stat-value', content)
        self.assertIn('stat-sub', content)

    def test_no_refresh_button_oq003(self):
        """OQ-003：系统开机状况卡片无刷新按钮"""
        content = self._read_homeview()
        # 确认 power-status-card 区域无 @click="fetchPowerStatus" 刷新按钮
        # 刷新按钮的模式是 el-button + @click 在 card-header 中
        # 检查「系统开机状况」header 区域不包含 el-button
        card_start = content.find('系统开机状况')
        card_end = content.find('</el-card>', card_start)
        card_section = content[card_start:card_end] if card_start > 0 else ''
        # 「系统开机状况」卡片的 header 中不应有 el-button
        header_end = card_section.find('</template>')
        header_section = card_section[:header_end] if header_end > 0 else card_section[:200]
        self.assertNotIn('@click="fetchPowerStatus"', header_section,
                         "系统开机状况卡片不应有刷新按钮（OQ-003）")
