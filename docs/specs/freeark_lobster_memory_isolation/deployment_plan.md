# 部署计划 — 方舟龙虾记忆隔离

```
file_header:
  document_id: DEPLOY-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_devops_engineer (PM-orchestrated, PARTIAL_FLOW GROUP_E)
  created_at: 2026-05-26
  depends_on:
    - ARCH-MEMORY-001 (architecture_design.md，ADR-009~013)
    - IMPL-MEMORY-001 (implementation_plan.md)
    - CR-MEMORY-001 (code_review_report.md)
    - TR-MEMORY-001 (test_report_groupd.md，130/130 通过)
    - DEPLOY-REASONING-001 (freeark_lobster_reasoning_stream/deployment_plan.md，参考结构)
    - SKILL.md (.claude/skills/freeark-prod-deploy/SKILL.md)
  scope: 仅文档，不含任何实际部署操作
  base_commit_at_authoring: ef3c509 (reasoning_stream GROUP_E 部署后状态)
  target_commit: 519ddb1 (memory-isolation GROUP_D 130/130 通过 + chat_memory 排序 bug 修复)
```

---

> **重要声明**：本文档为部署操作计划，描述所有步骤但不执行任何实际部署操作。
> **生产部署须等待用户明确发出 PRODUCTION_DEPLOY_CONFIRM 信号后，由运维人员按本计划执行。**
> **skeleton_guard lock（chattr +i）和 USER.md 通用化属于独立操作，各需独立 CONFIRM，不随代码部署一并授权。**
> 任何 SSH 连接、数据库迁移、服务重启、chattr 操作均不在本文档范围内执行。

---

## §0 强制约束

以下约束来自用户，优先级高于本文档一切内容。违反即视为部署失败。

| 编号 | 约束内容 |
|------|---------|
| HC-01 | **禁止 Docker**。一律通过 git pull 部署代码。 |
| HC-02 | **禁止 pscp 逐文件上传**。代码变更须通过 git pull，不得手动上传文件。 |
| HC-03 | **不碰生产 .env 中的密钥字段**。OPENCLAW_GATEWAY_TOKEN / DB 凭据 / SECRET_KEY 等敏感字段只能在 Pi 本地编辑，绝不入 git 仓库，绝不在任何日志/文档中打印原始值。 |
| HC-04 | **不碰 ~/.openclaw/ 配置文件**（SKILL.md、openclaw.json 等），除非有明确 CONFIRM。OpenClaw Gateway 本次不需要重启（除 .env 的 OPENCLAW_* 有变化）。 |
| HC-05 | **migrate 命令必须含回滚命令**。本文档 §3 给出全套 dry-run、实际执行和回滚到 0024 的完整命令，无一省略。 |
| HC-06 | **chattr +i 是 OS 层不可逆操作**，须在用户独立发出 SKELETON_LOCK_CONFIRM 信号后才能执行。此信号独立于代码部署 PRODUCTION_DEPLOY_CONFIRM，且每次执行前须重新确认，不可复用历史确认。 |
| HC-07 | **USER.md 通用化需用户独立 CONFIRM（USER_MD_CONFIRM）**，独立于代码部署和 skeleton lock，详见 §7。 |
| HC-08 | **git commit 走 `git commit -F <文件>`**（PowerShell 中文断字保护）。本期 PM 不 commit，commit 时机由用户决定。 |
| HC-09 | **生产部署前必须收到用户明确 PRODUCTION_DEPLOY_CONFIRM 信号**。未收到此信号前，任何人不得执行 §4 的 git pull 和 §5 的服务重启。 |
| HC-10 | **不碰 freeark_lobster_reasoning_stream 项目的代码或文档**。本期 §9 的 reasoning_stream 悬置项验证属于"触发对话观察日志"的只读操作，不修改 reasoning_stream 的任何文件。 |

---

## §1 部署前置条件清单

> 收到 PRODUCTION_DEPLOY_CONFIRM 后，运维人员须先完成本节所有检查，再执行 §3~§5。任意一项不满足须暂停部署并上报用户。

### §1.1 环境依赖版本确认

本次部署无新 Python 依赖，无前端构建，但须确认基础环境未发生变化。

| 依赖 | 要求 | 验证命令 | 备注 |
|------|------|---------|------|
| Python | 3.13.x（venv 内） | `venv/bin/python --version` | 须在 venv 路径下执行 |
| Node.js | 22.22.2（系统级） | `node --version` | 本次无前端构建，但确认未被意外降级 |
| Django / channels | 已安装 | `venv/bin/pip show django channels` | channels 是 ASGI 必需 |
| uvicorn[standard] | 已安装（含 websockets） | `venv/bin/pip show uvicorn` | 缺 [standard] 会出 WS 升级失败 |
| aiohttp | 已安装 | `venv/bin/pip show aiohttp` | OpenClaw adapter 依赖 |
| mysqlclient | 已安装 | `venv/bin/pip show mysqlclient` | ORM 连接 MySQL 9.4.0 |

