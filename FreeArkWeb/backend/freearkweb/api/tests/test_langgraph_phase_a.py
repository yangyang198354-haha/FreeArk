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
            ed = Path(d) / "freeark-expert"
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
            ed = Path(d) / "freeark-expert"
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
            ed = Path(d) / "freeark-expert"
            ed.mkdir()
            with self.assertRaises(FileNotFoundError):
                P._read_prompt_file(ed)

    def test_load_real_repo_prompts_are_langgraph_native(self):
        """对真实仓库 agents/ 装载：三专家均装载成功、注释已剥离、sanheng 拼 KNOWLEDGE.md。

        注：不断言提示里不含 'freeark_tool.py'/'operator_override' 字面——LangGraph 版提示
        常以**否定指令**提及这些（如「不要输出 freeark_tool.py 之类」），属合法内容。"""
        from api.langgraph_chat.prompts import load_expert_prompts, _FALLBACK_PROMPTS
        prompts = load_expert_prompts()
        for name in ("freeark-expert", "inspection-expert", "sanheng-knowledge"):
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
        self.assertEqual(parse_route_response('["freeark-expert"]'), ["freeark-expert"])

    def test_parse_json_fenced(self):
        from api.langgraph_chat.router import parse_route_response
        raw = '```json\n["inspection-expert"]\n```'
        self.assertEqual(parse_route_response(raw), ["inspection-expert"])

    def test_parse_prose_wrapped(self):
        from api.langgraph_chat.router import parse_route_response
        raw = '我认为应当由 ["freeark-expert","sanheng-knowledge"] 处理。'
        self.assertEqual(parse_route_response(raw),
                         ["freeark-expert", "sanheng-knowledge"])

    def test_parse_filters_invalid_names_and_dedupes(self):
        from api.langgraph_chat.router import parse_route_response
        raw = '["foo","freeark-expert","freeark-expert","bar"]'
        self.assertEqual(parse_route_response(raw), ["freeark-expert"])

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
            _StubLLM('["freeark-expert","sanheng-knowledge"]'), "随便问")
        self.assertEqual(set(out), {"freeark-expert", "sanheng-knowledge"})

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
        self.assertEqual(out, ["freeark-expert"])

    def test_classify_none_llm_uses_keyword(self):
        from api.langgraph_chat.router import classify_experts
        out = async_to_sync(classify_experts)(None, "查一下用电量")
        self.assertEqual(out, ["freeark-expert"])

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
        self.assertEqual(out, ["freeark-expert"])

    def test_control_keyword_falls_back_to_energy(self):
        from api.langgraph_chat.router import classify_experts
        # LLM 不可用 → 关键词兜底：控制词（设定）命中 energy
        out = async_to_sync(classify_experts)(_StubLLM("乱码无数组"), "把702的温度设定到24度")
        self.assertEqual(out, ["freeark-expert"])

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
        self.assertEqual(out, ["freeark-expert"])

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
        self.assertEqual(out, ["freeark-expert"])


@tag('unit')
class RouterShortCircuitTargetTests(SimpleTestCase):
    """P0-1：keyword_shortcircuit_target 纯函数——唯一无撞车关键词命中才短路。
    纯关键词逻辑，不依赖 langgraph。"""

    def _t(self, text):
        from api.langgraph_chat.router import keyword_shortcircuit_target
        return keyword_shortcircuit_target(text)

    def test_single_hit_energy(self):
        self.assertEqual(self._t("查一下用电量"), "freeark-expert")

    def test_single_hit_inspection(self):
        self.assertEqual(self._t("现在有哪些设备故障"), "inspection-expert")

    def test_single_hit_sanheng(self):
        self.assertEqual(self._t("三恒的恒氧原理是什么"), "sanheng-knowledge")

    def test_control_keyword_single_hit_energy(self):
        self.assertEqual(self._t("把702的温度设定到24度"), "freeark-expert")

    def test_zero_hit_returns_none(self):
        # 无任何关键词 → 需 LLM 语义判断，不短路
        self.assertIsNone(self._t("看一下设备运行状况"))
        self.assertIsNone(self._t("你好啊"))

    def test_collision_two_hits_returns_none(self):
        # "在线率"含"在线"(inspection) + "能耗"(energy) 撞车 → 不短路，交 LLM
        self.assertIsNone(self._t("当前系统总能耗和在线率是多少"))

    def test_composite_returns_none(self):
        self.assertIsNone(self._t("对比能耗看板与 PLC 故障巡检"))

    def test_uses_current_query_strips_history(self):
        # 历史里全是数据词，当前问题是纯知识 → 只看当前问题 → sanheng 单命中
        text = ("[历史记忆开始]\n用户: 能耗和故障\n助手: ...\n[历史记忆结束]\n"
                "[__freeark_user__:u] 三恒恒湿的原理是什么")
        self.assertEqual(self._t(text), "sanheng-knowledge")


