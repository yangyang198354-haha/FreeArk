#!/bin/bash

# 进入脚本所在目录
cd "$(dirname "$0")"

# 创建日志目录（如果不存在）
mkdir -p logs

echo "FreeArkWeb后端Linux启动脚本"
echo "使用waitress作为WSGI服务器"

# 检查虚拟环境是否存在，如果不存在则创建
if [ ! -d "venv" ]; then
    echo "虚拟环境不存在，正在创建..."
    python3 -m venv venv
fi

# 激活虚拟环境（使用POSIX兼容的点号命令）
echo "激活虚拟环境..."
. venv/bin/activate

# 在虚拟环境中安装所需依赖
echo "安装必要依赖..."
pip install --upgrade pip
pip install waitress python-dotenv --upgrade

# 确保Django依赖已安装
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# 设置环境变量
export DJANGO_SETTINGS_MODULE="freearkweb.settings"
export DEBUG="False"

# 收集静态文件
echo "收集静态文件..."
python manage.py collectstatic --noinput

# 创建一个临时的Python脚本来启动waitress
cat > start_waitress.py << 'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用waitress启动Django应用"""

import os
import sys

# 设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
os.environ.setdefault('DEBUG', 'False')

from waitress import serve
from freearkweb.wsgi import application

print("启动Waitress服务器...")
print("服务将在 http://0.0.0.0:8000 上运行")

# 确保使用0.0.0.0以允许从任何网络接口访问
serve(application, host='0.0.0.0', port=8000)
EOF

# 启动后端服务器，使用nohup并将日志重定向到logs目录
echo "启动后端服务器..."
nohup python start_waitress.py > logs/backend.log 2>&1 &

echo "后端服务器已启动，进程ID: $!"
echo "日志输出到 logs/backend.log"
echo "可以使用 'tail -f logs/backend.log' 查看日志"
echo "使用 'kill $!' 停止服务"
