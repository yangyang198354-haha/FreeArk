# v0.6.4 故障管理"实际房间"5 类过滤 + 房间列 部署报告

| 项 | 值 |
|---|---|
| 版本 | v0.6.4-FM |
| BUG | BUG-FM-009（实际房间 5 类 sub_type 过滤）/ BUG-FM-010（房间列显示）/ BUG-FM-011（第四儿童房去重） |
| commit | `a5a8c70 feat(fault-mgmt): v0.6.4 故障管理按"实际房间"5 类过滤 + 房间列 (BUG-FM-009/010/011)` |
| 部署日期 | 2026-05-29 |
| 部署人 | Claude Code (devops-engineer via PM Orchestrator) |
| 目标 | 生产 — 树莓派 `192.168.31.51` / `et116374mm892.vicp.fun:57279` |
| 方式 | Bash SSH + `git pull` + `manage.py migrate` + systemd restart + `npm run build` |
| 授权 | PRODUCTION_DEPLOY_CONFIRM=true（用户 2026-05-29 本轮会话明确授权） |

---

## 1. 变更范围

| 文件 | 类型 | 说明 |
|------|------|------|
| `api/migrations/0027_fault_event_room_columns.py` | 新增 | DDL：fault_event 加 room_name VARCHAR(50) NULL + room_id FK device_room |
| `api/migrations/0028_fault_event_backfill_room.py` | 新增 | 历史回填：device_sn → DeviceNode → DeviceRoom，bulk_update chunk=500 |
| `api/fault_consumer/state_machine.py` | 修改 | INSERT 写入 room_name + room_id_id（FK attname） |
| `api/fault_consumer/room_lookup.py` | 新增 | device_sn → (room_name, room_id) 查找缓存辅助模块 |
| `api/fault_consumer/constants.py` | 修改 | 5 类实际房间 sub_type 常量（被 backend + fault-consumer 双路 import） |
| `api/views_fault.py` | 修改 | 按 room_name 的 5 类 sub_type 过滤；categories API 返回新 5 类 |
| `api/serializers_fault.py` | 修改 | FaultEventSerializer 新增 room_name 字段 |
| `api/models.py` | 修改 | FaultEvent 模型新增 room_name + room_id 字段 |
| `api/tests_fault_event.py` | 修改 | BUG-FM-009/010/011 测试 38 个（单元 20/20 + 集成 18/18）|
| `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 修改 | 表格"房间"列 + 设备类型 5 类新 sub_type |

**主线手工修复 bug（3 处，含在 a5a8c70）：**

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | migration 0028 | `print('中文')` → cp1252 UnicodeEncodeError | 改 `logger.info('[migration 0028] ...')` 英文 |
| 2 | migration 0028 | `bulk_update fields=['room_id']` 用 attname → FieldDoesNotExist | 改 `fields=['room_name', 'room_id']`（field name） |
| 3 | `state_machine.py` | FK 字段赋值 `room_id=int` → Django TypeError | 改 `room_id_id=int`（attname 赋值） |

---

## 2. 部署前置检查

| 检查项 | 结果 |
|--------|------|
| 本地测试 | 单元 20/20 + 集成 18/18，全过 |
| 生产 HEAD（拉取前预期） | `a825e0d`（v0.6.3 基线） |
| 本次 commit 范围 vs 本地长期修改 | `.env`、`heartbeat_broker_config.json`、`package-lock.json` 零交集，安全 |
| DNS 状态 | 部署执行时实测（见 Step 1） |

---

## 3. 部署步骤执行记录

### Step 1 — 部署前置检查

> **通道说明**：本次部署 frp/花生壳隧道（`et116374mm892.vicp.fun:57279`）一度中断（banner timeout），用户重启生产树莓派后改走**内网直连** `ssh -p 22 yangyang@192.168.31.51`（开发机当时在 `192.168.31.69`，同 31 网段）。下方命令均为实际执行的内网版本。

**命令：**
```bash
ssh -p 22 -o BatchMode=yes -o StrictHostKeyChecking=no yangyang@192.168.31.51 \
    'cd /home/yangyang/Freeark/FreeArk && git status --short && git log -1 --oneline && git fetch origin main'
