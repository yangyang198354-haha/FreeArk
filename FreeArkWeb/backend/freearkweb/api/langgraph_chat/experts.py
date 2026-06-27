"""
api.langgraph_chat.experts —— 专家注册表（P2-2：单一真源）

把原先散落在 5 个模块里的「按专家并列声明」收敛到一处：
  - router.py   ：EXPERT_NAMES / DEFAULT_EXPERT / ROUTE_KEYWORDS / DATA_EXPERTS
  - prompts.py  ：_EXPERTS / _FALLBACK_PROMPTS
  - adapter.py  ：_EXPERT_CN
  - orchestrator.py：DELEGATING_EXPERTS
各模块改为**从本表派生**这些常量（保留原符号名作别名，引用/测试零改动）。加/改一个专家的
**元数据**只需改这一处（其工具仍在 fa_tools 按名挂载，提示仍在 agents/<name>/ 文件）。

**严格 langchain-free**：本模块只含纯数据 + dataclass + stdlib，不 import langchain/fa_tools——
故 router.py（顶层禁 langchain，便于离线单测）可安全 import 本表。工具对象（@tool，依赖
langchain）天然留在 fa_tools；本表只给「名字 + 顺序 + langchain-free 元数据」的权威来源。

顺序即全系统专家顺序（energy → inspection → sanheng），各派生常量保持此序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ExpertSpec:
    name: str                       # 专家 id（路由结果、TOOLS_BY_EXPERT 键、提示目录名）
    cn_label: str                   # 面向用户的中文标签（仅 reasoning 折叠框，不进正式答复）
    keywords: Tuple[str, ...]       # 关键词路由命中词（确定性兜底 + P0-1 短路基准）
    is_data_expert: bool            # 是否持有数据查询/写工具（护栏区分：数据查询不可落无工具专家）
    fallback_prompt: str            # 提示文件缺失时的内置兜底系统提示
    is_delegating: bool = False     # 是否可子委托同侪（阶段 G，目前仅 inspection）
    is_default: bool = False        # 零信号兜底默认专家（全系统唯一一个 True）


# ── 专家注册表（唯一真源；顺序 = 全系统专家顺序）─────────────────────────────
# 关键词选词原则（原 router.py 注释，随数据迁来）：
#   energy-expert 兼"操控"：能耗读词 + Tier-2 写/控制动作词（刷新/采集/下发/触发/设定）；
#     **不收** 控制/调节（"三恒怎么控制温度的原理"是知识问题，收了会被护栏误改派到 energy）。
#   sanheng-knowledge = 知识库/RAG：三恒原理概念 + 设备说明书/技术文档（接口/型号/接线/尺寸/
#     说明书/热量表…）。选**与数据域低撞车**的词，不收"参数/数据"等泛词（与实时参数查询冲突）。
EXPERT_SPECS: List[ExpertSpec] = [
    ExpertSpec(
        name="energy-expert",
        cn_label="能耗分析",
        keywords=("能耗", "用电", "用量", "电费", "看板", "节能", "kwh",
                  "刷新", "采集", "下发", "触发", "设定"),
        is_data_expert=True,
        fallback_prompt="你是 FreeArk 能耗分析专家，基于用电/看板数据给出节能与异常判断。",
        is_default=True,
    ),
    ExpertSpec(
        name="inspection-expert",
        cn_label="巡检诊断",
        keywords=("故障", "巡检", "plc", "离线", "在线", "传感器", "报警"),
        is_data_expert=True,
        fallback_prompt="你是 FreeArk 巡检诊断专家，结合 PLC 状态与故障汇总定位设备问题。",
        is_delegating=True,
    ),
    ExpertSpec(
        name="sanheng-knowledge",
        cn_label="三恒知识",
        keywords=("三恒", "恒温", "恒湿", "恒氧", "原理", "为什么",
                  "接口", "型号", "说明书", "接线", "图纸", "尺寸",
                  "热量表", "计量表", "主控箱", "手操器", "新风机",
                  "modbus", "485", "毛细管"),
        is_data_expert=False,
        fallback_prompt="你是三恒系统知识专家，依据恒温恒湿恒氧原理回答原理性问题。",
    ),
]

_BY_NAME: Dict[str, ExpertSpec] = {s.name: s for s in EXPERT_SPECS}


# ── 派生访问器（各模块据此构造原有常量，保持顺序）──────────────────────────
def names() -> Tuple[str, ...]:
    return tuple(s.name for s in EXPERT_SPECS)


def keywords_map() -> Dict[str, Tuple[str, ...]]:
    return {s.name: s.keywords for s in EXPERT_SPECS}


def cn_map() -> Dict[str, str]:
    return {s.name: s.cn_label for s in EXPERT_SPECS}


def fallback_prompts() -> Dict[str, str]:
    return {s.name: s.fallback_prompt for s in EXPERT_SPECS}


def data_experts() -> Tuple[str, ...]:
    return tuple(s.name for s in EXPERT_SPECS if s.is_data_expert)


def delegating_experts() -> Tuple[str, ...]:
    return tuple(s.name for s in EXPERT_SPECS if s.is_delegating)


def default_expert() -> str:
    for s in EXPERT_SPECS:
        if s.is_default:
            return s.name
    return EXPERT_SPECS[0].name  # 兜底：无标记则取首个（不应发生）


def get(name: str) -> ExpertSpec:
    return _BY_NAME[name]
