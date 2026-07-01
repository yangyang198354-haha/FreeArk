# 部署计划 — BUG-FM-003 故障类型/设备类型过滤器修复

```
file_header:
  document_id: DEPLOY-PLAN-BUG-FM-003
  title: BUG-FM-003 故障类型/设备类型过滤器无效 — 生产部署计划
  author_agent: main_agent_pm (PM Orchestrator, PARTIAL_FLOW GROUP_E)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX patch (BUG-FM-003)
  created_at: 2026-05-28
  status: APPROVED
  references:
    - docs/troubleshooting/BUG-FM-003_fault_type_device_type_filter_invalid.md
    - docs/deployment/v0.6.1_fault_mgmt_ux/deployment_report_2026-05-28.md
  production_deploy_confirm: true
  user_confirmed_at: 2026-05-28 (本轮会话明确授权"提交代码并且部署")
```

---

## 1. 部署概要

| 项 | 内容 |
|----|------|
| 部署版本 | BUG-FM-003 patch（基于 v0.6.1-FM-UX） |
| 基线版本 | v0.6.1-FM-UX（部署前 HEAD = c7aa7fd） |
| 目标 commit | `94fb3fd fix(fault-mgmt): 故障类型/设备类型过滤器无效 (BUG-FM-003)` |
| 部署目标 | 生产树莓派 Pi 5（内网 192.168.31.51，外网 et116374mm892.vicp.fun:57279） |
| 项目路径 | `/home/yangyang/Freeark/FreeArk` |
| venv 路径 | `/home/yangyang/Freeark/FreeArk/venv` |
| 部署方式 | plink + git pull origin main（密钥认证） |
| 受影响服务 | 无需重启（纯前端修复） |
| 前端构建 | 是（npm run build，仅 FaultManagementView chunk 变化） |
| 新增 systemd service | 无 |
| 新增 pip 依赖 | 无 |
| 数据库 migration | 无 |
| Docker | 禁用（物理机部署） |
| 生产 DB | MySQL 192.168.31.98:3306 |

---

## 2. 变更文件清单

### 2.1 修改文件（前端）

| 文件路径 | 变更描述 |
|---------|---------|
| `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | `fetchFaultEvents()` 改用 `URLSearchParams` 构建多值参数，修复 axios 1.x 序列化方括号问题 |

### 2.2 新增文件（后端测试）

| 文件路径 | 变更描述 |
|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/tests_fault_event.py`（新增测试类） | `TestFaultTypeFilterFrontendCompat`：11 个用例验证重复参数名格式的过滤效果 |

### 2.3 不变文件确认

- `.env`：生产长期本地修改，git pull 不触碰
- `package-lock.json`：生产长期本地修改，git pull 不触碰
- `heartbeat_broker_config.json`：生产长期本地修改，git pull 不触碰
- 后端所有业务逻辑文件：无修改（根因在前端，后端 `views_fault.py` 本身正确）
- systemd unit 文件：无变更
- nginx 配置：无变更
- DB schema：无 migration

---

## 3. 根因摘要（BUG-FM-003）

axios 1.x（项目使用 `^1.7.9`）对数组参数默认序列化为带方括号格式（`fault_type[]=comm`），而 Django 后端 `getlist('fault_type')` 仅识别无方括号的重复参数名（`fault_type=comm&fault_type=sensor`）。修复方案：改用 `URLSearchParams.append()` 逐一追加参数，绕过 axios 序列化行为。

---

## 4. 部署前检查清单

### 4.1 本地（已完成）

- [x] 修复 commit `94fb3fd` 已 push 到 GitHub origin/main
- [x] 单元测试 `TestFaultFilterParamFormatCompat` 11/11 通过
- [x] 用户已授权生产部署（本轮会话明确指令）

### 4.2 生产环境前置确认（Step 1 执行）

- [ ] git status 仅显示 .env / package-lock.json / heartbeat_broker_config.json 三个长期本地修改
- [ ] 当前 HEAD 已记录（c7aa7fd，用于回滚基线）
- [ ] freeark-backend.service 当前 active(running)

---

## 5. 部署步骤

### Step 0 — 文档产出（已完成）

