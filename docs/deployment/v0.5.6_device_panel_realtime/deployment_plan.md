# 部署计划 — v0.5.6 设备面板实时数据刷新

```
file_header:
  document_id: DEPLOY-PLAN-v0.5.6
  title: 设备面板实时数据刷新 — 生产部署计划
  author_agent: sub_agent_devops_engineer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/requirements/v0.5.6_device_panel_realtime/requirements_spec.md
    - docs/requirements/v0.5.6_device_panel_realtime/architecture_design.md
    - docs/development/v0.5.6_device_panel_realtime/implementation_plan.md
    - docs/development/v0.5.6_device_panel_realtime/code_review_report.md
    - docs/testing/v0.5.6_device_panel_realtime/integration_test_report.md
```

---

## 1. 部署概要

| 项 | 内容 |
|----|------|
| 部署版本 | v0.5.6 — 设备面板实时数据刷新 |
| 基线版本 | v0.5.5（commit: 14229b5） |
| 部署目标 | 生产树莓派 192.168.31.51（外网接入：et116374mm892.vicp.fun:57279） |
| 项目路径 | `/home/yangyang/Freeark/FreeArk` |
| 部署方式 | plink SSH + git pull（禁止 pscp 逐文件上传） |
| 受影响服务 | freeark-task-scheduler.service、freeark-mqtt-consumer.service、freeark-web.service |
| 前端构建 | 是（npm run build + 部署 dist 至 nginx static 目录） |
| 新增 systemd service | 无 |
| 新增 pip 依赖 | 无（paho-mqtt 已在生产环境安装） |
| 数据库 migration | 无（不涉及表结构变更） |
| Docker | 禁用（物理机部署） |
| 生产 DB | MySQL 192.168.31.98:3306 |
| MQTT Broker | 192.168.31.98:32788 |

---

## 2. 变更文件清单

### 2.1 新增文件

| 文件路径 | 说明 |
|---------|------|
| `datacollection/ondemand_collect_subscriber.py` | 按需采集指令订阅器（MOD-DC-01） |

### 2.2 修改文件

| 文件路径 | 变更说明 |
|---------|---------|
| `datacollection/improved_data_collection_manager.py` | start() 中启动 OndemandCollectSubscriber（MOD-DC-02） |
| `FreeArkWeb/backend/freearkweb/api/views.py` | 新增 device_ondemand_refresh 视图（MOD-BE-01） |
| `FreeArkWeb/backend/freearkweb/api/urls.py` | 追加 devices/ondemand-refresh/ 路由（MOD-BE-02） |
| `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 新增 OndemandPLCLatestDataHandler 类（MOD-BE-03） |
| `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | 新增 ondemand 队列/worker/路由/订阅（MOD-BE-04） |
| `FreeArkWeb/frontend/src/views/DeviceCardsView.vue` | 重构：按需采集、自动更新、统一时间戳（MOD-FE-01） |

### 2.3 不变文件确认

- `PLCDataHandler`、`ConnectionStatusHandler`、`PLCLatestDataHandler`（原类）：未修改
- `TaskScheduler`、`PLCWriteSubscriber`：未修改
- `energy_queue`、`general_queue`：未修改
- `device_param_history` 写入路径：未触及

---

## 3. 部署前检查清单

### 3.1 本地（Windows 主机）

- [ ] 确认 v0.5.6 所有 commits 已在本地 main 分支
  ```powershell
  cd C:\Users\yanggyan\MyProject\FreeArk
  git log --oneline -5
  ```
  预期：最新 commit 包含 v0.5.6 相关提交（feat/docs/test: v0.5.6 device panel realtime）

- [ ] 确认本地工作区无未提交变更
  ```powershell
  git status
  ```
  预期：无未提交的 .py / .vue / .js 变更（docs 文件可忽略）

- [ ] 推送至远端
  ```powershell
  git push origin main
  ```
  预期：Fast-forward 推送成功

- [ ] 确认远端已更新
  ```powershell
  git log origin/main --oneline -3
  ```

### 3.2 生产环境（192.168.31.51）前置确认

- [ ] MQTT Broker 可达
  ```bash
  nc -zv 192.168.31.98 32788
  ```
- [ ] MySQL 可达
  ```bash
  nc -zv 192.168.31.98 3306
  ```
