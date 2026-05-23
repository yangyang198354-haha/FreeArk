---
name: freeark-prod-deploy
description: FreeArk 生产环境部署参考手册。当需要部署 FreeArk 到生产（树莓派）、SSH 连接生产服务器、重启/排查 systemd 服务、构建前端、连接或查询生产数据库、或排查生产部署问题时使用。包含访问方式、目录结构、服务清单（含 OpenClaw Gateway）、ASGI/WebSocket 架构、构建与重启流程、操作注意事项。本文件不含任何密码。
---

# FreeArk 生产环境部署手册

> **信息快照：2026-05-23（OpenClaw 集成 + ASGI 迁移后）。** 带 ⚠️ 的项为易变 / 用前需实测复核。
> **本文件不含任何密码。** SSH 用密钥认证（见 §10）；数据库凭据在 `settings.py`、用 `dbshell` 间接使用；OpenClaw token 存于 Pi 上 `~/.openclaw_gateway_token` (mode 600)。
> 本手册给"怎么做"，但每次部署仍须先实测"当前是什么样"（生产工作树状态、服务状态、本次拉取涉及的文件）。

## 何时用本 skill
部署 FreeArk 到生产、SSH 连生产树莓派、重启 systemd 服务、构建前端、连生产数据库、排查生产部署或 OpenClaw 聊天链路问题时。

---

## 1. 生产环境基本信息

| 项 | 值 |
|---|---|
| 生产服务器 | 树莓派 Raspberry Pi 5（aarch64），hostname `raspberrypi`，4GB RAM |
| OS | Debian 13 (trixie) |
| 内网地址 | `192.168.31.51`（wlan0；eth0 上还有多个内部 VLAN IP） |
| 外网访问 | 动态域名 `et116374mm892.vicp.fun`（经路由器端口映射）|
| SSH 端口 | 外网 `57279`（映射到内网 22）|
| SSH 用户 | `yangyang` |
| SSH 认证 | SSH 密钥（见 §10）。**本文件不存密码。** |
| sudo | 免密（NOPASSWD）|
| 部署纪律 | 一律 `ssh`/`plink` + `git pull`；**禁止 pscp 逐文件上传**；**禁止 Docker** |
| Python | 3.13.x（venv 在 `/home/yangyang/Freeark/FreeArk/venv`）|
| Node.js | **22.22.2**（NodeSource APT 系统级安装；2026-05-23 OpenClaw 集成时从 20.x 升级）|
| Web 后端 | **Uvicorn ASGI**（端口 :8000，PID 见 `systemctl show -p MainPID freeark-backend`）|
| 反向代理 | Nginx :8080 |
| 生产数据库 | MySQL 9.4.0 @ `192.168.31.98:3306`，库名 `freeark` |
| AI 服务 | **OpenClaw 2026.5.20**（systemd 用户服务 `openclaw-gateway.service`），绑 `127.0.0.1:18789`，对接 DeepSeek v4-flash |

**连接方式（SSH 密钥配置好后，见 §10）：**
- OpenSSH（Windows 自带）：`ssh -p 57279 yangyang@et116374mm892.vicp.fun`
- plink（PuTTY）：`plink -ssh -P 57279 yangyang@et116374mm892.vicp.fun "<远程命令>"`
- ⚠️ 在 Claude Code 里调用 plink/ssh 请用 **Bash 工具**，不要用 PowerShell（原因见 §9）。

---

## 2. 目录结构

仓库根：`/home/yangyang/Freeark/FreeArk/`（git 仓库，分支 `main`，远程 GitHub）

