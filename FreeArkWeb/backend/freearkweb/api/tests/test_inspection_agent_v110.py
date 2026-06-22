"""
test_inspection_agent_v110.py — v1.1.0-AIA（方案 B）增量② 单元测试

覆盖 inspection_agent 包四个叶子模块（纯逻辑，离线可跑，不触 LLM/orchestrator）：

  auth.py（OD-01 写授权层，ARCH §6）
    UT-AUTH-001 默认（未设 AUTO_WRITE_POLICY）→ 策略 B 拦截
    UT-AUTH-002 显式 AUTO_WRITE_POLICY=B → 拦截，reason=POLICY_B_NO_AUTO_WRITE
    UT-AUTH-003 非法策略值（如 "x"）→ 退回策略 B 拦截
    UT-AUTH-004 策略 A：工具不在白名单 → OUT_OF_WHITELIST
    UT-AUTH-005 策略 A：set_device_params 参数在区间内 → 放行
    UT-AUTH-006 策略 A：参数越界 → OUT_OF_WHITELIST
    UT-AUTH-007 策略 A：取值非数值/参数无规则 → default-deny
    UT-AUTH-008 INSPECTION_WRITE_WHITELIST 非法 JSON → 空白名单（全拒）

  event_poller.py（OD-02 事件接入，ARCH §4/§10.4）
    UT-POLL-001 poll 取 PENDING 事件并原子置 IN_PROGRESS，按 first_seen_at 升序
    UT-POLL-002 已认领事件二次 poll 不再返回（IN_PROGRESS 已排除）
    UT-POLL-003 is_active=False / DONE 的事件不被取用
    UT-POLL-004 batch_size 截断
    UT-POLL-005 reset_in_progress 把 IN_PROGRESS 重置为 PENDING，DONE 不动

  event_poller.py：持续存在防抖窗口（v1.3.2-IGW，REQ-FUNC-GW-001/002/003/005）
    UT-POLL-GW-001 get_grace_window 默认 600s（10 分钟）
    UT-POLL-GW-002 get_grace_window 合法值生效
    UT-POLL-GW-003 get_grace_window 非法值（空/非数字/0/负）回退默认
    UT-POLL-GW-004 未达窗口的事件不认领、保持 PENDING（场景 A）
    UT-POLL-GW-005 已达窗口的事件正常认领（场景 C）
    UT-POLL-GW-006 窗口对故障/结露两表均生效
    UT-POLL-GW-007 skip_recovered_pending 把已恢复 PENDING 标 SKIPPED，活跃 PENDING 不动（场景 B 收尾）
    UT-POLL-GW-008 skip_recovered_pending 不误伤 DONE/IN_PROGRESS

  work_order.py（ARCH §7）
    UT-WO-101 generate_ticket_id 格式 + 当天递增
    UT-WO-102 create_from_event(FaultEvent) 推导字段并建单
    UT-WO-103 create_from_event(CW) 用 warning_type 作 severity
    UT-WO-104 重复来源事件活跃工单 → 返回已有、created=False（不重复建单）
    UT-WO-105 已有工单 RESOLVED 后可再建活跃工单

  audit.py（ARCH §9）
    UT-AUDIT-001 log_workorder_created 输出含正确 event_type 与字段
    UT-AUDIT-002 log_write_blocked 按 reason 映射事件类型
    UT-AUDIT-003 脱敏：action_detail 中含敏感键名的值被 REDACTED

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_inspection_agent_v110 \\
        --settings=freearkweb.test_settings --verbosity=2
"""

import json
import os
from unittest import mock

from django.test import TestCase, tag
from django.utils import timezone

from api.models import CondensationWarningEvent, FaultEvent, WorkOrder
from inspection_agent import audit, work_order
from inspection_agent.auth import (
    REASON_APPROVED_WHITELIST,
    REASON_OUT_OF_WHITELIST,
    REASON_POLICY_B,
    WriteAuthPolicy,
)
from inspection_agent.event_poller import EventPoller, get_grace_window


# ── 测试夹具 ────────────────────────────────────────────────────────────

