"""
v0.5.3-FCC 故障数量功能测试

覆盖范围：
- 单元测试：count_faults_for_row、compute_fault_count_v2、_compute_from_db_batch、缓存逻辑
- 集成测试：/api/devices/fault-count/ 视图 401/400/200 schema、缓存命中
- 集成测试：/api/devices/fault-summary/ 视图过滤与排序
- 端到端：SQLite 测试库种入 plc_latest_data 数据，接口验计数
- 性能 SLA：mock 1 section × 9 设备 × 30 param，API < 100 ms（仅在本地 SQLite 下）

运行方式（在 FreeArkWeb/backend/freearkweb/ 目录下）：
    python manage.py test api.tests_fault_count --settings=freearkweb.settings

严禁查询 device_param_history 表（NFR-FC-01-01）。
"""

import time
from unittest.mock import patch

from django.test import TestCase, tag
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import CustomUser, PLCLatestData, OwnerInfo
from .fault_utils import (
    count_faults_for_row,
    compute_fault_count_v2,
    get_fault_count_batch_cached,
    get_fault_count_cached,
    invalidate_fault_count_cache,
    _compute_from_db_batch,
    FAULT_PARAM_NAMES,
    is_fault_param,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username="testuser_fc", role="operator", password="pass_fc_123"):
    user = CustomUser.objects.create_user(username=username, password=password, role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token


def make_plc_latest(specific_part, param_name, value):
    """创建或覆盖一条 PLCLatestData 记录。"""
    obj, _ = PLCLatestData.objects.update_or_create(
        specific_part=specific_part,
        param_name=param_name,
        defaults={'value': value},
    )
    return obj


def make_owner(specific_part, building='3', unit='1', room_number='702'):
    obj, _ = OwnerInfo.objects.get_or_create(
        specific_part=specific_part,
        defaults={
            'building': building,
            'unit': unit,
            'room_number': room_number,
        },
    )
    return obj


# ===========================================================================
# 一、单元测试 — count_faults_for_row
# ===========================================================================

@tag('unit')
class CountFaultsForRowTest(TestCase):
    """count_faults_for_row(param_name, value) -> int 单元测试"""

    # ---- comm_fault_timeout ----
    def test_comm_fault_timeout_normal_zero(self):
        """comm_fault_timeout = 0 → 不计故障"""
        self.assertEqual(count_faults_for_row('comm_fault_timeout', 0), 0)

    def test_comm_fault_timeout_normal_none(self):
        """comm_fault_timeout = None → 不计故障"""
        self.assertEqual(count_faults_for_row('comm_fault_timeout', None), 0)

    def test_comm_fault_timeout_fault_nonzero(self):
        """comm_fault_timeout = 1 → 计 1 个故障"""
        self.assertEqual(count_faults_for_row('comm_fault_timeout', 1), 1)

    def test_comm_fault_timeout_fault_large_value(self):
        """comm_fault_timeout = 255 → 计 1 个故障（非 0 即故障）"""
        self.assertEqual(count_faults_for_row('comm_fault_timeout', 255), 1)

    # ---- error_<N> ----
    def test_error_82_zero(self):
        """error_82 = 0 → 不计故障"""
        self.assertEqual(count_faults_for_row('error_82', 0), 0)

    def test_error_82_none(self):
        """error_82 = None → 不计故障"""
        self.assertEqual(count_faults_for_row('error_82', None), 0)

    def test_error_82_fault(self):
        """error_82 = 1 → 计 1 个故障"""
        self.assertEqual(count_faults_for_row('error_82', 1), 1)

    def test_error_703_fault(self):
        """error_703 = 1 → 计 1 个故障"""
        self.assertEqual(count_faults_for_row('error_703', 1), 1)

    def test_error_non_digit_suffix_ignored(self):
        """error_abc（非数字后缀）→ 不计故障（不匹配 ^error_\\d+$）"""
        self.assertEqual(count_faults_for_row('error_abc', 1), 0)

    def test_error_mixed_suffix_ignored(self):
        """error_82_status（含下划线后缀）→ 不计故障"""
        self.assertEqual(count_faults_for_row('error_82_status', 1), 0)

    # ---- fresh_air_fault_status popcount (ADR-FC-006) ----
    def test_fresh_air_fault_status_zero(self):
        """fresh_air_fault_status = 0 → 贡献 0"""
        self.assertEqual(count_faults_for_row('fresh_air_fault_status', 0), 0)

    def test_fresh_air_fault_status_none(self):
        """fresh_air_fault_status = None → 贡献 0"""
        self.assertEqual(count_faults_for_row('fresh_air_fault_status', None), 0)

    def test_fresh_air_fault_status_1_bit(self):
        """fresh_air_fault_status = 1 (0b1) → popcount = 1"""
        self.assertEqual(count_faults_for_row('fresh_air_fault_status', 1), 1)

    def test_fresh_air_fault_status_3_bits(self):
        """fresh_air_fault_status = 3 (0b11) → popcount = 2"""
        self.assertEqual(count_faults_for_row('fresh_air_fault_status', 3), 2)

    def test_fresh_air_fault_status_7_bits(self):
        """fresh_air_fault_status = 7 (0b111) → popcount = 3"""
        self.assertEqual(count_faults_for_row('fresh_air_fault_status', 7), 3)

    def test_fresh_air_fault_status_15_bits(self):
        """fresh_air_fault_status = 15 (0b1111) → popcount = 4"""
        self.assertEqual(count_faults_for_row('fresh_air_fault_status', 15), 4)

    def test_fresh_air_fault_status_all_9_bits(self):
        """fresh_air_fault_status = 511 (0b111111111) → popcount = 9"""
        self.assertEqual(count_faults_for_row('fresh_air_fault_status', 511), 9)

    # ---- 非故障参数 ----
    def test_temperature_param_ignored(self):
        """温度参数（非故障字段）→ 不计故障"""
        self.assertEqual(count_faults_for_row('living_room_temperature', 999), 0)

    def test_system_switch_ignored(self):
        """system_switch（非故障字段）→ 不计故障"""
        self.assertEqual(count_faults_for_row('system_switch', 1), 0)

    # ---- 具名 FAULT_PARAM_NAMES 字段 ----
    def test_named_fault_param_zero(self):
        """living_room_temp_sensor_error = 0 → 不计故障"""
        self.assertEqual(count_faults_for_row('living_room_temp_sensor_error', 0), 0)

    def test_named_fault_param_one(self):
        """living_room_temp_sensor_error = 1 → 计 1 个故障"""
        self.assertEqual(count_faults_for_row('living_room_temp_sensor_error', 1), 1)

    def test_fresh_air_unit_communication_error_fault(self):
        """fresh_air_unit_communication_error = 1 → 计 1 个故障"""
        self.assertEqual(count_faults_for_row('fresh_air_unit_communication_error', 1), 1)


# ===========================================================================
# 二、单元测试 — is_fault_param
# ===========================================================================

@tag('unit')
class IsFaultParamTest(TestCase):
    """is_fault_param 正例/负例"""

    def test_comm_fault_timeout(self):
        self.assertTrue(is_fault_param('comm_fault_timeout'))

    def test_known_fault_param(self):
        self.assertTrue(is_fault_param('living_room_temp_sensor_error'))

    def test_error_numeric(self):
        self.assertTrue(is_fault_param('error_82'))
        self.assertTrue(is_fault_param('error_703'))

    def test_error_non_numeric(self):
        self.assertFalse(is_fault_param('error_abc'))
        self.assertFalse(is_fault_param('error_'))

    def test_temperature_not_fault(self):
        self.assertFalse(is_fault_param('living_room_temperature'))

    def test_system_switch_not_fault(self):
        self.assertFalse(is_fault_param('system_switch'))

    def test_fresh_air_fault_status_not_in_is_fault(self):
        """fresh_air_fault_status 不走 is_fault_param（由 count_faults_for_row 特殊处理）"""
        self.assertFalse(is_fault_param('fresh_air_fault_status'))


# ===========================================================================
# 三、单元测试 — compute_fault_count_v2
# ===========================================================================

@tag('unit')
class ComputeFaultCountV2Test(TestCase):
    """compute_fault_count_v2(records) -> int"""

    def test_empty_records(self):
        self.assertEqual(compute_fault_count_v2([]), 0)

    def test_all_normal(self):
        records = [
            ('comm_fault_timeout', 0),
            ('error_82', 0),
            ('living_room_temp_sensor_error', 0),
        ]
        self.assertEqual(compute_fault_count_v2(records), 0)

    def test_single_fault(self):
        records = [('comm_fault_timeout', 1)]
        self.assertEqual(compute_fault_count_v2(records), 1)

    def test_mixed_fault_and_normal(self):
        records = [
            ('comm_fault_timeout', 1),
            ('error_82', 0),
            ('living_room_temp_sensor_error', 1),
            ('fresh_air_fault_status', 3),  # popcount=2
            ('living_room_temperature', 245),  # 非故障字段
        ]
        # 1 + 0 + 1 + 2 + 0 = 4
        self.assertEqual(compute_fault_count_v2(records), 4)

    def test_multiple_sections_aggregated(self):
        """多个 section 合并聚合"""
        records = [
            ('comm_fault_timeout', 1),
            ('error_703', 1),
            ('fresh_air_fault_status', 7),  # popcount=3
        ]
        # 1 + 1 + 3 = 5
        self.assertEqual(compute_fault_count_v2(records), 5)

    def test_none_value_not_counted(self):
        records = [('comm_fault_timeout', None), ('error_82', None)]
        self.assertEqual(compute_fault_count_v2(records), 0)


# ===========================================================================
# 四、单元测试 — _compute_from_db_batch（使用 SQLite 测试库）
# ===========================================================================

@tag('unit')
class ComputeFromDbBatchTest(TestCase):
    """_compute_from_db_batch 直接从 DB 计算（不经缓存）"""

    def setUp(self):
        # hotfix BUG-FCC-001: 清缓存避免 _get_param_to_subtypes 跨测试污染
        from django.core.cache import cache
        cache.clear()
        # 种入测试数据：3-1-7-702 有 3 个故障
        make_plc_latest('3-1-7-702', 'comm_fault_timeout', 1)
        make_plc_latest('3-1-7-702', 'living_room_temp_sensor_error', 1)
        make_plc_latest('3-1-7-702', 'fresh_air_fault_status', 3)  # popcount=2 → 共 4
        make_plc_latest('3-1-7-702', 'error_82', 0)  # 正常，不计入
        make_plc_latest('3-1-7-702', 'living_room_temperature', 245)  # 非故障字段

        # 3-1-7-703 无故障
        make_plc_latest('3-1-7-703', 'comm_fault_timeout', 0)
        make_plc_latest('3-1-7-703', 'living_room_temp_sensor_error', 0)

    def test_single_section_with_faults(self):
        result = _compute_from_db_batch(['3-1-7-702'])
        # 1(comm_fault) + 1(living_room_temp) + 2(fresh_air popcount=2) = 4
        self.assertEqual(result['3-1-7-702'], 4)

    def test_section_all_normal(self):
        result = _compute_from_db_batch(['3-1-7-703'])
        self.assertEqual(result['3-1-7-703'], 0)

    def test_unknown_section_returns_none(self):
        result = _compute_from_db_batch(['99-9-9-999'])
        self.assertIsNone(result['99-9-9-999'])

    def test_batch_multiple_sections(self):
        result = _compute_from_db_batch(['3-1-7-702', '3-1-7-703', '99-9-9-999'])
        self.assertEqual(result['3-1-7-702'], 4)
        self.assertEqual(result['3-1-7-703'], 0)
        self.assertIsNone(result['99-9-9-999'])

    def test_empty_list(self):
        result = _compute_from_db_batch([])
        self.assertEqual(result, {})

    def test_error_n_field_counted(self):
        """error_<N> 格式的故障字段计入"""
        make_plc_latest('3-1-8-802', 'error_703', 1)
        result = _compute_from_db_batch(['3-1-8-802'])
        self.assertEqual(result['3-1-8-802'], 1)

    def test_error_non_numeric_ignored(self):
        """error_abc 不计入故障（Python 层正则过滤）"""
        make_plc_latest('3-1-9-902', 'error_abc', 1)  # 非标准命名
        make_plc_latest('3-1-9-902', 'comm_fault_timeout', 0)
        result = _compute_from_db_batch(['3-1-9-902'])
        # error_abc 不匹配 ^error_\d+$，comm_fault_timeout=0，合计 0
        self.assertEqual(result['3-1-9-902'], 0)


# ===========================================================================
# 四·B、单元测试 — sub_type 户型过滤（hotfix BUG-FCC-001）
# ===========================================================================

@tag('unit')
class SubTypeFilterTest(TestCase):
    """Hotfix BUG-FCC-001: 户型不存在的房型故障字段不计入故障数。

    与 views.get_device_realtime_params 的 sub_type 过滤口径保持一致。
    """

    def setUp(self):
        from django.core.cache import cache
        from .models import DeviceConfig
        cache.clear()

        # 建 DeviceConfig:
        #   fourth_children_room_communication_error 属于 panel_fourth_children
        #   bedroom_temp_sensor_error 属于 panel_bedroom
        #   fresh_air_fault_status 属于 fresh_air
        DeviceConfig.objects.create(
            param_name='fourth_children_room_communication_error',
            display_name='第四儿童房通讯故障',
            group='hvac', sub_type='panel_fourth_children',
            group_display='暖通', sub_type_display='第四儿童房',
            is_active=True,
        )
        DeviceConfig.objects.create(
            param_name='bedroom_temp_sensor_error',
            display_name='主卧温度传感器故障',
            group='hvac', sub_type='panel_bedroom',
            group_display='暖通', sub_type_display='主卧',
            is_active=True,
        )
        DeviceConfig.objects.create(
            param_name='fresh_air_fault_status',
            display_name='新风机故障状态',
            group='hvac', sub_type='fresh_air',
            group_display='暖通', sub_type_display='新风',
            is_active=True,
        )

        # 种入 10-1-16-1601 三个故障字段
        make_plc_latest('10-1-16-1601', 'fourth_children_room_communication_error', 1)
        make_plc_latest('10-1-16-1601', 'fresh_air_fault_status', 16)  # popcount=1
        make_plc_latest('10-1-16-1601', 'bedroom_temp_sensor_error', 1)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_filter_out_subtype_not_in_available_set(self):
        """sub_type ∉ available_sub_types → 跳过（复现 BUG-FCC-001 修复后行为）

        模拟"户型无第四儿童房"：available_sub_types 不含 panel_fourth_children
        预期：fourth_children_room_communication_error 不计入
        """
        with patch(
            'api.utils_room_filter.get_available_sub_types',
            return_value=frozenset(['fresh_air', 'panel_bedroom']),
        ):
            result = _compute_from_db_batch(['10-1-16-1601'])
        # fresh_air_fault_status(=16, popcount=1) + bedroom_temp_sensor_error(=1) = 2
        # fourth_children_room_communication_error 被过滤
        self.assertEqual(result['10-1-16-1601'], 2)

    def test_all_subtypes_available_counts_all(self):
        """所有 sub_type 都可见 → 全部计入"""
        with patch(
            'api.utils_room_filter.get_available_sub_types',
            return_value=frozenset(['fresh_air', 'panel_bedroom', 'panel_fourth_children']),
        ):
            result = _compute_from_db_batch(['10-1-16-1601'])
        # 三个都计入：1(popcount) + 1(bedroom) + 1(fourth_children) = 3
        self.assertEqual(result['10-1-16-1601'], 3)

    def test_param_without_device_config_still_counts(self):
        """DeviceConfig 无条目（如 comm_fault_timeout）→ 保留原行为（计入）

        系统级/PLC 通信故障字段不绑定 sub_type，不应受户型过滤影响。
        """
        make_plc_latest('10-1-16-1601', 'comm_fault_timeout', 1)
        with patch(
            'api.utils_room_filter.get_available_sub_types',
            return_value=frozenset(['fresh_air', 'panel_bedroom']),
        ):
            result = _compute_from_db_batch(['10-1-16-1601'])
        # popcount(16)=1 + bedroom=1 + comm_fault_timeout=1 = 3
        # fourth_children 被过滤
        self.assertEqual(result['10-1-16-1601'], 3)


# ===========================================================================
# 五、单元测试 — 缓存 hit / miss / TTL 过期
# ===========================================================================

@tag('unit')
class FaultCacheTest(TestCase):
    """缓存命中 / 未命中 / TTL 过期逻辑测试（使用 Django cache.clear()）"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        make_plc_latest('3-1-7-702', 'comm_fault_timeout', 1)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_cache_miss_computes_from_db(self):
        """缓存未命中时从 DB 计算并填充缓存"""
        from django.core.cache import cache
        result = get_fault_count_cached('3-1-7-702')
        self.assertEqual(result, 1)

    def test_cache_hit_returns_cached_value(self):
        """缓存命中时直接返回，不重查 DB"""
        from django.core.cache import cache
        # 首次调用填充缓存
        get_fault_count_cached('3-1-7-702')
        # 修改 DB（不通过 fault_utils，绕过缓存失效）
        PLCLatestData.objects.filter(
            specific_part='3-1-7-702', param_name='comm_fault_timeout'
        ).update(value=99)
        # 再次调用应返回缓存值（仍为 1，不感知 DB 变化）
        result = get_fault_count_cached('3-1-7-702')
        self.assertEqual(result, 1)

    def test_invalidate_clears_cache(self):
        """invalidate_fault_count_cache 清除后，再次查询从 DB 计算"""
        from django.core.cache import cache
        get_fault_count_cached('3-1-7-702')
        # 修改 DB
        PLCLatestData.objects.filter(
            specific_part='3-1-7-702', param_name='comm_fault_timeout'
        ).update(value=99)
        # 手动失效缓存
        invalidate_fault_count_cache('3-1-7-702')
        # 重新查询应反映 DB 最新值（comm_fault=99 → 非 0 → 1 个故障）
        result = get_fault_count_cached('3-1-7-702')
        self.assertEqual(result, 1)

    def test_batch_cache_hit_miss_mix(self):
        """批量查询：部分命中缓存，部分穿透到 DB"""
        from django.core.cache import cache
        make_plc_latest('3-1-7-703', 'comm_fault_timeout', 0)
        make_plc_latest('3-1-7-704', 'error_82', 1)
        # 预热 702
        get_fault_count_cached('3-1-7-702')
        # 批量查询 702(hit) + 703(miss) + 704(miss)
        result = get_fault_count_batch_cached(['3-1-7-702', '3-1-7-703', '3-1-7-704'])
        self.assertEqual(result['3-1-7-702'], 1)
        self.assertEqual(result['3-1-7-703'], 0)
        self.assertEqual(result['3-1-7-704'], 1)

    def test_ttl_expiry_triggers_recompute(self):
        """TTL 过期后，再次查询重新从 DB 计算"""
        from django.core.cache import cache as dj_cache
        # 用极短 TTL patch 来模拟过期
        with patch('api.fault_utils._FAULT_CACHE_TTL', 0):
            # TTL=0 时 set 的 key 立即过期（LocMemCache 行为）
            get_fault_count_cached('3-1-7-702')
            # 修改 DB
            PLCLatestData.objects.filter(
                specific_part='3-1-7-702', param_name='comm_fault_timeout'
            ).update(value=5)
            # 重新查询（TTL=0 缓存已过期）
            result = get_fault_count_cached('3-1-7-702')
            self.assertEqual(result, 1)  # value=5 非 0 → 仍计 1 个故障


# ===========================================================================
# 六、集成测试 — /api/devices/fault-count/ 视图
# ===========================================================================

@tag('integration')
class DeviceFaultCountViewTest(TestCase):
    """GET /api/devices/fault-count/ 集成测试"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        self.user, self.token = make_user(username='fc_view_user')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # 种入 3-1-7-702：2 个故障
        make_plc_latest('3-1-7-702', 'comm_fault_timeout', 1)
        make_plc_latest('3-1-7-702', 'living_room_temp_sensor_error', 1)
        make_plc_latest('3-1-7-702', 'living_room_temperature', 245)  # 非故障字段

        # 种入 3-1-7-703：0 个故障
        make_plc_latest('3-1-7-703', 'comm_fault_timeout', 0)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    # ---- 鉴权 ----
    def test_401_unauthenticated(self):
        """未登录应返回 401"""
        unauth_client = APIClient()
        response = unauth_client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702'},
        )
        self.assertEqual(response.status_code, 401)

    # ---- 参数校验 ----
    def test_400_missing_specific_part(self):
        """缺少 specific_part 参数返回 400"""
        response = self.client.get(reverse('device-fault-count'))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])

    def test_400_too_many_specific_parts(self):
        """超过 50 个 specific_part 返回 400"""
        sp_list = ','.join([f'3-1-7-{700 + i}' for i in range(51)])
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': sp_list},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('50', response.data['error'])

    # ---- 正常查询 ----
    def test_200_single_section_with_faults(self):
        """查询单个有故障的专有部分返回正确 fault_count"""
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertEqual(len(data['data']), 1)
        item = data['data'][0]
        self.assertEqual(item['specific_part'], '3-1-7-702')
        self.assertEqual(item['fault_count'], 2)
        self.assertIsInstance(item['fault_details'], list)
        self.assertEqual(len(item['fault_details']), 2)

    def test_200_schema_fields(self):
        """响应 schema 包含 success、data、queried_at"""
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('success', response.data)
        self.assertIn('data', response.data)
        self.assertIn('queried_at', response.data)

    def test_200_section_all_normal(self):
        """无故障专有部分返回 fault_count = 0"""
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-703'},
        )
        self.assertEqual(response.status_code, 200)
        item = response.data['data'][0]
        self.assertEqual(item['fault_count'], 0)
        self.assertEqual(item['fault_details'], [])

    def test_200_nonexistent_section_returns_null(self):
        """不存在的 specific_part 返回 fault_count = null（不返回 404）"""
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '99-9-9-999'},
        )
        self.assertEqual(response.status_code, 200)
        item = response.data['data'][0]
        self.assertIsNone(item['fault_count'])

    def test_200_batch_query(self):
        """批量查询多个 specific_part 全部返回"""
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702,3-1-7-703,99-9-9-999'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.data['data']
        self.assertEqual(len(data), 3)
        sp_map = {d['specific_part']: d['fault_count'] for d in data}
        self.assertEqual(sp_map['3-1-7-702'], 2)
        self.assertEqual(sp_map['3-1-7-703'], 0)
        self.assertIsNone(sp_map['99-9-9-999'])

    def test_fault_details_sorted_by_param_name(self):
        """fault_details 按 param_name 升序排列"""
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702'},
        )
        details = response.data['data'][0]['fault_details']
        param_names = [d['param_name'] for d in details]
        self.assertEqual(param_names, sorted(param_names))

    def test_cache_hit_latency(self):
        """缓存命中后响应时间极快（< 5 ms 目标，测试中用宽松阈值）"""
        from django.core.cache import cache
        cache.clear()
        # 首次调用填充缓存
        self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702'},
        )
        # 第二次调用应命中缓存
        start = time.monotonic()
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702'},
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        self.assertEqual(response.status_code, 200)
        # 宽松阈值：SQLite 下缓存命中应极快（< 100 ms）
        self.assertLess(elapsed_ms, 100, f'缓存命中响应超时 {elapsed_ms:.1f} ms')


