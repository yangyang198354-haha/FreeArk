"""
api.langgraph_chat.router —— 意图路由

阶段 A：关键词/显式命中的确定性路由（离线可测、零额外 LLM 调用）。
阶段 D：`classify_experts()` 升级为 **LLM 分类器**——一次轻量调用让模型从固定
        专家集合里选出应处理的专家（单意图 1 个 / 复合意图多个 / 都不沾边空）。
        签名仍是 text -> list[expert_name]，不影响下游并行 fan-out 结构。

兜底链（决策：总有专家应答）：
  LLM 分类器命中非空 → 用之
  → LLM 失败/解析不出/空 → 关键词路由 route_experts()
  → 关键词仍空 → DEFAULT_EXPERT（energy-expert）

设计要点：
  - LLM 调用走 tuple 格式消息 `[("system",..),("human",..)]`，router.py 顶层**不 import
    langchain**——纯解析器 parse_route_response 与关键词路由可在无 langchain 环境单测。
  - 解析器对 flash 模型常见的脏输出鲁棒：```json 围栏、前后散文、非法专家名、空数组、
    多个数组片段，均能正确提取或安全退回 None（交由上层兜底）。
  - 路由模型可独立于主模型（决策2：用更轻模型控成本），见 orchestrator._make_router_llm
    与 settings.LANGGRAPH_ROUTER_MODEL。
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

logger = logging.getLogger("api.langgraph_chat.router")

# 合法专家集合（分类结果只接受这三者之一）。
EXPERT_NAMES = ("energy-expert", "inspection-expert", "sanheng-knowledge")

DEFAULT_EXPERT = "energy-expert"

# ── 关键词路由（阶段 A 保留：LLM 不可用时的确定性兜底 + 离线单测基准）──────────
ROUTE_KEYWORDS = {
    "energy-expert": ("能耗", "用电", "用量", "电费", "看板", "节能", "kwh"),
    "inspection-expert": ("故障", "巡检", "plc", "离线", "在线", "传感器", "报警"),
    "sanheng-knowledge": ("三恒", "恒温", "恒湿", "恒氧", "原理", "为什么"),
}


# 数据域专家（持有查询/写工具）；sanheng-knowledge 无工具、纯知识问答。
DATA_EXPERTS = ("energy-expert", "inspection-expert")

# 从含历史前缀 + [__freeark_user__:..] 标签的整块里抽「当前问题」（最后一个标签之后）。
# 护栏关键词只匹配当前问题，避免历史里的数据词误触发、把正当的 sanheng 路由改掉。
_CURRENT_QUERY_RE = re.compile(r"\[__freeark_user__:[^\]]*\]\s*(.*)\Z", re.DOTALL)


def _current_query(text: str) -> str:
    """剥掉历史记忆前缀，取最后一个 __freeark_user__ 标签之后的当前问题；无标签则原样。"""
    m = _CURRENT_QUERY_RE.search(text or "")
    return (m.group(1) if m else (text or "")).strip()


def _keyword_hits(text: str) -> List[str]:
    """关键词命中的专家（真实命中、去重保序、不含兜底）。"""
    low = (text or "").lower()
    return [name for name, kws in ROUTE_KEYWORDS.items()
            if any(k in low for k in kws)]


def route_experts(text: str) -> List[str]:
    """关键词路由：返回命中的专家列表（去重保序），空则兜底单专家。

    阶段 D 后此函数退居为 LLM 分类器的兜底；仍是纯函数、离线可测。"""
    return _keyword_hits(text) or [DEFAULT_EXPERT]


# ── LLM 分类器（阶段 D）──────────────────────────────────────────────────────
ROUTER_SYSTEM_PROMPT = (
    "你是 FreeArk（自由方舟）智能客服的意图路由器。根据用户问题，判断应由哪些专家处理。\n"
    "只能从以下 3 个专家里选：\n"
    "- energy-expert：能耗/用电量/电费/看板摘要，以及设备实时传感器参数（温度/湿度/CO₂/风量）的查询与分析。\n"
    "- inspection-expert：PLC 在线/离线状态、设备故障汇总、巡检诊断、预警识别。\n"
    "- sanheng-knowledge：三恒系统（恒温/恒湿/恒氧）的原理、概念、参数含义等知识性问题。\n"
    "规则：\n"
    "1. 单一意图只选 1 个；只有问题明确同时涉及多个领域时才选多个（控成本与并发，不要滥选）。\n"
    "2. 三者都不沾边则返回空数组 []。\n"
    "3. 只输出 JSON 数组，元素是上面的专家 id，例如 [\"energy-expert\"] 或 "
    "[\"energy-expert\",\"sanheng-knowledge\"]。不要任何解释、不要代码围栏、不要多余文字。"
)

# 提取 JSON 数组片段（非贪婪；flash 可能在数组前后夹散文或 ```json 围栏）。
_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def parse_route_response(raw: Optional[str]) -> Optional[List[str]]:
    """从 LLM 原始输出解析专家名数组。

    鲁棒处理：散文包裹、```json 围栏、多个数组片段、非法元素。
    返回去重保序的合法专家名列表；解析不出任何合法专家 → None（交上层兜底）。"""
    if not raw:
        return None
    for m in _JSON_ARRAY_RE.finditer(raw):
        try:
            arr = json.loads(m.group(0))
        except Exception:
            continue
        if not isinstance(arr, list):
            continue
        seen, out = set(), []
        for x in arr:
            if isinstance(x, str) and x in EXPERT_NAMES and x not in seen:
                seen.add(x)
                out.append(x)
        if out:
            return out
    return None


async def classify_experts_llm(llm, text: str) -> Optional[List[str]]:
    """调 LLM 分类器选专家；任何异常/解析失败/空命中 → None（不抛错）。

    用 tuple 格式消息，避免本模块顶层依赖 langchain（便于离线单测用 stub）。"""
    try:
        ai = await llm.ainvoke([
            ("system", ROUTER_SYSTEM_PROMPT),
            ("human", (text or "").strip()[:2000]),
        ])
        raw = getattr(ai, "content", None)
        if raw is None and isinstance(ai, str):
            raw = ai
        return parse_route_response(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("classify_experts_llm 失败，回退关键词路由: %s", exc)
        return None


def _guard_against_toolless_misroute(names: List[str], text: str) -> List[str]:
    """护栏（2026-06-14）：LLM **仅**选了无工具的 sanheng-knowledge，但「当前问题」关键词
    命中数据域（能耗/巡检）→ 几乎必是误路由：数据查询会卡死在无工具知识专家、只能拒答
    （生产实例：用户问"当前有多少故障、影响多少户"却被答"我是三恒知识专家"）。
    改派关键词命中的数据专家。仅针对 sanheng-ONLY 这一危险情形，爆炸半径最小。

    关键词只匹配当前问题（剥历史前缀），避免历史里的数据词污染正当的 sanheng 路由。"""
    if names == ["sanheng-knowledge"]:
        data_hits = [e for e in _keyword_hits(_current_query(text)) if e in DATA_EXPERTS]
        if data_hits:
            logger.info("router 护栏：LLM 仅选 sanheng-knowledge（无工具）但当前问题命中数据域 "
                        "%s，判为误路由并改派之", data_hits)
            return data_hits
    return names


async def classify_experts(llm, text: str) -> List[str]:
    """阶段 D 路由入口：LLM 分类器 → 关键词兜底 → DEFAULT_EXPERT。
    LLM 命中后经 _guard_against_toolless_misroute 护栏（防数据查询漏到无工具 sanheng）。

    llm 为 None 时直接走关键词路由（供不想付 LLM 调用的场景）。"""
    if llm is not None:
        names = await classify_experts_llm(llm, text)
        if names:
            return _guard_against_toolless_misroute(names, text)
    return route_experts(text)  # 关键词路由自带 DEFAULT_EXPERT 兜底
