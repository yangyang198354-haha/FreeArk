#!/usr/bin/env bash
# =============================================================================
# verify_deployment.sh
# FreeArk v0.5.0 生产部署自动化验证脚本
# 目标主机：192.168.31.51
# 用法：bash verify_deployment.sh [--project-root /opt/freeark]
#
# 幂等可重跑：所有检查均为只读操作，不修改任何系统状态
# 输出规范：每项 [PASS] 或 [FAIL] 开头，最终输出 DEPLOYMENT_VERIFIED=true/false
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# 参数解析
# -----------------------------------------------------------------------------
PROJECT_ROOT="/opt/freeark"
FRONTEND_DIST="/usr/share/nginx/html"
BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="$2"
      shift 2
      ;;
    --backend-url)
      BACKEND_URL="$2"
      shift 2
      ;;
    --frontend-url)
      FRONTEND_URL="$2"
      shift 2
      ;;
    *)
      echo "未知参数：$1（忽略）"
      shift
      ;;
  esac
done

MANAGE_PY="${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb/manage.py"
DIST_ASSETS="${FRONTEND_DIST}/assets"

# -----------------------------------------------------------------------------
# 工具函数
# -----------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "[PASS] $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "[FAIL] $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

section() {
  echo ""
  echo "========================================"
  echo "  $1"
  echo "========================================"
}

# -----------------------------------------------------------------------------
echo "FreeArk v0.5.0 部署验证脚本"
echo "目标：192.168.31.51"
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "PROJECT_ROOT：${PROJECT_ROOT}"
echo "FRONTEND_DIST：${FRONTEND_DIST}"
echo "BACKEND_URL：${BACKEND_URL}"
echo "FRONTEND_URL：${FRONTEND_URL}"
# -----------------------------------------------------------------------------

# =============================================================================
# 检查 1：后端健康检查（HTTP 200）
# =============================================================================
section "检查 1/5：后端 API 健康检查"

echo "请求：GET ${BACKEND_URL}/api/health/"
HTTP_CODE_HEALTH=$(curl -s -o /tmp/vfy_health_resp.json -w "%{http_code}" \
  --connect-timeout 10 --max-time 15 \
  "${BACKEND_URL}/api/health/" || echo "000")

echo "响应状态码：${HTTP_CODE_HEALTH}"
cat /tmp/vfy_health_resp.json 2>/dev/null && echo ""

if [[ "${HTTP_CODE_HEALTH}" == "200" ]]; then
  pass "后端健康检查返回 HTTP 200"
else
  fail "后端健康检查异常（期望 200，实际 ${HTTP_CODE_HEALTH}）——后端服务可能未启动或端口错误"
fi

# =============================================================================
# 检查 2：设备设置 API 路由可达（未认证应返回 401）
# =============================================================================
section "检查 2/5：设备设置 API 路由可达性（期望 HTTP 401）"

echo "请求：GET ${BACKEND_URL}/api/device-settings/params/test_part/"
HTTP_CODE_API=$(curl -s -o /dev/null -w "%{http_code}" \
  --connect-timeout 10 --max-time 15 \
  "${BACKEND_URL}/api/device-settings/params/test_part/" || echo "000")

echo "响应状态码：${HTTP_CODE_API}"

if [[ "${HTTP_CODE_API}" == "401" ]]; then
  pass "设备设置 API 路由可达，未认证返回 HTTP 401（路由已注册，认证中间件生效）"
elif [[ "${HTTP_CODE_API}" == "200" ]]; then
  pass "设备设置 API 路由可达（已认证环境返回 200，亦可接受）"
else
  fail "设备设置 API 路由异常（期望 401，实际 ${HTTP_CODE_API}）——可能 URL 路由未注册或服务崩溃"
fi

# =============================================================================
# 检查 3：前端静态资源可访问（HTTP 200）
# =============================================================================
section "检查 3/5：前端静态资源可访问性（期望 HTTP 200）"

echo "请求：GET ${FRONTEND_URL}/"
HTTP_CODE_FE=$(curl -s -o /dev/null -w "%{http_code}" \
  --connect-timeout 10 --max-time 15 \
  "${FRONTEND_URL}/" || echo "000")

