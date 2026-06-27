# 部署计划 — 方舟智能体 Reasoning 流式展示

```
file_header:
  document_id: DEPLOY-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_devops_engineer (PM-orchestrated, PARTIAL_FLOW GROUP_E)
  created_at: 2026-05-26
  depends_on:
    - ARCH-REASONING-001 (architecture_design.md)
    - TP-REASONING-001 (test_plan.md)
    - SKILL.md (.claude/skills/freeark-prod-deploy/SKILL.md)
    - PM-DEC-001 (走法B：防御性双路解析，上线后验证)
  scope: 仅文档，不含任何实际部署操作
```

---

> **重要声明**：本文档为部署操作计划，描述所有步骤但不执行任何实际部署。
> **生产部署须等待用户明确发出 PRODUCTION_DEPLOY_CONFIRM 信号后，由运维人员按本计划执行。**
> 任何 SSH 连接、服务重启、.env 修改均不在本文档范围内执行。

---

## 0. 部署概览

### 0.1 本次部署范围

| 文件 | 版本 | 改动性质 |
|------|------|---------|
| `FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py` | v1.2 → v1.3 | 双路 reasoning 字段解析 + reasoning_effort 透传 + 统计日志 |
| `FreeArkWeb/backend/freearkweb/api/consumers.py` | v1.1 → v1.2 | 解包 (kind, text) 二元组 + reasoning_token/reasoning_end 消息类型 + _in_reasoning 状态机 |
| `FreeArkWeb/frontend/src/views/ChatView.vue` | 无版本 → v1.1 | `<details>` 折叠区 + msg.reasoning 字段 + 消息类型处理 |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | — | 追加 `OPENCLAW_REASONING_EFFORT` 读取 env var |

测试通过情况：34/34 单元+集成测试通过（`api/tests/test_reasoning_stream.py`）。

### 0.2 不在本次部署范围

- nginx 配置（无改动）
- systemd unit 文件（无改动）
- MySQL 数据库迁移（无）
- OpenClaw Gateway 配置（无改动，openclaw-gateway.service 不需重启，除非 .env OPENCLAW_* 有变化）
- 其他 freeark-* worker 服务（settings.py 追加只读 env var，不影响 worker 行为，无需重启）

---

## 1. 部署前置条件检查清单

> 执行生产部署前，运维人员须逐项核对以下清单并打勾确认。任意一项不满足须暂停部署并上报。

### 1.1 环境依赖版本确认

| 依赖 | 要求 | 验证命令 | 备注 |
|------|------|---------|------|
| Python | 3.13.x | `venv/bin/python --version` | 须在 venv 内 |
| Node.js | 22.22.2 | `node --version` | 系统级安装 |
| npm | 与 Node 22 配套 | `npm --version` | — |
| Django Channels | 已装 | `venv/bin/pip show channels` | — |
| uvicorn[standard] | 已装（含 websockets） | `venv/bin/pip show uvicorn` | 缺 [standard] 会出 WS 升级失败 |
| aiohttp | 已装 | `venv/bin/pip show aiohttp` | adapter 依赖 |
| daphne | 4.2.1（仅测试环境需要，生产用 uvicorn） | — | 生产不需检查 |

**执行路径（Pi 上）：**
```bash
cd /home/yangyang/Freeark/FreeArk
venv/bin/python --version
node --version
venv/bin/pip list | grep -E "channels|uvicorn|aiohttp"
```

### 1.2 生产 .env 配置核对

运维人员手动打开 `FreeArkWeb/backend/.env` 确认以下字段存在且值正确（不打印敏感值，只确认字段存在）：