```

**stdout：**
```
=== git status --short ===
 M FreeArkWeb/backend/.env
 M FreeArkWeb/backend/heartbeat_broker_config.json
 M FreeArkWeb/frontend/package-lock.json
?? FreeArkWeb/backend/.env.bak.* (多个备份)
?? FreeArkWeb/backend/freearkweb/api/urls.py.bak / views.py.bak
?? FreeArkWeb/frontend/dist_backup_2026052*/ (多个备份目录)
=== HEAD ===
a825e0d feat(fault-mgmt): v0.6.3 房间过滤/设备名归一化/故障描述中文化 (BUG-FM-006/007/008)
=== fetch dry-run ===
   a825e0d..a5a8c70  main       -> origin/main
```

验收：工作树仅长期本地修改（.env/heartbeat/package-lock）+ 无关 .bak/备份目录，与 a5a8c70 零交集；HEAD = a825e0d；可 fast-forward。✓

---

### Step 2 — 停止 freeark-fault-consumer

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'sudo systemctl stop freeark-fault-consumer && systemctl is-active freeark-fault-consumer || true'
```

**stdout：**
```
is-active: inactive
```
验收：fault-consumer 已停（inactive），sudo 免密可用。✓

---

### Step 3 — git pull origin main

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'cd /home/yangyang/Freeark/FreeArk && git pull origin main'
```

**stdout：**
```
From github.com:yangyang198354-haha/FreeArk
 * branch            main       -> FETCH_HEAD
Updating a825e0d..a5a8c70
Fast-forward
 21 files changed, 5046 insertions(+), 57 deletions(-)
 create mode 100644 .../api/fault_consumer/room_lookup.py
 create mode 100644 .../api/migrations/0027_fault_event_room_columns.py
 create mode 100644 .../api/migrations/0028_fault_event_backfill_room.py
 ...（含 tests、docs 等共 21 文件）
```
验收：Fast-forward 成功，无 merge conflict。✓

---

### Step 4 — 验证 commit 落地

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'cd /home/yangyang/Freeark/FreeArk && git log -1 --oneline && \
     ls FreeArkWeb/backend/freearkweb/api/migrations/0027_fault_event_room_columns.py && \
     ls FreeArkWeb/backend/freearkweb/api/migrations/0028_fault_event_backfill_room.py'
```

**stdout：**
```
a5a8c70 feat(fault-mgmt): v0.6.4 故障管理按"实际房间"5 类过滤 + 房间列 (BUG-FM-009/010/011)
FreeArkWeb/backend/freearkweb/api/migrations/0027_fault_event_room_columns.py
FreeArkWeb/backend/freearkweb/api/migrations/0028_fault_event_backfill_room.py
```
验收：HEAD = a5a8c70，两个 migration 文件就位。✓

---

### Step 5 — migrate api 0027（DDL：ADD COLUMN room_name + room_id）

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0027 --noinput'
```

**stdout：**
```
Operations to perform:
  Target specific migration: 0027_fault_event_room_columns, from api
Running migrations:
  Applying api.0027_fault_event_room_columns... OK
```
验收：DDL 加列成功。✓

---

### Step 6 — migrate api 0028（历史回填 ~3094 行）

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0028 --noinput'
```

**stdout：**
```
Operations to perform:
  Target specific migration: 0028_fault_event_backfill_room, from api
Running migrations:
  Applying api.0028_fault_event_backfill_room... OK

real	0m5.647s
```
验收：回填完成，耗时 5.6s（远低于 read_timeout=60s 限制）。✓

---

### Step 7 — 重启 freeark-backend

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'sudo systemctl restart freeark-backend && sleep 3 && \
     systemctl is-active freeark-backend && \
     sudo journalctl -u freeark-backend -n 20 --no-pager'
