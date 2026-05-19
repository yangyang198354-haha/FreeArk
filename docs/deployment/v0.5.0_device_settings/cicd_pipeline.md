<file_header>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
    <file>docs/architecture/architecture_design_v0.5.0_device_settings.md</file>
    <file>docs/development/v0.5.0_device_settings/implementation_plan.md</file>
    <file>docs/testing/v0.5.0_device_settings/test_plan.md</file>
    <file>docs/testing/v0.5.0_device_settings/unit_test_report.md</file>
    <file>docs/testing/v0.5.0_device_settings/integration_test_report.md</file>
    <file>docs/testing/v0.5.0_device_settings/fr001_hotfix_test_report.md</file>
    <file>FreeArkWeb/backend/requirements.txt</file>
    <file>FreeArkWeb/frontend/package.json</file>
    <file>FreeArkWeb/frontend/vite.config.js</file>
    <file>FreeArkWeb/frontend/nginx.conf</file>
    <file>datacollection/docker-compose.yml</file>
    <file>datacollection/Dockerfile</file>
  </input_files>
  <phase>PHASE_10</phase>
  <status>DRAFT</status>
</file_header>

---

# CI/CD 流水线设计文档

**文档编号**：CICD-PIPELINE-v0.5.0-device-settings  
**项目名称**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**基线版本**：v0.4.7  
**日期**：2026-05-20  
**状态**：DRAFT  
**作者**：sub_agent_devops_engineer

---

## 1. 现有 CI 资产扫描结论

经扫描仓库根目录及各子目录，**当前项目不存在以下 CI 资产**：

| 资产类型 | 路径 | 状态 |
|---------|------|------|
| GitHub Actions 工作流 | `.github/workflows/*.yml` | 不存在 |
| GitLab CI 配置 | `.gitlab-ci.yml` | 不存在 |
| 项目级 Dockerfile | `Dockerfile` / `FreeArkWeb/*/Dockerfile` | 不存在（仅 `datacollection/Dockerfile` 存在） |
| 项目级 docker-compose | `docker-compose.yml` | 不存在（仅 `datacollection/docker-compose.yml` 存在） |

**已有 CI 相关资产（参考）**：

- `datacollection/Dockerfile`：Python 3.9-slim，用于数据采集子系统，**与本次 Web 前后端部署无关**。
- `datacollection/docker-compose.yml`：仅启动 `freeark-data-collector` 服务，**与本次 Web 前后端部署无关**。
- `FreeArkWeb/frontend/nginx.conf`：Nginx 静态文件 + API 反代配置（生产环境实际使用的配置）。
- `FreeArkWeb/backend/requirements.txt`：后端依赖清单（Django 5.2、DRF、paho-mqtt、waitress 等）。
- `FreeArkWeb/frontend/package.json`：前端依赖清单（Vue 3、Vite 6、Element Plus 等）。

**建议方案**：采用 **GitHub Actions** 构建 CI/CD 流水线（与现有 Git 仓库工具栈对齐；若后续迁移至 GitLab 可直接映射流水线阶段）。本文档同时提供 GitHub Actions YAML 示例，供手动创建 `.github/workflows/ci-cd-v0.5.0.yml` 时参考。

---

## 2. 流水线触发条件

### 2.1 触发规则

| 触发场景 | 触发条件 | 执行流水线阶段 |
|---------|---------|--------------|
| 功能开发推送 | `push` 到 `feature/*`、`fix/*`、`hotfix/*` 分支 | Build + Test（不含部署） |
| 主分支推送 | `push` 到 `main` 分支 | Build + Test + Package + Staging 部署 |
| Release 标签 | `push` 标签 `v*`（如 `v0.5.0`） | Build + Test + Package + Staging 部署 + 人工审批节点 + Production 部署 |
| PR 创建/更新 | `pull_request` 目标分支为 `main` | Build + Test（只读验证，不部署） |

### 2.2 触发条件说明