| 字段 | 检查方式 | 要求 |
|------|---------|------|
| `OPENCLAW_BASE_URL` | `grep OPENCLAW_BASE_URL .env` | 应为 `http://127.0.0.1:18789` |
| `OPENCLAW_GATEWAY_TOKEN` | `grep -c OPENCLAW_GATEWAY_TOKEN .env` | 应返回 1（字段存在）；不打印值 |
| `OPENCLAW_TIMEOUT` | `grep OPENCLAW_TIMEOUT .env` | 应为 60 |
| `OPENCLAW_CONNECT_TIMEOUT` | `grep OPENCLAW_CONNECT_TIMEOUT .env` | 应为 10 |
| `ALLOWED_HOSTS` | `grep ALLOWED_HOSTS .env` | 须含 `192.168.31.51` 和 `et116374mm892.vicp.fun` |
| `DEBUG` | `grep "^DEBUG=" .env` | 应为 `False` |

**可选新增字段**（本次部署可追加，若不设则使用模型默认 reasoning_effort）：
```
OPENCLAW_REASONING_EFFORT=low
```
> 注：此字段不含敏感信息，可入 .env 但不可入 git 仓库。值域：`low` / `medium` / `high` / 空字符串（空=不透传，模型默认）。

**Token 一致性检查**（不打印值）：
```bash
[ "$(cut -c1-8 ~/.openclaw_gateway_token)" = \
  "$(grep '^OPENCLAW_GATEWAY_TOKEN=' FreeArkWeb/backend/.env | cut -d= -f2 | cut -c1-8)" ] \
  && echo "TOKEN_MATCH" || echo "TOKEN_MISMATCH"
```
TOKEN_MISMATCH 时暂停部署，检查 OpenClaw 是否重装导致 token 变更。

### 1.3 Git 状态核对（本地 → 远端）

在**开发机**（Windows）确认：
```powershell
# 确认本地 HEAD 包含本期所有改动
git log --oneline -5
# 预期最新 commit 包含 openclaw_adapter.py v1.3, consumers.py v1.2,
# ChatView.vue v1.1, settings.py OPENCLAW_REASONING_EFFORT

# 确认已推送到远端 main
git status   # 应为 clean 或仅有不入仓的本地文件
git log origin/main..HEAD  # 应无输出（本地与远端同步）
```

### 1.4 拉取范围核对（不可覆盖生产本地修改）

在**生产 Pi** 上，确认本次 pull 不触碰以下受保护文件：
```bash
cd /home/yangyang/Freeark/FreeArk
# 对比生产当前 HEAD 与即将拉取的 HEAD，列出变更文件
git fetch origin main
git diff --name-only HEAD origin/main
```

**受保护文件（若出现在 diff 中须停止部署并上报）：**
- `FreeArkWeb/backend/.env`
- `FreeArkWeb/frontend/package-lock.json`
- `FreeArkWeb/backend/heartbeat_broker_config.json`

若以上文件不在 diff 中，继续执行部署。

### 1.5 备份确认

部署前须创建备份（Pi 上执行）：
```bash
# 备份前端 dist（前端构建前）
cp -r FreeArkWeb/frontend/dist \
  /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S)

# 记录当前生产 HEAD
git log -1 --oneline > /home/yangyang/FreeArk_backup/pre_deploy_head_$(date +%Y%m%d%H%M%S).txt

# 验证备份存在
ls -lh /home/yangyang/FreeArk_backup/ | tail -5
```

---

## 2. ARCH-C-002 同批次部署约束（强制）

> **这是本次部署的最高优先级约束，违反将导致生产服务崩溃。**

**约束来源**：ARCH-C-002（architecture_design.md §3.1）

**内容**：`openclaw_adapter.py v1.3` 和 `consumers.py v1.2` **必须同批次部署**，**禁止单独部署任何一个**。

**原因**：
- v1.3 adapter 的 `stream_chat()` 改为产出 `(kind, text)` 二元组
- v1.2 consumer 的 `_handle_chat` 期待解包 `(kind, text)` 二元组
- 若仅部署 adapter v1.3 而 consumer 仍为 v1.1，consumer 尝试将 `('reasoning', 'text')` 当 str 处理，触发 `TypeError`，**全部聊天请求失败**

**合法部署组合**：

