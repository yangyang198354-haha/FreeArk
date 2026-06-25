"""
api.urls_miniapp — /api/miniapp/ 命名空间路由（v1.8.0_miniprogram_owner_account）

安全约束：本文件内每个端点必须显式配置权限类（IsOwnerUser 或 AllowAny 或 IsOperatorOrAbove）。
禁止使用 IsAuthenticated（过于宽泛，operator 也会通过 IsOwnerUser 不满足）。
新增端点时必须同步在本文件注释中说明权限类选择理由。

在根路由 freearkweb/urls.py 中 include：
    path('api/miniapp/', include('api.urls_miniapp'))
"""
from django.urls import path
from . import views_miniapp

urlpatterns = [
    # 注册（AllowAny）：role 强制 user，由视图层保证；无需 IsOwnerUser
    path('auth/register/', views_miniapp.miniapp_register, name='miniapp-register'),

    # 微信一键登录（AllowAny）：用 code 换 token，首次自动建账号
    path('auth/wechat/', views_miniapp.miniapp_wechat_login, name='miniapp-wechat-login'),

    # 绑定（IsOwnerUser）：仅 role=user 且已登录可操作
    path('bind/', views_miniapp.miniapp_bind, name='miniapp-bind'),

    # 解绑（IsOwnerUser）：业主自助解绑
    path('unbind/', views_miniapp.miniapp_unbind, name='miniapp-unbind'),

    # 绑定状态查询（IsOwnerUser）
    path('bind/status/', views_miniapp.miniapp_bind_status, name='miniapp-bind-status'),

    # 业主管理页账号绑定列（IsOperatorOrAbove）：web 端 admin/operator 专用
    path('admin/owner-bindings/', views_miniapp.owner_binding_list,
         name='miniapp-owner-binding-list'),
]