- **功能分支**：仅验证构建与测试，防止坏代码合并到 main。
- **main 分支**：合并后自动部署到 staging 环境，供功能验收。
- **版本标签**（`v0.5.0`）：唯一可触发 Production 部署的路径，且在 Staging 验证后设置人工审批节点（`PRODUCTION_DEPLOY_CONFIRM=true`）。
- **PR**：只做静态检查和测试，不触发任何部署；门控保护代码质量。

---

## 3. 流水线阶段设计

```
[触发] → [阶段1: 后端构建] → [阶段2: 前端构建] → [阶段3: 测试] → [阶段4: 制品打包]
       → [阶段5: Staging 部署] → [阶段6: Staging 验证] → [人工审批节点]
       → [阶段7: Production 部署] → [阶段8: Production 验证]
```

> 注：阶段 1-4 严格串行（后端构建完成才能进入测试）；阶段 5-8 仅在版本标签或 main 推送时执行。

---

### 3.1 阶段 1：后端构建（Backend Build）

**运行环境**：Ubuntu 22.04，Python 3.11（与 Django 5.2 官方支持版本对齐）

**执行步骤**：

```yaml
# 参考步骤（GitHub Actions 格式）
- name: 安装 Python 依赖
  run: |
    cd FreeArkWeb/backend
    python -m pip install --upgrade pip
    pip install -r requirements.txt

- name: Django 系统检查
  run: |
    cd FreeArkWeb/backend/freearkweb
    python manage.py check --deploy 2>&1 | tee django_check.log
    # 允许 HSTS/HTTPS 相关警告（内网部署无 HTTPS），但不允许 CRITICAL 错误
    if grep -i "CRITICAL\|SystemCheckError" django_check.log; then
      echo "Django check 发现 CRITICAL 错误，构建失败"
      exit 1
    fi

- name: Migration 一致性检查（只检查不执行）
  run: |
    cd FreeArkWeb/backend/freearkweb
    python manage.py migrate --check
    # 若有未应用的 migration，此命令退出码非0，流水线失败
    # v0.5.0 注意：本次无新增 migration 文件，此步骤应通过
```

**通过标准**：
- `pip install` 无依赖冲突
- `manage.py check` 无 CRITICAL 级别错误
- `manage.py migrate --check` 退出码为 0（无待执行 migration）

**关键说明**：v0.5.0 的 `seed_device_config.py` 变更属于**数据层 seed 操作**，不涉及数据库 schema 变更，因此**无需新增 migration 文件**，`migrate --check` 步骤可正常通过。

---

### 3.2 阶段 2：前端构建（Frontend Build）

**运行环境**：Ubuntu 22.04，Node.js 20 LTS

**执行步骤**：

```yaml
- name: 安装前端依赖
  run: |
    cd FreeArkWeb/frontend
    npm ci
    # 使用 npm ci 而非 npm install，确保依赖版本与 package-lock.json 锁定一致

- name: 前端 Lint 检查
  run: |
    cd FreeArkWeb/frontend
    # 项目当前使用 Vite 6 + Vue 3，无独立 ESLint 配置
    # 若后续引入 eslint，在此添加：npm run lint
    # 当前阶段：vite build 本身包含基础语法检查
    echo "Lint 阶段：当前项目未独立配置 ESLint，由 vite build 做基础检查"

- name: 前端生产构建
  run: |
    cd FreeArkWeb/frontend
    npm run build
    # 输出目录：FreeArkWeb/frontend/dist/（由 vite.config.js VITE_BUILD_DIR 控制）
    # 构建完成后 dist/ 包含：index.html、assets/、building_data.js、favicon.png

- name: 验证构建产物完整性
  run: |
    cd FreeArkWeb/frontend
    ls dist/index.html dist/building_data.js
    echo "前端构建产物验证通过"
```

**通过标准**：
- `npm ci` 无安装错误
- `npm run build`（即 `vite build`）退出码为 0
- `dist/index.html` 和 `dist/building_data.js` 存在（后者由 `vite.config.js` 的 `copyStaticFilesPlugin` 复制）

---

### 3.3 阶段 3：测试（Test）

**运行环境**：Ubuntu 22.04，Python 3.11，SQLite（测试数据库，与后端 `.env` 中 `DB_ENGINE=sqlite3` 对齐）