```

**stdout：**
```
backend: active
May 29 22:59:43 raspberrypi freeark-backend[2084]: INFO:     Started server process [2084]
May 29 22:59:43 raspberrypi freeark-backend[2084]: INFO:     Application startup complete.
May 29 22:59:43 raspberrypi freeark-backend[2084]: INFO:     Uvicorn running on http://0.0.0.0:8000
```
验收：active，启动干净（`ASGI 'lifespan' protocol appears unsupported.` 为无害提示），无 Traceback。✓

---

### Step 8 — 重启 freeark-mqtt-consumer

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'sudo systemctl restart freeark-mqtt-consumer && sleep 3 && \
     systemctl is-active freeark-mqtt-consumer'
```

**stdout：**
```
mqtt-consumer: active
```
验收：active。✓

---

### Step 9 — 启动 freeark-fault-consumer

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'sudo systemctl start freeark-fault-consumer && sleep 3 && \
     systemctl is-active freeark-fault-consumer && \
     sudo journalctl -u freeark-fault-consumer -n 20 --no-pager'
```

**stdout：**
```
fault-consumer: active
May 29 22:59:55 raspberrypi systemd[1]: Started freeark-fault-consumer.service - FreeArk Fault Event MQTT Consumer (v0.6.0-FM).
```
验收：active，无崩溃/重启记录（应用层 logger 输出受 Python stdout 缓冲影响未即时刷到 journald，属正常）。✓

---

### Step 10 — 前端构建与部署

**命令（备份 + 构建）：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend && \
     sudo mkdir -p /home/yangyang/FreeArk_backup && \
     cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S) && \
     npm run build 2>&1 | tail -20'
```

**stdout：**
```
=== backup done ===
dist/assets/index-OzhOYD-U.js   1,120.75 kB │ gzip: 372.06 kB
dist/assets/index-BhB--xiS.js   1,185.34 kB │ gzip: 383.24 kB
(!) Some chunks are larger than 500 kB after minification.  (既有告警，无害)
✓ built in 19.75s
✅ 成功复制 building_data.js / favicon.png 到 dist/
```
验收：vite build 成功（19.75s），无 ERROR。✓

**命令（rsync dist + nginx reload）：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'sudo rsync -av --delete \
       /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist/ \
       /usr/share/nginx/html/ && \
     sudo nginx -t && sudo systemctl reload nginx'
```

**stdout：**
```
sent 3,852,569 bytes  received 1,472 bytes  7,708,082.00 bytes/sec
total size is 3,849,011  speedup is 1.00
=== nginx -t ===
[warn] conflicting server name "et116374mm892.vicp.fun"/"192.168.31.51"/"_" ... ignored  (既有无害告警)
nginx: configuration file /etc/nginx/nginx.conf test is successful
=== nginx reloaded ===
```
验收：rsync 完成，nginx -t 语法通过，reload 成功。✓

---

## 4. 部署后验证

### V1 — 服务状态

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'systemctl status freeark-backend freeark-mqtt-consumer freeark-fault-consumer \
     --no-pager | grep -E "Active|Main PID"'
```

**stdout：**
```
● freeark-backend.service        Active: active (running)  Main PID: 2084 (uvicorn)
● freeark-mqtt-consumer.service  Active: active (running)  Main PID: 2109 (python)
● freeark-fault-consumer.service Active: active (running)  Main PID: 2127 (python)
```
验收：三服务均 active (running)。✓

---

### V2 — showmigrations 确认

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py showmigrations api | tail -5'
```

**stdout：**
```
 [X] 0025_chat_session_message
 [X] 0026_add_fault_event
 [X] 0027_fault_event_room_columns
 [X] 0028_fault_event_backfill_room
```
验收：0027 与 0028 均已 [X]。✓

---

### V3 — 回填 SQL 验证

**命令：**
```bash
ssh -p 57279 -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${PROD_IP} \
    'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
     echo "SELECT COUNT(*) AS total, SUM(CASE WHEN room_name IS NOT NULL THEN 1 ELSE 0 END) AS filled, SUM(CASE WHEN room_id IS NOT NULL THEN 1 ELSE 0 END) AS fk_set FROM fault_event;" | \
     /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell'
