"""
langgraph-poc — 编排图：supervisor 路由 + 专家并行 fan-out + 聚合

对应 OpenClaw 现状的逐项替换：

  OpenClaw                              LangGraph 本图
  ─────────────────────────────────    ─────────────────────────────────
  main agent 方舟龙虾                    supervisor / route 节点
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

import operator
import os
from typing import Annotated, List, Tuple, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage)
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
    def __init__(self, latency: float | None = None):
        self.llm = _make_llm(latency)
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

    # ── expert：单专家 ReAct（绑定该专家工具，一轮工具调用）──────────
    async def _expert(self, state: State):
        name = state["name"]
        query = state["query"]
        tools = TOOLS_BY_EXPERT.get(name, [])
        tool_map = {t.name: t for t in tools}
        llm = self.llm.bind_tools(tools) if tools else self.llm

        msgs: List[BaseMessage] = [
            SystemMessage(content=EXPERT_PROMPTS.get(name, "")),
            HumanMessage(content=query),
        ]
        ai = await llm.ainvoke(msgs)
        # 若请求工具，执行后再问一轮拿最终答复
        if getattr(ai, "tool_calls", None):
            msgs.append(ai)
            for tc in ai.tool_calls:
                t = tool_map.get(tc["name"])
                out = await t.ainvoke(tc["args"]) if t else {"error": "no tool"}
                msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
            ai = await llm.ainvoke(msgs)
        return {"expert_results": [{"expert": name, "answer": ai.content}]}

    # ── aggregate：合并各专家结论为给用户的最终回复 ──────────────────
    async def _aggregate(self, state: State):
        results = state.get("expert_results", [])
        if len(results) == 1:
            final = results[0]["answer"]
        else:
            digest = "\n".join(f"[{r['expert']}] {r['answer']}" for r in results)
            ai = await self.llm.ainvoke([
                SystemMessage(content="你是方舟龙虾总协调，融合各专家结论给出统一回复。"),
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
        return {
            "experts": [r["expert"] for r in out.get("expert_results", [])],
            "answer": out["messages"][-1].content,
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
