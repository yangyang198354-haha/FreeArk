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

import json
import os
import unittest

# 必须在 import 工具桥接层之前置 mock 标志（fa_tools 在 import 期读取它）。
os.environ.setdefault("FREEARK_POC_MOCK", "1")

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings, tag

# 检测 langgraph 依赖是否可用（阶段 A：默认 openclaw 部署可能未装）。
try:
    import langgraph  # noqa: F401
    import langchain_core  # noqa: F401
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False


@tag('unit')
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


@tag('unit')
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
        # LLM 命中 inspection，文本无矛盾的数据关键词 → 以 LLM 为准（护栏不介入）
        out = async_to_sync(classify_experts)(
            _StubLLM('["inspection-expert"]'), "看一下设备运行状况")
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

    # ── 护栏：数据查询误漏到无工具 sanheng 时按关键词改派（2026-06-14 生产问题）──
    def test_guard_overrides_sanheng_only_on_data_query(self):
        from api.langgraph_chat.router import classify_experts
        # LLM 误判数据查询为纯知识 → 护栏据当前问题关键词改派巡检
        out = async_to_sync(classify_experts)(
            _StubLLM('["sanheng-knowledge"]'), "当前系统有多少故障，影响多少户")
        self.assertEqual(out, ["inspection-expert"])

    def test_guard_keeps_sanheng_for_pure_knowledge(self):
        from api.langgraph_chat.router import classify_experts
        # 纯原理问题无数据关键词 → 护栏不触发，保留 sanheng（不过度改派）
        out = async_to_sync(classify_experts)(
            _StubLLM('["sanheng-knowledge"]'), "三恒系统恒温恒湿恒氧的工作原理是什么")
        self.assertEqual(out, ["sanheng-knowledge"])

    def test_guard_ignores_data_keywords_in_history_prefix(self):
        from api.langgraph_chat.router import classify_experts
        # 当前问题是纯知识；历史前缀里有"能耗/用电量"等数据词 → 护栏只看当前问题，不改派
        text = ("[历史记忆开始]\n用户: 看一下能耗看板和用电量\n助手: 今日能耗 8647\n"
                "[历史记忆结束]\n[__freeark_user__:u] 那三恒的恒氧原理是什么")
        out = async_to_sync(classify_experts)(_StubLLM('["sanheng-knowledge"]'), text)
        self.assertEqual(out, ["sanheng-knowledge"])

    def test_guard_overrides_with_history_when_current_is_data(self):
        from api.langgraph_chat.router import classify_experts
        # 当前问题是数据查询（带 __freeark_user__ 标签 + 历史）→ 护栏剥历史后命中巡检并改派
        text = ("[历史记忆开始]\n用户: 三恒原理\n助手: ...\n[历史记忆结束]\n"
                "[__freeark_user__:u] 现在有多少设备故障")
        out = async_to_sync(classify_experts)(_StubLLM('["sanheng-knowledge"]'), text)
        self.assertEqual(out, ["inspection-expert"])

    def test_guard_no_fire_when_data_expert_already_present(self):
        from api.langgraph_chat.router import classify_experts
        # LLM 已含数据专家（非 sanheng-only）→ 护栏不动，保留复合
        out = async_to_sync(classify_experts)(
            _StubLLM('["sanheng-knowledge","inspection-expert"]'), "有多少故障")
        self.assertEqual(set(out), {"sanheng-knowledge", "inspection-expert"})

    # ── 控制类关键词（2026-06-14）：写/控制请求漏到无工具 sanheng 时改派 energy ──
    def test_guard_overrides_sanheng_only_on_control_request(self):
        from api.langgraph_chat.router import classify_experts
        # 触发/刷新/采集类控制请求被误判纯知识 → 护栏据控制关键词改派 energy（持写工具）
        out = async_to_sync(classify_experts)(
            _StubLLM('["sanheng-knowledge"]'), "请触发设备3-1-7-702的数据采集刷新")
        self.assertEqual(out, ["energy-expert"])

    def test_control_keyword_falls_back_to_energy(self):
        from api.langgraph_chat.router import classify_experts
        # LLM 不可用 → 关键词兜底：控制词（设定）命中 energy
        out = async_to_sync(classify_experts)(_StubLLM("乱码无数组"), "把702的温度设定到24度")
        self.assertEqual(out, ["energy-expert"])

    def test_guard_excludes_control_concept_from_pure_knowledge(self):
        from api.langgraph_chat.router import classify_experts
        # "控制"刻意未收入关键词：纯知识问题（怎么控制温度的原理）不应被护栏误改派
        out = async_to_sync(classify_experts)(
            _StubLLM('["sanheng-knowledge"]'), "三恒系统是怎么控制温度的原理")
        self.assertEqual(out, ["sanheng-knowledge"])

    # ── 护栏情形2：数据专家串门（能耗查询误落 inspection）+ 路由剥历史（2026-06-14）──
    def test_guard_overrides_wrong_data_expert_on_energy_query(self):
        from api.langgraph_chat.router import classify_experts
        # 能耗查询被误路由到 inspection（无 get_usage_daily）→ 护栏据"能耗"改派 energy
        out = async_to_sync(classify_experts)(
            _StubLLM('["inspection-expert"]'),
            "3栋1单元702号 过去七天的能耗数据具体是多少，列出一个表格看一下")
        self.assertEqual(out, ["energy-expert"])

    def test_guard_keeps_llm_when_keyword_agrees(self):
        from api.langgraph_chat.router import classify_experts
        # 关键词与所选专家一致（故障→inspection）→ 护栏不动
        out = async_to_sync(classify_experts)(
            _StubLLM('["inspection-expert"]'), "有多少设备故障")
        self.assertEqual(out, ["inspection-expert"])

    def test_guard_keeps_llm_when_no_data_keyword(self):
        from api.langgraph_chat.router import classify_experts
        # 当前问题无数据关键词 → 护栏不介入，以 LLM 为准
        out = async_to_sync(classify_experts)(
            _StubLLM('["inspection-expert"]'), "看一下设备运行状况")
        self.assertEqual(out, ["inspection-expert"])

    def test_route_ignores_history_uses_current_query(self):
        from api.langgraph_chat.router import classify_experts
        # 路由只看当前问题：故障-heavy 历史 + 当前能耗查询 → 仍 energy（不被历史带偏）。
        # 用 None llm 走关键词路由直接验证剥历史：整块含"故障/离线"(inspection)，
        # 但 _current_query 只取"用电量"(energy)。
        text = ("[历史记忆开始]\n用户: 有多少故障\n助手: 共70个设备故障\n"
                "用户: PLC离线情况\n助手: 88台离线\n[历史记忆结束]\n"
                "[__freeark_user__:u] 查一下3-1-7-702的用电量")
        out = async_to_sync(classify_experts)(None, text)
        self.assertEqual(out, ["energy-expert"])


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 A 离线测试")
@tag('unit')
class ChatBackendFactoryTests(SimpleTestCase):
    """chat_backend 工厂选择逻辑。"""

    def test_always_selects_langgraph(self):
        """v1.7.0 退役 OpenClaw 后，工厂无论 CHAT_BACKEND 设置均返回 LangGraphAdapter。"""
        from api.chat_backend import get_chat_adapter
        from api.langgraph_chat.adapter import LangGraphAdapter
        self.assertIs(get_chat_adapter(), LangGraphAdapter)

    @override_settings(CHAT_BACKEND="langgraph")
    def test_switch_selects_langgraph(self):
        from api.chat_backend import get_chat_adapter
        from api.langgraph_chat.adapter import LangGraphAdapter
        self.assertIs(get_chat_adapter(), LangGraphAdapter)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 A 离线测试")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
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
@tag('unit')
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


