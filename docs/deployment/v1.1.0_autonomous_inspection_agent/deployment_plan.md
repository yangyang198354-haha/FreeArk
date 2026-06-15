# 自治巡检 Agent（方案 B）— 部署计划（GROUP_E）

```
document_id : DEPLOY-v1.1.0-AIA
title       : freeark-inspection-agent 生产部署计划
project     : FreeArk v1.1.0
created_at  : 2026-06-16
status      : 待执行（须用户明确 CONFIRM 后方可在生产执行）
target      : 树莓派 192.168.31.51（内网）/ et116374mm892.vicp.fun:57279（外网）
references  :
  - docs/requirements/v1.1.0_autonomous_inspection_agent/architecture_design.md §12
  - docs/requirements/v1.1.0_autonomous_inspection_agent/test_plan.md §6（Pi 权威回归）
  - skill: freeark-prod-deploy
```

> 🚦 **部署门控**：本计划**不自动执行**。生产任何一步（git pull / migrate / 起服务）均须用户
> 明确 CONFIRM 后才操作。部署一律 **plink/ssh + git pull**，**禁止 pscp 逐文件上传**；**禁止 Docker**。
> SSH 用密钥认证；`.env` / `package-lock.json` / `heartbeat_broker_config.json` 是生产本地文件，
> `git pull` 前确认分支不触碰它们。

---

## 1. 变更摘要

| 类别 | 内容 | 破坏性 |
|------|------|--------|
| DB migration | `0033_add_inspection_status_and_workorder`：两张事件表各加 2 字段 + 新建 `inspection_work_order` 表 + 条件唯一约束/索引 | 非破坏（纯 AddField/CreateModel，现有代码不读新字段） |
| 新代码 | `inspection_agent/` 包 + `run_inspection_agent` 命令 | 新增，不改 `api/langgraph_chat/` 与 `agents/`（OOS-01） |
| 新服务 | systemd `freeark-inspection-agent`（独立进程，串行单核友好） | 新增常驻服务 |
| `.env` | 追加 4 个键（§3.2，不入 git） | 仅本机 |
| 现有服务 | `freeark-backend` / `freeark-fault-consumer` / `freeark-condensation-consumer` 等 | **不改、不重启**（方案 B 仅消费其写入 DB 的记录） |

---

## 2. 部署前置检查（Pre-flight，全部满足才进入 §3）

- [ ] **测试门控**：test_plan.md §6 的 Pi 权威回归已执行且通过（迁移一致性 + 增量/回归套件 + 方案 A 无回归）。
- [ ] **分支就绪**：`feat/aia-b-increment1` 已合并到 `main`（或确认按该分支部署），且 PR 已评审。
- [ ] **langgraph 依赖**：Pi 的 venv 已装 langgraph/langchain（方案 A 已上线即满足）。巡检 Agent **直接构造 `Orchestrator()`**，与 `CHAT_BACKEND` 取值无关——无需把 chat 切到 langgraph。
- [ ] **凭证**：`.env` 内 `DEEPSEEK_API_KEY` 有效（Agent 走真 DeepSeek 决策；缺失会导致决策失败→全部兜底建单）。
- [ ] **提示词目录**：`agents/inspection-expert/SYSTEM_PROMPT.langgraph.md` 在仓内（prompts.py 按 `__file__` 上溯自动定位 `agents/`；如有定制路径可设 `LANGGRAPH_AGENTS_DIR`）。
- [ ] **磁盘/连接**：生产 DB（192.168.31.98:3306）可达；Pi 出网正常（注意 wlan0 power_save 与 vicp.fun DNS 既有风险，见 §7）。

---

## 3. 部署步骤（生产 Pi，逐步 CONFIRM）

> SSH 登录见 skill `freeark-prod-deploy`（本文件不含密码）。以下命令在 Pi 上执行。

### 3.1 拉取代码
```bash
cd /home/yangyang/Freeark/FreeArk
git status            # 确认 .env / package-lock.json / heartbeat_broker_config.json 无冲突
git pull             # 或 git fetch && git checkout <目标分支/commit>
```

### 3.2 追加 .env 配置（不入 git）
向 `FreeArkWeb/backend/freearkweb/.env` 追加：
```bash
AUTO_WRITE_POLICY=B            # 本期拍板：零自动写、全部转工单
INSPECTION_POLL_INTERVAL=30    # 轮询间隔秒
INSPECTION_BATCH_SIZE=5        # 每轮最多处理事件数（单核防爆发）
INSPECTION_WRITE_WHITELIST={}  # 策略 B 留空；升级策略 A 时再填 JSON
```
（可选）`INSPECTION_DECISION_TIMEOUT=300` 单事件决策总超时秒，默认 300。