**执行路径（Pi 上）：**
```bash
cd /home/yangyang/Freeark/FreeArk
venv/bin/python --version
node --version
venv/bin/pip list | grep -E "Django|channels|uvicorn|aiohttp|mysqlclient"
```

### §1.2 生产 HEAD 确认

```bash
cd /home/yangyang/Freeark/FreeArk

# 确认当前生产 HEAD（预期 ef3c509）
git log -1 --oneline
# 预期：ef3c509 docs(reasoning-stream): GROUP_E 部署计划 + CI/CD pipeline 文档

# 确认远端 main 包含本期 3 个 commit
git fetch origin main
git log --oneline ef3c509..origin/main
# 预期输出（3 行）：
#   519ddb1 test(memory-isolation): GROUP_D 130/130 通过 + chat_memory 排序 bug 修复
#   752faf0 feat(memory-isolation): GROUP_C 后端实现 + 运维脚本
#   d584d1b docs(memory-isolation): GROUP_A+B 需求/架构/ADR 全部 CONFIRMED
```

### §1.3 受保护文件不被覆盖

本次 pull 范围为 3 个 commit（d584d1b → 752faf0 → 519ddb1）。须确认这 3 个 commit 不涉及受保护文件。

```bash
# 列出本次将拉取的所有改动文件
git diff --name-only ef3c509 origin/main
```

**受保护文件（若出现在 diff 中须停止部署并上报）：**
- `FreeArkWeb/backend/.env`
- `FreeArkWeb/frontend/package-lock.json`
- `FreeArkWeb/backend/heartbeat_broker_config.json`

预期 diff 包含的文件（不含以上三个）：

| 文件 | 所属 commit |
|------|-----------|
| `FreeArkWeb/backend/freearkweb/api/models.py` | 752faf0 |
| `FreeArkWeb/backend/freearkweb/api/migrations/0025_chat_session_message.py` | 752faf0 |
| `FreeArkWeb/backend/freearkweb/api/chat_memory.py` | 752faf0 / 519ddb1 |
| `FreeArkWeb/backend/freearkweb/api/consumers.py` | 752faf0 |
| `FreeArkWeb/backend/freearkweb/api/memory_views.py` | 752faf0 |
| `FreeArkWeb/backend/freearkweb/api/urls.py` | 752faf0 |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | 752faf0 |
| `scripts/skeleton_guard.sh` | 752faf0 |
| `api/tests/test_memory_*.py` (5 个文件) | 519ddb1 |
| `docs/specs/freeark_lobster_memory_isolation/` (文档) | d584d1b / 752faf0 / 519ddb1 |

若 diff 列表与上表不符（特别是出现 `.env` / `package-lock.json`），**暂停部署并上报用户**。

### §1.4 生产 .env 核对（只读确认）

本次新增一个 settings.py 配置项 `CHAT_HISTORY_INJECT_TURNS`，其默认值写在代码里（20），**不需要改 .env**。

运维人员手动确认以下字段仍然存在且值正确（不打印敏感值）：

| 字段 | 检查命令 | 要求 |
|------|---------|------|
| `OPENCLAW_BASE_URL` | `grep OPENCLAW_BASE_URL FreeArkWeb/backend/.env` | `http://127.0.0.1:18789` |
| `OPENCLAW_GATEWAY_TOKEN` | `grep -c OPENCLAW_GATEWAY_TOKEN FreeArkWeb/backend/.env` | 返回 1 |
| `ALLOWED_HOSTS` | `grep ALLOWED_HOSTS FreeArkWeb/backend/.env` | 须含 `192.168.31.51` 和 `et116374mm892.vicp.fun` |
| `DEBUG` | `grep "^DEBUG=" FreeArkWeb/backend/.env` | `False` |
| `APP_LOG_LEVEL` | `grep APP_LOG_LEVEL FreeArkWeb/backend/.env` | 当前仍为 `INFO`（reasoning_stream 验证期遗留），本次部署不改，§9 用到 |

**Token 一致性检查（不打印 token 值）：**
```bash
[ "$(cut -c1-8 ~/.openclaw_gateway_token)" = \
  "$(grep '^OPENCLAW_GATEWAY_TOKEN=' FreeArkWeb/backend/.env | cut -d= -f2 | cut -c1-8)" ] \
  && echo "TOKEN_MATCH" || echo "TOKEN_MISMATCH"
```
TOKEN_MISMATCH 时暂停部署，检查 OpenClaw 是否重装导致 token 变更。

### §1.5 备份确认

```bash
cd /home/yangyang/Freeark/FreeArk

# 记录当前生产 HEAD（用于 rollback 时定位回滚点）
git log -1 --oneline > /home/yangyang/FreeArk_backup/pre_deploy_memory_head_$(date +%Y%m%d%H%M%S).txt

# 验证备份文件已创建
ls -lh /home/yangyang/FreeArk_backup/pre_deploy_memory_head_*.txt | tail -3
```

---

