<file_header>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/deployment/v0.5.0_device_settings/deployment_plan.md</file>
    <file>docs/deployment/v0.5.0_device_settings/cicd_pipeline.md</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
    <file>FreeArkWeb/frontend/nginx.conf</file>
    <file>FreeArkWeb/frontend/vite.config.js</file>
    <file>FreeArkWeb/frontend/package.json</file>
  </input_files>
  <phase>PHASE_11</phase>
  <status>DRAFT</status>
</file_header>

---

# 生产部署 Runbook

**文档编号**：RUNBOOK-PROD-v0.5.0-192.168.31.51  
**项目名称**：FreeArk 设备设置页面增量变更  
**目标版本**：v0.5.0  
**基线版本**：v0.4.7（回滚目标 commit: b714db1）  
**部署目标**：`192.168.31.51`（内网生产服务器）  
**部署日期**：2026-05-20  
**执行模式**：用户 SSH 手动逐步执行  
**状态**：DRAFT（待用户执行）

---

## 重要声明

- 本 Runbook 由 devops-engineer 生成，**devops-engineer 不执行任何远程命令**，所有命令由操作人员在目标机上手动执行。
- **密码 SSH 认证**：操作人员须自行输入登录密码，本文档中无法替代。
- **已接受风险**：
  - RISK_ACCEPTED_001：跳过 Staging 验证（用户授权，2026-05-20）。
  - RISK_ACCEPTED_002：密码 SSH 认证，runbook 手动执行模式。
- **PRODUCTION_DEPLOY_CONFIRM = true**，已由用户在本次会话中明确授权。

---

## 前置环境说明

本 Runbook 使用以下占位变量，**执行前请先导出或逐步替换**：

```bash
# 在目标机 SSH 会话中执行，或替换后粘贴
export DEPLOY_USER="root"           # 实际登录用户名，如 root / freeark / deploy
export PROJECT_ROOT="/opt/freeark"  # 项目根目录，按实际路径调整
export BACKUP_DIR="/opt/freeark/backup"
export FRONTEND_DIST="/usr/share/nginx/html"
```

> 说明：`nginx.conf` 中 `root /usr/share/nginx/html`，`FRONTEND_DIST` 默认值与此对齐。
> 若项目根目录不在 `/opt/freeark/`，请相应调整所有引用 `${PROJECT_ROOT}` 的路径。

---

## Step 0：本地前置（Windows 主机 — 执行者在 user 本机操作）

> 注意：如尚未将 v0.5.0 commits 推送到远端，请先在 user 主机上执行以下命令。
> **本 Runbook 假定 origin/main 已包含以下 3 个 v0.5.0 commit，如已 push 则跳过本步骤。**

### 0.1 确认本地 commit 状态

```powershell
# 在 Windows PowerShell 中，于项目目录执行
cd C:\Users\胖子熊\MyProject\FreeArk
git log --oneline -5
```

预期输出包含（由新到旧）：
```
34e6fce docs(deployment): v0.5.0 — CI/CD 流水线与生产部署计划
61d096c test(device-settings): v0.5.0 — 单元/集成测试套件 + FR-001 hotfix 回归
778a6fd feat(device-settings): v0.5.0 — 水利模块新增模式/离家节能字段，移除主温控冗余系统开关，前端引入脏值追踪
```

### 0.2 推送至远端（如尚未推送）

```powershell
git push origin main
```

预期输出：推送成功，包含 3 个新 commit 的提示信息。

**若推送失败**（rejected），请先执行 `git pull --rebase origin main` 解决冲突后再推送。

### 0.3 确认远端状态

```powershell
git log origin/main --oneline -3
```

预期：与本地 main 的最新 3 个 commit 一致（34e6fce、61d096c、778a6fd）。

- [ ] Step 0 完成，origin/main 已包含 3 个 v0.5.0 commit

---

## Step 1：SSH 登录目标机

```bash
ssh ${DEPLOY_USER}@192.168.31.51
# 系统提示时输入密码
```

登录成功后确认身份与主机：

```bash
whoami
hostname
uname -a
```

预期：用户名与 `${DEPLOY_USER}` 一致，主机为生产服务器。

- [ ] Step 1 完成，已成功登录 192.168.31.51