@tag('unit')
class ExpertRegistryTests(SimpleTestCase):
    """P2-2：专家注册表 = 单一真源。golden 值锁定 + 各模块派生常量与注册表一致。"""

    def test_registry_golden_values(self):
        from api.langgraph_chat import experts as E
        self.assertEqual(E.names(),
                         ("freeark-expert", "inspection-expert", "sanheng-knowledge"))
        self.assertEqual(E.default_expert(), "freeark-expert")
        self.assertEqual(E.data_experts(), ("freeark-expert", "inspection-expert"))
        self.assertEqual(E.delegating_experts(),
                         ("freeark-expert", "inspection-expert", "sanheng-knowledge"))
        self.assertEqual(E.cn_map(), {
            "freeark-expert": "系统管家",
            "inspection-expert": "巡检诊断",
            "sanheng-knowledge": "三恒知识",
        })
        self.assertEqual(E.keywords_map()["inspection-expert"],
                         ("故障", "巡检", "plc", "离线", "在线", "传感器", "报警",
                          "诊断", "修复"))
        self.assertEqual(E.keywords_map()["freeark-expert"][:3], ("能耗", "用电", "用量"))
        self.assertIn("系统管家", E.fallback_prompts()["freeark-expert"])
        # 恰好一个默认专家
        self.assertEqual(sum(1 for s in E.EXPERT_SPECS if s.is_default), 1)

    def test_router_and_prompts_derived_from_registry(self):
        from api.langgraph_chat import experts as E
        from api.langgraph_chat import router as R
        from api.langgraph_chat import prompts as P
        self.assertEqual(R.EXPERT_NAMES, E.names())
        self.assertEqual(R.DEFAULT_EXPERT, E.default_expert())
        self.assertEqual(R.ROUTE_KEYWORDS, E.keywords_map())
        self.assertEqual(R.DATA_EXPERTS, E.data_experts())
        self.assertEqual(P._EXPERTS, E.names())
        self.assertEqual(P._FALLBACK_PROMPTS, E.fallback_prompts())

    @unittest.skipUnless(LANGGRAPH_AVAILABLE, "需 langgraph/langchain-core")
    def test_langgraph_consumers_match_registry(self):
        from api.langgraph_chat import experts as E
        import api.langgraph_chat.adapter as ad
        import api.langgraph_chat.orchestrator as orch_mod
        from api.langgraph_chat.fa_tools import TOOLS_BY_EXPERT
        self.assertEqual(ad._EXPERT_CN, E.cn_map())
        self.assertEqual(orch_mod.DELEGATING_EXPERTS, E.delegating_experts())
        # 工具表的专家集合必须与注册表一致（防加专家漏挂工具 / 反之）
        self.assertEqual(set(TOOLS_BY_EXPERT.keys()), set(E.names()))


@tag('unit')
class CapabilityDigestTests(SimpleTestCase):
    """P2-1：build_capability_digest 据工具表派生能力摘要（纯函数，不依赖 langchain）。"""

    class _FakeTool:
        def __init__(self, name, description):
            self.name = name
            self.description = description

    def test_brief_strips_write_prefix_and_takes_first_sentence(self):
        from api.langgraph_chat.router import _tool_brief
        self.assertEqual(_tool_brief("[写操作·需用户确认] 修改三恒设备参数。下发到 PLC。"),
                         "修改三恒设备参数")
        self.assertEqual(_tool_brief("查询某专有部分的日用电量。日期可选。"),
                         "查询某专有部分的日用电量")

    def test_digest_lists_each_expert_tools(self):
        from api.langgraph_chat.router import build_capability_digest
        tbe = {
            "freeark-expert": [self._FakeTool("get_usage_daily", "查询日用电量。")],
            "sanheng-knowledge": [self._FakeTool("search_sanheng_knowledge", "在三恒知识库检索。")],
        }
        d = build_capability_digest(tbe)
        self.assertIn("freeark-expert", d)
        self.assertIn("查询日用电量", d)
        self.assertIn("三恒知识库检索", d)

    def test_digest_empty_inputs(self):
        from api.langgraph_chat.router import build_capability_digest
        self.assertEqual(build_capability_digest({}), "")
        self.assertEqual(build_capability_digest(None), "")

    def test_digest_from_real_tools_distinguishes_experts(self):
        # 真实工具表：能力摘要应体现 energy 有用电量、inspection 有 PLC/故障、sanheng 仅知识检索
        import os
        os.environ.setdefault("FREEARK_POC_MOCK", "1")
        from api.langgraph_chat.fa_tools import TOOLS_BY_EXPERT
        from api.langgraph_chat.router import build_capability_digest
        d = build_capability_digest(TOOLS_BY_EXPERT)
        self.assertIn("用电量", d)        # energy 专属
        self.assertIn("PLC", d)           # inspection 专属
        self.assertIn("知识库", d)         # sanheng 专属
        # sanheng 行不含数据查询工具名（佐证「无数据工具」可被 LLM 推断）
        sanheng_line = [ln for ln in d.splitlines() if ln.startswith("- sanheng-knowledge")][0]
        self.assertNotIn("用电量", sanheng_line)
        self.assertNotIn("PLC", sanheng_line)