**测试对象**：`FreeArkWeb/backend/freearkweb/api/tests/test_device_settings_v050.py`

**执行步骤**：

```yaml
- name: 执行 v0.5.0 设备设置测试套件
  env:
    SECRET_KEY: "ci-test-secret-key-not-for-production"
    DB_ENGINE: django.db.backends.sqlite3
    DB_NAME: ":memory:"
    DJANGO_SETTINGS_MODULE: freearkweb.settings
  run: |
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_device_settings_v050 \
      --verbosity=2 \
      --keepdb \
      2>&1 | tee test_output.log
    
    # 解析测试结果
    TOTAL=$(grep -oP "Ran \K[0-9]+" test_output.log | tail -1)
    FAILURES=$(grep -oP "[0-9]+ failure" test_output.log | grep -oP "[0-9]+" || echo "0")
    ERRORS=$(grep -oP "[0-9]+ error" test_output.log | grep -oP "[0-9]+" || echo "0")
    
    echo "测试总数: $TOTAL | 失败: $FAILURES | 错误: $ERRORS"
    
    # 门控：通过率必须 = 100%（GROUP_D 基线：79/79，100% 通过）
    if [ "$FAILURES" -gt "0" ] || [ "$ERRORS" -gt "0" ]; then
      echo "测试门控未通过：存在失败或错误，禁止继续部署"
      exit 1
    fi
    echo "测试门控通过：$TOTAL 条用例全部通过"
```

**测试套件覆盖范围**（依据 GROUP_D 测试报告基线）：

| 测试类别 | 用例数 | 关联需求 |
|---------|-------|---------|
| 单元测试（`_is_writable` 逻辑） | 35 | REQ-FUNC-002、REQ-FUNC-003、REQ-NFUNC-001 |
| 集成测试（API 端到端） | 37 | REQ-FUNC-001~004、US-001~005 |
| HOTFIX 回归测试（FR-001） | 7 | FR-001（plc_latest_data 写后同步） |
| **合计** | **79** | **全量覆盖** |

**通过率门控标准**（对齐 GROUP_D APPROVED 基线）：

| 指标 | 门控阈值 | GROUP_D 基线值 | 判定 |
|-----|---------|--------------|------|
| 单元测试通过率 | ≥ 80% | 100%（35/35） | 必须 ≥ 80% |
| 集成测试通过率 | ≥ 90% | 100%（37/37） | 必须 ≥ 90% |
| HOTFIX 回归通过率 | 100% | 100%（7/7） | 必须 100%（回归不允许任何退化） |
| **总体通过率** | **100%** | **100%（79/79）** | **CI 门控：0 失败 0 错误** |

> 说明：CI 门控要求总体通过率 = 100%（即 GROUP_D 基线的保持，任何退化均阻断部署）。

---

### 3.4 阶段 4：制品打包（Package）

**触发条件**：仅在 `main` 分支推送或版本标签时执行。

**后端制品**：

```yaml
- name: 打包后端源码制品
  run: |
    # 采用源码包方式（与现有 waitress 部署模式对齐，无 wheel 构建需求）
    VERSION=$(git describe --tags --abbrev=0 || echo "v0.5.0-dev")
    tar -czf backend-${VERSION}.tar.gz \
      FreeArkWeb/backend/ \
      --exclude='FreeArkWeb/backend/**/__pycache__' \
      --exclude='FreeArkWeb/backend/**/*.pyc' \
      --exclude='FreeArkWeb/backend/db.sqlite3'
    echo "后端制品：backend-${VERSION}.tar.gz"

- name: 上传后端制品（GitHub Actions Artifact）
  uses: actions/upload-artifact@v4
  with:
    name: backend-${{ github.ref_name }}
    path: backend-*.tar.gz
    retention-days: 30
```

**前端制品**：

```yaml
- name: 打包前端构建产物
  run: |
    VERSION=$(git describe --tags --abbrev=0 || echo "v0.5.0-dev")
    tar -czf frontend-dist-${VERSION}.tar.gz \
      -C FreeArkWeb/frontend dist/
    echo "前端制品：frontend-dist-${VERSION}.tar.gz"

- name: 上传前端制品
  uses: actions/upload-artifact@v4
  with:
    name: frontend-dist-${{ github.ref_name }}
    path: frontend-dist-*.tar.gz
    retention-days: 30
```

