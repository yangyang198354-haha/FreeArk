"""
langgraph-poc — 编排图：supervisor 路由 + 专家并行 fan-out + 聚合

对应 OpenClaw 现状的逐项替换：

  OpenClaw                              LangGraph 本图
  ─────────────────────────────────    ─────────────────────────────────
  main agent 方舟智能体                  supervisor / route 节点
  exec `openclaw agent --agent X`       Send(expert, payload)（进程内，无冷启动）
  串行委派 3 专家 ≈ 3×31s               Send fan-out 并行 ≈ max(单专家)
  freeark_tool.py 子进程                 fa_tools.@tool 进程内直调
  gateway WS 跳转                        graph.astream 进程内迭代

并行的本质：route 作为条件边一次返回多个 `Send`，LangGraph 在同一个 superstep 内
并发执行所有目标节点；各分支把结果写入带 `operator.add` reducer 的 expert_results，
天然归并。这把「复合意图」从线性累加变成取最大值。

路由说明：PoC 的 route 用关键词/显式 @标记 做确定性分流（离线可测）。生产可无缝
替换为「LLM 分类器」或「supervisor 第一轮 tool_calls handoff」——这只增加一次快速
分类调用，不改变并行延迟结构。

文档引用：detailed_design.md §1.2/§1.3, [[openclaw-multiagent-capabilities]]
"""

from __future__ import annotations

import inspect
import operator
import os
from typing import Annotated, Callable, List, Optional, Tuple, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage)
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from fa_tools import TOOLS_BY_EXPERT

# ── 专家系统提示（PoC 精简版；生产装载 agents/<expert>/SYSTEM_PROMPT.md）────
EXPERT_PROMPTS = {
    "energy-expert": "你是 FreeArk 能耗分析专家，基于用电/看板数据给出节能与异常判断。",
    "inspection-expert": "你是 FreeArk 巡检诊断专家，结合 PLC 状态与故障汇总定位设备问题。",
    "sanheng-knowledge": "你是三恒系统知识专家，依据恒温恒湿恒氧原理回答原理性问题。",
}

# 关键词 → 专家（PoC 确定性路由；生产换 LLM 分类器）
_ROUTE_KEYWORDS = {
    "energy-expert": ("能耗", "用电", "用量", "电费", "看板", "节能", "kwh"),
    "inspection-expert": ("故障", "巡检", "plc", "离线", "在线", "传感器", "报警"),
    "sanheng-knowledge": ("三恒", "恒温", "恒湿", "恒氧", "原理", "为什么"),
}


# ── 跨 agent 委托（sub-delegation）工具 ───────────────────────────────
# 巡检专家在推理中可调用以下「委托工具」请求同侪能力。它们不真正执行 API，而是被
# orchestrator 的 expert 循环按名拦截，路由到目标专家（深度限 1：目标专家不再带委托
# 工具，避免递归），结果作为 ToolMessage 回灌发起方继续推理——对应 inspection-expert
# SYSTEM_PROMPT 的 delegations 契约（knowledge_query / read_query / write_command）。
@tool
def delegate_knowledge(question: str = "") -> dict:
    """向三恒知识库专家请求原理/机理/概念分析（只读知识，无副作用）。
    question: 需要分析的问题或巡检情况描述。"""
    return {"_delegation": "knowledge_query"}  # 占位：实际执行由 orchestrator 拦截


@tool
def delegate_read(query: str = "", specific_part: str = "") -> dict:
    """向能耗专家请求只读数据（实时参数/配置/历史/能耗）。
    query: 取数需求；specific_part: 设备号如 '3-1-7-702'（可选）。"""
    return {"_delegation": "read_query"}  # 占位：实际执行由 orchestrator 拦截


@tool
def delegate_write(description: str = "", specific_part: str = "",
                   params: Optional[dict] = None) -> dict:
    """提案下发/修改设备参数等写操作（有副作用，必须用户确认后由能耗专家执行）。
    description: 处置说明；specific_part: 设备号；params: 待写参数。"""
    return {"_delegation": "write_command"}  # 占位：实际执行由 orchestrator 拦截


DELEGATION_TOOLS = [delegate_knowledge, delegate_read, delegate_write]
DELEGATION_TOOL_NAMES = {t.name for t in DELEGATION_TOOLS}
MAX_EXPERT_STEPS = 8  # 单专家 ReAct + 委托链的步数上限（防失控循环）