def _make_fault_event(seconds_ago=0, **overrides):
    base = timezone.now() - timezone.timedelta(seconds=seconds_ago)
    defaults = dict(
        specific_part='3-1-7-702',
        device_sn='SN-FAULT-001',
        product_code='PC-001',
        fault_code='E101',
        fault_type='comm',
        fault_message='通信中断',
        severity='error',
        first_seen_at=base,
        last_seen_at=base,
    )
    defaults.update(overrides)
    return FaultEvent.objects.create(**defaults)


def _make_cw_event(seconds_ago=0, **overrides):
    base = timezone.now() - timezone.timedelta(seconds=seconds_ago)
    defaults = dict(
        specific_part='3-1-8-801',
        device_sn='SN-CW-001',
        product_code='PC-001',
        warning_type='结露预警',
        warning_message='结露报警',
        first_seen_at=base,
        last_seen_at=base,
    )
    defaults.update(overrides)
    return CondensationWarningEvent.objects.create(**defaults)


def _clear_policy_env():
    """返回一个把策略相关 env 清空的 patch.dict 上下文。"""
    return mock.patch.dict(os.environ,
                           {k: v for k, v in os.environ.items()
                            if k not in ('AUTO_WRITE_POLICY', 'INSPECTION_WRITE_WHITELIST')},
                           clear=True)


# ── auth.py ────────────────────────────────────────────────────────────

@tag('unit')
class WriteAuthPolicyTest(TestCase):
    """UT-AUTH-*: 写授权层（策略 B 默认拦截 / 策略 A 白名单备选）。"""

    def test_default_is_policy_b_block(self):
        with _clear_policy_env():
            result = WriteAuthPolicy().check('set_device_params', {'items': []})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, REASON_POLICY_B)

    def test_explicit_policy_b_block(self):
        with mock.patch.dict(os.environ, {'AUTO_WRITE_POLICY': 'B'}):
            result = WriteAuthPolicy().check('set_device_params', {'items': [
                {'param_name': '设定温度', 'new_value': '24'}]})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, REASON_POLICY_B)

    def test_invalid_policy_falls_back_to_b(self):
        with mock.patch.dict(os.environ, {'AUTO_WRITE_POLICY': 'x'}):
            result = WriteAuthPolicy().check('trigger_refresh', {})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, REASON_POLICY_B)

    def test_policy_a_tool_not_in_whitelist(self):
        with mock.patch.dict(os.environ, {
            'AUTO_WRITE_POLICY': 'A',
            'INSPECTION_WRITE_WHITELIST': json.dumps({'trigger_refresh': {}}),
        }):
            result = WriteAuthPolicy().check('set_device_params', {'items': [
                {'param_name': '设定温度', 'new_value': '24'}]})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, REASON_OUT_OF_WHITELIST)

    def test_policy_a_value_within_bounds(self):
        wl = {'set_device_params': {'设定温度': {'abs_min': 20, 'abs_max': 28}}}
        with mock.patch.dict(os.environ, {
            'AUTO_WRITE_POLICY': 'A', 'INSPECTION_WRITE_WHITELIST': json.dumps(wl),
        }):
            result = WriteAuthPolicy().check('set_device_params', {'items': [
                {'param_name': '设定温度', 'new_value': '24'}]})
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, REASON_APPROVED_WHITELIST)

    def test_policy_a_value_out_of_bounds(self):
        wl = {'set_device_params': {'设定温度': {'abs_min': 20, 'abs_max': 28}}}
        with mock.patch.dict(os.environ, {
            'AUTO_WRITE_POLICY': 'A', 'INSPECTION_WRITE_WHITELIST': json.dumps(wl),
        }):
            result = WriteAuthPolicy().check('set_device_params', {'items': [
                {'param_name': '设定温度', 'new_value': '35'}]})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, REASON_OUT_OF_WHITELIST)

    def test_policy_a_non_numeric_and_unknown_param_deny(self):
        wl = {'set_device_params': {'设定温度': {'abs_min': 20, 'abs_max': 28}}}
        with mock.patch.dict(os.environ, {
            'AUTO_WRITE_POLICY': 'A', 'INSPECTION_WRITE_WHITELIST': json.dumps(wl),
        }):
            # 取值非数值 → default-deny
            r1 = WriteAuthPolicy().check('set_device_params', {'items': [
                {'param_name': '设定温度', 'new_value': '高'}]})
            # 参数无对应规则 → default-deny
            r2 = WriteAuthPolicy().check('set_device_params', {'items': [
                {'param_name': '风速', 'new_value': '3'}]})
        self.assertFalse(r1.allowed)
        self.assertFalse(r2.allowed)

    def test_invalid_whitelist_json_blocks_all(self):
        with mock.patch.dict(os.environ, {
            'AUTO_WRITE_POLICY': 'A', 'INSPECTION_WRITE_WHITELIST': '{not json',
        }):
            result = WriteAuthPolicy().check('set_device_params', {'items': [
                {'param_name': '设定温度', 'new_value': '24'}]})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, REASON_OUT_OF_WHITELIST)