## §2 ARCH-C-006 向后兼容验证步骤

> **背景**：本次部署的核心约束之一是 reasoning_stream v1.2 协议不被破坏（ARCH-C-006）。
> consumers.py 从 v1.2 升级到 v1.3，所有新增 DB 调用均在降级保护块内（try/except），不改变 reasoning/stream 的核心流程。
> 本节提供部署后的实测验证步骤。

### §2.1 consumers.py 版本确认

```bash
cd /home/yangyang/Freeark/FreeArk

# 确认 consumers.py 已更新到 v1.3
grep -n "v1.3\|chat_memory\|chat_session" \
  FreeArkWeb/backend/freearkweb/api/consumers.py | head -10
# 预期：有 "v1.3" 字样和 chat_memory import 相关行
```

### §2.2 ChatConsumer 健康检查（HTTP 层）

```bash
# 后端基础健康
curl -s http://127.0.0.1:8080/api/health/
# 预期：{"status":"ok",...} HTTP 200
```

### §2.3 WS 聊天功能验证（触发对话，验证 reasoning 协议未破坏）

从前端 ChatView 发送一条需要推理的问题（如"分析三恒系统的智能控制优化方向"），观察：

| 验证点 | 预期行为 | 验证方式 |
|--------|---------|---------|
| WS 连接建立 | `connected` 消息正常收到 | 浏览器 DevTools → Network → WS |
| `reasoning_token` 帧 | 流式推理 token 正常流出 | 浏览器 WS 帧列表 |
| `reasoning_end` 帧 | 推理结束帧正常发送 | 浏览器 WS 帧列表 |
| `stream_token` 帧 | 正式回答流式流出 | 浏览器 WS 帧列表 |
| `stream_end` 帧 | 会话正常结束 | 浏览器 WS 帧列表 |
| `<details>` 折叠区 | 出现思考过程折叠区（reasoning_stream 功能完好） | 前端 UI |

### §2.4 日志验证（确认无兼容性错误）

```bash
# 查看后端重启后的最新日志
sudo journalctl -u freeark-backend -n 50 --no-pager | grep -E "ERROR|Traceback|TypeError|AttributeError"
# 预期：无输出（无 v1.3 相关错误）

# 若 APP_LOG_LEVEL=INFO 已激活，验证 stream_complete 日志存在
sudo journalctl -u freeark-backend -n 50 --no-pager | grep stream_complete
# 预期：出现 stream_complete reasoning_tokens=N content_tokens=M reasoning_ms=... content_ms=...
```

**ARCH-C-006 通过条件**：reasoning_token / reasoning_end / stream_token / stream_end 四类消息均正常出现，无 TypeError，stream_complete 日志中 reasoning_tokens > 0（若 APP_LOG_LEVEL=INFO 已激活）。

---

## §3 Django migrate 操作（高风险章节）

> **本节是本次部署最高风险操作**。migrate 前必须完成 MySQL 备份。migrate 失败时必须执行回滚命令，不能仅上报后等待。

### §3.1 MySQL 生产数据库备份（migrate 前必做）

```bash
# SSH 连接生产 Pi 后执行（在 venv 外，使用系统 mysqldump）
# 数据库凭据从 settings.py 中取得（由 dbshell 间接使用，不需要手填密码）

# 方法：通过 Django dbshell 取到数据库连接信息后，手动执行 mysqldump
# 先确认 DB 连接信息（仅确认，不打印密码）：
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
echo "SHOW DATABASES;" | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell

# 执行完整备份（需要在 Pi 上知道 DB 用户名和密码，从 settings.py 读取）
# settings.py 的 DATABASES['default'] 中有 USER / PASSWORD / HOST / NAME
# 备份命令（替换 <DB_USER>、<DB_HOST>、<DB_NAME> 为实际值，密码交互输入，不写在命令行）：
mysqldump -u <DB_USER> -h <DB_HOST> -p <DB_NAME> \
  --single-transaction --quick --lock-tables=false \
  > /home/yangyang/FreeArk_backup/freeark_pre_migrate_memory_$(date +%Y%m%d%H%M%S).sql

# 验证备份文件大小合理（非零，有内容）
ls -lh /home/yangyang/FreeArk_backup/freeark_pre_migrate_memory_*.sql | tail -1
# 预期：文件大小 > 0（几十 KB 到几十 MB，视数据量）
```

> **注意**：mysqldump 中的密码不得写入命令行参数（`-p` 后不跟密码，交互输入），避免密码出现在 shell 历史记录中。

### §3.2 migrate dry-run（预检，无实际变更）

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb

# dry-run：仅显示将要执行的 SQL，不实际应用
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0025_chat_session_message --plan

