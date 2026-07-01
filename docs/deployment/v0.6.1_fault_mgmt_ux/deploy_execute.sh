#!/usr/bin/env bash
# =============================================================================
# deploy_execute.sh — v0.6.1-FM-UX 生产部署执行脚本
# 目标主机：树莓派 Pi 5，et116374mm892.vicp.fun:57279
# 用法：bash deploy_execute.sh
# 注意：需要 SSH 密钥免密，在 Windows 下用 Git Bash 或 WSL 执行
# =============================================================================

set -euo pipefail

SSH_HOST="yangyang@et116374mm892.vicp.fun"
SSH_PORT="57279"
REPO_ROOT="/home/yangyang/Freeark/FreeArk"
FRONTEND_DIR="$REPO_ROOT/FreeArkWeb/frontend"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"
BACKUP_DIR="/home/yangyang/FreeArk_backup"
TIMESTAMP=$(date +%Y%m%d%H%M%S)

echo "============================================================"
echo "v0.6.1-FM-UX 生产部署 — $(date)"
echo "============================================================"

# ----- Step 1: 部署前置检查 -----
echo ""
echo "=== Step 1: 部署前置检查 ==="
ssh -p "$SSH_PORT" "$SSH_HOST" "
  cd $REPO_ROOT
  echo '--- git status ---'
  git status --short
  echo '--- git log -1 ---'
  git log -1 --oneline
  echo '--- freeark-backend 当前状态 ---'
  systemctl is-active freeark-backend
"

echo ""
read -p "Step 1 结果确认: git status 仅有三个长期本地修改？(y/n): " confirm_step1
if [[ "$confirm_step1" != "y" ]]; then
  echo "Step 1 验证失败，中止部署！"
  exit 1
fi

# ----- Step 2: git pull -----
echo ""
echo "=== Step 2: git pull origin main ==="
ssh -p "$SSH_PORT" "$SSH_HOST" "
  cd $REPO_ROOT
  git pull origin main
"

# ----- Step 3: 验证落地 -----
echo ""
echo "=== Step 3: 验证落地 ==="
ssh -p "$SSH_PORT" "$SSH_HOST" "
  cd $REPO_ROOT
  echo '--- 当前 HEAD ---'
  git log -1 --oneline
  echo '--- device_name_cache.py ---'
  ls -la FreeArkWeb/backend/freearkweb/api/device_name_cache.py
  echo '--- PRODUCT_CODE_LABELS 出现次数 ---'
  grep -c PRODUCT_CODE_LABELS FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py
"

# ----- Step 4: 前端构建 -----
echo ""
echo "=== Step 4: 前端构建（备份 + npm run build）==="
BUILD_START=$(date +%s)
ssh -p "$SSH_PORT" "$SSH_HOST" "
  cd $FRONTEND_DIR
  echo '--- 备份现有 dist ---'
  cp -r dist $BACKUP_DIR/dist_backup_$TIMESTAMP
  echo '--- npm run build ---'
  npm run build 2>&1 | tail -30
"
BUILD_END=$(date +%s)
BUILD_ELAPSED=$((BUILD_END - BUILD_START))
echo "前端构建耗时: ${BUILD_ELAPSED}s"

# ----- Step 5: 重启后端 -----
echo ""
echo "=== Step 5: 重启 freeark-backend ==="
ssh -p "$SSH_PORT" "$SSH_HOST" "
  sudo systemctl restart freeark-backend
  sleep 3
  echo '--- is-active ---'
  systemctl is-active freeark-backend
  echo '--- journal 末 30 行 ---'
  sudo journalctl -u freeark-backend -n 30 --no-pager
"

# ----- Step 6a: 健康检查 -----
echo ""
echo "=== Step 6a: 健康检查 ==="
ssh -p "$SSH_PORT" "$SSH_HOST" "
  curl -sS http://127.0.0.1:8080/api/health/ -m 10 || \
  curl -sS http://127.0.0.1:8000/api/health/ -m 10 || \
  echo 'health check: 8080/8000 均无响应，尝试检查路由'
"

# ----- Step 6b: 序列化器字段验证 -----
echo ""
echo "=== Step 6b: 序列化器字段验证（device_name / device_type_label）==="
ssh -p "$SSH_PORT" "$SSH_HOST" "
  cd $REPO_ROOT/FreeArkWeb/backend/freearkweb
  $VENV_PYTHON manage.py shell -c \"
from api.models import FaultEvent
from api.serializers_fault import FaultEventSerializer
fe = FaultEvent.objects.first()
if fe:
    data = FaultEventSerializer(fe).data
    print('device_name:', data.get('device_name'))
    print('device_type_label:', data.get('device_type_label'))
    print('sn:', data.get('device_sn'))
else:
    print('No FaultEvent records — 验证路由可达性:')
    import subprocess
    r = subprocess.run(['curl','-sS','-o','/dev/null','-w','%{http_code}',
        'http://127.0.0.1:8000/api/devices/fault-events/?page_size=1','-m','5'],
        capture_output=True, text=True)
    print('HTTP status:', r.stdout)
\"
"

echo ""
echo "============================================================"
echo "v0.6.1-FM-UX 部署执行完毕 — $(date)"
echo "构建耗时: ${BUILD_ELAPSED}s"
echo "============================================================"
