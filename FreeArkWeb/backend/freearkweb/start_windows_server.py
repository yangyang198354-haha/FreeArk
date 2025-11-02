#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FreeArkWeb后端Windows启动脚本

此脚本直接在项目目录中运行，避免路径问题
使用waitress作为WSGI服务器替代Gunicorn（Windows兼容）
"""

import os
import sys
import subprocess

# 设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
os.environ.setdefault('DEBUG', 'False')

# 创建日志目录（如果不存在）
log_dir = os.path.join(os.getcwd(), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
    print(f"创建日志目录: {log_dir}")

# 确保依赖已安装
try:
    import dotenv
except ImportError:
    print("安装python-dotenv...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-dotenv'])

try:
    import waitress
except ImportError:
    print("安装waitress...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'waitress'])

# 收集静态文件
print("收集静态文件...")
subprocess.check_call([sys.executable, 'manage.py', 'collectstatic', '--noinput'])

# 使用waitress启动应用
print("启动Waitress服务器...")
print("服务将在 http://0.0.0.0:8000 上运行")
print("按 Ctrl+C 停止服务")

from waitress import serve
from freearkweb.wsgi import application

# 确保使用0.0.0.0以允许从任何网络接口访问
serve(application, host='0.0.0.0', port=8000)