@tag('unit')
class FaDirectConnectionHealthTests(SimpleTestCase):
    """回归（2026-06-14 根因）：DirectClient 在 langchain 工具线程池里跑，线程本地 DB
    连接活在请求生命周期外、不被 close_old_connections 回收 → 闲置后腐烂复用即
    OperationalError(2013) → 生产"服务器连接异常"。修复=get() 开头 close_old_connections
    让 CONN_MAX_AGE 对工具线程生效 + OperationalError 关连接重试一次。全离线、不连 DB。"""

    def test_get_calls_close_old_connections_before_healthy_view(self):
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        from api.langgraph_chat.fa_direct import DirectClient

        func = MagicMock(return_value=SimpleNamespace(status_code=200, data={"ok": True}))
        coc = MagicMock()
        with patch("api.langgraph_chat.fa_direct.close_old_connections", coc), \
                patch("django.urls.resolve",
                      return_value=SimpleNamespace(func=func, args=(), kwargs={})), \
                patch("rest_framework.test.force_authenticate", lambda *a, **k: None), \
                patch("api.langgraph_chat.fa_direct._agent_user", return_value=object()):
            r = DirectClient().get("/api/dashboard/summary/")

        self.assertTrue(r["success"])                 # 健康连接路径成功
        self.assertEqual(r["data"], {"ok": True})
        self.assertEqual(func.call_count, 1)          # 无重试
        self.assertEqual(coc.call_count, 1)           # 仅开头那次连接健康兜底

    def test_get_retries_once_on_operational_error_then_succeeds(self):
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        from django.db import OperationalError
        from api.langgraph_chat.fa_direct import DirectClient

        func = MagicMock(side_effect=[
            OperationalError(2013, "Lost connection to server during query"),
            SimpleNamespace(status_code=200, data={"recovered": True}),
        ])
        coc = MagicMock()
        with patch("api.langgraph_chat.fa_direct.close_old_connections", coc), \
                patch("django.urls.resolve",
                      return_value=SimpleNamespace(func=func, args=(), kwargs={})), \
                patch("rest_framework.test.force_authenticate", lambda *a, **k: None), \
                patch("api.langgraph_chat.fa_direct._agent_user", return_value=object()):
            r = DirectClient().get("/api/dashboard/summary/")

        self.assertTrue(r["success"])                 # 重试后成功
        self.assertEqual(r["data"], {"recovered": True})
        self.assertEqual(func.call_count, 2)          # 失败一次 + 重试一次
        self.assertEqual(coc.call_count, 2)           # 开头一次 + 重试前一次

    def test_get_retry_exhausted_returns_error_envelope(self):
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        from django.db import OperationalError
        from api.langgraph_chat.fa_direct import DirectClient

        func = MagicMock(side_effect=OperationalError(2013, "Lost connection"))
        coc = MagicMock()
        with patch("api.langgraph_chat.fa_direct.close_old_connections", coc), \
                patch("django.urls.resolve",
                      return_value=SimpleNamespace(func=func, args=(), kwargs={})), \
                patch("rest_framework.test.force_authenticate", lambda *a, **k: None), \
                patch("api.langgraph_chat.fa_direct._agent_user", return_value=object()):
            r = DirectClient().get("/api/dashboard/summary/")

        self.assertFalse(r["success"])                # 重试仍失败 → 统一 error 信封
        self.assertEqual(r["http_status"], 500)
        self.assertIn("view error", r["error"])
        self.assertEqual(func.call_count, 2)          # 原调用 + 一次重试
        self.assertEqual(coc.call_count, 2)


