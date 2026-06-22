"""
单元测试 —— LangGraph 生产缺陷修复验证（2026-06-22）

缺陷 1：多专家 aggregate 输出暴露内部专家 id / 转交措辞
缺陷 2：多专家路径回复逐字重复两遍（AIMessage+AIMessageChunk 均放行导致双倍）

全离线：FREEARK_POC_MOCK=1 + LANGGRAPH_USE_FAKE_LLM=True

运行命令：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_langgraph_defect_fixes --settings=freearkweb.test_settings --verbosity=2
"""

import os
import unittest

os.environ.setdefault("FREEARK_POC_MOCK", "1")

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings, tag

try:
    import langgraph  # noqa: F401
    import langchain_core  # noqa: F401
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class AggregateNoExpertLabelTests(SimpleTestCase):
    """缺陷 1：aggregate 融合输出不得含专家 id 标签或内部转交措辞。"""

    def _orch(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        return Orchestrator(latency=0.0)

    def test_aggregate_digest_excludes_expert_id_labels(self):
        """直接调 _aggregate：fake LLM final_text 不含 [energy-expert] 等标签。"""
        orch = self._orch()
        results = [
            {"expert": "energy-expert", "answer": "能耗正常，今日用电 120kWh。"},
            {"expert": "inspection-expert", "answer": "巡检发现 2 台设备异常。"},
        ]
        out = async_to_sync(orch._aggregate)({"expert_results": results})
        final_msg = out["messages"][-1].content
        self.assertIsInstance(final_msg, str)
        self.assertTrue(final_msg)
        self.assertNotIn("[energy-expert]", final_msg)
        self.assertNotIn("[inspection-expert]", final_msg)
        self.assertNotIn("[sanheng-knowledge]", final_msg)

    def test_aggregate_system_prompt_forbids_routing_terms(self):
        """_aggregate 源码里的 SystemMessage 须含禁止暴露内部分工的措辞。"""
        import inspect
        from api.langgraph_chat.orchestrator import Orchestrator
        src = inspect.getsource(Orchestrator._aggregate)
        self.assertIn("严格禁止", src)
        self.assertIn("转交", src)

    def test_single_expert_passthrough_unchanged(self):
        """单专家时直接透传 answer，不经 LLM 融合，output 与 answer 一致。"""
        orch = self._orch()
        answer = "今日能耗 120kWh，系统正常。"
        results = [{"expert": "energy-expert", "answer": answer}]
        out = async_to_sync(orch._aggregate)({"expert_results": results})
        self.assertEqual(out["messages"][-1].content, answer)

    def test_no_results_returns_retry_message(self):
        """无有效结果时返回标准"请重试"提示，不抛异常。"""
        orch = self._orch()
        out = async_to_sync(orch._aggregate)({"expert_results": []})
        self.assertIn("重试", out["messages"][-1].content)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class DriveNoduplicateTests(SimpleTestCase):
    """缺陷 2：_drive 多专家路径不得重复输出（AIMessageChunk 增量 + 终态 AIMessage 各一份）。"""

    def setUp(self):
        import api.langgraph_chat.adapter as ad
        ad._ORCH = None

    def test_drive_multi_expert_no_content_duplication(self):
        """
        注入 mock astream：aggregate 节点先产 AIMessageChunk 增量（内容="ABC"），
        再产终态 AIMessage（内容="ABC"）。修复后只透传 Chunk，总输出 "ABC" 不翻倍。
        """
        from langchain_core.messages import AIMessage, AIMessageChunk
        from api.langgraph_chat.adapter import _drive

        class _MockGraph:
            async def astream(self, payload, config, stream_mode):
                yield ("updates", {"route": {"plan": [("energy-expert", "q"), ("inspection-expert", "q")]}})
                yield ("messages", (AIMessageChunk(content="ABC"), {"langgraph_node": "aggregate"}))
                yield ("messages", (AIMessage(content="ABC"), {"langgraph_node": "aggregate"}))

            async def aget_state(self, config):
                return None

        class _MockOrch:
            graph = _MockGraph()

            @staticmethod
            def _cfg(thread_id):
                return {"configurable": {"thread_id": thread_id}}

        async def _collect():
            out = []
            async for kind, text in _drive(_MockOrch(), {"messages": []}, {}):
                if kind == "content":
                    out.append(text)
            return out

        total = "".join(async_to_sync(_collect)())
        self.assertEqual(total, "ABC", f"期望 'ABC'，实际 '{total}'（可能重复）")

    def test_drive_single_expert_not_affected(self):
        """单专家路径 expert 节点的 AIMessageChunk 正常透传，不受修复影响。"""
        from langchain_core.messages import AIMessageChunk
        from api.langgraph_chat.adapter import _drive

        class _MockGraph:
            async def astream(self, payload, config, stream_mode):
                yield ("updates", {"route": {"plan": [("energy-expert", "q")]}})
                yield ("messages", (AIMessageChunk(content="XYZ"), {"langgraph_node": "expert"}))

            async def aget_state(self, config):
                return None

        class _MockOrch:
            graph = _MockGraph()

            @staticmethod
            def _cfg(thread_id):
                return {}

        async def _go():
            out = []
            async for kind, text in _drive(_MockOrch(), {}, {}):
                if kind == "content":
                    out.append(text)
            return out

        self.assertEqual("".join(async_to_sync(_go)()), "XYZ")

    def test_drive_fallback_when_no_stream_chunks(self):
        """非流式兜底：只有终态 AIMessage 时走 aget_state 补发，输出一次不重复。"""
        from langchain_core.messages import AIMessage
        from api.langgraph_chat.adapter import _drive
        from types import SimpleNamespace

        class _MockGraph:
            async def astream(self, payload, config, stream_mode):
                yield ("updates", {"route": {"plan": [("energy-expert", "q"), ("inspection-expert", "q")]}})
                yield ("messages", (AIMessage(content="FALLBACK"), {"langgraph_node": "aggregate"}))

            async def aget_state(self, config):
                return SimpleNamespace(values={"messages": [AIMessage(content="FALLBACK")]})

        class _MockOrch:
            graph = _MockGraph()

            @staticmethod
            def _cfg(thread_id):
                return {}

        async def _go():
            out = []
            async for kind, text in _drive(_MockOrch(), {}, {}):
                if kind == "content":
                    out.append(text)
            return out

        chunks = async_to_sync(_go)()
        self.assertEqual(chunks, ["FALLBACK"], f"兜底路径期望 ['FALLBACK']，实际 {chunks}")
