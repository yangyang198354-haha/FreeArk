# Project Profile — FreeArk

> 本文件是 SDLC 套件在 FreeArk 仓库中的项目画像（模板见 `templates/project_profile.template.md`）。
> 事实来源：`CLAUDE.md`、`.claude/skills/freeark-prod-deploy/SKILL.md`、`.claude/skills/test-runner/SKILL.md`。两处冲突时以 skill 和实际仓库为准，并修正本文件。
> 本文件不含任何密码、令牌、私钥。

<file_header>
  <author_agent>human</author_agent>
  <timestamp>2026-10-22T16:51:47+08:00</timestamp>
  <project_name>FreeArk</project_name>
  <version>1.0.0</version>
  <status>APPROVED</status>
</file_header>

## P1. 项目概况
- 智能建筑/物业管理平台：Web 管理后台、微信小程序业主端、PLC 数据采集、AI 聊天助手。
- 技术栈：
  | 层 | 技术 |
  |---|---|
  | Web 后端 | Django + DRF（Python 3.12），Channels（WebSocket）；生产由 **Uvicorn ASGI**（`freearkweb.asgi:application`，:8000，`--workers 1`，InMemoryChannelLayer 不支持多进程）运行（CLAUDE.md 写的 Waitress/Gunicorn 已过时，以 deploy skill 为准） |
  | Web 前端 | Vue 3 + Vite + Element Plus |
  | 小程序 | uni-app（Vue 3） |
  | 数据采集 | Python（paho-mqtt、snap7） |
  | AI 聊天 | LangGraph + DeepSeek（进程内直连）；`langchain-openai` pin `<0.3` |
  | 数据库 | 生产 MySQL；测试 SQLite 内存库 |
  | 运行环境 | 树莓派 5（aarch64，Debian 13，4GB），systemd + Nginx + venv |
- 权威说明：`CLAUDE.md`

## P2. 文档工作区
- `docs_root`: `project_workspace/{project_name}/`
- `docs_layout`: nested
- 是否入库: 否（`project_workspace/` 已在 .gitignore）

## P3. 代码布局
- `code_mode`: in-repo
- 代码目录：
  | 组件 | 目录 |
  |---|---|
  | Django 后端（主应用 `api/`） | `FreeArkWeb/backend/freearkweb/` |
  | Vue 3 Web 前端 | `FreeArkWeb/frontend/` |
  | uni-app 小程序 | `miniprogram/` |
  | 数据采集（MQTT/PLC） | `datacollection/` |
  | 巡检 Agent | `FreeArkWeb/backend/freearkweb/inspection_agent/` |
- 测试位置约定：
  | 组件 | 新测试放在 | 框架 |
  |---|---|---|
  | 后端 | `FreeArkWeb/backend/freearkweb/api/tests/test_{功能}.py`（根目录 `api/tests_*.py` 是旧文件，不再新增） | Django test runner；`django.test.TestCase` / DRF `APITestCase`；类上加 `@tag('unit'|'integration'|'e2e')` |
  | 数据采集 | `datacollection/tests/` | pytest |
  | 前端 | `*.spec.*` | vitest |
- 不可修改：`agents/langgraph-poc/`（PoC，非生产）除非需求明确涉及。

## P4. 命令（严禁连接生产数据库）
| 用途 | 工作目录 | 命令 |
|---|---|---|
| 环境变量 | — | `FREEARK_POC_MOCK=1`（离线导入必需），`PYTHONUTF8=1` |
| 检查 | `FreeArkWeb/backend/freearkweb` | `FREEARK_POC_MOCK=1 python manage.py check --settings=freearkweb.test_settings` |
| 迁移一致性（只读） | 同上 | `FREEARK_POC_MOCK=1 python manage.py makemigrations api --check --dry-run --settings=freearkweb.test_settings`（存在既有漂移，只确认差异不含本次字段） |
| 单元 / 集成 / E2E | 同上 | `FREEARK_POC_MOCK=1 python manage.py test api --tag=unit|integration|e2e --settings=freearkweb.test_settings` |
| 指定模块 | 同上 | `FREEARK_POC_MOCK=1 python manage.py test api.tests.<模块> --settings=freearkweb.test_settings -v 2` |
| 全量回归 | 同上 | `FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings`（约 2–5 分钟） |
| 数据采集 | `datacollection` | `python -m pytest tests/ -v` |
| 前端构建 / 测试 | `FreeArkWeb/frontend` | `npm run build` / vitest（node_modules 不存在则记为未验证） |
- 已知既有失败与分层标准：`.claude/skills/test-runner/SKILL.md`（以实跑为准）。本地缺 `mysqlclient` 时 import MySQL 模块的测试报 `No module named 'MySQLdb'`，属环境失败。
- 不要用 git worktree 做对照实验（`.env` 差异导致假阳性，见 test-runner skill）。

## P5. 质量判定
- INCREMENTAL（日常）：`gate_mode` baseline — 相对基线零新增失败，新写用例全部通过，critical_path 1.00。
- FULL_FLOW（新子系统）：`gate_mode` threshold — unit_pass 0.80 / integration_pass 0.90 / critical_path 1.00；同时要求全量回归零新增失败。
- `inferred_max`: 0.20

