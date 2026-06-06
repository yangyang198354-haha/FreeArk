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

import operator
from typing import Annotated, List, Tuple, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage)
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .fa_tools import TOOLS_BY_EXPERT
from .prompts import EXPERT_PROMPTS
from .router import classify_experts


class State(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: List[Tuple[str, str]]
    expert_results: Annotated[List[dict], operator.add]
    # 仅在 Send 分支负载里出现：
    name: str
    query: str


def _make_llm(latency: float | None = None):
    """模型工厂：默认连真 DeepSeek（OpenAI 兼容）；
    settings.LANGGRAPH_USE_FAKE_LLM=True 时走离线假模型（CI/单测）。"""
    from django.conf import settings

    if getattr(settings, "LANGGRAPH_USE_FAKE_LLM", False):
        from .fake_llm import LatencyFakeChat
        return LatencyFakeChat() if latency is None else LatencyFakeChat(latency=latency)

    from langchain_openai import ChatOpenAI  # 延迟 import，假模型路径不需要
    return ChatOpenAI(
        model=getattr(settings, "LANGGRAPH_MODEL", "deepseek-v4-flash"),
        base_url=getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key=getattr(settings, "DEEPSEEK_API_KEY", "") or "sk-noop",
        temperature=0.2,
        timeout=getattr(settings, "LANGGRAPH_LLM_TIMEOUT", 60),
        max_retries=1,
    )


def _make_router_llm(main_llm, latency: float | None = None):
    """路由分类器模型（决策2：可用更轻模型控成本）。
    fake 模式或 LANGGRAPH_ROUTER_MODEL 为空 → 复用主模型实例；
    配置了独立路由模型则单独构造（temperature 0，确定性分类）。"""
    from django.conf import settings

    if getattr(settings, "LANGGRAPH_USE_FAKE_LLM", False):
        return main_llm
    rm = (getattr(settings, "LANGGRAPH_ROUTER_MODEL", "") or "").strip()
    if not rm:
        return main_llm

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=rm,
        base_url=getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key=getattr(settings, "DEEPSEEK_API_KEY", "") or "sk-noop",
        temperature=0.0,
        timeout=getattr(settings, "LANGGRAPH_LLM_TIMEOUT", 60),
        max_retries=1,
    )


# 编排器：图编译一次、模型一次 → 进程常驻，零 per-request 冷启动
class Orchestrator:
    def __init__(self, latency: float | None = None):
        self.llm = _make_llm(latency)
        self.router_llm = _make_router_llm(self.llm, latency)
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
