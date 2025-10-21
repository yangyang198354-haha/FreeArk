from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from .models import CustomUser, UsageQuantityDaily
from .serializers import (
    UserSerializer,
    UserRegistrationSerializer, UserLoginSerializer, UserCreateSerializer,
    UsageQuantityDailySerializer
)

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

# 健康检查接口保持不变

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    """健康检查接口（允许未认证访问）"""
    return Response({'status': 'ok', 'message': 'FreeArk Web API 服务正常运行'})


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_usage_quantity(request):
    """
    获取每日用量数据
    支持按多个条件过滤：房号、专有部分、供能模式、开始时间和结束时间
    """
    # 构建基础查询集
    queryset = UsageQuantityDaily.objects.all()
    
    # 获取查询参数
    room_number = request.GET.get('room_number')
    specific_part = request.GET.get('specific_part')
    energy_mode = request.GET.get('energy_mode')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    
    # 应用过滤条件
    if room_number:
        queryset = queryset.filter(room_number=room_number)
    if specific_part:
        queryset = queryset.filter(specific_part=specific_part)
    if energy_mode:
        queryset = queryset.filter(energy_mode=energy_mode)
    if start_time:
        queryset = queryset.filter(time_period__gte=start_time)
    if end_time:
        queryset = queryset.filter(time_period__lte=end_time)
    
    # 按时间降序排序
    queryset = queryset.order_by('-time_period')
    
    # 序列化数据
    serializer = UsageQuantityDailySerializer(queryset, many=True)
    
    return Response({
        'success': True,
        'data': serializer.data,
        'total': len(serializer.data)
    })