| 路径 | 说明 |
|---|---|
| `FreeArkWeb/backend/freearkweb/` | Django 后端根，`manage.py` 在此 |
| `FreeArkWeb/backend/freearkweb/freearkweb/` | Django 项目配置（`settings.py`、`asgi.py`、`wsgi.py`）|
| `FreeArkWeb/backend/freearkweb/freearkweb/asgi.py` | **ProtocolTypeRouter** (http→Django, ws→Channels) — uvicorn 入口 |
| `FreeArkWeb/backend/freearkweb/api/` | 主应用（models / views / management commands）|
| `FreeArkWeb/backend/freearkweb/api/consumers.py` | ChatConsumer（WS 聊天） |
| `FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py` | OpenClaw 适配层（aiohttp WS RPC v4 客户端） |
| `FreeArkWeb/backend/freearkweb/api/routing.py` | Django Channels WebSocket URL 路由 |
| `FreeArkWeb/backend/.env` | 生产专属环境配置（DB/ALLOWED_HOSTS/`OPENCLAW_GATEWAY_TOKEN`/...，**不入仓**）|
| `FreeArkWeb/frontend/` | Vue3 + Vite 前端；`dist/` 为构建产物 |
| `FreeArkWeb/frontend/src/views/ChatView.vue` | 「和方舟龙虾聊天」页面 |
| `datacollection/` | PLC 数据采集（`run_task_scheduler.py`）|
| `venv/` | Python 虚拟环境；解释器 `venv/bin/python` |
| `systemctl/` | systemd unit 文件的**仓库副本（源文件）** |
| `logs/` | 应用日志（见 §8）|
| `docs/` | 项目文档 |
| `~/.openclaw/openclaw.json` | OpenClaw 配置（plaintext token、模型、bind=loopback）|
| `~/.openclaw_gateway_token` | Gateway Bearer token（64 字符随机，mode 600；FreeArk `.env` 引用其值）|
| `/home/yangyang/FreeArk_backup/` | 部署期备份目录（dist/service/nginx）|

⚠️ **生产工作树长期存在本地修改**，`git pull` 前必须确认本次拉取不触碰它们：
- `FreeArkWeb/backend/.env` — 生产专属环境配置（含 `OPENCLAW_GATEWAY_TOKEN`、DB 凭据、`ALLOWED_HOSTS` 等）
- `FreeArkWeb/frontend/package-lock.json` — 生产 ARM 依赖树
- `FreeArkWeb/backend/heartbeat_broker_config.json` — 心跳服务 broker（wss/mqtt）配置

---

## 3. systemd 服务清单

unit 文件部署于 `/etc/systemd/system/`；仓库 `systemctl/` 目录是**源副本**。
全部 `User=yangyang`、`WorkingDirectory=/home/yangyang/Freeark/FreeArk/`、`Restart=on-failure`。

| 服务 | 作用 | 入口 |
|---|---|---|
| `freeark-backend` | **Django Web (Uvicorn ASGI, :8000)** | `uvicorn freearkweb.asgi:application --app-dir FreeArkWeb/backend/freearkweb --workers 1` |
| `freeark-mqtt-consumer` | MQTT 消费 | `manage.py mqtt_consumer_service` |
| `freeark-plc-connection-monitor` | PLC 连接状态监控 | `manage.py plc_connection_monitor` |
| `freeark-plc-cleanup` | plc_data 清理（每周日 02:00）| `manage.py plc_data_clean_up_service` |
| `freeark-dph-cleanup` | device_param_history 清理（每天 03:00）| `manage.py dph_cleanup_service` |
| `freeark-screen-heartbeat` | 屏幕心跳消费（mqtt/wss 双协议）| `manage.py screen_heartbeat_consumer` |
| `freeark-daily-usage` | 日用量统计 | `manage.py daily_usage_service` |
| `freeark-monthly-usage` | 月用量统计 | `manage.py monthly_usage_service` |
| `freeark-task-scheduler` | 任务调度 | `datacollection/run_task_scheduler.py` |
| **`openclaw-gateway.service`** | **OpenClaw Gateway**（systemd **用户服务**，lingering 已启用）| `node /usr/lib/node_modules/openclaw/dist/index.js gateway --port 18789` |

> 💡 **scheduled 服务的 inactive 是正常的**：`freeark-dph-cleanup`、`freeark-plc-cleanup` 等定时类服务在非执行时段 `is-active` 返回 `inactive`（dead），属正常状态。

**常用命令：**
```bash
systemctl status <svc> --no-pager              # 系统服务
sudo systemctl restart <svc>                   # 重启系统服务
sudo journalctl -u <svc> -n 50 --no-pager      # 看系统服务日志

# OpenClaw Gateway 是 **用户服务**：
systemctl --user status openclaw-gateway.service --no-pager
systemctl --user restart openclaw-gateway.service
journalctl --user -u openclaw-gateway.service -n 50 --no-pager
# 或直接看 OpenClaw 日志文件：/tmp/openclaw-1000/openclaw-YYYY-MM-DD.log

systemctl list-units 'freeark*' --no-pager     # 全部 freeark 服务一览
```

