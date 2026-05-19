#!/usr/bin/env bash
# =============================================================================
# rollback.sh
# FreeArk v0.5.0 → v0.4.7 生产回滚脚本
# 对应 deployment_plan.md §6 回滚方案
#
# 用法：
#   bash rollback.sh --snapshot-timestamp <ts>
#
#   <ts>：Step 3 备份时的时间戳，如 20260520_020000
#
# 示例：
#   bash rollback.sh --snapshot-timestamp 20260520_020000
#
# 选项：
#   --project-root <path>    项目根目录（默认 /opt/freeark）
#   --backup-dir <path>      备份根目录（默认 /opt/freeark/backup）
#   --frontend-dist <path>   Nginx 静态目录（默认 /usr/share/nginx/html）
#   --dry-run                仅打印将要执行的操作，不实际执行
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# 参数解析
# -----------------------------------------------------------------------------
SNAPSHOT_TIMESTAMP=""
PROJECT_ROOT="/opt/freeark"
BACKUP_DIR="/opt/freeark/backup"
FRONTEND_DIST="/usr/share/nginx/html"
DRY_RUN=false
ROLLBACK_COMMIT="b714db1"  # v0.4.7 commit hash

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot-timestamp)
      SNAPSHOT_TIMESTAMP="$2"
      shift 2
      ;;
    --project-root)
      PROJECT_ROOT="$2"
      shift 2
      ;;
    --backup-dir)
      BACKUP_DIR="$2"
      shift 2
      ;;
    --frontend-dist)
      FRONTEND_DIST="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "未知参数：$1"
      echo "用法：bash rollback.sh --snapshot-timestamp <ts> [--project-root <path>] [--backup-dir <path>] [--frontend-dist <path>] [--dry-run]"
      exit 1
      ;;
  esac
done

# -----------------------------------------------------------------------------
# 参数校验
# -----------------------------------------------------------------------------
if [[ -z "${SNAPSHOT_TIMESTAMP}" ]]; then
  echo "错误：必须提供 --snapshot-timestamp 参数"
  echo "示例：bash rollback.sh --snapshot-timestamp 20260520_020000"
  echo "提示：该时间戳在 production_runbook Step 3.5 的备份摘要中已打印"
  exit 1
fi

SNAPSHOT_PATH="${BACKUP_DIR}/${SNAPSHOT_TIMESTAMP}"

echo "========================================"
echo "FreeArk v0.5.0 → v0.4.7 回滚脚本"
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "快照时间戳：${SNAPSHOT_TIMESTAMP}"
echo "快照路径：${SNAPSHOT_PATH}"
echo "项目根目录：${PROJECT_ROOT}"
echo "Nginx 静态目录：${FRONTEND_DIST}"
echo "回滚目标 commit：${ROLLBACK_COMMIT}（v0.4.7）"
if [[ "${DRY_RUN}" == "true" ]]; then
  echo "*** DRY-RUN 模式：仅打印操作，不实际执行 ***"
fi
echo "========================================"
echo ""

# 工具函数
run() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY-RUN] 将执行：$*"
  else
    echo "[执行] $*"
    eval "$@"
  fi
}

# -----------------------------------------------------------------------------
# 前置检查
# -----------------------------------------------------------------------------
echo "=== 前置检查 ==="

echo "检查快照目录是否存在：${SNAPSHOT_PATH}"
if [[ ! -d "${SNAPSHOT_PATH}" ]]; then
  echo "错误：快照目录不存在（${SNAPSHOT_PATH}）"
  echo "请确认 --snapshot-timestamp 参数正确，或检查备份目录（${BACKUP_DIR}/）中已有的快照。"
  echo "可用快照列表："
  ls "${BACKUP_DIR}/" 2>/dev/null || echo "（备份目录不存在或为空）"
  exit 1
fi
echo "[OK] 快照目录存在"

echo "检查数据库备份文件：${SNAPSHOT_PATH}/db.sqlite3.bak"
if [[ ! -f "${SNAPSHOT_PATH}/db.sqlite3.bak" ]]; then
  echo "错误：数据库备份文件不存在（${SNAPSHOT_PATH}/db.sqlite3.bak）"
  echo "无法安全回滚数据库，请手动检查备份内容后决定是否继续。"
  exit 1