@tag('unit')
class ClassifyGuardFlagTests(SimpleTestCase):
    """P2-1：guard 开关——关掉时跳过确定性护栏（供能力提示验证后退役护栏）。"""

    def _c(self, raw, text, guard):
        from api.langgraph_chat.router import classify_experts
        return async_to_sync(classify_experts)(_StubLLM(raw), text, guard=guard)

    def test_guard_on_corrects_misroute(self):
        # 默认 guard=True：数据查询被 LLM 误判 sanheng → 护栏据关键词改派
        self.assertEqual(self._c('["sanheng-knowledge"]', "当前系统有多少故障", True),
                         ["inspection-expert"])

    def test_guard_off_keeps_llm_result(self):
        # guard=False：不纠正，保留 LLM 的（错误）结果 → 验证开关确实绕过护栏
        self.assertEqual(self._c('["sanheng-knowledge"]', "当前系统有多少故障", False),
                         ["sanheng-knowledge"])

    def test_capability_digest_injected_into_system_prompt(self):
        # capability_digest 非空 → 拼入 system 提示（用捕获消息的 stub 验证）
        from api.langgraph_chat.router import classify_experts_llm_ex

        class _CaptureLLM:
            captured = None

            async def ainvoke(self, messages, **kw):
                _CaptureLLM.captured = messages

                class _M:
                    content = '["freeark-expert"]'
                return _M()

        llm = _CaptureLLM()
        async_to_sync(classify_experts_llm_ex)(llm, "查能耗", "【能力】- energy: 用电量")
        sys_msg = _CaptureLLM.captured[0][1]
        self.assertIn("【能力】", sys_msg)


@tag('unit')
class PreviousTurnExpertTests(SimpleTestCase):
    """P0-2：previous_turn_expert 纯函数——从历史块取最后一轮用户问题反推上一轮专家。"""

    def _p(self, text):
        from api.langgraph_chat.router import previous_turn_expert
        return previous_turn_expert(text)

    def _q(self, prev_user, current):
        return (f"[历史记忆开始]\n用户: {prev_user}\n助手: 略\n[历史记忆结束]\n"
                f"[__freeark_user__:u] {current}")

    def test_prev_inspection(self):
        self.assertEqual(self._p(self._q("现在有哪些设备故障", "那严重吗")),
                         "inspection-expert")

    def test_prev_energy(self):
        self.assertEqual(self._p(self._q("今天的总能耗是多少", "那上个月呢")),
                         "freeark-expert")

    def test_prev_sanheng(self):
        self.assertEqual(self._p(self._q("三恒恒氧原理是什么", "再细讲讲")),
                         "sanheng-knowledge")

    def test_takes_last_user_turn(self):
        # 多轮历史：取**最近**一轮用户问题（故障），不取更早的能耗
        text = ("[历史记忆开始]\n用户: 今天能耗多少\n助手: 8647\n"
                "用户: 有哪些设备故障\n助手: 3处\n[历史记忆结束]\n"
                "[__freeark_user__:u] 那严重吗")
        self.assertEqual(self._p(text), "inspection-expert")

    def test_no_history_block_returns_none(self):
        self.assertIsNone(self._p("现在有哪些设备故障"))

    def test_ambiguous_prev_returns_none(self):
        # 上一轮用户问题撞车（能耗+故障）→ 非唯一命中 → None（不强行粘）
        self.assertIsNone(self._p(self._q("对比能耗和故障", "然后呢")))


