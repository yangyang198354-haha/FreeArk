# 部署计划 — v0.6.1-FM-UX 故障管理 UX 调整

```
file_header:
  document_id: DEPLOY-PLAN-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 生产部署计划
  author_agent: sub_agent_devops_engineer (via PM Orchestrator, PARTIAL_FLOW GROUP_E)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: APPROVED
  references:
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
    - docs/architecture/architecture_design_v0.6.1_fault_mgmt_ux.md
    - docs/implementation/v0.6.1_fault_mgmt_ux/implementation_plan.md
    - docs/testing/v0.6.1_fault_mgmt_ux/unit_test_report.md
    - docs/testing/v0.6.1_fault_mgmt_ux/integration_test_report.md
    - docs/deployment/v0.6.1_fault_mgmt_ux/cicd_pipeline.md
```

---

## 1. 部署概要

| 项 | 内容 |
|----|------|
| 部署版本 | v0.6.1-FM-UX — 故障管理 UX 调整 |
| 基线版本 | v0.6.0（部署前 HEAD，预期为 1554e8f 或近期 commit） |
| 目标 commit | `c7aa7fd feat(fault-mgmt): v0.6.1 UX 调整（导航/房号控件/设备名/默认筛选）` |
| 部署目标 | 生产树莓派 Pi 5（内网 192.168.31.51，外网 et116374mm892.vicp.fun:57279） |
| 项目路径 | `/home/yangyang/Freeark/FreeArk` |
| venv 路径 | `/home/yangyang/Freeark/FreeArk/venv` |
| 部署方式 | Bash SSH + git pull origin main |
| 受影响服务 | `freeark-backend.service`（Uvicorn ASGI :8000） |
| 前端构建 | 是（npm run build，输出 dist/，nginx 自动 serve） |
| 新增 systemd service | 无 |
| 新增 pip 依赖 | 无 |
| 数据库 migration | 无 |
| Docker | 禁用（物理机部署） |
| 生产 DB | MySQL 192.168.31.98:3306 |

---

## 2. 变更文件清单

### 2.1 新增文件

| 文件路径（相对于仓库根/FreeArkWeb/backend/freearkweb） | 说明 |
|------------------------------------------------------|------|
| `api/device_name_cache.py` | 设备名懒加载缓存（TTL=300s，MOD-BE-UX-01） |

### 2.2 修改文件

| 文件路径 | 变更说明 |
|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py` | 追加 `PRODUCT_CODE_LABELS` 字典（设备类型标签，MOD-BE-UX-02） |
| `FreeArkWeb/backend/freearkweb/api/serializers_fault.py` | 序列化器新增 `device_name`、`device_type_label` 字段（MOD-BE-UX-03） |
| `FreeArkWeb/frontend/src/components/Layout.vue` | 导航菜单 UX 调整（MOD-FE-UX-01） |
| `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 房号输入控件优化（MOD-FE-UX-02） |
| `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 设备名列、默认筛选"仅有故障"、视图刷新逻辑（MOD-FE-UX-03） |

### 2.3 不变文件确认

- `.env`：生产长期本地修改，git pull 不触碰（未包含在 c7aa7fd）
- `package-lock.json`：生产长期本地修改，git pull 不触碰
- `heartbeat_broker_config.json`：生产长期本地修改，git pull 不触碰
- systemd unit 文件：无变更
- nginx 配置：无变更
- DB schema：无 migration

---

## 3. 部署前检查清单

### 3.1 本地（已完成）

- [x] v0.6.1 commit `c7aa7fd` 已 push 到 GitHub origin/main
- [x] 单元测试 27/27 通过
- [x] 回归测试 112/112 通过
- [x] 用户已授权跳过本地 E2E，由生产部署后验证替代

### 3.2 生产环境前置确认（Step 1 执行）

- [ ] `git status` 仅显示 .env / package-lock.json / heartbeat_broker_config.json 三个长期本地修改
- [ ] 当前 HEAD 已记录（用于回滚）
- [ ] `freeark-backend.service` 当前 active(running)

---

## 4. 部署步骤

### Step 0 — 文档产出（已完成）

- [x] `docs/deployment/v0.6.1_fault_mgmt_ux/cicd_pipeline.md` 已生成
- [x] `docs/deployment/v0.6.1_fault_mgmt_ux/deployment_plan.md` 已生成（本文件）

---

### Step 1 — 部署前置检查

```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk && git status --short && git log -1 --oneline"
```

验收标准：
- `git status --short` 只显示 M .env、M package-lock.json、M heartbeat_broker_config.json（或其中部分）
- `git log -1` 输出为近期某个 commit hash（记录为回滚基线）

---

### Step 2 — 执行 git pull

```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk && git pull origin main"
```

验收标准：
- Fast-forward 成功，HEAD 更新至 `c7aa7fd`
- 若出现 merge conflict → 立即 abort，不执行 git stash / git checkout，上报 PM

---

### Step 3 — 验证落地

```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk && \
   git log -1 --oneline && \
   ls -la FreeArkWeb/backend/freearkweb/api/device_name_cache.py && \
   grep -c PRODUCT_CODE_LABELS FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py"
