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
from . import views_miniapp_device_settings as views_ds

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

    # v1.10.0 屏端 MQTT 参数配置（IsOwnerUser）
    #   config：下发 broker 连接参数 + 业主自己房间(含 screenMac) + 可写白名单/标签
    #   audit ：客户端尽力上报写操作审计，落 PLCWriteRecord(channel='screen-mqtt')
    path('device-settings/config/', views_ds.device_settings_config,
         name='miniapp-ds-config'),
    path('device-settings/audit/', views_ds.device_settings_audit,
         name='miniapp-ds-audit'),

    # v1.11.0 业主端设备实时参数 + 按需采集（IsOwnerUser + 归属过滤）
    #   realtime-params：业主读自己绑定的专有部分实时参数，含 screen_mac/device_sns
    #   ondemand-refresh：业主触发 PLC 按需采集（代理端点，归属过滤后转发）
    path('owner/realtime-params/', views_ds.miniapp_owner_realtime_params,
         name='miniapp-owner-realtime-params'),
    path('owner/ondemand-refresh/', views_ds.miniapp_owner_ondemand_refresh,
         name='miniapp-owner-ondemand-refresh'),

    # v1.11.1 业主设备树结构骨架端点（IsOwnerUser + 归属过滤）
    #   structure：返回 rooms/system_devices 结构骨架 + params_skeleton（DeviceConfig）
    #              不含任何 PLCLatestData 字段，与实时数据完全解耦（REQ-FUNC-001-C）
    #              前端结构缓存 TTL=24h；sync_status="pending" 时前端缩短至 5min
    path('owner/structure/', views_ds.miniapp_owner_structure,
         name='miniapp-owner-structure'),

    # v1.12.0 资料更新（IsAuthenticated）：上传头像（multipart）和/或保存昵称
    #   使用 IsAuthenticated 而非 IsOwnerUser——头像昵称是用户自身资料，不限制 role。
    #   POST /api/miniapp/profile/update/ multipart/form-data {avatar?, nickname?}
    #   → 200 {avatar_url, nickname}；400 参数错误/文件校验失败；401 未认证
    path('profile/update/', views_miniapp.miniapp_profile_update,
         name='miniapp-profile-update'),
]
