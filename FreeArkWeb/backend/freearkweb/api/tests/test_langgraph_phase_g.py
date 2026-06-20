"""
单元测试 —— LangGraph 阶段 G：跨 agent 子委托（expert→expert）

全离线：FREEARK_POC_MOCK=1（工具 canned）+ LANGGRAPH_USE_FAKE_LLM=True（假模型）。
fake LLM 见 'TOOLCALL:<name>' 链按序逐个发起工具调用（含委托工具）。

覆盖：
  - 读/知识委托：inspection 调 delegate_knowledge→sanheng、delegate_read→energy，
    内联跑只读子专家、结果回灌、审计日志正确；深度限 1（子专家不带委托工具，不递归）。
  - 写委托：delegate_write → pending_write → **复用现有 _gate interrupt 确认门**：
    ①触发 confirm_required ②批准→execute_write（带 operator 追溯）③拒绝→不执行。
  - 非委托专家（energy）不暴露委托工具。

运行：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_langgraph_phase_g --settings=freearkweb.test_settings -v2
"""

import json
import os
import unittest

os.environ.setdefault("FREEARK_POC_MOCK", "1")  # 必须在 import fa_tools 前置

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings, tag

try:
    import langgraph  # noqa: F401
    import langchain_core  # noqa: F401
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 G 测试")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class ReadKnowledgeDelegationTests(SimpleTestCase):
    """读/知识委托：内联跑只读子专家、回灌、审计日志。"""

    def _orch(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        return Orchestrator(latency=0.0)

    def test_inspection_delegates_knowledge_and_read(self):
        # 巡检（关键词路由命中）依次委托三恒分析 + 能耗取数，均为只读、内联回灌。
        out = async_to_sync(self._orch().run)(
            "巡检 TOOLCALL:delegate_knowledge TOOLCALL:delegate_read")
        self.assertEqual(out["experts"], ["inspection-expert"])
        self.assertEqual(
            out["delegations"],
            [{"target_agent": "sanheng-knowledge",
              "intent": "knowledge_query", "status": "OK"},
             {"target_agent": "energy-expert",
              "intent": "read_query", "status": "OK"}])
        self.assertTrue(out["answer"])  # 续推理给出最终答复

    def test_knowledge_only_delegation(self):
        out = async_to_sync(self._orch().run)("巡检 TOOLCALL:delegate_knowledge")
        self.assertEqual(
            [d["target_agent"] for d in out["delegations"]], ["sanheng-knowledge"])

    def test_non_delegating_expert_has_no_delegation_tools(self):
        # 路由到 energy（非委托专家）：脚本里的 delegate_knowledge 未绑定→被过滤→无委托。
        out = async_to_sync(self._orch().run)("能耗 TOOLCALL:delegate_knowledge")
        self.assertEqual(out["experts"], ["energy-expert"])
        self.assertEqual(out["delegations"], [])

    def test_subexpert_depth_limit_no_recursion(self):
        # 子专家不带委托工具：即便把委托链塞进 origin_query，被委托的 energy/sanheng
        # 也不会再触发委托（valid 集合不含 delegate_*）。run 正常返回即证明无无限递归。
        out = async_to_sync(self._orch().run)(
            "巡检 TOOLCALL:delegate_read TOOLCALL:delegate_knowledge")
        self.assertEqual(
            sorted(d["intent"] for d in out["delegations"]),
            ["knowledge_query", "read_query"])


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 G 测试")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class WriteDelegationGateTests(SimpleTestCase):
    """写委托复用现有 _gate interrupt 确认门。"""

    def setUp(self):
        import api.langgraph_chat.adapter as ad
        ad._ORCH = None

    def _set_orch(self):
        import api.langgraph_chat.adapter as ad
        from api.langgraph_chat.orchestrator import Orchestrator
        ad._ORCH = Orchestrator(latency=0.0)

    def _stream(self, adapter_cls, msg, sess):
        async def _go():
            return [(k, t) async for k, t in adapter_cls.stream_chat(msg, sess)]
        return async_to_sync(_go)()

    def _resume(self, adapter_cls, sess, approved):
        async def _go():
            return [(k, t) async for k, t
                    in adapter_cls.resume_chat(sess, {"approved": approved})]
        return async_to_sync(_go)()

    def test_delegate_write_triggers_confirm_then_executes(self):
        from api.langgraph_chat.adapter import LangGraphAdapter
        self._set_orch()
        chunks = self._stream(
            LangGraphAdapter,
            "[__freeark_user__:alice] 巡检处置 TOOLCALL:delegate_write", "gsess1")
        confirms = [t for k, t in chunks if k == "confirm"]
        self.assertTrue(confirms, "委托写未触发确认门")
        payload = json.loads(confirms[0])
        self.assertEqual(payload["kind"], "confirm_required")
        # delegate_write 映射到能耗写工具 set_device_params，经 gate 确认
        self.assertEqual(payload["actions"][0]["tool"], "set_device_params")
        self.assertFalse([t for k, t in chunks if k == "content"])  # 确认前不执行
        out2 = self._resume(LangGraphAdapter, "gsess1", True)
        self.assertIn("已执行", "".join(t for k, t in out2 if k == "content"))

    def test_delegate_write_rejected_does_not_execute(self):
        from unittest import mock
        import api.langgraph_chat.orchestrator as orch_mod
        from api.langgraph_chat.adapter import LangGraphAdapter
        self._set_orch()
        with mock.patch.object(orch_mod, "execute_write") as m:
            self._stream(
                LangGraphAdapter,
                "[__freeark_user__:bob] 巡检处置 TOOLCALL:delegate_write", "gsess2")
            out2 = self._resume(LangGraphAdapter, "gsess2", False)
            m.assert_not_called()
        self.assertIn("已取消", "".join(t for k, t in out2 if k == "content"))

    def test_delegate_write_approve_executes_with_operator(self):
        from unittest import mock
        import api.langgraph_chat.orchestrator as orch_mod
        from api.langgraph_chat.adapter import LangGraphAdapter
        self._set_orch()
        with mock.patch.object(orch_mod, "execute_write",
                               return_value={"success": True, "summary": "ok"}) as m:
            self._stream(
                LangGraphAdapter,
                "[__freeark_user__:alice] 巡检处置 TOOLCALL:delegate_write", "gsess3")
            self._resume(LangGraphAdapter, "gsess3", True)
            m.assert_called_once()
            args = m.call_args.args
            self.assertEqual(args[0], "set_device_params")          # 映射到能耗写工具
            self.assertEqual(args[2], "openclaw-agent::alice")      # operator 追溯
