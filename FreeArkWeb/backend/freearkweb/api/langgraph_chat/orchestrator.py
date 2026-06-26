"""
api.langgraph_chat.orchestrator —— 编排图：supervisor 路由 + 专家并行 fan-out + 聚合

对应 OpenClaw 现状的逐项替换：

  OpenClaw                              LangGraph 本图
  ─────────────────────────────────    ─────────────────────────────────
  main agent 方舟龙虾                    route 节点（阶段D LLM 分类器）+ aggregate 节点
  exec `openclaw agent --agent X`       Send(expert, payload)（进程内，无冷启动）
  串行委派 3 专家 ≈ 3×31s               Send fan-out 并行 ≈ max(单专家)
  freeark_tool.py 子进程                 fa_tools.@tool 进程内直调
  gateway WS 跳转                        graph.astream 进程内迭代

并行的本质：route 作为条件边一次返回多个 Send，LangGraph 在同一个 superstep 内
并发执行所有目标节点；各分支把结果写入带 operator.add reducer 的 expert_results，
天然归并。这把「复合意图」从线性累加变成取最大值。

真机实测（树莓派 Pi 5 / deepseek-v4-flash，见 agents/langgraph-poc/README.md §3.1）：
单专家 8.3s（OpenClaw ~31s，≈3.7×）、复合三专家并行 35.6s（OpenClaw ~93s，≈2.6×）。

配置（settings.py）：
  LANGGRAPH_USE_FAKE_LLM  - True 走离线假模型（CI/单测），默认 False
  LANGGRAPH_MODEL         - DeepSeek 模型名，默认 deepseek-v4-flash
  LANGGRAPH_ROUTER_MODEL  - 阶段D 路由分类器模型，空=复用主模型；可设更轻模型控成本
  DEEPSEEK_BASE_URL       - OpenAI 兼容端点，默认 https://api.deepseek.com/v1
  DEEPSEEK_API_KEY        - 密钥（生产 .env 注入，绝不入 git）
  LANGGRAPH_LLM_TIMEOUT   - 单次调用超时秒，默认 60

阶段D 路由：route 节点经 router.classify_experts() 用 LLM 分类器选专家，失败/空命中
回退关键词路由、再回退 energy-expert（三级兜底，见 router.py）。fake 模式下分类器返回
非 JSON → 自动回退关键词路由，故离线单测路由仍确定。

文档引用：PHASE3_ROLLOUT.md 阶段 A/C/D, detailed_design.md §1.2/§1.3,
          [[openclaw-multiagent-capabilities]]
"""

from __future__ import annotations

import asyncio
import datetime
import operator
import re
from typing import Annotated, List, Optional, Tuple, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage)
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from .adapter import INTERNAL_NOSTREAM_TAG
from .fa_tools import (TOOLS_BY_EXPERT, WRITE_TOOL_NAMES, execute_write,
                       get_last_search_images, prepare_search_images_sink)
from .prompts import EXPERT_PROMPTS
from .router import classify_experts


# ── 阶段 G：跨 agent 子委托（expert→expert）─────────────────────────────
# 巡检专家在推理中可调用以下「委托工具」请求同侪能力。它们不直接执行，而是被
# _expert 循环按名拦截，路由到目标专家（深度限 1：被委托方不再带委托工具，杜绝
# 递归）：knowledge/read 内联跑只读子专家、结果回灌发起方继续推理；write 转为
# pending_write 走**现有 _gate interrupt 确认门**（复用，不另起确认路径）。
# 对应 inspection-expert SYSTEM_PROMPT 的 delegations 契约。
DELEGATING_EXPERTS = ("inspection-expert",)
MAX_EXPERT_STEPS = 8  # 单专家 ReAct + 委托链步数上限（防失控循环）


@tool
def delegate_knowledge(question: str = "") -> dict:
    """向三恒知识库专家请求原理/机理/概念分析（只读知识，无副作用）。
    question: 需要分析的问题或巡检情况描述。"""
    return {"_delegation": "knowledge_query"}  # 占位：实际执行由 orchestrator 拦截


