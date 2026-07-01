# 部署计划 — v0.6.4-FM 故障管理"实际房间"5 类过滤 + 房间列

```
file_header:
  document_id: DEPLOY-PLAN-v0.6.4-FM-ROOM
  title: 故障管理按实际房间 5 类过滤 + 房间列 — 生产部署计划
  author_agent: sub_agent_devops_engineer (via PM Orchestrator, PARTIAL_FLOW GROUP_E)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.4
  created_at: 2026-05-29
  status: APPROVED
  references:
    - docs/deployment/v0.6.4_fault_mgmt_room_column/cicd_pipeline.md
```

---

## 1. 部署概要

| 项 | 内容 |
|----|------|
| 部署版本 | v0.6.4-FM — 故障管理按"实际房间"5 类过滤 + 房间列 |
| BUG | BUG-FM-009 / BUG-FM-010 / BUG-FM-011 |
| 基线版本 (回滚锚点) | `a825e0d` — v0.6.3（部署前上一个稳定 commit） |
| 目标 commit | `a5a8c70 feat(fault-mgmt): v0.6.4 故障管理按"实际房间"5 类过滤 + 房间列 (BUG-FM-009/010/011)` |
| 目标环境 | 生产树莓派 Pi 5（内网 192.168.31.51，外网 et116374mm892.vicp.fun:57279） |
| 仓库路径 | `/home/yangyang/Freeark/FreeArk/` |
| venv | `/home/yangyang/Freeark/FreeArk/venv/bin/python` |
| manage.py 路径 | `/home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py` |
| 部署方式 | Bash SSH + git pull origin main（禁止 pscp 逐文件上传） |
| 数据库 migration | **有**（0027 DDL + 0028 历史回填，高风险，必须先停 fault-consumer） |
| 前端构建 | 是（npm run build，Pi 上构建，rsync 到 nginx 目录） |
| 受影响服务 | `freeark-backend` + `freeark-mqtt-consumer` + `freeark-fault-consumer`（三个都要重启） |
| 新增 systemd service | 无 |
| 新增 pip 依赖 | 无 |
| Docker | 禁用（物理机部署） |
| 生产 DB | MySQL 9.4.0 @ `192.168.31.98:3306`，库 `freeark` |
| 部署授权 | PRODUCTION_DEPLOY_CONFIRM=true（用户于 2026-05-29 本轮会话明确授权） |

---

## 2. 变更文件清单

### 2.1 后端（Python / Django）

| 文件路径（相对仓库根/FreeArkWeb/backend/freearkweb） | 变更类型 | 说明 |
|-----------------------------------------------------|---------|------|
| `api/migrations/0027_fault_event_room_columns.py` | 新增 | DDL：fault_event 表加 room_name VARCHAR(50) NULL + room_id FK device_room |
| `api/migrations/0028_fault_event_backfill_room.py` | 新增 | 历史回填：device_sn → DeviceNode → DeviceRoom，bulk_update chunk=500 |
| `api/fault_consumer/state_machine.py` | 修改 | INSERT fault_event 时写入 room_name + room_id_id（FK attname） |
| `api/fault_consumer/room_lookup.py` | 新增 | device_sn → (room_name, room_id) 的查找缓存辅助模块 |
| `api/fault_consumer/constants.py` | 修改 | 新增 5 类实际房间 sub_type 常量（被 backend + fault-consumer 双路 import） |
| `api/views_fault.py` | 修改 | 新增按 room_name 的 5 类 sub_type 过滤逻辑；fault-event-categories API 返回新 5 类 |
| `api/serializers_fault.py` | 修改 | FaultEventSerializer 新增 room_name 字段（表格"房间"列） |
| `api/models.py` | 修改 | FaultEvent 模型新增 room_name + room_id 字段 |
| `api/tests_fault_event.py` | 修改 | 新增 BUG-FM-009/010/011 测试共 20 单元 + 18 集成（主线手修 3 处后 38/38 通过） |

### 2.2 前端（Vue3 + Vite）