@tag('unit')
class UsageDailyParamMappingTests(SimpleTestCase):
    """回归（2026-06-14）：日用量工具的 start_date/end_date 必须映射到 API 端点
    /api/usage/quantity/ 实际过滤字段 start_time/end_time，否则日期过滤静默失效、
    任何区间都只返回该设备最早 N 条（误导模型 punt 到"联系运维"）。"""

    def test_start_date_maps_to_start_time(self):
        from api.langgraph_chat import fa_tools  # noqa: F401 触发 sys.path 注入 skill scripts
        try:
            import tier1_readonly
        except Exception:  # pragma: no cover
            self.skipTest("tier1_readonly 不可导入（skill scripts 目录缺失）")

        captured = {}

        class _Cap:
            def get(self, path, params=None, timeout=5):
                captured["path"] = path
                captured["params"] = dict(params or {})
                return {"success": True, "data": []}

        orig = tier1_readonly._client
        tier1_readonly._client = lambda: _Cap()
        try:
            tier1_readonly.freeark_get_usage_daily({
                "specific_part": "3-1-7-702",
                "start_date": "2026-06-08", "end_date": "2026-06-14"})
        finally:
            tier1_readonly._client = orig

        p = captured["params"]
        self.assertEqual(p.get("start_time"), "2026-06-08")  # 映射到 API 真实字段
        self.assertEqual(p.get("end_time"), "2026-06-14")
        self.assertNotIn("start_date", p)   # 旧错误参数名不应再发给 API
        self.assertNotIn("end_date", p)
        self.assertEqual(p.get("specific_part"), "3-1-7-702")


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@tag('unit')
class DateHintInjectionTests(SimpleTestCase):
    """回归（2026-06-14）：专家上下文须注入当前日期，否则相对时间查询会臆造日期。"""

    def test_date_hint_contains_today_and_guidance(self):
        import datetime
        from api.langgraph_chat.orchestrator import _date_hint
        h = _date_hint()
        self.assertIn(datetime.date.today().strftime("%Y-%m-%d"), h)  # 含今天日期
        self.assertIn("start_date", h)   # 引导模型据此推算日期参数后再调工具


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过阶段 A 离线测试")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
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
            # status：静默期进度提示（2026-06-14 新增 kind，consumers 转 status_update）
            self.assertIn(kind, ("reasoning", "content", "status"))
            self.assertIsInstance(text, str)
        # 至少有一个 content 块，且拼起来非空
        content = "".join(t for k, t in chunks if k == "content")
        self.assertTrue(content)
        # 应至少发一个 reasoning 进度事件（阶段b：编排步骤作为思考过程进折叠框；
        # 消灭静默期无反馈。2026-06-22 起进度由 status 改 reasoning，详见 adapter._drive）
        self.assertTrue(any(k == "reasoning" for k, _ in chunks))

    def test_failure_raises_openclaw_unavailable(self):
        """编排构造/运行失败统一抛 OpenClawUnavailableError（consumers 降级通道）。"""
        from api.chat_exceptions import OpenClawUnavailableError
        import api.langgraph_chat.adapter as ad

        class _Boom:
            @staticmethod
            def _cfg(thread_id):
                return {"configurable": {"thread_id": thread_id}}

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


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class OrchestratorWriteGateTests(SimpleTestCase):
    """阶段 E：Tier-2 写操作 interrupt 确认门 + resume（fake LLM + mock 写工具）。

    fake LLM 见到 'TOOLCALL:<tool>' 即对该工具发起一次 tool_call；写工具被 expert
    延迟、gate interrupt，验证：①触发 confirm_required ②批准→执行 ③拒绝→不执行
    ④operator 由 [__freeark_user__:X] 前缀构造。"""

    def _set_orch(self):
        import api.langgraph_chat.adapter as ad
        from api.langgraph_chat.orchestrator import Orchestrator
        ad._ORCH = Orchestrator(latency=0.0)
        return ad

    def _stream(self, adapter_cls, msg, sess):
        async def _go():
            out = []
            async for k, t in adapter_cls.stream_chat(msg, sess):
                out.append((k, t))
            return out
        return async_to_sync(_go)()

    def _resume(self, adapter_cls, sess, approved):
        async def _go():
            out = []
            async for k, t in adapter_cls.resume_chat(sess, {"approved": approved}):
                out.append((k, t))
            return out
        return async_to_sync(_go)()

    def test_write_triggers_confirm_then_executes_on_approve(self):
        from api.langgraph_chat.adapter import LangGraphAdapter
        self._set_orch()
        chunks = self._stream(LangGraphAdapter,
                              "[__freeark_user__:alice] TOOLCALL:set_device_params", "wsess1")
        confirms = [t for k, t in chunks if k == "confirm"]
        self.assertTrue(confirms, "未触发 Tier-2 写确认门")
        payload = json.loads(confirms[0])
        self.assertEqual(payload["kind"], "confirm_required")
        self.assertEqual(payload["actions"][0]["tool"], "set_device_params")
        # 确认前不应有任何 content（写未执行）
        self.assertFalse([t for k, t in chunks if k == "content"])
        # 批准 → 执行（mock 成功）
        out2 = self._resume(LangGraphAdapter, "wsess1", True)
        content = "".join(t for k, t in out2 if k == "content")
        self.assertIn("已执行", content)

    def test_write_rejected_does_not_execute(self):
        from unittest import mock
        import api.langgraph_chat.orchestrator as orch_mod
        from api.langgraph_chat.adapter import LangGraphAdapter
        self._set_orch()
        with mock.patch.object(orch_mod, "execute_write") as m:
            self._stream(LangGraphAdapter,
                         "[__freeark_user__:bob] TOOLCALL:trigger_refresh", "wsess2")
            out2 = self._resume(LangGraphAdapter, "wsess2", False)
            m.assert_not_called()   # 拒绝路径绝不执行写
        content = "".join(t for k, t in out2 if k == "content")
        self.assertIn("已取消", content)

    def test_approve_executes_with_operator_from_prefix(self):
        from unittest import mock
        import api.langgraph_chat.orchestrator as orch_mod
        from api.langgraph_chat.adapter import LangGraphAdapter
        self._set_orch()
        with mock.patch.object(orch_mod, "execute_write",
                               return_value={"success": True, "summary": "ok"}) as m:
            self._stream(LangGraphAdapter,
                         "[__freeark_user__:alice] TOOLCALL:set_device_params", "wsess3")
            self._resume(LangGraphAdapter, "wsess3", True)
            m.assert_called_once()
            call_args = m.call_args.args
            self.assertEqual(call_args[0], "set_device_params")          # tool
            self.assertEqual(call_args[2], "energy-agent::alice")        # operator 追溯（服务账号改名后）


