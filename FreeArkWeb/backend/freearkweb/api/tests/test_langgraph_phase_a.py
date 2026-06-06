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


class PromptLoadingTests(SimpleTestCase):
    """阶段 C：专家提示装载——优先 .langgraph.md、剥 HTML 注释、sanheng 拼 KNOWLEDGE。

    纯 stdlib + django.conf，不依赖 langgraph，默认 openclaw 部署也能跑。"""

    def test_strip_comments(self):
        from api.langgraph_chat.prompts import _strip_comments
        out = _strip_comments(
            "<!--\nprovenance 注释\n-->\n\n# 标题\n正文 <!-- 行内 --> 结尾")
        self.assertNotIn("provenance", out)
        self.assertNotIn("<!--", out)
        self.assertIn("# 标题", out)
        self.assertIn("正文", out)
        self.assertIn("结尾", out)

    def test_prefers_langgraph_variant_and_strips_comment(self):
        import tempfile
        from pathlib import Path
        from api.langgraph_chat import prompts as P
        with tempfile.TemporaryDirectory() as d:
            ed = Path(d) / "energy-expert"
            ed.mkdir()
            (ed / "SYSTEM_PROMPT.md").write_text(
                "OPENCLAW_VER exec python3 freeark_tool.py", encoding="utf-8")
            (ed / "SYSTEM_PROMPT.langgraph.md").write_text(
                "<!-- prov -->\nLANGGRAPH_VER", encoding="utf-8")
            text, fname = P._read_prompt_file(ed)
        self.assertEqual(fname, "SYSTEM_PROMPT.langgraph.md")
        self.assertIn("LANGGRAPH_VER", text)
        self.assertNotIn("OPENCLAW_VER", text)
        self.assertNotIn("<!--", text)

    def test_falls_back_to_openclaw_md_when_no_variant(self):
        import tempfile
        from pathlib import Path
        from api.langgraph_chat import prompts as P
        with tempfile.TemporaryDirectory() as d:
            ed = Path(d) / "energy-expert"
            ed.mkdir()
            (ed / "SYSTEM_PROMPT.md").write_text("ONLY_OPENCLAW", encoding="utf-8")
            text, fname = P._read_prompt_file(ed)
        self.assertEqual(fname, "SYSTEM_PROMPT.md")
        self.assertIn("ONLY_OPENCLAW", text)

    def test_missing_files_raise(self):
        import tempfile
        from pathlib import Path
        from api.langgraph_chat import prompts as P
        with tempfile.TemporaryDirectory() as d:
            ed = Path(d) / "energy-expert"
            ed.mkdir()
            with self.assertRaises(FileNotFoundError):
                P._read_prompt_file(ed)

    def test_load_real_repo_prompts_are_langgraph_native(self):
        """对真实仓库 agents/ 装载：三专家均装载成功、注释已剥离、sanheng 拼 KNOWLEDGE.md。

        注：不断言提示里不含 'freeark_tool.py'/'operator_override' 字面——LangGraph 版提示
        常以**否定指令**提及这些（如「不要输出 freeark_tool.py 之类」），属合法内容。"""
        from api.langgraph_chat.prompts import load_expert_prompts, _FALLBACK_PROMPTS
        prompts = load_expert_prompts()
        for name in ("energy-expert", "inspection-expert", "sanheng-knowledge"):
            self.assertNotEqual(
                prompts[name], _FALLBACK_PROMPTS[name],
                f"{name} 退回了内置兜底（应装载 .langgraph.md）")
            # provenance 注释块已剥离（不把 <!-- --> 喂给模型）
            self.assertNotIn("<!--", prompts[name], name)
        # sanheng 装载时拼接了参考知识区（KNOWLEDGE.md）
        self.assertIn("参考知识", prompts["sanheng-knowledge"])


class _StubLLM:
    """最小异步 LLM 桩：ainvoke 返回带 .content 的对象，或抛异常。不依赖 langchain。"""

    def __init__(self, content=None, exc=None):
        self._content = content
        self._exc = exc

    async def ainvoke(self, messages, **kwargs):
        if self._exc is not None:
            raise self._exc

        class _Msg:
            pass
        m = _Msg()
        m.content = self._content
        return m


