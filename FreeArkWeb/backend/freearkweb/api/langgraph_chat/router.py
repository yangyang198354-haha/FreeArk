"""
api.langgraph_chat.router —— 意图路由

阶段 A：关键词/显式命中的确定性路由（离线可测、零额外 LLM 调用）。
阶段 D：`classify_experts()` 升级为 **LLM 分类器**——一次轻量调用让模型从固定
        专家集合里选出应处理的专家（单意图 1 个 / 复合意图多个 / 都不沾边空）。
        签名仍是 text -> list[expert_name]，不影响下游并行 fan-out 结构。

兜底链（决策：总有专家应答）：
  LLM 分类器命中非空 → 用之
  → LLM 失败/解析不出/空 → 关键词路由 route_experts()
  → 关键词仍空 → DEFAULT_EXPERT（freeark-expert）

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

# P2-2：专家元数据收敛到 experts 注册表（单一真源）。以下常量从注册表**派生**——
# 保留原符号名作别名，引用/测试零改动；关键词选词原则等说明已随数据迁入 experts.py。
# （experts 模块 langchain-free，本模块"顶层禁 langchain"约束不破。）
from . import experts as _experts

EXPERT_NAMES = _experts.names()             # 合法专家集合（分类结果只接受其中之一）
DEFAULT_EXPERT = _experts.default_expert()  # 零信号兜底默认专家
ROUTE_KEYWORDS = _experts.keywords_map()    # 关键词路由命中词（确定性兜底 + P0-1 短路基准）
DATA_EXPERTS = _experts.data_experts()      # 数据域专家（持查询/写工具）；sanheng 无工具纯知识

# 从含历史前缀 + [__freeark_user__:..] 标签的整块里抽「当前问题」（最后一个标签之后）。
# 护栏关键词只匹配当前问题，避免历史里的数据词误触发、把正当的 sanheng 路由改掉。
_CURRENT_QUERY_RE = re.compile(r"\[__freeark_user__:[^\]]*\]\s*(.*)\Z", re.DOTALL)

# 历史记忆块（chat_memory.build_inject_prefix 写入）：[历史记忆开始]...[历史记忆结束]。
# P0-2 粘性路由从中取「上一轮用户问题」推断上一轮专家。
_HISTORY_BLOCK_RE = re.compile(r"\[历史记忆开始\](.*?)\[历史记忆结束\]", re.DOTALL)
_HISTORY_USER_LINE_RE = re.compile(r"^用户:\s*(.+)$", re.MULTILINE)


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


def previous_turn_expert(text: str) -> Optional[str]:
    """P0-2 粘性路由：从注入的历史记忆块里取**最后一轮用户问题**，关键词路由出上一轮专家。

    唯一命中才返回（与短路同口径，避免歧义续接）；无历史块 / 取不到用户行 / 0 或 ≥2 命中
    → None。纯函数、离线可测、零额外 LLM 调用。

    用途：当前问题零路由信号（无关键词且 LLM 返回空）时，用它替代盲目的 DEFAULT_EXPERT，
    接住「那上个月呢/再详细点」这类自身无领域词的追问。只作 fallback，不覆盖关键词/LLM/短路。

    注：聊天历史只存 role/content（见 chat_memory），不记录每轮专家；故从上一轮用户问题
    的关键词反推，而非读结构化的"上轮专家"——这是当前架构下最稳的来源（历史前缀每轮必带）。"""
    m = _HISTORY_BLOCK_RE.search(text or "")
    if not m:
        return None
    users = _HISTORY_USER_LINE_RE.findall(m.group(1))
    if not users:
        return None
    hits = _keyword_hits(users[-1])  # 仅看最近一轮用户问题
    return hits[0] if len(hits) == 1 else None


# ── LLM 分类器（阶段 D）──────────────────────────────────────────────────────
ROUTER_SYSTEM_PROMPT = (
    "你是 FreeArk（自由方舟）智能客服的意图路由器。根据用户问题，判断应由哪些专家处理。\n"
    "只能从以下 3 个专家里选：\n"
    "- freeark-expert：系统管家，拥有全系统掌控权——能耗看板摘要、日用电量、设备实时传感器参数"
    "（温度/湿度/CO₂/风量）查询与分析、PLC 在线/离线状态、设备故障汇总、设备参数控制（写操作）、"
    "按需采集刷新、三恒知识库检索。覆盖面最广，是默认承接专家。\n"
    "- inspection-expert：巡检诊断专家，专注 PLC 在线/离线状态深度诊断、设备故障汇总分析、"
    "巡检诊断、预警识别、故障修复建议。\n"
    "- sanheng-knowledge：三恒系统（恒温/恒湿/恒氧）的原理、概念、参数含义，以及设备说明书/"
    "技术文档类知识问题（如热量表/计量表接口标准、设备型号、接线方式、尺寸图纸、主控箱/新风机/"
    "手操器/面板等部件的说明）——凡答案来自产品手册或技术文档的，都归本专家。\n"
    "规则：\n"
    "1. 单一意图只选 1 个；只有问题明确同时涉及多个领域时才选多个（控成本与并发，不要滥选）。\n"
    "2. 三者都不沾边则返回空数组 []。\n"
    "3. 只输出 JSON 数组，元素是上面的专家 id，例如 [\"freeark-expert\"] 或 "
    "[\"freeark-expert\",\"sanheng-knowledge\"]。不要任何解释、不要代码围栏、不要多余文字。"
)

# 提取 JSON 数组片段（非贪婪；flash 可能在数组前后夹散文或 ```json 围栏）。
_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def parse_route_response_ex(raw: Optional[str]) -> tuple[Optional[List[str]], bool]:
    """解析 LLM 原始输出 → (合法专家名列表 or None, saw_empty)。

    返回值两个分量：
      - 专家列表：去重保序的合法专家名；解析不出任何合法专家 → None。
      - saw_empty（P1-2 域外信号）：是否**成功解析出一个 JSON 数组、但其中无任何合法专家**
        （字面 `[]` 或 `["foo"]` 之类）。区分「LLM 明确表态不属任何领域」(saw_empty=True)
        与「输出根本无法解析/异常」(saw_empty=False)——前者才是可信的 OOD 信号。

    鲁棒处理：散文包裹、```json 围栏、多个数组片段、非法元素。"""
    if not raw:
        return None, False
    saw_array = False
    for m in _JSON_ARRAY_RE.finditer(raw):
        try:
            arr = json.loads(m.group(0))
        except Exception:
            continue
        if not isinstance(arr, list):
            continue
        saw_array = True
        seen, out = set(), []
        for x in arr:
            if isinstance(x, str) and x in EXPERT_NAMES and x not in seen:
                seen.add(x)
                out.append(x)
        if out:
            return out, False
    return None, saw_array  # 有数组但无合法专家 → saw_empty=True（OOD）；无数组 → False


def parse_route_response(raw: Optional[str]) -> Optional[List[str]]:
    """从 LLM 原始输出解析专家名数组（兼容旧签名；仅返回专家列表，丢弃 saw_empty）。

    鲁棒处理：散文包裹、```json 围栏、多个数组片段、非法元素。
    返回去重保序的合法专家名列表；解析不出任何合法专家 → None（交上层兜底）。"""
    return parse_route_response_ex(raw)[0]


# ── P2-1：能力（工具）感知路由提示 ───────────────────────────────────────────
def _tool_brief(description: str) -> str:
    """取工具描述首句（到第一个 。/换行前），去掉 [写操作·需用户确认] 这类前缀标注，精简。"""
    d = (description or "").strip()
    if d.startswith("["):
        end = d.find("]")
        if end != -1:
            d = d[end + 1:].strip()
    for sep in ("。", "\n"):
        i = d.find(sep)
        if i != -1:
            d = d[:i]
            break
    return d.strip()


def build_capability_digest(tools_by_expert) -> str:
    """据各专家持有的工具（@tool 的 .name/.description）生成能力摘要，供注入路由 LLM 提示，
    使其据「谁有能力处理」分派——避免把需某工具的问题分给无该工具的专家（P2-1：护栏的**预防层**，
    从源头减少误路由，使确定性护栏 _guard_against_misroute 退居 backstop）。

    纯函数：只读传入工具对象的 .description，**不 import langchain/fa_tools**（保持本模块离线可测；
    工具表由 orchestrator 传入）。传入空/异常 → 返回空串（调用方据此不注入，行为同 P2-1 前）。"""
    try:
        if not tools_by_expert:
            return ""
        lines = ["【各专家可用能力——据此判断谁能处理；不要把需要某工具的问题分给没有该工具的专家】"]
        for expert, tools in tools_by_expert.items():
            briefs = "；".join(
                _tool_brief(getattr(t, "description", "")) for t in (tools or []))
            lines.append(f"- {expert}：{briefs or '无任何工具（仅据通用知识作答，不能查询数据或执行操作）'}")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        return ""


async def classify_experts_llm_ex(llm, text: str,
                                  capability_digest: str = "") -> tuple[Optional[List[str]], bool]:
    """调 LLM 分类器 → (专家列表 or None, llm_said_ood)。任何异常/解析失败 → (None, False)。

    llm_said_ood：LLM 成功返回了"不属任何专家"的明确表态（见 parse_route_response_ex）。
    capability_digest（P2-1）非空时拼到 system 提示尾部，令 LLM 据工具能力分派（预防误路由）。
    用 tuple 格式消息，避免本模块顶层依赖 langchain（便于离线单测用 stub）。"""
    try:
        system = ROUTER_SYSTEM_PROMPT
        if capability_digest:
            system = ROUTER_SYSTEM_PROMPT + "\n\n" + capability_digest
        ai = await llm.ainvoke([
            ("system", system),
            ("human", (text or "").strip()[:2000]),
        ])
        raw = getattr(ai, "content", None)
        if raw is None and isinstance(ai, str):
            raw = ai
        return parse_route_response_ex(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("classify_experts_llm 失败，回退关键词路由: %s", exc)
        return None, False


async def classify_experts_llm(llm, text: str) -> Optional[List[str]]:
    """兼容旧签名：仅返回专家列表（丢弃 OOD 信号）。"""
    return (await classify_experts_llm_ex(llm, text))[0]


def _guard_against_misroute(names: List[str], query: str) -> List[str]:
    """护栏（2026-06-14）：纠正两类高置信误路由（query 为已剥历史的当前问题）。

      情形1：LLM **仅**选了无工具的 sanheng-knowledge，但当前问题命中数据域关键词
             → 改派关键词命中的数据专家（数据查询落到无工具知识专家只能拒答）。
             生产实例：问"当前有多少故障"却被答"我是三恒知识专家"。
      情形2：LLM **仅**选了某单一数据专家 X，但当前问题关键词**只**指向另一数据专家(非 X)
             → 改派之。生产实例：问"过去七天能耗数据"被路由到 inspection-expert，
             而它无 get_usage_daily，只能答"我手头工具只能查 PLC/故障"。

    仅在「单一路由 + 关键词明确指向数据域」时介入；复合路由、关键词为空、或关键词含
    所选专家时一律保留 LLM 结果（LLM 仍是判断主力，护栏只兜高置信矛盾），爆炸半径最小。

    2026-07-04（freeark-expert 改名+关键词扩展）：情形1 新增 sanheng 关键词共存检查——
    freeark-expert 关键词扩大后与 sanheng 可能出现交集（如"温度"既可以是传感器查询也
    可以是原理话题）。若 query **同时**命中 sanheng 关键词，说明它可能是正当的知识问题，
    此时不覆盖、保留 LLM 判断。"""
    data_hits = [e for e in _keyword_hits(query) if e in DATA_EXPERTS]
    if not data_hits:
        return names
    # 情形1：仅选无工具的 sanheng，但当前问题是数据查询
    if names == ["sanheng-knowledge"]:
        # 若 query 同时也命中 sanheng 自身关键词 → 可能是正当知识问题，不覆盖
        sanheng_kws = ROUTE_KEYWORDS.get("sanheng-knowledge", ())
        if any(k in query.lower() for k in sanheng_kws):
            return names
        logger.info("router 护栏1：LLM 仅选 sanheng-knowledge（无工具）但当前问题命中数据域 "
                    "%s，改派", data_hits)
        return data_hits
    # 情形2：仅选某数据专家，但关键词只指向另一数据专家（落到无该工具的专家会拒答）
    if len(names) == 1 and names[0] in DATA_EXPERTS and names[0] not in data_hits:
        logger.info("router 护栏2：LLM 仅选 %s 但当前问题关键词只指向 %s，改派",
                    names[0], data_hits)
        return data_hits
    return names


async def classify_experts(llm, text: str,
                           sticky_hint: Optional[str] = None,
                           allow_ood: bool = False,
                           capability_digest: str = "",
                           guard: bool = True) -> List[str]:
    """阶段 D 路由入口：路由决策只看「当前问题」（剥历史前缀，防历史污染路由）。

    兜底优先级（高→低）：
      LLM 命中非空（经护栏）→ 关键词命中 → P0-2 粘性（sticky_hint，上一轮专家）
      → P1-2 域外（allow_ood 且 LLM 明确表态不属任何领域）返回 **[]** → DEFAULT_EXPERT。

    设计要点：
      - 历史不参与路由意图分类（掺入会被前文带偏）；粘性/域外均为受控例外，仅在当前问题
        **零信号**时介入，绝不覆盖关键词/LLM 的明确判断。
      - **返回 []** 表示「无专家应答，交通用应答节点」（P1-2）。仅当 LLM 可信地表态域外
        （parse 出空数组而非解析失败）、且无关键词、无粘性时才返回；否则仍落 DEFAULT。
        粘性优先于域外：有上一轮专家时优先承接对话，避免把追问误判为闲聊。

    P2-1：capability_digest 非空时注入路由 LLM 提示（按工具能力分派，预防误路由）；guard=False
    时跳过确定性护栏 _guard_against_misroute（供能力提示验证充分后灰度退役护栏）。

    向后兼容：sticky_hint=None、allow_ood=False、capability_digest=""、guard=True（默认）时行为与
    P2-1 前完全一致——既有调用/测试零影响。llm 为 None 时走关键词路由（无 LLM 即无 OOD 信号）。"""
    query = _current_query(text)  # 路由只用当前问题，不掺历史
    llm_said_ood = False
    if llm is not None:
        names, llm_said_ood = await classify_experts_llm_ex(llm, query, capability_digest)
        if names:
            # P2-1：能力提示是预防层；确定性护栏退居可选 backstop（guard=False 可关，灰度退役）。
            return _guard_against_misroute(names, query) if guard else names
    # 零信号兜底：关键词命中 → 粘性（上一轮专家）→ 域外[] → DEFAULT。
    hits = _keyword_hits(query)
    if hits:
        return hits
    if sticky_hint in EXPERT_NAMES:
        logger.info("router 粘性兜底：当前问题零信号，承接上一轮专家 %s", sticky_hint)
        return [sticky_hint]
    if allow_ood and llm_said_ood:
        logger.info("router 域外路径：LLM 明确表态不属任何专家且无关键词/粘性 → 通用应答")
        return []
    return [DEFAULT_EXPERT]