# ── event_poller.py ─────────────────────────────────────────────────────

@tag('unit')
class EventPollerTest(TestCase):
    """UT-POLL-*: DB 轮询取用 + 原子认领 + 启动重建。"""

    def test_poll_claims_and_orders(self):
        # 先发生的 fault（older）应排在后发生的 cw 之前
        fe = _make_fault_event(seconds_ago=60)
        cw = _make_cw_event(seconds_ago=30)
        claimed = EventPoller(batch_size=5, grace_window=0).poll()
        self.assertEqual([e.pk for e in claimed], [fe.pk, cw.pk])
        self.assertTrue(all(e.inspection_status == 'IN_PROGRESS' for e in claimed))
        fe.refresh_from_db()
        cw.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'IN_PROGRESS')
        self.assertIsNotNone(fe.inspection_started_at)
        self.assertEqual(cw.inspection_status, 'IN_PROGRESS')

    def test_claimed_events_not_repolled(self):
        _make_fault_event(seconds_ago=10)
        poller = EventPoller(batch_size=5, grace_window=0)
        first = poller.poll()
        self.assertEqual(len(first), 1)
        second = poller.poll()
        self.assertEqual(second, [])

    def test_inactive_and_done_excluded(self):
        # 各事件 fault_code 不同，避免命中 uq_fault_event_key_time 唯一约束
        _make_fault_event(seconds_ago=12, fault_code='E101', is_active=False)        # 已恢复
        _make_fault_event(seconds_ago=10, fault_code='E102', inspection_status='DONE')  # 已处置
        active = _make_fault_event(seconds_ago=5, fault_code='E103')
        claimed = EventPoller(batch_size=5, grace_window=0).poll()
        self.assertEqual([e.pk for e in claimed], [active.pk])

    def test_batch_size_limit(self):
        for i in range(4):
            _make_fault_event(seconds_ago=100 - i)
        claimed = EventPoller(batch_size=2, grace_window=0).poll()
        self.assertEqual(len(claimed), 2)
        # 剩余仍为 PENDING
        self.assertEqual(FaultEvent.objects.filter(inspection_status='PENDING').count(), 2)

    def test_reset_in_progress(self):
        fe = _make_fault_event(seconds_ago=10, inspection_status='IN_PROGRESS',
                               inspection_started_at=timezone.now())
        done = _make_fault_event(seconds_ago=5, inspection_status='DONE')
        cw = _make_cw_event(seconds_ago=8, inspection_status='IN_PROGRESS',
                            inspection_started_at=timezone.now())
        reset_count = EventPoller.reset_in_progress()
        self.assertEqual(reset_count, 2)
        fe.refresh_from_db()
        cw.refresh_from_db()
        done.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'PENDING')
        self.assertIsNone(fe.inspection_started_at)
        self.assertEqual(cw.inspection_status, 'PENDING')
        self.assertEqual(done.inspection_status, 'DONE')  # 不动


# ── event_poller.py：持续存在防抖窗口（v1.3.2-IGW）────────────────────────