---

## Step 2：拉取代码

### 2.1 进入项目目录

```bash
# 确认项目目录正确（若路径不同请调整 PROJECT_ROOT）
cd ${PROJECT_ROOT}
ls -la
```

预期：可看到 `FreeArkWeb/` 子目录。

### 2.2 确认远端 3 个新 commit

```bash
cd ${PROJECT_ROOT}
git fetch origin
git log HEAD..origin/main --oneline
```

预期输出（3 行）：
```
34e6fce docs(deployment): v0.5.0 — CI/CD 流水线与生产部署计划
61d096c test(device-settings): v0.5.0 — 单元/集成测试套件 + FR-001 hotfix 回归
778a6fd feat(device-settings): v0.5.0 — 水利模块新增模式/离家节能字段，移除主温控冗余系统开关，前端引入脏值追踪
```

**若输出多于 3 行**：停下，确认是否有未预期的 commit，排查后再继续。
**若输出为空**：检查 origin/main 是否已包含 v0.5.0 commit（确认 Step 0 已执行）。

### 2.3 拉取代码

```bash
git pull origin main
```

预期：3 个文件变更（`views_device_settings.py`、`seed_device_config.py`、`DeviceSettingsPanelView.vue`及部署文档），无冲突。

```bash
# 确认当前 HEAD
git log --oneline -1
```

预期：`34e6fce docs(deployment): v0.5.0 — CI/CD 流水线与生产部署计划`

- [ ] Step 2 完成，代码已更新至 v0.5.0（HEAD = 34e6fce）

---

## Step 3：备份现场（CRITICAL — 回滚依赖此步骤，禁止跳过）

> 警告：此步骤是回滚的唯一依据，任何一项备份失败都应中止部署，排查原因后再继续。

```bash
# 创建备份目录（以时间戳命名，避免覆盖）
BACKUP_TS=$(date +%Y%m%d_%H%M%S)
mkdir -p ${BACKUP_DIR}/${BACKUP_TS}
echo "备份时间戳：${BACKUP_TS}"
echo "备份目录：${BACKUP_DIR}/${BACKUP_TS}"
```

### 3.1 备份数据库

```bash
# --- SQLite 环境 ---
# 确认数据库路径（按实际路径调整，通常在 freearkweb/ 目录下）
ls -la ${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb/db.sqlite3

# 备份 SQLite 文件
cp ${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb/db.sqlite3 \
   ${BACKUP_DIR}/${BACKUP_TS}/db.sqlite3.bak
echo "[备份] SQLite 数据库 → ${BACKUP_DIR}/${BACKUP_TS}/db.sqlite3.bak"

# 同时导出 device_config 表为 CSV（便于人工核查）
cd ${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb
python manage.py shell -c "
import csv, sys
from api.models import DeviceConfig
w = csv.writer(sys.stdout)
w.writerow(['id','param_name','sub_type','is_active','display_name'])
for r in DeviceConfig.objects.all().order_by('sub_type','param_name'):
    w.writerow([r.id, r.param_name, r.sub_type, r.is_active, r.display_name])
" > ${BACKUP_DIR}/${BACKUP_TS}/device_config_backup.csv
echo "[备份] device_config 表 → ${BACKUP_DIR}/${BACKUP_TS}/device_config_backup.csv"
```

### 3.2 记录 system_switch 当前状态（v0.5.0 seed 执行的关键对比基准）

```bash
cd ${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb
python manage.py shell -c "
from api.models import DeviceConfig
obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
print(f'[基准记录] system_switch(main_thermostat) is_active={obj.is_active if obj else \"NOT_FOUND\"}')
"
# 预期输出：[基准记录] system_switch(main_thermostat) is_active=True
# 若为 NOT_FOUND：该记录尚未存在，seed 后将创建并设为 False，属正常情况
```

### 3.3 备份前端 dist

```bash
# 确认当前 nginx 静态目录
ls -la ${FRONTEND_DIST}/index.html

# 整体备份（保留旧 dist 作为 v0.4.7 快照）
cp -r ${FRONTEND_DIST}/ \
      ${BACKUP_DIR}/${BACKUP_TS}/nginx_html_v0.4.7/
echo "[备份] 前端 dist → ${BACKUP_DIR}/${BACKUP_TS}/nginx_html_v0.4.7/"
```