| 文件路径 | 变更说明 |
|---------|---------|
| `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 表格新增"房间"列；设备类型下拉新增 5 类温控面板 sub_type |

### 2.3 不变文件确认（生产本地长期修改，git pull 不触碰）

| 文件 | 说明 |
|------|------|
| `FreeArkWeb/backend/.env` | 生产 DB 凭据 / ALLOWED_HOSTS / OPENCLAW token，不入仓 |
| `FreeArkWeb/frontend/package-lock.json` | 生产 ARM 依赖树 |
| `FreeArkWeb/backend/heartbeat_broker_config.json` | 心跳 broker 配置 |

---

## 3. 启停顺序硬约束

> 顺序错会导致 migration 期间并发写入 OperationalError 或数据错乱。

**部署期严格顺序：**

1. `systemctl stop freeark-fault-consumer` — **必须先停**，才能安全执行 migration
2. `git pull origin main`
3. 验证 HEAD == `a5a8c70`
4. `manage.py migrate api 0027` — DDL（加列），秒级完成
5. `manage.py migrate api 0028` — 历史回填（~3094 行，预估 <10s）
6. `systemctl restart freeark-backend`
7. `systemctl restart freeark-mqtt-consumer`
8. `systemctl start freeark-fault-consumer` — migration 完成后才能启动
9. 前端：npm run build + rsync dist + nginx reload

---

## 4. 部署步骤（含命令）

### Step 0 — 文档产出（已完成）

- [x] `docs/deployment/v0.6.4_fault_mgmt_room_column/cicd_pipeline.md`
- [x] `docs/deployment/v0.6.4_fault_mgmt_room_column/deployment_plan.md`（本文件）

---

### Step 1 — 部署前置检查

```bash
# 1a. 解析当前生产 IP（花生壳动态 IP，每次部署前实时取）
nslookup et116374mm892.vicp.fun 8.8.8.8

# 1b. 检查生产工作树状态与当前 HEAD
ssh -p 57279 \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk && git status --short && git log -1 --oneline'
```

验收标准：
- `git status --short` 仅显示长期本地修改（M .env / M package-lock.json / M heartbeat_broker_config.json 等），无其他未提交改动
- `git log -1` 输出为 `a825e0d`（v0.6.3 基线，记录为回滚锚点）

---

### Step 2 — 停止 freeark-fault-consumer

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'sudo systemctl stop freeark-fault-consumer && systemctl is-active freeark-fault-consumer'
```

验收标准：`is-active` 返回 `inactive`（非 `active`）

---

### Step 3 — git pull

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk && git pull origin main'
```

验收标准：
- Fast-forward 成功，输出含 `Updating a825e0d..a5a8c70`
- 若出现 merge conflict → **立即停止**，不执行 stash/checkout，触发回滚流程

---

### Step 4 — 验证 commit 落地

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk && git log -1 --oneline && \
     ls FreeArkWeb/backend/freearkweb/api/migrations/0027_fault_event_room_columns.py && \
     ls FreeArkWeb/backend/freearkweb/api/migrations/0028_fault_event_backfill_room.py'
```

验收标准：
- `git log -1` 显示 `a5a8c70 feat(fault-mgmt): v0.6.4 ...`
- 两个 migration 文件存在

---

### Step 5 — 执行 migration 0027（DDL）

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0027 --noinput'
```

验收标准：
- 输出含 `Running migrations: Applying api.0027_fault_event_room_columns... OK`
- 若出现 OperationalError 或 MySQL error → **立即停止**，触发回滚

---

### Step 6 — 执行 migration 0028（历史回填）

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0028 --noinput'
```

验收标准：
- 输出含 `Applying api.0028_fault_event_backfill_room... OK`
- 命令正常退出（exit code 0）
- 预计 <10s（~3094 行 bulk_update chunk=500）

---

### Step 7 — 重启 freeark-backend

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'sudo systemctl restart freeark-backend && sleep 3 && \
     systemctl is-active freeark-backend && \
     sudo journalctl -u freeark-backend -n 20 --no-pager'
```

验收标准：
- `is-active` 返回 `active`
- journalctl 末 20 行无 Traceback / ImportError / Error

---

### Step 8 — 重启 freeark-mqtt-consumer

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'sudo systemctl restart freeark-mqtt-consumer && sleep 3 && \
     systemctl is-active freeark-mqtt-consumer'
```

验收标准：`is-active` 返回 `active`

---

### Step 9 — 启动 freeark-fault-consumer

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'sudo systemctl start freeark-fault-consumer && sleep 3 && \
     systemctl is-active freeark-fault-consumer && \
     sudo journalctl -u freeark-fault-consumer -n 20 --no-pager'
```

验收标准：
- `is-active` 返回 `active`
- journalctl 末 20 行无 Traceback / ImportError / Error

---

### Step 10 — 前端构建与部署

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend && \
     sudo mkdir -p /home/yangyang/FreeArk_backup && \
     cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S) && \
     npm run build 2>&1 | tail -30'
```

构建完成后同步 dist 到 nginx 静态目录：

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'sudo rsync -av --delete /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist/ \
     /usr/share/nginx/html/ && sudo nginx -t && sudo systemctl reload nginx'
```

验收标准：
- `npm run build` 无 ERROR 输出，`dist/` 更新时间戳最新
- `rsync` 完成，`nginx -t` 语法通过
- 若构建失败 → 保持原有 dist，触发回滚

---

## 5. 部署后验证（必须执行，每项粘贴真实输出）

### V1 — 服务状态

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'systemctl status freeark-backend freeark-mqtt-consumer freeark-fault-consumer \
     --no-pager | grep -E "Active|Main PID"'
```