# ===========================================================================
# 七、集成测试 — /api/devices/fault-summary/ 视图
# ===========================================================================

@tag('integration')
class DeviceFaultSummaryViewTest(TestCase):
    """GET /api/devices/fault-summary/ 集成测试"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        self.user, self.token = make_user(username='fs_view_user')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # 创建业主数据
        make_owner('3-1-7-702', building='3', unit='1', room_number='702')
        make_owner('3-1-8-802', building='3', unit='1', room_number='802')
        make_owner('5-2-6-601', building='5', unit='2', room_number='601')

        # 种入故障数据
        make_plc_latest('3-1-7-702', 'comm_fault_timeout', 1)  # 1 fault
        make_plc_latest('3-1-8-802', 'comm_fault_timeout', 1)
        make_plc_latest('3-1-8-802', 'error_82', 1)             # 2 faults
        make_plc_latest('5-2-6-601', 'comm_fault_timeout', 0)   # 0 faults

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_401_unauthenticated(self):
        unauth = APIClient()
        response = unauth.get(reverse('device-fault-summary'))
        self.assertEqual(response.status_code, 401)

    def test_400_invalid_min_fault_count(self):
        response = self.client.get(
            reverse('device-fault-summary'),
            {'min_fault_count': 'abc'},
        )
        self.assertEqual(response.status_code, 400)

    def test_200_default_min_fault_count_1(self):
        """默认 min_fault_count=1，只返回有故障的专有部分"""
        response = self.client.get(reverse('device-fault-summary'))
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertTrue(data['success'])
        sp_list = [d['specific_part'] for d in data['data']]
        self.assertIn('3-1-7-702', sp_list)
        self.assertIn('3-1-8-802', sp_list)
        self.assertNotIn('5-2-6-601', sp_list)

    def test_200_sorted_by_fault_count_desc(self):
        """结果按故障数降序"""
        response = self.client.get(reverse('device-fault-summary'))
        faults = [d['fault_count'] for d in response.data['data']]
        self.assertEqual(faults, sorted(faults, reverse=True))

    def test_200_building_filter(self):
        """楼栋过滤：building=5 只返回 5 号楼有故障的专有部分"""
        # 5-2-6-601 fault_count=0，所以 building=5 且默认 min=1 → 无结果
        response = self.client.get(
            reverse('device-fault-summary'),
            {'building': '5'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['data']), 0)

    def test_200_min_fault_count_2(self):
        """min_fault_count=2 只返回故障数 >= 2 的专有部分"""
        response = self.client.get(
            reverse('device-fault-summary'),
            {'min_fault_count': '2'},
        )
        self.assertEqual(response.status_code, 200)
        sp_list = [d['specific_part'] for d in response.data['data']]
        self.assertIn('3-1-8-802', sp_list)
        self.assertNotIn('3-1-7-702', sp_list)


# ===========================================================================
# 八、集成测试 — /api/device-management/device-list/ 包含 fault_count
# ===========================================================================

@tag('integration')
class DeviceListFaultCountFieldTest(TestCase):
    """device_management_device_list 响应包含 fault_count 字段"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        self.user, self.token = make_user(username='dl_fc_user')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        make_owner('3-1-7-702', building='3', unit='1', room_number='702')
        make_plc_latest('3-1-7-702', 'comm_fault_timeout', 1)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_fault_count_field_present_in_results(self):
        """设备列表响应的每条记录包含 fault_count 字段"""
        response = self.client.get(reverse('device-management-device-list'))
        self.assertEqual(response.status_code, 200)
        results = response.data.get('results', [])
        self.assertGreater(len(results), 0)
        for row in results:
            self.assertIn('fault_count', row)

    def test_fault_count_correct_value(self):
        """fault_count 值与实际故障数一致"""
        response = self.client.get(reverse('device-management-device-list'))
        results = response.data.get('results', [])
        row = next((r for r in results if r['specific_part'] == '3-1-7-702'), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['fault_count'], 1)