> 注：服务器上还有一个 GitHub Actions self-hosted runner（`actions.runner.*`）。当前生产部署实践为**手动 `git pull`**，不依赖该 runner 自动部署。

---

## 4. Web 架构与访问链路

```
浏览器 → nginx(:8080) ┬→ /             静态文件 FreeArkWeb/frontend/dist/ (Vue SPA)
                      ├→ /api          反代 → http://192.168.31.51:8000  (Django, Uvicorn ASGI)
                      ├→ /ws/chat/     反代 → ws://127.0.0.1:8000        (Channels ChatConsumer)
                      │                              ↓
                      │                       ChatConsumer.receive
                      │                              ↓ aiohttp WS RPC v4
                      │                       OpenClaw Gateway (127.0.0.1:18789, loopback)
                      │                              ↓ HTTPS
                      │                       DeepSeek v4-flash (公网 LLM)
                      └→ /mqtt-ws      反代 → http://192.168.31.98:32797/mqtt (现有 MQTT WS)
```

**关键文件**：
- nginx 站点配置：`/etc/nginx/sites-enabled/freeark`（监听 `:8080`，server_name `et116374mm892.vicp.fun 192.168.31.51`）
- Nginx `/ws/` 块要求 `proxy_http_version 1.1` + `Upgrade $http_upgrade` + `Connection "upgrade"` + `proxy_read_timeout 600s`（聊天可能很久）
- Django ASGI 入口：`freearkweb.asgi:application`（ProtocolTypeRouter；`http` → Django，`websocket` → AllowedHostsOriginValidator + URLRouter）
- Uvicorn 启动参数：`--host 0.0.0.0 --port 8000 --workers 1 --app-dir /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb`
  - **必须 `--workers 1`**：当前用 `InMemoryChannelLayer`，多 worker 间不共享 channel 状态
- venv 必装：`channels uvicorn[standard] aiohttp wsproto`（uvicorn 不带 `[standard]` 时缺 WebSocket 后端会出 `Unsupported upgrade request`）

⚠️ **`sites-enabled/` 内还有 `default` 与 `freeark.bak.150500`**，`nginx -t` 会报 `conflicting server name` warning（非错误）；必要时清理。

⚠️ 外网 Web 访问端口经路由器端口映射，**具体外网端口本手册未记录**——需查路由器映射表或问运维。外网经 frp 透传 WebSocket 的连通性 **待实测**（RISK-007）。

### 4.1 ASGI 关键配置（OpenClaw 集成后强制）

`.env` 必含字段（其他略）：
```
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,192.168.31.51,192.168.31.52,et116374mm892.vicp.fun
# ↑ 必须含 192.168.31.51（Pi 自身 IP）和外网域名；否则 AllowedHostsOriginValidator 会 403 拒绝 WS Origin
OPENCLAW_BASE_URL=http://127.0.0.1:18789
OPENCLAW_GATEWAY_TOKEN=<从 ~/.openclaw_gateway_token 取得，绝不入仓>
OPENCLAW_TIMEOUT=60
OPENCLAW_CONNECT_TIMEOUT=10
```

`settings.py` 必含：`'channels'` 在 INSTALLED_APPS；`CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}`。

⚠️ 已知坑：**ALLOWED_HOSTS 不含 `192.168.31.51` 时，WS 连接会被 `AllowedHostsOriginValidator` 拒（HTTP 403）**——这是 2026-05-23 部署期实测发现的，因为 .env 旧值（`192.168.31.52`）漏了 Pi 实际 IP。HTTP 请求受影响较小因 Nginx 改写了 Host。

---

## 5. 标准部署流程（后端 / 服务 / 文档变更）

1. **本地提交并推送**到 `main`：`git push origin main`。
   - ⚠️ PowerShell 5.1 下 `git commit -m` 若消息含中文、双引号或 `$()` 会被错误拆分。改用 `git commit -F <消息文件>`，或用 Bash 工具提交。