@tool
def delegate_read(query: str = "", specific_part: str = "") -> dict:
    """向能耗专家请求只读数据（设备实时参数/配置/历史能耗）。
    query: 取数需求；specific_part: 设备号如 '3-1-7-702'（可选）。"""
    return {"_delegation": "read_query"}  # 占位：实际执行由 orchestrator 拦截


@tool
def delegate_write(specific_part: str = "", items: Optional[list] = None,
                   trigger_refresh_only: bool = False) -> dict:
    """[写处置·需用户确认] 巡检判断需自行处置时，委托执行设备写操作（经能耗专家写工具）。
    specific_part 形如 '3-1-7-702'；items 形如 [{"param_name":"设定温度","new_value":"24"}]；
    仅触发按需采集刷新则 trigger_refresh_only=true。写操作必经用户确认门，绝不自动执行。"""
    return {"_delegation": "write_command"}  # 占位：转 pending_write 交 _gate 确认


DELEGATION_TOOLS = [delegate_knowledge, delegate_read, delegate_write]
DELEGATION_TOOL_NAMES = {t.name for t in DELEGATION_TOOLS}
READ_DELEGATION_NAMES = {"delegate_knowledge", "delegate_read"}


class State(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: List[Tuple[str, str]]
    # expert_results 项两种形态（append-only reducer）：
    #   {"expert": name, "answer": str}                         普通答复（aggregate 取用）
    #   {"expert": name, "pending_write": {"tool","args"}}      待确认写（gate 处理，aggregate 忽略）
    expert_results: Annotated[List[dict], operator.add]
    # 仅在 Send 分支负载里出现：
    name: str
    query: str
    # ── v1.4.1 新增（IFC-141-501，MOD-141-05）────────────────────────────
    related_images: List[dict]
    # 不使用 operator.add reducer：由 _aggregate 统一收集后一次性赋值
    # 格式：[{"image_id": int, "source": str}, ...]（已去重）
    # ── v1.5.0 新增（MOD-MQ-06）：VLM 图片分析描述文字，仅作调试/观测用
    # adapter 层在 graph.astream 启动前注入；各节点可忽略（Optional[str]）
    vision_description: Optional[str]
    # ── v1.8.0 新增（MOD-180-07）：用户数据访问范围上下文
    # MiniAppChatConsumer 经 adapter 注入；None=无限制（admin/operator 路径直通）
    user_scope: Optional[object]  # UserScope instance or None


# 从消息里提取 ChatConsumer 注入的 [__freeark_user__:<name>] 前缀，构造 operator 追溯。
_CHATUSER_RE = re.compile(r"\[__freeark_user__:([^\]]*)\]")


def _operator_from_state(state: State) -> str:
    text = ""
    for m in state.get("messages", []):
        if isinstance(m, HumanMessage):
            text = (m.content or "")
            break
    mt = _CHATUSER_RE.search(text)
    user = (mt.group(1).strip() if mt else "") or "unknown"
    return f"energy-agent::{user}"


def _preview_write(tool: str, args: dict) -> str:
    """生成面向用户的写操作影响预览（禁止杜撰，仅据参数）。"""
    args = args or {}
    if tool == "set_device_params":
        sp = args.get("specific_part", "?")
        items = args.get("items") or []
        parts = "、".join(
            f"{i.get('param_name', '?')} → {i.get('new_value', '?')}"
            for i in items) or "(无参数项)"
        return f"将修改设备 {sp} 的参数：{parts}（下发至 PLC，设备响应约 10–30 秒）"
    if tool == "trigger_refresh":
        return f"将触发设备 {args.get('specific_part', '?')} 的按需数据采集刷新"
    return f"{tool}({args})"


_WEEKDAY_CN = "一二三四五六日"


def _date_hint() -> str:
    """每请求注入当前系统日期（修复 2026-06-14）：专家模型本身不知道"今天"，对"近 N 天/
    本周/上月/今天"等相对时间会臆造日期（实测把"过去七天"猜成一年前）。在专家 system
    提示尾部附上当前日期，令其据此推算 start_date/end_date 等参数后再调工具。"""
    today = datetime.date.today()
    return (f"\n\n[当前系统日期：{today:%Y-%m-%d}（星期{_WEEKDAY_CN[today.weekday()]}）。"
            f"涉及「近N天/本周/上月/今天」等相对时间时，请据此推算具体的 start_date/end_date "
            f"等日期参数后再调用工具，不要臆造日期。]")


_REASONING_LLM_CLS = None  # 惰性构造并缓存的 ChatOpenAI 子类（阶段a）


def _delta_get(delta, key):
    """从流式 delta（dict 或 pydantic 对象）安全取字段。"""
    if delta is None:
        return None
    if isinstance(delta, dict):
        return delta.get(key)
    return getattr(delta, key, None)


def _get_reasoning_chat_openai_cls():
    """惰性构造透传 reasoning_content 的 ChatOpenAI 子类（阶段a）。

    deepseek-v4-flash 原生 wire 逐 token 流式输出 delta.reasoning_content（思考过程），
    但 langchain_openai 0.3.x 的 ChatOpenAI 默认丢弃它（不进 additional_kwargs、也不进
    response_metadata，思考期 chunk.content 为空）。本子类在 chunk 转换钩子里把
    reasoning_content 注回 message.additional_kwargs，供 adapter._drive 以
    ('reasoning', ...) 透传到前端折叠思考框。reasoning 提取异常绝不影响正常 content 流。"""
    global _REASONING_LLM_CLS
    if _REASONING_LLM_CLS is None:
        from langchain_openai import ChatOpenAI  # 延迟 import，假模型路径不需要

        # langchain_openai 0.2.x 起 _convert_chunk_to_generation_chunk 从 ChatOpenAI 的
        # 实例方法改成了 chat_models.base 的模块级函数，ChatOpenAI 上已无此方法——
        # 旧 super()._convert_chunk_to_generation_chunk(...) 会抛 AttributeError。
        # 改为委托模块级函数再注入 reasoning_content，使本钩子在被直接调用时行为正确。
        from langchain_openai.chat_models import base as _oai_base

        def _inject_reasoning(gen, chunk):
            try:
                if gen is not None:
                    choices = (chunk.get("choices")
                               or chunk.get("chunk", {}).get("choices") or [])
                    if choices:
                        rc = _delta_get(choices[0].get("delta"), "reasoning_content")
                        if rc:
                            gen.message.additional_kwargs["reasoning_content"] = rc
            except Exception:  # noqa: BLE001 防御：reasoning 提取绝不拖垮 content 流
                pass
            return gen

        class _ReasoningChatOpenAI(ChatOpenAI):
            def _convert_chunk_to_generation_chunk(
                    self, chunk, default_chunk_class, base_generation_info):
                gen = _oai_base._convert_chunk_to_generation_chunk(
                    chunk, default_chunk_class, base_generation_info)
                return _inject_reasoning(gen, chunk)

            # 注意（生产透传现状）：langchain_openai 0.2.x 的 ChatOpenAI._stream/_astream
            # 直接调用模块级 _convert_chunk_to_generation_chunk，不经本实例方法。为让生产
            # 流式真正透传 reasoning_content，这里覆盖 _stream/_astream，复用父类全部
            # 取数逻辑（_get_request_payload/client.create），仅把分块转换换成本实例方法。
            def _stream(self, messages, stop=None, run_manager=None, **kwargs):
                kwargs["stream"] = True
                payload = self._get_request_payload(messages, stop=stop, **kwargs)
                # 罕见的 Pydantic response_format 流式分支交回父类（本项目未用此路径；
                # 该分支也不携带 reasoning_content，无需本子类透传）。
                if isinstance(payload.get("response_format"), type):
                    yield from super()._stream(
                        messages, stop=stop, run_manager=run_manager, **kwargs)
                    return
                from langchain_core.messages import AIMessageChunk as _AIChunk
                default_chunk_class = _AIChunk
                base_generation_info = {}
                if self.include_response_headers:
                    raw = self.client.with_raw_response.create(**payload)
                    response = raw.parse()
                    base_generation_info = {"headers": dict(raw.headers)}
                else:
                    response = self.client.create(**payload)
                with response:
                    is_first = True
                    for chunk in response:
                        if not isinstance(chunk, dict):
                            chunk = chunk.model_dump()
                        gen = self._convert_chunk_to_generation_chunk(
                            chunk, default_chunk_class,
                            base_generation_info if is_first else {})
                        if gen is None:
                            continue
                        default_chunk_class = gen.message.__class__
                        logprobs = (gen.generation_info or {}).get("logprobs")
                        if run_manager:
                            run_manager.on_llm_new_token(
                                gen.text, chunk=gen, logprobs=logprobs)
                        is_first = False
                        yield gen

            async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
                kwargs["stream"] = True
                payload = self._get_request_payload(messages, stop=stop, **kwargs)
                if isinstance(payload.get("response_format"), type):
                    async for _c in super()._astream(
                            messages, stop=stop, run_manager=run_manager, **kwargs):
                        yield _c
                    return
                from langchain_core.messages import AIMessageChunk as _AIChunk
                default_chunk_class = _AIChunk
                base_generation_info = {}
                if self.include_response_headers:
                    raw = await self.async_client.with_raw_response.create(**payload)
                    response = raw.parse()
                    base_generation_info = {"headers": dict(raw.headers)}
                else:
                    response = await self.async_client.create(**payload)
                async with response:
                    is_first = True
                    async for chunk in response:
                        if not isinstance(chunk, dict):
                            chunk = chunk.model_dump()
                        gen = self._convert_chunk_to_generation_chunk(
                            chunk, default_chunk_class,
                            base_generation_info if is_first else {})
                        if gen is None:
                            continue
                        default_chunk_class = gen.message.__class__
                        logprobs = (gen.generation_info or {}).get("logprobs")
                        if run_manager:
                            await run_manager.on_llm_new_token(
                                gen.text, chunk=gen, logprobs=logprobs)
                        is_first = False
                        yield gen

        _REASONING_LLM_CLS = _ReasoningChatOpenAI
    return _REASONING_LLM_CLS


def _make_llm(latency: float | None = None):
    """模型工厂：默认连真 DeepSeek（OpenAI 兼容）；
    settings.LANGGRAPH_USE_FAKE_LLM=True 时走离线假模型（CI/单测）。
    阶段a：真模型用 _ReasoningChatOpenAI 子类透传原生 reasoning_content。"""
    from django.conf import settings

    if getattr(settings, "LANGGRAPH_USE_FAKE_LLM", False):
        from .fake_llm import LatencyFakeChat
        return LatencyFakeChat() if latency is None else LatencyFakeChat(latency=latency)

    cls = _get_reasoning_chat_openai_cls()
    return cls(
        model=getattr(settings, "LANGGRAPH_MODEL", "deepseek-v4-flash"),
        base_url=getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key=getattr(settings, "DEEPSEEK_API_KEY", "") or "sk-noop",
        temperature=0.2,
        timeout=getattr(settings, "LANGGRAPH_LLM_TIMEOUT", 60),
        max_retries=1,
    )


def _make_router_llm(main_llm, latency: float | None = None):
    """路由分类器模型——**始终 temperature 0**（分类确定性，消除路由抖动）。

    意图分类是确定性任务；复用主模型的 temperature 0.2 会导致同一问题偶发被路由到
    不同专家（F.1 实测：偶发把三恒原理误路由 energy、把写请求过度分发致确认消息被
    aggregate 融合稀释）。故路由单独用一个 temp 0 的 ChatOpenAI 实例：
      - LANGGRAPH_ROUTER_MODEL 非空 → 用该（更轻）模型（决策2 控成本）；
      - 为空 → 用 LANGGRAPH_MODEL（主模型同名）但 temperature 0。
    fake 模式仍复用 main_llm（fake 忽略 temp；路由会自动回退关键词，离线确定）。"""
    from django.conf import settings

    if getattr(settings, "LANGGRAPH_USE_FAKE_LLM", False):
        return main_llm
    rm = (getattr(settings, "LANGGRAPH_ROUTER_MODEL", "") or "").strip()
    model = rm or getattr(settings, "LANGGRAPH_MODEL", "deepseek-v4-flash")

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model,
        base_url=getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key=getattr(settings, "DEEPSEEK_API_KEY", "") or "sk-noop",
        temperature=0.0,
        timeout=getattr(settings, "LANGGRAPH_LLM_TIMEOUT", 60),
        max_retries=1,
    )


