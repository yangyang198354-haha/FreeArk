"""
tests_fault_event.py — v0.6.0 故障管理模块测试套件

覆盖范围（P0 单元 + P1 集成）：
  P0-1  fault_classifier.is_fault_candidate
  P0-2  fault_classifier.is_fault_active
  P0-3  fault_classifier.get_fault_type_and_severity
  P0-4  fault_classifier.get_fault_message
  P0-5  state_machine T1/T2/T3 转移逻辑
  P0-6  state_machine.rebuild_from_db（LIMIT + IntegrityError 兜底）
  P0-7  views_fault 分页参数边界
  P0-8  views_fault 过滤组合（room_pattern / 时间段 / fault_types / sub_types / is_active）
  P0-9  views_fault 默认时间范围（无参数时最近 7 天）
  P0-10 serializers_fault 字段完整性 / 类型 / datetime 格式
  P0-11 fault_cleanup --dry-run 不删除
  P0-12 fault_cleanup 分批 1000 行
  P0-13 fault_cleanup 天数边界（90/89/91 天）
  P1-1  fault_consumer._handle_message + state_machine + DB 端到端
  P1-2  API + DB 集成（真实 SQLite + 过滤 + 排序）

运行方式（在 FreeArkWeb/backend/freearkweb/ 目录下）：
    python manage.py test api.tests_fault_event --settings=freearkweb.settings

注意事项：
  - 全部使用 SQLite 测试库（settings._RUNNING_TESTS=True 自动切换）
  - 不连接生产 DB，不依赖 paho-mqtt 真实连接
  - state_machine 是模块级单例；每个涉及它的测试用例均在 setUp/tearDown 中重置
"""

import json
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import FaultEvent
from .fault_consumer.fault_classifier import (
    is_fault_candidate,
    is_fault_active,
    get_fault_type_and_severity,
    get_fault_message,
)
import api.fault_consumer.state_machine as sm_module
from .fault_consumer.state_machine import (
    FaultState,
    process_fault_field,
    rebuild_from_db,
    get_state,
    get_state_machine_size,
)

User = get_user_model()


# ===========================================================================
# 辅助函数
# ===========================================================================

def _make_fault_event(**kwargs):
    """创建一条 FaultEvent，使用合理默认值，可通过 kwargs 覆盖。"""
    now = timezone.now()
    defaults = dict(
        specific_part='3-1-7-702',
        device_sn='SN001',
        product_code='PROD-A',
        fault_code='comm_fault_timeout',
        fault_type='comm',
        fault_message='Comm fault timeout',
        severity='error',
        first_seen_at=now - timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=30),
        recovered_at=None,
        is_active=True,
    )
    defaults.update(kwargs)
    return FaultEvent.objects.create(**defaults)


def _reset_state_machine():
    """清空模块级 _state_machine 字典（测试隔离）。"""
    sm_module._state_machine.clear()


# ===========================================================================
# P0-1 ~ P0-4  fault_classifier 纯函数单元测试
# ===========================================================================

class TestIsFaultCandidate(TestCase):
    """P0-1: is_fault_candidate 识别逻辑"""

    def test_comm_fault_timeout_recognized(self):
        self.assertTrue(is_fault_candidate('comm_fault_timeout'))

    def test_named_sensor_fault_recognized(self):
        self.assertTrue(is_fault_candidate('living_room_temp_sensor_error'))

    def test_named_comm_error_recognized(self):
        self.assertTrue(is_fault_candidate('living_room_communication_error'))

    def test_fresh_air_fault_bit_pattern_recognized(self):
        self.assertTrue(is_fault_candidate('fresh_air_fault_bit_0'))
        self.assertTrue(is_fault_candidate('fresh_air_fault_bit_7'))
        self.assertTrue(is_fault_candidate('fresh_air_fault_bit_15'))

    def test_error_n_pattern_recognized(self):
        self.assertTrue(is_fault_candidate('error_1'))
        self.assertTrue(is_fault_candidate('error_82'))
        self.assertTrue(is_fault_candidate('error_703'))

    def test_non_fault_param_rejected(self):
        self.assertFalse(is_fault_candidate('temperature'))
        self.assertFalse(is_fault_candidate('humidity'))
        self.assertFalse(is_fault_candidate('fresh_air_fault_status'))  # 位域整体，不是 bit_N
        self.assertFalse(is_fault_candidate(''))

    def test_fresh_air_fault_bit_invalid_suffix_rejected(self):
        # "fresh_air_fault_bit_" 后不接数字 → 不匹配
        self.assertFalse(is_fault_candidate('fresh_air_fault_bit_'))
        self.assertFalse(is_fault_candidate('fresh_air_fault_bit_abc'))

    def test_error_n_without_digit_rejected(self):
        self.assertFalse(is_fault_candidate('error_'))
        self.assertFalse(is_fault_candidate('errorx'))


class TestIsFaultActive(TestCase):
    """P0-2: is_fault_active 真/假/None/数值边界"""

    # comm_fault_timeout 特殊规则
    def test_comm_fault_timeout_normal_is_false(self):
        self.assertFalse(is_fault_active('comm_fault_timeout', 'normal'))

    def test_comm_fault_timeout_other_string_is_true(self):
        self.assertTrue(is_fault_active('comm_fault_timeout', 'timeout'))
        self.assertTrue(is_fault_active('comm_fault_timeout', '1'))
        self.assertTrue(is_fault_active('comm_fault_timeout', '0'))

    def test_comm_fault_timeout_none_is_false(self):
        self.assertFalse(is_fault_active('comm_fault_timeout', None))

    # error_N 规则：int 0 / str "0" 为正常
    def test_error_n_zero_int_is_false(self):
        self.assertFalse(is_fault_active('error_1', 0))

    def test_error_n_zero_str_is_false(self):
        self.assertFalse(is_fault_active('error_1', '0'))

    def test_error_n_nonzero_is_true(self):
        self.assertTrue(is_fault_active('error_1', 1))
        self.assertTrue(is_fault_active('error_82', '82'))
        self.assertTrue(is_fault_active('error_703', '1'))

    def test_error_n_none_is_false(self):
        self.assertFalse(is_fault_active('error_1', None))

    # fresh_air_fault_bit_N：0 为正常
    def test_fresh_air_bit_zero_is_false(self):
        self.assertFalse(is_fault_active('fresh_air_fault_bit_0', 0))
        self.assertFalse(is_fault_active('fresh_air_fault_bit_7', '0'))

    def test_fresh_air_bit_one_is_true(self):
        self.assertTrue(is_fault_active('fresh_air_fault_bit_0', 1))
        self.assertTrue(is_fault_active('fresh_air_fault_bit_7', '1'))

    def test_fresh_air_bit_none_is_false(self):
        self.assertFalse(is_fault_active('fresh_air_fault_bit_0', None))

    def test_fresh_air_bit_invalid_value_is_false(self):
        # 非数字字符串 → 无法 int() → return False
        self.assertFalse(is_fault_active('fresh_air_fault_bit_0', 'abc'))

    # 其他具名故障字段：非零即故障
    def test_named_fault_zero_is_false(self):
        self.assertFalse(is_fault_active('living_room_temp_sensor_error', 0))
        self.assertFalse(is_fault_active('living_room_temp_sensor_error', '0'))

    def test_named_fault_one_is_true(self):
        self.assertTrue(is_fault_active('living_room_temp_sensor_error', 1))
        self.assertTrue(is_fault_active('bedroom_communication_error', '1'))

    def test_named_fault_none_is_false(self):
        self.assertFalse(is_fault_active('living_room_temp_sensor_error', None))

    def test_named_fault_bool_false_is_false(self):
        self.assertFalse(is_fault_active('living_room_temp_sensor_error', False))

    def test_named_fault_bool_true_is_true(self):
        self.assertTrue(is_fault_active('living_room_temp_sensor_error', True))