# 预期输出（包含但不限于）：
#   Planned operations:
#   api.0025_chat_session_message
#     Create model ChatSession
#     Create index chat_sess_user_start_idx on field(s) user, started_at of model chatsession
#     Create model ChatMessage
#     Create index chat_msg_sess_time_idx on field(s) session, created_at of model chatmessage
```

若 --plan 输出有任何意外操作（如 drop table、alter column），**立即暂停并上报用户**，不得继续执行实际 migrate。

### §3.3 实际 migrate 执行

dry-run 确认无异常后，执行实际 migrate：

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb

/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0025_chat_session_message

# 预期输出：
#   Operations to perform:
#     Apply all migrations: api (through 0025_chat_session_message)
#   Running migrations:
#     Applying api.0025_chat_session_message... OK
```

### §3.4 migrate 后验证（两个表已创建）

```bash
# 验证 chat_session 表
echo "DESC api_chat_session;" | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
# 预期输出含：id BIGINT, user_id INT(FK), session_key VARCHAR(36), started_at DATETIME(6), ended_at DATETIME(6)

# 验证 chat_message 表
echo "DESC api_chat_message;" | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
# 预期输出含：id BIGINT, session_id BIGINT(FK), role VARCHAR(20), content LONGTEXT, created_at DATETIME(6)

# 验证索引存在
echo "SHOW INDEX FROM api_chat_session;" | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
# 预期含：chat_sess_user_start_idx

echo "SHOW INDEX FROM api_chat_message;" | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
# 预期含：chat_msg_sess_time_idx

# 验证 migration 历史记录（Django 内部）
echo "SELECT app, name, applied FROM django_migrations WHERE app='api' ORDER BY applied DESC LIMIT 3;" \
  | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
# 预期最新一条：api | 0025_chat_session_message | <当前时间>
```

### §3.5 migrate 失败处理（回滚到 0024）

若 §3.3 的 migrate 命令失败，立即执行以下回滚命令（不得等待，不得重试超过 2 次）：

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb

# 回滚到 0024（migration 回滚命令）
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0024_plcwriterecord_batch_request_id

# 预期输出：
#   Operations to perform:
#     Target specific migration: 0024_plcwriterecord_batch_request_id, from api
#   Running migrations:
#     Unapplying api.0025_chat_session_message... OK
```

回滚成功后验证：
```bash
# 确认 chat_session 表已被删除
echo "SHOW TABLES LIKE 'api_chat_%';" | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
# 预期：Empty set（两个表已删除）
```

回滚完成后**立即上报用户**，提供完整的错误信息和 migrate 输出，等待用户决策下一步。

---

## §4 后端代码部署（git pull）

> **前置条件**：§3 migrate 已成功完成（两个表已创建，验证通过）。
> **禁止 Docker。禁止 pscp。一律 git pull。**

```bash
cd /home/yangyang/Freeark/FreeArk

# 步骤 1：确认当前工作树状态
git status
# 预期：仅受保护文件（.env / package-lock.json / heartbeat_broker_config.json）有本地修改
# 若有其他未预期的已修改或未跟踪文件，评估影响，有疑虑则暂停上报

# 步骤 2：拉取（fast-forward）
git pull origin main
# 预期：fast-forward 更新，无 merge conflict
# 若出现 merge conflict 立即停止，不得强制合并，上报用户

# 步骤 3：验证 HEAD 已更新
git log -1 --oneline
# 预期：519ddb1 test(memory-isolation): GROUP_D 130/130 通过 + chat_memory 排序 bug 修复

# 步骤 4：关键文件落地验证
grep -n "ChatSession\|ChatMessage" \
  FreeArkWeb/backend/freearkweb/api/models.py | head -5
# 预期：有 ChatSession 和 ChatMessage 类定义

grep -n "chat_memory\|chat_session" \
  FreeArkWeb/backend/freearkweb/api/consumers.py | head -5
# 预期：有 chat_memory 模块导入行

grep -n "memory/me\|admin/memory" \
  FreeArkWeb/backend/freearkweb/api/urls.py | head -5
# 预期：有 memory/me/ 和 admin/memory/ 端点注册

grep -n "CHAT_HISTORY_INJECT_TURNS" \
  FreeArkWeb/backend/freearkweb/freearkweb/settings.py | head -3
# 预期：有 CHAT_HISTORY_INJECT_TURNS = ... 行

ls -lh scripts/skeleton_guard.sh
# 预期：文件存在，大小约 4KB

# 步骤 5：确认无新 Python 依赖（本次无变化）
# 本次改动不引入新第三方库，无需执行 pip install
# 若发现 requirements.txt 有变化（git diff 显示），则执行：
# /home/yangyang/Freeark/FreeArk/venv/bin/pip install -r FreeArkWeb/backend/requirements.txt
```

---

## §5 systemd 服务重启（仅 freeark-backend）

> **前置条件**：§4 git pull 完成，所有关键文件落地验证通过。
> OpenClaw Gateway 本次不需要重启（.env 中 OPENCLAW_* 字段无变化）。

### §5.1 必须重启的服务

| 服务 | 重启原因 |
|------|---------|
| `freeark-backend` | consumers.py（v1.2→v1.3）、chat_memory.py（新建）、models.py（新增）、settings.py（新增 CHAT_HISTORY_INJECT_TURNS）均在此进程中加载，必须重启生效 |

### §5.2 不需要重启的服务

以下服务的代码无改动，不重启：

- `freeark-mqtt-consumer`
- `freeark-plc-connection-monitor`
- `freeark-plc-cleanup`
- `freeark-dph-cleanup`
- `freeark-screen-heartbeat`
- `freeark-daily-usage`
- `freeark-monthly-usage`
- `freeark-task-scheduler`
- `openclaw-gateway.service`（Gateway 协议未改动，.env 的 OPENCLAW_* 字段无变化）

### §5.3 重启执行

```bash
# 重启 freeark-backend
sudo systemctl restart freeark-backend