2. **核对拉取范围**：本地 `git diff --name-only <生产当前HEAD> <新HEAD>`，确认不含 `.env` / `package-lock.json` / `heartbeat_broker_config.json`。
3. **生产拉取**：`cd /home/yangyang/Freeark/FreeArk && git pull origin main`（应为 fast-forward）。
4. **验证代码落地**：`grep` 关键改动确认已到生产文件；`git log -1 --oneline` 确认 HEAD。
5. **若引入新 Python 依赖**：`venv/bin/pip install -r FreeArkWeb/backend/requirements.txt`（一定要走 venv 而非系统 pip）。
6. **重启受影响服务**（见 §6）。
7. **验证**：服务 `active (running)`，`journalctl` 无异常堆栈；对 Web 改动可 `curl http://127.0.0.1:8080/api/health/` 应得 `{"status":"ok",...}`。

---

## 6. 什么改动重启什么

| 改动内容 | 操作 |
|---|---|
| 后端通用 Python 代码（`api/` 等被多处引用的代码）| 重启 `freeark-backend` + 用到该代码的 worker 服务 |
| 某个 management command 自身代码（如 `dph_cleanup_service.py`）| 只重启对应的那个服务 |
| `settings.py` / `asgi.py` / `routing.py` / `consumers.py` / `openclaw_adapter.py` | 重启 `freeark-backend`（ASGI 入口和 WS 路由变更）|
| `.env`（任一 OPENCLAW_*、ALLOWED_HOSTS 等）| 重启 `freeark-backend` + 全部 worker 服务（均加载 .env）|
| systemd unit 文件（`systemctl/*.service`）| `sudo cp systemctl/<unit> /etc/systemd/system/` → `sudo systemctl daemon-reload` → `sudo systemctl restart <svc>` |
| 前端代码 | 见 §7（重新构建 `dist/`，无需 reload nginx；如需保险 `sudo systemctl reload nginx`）|
| nginx 配置 | 改 `/etc/nginx/sites-enabled/freeark` → `sudo nginx -t` → `sudo systemctl reload nginx`（不要 restart，避免短停顿）|
| OpenClaw 配置（`~/.openclaw/openclaw.json` 或 `~/.openclaw_gateway_token`）| `systemctl --user restart openclaw-gateway.service`（用户服务，**不要** sudo）|
| 纯文档 / 测试 | 无需重启 |

> **关键坑 1**：仓库 `systemctl/` 里的 unit 文件只是源副本。`git pull` **不会**更新正在运行的 systemd——必须手动 `cp` 到 `/etc/systemd/system/` 并 `daemon-reload`。
>
> **关键坑 2**：`freeark-backend` 是 Uvicorn ASGI（不是 waitress）；`start_waitress_server.py` 仅作回滚备用，正常部署不再用。

---

## 7. 前端构建与部署