- [ ] 三个受影响服务当前状态为 active(running)
  ```bash
  systemctl is-active freeark-task-scheduler freeark-mqtt-consumer freeark-web
  ```

---

## 4. 部署步骤（操作人员手动执行）

> **重要声明**：本计划由 devops-engineer 生成。devops-engineer 不执行任何远程命令，所有命令由操作人员在目标机手动执行。

### Step 0：本地推送（Windows PowerShell）

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk

# 确认本地状态
git log --oneline -5

# 推送到远端（如已推送则跳过）
git push origin main

# 确认推送成功
git log origin/main --oneline -3
```

- [ ] Step 0 完成，origin/main 已包含 v0.5.6 commits

---

### Step 1：SSH 登录生产服务器

```bash
# 方式 A：内网直连
ssh yangyang@192.168.31.51

# 方式 B：外网经动态域名
plink -ssh yangyang@et116374mm892.vicp.fun -P 57279
```

登录后确认：
```bash
whoami && hostname && date
```

- [ ] Step 1 完成，已登录 192.168.31.51

---

### Step 2：拉取代码

```bash
cd /home/yangyang/Freeark/FreeArk

# 查看待拉取 commits
git fetch origin
git log HEAD..origin/main --oneline
```

预期：列出 v0.5.6 新增的若干 commits（代码 + 文档 + 测试）。  
若输出为空：确认 Step 0 本地推送已完成。  
若输出包含非预期 commits：停下，排查后再继续。

```bash
# 拉取
git pull origin main
```

预期：Fast-forward，包含 `datacollection/ondemand_collect_subscriber.py` 等变更文件。

- [ ] Step 2 完成，代码已拉取至最新

---

### Step 3：前端构建与部署

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend

# 确认 Node.js 可用
node --version
npm --version

# 安装依赖（如首次或 package.json 有变更则执行；v0.5.6 无新依赖，通常可跳过）
# npm install

# 执行构建
npm run build
```

预期：构建成功，生成 `dist/` 目录，无 ERROR 输出。  
若构建失败：检查 Node 版本兼容性，查看具体错误，**不得继续后续步骤**。

```bash
# 部署构建产物至 nginx static 目录
# 注意：请根据实际 nginx 配置确认 dist 目标路径
# 常见路径：/usr/share/nginx/html 或由 nginx.conf 中的 root 指令决定

# 查看 nginx.conf 中的 root 路径
grep -r "root " /etc/nginx/sites-enabled/ 2>/dev/null || grep "root " /etc/nginx/nginx.conf

# 部署（将 dist/ 内容复制到 nginx static 目录，请替换 NGINX_STATIC 为实际路径）
NGINX_STATIC=/usr/share/nginx/html   # 请按实际 nginx.conf 调整
sudo cp -r dist/* ${NGINX_STATIC}/

# 验证静态文件已更新（检查 index.html 的修改时间）
ls -la ${NGINX_STATIC}/index.html
```

- [ ] Step 3 完成，前端 dist 已部署至 nginx 目录

---

### Step 4：重启 freeark-task-scheduler.service

> 原因：`improved_data_collection_manager.py` 修改（新增启动 OndemandCollectSubscriber），以及新增 `ondemand_collect_subscriber.py`。

```bash
sudo systemctl restart freeark-task-scheduler.service

# 等待 5 秒后检查状态
sleep 5
systemctl status freeark-task-scheduler.service --no-pager -l

# 检查日志（重点：确认 OndemandCollectSubscriber 启动日志）
sudo journalctl -u freeark-task-scheduler.service --since "1 minute ago" --no-pager | \
  grep -iE "ondemand|error|critical|exception|traceback" | tail -20
```

预期：
- `Active: active (running)`
- 日志中出现 `OndemandCollectSubscriber 已在后台线程启动`
- 日志中出现 `OndemandCollectSubscriber 已订阅 /datacollection/plc/ondemand/request/#`
- **无 error / critical / exception / traceback**

若服务未能 active：参阅 Section 7 回滚方案。

- [ ] Step 4 完成，freeark-task-scheduler 重启成功并显示 OndemandCollectSubscriber 已订阅

---

### Step 5：重启 freeark-mqtt-consumer.service

