import calendar
import logging
import subprocess
from datetime import date, timedelta
from django.utils.timezone import now as django_now
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from django.db.models import Min, Max, Count, Case, When, IntegerField, Sum, Subquery, OuterRef, Q
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from .models import CustomUser, UsageQuantityDaily, UsageQuantityMonthly, PLCConnectionStatus, PLCStatusChangeHistory, OwnerInfo, PLCLatestData, DeviceConfig, DeviceParamHistory, ScreenConnectivityStatus, TokenActivity
from .utils_room_filter import (  # v0.5.7: 房型过滤工具
    get_available_sub_types,
    get_allowed_param_names,
    invalidate_room_filter_cache,
    SYSTEM_LEVEL_SUB_TYPES,
)
from .serializers import (
    UserSerializer,
    UserRegistrationSerializer, UserLoginSerializer, UserCreateSerializer,
    UsageQuantityDailySerializer, UsageQuantityMonthlySerializer,
    PLCConnectionStatusSerializer, OwnerInfoSerializer,
    PLCLatestDataParamSerializer,
    DeviceParamHistorySerializer,
)

# 获取logger实例
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 看板接口短期缓存装饰器（perf-P0；perf-P2：增加 Redis 降级兜底）
# ---------------------------------------------------------------------------
# 背景：树莓派经 wlan0 → 远程 MySQL(192.168.31.98)，单次 DB 往返实测 ~24ms 且会
#   间歇尖刺；看板多数接口需多次往返，叠加单 worker(--workers 1) 串行，慢接口会
#   占住 worker 致其余请求排队（实测 401 排队 10~60s）。看板数据非强实时，
#   对慢接口加 30s 进程内缓存可大幅削减重复往返与排队。
# 实现（perf-P2 更新）：后端换为 Redis（django.core.cache.backends.redis.RedisCache），
#   settings.py 的 CACHES 生产分支改 Redis；测试分支仍 DummyCache，行为不变。
#   鉴权在 @api_view/@permission_classes 层完成，早于本装饰器，故 401 不会命中缓存。
#   仅缓存 HTTP 200 成功响应；带查询参数的接口需 vary_params=True 以参数入键。
# 降级兜底（perf-P2 新增）：Django 内置 RedisCache 不支持 IGNORE_EXCEPTIONS，
#   因此在装饰器层对 cache.get/set 加 try/except 捕获所有 Redis 异常。
#   Redis 不可用时：get 返回 None（缓存未命中），set 静默忽略，接口正常返回。
#   不会因 Redis 故障导致 HTTP 500，看板退化为无缓存直查模式。
import functools
from urllib.parse import urlencode
from django.core.cache import cache

_cache_logger = logging.getLogger(__name__)  # logging 已在文件顶部导入


def cache_dashboard(ttl=30, prefix=None, vary_params=False):
    def decorator(view_fn):
        @functools.wraps(view_fn)
        def wrapper(request, *args, **kwargs):
            key = 'dash:' + (prefix or view_fn.__name__)
            if vary_params:
                key += ':' + urlencode(sorted(request.query_params.items()))
            # perf-P2：Redis 降级兜底 — get 失败视为缓存未命中，不中断请求
            try:
                cached = cache.get(key)
            except Exception as _cache_exc:
                _cache_logger.warning(
                    'cache_dashboard: Redis get 失败（降级为直查）: %s', _cache_exc
                )
                cached = None
            if cached is not None:
                return Response(cached)
            resp = view_fn(request, *args, **kwargs)
            if getattr(resp, 'status_code', None) == 200:
                # perf-P2：Redis 降级兜底 — set 失败静默忽略，不影响响应
                try:
                    cache.set(key, resp.data, ttl)
                except Exception as _cache_exc:
                    _cache_logger.warning(
                        'cache_dashboard: Redis set 失败（降级为无缓存）: %s', _cache_exc
                    )
            return resp
        return wrapper
    return decorator

# 获取CSRF token的视图函数
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_csrf_token(request):
    """获取CSRF token，同时在响应体和cookies中返回token值"""
    # 导入get_token函数，确保CSRF token被生成
    from django.middleware.csrf import get_token
    from django.conf import settings
    
    # 调用get_token确保token已生成并设置到cookie中
    csrf_token = get_token(request)
    
    # 创建响应对象
    response = Response({"status": "success", "csrftoken": csrf_token}, status=status.HTTP_200_OK)
    
    # 显式地将CSRF token设置到响应的cookies中
    # 这样前端就能从response cookies中获取到token
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=settings.CSRF_COOKIE_HTTPONLY,
        secure=settings.CSRF_COOKIE_SECURE,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        max_age=settings.CSRF_COOKIE_AGE if hasattr(settings, 'CSRF_COOKIE_AGE') else None,
        path=settings.CSRF_COOKIE_PATH if hasattr(settings, 'CSRF_COOKIE_PATH') else '/',
        domain=settings.CSRF_COOKIE_DOMAIN if hasattr(settings, 'CSRF_COOKIE_DOMAIN') else None,
    )
    
    return response

# 自定义权限类
class IsAdminOrReadOnly(permissions.BasePermission):
    """管理员可以编辑，其他人只读"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == 'admin'

class IsAdminUser(permissions.BasePermission):
    """只允许管理员访问"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'

class IsOperatorOrAbove(permissions.BasePermission):
    """v1.6.0: 允许 admin 和 operator（运维人员）访问，拒绝 user（普通业主）与匿名用户。

    用于业务数据接口的角色级保护——业主角色（role='user'）不得访问任何设备/能耗/业主数据。
    与全局 UserRoleApiGuardMiddleware 形成双重保障（中间件兜底拦截 user，权限类显式声明意图）。
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) in ('admin', 'operator')
        )


class IsOwnerUser(permissions.BasePermission):
    """v1.8.0: 仅允许 role='user'（普通业主）且已登录的用户访问。

    用于 /api/miniapp/ 命名空间端点的精细权限控制。
    admin/operator 不满足此权限类（由各自权限类保护，不经此类）。
    与 UserRoleApiGuardMiddleware 的 /api/miniapp/ 放行配合使用：
      中间件放行整个命名空间 → 各端点通过 IsOwnerUser 确认只有 role=user 可访问。
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) == 'user'
        )


