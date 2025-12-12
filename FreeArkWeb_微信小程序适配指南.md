# FreeArkWeb后端微信小程序适配指南

## 一、项目概述

FreeArkWeb是一个基于Django REST Framework开发的Web后端服务，提供数据采集、监控和管理功能。为了支持微信小程序调用，需要对当前后端进行一系列调整，以满足微信小程序的技术要求和安全规范。

## 二、当前后端分析

### 2.1 目录结构
```
FreeArkWeb/
├── backend/
│   ├── freearkweb/
│   │   ├── api/           # API视图和路由
│   │   ├── freearkweb/    # 项目配置
│   │   ├── manage.py      # Django管理脚本
│   │   └── start_waitress_server.py # 服务器启动脚本
│   ├── requirements.txt   # 依赖列表
│   └── Dockerfile         # Docker配置
└── frontend/              # 前端代码（暂不涉及）
```

### 2.2 关键配置
- **框架**: Django 5.2 + Django REST Framework
- **服务器**: Waitress (跨平台WSGI服务器)
- **认证**: Token认证 + Session认证
- **CORS**: django-cors-headers已配置
- **数据库**: 默认SQLite，支持MySQL/PostgreSQL

### 2.3 主要API端点
```
/api/get-csrf-token/        # 获取CSRF令牌
/api/auth/login/           # 用户登录
/api/auth/logout/          # 用户注销
/api/auth/me/              # 获取当前用户信息
/api/auth/register/        # 用户注册
/api/admin/users/          # 管理员用户管理
/api/health/               # 健康检查
/api/test/log/             # 日志测试
/api/usage-data/           # 用量数据查询
```

## 三、微信小程序技术要求

微信小程序对网络请求有严格的限制和要求，主要包括：

1. **HTTPS强制要求**: 小程序只能请求HTTPS类型的接口
2. **域名白名单**: 必须将接口域名添加到微信公众平台的信任列表
3. **并发请求限制**: 最多同时发起10个并发请求
4. **超时限制**: 默认和最大超时时间均为60秒
5. **后台请求限制**: 进入后台5秒内未完成的请求会被中断
6. **请求头限制**: 不能设置Referer，支持常见的Content-Type

## 四、具体调整建议

### 4.1 HTTPS配置（必须）

**问题**: 当前服务器仅支持HTTP，微信小程序要求必须使用HTTPS

**解决方案**: 配置Waitress服务器支持HTTPS，添加SSL证书

**实施步骤**:
1. 申请SSL证书（推荐使用Let's Encrypt免费证书）
2. 修改`start_waitress_server.py`添加HTTPS支持

**代码调整**:
```python
# start_waitress_server.py - 增加HTTPS配置
from waitress import serve
from freearkweb.wsgi import application
import os

# 证书路径配置
CERT_PATH = os.environ.get('SSL_CERT_PATH', '/path/to/cert.pem')
KEY_PATH = os.environ.get('SSL_KEY_PATH', '/path/to/key.pem')

# 同时支持HTTP和HTTPS（建议生产环境仅启用HTTPS）
serve(application, host='0.0.0.0', port=80)
serve(application, host='0.0.0.0', port=443, 
      url_scheme='https', certfile=CERT_PATH, keyfile=KEY_PATH)
```

### 4.2 域名与安全配置（必须）

**问题**: 需要确保域名已备案且配置正确

**解决方案**:
1. 确保使用已备案的域名（微信要求）
2. 将域名添加到`ALLOWED_HOSTS`
3. 配置正确的CORS策略

**代码调整**:
```python
# settings.py - 更新ALLOWED_HOSTS
ALLOWED_HOSTS = [
    'localhost', '127.0.0.1', 
    '192.168.31.51', '192.168.31.52',
    'et116374mm892.vicp.fun',  # 确保此域名已备案
]

# settings.py - CORS配置优化
CORS_ALLOWED_ORIGINS = [
    "https://servicewechat.com",  # 微信小程序固定请求源
    "http://localhost:8080",      # 开发环境支持
    "http://127.0.0.1:8080",
]

# 支持凭证（cookies）
CORS_ALLOW_CREDENTIALS = True

# 生产环境安全配置
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = 'None'  # 支持跨域
SESSION_COOKIE_SAMESITE = 'None'
```

### 4.3 API认证机制调整

**问题**: 当前Token认证机制需要适配微信小程序的使用习惯

**解决方案**: 优化Token管理，增加有效期和刷新机制

**代码调整**:
```python
# api/views.py - 增强登录接口返回信息
@csrf_exempt
@api_view(['POST'])
def user_login(request):
    """用户登录接口"""
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        username = serializer.validated_data['username']
        password = serializer.validated_data['password']
        user = authenticate(request, username=username, password=password)
        
        if user:
            login(request, user)
            token, created = Token.objects.get_or_create(user=user)
            
            # 返回更完整的用户信息和token
            return Response({
                'status': 'success',
                'message': '登录成功',
                'token': token.key,
                'user_info': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                }
            }, status=status.HTTP_200_OK)
        
        return Response({
            'status': 'error',
            'message': '用户名或密码错误'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    return Response({
        'status': 'error',
        'message': '参数错误',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)
```

### 4.4 API响应优化