## P6. 开发约定
- **迁移**：手写 scoped 迁移，放 `api/migrations/`，编号接续最新，`dependencies` 指向最新；**禁止** `makemigrations` 全量产物（存在迁移漂移）；已应用到生产的迁移不得修改；字段重命名用 `RenameField`。
- **鉴权**：Admin 判断 `User.role == 'admin'`（不是 `is_staff`），视图用 `api.views.IsAdminUser`；三角色 admin / operator / user（业主）；小程序 `/api/miniapp/` + `api.views.IsOwnerUser`；全局 `api.middleware.UserRoleApiGuardMiddleware` 拦截 user 角色访问非小程序接口。
- **改动范围**：修改既有文件做最小改动，不得顺手重写/压缩无关代码；"只改样式"类改动要用方法名集合对比核验。
- **搜索**：全仓内容核验用 `git grep`（ripgrep 遵守 .gitignore 会漏扫强制跟踪的文件）。
- 凭据只从 `.env` / 配置读取。

## P7. 环境、CI 与部署
- 环境：
  | 环境 | 存在 | 访问方式 | 部署需用户确认 |
  |---|---|---|---|
  | 本地/开发机 | 是 | — | 否 |
  | staging | **否** | — | — |
  | production | 是 | `ssh -p 57279 yangyang@47.109.197.217`（阿里云 VPS + frp，密钥认证）；内网 192.168.31.51；Web `https://ai-freeark.xin` | **是** |
- 花生壳通道 `et116374mm892.vicp.fun` 已退役，禁止引用。
- 生产仓库：`/home/yangyang/Freeark/FreeArk/`，venv `venv/bin/python`；生产 MySQL `192.168.31.98:3306` 库 `freeark`，凭据仅在生产 `.env` 中。
- 部署方式：生产机 `git pull origin main` + 必要时 `manage.py migrate` / `npm run build` + `sudo systemctl restart <具体服务>`。
- 允许的部署策略：**recreate**（单机直接替换重启）。无蓝绿/金丝雀/滚动条件。
- 构建产物管理：无制品库；前端在生产机本地 `npm run build`。
- 运行单元与重启矩阵：以 deploy skill §3/§6 为准（如改 `api/fault_consumer/` → `freeark-fault-consumer`；只改 API 视图 → `freeark-backend`；改前端 → `npm run build`）。服务清单以生产 `systemctl list-units 'freeark*'` 为准。
- **目标机必须保留的本地状态**：生产工作树对已跟踪文件有本地修改 `FreeArkWeb/backend/.env`、`FreeArkWeb/frontend/package-lock.json`、`FreeArkWeb/backend/heartbeat_broker_config.json`。pull 前 `git diff --name-only HEAD origin/main` 不得触碰它们。
- 回滚偏好：开发机 `git revert` + push → 生产 `git pull --ff-only` → 重启；紧急止血才用 `git checkout <锚点> -- <修改过的文件>`，且必须写收尾步骤（见 devops 项目知识）。
- 部署后验证：`systemctl is-active <服务>`；`journalctl -u <服务>` 无新 ERROR；`https://ai-freeark.xin` 可达；新功能冒烟请求。
- CI：`.github/workflows/ci.yml`（后端全量 / datacollection pytest / 前端 vitest+build；`.claude/**` 与文档变更不触发）。基线有既有失败时 CI 会红，判断回归要对比基线。
- 部署相关配置文件：`systemctl/`（systemd unit 定义）、`.github/workflows/ci.yml`。

## P8. 禁用项
| 禁用 | 原因 |
|---|---|
| Docker / docker-compose / Kubernetes / 任何容器化 | 项目约定物理机直接部署 |
| pscp / scp 逐文件上传部署 | 只允许 git pull |
| 生产机 `git stash` | 会藏起生产本地配置导致服务起不来 |
| 生产机 `git reset --hard` | 冲掉已跟踪文件的生产本地修改 |
| 生产机随手 `npm install` | 会改生产 `package-lock.json`；仅 package.json 变化且人工确认后 |
| 测试连接生产数据库 / 生产服务 | 安全红线 |
| `makemigrations` 全量产物 | 迁移漂移 |
| 设计 staging 或多环境晋升 | 不存在该环境 |

## P9. 版本控制与远程操作权限
- 直接提交到 `main`，不开分支/PR。
- commit / push 由主会话在用户确认后执行；子代理不执行。
- 子代理不 ssh；E2 经用户本轮授权后，devops 执行的每条 ssh 仍会触发用户权限确认（`.claude/settings.json` 中 ssh/scp/git push 为 ask，docker 为 deny）。

## P10. 额外必读
| Agent | 额外文件 |
|---|---|
| test-engineer | `.claude/skills/test-runner/SKILL.md` |
| devops-engineer | `.claude/skills/freeark-prod-deploy/SKILL.md`、`.github/workflows/ci.yml` |
| system-architect | `CLAUDE.md` |
| requirement-analyst | `CLAUDE.md` |