fi
echo "[OK] 数据库备份文件存在"

echo "检查前端备份目录：${SNAPSHOT_PATH}/nginx_html_v0.4.7/"
if [[ ! -d "${SNAPSHOT_PATH}/nginx_html_v0.4.7/" ]]; then
  echo "警告：前端备份目录不存在（${SNAPSHOT_PATH}/nginx_html_v0.4.7/）"
  echo "将跳过前端 dist 恢复，仅回滚代码和数据库。"
  SKIP_FRONTEND=true
else
  echo "[OK] 前端备份目录存在"
  SKIP_FRONTEND=false
fi

echo ""
echo "前置检查完成，开始执行回滚流程。"
echo ""

# -----------------------------------------------------------------------------
# 步骤 R1：git checkout 回滚到 v0.4.7
# -----------------------------------------------------------------------------
echo "=== 步骤 R1：代码回滚至 v0.4.7（commit ${ROLLBACK_COMMIT}）==="

run "cd ${PROJECT_ROOT} && git log --oneline -1"

echo "回滚代码至 commit ${ROLLBACK_COMMIT}..."
run "cd ${PROJECT_ROOT} && git checkout ${ROLLBACK_COMMIT}"

if [[ "${DRY_RUN}" == "false" ]]; then
  CURRENT_HEAD=$(cd "${PROJECT_ROOT}" && git log --oneline -1)
  echo "[验证] 当前 HEAD：${CURRENT_HEAD}"
fi

echo "[完成] 代码已回滚至 v0.4.7"
echo ""

# -----------------------------------------------------------------------------
# 步骤 R2：恢复数据库（SQLite 文件直接替换）
# -----------------------------------------------------------------------------
echo "=== 步骤 R2：恢复数据库备份 ==="

DB_PATH="${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb/db.sqlite3"
echo "备份来源：${SNAPSHOT_PATH}/db.sqlite3.bak"
echo "恢复目标：${DB_PATH}"

# 先将当前 v0.5.0 数据库保留一份（以防误操作，可人工恢复）
if [[ -f "${DB_PATH}" ]]; then
  run "cp ${DB_PATH} ${SNAPSHOT_PATH}/db.sqlite3.v050_before_rollback.bak"
  echo "[保留] v0.5.0 数据库已另存至：${SNAPSHOT_PATH}/db.sqlite3.v050_before_rollback.bak"
fi

run "cp ${SNAPSHOT_PATH}/db.sqlite3.bak ${DB_PATH}"
echo "[完成] 数据库已恢复至 v0.4.7 快照"

