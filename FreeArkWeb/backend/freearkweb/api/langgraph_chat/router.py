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
# energy-expert 兼"操控"：除能耗读词外，含 Tier-2 写/控制类动作词（set_device_params /
# trigger_refresh 归 energy）。控制词（2026-06-14 补）选**动作性强、与知识问题低撞车**者：
# 收 刷新/采集/下发/触发/设定；**不收** 控制/调节（"三恒怎么控制温度的原理"是知识问题，
# 收了会让护栏把这类纯知识问题误改派到 energy）。
ROUTE_KEYWORDS = {
    "energy-expert": ("能耗", "用电", "用量", "电费", "看板", "节能", "kwh",
                      "刷新", "采集", "下发", "触发", "设定"),
    "inspection-expert": ("故障", "巡检", "plc", "离线", "在线", "传感器", "报警"),
    # sanheng-knowledge = 知识库/RAG 专家：除三恒原理概念外，亦覆盖设备说明书/技术文档类
    # 问题（接口标准、型号、接线、尺寸图、说明书等）——这些答案在 RAG 知识库里，须路由到
    # 唯一持有 search_sanheng_knowledge 工具的本专家。词选**与数据域低撞车**者，避免误把
    # 数据查询(能耗/故障)拽进来；故不收"参数/数据"等泛词（与 energy 实时参数查询易冲突）。
    "sanheng-knowledge": ("三恒", "恒温", "恒湿", "恒氧", "原理", "为什么",
                          "接口", "型号", "说明书", "接线", "图纸", "尺寸",
                          "热量表", "计量表", "主控箱", "手操器", "新风机",
                          "modbus", "485", "毛细管"),
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


def keyword_shortcircuit_target(text: str) -> Optional[str]:
    """P0-1 关键词短路判定：当前问题**唯一且无撞车**地命中某专家关键词时返回该专家，
    否则 None（→ 应交 LLM 分类器）。

    判据来自 routing_eval 评测（2026-06-27，见 routing_eval/README.md）：唯一关键词命中
    的用例，关键词路由与真实 LLM 路由都 100% 命中——这些查询可跳过 LLM 分类器省 ~2s/条、
    零精度损失。0 命中（需语义判断，如无关键词的知识/巡检问题）或 ≥2 命中（撞车/复合，
    交 LLM 决断）一律**不**短路。

    只看当前问题（剥历史前缀），与 classify_experts 的路由口径一致。纯函数、离线可测。
    实际短路在 orchestrator._route 执行（受 settings.LANGGRAPH_ROUTER_KEYWORD_SHORTCIRCUIT
    开关控制）；classify_experts 不变，故护栏/兜底测试与本短路解耦。

    残留风险：含数据关键词的纯知识问题（如「故障率怎么定义」命中"故障"）会被短路到数据
    专家。关键词表已刻意规避（如不收"控制/调节"）；如生产暴露新例，加入 routing_eval 数据集
    并按需收窄，或置开关为 False 一键回退恒走 LLM。"""
    hits = _keyword_hits(_current_query(text))
    return hits[0] if len(hits) == 1 else None


# ── LLM 分类器（阶段 D）──────────────────────────────────────────────────────
ROUTER_SYSTEM_PROMPT = (
    "你是 FreeArk（自由方舟）智能客服的意图路由器。根据用户问题，判断应由哪些专家处理。\n"
    "只能从以下 3 个专家里选：\n"
    "- energy-expert：能耗/用电量/电费/看板摘要，以及设备实时传感器参数（温度/湿度/CO₂/风量）的查询与分析。\n"
    "- inspection-expert：PLC 在线/离线状态、设备故障汇总、巡检诊断、预警识别。\n"
    "- sanheng-knowledge：三恒系统（恒温/恒湿/恒氧）的原理、概念、参数含义，以及设备说明书/"
    "技术文档类知识问题（如热量表/计量表接口标准、设备型号、接线方式、尺寸图纸、主控箱/新风机/"
    "手操器/面板等部件的说明）——凡答案来自产品手册或技术文档的，都归本专家。\n"
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


def _guard_against_misroute(names: List[str], query: str) -> List[str]:
    """护栏（2026-06-14）：纠正两类高置信误路由（query 为已剥历史的当前问题）。

      情形1：LLM **仅**选了无工具的 sanheng-knowledge，但当前问题命中数据域关键词
             → 改派关键词命中的数据专家（数据查询落到无工具知识专家只能拒答）。
             生产实例：问"当前有多少故障"却被答"我是三恒知识专家"。
      情形2：LLM **仅**选了某单一数据专家 X，但当前问题关键词**只**指向另一数据专家(非 X)
             → 改派之。生产实例：问"过去七天能耗数据"被路由到 inspection-expert，
             而它无 get_usage_daily，只能答"我手头工具只能查 PLC/故障"。

    仅在「单一路由 + 关键词明确指向数据域」时介入；复合路由、关键词为空、或关键词含
    所选专家时一律保留 LLM 结果（LLM 仍是判断主力，护栏只兜高置信矛盾），爆炸半径最小。"""
    data_hits = [e for e in _keyword_hits(query) if e in DATA_EXPERTS]
    if not data_hits:
        return names
    # 情形1：仅选无工具的 sanheng，但当前问题是数据查询
    if names == ["sanheng-knowledge"]:
        logger.info("router 护栏1：LLM 仅选 sanheng-knowledge（无工具）但当前问题命中数据域 "
                    "%s，改派", data_hits)
        return data_hits
    # 情形2：仅选某数据专家，但关键词只指向另一数据专家（落到无该工具的专家会拒答）
    if len(names) == 1 and names[0] in DATA_EXPERTS and names[0] not in data_hits:
        logger.info("router 护栏2：LLM 仅选 %s 但当前问题关键词只指向 %s，改派",
                    names[0], data_hits)
        return data_hits
    return names


async def classify_experts(llm, text: str) -> List[str]:
    """阶段 D 路由入口：路由决策只看「当前问题」（剥历史前缀，防历史污染路由）→
    LLM 分类器 → 护栏纠误（防数据查询落到无该工具的专家）→ 关键词兜底 → DEFAULT_EXPERT。

    注：历史仅供专家**作答**时参考（consumers 注入），不参与**路由**决策——路由是对当前
    意图分类，掺入历史会被前文话题带偏（生产实例：故障-heavy 历史把能耗查询带偏到 inspection）。

    llm 为 None 时直接走关键词路由（供不想付 LLM 调用的场景）。"""
    query = _current_query(text)  # 路由只用当前问题，不掺历史
    if llm is not None:
        names = await classify_experts_llm(llm, query)
        if names:
            return _guard_against_misroute(names, query)
    return route_experts(query)  # 关键词路由自带 DEFAULT_EXPERT 兜底