- [x] `docs/deployment/v0.6.1_fault_mgmt_ux/BUG-FM-003/deployment_plan.md` 已生成（本文件）

---

### Step 1 — 部署前置检查

```bash
plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk && git status --short && git log -1 --oneline"
```

验收标准：
- `git status --short` 只显示长期本地修改文件（.env、package-lock.json、heartbeat_broker_config.json）
- `git log -1` 为 `c7aa7fd feat(fault-mgmt): v0.6.1 UX 调整...`（即上一次部署的 HEAD）

---

### Step 2 — 执行 git pull

```bash
plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk && git pull origin main"
```

验收标准：
- Fast-forward 成功，HEAD 更新至 `94fb3fd`
- 若出现 merge conflict → 立即停止，上报 PM，不执行 git stash / git checkout

---

### Step 3 — 验证落地

```bash
plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk && \
   git log -1 --oneline && \
   grep -n 'URLSearchParams' FreeArkWeb/frontend/src/views/FaultManagementView.vue | head -5"
```

验收标准：
- git log 显示 `94fb3fd fix(fault-mgmt): 故障类型/设备类型过滤器无效 (BUG-FM-003)`
- grep 找到 `URLSearchParams`（BUG-FM-003 修复标志）

---

### Step 4 — 前端构建（备份 + build）

```bash
plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend && \
   cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S) && \
   npm run build 2>&1 | tail -20"
```

验收标准：
- dist 备份成功（cp 无报错）
- `npm run build` 无 ERROR 输出，Vite 构建完成
- 若构建失败 → 立即停止，保持原有 dist（v0.6.1 版本继续服务），上报 PM

---

### Step 5 — 后端（不需重启）

本次变更为纯前端修复，后端逻辑无变更。`freeark-backend.service` **无需重启**。

验收标准：确认 freeark-backend.service 仍为 active(running) 即可。

```bash
plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
  "systemctl is-active freeark-backend"
```

---

### Step 6 — 烟测

```bash
# 6a. 健康检查
plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
  "curl -sS http://127.0.0.1:8080/api/health/ -m 10"

# 6b. 验证修复标志已编入前端 bundle
plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
  "grep -r 'URLSearchParams' /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist/assets/*.js \
   | head -3 && echo 'URLSearchParams fix confirmed in bundle'"
```

验收标准：
- 6a：返回 HTTP 200，JSON 含 `"status":"ok"`
- 6b：dist/assets/*.js 中能找到 `URLSearchParams`（证明修复代码已编入 bundle）
- 若 6b 未找到 → 构建未包含最新代码，需排查，上报 PM

---

## 6. 回滚方案

触发条件（满足任一）：
- git pull 出现 merge conflict
- npm build 失败
- 6b 烟测中 URLSearchParams 未编入 bundle
- 用户反馈过滤器行为异常加剧

回滚步骤：
```bash
# 在开发机（本地）执行 revert
cd C:\Users\yanggyan\MyProject\FreeArk
git revert 94fb3fd --no-edit
git push origin main

# 在生产服务器执行
# plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun \
#   "cd /home/yangyang/Freeark/FreeArk && git pull origin main"

# 前端回滚（如已构建新版本）：
# cp -r /home/yangyang/FreeArk_backup/dist_backup_<本次备份时间戳> \
#        /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist

# freeark-backend 本次无需重启，回滚后同样无需重启
```

---

## 7. 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| git pull 与本地文件冲突 | 极低 | 94fb3fd 未触碰 .env/package-lock.json/heartbeat_broker_config.json |
| npm build 失败 | 低 | 备份 dist 在先，失败不影响当前生产前端（v0.6.1 继续服务） |
| URLSearchParams 兼容性 | 极低 | URLSearchParams 是原生 Web API，所有现代浏览器均支持 |
| 后端影响 | 无 | 纯前端修复，后端无变更，无需重启 |

---

*本部署计划由 main_agent_pm（PM Orchestrator）生成，PRODUCTION_DEPLOY_CONFIRM=true，用户于 2026-05-28 本轮会话明确授权（"提交代码并且部署"）。*
