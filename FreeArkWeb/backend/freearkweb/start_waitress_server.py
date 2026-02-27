#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FreeArkWeb后端启动脚本

此脚本兼容Windows和Linux平台
使用waitress作为WSGI服务器（跨平台兼容）
"""

import os
import sys
import subprocess
import platform

# 获取当前脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"脚本运行目录: {script_dir}")

# 设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
os.environ.setdefault('ALLOWED_HOSTS', 'localhost,127.0.0.1,192.168.31.51,192.168.31.52,et116374mm892.vicp.fun')

os.environ.setdefault('DEBUG', 'False')

# 获取操作系统信息
current_os = platform.system()
print(f"当前操作系统: {current_os}")

# 创建日志目录（如果不存在）
log_dir = os.path.join(script_dir, 'logs')
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

# 找到manage.py文件
manage_py_path = os.path.join(script_dir, 'manage.py')
if not os.path.exists(manage_py_path):
    # 尝试在其他可能的位置查找manage.py
    parent_dir = os.path.dirname(script_dir)
    alternative_manage_py = os.path.join(parent_dir, 'manage.py')
    if os.path.exists(alternative_manage_py):
        manage_py_path = alternative_manage_py
    else:
        print(f"错误: 找不到manage.py文件，尝试路径: {manage_py_path} 和 {alternative_manage_py}")
        sys.exit(1)

print(f"使用manage.py路径: {manage_py_path}")

# 收集静态文件
try:
    print("收集静态文件...")
    # 使用绝对路径调用manage.py
    subprocess.check_call([sys.executable, manage_py_path, 'collectstatic', '--noinput'])
except subprocess.CalledProcessError as e:
    print(f"收集静态文件时出错: {e}")
    print("尝试继续启动服务...")

# 使用waitress启动应用
print("启动Waitress服务器...")
print("服务将在 http://0.0.0.0:8000 上运行")
print("按 Ctrl+C 停止服务")

try:
    from waitress import serve
    # 确保正确导入应用
    sys.path.append(script_dir)
    from freearkweb.wsgi import application
    
    # 确保使用0.0.0.0以允许从任何网络接口访问
    serve(application, host='0.0.0.0', port=8000)
except ImportError as e:
    print(f"导入错误: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    print("服务已停止")
except Exception as e:
    print(f"服务启动失败: {e}")
    sys.exit(1)