@tag('unit')
class GraceWindowTest(TestCase):
    """UT-POLL-GW-*: 持续存在防抖窗口过滤 + 孤儿行收尾（REQ-FUNC-GW-001/002/003/005）。"""

    @staticmethod
    def _clear_window_env():
        return mock.patch.dict(
            os.environ,
            {k: v for k, v in os.environ.items()
             if k != 'INSPECTION_GRACE_WINDOW_SECONDS'},
            clear=True)

    def test_get_grace_window_default_is_10_min(self):
        with self._clear_window_env():
            self.assertEqual(get_grace_window(), 600)

    def test_get_grace_window_legal_value(self):
        with mock.patch.dict(os.environ, {'INSPECTION_GRACE_WINDOW_SECONDS': '300'}):
            self.assertEqual(get_grace_window(), 300)

    def test_get_grace_window_illegal_falls_back_to_default(self):
        for bad in ('', 'abc', '0', '-5'):
            with mock.patch.dict(os.environ, {'INSPECTION_GRACE_WINDOW_SECONDS': bad}):
                self.assertEqual(get_grace_window(), 600, msg=f'bad={bad!r}')

    def test_event_younger_than_window_not_claimed(self):
        # 上报 5 分钟前、窗口 10 分钟 → 未达窗口，不认领，保持 PENDING（场景 A）
        fe = _make_fault_event(seconds_ago=300)
        claimed = EventPoller(batch_size=5, grace_window=600).poll()
        self.assertEqual(claimed, [])
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'PENDING')

    def test_event_older_than_window_claimed(self):
        # 上报 11 分钟前、窗口 10 分钟 → 已达窗口，正常认领（场景 C）
        fe = _make_fault_event(seconds_ago=660)
        claimed = EventPoller(batch_size=5, grace_window=600).poll()
        self.assertEqual([e.pk for e in claimed], [fe.pk])
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'IN_PROGRESS')

    def test_window_applies_to_both_event_models(self):
        # 两类事件均受窗口约束：新故障被挡、老结露放行
        young_fe = _make_fault_event(seconds_ago=60)
        old_cw = _make_cw_event(seconds_ago=900)
        claimed = EventPoller(batch_size=5, grace_window=600).poll()
        self.assertEqual([e.pk for e in claimed], [old_cw.pk])
        young_fe.refresh_from_db()
        self.assertEqual(young_fe.inspection_status, 'PENDING')

    def test_skip_recovered_pending_marks_skipped(self):
        # is_active=False 且 PENDING → 标 SKIPPED；活跃 PENDING 不动（场景 B 收尾，REQ-FUNC-GW-005）
        recovered = _make_fault_event(seconds_ago=300, fault_code='E201', is_active=False)
        active = _make_fault_event(seconds_ago=300, fault_code='E202', is_active=True)
        recovered_cw = _make_cw_event(seconds_ago=300, is_active=False)
        with self.assertLogs('freeark.inspection_agent.event_poller', level='INFO'):
            total = EventPoller.skip_recovered_pending()
        self.assertEqual(total, 2)
        recovered.refresh_from_db()
        active.refresh_from_db()
        recovered_cw.refresh_from_db()
        self.assertEqual(recovered.inspection_status, 'SKIPPED')
        self.assertEqual(recovered_cw.inspection_status, 'SKIPPED')
        self.assertEqual(active.inspection_status, 'PENDING')  # 仍活跃，不受影响

    def test_skip_recovered_pending_leaves_done_untouched(self):
        # 仅作用于 PENDING：已恢复但状态 DONE 的行不动（防误伤）
        done = _make_fault_event(seconds_ago=300, fault_code='E301',
                                 is_active=False, inspection_status='DONE')
        total = EventPoller.skip_recovered_pending()
        self.assertEqual(total, 0)
        done.refresh_from_db()
        self.assertEqual(done.inspection_status, 'DONE')


# ── work_order.py ───────────────────────────────────────────────────────