# 等待 5 秒（Django ORM 初始化 + channels layer 启动）
sleep 5

# 确认服务状态
systemctl status freeark-backend --no-pager | grep -E "Active|Main PID"
# 预期：Active: active (running)

# 快速健康检查
curl -s http://127.0.0.1:8080/api/health/
# 预期：{"status":"ok",...}

# 检查无启动错误
sudo journalctl -u freeark-backend -n 30 --no-pager | grep -E "ERROR|Traceback|ImportError"
# 预期：无输出
```

### §5.4 关于 systemd unit 文件

本次部署**不修改** systemd unit 文件。`systemctl/` 目录下的 unit 文件是源副本，`git pull` 不会自动更新正在运行的 systemd。本期无 unit 文件变更，无需 `daemon-reload`。

---

## §6 ADR-011 骨架锁定部署（独立段落，需用户额外 CONFIRM）

> **本节操作须等待用户独立发出 SKELETON_LOCK_CONFIRM 信号才能执行，独立于代码部署的 PRODUCTION_DEPLOY_CONFIRM。**
> chattr +i 是 OS 层不可逆操作（解除需要 sudo chattr -i），请在确认骨架文件内容正确后再执行 lock。

### §6.1 前置条件

在执行任何 skeleton_guard 命令前，须确认：

1. `scripts/skeleton_guard.sh` 已通过 §4 的 git pull 落地到生产 Pi
2. 骨架文件 4 个均存在于 `~/.openclaw/workspace/`（可用 §6.5 的 status 命令验证）
3. 若执行 USER.md 通用化（§7），须先完成 §7 再执行 §6.3 的 lock

### §6.2 init（计算哈希基准）

```bash
cd /home/yangyang/Freeark/FreeArk

# 计算 4 个骨架文件的 SHA-256 哈希基准
bash scripts/skeleton_guard.sh init

# 预期输出：
#   计算骨架文件哈希基准...
#   [OK] ~/.openclaw/workspace/AGENTS.md => <64字符哈希>
#   [OK] ~/.openclaw/workspace/SOUL.md => <64字符哈希>
#   [OK] ~/.openclaw/workspace/TOOLS.md => <64字符哈希>
#   [OK] ~/.openclaw/workspace/USER.md => <64字符哈希>
#   哈希基准已写入: ~/.openclaw/workspace/.skeleton_hashes
```

### §6.3 lock（执行 chattr +i，须 SKELETON_LOCK_CONFIRM）

> **等待用户独立 SKELETON_LOCK_CONFIRM 信号后执行本步骤。**
> 此操作对 4 个骨架文件设置不可变属性，之后任何进程（包括 LLM 工具调用）均无法修改这些文件，直到执行 unlock。

```bash
cd /home/yangyang/Freeark/FreeArk

# 锁定 4 个骨架文件（需要 sudo，yangyang 有 NOPASSWD）
bash scripts/skeleton_guard.sh lock

# 预期输出：
#   对骨架文件设置 chattr +i...
#   [LOCKED] ~/.openclaw/workspace/AGENTS.md
#   [LOCKED] ~/.openclaw/workspace/SOUL.md
#   [LOCKED] ~/.openclaw/workspace/TOOLS.md
#   [LOCKED] ~/.openclaw/workspace/USER.md
#   完成。使用 'unlock' 命令解除锁定后才能修改。
```

### §6.4 verify（验证哈希一致性）

lock 完成后，立即运行 verify 确认文件未在 init 和 lock 之间被篡改：

```bash
bash scripts/skeleton_guard.sh verify

# 预期输出：
#   [PASS] AGENTS.md OK
#   [PASS] SOUL.md OK
#   [PASS] TOOLS.md OK
#   [PASS] USER.md OK
#   验证结果: PASS
```

verify FAIL 时，检查哪个文件哈希不符，调查原因后决定是否重新 init + lock。

### §6.5 status（快速诊断）

任何时候可运行 status 查看当前锁定状态：

```bash
bash scripts/skeleton_guard.sh status

