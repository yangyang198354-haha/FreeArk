"""
tests_condensation_watchdog.py — condensation-consumer P0 防复发（看门狗 + 计数 + 连接重置）

与 fault-consumer 同源事故（2026-06-16 两个消费者同一时刻静默停写）。本文件镜像
tests_fault_watchdog.py，验证 condensation_consumer 的同款防护：
  - state_machine 运行计数器（键名与 fault 一致，复用 watchdog.evaluate_stall）
  - T1 IntegrityError 兜底查不到活跃行时强制关连接以便重连
  - 看门狗判定逻辑复用 fault_consumer.watchdog.evaluate_stall（已在 fault 测试覆盖）

运行（在 FreeArkWeb/backend/freearkweb/ 下）：
    python manage.py test api.tests_condensation_watchdog
"""

from unittest.mock import patch

from django.test import TestCase, tag

import api.condensation_consumer.state_machine as cw_sm
from .condensation_consumer.state_machine import process_condensation_alarm, get_counters
from .condensation_consumer.watchdog import evaluate_stall  # 复用 fault 的纯判定逻辑
from .models import CondensationWarningEvent
from django.utils import timezone


def _reset():
    cw_sm._cw_state_machine.clear()
    cw_sm.reset_counters()


def _emit(active, received_at):
    process_condensation_alarm(
        specific_part='1-1-16-1601', device_sn='SN-CW-1', product_code='PROD-CW',
        is_active_now=active, received_at=received_at,
        condensation_alarm_value='1', dew_point_temp='120', ntc_temp='100',
        humidity='850', system_switch='on',
    )


@tag('unit')
class TestCondensationCounters(TestCase):
    """计数器随 T1/T3 转移正确累加；事故特征触发连接重置。"""

    def setUp(self):
        _reset()
        self.now = timezone.now()

    def tearDown(self):
        _reset()

    def test_t1_success_increments(self):
        _emit(True, self.now)
        self.assertEqual(get_counters()['t1_attempt'], 1)
        self.assertEqual(get_counters()['t1_success'], 1)
        self.assertEqual(CondensationWarningEvent.objects.filter(is_active=True).count(), 1)

    def test_t3_recover_increments(self):
        _emit(True, self.now)
        _emit(False, self.now + timezone.timedelta(seconds=5))
        self.assertEqual(get_counters()['t3_recover'], 1)

    def test_integrity_fallback_increments_and_resets_connection(self):
        """T1 撞 IntegrityError 且查不到活跃行（事故特征）→ 计数 + 关连接。"""
        from django.db import IntegrityError
        with patch.object(CondensationWarningEvent.objects, 'create',
                          side_effect=IntegrityError('dup')), \
                patch('api.condensation_consumer.state_machine._force_close_connection') as mock_close:
            _emit(True, self.now)
        self.assertEqual(get_counters()['t1_integrity'], 1)
        self.assertEqual(get_counters()['t1_success'], 0)
        mock_close.assert_called_once()


@tag('unit')
class TestCondensationWatchdogReuse(TestCase):
    """condensation 看门狗复用 fault 的 evaluate_stall：键名兼容、判定一致。"""

    def test_stall_then_trigger(self):
        prev = {'t1_attempt': 0, 't1_success': 0}
        curr = {'t1_attempt': 50, 't1_success': 0}
        heal, streak = evaluate_stall(prev, curr, 2, min_attempts=20, stall_limit=3)
        self.assertTrue(heal)

    def test_success_resets(self):
        prev = {'t1_attempt': 0, 't1_success': 0}
        curr = {'t1_attempt': 50, 't1_success': 1}
        heal, streak = evaluate_stall(prev, curr, 2, min_attempts=20, stall_limit=3)
        self.assertFalse(heal)
        self.assertEqual(streak, 0)