@tag('unit')
class ClassifyStickyFallbackTests(SimpleTestCase):
    """P0-2：classify_experts 的 sticky_hint 兜底——仅零信号时采用，绝不覆盖关键词/LLM。"""

    def _c(self, llm, text, sticky):
        from api.langgraph_chat.router import classify_experts
        return async_to_sync(classify_experts)(llm, text, sticky_hint=sticky)

    def test_sticky_used_on_zero_signal(self):
        # LLM 空 + 当前无关键词 → 用 sticky（而非 DEFAULT energy）
        out = self._c(_StubLLM("[]"), "那严重吗", "inspection-expert")
        self.assertEqual(out, ["inspection-expert"])

    def test_sticky_ignored_when_keyword_hits(self):
        # 当前问题有关键词(故障)→inspection 胜出，sticky(energy) 不参与
        out = self._c(_StubLLM("乱码"), "现在有设备故障吗", "freeark-expert")
        self.assertEqual(out, ["inspection-expert"])

    def test_sticky_ignored_when_llm_confident(self):
        # LLM 明确返回 inspection → 直接用，sticky(sanheng) 不参与
        out = self._c(_StubLLM('["inspection-expert"]'), "看看设备状况", "sanheng-knowledge")
        self.assertEqual(out, ["inspection-expert"])

    def test_invalid_sticky_falls_to_default(self):
        # sticky 非法/None + 零信号 → DEFAULT energy（与 P0-2 前一致）
        self.assertEqual(self._c(_StubLLM("[]"), "随便聊聊", "not-an-expert"),
                         ["freeark-expert"])
        self.assertEqual(self._c(_StubLLM("[]"), "随便聊聊", None), ["freeark-expert"])


@tag('unit')
class ParseRouteResponseExTests(SimpleTestCase):
    """P1-2：parse_route_response_ex 区分「LLM 明确域外」与「解析失败」。"""

    def _p(self, raw):
        from api.langgraph_chat.router import parse_route_response_ex
        return parse_route_response_ex(raw)

    def test_empty_array_is_ood(self):
        # 字面 [] → 无专家 + saw_empty=True（可信域外信号）
        self.assertEqual(self._p("[]"), (None, True))

    def test_invalid_names_array_is_ood(self):
        # 解析出数组但无合法专家（["foo"]）→ saw_empty=True
        self.assertEqual(self._p('["foo","bar"]'), (None, True))

    def test_no_array_is_not_ood(self):
        # 根本无可解析数组 → saw_empty=False（解析失败，不可当域外）
        self.assertEqual(self._p("我不确定"), (None, False))
        self.assertEqual(self._p(""), (None, False))
        self.assertEqual(self._p(None), (None, False))

    def test_valid_experts_not_ood(self):
        self.assertEqual(self._p('["freeark-expert"]'), (["freeark-expert"], False))

    def test_back_compat_parse_route_response(self):
        # 旧签名仍返回列表/None（域外/失败都 None）
        from api.langgraph_chat.router import parse_route_response
        self.assertIsNone(parse_route_response("[]"))
        self.assertEqual(parse_route_response('["freeark-expert"]'), ["freeark-expert"])


