# FreeArkWeb 后端服务生产环境部署指南

本文档提供了 FreeArkWeb 后端服务在生产环境中使用 Waitress 作为 WSGI 服务器的部署指南。

## 准备工作

1. **安装 Python 环境**
   - 确保系统已安装 Python 3.9+（推荐 Python 3.10）
   - 建议使用虚拟环境进行隔离

2. **安装依赖**
   ```bash
   cd c:/Users/yanggyan/TRAE/FreeArk/FreeArkWeb/backend
   pip install -r requirements.txt
   ```

3. **准备数据库**
   - 确保 MySQL 数据库已安装并运行
   - 创建数据库 `freeark`

## 配置环境变量

1. 复制环境变量示例文件
   ```bash
   cp .env.production .env
   ```

2. 编辑 `.env` 文件，设置必要的环境变量
   ```
   # 生成一个安全的密钥
   # 方法1: 使用我们提供的脚本
   ```bash
   python generate_secret_key.py
   ```
   # 方法2: 直接在 Python 交互式环境中使用 Django 函数
   ```python
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
   # 方法3: 手动安装 Django 后使用
   ```bash
   pip install django
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
   # 生成后，将密钥复制到 .env 文件中的 SECRET_KEY 字段
   SECRET_KEY=your_secure_random_secret_key_here
   
   # 设置允许的主机为您的实际域名或 IP
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   
   # 设置数据库密码
   DB_PASSWORD=your_secure_password_here
   
   # 其他配置根据实际情况调整
   ```

## 收集静态文件

```bash
cd c:/Users/yanggyan/TRAE/FreeArk/FreeArkWeb/backend/freearkweb
python manage.py collectstatic --noinput
```

## 使用 Waitress 启动服务

Waitress 是一个纯 Python 实现的 WSGI 服务器，与 Windows 完全兼容，也适用于 Linux 和 macOS 环境。

```cmd
cd c:\Users\yanggyan\TRAE\FreeArk\FreeArkWeb\backend\freearkweb
python start_waitress_server.py
```

该脚本会自动：
- 检查并安装必要的依赖
- 设置环境变量
- 创建日志目录
- 收集静态文件
- 启动 Waitress 服务器，监听在 127.0.0.1:8000

## 配置 Nginx 作为反向代理（推荐）

在生产环境中，建议使用 Nginx 作为反向代理，处理静态文件并将动态请求转发给 Waitress。

### Nginx 配置示例

```nginx
upstream freearkweb {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # 重定向到 HTTPS（如果启用）
    # return 301 https://$server_name$request_uri;
    
    # 静态文件配置
    location /static/ {
        alias c:/Users/yanggyan/TRAE/FreeArk/FreeArkWeb/backend/freearkweb/staticfiles/;
        expires 30d;
    }
    
    # 媒体文件配置（如果有）
    location /media/ {
        alias c:/Users/yanggyan/TRAE/FreeArk/FreeArkWeb/backend/freearkweb/media/;
        expires 30d;
    }
    
    # 动态请求转发
    location / {
        proxy_pass http://freearkweb;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# HTTPS 配置（可选）
# server {
#     listen 443 ssl;
#     server_name yourdomain.com www.yourdomain.com;
#     
#     ssl_certificate /path/to/ssl/cert.pem;
#     ssl_certificate_key /path/to/ssl/key.pem;
#     
#     # 静态文件和动态请求配置与上面相同
# }
```



## 日志管理

### 日志文件位置
- Django 应用日志：`c:/Users/yanggyan/TRAE/FreeArk/logs/django.log`

日志配置已包含轮转设置，单个日志文件最大 5MB，保留最近 5 个备份文件。

## 安全建议

1. **环境变量安全**
   - 不要在代码中硬编码敏感信息
   - 定期更换 SECRET_KEY
   - 数据库密码应使用强密码

2. **服务器安全**
   - 定期更新系统和依赖包
   - 配置防火墙，只开放必要的端口
   - 启用 HTTPS

3. **数据库安全**
   - 限制数据库用户权限
   - 定期备份数据库
   - 考虑使用连接池提高性能和安全性

## 性能优化建议

1. **启用缓存**
   - 考虑使用 Redis 或 Memcached 作为缓存后端
   - 配置视图缓存和模板缓存

2. **数据库优化**
   - 添加适当的索引
   - 优化查询
   - 考虑使用连接池



## 故障排除

1. **服务无法启动**
   - 检查端口是否被占用
   - 查看日志文件中的错误信息
   - 确认数据库连接配置正确

2. **静态文件无法访问**
   - 确保已运行 `collectstatic` 命令
   - 检查 Nginx 静态文件路径配置是否正确

3. **性能问题**
   - 检查数据库查询性能
   - 监控服务器资源使用情况
   - 考虑增加工作进程数或升级服务器配置

## 部署检查清单

- [ ] 已设置安全的 SECRET_KEY
- [ ] DEBUG 模式已关闭
- [ ] ALLOWED_HOSTS 已正确配置
- [ ] 数据库连接配置正确
- [ ] 已收集静态文件
- [ ] 已配置适当的日志级别
- [ ] 已启用必要的安全中间件
- [ ] Nginx 配置正确（如果使用）
- [ ] 进程管理工具已配置（如果使用）
- [ ] 系统防火墙已正确配置