### 3.4 记录当前服务状态

```bash
echo "=== 服务状态快照 ===" | tee ${BACKUP_DIR}/${BACKUP_TS}/service_snapshot.txt
systemctl status freeark-backend --no-pager 2>&1 | tee -a ${BACKUP_DIR}/${BACKUP_TS}/service_snapshot.txt
systemctl status nginx --no-pager 2>&1 | tee -a ${BACKUP_DIR}/${BACKUP_TS}/service_snapshot.txt
echo "[备份] 服务状态 → ${BACKUP_DIR}/${BACKUP_TS}/service_snapshot.txt"
```

### 3.5 打印备份摘要

```bash
echo "========================================"
echo "备份完成摘要"
echo "时间戳：${BACKUP_TS}"
echo "备份目录：${BACKUP_DIR}/${BACKUP_TS}/"
ls -lh ${BACKUP_DIR}/${BACKUP_TS}/
echo "========================================"
echo "请记录上述备份路径，rollback.sh 需要使用该时间戳"
```

> 重要：将 `${BACKUP_TS}` 的实际值（如 `20260520_020000`）记录下来，rollback.sh 的 `--snapshot-timestamp` 参数需要该值。

- [ ] Step 3 完成，备份时间戳已记录：`____________________`

---

## Step 4：后端依赖与迁移检查

### 4.1 激活虚拟环境（若有）

```bash
# 若项目使用 virtualenv / venv：
# source ${PROJECT_ROOT}/venv/bin/activate
# 或：
# source ${PROJECT_ROOT}/.venv/bin/activate
# 若使用系统级 Python 则跳过此命令
```

### 4.2 安装/更新 Python 依赖

```bash
cd ${PROJECT_ROOT}/FreeArkWeb/backend
echo "=== 安装 Python 依赖 ==="
pip install -r requirements.txt
echo "[完成] pip install 完成"
```

> 说明：v0.5.0 未新增 Python 依赖，若 `requirements.txt` 无变化此步骤将快速完成。

### 4.3 Django 系统检查

```bash
cd ${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb
echo "=== Django 系统检查 ==="
python manage.py check
```

预期：`System check identified no issues (0 silenced).`

若出现 CRITICAL 错误：**停止部署，记录错误信息，联系后端开发排查。**

### 4.4 Migration 检查（只检查不执行）

```bash
echo "=== Migration 检查 ==="
python manage.py migrate --check
echo "[完成] migrate --check 退出码: $?"
```

预期：退出码 0（无待执行 migration）。

> v0.5.0 无新增 migration 文件（仅 seed 数据变更），此步骤应通过。
> 若退出码非 0：**停止部署，检查是否有未预期的 migration 文件被引入。**

### 4.5 执行 seed_device_config（核心步骤）

```bash
echo "=== 执行 seed_device_config ==="
python manage.py seed_device_config
echo "[完成] seed_device_config 执行完成，退出码: $?"
```

预期输出（关键行）：
```
[deactivated(updated)] system_switch -> main_thermostat (is_active=False)
...
Done: created N, skipped M
```

**关键验证**：确认输出中包含 `system_switch -> main_thermostat (is_active=False)`。

若记录不存在（首次部署场景），输出将为 `[deactivated(created)]`，同样正确。

```bash
# 二次验证 seed 结果
python manage.py shell -c "
from api.models import DeviceConfig
obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
result = obj.is_active if obj else 'NOT_FOUND'
print(f'[验证] system_switch is_active={result}')
assert result == False, f'ABORT: system_switch is_active 应为 False，实际为 {result}'
print('[验证] PASS: system_switch 已正确设为 is_active=False')
"
```

若断言失败：**停止部署，检查 seed_device_config.py 版本是否正确（HEAD 应为 34e6fce）。**

- [ ] Step 4 完成，migrate --check 退出码 = 0，system_switch is_active=False

---

## Step 5：前端构建（远程服务器 CI 构建）

> 前提：已确认目标机有 Node.js 20+ 环境（`node -v` 应输出 `v20.x.x` 或以上）。

### 5.1 确认 Node.js 版本

```bash
echo "=== 确认 Node.js 版本 ==="
node -v
npm -v
```

