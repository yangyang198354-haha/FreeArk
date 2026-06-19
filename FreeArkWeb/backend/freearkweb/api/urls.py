from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import views_device_settings
from . import views_heartbeat_config
from . import memory_views
from . import views_fault
from . import views_condensation
from . import views_inspection
from . import views_workorder
from . import views_rag

# RAG 知识库路由（v1.4.0_sanheng_rag）
_rag_router = DefaultRouter()
_rag_router.register(r'rag/documents', views_rag.RagDocumentViewSet, basename='rag-document')

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
    path('dashboard/power-status/', views.dashboard_power_status, name='dashboard-power-status'),
    # v1.0.0: 故障与子设备汇总接口（REQ-FUNC-DC-01, REQ-FUNC-DC-06）
    path('dashboard/fault-summary/', views.dashboard_fault_summary, name='dashboard-fault-summary'),
    path('dashboard/device-fault-summary/', views.dashboard_device_fault_summary, name='dashboard-device-fault-summary'),

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
    # v0.5.6: 按需采集触发接口 (MOD-BE-01, REQ-FUNC-001)
    path('devices/ondemand-refresh/', views.device_ondemand_refresh, name='device-ondemand-refresh'),
    # v0.5.3-FCC: 故障数量查询接口 (REQ-FUNC-FC-05/FC-06)
    path('devices/fault-count/', views.device_fault_count, name='device-fault-count'),
    path('devices/fault-summary/', views.device_fault_summary, name='device-fault-summary'),

    # 设备管理 — 设备列表接口 (MOD-BE-01, US-002~007)
    path('device-management/device-list/', views.device_management_device_list, name='device-management-device-list'),

    # 设备管理 — 设备树同步接口（单户 / 批量 / 批量进度）
    path('device-management/screen-device-tree/sync/', views.device_tree_sync_one, name='device-tree-sync-one'),
    path('device-management/screen-device-tree/batch-sync/', views.device_tree_sync_batch, name='device-tree-sync-batch'),
    path('device-management/screen-device-tree/batch-sync/<str:task_id>/', views.device_tree_sync_batch_status, name='device-tree-sync-batch-status'),

    # 服务管理接口
    # 巡检智能体按需触发 / 状态轮询 / 工作日志（v1.3.0-AOW）
    path('inspection/trigger/<str:event_type>/<int:event_id>/',
         views_inspection.inspection_trigger, name='inspection-trigger'),
    path('inspection/status/<str:event_type>/<int:event_id>/',
         views_inspection.inspection_status_view, name='inspection-status'),
    path('inspection/logs/', views_inspection.inspection_logs, name='inspection-logs'),

    # 巡检工单查看 + 写提案人工审批执行（v1.3.1-WO）
    path('workorders/', views_workorder.workorder_list, name='workorder-list'),
    path('workorders/<int:pk>/', views_workorder.workorder_detail, name='workorder-detail'),
    path('workorders/<int:pk>/approve-write/', views_workorder.workorder_approve_write,
         name='workorder-approve-write'),
    path('workorders/<int:pk>/resolve/', views_workorder.workorder_resolve,
         name='workorder-resolve'),

    path('services/list/', views.service_management_list, name='service-management-list'),
    path('services/<str:service_name>/detail/', views.service_management_detail, name='service-management-detail'),
    path('services/<str:service_name>/action/', views.service_management_action, name='service-management-action'),

    # 设备参数设置接口（FR1~FR6）
    path('device-settings/params/<str:specific_part>/', views_device_settings.device_settings_params, name='device-settings-params'),
    path('device-settings/write/', views_device_settings.device_settings_write, name='device-settings-write'),
    path('device-settings/records/', views_device_settings.device_settings_records, name='device-settings-records'),

    # 心跳 Broker 配置接口（v0.5.9, REQ-FUNC-002）
    path('heartbeat-broker-config/', views_heartbeat_config.heartbeat_broker_config_get, name='heartbeat-broker-config-get'),
    path('heartbeat-broker-config/update/', views_heartbeat_config.heartbeat_broker_config_put, name='heartbeat-broker-config-put'),

    # 记忆隔离接口（freeark_lobster_memory_isolation，REQ-FUNC-017）
    path('memory/me/', memory_views.MyMemoryView.as_view(), name='memory-me'),
    path('admin/memory/<int:user_id>/', memory_views.AdminMemoryView.as_view(), name='admin-memory-user'),
    path('memory/session/<str:session_key>/', memory_views.SessionDeleteView.as_view(), name='memory-session-delete'),

    # 故障管理接口（v0.6.0-FM，FR-FM-05）
    path('devices/fault-events/', views_fault.fault_event_list, name='fault-event-list'),
    path('devices/fault-event-categories/', views_fault.fault_event_categories, name='fault-event-categories'),

    # 结露预警接口（v0.7.0-CW，MOD-BE-CW-06）
    path('devices/condensation-warning-events/', views_condensation.condensation_warning_event_list, name='condensation-warning-event-list'),
]

# 追加 RAG 路由（v1.4.0_sanheng_rag，不修改上方现有路由）
urlpatterns += _rag_router.urls