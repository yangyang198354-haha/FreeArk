"""
ASGI config for freearkweb project — 重构为 ProtocolTypeRouter（MOD-BE-03）

架构变更（ADR-001）：
  原：Django 默认 get_asgi_application()（仅支持 HTTP，Waitress 驱动）
  改：ProtocolTypeRouter（http → Django ASGI，websocket → URLRouter(ChatConsumer)）

启动命令（部署时修改 systemd 服务文件，见 module_design.md MOD-OPS-01）：
  uvicorn freearkweb.asgi:application --host 0.0.0.0 --port 8000 --workers 1
  注意：必须 --workers 1（InMemoryChannelLayer 不支持多进程）

项目: FreeArk_Openclaw
文档引用: module_design.md MOD-BE-03, architecture_design.md ADR-001
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')

# 必须在 Django 设置加载（get_asgi_application()）之后导入 channels 相关模块，
# 否则 Django apps 尚未初始化，ORM 访问会失败。
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

# 延迟导入路由，确保 Django setup 已完成
from api.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    # HTTP 请求：交由 Django 处理（现有所有 API 视图不受影响）
    'http': django_asgi_app,

    # WebSocket 请求：经 AllowedHostsOriginValidator 校验 Origin，
    # 再由 URLRouter 分发至对应 Consumer
    # AllowedHostsOriginValidator 使用 settings.ALLOWED_HOSTS 进行校验
    'websocket': AllowedHostsOriginValidator(
        URLRouter(websocket_urlpatterns)
    ),
})