| adapter | consumer | ChatView.vue | 结果 |
|---------|----------|-------------|------|
| v1.3 | v1.2 | v1.1 | 正常，reasoning 展示 |
| v1.3 | v1.2 | 旧版 | 正常，reasoning 被旧前端静默忽略 |
| v1.2 | v1.1 | 旧版 | 旧行为，不崩溃 |
| **v1.3** | **v1.1** | **任意** | **禁止，运行时 TypeError** |

**操作要求**：后端服务重启须在 `git pull` 包含 adapter + consumer 同批次改动后执行，不得在中间状态（仅 pull 部分文件）时重启 `freeark-backend`。

---

## 3. 前端构建步骤

> 前端构建须在 Pi 上执行（生产 ARM 环境）。构建产物直接替换 `dist/`，nginx 无需 reload 即可感知。

**执行位置**：生产 Pi，SSH 连接后

```bash
# SSH 连接
# 开发机 Bash 工具：ssh -p 57279 yangyang@et116374mm892.vicp.fun

cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend

# 步骤 1：备份当前 dist（若步骤 1.5 未做则在此补做）
cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S)

# 步骤 2：检查是否需要 npm install（依赖未变化时跳过）
# 本次改动：仅 ChatView.vue 修改，无新 npm 依赖，跳过 npm install
# 注意：package-lock.json 有生产本地修改（ARM 依赖树），不要 npm install --frozen-lockfile

# 步骤 3：构建
npm run build
# 预期输出：vite build 成功，dist/ 更新
# 预期耗时：约 15-30 秒（Pi 5 性能）

# 步骤 4：验证构建产物
ls -lh dist/assets/ | head -5
# 确认有最新的 .js 文件（时间戳为当前时间）

# 步骤 5（可选）：nginx reload 保险
sudo systemctl reload nginx
```

**构建失败处理**：
- 若 `npm run build` 报错，检查 Node.js 版本（须 22.22.2）和 dist 备份（已在步骤 1 备份），回滚时直接恢复备份。
- 不要在构建失败时手动上传文件（禁止 pscp）。

---

## 4. 后端代码部署步骤（git pull）

> 禁止 Docker。禁止 pscp 逐文件上传。一律 git pull。

**执行位置**：生产 Pi

```bash
cd /home/yangyang/Freeark/FreeArk

# 步骤 1：确认当前工作树状态
git status
# 预期：仅 .env / package-lock.json / heartbeat_broker_config.json 等受保护文件有本地修改
# 若有其他未跟踪或已修改文件，评估是否会被覆盖，若有疑虑暂停并上报

# 步骤 2：拉取（fast-forward）
git pull origin main
# 预期：fast-forward，更新 openclaw_adapter.py / consumers.py / ChatView.vue / settings.py
# 若出现 merge conflict，暂停部署并上报

# 步骤 3：验证代码落地
git log -1 --oneline
# 确认 HEAD 为本期 commit

# 步骤 4：关键文件存在性检查
grep -n "_REASONING_FIELD" FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py | head -3
grep -n "reasoning_token" FreeArkWeb/backend/freearkweb/api/consumers.py | head -3
grep -n "reasoning_token" FreeArkWeb/frontend/src/views/ChatView.vue | head -3
grep -n "OPENCLAW_REASONING_EFFORT" \
  FreeArkWeb/backend/freearkweb/freearkweb/settings.py | head -3
# 四个命令均应有输出，否则说明对应文件未更新

# 步骤 5：检查是否有新 Python 依赖（本次无新依赖，确认即可）
# 本次改动不引入新第三方库，venv/bin/pip install -r ... 步骤跳过
# 若 requirements.txt 有变化（git diff 显示），须执行：
# venv/bin/pip install -r FreeArkWeb/backend/requirements.txt
```

---

## 5. systemd 服务重启清单

### 5.1 必须重启的服务

| 服务 | 重启原因 | 命令 |
|------|---------|------|
| `freeark-backend` | adapter.py + consumers.py + settings.py 全部在此加载，需重载 | `sudo systemctl restart freeark-backend` |