echo "响应状态码：${HTTP_CODE_FE}"

if [[ "${HTTP_CODE_FE}" == "200" ]]; then
  pass "前端静态资源 HTTP 200，Nginx 正常提供 index.html"
else
  fail "前端静态资源异常（期望 200，实际 ${HTTP_CODE_FE}）——检查 Nginx 服务状态及 ${FRONTEND_DIST}/index.html 是否存在"
fi

# =============================================================================
# 检查 4：bundle 中存在 markDirty 标识（证明 FR-001 hotfix 已编入构建产物）
# =============================================================================
section "检查 4/5：前端 bundle 包含 markDirty 标识（FR-001 hotfix 验证）"

echo "扫描路径：${DIST_ASSETS}/*.js"

if [[ ! -d "${DIST_ASSETS}" ]]; then
  fail "assets 目录不存在（${DIST_ASSETS}）——前端构建产物可能未正确部署至 ${FRONTEND_DIST}"
else
  JS_FILES=$(ls "${DIST_ASSETS}"/*.js 2>/dev/null || echo "")
  if [[ -z "${JS_FILES}" ]]; then
    fail "未在 ${DIST_ASSETS} 中找到 .js 文件——前端 bundle 缺失"
  else
    echo "找到 JS 文件："
    ls "${DIST_ASSETS}"/*.js
    if grep -rl "markDirty" "${DIST_ASSETS}"/*.js > /dev/null 2>&1; then
      pass "markDirty 标识存在于 bundle 中——FR-001 hotfix（脏值追踪）已上线"
    else
      fail "markDirty 标识不在 bundle 中——可能部署了错误版本的前端构建产物（期望 v0.5.0，请检查构建是否基于最新代码）"
    fi
  fi
fi

# =============================================================================
# 检查 5：DeviceConfig 中 system_switch (main_thermostat) is_active=False
# （证明 seed_device_config 已正确执行）
# =============================================================================
section "检查 5/5：数据库验证 system_switch is_active=False（seed 执行验证）"

if [[ ! -f "${MANAGE_PY}" ]]; then
  fail "manage.py 不存在（${MANAGE_PY}）——项目路径配置错误，请使用 --project-root 参数指定正确路径"
else
  SEED_CHECK=$(cd "$(dirname "${MANAGE_PY}")" && python manage.py shell -c "
from api.models import DeviceConfig
obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
if obj is None:
    print('NOT_FOUND')
elif obj.is_active == False:
    print('OK_IS_ACTIVE_FALSE')
else:
    print(f'WRONG_is_active={obj.is_active}')
" 2>/dev/null || echo "SHELL_ERROR")

  echo "Django shell 返回：${SEED_CHECK}"

  if [[ "${SEED_CHECK}" == "OK_IS_ACTIVE_FALSE" ]]; then
    pass "system_switch(main_thermostat) is_active=False——seed_device_config 已正确执行，主温控系统开关已软删除"
  elif [[ "${SEED_CHECK}" == "NOT_FOUND" ]]; then
    fail "system_switch(main_thermostat) 记录不存在——seed_device_config 可能未执行，请重新执行 Step 4.5"
  elif [[ "${SEED_CHECK}" == "SHELL_ERROR" ]]; then
    fail "Django shell 执行异常——检查后端环境（Python 路径、DB 连接）"
  else
    fail "system_switch is_active 值异常（${SEED_CHECK}）——期望 False，seed_device_config 可能执行了错误版本"
  fi
fi

# =============================================================================
# 汇总
# =============================================================================
section "验证汇总"

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "总检查项：${TOTAL}"
echo "通过（PASS）：${PASS_COUNT}"
echo "失败（FAIL）：${FAIL_COUNT}"
echo ""

if [[ "${FAIL_COUNT}" -eq 0 ]]; then
  echo "所有验证项通过。"
  echo "DEPLOYMENT_VERIFIED=true"
  exit 0
else
  echo "存在 ${FAIL_COUNT} 个失败项，部署验证未通过。"
  echo "请根据上述 [FAIL] 提示逐项排查，必要时执行 rollback.sh。"
  echo "DEPLOYMENT_VERIFIED=false"
  exit 1
fi