**制品清单**：

| 制品名称 | 内容 | 用途 |
|---------|------|------|
| `backend-v0.5.0.tar.gz` | `FreeArkWeb/backend/` 源码（不含 `.pyc`、`db.sqlite3`） | 部署到应用服务器 |
| `frontend-dist-v0.5.0.tar.gz` | `FreeArkWeb/frontend/dist/` 构建产物 | 部署到 Nginx 静态目录 |

---

### 3.5 阶段 5：Staging 部署（Staging Deploy）

**触发条件**：仅在测试通过且制品打包成功后执行；`main` 分支推送自动触发，版本标签亦触发。

**Staging 环境规格**（建议，与生产环境隔离）：

- 服务器：独立测试机或与生产机同网段的备机（内网 IP 区别于 `192.168.31.51`）
- 数据库：独立 SQLite 文件（或 MySQL 测试实例）
- MQTT Broker：与生产共享（订阅独立 topic 前缀 `staging/`）或独立 broker

**执行方式**（SSH 远程执行，需在 CI 中配置 `STAGING_SSH_KEY` 密钥）：

```yaml
- name: 部署到 Staging 环境
  env:
    STAGING_HOST: ${{ secrets.STAGING_HOST }}
    STAGING_USER: ${{ secrets.STAGING_USER }}
    STAGING_SSH_KEY: ${{ secrets.STAGING_SSH_KEY }}
  run: |
    # 传输制品
    scp -i "$STAGING_SSH_KEY" backend-*.tar.gz \
      ${STAGING_USER}@${STAGING_HOST}:/opt/freeark/deploy/
    scp -i "$STAGING_SSH_KEY" frontend-dist-*.tar.gz \
      ${STAGING_USER}@${STAGING_HOST}:/opt/freeark/deploy/

    # 远程执行部署脚本
    ssh -i "$STAGING_SSH_KEY" ${STAGING_USER}@${STAGING_HOST} \
      "bash /opt/freeark/scripts/deploy_staging.sh v0.5.0"
```

---

### 3.6 阶段 6：Staging 验证（Staging Smoke Test）

**执行步骤**（自动化冒烟测试）：

```yaml
- name: Staging 冒烟测试
  run: |
    STAGING_URL="http://${{ secrets.STAGING_HOST }}"
    
    # 等待服务启动（最多 60s）
    for i in $(seq 1 12); do
      if curl -sf "${STAGING_URL}/api/health/" > /dev/null 2>&1; then
        echo "Staging 服务已就绪"
        break
      fi
      echo "等待服务启动... ($i/12)"
      sleep 5
    done
    
    # 验证点 1：API 健康检查
    curl -sf "${STAGING_URL}/api/health/" || (echo "健康检查失败" && exit 1)
    
    # 验证点 2：设备设置参数接口可访问（需认证，此处验证 HTTP 401 而非 200）
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
      "${STAGING_URL}/api/device-settings/params/test_part/")
    if [ "$HTTP_CODE" != "401" ] && [ "$HTTP_CODE" != "200" ]; then
      echo "设备设置接口异常（HTTP ${HTTP_CODE}）"
      exit 1
    fi
    echo "Staging 冒烟测试通过"
```

---

### 3.7 人工审批节点（Manual Approval Gate）

**触发条件**：仅在版本标签（`v*`）触发时，Staging 验证通过后进入此节点。

**GitHub Actions 实现**：

```yaml
- name: 等待生产部署授权
  uses: trstringer/manual-approval@v1
  with:
    secret: ${{ github.TOKEN }}
    approvers: <项目负责人 GitHub 用户名>
    minimum-approvals: 1
    issue-title: "请求授权：FreeArk v0.5.0 生产部署"
    issue-body: |
      Staging 验证已通过，请确认以下内容后批准生产部署：
      
      - [ ] 已阅读 deployment_plan.md 并确认变更范围
      - [ ] 已确认停机窗口与设备终端用户沟通
      - [ ] 已完成 device_config 数据表备份
      - [ ] 已完成前端 dist/ 备份
      
      **批准方式**：在本 Issue 下回复 `approved` 以授权部署。
      
      本授权仅对本次 CI 运行有效（run-id: ${{ github.run_id }}）。
```