class RouterClassifierTests(SimpleTestCase):
    """阶段 D：LLM 意图分类器解析 + 三级兜底链（纯逻辑，不依赖 langgraph）。"""

    # ── parse_route_response 鲁棒性 ──────────────────────────────
    def test_parse_clean_json(self):
        from api.langgraph_chat.router import parse_route_response
        self.assertEqual(parse_route_response('["energy-expert"]'), ["energy-expert"])

    def test_parse_json_fenced(self):
        from api.langgraph_chat.router import parse_route_response
        raw = '```json\n["inspection-expert"]\n```'
        self.assertEqual(parse_route_response(raw), ["inspection-expert"])

    def test_parse_prose_wrapped(self):
        from api.langgraph_chat.router import parse_route_response
        raw = '我认为应当由 ["energy-expert","sanheng-knowledge"] 处理。'
        self.assertEqual(parse_route_response(raw),
                         ["energy-expert", "sanheng-knowledge"])

    def test_parse_filters_invalid_names_and_dedupes(self):
        from api.langgraph_chat.router import parse_route_response
        raw = '["foo","energy-expert","energy-expert","bar"]'
        self.assertEqual(parse_route_response(raw), ["energy-expert"])

    def test_parse_skips_non_name_array_then_finds_valid(self):
        from api.langgraph_chat.router import parse_route_response
        # 第一个数组 [1,2] 无合法名 → 跳过；第二个数组命中
        raw = '参考 [1,2] 后判断：["inspection-expert"]'
        self.assertEqual(parse_route_response(raw), ["inspection-expert"])

    def test_parse_empty_or_garbage_returns_none(self):
        from api.langgraph_chat.router import parse_route_response
        for raw in ("", None, "[]", "没有数组", '["foo"]', "[not json]"):
            self.assertIsNone(parse_route_response(raw), repr(raw))

    # ── classify_experts 三级兜底 ────────────────────────────────
    def test_classify_llm_hit_wins(self):
        from api.langgraph_chat.router import classify_experts
        # LLM 明确命中 inspection，即便文本含能耗关键词也以 LLM 为准
        out = async_to_sync(classify_experts)(
            _StubLLM('["inspection-expert"]'), "看一下能耗看板")
        self.assertEqual(out, ["inspection-expert"])

    def test_classify_llm_composite(self):
        from api.langgraph_chat.router import classify_experts
        out = async_to_sync(classify_experts)(
            _StubLLM('["energy-expert","sanheng-knowledge"]'), "随便问")
        self.assertEqual(set(out), {"energy-expert", "sanheng-knowledge"})

    def test_classify_garbage_falls_back_to_keyword(self):
        from api.langgraph_chat.router import classify_experts
        # LLM 输出无法解析 → 关键词路由命中"三恒原理"
        out = async_to_sync(classify_experts)(
            _StubLLM("我不确定"), "请讲讲三恒原理")
        self.assertEqual(out, ["sanheng-knowledge"])

    def test_classify_exception_falls_back_to_keyword(self):
        from api.langgraph_chat.router import classify_experts
        out = async_to_sync(classify_experts)(
            _StubLLM(exc=RuntimeError("boom")), "PLC 故障巡检")
        self.assertEqual(out, ["inspection-expert"])

    def test_classify_empty_llm_falls_back_then_default(self):
        from api.langgraph_chat.router import classify_experts
        # LLM 返回 [] → 关键词路由；文本无关键词 → DEFAULT_EXPERT
        out = async_to_sync(classify_experts)(_StubLLM("[]"), "你好啊")
        self.assertEqual(out, ["energy-expert"])

    def test_classify_none_llm_uses_keyword(self):
        from api.langgraph_chat.router import classify_experts
        out = async_to_sync(classify_experts)(None, "查一下用电量")
        self.assertEqual(out, ["energy-expert"])


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


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
class FaDirectRoutingTests(SimpleTestCase):
    """阶段 B：DirectClient 的 URL 解析路由机制（离线，不需 DB）。"""

    def test_resolve_maps_tool_paths_to_views(self):
        # 用 url_name 断言（稳定，不受 @cache_dashboard 等装饰器改写 func.__name__ 影响）；
        # DirectClient 用 match.func 直接调用，不依赖名字。
        from django.urls import resolve
        cases = {
            "/api/dashboard/summary/": "dashboard-summary",
            "/api/usage/quantity/": "get-usage-quantity",
            "/api/devices/realtime-params/": "device-realtime-params",
            "/api/plc/connection-status/": "get-plc-connection-status",
            "/api/devices/fault-summary/": "device-fault-summary",
        }
        for path, uname in cases.items():
            m = resolve(path)
            self.assertEqual(m.url_name, uname, path)
            self.assertTrue(callable(m.func), path)

    def test_directclient_unknown_path_returns_404_envelope(self):
        # Resolver404 先于鉴权/DB 触发，无需数据库
        from api.langgraph_chat.fa_direct import DirectClient
        r = DirectClient().get("/api/__definitely_nonexistent__/")
        self.assertFalse(r["success"])
        self.assertEqual(r["http_status"], 404)

    @override_settings(FA_TOOLS_MODE="http")
    def test_default_mode_resolves_http(self):
        # 默认 http（现状零风险）；env 未设时取 settings 值
        import os
        from api.langgraph_chat.fa_tools import _resolve_mode
        if "FA_TOOLS_MODE" in os.environ:
            self.skipTest("env FA_TOOLS_MODE 已设，跳过 settings 默认值断言")
        self.assertEqual(_resolve_mode(), "http")

    @override_settings(FA_TOOLS_MODE="direct")
    def test_settings_direct_resolves(self):
        import os
        from api.langgraph_chat.fa_tools import _resolve_mode
        if "FA_TOOLS_MODE" in os.environ:
            self.skipTest("env FA_TOOLS_MODE 已设，跳过 settings 断言")
        self.assertEqual(_resolve_mode(), "direct")


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