@tag('unit')
class ClassifyOODTests(SimpleTestCase):
    """P1-2：classify_experts 的 allow_ood 域外路径——LLM 明确域外才返回 []。"""

    def _c(self, llm, text, allow_ood, sticky=None):
        from api.langgraph_chat.router import classify_experts
        return async_to_sync(classify_experts)(
            llm, text, sticky_hint=sticky, allow_ood=allow_ood)

    def test_ood_returns_empty_when_enabled(self):
        # LLM 明确 [] + 无关键词 + 无粘性 + allow_ood → []
        self.assertEqual(self._c(_StubLLM("[]"), "你好啊", True), [])

    def test_ood_disabled_falls_to_default(self):
        # allow_ood=False（默认/开关关）→ 仍落 DEFAULT energy（向后兼容）
        self.assertEqual(self._c(_StubLLM("[]"), "你好啊", False), ["freeark-expert"])

    def test_parse_failure_not_treated_as_ood(self):
        # LLM 输出无法解析（非 []）→ 不当域外 → DEFAULT（避免把失败误判闲聊）
        self.assertEqual(self._c(_StubLLM("我不确定"), "你好啊", True), ["freeark-expert"])

    def test_keyword_overrides_ood(self):
        # 当前问题有关键词 → 关键词胜，绝不因 LLM 说 [] 就当域外
        self.assertEqual(self._c(_StubLLM("[]"), "现在有设备故障吗", True),
                         ["inspection-expert"])

    def test_sticky_takes_precedence_over_ood(self):
        # 零信号 + LLM[] 但有上一轮专家 → 优先承接对话（粘性），不当域外。
        # sticky_hint 由 orchestrator 经 previous_turn_expert 计算后传入（此处复刻）。
        from api.langgraph_chat.router import previous_turn_expert
        text = ("[历史记忆开始]\n用户: 现在有哪些设备故障\n助手: 3处\n[历史记忆结束]\n"
                "[__freeark_user__:u] 那然后呢")
        sticky = previous_turn_expert(text)
        self.assertEqual(sticky, "inspection-expert")  # 前置：粘性确实算得出
        self.assertEqual(self._c(_StubLLM("[]"), text, True, sticky=sticky),
                         ["inspection-expert"])


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
        self.assertEqual(route_experts("看一下今天的能耗看板"), ["freeark-expert"])

    def test_router_composite_intent(self):
        from api.langgraph_chat.router import route_experts
        chosen = route_experts("对比能耗看板与 PLC 故障巡检，并解释三恒原理")
        self.assertEqual(set(chosen),
                         {"freeark-expert", "inspection-expert", "sanheng-knowledge"})

    def test_run_single_expert(self):
        result = async_to_sync(self._orch().run)("看一下今天的能耗看板")
        self.assertEqual(result["experts"], ["freeark-expert"])
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
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class OrchestratorShortCircuitTests(SimpleTestCase):
    """P0-1：_route 在唯一关键词命中时短路、跳过 classify_experts（LLM 分类器）。"""

    def _route(self, orch, text):
        from langchain_core.messages import HumanMessage
        return async_to_sync(orch._route)({"messages": [HumanMessage(content=text)]})

    def test_shortcircuit_skips_classifier(self):
        from unittest import mock
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        self.assertTrue(orch.keyword_shortcircuit)  # 默认开
        with mock.patch("api.langgraph_chat.orchestrator.classify_experts",
                        new=mock.AsyncMock(return_value=["sanheng-knowledge"])) as mc:
            out = self._route(orch, "查一下用电量")
        self.assertEqual(out["plan"], [("freeark-expert", "查一下用电量")])
        mc.assert_not_called()   # 短路：未调 LLM 分类器

    def test_disabled_falls_through_to_classifier(self):
        from unittest import mock
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        orch.keyword_shortcircuit = False
        with mock.patch("api.langgraph_chat.orchestrator.classify_experts",
                        new=mock.AsyncMock(return_value=["sanheng-knowledge"])) as mc:
            out = self._route(orch, "查一下用电量")
        # 关掉短路 → 用分类器结果（此处 mock 成 sanheng）而非关键词 energy
        self.assertEqual(out["plan"], [("sanheng-knowledge", "查一下用电量")])
        mc.assert_awaited_once()

    def test_no_shortcircuit_on_composite_calls_classifier(self):
        from unittest import mock
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        with mock.patch("api.langgraph_chat.orchestrator.classify_experts",
                        new=mock.AsyncMock(
                            return_value=["freeark-expert", "inspection-expert"])) as mc:
            out = self._route(orch, "对比能耗和设备故障")
        self.assertEqual({n for n, _ in out["plan"]},
                         {"freeark-expert", "inspection-expert"})
        mc.assert_awaited_once()   # ≥2 命中不短路 → 走分类器

    def test_route_passes_sticky_on_zero_signal_followup(self):
        # 零信号追问（当前无关键词）+ inspection 历史 → _route 经 classify_experts
        # 用粘性落 inspection（而非盲落 DEFAULT energy）。用 fake LLM（返回非 JSON → 兜底）。
        from api.langgraph_chat.orchestrator import Orchestrator
        from langchain_core.messages import HumanMessage
        orch = Orchestrator(latency=0.0)
        self.assertTrue(orch.sticky_routing)  # 默认开
        text = ("[历史记忆开始]\n用户: 现在有哪些设备故障\n助手: 3处\n[历史记忆结束]\n"
                "[__freeark_user__:u] 那严重吗")
        out = async_to_sync(orch._route)({"messages": [HumanMessage(content=text)]})
        self.assertEqual([n for n, _ in out["plan"]], ["inspection-expert"])

    def test_sticky_disabled_falls_to_default(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        from langchain_core.messages import HumanMessage
        orch = Orchestrator(latency=0.0)
        orch.sticky_routing = False
        text = ("[历史记忆开始]\n用户: 现在有哪些设备故障\n助手: 3处\n[历史记忆结束]\n"
                "[__freeark_user__:u] 那严重吗")
        out = async_to_sync(orch._route)({"messages": [HumanMessage(content=text)]})
        # 关掉粘性 → 零信号落 DEFAULT energy
        self.assertEqual([n for n, _ in out["plan"]], ["freeark-expert"])


@tag('unit')
class SemanticRouterPureTests(SimpleTestCase):
    """P1-1：语义路由纯逻辑（score_experts / decide / route_with_vector），离线、stub 向量、无网络。"""

    def _np(self):
        import numpy as np
        return np

    def _mats(self):
        # 3 个专家，每个 1~2 条范例向量（2 维，便于手算余弦）。
        import numpy as np
        def n(v):
            v = np.asarray(v, dtype=np.float32)
            return v / (np.linalg.norm(v) + 1e-9)
        return {
            "freeark-expert": np.array([n([1.0, 0.0])]),
            "inspection-expert": np.array([n([0.0, 1.0])]),
            "sanheng-knowledge": np.array([n([-1.0, 0.0])]),
        }

    def test_score_experts_orders_by_max_cosine(self):
        from api.langgraph_chat.semantic_router import score_experts
        scored = score_experts([1.0, 0.0], self._mats())  # 与 energy 完全同向
        self.assertEqual(scored[0][0], "freeark-expert")
        self.assertAlmostEqual(scored[0][1], 1.0, places=4)

    def test_decide_routes_on_high_conf(self):
        from api.langgraph_chat.semantic_router import decide
        # top 0.9 ≥ τ0.65，margin 0.9-0.2=0.7 ≥ δ0.05 → 命中
        self.assertEqual(decide([("freeark-expert", 0.9), ("x", 0.2)], 0.65, 0.05),
                         "freeark-expert")

    def test_decide_abstains_below_tau(self):
        from api.langgraph_chat.semantic_router import decide
        self.assertIsNone(decide([("freeark-expert", 0.5), ("x", 0.1)], 0.65, 0.05))

    def test_decide_abstains_low_margin(self):
        from api.langgraph_chat.semantic_router import decide
        # 两专家都高分、margin 小（复合/模糊）→ 穿透 LLM
        self.assertIsNone(decide([("a", 0.80), ("b", 0.78)], 0.65, 0.05))

    def test_decide_empty(self):
        from api.langgraph_chat.semantic_router import decide
        self.assertIsNone(decide([], 0.65, 0.05))

    def test_route_with_vector_no_exemplars_returns_none(self):
        from api.langgraph_chat.semantic_router import SemanticRouter
        r = SemanticRouter()
        self.assertIsNone(r.route_with_vector([1.0, 0.0]))  # 未加载范例 → None

    def test_route_with_vector_hits(self):
        from api.langgraph_chat.semantic_router import SemanticRouter
        r = SemanticRouter(tau=0.65, margin=0.05)
        r._exemplars = self._mats()
        r._loaded = True
        self.assertEqual(r.route_with_vector([1.0, 0.05]), "freeark-expert")
        self.assertEqual(r.route_with_vector([0.05, 1.0]), "inspection-expert")

    def test_load_exemplars_excludes_composite_and_ood(self):
        # 范例只取单专家类别；composite/out_of_domain 不入范例
        from api.langgraph_chat.semantic_router import load_exemplar_texts
        groups = load_exemplar_texts()
        self.assertTrue(set(groups).issubset(
            {"freeark-expert", "inspection-expert", "sanheng-knowledge"}))
        # 至少三个专家各有若干范例
        self.assertTrue(all(len(groups.get(e, [])) >= 3 for e in
                            ("freeark-expert", "inspection-expert", "sanheng-knowledge")))

    def test_route_fail_open_on_embed_error(self):
        # embedding 抛错 → route() 返回 None（fail-open，穿透 LLM）
        from unittest import mock
        from api.langgraph_chat.semantic_router import SemanticRouter
        r = SemanticRouter()
        r._exemplars = self._mats()
        r._loaded = True
        with mock.patch("api.rag_service.RagEmbedder") as M:
            M.return_value.embed_query.side_effect = RuntimeError("embed down")
            out = async_to_sync(r.route)("查能耗")
        self.assertIsNone(out)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class OrchestratorSemanticTests(SimpleTestCase):
    """P1-1：_route 集成——语义层在关键词短路后、LLM 前；命中跳过 LLM，未命中穿透。"""

    def _route(self, orch, text):
        from langchain_core.messages import HumanMessage
        return async_to_sync(orch._route)({"messages": [HumanMessage(content=text)]})

    @override_settings(LANGGRAPH_ROUTER_SEMANTIC=False)
    def test_disabled_by_default_no_semantic_router(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        self.assertIsNone(orch._semantic_router)

    @override_settings(LANGGRAPH_ROUTER_SEMANTIC=True)
    def test_semantic_hit_skips_llm(self):
        from unittest import mock
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        self.assertIsNotNone(orch._semantic_router)
        # 语义命中 inspection（无关键词的问题）→ 跳过 LLM 分类器
        orch._semantic_router.route = mock.AsyncMock(return_value="inspection-expert")
        with mock.patch("api.langgraph_chat.orchestrator.classify_experts",
                        new=mock.AsyncMock(return_value=["freeark-expert"])) as mc:
            out = self._route(orch, "设备最近怪怪的")  # 无关键词
        self.assertEqual([n for n, _ in out["plan"]], ["inspection-expert"])
        mc.assert_not_called()

    @override_settings(LANGGRAPH_ROUTER_SEMANTIC=True)
    def test_semantic_miss_falls_through_to_llm(self):
        from unittest import mock
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        orch._semantic_router.route = mock.AsyncMock(return_value=None)  # 语义未命中
        with mock.patch("api.langgraph_chat.orchestrator.classify_experts",
                        new=mock.AsyncMock(return_value=["sanheng-knowledge"])) as mc:
            out = self._route(orch, "设备最近怪怪的")
        self.assertEqual([n for n, _ in out["plan"]], ["sanheng-knowledge"])
        mc.assert_awaited_once()

    @override_settings(LANGGRAPH_ROUTER_SEMANTIC=True)
    def test_keyword_shortcircuit_precedes_semantic(self):
        from unittest import mock
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        # 关键词命中（"用电量"→energy）应在语义层之前，语义 route 不被调用
        orch._semantic_router.route = mock.AsyncMock(return_value="inspection-expert")
        out = self._route(orch, "查一下用电量")
        self.assertEqual([n for n, _ in out["plan"]], ["freeark-expert"])
        orch._semantic_router.route.assert_not_called()

    @override_settings(LANGGRAPH_ROUTER_SEMANTIC=True)
    def test_semantic_skipped_on_composite_keywords(self):
        # Phase-2 灰度教训：复合关键词（能耗+故障）绝不可被语义短路成单专家，必须交 LLM。
        from unittest import mock
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        orch._semantic_router.route = mock.AsyncMock(return_value="inspection-expert")
        with mock.patch("api.langgraph_chat.orchestrator.classify_experts",
                        new=mock.AsyncMock(
                            return_value=["freeark-expert", "inspection-expert"])) as mc:
            out = self._route(orch, "对比能耗和设备故障")  # ≥2 关键词命中=复合
        # 语义被跳过（≥2 关键词），交 LLM 多专家
        orch._semantic_router.route.assert_not_called()
        mc.assert_awaited_once()
        self.assertEqual({n for n, _ in out["plan"]},
                         {"freeark-expert", "inspection-expert"})


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class OrchestratorCapabilityTests(SimpleTestCase):
    """P2-1：orchestrator 据 settings 装配能力摘要 + 护栏开关。"""

    def test_capability_digest_built_and_guard_on_by_default(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        self.assertTrue(orch.guard_enabled)
        self.assertIn("freeark-expert", orch._capability_digest)
        self.assertIn("用电量", orch._capability_digest)

    @override_settings(LANGGRAPH_ROUTER_CAPABILITY_PROMPT=False)
    def test_capability_prompt_can_be_disabled(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        self.assertEqual(orch._capability_digest, "")

    @override_settings(LANGGRAPH_ROUTER_GUARD=False)
    def test_guard_can_be_disabled(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        self.assertFalse(orch.guard_enabled)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class OrchestratorOODTests(SimpleTestCase):
    """P1-2：域外问题路由到 general 通用应答节点（空 plan）。"""

    def _orch_ood(self):
        # fake 路由器返回非 JSON，故用 StubLLM("[]") 模拟 LLM 明确域外信号。
        from api.langgraph_chat.orchestrator import Orchestrator
        orch = Orchestrator(latency=0.0)
        orch.router_llm = _StubLLM("[]")
        return orch

    def test_route_empty_plan_on_ood(self):
        from langchain_core.messages import HumanMessage
        orch = self._orch_ood()
        self.assertTrue(orch.ood_path)
        out = async_to_sync(orch._route)({"messages": [HumanMessage(content="你好啊")]})
        self.assertEqual(out["plan"], [])              # 空 plan = 域外
        self.assertEqual(out["route_text"], "你好啊")    # 暂存全文供 general

    def test_fan_out_routes_empty_plan_to_general(self):
        orch = self._orch_ood()
        sends = orch._fan_out({"plan": [], "route_text": "你好啊"})
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0].node, "general")
        self.assertEqual(sends[0].arg["query"], "你好啊")

    def test_fan_out_disabled_ood_falls_to_expert(self):
        # plan 非空（域外关闭时落 DEFAULT energy）→ 正常走 expert
        orch = self._orch_ood()
        sends = orch._fan_out({"plan": [("freeark-expert", "你好啊")], "route_text": "你好啊"})
        self.assertEqual([s.node for s in sends], ["expert"])

    def test_general_node_produces_answer(self):
        orch = self._orch_ood()
        out = async_to_sync(orch._general)({"query": "你好啊"})
        r = out["expert_results"][0]
        self.assertEqual(r["expert"], "__general__")
        self.assertTrue(r["answer"])
        self.assertNotIn("pending_write", r)   # 通用应答无写，不触发 gate

    def test_run_end_to_end_ood(self):
        # 端到端：你好 → route 空 plan → general → aggregate → 返回通用答复
        orch = self._orch_ood()
        res = async_to_sync(orch.run)("你好啊", thread_id="ood-e2e")
        self.assertEqual(res["experts"], ["__general__"])
        self.assertTrue(res["answer"])

    def test_run_keyword_question_unaffected(self):
        # 有关键词的正常问题不受 OOD 影响（仍走专家）
        orch = self._orch_ood()
        res = async_to_sync(orch.run)("查一下今天的能耗看板", thread_id="ood-kw")
        self.assertEqual(res["experts"], ["freeark-expert"])


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
@tag('unit')
class ClassifyStreamFailureTests(SimpleTestCase):
    """adapter._classify_stream_failure：底层异常 → 分类降级异常 / None(代码 bug)。

    动机见 RCA：原 `except Exception` 把代码 bug 也伪装成"暂时离线"误导排查。
    """

    def _classify(self, exc):
        from api.langgraph_chat.adapter import _classify_stream_failure
        return _classify_stream_failure(exc, "sess1234")

    def test_code_bug_returns_none_for_reraise(self):
        # 代码级 bug 不应伪装成"离线"：返回 None → 调用方原样 re-raise → INTERNAL_ERROR
        for exc in (AttributeError("no attr"), TypeError("bad"), ImportError("m"),
                    KeyError("k"), NameError("n"), IndexError("i"), AssertionError()):
            self.assertIsNone(self._classify(exc),
                              f"{type(exc).__name__} 应判为代码 bug(None)")

    def test_context_length_exceeded(self):
        from api.chat_exceptions import OpenClawUnavailableError
        out = self._classify(RuntimeError("maximum context length is 65536 tokens"))
        self.assertIsInstance(out, OpenClawUnavailableError)
        self.assertEqual(out.code, "CONTEXT_LENGTH_EXCEEDED")
        self.assertIn("过长", out.user_message)

    def test_rate_limited(self):
        out = self._classify(RuntimeError("429 Too Many Requests: rate limit reached"))
        self.assertEqual(out.code, "RATE_LIMITED")
        self.assertTrue(out.user_message)

    def test_auth_config_error(self):
        out = self._classify(RuntimeError("Error code: 401 - invalid api key"))
        self.assertEqual(out.code, "LLM_CONFIG_ERROR")
        self.assertTrue(out.user_message)

    def test_generic_falls_back_to_offline(self):
        # 未识别错误 → 默认"离线"：code 兼容旧值、user_message=None(consumers 用默认文案)
        out = self._classify(RuntimeError("boom"))
        self.assertEqual(out.code, "OPENCLAW_UNAVAILABLE")
        self.assertIsNone(out.user_message)

    def test_5xx_not_misclassified_as_auth(self):
        # 5xx 不含鉴权/超限关键词 → 走默认离线，不应误命中 4xx 分支
        out = self._classify(RuntimeError("Error code: 500 - internal server error"))
        self.assertEqual(out.code, "OPENCLAW_UNAVAILABLE")
        self.assertIsNone(out.user_message)


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

    def test_stream_injects_reasoning_through_real_loop(self):
        """覆盖生产钩子：_stream 真实循环（langchain 0.2.x 经此路径，非实例转换方法）
        应把 delta.reasoning_content 注入 additional_kwargs。"""
        from unittest.mock import MagicMock
        from langchain_core.messages import HumanMessage
        llm = self._make_llm()
        chunks = [
            {"choices": [{"delta": {"content": "", "reasoning_content": "想A"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "答案"}, "finish_reason": None}]},
        ]

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __iter__(self):
                return iter(chunks)

        mock_client = MagicMock()
        mock_client.create.return_value = _Resp()
        llm.client = mock_client

        gens = list(llm._stream([HumanMessage(content="hi")]))
        rc = [g.message.additional_kwargs.get("reasoning_content") for g in gens]
        self.assertIn("想A", rc)
        self.assertEqual("".join(g.message.content for g in gens), "答案")

    def test_astream_injects_reasoning_through_real_loop(self):
        """覆盖生产钩子：_astream（langgraph 实际走异步流）同样注入 reasoning_content。"""
        from unittest.mock import MagicMock
        from langchain_core.messages import HumanMessage
        llm = self._make_llm()
        chunks = [
            {"choices": [{"delta": {"content": "", "reasoning_content": "想B"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "好"}, "finish_reason": None}]},
        ]

        class _AResp:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def __aiter__(self):
                async def _g():
                    for c in chunks:
                        yield c
                return _g()

        async def _create(**kwargs):
            return _AResp()

        mock_async = MagicMock()
        mock_async.create = _create
        llm.async_client = mock_async

        async def _collect():
            out = []
            async for g in llm._astream([HumanMessage(content="hi")]):
                out.append(g)
            return out

        gens = async_to_sync(_collect)()
        rc = [g.message.additional_kwargs.get("reasoning_content") for g in gens]
        self.assertIn("想B", rc)
        self.assertEqual("".join(g.message.content for g in gens), "好")

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
            ("updates", {"route": {"plan": [("freeark-expert", "q")]}}),
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
        self.assertTrue(any("系统管家" in t for k, t in out if k == "reasoning"))