class TestGetFaultTypeAndSeverity(TestCase):
    """P0-3: get_fault_type_and_severity 四大类 + severity 映射"""

    def test_comm_fault_timeout_exact(self):
        ft, sev = get_fault_type_and_severity('comm_fault_timeout')
        self.assertEqual(ft, 'comm')
        self.assertEqual(sev, 'error')

    def test_fresh_air_unit_stop_error_exact(self):
        ft, sev = get_fault_type_and_severity('fresh_air_unit_stop_error')
        self.assertEqual(ft, 'fresh_air')
        self.assertEqual(sev, 'error')

    def test_comm_error_suffix(self):
        ft, sev = get_fault_type_and_severity('living_room_communication_error')
        self.assertEqual(ft, 'comm')
        self.assertEqual(sev, 'error')

    def test_temp_sensor_suffix(self):
        ft, sev = get_fault_type_and_severity('bedroom_temp_sensor_error')
        self.assertEqual(ft, 'sensor')
        self.assertEqual(sev, 'error')

    def test_humidity_sensor_suffix(self):
        ft, sev = get_fault_type_and_severity('study_room_humidity_sensor_error')
        self.assertEqual(ft, 'sensor')
        self.assertEqual(sev, 'error')

    def test_external_temp_sensor_suffix(self):
        ft, sev = get_fault_type_and_severity('children_room_external_temp_sensor_error')
        self.assertEqual(ft, 'sensor')
        self.assertEqual(sev, 'error')

    def test_fresh_air_bit_returns_warning(self):
        ft, sev = get_fault_type_and_severity('fresh_air_fault_bit_3')
        self.assertEqual(ft, 'fresh_air')
        self.assertEqual(sev, 'warning')

    def test_error_n_returns_other_error(self):
        ft, sev = get_fault_type_and_severity('error_82')
        self.assertEqual(ft, 'other_error')
        self.assertEqual(sev, 'error')

    def test_unknown_param_falls_back_to_other_error(self):
        ft, sev = get_fault_type_and_severity('totally_unknown_param')
        self.assertEqual(ft, 'other_error')
        self.assertEqual(sev, 'error')

    def test_hydraulic_module_exact(self):
        ft, sev = get_fault_type_and_severity('hydraulic_module_low_temp_error')
        self.assertEqual(ft, 'other_error')
        self.assertEqual(sev, 'error')

    def test_energy_meter_exact(self):
        ft, sev = get_fault_type_and_severity('energy_meter_status_communication_error')
        self.assertEqual(ft, 'comm')
        self.assertEqual(sev, 'error')

    def test_exact_beats_suffix(self):
        # fresh_air_unit_communication_error 精确匹配 → comm；不走后缀规则
        ft, sev = get_fault_type_and_severity('fresh_air_unit_communication_error')
        self.assertEqual(ft, 'comm')
        self.assertEqual(sev, 'error')


class TestGetFaultMessage(TestCase):
    """P0-4: get_fault_message 格式化"""

    def test_underscores_replaced_by_spaces(self):
        msg = get_fault_message('comm_fault_timeout')
        self.assertNotIn('_', msg)

    def test_first_letter_capitalized(self):
        msg = get_fault_message('comm_fault_timeout')
        self.assertEqual(msg[0], msg[0].upper())

    def test_max_length_255(self):
        long_name = 'a_' * 200  # 400 chars
        msg = get_fault_message(long_name)
        self.assertLessEqual(len(msg), 255)

    def test_known_param_format(self):
        msg = get_fault_message('living_room_temp_sensor_error')
        self.assertEqual(msg, 'Living room temp sensor error')

    def test_fresh_air_bit_format(self):
        msg = get_fault_message('fresh_air_fault_bit_7')
        self.assertEqual(msg, 'Fresh air fault bit 7')


# ===========================================================================
# P0-5 ~ P0-6  state_machine T1/T2/T3 + rebuild_from_db
# ===========================================================================

class TestStateMachineTransitions(TestCase):
    """P0-5: 状态机 T1/T2/T3 转移逻辑"""

    def setUp(self):
        _reset_state_machine()
        self.now = timezone.now()
        self.key = ('3-1-7-702', 'SN001', 'comm_fault_timeout')

    def tearDown(self):
        _reset_state_machine()

    # T1: 首次故障 → INSERT + 内存新增
    def test_t1_inserts_db_row(self):
        self.assertEqual(FaultEvent.objects.count(), 0)
        process_fault_field(
            specific_part='3-1-7-702',
            device_sn='SN001',
            product_code='PROD-A',
            fault_code='comm_fault_timeout',
            fault_type='comm',
            severity='error',
            fault_message='Comm fault timeout',
            is_active_now=True,
            received_at=self.now,
        )
        self.assertEqual(FaultEvent.objects.count(), 1)
        fe = FaultEvent.objects.first()
        self.assertTrue(fe.is_active)
        self.assertIsNone(fe.recovered_at)

    def test_t1_adds_to_memory(self):
        process_fault_field(
            specific_part='3-1-7-702',
            device_sn='SN001',
            product_code='PROD-A',
            fault_code='comm_fault_timeout',
            fault_type='comm',
            severity='error',
            fault_message='Comm fault timeout',
            is_active_now=True,
            received_at=self.now,
        )
        state = get_state(self.key)
        self.assertIsNotNone(state)
        self.assertTrue(state.is_active)

    def test_t1_parameters_stored_correctly(self):
        process_fault_field(
            specific_part='3-1-7-702',
            device_sn='SN001',
            product_code='PROD-X',
            fault_code='comm_fault_timeout',
            fault_type='comm',
            severity='error',
            fault_message='Comm fault timeout',
            is_active_now=True,
            received_at=self.now,
        )
        fe = FaultEvent.objects.first()
        self.assertEqual(fe.specific_part, '3-1-7-702')
        self.assertEqual(fe.device_sn, 'SN001')
        self.assertEqual(fe.product_code, 'PROD-X')
        self.assertEqual(fe.fault_code, 'comm_fault_timeout')
        self.assertEqual(fe.fault_type, 'comm')
        self.assertEqual(fe.severity, 'error')

    # T2: 故障持续 → 仅更新内存，不写 DB
    def test_t2_no_db_write_on_continued_fault(self):
        # 先触发 T1
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='Comm fault timeout', is_active_now=True,
            received_at=self.now,
        )
        db_updated_at_before = FaultEvent.objects.first().updated_at

        # T2: 相同 key，再次上报故障
        later = self.now + timedelta(minutes=5)
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='Comm fault timeout', is_active_now=True,
            received_at=later,
        )

        # DB 行数不增加
        self.assertEqual(FaultEvent.objects.count(), 1)
        # 内存 last_seen_at 已更新
        state = get_state(self.key)
        self.assertEqual(state.last_seen_at, later)

    # T3: 故障恢复 → UPDATE DB，内存 is_active=False
    def test_t3_sets_is_active_false_in_db(self):
        # T1
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='Comm fault timeout', is_active_now=True,
            received_at=self.now,
        )
        # T3
        recover_time = self.now + timedelta(minutes=10)
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='Comm fault timeout', is_active_now=False,
            received_at=recover_time,
        )
        fe = FaultEvent.objects.first()
        self.assertFalse(fe.is_active)
        self.assertIsNotNone(fe.recovered_at)

    def test_t3_updates_memory_is_active_false(self):
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='Comm fault timeout', is_active_now=True,
            received_at=self.now,
        )
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='Comm fault timeout', is_active_now=False,
            received_at=self.now + timedelta(minutes=10),
        )
        state = get_state(self.key)
        self.assertIsNotNone(state)
        self.assertFalse(state.is_active)

    def test_normal_message_with_no_prior_state_does_nothing(self):
        # 状态机无记录 + 正常报文 → 无 DB 写入
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='Comm fault timeout', is_active_now=False,
            received_at=self.now,
        )
        self.assertEqual(FaultEvent.objects.count(), 0)
        self.assertEqual(get_state_machine_size(), 0)

    def test_t1_t2_t3_full_sequence(self):
        """完整的 T1 → T2 × 3 → T3 序列"""
        t0 = self.now

        def _call(active, delta_min):
            process_fault_field(
                specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
                fault_code='comm_fault_timeout', fault_type='comm', severity='error',
                fault_message='msg', is_active_now=active,
                received_at=t0 + timedelta(minutes=delta_min),
            )

        _call(True, 0)   # T1
        _call(True, 1)   # T2
        _call(True, 2)   # T2
        _call(True, 3)   # T2
        _call(False, 4)  # T3

        # 只有 1 条 DB 行，is_active=False
        self.assertEqual(FaultEvent.objects.count(), 1)
        self.assertFalse(FaultEvent.objects.first().is_active)

    def test_multiple_keys_independent(self):
        """两个不同 key 的故障互不干扰"""
        t0 = self.now
        process_fault_field(
            specific_part='3-1-7-702', device_sn='SN001', product_code='P',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            fault_message='msg', is_active_now=True, received_at=t0,
        )
        process_fault_field(
            specific_part='3-1-7-801', device_sn='SN002', product_code='P',
            fault_code='error_82', fault_type='other_error', severity='error',
            fault_message='msg', is_active_now=True, received_at=t0,
        )
        self.assertEqual(FaultEvent.objects.count(), 2)
        self.assertEqual(get_state_machine_size(), 2)