@tag('unit')
class WorkOrderCreateTest(TestCase):
    """UT-WO-1xx: 工单编号生成、按事件建单、防重复建单。"""

    def test_generate_ticket_id_format_and_increment(self):
        now = timezone.now()
        tid1 = work_order.generate_ticket_id(now=now)
        self.assertRegex(tid1, r'^WO-\d{8}-\d{6}$')
        self.assertTrue(tid1.endswith('-000001'))
        # 落一条后，下一个序号递增
        work_order.create_work_order(
            source_event_type='fault_event', source_event_id=1, severity='error',
            affected_device='SN / 3-1-7-702', symptom='x')
        tid2 = work_order.generate_ticket_id(now=now)
        self.assertTrue(tid2.endswith('-000002'))

    def test_create_from_fault_event(self):
        fe = _make_fault_event()
        wo, created = work_order.create_from_event(fe, diagnosis='诊断A',
                                                   recommended_action='建议X')
        self.assertTrue(created)
        self.assertEqual(wo.source_event_type, 'fault_event')
        self.assertEqual(wo.source_event_id, fe.pk)
        self.assertEqual(wo.severity, 'error')
        self.assertEqual(wo.symptom, '通信中断')
        self.assertEqual(wo.affected_device, 'SN-FAULT-001 / 3-1-7-702')
        self.assertEqual(wo.diagnosis, '诊断A')
        self.assertEqual(wo.recommended_action, '建议X')
        self.assertEqual(wo.status, 'OPEN')

    def test_create_from_cw_event_uses_warning_type(self):
        cw = _make_cw_event(warning_type='结露预警')
        wo, created = work_order.create_from_event(cw)
        self.assertTrue(created)
        self.assertEqual(wo.source_event_type, 'condensation_warning_event')
        self.assertEqual(wo.severity, '结露预警')
        self.assertEqual(wo.symptom, '结露报警')

    def test_duplicate_active_returns_existing(self):
        fe = _make_fault_event()
        wo1, c1 = work_order.create_from_event(fe)
        wo2, c2 = work_order.create_from_event(fe)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(wo1.pk, wo2.pk)
        self.assertEqual(WorkOrder.objects.count(), 1)

    def test_can_recreate_after_resolved(self):
        fe = _make_fault_event()
        wo1, _ = work_order.create_from_event(fe)
        wo1.status = 'RESOLVED'
        wo1.resolved_at = timezone.now()
        wo1.save(update_fields=['status', 'resolved_at', 'updated_at'])
        wo2, created = work_order.create_from_event(fe)
        self.assertTrue(created)
        self.assertNotEqual(wo1.pk, wo2.pk)
        self.assertEqual(WorkOrder.objects.count(), 2)


# ── audit.py ────────────────────────────────────────────────────────────

@tag('unit')
class AuditLogTest(TestCase):
    """UT-AUDIT-*: 审计 JSON 结构、事件类型映射、凭证脱敏。"""

    def test_workorder_created_record(self):
        with self.assertLogs('freeark.inspection_agent.audit', level='INFO') as cm:
            rec = audit.log_workorder_created(
                source_event_id=42, source_event_type='fault_event',
                specific_part='3-1-7-702', ticket_id='WO-20260615-000001',
                severity='warning')
        self.assertEqual(rec['event_type'], audit.WORKORDER_CREATED)
        self.assertEqual(rec['source_event_id'], 42)
        self.assertEqual(rec['action_detail']['ticket_id'], 'WO-20260615-000001')
        self.assertEqual(rec['result'], 'SUCCESS')
        # 实际写到了 logger，且是合法 JSON
        payload = json.loads(cm.output[0].split(':', 2)[-1])
        self.assertEqual(payload['event_type'], audit.WORKORDER_CREATED)

    def test_write_blocked_event_type_mapping(self):
        with self.assertLogs('freeark.inspection_agent.audit', level='WARNING'):
            rec_b = audit.log_write_blocked(
                1, 'fault_event', '3-1-7-702', 'set_device_params',
                {'items': []}, 'POLICY_B_NO_AUTO_WRITE')
            rec_w = audit.log_write_blocked(
                2, 'fault_event', '3-1-7-702', 'set_device_params',
                {'items': []}, 'OUT_OF_WHITELIST')
        self.assertEqual(rec_b['event_type'], audit.WRITE_BLOCKED_POLICY_B)
        self.assertEqual(rec_w['event_type'], audit.WRITE_BLOCKED_WHITELIST)
        self.assertEqual(rec_b['result'], 'BLOCKED')

    def test_sensitive_keys_redacted(self):
        with self.assertLogs('freeark.inspection_agent.audit', level='INFO'):
            rec = audit.log_write_executed(
                1, 'fault_event', '3-1-7-702', 'set_device_params',
                {'设定温度': '24', 'api_key': 'sk-should-not-leak',
                 'nested': {'access_token': 'leak2', 'ok': 'visible'}},
                'SUCCESS')
        args = rec['action_detail']['args']
        self.assertEqual(args['api_key'], audit._REDACTED)
        self.assertEqual(args['nested']['access_token'], audit._REDACTED)
        self.assertEqual(args['设定温度'], '24')       # 业务值保留
        self.assertEqual(args['nested']['ok'], 'visible')
        # 序列化后整条日志不含明文凭证
        self.assertNotIn('sk-should-not-leak',
                         json.dumps(rec, ensure_ascii=False))