class State(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: List[Tuple[str, str]]
    expert_results: Annotated[List[dict], operator.add]
    # 仅在 Send 分支负载里出现：
    name: str
    query: str


def _make_llm(latency: float | None = None):
    """模型工厂：有 key 走真 DeepSeek（OpenAI 兼容），否则离线假模型。"""
    live = os.environ.get("FREEARK_POC_LIVE", "") == "1"
    if live:
        from langchain_openai import ChatOpenAI  # 延迟 import，离线不需要
        return ChatOpenAI(
            model=os.environ.get("POC_MODEL", "deepseek-v4-flash"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-noop"),
            temperature=0.2, timeout=60, max_retries=1,
        )
    from fake_llm import LatencyFakeChat
    return LatencyFakeChat() if latency is None else LatencyFakeChat(latency=latency)


# 模块级编排器：图编译一次、模型一次 → 进程常驻，零 per-request 冷启动
class Orchestrator:
    def __init__(self, latency: float | None = None,
                 confirm_write: Callable[[dict], bool] | None = None,
                 delegating_experts: tuple[str, ...] = ("inspection-expert",)):
        self.llm = _make_llm(latency)
        # 写操作确认门：默认拒绝（安全缺省——无人确认即不执行）。生产应接 LangGraph
        # interrupt() 人审打断（见 README §6）；此处保留可注入回调，便于离线测试与
        # 在尚未接 interrupt 的过渡期保持「写必确认」语义不被绕过。
        self.confirm_write = confirm_write or (lambda d: False)
        self.delegating_experts = set(delegating_experts)
        self.graph = self._build()

    # ── route：复合意图分流为多个并行 Send ──────────────────────────
    def _route(self, state: State):
        text = ""
        for m in reversed(state["messages"]):
            if isinstance(m, HumanMessage):
                text = (m.content or "").lower()
                break
        chosen = [name for name, kws in _ROUTE_KEYWORDS.items()
                  if any(k in text for k in kws)]
        if not chosen:
            chosen = ["energy-expert"]  # 兜底
        plan = [(name, text) for name in chosen]
        return {"plan": plan}

    def _fan_out(self, state: State):
        # 条件边：一次返回多个 Send → LangGraph 并发执行（核心并行点）
        return [Send("expert", {"name": name, "query": q, "messages": []})
                for name, q in state["plan"]]

    # ── expert：单专家 ReAct（绑定该专家工具 + 可选委托工具，多轮直到收敛）──
    async def _expert(self, state: State):
        name = state["name"]
        query = state["query"]
        allow = name in self.delegating_experts
        return await self._run_expert(name, query, allow_delegation=allow)

    async def _run_expert(self, name: str, query: str,
                          allow_delegation: bool = False) -> dict:
        base_tools = TOOLS_BY_EXPERT.get(name, [])
        tool_map = {t.name: t for t in base_tools}
        bound = list(base_tools) + (DELEGATION_TOOLS if allow_delegation else [])
        llm = self.llm.bind_tools(bound) if bound else self.llm

        msgs: List[BaseMessage] = [
            SystemMessage(content=EXPERT_PROMPTS.get(name, "")),
            HumanMessage(content=query),
        ]
        delegations: List[dict] = []
        ai = await llm.ainvoke(msgs)
        steps = 0
        # 多轮：普通工具直调，委托工具拦截路由到同侪，结果回灌后续推理
        while getattr(ai, "tool_calls", None) and steps < MAX_EXPERT_STEPS:
            steps += 1
            msgs.append(ai)
            for tc in ai.tool_calls:
                if tc["name"] in DELEGATION_TOOL_NAMES and allow_delegation:
                    handled = await self._handle_delegation(
                        name, tc["name"], tc.get("args", {}), query)
                    delegations.append(handled["log"])
                    out = handled["result"]
                else:
                    t = tool_map.get(tc["name"])
                    out = await t.ainvoke(tc["args"]) if t else {"error": "no tool"}
                msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
            ai = await llm.ainvoke(msgs)
        return {"expert_results": [
            {"expert": name, "answer": ai.content, "delegations": delegations}]}

    # ── sub-delegation：把发起方的委托路由到目标专家 / 写经确认门 ──────────
    async def _handle_delegation(self, origin: str, tool_name: str,
                                 args: dict, origin_query: str) -> dict:
        args = args or {}
        if tool_name == "delegate_knowledge":
            q = args.get("question") or (
                f"（{origin} 委托）请就以下巡检情况做三恒原理分析：{origin_query}")
            ans = (await self._run_expert(
                "sanheng-knowledge", q))["expert_results"][0]["answer"]
            return {
                "result": {"status": "OK", "from": "sanheng-knowledge",
                           "intent": "knowledge_query", "data": ans},
                "log": {"target_agent": "sanheng-knowledge",
                        "intent": "knowledge_query", "status": "OK"},
            }
        if tool_name == "delegate_read":
            part = args.get("specific_part") or ""
            q = args.get("query") or origin_query
            if part:
                q = f"{q}（设备 {part}）"
            ans = (await self._run_expert(
                "energy-expert", q))["expert_results"][0]["answer"]
            return {
                "result": {"status": "OK", "from": "energy-expert",
                           "intent": "read_query", "data": ans},
                "log": {"target_agent": "energy-expert",
                        "intent": "read_query", "status": "OK"},
            }
        if tool_name == "delegate_write":
            delegation = {
                "target_agent": "energy-expert", "intent": "write_command",
                "description": args.get("description", ""),
                "specific_part": args.get("specific_part", ""),
                "params": args.get("params") or {},
                "requires_user_confirmation": True,
            }
            log = {"target_agent": "energy-expert", "intent": "write_command",
                   "specific_part": delegation["specific_part"]}
            if not await self._ask_confirm(delegation):
                return {
                    "result": {"status": "USER_CANCELLED",
                               "note": "写操作未获用户确认，未执行"},
                    "log": {**log, "status": "USER_CANCELLED"},
                }
            q = (f"已确认执行写操作：{delegation['description']} "
                 f"设备={delegation['specific_part']} 参数={delegation['params']}")
            ans = (await self._run_expert(
                "energy-expert", q))["expert_results"][0]["answer"]
            return {
                "result": {"status": "OK", "from": "energy-expert",
                           "intent": "write_command", "executed": True, "data": ans},
                "log": {**log, "status": "EXECUTED"},
            }
        return {"result": {"status": "ERROR", "error": f"未知委托工具 {tool_name}"},
                "log": {"target_agent": "?", "intent": "?", "status": "ERROR"}}

    async def _ask_confirm(self, delegation: dict) -> bool:
        """写操作确认门。默认实现走注入的 confirm_write 回调；生产替换为 interrupt()。
        回调异常一律视为未确认（安全缺省）。"""
        try:
            res = self.confirm_write(delegation)
            if inspect.isawaitable(res):
                res = await res
            return bool(res)
        except Exception:
            return False

    # ── aggregate：合并各专家结论为给用户的最终回复 ──────────────────
    async def _aggregate(self, state: State):
        results = state.get("expert_results", [])
        if len(results) == 1:
            final = results[0]["answer"]
        else:
            digest = "\n".join(f"[{r['expert']}] {r['answer']}" for r in results)
            ai = await self.llm.ainvoke([
                SystemMessage(content="你是方舟智能体总协调，融合各专家结论给出统一回复。"),
                HumanMessage(content=f"各专家结论：\n{digest}\n\n请综合为一段答复。"),
            ])
            final = ai.content
        return {"messages": [AIMessage(content=final)]}

    def _build(self):
        g = StateGraph(State)
        g.add_node("route", self._route)
        g.add_node("expert", self._expert)
        g.add_node("aggregate", self._aggregate)
        g.add_edge(START, "route")
        g.add_conditional_edges("route", self._fan_out, ["expert"])
        g.add_edge("expert", "aggregate")
        g.add_edge("aggregate", END)
        return g.compile()

    async def run(self, message: str) -> dict:
        out = await self.graph.ainvoke({"messages": [HumanMessage(content=message)]})
        results = out.get("expert_results", [])
        return {
            "experts": [r["expert"] for r in results],
            "answer": out["messages"][-1].content,
            "delegations": [d for r in results for d in r.get("delegations", [])],
        }

    async def run_serial(self, message: str) -> dict:
        """同样的专家 + 聚合，但专家阶段强制串行——等价 OpenClaw 主 agent 顺序
        exec 委派。与 run() 做 apples-to-apples 对比：仅专家阶段并发度不同。"""
        plan = self._route({"messages": [HumanMessage(content=message)]})["plan"]
        results = []
        for name, q in plan:  # 串行：逐个 await
            r = await self._expert({"name": name, "query": q, "messages": []})
            results.extend(r["expert_results"])
        agg = await self._aggregate({"expert_results": results})
        return {
            "experts": [r["expert"] for r in results],
            "answer": agg["messages"][-1].content,
        }