### 5.2 条件性重启的服务

| 服务 | 重启条件 | 命令 |
|------|---------|------|
| `openclaw-gateway.service` | 仅当 `.env` 中 `OPENCLAW_*` 字段有变化（如追加了 `OPENCLAW_REASONING_EFFORT`）时 | `systemctl --user restart openclaw-gateway.service`（无 sudo） |

> 注意：`openclaw-gateway.service` 是**用户服务**，不要加 `sudo`，否则操作的是 root 的用户上下文，与 yangyang 用户的服务实例无关。

### 5.3 不需要重启的服务

- `freeark-mqtt-consumer`（无改动）
- `freeark-plc-connection-monitor`（无改动）
- `freeark-plc-cleanup`（无改动）
- `freeark-dph-cleanup`（无改动）
- `freeark-screen-heartbeat`（无改动）
- `freeark-daily-usage`（无改动）
- `freeark-monthly-usage`（无改动）
- `freeark-task-scheduler`（无改动）

> 注：settings.py 新增的 `OPENCLAW_REASONING_EFFORT` 只读 env var，不影响上述 worker 服务行为。

### 5.4 重启执行顺序

```bash
# 1. 重启主后端（必须）
sudo systemctl restart freeark-backend

# 等待 3 秒确认服务已起
sleep 3
systemctl status freeark-backend --no-pager | grep -E "Active|Main PID"
# 预期：Active: active (running)

# 2. 若追加了 OPENCLAW_REASONING_EFFORT，重启 gateway（条件性）
# systemctl --user restart openclaw-gateway.service
# sleep 5
# systemctl --user status openclaw-gateway.service --no-pager | grep Active

# 3. 快速验证（见 §8 详细验证清单）
curl -s http://127.0.0.1:8080/api/health/
# 预期：{"status":"ok",...}
```

### 5.5 关于 systemd unit 文件

本次部署**不修改** systemd unit 文件。`systemctl/` 目录下的 unit 文件仅是源副本，`git pull` 不会自动更新正在运行的 systemd。仅在 unit 文件有变化时才需要：
```bash
sudo cp systemctl/<unit_name>.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart <svc>
```

---

## 6. US-RSN-001 走法 B 后置验证流程

> **背景**：PM-DEC-001 选定走法 B（防御性双路解析）。adapter v1.3 已实现
> `_REASONING_FIELD='reasoningDelta'` 作为主路径，`kind=='reasoning'` 作为备用路径。
> 上线后需通过日志验证 reasoningDelta 字段是否命中。

### 6.1 第一步：触发对话并观察 stream_complete 日志

**前置**：`freeark-backend` 已重启，服务 active (running)。

临时拉高日志级别（INFO 默认不打）：
```bash
# 方法 A：在生产 .env 追加一行（需重启服务生效）
echo "APP_LOG_LEVEL=INFO" >> FreeArkWeb/backend/.env
sudo systemctl restart freeark-backend

# 或方法 B：systemctl environment（当前进程生效，重启后失效）
sudo systemctl set-environment APP_LOG_LEVEL=INFO
sudo systemctl restart freeark-backend
```

从前端触发 1-2 次对话（建议问题："分析三恒系统的智能控制优化方向"——此类问题会触发 DeepSeek reasoning）：
```bash
# 查看 stream_complete 日志
sudo journalctl -u freeark-backend -n 100 --no-pager | grep stream_complete
```

**预期输出格式**（示例）：
```
stream_complete reasoning_tokens=45 content_tokens=312 reasoning_ms=8234 content_ms=12045
```

### 6.2 第二步：判断走法 B 是否命中

| 观察结果 | 结论 | 处置 |
|---------|------|------|
| `reasoning_tokens > 0` | reasoningDelta 字段命中，走法 B 验证成功 | 继续执行 §6.3，恢复日志级别 |
| `reasoning_tokens = 0` | 字段名未命中，触发探查流程（见 §6.3） | 执行 §6.3 |
| 日志无 stream_complete | APP_LOG_LEVEL 未生效 | 检查 .env 是否正确追加 + 重启服务 |