# 预期输出（lock 后）：
#   骨架文件状态：
#     AGENTS.md: chattr_immutable=YES  hash=<前16位>...
#     SOUL.md: chattr_immutable=YES  hash=<前16位>...
#     TOOLS.md: chattr_immutable=YES  hash=<前16位>...
#     USER.md: chattr_immutable=YES  hash=<前16位>...
```

### §6.6 unlock（应急解锁说明）

需要修改骨架文件时（如 USER.md 内容更新、SOUL.md 规则调整），执行应急解锁：

```bash
bash scripts/skeleton_guard.sh unlock
# 预期：4 个文件均解除 +i 属性

# 修改完成后，重新 init 更新哈希基准
bash scripts/skeleton_guard.sh init

# 重新锁定
bash scripts/skeleton_guard.sh lock

# 验证
bash scripts/skeleton_guard.sh verify
```

**注意**：unlock 操作同样须在用户明确授权下执行，不得运维人员自行决定。

---

## §7 ADR-012 USER.md 通用化（独立段落，需用户额外 CONFIRM）

> **本节操作须等待用户独立发出 USER_MD_CONFIRM 信号才能执行，独立于代码部署（PRODUCTION_DEPLOY_CONFIRM）和骨架锁定（SKELETON_LOCK_CONFIRM）。**

### §7.1 背景

ADR-012 决策（方案 12-A）：废弃 USER.md 的个性化字段，USER.md 改为通用默认值并被 chattr +i 锁定。个性化（如"老板"等称呼）通过历史记忆注入机制实现，不再写死在骨架文件中。

### §7.2 USER.md 内容检查（用户必须人工完成）

在执行任何文件操作前，用户须 SSH 到生产 Pi 检查当前 USER.md 内容：

```bash
cat ~/.openclaw/workspace/USER.md
```

**检查项**：
1. 当前 USER.md 是否含特定称呼（如"老板"、用户名等个性化字段）？
2. 若含特定称呼：用户是否决定将其替换为通用版本（如不含任何特定称呼，或使用占位词"用户"）？

**决策分支**：

| 情况 | 处置 |
|------|------|
| USER.md 已是通用内容，无特定称呼 | 直接进入 §6（init + lock），USER.md 当前内容即为锁定内容 |
| USER.md 含特定称呼，用户决定**保留** | 跳过 USER.md 修改，保留当前内容并锁定，个性化在记忆注入中自然体现 |
| USER.md 含特定称呼，用户决定**替换** | 执行 §7.3 的替换流程 |

### §7.3 替换流程（仅当用户决定替换时执行）

> **前置条件**：若骨架文件已被 chattr +i 锁定，须先执行 unlock，再修改，再重新 init + lock。

```bash
# 步骤 1（若已 lock）：先解锁
bash /home/yangyang/Freeark/FreeArk/scripts/skeleton_guard.sh unlock

# 步骤 2：编辑 USER.md（将特定称呼替换为通用内容）
# 使用 nano 或 vi，具体内容由用户决定
nano ~/.openclaw/workspace/USER.md
# 修改内容由用户自行决定，devops 不代为决策

# 步骤 3：确认修改后内容
cat ~/.openclaw/workspace/USER.md

# 步骤 4：重新计算哈希基准（包含修改后的 USER.md）
bash /home/yangyang/Freeark/FreeArk/scripts/skeleton_guard.sh init

# 步骤 5：重新锁定
bash /home/yangyang/Freeark/FreeArk/scripts/skeleton_guard.sh lock

# 步骤 6：验证
bash /home/yangyang/Freeark/FreeArk/scripts/skeleton_guard.sh verify
```

### §7.4 注意事项

- 若 USER.md 被替换为通用内容，用户在对话中提到的个性化偏好（"叫我老板"等）会在未来的对话中通过历史记忆自然注入——这是 ADR-012 方案 12-A 的设计意图。
- 历史对话中已存储的消息不受影响（ChatMessage 表的已有内容不会变）。

---

## §8 部署后验证清单

> 完成 §3~§5 后执行本节验证（§6/§7 的骨架锁定是独立操作，独立验证）。

### §8.1 HTTP /api/health/ 检查

```bash
curl -s http://127.0.0.1:8080/api/health/
# 预期：{"status":"ok",...}  HTTP 200
```

### §8.2 WS 聊天功能完整验证

从前端 ChatView 发送一条消息，在浏览器 DevTools → Network → WS 中验证以下消息帧按顺序出现：

| 消息类型 | 预期 | 说明 |
|---------|------|------|
| `connected` | type: "connected"，含 session_id | WS 连接建立成功 |
| `reasoning_token` | 多帧，含 reasoning 文本 | DeepSeek 推理过程（ARCH-C-006 验证） |
| `reasoning_end` | type: "reasoning_end" | 推理结束（ARCH-C-006 验证） |
| `stream_token` | 多帧，含正式回答文本 | 正式回答流式输出 |
| `stream_end` | type: "stream_end" | 会话完整结束 |

### §8.3 chat_session / chat_message 表写入验证

发送一条对话后，查询 DB 确认两个表已有记录：

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb

# 查询最新 chat_session（使用登录用户的 user_id）
echo "SELECT id, user_id, LEFT(session_key,8) as sk_prefix, started_at, ended_at FROM api_chat_session ORDER BY started_at DESC LIMIT 3;" \
  | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell

# 查询最新 chat_message
echo "SELECT id, session_id, role, LEFT(content,30) as content_preview, created_at FROM api_chat_message ORDER BY created_at DESC LIMIT 5;" \
  | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
```