预期：三个服务均 `Active: active (running)`

### V2 — Migration 确认

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py showmigrations api | tail -5'
```

预期：`[X] 0027_fault_event_room_columns` 和 `[X] 0028_fault_event_backfill_room` 均打 X

### V3 — 回填 SQL 验证

```sql
-- 在生产 dbshell 执行
SELECT COUNT(*) AS total,
       SUM(CASE WHEN room_name IS NOT NULL THEN 1 ELSE 0 END) AS filled,
       SUM(CASE WHEN room_id IS NOT NULL THEN 1 ELSE 0 END) AS fk_set
FROM fault_event;
```

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     echo "SELECT COUNT(*) AS total, SUM(CASE WHEN room_name IS NOT NULL THEN 1 ELSE 0 END) AS filled, SUM(CASE WHEN room_id IS NOT NULL THEN 1 ELSE 0 END) AS fk_set FROM fault_event;" | \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell'
```

预期：`filled / total >= 95%`（少量孤立 device_sn 可能为 NULL，属正常）

### V4 — API 烟测（新 5 类 sub_type）

```bash
ssh -p 57279 -o HostKeyAlias=et116374mm892.vicp.fun yangyang@<PROD_IP> \
    'curl -s http://127.0.0.1:8000/api/devices/fault-event-categories/ | \
     python3 -m json.tool | grep -E "study_room_panel|master_bedroom_panel|children_room|living_room|fresh_air"'
```

预期：能看到新的 5 个实际房间 sub_type，`fourth_children_room_thermostat` 已更新或消失（视实现而定）

### V5 — 用户级烟测（浏览器，部署完成后告知用户执行）

1. 故障管理页打开，确认表格有"房间"列
2. 设备类型过滤器下拉，确认 5 个温控面板 sub_type（客厅/主卧/次卧/儿童房/书房）
3. 用 `3-1-602` 房号 + 选"书房温控面板" → 应返回 1 条
4. 用 `3-1-602` 房号 + 选"儿童房温控面板" → 应返回 1 条（不再与"第四儿童房"重复）

---

## 6. 回滚方案

### 触发条件（满足任一立即执行回滚）

- 任何 `systemctl restart/start` 后服务 status = failed
- `manage.py migrate` 执行出错
- API 烟测返回 HTTP 500
- 前端构建失败（npm run build 有 ERROR）
- 前端打开报错（console 500 / 网络错误）

### 回滚步骤

```bash
# R1. 停止 fault-consumer（避免并发写入）
sudo systemctl stop freeark-fault-consumer

# R2. 代码回滚到 v0.6.3 基线（仅生产服务器，不动远端 origin）
cd /home/yangyang/Freeark/FreeArk && git reset --hard a825e0d

# R3. 逐级回滚 migration（顺序：先 0028 反向，再 0027 反向）
cd FreeArkWeb/backend/freearkweb
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0026 --noinput
# 注：migrate 0026 会自动反向执行 0028 和 0027（先 0028 reverse，再 0027 reverse）
# 0028 reverse = 清空 room_name + room_id（SET NULL）
# 0027 reverse = DROP COLUMN room_name + room_id

# R4. 重启服务
sudo systemctl restart freeark-backend
sudo systemctl restart freeark-mqtt-consumer
sudo systemctl start freeark-fault-consumer

# R5. 前端回滚（使用部署前备份）
# cp -r /home/yangyang/FreeArk_backup/dist_backup_<TIMESTAMP> \
#        /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist
# sudo rsync -av --delete \
#        /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist/ \
#        /usr/share/nginx/html/
# sudo systemctl reload nginx

# R6. 验证回滚后状态
systemctl is-active freeark-backend freeark-mqtt-consumer freeark-fault-consumer
```

> 重要：`git reset --hard` 只在生产服务器执行，**远端 origin/main 不做任何 reset / force-push**。

---

## 7. 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| migration 0027 DDL 加列时 MySQL 锁表 | 低 | fault_event ~3094 行，秒级 ALTER，停 fault-consumer 期间无并发写入 |
| migration 0028 回填超时（Django read_timeout=60s） | 低 | ~3094 行 bulk_update chunk=500，预计 <10s，远低于 60s 限制 |
| git pull 与 .env 等本地文件冲突 | 极低 | a5a8c70 未包含这些文件，fast-forward 不触碰 |
| constants.py 双路 import 漏重启某服务 | 已管控 | 部署计划明确三服务全重启（吸取 v0.6.3 BUG-FM-008 教训） |
| 前端构建失败 | 低 | 备份 dist 在先，失败不影响当前生产前端；回滚路径清晰 |

---

*本部署计划由 sub_agent_devops_engineer（via PM Orchestrator）生成，PRODUCTION_DEPLOY_CONFIRM=true，用户于 2026-05-29 本轮会话明确授权。*
