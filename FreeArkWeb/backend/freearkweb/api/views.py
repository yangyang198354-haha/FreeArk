import logging
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from .models import CustomUser, UsageQuantityDaily, UsageQuantityMonthly
from .serializers import (
    UserSerializer,
    UserRegistrationSerializer, UserLoginSerializer, UserCreateSerializer,
    UsageQuantityDailySerializer, UsageQuantityMonthlySerializer
)

# 获取logger实例
logger = logging.getLogger(__name__)

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
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'department': user.department,
        'position': user.position
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
            print(f"更新用户请求数据: {request.data}")
            response = super().update(request, *args, **kwargs)
            return response
        except Exception as e:
            print(f"更新用户错误: {str(e)}")
            # 如果是序列化器错误
            if hasattr(e, 'detail'):
                print(f"序列化器错误详情: {e.detail}")
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
            print(f"创建用户异常: {str(e)}")
            
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
    logger.debug('健康检查请求: %s', request.GET)
    logger.info('健康检查API被调用')
    logger.warning('这是一条警告日志测试')
    logger.error('这是一条错误日志测试')
    return Response({'status': 'ok', 'message': 'FreeArk Web API 服务正常运行'})


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def test_logging(request):
    """日志测试接口（允许未认证访问）"""
    # 记录不同级别的日志
    logger.debug('这是一条DEBUG级别的日志')
    logger.info('这是一条INFO级别的日志')
    logger.warning('这是一条WARNING级别的日志')
    logger.error('这是一条ERROR级别的日志')
    logger.critical('这是一条CRITICAL级别的日志')
    
    # 尝试记录异常信息
    try:
        result = 1 / 0
    except Exception as e:
        logger.exception('捕获到异常: %s', str(e))
    
    return Response({
        'status': 'ok', 
        'message': '日志测试完成，请检查日志文件'
    })



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
    if energy_mode:
        queryset = queryset.filter(energy_mode=energy_mode)
    if start_time:
        queryset = queryset.filter(time_period__gte=start_time)
    if end_time:
        queryset = queryset.filter(time_period__lte=end_time)
    
    # 按专有部分和供能模式分组，计算每个组的初期能耗最小值、末期能耗最大值
    from django.db.models import Min, Max, F
    
    # 获取所有唯一的专有部分
    unique_specific_parts = queryset.values_list('specific_part', flat=True).distinct()
    
    # 定义所有供能模式
    energy_modes = ['制热', '制冷']
    
    # 生成所有组合（专有部分 + 所有供能模式）并去重
    unique_combinations_set = set()
    for sp in unique_specific_parts:
        for em in energy_modes:
            unique_combinations_set.add((sp, em))
    # 将去重后的组合转换为字典列表
    unique_combinations = [{'specific_part': sp, 'energy_mode': em} for sp, em in unique_combinations_set]
    
    # 按时间升序排序（用于后续计算）
    queryset = queryset.order_by('time_period')
    
    result_data = []
    
    for combination in unique_combinations:
        # 过滤当前组合的数据
        combo_queryset = queryset.filter(
            specific_part=combination['specific_part'],
            energy_mode=combination['energy_mode']
        )
        
        # 获取该组合的第一个building、unit、room_number作为展示数据
        first_record = queryset.filter(
            specific_part=combination['specific_part'],
            energy_mode=combination['energy_mode']
        ).first()
        
        # 设置组合的基本信息
        combination['building'] = first_record.building if first_record else ''
        combination['unit'] = first_record.unit if first_record else ''
        combination['room_number'] = first_record.room_number if first_record else ''
        
        # 计算初期能耗（最小值）和末期能耗（最大值）
        initial_energy = combo_queryset.aggregate(min_energy=Min('initial_energy'))['min_energy']
        final_energy = combo_queryset.aggregate(max_energy=Max('final_energy'))['max_energy']
        
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
    
    total_count = len(result_data)
    
    # 记录查询结果到日志
    logger.info(f"能耗报表查询结果 - 找到 {total_count} 条记录")
    
    # 处理分页
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    
    # 计算分页范围
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_data = result_data[start_index:end_index]
    
    return Response({
        'success': True,
        'data': paginated_data,
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
    
    # 按用量月度升序排序
    queryset = queryset.order_by('usage_month')
    
    # 序列化数据
    serializer = UsageQuantityMonthlySerializer(queryset, many=True)
    result_data = serializer.data
    total_count = len(result_data)
    
    # 记录查询结果到日志
    logger.info(f"UsageQuantityMonthly 查询结果 - 找到 {total_count} 条记录")
    
    return Response({
        'success': True,
        'data': result_data,
        'total': total_count
    })
