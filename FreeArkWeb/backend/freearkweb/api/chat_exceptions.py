"""
api.chat_exceptions —— 聊天后端统一异常类型

原 OpenClawUnavailableError 定义于 api.openclaw_adapter，退役 OpenClaw 后迁移至此，
作为聊天后端（LangGraph）失败时的统一降级异常，被 consumers.py 捕获映射至 WS 错误码。
"""


class ChatBackendUnavailableError(Exception):
    """聊天后端不可用（LangGraph 编排失败、网络超时等）。

    ChatConsumer 捕获此异常，映射至 OPENCLAW_UNAVAILABLE WS 错误码（向后兼容）。
    原名 OpenClawUnavailableError，退役 OpenClaw 后统一改名，消费端错误码不变。

    可选携带分类信息（adapter._classify_stream_failure 产出）：
      - user_message：面向用户的安全降级文案。None → consumers 用默认"暂时离线"。
        绝不放原始异常细节（可能含内部实现/密钥片段），仅放可安全展示的提示。
      - code：WS 错误码。默认 'OPENCLAW_UNAVAILABLE'（向后兼容）；分类后可为
        CONTEXT_LENGTH_EXCEEDED / RATE_LIMITED / LLM_CONFIG_ERROR 等。前端对未知
        error code 统一按 message 展示（ChatView.vue / 小程序 chat-ws 均如此），
        故新增 code 无需前端联动。
    """

    def __init__(self, *args, user_message: str | None = None,
                 code: str = "OPENCLAW_UNAVAILABLE"):
        super().__init__(*args)
        self.user_message = user_message
        self.code = code


# 向后兼容别名：现有 import OpenClawUnavailableError 的调用方可逐步迁移。
OpenClawUnavailableError = ChatBackendUnavailableError