### 3.3 执行 migration
```bash
cd FreeArkWeb/backend/freearkweb
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0033_add_inspection_status_and_workorder
# 验证：
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py showmigrations api | grep 0033
```

### 3.4 安装并启动 systemd 服务
```bash
sudo cp deployment/systemd/freeark-inspection-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now freeark-inspection-agent
```

### 3.5 验证
```bash
systemctl status freeark-inspection-agent --no-pager
journalctl -u freeark-inspection-agent -n 80 --no-pager
# 期望日志：
#   freeark-inspection-agent 启动
#   启动重建完成：重置 N 条 IN_PROGRESS → PENDING
#   InspectionAgent 启动：poll_interval=30s decision_timeout=300s policy=B
# 若当前有活跃 PENDING 故障/结露事件，应观察到：
#   DELEGATION_CALLED → WRITE_BLOCKED_POLICY_B（若 LLM 提案写）/ WORKORDER_CREATED
```
经 Django Admin（`/admin/api/workorder/`）核对新建工单（本期仅落库 + Admin，无前端 UI、无通知）。

---

## 4. 回滚

```bash
# 1) 停服务
sudo systemctl disable --now freeark-inspection-agent
sudo rm -f /etc/systemd/system/freeark-inspection-agent.service
sudo systemctl daemon-reload
# 2) （如需）回滚 DB —— 会删除已建工单与处置状态，回滚前先备份 inspection_work_order
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0032_token_activity_extended_session
# 3) 代码回滚：git checkout 上一个 commit（现有 backend/consumer 不受影响，无需重启）
```
说明：仅停服务即可让系统回到"无自治巡检"状态（migration 非破坏，可保留字段/表不回滚 DB，零副作用）。

---

## 5. 影响面与隔离

- **进程隔离**：独立 systemd 进程，不与 `freeark-backend`（WSGI/Gunicorn）共享线程池；巡检阻塞不影响 chat/HTTP（REQ-NFUNC-001）。
- **consumer 不动**：方案 B 只读消费 `fault_event`/`condensation_warning_event`，不改也不重启两个 consumer（OOS-03）。
- **DB 负担**：每 30s 两次轻量 SELECT + 少量 UPDATE/INSERT，对 MySQL 影响极低；**严禁**触碰 `device_param_history`（巡检链路不查该大表）。
- **写安全**：策略 B 下 `execute_write` 永不被调用（唯一入口 `WriteAuthPolicy.check()` 恒拒），生产设备参数零自动改动。

---

## 6. 上线后观察（建立策略 A 升级基线，EV-01）

```bash
# 工单创建速率与写提案拦截情况
journalctl -u freeark-inspection-agent --since today | grep -E 'WORKORDER_CREATED|WRITE_BLOCKED'
# 决策异常/超时兜底
journalctl -u freeark-inspection-agent --since today | grep -iE 'ERROR|兜底|未完成'
```
建议连续观察，评估 LLM 写提案与人工处置的吻合率；达标（架构建议 30 天 ≥90%）后再议是否切策略 A（仅改 `.env` 重启，无需改代码）。

---

## 7. 已知生产风险（运维提示）

- **wlan0 省电劣化**（`project_prod_internet_loss_wifi_rca`）：间歇网络抖动会让 LLM 决策超时 → 兜底建单（不丢单），日志可见 ERROR。非致命。
- **vicp.fun DNS 偶发失败**（`feedback_prod_ssh_dns_workaround`）：SSH 连接时用 8.8.8.8 解析 IP + HostKeyAlias 绕过。
- **pid1 fd 上限 1024**（`project_prod_internet_loss_wifi_rca` 附带）：新增常驻进程占用少量 fd，留意总量。
- **服务清单**（`project_freeark_systemd_services`）：本服务为**新增**，不替代任何现有服务；勿与 `freeark-fault-consumer` 混淆。

---

## 8. 部署执行记录（部署后回填）

| 项 | 值 |
|----|----|
| 部署人 | |
| 部署时间 | |
| 部署 commit | |
| Pi 权威回归结果 | |
| migration 0033 结果 | |
| 服务启动结果 | |
| 首日工单数 / 拦截数 / 兜底数 | |
| 异常与处理 | |
```
（首次部署完成后，可在 docs/deployment/v1.1.0_autonomous_inspection_agent/ 下补 deployment_report_<date>.md）
```