> 安全说明：此节点对应 PM 编排协议中的 `PRODUCTION_DEPLOY_CONFIRM=true` 信号机制。只有项目负责人在 GitHub Issue 中明确回复 `approved` 后，流水线才会继续执行 Production 部署阶段。信号不可跨 CI 运行复用。

---

### 3.8 阶段 7：Production 部署（Production Deploy）

**执行步骤**（参见 `deployment_plan.md` 第 4 节详细步骤，此处为流水线自动化映射）：

```yaml
- name: 生产部署
  env:
    PROD_HOST: ${{ secrets.PROD_HOST }}          # 生产服务器 IP，如 192.168.31.51
    PROD_USER: ${{ secrets.PROD_USER }}
    PROD_SSH_KEY: ${{ secrets.PROD_SSH_KEY }}
  run: |
    # 传输制品到生产服务器
    scp -i "$PROD_SSH_KEY" backend-*.tar.gz \
      ${PROD_USER}@${PROD_HOST}:/opt/freeark/deploy/
    scp -i "$PROD_SSH_KEY" frontend-dist-*.tar.gz \
      ${PROD_USER}@${PROD_HOST}:/opt/freeark/deploy/

    # 远程执行生产部署脚本（与 deployment_plan.md 步骤一一对应）
    ssh -i "$PROD_SSH_KEY" ${PROD_USER}@${PROD_HOST} \
      "bash /opt/freeark/scripts/deploy_production.sh v0.5.0"
```

**生产部署脚本（`deploy_production.sh`）内容概要**（对应 `deployment_plan.md` 步骤 3-9）：

```bash
#!/bin/bash
set -e
VERSION=$1
DEPLOY_DIR="/opt/freeark/deploy"
BACKEND_DIR="/opt/freeark/backend"
FRONTEND_DIST="/usr/share/nginx/html"
MANAGE_PY="${BACKEND_DIR}/freearkweb/manage.py"

# 步骤 3: 解压后端制品
tar -xzf ${DEPLOY_DIR}/backend-${VERSION}.tar.gz -C ${DEPLOY_DIR}/extracted/

# 步骤 4: 更新后端代码
rsync -av --delete ${DEPLOY_DIR}/extracted/FreeArkWeb/backend/ ${BACKEND_DIR}/

# 步骤 5: 执行 seed_device_config（update_or_create 幂等，REQ-NFUNC-004）
cd ${BACKEND_DIR}/freearkweb
python ${MANAGE_PY} seed_device_config
echo "seed_device_config 执行完成"

# 步骤 6: 重启 Django 服务（waitress 进程重载 WRITABLE_SUFFIXES）
systemctl restart freeark-backend
echo "后端服务已重启"

# 步骤 7: 部署前端静态文件
tar -xzf ${DEPLOY_DIR}/frontend-dist-${VERSION}.tar.gz -C /tmp/frontend_new/
rsync -av --delete /tmp/frontend_new/dist/ ${FRONTEND_DIST}/
nginx -t && systemctl reload nginx
echo "前端部署完成，Nginx 已重载"
```

---

### 3.9 阶段 8：Production 验证（Post-Deploy Verification）

```yaml
- name: 生产验证
  run: |
    PROD_URL="http://${{ secrets.PROD_HOST }}"
    
    # 验证点 1：API 健康检查
    curl -sf "${PROD_URL}/api/health/" || (echo "生产 API 健康检查失败" && exit 1)
    
    # 验证点 2：登录设备设置页面 — 验证接口可访问（HTTP 401 = 正常未认证）
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
      "${PROD_URL}/api/device-settings/params/test_part/")
    if [ "$HTTP_CODE" = "404" ] || [ "$HTTP_CODE" = "500" ]; then
      echo "设备设置接口异常（HTTP ${HTTP_CODE}），部署可能失败"
      exit 1
    fi
    
    echo "生产验证通过（HTTP ${HTTP_CODE}）"
    echo "请操作人员手动确认：登录设备设置页面，检查主温控系统开关已消失、水力模块出现工作模式/离家节能字段"
```