```

验收标准：
- git log 显示 `c7aa7fd feat(fault-mgmt): v0.6.1 UX 调整...`
- `device_name_cache.py` 存在
- `grep -c PRODUCT_CODE_LABELS` 输出 ≥ 1

---

### Step 4 — 前端构建

```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend && \
   cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S) && \
   npm run build" 2>&1 | tail -30
```

验收标准：
- dist 备份成功
- `npm run build` 无 ERROR 输出
- 若构建失败 → 立即 abort，保持原有 dist，上报 PM

---

### Step 5 — 重启后端

```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  "sudo systemctl restart freeark-backend && \
   sleep 3 && \
   systemctl is-active freeark-backend && \
   sudo journalctl -u freeark-backend -n 30 --no-pager"
```

验收标准：
- `is-active` 返回 `active`
- journalctl 末 30 行无 Traceback / Error

---

### Step 6 — 烟测

```bash
# 6a. 健康检查
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  "curl -sS http://127.0.0.1:8080/api/health/ -m 10"

# 6b. 序列化器字段验证（不依赖 HTTP auth）
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  "cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
   /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py shell -c \"
from api.models import FaultEvent
from api.serializers_fault import FaultEventSerializer
fe = FaultEvent.objects.first()
if fe:
    data = FaultEventSerializer(fe).data
    print('device_name:', data.get('device_name'))
    print('device_type_label:', data.get('device_type_label'))
else:
    print('No FaultEvent records found')
\""
```

验收标准：
- 健康检查返回 HTTP 200 或 JSON 含 ok/healthy
- 序列化器输出含 `device_name`（如 '新风' / '水力模块' / None）和 `device_type_label`（如 '新风机' / None）
- 若 FaultEvent 无记录 → 改用 HTTP curl 验证路由可达性（401 = 路由已注册，可接受）

---

## 5. 回滚方案

触发条件（满足任一）：
- git pull 出现 merge conflict
- npm build 失败
- freeark-backend restart 后 is-active 不为 active
- journalctl 出现 Traceback / ImportError

回滚步骤：
```bash
# 在生产服务器执行
cd /home/yangyang/Freeark/FreeArk

# 1. 查看当前 HEAD（应为 c7aa7fd）
git log --oneline -3

# 2. 创建 revert commit（保留历史）
git revert c7aa7fd --no-edit

# 3. 推送至 origin
git push origin main

# 4. 生产重新 pull（获取 revert commit）
git pull origin main

# 5. 还原前端（使用备份）
# cp -r /home/yangyang/FreeArk_backup/dist_backup_<TIMESTAMP> \
#        /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist

# 6. 重启后端
sudo systemctl restart freeark-backend
sleep 3
systemctl is-active freeark-backend
```

---

## 6. 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| git pull 与 .env 等本地文件冲突 | 低 | c7aa7fd 未包含这些文件，fast-forward 不触碰 |
| npm build 失败（Node 兼容性） | 低 | 备份 dist 在先，失败不影响当前生产前端 |
| device_name_cache DB 查询首次延迟 | 低 | TTL=300s 懒加载，首次请求单次额外查询，可接受 |
| 无 DB migration，无 systemd 变更 | — | 变更范围极小，风险极低 |

---

*本部署计划由 sub_agent_devops_engineer（via PM Orchestrator）生成，PRODUCTION_DEPLOY_CONFIRM=true，用户于 2026-05-28 本轮会话明确授权。*
