"""
api.chat_backend —— 聊天后端工厂

生产唯一聊天路径：LangGraph（进程内编排，直连 DeepSeek）。
OpenClaw 集成已于 v1.7.0 退役。

文档引用：docs/requirements/v1.7.0_openclaw_retirement/
"""

from __future__ import annotations


def get_chat_adapter():
    """返回当前生效的聊天适配器类（LangGraph）。"""
    from api.langgraph_chat.adapter import LangGraphAdapter
    return LangGraphAdapter