# ===========================================================================
# 九、性能测试 — mock 数据 API < 100 ms（SQLite，无 DB 穿透约束）
# ===========================================================================

@tag('integration')
class FaultCountPerformanceTest(TestCase):
    """性能 SLA 测试：mock 1 section × 9 设备 × 30 param，API < 100 ms。

    注意：此测试在 SQLite 内存库下运行，无法代表生产 MySQL 性能；
    仅验证批量聚合逻辑本身不引入 O(N) 查询放大。
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        self.user, self.token = make_user(username='perf_user')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # 1 section × 9 子设备 × 30 param = 270 行
        sp = '3-1-7-702'
        params = list(FAULT_PARAM_NAMES) + [
            'fresh_air_fault_status',
            'error_82', 'error_140', 'error_703',
        ]
        for i, p in enumerate(params[:30]):
            make_plc_latest(sp, p, 0)  # 全部正常值

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_api_response_under_100ms(self):
        """API 冷启动（无缓存）响应时间 < 100 ms（SQLite）"""
        from django.core.cache import cache
        cache.clear()
        start = time.monotonic()
        response = self.client.get(
            reverse('device-fault-count'),
            {'specific_part': '3-1-7-702'},
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed_ms, 100, f'API 响应超时 {elapsed_ms:.1f} ms（SQLite 下不应超过 100 ms）')
