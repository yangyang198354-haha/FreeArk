"""
api.langgraph_chat.router —— 意图路由

阶段 A：关键词/显式命中的确定性路由（离线可测、零额外 LLM 调用）。
阶段 D：替换 route_experts 为 LLM 分类器或 supervisor handoff tool_calls，
        签名不变（text -> list[expert_name]），不影响并行延迟结构。

兜底链：分类命中为空 → energy-expert（保证总有专家应答，对齐 PoC 行为）。
"""

from __future__ import annotations

from typing import List

# 关键词 → 专家
ROUTE_KEYWORDS = {
    "energy-expert": ("能耗", "用电", "用量", "电费", "看板", "节能", "kwh"),
    "inspection-expert": ("故障", "巡检", "plc", "离线", "在线", "传感器", "报警"),
    "sanheng-knowledge": ("三恒", "恒温", "恒湿", "恒氧", "原理", "为什么"),
}

DEFAULT_EXPERT = "energy-expert"


def route_experts(text: str) -> List[str]:
    """根据用户问题文本返回命中的专家列表（去重保序），空则兜底单专家。"""
    low = (text or "").lower()
    chosen = [name for name, kws in ROUTE_KEYWORDS.items()
              if any(k in low for k in kws)]
    return chosen or [DEFAULT_EXPERT]
