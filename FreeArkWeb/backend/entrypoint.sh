#!/bin/bash

# 设置环境变量
export DJANGO_SETTINGS_MODULE=freearkweb.settings
export DEBUG=${DEBUG:-False}

# 加载.env文件（如果存在）
if [ -f "/app/freearkweb/.env" ]; then
    echo "加载环境变量文件..."
    export $(cat /app/freearkweb/.env | grep -v '^#' | xargs)
fi

# 创建日志目录（如果不存在）
mkdir -p /app/logs

# 收集静态文件
echo "收集静态文件..."
python /app/freearkweb/manage.py collectstatic --noinput

# 运行数据库迁移（可选，如果需要）
# echo "运行数据库迁移..."
# python /app/freearkweb/manage.py migrate

# 使用waitress启动应用
echo "启动Waitress服务器..."
echo "服务将在 http://0.0.0.0:8000 上运行"

# 创建临时启动脚本
cat > /app/start_server.py << 'EOF'
#!/usr/bin/env python3
import os

# 设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')

# 导入并启动服务
from waitress import serve
from freearkweb.wsgi import application

if __name__ == '__main__':
    serve(application, host='0.0.0.0', port=8000)
EOF

# 运行启动脚本
python /app/start_server.py