---

## 4. 失败回滚策略

### 4.1 各阶段失败处理

| 失败阶段 | 回滚动作 | 自动/手动 |
|---------|---------|---------|
| 阶段 1（后端构建失败） | 无需回滚；修复代码重新推送 | 自动中止 |
| 阶段 2（前端构建失败） | 无需回滚；修复代码重新推送 | 自动中止 |
| 阶段 3（测试门控未通过） | 无需回滚；分析失败用例，修复后重新触发 | 自动中止 |
| 阶段 4（制品打包失败） | 无需回滚；检查磁盘空间和权限 | 自动中止 |
| 阶段 5（Staging 部署失败） | 恢复 Staging 环境到 v0.4.7 制品 | 手动执行 |
| 阶段 6（Staging 验证失败） | 阻断进入生产；分析 Staging 日志；修复后重新部署 | 自动阻断 |
| 阶段 7（Production 部署失败） | 立即执行完整回滚方案（见 `deployment_plan.md` 第 6 节） | 手动执行 |
| 阶段 8（Production 验证失败） | 立即执行完整回滚方案 | 手动执行 |

### 4.2 自动回滚触发条件

以下条件触发自动告警（流水线失败 + 发送通知），**但不执行自动回滚**（生产环境回滚必须人工确认）：

- 阶段 7 SSH 命令退出码非 0
- 阶段 8 生产验证 HTTP 500 / 404
- 后端服务重启后 30s 内健康检查连续失败 3 次

### 4.3 手动回滚脚本（`rollback_production.sh`）

```bash
#!/bin/bash
set -e
# 回滚到 v0.4.7
ROLLBACK_VERSION="v0.4.7"
DEPLOY_DIR="/opt/freeark/deploy"
BACKEND_DIR="/opt/freeark/backend"
FRONTEND_DIST="/usr/share/nginx/html"

echo "开始回滚到 ${ROLLBACK_VERSION}..."

# 1. 恢复后端（从备份或 v0.4.7 制品）
tar -xzf ${DEPLOY_DIR}/backend-${ROLLBACK_VERSION}.tar.gz -C ${DEPLOY_DIR}/rollback/
rsync -av --delete ${DEPLOY_DIR}/rollback/FreeArkWeb/backend/ ${BACKEND_DIR}/

# 2. 重跑 v0.4.7 版本 seed_device_config（恢复 system_switch is_active=True）
cd ${BACKEND_DIR}/freearkweb
python manage.py seed_device_config --reset
echo "数据库 seed 已回滚"

# 3. 重启后端服务
systemctl restart freeark-backend

# 4. 恢复前端（从备份的 dist/ 快照）
rsync -av --delete ${DEPLOY_DIR}/backup/dist/ ${FRONTEND_DIST}/
nginx -t && systemctl reload nginx

echo "回滚完成，当前版本：${ROLLBACK_VERSION}"
```

> 注意：`dirtyFields` 是纯前端内存状态，无持久化数据，回滚时无需特殊处理。

---

## 5. 完整流水线 YAML 示例

以下为完整的 GitHub Actions 工作流文件，供创建 `.github/workflows/ci-cd-v050.yml` 时参考：