# 用户相关视图
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@csrf_exempt
def user_login(request):
    """用户登录视图"""
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        login(request, user)
        
        # 创建或获取Token
        token, created = Token.objects.get_or_create(user=user)

        # "7天内保持登录"：前端勾选时传 remember_me=True，决定会话超时阈值
        remember_me = bool(request.data.get('remember_me', False))

        # REQ-AUTH-001 (v0.9.0): 登录时强制初始化/重置活动时间戳（绕过节流）
        # 同步按 remember_me 重置 extended_session（每次登录依当前勾选状态覆盖）
        TokenActivity.objects.update_or_create(
            token=token,
            defaults={
                'last_active_at': django_now(),
                'extended_session': remember_me,
            },
        )

        return Response({
            'success': True,
            'token': token.key,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def user_logout(request):
    """用户登出视图"""
    # 删除Token
    if request.user.is_authenticated:
        Token.objects.filter(user=request.user).delete()
    logout(request)
    return Response({'success': True, 'message': '成功登出'})

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_current_user(request):
    """获取当前登录用户信息"""
    user = request.user
    return Response({
        'success': True,
        'data': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'department': user.department,
            'position': user.position
        }
    })

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def user_register(request):
    """用户注册视图"""
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        # 自动登录新注册的用户
        login(request, user)
        # 创建Token
        token, created = Token.objects.get_or_create(user=user)

        # REQ-AUTH-001 (v0.9.0): 注册时同步初始化活动时间戳（绕过节流）
        TokenActivity.objects.update_or_create(
            token=token,
            defaults={'last_active_at': django_now()},
        )

        return Response({
            'success': True,
            'token': token.key,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role
            }
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 管理员用户管理视图
class UserList(generics.ListAPIView):
    """用户列表视图（仅管理员）"""
    permission_classes = [IsAdminUser]
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

class UserDetail(generics.RetrieveUpdateDestroyAPIView):
    """用户详情视图（仅管理员）"""
    permission_classes = [IsAdminUser]
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    
    def update(self, request, *args, **kwargs):
        try:
            logger.debug("更新用户请求数据: %s", request.data)
            response = super().update(request, *args, **kwargs)
            return response
        except Exception as e:
            logger.debug("更新用户错误: %s", str(e))
            if hasattr(e, 'detail'):
                logger.debug("序列化器错误详情: %s", e.detail)
            raise

class AdminUserCreate(generics.CreateAPIView):
    """管理员创建用户视图"""
    permission_classes = [IsAdminUser]
    serializer_class = UserCreateSerializer
    
    def create(self, request, *args, **kwargs):
        try:
            # 检查用户名是否已存在
            username = request.data.get('username')
            if username and CustomUser.objects.filter(username=username).exists():
                return Response(
                    {'error': f'用户名 "{username}" 已存在，请选择其他用户名', 'success': False},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # 调用父类方法创建用户
            response = super().create(request, *args, **kwargs)
            
            # 确保响应数据包含id字段，与前端期望的格式匹配
            user_data = response.data
            if user_data and 'id' not in user_data:
                # 获取刚创建的用户对象
                created_user = CustomUser.objects.get(username=user_data.get('username'))
                user_data['id'] = created_user.id
            
            # 格式化成功响应 - 直接返回user_data以匹配前端期望
            return Response(user_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            # 记录错误日志
            logger.error(f"创建用户异常: {str(e)}")
            
            # 检查是否是用户名重复错误
            if 'Duplicate entry' in str(e) and 'for key' in str(e):
                # 尝试提取重复的用户名
                username_match = str(e).split("'")[1] if "'" in str(e) else username
                return Response(
                    {'error': f'用户名 "{username_match}" 已存在，请选择其他用户名', 'success': False},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 返回友好的错误信息
            return Response(
                {'error': str(e), 'message': '创建用户时发生错误', 'success': False},
                status=status.HTTP_400_BAD_REQUEST
            )

# 健康检查接口保持不变

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    """健康检查接口（允许未认证访问）"""
    logger.info('健康检查API被调用')
    return Response({'status': 'ok', 'message': 'FreeArk Web API 服务正常运行'})



@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_usage_quantity(request):
    """
    获取能耗日用量报表数据（原有端点，保持不变）
    """
    # 获取查询参数
    specific_part = request.GET.get('specific_part')
    energy_mode = request.GET.get('energy_mode')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    
    # 记录查询条件到日志
    logger.info(f"能耗日用量报表查询条件 - specific_part: {specific_part}, energy_mode: {energy_mode}, "
                f"start_time: {start_time}, end_time: {end_time}")
    
    # 构建基础查询集
    queryset = UsageQuantityDaily.objects.all()
    
    # 应用过滤条件
    if specific_part:
        queryset = queryset.filter(specific_part=specific_part)
    if energy_mode:
        queryset = queryset.filter(energy_mode=energy_mode)
    if start_time:
        queryset = queryset.filter(time_period__gte=start_time)
    if end_time:
        queryset = queryset.filter(time_period__lte=end_time)
    
    # 按时间升序排序
    queryset = queryset.order_by('time_period')
    
    # 处理分页
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    
    # 计算分页范围
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_data = queryset[start_index:end_index]
    
    # 序列化数据
    serializer = UsageQuantityDailySerializer(paginated_data, many=True)
    total_count = queryset.count()
    
    return Response({
        'success': True,
        'data': serializer.data,
        'total': total_count
    })


@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_usage_quantity_specific_time_period(request):
    """
    获取能耗报表数据（新端点）
    根据楼栋-单元-户号，供能模式，把包含在指定时间段的数据过滤出来，计算这段时间的用量综合
    """
    # 获取查询参数
    specific_part = request.GET.get('specific_part')
    energy_mode = request.GET.get('energy_mode')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    
    # 记录查询条件到日志
    logger.info(f"能耗报表查询条件 - specific_part: {specific_part}, energy_mode: {energy_mode}, "
                f"start_time: {start_time}, end_time: {end_time}")
    
    # 构建基础查询集
    queryset = UsageQuantityDaily.objects.all()
    
    # 应用过滤条件
    if specific_part:
        queryset = queryset.filter(specific_part=specific_part)
    # 确保严格应用供能模式过滤，避免显示不符合选择模式的记录
    if energy_mode:
        queryset = queryset.filter(energy_mode=energy_mode)
        logger.info(f"应用供能模式过滤: {energy_mode}")
    if start_time:
        queryset = queryset.filter(time_period__gte=start_time)
    if end_time:
        queryset = queryset.filter(time_period__lte=end_time)
    
    # 按专有部分和供能模式分组，计算每个组的初期能耗最小值、末期能耗最大值

    # 从已过滤的查询集中严格获取符合条件的(specific_part, energy_mode)组合
    unique_combinations = list(queryset.values('specific_part', 'energy_mode').distinct())
    logger.info(f"过滤后获取的组合数量: {len(unique_combinations)}")
    
    # 按专有部分和供能模式升序排序组合列表
    unique_combinations.sort(key=lambda x: (x['specific_part'], x['energy_mode']))
    
    # 按时间升序排序（用于后续计算）
    queryset = queryset.order_by('time_period')
    
    # 处理分页：先对组合列表进行分页
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    
    # 计算分页范围
    total_count = len(unique_combinations)
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_combinations = unique_combinations[start_index:end_index]
    
    result_data = []
    
    for combination in paginated_combinations:
        # 严格过滤当前组合的数据，确保只获取符合条件的特定组合数据
        combo_queryset = queryset.filter(
            specific_part=combination['specific_part'],
            energy_mode=combination['energy_mode']
        )

        # 获取该组合的第一个building、unit、room_number作为展示数据
        first_record = combo_queryset.first()
        
        # 设置组合的基本信息
        combination['building'] = first_record.building if first_record else ''
        combination['unit'] = first_record.unit if first_record else ''
        combination['room_number'] = first_record.room_number if first_record else ''
        
        # 计算初期能耗（最小值）和末期能耗（最大值），单次聚合查询
        agg = combo_queryset.aggregate(min_energy=Min('initial_energy'), max_energy=Max('final_energy'))
        initial_energy = agg['min_energy']
        final_energy = agg['max_energy']
        
        # 计算使用量
        usage_quantity = final_energy - initial_energy if initial_energy is not None and final_energy is not None else None
        
        # 构建时间段字符串
        time_period_str = f"{start_time} 至 {end_time}" if start_time and end_time else ""
        
        # 添加到结果数据
        result_data.append({
            'specific_part': combination['specific_part'],
            'building': combination['building'],
            'unit': combination['unit'],
            'room_number': combination['room_number'],
            'energy_mode': combination['energy_mode'],
            'initial_energy': initial_energy,
            'final_energy': final_energy,
            'usage_quantity': usage_quantity,
            'time_period': time_period_str
        })
    
    # 记录查询结果到日志
    logger.info(f"能耗报表查询结果 - 找到 {total_count} 条记录")
    
    return Response({
        'success': True,
        'data': result_data,
        'total': total_count
    })


@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_usage_quantity_monthly(request):
    """
    获取每月用量数据
    支持按多个条件过滤：专有部分、楼栋、单元、房号、功能模式、用量月度
    """
    # 获取查询参数
    specific_part = request.GET.get('specific_part')
    building = request.GET.get('building')
    unit = request.GET.get('unit')
    room_number = request.GET.get('room_number')
    energy_mode = request.GET.get('energy_mode')
    usage_month = request.GET.get('usage_month')
    start_month = request.GET.get('start_month')
    end_month = request.GET.get('end_month')
    
    # 记录查询条件到日志
    logger.info(f"UsageQuantityMonthly 查询条件 - specific_part: {specific_part}, building: {building}, "
                f"unit: {unit}, room_number: {room_number}, energy_mode: {energy_mode}, "
                f"usage_month: {usage_month}, start_month: {start_month}, end_month: {end_month}")
    
    # 构建基础查询集
    queryset = UsageQuantityMonthly.objects.all()
    
    # 应用过滤条件
    if specific_part:
        queryset = queryset.filter(specific_part=specific_part)
    if building:
        queryset = queryset.filter(building=building)
    if unit:
        queryset = queryset.filter(unit=unit)
    if room_number:
        queryset = queryset.filter(room_number=room_number)
    if energy_mode:
        queryset = queryset.filter(energy_mode=energy_mode)
    if usage_month:
        queryset = queryset.filter(usage_month=usage_month)
    if start_month:
        queryset = queryset.filter(usage_month__gte=start_month)
    if end_month:
        queryset = queryset.filter(usage_month__lte=end_month)
    
    # 按专有部分、供能模式、用量月度升序排序
    queryset = queryset.order_by('specific_part', 'energy_mode', 'usage_month')
    
    # 处理分页（使用前端约定的参数名）
    page = int(request.GET.get('page', 1))
    size = int(request.GET.get('page_size', 10))
    
    # 计算分页范围
    start_index = (page - 1) * size
    end_index = start_index + size
    paginated_queryset = queryset[start_index:end_index]
    
    # 序列化数据
    serializer = UsageQuantityMonthlySerializer(paginated_queryset, many=True)
    total_count = queryset.count()
    
    # 记录查询结果到日志
    logger.info(f"UsageQuantityMonthly 查询结果 - 找到 {total_count} 条记录")
    
    return Response({
        'success': True,
        'data': serializer.data,
        'total': total_count
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    """
    修改用户密码
    需要提供当前密码和新密码
    """
    user = request.user
    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')
    
    # 验证参数
    if not current_password or not new_password:
        return Response({
            'success': False,
            'error': '当前密码和新密码不能为空'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # 验证当前密码是否正确
    if not user.check_password(current_password):
        return Response({
            'success': False,
            'error': '当前密码错误'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # 设置新密码
    user.set_password(new_password)
    user.save()
    
    # 记录日志
    logger.info(f"用户 {user.username} 成功修改了密码")
    
    return Response({
        'success': True,
        'message': '密码修改成功'
    })


@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_plc_connection_status(request):
    """
    获取PLC设备连接状态列表
    支持分页、筛选（按楼栋、单元、连接状态）
    """
    # 获取查询参数
    building = request.GET.get('building')
    unit = request.GET.get('unit')
    connection_status = request.GET.get('connection_status')
    
    # 记录查询条件到日志
    logger.info(f"PLC连接状态查询条件 - building: {building}, unit: {unit}, connection_status: {connection_status}")
    
    # 构建基础查询集
    queryset = PLCConnectionStatus.objects.all()
    
    # 应用过滤条件
    if building:
        queryset = queryset.filter(building=building)
    if unit:
        queryset = queryset.filter(unit=unit)
    if connection_status:
        queryset = queryset.filter(connection_status=connection_status)
    
    # 按特定部分排序
    queryset = queryset.order_by('specific_part')
    
    # 处理分页
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 10))
    
    # 计算分页范围
    total_count = queryset.count()
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_data = queryset[start_index:end_index]
    
    # 序列化数据
    serializer = PLCConnectionStatusSerializer(paginated_data, many=True)

    # 计算统计数据 — 单次聚合查询，避免 3 次全表 COUNT
    stats = PLCConnectionStatus.objects.aggregate(
        total_devices=Count('id'),
        online_count=Count(Case(When(connection_status='online', then=1), output_field=IntegerField())),
        offline_count=Count(Case(When(connection_status='offline', then=1), output_field=IntegerField())),
    )
    total_devices = stats['total_devices']
    online_count = stats['online_count']
    offline_count = stats['offline_count']
    online_rate = round((online_count / total_devices) * 100, 2) if total_devices > 0 else 0
    
    return Response({
        'success': True,
        'data': serializer.data,
        'total': total_count,
        'statistics': {
            'online_count': online_count,
            'offline_count': offline_count,
            'total_devices': total_devices,
            'online_rate': online_rate
        }
    })


@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_plc_connection_status_detail(request, specific_part):
    """
    获取单个PLC设备的连接状态详情
    """
    # 记录查询条件到日志
    logger.info(f"PLC连接状态详情查询 - specific_part: {specific_part}")
    
    try:
        # 查询指定specific_part的设备
        plc_status = PLCConnectionStatus.objects.get(specific_part=specific_part)
        
        # 序列化数据
        serializer = PLCConnectionStatusSerializer(plc_status)
        
        return Response({
            'success': True,
            'data': serializer.data
        })
    except PLCConnectionStatus.DoesNotExist:
        # 设备不存在
        return Response({
            'success': False,
            'error': f'未找到特定部分为 {specific_part} 的PLC设备'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        # 其他错误
        logger.error(f"查询PLC连接状态详情时发生错误: {e}", exc_info=True)
        return Response({
            'success': False,
            'error': '查询PLC连接状态详情时发生错误'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_plc_status_change_history(request, specific_part):
    """
    获取单个PLC设备的状态变化历史记录
    """
    # 记录查询条件到日志
    logger.info(f"PLC状态变化历史查询 - specific_part: {specific_part}")
    
    try:
        # 查询指定specific_part的设备状态变化历史，按时间倒序排序
        history_records = PLCStatusChangeHistory.objects.filter(
            specific_part=specific_part
        ).order_by('-change_time')
        
        # 处理分页
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        # 计算分页范围
        total_count = history_records.count()
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_data = history_records[start_index:end_index]
        
        # 构建响应数据
        result_data = []
        for record in paginated_data:
            result_data.append({
                'status': record.status,
                'change_time': record.change_time,
                'building': record.building,
                'unit': record.unit,
                'room_number': record.room_number
            })
        
        return Response({
            'success': True,
            'data': result_data,
            'total': total_count
        })
    except Exception as e:
        # 其他错误
        logger.error(f"查询PLC状态变化历史时发生错误: {e}", exc_info=True)
        return Response({
            'success': False,
            'error': '查询PLC状态变化历史时发生错误'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_bill_list(request):
    """
    获取历史用能数据
    参考ark/billing-managerment/list规范
    """
    try:
        # 从HTTP请求头中提取screenMAC信息
        screen_mac = request.META.get('HTTP_SCREENMAC', '')
        logger.info(f"历史用能数据查询 - screenMac: {screen_mac}")
        
        # 验证screenMAC是否存在
        if not screen_mac:
            logger.error("请求头中缺少screenMAC信息")
            return Response({
                "code": 400,
                "message": "请求头中缺少screenMAC信息",
                "data": []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 使用screenMAC查询owner_info表，获取对应的specific_part
        try:
            owner = OwnerInfo.objects.get(unique_id=screen_mac)
            specific_part = owner.specific_part
            logger.info(f"screenMAC {screen_mac} 对应的specific_part: {specific_part}")
        except OwnerInfo.DoesNotExist:
            logger.error(f"screenMAC {screen_mac} 未找到对应的专有部分信息")
            return Response({
                "code": 404,
                "message": f"screenMAC {screen_mac} 未找到对应的专有部分信息",
                "data": []
            }, status=status.HTTP_404_NOT_FOUND)
        
        # 获取请求参数
        start_date = request.data.get('startDate')
        end_date = request.data.get('endDate')
        energy_type = request.data.get('energyType', '')
        
        logger.info(f"查询参数 - startDate: {start_date}, endDate: {end_date}, energyType: {energy_type}")
        
        # 构建查询集
        queryset = UsageQuantityMonthly.objects.filter(specific_part=specific_part)
        
        # 处理时间格式转换（从YYYYMM到YYYY-MM）
        def format_date(date_str):
            if date_str and len(date_str) == 6:
                try:
                    return f"{date_str[:4]}-{date_str[4:]}"
                except:
                    return date_str
            return date_str
        
        # 应用时间范围过滤
        if start_date:
            # 转换为YYYY-MM格式
            formatted_start_date = format_date(start_date)
            queryset = queryset.filter(usage_month__gte=formatted_start_date)
        if end_date:
            # 转换为YYYY-MM格式
            formatted_end_date = format_date(end_date)
            queryset = queryset.filter(usage_month__lte=formatted_end_date)
        
        # 应用能源类型过滤
        if energy_type in ['制冷', '制热']:
            # 直接使用energy_type作为energy_mode查询条件
            queryset = queryset.filter(energy_mode=energy_type)
        
        # 按用量月度和能源模式排序（先按月份，再按能源模式）
        queryset = queryset.order_by('usage_month', 'energy_mode')
        
        # 不需要分页，直接使用所有数据
        paginated_data = queryset
        
        # 构建响应数据
        result_data = []
        for record in paginated_data:
            # 解析专有部分信息
            parts = record.specific_part.split('-')
            building = parts[0] if len(parts) > 0 else ''
            unit = parts[1] if len(parts) > 1 else ''
            room_number = parts[3] if len(parts) > 3 else ''
            
            # 格式化账单周期
            month_parts = record.usage_month.split('-')
            billing_cycle = f"{month_parts[0]}年{month_parts[1]}月"
            
            # 计算账单日期（使用月末日期）
            year = int(month_parts[0])
            month = int(month_parts[1])
            last_day = calendar.monthrange(year, month)[1]
            billing_date = f"{year}-{month:02d}-{last_day:02d}"
            
            # 计算账单金额
            unit_price = 0.28
            usage_amount = record.usage_quantity or 0
            bill_amount = round(usage_amount * unit_price, 2)
            
            # 构建账单数据
            bill_data = {
                "id": record.id,
                "realestateId": 67754642,
                "familyId": 521697181,
                "familyName": f"{building}栋{unit}单元{room_number}",
                "modeName": record.energy_mode,
                "chargeItems": f"{record.energy_mode}费",
                "usageAmount": str(int(usage_amount)) if usage_amount == int(usage_amount) else str(usage_amount),
                "basicAmount": None,
                "beyondAmount": None,
                "basicPrice": str(unit_price),
                "beyondPrice": None,
                "billingCycle": billing_cycle,
                "billingDate": billing_date,
                "billAmount": f"{bill_amount:.2f}"
            }
            result_data.append(bill_data)
        
        # 构建响应
        response_data = {
            "code": 200,
            "message": "成功",
            "data": result_data
        }
        
        logger.info(f"历史用能数据查询成功 - 找到 {len(result_data)} 条记录")
        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"查询历史用能数据时发生错误: {str(e)}", exc_info=True)
        return Response({
            "code": 500,
            "message": f"查询历史用能数据时发生错误: {str(e)}",
            "data": []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# 看板（Dashboard）API
# ===========================================================================

def _parse_date_param(date_str, param_name):
    """解析日期字符串，严格要求 YYYY-MM-DD 格式，失败时抛出 ValueError"""
    try:
        from datetime import datetime as _dt
        return _dt.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValueError(f"参数 {param_name} 格式非法，请使用 YYYY-MM-DD")


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@cache_dashboard(ttl=30, vary_params=True)
def dashboard_total_energy(request):
    """
    看板 API 1：总电量查询（支持自定义时间段）
    GET /api/dashboard/total-energy/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    若未传参数，默认返回当年数据。
    返回 start_date, end_date, cooling_kwh, heating_kwh, total_kwh
    """
    today = date.today()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    # 参数校验
    if start_date_str:
        try:
            start_date = _parse_date_param(start_date_str, 'start_date')
        except ValueError as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    else:
        start_date = date(today.year, 1, 1)

    if end_date_str:
        try:
            end_date = _parse_date_param(end_date_str, 'end_date')
        except ValueError as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    else:
        end_date = today

    queryset = UsageQuantityDaily.objects.filter(
        time_period__gte=start_date,
        time_period__lte=end_date,
    )

    agg = queryset.aggregate(
        cooling_kwh=Sum(Case(When(energy_mode='制冷', then='usage_quantity'), output_field=IntegerField())),
        heating_kwh=Sum(Case(When(energy_mode='制热', then='usage_quantity'), output_field=IntegerField())),
        total_kwh=Sum('usage_quantity'),
    )

    return Response({
        'success': True,
        'data': {
            'start_date': str(start_date),
            'end_date': str(end_date),
            'cooling_kwh': agg['cooling_kwh'] or 0,
            'heating_kwh': agg['heating_kwh'] or 0,
            'total_kwh': agg['total_kwh'] or 0,
        }
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_summary(request):
    """
    看板 API 2：今日/本月累计用电量
    GET /api/dashboard/summary/
    返回 today_kwh, month_kwh
    """
    today = date.today()
    month_start = date(today.year, today.month, 1)

    today_agg = UsageQuantityDaily.objects.filter(
        time_period=today
    ).aggregate(total=Sum('usage_quantity'))

    month_agg = UsageQuantityDaily.objects.filter(
        time_period__gte=month_start,
        time_period__lte=today,
    ).aggregate(total=Sum('usage_quantity'))

    return Response({
        'success': True,
        'data': {
            'today_kwh': today_agg['total'] or 0,
            'month_kwh': month_agg['total'] or 0,
            'date': str(today),
            'month': today.strftime('%Y-%m'),
        }
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_plc_online_rate(request):
    """
    看板 API 3：PLC 系统运行率
    GET /api/dashboard/plc-online-rate/
    返回 online_count, total_count, rate（百分比，0-100）
    """
    stats = PLCConnectionStatus.objects.aggregate(
        total_count=Count('id'),
        online_count=Count(Case(When(connection_status='online', then=1), output_field=IntegerField())),
    )
    total = stats['total_count'] or 0
    online = stats['online_count'] or 0
    rate = round((online / total) * 100, 2) if total > 0 else 0.0

    return Response({
        'success': True,
        'data': {
            'online_count': online,
            'offline_count': total - online,
            'total_count': total,
            'rate': rate,
        }
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@cache_dashboard(ttl=30)
def dashboard_power_status(request):
    """
    看板 API：系统开机状况统计
    GET /api/dashboard/power-status/
    返回 powered_on_count, total_count, power_on_rate, mode_distribution
    开机判定：PLCConnectionStatus.connection_status='online'
              AND PLCLatestData(param_name='system_switch').value IS NOT NULL AND != 0
    运行模式：PLCLatestData(param_name='operation_mode').value，1=制冷/2=制热/3=通风/4=除湿
    未知模式：powered_on_count - sum(mode 1-4)，包含无记录/value=0/null/超范围（OQ-002）
    """
    # Query 1：总台数（与 dashboard_plc_online_rate 口径一致，OQ-001）
    total_count = PLCConnectionStatus.objects.count()

    # Query 2a：在线设备的 specific_part 集合（走 connection_status 单列索引）
    online_parts_qs = PLCConnectionStatus.objects.filter(
        connection_status='online'
    ).values_list('specific_part', flat=True)

    # Query 2b：开机设备（在线 + system_switch 非零非空）的 specific_part 集合
    # 走 PLCLatestData.(specific_part, param_name) UNIQUE 索引
    switched_on_parts_qs = PLCLatestData.objects.filter(
        specific_part__in=online_parts_qs,
        param_name='system_switch',
        value__isnull=False,
    ).exclude(value=0).values_list('specific_part', flat=True)

    powered_on_count = switched_on_parts_qs.count()

    # 除零安全（OQ-001，AC-104）
    power_on_rate = round((powered_on_count / total_count) * 100, 2) if total_count > 0 else 0.0

    # Query 2c：开机设备的运行模式分布聚合（Case/When，走 UNIQUE 索引）
    mode_agg = PLCLatestData.objects.filter(
        specific_part__in=switched_on_parts_qs,
        param_name='operation_mode',
    ).aggregate(
        cooling=Count(Case(When(value=1, then=1), output_field=IntegerField())),
        heating=Count(Case(When(value=2, then=1), output_field=IntegerField())),
        ventilation=Count(Case(When(value=3, then=1), output_field=IntegerField())),
        dehumidification=Count(Case(When(value=4, then=1), output_field=IntegerField())),
    )

    cooling = mode_agg['cooling'] or 0
    heating = mode_agg['heating'] or 0
    ventilation = mode_agg['ventilation'] or 0
    dehumidification = mode_agg['dehumidification'] or 0
    # 未知模式 = 开机台数 - 四类有效模式之和（OQ-002，可对账：四类+未知==开机台数）
    unknown = powered_on_count - (cooling + heating + ventilation + dehumidification)

    return Response({
        'success': True,
        'data': {
            'powered_on_count': powered_on_count,
            'total_count': total_count,
            'power_on_rate': power_on_rate,
            'mode_distribution': {
                'cooling': cooling,
                'heating': heating,
                'ventilation': ventilation,
                'dehumidification': dehumidification,
                'unknown': unknown,
            }
        }
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_screen_online_rate(request):
    """
    看板 API：大屏在线率
    GET /api/dashboard/screen-online-rate/
    返回 online_count, total_count, rate（百分比，0-100）
    在线标准：last_seen_at 距今 <= ONLINE_THRESHOLD_MINUTES 分钟
    """
    online_cutoff = timezone.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)
    stats = ScreenConnectivityStatus.objects.aggregate(
        total_count=Count('id'),
        online_count=Count(Case(When(last_seen_at__gte=online_cutoff, then=1), output_field=IntegerField())),
    )
    total = stats['total_count'] or 0
    online = stats['online_count'] or 0
    rate = round((online / total) * 100, 2) if total > 0 else 0.0

    return Response({
        'success': True,
        'data': {
            'online_count': online,
            'total_count': total,
            'rate': rate,
        }
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_trend(request):
    """
    看板 API 4：近 N 天用电量趋势
    GET /api/dashboard/trend/?days=7
    返回每天日期 + 用电量（cooling/heating/total）数组
    """
    days_str = request.GET.get('days', '7')
    try:
        days = int(days_str)
        if days <= 0 or days > 365:
            raise ValueError()
    except (ValueError, TypeError):
        return Response(
            {'success': False, 'error': '参数 days 必须为 1-365 之间的正整数'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    today = date.today()
    start_date = today - timedelta(days=days - 1)

    queryset = UsageQuantityDaily.objects.filter(
        time_period__gte=start_date,
        time_period__lte=today,
    ).values('time_period', 'energy_mode').annotate(day_total=Sum('usage_quantity'))

    # 按日期聚合
    day_map = {}
    for row in queryset:
        d = str(row['time_period'])
        if d not in day_map:
            day_map[d] = {'date': d, 'cooling_kwh': 0, 'heating_kwh': 0, 'total_kwh': 0}
        kwh = row['day_total'] or 0
        if row['energy_mode'] == '制冷':
            day_map[d]['cooling_kwh'] += kwh
        elif row['energy_mode'] == '制热':
            day_map[d]['heating_kwh'] += kwh
        day_map[d]['total_kwh'] += kwh

    # 补全无数据的日期（值为 0）
    result = []
    for i in range(days):
        d = str(start_date + timedelta(days=i))
        if d in day_map:
            result.append(day_map[d])
        else:
            result.append({'date': d, 'cooling_kwh': 0, 'heating_kwh': 0, 'total_kwh': 0})

    return Response({
        'success': True,
        'data': result,
    })


# 受监控的 systemctl 服务列表（白名单，防止任意命令注入）
# 服务名与 systemctl/ 目录下的 .service 文件名一一对应
# 受监控 / 受管理的 systemd 单元白名单（v1.2.0：全量纳管 freeark-*，以 Pi
# `systemctl list-unit-files 'freeark-*'` 实测为准；不含非 freeark 的 openclaw-gateway
# 用户服务与 redis-server apt 服务）。仅此白名单内的单元可被服务管理 / 看板查询与操作，
# 兼作命令注入防线（subprocess 以 argv 形式调用，绝不经 shell）。
MONITORED_SERVICES = [
    # ── 常驻守护服务（长期 active running）──────────────────────────────
    'freeark-backend',
    'freeark-mqtt-consumer',
    'freeark-fault-consumer',            # 故障事件写入（事件源）
    'freeark-condensation-consumer',     # 结露预警写入（事件源）
    'freeark-screen-heartbeat',
    'freeark-daily-usage',
    'freeark-monthly-usage',
    'freeark-plc-connection-monitor',
    'freeark-task-scheduler',
    'freeark-inspection-agent',          # v1.1.0 自治巡检 Agent（方案 B，当前可 disabled）
    # ── 定时 / 看护类 .service（多为 static/disabled，由各自 .timer 触发）──
    'freeark-dph-cleanup',
    'freeark-plc-cleanup',
    'freeark-fault-cleanup',
    'freeark-condensation-cleanup',
    'freeark-netwatch',
    'freeark-wifi-watchdog',
    # ── 定时器单元 .timer（is-active=active 表示已排程、等待触发，属正常）──
    'freeark-fault-cleanup.timer',
    'freeark-condensation-cleanup.timer',
    'freeark-netwatch.timer',
    'freeark-wifi-watchdog.timer',
]

# 白名单 Set（O(1) 查询），用于服务管理接口安全校验
_MONITORED_SERVICES_SET = set(MONITORED_SERVICES)

# 服务管理接口允许的操作列表
_ALLOWED_ACTIONS = {'start', 'stop', 'restart', 'status'}


def _get_service_status(service_name):
    """调用 systemctl is-active 获取单个服务的状态，失败时返回 'unknown'"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or 'unknown'
    except Exception:
        return 'unknown'


def _get_service_enabled(service_name):
    """调用 systemctl is-enabled 获取自启动状态（enabled/disabled/static/…）。

    注意：systemctl is-enabled 对 disabled/static 会以非零退出码返回，但状态字符串仍写到
    stdout，故只取 stdout、不看 returncode。失败/超时返回 'unknown'。
    语义：enabled=开机自启；disabled=主动停用；static=由 .timer 触发的 oneshot（无独立自启开关）。
    """
    try:
        result = subprocess.run(
            ['systemctl', 'is-enabled', service_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or 'unknown'
    except Exception:
        return 'unknown'


def _get_service_detail(service_name):
    """
    调用 systemctl status <service_name> 获取详细运行信息。
    返回字典，包含 active_state, sub_state, pid, memory, raw_output 等字段。
    失败时返回含 error 字段的字典。
    """
    try:
        result = subprocess.run(
            ['systemctl', 'status', '--no-pager', '-l', service_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        raw = result.stdout + result.stderr
        # 解析关键字段（简单文本解析，兼容 systemd 各版本输出格式）
        active_state = 'unknown'
        sub_state = 'unknown'
        pid = None
        memory = None
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith('Active:'):
                # 例: "Active: active (running) since ..."
                parts = stripped.split(None, 2)
                if len(parts) >= 2:
                    active_state = parts[1]
                if '(' in stripped:
                    sub_state_part = stripped.split('(')[1].split(')')[0]
                    sub_state = sub_state_part
            elif 'Main PID:' in stripped:
                try:
                    pid = int(stripped.split(':')[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
            elif 'Memory:' in stripped:
                try:
                    memory = stripped.split(':', 1)[1].strip()
                except IndexError:
                    pass
        return {
            'active_state': active_state,
            'sub_state': sub_state,
            'pid': pid,
            'memory': memory,
            'raw_output': raw[:4096],  # 限制原始输出长度
        }
    except subprocess.TimeoutExpired:
        return {'error': 'systemctl status 超时'}
    except Exception as exc:
        return {'error': str(exc)}


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@cache_dashboard(ttl=30)
def dashboard_services(request):
    """
    看板 API 5：系统服务状态
    GET /api/dashboard/services/
    通过 subprocess 调用 systemctl is-active + is-enabled 查询各服务状态。
    返回 services 数组，每项含 name, status, is_active, enabled
    （enabled 供前端做四态语义显示：运行中 / 待机 / 已停用 / 异常，区分定时服务正常待机
      与主动停用，避免把 inactive 一律误报为"已停止"）。
    """
    services = []
    for name in MONITORED_SERVICES:
        svc_status = _get_service_status(name)
        services.append({
            'name': name,
            'status': svc_status,
            'is_active': svc_status == 'active',
            'enabled': _get_service_enabled(name),
        })

    return Response({
        'success': True,
        'data': services,
    })


# ===========================================================================
# 服务管理 API（Service Management）
# ===========================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])  # v1.6.0: 服务管理仅 admin（operator 不可访问）
def service_management_list(request):
    """
    服务管理 API 1：获取所有受监控服务的列表及状态。

    GET /api/services/list/

    响应：
    {
        "success": true,
        "data": [
            {
                "name": "freeark-backend",
                "active_state": "active",
                "sub_state": "running",
                "is_active": true,
                "enabled": true|false|"unknown"
            },
            ...
        ]
    }
    """
    services = []
    for name in MONITORED_SERVICES:
        active_state = _get_service_status(name)
        services.append({
            'name': name,
            'active_state': active_state,
            'sub_state': '',          # 简略列表不展开 sub_state，详情接口再查
            'is_active': active_state == 'active',
            'enabled': _get_service_enabled(name),
        })

    return Response({'success': True, 'data': services})


@api_view(['GET'])
@permission_classes([IsAdminUser])  # v1.6.0: 服务管理仅 admin（operator 不可访问）
def service_management_detail(request, service_name):
    """
    服务管理 API 2：获取单个服务的详细运行信息（systemctl status 输出）。

    GET /api/services/<service_name>/detail/

    安全：service_name 必须在白名单内。
    响应：
    {
        "success": true,
        "name": "freeark-backend",
        "detail": {
            "active_state": "active",
            "sub_state": "running",
            "pid": 1234,
            "memory": "12.0M",
            "raw_output": "..."
        }
    }
    """
    if service_name not in _MONITORED_SERVICES_SET:
        return Response(
            {'success': False, 'error': f'服务 "{service_name}" 不在受管理的服务白名单中'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    detail = _get_service_detail(service_name)
    return Response({'success': True, 'name': service_name, 'detail': detail})


@api_view(['POST'])
@permission_classes([IsAdminUser])  # v1.6.0: 服务管理仅 admin（operator 不可访问）
def service_management_action(request, service_name):
    """
    服务管理 API 3：对指定服务执行 start / stop / restart 操作。

    POST /api/services/<service_name>/action/
    Body: { "action": "start" | "stop" | "restart" }

    安全约束：
    - service_name 必须在白名单 MONITORED_SERVICES 内（防止命令注入）
    - action 必须为 start / stop / restart 之一
    - 需要已登录用户（IsAuthenticated）
    - 执行 sudo systemctl <action> <service_name>（需 sudoers 配置，见部署说明）

    响应：
    {
        "success": true,
        "message": "服务 freeark-backend start 执行成功",
        "new_status": "active"
    }
    """
    # --- 1. 白名单校验：服务名 ---
    if service_name not in _MONITORED_SERVICES_SET:
        logger.warning(
            "service_management_action: 非法服务名 %s，用户 %s",
            service_name, request.user.username,
        )
        return Response(
            {'success': False, 'error': f'服务 "{service_name}" 不在受管理的服务白名单中'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- 2. 白名单校验：操作 ---
    action = request.data.get('action', '').strip().lower()
    if action not in _ALLOWED_ACTIONS - {'status'}:
        # status 不通过此接口，走 detail 接口
        return Response(
            {'success': False, 'error': f'不支持的操作 "{action}"，允许值：start, stop, restart'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- 3. 执行 sudo systemctl <action> <service_name> ---
    logger.info(
        "service_management_action: 用户 %s 对服务 %s 执行 %s",
        request.user.username, service_name, action,
    )
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', action, service_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout or '未知错误').strip()
            logger.error(
                "service_management_action: 执行失败 service=%s action=%s error=%s",
                service_name, action, error_msg,
            )
            return Response(
                {'success': False, 'error': error_msg},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    except subprocess.TimeoutExpired:
        return Response(
            {'success': False, 'error': 'systemctl 操作超时（30s），请稍后重试'},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except Exception as exc:
        logger.error("service_management_action: 执行异常 %s", exc, exc_info=True)
        return Response(
            {'success': False, 'error': str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # --- 4. 查询操作后的最新状态 ---
    new_status = _get_service_status(service_name)
    return Response({
        'success': True,
        'message': f'服务 {service_name} {action} 执行成功',
        'new_status': new_status,
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_activities(request):
    """
    看板 API 6：最近活动
    GET /api/dashboard/activities/?limit=20
    返回：当前用户的操作日志（PLCStatusChangeHistory）+ 系统服务运行事件（占位）
    合并后按时间倒序返回最近 limit 条。
    """
    limit_str = request.GET.get('limit', '20')
    try:
        limit = int(limit_str)
        if limit <= 0 or limit > 200:
            raise ValueError()
    except (ValueError, TypeError):
        return Response(
            {'success': False, 'error': '参数 limit 必须为 1-200 之间的正整数'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 从 PLCStatusChangeHistory 取最近 PLC 状态变化事件
    plc_events = PLCStatusChangeHistory.objects.order_by('-change_time')[:limit]
    activities = []
    for event in plc_events:
        label = '上线' if event.status == 'online' else '离线'
        activities.append({
            'type': 'plc_status',
            'timestamp': event.change_time.strftime('%Y-%m-%d %H:%M:%S'),
            'message': f"PLC {event.specific_part} {label}",
            'detail': {
                'specific_part': event.specific_part,
                'status': event.status,
                'building': event.building,
                'unit': event.unit,
                'room_number': event.room_number,
            },
        })

    # 按时间倒序截取 limit 条
    activities = activities[:limit]

    return Response({
        'success': True,
        'data': activities,
        'total': len(activities),
    })


# ===========================================================================
# 看板 — 故障汇总 API（v1.0.0-DASHBOARD-REDESIGN）
# ===========================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@cache_dashboard(ttl=30)
def dashboard_fault_summary(request):
    """GET /api/dashboard/fault-summary/
    返回当前未恢复故障总数及影响户数（specific_part 去重计数）。
    REQ-FUNC-DC-01 / US-DC-01
    """
    try:
        from .models import FaultEvent
        # perf-P0：单次聚合（COUNT(*) + COUNT(DISTINCT specific_part)）替代 2 次 DB 往返
        agg = FaultEvent.objects.filter(is_active=True).aggregate(
            active_fault_count=Count('id'),
            affected_unit_count=Count('specific_part', distinct=True),
        )
        return Response({
            'success': True,
            'data': {
                'active_fault_count': agg['active_fault_count'],
                'affected_unit_count': agg['affected_unit_count'],
            }
        })
    except Exception as e:
        logger.error('dashboard_fault_summary error: %s', str(e))
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@cache_dashboard(ttl=30)
def dashboard_device_fault_summary(request):
    """GET /api/dashboard/device-fault-summary/
    一次返回四类子设备的 total（DeviceNode 按 product_code）
    和 fault_count（FaultEvent is_active=True 且 product_code 匹配的记录条数）。

    注意：FaultEvent 无 sub_type 字段；通过 product_code 过滤与 DeviceNode.total 口径一致。
    温控面板含 product_code=120003（各房间温控面板）和 product_code=260001（客厅主温控）。

    REQ-FUNC-DC-02~06
    """
    try:
        from .models import FaultEvent, DeviceNode

        # perf-P0：用 2 次 GROUP BY 聚合替代原 8 次独立 COUNT，削减 DB 往返
        #（树莓派 wlan0→远程 MySQL 单次往返 ~24ms，8 次往返是该接口慢的主因）。
        GROUPS = {
            'air_quality_sensor': ['100007'],
            'thermostat_panels':  ['120003', '260001'],
            'fresh_air_unit':     ['130004'],
            'hydraulic_module':   ['270001'],
        }
        all_codes = [c for codes in GROUPS.values() for c in codes]

        node_counts = dict(
            DeviceNode.objects.filter(product_code__in=all_codes)
            .values_list('product_code').annotate(n=Count('id'))
        )
        fault_counts = dict(
            FaultEvent.objects.filter(product_code__in=all_codes, is_active=True)
            .values_list('product_code').annotate(n=Count('id'))
        )

        data = {
            group: {
                'total': sum(node_counts.get(c, 0) for c in codes),
                'fault_count': sum(fault_counts.get(c, 0) for c in codes),
            }
            for group, codes in GROUPS.items()
        }

        return Response({'success': True, 'data': data})
    except Exception as e:
        logger.error('dashboard_device_fault_summary error: %s', str(e))
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# 业主信息管理 API
# ===========================================================================

class OwnerListCreateView(generics.ListCreateAPIView):
    """
    业主信息列表与创建视图
    GET  /api/owners/  — 分页列表，支持过滤（all users）
    POST /api/owners/  — 创建新记录（admin only）
    """
    serializer_class = OwnerInfoSerializer

    def get_permissions(self):
        # v1.6.0: 业主信息管理对 admin+operator 全量 CRUD 开放（OQ-02 已确认）；
        # user（业主）由 UserRoleApiGuardMiddleware 兜底拦截。
        return [IsOperatorOrAbove()]

    def get_queryset(self):
        from django.db.models import Q, Count
        queryset = OwnerInfo.objects.all().order_by('building', 'unit', 'room_number')
        building = self.request.GET.get('building')
        unit = self.request.GET.get('unit')
        search = self.request.GET.get('search')
        if building:
            queryset = queryset.filter(building=building)
        if unit:
            queryset = queryset.filter(unit=unit)
        if search:
            queryset = queryset.filter(
                Q(specific_part__icontains=search) |
                Q(location_name__icontains=search) |
                Q(room_number__icontains=search)
            )
        # US-02: 房间数量（跨 DeviceFloor→DeviceRoom，COUNT DISTINCT 避免重复）
        queryset = queryset.annotate(room_count=Count('floors__rooms', distinct=True))
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        total = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        serializer = self.get_serializer(queryset[start:end], many=True)
        return Response({
            'success': True,
            'data': serializer.data,
            'total': total,
            'page': page,
            'page_size': page_size,
        })

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'data': serializer.data}, status=status.HTTP_201_CREATED)
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class OwnerRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    业主信息详情、更新、删除视图
    GET    /api/owners/<id>/  — 详情（all users）
    PUT    /api/owners/<id>/  — 全量更新（admin only）
    PATCH  /api/owners/<id>/  — 部分更新（admin only）
    DELETE /api/owners/<id>/  — 删除（admin only）
    """
    queryset = OwnerInfo.objects.all()
    serializer_class = OwnerInfoSerializer

    def get_permissions(self):
        # v1.6.0: 业主信息管理对 admin+operator 全量 CRUD 开放（OQ-02 已确认）；
        # user（业主）由 UserRoleApiGuardMiddleware 兜底拦截。
        return [IsOperatorOrAbove()]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({'success': True, 'data': serializer.data})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'data': serializer.data})
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({'success': True, 'message': '删除成功'}, status=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# US-03: 业主设备树查看 API
# ===========================================================================

class OwnerDeviceTreeView(generics.RetrieveAPIView):
    """
    GET /api/owners/<pk>/device-tree/
    返回指定业主的完整设备树：楼层 → 房间 → 设备
    权限：IsOperatorOrAbove（admin/operator 可见全部业主）
    """
    queryset = OwnerInfo.objects.prefetch_related(
        'floors__rooms__devices'
    )
    permission_classes = [IsOperatorOrAbove]  # v1.6.0: 业主设备树对 admin+operator 开放

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        floors_data = []
        for floor in instance.floors.all():
            rooms_data = []
            for room in floor.rooms.all():
                devices_data = [
                    {
                        'device_sn': dev.device_sn,
                        'device_name': dev.device_name,
                        'system_flag': dev.system_flag,
                        'product_code': dev.product_code,
                        'category_code': dev.category_code,
                    }
                    for dev in room.devices.all()
                ]
                rooms_data.append({
                    'room_name': room.room_name,
                    'ori_room_name': room.ori_room_name,
                    'room_type': room.room_type,
                    'devices': devices_data,
                })
            floors_data.append({
                'floor_no': floor.floor_no,
                'floor_name': floor.floor_name,
                'rooms': rooms_data,
            })
        return Response({
            'success': True,
            'data': {
                'id': instance.id,
                'specific_part': instance.specific_part,
                'location_name': instance.location_name,
                'floors': floors_data,
            }
        })


# ===========================================================================
# PLC 最新参数数据 API
# ===========================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_plc_latest_data(request):
    """
    查询 PLCLatestData 表中的最新参数值。

    GET /api/plc-latest/?specific_part=3-1-7-702
        返回该专有部分所有参数的最新值列表。

    GET /api/plc-latest/?specific_part=3-1-7-702&param_name=living_room_temperature
        返回该专有部分指定参数的最新值。

    响应格式：
    {
        "specific_part": "3-1-7-702",
        "params": [
            {"param_name": "living_room_temperature", "value": 245, "collected_at": "2026-04-18 10:42:55"},
            ...
        ]
    }
    """
    specific_part = request.GET.get('specific_part', '').strip()
    param_name = request.GET.get('param_name', '').strip()

    if not specific_part:
        return Response(
            {'detail': '参数 specific_part 为必填项'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = PLCLatestData.objects.filter(specific_part=specific_part)

    if param_name:
        qs = qs.filter(param_name=param_name)

    qs = qs.order_by('param_name')

    serializer = PLCLatestDataParamSerializer(qs, many=True)
    return Response({
        'specific_part': specific_part,
        'params': serializer.data,
    })


# ===========================================================================
# 非专有部分设备实时参数卡片 API  (REQ-FUNC-033)
# ===========================================================================



@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_device_realtime_params(request):
    """
    GET /api/devices/realtime-params/?specific_part=9-1-31-3104[&group=hvac]
    返回指定专有部分的设备实时参数，按 group -> sub_type -> params 嵌套结构。

    Query params:
      specific_part (str, required) — 住宅专有部分标识，如 9-1-31-3104
      group         (str, optional) — 过滤指定设备分组（如 hvac）
    """
    from datetime import datetime as _dt, timedelta as _td

    specific_part = request.GET.get('specific_part', '').strip()
    if not specific_part:
        return Response(
            {'success': False, 'error': 'specific_part 参数为必填项'},
            status=400,
        )

    group_filter = request.GET.get('group', '').strip()

    # 查询该专有部分的所有最新 PLC 参数（一次批量查询）
    latest_data_qs = PLCLatestData.objects.filter(specific_part=specific_part)

    # 构建 param_name -> PLCLatestData 记录的映射
    latest_by_param = {record.param_name: record for record in latest_data_qs}

    # 查询激活的 DeviceConfig（param_name -> group/sub_type 的映射表）
    # order_by('id') 保证子面板顺序与 seed_device_config 插入顺序一致
    configs_qs = DeviceConfig.objects.filter(is_active=True).order_by('id')
    if group_filter:
        configs_qs = configs_qs.filter(group=group_filter)

    # v0.5.7 M2: 查询该专有部分可用的 sub_type 集合（带 300s 缓存）
    # 设备树未同步时降级为仅系统级面板（方案 B，PM OQ-v0.5.7-02 已锁定）
    available_sub_types = get_available_sub_types(specific_part)

    # 超过此阈值未更新的参数标记为 is_stale=True
    _STALE_MINUTES = 10
    _stale_cutoff = _dt.now() - _td(minutes=_STALE_MINUTES)

    # 构建嵌套响应结构：group -> sub_type -> params
    result = {}
    for cfg in configs_qs:
        group_key = cfg.group
        sub_key = cfg.sub_type

        # v0.5.7 M2: 跳过不属于该专有部分房型的温控面板 sub_type
        if sub_key not in available_sub_types:
            continue

        if group_key not in result:
            result[group_key] = {
                'display': cfg.group_display,
                'sub_types': {},
            }
        if sub_key not in result[group_key]['sub_types']:
            result[group_key]['sub_types'][sub_key] = {
                'display': cfg.sub_type_display,
                'params': [],
            }

        # 在当前专有部分的 PLCLatestData 中查找该 param_name 的记录
        record = latest_by_param.get(cfg.param_name)
        if record is None:
            # 该参数在此专有部分暂无数据，跳过（只展示有数据的参数）
            continue

        is_stale = bool(record.collected_at and record.collected_at < _stale_cutoff)
        result[group_key]['sub_types'][sub_key]['params'].append({
            'param_name': cfg.param_name,
            'display_name': cfg.display_name,
            'value': record.value,
            'collected_at': record.collected_at.strftime('%Y-%m-%d %H:%M:%S') if record.collected_at else None,
            'is_stale': is_stale,
        })

    # 移除没有任何参数数据的 sub_type，保持响应整洁
    for group_key in list(result.keys()):
        sub_types = result[group_key]['sub_types']
        empty_subs = [k for k, v in sub_types.items() if not v['params']]
        for sub_key in empty_subs:
            del sub_types[sub_key]
        if not sub_types:
            del result[group_key]

    return Response({'success': True, 'specific_part': specific_part, 'data': result})


# ===========================================================================
# 非专有部分设备历史参数查询 API  (REQ-FUNC-034)
# ===========================================================================

@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])  # v1.6.0: 仅 admin/operator（匿名与业主均拒，OQ/AC-4.4）
def get_device_param_history(request):
    """
    GET /api/devices/param-history/?specific_part=9-1-31-3104[&sub_type=main_thermostat][&param_name=living_room_temperature]
    返回指定专有部分的历史参数记录，按 collected_at 倒序分页。

    Query params:
      specific_part (str, required)  — 住宅专有部分标识，如 9-1-31-3104
      sub_type      (str, optional)  — 过滤子类型（通过 DeviceConfig 找到该 sub_type 的 param_name 列表）
      param_name    (str, optional)  — 精确过滤单个参数名称
      start_time    (str, optional)  — 开始时间 YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD
      end_time      (str, optional)  — 结束时间 YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD
      page          (int, default 1)
      page_size     (int, default 50)
    """
    specific_part = request.GET.get('specific_part', '').strip()
    if not specific_part:
        return Response(
            {'success': False, 'error': 'specific_part 参数为必填项'},
            status=400,
        )

    sub_type = request.GET.get('sub_type', '').strip()
    param_name = request.GET.get('param_name', '').strip()
    param_names_raw = request.GET.get('param_names', '').strip()
    start_time = request.GET.get('start_time', '').strip()
    end_time = request.GET.get('end_time', '').strip()
    is_chart = request.GET.get('chart', '').lower() == 'true'

    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = max(1, min(500, int(request.GET.get('page_size', 50))))
    except (ValueError, TypeError):
        page_size = 50

    qs = DeviceParamHistory.objects.filter(specific_part=specific_part)

    if param_name:
        qs = qs.filter(param_name=param_name)
    elif param_names_raw:
        pnames = [p.strip() for p in param_names_raw.split(',') if p.strip()]
        qs = qs.filter(param_name__in=pnames) if pnames else qs.none()
    elif sub_type:
        # 通过 DeviceConfig 查出该 sub_type 下的所有 param_name
        sub_type_params = list(
            DeviceConfig.objects.filter(sub_type=sub_type, is_active=True)
            .values_list('param_name', flat=True)
        )
        if sub_type_params:
            qs = qs.filter(param_name__in=sub_type_params)
        else:
            qs = qs.none()

    if start_time:
        qs = qs.filter(collected_at__gte=start_time)
    if end_time:
        qs = qs.filter(collected_at__lte=end_time)

    # 图表模式：返回全量数据（按时间正序，上限 10000 条），不分页
    if is_chart:
        qs = qs.order_by('collected_at')
        results = list(qs[:10000])
        serializer = DeviceParamHistorySerializer(results, many=True)
        return Response({
            'success': True,
            'specific_part': specific_part,
            'count': len(results),
            'results': serializer.data,
        })

    qs = qs.order_by('-collected_at')

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    page_qs = qs[start:end]

    serializer = DeviceParamHistorySerializer(page_qs, many=True)
    return Response({
        'success': True,
        'specific_part': specific_part,
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': serializer.data,
    })


# ---------------------------------------------------------------------------
# MOD-BE-01 — 设备管理：设备列表接口
# REQ-FUNC-001~005, US-002~007, NFR-001~003
# ---------------------------------------------------------------------------

# 大屏在线判断阈值（分钟）：last_seen_at 距今超过此值则视为离线
ONLINE_THRESHOLD_MINUTES = 15


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def device_management_device_list(request):
    """
    GET /api/device-management/device-list/

    返回本小区所有专有部分的设备列表，支持五维过滤与分页。

    大屏在线判断基于心跳：last_seen_at 距今 <= ONLINE_THRESHOLD_MINUTES 分钟 → online，
    否则 offline；ScreenConnectivityStatus 中无记录 → unknown。

    PLC 状态来自 PLCConnectionStatus 表，通过 specific_part LEFT JOIN。
    PLCConnectionStatus 无记录 → plc_status='unknown'。

    Query 参数：
      room_no        (str, 可选)  — 三段格式，如 "3-1-702"，1~3 段均可
      screen_status  (str, 可选)  — "online" | "offline" | "unknown"
      system_switch  (str, 可选)  — "on" | "off"
      plc_status     (str, 可选)  — "online" | "offline"
      fault_status   (str, 可选)  — "has_fault" | "no_fault"（Python 层全量过滤，ADR-FFF-001）
                                    has_fault: fault_count > 0；no_fault: fault_count == 0；
                                    fault_count=None 在两侧均排除（ADR-FFF-003）
      page           (int, 可选)  — 默认 1
      page_size      (int, 可选)  — 分页 UI 通常用 10/20/50，上限 cap 至 50，默认 20

    响应 200：
      {
        "count": <int>,
        "page": <int>,
        "page_size": <int>,
        "results": [ {
          "specific_part": <str>,
          "building": <str>,
          "unit": <str>,
          "room_number": <str>,
          "screen_status": "online"|"offline"|"unknown",
          "screen_last_seen_at": <str|null>,
          "system_switch_value": <int|null>,
          "system_switch_display": "开"|"关"|"未知",
          "operation_mode_value": <int|null>,
          "operation_mode_display": "制冷"|"制热"|"通风"|"除湿"|"未知",
          "plc_status": "online"|"offline"|"unknown",
          "plc_last_online_time": <str|null>
        } ]
      }
    """
    # ---- 1. 解析过滤参数 ----
    room_no = request.GET.get('room_no', '').strip()
    screen_status_filter = request.GET.get('screen_status', '').strip().lower()
    system_switch_filter = request.GET.get('system_switch', '').strip().lower()
    plc_status_filter = request.GET.get('plc_status', '').strip().lower()
    operation_mode_filter = request.GET.get('operation_mode', '').strip()
    # REQ-FUNC-FFF-02: 故障状态过滤（ADR-FFF-001 Python 层全量过滤）
    fault_status_filter = request.GET.get('fault_status', '').strip().lower()
    if fault_status_filter not in ('has_fault', 'no_fault'):
        fault_status_filter = ''

    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        # 分页 UI 通常使用 10/20/50，上限 50 条
        page_size = max(1, min(50, int(request.GET.get('page_size', 20))))
    except (ValueError, TypeError):
        page_size = 20

    # ---- 2. 基础查询集（OwnerInfo 全量，按 building/unit/room_number 升序）----
    qs = OwnerInfo.objects.all().order_by('building', 'unit', 'room_number')

    # ---- 3. 房号过滤（三段解析，ADR-005）----
    if room_no:
        parts = room_no.split('-')
        # 过滤非法字符（每段只允许数字/字母，最多3段）
        if len(parts) > 3 or any(not p.strip() for p in parts):
            return Response(
                {'error': 'room_no 格式非法，期望 1~3 段数字，如 3-1-702'},
                status=400,
            )
        try:
            if len(parts) >= 1 and parts[0]:
                b = parts[0].strip()
                qs = qs.filter(building__in=[b, f'{b}栋'])
            if len(parts) >= 2 and parts[1]:
                u = parts[1].strip()
                qs = qs.filter(unit__in=[u, f'{u}单元'])
            if len(parts) >= 3 and parts[2]:
                qs = qs.filter(room_number=parts[2].strip())
        except Exception:
            return Response(
                {'error': 'room_no 格式非法，期望 1~3 段数字，如 3-1-702'},
                status=400,
            )

    # ---- 4. Subquery annotate：大屏 last_seen_at（ADR-001）----
    screen_last_seen_sq = Subquery(
        ScreenConnectivityStatus.objects.filter(
            specific_part=OuterRef('specific_part')
        ).values('last_seen_at')[:1]
    )

    # ---- 5. Subquery annotate：系统开关值（ADR-001）----
    # FIX-001: PLCLatestData.building/unit/room_number 在生产 DB 中为空字符串（blank=True, default=''），
    # 改为用 specific_part 直接关联，与 OwnerInfo.specific_part 格式一致（四段）。
    system_switch_sq = Subquery(
        PLCLatestData.objects.filter(
            specific_part=OuterRef('specific_part'),
            param_name='system_switch',
        ).values('value')[:1]
    )

    # ---- 5c. Subquery annotate：运行模式值（REQ-FUNC-002）----
    operation_mode_sq = Subquery(
        PLCLatestData.objects.filter(
            specific_part=OuterRef('specific_part'),
            param_name='operation_mode',
        ).values('value')[:1]
    )

    # ---- 5b. Subquery annotate：PLC 连接状态与最后在线时间----
    plc_connection_status_sq = Subquery(
        PLCConnectionStatus.objects.filter(
            specific_part=OuterRef('specific_part')
        ).values('connection_status')[:1]
    )
    plc_last_online_time_sq = Subquery(
        PLCConnectionStatus.objects.filter(
            specific_part=OuterRef('specific_part')
        ).values('last_online_time')[:1]
    )

    qs = qs.annotate(
        _screen_last_seen_at=screen_last_seen_sq,
        _system_switch_value=system_switch_sq,
        _operation_mode_value=operation_mode_sq,
        _plc_connection_status=plc_connection_status_sq,
        _plc_last_online_time=plc_last_online_time_sq,
    )

    # ---- 6. 在线状态阈值计算（Python 层，避免复杂 SQL 表达式）----
    # 对于 screen_status 过滤，需要先取出全量再过滤，代价可接受（业主总数有限）。
    # 若将来需要 DB 层过滤可改为 annotate ExpressionWrapper。
    online_cutoff = timezone.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)

    def _compute_screen_status(last_seen_at):
        """根据 last_seen_at 计算大屏状态字符串。"""
        if last_seen_at is None:
            return 'unknown'
        return 'online' if last_seen_at >= online_cutoff else 'offline'

    def _compute_plc_status(connection_status):
        """根据 PLCConnectionStatus.connection_status 计算 PLC 状态字符串。"""
        if connection_status is None:
            return 'unknown'
        return connection_status  # 'online' | 'offline'

    # ---- 7. 系统开关过滤（DB 层）----
    if system_switch_filter == 'on':
        qs = qs.filter(_system_switch_value__isnull=False).exclude(_system_switch_value=0)
    elif system_switch_filter == 'off':
        qs = qs.filter(Q(_system_switch_value__isnull=True) | Q(_system_switch_value=0))

    # ---- 7b. PLC 状态过滤（DB 层）----
    if plc_status_filter == 'online':
        qs = qs.filter(_plc_connection_status='online')
    elif plc_status_filter == 'offline':
        qs = qs.filter(_plc_connection_status='offline')

    # ---- 7c. 运行模式过滤（DB 层）----
    if operation_mode_filter:
        try:
            qs = qs.filter(_operation_mode_value=int(operation_mode_filter))
        except (ValueError, TypeError):
            pass

    # ---- 8. 分页 ----
    # ADR-FFF-002: fault_status 或 screen_status 存在时走全量拉取路径（Python 层过滤）
    need_full_scan = (
        screen_status_filter in ('online', 'offline', 'unknown')
        or fault_status_filter in ('has_fault', 'no_fault')
    )

    all_fault_counts = None  # 全量故障数缓存，用于 step 9a 复用

    if need_full_scan:
        all_rows = list(qs)

        # 8a. screen_status 过滤（若存在，ADR-FFF-002 先于 fault_status）
        if screen_status_filter in ('online', 'offline', 'unknown'):
            all_rows = [
                owner for owner in all_rows
                if _compute_screen_status(owner._screen_last_seen_at) == screen_status_filter
            ]

        # 8b. fault_status 过滤（若存在，ADR-FFF-001 Python 层，ADR-FFF-003 None 两侧排除）
        if fault_status_filter in ('has_fault', 'no_fault'):
            from .fault_utils import get_fault_count_batch_cached
            all_specific_parts = [owner.specific_part for owner in all_rows]
            all_fault_counts = get_fault_count_batch_cached(all_specific_parts)
            if fault_status_filter == 'has_fault':
                # fault_count > 0 且不为 None（ADR-FFF-003）
                all_rows = [
                    owner for owner in all_rows
                    if all_fault_counts.get(owner.specific_part) is not None
                    and all_fault_counts.get(owner.specific_part) > 0
                ]
            else:  # no_fault
                # fault_count == 0 严格等于（ADR-FFF-003：None 排除）
                all_rows = [
                    owner for owner in all_rows
                    if all_fault_counts.get(owner.specific_part) == 0
                ]

        # REQ-FUNC-FFF-03: total 在所有 Python 层过滤完毕后计算
        total = len(all_rows)
        start = (page - 1) * page_size
        page_rows = all_rows[start:start + page_size]
    else:
        total = qs.count()
        start = (page - 1) * page_size
        page_rows = list(qs[start:start + page_size])

    # ---- 9. 序列化结果 ----
    _OPERATION_MODE_MAP = {1: '制冷', 2: '制热', 3: '通风', 4: '除湿'}

    # ---- 9a. 批量获取故障数量（v0.5.3-FCC, REQ-FUNC-FC-02）----
    from .fault_utils import get_fault_count_batch_cached
    if all_fault_counts is not None:
        # fault_status 过滤时已在 step 8b 全量查过，直接取 page_rows 子集（REQ-NFR-FFF-01 不重复查询）
        fault_counts = {
            owner.specific_part: all_fault_counts.get(owner.specific_part)
            for owner in page_rows
        }
    else:
        # 现有逻辑：仅查 page_rows 的故障数
        page_specific_parts = [owner.specific_part for owner in page_rows]
        fault_counts = get_fault_count_batch_cached(page_specific_parts)

    # ---- 9b. 批量获取凝露提醒状态（REQ-FUNC-CL-01, REQ-NFR-PERF-02）----
    from .models import CondensationWarningEvent
    page_specific_parts_for_cond = [owner.specific_part for owner in page_rows]
    active_condensation_set = set(
        CondensationWarningEvent.objects.filter(
            specific_part__in=page_specific_parts_for_cond,
            is_active=True,
        ).values_list('specific_part', flat=True).distinct()
    )

    results = []
    for owner in page_rows:
        last_seen_at = owner._screen_last_seen_at   # datetime | None
        sw_value = owner._system_switch_value        # int | None
        om_value = owner._operation_mode_value       # int | None
        plc_conn_status = owner._plc_connection_status   # 'online' | 'offline' | None
        plc_last_online = owner._plc_last_online_time    # datetime | None

        screen_display = _compute_screen_status(last_seen_at)
        plc_status_display = _compute_plc_status(plc_conn_status)

        # 映射系统开关显示
        if sw_value is None:
            sw_display = '未知'
        elif sw_value == 0:
            sw_display = '关'
        else:
            sw_display = '开'

        # 映射运行模式显示（REQ-FUNC-002，AC-103~105）
        if om_value is None:
            om_display = '未知'
        else:
            om_display = _OPERATION_MODE_MAP.get(int(om_value), '未知')

        results.append({
            'specific_part': owner.specific_part,
            'building': owner.building,
            'unit': owner.unit,
            'room_number': owner.room_number,
            'screen_status': screen_display,
            'screen_last_seen_at': last_seen_at.isoformat() if last_seen_at else None,
            'system_switch_value': sw_value,
            'system_switch_display': sw_display,
            'operation_mode_value': om_value,
            'operation_mode_display': om_display,
            'plc_status': plc_status_display,
            'plc_last_online_time': plc_last_online.isoformat() if plc_last_online else None,
            # 同步设备信息按钮可用性：unique_id (screenMAC) 非空才能调远程接口
            'has_screen_mac': bool((owner.unique_id or '').strip()),
            # v0.5.3-FCC: 故障数量（REQ-FUNC-FC-02）
            # None = PLCLatestData 中无该 specific_part 记录（前端显示 —）
            'fault_count': fault_counts.get(owner.specific_part),
            # REQ-FUNC-CL-01: 凝露提醒（v1.0.0）
            'has_active_condensation': owner.specific_part in active_condensation_set,
        })

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': results,
    })


# ---------------------------------------------------------------------------
# 设备树同步接口（单户 / 批量）
# 远程调用：POST http://47.117.41.184:10013/.../floor-room-device/list
# Header: screenMAC = OwnerInfo.unique_id
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def device_tree_sync_one(request):
    """POST /api/device-management/screen-device-tree/sync/

    Body 或 Query：
      specific_part (str, 必填)  — 如 "3-1-7-702"
      prune         (bool, 可选) — 默认 False；True 时清理远程未返回的旧节点

    返回 200：{ specific_part, screen_mac, stats: {...} }
    错误：400 未绑定 MAC / 404 户不存在 / 502 远程异常
    """
    from .device_tree_sync import (
        MissingScreenMacError, OwnerNotFoundError, SyncError, sync_one_specific_part,
    )

    specific_part = (
        request.data.get('specific_part')
        if isinstance(request.data, dict) else None
    ) or request.GET.get('specific_part', '')
    specific_part = (specific_part or '').strip()
    if not specific_part:
        return Response({'error': 'specific_part 必填'}, status=400)

    prune_raw = (
        request.data.get('prune') if isinstance(request.data, dict) else None
    )
    if prune_raw is None:
        prune_raw = request.GET.get('prune', '')
    prune = str(prune_raw).lower() in ('1', 'true', 'yes')

    try:
        result = sync_one_specific_part(specific_part, prune=prune)
    except (MissingScreenMacError, OwnerNotFoundError, SyncError) as e:
        logger.warning('device_tree_sync_one failed sp=%s err=%s', specific_part, e.message)
        return Response({'error': e.message}, status=e.http_status)
    except Exception as e:  # noqa: BLE001
        logger.exception('device_tree_sync_one unexpected error sp=%s', specific_part)
        return Response({'error': f'未预期错误: {e}'}, status=500)

    # v0.5.7 M5: 设备树同步成功后主动清除该专有部分的房型过滤缓存
    invalidate_room_filter_cache(specific_part)

    return Response({
        'code': 200,
        'message': 'ok',
        **result,
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def device_tree_sync_batch(request):
    """POST /api/device-management/screen-device-tree/batch-sync/

    Body：
      specific_parts (list[str], 可选)
        — 不传则同步所有 OwnerInfo 中 unique_id 非空的户

      prune (bool, 可选) — 默认 False

    返回 202：{ task_id, total }
    """
    from .device_tree_sync import start_batch_sync

    payload = request.data if isinstance(request.data, dict) else {}
    sp_input = payload.get('specific_parts')

    if isinstance(sp_input, list) and sp_input:
        specific_parts = [str(x).strip() for x in sp_input if str(x).strip()]
    else:
        specific_parts = list(
            OwnerInfo.objects
            .exclude(unique_id='')
            .values_list('specific_part', flat=True)
        )

    prune = bool(payload.get('prune')) if isinstance(payload, dict) else False
    task_id, total = start_batch_sync(specific_parts, prune=prune)
    # v0.5.7 M5: 批量同步启动时预清除全部房型过滤缓存（同步完成后缓存会按需重建）
    # 批量同步在后台线程执行，同步期间各户缓存自然因 TTL 超期或按需刷新；
    # 此处预清除确保同步结束后再次访问时立即读取最新房间信息，不等 300s TTL 超期。
    invalidate_room_filter_cache()
    return Response({'task_id': task_id, 'total': total}, status=202)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def device_tree_sync_batch_status(request, task_id):
    """GET /api/device-management/screen-device-tree/batch-sync/<task_id>/

    返回任务进度；404 表示 task_id 不存在或已过期。
    """
    from .device_tree_sync import get_task_status

    record = get_task_status(task_id)
    if record is None:
        return Response({'error': '任务不存在或已过期'}, status=404)
    return Response(record)


# ===========================================================================
# v0.5.6 — 按需采集触发接口 (MOD-BE-01, REQ-FUNC-001)
# ===========================================================================

# 进程内防重入缓存：{specific_part: last_request_timestamp}
# TTL = 25s：同一 specific_part 25 秒内重复请求直接返回 202，不重复发布 MQTT
_ondemand_inflight: dict = {}
_ONDEMAND_INFLIGHT_TTL = 25  # 秒


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def device_ondemand_refresh(request):
    """POST /api/devices/ondemand-refresh/

    触发指定专有部分的按需 PLC 数据采集。
    向 MQTT broker 发布 /datacollection/plc/ondemand/request/<specific_part>。
    返回 202 Accepted（不等待采集完成）。

    Request body:
        {"specific_part": "9-1-31-3104"}

    Responses:
        202: {"status": "accepted", "specific_part": "..."}
        400: {"detail": "specific_part 为必填项"}
        503: {"detail": "MQTT broker 不可达，无法提交采集请求"}
    """
    import time as _time
    specific_part = (request.data.get('specific_part') or '').strip()
    if not specific_part:
        return Response({'detail': 'specific_part 为必填项'}, status=status.HTTP_400_BAD_REQUEST)

    # 防重入：同一 specific_part 25 秒内不重复发布（幂等保护）
    now = _time.monotonic()
    last_ts = _ondemand_inflight.get(specific_part)
    if last_ts is not None and (now - last_ts) < _ONDEMAND_INFLIGHT_TTL:
        logger.info(
            'device_ondemand_refresh: 防重入幂等返回 202: specific_part=%s', specific_part
        )
        return Response({'status': 'accepted', 'specific_part': specific_part},
                        status=status.HTTP_202_ACCEPTED)

    # 向 MQTT broker 发布按需采集指令
    import json as _json
    import paho.mqtt.publish as mqtt_publish
    from django.conf import settings as dj_settings
    import os as _os

    mqtt_config_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
        'mqtt_config.json',
    )
    try:
        with open(mqtt_config_path, 'r', encoding='utf-8') as f:
            mqtt_cfg = _json.load(f)
    except Exception:
        mqtt_cfg = {}

    broker_host = mqtt_cfg.get('host', '192.168.31.98')
    broker_port = int(mqtt_cfg.get('port', 32788))
    broker_user = mqtt_cfg.get('username') or None
    broker_pass = mqtt_cfg.get('password') or None

    request_topic = f'/datacollection/plc/ondemand/request/{specific_part}'
    import datetime as _dt

    # v0.5.7 M7-A: 计算 allowed_params 白名单，注入 ondemand 指令
    # 采集侧收到后仅读取白名单内的 PLC 地址，彻底闭环 BG-04（FR-v0.5.7-05）
    _allowed_params = get_allowed_param_names(specific_part)
    _payload_dict = {
        'specific_part': specific_part,
        'requested_at': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    if _allowed_params:
        _payload_dict['allowed_params'] = _allowed_params
        logger.debug(
            'device_ondemand_refresh: specific_part=%s, allowed_params 共 %d 个参数',
            specific_part, len(_allowed_params),
        )
    else:
        # allowed_params 为空或计算失败 → 不注入，采集侧降级为全量采集
        logger.debug(
            'device_ondemand_refresh: specific_part=%s, allowed_params 为空，采集侧将全量采集',
            specific_part,
        )
    payload_body = _json.dumps(_payload_dict)
    # ── end v0.5.7 M7-A ────────────────────────────────────────────────────

    auth = {'username': broker_user, 'password': broker_pass} if broker_user else None
    try:
        mqtt_publish.single(
            request_topic,
            payload=payload_body,
            qos=1,
            hostname=broker_host,
            port=broker_port,
            auth=auth,
        )
        logger.info(
            'device_ondemand_refresh: 已发布 MQTT 指令: topic=%s specific_part=%s',
            request_topic, specific_part,
        )
    except Exception as e:
        logger.error(
            'device_ondemand_refresh: MQTT 发布失败: specific_part=%s error=%s',
            specific_part, e, exc_info=True,
        )
        return Response(
            {'detail': f'MQTT broker 不可达，无法提交采集请求: {e}'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # 记录本次请求时间（防重入缓存）
    _ondemand_inflight[specific_part] = now

    return Response({'status': 'accepted', 'specific_part': specific_part},
                    status=status.HTTP_202_ACCEPTED)


# ---------------------------------------------------------------------------
# v0.5.3-FCC: 故障数量查询 API（REQ-FUNC-FC-05）
# GET /api/devices/fault-count/?specific_part=3-1-7-702[,3-1-7-703,...]
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def device_fault_count(request):
    """查询指定专有部分的故障数量和故障明细。

    GET /api/devices/fault-count/?specific_part=3-1-7-702[,3-1-7-703,...]

    查询参数：
        specific_part (str): 必须，逗号分隔，最多 50 个

    响应 200：
        {
          "success": true,
          "data": [
            {
              "specific_part": "3-1-7-702",
              "fault_count": 3,
              "fault_details": [
                {"param_name": "comm_fault_timeout", "value": 1},
                {"param_name": "living_room_temp_sensor_error", "value": 1}
              ],
              "updated_at": "2026-05-26T10:30:00+08:00"
            }
          ],
          "queried_at": "2026-05-26T10:30:05+08:00"
        }

    错误响应：
        400  specific_part 缺失或超过 50 个
        401  未鉴权（DRF 默认）
        500  DB 异常
    """
    from .fault_utils import get_fault_count_batch_cached, get_fault_details, get_fault_details_updated_at

    sp_param = request.GET.get('specific_part', '').strip()
    if not sp_param:
        return Response(
            {'success': False, 'error': '参数 specific_part 不能为空'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    specific_parts = [s.strip() for s in sp_param.split(',') if s.strip()]
    if not specific_parts:
        return Response(
            {'success': False, 'error': '参数 specific_part 不能为空'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(specific_parts) > 50:
        return Response(
            {'success': False, 'error': '一次最多查询 50 个专有部分'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        fault_counts = get_fault_count_batch_cached(specific_parts)
        data = []
        for sp in specific_parts:
            fc = fault_counts.get(sp)
            if fc is None:
                # PLCLatestData 中无记录
                data.append({
                    'specific_part': sp,
                    'fault_count': None,
                    'fault_details': [],
                    'updated_at': None,
                })
            else:
                details = get_fault_details(sp)
                updated_at = get_fault_details_updated_at(sp)
                data.append({
                    'specific_part': sp,
                    'fault_count': fc,
                    'fault_details': details,
                    'updated_at': updated_at.isoformat() if updated_at else None,
                })
    except Exception as exc:
        logger.exception('device_fault_count: 查询异常 specific_parts=%s', specific_parts)
        return Response(
            {'success': False, 'error': '查询故障数量时发生内部错误'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        'success': True,
        'data': data,
        'queried_at': django_now().isoformat(),
    })


# ---------------------------------------------------------------------------
# v0.5.3-FCC: 故障汇总查询 API（REQ-FUNC-FC-06 / OpenClaw freeark_get_fault_summary）
# GET /api/devices/fault-summary/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def device_fault_summary(request):
    """查询有故障的专有部分汇总（按故障数降序，最多 100 条）。

    GET /api/devices/fault-summary/

    可选查询参数：
        building (str): 楼栋过滤，如 "3"
        unit (str): 单元过滤，如 "1"
        min_fault_count (int): 最小故障数过滤，默认 1

    响应 200：
        {
          "success": true,
          "total_with_faults": 5,
          "data": [
            {"specific_part": "3-1-7-702", "building": "3", "unit": "1",
             "room_number": "702", "fault_count": 5},
            ...
          ],
          "queried_at": "2026-05-26T10:30:05+08:00"
        }

    错误响应：
        400  min_fault_count 非法
        401  未鉴权
        500  内部错误
    """
    from .fault_utils import get_fault_count_batch_cached

    building_filter = request.GET.get('building', '').strip()
    unit_filter = request.GET.get('unit', '').strip()
    min_fc_raw = request.GET.get('min_fault_count', '1').strip()

    try:
        min_fault_count = int(min_fc_raw)
        if min_fault_count < 0:
            raise ValueError('min_fault_count 不能为负数')
    except (ValueError, TypeError):
        return Response(
            {'success': False, 'error': 'min_fault_count 必须是非负整数'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        qs = OwnerInfo.objects.all()
        if building_filter:
            qs = qs.filter(Q(building=building_filter) | Q(building=f'{building_filter}栋'))
        if unit_filter:
            qs = qs.filter(Q(unit=unit_filter) | Q(unit=f'{unit_filter}单元'))

        all_owners = list(qs.values('specific_part', 'building', 'unit', 'room_number'))
        if not all_owners:
            return Response({
                'success': True,
                'total_with_faults': 0,
                'data': [],
                'queried_at': django_now().isoformat(),
            })

        all_specific_parts = [o['specific_part'] for o in all_owners]
        fault_counts = get_fault_count_batch_cached(all_specific_parts)

        # 过滤 fault_count >= min_fault_count 且非 None
        filtered = []
        for owner in all_owners:
            sp = owner['specific_part']
            fc = fault_counts.get(sp)
            if fc is not None and fc >= min_fault_count:
                filtered.append({
                    'specific_part': sp,
                    'building': owner['building'],
                    'unit': owner['unit'],
                    'room_number': owner['room_number'],
                    'fault_count': fc,
                })

        # 按 fault_count 降序，最多 100 条
        filtered.sort(key=lambda x: x['fault_count'], reverse=True)
        filtered = filtered[:100]

    except Exception as exc:
        logger.exception('device_fault_summary: 查询异常')
        return Response(
            {'success': False, 'error': '查询故障汇总时发生内部错误'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        'success': True,
        'total_with_faults': len(filtered),
        'data': filtered,
        'queried_at': django_now().isoformat(),
    })