预期：`node -v` >= v18.0.0（v0.5.0 使用 Vite 6，要求 Node >= 18）。

### 5.2 安装前端依赖

```bash
cd ${PROJECT_ROOT}/FreeArkWeb/frontend
echo "=== 安装前端依赖（npm ci）==="
npm ci
echo "[完成] npm ci 完成"
```

> 使用 `npm ci` 而非 `npm install`，确保依赖版本与 `package-lock.json` 锁定一致。

### 5.3 执行生产构建

```bash
echo "=== 前端生产构建（npm run build）==="
npm run build
echo "[完成] npm run build 完成，退出码: $?"
```

Vite 构建输出目录为 `dist/`（由 `vite.config.js` 的 `VITE_BUILD_DIR` 或默认值 `dist` 控制）。

### 5.4 验证构建产物

```bash
echo "=== 验证前端构建产物 ==="
ls -la ${PROJECT_ROOT}/FreeArkWeb/frontend/dist/
ls -la ${PROJECT_ROOT}/FreeArkWeb/frontend/dist/index.html
ls -la ${PROJECT_ROOT}/FreeArkWeb/frontend/dist/building_data.js
echo "[验证] dist/ 构建产物存在"
```

预期：`index.html`、`building_data.js`、`assets/` 目录均存在。

```bash
# 确认 v0.5.0 标志：markDirty 函数应已编译进 JS bundle
grep -r "markDirty" ${PROJECT_ROOT}/FreeArkWeb/frontend/dist/assets/*.js \
  && echo "[验证] PASS: markDirty 标识存在于 bundle 中（FR-001 hotfix 已编入）" \
  || echo "[警告] markDirty 未在 bundle 中找到，请确认构建使用了 v0.5.0 代码"
```

- [ ] Step 5 完成，dist/ 已构建，markDirty 标识确认存在

---

## Step 6：部署后端与前端

### 6.1 替换前端静态资源

```bash
echo "=== 替换 Nginx 前端静态目录 ==="
# 使用 rsync 替换（--delete 移除旧版 hash 文件名，避免旧资源残留）
rsync -av --delete \
  ${PROJECT_ROOT}/FreeArkWeb/frontend/dist/ \
  ${FRONTEND_DIST}/
echo "[完成] 前端 dist 已同步至 ${FRONTEND_DIST}/"
```

### 6.2 重启 Django 后端服务

```bash
echo "=== 重启 Django 后端服务 ==="
systemctl restart freeark-backend
echo "[等待] 等待服务启动（10s）..."
sleep 10
systemctl status freeark-backend --no-pager
```

预期：`Active: active (running)`。

> 此步骤必须执行的原因：`WRITABLE_SUFFIXES` 和 `WRITABLE_PARAM_NAMES` 是模块级常量，在 Django 进程启动时加载。
> 不重启则生产环境仍运行 v0.4.7 旧常量（`_mode` 未在白名单中），`operation_mode` 写入将返回 HTTP 400。

若服务启动失败：
```bash
# 查看错误日志
journalctl -u freeark-backend -n 50 --no-pager
```

### 6.3 Nginx 配置验证与重载

```bash
echo "=== Nginx 配置检查与重载 ==="
nginx -t
# 预期输出：
# nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
# nginx: configuration file /etc/nginx/nginx.conf test is successful
nginx -s reload
echo "[完成] Nginx 已重载"
```

- [ ] Step 6 完成，后端服务 active (running)，Nginx 已重载

---

## Step 7：自动化验证脚本

```bash
echo "=== 执行自动化验证脚本 ==="
cd ${PROJECT_ROOT}
bash docs/deployment/v0.5.0_device_settings/verify_deployment.sh
```

预期最后一行输出：`DEPLOYMENT_VERIFIED=true`，脚本退出码 0。

若任何验证项 FAIL：**不要继续手动验收，优先排查验证脚本输出的具体 FAIL 项**，考虑执行 rollback.sh。

- [ ] Step 7 完成，verify_deployment.sh 输出 DEPLOYMENT_VERIFIED=true

---

## Step 8：手动功能验收

**操作方式**：使用有效账号登录前端页面（`http://192.168.31.51/`），导航至设备设置页面（`/device-settings`），逐项检查以下验收项：

