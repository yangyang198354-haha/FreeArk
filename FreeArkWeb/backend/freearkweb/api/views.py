import calendar
import logging
import subprocess
from datetime import date, timedelta
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from django.db.models import Min, Max, Count, Case, When, IntegerField, Sum, Subquery, OuterRef, Q
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from .models import CustomUser, UsageQuantityDaily, UsageQuantityMonthly, PLCConnectionStatus, PLCStatusChangeHistory, OwnerInfo, PLCLatestData, DeviceConfig, DeviceParamHistory, ScreenConnectivityStatus
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
@permission_classes([permissions.AllowAny])
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
@permission_classes([permissions.AllowAny])
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
@permission_classes([permissions.AllowAny])
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
@permission_classes([permissions.AllowAny])
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
@permission_classes([permissions.AllowAny])
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
@permission_classes([permissions.AllowAny])
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
@permission_classes([permissions.AllowAny])
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
def dashboard_total_energy(request):
    """
    看板 API 1：总电量查询（支持自定义时间段）
    GET /api/dashboard/total-energy/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    若未传参数，默认返回当年数据。
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
MONITORED_SERVICES = [
    'freeark-backend',
    'freeark-mqtt-consumer',
    'freeark-daily-usage',
    'freeark-monthly-usage',
    'freeark-plc-cleanup',
    'freeark-plc-connection-monitor',
    'freeark-task-scheduler',
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
def dashboard_services(request):
    """
    看板 API 5：系统服务状态
    GET /api/dashboard/services/
    通过 subprocess 调用 systemctl is-active 查询各服务状态。
    """
    services = []
    for name in MONITORED_SERVICES:
        svc_status = _get_service_status(name)
        services.append({
            'name': name,
            'status': svc_status,
            'is_active': svc_status == 'active',
        })

    return Response({
        'success': True,
        'data': services,
    })


# ===========================================================================
# 服务管理 API（Service Management）
# ===========================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
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

        # 查询 is-enabled 状态（enabled/disabled/static/…）
        try:
            enabled_result = subprocess.run(
                ['systemctl', 'is-enabled', name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            enabled_str = enabled_result.stdout.strip()
        except Exception:
            enabled_str = 'unknown'

        services.append({
            'name': name,
            'active_state': active_state,
            'sub_state': '',          # 简略列表不展开 sub_state，详情接口再查
            'is_active': active_state == 'active',
            'enabled': enabled_str if enabled_str else 'unknown',
        })

    return Response({'success': True, 'data': services})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
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
@permission_classes([permissions.IsAuthenticated])
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
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsAdminUser()]

    def get_queryset(self):
        from django.db.models import Q
        queryset = OwnerInfo.objects.all().order_by('building', 'unit', 'room_number')
        building = self.request.GET.get('building')
        unit = self.request.GET.get('unit')
        bind_status = self.request.GET.get('bind_status')
        search = self.request.GET.get('search')
        if building:
            queryset = queryset.filter(building=building)
        if unit:
            queryset = queryset.filter(unit=unit)
        if bind_status:
            queryset = queryset.filter(bind_status=bind_status)
        if search:
            queryset = queryset.filter(
                Q(specific_part__icontains=search) |
                Q(location_name__icontains=search) |
                Q(room_number__icontains=search)
            )
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
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsAdminUser()]

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
@permission_classes([permissions.AllowAny])
def get_device_realtime_params(request):
    """
    GET /api/devices/realtime-params/?specific_part=9-1-31-3104[&group=hvac]
    返回指定专有部分的设备实时参数，按 group -> sub_type -> params 嵌套结构。

    Query params:
      specific_part (str, required) — 住宅专有部分标识，如 9-1-31-3104
      group         (str, optional) — 过滤指定设备分组（如 hvac）
    """
    from datetime import datetime as _dt

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

    # 构建嵌套响应结构：group -> sub_type -> params
    result = {}
    for cfg in configs_qs:
        group_key = cfg.group
        sub_key = cfg.sub_type

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

        result[group_key]['sub_types'][sub_key]['params'].append({
            'param_name': cfg.param_name,
            'display_name': cfg.display_name,
            'value': record.value,
            'collected_at': record.collected_at.strftime('%Y-%m-%d %H:%M:%S') if record.collected_at else None,
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
@permission_classes([permissions.AllowAny])
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
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def device_management_device_list(request):
    """
    GET /api/device-management/device-list/

    返回本小区所有专有部分的设备列表，支持三维过滤与分页。

    Query 参数：
      room_no        (str, 可选)  — 三段格式，如 "3-1-702"，1~3 段均可
      screen_status  (str, 可选)  — "online" | "offline" | "unknown"
      system_switch  (str, 可选)  — "on" | "off"
      page           (int, 可选)  — 默认 1
      page_size      (int, 可选)  — 可选 10/20/50，默认 20，最大 50

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
          "screen_last_checked_at": <str|null>,
          "system_switch_value": <int|null>,
          "system_switch_display": "开"|"关"|"未知"
        } ]
      }
    """
    # ---- 1. 解析过滤参数 ----
    room_no = request.GET.get('room_no', '').strip()
    screen_status_filter = request.GET.get('screen_status', '').strip().lower()
    system_switch_filter = request.GET.get('system_switch', '').strip().lower()

    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
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
                qs = qs.filter(building=parts[0].strip())
            if len(parts) >= 2 and parts[1]:
                qs = qs.filter(unit=parts[1].strip())
            if len(parts) >= 3 and parts[2]:
                qs = qs.filter(room_number=parts[2].strip())
        except Exception:
            return Response(
                {'error': 'room_no 格式非法，期望 1~3 段数字，如 3-1-702'},
                status=400,
            )

    # ---- 4. Subquery annotate：大屏连通状态（ADR-001）----
    screen_status_sq = Subquery(
        ScreenConnectivityStatus.objects.filter(
            specific_part=OuterRef('specific_part')
        ).values('status')[:1]
    )
    screen_checked_sq = Subquery(
        ScreenConnectivityStatus.objects.filter(
            specific_part=OuterRef('specific_part')
        ).values('last_checked_at')[:1]
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

    qs = qs.annotate(
        _screen_status=screen_status_sq,
        _screen_checked_at=screen_checked_sq,
        _system_switch_value=system_switch_sq,
    )

    # ---- 6. 大屏状态过滤 ----
    if screen_status_filter == 'online':
        qs = qs.filter(_screen_status='online')
    elif screen_status_filter == 'offline':
        qs = qs.filter(_screen_status='offline')
    elif screen_status_filter == 'unknown':
        qs = qs.filter(_screen_status__isnull=True)

    # ---- 7. 系统开关过滤 ----
    if system_switch_filter == 'on':
        qs = qs.filter(_system_switch_value__isnull=False).exclude(_system_switch_value=0)
    elif system_switch_filter == 'off':
        # value IS NULL OR value = 0
        qs = qs.filter(Q(_system_switch_value__isnull=True) | Q(_system_switch_value=0))

    # ---- 8. 分页 ----
    total = qs.count()
    start = (page - 1) * page_size
    page_qs = qs[start:start + page_size]

    # ---- 9. 序列化结果 ----
    results = []
    for owner in page_qs:
        raw_status = owner._screen_status          # None / "online" / "offline"
        checked_at = owner._screen_checked_at      # datetime | None
        sw_value = owner._system_switch_value      # int | None

        # 映射大屏状态显示
        if raw_status == 'online':
            screen_display = 'online'
        elif raw_status == 'offline':
            screen_display = 'offline'
        else:
            screen_display = 'unknown'

        # 映射系统开关显示
        if sw_value is None:
            sw_display = '未知'
        elif sw_value == 0:
            sw_display = '关'
        else:
            sw_display = '开'

        results.append({
            'specific_part': owner.specific_part,
            'building': owner.building,
            'unit': owner.unit,
            'room_number': owner.room_number,
            'screen_status': screen_display,
            'screen_last_checked_at': checked_at.isoformat() if checked_at else None,
            'system_switch_value': sw_value,
            'system_switch_display': sw_display,
        })

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': results,
    })