# 编排器：图编译一次、模型一次 → 进程常驻，零 per-request 冷启动
class Orchestrator:
    def __init__(self, latency: float | None = None,
                 delegating_experts: tuple[str, ...] = DELEGATING_EXPERTS):
        self.llm = _make_llm(latency)
        self.router_llm = _make_router_llm(self.llm, latency)
        self.delegating_experts = set(delegating_experts)
        self.graph = self._build()

    # ── route：LLM 分类器选专家，复合意图分流为多个并行 Send ──────────
    async def _route(self, state: State):
        text = ""
        for m in reversed(state["messages"]):
            if isinstance(m, HumanMessage):
                text = (m.content or "")
                break
        chosen = await classify_experts(self.router_llm, text)
        plan = [(name, text) for name in chosen]
        return {"plan": plan}

    def _fan_out(self, state: State):
        # 条件边：一次返回多个 Send → LangGraph 并发执行（核心并行点）
        # v1.8.0 新增：透传 user_scope 到每个 expert 子节点 State（MOD-180-07）
        return [Send("expert", {
            "name": name, "query": q, "messages": [],
            "user_scope": state.get("user_scope"),
        }) for name, q in state["plan"]]

    # ── expert：单专家 ReAct（读工具内联；写工具延迟到 gate；委托专家可子委托同侪）──
    async def _expert(self, state: State):
        name = state["name"]
        query = state["query"]
        allow_deleg = name in self.delegating_experts
        base_tools = TOOLS_BY_EXPERT.get(name, [])
        tool_map = {t.name: t for t in base_tools}
        bound = list(base_tools) + (DELEGATION_TOOLS if allow_deleg else [])
        llm = self.llm.bind_tools(bound) if bound else self.llm

        msgs: List[BaseMessage] = [
            SystemMessage(content=EXPERT_PROMPTS.get(name, "") + _date_hint()),
            HumanMessage(content=query),
        ]
        delegations: List[dict] = []
        accumulated_images: list = []   # v1.4.1：收集本 expert 执行期间所有命中的图片（IFC-141-502）
        ai = await llm.ainvoke(msgs)
        steps = 0
        while getattr(ai, "tool_calls", None) and steps < MAX_EXPERT_STEPS:
            steps += 1
            tcs = ai.tool_calls

            # 1) 写优先：专家自身写工具 → pending_write，终止本节点交 gate 确认。
            pending = [tc for tc in tcs if tc["name"] in WRITE_TOOL_NAMES]
            if pending:
                return {"expert_results": [
                    {"expert": name,
                     "pending_write": {"tool": tc["name"], "args": tc.get("args", {})}}
                    for tc in pending]}

            # 2) 写委托：delegate_write → 转为 pending_write（复用 _gate 确认门）。
            if allow_deleg:
                dw = next((tc for tc in tcs if tc["name"] == "delegate_write"), None)
                if dw is not None:
                    return {"expert_results": [{
                        "expert": name,
                        "pending_write": self._write_from_delegation(dw.get("args", {})),
                        "delegations": delegations + [{
                            "target_agent": "energy-expert", "intent": "write_command",
                            "status": "PENDING_CONFIRM"}],
                    }]}

            # 3) 读类工具 + 读/知识委托 → 内联执行，回灌后继续推理。
            msgs.append(ai)
            for tc in tcs:
                if allow_deleg and tc["name"] in READ_DELEGATION_NAMES:
                    out, log = await self._handle_read_delegation(
                        name, tc["name"], tc.get("args", {}), query)
                    delegations.append(log)
                else:
                    t = tool_map.get(tc["name"])
                    # ── v1.4.1：search_sanheng_knowledge 前先放置可变 sink，工具体原地回传图片
                    # （2026-06-23 修正 ContextVar 经 ainvoke copy_context 失效，见 fa_tools 说明）──
                    if tc["name"] == "search_sanheng_knowledge":
                        prepare_search_images_sink()
                    # ── v1.8.0 新增：ScopeEnforcer 工具调用前范围检查（MOD-180-07）──
                    # user_scope=None（admin/operator）时 check_and_enforce 直通，行为不变
                    if t:
                        from .scope_enforcer import check_and_enforce, ScopeViolationError
                        _user_scope = state.get("user_scope")
                        try:
                            _enforced_args, _clarification = check_and_enforce(
                                tc["name"], tc.get("args", {}), _user_scope)
                        except ScopeViolationError as _scope_err:
                            _enforced_args = None
                            _clarification = f"权限拒绝：您无权对该专有部分执行写操作。（{_scope_err}）"
                        if _enforced_args is not None:
                            out = await t.ainvoke(_enforced_args)
                        else:
                            out = {"clarification": _clarification, "scope_blocked": True}
                    else:
                        out = {"error": "no tool"}
                    # ── end v1.8.0 ───────────────────────────────────────────────────────
                    if tc["name"] == "search_sanheng_knowledge":
                        imgs = get_last_search_images()   # 读取并清空 sink（IFC-141-502）
                        accumulated_images.extend(imgs)
                    # ──────────────────────────────────────────────────────────────────────
                msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
            ai = await llm.ainvoke(msgs)

        # v1.4.1：对 accumulated_images 做最终去重（同一专家多轮工具调用可能重复命中）
        seen_ids: set = set()
        deduped_images: list = []
        for img in accumulated_images:
            if img["image_id"] not in seen_ids:
                seen_ids.add(img["image_id"])
                deduped_images.append(img)

        return {"expert_results": [
            {
                "expert": name,
                "answer": ai.content,
                "delegations": delegations,
                "related_images": deduped_images,   # v1.4.1 新增（IFC-141-502）
            }
        ]}

    @staticmethod
    def _write_from_delegation(args: dict) -> dict:
        """把 inspection 的 delegate_write 提案映射为 gate 可执行的 pending_write。
        走能耗专家的写工具（set_device_params / trigger_refresh）+ 既有 execute_write 审计。"""
        args = args or {}
        sp = args.get("specific_part", "") or ""
        if args.get("trigger_refresh_only"):
            return {"tool": "trigger_refresh", "args": {"specific_part": sp}}
        return {"tool": "set_device_params",
                "args": {"specific_part": sp, "items": args.get("items") or []}}

    async def _handle_read_delegation(self, origin: str, tool_name: str,
                                      args: dict, origin_query: str):
        """只读委托：跑目标只读子专家，返回 (回灌结果, 审计日志)。无副作用。"""
        args = args or {}
        if tool_name == "delegate_knowledge":
            q = args.get("question") or (
                f"（{origin} 委托）请就以下情况做三恒原理/机理分析：{origin_query}")
            ans = (await self._run_subexpert("sanheng-knowledge", q)).get("answer", "")
            return ({"status": "OK", "from": "sanheng-knowledge",
                     "intent": "knowledge_query", "data": ans},
                    {"target_agent": "sanheng-knowledge",
                     "intent": "knowledge_query", "status": "OK"})
        # delegate_read
        part = args.get("specific_part") or ""
        q = args.get("query") or origin_query
        if part:
            q = f"{q}（设备 {part}）"
        ans = (await self._run_subexpert("energy-expert", q)).get("answer", "")
        return ({"status": "OK", "from": "energy-expert",
                 "intent": "read_query", "data": ans},
                {"target_agent": "energy-expert",
                 "intent": "read_query", "status": "OK"})

    async def _run_subexpert(self, name: str, query: str) -> dict:
        """跑被委托的只读子专家：过滤写工具、不带委托工具（深度限 1）→ 返回 {"answer": ...}。

        子专家的所有 LLM 生成均打 INTERNAL_NOSTREAM_TAG：它是委托的**内部产物**，只回灌给
        发起方继续推理，绝不直接流给用户——否则委托型专家会把「子专家完整答案 + 自身整合
        终稿」两份近似内容一并流出（2026-06-22 修复）。adapter._drive 据该 tag 跳过这些生成。"""
        tools = [t for t in TOOLS_BY_EXPERT.get(name, [])
                 if t.name not in WRITE_TOOL_NAMES]
        tool_map = {t.name: t for t in tools}
        llm = self.llm.bind_tools(tools) if tools else self.llm
        msgs: List[BaseMessage] = [
            SystemMessage(content=EXPERT_PROMPTS.get(name, "") + _date_hint()),
            HumanMessage(content=query),
        ]
        nostream = {"tags": [INTERNAL_NOSTREAM_TAG]}
        ai = await llm.ainvoke(msgs, config=nostream)
        steps = 0
        while getattr(ai, "tool_calls", None) and steps < MAX_EXPERT_STEPS:
            steps += 1
            msgs.append(ai)
            for tc in ai.tool_calls:
                t = tool_map.get(tc["name"])
                out = await t.ainvoke(tc["args"]) if t else {"error": "no tool"}
                msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
            ai = await llm.ainvoke(msgs, config=nostream)
        return {"answer": ai.content}

    # ── gate：Tier-2 写操作图级强制确认门（interrupt 硬约束，阶段 E）────
    async def _gate(self, state: State):
        results = state.get("expert_results", [])
        pendings = [r for r in results if "pending_write" in r]
        if not pendings:
            return {}  # 无写操作：直通，不触发 interrupt

        actions = [{
            "expert": r["expert"],
            "tool": r["pending_write"]["tool"],
            "args": r["pending_write"]["args"],
            "preview": _preview_write(r["pending_write"]["tool"],
                                      r["pending_write"]["args"]),
        } for r in pendings]

        # 暂停图、把待确认动作回传前端；resume 时 interrupt() 返回用户决策。
        # gate 节点廉价、无 LLM 调用，resume 重跑无副作用（写操作仅在批准分支执行）。
        decision = interrupt({"kind": "confirm_required", "actions": actions})
        approved = bool((decision or {}).get("approved"))
        operator_id = _operator_from_state(state)

        new_results = []
        for r in pendings:
            pw = r["pending_write"]
            preview = _preview_write(pw["tool"], pw["args"])
            if approved:
                # ── v1.8.0 新增：execute_write 前二次校验 specific_part 归属（REQ-ISO-003）──
                from .scope_enforcer import verify_write_scope, ScopeViolationError as _SVE
                _ws = state.get("user_scope")
                _sp = pw["args"].get("specific_part", "")
                try:
                    verify_write_scope(_sp, _ws)
                except _SVE as _ve:
                    ans = (f"⚠️ 安全拦截：专有部分 {_sp} 不在您的绑定范围内，"
                           f"写操作已中止。如有问题请联系管理员。")
                    new_results.append({"expert": r["expert"], "answer": ans})
                    continue
                # ── end v1.8.0 ────────────────────────────────────────────────────────────
                out = await asyncio.to_thread(
                    execute_write, pw["tool"], pw["args"], operator_id)
                if isinstance(out, dict) and out.get("success", False):
                    ans = f"✅ 已执行：{out.get('summary') or preview}"
                else:
                    err = out.get("error") if isinstance(out, dict) else str(out)
                    ans = f"⚠️ 写操作执行失败：{err}。未确认数据已回滚，请稍后重试或联系运维。"
            else:
                ans = f"已取消「{preview}」——未执行，系统数据无任何变化。"
            new_results.append({"expert": r["expert"], "answer": ans})
        return {"expert_results": new_results}

    # ── aggregate：合并各专家结论为给用户的最终回复（仅取带 answer 的）──
    async def _aggregate(self, state: State):
        results = [r for r in state.get("expert_results", []) if "answer" in r]
        if not results:
            final = "未获得有效答复，请重试。"
        elif len(results) == 1:
            final = results[0]["answer"]
        else:
            # 去掉 [expert-id] 标签：避免融合模型在输出中暴露内部分工/路由（对用户透明）。
            digest = "\n".join(r["answer"] for r in results)
            ai = await self.llm.ainvoke([
                SystemMessage(content=(
                    "你就是方舟智能体本人，以第一人称统一作答。"
                    "将下列各段结论融合成一段连贯回复，重复内容合并为一次表述、不要重复。"
                    "严格禁止提及「专家」「转交」「咨询」「路由」或任何内部分工、多智能体编排细节；"
                    "禁止出现「根据各专家」「某专家认为」「巡检专家」「能耗专家」等措辞。"
                )),
                HumanMessage(content=f"以下是需要整合的结论：\n{digest}\n\n请综合为一段回复。"),
            ])
            final = ai.content

        # ── v1.4.1：全局去重 related_images（IFC-141-503，MOD-141-05）──────────
        all_images: list = []
        for r in results:
            all_images.extend(r.get("related_images", []))
        seen_ids: set = set()
        unique_images: list = []
        for img in all_images:
            if img["image_id"] not in seen_ids:
                seen_ids.add(img["image_id"])
                unique_images.append(img)
        # ────────────────────────────────────────────────────────────────────────

        return {
            "messages": [AIMessage(content=final)],
            "related_images": unique_images,   # v1.4.1 新增：写入 State 字段（IFC-141-503）
        }

    def _build(self):
        g = StateGraph(State)
        g.add_node("route", self._route)
        g.add_node("expert", self._expert)
        g.add_node("gate", self._gate)
        g.add_node("aggregate", self._aggregate)
        g.add_edge(START, "route")
        g.add_conditional_edges("route", self._fan_out, ["expert"])
        g.add_edge("expert", "gate")        # 所有专家分支汇聚到 gate（写确认门）
        g.add_edge("gate", "aggregate")
        g.add_edge("aggregate", END)
        # MemorySaver：interrupt/resume 在同一 WS 连接=同一 worker 进程内完成（决策E）。
        # 重启丢弃待确认状态=fail-closed（安全）；零额外依赖。
        return g.compile(checkpointer=MemorySaver())

    @staticmethod
    def _cfg(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    async def run(self, message: str, thread_id: str = "run-default") -> dict:
        """一次性运行（读路径/测试用）。写路径会在 gate interrupt，ainvoke 返回不含
        最终 answer——写确认请走 adapter.stream_chat + resume_chat。"""
        out = await self.graph.ainvoke(
            {"messages": [HumanMessage(content=message)]}, self._cfg(thread_id))
        msgs = out.get("messages", [])
        answer = msgs[-1].content if msgs else ""
        results = out.get("expert_results", [])
        return {
            "experts": [r["expert"] for r in results],
            "answer": answer,
            "delegations": [d for r in results for d in r.get("delegations", [])],
        }

    async def run_serial(self, message: str) -> dict:
        """同样的专家 + 聚合，但专家阶段强制串行——等价 OpenClaw 主 agent 顺序
        exec 委派。与 run() 做 apples-to-apples 对比：仅专家阶段并发度不同。
        注：绕过 graph/gate，仅用于读路径基准对比，不支持写确认门。"""
        plan = (await self._route({"messages": [HumanMessage(content=message)]}))["plan"]
        results = []
        for name, q in plan:  # 串行：逐个 await
            r = await self._expert({"name": name, "query": q, "messages": []})
            results.extend(r["expert_results"])
        agg = await self._aggregate({"expert_results": results})
        return {
            "experts": [r["expert"] for r in results],
            "answer": agg["messages"][-1].content,
        }