> 原因：`mqtt_handlers.py`（新增 OndemandPLCLatestDataHandler）、`mqtt_consumer.py`（新增 ondemand 队列/worker/路由/订阅）修改。

```bash
sudo systemctl restart freeark-mqtt-consumer.service

sleep 5
systemctl status freeark-mqtt-consumer.service --no-pager -l

# 检查日志（重点：ondemand worker 启动 + 订阅成功）
sudo journalctl -u freeark-mqtt-consumer.service --since "1 minute ago" --no-pager | \
  grep -iE "ondemand|worker|error|critical|exception|traceback" | tail -30
```

预期：
- `Active: active (running)`
- 日志中出现 `mqtt-ondemand-worker-0` 相关启动记录
- 日志中出现订阅 `/datacollection/plc/ondemand/result/#` 成功记录
- **无 error / critical / exception / traceback**

- [ ] Step 5 完成，freeark-mqtt-consumer 重启成功并显示 ondemand worker 启动

---

### Step 6：重启 freeark-web.service

> 原因：`views.py`（新增 device_ondemand_refresh 视图）、`urls.py`（新增路由）修改。

```bash
sudo systemctl restart freeark-web.service

sleep 5
systemctl status freeark-web.service --no-pager -l

# 检查日志
sudo journalctl -u freeark-web.service --since "1 minute ago" --no-pager | \
  grep -iE "error|critical|exception|traceback" | tail -20

# 验证新路由已注册
sudo journalctl -u freeark-web.service --since "1 minute ago" --no-pager | \
  grep -i "ondemand" | tail -10
```

预期：
- `Active: active (running)`
- 日志无 error / critical / exception / traceback

- [ ] Step 6 完成，freeark-web 重启成功

---

### Step 7：部署后快速验证

```bash
# 7.1 确认三个服务均 active
systemctl is-active freeark-task-scheduler freeark-mqtt-consumer freeark-web
# 预期：三行均输出 "active"

# 7.2 验证后端新接口可访问（在生产机本地测试）
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8000/api/devices/ondemand-refresh/ \
  -H "Content-Type: application/json" \
  -d '{"specific_part": ""}' 
# 预期：400（空 specific_part 被拦截）

# 7.3 验证日志中无崩溃
sudo journalctl -u freeark-task-scheduler -u freeark-mqtt-consumer -u freeark-web \
  --since "5 minutes ago" --no-pager | grep -iE "error|critical|traceback" | tail -20
# 预期：无输出或仅有非 v0.5.6 变更相关的已知告警
```

- [ ] Step 7 完成，三服务均 active，无崩溃日志

---

## 5. 生产集成测试清单（部署后人工执行）

部署验证后，请在生产环境人工执行以下 6 个集成测试：

| 测试 ID | 测试项 | 执行方式 | 验收标准 |
|--------|--------|---------|---------|
| IT-001 | 按需采集端到端流程（15s 内完成） | 打开设备面板，观察 Network 面板 POST 请求，计时从请求发出到前端参数更新 | P95 ≤ 15 秒；参数 `collected_at` 晚于页面打开时间 |
| IT-002 | 按需采集不写 device_param_history | 采集前记录历史表行数，触发一次按需采集，等待 done 通知，再次查询行数 | 行数不增加 |
| IT-003 | ondemand 消息进 ondemand 队列（不进 energy/general） | 触发按需采集，检查 consumer 日志 `消息入队: queue=` | 日志显示 `queue=ondemand`，不出现 `queue=energy` 或 `queue=general` |
| IT-004 | 页面打开时自动触发按需采集 | 打开设备面板，观察浏览器 Network 面板 | mounted 后立即出现 POST `/api/devices/ondemand-refresh/`；刷新按钮已消失 |
| IT-005 | 30s 定时器防重入 | 手动触发 triggerOndemandRefresh()，不等待结果，等待 30s 定时器到期 | 定时器到期后不发出新的 POST 请求（ondemandInFlight=true 时跳过） |
| IT-006 | MQTT 不可用时降级 DB 轮询 | 模拟断开 MQTT WebSocket，等待 30s 定时器 | 触发 GET /api/devices/realtime-params/，不触发 POST /api/devices/ondemand-refresh/ |

### 附加验证项