# 验证恢复后 system_switch is_active 应为 True（v0.4.7 基线）
if [[ "${DRY_RUN}" == "false" ]]; then
  echo "验证回滚后 system_switch is_active..."
  cd "${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb"
  SEED_CHECK=$(python manage.py shell -c "
from api.models import DeviceConfig
obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
print(obj.is_active if obj else 'NOT_FOUND')
" 2>/dev/null || echo "SHELL_ERROR")
  echo "[验证] system_switch is_active = ${SEED_CHECK}（v0.4.7 基线期望值：True）"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 R3：恢复前端 dist
# -----------------------------------------------------------------------------
echo "=== 步骤 R3：恢复前端静态资源（v0.4.7 快照）==="

if [[ "${SKIP_FRONTEND}" == "true" ]]; then
  echo "[跳过] 前端备份目录不存在，跳过前端 dist 恢复"
  echo "警告：Nginx 当前仍提供 v0.5.0 前端文件，后端已回滚至 v0.4.7，可能存在前后端版本不一致"
  echo "建议：手动恢复 v0.4.7 前端 dist，或重新构建 v0.4.7 版本"
else
  echo "备份来源：${SNAPSHOT_PATH}/nginx_html_v0.4.7/"
  echo "恢复目标：${FRONTEND_DIST}/"
  run "rsync -av --delete ${SNAPSHOT_PATH}/nginx_html_v0.4.7/ ${FRONTEND_DIST}/"
  echo "[完成] 前端 dist 已恢复至 v0.4.7 快照"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 R4：重启后端服务
# -----------------------------------------------------------------------------
echo "=== 步骤 R4：重启后端服务 ==="

run "systemctl restart freeark-backend"
echo "[等待] 等待服务启动（10s）..."
if [[ "${DRY_RUN}" == "false" ]]; then
  sleep 10
fi
run "systemctl status freeark-backend --no-pager"

echo "[完成] 后端服务已重启"
echo ""

# -----------------------------------------------------------------------------
# 步骤 R5：Nginx 重载
# -----------------------------------------------------------------------------
echo "=== 步骤 R5：Nginx 配置检查与重载 ==="

run "nginx -t"
run "nginx -s reload"

echo "[完成] Nginx 已重载"
echo ""

# -----------------------------------------------------------------------------
# 步骤 R6：回滚后验证清单
# -----------------------------------------------------------------------------
echo "=== 步骤 R6：回滚后验证清单 ==="

if [[ "${DRY_RUN}" == "false" ]]; then
  echo "执行快速验证..."

  echo ""
  echo "[验证 R6-1] 后端健康检查..."
  HTTP_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout 10 --max-time 15 \
    "http://localhost:8000/api/health/" || echo "000")
  if [[ "${HTTP_HEALTH}" == "200" ]]; then
    echo "[PASS] 后端健康检查 HTTP 200"
  else
    echo "[FAIL] 后端健康检查异常（HTTP ${HTTP_HEALTH}）"
  fi

  echo ""
  echo "[验证 R6-2] 前端可访问..."
  HTTP_FE=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout 10 --max-time 15 \
    "http://localhost/" || echo "000")
  if [[ "${HTTP_FE}" == "200" ]]; then
    echo "[PASS] 前端 HTTP 200"
  else
    echo "[FAIL] 前端访问异常（HTTP ${HTTP_FE}）"
  fi

  echo ""
  echo "[验证 R6-3] system_switch is_active 应为 True（v0.4.7 基线）..."
  cd "${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb"
  RB_CHECK=$(python manage.py shell -c "
from api.models import DeviceConfig
obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
print(obj.is_active if obj else 'NOT_FOUND')
" 2>/dev/null || echo "SHELL_ERROR")
  if [[ "${RB_CHECK}" == "True" ]]; then
    echo "[PASS] system_switch is_active=True（v0.4.7 基线已恢复）"
  else
    echo "[FAIL] system_switch is_active=${RB_CHECK}（期望 True，数据库恢复可能未成功）"
  fi

  echo ""
  echo "[验证 R6-4] operation_mode 写入白名单应不包含 _mode 后缀（v0.4.7 行为验证）..."
  cd "${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb"
  MODE_CHECK=$(python manage.py shell -c "
import sys
sys.path.insert(0, '.')
from api.views_device_settings import WRITABLE_SUFFIXES
print('_mode in WRITABLE_SUFFIXES:', '_mode' in WRITABLE_SUFFIXES)
" 2>/dev/null || echo "SHELL_ERROR")
  if [[ "${MODE_CHECK}" == "_mode in WRITABLE_SUFFIXES: False" ]]; then
    echo "[PASS] _mode 不在 WRITABLE_SUFFIXES 中（v0.4.7 行为已恢复）"
  else
    echo "[信息] ${MODE_CHECK}（若为 True 说明代码未完全回滚，请检查 git checkout 结果）"
  fi
fi

# -----------------------------------------------------------------------------
# 回滚完成摘要
# -----------------------------------------------------------------------------
echo ""
echo "========================================"
echo "回滚操作完成"
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "回滚目标版本：v0.4.7（commit ${ROLLBACK_COMMIT}）"
echo "使用快照：${SNAPSHOT_PATH}/"
if [[ "${DRY_RUN}" == "true" ]]; then
  echo "*** DRY-RUN 模式：以上均为模拟输出，未实际执行任何操作 ***"
fi
echo ""
echo "请手动确认："
echo "  1. 浏览器访问设备设置页面，确认主温控系统开关重新出现（is_active=True 已恢复）"
echo "  2. 确认 operation_mode 写入返回 HTTP 400（v0.4.7 白名单不含 _mode）"
echo "  3. 更新 deployment_report.md：is_rollback=true，final_status=FAILED_ROLLED_BACK"
echo "========================================"