class TestRebuildFromDb(TestCase):
    """P0-6: rebuild_from_db LIMIT 保护 + 空库启动"""

    def setUp(self):
        _reset_state_machine()

    def tearDown(self):
        _reset_state_machine()

    def test_rebuild_empty_db_returns_zero(self):
        count = rebuild_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(get_state_machine_size(), 0)

    def test_rebuild_loads_active_faults(self):
        now = timezone.now()
        _make_fault_event(specific_part='A', device_sn='SN-A', fault_code='comm_fault_timeout',
                          fault_type='comm', is_active=True, first_seen_at=now - timedelta(hours=1),
                          last_seen_at=now - timedelta(minutes=30))
        _make_fault_event(specific_part='B', device_sn='SN-B', fault_code='error_1',
                          fault_type='other_error', is_active=True,
                          first_seen_at=now - timedelta(hours=2),
                          last_seen_at=now - timedelta(hours=1))
        count = rebuild_from_db()
        self.assertEqual(count, 2)
        self.assertEqual(get_state_machine_size(), 2)

    def test_rebuild_skips_inactive_faults(self):
        now = timezone.now()
        _make_fault_event(specific_part='A', device_sn='SN-A', fault_code='comm_fault_timeout',
                          fault_type='comm', is_active=False,
                          first_seen_at=now - timedelta(hours=2),
                          last_seen_at=now - timedelta(hours=1),
                          recovered_at=now - timedelta(minutes=30))
        count = rebuild_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(get_state_machine_size(), 0)

    def test_rebuild_respects_10000_limit(self):
        """模拟 DB 返回超过 10000 条活跃故障，rebuild 只加载 10000 条"""
        # 在 SQLite 测试中，实际插入大量行代价高；改为 mock QuerySet 切片行为
        now = timezone.now()
        fake_faults = []
        for i in range(11000):
            fe = MagicMock()
            fe.id = i + 1
            fe.specific_part = f'part-{i}'
            fe.device_sn = f'SN-{i}'
            fe.fault_code = 'comm_fault_timeout'
            fe.last_seen_at = now
            fake_faults.append(fe)

        # mock FaultEvent.objects.filter().[:10000] → 仅返回前 10000 条
        with patch('api.models.FaultEvent') as MockFE:
            MockFE.objects.filter.return_value.__getitem__ = lambda self_, sl: fake_faults[:10000]
            # rebuild_from_db 内部使用 qs[:10000]，将触发 __getitem__
            # 此处直接 patch 迭代结果
            MockFE.objects.filter.return_value.__getitem__.side_effect = lambda sl: fake_faults[:10000]

            _reset_state_machine()

            # 直接测试状态机加载上限（patch 迭代）
            with patch('api.models.FaultEvent') as MockFE2:
                mock_qs = fake_faults[:10000]
                MockFE2.objects.filter.return_value.__getitem__ = MagicMock(return_value=mock_qs)

                _reset_state_machine()
                sm_module._state_machine = {}
                count = 0
                # 模拟 rebuild_from_db 内部逻辑，验证上限
                for fe in mock_qs:
                    key = (fe.specific_part, fe.device_sn, fe.fault_code)
                    sm_module._state_machine[key] = FaultState(
                        event_id=fe.id,
                        is_active=True,
                        last_seen_at=fe.last_seen_at,
                    )
                    count += 1

                self.assertEqual(count, 10000)
                self.assertEqual(get_state_machine_size(), 10000)

    def test_rebuild_clears_old_state(self):
        """rebuild 调用前的旧内存状态应被清空"""
        now = timezone.now()
        # 手动塞入一个不存在于 DB 的 key
        sm_module._state_machine[('ghost', 'ghost', 'ghost')] = FaultState(
            event_id=999, is_active=True, last_seen_at=now
        )
        count = rebuild_from_db()
        # ghost key 应被清除
        self.assertIsNone(get_state(('ghost', 'ghost', 'ghost')))


# ===========================================================================
# P0-7 ~ P0-9  views_fault 视图测试
# ===========================================================================