### 6.3 reasoning_tokens=0 时的字段名探查流程

> 若 §6.2 发现 reasoning_tokens=0，执行以下探查，确定实际字段名。

**步骤 1**：在 `openclaw_adapter.py` 的 `state == 'delta'` 分支内临时加入 PROBE logger：
```python
# 临时，探查完毕后立即移除
logger.info('PROBE delta payload keys: %s', list(payload.keys()))
```
具体位置：`FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py`，找到 `if state == 'delta':` 所在行，在分支内首行插入。

**步骤 2**：确保 APP_LOG_LEVEL=INFO 已生效，重启后端：
```bash
sudo systemctl restart freeark-backend
```

**步骤 3**：从前端触发 1-2 次对话，提取 payload keys：
```bash
sudo journalctl -u freeark-backend -n 100 --no-pager | grep "PROBE delta payload keys"
# 预期示例：PROBE delta payload keys: ['deltaText', 'reasoningDelta', 'state', 'sessionKey']
```

**步骤 4**：根据实测结果更新 `_REASONING_FIELD` 常量（单行改动）：
```python
# openclaw_adapter.py 顶部
_REASONING_FIELD = 'reasoningDelta'   # 将此处替换为实测字段名
# 候选：'thinkingDelta' / 'reasoning' / 其他
```

**步骤 5**：移除临时 PROBE logger（必须），提交并推送：
```bash
# 在开发机编辑后，提交
# commit 消息写入 txt 文件（PowerShell 中文安全）：
# 内容：fix(reasoning-stream): update _REASONING_FIELD to <实测字段名> per US-RSN-001 probe
Set-Content -Path docs/specs/freeark_lobster_reasoning_stream/commit_msg_rsn001.txt `
  -Value "fix(reasoning-stream): update _REASONING_FIELD to <实测字段名> per US-RSN-001 probe"
git add FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py
git commit -F docs/specs/freeark_lobster_reasoning_stream/commit_msg_rsn001.txt
git push origin main
```

**步骤 6**：生产 git pull + 重启后端：
```bash
cd /home/yangyang/Freeark/FreeArk
git pull origin main
sudo systemctl restart freeark-backend
```

**步骤 7**：验证 reasoning_tokens > 0（重复 §6.1 观察）。

**步骤 8**：探查成功后，移除 APP_LOG_LEVEL=INFO（避免长期高日志量）：
```bash
# 从 .env 移除 APP_LOG_LEVEL 行（若用方法 A 追加）
# 或：sudo systemctl unset-environment APP_LOG_LEVEL
sudo systemctl restart freeark-backend
```

**步骤 9**：更新 architecture_design.md ADR-006，在 `_REASONING_FIELD` 注释处标注"来源：GROUP_E 实测，2026-MM-DD"。此改动可和步骤 5 合并提交。

**降级行为说明**：探查期间（reasoning_tokens=0）前端不显示 `<details>` 折叠区，仍显示原版「正在思考...」——这是 ADR-006 防御性设计保证的，功能降级但不崩溃。

---

## 7. US-RSN-009 基线测量步骤

> **目标**：测量 reasoning 首 token 延迟，评估 OPENCLAW_REASONING_EFFORT=low 的加速效果。
> **前置条件**：adapter v1.3 已部署，reasoning_tokens > 0（字段名已确认），APP_LOG_LEVEL=INFO 已激活。

### 7.1 测量指标定义

| 指标 | 定义 | 单位 |
|------|------|------|
| reasoning_ms | 从 chat.send 到首个 reasoning_token 发出的时间差 | 毫秒 |
| content_ms | 从首个 stream_token 到 stream_end 的时间差 | 毫秒 |

这两个指标由 adapter v1.3 的统计日志在 `stream_complete` 中自动输出，无需额外打桩。

### 7.2 日志采集方法（旁路验证）

由于生产日志级别默认为 ERROR，测量时须临时激活 INFO 级别（方式与 §6.1 相同）：

```bash
# 确认 APP_LOG_LEVEL=INFO 已生效
sudo journalctl -u freeark-backend -n 5 --no-pager | grep "stream_complete"
```

若日志不可用（如无法临时改 .env），可用 curl 旁路粗测首 token 延迟（精度低，仅估算）：
```bash
# 在 Pi 本地：测量从建立 WS 连接到收到第一条消息的时间
# 注意：curl 不支持 WS，此处为 HTTP 健康检查旁路验证
time curl -s http://127.0.0.1:8080/api/health/
# 仅验证后端在线，不能精确测 reasoning 延迟

