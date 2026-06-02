"""
api.chat_backend —— 聊天后端工厂（阶段 A 影子接入开关）

ChatConsumer 不再硬依赖 OpenClawAdapter，而是经本工厂按 settings.CHAT_BACKEND
选择适配器。两个适配器同签名（stream_chat(message, session_key) -> AsyncGenerator
[tuple[str,str]]），且均以 OpenClawUnavailableError 作为统一降级异常。

  CHAT_BACKEND=openclaw  （默认）→ OpenClawAdapter（现状，零行为变化）
  CHAT_BACKEND=langgraph         → LangGraphAdapter（进程内 LangGraph 编排）

切换/回滚只需改一个 env 值并重启 worker，无 DB 变更。langgraph_chat 包仅在选中
该后端时才 import，因此默认 openclaw 部署无需安装 langgraph 依赖、也不会因其缺失而崩。

文档引用：agents/langgraph-poc/PHASE3_ROLLOUT.md 阶段 A.2
"""

from __future__ import annotations

from django.conf import settings


def get_chat_adapter():
    """返回当前生效的聊天适配器类（按 settings.CHAT_BACKEND）。"""
    backend = getattr(settings, "CHAT_BACKEND", "openclaw")
    if backend == "langgraph":
        from api.langgraph_chat.adapter import LangGraphAdapter
        return LangGraphAdapter
    from api.openclaw_adapter import OpenClawAdapter
    return OpenClawAdapter
