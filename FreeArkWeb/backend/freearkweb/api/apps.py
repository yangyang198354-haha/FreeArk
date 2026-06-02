import logging

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger('api.apps')


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        # 阶段 A：仅当 CHAT_BACKEND=langgraph 时预热 LangGraph 编排器，使图编译/
        # 模型构造在 worker 启动时一次性付清，避免首个聊天请求承担冷启动。
        # 预热失败仅记日志、不阻断启动（首个请求会重试并经统一降级通道处理）。
        # 默认 openclaw 时绝不 import langgraph_chat（不要求安装其依赖）。
        if getattr(settings, 'CHAT_BACKEND', 'openclaw') != 'langgraph':
            return
        try:
            from api.langgraph_chat.adapter import warm
            warm()
        except Exception as exc:  # noqa: BLE001
            logger.warning('LangGraph 预热入口异常（忽略，运行期重试）: %s', exc)
