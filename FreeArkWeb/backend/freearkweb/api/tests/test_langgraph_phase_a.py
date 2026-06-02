"""
单元测试 —— LangGraph 阶段 A 影子接入（api.langgraph_chat + chat_backend 工厂）

全离线：FREEARK_POC_MOCK=1（工具返回 canned 数据）+ LANGGRAPH_USE_FAKE_LLM=True
（假模型，毫秒级延迟），不连真 DeepSeek、不连真后端，跑通真实 LangGraph 图遍历。

覆盖范围：
  - chat_backend 工厂按 CHAT_BACKEND 选对适配器（默认 openclaw / 显式 langgraph）
  - 关键词路由：单意图 → 1 专家；复合意图 → 多专家（并行 fan-out 命中集合正确）
  - Orchestrator.run / run_serial 返回结构正确，且专家集合一致（仅并发度不同）
  - LangGraphAdapter.stream_chat 签名与 yield 协议（(kind, text)，kind=='content'）
  - 适配器失败时抛 OpenClawUnavailableError（统一降级通道）

运行命令：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_langgraph_phase_a --settings=freearkweb.test_settings --verbosity=2

⚠️ aarch64 纪律：本套件离线验证编排接线；真机启用前仍须在 Pi 上跑
   `python -m api.langgraph_chat.fa_tools`（LIVE 5/5）+ 真 DeepSeek 端到端墙钟。
"""

import os
import unittest

# 必须在 import 工具桥接层之前置 mock 标志（fa_tools 在 import 期读取它）。
os.environ.setdefault("FREEARK_POC_MOCK", "1")

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings

# 检测 langgraph 依赖是否可用（阶段 A：默认 openclaw 部署可能未装）。
try:
    import langgraph  # noqa: F401
    import langchain_core  # noqa: F401
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 A 离线测试")
class ChatBackendFactoryTests(SimpleTestCase):
    """chat_backend 工厂选择逻辑。"""

    @override_settings(CHAT_BACKEND="openclaw")
    def test_default_selects_openclaw(self):
        from api.chat_backend import get_chat_adapter
        from api.openclaw_adapter import OpenClawAdapter
        self.assertIs(get_chat_adapter(), OpenClawAdapter)

    @override_settings(CHAT_BACKEND="langgraph")
    def test_switch_selects_langgraph(self):
        from api.chat_backend import get_chat_adapter
        from api.langgraph_chat.adapter import LangGraphAdapter
        self.assertIs(get_chat_adapter(), LangGraphAdapter)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 A 离线测试")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
class OrchestratorRoutingTests(SimpleTestCase):
    """关键词路由 + 并行/串行编排结构。"""

    def _orch(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        return Orchestrator(latency=0.0)

    def test_router_single_intent(self):
        from api.langgraph_chat.router import route_experts
        self.assertEqual(route_experts("看一下今天的能耗看板"), ["energy-expert"])

    def test_router_composite_intent(self):
        from api.langgraph_chat.router import route_experts
        chosen = route_experts("对比能耗看板与 PLC 故障巡检，并解释三恒原理")
        self.assertEqual(set(chosen),
                         {"energy-expert", "inspection-expert", "sanheng-knowledge"})

    def test_run_single_expert(self):
        result = async_to_sync(self._orch().run)("看一下今天的能耗看板")
        self.assertEqual(result["experts"], ["energy-expert"])
        self.assertIsInstance(result["answer"], str)
        self.assertTrue(result["answer"])

    def test_run_parallel_vs_serial_same_experts(self):
        orch = self._orch()
        q = "对比能耗看板与 PLC 故障巡检，并解释三恒原理"
        parallel = async_to_sync(orch.run)(q)
        serial = async_to_sync(orch.run_serial)(q)
        # 并行与串行命中的专家集合必须一致（仅并发度不同）
        self.assertEqual(set(parallel["experts"]), set(serial["experts"]))
        self.assertEqual(len(parallel["experts"]), 3)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 A 离线测试")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
class LangGraphAdapterTests(SimpleTestCase):
    """drop-in 适配器签名与 yield 协议。"""

    def setUp(self):
        # 清掉可能被前序测试构造的单例，确保用当前 override_settings 重建。
        import api.langgraph_chat.adapter as ad
        ad._ORCH = None

    def test_stream_chat_yields_content_tuples(self):
        from api.langgraph_chat.adapter import LangGraphAdapter

        async def _collect():
            out = []
            async for kind, text in LangGraphAdapter.stream_chat(
                    message="看一下今天的能耗看板", session_key="test-session"):
                out.append((kind, text))
            return out

        chunks = async_to_sync(_collect)()
        self.assertTrue(chunks, "适配器未产出任何 chunk")
        for kind, text in chunks:
            self.assertIn(kind, ("reasoning", "content"))
            self.assertIsInstance(text, str)
        # 至少有一个 content 块，且拼起来非空
        content = "".join(t for k, t in chunks if k == "content")
        self.assertTrue(content)

    def test_failure_raises_openclaw_unavailable(self):
        """编排构造/运行失败统一抛 OpenClawUnavailableError（consumers 降级通道）。"""
        from api.openclaw_adapter import OpenClawUnavailableError
        import api.langgraph_chat.adapter as ad

        class _Boom:
            class graph:
                @staticmethod
                def astream(*a, **k):
                    raise RuntimeError("boom")
        ad._ORCH = _Boom()

        async def _collect():
            async for _ in ad.LangGraphAdapter.stream_chat(
                    message="x", session_key="s"):
                pass

        with self.assertRaises(OpenClawUnavailableError):
            async_to_sync(_collect)()