| 编号 | 验收项 | 预期结果 | 实际结果 | 通过？ |
|------|-------|---------|---------|-------|
| AC-01 | 主温控（Main Thermostat）分组 | **系统开关字段消失**（seed 将 is_active=False，API 过滤不下发该字段） | | |
| AC-02 | 水力模块（Hydraulic Module）分组 | 出现**工作模式**（`operation_mode`）字段，下拉可选，可编辑 | | |
| AC-03 | 水力模块（Hydraulic Module）分组 | 出现**离家节能标识**（`away_energy_saving`）字段，下拉可选，可编辑 | | |
| AC-04 | 修改任意字段值（不提交） | 提交按钮旁显示**脏值数量**（`dirtyFields` Set 追踪功能，REQ-FUNC-004） | | |
| AC-05 | 仅提交已修改字段 | 请求 payload 中**只包含已修改的参数**（未修改参数不在请求体中）；可通过浏览器 DevTools 的 Network 面板确认 | | |
| AC-06 | 对 `operation_mode` 发起写入 | 后端返回 **HTTP 202**（pending），无 HTTP 400 "不在可写白名单" | | |

**验收失败处理**：
- 若 AC-01 失败（系统开关仍显示）：Step 4.5 seed 未生效，检查 seed 输出日志，必要时重执行 Step 4.5 再重启服务。
- 若 AC-06 失败（返回 400）：Step 6.2 后端服务未重启成功，检查 `systemctl status freeark-backend`。

- [ ] Step 8 完成，所有 AC 通过

---

## Step 9：失败时回滚

**触发回滚的条件（满足任意一项即执行）**：
- verify_deployment.sh 有任何 FAIL 项
- AC-01/AC-06 验收失败且无法快速修复
- 部署后 1 小时内后端 5xx 错误率异常上升
- 数据服务（MQTT、PLC 采集）出现异常

**执行回滚**：

```bash
# 使用 Step 3 中记录的备份时间戳
bash ${PROJECT_ROOT}/docs/deployment/v0.5.0_device_settings/rollback.sh \
  --snapshot-timestamp ${BACKUP_TS}
```

其中 `${BACKUP_TS}` 替换为 Step 3.5 中记录的实际值（如 `20260520_020000`）。

回滚完成后，验证服务恢复至 v0.4.7：
```bash
cd ${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb
git log --oneline -1
# 预期：b714db1 feat(device-settings): v0.4.7 ...
```

---

## Step 10：记录部署完成信息

部署完成后（或回滚完成后），请回填 `deployment_report.md` 的留空字段：

```
实际执行开始时间：____________________
实际执行完成时间：____________________
执行人员：____________________
verify_deployment.sh 输出：[ PASS / 有 FAIL 项（注明） ]
备份产物路径：${BACKUP_DIR}/${BACKUP_TS}/
是否触发回滚：[ 是 / 否 ]
最终状态：[ DEPLOYED_SUCCESSFULLY / FAILED_ROLLED_BACK ]
```

- [ ] Step 10 完成，deployment_report.md 已回填

---

## 附录：路径快速参考

| 用途 | 路径 |
|------|------|
| 项目根目录 | `${PROJECT_ROOT}`（默认 `/opt/freeark`） |
| Django manage.py | `${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb/manage.py` |
| 后端 views | `${PROJECT_ROOT}/FreeArkWeb/backend/freearkweb/api/views_device_settings.py` |
| seed 命令 | `python manage.py seed_device_config` |
| 前端源码 | `${PROJECT_ROOT}/FreeArkWeb/frontend/` |
| 前端构建输出 | `${PROJECT_ROOT}/FreeArkWeb/frontend/dist/` |
| Nginx 静态目录 | `/usr/share/nginx/html/`（来自 `nginx.conf` `root` 配置） |
| 备份目录 | `${BACKUP_DIR}/${BACKUP_TS}/` |
| verify 脚本 | `docs/deployment/v0.5.0_device_settings/verify_deployment.sh` |
| rollback 脚本 | `docs/deployment/v0.5.0_device_settings/rollback.sh` |

---

*文档状态：DRAFT — 待用户执行并回填 deployment_report.md 后更新为 APPROVED*