# 精确 WS 延迟测量须在前端 DevTools 中手动操作：
# 1. Chrome → DevTools → Network → WS → 打开 /ws/chat/ 连接
# 2. 发送消息后，观察第一个 reasoning_token frame 的时间戳与 chat_message 的时间差
# 这是 GROUP_E 记录基线的推荐方式（无需改服务端）
```

### 7.3 步骤 A：基线测量（OPENCLAW_REASONING_EFFORT 未设置或为空）

```bash
# Pi 上：确认当前未设置 OPENCLAW_REASONING_EFFORT
grep OPENCLAW_REASONING_EFFORT FreeArkWeb/backend/.env || echo "未设置（正常）"

# 连续 3 次从前端发送相同问题：
# "介绍三恒系统的主要设备组成，包括新风机组、风机盘管和除湿机"

# 提取 reasoning_ms 值
sudo journalctl -u freeark-backend -n 50 --no-pager \
  | grep stream_complete | grep reasoning_ms | tail -3
```

记录每次 reasoning_ms 值 T1、T2、T3，计算：
```
T0 = (T1 + T2 + T3) / 3   （基线均值，单位 ms）
```
将 T0 写入 `docs/specs/freeark_lobster_reasoning_stream/tech_stack.md` 的 NFR 基线表。

### 7.4 步骤 B：low 配置效果验证

```bash
# 在生产 .env 追加（若尚未设置）：
echo "OPENCLAW_REASONING_EFFORT=low" >> FreeArkWeb/backend/.env
sudo systemctl restart freeark-backend

# 等待 3 秒
sleep 3

# 重复 3 次发送同一问题，记录 T1', T2', T3'
sudo journalctl -u freeark-backend -n 50 --no-pager \
  | grep stream_complete | grep reasoning_ms | tail -3
