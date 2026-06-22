"""
test_inspection_agent_loop_v110.py — v1.1.0-AIA（方案 B）增量③ 决策循环单元测试

不触 langgraph / 真 LLM：注入 fake orchestrator（async _expert）与 fake write_executor，
验证 InspectionAgent 的处置编排与 WriteAuthPolicy 联动（OD-01 策略B 唯一写入口、无旁路）。

  UT-AGENT-001 结论(answer)路径 → 建工单(recommended_action=结论)，事件置 DONE
  UT-AGENT-002 写提案 + 策略B → 拦截建单（不调 execute_write），审计 WRITE_BLOCKED
  UT-AGENT-003 写提案 + 策略A 区间内 → 调 execute_write、不建单、DONE，审计 WRITE_EXECUTED
  UT-AGENT-004 事件已恢复(inactive) → SKIPPED、不建单
  UT-AGENT-005 决策超时/异常 → 兜底建单、DONE（不丢单、不崩溃）
  UT-AGENT-006 run_once 串行处置轮询取到的多条事件
  UT-AGENT-007 工单/状态持久化失败 → 事件重置 PENDING 待重试（不置 DONE）
  UT-AGENT-008 同一事件重复处置 → 命中活跃工单去重，不重复建单
  UT-AGENT-009 run_once 顺带把已恢复仍 PENDING 的孤儿行标 SKIPPED（v1.3.2-IGW，REQ-FUNC-GW-005）

运行：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_inspection_agent_loop_v110 \\
        --settings=freearkweb.test_settings --verbosity=2
"""

import asyncio
import json
import os
from unittest import mock

from django.test import TestCase, tag
from django.utils import timezone

from api.models import CondensationWarningEvent, FaultEvent, WorkOrder
from inspection_agent import agent as agent_mod
from inspection_agent.agent import InspectionAgent
from inspection_agent.auth import WriteAuthPolicy
from inspection_agent.event_poller import EventPoller


# ── 夹具 ────────────────────────────────────────────────────────────────

def _make_fault_event(seconds_ago=0, **overrides):
    base = timezone.now() - timezone.timedelta(seconds=seconds_ago)
    defaults = dict(
        specific_part='3-1-7-702', device_sn='SN-FAULT-001', product_code='PC-001',
        fault_code='E101', fault_type='comm', fault_message='通信中断',
        severity='error', first_seen_at=base, last_seen_at=base,
    )
    defaults.update(overrides)
    return FaultEvent.objects.create(**defaults)


def _make_cw_event(seconds_ago=0, **overrides):
    base = timezone.now() - timezone.timedelta(seconds=seconds_ago)
    defaults = dict(
        specific_part='3-1-8-801', device_sn='SN-CW-001', product_code='PC-001',
        warning_type='结露预警', warning_message='结露报警',
        first_seen_at=base, last_seen_at=base,
    )
    defaults.update(overrides)
    return CondensationWarningEvent.objects.create(**defaults)


class _FakeOrchestrator:
    """提供 async _expert(state)：返回预置 expert_results 或抛异常。"""

    def __init__(self, result=None, raise_exc=None):
        self.result = result if result is not None else {"expert_results": []}
        self.raise_exc = raise_exc
        self.calls = []

    async def _expert(self, state):
        self.calls.append(state)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.result


class _FakeWriteExecutor:
    def __init__(self, out=None):
        self.out = out if out is not None else {"success": True, "summary": "已下发(fake)"}
        self.calls = []

    def __call__(self, tool, args, operator):
        self.calls.append((tool, args, operator))
        return self.out


def _answer_result(answer, delegations=None):
    return {"expert_results": [{
        "expert": "inspection-expert", "answer": answer,
        "delegations": delegations or [],
    }]}


def _pending_write_result(tool, args, delegations=None):
    return {"expert_results": [{
        "expert": "inspection-expert",
        "pending_write": {"tool": tool, "args": args},
        "delegations": delegations or [],
    }]}


def _agent(orchestrator, auth_policy=None, write_executor=None, poller=None):
    return InspectionAgent(orchestrator=orchestrator,
                           auth_policy=auth_policy or WriteAuthPolicy(),
                           poller=poller, write_executor=write_executor)


# ── 测试 ────────────────────────────────────────────────────────────────

