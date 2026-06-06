"""
api.langgraph_chat.prompts —— 专家系统提示装载

阶段 A：内置精简提示作为兜底，保证开关一开即可用。
阶段 C（已合并入 main，见 PR#4）：装载生产级提示替换兜底。每个专家**优先**读
LangGraph 运行时版 `SYSTEM_PROMPT.langgraph.md`（原生工具 + 自然语言输出，已真机验证），
缺失则退回 OpenClaw 版 `SYSTEM_PROMPT.md`，再缺失退回内置兜底。
sanheng-knowledge 额外拼接 KNOWLEDGE.md。

为什么分出 .langgraph.md：原 SYSTEM_PROMPT.md 是 OpenClaw 设计期产物，通篇围绕
`exec python3 freeark_tool.py` + JSON 信封输出 + operator_override 写——这些在
LangGraph 运行时（@tool 原生调用 + ai.content 自然语言）下是错配。
.langgraph.md 是据实际绑定工具与运行时契约重写的版本，安全脊柱保留。

本文件相对 main(PR#4) 的增强（PR#5/阶段D 顺带）：剥离提示头部 `<!-- -->` 注释块
（不喂给模型）、`_read_prompt_file` 统一优先级读取、缺文件 FileNotFoundError 清晰化。

装载目录优先级：env FREEARK_AGENTS_DIR > settings.LANGGRAPH_AGENTS_DIR >
仓内相对 <repo>/agents。文件缺失时**不**抛错，退回上一级来源并记一条 warning，
以保证「影子接入零行为风险」——绝不因提示缺失把聊天打挂。

提示文件头部的 `<!-- ... -->` HTML 注释块仅是 provenance/部署标注，装载时一律
剥离，不作为系统提示喂给模型。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("api.langgraph_chat.prompts")

_EXPERTS = ("energy-expert", "inspection-expert", "sanheng-knowledge")

# 提示文件优先级：LangGraph 运行时版 > OpenClaw 版。
_PROMPT_FILENAMES = ("SYSTEM_PROMPT.langgraph.md", "SYSTEM_PROMPT.md")

# 剥离 HTML 注释块（provenance/部署标注，非提示正文）。
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_comments(text: str) -> str:
    return _HTML_COMMENT_RE.sub("", text).strip()

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


def _read_prompt_file(expert_dir: Path) -> tuple[str, str]:
    """按 _PROMPT_FILENAMES 优先级读首个存在且非空的提示文件。
    返回 (剥注释后的正文, 文件名)；都没有则抛 FileNotFoundError。"""
    for fname in _PROMPT_FILENAMES:
        sp = expert_dir / fname
        if not sp.is_file():
            continue
        text = _strip_comments(sp.read_text(encoding="utf-8"))
        if text:
            return text, fname
    raise FileNotFoundError(
        f"未找到非空提示文件（尝试 {_PROMPT_FILENAMES}）于 {expert_dir}")


def load_expert_prompts() -> dict:
    """装载专家提示；任何文件缺失/读失败均退回内置兜底（不抛错）。"""
    base = _agents_dir()
    prompts = dict(_FALLBACK_PROMPTS)
    for name in _EXPERTS:
        try:
            text, fname = _read_prompt_file(base / name)
            if name == "sanheng-knowledge":
                kp = base / name / "KNOWLEDGE.md"
                if kp.is_file():
                    kb = _strip_comments(kp.read_text(encoding="utf-8"))
                    if kb:
                        text += "\n\n# 参考知识\n" + kb
            prompts[name] = text
            logger.info("load_expert_prompts: %s 装载自 %s（%d 字符）",
                        name, fname, len(text))
        except Exception as exc:
            logger.warning(
                "load_expert_prompts: %s 装载失败，使用内置兜底提示: %s", name, exc)
    return prompts


# 模块级装载一次（编排器构造时引用）。
EXPERT_PROMPTS = load_expert_prompts()
