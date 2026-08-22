"""
单元测试 —— 副官人格身份一致性（修复 2026-08-21）

背景缺陷：小程序聊天入口通篇以「智能方舟的副官」自称（ChatInputBar placeholder、
chat/index.vue personaGreeting、consumers.py 落库问候语），但 AI 回答时有时自称
「方舟智能体」——同一句「你是谁」，答案在两个身份间来回跳。

根因：v1.12.0 的人格注入只做了 `_expert` 分支，而
  - `_general`（P1-2 域外/闲聊节点）：拿到了 state["persona"] 却从不消费，且
    GENERAL_PROMPT 里写死「你就是方舟智能体本人」——"你是谁"恰恰最容易被路由判为
    域外落到这里；
  - `_aggregate`（多专家融合）：融合提示同样写死旧身份且不注入 persona，把各专家已按
    副官人格给出的回答又改回旧称。
路由到哪个分支不确定（router.py 兜底顺序 关键词→粘性→域外[]→DEFAULT_EXPERT），
所以表现为「有时」不一致。

本套件锁死三条链路都必须注入人格块，且喂给模型的系统提示不得再写死旧身份。

全离线：FREEARK_POC_MOCK=1 + LANGGRAPH_USE_FAKE_LLM=True，不连真 DeepSeek。

运行命令：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_persona_identity_consistency \
      --settings=freearkweb.test_settings --verbosity=2
"""

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("FREEARK_POC_MOCK", "1")

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings, tag

try:
    import langgraph  # noqa: F401
    import langchain_core  # noqa: F401
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False


# 旧身份字样：任何喂给模型的系统提示里都不允许再出现（身份只由人格块决定）。
_LEGACY_IDENTITY = "方舟智能体"

_CUSTOM_PERSONA = {"greeting_style": "方舟管家", "tone_style": "先生"}


@contextmanager
def _capture_llm_calls():
    """类级 patch LatencyFakeChat._agenerate，录下每次调用的 messages 列表。

    必须打在类上而非实例上：`_expert` 用 `self.llm.bind_tools(...)` 拿到的是
    model_copy 出来的**新实例**，只 patch orch.llm 实例会漏掉专家分支。
    """
    from api.langgraph_chat.fake_llm import LatencyFakeChat
    calls = []
    original = LatencyFakeChat._agenerate

    async def recording(self, messages, stop=None, run_manager=None, **kwargs):
        calls.append(list(messages))
        return await original(self, messages, stop=stop,
                              run_manager=run_manager, **kwargs)

    LatencyFakeChat._agenerate = recording
    try:
        yield calls
    finally:
        LatencyFakeChat._agenerate = original