**预期**：
- chat_session 表有 1 条新记录，started_at 为当前时间，ended_at 已填写（WS disconnect 时写入）
- chat_message 表有至少 2 条记录（1 条 role=user，1 条 role=assistant），均关联至上述 session

### §8.4 跨用户隔离验证

用两个不同的 FreeArk 账号（user A 和 user B）分别发送不同的消息，然后验证：

```bash
# 验证用户 A 的历史不包含用户 B 的消息
# （通过 /api/memory/me/ 端点查询，须携带对应用户的 Token）

# 用户 A：
curl -s -H "Authorization: Token <USER_A_TOKEN>" \
  http://127.0.0.1:8080/api/memory/me/
# 预期：仅含用户 A 的 session

# 用户 B：
curl -s -H "Authorization: Token <USER_B_TOKEN>" \
  http://127.0.0.1:8080/api/memory/me/
# 预期：仅含用户 B 的 session（不含用户 A 的任何记录）
```

> **生产 Token 获取**：通过 FreeArk 登录 API（`/api/token/` 或 `/api/auth/login/`）获取，不得硬编码写入文档。

### §8.5 memory/me/ API 端点验证

```bash
# GET /api/memory/me/（须 DRF Token 认证）
curl -s -H "Authorization: Token <USER_TOKEN>" \
  http://127.0.0.1:8080/api/memory/me/
# 预期：{"total":N,"page":1,"sessions":[...]}

# DELETE /api/memory/me/（清空当前用户记忆）
curl -s -X DELETE -H "Authorization: Token <USER_TOKEN>" \
  http://127.0.0.1:8080/api/memory/me/
# 预期：{"deleted_sessions":N,"message":"记忆已清空"}

# 验证 memory 已清空（再次 GET）
curl -s -H "Authorization: Token <USER_TOKEN>" \
  http://127.0.0.1:8080/api/memory/me/
# 预期：{"total":0,"page":1,"sessions":[]}
```

### §8.6 Django shell 快速 import 验证

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb

# 验证新模块可正常 import（依赖齐全，无语法错误）
/home/yangyang/Freeark/FreeArk/venv/bin/python -c "
from api.models import ChatSession, ChatMessage
from api import chat_memory
from api.memory_views import MyMemoryView, AdminMemoryView
from api.consumers import ChatConsumer
print('all imports OK')
"
# 预期：all imports OK
```

---

## §9 同时验证上一项目 reasoning_stream 的悬置项

> **本节是只读验证操作，不修改 reasoning_stream 的任何代码或文档。**
> 若 APP_LOG_LEVEL=INFO 仍激活（§1.4 已确认当前生产仍为 INFO），本节验证可与 §8.2 合并执行（同一次触发对话即可收集所有数据）。

### §9.1 US-RSN-001 验证（reasoning_tokens > 0 表明 reasoningDelta 命中）

**背景**：reasoning_stream 项目部署后，US-RSN-001（验证 reasoningDelta 字段命中）是悬置项。当前 APP_LOG_LEVEL=INFO 仍激活，可直接验证。

```bash
# 从前端触发 1-2 次对话（建议问题："分析三恒系统的智能控制优化方向"）

# 提取 stream_complete 日志
sudo journalctl -u freeark-backend -n 100 --no-pager | grep stream_complete
```

**判断标准**：

| 结果 | 结论 |
|------|------|
| `reasoning_tokens > 0` | **US-RSN-001 通过**，reasoningDelta 字段命中，走法 B 验证成功 |
| `reasoning_tokens = 0` | reasoning 字段未命中，需按 reasoning_stream 部署计划 §6.3 执行字段探查（不在本文档范围，须上报用户） |
| 日志无 stream_complete 行 | APP_LOG_LEVEL 未生效，检查 .env 是否含该行并重启服务 |

### §9.2 US-RSN-009 基线测量（T0，仅首次基线，T0' 因 RISK-003 已废弃）

**背景**：US-RSN-009 要求测量 reasoning 首 token 延迟基线。RISK-003（OPENCLAW_REASONING_EFFORT= 已清空）意味着 T0'（low 配置效果对比）已废弃，本次仅记录 T0 基线。

**注意**：当前生产 .env 中 OPENCLAW_REASONING_EFFORT= 已清空（RISK-003 接受现状），代表当前运行在模型默认 reasoning effort 下。T0 基线值反映的即是默认配置下的延迟。

```bash
# 连续 3 次从前端发送相同问题（建议："介绍三恒系统的主要设备组成"）
# 每次发送后等待对话完成，再发下一次

# 提取最近 3 次 stream_complete 的 reasoning_ms 值
sudo journalctl -u freeark-backend -n 200 --no-pager \
  | grep stream_complete | grep reasoning_ms | tail -3
