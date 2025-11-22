#!/bin/bash

# 进入项目根目录（脚本所在目录）
cd "$(dirname "$0")"

# 创建日志目录（如果不存在）
mkdir -p logs

echo "FreeArkWeb后端Linux启动脚本"
echo "使用跨平台Python脚本启动服务"

# 检查虚拟环境是否存在，如果不存在则创建（在脚本所在目录）
if [ ! -d "venv" ]; then
    echo "虚拟环境不存在，正在创建..."
    python3 -m venv venv
fi

# 激活虚拟环境（使用POSIX兼容的点号命令）
echo "激活虚拟环境..."
source venv/bin/activate

# 在虚拟环境中安装所需依赖
echo "安装必要依赖..."
pip install --upgrade pip
pip install waitress python-dotenv --upgrade

# 定义后端目录路径
BACKEND_DIR="FreeArkWeb/backend/freearkweb"

# 确保Django依赖已安装
if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    echo "安装Django依赖..."
    pip install -r "$BACKEND_DIR/requirements.txt"
fi

# 检查start_windows_server.py文件是否存在
if [ -f "$BACKEND_DIR/start_windows_server.py" ]; then
    echo "找到跨平台启动脚本: $BACKEND_DIR/start_windows_server.py"
    # 设置执行权限
    chmod +x "$BACKEND_DIR/start_windows_server.py"
    
    # 启动后端服务器，使用nohup并将日志重定向到logs目录
    echo "启动后端服务器..."
    # 注意：这里直接使用当前激活的虚拟环境运行脚本
    nohup python "$BACKEND_DIR/start_windows_server.py" > logs/backend.log 2>&1 &
    
    echo "后端服务器已启动，进程ID: $!"
    echo "日志输出到 logs/backend.log"
    echo "可以使用 'tail -f logs/backend.log' 查看日志"
    echo "使用 'kill $!' 停止服务"
else
    echo "错误: 找不到start_windows_server.py文件"
    echo "请确保文件位于 $BACKEND_DIR 目录中"
    exit 1
fi