前端 = Vue3 + Vite，源在 `FreeArkWeb/frontend/`。

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend
# （可选）依赖变化时：npm install   ——注意生产 package-lock.json 有本地修改
cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S)
npm run build                                   # = vite build，产物输出到 dist/
```

nginx 直接服务 `dist/` 静态文件，构建完成即生效；如需保险可 `sudo systemctl reload nginx`。

---

## 8. 数据库与日志

**数据库**
- MySQL 9.4.0 @ `192.168.31.98:3306`，库 `freeark`。连接配置在 Django `settings.py` 的 `MYSQL_DATABASE`。
- 在生产查库（复用 `settings.py` 凭据，无需手填密码）：
  ```bash
  echo "SHOW VARIABLES LIKE 'innodb%';" | venv/bin/python FreeArkWeb/backend/freearkweb/manage.py dbshell
  ```
- ⚠️ `settings.py` 连接 `OPTIONS` 设了 `read_timeout/write_timeout=60s`（mysqlclient 客户端 socket 超时）——长查询超 60s 会被客户端掐断并抛 `OperationalError(2013, 'Lost connection ... during query')`。维护类长任务须在进程内放大该超时（参考 `dph_cleanup_service.py` 的 `_apply_cleanup_db_timeout()`）。
- 大表删除务必分批（参考 `dph_cleanup_service` / `plc_data_clean_up_service`）。
- ⚠️ **聊天功能对 MySQL 零写入**：方舟龙虾的对话历史由 OpenClaw 内部按 `sessionKey` 维护，FreeArk 后端无状态、不落库。

**日志**
- systemd 服务输出 → journald：`sudo journalctl -u <svc>`
- OpenClaw 日志（用户服务）：`journalctl --user -u openclaw-gateway.service` 或 `/tmp/openclaw-1000/openclaw-YYYY-MM-DD.log`
- 应用文件日志 → `/home/yangyang/Freeark/FreeArk/logs/`（如 `multi_thread_plc_handler.log`、`mqtt_client.log` 等）
- ⚠️ `logs/` 下部分日志体积很大（PLC handler 日志单文件上百 MB），排查时用 `tail` 不要 `cat`。

---

## 9. 操作注意事项 / 已知坑

- **用 Bash 工具调用 plink/ssh，不要用 PowerShell。** PowerShell 5.1 对双引号、`$()`、`&` 的原生命令传参有缺陷，会把命令拆错。
- **SSH 远端命令体用单引号包裹**：双引号下 `$VAR` 会在本地展开成空字符串。`ssh user@host 'echo $REMOTE_VAR'` 才能在远端展开。
- plink 首次连接新主机需缓存主机密钥；`-batch` 模式无法应答交互提示（密码 / 主机密钥确认）。
- 后台跑长任务：`nohup <cmd> </dev/null >日志文件 2>&1 &`。Python 命令加 `-u` 取消 stdout 缓冲，否则日志要等缓冲区满才落盘。
- `git pull` 前务必确认不会覆盖生产本地修改的 `.env` / `package-lock.json` / `heartbeat_broker_config.json`。
- 数据库写操作 / 生产部署属高风险操作——执行前应取得明确确认。
- 测试用 SQLite：`python manage.py test`（settings.py 检测到 test 自动切 SQLite，不连生产 DB）。集成测试涉及 sync_to_async 时必须用 `TransactionTestCase`，否则线程池连接看不到外层事务里 setUp 创建的对象。

### 9.1 Uvicorn / Channels 已知坑

- `pip install uvicorn` 装的是 base 版本，**缺 WebSocket 后端**。journald 出现 `Unsupported upgrade request` + `No supported WebSocket library detected` 时，安装 `uvicorn[standard]`（带 websockets/uvloop/httptools/watchfiles 等）即可。
- Channels 的 `AllowedHostsOriginValidator` 看的是请求的 **`Origin` 头**，不是 `Host`。浏览器 Origin = 协议+`server_name`+端口；只要 `ALLOWED_HOSTS` 缺哪一个就会 403。Python `websockets` 库默认不发 Origin，调试时显式传 `origin=` 参数。
- ASGI 启动日志 `ASGI 'lifespan' protocol appears unsupported.` 是无害的——Django 没实现 lifespan 协议，uvicorn 自动 fallback。

### 9.2 OpenClaw 已知坑

- 主协议是 **WebSocket Gateway + RPC v4**，**不是 HTTP REST**。社区文章常引用的 `/v1/agent/run/stream`、`/v1/chat/completions` 在 2026.5.20 全部 **404**。直接 curl 探测端点不要依赖那些路径。
- 握手必须先发 `req method:connect`（响应服务器 `event:connect.challenge`），再发 `chat.send`。`scopes` 至少含 `operator.write`；只传 `["*"]` 字面量**不**当通配，会被拒。
- `client.mode=backend` + `auth.token` + loopback URL 三条件同时满足时可省略 device ECDSA 签名（adapter v1.2 走的就是这条路径）。
- 流式 token 增量在 `event:chat` 帧的 `payload.deltaText`；`payload.state ∈ {delta, final, aborted, error}`。`event:agent`、`event:health`、`event:tick`、`event:heartbeat` 等其他事件忽略。
- OpenClaw 重装后 gateway token 会变，需要同步更新生产 `.env` 的 `OPENCLAW_GATEWAY_TOKEN`。
- 安装命令（一次性）：
  ```bash
  npm install -g openclaw@latest
  openclaw --no-color onboard \
    --accept-risk --non-interactive --flow quickstart \
    --auth-choice deepseek-api-key --deepseek-api-key '<DEEPSEEK_KEY>' \
    --gateway-bind loopback --gateway-port 18789 \
    --gateway-auth token --gateway-token '<RANDOM_64HEX>' \
    --skip-channels --skip-ui --skip-search --skip-hooks --skip-skills \
    --install-daemon --json
  ```
  注意：`--no-color` 是顶级 option，必须放 `onboard` 之前；`--skip-channels` 必填（否则 QuickStart 卡在 channel 选择交互）。

---

## 10. SSH 密钥认证设置

> ✅ **当前状态（2026-05-22）**：开发机 `~/.ssh/id_ed25519` 的公钥已安装到生产
> `~/.ssh/authorized_keys`，已验证免密登录可用：
> `ssh -p 57279 yangyang@et116374mm892.vicp.fun`（OpenSSH 自动使用默认密钥，无需 `-i`）。
> 下面的步骤仅供换新开发机 / 重装密钥时参考。

本手册约定 SSH 用**密钥**认证、不用密码。把公钥装到生产的步骤：

```bash
# 1. 本机生成密钥（若还没有）
ssh-keygen -t ed25519 -C "freeark-deploy"