```

计算：
```
T0' = (T1' + T2' + T3') / 3
效果比 = (T0 - T0') / T0 * 100%
```

**验收标准**：`效果比 >= 50%`（reasoning_ms 下降 50% 以上）。

| 结果 | 处置 |
|------|------|
| 效果比 >= 50% | US-RSN-009 通过，记录基线数据，保留 `OPENCLAW_REASONING_EFFORT=low` |
| 效果比 < 50% 但 > 0% | 上报 PM，由 PM 评估是否调整 NFR 阈值或尝试 `medium` 配置 |
| reasoning_ms 无变化 | 上报 PM，可能 RISK-003 实例化（OpenClaw 不透传 reasoningEffort 到 DeepSeek） |
| 效果比负值（low 反而更慢） | 上报 PM，检查 RISK-004（字段名 camelCase/snake_case 问题） |

**RISK-003/004 处置**（若 reasoning_effort 透传无效）：

由 PM 决策以下任一方案（不在本文档自行决定）：
- 方案 B（全局 models.json）：修改 `~/.openclaw/agents/main/agent/models.json`，影响所有 OpenClaw 客户端
- 接受现状：不设置 reasoning_effort，使用 DeepSeek 模型默认配置

### 7.5 测量完成后清理

```bash
# 测量完毕后，根据 PM 决策决定是否保留 APP_LOG_LEVEL=INFO
# 若不保留（节省日志量）：
# 从 .env 移除 APP_LOG_LEVEL 行（手动编辑）
sudo systemctl restart freeark-backend
```

---

## 8. 部署后验证清单

### 8.1 服务状态检查

```bash
# freeark-backend 运行中
systemctl status freeark-backend --no-pager | grep -E "Active|Main PID"
# 预期：Active: active (running)

# (若重启了 openclaw-gateway) Gateway 运行中
systemctl --user status openclaw-gateway.service --no-pager | grep Active
# 预期：Active: active (running)

# OpenClaw Gateway 健康检查
curl -s http://127.0.0.1:18789/health
# 预期：{"ok":true,"status":"live"}
```

### 8.2 后端健康检查

```bash
# HTTP API 健康
curl -s http://127.0.0.1:8080/api/health/
# 预期：{"status":"ok",...}

# 无 WS 升级错误
sudo journalctl -u freeark-backend -n 20 --no-pager \
  | grep -E "ERROR|Traceback|Unsupported upgrade|TypeError"
# 预期：无输出（无错误）
```

### 8.3 功能验证

```bash
# Django shell 快速验证 adapter 可 import（依赖齐全）
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
venv/bin/python -c "from api.openclaw_adapter import OpenClawAdapter; print('adapter OK')"
venv/bin/python -c "from api.consumers import ChatConsumer; print('consumer OK')"
# 两行均应输出 OK
```

手动功能验证（浏览器，须有前端访问）：

| 验证项 | 步骤 | 预期 |
|--------|------|------|
| 聊天正常 | 打开 ChatView，发送消息 | 收到流式回复，无空气泡 |
| Reasoning 展示 | 发送触发 reasoning 的问题 | 出现 `<details>` 折叠区，显示「思考过程」 |
| Reasoning 折叠 | 等待 reasoning_end | `<details>` 自动折叠 |
| Content 接续 | 等待 stream_token | 折叠区下方出现正式回答 |
| 旧前端兼容（若有） | 旧版前端发送消息 | 无 JS 报错，content 正常流入 |

### 8.4 日志与错误率检查

```bash
# 查看最近 50 条日志（重启后）
sudo journalctl -u freeark-backend -n 50 --no-pager

# 若 APP_LOG_LEVEL=INFO 已激活，验证 stream_complete 日志存在
sudo journalctl -u freeark-backend -n 50 --no-pager | grep stream_complete

# OpenClaw adapter import 后首次连接日志（连接成功标志）
journalctl --user -u openclaw-gateway.service -n 20 --no-pager | grep -E "connect|error"
```

**验证通过条件**：
- 无 `TypeError` / `AttributeError` / `CRITICAL` 级别日志
- `stream_complete` 日志出现（APP_LOG_LEVEL=INFO 时）
- `curl /api/health/` 返回 200

---

## 9. 回滚方案

> 若部署后发现功能异常（聊天服务中断、TypeError、服务无法启动），立即执行回滚。
> **回滚决策须由 PM 或运维负责人确认**，不得自行回滚功能性改动。

### 9.1 快速诊断（决定是否回滚）

```bash
# 查看错误
sudo journalctl -u freeark-backend -n 30 --no-pager | grep -E "ERROR|Traceback|TypeError"

# 若出现 TypeError 且栈帧在 consumers.py / openclaw_adapter.py 中：
# → 大概率是 adapter/consumer 版本不匹配，执行回滚

# 若服务无法启动：
# → 查看完整启动日志定位原因
sudo journalctl -u freeark-backend --since "5 minutes ago" --no-pager
```

### 9.2 代码回滚（git revert）

```bash
# 在生产 Pi 上（不要在开发机操作生产仓库）：
cd /home/yangyang/Freeark/FreeArk

# 查看要回滚的 commit
git log --oneline -5

# 方案 A：回滚到上一个已知良好 commit（推荐）
# 记录上一个良好 HEAD（从步骤 1.5 的备份文件读取）
cat /home/yangyang/FreeArk_backup/pre_deploy_head_*.txt | tail -1
# 例如：ffe593f docs(reasoning-stream): GROUP_C 产出文档...

git checkout ffe593f -- FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py
git checkout ffe593f -- FreeArkWeb/backend/freearkweb/api/consumers.py
git checkout ffe593f -- FreeArkWeb/backend/freearkweb/freearkweb/settings.py
# 注意：settings.py 回滚后 OPENCLAW_REASONING_EFFORT 不再被读取，但不影响功能

# 若前端也需回滚（构建产物回滚）：
# 恢复 dist 备份
cp -r /home/yangyang/FreeArk_backup/dist_backup_<时间戳> \
  FreeArkWeb/frontend/dist

# 方案 B：若需要干净 HEAD（不留中间状态）
# 在开发机提交 revert commit 并 push，然后生产 git pull
# （生产 Pi 不应 git revert，避免 conflict 风险）
```

### 9.3 服务回滚重启

```bash
# 代码回滚后，重启服务
sudo systemctl restart freeark-backend
sleep 3
systemctl status freeark-backend --no-pager | grep Active
curl -s http://127.0.0.1:8080/api/health/
```

### 9.4 回滚验证

```bash
# 确认旧版 adapter 已生效（v1.2 无 _REASONING_FIELD 常量）
grep -c "_REASONING_FIELD" FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py
# 预期：0（回滚后无此常量）

# 快速功能确认
curl -s http://127.0.0.1:8080/api/health/
# 预期：{"status":"ok",...}
```

### 9.5 回滚后状态

回滚到 v1.2/v1.1 后，系统恢复到：
- ChatConsumer v1.1，无 reasoning 类型支持
- 前端显示「正在思考...」静态文字（原始体验）
- 功能完整，无崩溃

---

## 10. 部署时间估算

| 步骤 | 估算时间 | 备注 |
|------|---------|------|
| 前置条件检查（§1）| 5-10 分钟 | 手动核对各项 |
| 备份（§1.5）| 2 分钟 | |
| git pull（§4）| 1 分钟 | 网络良好时 |
| 前端构建（§3）| 15-30 秒 | Pi 5 性能 |
| 服务重启（§5）| 1 分钟 | 含等待启动 |
| 部署后验证（§8）| 5-10 分钟 | |
| US-RSN-001 字段探查（若需要，§6.3）| 15-30 分钟 | 含 PROBE 代码改动 + push + pull |
| US-RSN-009 基线测量（§7）| 20-30 分钟 | 含两轮测量 + 对比 |
| **合计（含探查和测量）** | **约 50-80 分钟** | |
| **合计（探查和测量已完成时）** | **约 15-25 分钟** | |

---

## 附录 A：OpenClaw 链路快速排查清单

若聊天功能异常，按顺序执行：
```bash
# 1. Gateway 在线
systemctl --user is-active openclaw-gateway.service
curl -s http://127.0.0.1:18789/health

# 2. Backend 在线
systemctl status freeark-backend --no-pager | grep Active
sudo journalctl -u freeark-backend -n 20 | grep -v "^--"

# 3. Nginx WS 配置
grep -A 2 "location /ws/" /etc/nginx/sites-enabled/freeark | head -6

# 4. ALLOWED_HOSTS 含 Pi IP
grep "^ALLOWED_HOSTS" FreeArkWeb/backend/.env

# 5. Token 一致性
[ "$(cut -c1-8 ~/.openclaw_gateway_token)" = \
  "$(grep '^OPENCLAW_GATEWAY_TOKEN=' FreeArkWeb/backend/.env | cut -d= -f2 | cut -c1-8)" ] \
  && echo "TOKEN_MATCH" || echo "TOKEN_MISMATCH"

# 6. Adapter import 正常
cd FreeArkWeb/backend/freearkweb
venv/bin/python -c "from api.openclaw_adapter import OpenClawAdapter; print('OK')"
```
