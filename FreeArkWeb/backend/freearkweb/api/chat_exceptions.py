"""
api.chat_exceptions —— 聊天后端统一异常类型

原 OpenClawUnavailableError 定义于 api.openclaw_adapter，退役 OpenClaw 后迁移至此，
作为聊天后端（LangGraph）失败时的统一降级异常，被 consumers.py 捕获映射至 WS 错误码。
"""


class ChatBackendUnavailableError(Exception):
    """聊天后端不可用（LangGraph 编排失败、网络超时等）。

    ChatConsumer 捕获此异常，映射至 OPENCLAW_UNAVAILABLE WS 错误码（向后兼容）。
    原名 OpenClawUnavailableError，退役 OpenClaw 后统一改名，消费端错误码不变。
    """
    pass


# 向后兼容别名：现有 import OpenClawUnavailableError 的调用方可逐步迁移。
OpenClawUnavailableError = ChatBackendUnavailableError