# 2. 安装公钥到生产（此步需输入一次密码，之后即免密）
ssh -p 57279 yangyang@et116374mm892.vicp.fun "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys" < $env:USERPROFILE\.ssh\id_ed25519.pub
#  （Bash 环境用： ... < ~/.ssh/id_ed25519.pub ）

# 3. 之后免密连接
ssh -p 57279 yangyang@et116374mm892.vicp.fun
```

- plink 使用密钥：用 `puttygen` 把 `id_ed25519` 转成 `.ppk`，`plink -i <key.ppk>`；或用 pageant 加载密钥。
- ⚠️ 私钥仅存本机 `~/.ssh/`，**绝不提交进仓库**。

---

## 11. 方舟龙虾聊天链路排查清单

发生聊天异常时按顺序排查：

```bash
# 1. OpenClaw Gateway 是否在跑（loopback）
systemctl --user is-active openclaw-gateway.service
ss -tlnp | grep 18789                      # 应有 127.0.0.1:18789 LISTEN
curl -s http://127.0.0.1:18789/health      # 应返 {"ok":true,"status":"live"}

# 2. FreeArk backend 是 Uvicorn 且有 WebSocket 后端
systemctl status freeark-backend --no-pager | grep -E "uvicorn|Active"
sudo journalctl -u freeark-backend -n 20   # 不应见 "Unsupported upgrade request"

# 3. Nginx 含 /ws/ location
grep -A 2 "location /ws/" /etc/nginx/sites-enabled/freeark | head -3

# 4. ALLOWED_HOSTS 含 Pi 实际访问 IP / 域名
grep "^ALLOWED_HOSTS" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/.env

# 5. OPENCLAW_GATEWAY_TOKEN 在 .env，且与 ~/.openclaw_gateway_token 一致
# （不打印 token 值，仅比对前 8 字符校验）
[ "$(cut -c1-8 ~/.openclaw_gateway_token)" = "$(grep '^OPENCLAW_GATEWAY_TOKEN=' /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/.env | cut -d= -f2 | cut -c1-8)" ] && echo "TOKEN_MATCH" || echo "TOKEN_MISMATCH"

# 6. Django shell 中 import 适配层（验证依赖齐全）
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb &&
  /home/yangyang/Freeark/FreeArk/venv/bin/python -c "from api.openclaw_adapter import OpenClawAdapter; print('OK')"
```

---

## 附：维护说明

本手册信息采集于 **2026-05-23（OpenClaw 集成 + ASGI 迁移完成日）**。基础设施变更后请同步更新本文件。
易变项（服务启动参数、nginx 配置、外网端口映射、数据库表规模、OpenClaw 版本等）用前需实测复核——
切勿把过时数值当事实（历史教训：曾误把 `innodb_buffer_pool_chunk_size` 当成 `innodb_buffer_pool_size`，并长期沿用过时数值；曾基于社区文章假设 OpenClaw HTTP SSE 接口存在，实测全 404，浪费一轮架构设计）。