| 项目 | 检查要点 |
|------|---------|
| 统一时间戳显示 | 页面显示 `上次数据更新于：YYYY-MM-DD hh:mm:ss`（取所有参数 collected_at 最大值） |
| 各列时间移除 | 各子系统列不再显示 `HH:mm` 格式的独立时间戳 |
| 加载指示 | 按需采集进行中时，导航栏显示 Loading 图标 |
| 周期采集不受影响 | energy/general 队列正常处理消息，无积压加重 |

---

## 6. 回滚方案

### 6.1 触发条件

满足以下任一条件，立即执行回滚：

- 重启任一受影响 service 后，2 分钟内 `systemctl is-active` 不为 `active`
- `journalctl` 出现 CRITICAL 级别错误，影响周期采集链路（energy/general 队列）
- 前端页面出现白屏或设备面板完全不可访问

### 6.2 回滚步骤

**在生产服务器执行：**

```bash
cd /home/yangyang/Freeark/FreeArk

# 1. 识别 v0.5.6 最新 commit（即需要 revert 的 commit hash）
git log --oneline -5

# 2. Revert（保留历史，创建 revert commit）
#    将 <v0.5.6-latest-commit> 替换为实际 hash
git revert <v0.5.6-latest-commit> --no-edit

# 若 v0.5.6 有多个 commits，需逐一 revert（从最新到最旧）：
# git revert <commit-N> --no-edit
# git revert <commit-N-1> --no-edit
# ...

# 3. 推送 revert commits 至远端
git push origin main

# 4. 重启受影响的三个服务
sudo systemctl restart freeark-task-scheduler.service
sleep 3
sudo systemctl restart freeark-mqtt-consumer.service
sleep 3
sudo systemctl restart freeark-web.service

# 5. 验证回滚后服务状态
systemctl is-active freeark-task-scheduler freeark-mqtt-consumer freeark-web
# 预期：三行均 "active"
```

**前端回滚（如已执行 npm run build 部署）：**

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend

# git revert 已还原源码，重新构建
npm run build

NGINX_STATIC=/usr/share/nginx/html   # 按实际路径调整
sudo cp -r dist/* ${NGINX_STATIC}/
```

### 6.3 回滚后验证

```bash
# 确认三服务均 active
systemctl is-active freeark-task-scheduler freeark-mqtt-consumer freeark-web

# 确认无新的 CRITICAL 错误
sudo journalctl -u freeark-task-scheduler -u freeark-mqtt-consumer -u freeark-web \
  --since "3 minutes ago" --no-pager | grep -iE "critical|traceback" | tail -20

# 确认周期采集仍在正常运行（energy 消息仍在写入 plc_latest_data）
# 可通过 Django admin 或直接查询 MySQL 确认 plc_latest_data.collected_at 持续更新
```

### 6.4 回滚影响说明

- `plc_latest_data` 数据：回滚不影响，已写入数据保留
- `device_param_history` 数据：不受影响（v0.5.6 按需采集不写历史表）
- 周期采集链路（energy/general）：回滚后恢复 v0.5.5 行为，功能不降级
- 前端：回滚后设备面板恢复 v0.5.5 UI（有刷新按钮，30s DB 轮询），功能正常

---

## 7. 风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| OndemandCollectSubscriber 崩溃影响 TaskScheduler | 低 | 守护线程隔离，崩溃不传播到主调度循环 |
| ondemand 消息误入 energy/general 队列 | 低 | topic prefix 路由优先级最高，代码评审已确认 |
| 按需采集写入 device_param_history | 低 | OndemandPLCLatestDataHandler 覆盖 _write_history 为 no-op，代码评审已确认 |
| 前端构建失败（npm 版本问题） | 中 | 构建失败时不部署 dist，保持原有前端版本；不影响后端服务 |
| 多用户同时触发同设备按需采集 | 中 | 后端 _ondemand_inflight（TTL=25s）+ OndemandCollectSubscriber pending set（maxsize=20）双重防重入 |
| MQTT broker 不可达时 views 返回 503 | 低 | 前端降级 30s DB 轮询兜底，用户体验可接受 |

---

*本部署计划由 sub_agent_devops_engineer（via PM Orchestrator）生成，PRODUCTION_DEPLOY_CONFIRM=true，用户于 2026-05-21 本轮会话明确授权。*