# ===========================================================================
# 阶段 a —— 模型原生思考（reasoning_content）透传
# ===========================================================================
#
# deepseek-v4-flash 原生 wire 流式吐 delta.reasoning_content（思考过程），但
# langchain_openai 0.3.x ChatOpenAI 默认丢弃。_ReasoningChatOpenAI 子类把它注回
# additional_kwargs，adapter._drive 据此以 ('reasoning', ...) 透传到折叠思考框。
# ===========================================================================


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@tag('unit')
class ReasoningPassthroughTests(SimpleTestCase):
    """阶段a：reasoning_content 子类注入 + _drive 透传协议。"""

    def _make_llm(self):
        from api.langgraph_chat.orchestrator import _get_reasoning_chat_openai_cls
        cls = _get_reasoning_chat_openai_cls()
        return cls(model="deepseek-v4-flash", api_key="sk-test",
                   base_url="https://api.deepseek.com/v1", temperature=0.2)

    def test_subclass_injects_reasoning_content(self):
        """delta.reasoning_content → message.additional_kwargs['reasoning_content']。"""
        from langchain_core.messages import AIMessageChunk
        llm = self._make_llm()
        chunk = {"choices": [{"delta": {"content": "",
                                        "reasoning_content": "思考片段X"},
                              "finish_reason": None}]}
        gen = llm._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, {})
        self.assertIsNotNone(gen)
        self.assertEqual(
            gen.message.additional_kwargs.get("reasoning_content"), "思考片段X")

    def test_subclass_no_reasoning_is_passthrough(self):
        """无 reasoning_content 时不注入，正常 content 不受影响。"""
        from langchain_core.messages import AIMessageChunk
        llm = self._make_llm()
        chunk = {"choices": [{"delta": {"content": "答案"},
                              "finish_reason": None}]}
        gen = llm._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, {})
        self.assertNotIn("reasoning_content", gen.message.additional_kwargs)
        self.assertEqual(gen.message.content, "答案")

    def test_drive_yields_reasoning_before_content(self):
        """_drive：单专家路径下，先 yield ('reasoning', rc) 再 yield ('content', ...)。"""
        from langchain_core.messages import AIMessageChunk
        from api.langgraph_chat.adapter import _drive

        class _FakeGraph:
            def __init__(self, events):
                self._events = events

            async def astream(self, payload, config, stream_mode=None):
                for ev in self._events:
                    yield ev

            async def aget_state(self, config):
                return None

        class _FakeOrch:
            def __init__(self, events):
                self.graph = _FakeGraph(events)

        events = [
            ("updates", {"route": {"plan": [("energy-expert", "q")]}}),
            ("messages", (AIMessageChunk(content="",
                          additional_kwargs={"reasoning_content": "先想一想"}),
                          {"langgraph_node": "expert"})),
            ("messages", (AIMessageChunk(content="",
                          additional_kwargs={"reasoning_content": "再想一想"}),
                          {"langgraph_node": "expert"})),
            ("messages", (AIMessageChunk(content="最终答案"),
                          {"langgraph_node": "expert"})),
        ]

        async def _collect():
            out = []
            async for kt in _drive(_FakeOrch(events), {"messages": []},
                                   {"configurable": {"thread_id": "t"}}):
                out.append(kt)
            return out

        out = async_to_sync(_collect)()
        kinds = [k for k, _ in out]
        # 模型原生思考被透传
        self.assertIn(("reasoning", "先想一想"), out)
        self.assertIn(("reasoning", "再想一想"), out)
        self.assertIn(("content", "最终答案"), out)
        # reasoning 在 content 之前（折叠框先显示思考、答案到达再折叠）
        first_content = kinds.index("content")
        self.assertLess(kinds.index("reasoning"), first_content)
        self.assertLess(
            max(i for i, (k, t) in enumerate(out) if t == "再想一想"),
            first_content,
            "模型 reasoning 应全部早于首个 content")
        # 阶段b 编排步骤也在（两者结合）
        self.assertTrue(any(t.startswith("🔍") for k, t in out if k == "reasoning"))
        self.assertTrue(any("能耗分析" in t for k, t in out if k == "reasoning"))