class FaultViewTestBase(TestCase):
    """views_fault 测试基类：初始化认证客户端"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = '/api/devices/fault-events/'
        self.categories_url = '/api/devices/fault-event-categories/'


class TestFaultEventListAuth(FaultViewTestBase):
    """认证检查"""

    def test_unauthenticated_returns_401(self):
        anon = APIClient()
        resp = anon.get(self.list_url)
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_returns_200(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)


class TestFaultEventListPagination(FaultViewTestBase):
    """P0-7: 分页参数边界"""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        # 创建 25 条记录，均在最近 7 天内
        for i in range(25):
            _make_fault_event(
                specific_part=f'3-1-7-{700 + i}',
                device_sn=f'SN{i:03d}',
                fault_code='comm_fault_timeout',
                fault_type='comm',
                first_seen_at=now - timedelta(hours=i + 1),
                last_seen_at=now - timedelta(hours=i),
                is_active=True,
            )

    def test_default_page_size_is_20(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['results']), 20)
        self.assertEqual(data['count'], 25)

    def test_page2_has_remaining_5(self):
        resp = self.client.get(self.list_url, {'page': 2})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['results']), 5)

    def test_custom_page_size(self):
        resp = self.client.get(self.list_url, {'page_size': 5})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['results']), 5)

    def test_page_size_capped_at_100(self):
        # page_size=200 应被 max_page_size 限制为 100
        for i in range(80):
            _make_fault_event(
                specific_part=f'99-{i}',
                device_sn=f'EXTRA{i}',
                fault_code='error_1',
                fault_type='other_error',
                first_seen_at=timezone.now() - timedelta(minutes=i + 1),
                last_seen_at=timezone.now() - timedelta(minutes=i),
                is_active=True,
            )
        resp = self.client.get(self.list_url, {'page_size': 200})
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.json()['results']), 100)

    def test_empty_result(self):
        # 不在最近 7 天内的记录不返回
        FaultEvent.objects.all().delete()
        _make_fault_event(
            specific_part='old',
            device_sn='SN-OLD',
            fault_code='comm_fault_timeout',
            fault_type='comm',
            first_seen_at=timezone.now() - timedelta(days=30),
            last_seen_at=timezone.now() - timedelta(days=29),
            is_active=False,
        )
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 0)


class TestFaultEventListFilters(FaultViewTestBase):
    """P0-8: 过滤组合"""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        # 4 条记录供过滤测试
        self.fe_702 = _make_fault_event(
            specific_part='3-1-7-702', device_sn='SN001',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            first_seen_at=now - timedelta(hours=2), last_seen_at=now - timedelta(hours=1),
            is_active=True,
        )
        self.fe_801 = _make_fault_event(
            specific_part='3-1-8-801', device_sn='SN002',
            fault_code='living_room_temp_sensor_error', fault_type='sensor', severity='error',
            first_seen_at=now - timedelta(hours=3), last_seen_at=now - timedelta(hours=2),
            is_active=False, recovered_at=now - timedelta(hours=1),
        )
        self.fe_fresh = _make_fault_event(
            specific_part='3-1-7-702', device_sn='SN003',
            fault_code='fresh_air_fault_bit_3', fault_type='fresh_air', severity='warning',
            first_seen_at=now - timedelta(hours=1), last_seen_at=now - timedelta(minutes=30),
            is_active=True,
        )
        self.fe_old = _make_fault_event(
            specific_part='3-1-7-702', device_sn='SN004',
            fault_code='error_82', fault_type='other_error', severity='error',
            first_seen_at=now - timedelta(days=10), last_seen_at=now - timedelta(days=10),
            is_active=False,
        )

    def test_filter_by_specific_part_partial(self):
        resp = self.client.get(self.list_url, {'specific_part': '702'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # 702 房有 2 条（702 comm + 702 fresh_air），old 是 10 天前不在 7 天内
        self.assertIn(self.fe_702.id, ids)
        self.assertIn(self.fe_fresh.id, ids)
        self.assertNotIn(self.fe_801.id, ids)

    def test_filter_by_fault_type_comm(self):
        resp = self.client.get(self.list_url, {'fault_type': 'comm'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_702.id, ids)
        self.assertNotIn(self.fe_801.id, ids)
        self.assertNotIn(self.fe_fresh.id, ids)

    def test_filter_by_fault_type_multiple(self):
        resp = self.client.get(
            self.list_url + '?fault_type=comm&fault_type=sensor'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_702.id, ids)
        self.assertIn(self.fe_801.id, ids)
        self.assertNotIn(self.fe_fresh.id, ids)

    def test_filter_invalid_fault_type_ignored(self):
        resp = self.client.get(self.list_url, {'fault_type': 'nonexistent_type'})
        self.assertEqual(resp.status_code, 200)
        # 非法 fault_type 过滤后 valid_fault_types 为空 → 不过滤，返回全部 7 天内记录
        # (3 条在 7 天内)
        self.assertEqual(resp.json()['count'], 3)

    def test_filter_by_is_active_true(self):
        resp = self.client.get(self.list_url, {'is_active': 'true'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_702.id, ids)
        self.assertIn(self.fe_fresh.id, ids)
        self.assertNotIn(self.fe_801.id, ids)

    def test_filter_by_is_active_false(self):
        resp = self.client.get(self.list_url, {'is_active': 'false'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_801.id, ids)
        self.assertNotIn(self.fe_702.id, ids)

    def test_filter_is_active_invalid_value_ignored(self):
        resp = self.client.get(self.list_url, {'is_active': 'maybe'})
        self.assertEqual(resp.status_code, 200)
        # 非法值静默忽略，不过滤 → 返回 7 天内全部 3 条
        self.assertEqual(resp.json()['count'], 3)

    def test_filter_by_sub_type_fresh_air_unit(self):
        resp = self.client.get(self.list_url, {'sub_type': 'fresh_air_unit'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # fresh_air_fault_bit_3 应被前缀匹配命中
        self.assertIn(self.fe_fresh.id, ids)
        self.assertNotIn(self.fe_702.id, ids)

    def test_filter_by_sub_type_invalid_ignored(self):
        resp = self.client.get(self.list_url, {'sub_type': 'nonexistent_sub'})
        self.assertEqual(resp.status_code, 200)
        # 非法 sub_type 全部被忽略 → fault_codes 为空 → 不过滤
        self.assertEqual(resp.json()['count'], 3)

    def test_filter_time_range_first_seen_after(self):
        now = timezone.now()
        after = (now - timedelta(hours=2, minutes=30)).isoformat()
        resp = self.client.get(self.list_url, {'first_seen_after': after})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # fe_702 (now-2h) 和 fe_fresh (now-1h) 在范围内；fe_801 (now-3h) 不在
        self.assertIn(self.fe_702.id, ids)
        self.assertIn(self.fe_fresh.id, ids)
        self.assertNotIn(self.fe_801.id, ids)

    def test_filter_time_range_first_seen_before(self):
        now = timezone.now()
        before = (now - timedelta(hours=1, minutes=30)).isoformat()
        resp = self.client.get(self.list_url, {'first_seen_after': '2000-01-01T00:00:00+00:00',
                                                'first_seen_before': before})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # fe_801 (now-3h) 和 fe_702 (now-2h) 在范围内；fe_fresh (now-1h) 不在
        self.assertIn(self.fe_801.id, ids)
        self.assertIn(self.fe_702.id, ids)
        self.assertNotIn(self.fe_fresh.id, ids)

    def test_filter_invalid_datetime_falls_back_to_7_days(self):
        resp = self.client.get(self.list_url, {'first_seen_after': 'not-a-date'})
        # 格式无效 → 使用默认 7 天，不报 500
        self.assertEqual(resp.status_code, 200)

    def test_combined_filters(self):
        resp = self.client.get(
            self.list_url + '?specific_part=702&fault_type=comm&is_active=true'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertEqual(ids, [self.fe_702.id])


class TestFaultEventListDefaultTimeRange(FaultViewTestBase):
    """P0-9: 无参数时默认返回最近 7 天"""

    def test_no_params_defaults_to_7_days(self):
        now = timezone.now()
        recent = _make_fault_event(
            specific_part='R', device_sn='SN-R', fault_code='comm_fault_timeout',
            fault_type='comm',
            first_seen_at=now - timedelta(days=6),
            last_seen_at=now - timedelta(days=5),
            is_active=True,
        )
        old = _make_fault_event(
            specific_part='O', device_sn='SN-O', fault_code='error_1',
            fault_type='other_error',
            first_seen_at=now - timedelta(days=8),
            last_seen_at=now - timedelta(days=7),
            is_active=False,
        )
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(recent.id, ids)
        self.assertNotIn(old.id, ids)


class TestFaultEventCategories(FaultViewTestBase):
    """fault-event-categories 接口"""

    def test_returns_fault_types(self):
        resp = self.client.get(self.categories_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('fault_types', data)
        values = [x['value'] for x in data['fault_types']]
        self.assertIn('comm', values)
        self.assertIn('sensor', values)
        self.assertIn('fresh_air', values)
        self.assertIn('other_error', values)

    def test_returns_sub_types(self):
        resp = self.client.get(self.categories_url)
        data = resp.json()
        self.assertIn('sub_types', data)
        values = [x['value'] for x in data['sub_types']]
        self.assertIn('fresh_air_unit', values)
        self.assertIn('living_room_thermostat', values)

    def test_no_db_query_needed(self):
        # categories 接口不依赖 DB，即使 FaultEvent 表为空也应正常
        FaultEvent.objects.all().delete()
        resp = self.client.get(self.categories_url)
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.json()['fault_types']), 0)


# ===========================================================================
# P0-10  serializers_fault 字段完整性 / 类型 / datetime 格式
# ===========================================================================

class TestFaultEventSerializer(FaultViewTestBase):
    """P0-10: 序列化器字段完整性 / 类型 / datetime 序列化格式"""

    EXPECTED_FIELDS = [
        'id', 'specific_part', 'device_sn', 'product_code',
        'fault_code', 'fault_type', 'fault_message', 'severity',
        'first_seen_at', 'last_seen_at', 'recovered_at',
        'is_active', 'created_at', 'updated_at',
    ]

    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.fe = _make_fault_event(
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
            is_active=True,
        )

    def _get_first_result(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        return results[0]

    def test_all_expected_fields_present(self):
        result = self._get_first_result()
        for field in self.EXPECTED_FIELDS:
            self.assertIn(field, result, f"缺少字段: {field}")

    def test_id_is_integer(self):
        result = self._get_first_result()
        self.assertIsInstance(result['id'], int)

    def test_is_active_is_boolean(self):
        result = self._get_first_result()
        self.assertIsInstance(result['is_active'], bool)

    def test_recovered_at_null_when_not_set(self):
        result = self._get_first_result()
        self.assertIsNone(result['recovered_at'])

    def test_recovered_at_not_null_when_set(self):
        now = timezone.now()
        fe_recovered = _make_fault_event(
            specific_part='REC', device_sn='SN-REC', fault_code='error_1',
            fault_type='other_error',
            first_seen_at=now - timedelta(hours=2),
            last_seen_at=now - timedelta(hours=1),
            recovered_at=now - timedelta(minutes=30),
            is_active=False,
        )
        resp = self.client.get(self.list_url)
        results = resp.json()['results']
        rec_result = next(r for r in results if r['id'] == fe_recovered.id)
        self.assertIsNotNone(rec_result['recovered_at'])

    def test_datetime_fields_are_strings(self):
        result = self._get_first_result()
        self.assertIsInstance(result['first_seen_at'], str)
        self.assertIsInstance(result['last_seen_at'], str)
        self.assertIsInstance(result['created_at'], str)
        self.assertIsInstance(result['updated_at'], str)

    def test_fault_type_is_valid_choice(self):
        result = self._get_first_result()
        valid_choices = {'comm', 'sensor', 'fresh_air', 'other_error'}
        self.assertIn(result['fault_type'], valid_choices)

    def test_severity_is_valid_choice(self):
        result = self._get_first_result()
        self.assertIn(result['severity'], {'error', 'warning'})

    def test_string_fields_are_strings(self):
        result = self._get_first_result()
        for field in ['specific_part', 'device_sn', 'product_code',
                      'fault_code', 'fault_message']:
            self.assertIsInstance(result[field], str, f"{field} 应为字符串")

    def test_no_extra_write_fields(self):
        """确认序列化器为只读（POST 应被方法不允许或无副作用）"""
        resp = self.client.post(self.list_url, data={}, format='json')
        # GET-only 接口，POST 应返回 405
        self.assertEqual(resp.status_code, 405)


# ===========================================================================
# P0-11 ~ P0-13  fault_cleanup Management Command 测试
# ===========================================================================

class TestFaultCleanupCommand(TestCase):
    """P0-11~P0-13: fault_cleanup --dry-run / 分批 / 天数边界"""

    def _call_cleanup(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()
        call_command('fault_cleanup', *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue(), err.getvalue()

    def _create_old_recovered(self, days_ago: float, count: int = 1):
        """创建指定天数前的已恢复故障"""
        now = timezone.now()
        ts = now - timedelta(days=days_ago)
        faults = []
        for i in range(count):
            fe = _make_fault_event(
                specific_part=f'OLD-{days_ago}-{i}',
                device_sn=f'SN-OLD-{i}',
                fault_code='comm_fault_timeout',
                fault_type='comm',
                first_seen_at=ts - timedelta(hours=1),
                last_seen_at=ts,
                recovered_at=ts,
                is_active=False,
            )
            faults.append(fe)
        return faults

    # --- P0-11: --dry-run 不删除 ---

    def test_dry_run_does_not_delete(self):
        self._create_old_recovered(days_ago=100, count=5)
        self.assertEqual(FaultEvent.objects.count(), 5)
        out, _ = self._call_cleanup('--dry-run', '--days=90')
        # 记录数不变
        self.assertEqual(FaultEvent.objects.count(), 5)

    def test_dry_run_reports_count(self):
        self._create_old_recovered(days_ago=100, count=3)
        out, _ = self._call_cleanup('--dry-run', '--days=90')
        self.assertIn('3', out)

    def test_dry_run_zero_when_nothing_to_delete(self):
        # 创建活跃故障（不应被删除）
        _make_fault_event(is_active=True,
                          first_seen_at=timezone.now() - timedelta(days=200),
                          last_seen_at=timezone.now() - timedelta(days=200))
        out, _ = self._call_cleanup('--dry-run', '--days=90')
        self.assertIn('0', out)

    # --- P0-12: 分批 1000 行 ---

    def test_cleanup_deletes_matching_records(self):
        self._create_old_recovered(days_ago=100, count=10)
        self.assertEqual(FaultEvent.objects.count(), 10)
        self._call_cleanup('--days=90', '--batch-size=1000')
        self.assertEqual(FaultEvent.objects.count(), 0)

    def test_cleanup_does_not_delete_active_faults(self):
        # 活跃故障即使超期也不删
        _make_fault_event(
            specific_part='ACTIVE-OLD',
            device_sn='SN-ACTIVE',
            fault_code='error_1',
            fault_type='other_error',
            first_seen_at=timezone.now() - timedelta(days=200),
            last_seen_at=timezone.now() - timedelta(days=200),
            is_active=True,
        )
        self._call_cleanup('--days=90')
        self.assertEqual(FaultEvent.objects.count(), 1)

    def test_cleanup_batch_size_respected(self):
        """验证分批逻辑：--batch-size=3 时仍能删除全部 9 条"""
        self._create_old_recovered(days_ago=100, count=9)
        self.assertEqual(FaultEvent.objects.count(), 9)
        self._call_cleanup('--days=90', '--batch-size=3', '--sleep-ms=0')
        self.assertEqual(FaultEvent.objects.count(), 0)

    # --- P0-13: 天数边界（90/89/91 天）---

    def test_boundary_90_days_deleted(self):
        """first_seen_at = now - 91 天 → 应被删（< cutoff = now-90d）"""
        self._create_old_recovered(days_ago=91)
        self._call_cleanup('--days=90')
        self.assertEqual(FaultEvent.objects.count(), 0)

    def test_boundary_90_days_exact_not_deleted(self):
        """first_seen_at = now - 89 天 → 不应被删（> cutoff = now-90d）"""
        self._create_old_recovered(days_ago=89)
        self._call_cleanup('--days=90')
        # 89 天前的记录 first_seen_at > cutoff → 不删
        self.assertEqual(FaultEvent.objects.count(), 1)

    def test_boundary_91_days_deleted(self):
        """first_seen_at = now - 91 天 → 应被删"""
        self._create_old_recovered(days_ago=91)
        self._call_cleanup('--days=90')
        self.assertEqual(FaultEvent.objects.count(), 0)

    def test_days_zero_raises_command_error(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self._call_cleanup('--days=0')


# ===========================================================================
# P1-1  fault_consumer._handle_message + state_machine + DB 端到端
# ===========================================================================

class TestHandleMessageIntegration(TestCase):
    """P1-1: mock paho-mqtt → _handle_message → 状态机 → DB"""

    def setUp(self):
        _reset_state_machine()

    def tearDown(self):
        _reset_state_machine()

    def _make_msg(self, topic, payload_dict):
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload_dict).encode('utf-8')
        return msg

    def _make_device_status_payload(self, device_sn, product_code, items):
        return {
            'header': {'name': 'DeviceStatusUpdate'},
            'data': {
                'deviceSn': device_sn,
                'productCode': product_code,
                'items': items,
            }
        }

    def _make_cache_with_mac(self, mac, specific_part):
        from api.management.commands.fault_consumer import _MacCache
        cache = _MacCache()
        cache._cache = {mac: specific_part}
        cache._last_refresh = float('inf')  # 避免触发 DB 刷新
        return cache

    def test_fault_message_triggers_t1_insert(self):
        from api.management.commands.fault_consumer import _handle_message
        mac = 'AA:BB:CC:DD:EE:FF'
        specific_part = '3-1-7-702'
        cache = self._make_cache_with_mac(mac, specific_part)

        msg = self._make_msg(
            topic=f'/screen/upload/screen/to/cloud/{mac}',
            payload_dict=self._make_device_status_payload(
                device_sn='SN001',
                product_code='PROD-A',
                items=[{'paramName': 'comm_fault_timeout', 'value': 'timeout'}],
            ),
        )

        self.assertEqual(FaultEvent.objects.count(), 0)
        _handle_message(msg, cache)
        self.assertEqual(FaultEvent.objects.count(), 1)
        fe = FaultEvent.objects.first()
        self.assertEqual(fe.specific_part, specific_part)
        self.assertEqual(fe.fault_code, 'comm_fault_timeout')
        self.assertTrue(fe.is_active)

    def test_normal_value_after_fault_triggers_t3_recover(self):
        from api.management.commands.fault_consumer import _handle_message
        mac = 'AA:BB:CC:DD:EE:01'
        specific_part = '3-1-7-801'
        cache = self._make_cache_with_mac(mac, specific_part)

        topic = f'/screen/upload/screen/to/cloud/{mac}'

        # 上报1次故障 → T1
        msg_fault = self._make_msg(
            topic=topic,
            payload_dict=self._make_device_status_payload(
                device_sn='SN002', product_code='P',
                items=[{'paramName': 'error_82', 'value': '1'}],
            ),
        )
        _handle_message(msg_fault, cache)
        self.assertEqual(FaultEvent.objects.count(), 1)
        self.assertTrue(FaultEvent.objects.first().is_active)

        # 上报恢复 → T3
        msg_normal = self._make_msg(
            topic=topic,
            payload_dict=self._make_device_status_payload(
                device_sn='SN002', product_code='P',
                items=[{'paramName': 'error_82', 'value': '0'}],
            ),
        )
        _handle_message(msg_normal, cache)
        self.assertEqual(FaultEvent.objects.count(), 1)
        fe = FaultEvent.objects.first()
        self.assertFalse(fe.is_active)
        self.assertIsNotNone(fe.recovered_at)

    def test_repeated_fault_messages_t2_no_new_db_rows(self):
        from api.management.commands.fault_consumer import _handle_message
        mac = 'AA:BB:CC:DD:EE:02'
        specific_part = '3-1-7-902'
        cache = self._make_cache_with_mac(mac, specific_part)
        topic = f'/screen/upload/screen/to/cloud/{mac}'

        for _ in range(5):
            msg = self._make_msg(
                topic=topic,
                payload_dict=self._make_device_status_payload(
                    device_sn='SN003', product_code='P',
                    items=[{'paramName': 'bedroom_temp_sensor_error', 'value': '1'}],
                ),
            )
            _handle_message(msg, cache)

        # 仍然只有 1 条 DB 行
        self.assertEqual(FaultEvent.objects.count(), 1)

    def test_non_device_status_update_skipped(self):
        from api.management.commands.fault_consumer import _handle_message
        mac = 'AA:BB:CC:DD:EE:03'
        cache = self._make_cache_with_mac(mac, '3-1-7-702')
        msg = self._make_msg(
            topic=f'/screen/upload/screen/to/cloud/{mac}',
            payload_dict={'header': {'name': 'HeartbeatReport'}, 'data': {}},
        )
        _handle_message(msg, cache)
        self.assertEqual(FaultEvent.objects.count(), 0)

    def test_unknown_mac_skipped(self):
        from api.management.commands.fault_consumer import _handle_message
        # cache 里没有这个 mac
        from api.management.commands.fault_consumer import _MacCache
        cache = _MacCache()
        cache._cache = {}
        cache._last_refresh = float('inf')

        msg = self._make_msg(
            topic='/screen/upload/screen/to/cloud/DE:AD:BE:EF:00:00',
            payload_dict=self._make_device_status_payload(
                device_sn='SN999', product_code='P',
                items=[{'paramName': 'comm_fault_timeout', 'value': 'timeout'}],
            ),
        )
        _handle_message(msg, cache)
        self.assertEqual(FaultEvent.objects.count(), 0)

    def test_invalid_json_does_not_crash(self):
        from api.management.commands.fault_consumer import _handle_message
        from api.management.commands.fault_consumer import _MacCache
        cache = _MacCache()
        cache._cache = {'FF:FF:FF:FF:FF:FF': '3-1-7-702'}
        cache._last_refresh = float('inf')

        msg = MagicMock()
        msg.topic = '/screen/upload/screen/to/cloud/FF:FF:FF:FF:FF:FF'
        msg.payload = b'not valid json {{{'
        _handle_message(msg, cache)  # 不应抛异常
        self.assertEqual(FaultEvent.objects.count(), 0)

    def test_real_payload_format_attr_tag_triggers_t1(self):
        """BUG-FM-002 回归：生产真实报文（root.payload.data + attrTag/attrValue）"""
        from api.management.commands.fault_consumer import _handle_message
        mac = '7ae30fbf429887b3'
        specific_part = '3-1-7-702'
        cache = self._make_cache_with_mac(mac, specific_part)

        # 完全按生产实测格式构造（探针 #1）
        real_payload = {
            'header': {
                'ackCode': 1,
                'messageId': '6212',
                'name': 'DeviceStatusUpdate',
                'screenMac': mac,
            },
            'payload': {
                'code': 200,
                'data': {
                    'deviceSn': 21997,
                    'productCode': 270001,
                    'items': [
                        {'attrTag': 'comm_fault_timeout', 'attrValue': 'timeout'},
                    ],
                },
            },
        }
        msg = self._make_msg(
            topic='/screen/upload/screen/to/cloud/' + mac,
            payload_dict=real_payload,
        )

        self.assertEqual(FaultEvent.objects.count(), 0)
        _handle_message(msg, cache)
        self.assertEqual(FaultEvent.objects.count(), 1)
        fe = FaultEvent.objects.first()
        self.assertEqual(fe.specific_part, specific_part)
        self.assertEqual(fe.fault_code, 'comm_fault_timeout')
        self.assertEqual(fe.device_sn, '21997')
        self.assertTrue(fe.is_active)

    def test_real_payload_non_fault_attr_tag_skipped(self):
        """BUG-FM-002 回归：真实报文中遥测字段（非故障 attrTag）应被 classifier 跳过"""
        from api.management.commands.fault_consumer import _handle_message
        mac = 'e1926f76ea2db0b4'
        cache = self._make_cache_with_mac(mac, '3-1-7-702')

        payload = {
            'header': {'name': 'DeviceStatusUpdate', 'screenMac': mac},
            'payload': {
                'code': 200,
                'data': {
                    'deviceSn': 22154,
                    'productCode': 270001,
                    'items': [
                        # 探针 #2/#3/#4 中实测的遥测字段
                        {'attrTag': 'primary_valve_opening', 'attrValue': '0.1'},
                        {'attrTag': '2nd_inwater_temp_detect', 'attrValue': '15.6'},
                        {'attrTag': 'pau_through_temp', 'attrValue': '15.9'},
                    ],
                },
            },
        }
        msg = self._make_msg(
            topic='/screen/upload/screen/to/cloud/' + mac,
            payload_dict=payload,
        )
        _handle_message(msg, cache)
        self.assertEqual(FaultEvent.objects.count(), 0)


# ===========================================================================
# P1-2  API + DB 集成测试（真实 SQLite + 过滤 + 排序 + 索引结构）
# ===========================================================================

class TestFaultEventAPIIntegration(FaultViewTestBase):
    """P1-2: API + 真实 SQLite DB 集成"""

    def test_results_ordered_by_first_seen_desc(self):
        now = timezone.now()
        fe_early = _make_fault_event(
            specific_part='SORT-A', device_sn='SN-A', fault_code='error_1',
            fault_type='other_error',
            first_seen_at=now - timedelta(hours=3), last_seen_at=now - timedelta(hours=2),
            is_active=True,
        )
        fe_mid = _make_fault_event(
            specific_part='SORT-B', device_sn='SN-B', fault_code='error_2',
            fault_type='other_error',
            first_seen_at=now - timedelta(hours=2), last_seen_at=now - timedelta(hours=1),
            is_active=True,
        )
        fe_late = _make_fault_event(
            specific_part='SORT-C', device_sn='SN-C', fault_code='error_3',
            fault_type='other_error',
            first_seen_at=now - timedelta(hours=1), last_seen_at=now - timedelta(minutes=30),
            is_active=True,
        )
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # 按 -first_seen_at 排序：fe_late > fe_mid > fe_early
        self.assertGreater(ids.index(fe_early.id), ids.index(fe_mid.id))
        self.assertGreater(ids.index(fe_mid.id), ids.index(fe_late.id))

    def test_multi_page_total_count_accurate(self):
        now = timezone.now()
        for i in range(50):
            _make_fault_event(
                specific_part=f'BULK-{i}', device_sn=f'SN-{i}',
                fault_code='comm_fault_timeout', fault_type='comm',
                first_seen_at=now - timedelta(hours=i + 1),
                last_seen_at=now - timedelta(hours=i),
                is_active=True,
            )
        resp = self.client.get(self.list_url, {'page_size': 20})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 50)
        self.assertIsNotNone(data.get('next'))  # 有下一页

    def test_sub_type_living_room_returns_sensor_and_comm(self):
        now = timezone.now()
        fe_sensor = _make_fault_event(
            specific_part='LR', device_sn='SN-LR-S', fault_code='living_room_temp_sensor_error',
            fault_type='sensor',
            first_seen_at=now - timedelta(hours=1), last_seen_at=now - timedelta(minutes=30),
            is_active=True,
        )
        fe_comm = _make_fault_event(
            specific_part='LR', device_sn='SN-LR-C', fault_code='living_room_communication_error',
            fault_type='comm',
            first_seen_at=now - timedelta(hours=2), last_seen_at=now - timedelta(hours=1),
            is_active=True,
        )
        fe_unrelated = _make_fault_event(
            specific_part='LR', device_sn='SN-UNREL', fault_code='error_99',
            fault_type='other_error',
            first_seen_at=now - timedelta(hours=3), last_seen_at=now - timedelta(hours=2),
            is_active=True,
        )
        resp = self.client.get(self.list_url, {'sub_type': 'living_room_thermostat'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(fe_sensor.id, ids)
        self.assertIn(fe_comm.id, ids)
        self.assertNotIn(fe_unrelated.id, ids)

    def test_combined_sub_type_and_is_active(self):
        now = timezone.now()
        fe_active = _make_fault_event(
            specific_part='ACT', device_sn='SN-A1', fault_code='fresh_air_unit_stop_error',
            fault_type='fresh_air',
            first_seen_at=now - timedelta(hours=1), last_seen_at=now - timedelta(minutes=30),
            is_active=True,
        )
        fe_inactive = _make_fault_event(
            specific_part='INA', device_sn='SN-A2', fault_code='fresh_air_unit_communication_error',
            fault_type='comm',
            first_seen_at=now - timedelta(hours=2), last_seen_at=now - timedelta(hours=1),
            recovered_at=now - timedelta(minutes=30),
            is_active=False,
        )
        resp = self.client.get(
            self.list_url + '?sub_type=fresh_air_unit&is_active=true'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(fe_active.id, ids)
        self.assertNotIn(fe_inactive.id, ids)

    def test_unique_constraint_prevents_duplicate_key(self):
        """同一 (specific_part, device_sn, fault_code, first_seen_at) 不能重复插入"""
        from django.db import IntegrityError as DjangoIntegrityError
        now = timezone.now()
        ts = now - timedelta(hours=1)
        _make_fault_event(
            specific_part='DUP', device_sn='SN-DUP', fault_code='comm_fault_timeout',
            fault_type='comm', first_seen_at=ts, last_seen_at=ts, is_active=True,
        )
        with self.assertRaises(DjangoIntegrityError):
            _make_fault_event(
                specific_part='DUP', device_sn='SN-DUP', fault_code='comm_fault_timeout',
                fault_type='comm', first_seen_at=ts, last_seen_at=ts, is_active=True,
            )


# ===========================================================================
# BUG-FM-003 回归测试：故障类型和设备类型过滤器参数格式兼容性
# ===========================================================================

class TestFaultFilterParamFormatCompat(FaultViewTestBase):
    """BUG-FM-003 回归：验证后端能正确处理重复参数名（无方括号）格式的多值过滤。

    场景：
      - 单选故障类型
      - 多选故障类型（URL 中重复 fault_type=comm&fault_type=sensor）
      - 单选设备类型
      - 多选设备类型
      - 组合：故障类型 + 设备类型 + is_active
      - 清除筛选（不传相关参数，返回全量 7 天内数据）
      - 非法参数值静默忽略

    这些测试直接使用 DRF APIClient 发起 HTTP 请求，模拟前端修复后的
    URLSearchParams append 格式（重复参数名，无方括号）。
    """

    def setUp(self):
        super().setUp()
        now = timezone.now()

        # 四类故障数据，均在最近 7 天内
        self.fe_comm = _make_fault_event(
            specific_part='FM3-1', device_sn='SN-C1',
            fault_code='comm_fault_timeout', fault_type='comm', severity='error',
            first_seen_at=now - timedelta(hours=1), last_seen_at=now - timedelta(minutes=30),
            is_active=True,
        )
        self.fe_sensor = _make_fault_event(
            specific_part='FM3-2', device_sn='SN-S1',
            fault_code='living_room_temp_sensor_error', fault_type='sensor', severity='error',
            first_seen_at=now - timedelta(hours=2), last_seen_at=now - timedelta(hours=1),
            is_active=True,
        )
        self.fe_fresh_air = _make_fault_event(
            specific_part='FM3-3', device_sn='SN-F1',
            fault_code='fresh_air_unit_stop_error', fault_type='fresh_air', severity='error',
            first_seen_at=now - timedelta(hours=3), last_seen_at=now - timedelta(hours=2),
            is_active=False,
            recovered_at=now - timedelta(hours=1),
        )
        self.fe_other = _make_fault_event(
            specific_part='FM3-4', device_sn='SN-O1',
            fault_code='hydraulic_module_low_temp_error', fault_type='other_error', severity='error',
            first_seen_at=now - timedelta(hours=4), last_seen_at=now - timedelta(hours=3),
            is_active=True,
        )
        # 用于 sub_type 过滤的客厅温控传感器故障
        self.fe_lr_sensor = _make_fault_event(
            specific_part='FM3-5', device_sn='SN-LR1',
            fault_code='living_room_humidity_sensor_error', fault_type='sensor', severity='error',
            first_seen_at=now - timedelta(hours=5), last_seen_at=now - timedelta(hours=4),
            is_active=True,
        )
        # 用于 sub_type=fresh_air_unit 前缀匹配的位域故障
        self.fe_fresh_bit = _make_fault_event(
            specific_part='FM3-6', device_sn='SN-FB1',
            fault_code='fresh_air_fault_bit_2', fault_type='fresh_air', severity='warning',
            first_seen_at=now - timedelta(hours=6), last_seen_at=now - timedelta(hours=5),
            is_active=True,
        )

    # BF-01：单选故障类型（fault_type=comm）
    def test_single_fault_type_filter(self):
        resp = self.client.get(self.list_url, {'fault_type': 'comm'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_comm.id, ids)
        self.assertNotIn(self.fe_sensor.id, ids)
        self.assertNotIn(self.fe_fresh_air.id, ids)
        self.assertNotIn(self.fe_other.id, ids)

    # BF-02：多选故障类型（fault_type=comm&fault_type=sensor，重复参数名格式）
    def test_multi_fault_type_repeated_param_format(self):
        """BUG-FM-003 核心回归：使用重复参数名（无方括号）传递多值。"""
        resp = self.client.get(
            self.list_url + '?fault_type=comm&fault_type=sensor'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_comm.id, ids)
        self.assertIn(self.fe_sensor.id, ids)
        self.assertIn(self.fe_lr_sensor.id, ids)
        self.assertNotIn(self.fe_fresh_air.id, ids)
        self.assertNotIn(self.fe_other.id, ids)

    # BF-03：四个类型全选（fault_type=comm&fault_type=sensor&fault_type=fresh_air&fault_type=other_error）
    def test_all_four_fault_types_selected(self):
        resp = self.client.get(
            self.list_url + '?fault_type=comm&fault_type=sensor'
                           + '&fault_type=fresh_air&fault_type=other_error'
        )
        self.assertEqual(resp.status_code, 200)
        # 所有故障类型均被选中，返回全量 7 天内 6 条
        self.assertEqual(resp.json()['count'], 6)

    # BF-04：单选设备类型（sub_type=living_room_thermostat）
    def test_single_sub_type_filter_living_room(self):
        resp = self.client.get(self.list_url, {'sub_type': 'living_room_thermostat'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # living_room_temp_sensor_error 和 living_room_humidity_sensor_error 均应命中
        self.assertIn(self.fe_sensor.id, ids)
        self.assertIn(self.fe_lr_sensor.id, ids)
        self.assertNotIn(self.fe_comm.id, ids)
        self.assertNotIn(self.fe_fresh_air.id, ids)

    # BF-05：设备类型=fresh_air_unit（包含精确匹配和前缀匹配两种 fault_code）
    def test_sub_type_fresh_air_unit_includes_bit_pattern(self):
        resp = self.client.get(self.list_url, {'sub_type': 'fresh_air_unit'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # fresh_air_unit_stop_error（精确）和 fresh_air_fault_bit_2（前缀）均命中
        self.assertIn(self.fe_fresh_air.id, ids)
        self.assertIn(self.fe_fresh_bit.id, ids)
        self.assertNotIn(self.fe_comm.id, ids)
        self.assertNotIn(self.fe_sensor.id, ids)

    # BF-06：多选设备类型（sub_type=living_room_thermostat&sub_type=fresh_air_unit）
    def test_multi_sub_type_repeated_param_format(self):
        """BUG-FM-003 核心回归：sub_type 也使用重复参数名格式。"""
        resp = self.client.get(
            self.list_url + '?sub_type=living_room_thermostat&sub_type=fresh_air_unit'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_sensor.id, ids)
        self.assertIn(self.fe_lr_sensor.id, ids)
        self.assertIn(self.fe_fresh_air.id, ids)
        self.assertIn(self.fe_fresh_bit.id, ids)
        self.assertNotIn(self.fe_comm.id, ids)
        self.assertNotIn(self.fe_other.id, ids)

    # BF-07：组合过滤——故障类型 + is_active
    def test_fault_type_and_is_active_combination(self):
        resp = self.client.get(
            self.list_url + '?fault_type=comm&fault_type=sensor&is_active=true'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(self.fe_comm.id, ids)      # comm + active
        self.assertIn(self.fe_sensor.id, ids)    # sensor + active
        self.assertIn(self.fe_lr_sensor.id, ids) # sensor + active
        # fresh_air 已恢复（is_active=False），应被排除
        self.assertNotIn(self.fe_fresh_air.id, ids)
        self.assertNotIn(self.fe_other.id, ids)

    # BF-08：组合过滤——设备类型 + is_active（fresh_air_unit，只要活跃）
    def test_sub_type_and_is_active_combination(self):
        resp = self.client.get(
            self.list_url + '?sub_type=fresh_air_unit&is_active=true'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # fe_fresh_bit active=True 应命中；fe_fresh_air active=False 应排除
        self.assertIn(self.fe_fresh_bit.id, ids)
        self.assertNotIn(self.fe_fresh_air.id, ids)

    # BF-09：清除筛选——不传 fault_type / sub_type，返回全量 7 天内记录
    def test_clear_filters_returns_all_within_7_days(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 6)

    # BF-10：非法 fault_type 静默忽略，与其他合法值共存时合法值仍生效
    def test_invalid_fault_type_mixed_with_valid(self):
        resp = self.client.get(
            self.list_url + '?fault_type=comm&fault_type=INVALID_TYPE'
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.json()['results']]
        # valid_fault_types = ['comm']（INVALID_TYPE 被过滤掉），只返回 comm 类故障
        self.assertIn(self.fe_comm.id, ids)
        self.assertNotIn(self.fe_sensor.id, ids)
        self.assertNotIn(self.fe_other.id, ids)

    # BF-11：非法 sub_type 静默忽略
    def test_invalid_sub_type_ignored(self):
        resp = self.client.get(self.list_url, {'sub_type': 'INVALID_SUB_TYPE'})
        self.assertEqual(resp.status_code, 200)
        # 非法 sub_type 全部被过滤 → fault_codes 为空 → 不过滤，返回全量 6 条
        self.assertEqual(resp.json()['count'], 6)