```yaml
name: FreeArk CI/CD — v0.5.0 Device Settings

on:
  push:
    branches: [main, 'feature/*', 'fix/*', 'hotfix/*']
    tags: ['v*']
  pull_request:
    branches: [main]

jobs:
  backend-build:
    name: 后端构建与检查
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: 安装依赖
        run: |
          cd FreeArkWeb/backend
          pip install -r requirements.txt
      - name: Django 系统检查
        run: |
          cd FreeArkWeb/backend/freearkweb
          SECRET_KEY=ci-dummy DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
            python manage.py check 2>&1 | tee django_check.log
          grep -i "CRITICAL\|SystemCheckError" django_check.log && exit 1 || true
      - name: Migration 一致性检查
        run: |
          cd FreeArkWeb/backend/freearkweb
          SECRET_KEY=ci-dummy DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
            python manage.py migrate --check

  frontend-build:
    name: 前端构建
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: 安装依赖
        run: |
          cd FreeArkWeb/frontend
          npm ci
      - name: 生产构建
        run: |
          cd FreeArkWeb/frontend
          npm run build
      - name: 验证构建产物
        run: |
          ls FreeArkWeb/frontend/dist/index.html
          ls FreeArkWeb/frontend/dist/building_data.js
      - name: 上传前端制品
        if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')
        uses: actions/upload-artifact@v4
        with:
          name: frontend-dist-${{ github.ref_name }}
          path: FreeArkWeb/frontend/dist/

  test:
    name: 测试门控
    needs: [backend-build, frontend-build]
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: 安装依赖
        run: |
          cd FreeArkWeb/backend
          pip install -r requirements.txt
      - name: 执行测试套件
        env:
          SECRET_KEY: ci-test-secret-not-for-production
          DB_ENGINE: django.db.backends.sqlite3
          DB_NAME: ":memory:"
        run: |
          cd FreeArkWeb/backend/freearkweb
          python manage.py test api.tests.test_device_settings_v050 --verbosity=2
          # 零失败才通过，任何失败阻断部署

  deploy-staging:
    name: Staging 部署
    needs: [test]
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-22.04
    steps:
      - name: 部署到 Staging
        run: echo "Staging 部署步骤（配置 SSH 密钥后激活）"

  approve-production:
    name: 生产部署人工审批
    needs: [deploy-staging]
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-22.04
    steps:
      - name: 请求人工审批
        uses: trstringer/manual-approval@v1
        with:
          secret: ${{ github.TOKEN }}
          approvers: <项目负责人>
          minimum-approvals: 1
          issue-title: "授权请求：生产部署 ${{ github.ref_name }}"

  deploy-production:
    name: Production 部署
    needs: [approve-production]
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-22.04
    steps:
      - name: 生产部署
        run: echo "生产部署步骤（配置 PROD_SSH_KEY 后激活）"
```

---

## 6. CI 配置所需 Secrets 清单

| Secret 名称 | 说明 | 首次配置时机 |
|------------|------|------------|
| `STAGING_HOST` | Staging 服务器 IP/域名 | Staging 环境就绪后 |
| `STAGING_USER` | Staging SSH 用户名 | Staging 环境就绪后 |
| `STAGING_SSH_KEY` | Staging SSH 私钥 | Staging 环境就绪后 |
| `PROD_HOST` | 生产服务器 IP（`192.168.31.51`） | 生产部署前 |
| `PROD_USER` | 生产 SSH 用户名 | 生产部署前 |
| `PROD_SSH_KEY` | 生产 SSH 私钥（与 `STAGING_SSH_KEY` 严格隔离） | 生产部署前 |

> 安全提示：所有 SSH 私钥以 GitHub Actions Secrets 方式存储，不得明文写入代码库或日志。密钥轮换周期建议 90 天。

---

## 7. 与项目现有工具栈的对齐说明

| 技术组件 | 现有状态 | CI 对齐方式 |
|---------|---------|-----------|
| Python / Django | `requirements.txt` 已存在，Django 5.2 + waitress | CI 直接 `pip install -r requirements.txt` |
| Node.js / Vite | `package.json` 已存在，Vite 6 + Vue 3 | CI `npm ci` + `npm run build` |
| Nginx | `nginx.conf` 已存在（含 MQTT-WS 反代） | CI 部署 `dist/` 至 `/usr/share/nginx/html`，Nginx reload |
| Docker | 仅 `datacollection/` 有 Dockerfile，**Web 部分无** | 本次不引入 Web 部分 Docker 化（保持现状，可在 v0.6.0+ 评估） |
| 数据采集服务 | `datacollection/docker-compose.yml` 独立运行 | 与 Web 部署完全解耦，本次 CI 不涉及 |
| MQTT Broker | 外部服务（`192.168.31.98:32788`） | CI 测试阶段 mock MQTT，不连接真实 broker |

---

*文档状态：DRAFT — 待 PHASE_10 门控评审通过后更新为 APPROVED*