```

记录输出中的 3 个 `reasoning_ms=N` 值（T1、T2、T3），计算 T0 = (T1+T2+T3)/3，记录到测试报告或 tech_stack.md 的 NFR 基线表中（由用户决定记录位置，本文档不代为修改 reasoning_stream 的文档）。

---

## §10 回滚方案

> **回滚决策须由用户确认，不得由运维人员自行决定。**
> 若部署后发现异常，先按 §10.1 快速诊断，再决定是否执行回滚。

### §10.1 快速诊断

```bash
# 查看后端最近错误日志
sudo journalctl -u freeark-backend -n 50 --no-pager | grep -E "ERROR|Traceback|ImportError|OperationalError"

# 若有 OperationalError（DB 表不存在）：migrate 未完成或回滚了但代码已更新
# 若有 ImportError（模块找不到）：git pull 未完成
# 若有 TypeError（consumers.py 行为异常）：可能 chat_memory 初始化失败
```

### §10.2 代码回滚（回退到 ef3c509）

```bash
cd /home/yangyang/Freeark/FreeArk

# 回滚本期新增的后端文件到 reasoning_stream 部署后状态（ef3c509）
git checkout ef3c509 -- FreeArkWeb/backend/freearkweb/api/consumers.py
git checkout ef3c509 -- FreeArkWeb/backend/freearkweb/freearkweb/settings.py
# 注意：以下为本期新增文件，回滚时从工作树删除（或保留但不注册到 urls.py）
# 若决定完全回滚，可删除：
#   FreeArkWeb/backend/freearkweb/api/chat_memory.py
#   FreeArkWeb/backend/freearkweb/api/memory_views.py
# 以及从 urls.py 中移除 memory 端点注册

# 若 models.py 有问题（如 ORM 初始化失败导致无法启动）：
git checkout ef3c509 -- FreeArkWeb/backend/freearkweb/api/models.py
```

**注意**：代码回滚到 ef3c509 后，若 migration 0025 已应用（chat_session / chat_message 表已存在），Django ORM 不会主动报错，但这两个表将不再被代码使用（孤立表）。可保留孤立表（不影响运行），或单独执行 migration 回滚（见 §10.3）。

### §10.3 migration 回滚（若需要删除 chat_session / chat_message 表）

> **警告**：migration 回滚会删除 api_chat_session 和 api_chat_message 表及其中的所有数据。仅在用户明确要求清除数据的情况下执行。

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb

/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0024_plcwriterecord_batch_request_id

# 验证表已删除
echo "SHOW TABLES LIKE 'api_chat_%';" | /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py dbshell
# 预期：Empty set
```

### §10.4 skeleton_guard unlock（若 chattr +i 已执行）

```bash
bash /home/yangyang/Freeark/FreeArk/scripts/skeleton_guard.sh unlock
```

### §10.5 服务回滚重启

代码回滚后重启 freeark-backend：

```bash
sudo systemctl restart freeark-backend
sleep 5
systemctl status freeark-backend --no-pager | grep Active
curl -s http://127.0.0.1:8080/api/health/
# 预期：active (running)，{"status":"ok",...}
```

### §10.6 回滚后状态

代码回滚到 ef3c509 + migration 回滚到 0024 后，系统恢复到：
- consumers.py v1.2（无 chat_memory 集成）
- 无 chat_session / chat_message 表
- reasoning_stream 功能完整（reasoning_token / reasoning_end 正常工作）
- 无记忆隔离功能

---

## §11 部署时间估算

| 步骤 | 估算时间 | 备注 |
|------|---------|------|
| §1 前置条件检查 | 5-10 分钟 | 手动核对所有检查项 |
| §3.1 MySQL 备份 | 3-8 分钟 | 视数据量，freeark 库通常较小 |
| §3.2 migrate dry-run | < 1 分钟 | |
| §3.3 实际 migrate | < 1 分钟 | 仅创建 2 个新表，速度快 |
| §3.4 migrate 验证 | 2-3 分钟 | 4 条验证查询 |
| §4 git pull + 落地验证 | 2-3 分钟 | 网络良好时拉取快 |
| §5 服务重启 + 健康检查 | 2-3 分钟 | 含等待启动和基础验证 |
| §8 部署后验证清单 | 10-15 分钟 | 含 WS 功能验证、DB 写入验证、隔离验证 |
| §9 reasoning_stream 悬置项验证 | 5-10 分钟 | 与 §8.2 部分重叠，可合并 |
| **合计（代码部署 + 验证）** | **约 30-50 分钟** | 不含 skeleton lock 和 USER.md 通用化 |
| §6 skeleton_guard lock（独立操作） | 5-10 分钟 | 含 init + lock + verify |
| §7 USER.md 通用化（若执行） | 10-15 分钟 | 含内容确认 + 编辑 + 重新 init + lock |
| **合计（含所有独立 CONFIRM 操作）** | **约 45-75 分钟** | |
