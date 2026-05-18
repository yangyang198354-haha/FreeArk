from django.urls import path
from . import views
from . import views_device_settings

urlpatterns = [
    # CSRF token获取
    path('get-csrf-token/', views.get_csrf_token, name='get-csrf-token'),
    
    # 用户认证相关路由
    path('auth/login/', views.user_login, name='user-login'),
    path('auth/logout/', views.user_logout, name='user-logout'),
    path('auth/me/', views.get_current_user, name='get-current-user'),
    path('auth/register/', views.user_register, name='user-register'),
    path('change-password/', views.change_password, name='change-password'),
    
    # 管理员用户管理路由
    path('users/', views.UserList.as_view(), name='user-list'),
    path('users/<int:pk>/', views.UserDetail.as_view(), name='user-detail'),
    path('users/create/', views.AdminUserCreate.as_view(), name='admin-user-create'),
    

    
    # 健康检查
    path('health/', views.health_check, name='health-check'),
    
    # 用量数据查询
    path('usage/quantity/', views.get_usage_quantity, name='get-usage-quantity'),
    # 特定时间段用量数据查询（新端点）
    path('usage/quantity/specifictimeperiod/', views.get_usage_quantity_specific_time_period, name='get-usage-quantity-specific-time-period'),
    # 月度用量数据查询
    path('usage/quantity/monthly/', views.get_usage_quantity_monthly, name='get-usage-quantity-monthly'),
    
    # PLC连接状态查询
    path('plc/connection-status/', views.get_plc_connection_status, name='get-plc-connection-status'),
    # 单个PLC连接状态详情查询
    path('plc/connection-status/<str:specific_part>/', views.get_plc_connection_status_detail, name='get-plc-connection-status-detail'),
    # PLC状态变化历史查询
    path('plc/status-change-history/<str:specific_part>/', views.get_plc_status_change_history, name='get-plc-status-change-history'),
    
    # 计费管理接口
    path('billing/list/', views.get_bill_list, name='get-bill-list'),

    # 看板（Dashboard）接口
    path('dashboard/total-energy/', views.dashboard_total_energy, name='dashboard-total-energy'),
    path('dashboard/summary/', views.dashboard_summary, name='dashboard-summary'),
    path('dashboard/plc-online-rate/', views.dashboard_plc_online_rate, name='dashboard-plc-online-rate'),
    path('dashboard/screen-online-rate/', views.dashboard_screen_online_rate, name='dashboard-screen-online-rate'),
    path('dashboard/trend/', views.dashboard_trend, name='dashboard-trend'),
    path('dashboard/services/', views.dashboard_services, name='dashboard-services'),
    path('dashboard/activities/', views.dashboard_activities, name='dashboard-activities'),

    # 业主信息管理接口
    path('owners/', views.OwnerListCreateView.as_view(), name='owner-list-create'),
    path('owners/<int:pk>/', views.OwnerRetrieveUpdateDestroyView.as_view(), name='owner-detail'),
    # US-03: 业主设备树查看
    path('owners/<int:pk>/device-tree/', views.OwnerDeviceTreeView.as_view(), name='owner-device-tree'),

    # PLC 最新参数数据查询接口
    path('plc-latest/', views.get_plc_latest_data, name='get-plc-latest-data'),

    # 非专有部分设备实时参数卡片接口 (REQ-FUNC-033)
    path('devices/realtime-params/', views.get_device_realtime_params, name='device-realtime-params'),
    # 非专有部分设备历史参数查询接口 (REQ-FUNC-034)
    # 使用 query param 方式：?specific_part=9-1-31-3104[&sub_type=...][&param_name=...]
    path('devices/param-history/', views.get_device_param_history, name='device-param-history'),

    # 设备管理 — 设备列表接口 (MOD-BE-01, US-002~007)
    path('device-management/device-list/', views.device_management_device_list, name='device-management-device-list'),

    # 设备管理 — 设备树同步接口（单户 / 批量 / 批量进度）
    path('device-management/screen-device-tree/sync/', views.device_tree_sync_one, name='device-tree-sync-one'),
    path('device-management/screen-device-tree/batch-sync/', views.device_tree_sync_batch, name='device-tree-sync-batch'),
    path('device-management/screen-device-tree/batch-sync/<str:task_id>/', views.device_tree_sync_batch_status, name='device-tree-sync-batch-status'),

    # 服务管理接口
    path('services/list/', views.service_management_list, name='service-management-list'),
    path('services/<str:service_name>/detail/', views.service_management_detail, name='service-management-detail'),
    path('services/<str:service_name>/action/', views.service_management_action, name='service-management-action'),

    # 设备参数设置接口（FR1~FR6）
    path('device-settings/params/<str:specific_part>/', views_device_settings.device_settings_params, name='device-settings-params'),
    path('device-settings/write/', views_device_settings.device_settings_write, name='device-settings-write'),
    path('device-settings/records/', views_device_settings.device_settings_records, name='device-settings-records'),
]