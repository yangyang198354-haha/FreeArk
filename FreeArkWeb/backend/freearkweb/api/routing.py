"""
WebSocket URL 路由配置（MOD-BE-04）

将 ws/chat/ 路径映射到 ChatConsumer。
此文件由 asgi.py 中的 ProtocolTypeRouter 导入。

项目: FreeArk_Openclaw
文档引用: module_design.md MOD-BE-04, architecture_design.md ADR-001
"""

from django.urls import re_path
from api.consumers import ChatConsumer, MiniAppChatConsumer

websocket_urlpatterns = [
    re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    # v1.8.0 新增：小程序业主端聊天 WebSocket（role=user 允许连接）
    re_path(r'^ws/miniapp/chat/$', MiniAppChatConsumer.as_asgi()),
]
