"""
api.langgraph_chat.prompts —— 专家系统提示装载

阶段 A：内置精简提示作为兜底，保证开关一开即可用。
阶段 C：若 agents/<expert>/SYSTEM_PROMPT.md（agent-builder 产物，评分 98/94/91）
可定位，则装载生产级提示替换兜底；sanheng-knowledge 额外拼接 KNOWLEDGE.md。

装载目录优先级：env FREEARK_AGENTS_DIR > settings.LANGGRAPH_AGENTS_DIR >
仓内相对 <repo>/agents。文件缺失时**不**抛错，退回内置兜底并记一条 warning，
以保证阶段 A「影子接入零行为风险」——绝不因提示缺失把聊天打挂。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("api.langgraph_chat.prompts")

_EXPERTS = ("energy-expert", "inspection-expert", "sanheng-knowledge")

# 内置兜底（PoC 精简版）。生产装载成功后会被覆盖。
_FALLBACK_PROMPTS = {
    "energy-expert": "你是 FreeArk 能耗分析专家，基于用电/看板数据给出节能与异常判断。",
    "inspection-expert": "你是 FreeArk 巡检诊断专家，结合 PLC 状态与故障汇总定位设备问题。",
    "sanheng-knowledge": "你是三恒系统知识专家，依据恒温恒湿恒氧原理回答原理性问题。",
}


def _agents_dir() -> Path:
    env_dir = os.environ.get("FREEARK_AGENTS_DIR")
    if env_dir:
        return Path(env_dir)
    try:
        from django.conf import settings
        cfg = getattr(settings, "LANGGRAPH_AGENTS_DIR", "")
        if cfg:
            return Path(cfg)
    except Exception:  # pragma: no cover
        pass
    # 向上逐层找含 agents/energy-expert 的目录（不依赖固定层数，避免 IndexError）。
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "agents"
        if (cand / "energy-expert").is_dir():
            return cand
    return here.parents[-1] / "agents"


def load_expert_prompts() -> dict:
    """装载专家提示；任何文件缺失/读失败均退回内置兜底（不抛错）。"""
    base = _agents_dir()
    prompts = dict(_FALLBACK_PROMPTS)
    for name in _EXPERTS:
        sp = base / name / "SYSTEM_PROMPT.md"
        try:
            text = sp.read_text(encoding="utf-8").strip()
            if not text:
                raise ValueError("empty SYSTEM_PROMPT.md")
            if name == "sanheng-knowledge":
                kp = base / name / "KNOWLEDGE.md"
                if kp.is_file():
                    text += "\n\n# 参考知识\n" + kp.read_text(encoding="utf-8").strip()
            prompts[name] = text
        except Exception as exc:
            logger.warning(
                "load_expert_prompts: %s 装载失败，使用内置兜底提示: %s", name, exc)
    return prompts


# 模块级装载一次（编排器构造时引用）。
EXPERT_PROMPTS = load_expert_prompts()
