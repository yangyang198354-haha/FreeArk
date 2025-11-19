#!/bin/bash

# FreeArk 数据收集模块部署脚本
# 该脚本将FreeArk数据收集模块部署为Linux系统服务和Docker容器

echo "====================================="
echo "FreeArk 数据收集模块部署脚本"
echo "====================================="

# 检查是否有root权限
if [ "$EUID" -ne 0 ]; then
  echo "❌ 请使用root权限运行此脚本"
  exit 1
fi

# 检查Docker是否已安装
if ! command -v docker &> /dev/null; then
  echo "❌ Docker未安装，正在安装..."
  # 安装Docker
  curl -fsSL https://get.docker.com -o get-docker.sh
  sh get-docker.sh
  rm get-docker.sh
  
  # 启动Docker服务
  systemctl start docker
  systemctl enable docker
  
  echo "✅ Docker安装完成"
fi

# 检查Docker Compose是否已安装
if ! command -v docker-compose &> /dev/null; then
  echo "❌ Docker Compose未安装，正在安装..."
  # 安装Docker Compose
  curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  
  echo "✅ Docker Compose安装完成"
fi

# 创建部署目录
DEPLOY_DIR="/opt/freeark"
if [ ! -d "$DEPLOY_DIR" ]; then
  mkdir -p "$DEPLOY_DIR"
  echo "✅ 部署目录 $DEPLOY_DIR 创建完成"
fi

# 复制项目文件到部署目录
cp -r .. "$DEPLOY_DIR"
echo "✅ 项目文件复制完成"

# 设置权限
chmod -R 755 "$DEPLOY_DIR"
echo "✅ 权限设置完成"

# 复制systemd服务文件
cp "$DEPLOY_DIR/datacollection/freeark-data-collector.service" /etc/systemd/system/
echo "✅ Systemd服务文件复制完成"

# 重新加载systemd配置
systemctl daemon-reload

# 启用并启动服务
systemctl enable freeark-data-collector
systemctl start freeark-data-collector

# 检查服务状态
echo "====================================="
echo "服务状态检查"
echo "====================================="
systemctl status freeark-data-collector --no-pager

# 显示日志
echo "====================================="
echo "最新日志"
echo "====================================="
journalctl -u freeark-data-collector -n 20 --no-pager

echo "====================================="
echo "部署完成！"
echo "服务名称：freeark-data-collector"
echo "部署目录：$DEPLOY_DIR"
echo "配置文件：$DEPLOY_DIR/resource/task_scheduler_config.json"
echo "输出目录：$DEPLOY_DIR/output"
echo "查看日志：journalctl -u freeark-data-collector -f"
echo "重启服务：systemctl restart freeark-data-collector"
echo "停止服务：systemctl stop freeark-data-collector"
echo "====================================="