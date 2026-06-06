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
import operator
import re
from typing import Annotated, List, Tuple, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from .fa_tools import TOOLS_BY_EXPERT, WRITE_TOOL_NAMES, execute_write
from .prompts import EXPERT_PROMPTS
from .router import classify_experts


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
    return f"openclaw-agent::{user}"


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

    # ── expert：单专家 ReAct（读工具内联执行；写工具延迟到 gate 确认）──
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
        if getattr(ai, "tool_calls", None):
            # 拆分读/写：读工具内联执行；写工具不执行，记 pending_write 交 gate 确认。
            pending = [tc for tc in ai.tool_calls if tc["name"] in WRITE_TOOL_NAMES]
            if pending:
                # LLM 的写决策已被 checkpoint（本节点返回即落 state）；resume 时不重跑本节点。
                return {"expert_results": [
                    {"expert": name,
                     "pending_write": {"tool": tc["name"], "args": tc.get("args", {})}}
                    for tc in pending]}
            msgs.append(ai)
            for tc in ai.tool_calls:
                t = tool_map.get(tc["name"])
                out = await t.ainvoke(tc["args"]) if t else {"error": "no tool"}
                msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
            ai = await llm.ainvoke(msgs)
        return {"expert_results": [{"expert": name, "answer": ai.content}]}

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
        return {
            "experts": [r["expert"] for r in out.get("expert_results", [])],
            "answer": answer,
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
