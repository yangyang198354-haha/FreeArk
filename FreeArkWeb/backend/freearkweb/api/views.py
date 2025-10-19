from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from .models import CustomUser
from .serializers import (
    UserSerializer,
    UserRegistrationSerializer, UserLoginSerializer, UserCreateSerializer
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
def user_logout(request):
    """用户登出视图"""
    # 删除Token
    if request.user.is_authenticated:
        Token.objects.filter(user=request.user).delete()
    logout(request)
    return Response({'success': True, 'message': '成功登出'})

@api_view(['GET'])
def get_current_user(request):
    """获取当前登录用户信息"""
    if request.user.is_authenticated:
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
    return Response({'error': '用户未登录'}, status=status.HTTP_401_UNAUTHORIZED)

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