**问题**: 微信小程序对API响应时间和格式有严格要求

**解决方案**: 优化API响应格式和性能

**代码调整**:
```python
# api/exceptions.py - 统一异常处理
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    """自定义异常处理，统一API响应格式"""
    response = exception_handler(exc, context)
    
    if response is not None:
        # 统一错误响应格式
        response.data = {
            'status': 'error',
            'code': response.status_code,
            'message': response.data.get('detail', '请求失败'),
            'data': None
        }
    else:
        # 未捕获的异常
        response = Response({
            'status': 'error',
            'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
            'message': '服务器内部错误',
            'data': None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return response

# settings.py - 配置自定义异常处理
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'api.exceptions.custom_exception_handler',
    # 其他配置...
}
```

### 4.5 微信小程序专属API（可选）

**问题**: 可以提供专门针对微信小程序的功能接口

**解决方案**: 增加微信登录和小程序特定功能接口

**代码调整**:
```python
# api/views.py - 微信小程序登录接口
@api_view(['POST'])
def wechat_login(request):
    """微信小程序登录接口"""
    code = request.data.get('code')
    if not code:
        return Response({
            'status': 'error',
            'message': '缺少code参数'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # 调用微信API获取session_key和openid
        import requests
        wechat_url = f"https://api.weixin.qq.com/sns/jscode2session"
        params = {
            'appid': '你的小程序AppID',
            'secret': '你的小程序AppSecret',
            'js_code': code,
            'grant_type': 'authorization_code'
        }
        
        response = requests.get(wechat_url, params=params)
        data = response.json()
        
        if 'errcode' in data:
            return Response({
                'status': 'error',
                'message': '微信登录失败',
                'errcode': data['errcode'],
                'errmsg': data['errmsg']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        openid = data['openid']
        session_key = data['session_key']
        
        # 根据openid查找或创建用户
        from django.contrib.auth.models import User
        user, created = User.objects.get_or_create(username=openid)
        
        # 创建或获取token
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            'status': 'success',
            'message': '微信登录成功',
            'token': token.key,
            'user_info': {
                'id': user.id,
                'username': user.username,
                'openid': openid
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': '服务器错误',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# api/urls.py - 添加微信登录路由
path('auth/wechat-login/', views.wechat_login, name='wechat-login'),
```

## 五、实施清单与优先级

| 优先级 | 任务内容 | 实施说明 | 完成标记 |
|--------|----------|----------|----------|
| 高 | 申请并配置SSL证书 | 为域名et116374mm892.vicp.fun申请SSL证书 | □ |
| 高 | 配置HTTPS服务器 | 修改start_waitress_server.py支持HTTPS | □ |
| 高 | 更新ALLOWED_HOSTS和CORS配置 | 确保域名在白名单中，配置正确的跨域策略 | □ |
| 中 | 统一API响应格式 | 实现自定义异常处理，统一错误响应格式 | □ |
| 中 | 优化认证机制 | 增强登录接口，提供更完整的用户信息 | □ |
| 中 | 配置生产环境安全设置 | 启用HTTPS cookie、CSRF保护等 | □ |
| 低 | 实现微信登录接口 | 提供基于微信openid的登录方式 | □ |
| 低 | 增加小程序专属功能 | 根据需求开发小程序特定API | □ |

## 六、微信公众平台配置

1. 登录[微信公众平台](https://mp.weixin.qq.com/)
2. 进入小程序管理后台
3. 依次点击「开发」→「开发设置」→「服务器域名」
4. 添加以下域名到对应白名单：
   - request合法域名：`https://et116374mm892.vicp.fun`
   - uploadFile合法域名（如需文件上传）：`https://et116374mm892.vicp.fun`
   - downloadFile合法域名（如需文件下载）：`https://et116374mm892.vicp.fun`

## 七、测试建议

1. **HTTPS测试**: 使用curl或Postman测试HTTPS接口是否正常
   ```bash
   curl -v https://et116374mm892.vicp.fun/api/health/
   ```

2. **CORS测试**: 使用浏览器控制台测试跨域请求

3. **微信开发者工具测试**: 在微信开发者工具中测试所有API调用

4. **性能测试**: 确保API响应时间在微信小程序限制范围内（<5秒）

5. **安全测试**: 检查HTTPS证书有效性、CSRF保护、认证机制等

## 八、部署与维护

1. **Docker部署**: 可以使用Docker容器化部署，便于管理HTTPS证书

2. **自动化测试**: 为微信小程序API添加专门的自动化测试

3. **监控与日志**: 增加API调用监控和详细日志记录

4. **定期更新**: 定期更新依赖包和安全补丁

## 九、注意事项

1. **安全第一**: 确保所有接口都使用HTTPS，保护用户数据安全

2. **性能优化**: 优化数据库查询和API响应时间，避免超时

3. **错误处理**: 提供清晰的错误信息，便于小程序开发者调试

4. **文档更新**: 及时更新API文档，确保小程序开发者了解接口变化

5. **版本兼容性**: 确保API版本兼容性，避免破坏性更新影响小程序正常运行

---

**文档创建时间**: 2025年5月9日
**文档版本**: 1.0
**适用范围**: FreeArkWeb后端微信小程序适配