@tag('unit')
class DecisionLoopTest(TestCase):

    def test_conclusion_creates_workorder(self):
        fe = _make_fault_event()
        orch = _FakeOrchestrator(_answer_result(
            "传感器疑似漂移，建议人工现场校准。",
            delegations=[{"target_agent": "sanheng-knowledge",
                          "intent": "knowledge_query", "status": "OK"}]))
        with self.assertLogs('freeark.inspection_agent.audit', level='INFO'):
            _agent(orch).process_event(fe)
        self.assertEqual(len(orch.calls), 1)
        self.assertEqual(orch.calls[0]['name'], 'inspection-expert')
        wo = WorkOrder.objects.get()
        self.assertEqual(wo.source_event_type, 'fault_event')
        self.assertEqual(wo.source_event_id, fe.pk)
        self.assertIn('校准', wo.recommended_action)
        self.assertIn('sanheng-knowledge', wo.diagnosis)
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'DONE')

    def test_write_proposal_blocked_policy_b(self):
        fe = _make_fault_event()
        orch = _FakeOrchestrator(_pending_write_result(
            "set_device_params",
            {"specific_part": "3-1-7-702",
             "items": [{"param_name": "设定温度", "new_value": "24"}]}))
        write_exec = _FakeWriteExecutor()
        with mock.patch.dict(os.environ, {'AUTO_WRITE_POLICY': 'B'}):
            with self.assertLogs('freeark.inspection_agent.audit', level='INFO') as cm:
                _agent(orch, write_executor=write_exec).process_event(fe)
        # 策略B：绝不调用 execute_write
        self.assertEqual(write_exec.calls, [])
        wo = WorkOrder.objects.get()
        self.assertIn('设定温度', wo.recommended_action)
        self.assertIn('拦截', wo.recommended_action)
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'DONE')
        # 审计含 WRITE_BLOCKED_POLICY_B 与 WORKORDER_CREATED
        joined = "\n".join(cm.output)
        self.assertIn('WRITE_BLOCKED_POLICY_B', joined)
        self.assertIn('WORKORDER_CREATED', joined)

    def test_write_proposal_allowed_policy_a_executes(self):
        fe = _make_fault_event()
        orch = _FakeOrchestrator(_pending_write_result(
            "set_device_params",
            {"specific_part": "3-1-7-702",
             "items": [{"param_name": "设定温度", "new_value": "24"}]}))
        write_exec = _FakeWriteExecutor({"success": True, "summary": "ok"})
        wl = {"set_device_params": {"设定温度": {"abs_min": 20, "abs_max": 28}}}
        with mock.patch.dict(os.environ, {
                'AUTO_WRITE_POLICY': 'A',
                'INSPECTION_WRITE_WHITELIST': json.dumps(wl)}):
            policy = WriteAuthPolicy()
            with self.assertLogs('freeark.inspection_agent.audit', level='INFO') as cm:
                _agent(orch, auth_policy=policy, write_executor=write_exec).process_event(fe)
        # 策略A 区间内：调用 execute_write，operator 注入 inspection-agent，不建工单
        self.assertEqual(len(write_exec.calls), 1)
        self.assertEqual(write_exec.calls[0][0], 'set_device_params')
        self.assertEqual(write_exec.calls[0][2], 'inspection-agent')
        self.assertEqual(WorkOrder.objects.count(), 0)
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'DONE')
        self.assertIn('WRITE_EXECUTED', "\n".join(cm.output))

    def test_inactive_event_skipped(self):
        fe = _make_fault_event(is_active=False)
        orch = _FakeOrchestrator(_answer_result("x"))
        _agent(orch).process_event(fe)
        # 未走决策，未建单
        self.assertEqual(orch.calls, [])
        self.assertEqual(WorkOrder.objects.count(), 0)
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'SKIPPED')

    def test_decision_exception_fallback_workorder(self):
        fe = _make_fault_event()
        orch = _FakeOrchestrator(raise_exc=asyncio.TimeoutError())
        with self.assertLogs('freeark.inspection_agent.audit', level='INFO'):
            _agent(orch).process_event(fe)
        wo = WorkOrder.objects.get()
        self.assertIn('兜底', wo.recommended_action)
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'DONE')

    def test_run_once_processes_polled_events(self):
        _make_fault_event(seconds_ago=20)
        _make_cw_event(seconds_ago=10)
        orch = _FakeOrchestrator(_answer_result("无需处置，持续观察。"))
        # grace_window=0：本测试验证轮询处置编排，与防抖窗口无关
        with self.assertLogs('freeark.inspection_agent.audit', level='INFO'):
            processed = _agent(orch, poller=EventPoller(grace_window=0)).run_once()
        self.assertEqual(processed, 2)
        self.assertEqual(WorkOrder.objects.count(), 2)
        self.assertEqual(FaultEvent.objects.filter(inspection_status='DONE').count(), 1)
        self.assertEqual(
            CondensationWarningEvent.objects.filter(inspection_status='DONE').count(), 1)

    def test_run_once_sweeps_recovered_pending_to_skipped(self):
        # 一条已恢复(is_active=False)却仍 PENDING 的孤儿行：run_once 应顺带标 SKIPPED，
        # 且不当作处理事件（REQ-FUNC-GW-005，OQ-2=B）
        _make_fault_event(seconds_ago=10, is_active=False)
        orch = _FakeOrchestrator(_answer_result("x"))
        processed = _agent(orch, poller=EventPoller(grace_window=0)).run_once()
        self.assertEqual(processed, 0)               # 孤儿行不被认领处理
        self.assertEqual(orch.calls, [])             # 未走决策
        self.assertEqual(WorkOrder.objects.count(), 0)
        fe = FaultEvent.objects.get()
        self.assertEqual(fe.inspection_status, 'SKIPPED')

    def test_persistence_failure_resets_pending(self):
        fe = _make_fault_event()
        orch = _FakeOrchestrator(_answer_result("建议人工检查。"))
        with mock.patch.object(agent_mod, 'create_from_event',
                               side_effect=RuntimeError('db down')):
            _agent(orch).process_event(fe)
        self.assertEqual(WorkOrder.objects.count(), 0)
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'PENDING')
        self.assertIsNone(fe.inspection_started_at)

    def test_duplicate_event_no_second_workorder(self):
        fe = _make_fault_event()
        orch = _FakeOrchestrator(_answer_result("建议人工检查。"))
        ag = _agent(orch)
        with self.assertLogs('freeark.inspection_agent.audit', level='INFO'):
            ag.process_event(fe)
        # 复位为 PENDING 再处理一次，应命中活跃工单去重
        fe.inspection_status = 'PENDING'
        fe.save(update_fields=['inspection_status'])
        ag.process_event(fe)
        self.assertEqual(WorkOrder.objects.count(), 1)
