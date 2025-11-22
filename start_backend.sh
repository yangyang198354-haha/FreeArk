#!/bin/bash

# 进入项目根目录
cd "$(dirname "$0")"

# 创建日志目录（如果不存在）
mkdir -p logs

# 激活虚拟环境
source venv/bin/activate

# 启动后端服务器，使用nohup并将日志重定向到logs目录
nohup python FreeArkWeb/backend/freearkweb/start_windows_server.py > logs/backend.log 2>&1 &

echo "后端服务器已启动，日志输出到 logs/backend.log"