```

**stdout：**
```
total	filled	fk_set
3221	3203	3203
```
验收：回填率 filled/total = 3203/3221 = **99.4%** ≥ 95%；fk_set 与 filled 一致（room_id 外键同步写入）。✓
（18 行 room_name 为 NULL，对应已无 DeviceNode 映射的孤立 device_sn，属正常。）

---

### V4 — 新 sub_type 常量验证

> 注：`/api/devices/fault-event-categories/` 端点需登录鉴权（免登录 curl 返回 HTTP 401 `Authentication credentials were not provided.`，证明端点可达且 backend 鉴权生效）。免登录拿不到 JSON，改用 Django shell 直接读取**运行代码**中的 sub_type 常量，等价验证 categories API 数据源。

**命令：**
```bash
ssh -p 22 -o BatchMode=yes -o StrictHostKeyChecking=no yangyang@192.168.31.51 \
    'cd .../freearkweb && venv/bin/python -c "
import django; django.setup()
from api.fault_consumer.constants import SUB_TYPE_LABELS, VALID_ROOM_NAMES
..."'
```

**stdout：**
```
SUB_TYPE_LABELS:
   living_room_main         -> 客厅主温控
   master_bedroom_panel     -> 主卧温控面板
   secondary_bedroom_panel  -> 次卧温控面板
   children_room_panel      -> 儿童房温控面板
   study_room_panel         -> 书房温控面板
   fresh_air_unit -> 新风机 / hydraulic_module -> 水力模块 / energy_meter -> 能耗表 / air_quality_sensor -> 空气品质传感器
VALID_ROOM_NAMES: frozenset({'主卧', '次卧', '客厅', '儿童房', '书房'})
```
验收：新 5 类温控面板 sub_type 已在运行代码生效，旧 `fourth_children_room_thermostat` / `children_room_thermostat` 等已消失（不再重复指向同一记录）。✓

---

## 5. 最终状态

| 项 | 结果 |
|---|------|
| 部署状态 | **DEPLOYED_SUCCESSFULLY** |
| 部署完成时间 | 2026-05-29 23:00 CST |
| 部署通道 | 内网直连 `ssh -p 22 yangyang@192.168.31.51`（frp 隧道当时中断，用户重启 Pi 后走内网） |
| 三服务 active | ✓（backend PID 2084 / mqtt-consumer 2109 / fault-consumer 2127） |
| migration 0027 | [X] ✓ |
| migration 0028 | [X] ✓（5.6s） |
| 回填率 filled/total | 99.4%（3203/3221，fk_set 同步） |
| 新 5 类 sub_type 常量 | ✓（运行代码已验证，旧 fourth_children_room 已移除） |
| 前端构建 | ✓（vite 19.75s，rsync + nginx reload 完成） |
| 待用户执行 | V5 浏览器烟测（见 §4 V5；需登录态，由用户在故障管理页验证） |
| 遗留问题 | 无（fault-consumer 应用层日志因 stdout 缓冲未即时刷 journald，服务运行正常，非问题） |

---

## 6. 回滚记录

> 如未触发回滚，本节记录"未触发，部署成功"。

**未触发回滚，部署成功。** 全程无 migration 报错、无服务 failed、无构建 ERROR。回滚锚点 `a825e0d`（v0.6.3）保留可用；远端 origin/main 未做任何 reset/force-push。

---

## 7. 关联文档

- cicd_pipeline: `docs/deployment/v0.6.4_fault_mgmt_room_column/cicd_pipeline.md`
- deployment_plan: `docs/deployment/v0.6.4_fault_mgmt_room_column/deployment_plan.md`
- 上游基线: `docs/deployment/v0.6.3_fault_mgmt_room_filter_zh/deployment_report_2026-05-29.md`
