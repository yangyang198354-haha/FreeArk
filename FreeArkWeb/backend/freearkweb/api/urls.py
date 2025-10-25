from django.urls import path
from . import views

urlpatterns = [
    # 用户认证相关路由
    path('auth/login/', views.user_login, name='user-login'),
    path('auth/logout/', views.user_logout, name='user-logout'),
    path('auth/me/', views.get_current_user, name='get-current-user'),
    path('auth/register/', views.user_register, name='user-register'),
    
    # 管理员用户管理路由
    path('users/', views.UserList.as_view(), name='user-list'),
    path('users/<int:pk>/', views.UserDetail.as_view(), name='user-detail'),
    path('users/create/', views.AdminUserCreate.as_view(), name='admin-user-create'),
    

    
    # 健康检查
    path('health/', views.health_check, name='health-check'),
    
    # 日志测试
    path('test_logging/', views.test_logging, name='test-logging'),
    
    # 用量数据查询
    path('usage/quantity/', views.get_usage_quantity, name='get-usage-quantity'),
]