def _system_texts(messages):
    from langchain_core.messages import SystemMessage
    return [m.content for m in messages if isinstance(m, SystemMessage)]


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class GeneralNodePersonaTests(SimpleTestCase):
    """修复 1+2：域外/闲聊节点必须注入人格，GENERAL_PROMPT 不得写死旧身份。"""

    def _orch(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        return Orchestrator(latency=0.0)

    def test_general_prompt_no_longer_hardcodes_legacy_identity(self):
        """GENERAL_PROMPT 正文不得再自称「方舟智能体」，并须把身份让渡给人格设定。"""
        from api.langgraph_chat.orchestrator import GENERAL_PROMPT
        self.assertNotIn(_LEGACY_IDENTITY, GENERAL_PROMPT)
        self.assertIn("人格", GENERAL_PROMPT)

    def test_general_injects_default_persona_when_persona_absent(self):
        """persona 缺省（None）→ 仍注入默认副官人格块，而非退回旧身份。"""
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._general)({"query": "你是谁"})
        self.assertEqual(len(calls), 1)
        sys_texts = _system_texts(calls[0])
        joined = "\n".join(sys_texts)
        self.assertIn("智能方舟的副官", joined)
        self.assertIn("尊敬的舰长大人", joined)
        self.assertNotIn(_LEGACY_IDENTITY, joined)

    def test_general_injects_custom_persona(self):
        """用户自定义人格 → general 分支按自定义身份注入，不写死副官。"""
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._general)(
                {"query": "你是谁", "persona": _CUSTOM_PERSONA})
        joined = "\n".join(_system_texts(calls[0]))
        self.assertIn("方舟管家", joined)
        self.assertIn("先生", joined)
        self.assertNotIn("智能方舟的副官", joined)
        self.assertNotIn(_LEGACY_IDENTITY, joined)

    def test_persona_block_follows_general_prompt(self):
        """人格块须排在 GENERAL_PROMPT 之后——靠后的系统消息对身份判定更有权重。"""
        from api.langgraph_chat.orchestrator import GENERAL_PROMPT
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._general)({"query": "你好啊"})
        sys_texts = _system_texts(calls[0])
        self.assertEqual(len(sys_texts), 2)
        self.assertTrue(sys_texts[0].startswith(GENERAL_PROMPT[:20]))
        self.assertIn("智能方舟的副官", sys_texts[1])

    def test_general_still_returns_general_result(self):
        """回归守卫：人格注入不得改变 general 节点的产出契约。"""
        orch = self._orch()
        out = async_to_sync(orch._general)({"query": "你好啊"})
        r = out["expert_results"][0]
        self.assertEqual(r["expert"], "__general__")
        self.assertTrue(r["answer"])
        self.assertNotIn("pending_write", r)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class AggregatePersonaTests(SimpleTestCase):
    """修复 3：多专家融合必须注入人格，融合提示不得写死旧身份。"""

    _RESULTS = [
        {"expert": "freeark-expert", "answer": "今日用电 120kWh，系统正常。"},
        {"expert": "inspection-expert", "answer": "巡检发现 2 台设备异常。"},
    ]

    def _orch(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        return Orchestrator(latency=0.0)

    def test_aggregate_fusion_prompt_has_no_legacy_identity(self):
        """融合调用喂给模型的系统提示里不得出现「方舟智能体」。"""
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._aggregate)({"expert_results": self._RESULTS})
        self.assertEqual(len(calls), 1)
        joined = "\n".join(_system_texts(calls[0]))
        self.assertNotIn(_LEGACY_IDENTITY, joined)

    def test_aggregate_injects_default_persona(self):
        """persona 缺省 → 融合阶段仍以副官身份统一作答。"""
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._aggregate)({"expert_results": self._RESULTS})
        joined = "\n".join(_system_texts(calls[0]))
        self.assertIn("智能方舟的副官", joined)

    def test_aggregate_injects_custom_persona(self):
        """自定义人格经主图 state 传到融合节点（persona 由 adapter 注入初始 State）。"""
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._aggregate)(
                {"expert_results": self._RESULTS, "persona": _CUSTOM_PERSONA})
        joined = "\n".join(_system_texts(calls[0]))
        self.assertIn("方舟管家", joined)
        self.assertNotIn("智能方舟的副官", joined)

    def test_aggregate_still_forbids_routing_terms(self):
        """回归守卫：改身份措辞不得把「禁止暴露内部分工」的约束一起删掉。"""
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._aggregate)({"expert_results": self._RESULTS})
        joined = "\n".join(_system_texts(calls[0]))
        self.assertIn("严格禁止", joined)
        self.assertIn("转交", joined)

    def test_aggregate_single_result_makes_no_llm_call(self):
        """回归守卫：单专家仍直通透传，人格注入不得凭空多一次 LLM 调用。"""
        orch = self._orch()
        answer = "今日能耗 120kWh，系统正常。"
        with _capture_llm_calls() as calls:
            out = async_to_sync(orch._aggregate)(
                {"expert_results": [{"expert": "freeark-expert", "answer": answer}]})
        self.assertEqual(calls, [])
        self.assertEqual(out["messages"][-1].content, answer)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class ExpertPersonaUnchangedTests(SimpleTestCase):
    """守卫本来就正确的 expert 分支：修复不得回退它。"""

    def _orch(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        return Orchestrator(latency=0.0)

    def test_expert_injects_persona(self):
        orch = self._orch()
        with _capture_llm_calls() as calls:
            async_to_sync(orch._expert)({
                "name": "freeark-expert", "query": "你是谁",
                "messages": [], "persona": _CUSTOM_PERSONA,
            })
        joined = "\n".join(_system_texts(calls[0]))
        self.assertIn("方舟管家", joined)


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('integration')
class IdentityConsistencyAcrossBranchesTests(SimpleTestCase):
    """跨分支一致性：同一句「你是谁」，无论落 general 还是 expert，身份必须同一个。

    这正是缺陷的用户可见形态——路由兜底顺序（关键词→粘性→域外[]→DEFAULT_EXPERT）
    决定落哪条分支，而分支之间身份不能再有分歧。
    """

    def _orch(self):
        from api.langgraph_chat.orchestrator import Orchestrator
        return Orchestrator(latency=0.0)

    def test_same_question_same_identity_on_both_branches(self):
        orch = self._orch()
        state = {"query": "你是谁", "persona": _CUSTOM_PERSONA}

        with _capture_llm_calls() as calls_general:
            async_to_sync(orch._general)(dict(state))
        general_sys = "\n".join(_system_texts(calls_general[0]))

        with _capture_llm_calls() as calls_expert:
            async_to_sync(orch._expert)(
                dict(state, name="freeark-expert", messages=[]))
        expert_sys = "\n".join(_system_texts(calls_expert[0]))

        for label, text in (("general", general_sys), ("expert", expert_sys)):
            with self.subTest(branch=label):
                self.assertIn("方舟管家", text)
                self.assertNotIn(_LEGACY_IDENTITY, text)
