"""
tests_fault_watchdog.py — fault-consumer P0 防复发（看门狗 + 计数 + 连接重置）

对应 2026-06-16 "进程未崩溃却静默停写故障 4 天" 事故的防复发改动：
  - state_machine 运行计数器（t1_attempt / t1_success / t1_integrity / ...）
  - T1 IntegrityError 兜底查不到活跃行时（事故特征）强制关连接以便重连
  - watchdog.evaluate_stall 纯判定逻辑：持续"有尝试零成功"即触发自愈

运行（在 FreeArkWeb/backend/freearkweb/ 下）：
    python manage.py test api.tests_fault_watchdog
全部 SQLite 测试库，不连生产、不起真实 MQTT/线程。
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, tag
from django.utils import timezone

import api.fault_consumer.state_machine as sm_module
from .fault_consumer.state_machine import process_fault_field, get_counters
from .fault_consumer.watchdog import evaluate_stall
from .models import FaultEvent


def _reset():
    sm_module._state_machine.clear()
    sm_module.reset_counters()


def _emit(active, received_at, *, code='comm_fault_timeout'):
    process_fault_field(
        specific_part='3-1-7-702', device_sn='SN001', product_code='PROD-A',
        fault_code=code, fault_type='comm', severity='error',
        fault_message='Comm fault timeout', is_active_now=active,
        received_at=received_at,
    )


# ===========================================================================
# 计数器
# ===========================================================================

@tag('unit')
class TestStateMachineCounters(TestCase):
    """计数器随 T1/T3 转移正确累加。"""

    def setUp(self):
        _reset()
        self.now = timezone.now()

    def tearDown(self):
        _reset()

    def test_t1_success_increments(self):
        _emit(True, self.now)
        self.assertEqual(get_counters()['t1_attempt'], 1)
        self.assertEqual(get_counters()['t1_success'], 1)
        self.assertEqual(get_counters()['t1_integrity'], 0)

    def test_t3_recover_increments(self):
        _emit(True, self.now)                                  # T1
        _emit(False, self.now + timezone.timedelta(seconds=5))  # T3
        self.assertEqual(get_counters()['t3_recover'], 1)

    def test_integrity_fallback_increments_and_resets_connection(self):
        """T1 撞 IntegrityError 且查不到活跃行（事故特征）→ 计数 + 关连接。"""
        # DB 中无任何活跃行；令 create 抛 IntegrityError 走兜底 else 分支
        from django.db import IntegrityError
        with patch.object(FaultEvent.objects, 'create', side_effect=IntegrityError('dup')), \
                patch('api.fault_consumer.state_machine._force_close_connection') as mock_close:
            _emit(True, self.now)
        self.assertEqual(get_counters()['t1_attempt'], 1)
        self.assertEqual(get_counters()['t1_success'], 0)
        self.assertEqual(get_counters()['t1_integrity'], 1)
        # 兜底查不到活跃行 → 强制关连接以便下次重连
        mock_close.assert_called_once()


# ===========================================================================
# 看门狗判定逻辑（纯函数）
# ===========================================================================

@tag('unit')
class TestEvaluateStall(SimpleTestCase):
    """evaluate_stall：'有尝试、零成功' 连续达阈值即触发自愈。"""

    KW = dict(min_attempts=20, stall_limit=3)

    def test_stall_window_accumulates(self):
        prev = {'t1_attempt': 0, 't1_success': 0}
        curr = {'t1_attempt': 50, 't1_success': 0}  # 有尝试、零成功
        heal, streak = evaluate_stall(prev, curr, 0, **self.KW)
        self.assertFalse(heal)
        self.assertEqual(streak, 1)

    def test_success_resets_streak(self):
        prev = {'t1_attempt': 0, 't1_success': 0}
        curr = {'t1_attempt': 50, 't1_success': 3}  # 有成功 → 复位
        heal, streak = evaluate_stall(prev, curr, 2, **self.KW)
        self.assertFalse(heal)
        self.assertEqual(streak, 0)

    def test_quiet_period_does_not_count(self):
        """故障稀少（attempts 增量 < min_attempts）不算失速，避免误判。"""
        prev = {'t1_attempt': 0, 't1_success': 0}
        curr = {'t1_attempt': 5, 't1_success': 0}
        heal, streak = evaluate_stall(prev, curr, 2, **self.KW)
        self.assertFalse(heal)
        self.assertEqual(streak, 0)

    def test_triggers_at_limit(self):
        prev = {'t1_attempt': 0, 't1_success': 0}
        curr = {'t1_attempt': 50, 't1_success': 0}
        heal, streak = evaluate_stall(prev, curr, 2, **self.KW)  # 2 -> 3 = limit
        self.assertTrue(heal)
        self.assertEqual(streak, 3)
