---
name: freeark-prod-deploy
description: FreeArk 生产环境部署参考手册。当需要部署 FreeArk 到生产（树莓派）、SSH 连接生产服务器、重启/排查 systemd 服务、构建前端、连接或查询生产数据库、或排查生产部署问题时使用。包含访问方式、目录结构、服务清单（含 freeark-fault-consumer 故障事件写入服务）、ASGI/WebSocket 架构（聊天=进程内 LangGraph 直连 DeepSeek）、构建与重启流程、操作注意事项。本文件不含任何密码。
---

# FreeArk 生产环境部署手册

> **信息快照：2026-06-26（v1.7.0 退役 OpenClaw + v1.8.0 小程序业主端上线；聊天后端 = 进程内 LangGraph 直连 DeepSeek）。** 带 ⚠️ 的项为易变 / 用前需实测复核。
> ⚠️ **OpenClaw 已于 2026-06-26 从生产完全卸载**（停服+禁用+删 user unit+`npm uninstall -g openclaw`+清 `~/.openclaw`/token/`/tmp/openclaw-1000`+删 nginx control UI+删 `.env` 的 `OPENCLAW_*`）。聊天唯一路径 = `api/chat_backend.get_chat_adapter()` → `LangGraphAdapter`（进程内编排，直连 DeepSeek v4-flash）。本文凡涉 OpenClaw 的段落仅作历史存档。
> ⚠️ **perf-P1a（Redis Channel Layer + `--workers 2`）已回滚**：channels_redis 4.3.0 与 redis-py 8.0.0 不兼容（WS receive 触发 RESP3 读取超时），已退回 `InMemoryChannelLayer` + `--workers 1`。Redis 服务保留，**当前仅 perf-P2 缓存（db=1）在用，Channel Layer（db=0）已停用**。
> ⚠️ **外网访问改造中（2026-06-26 起）**：新增 **阿里云 VPS `47.109.197.217` + frp 隧道**作对外通道（web→VPS `:18080`、SSH→VPS `:57279`），比花生壳稳（不依赖会抽风的 vicp.fun 公司 DNS）。两条通道并存；Phase B（待 `ai-freeark.xin` ICP 备案）将切 443/HTTPS 并退役花生壳。详见 §1、§10。
> **本文件不含任何密码。** SSH 用密钥认证（见 §10）；数据库凭据在 `settings.py`、用 `dbshell` 间接使用。
> 本手册给"怎么做"，但每次部署仍须先实测"当前是什么样"（生产工作树状态、服务状态、本次拉取涉及的文件）。

## 何时用本 skill
部署 FreeArk 到生产、SSH 连生产树莓派、重启 systemd 服务、构建前端、连生产数据库、排查生产部署或 LangGraph 聊天链路问题时。

---

## 1. 生产环境基本信息

| 项 | 值 |
|---|---|
| 生产服务器 | 树莓派 Raspberry Pi 5（aarch64），hostname `raspberrypi`，4GB RAM |
| OS | Debian 13 (trixie) |
| 内网地址 | `192.168.31.51`（wlan0；eth0 上还有多个内部 VLAN IP） |
| 外网访问（推荐）| **阿里云 VPS `47.109.197.217` + frp 隧道**（2026-06-26 起）：web→VPS `:18080`、SSH→VPS `:57279`。目标域名 `ai-freeark.xin`（待 ICP 备案，Phase B 切 443/HTTPS）|
| 外网访问（旧）| 花生壳动态域名 `et116374mm892.vicp.fun`（中继 `43.228.71.225`）；Phase B 备案后退役 |
| SSH 端口 | 外网 `57279`（两条通道同此端口 → 内网 22）|
| SSH 用户 | `yangyang` |
| SSH 认证 | SSH 密钥（见 §10）。**本文件不存密码。** |
| sudo | 免密（NOPASSWD）|
| 部署纪律 | 一律 `ssh`/`plink` + `git pull`；**禁止 pscp 逐文件上传**；**禁止 Docker** |
| Python | 3.13.x（venv 在 `/home/yangyang/Freeark/FreeArk/venv`）|
| Node.js | **22.22.2**（NodeSource APT 系统级安装；2026-05-23 OpenClaw 集成时从 20.x 升级）|
| Web 后端 | **Uvicorn ASGI**（端口 :8000，PID 见 `systemctl show -p MainPID freeark-backend`）|
| 反向代理 | Nginx :8080 |
| 生产数据库 | MySQL 9.4.0 @ `192.168.31.98:3306`，库名 `freeark` |
| 聊天 AI | **进程内 LangGraph**（`api/langgraph_chat/`，无独立服务/端口），直连 DeepSeek v4-flash（`.env` 的 `DEEPSEEK_API_KEY`）。v1.7.0 起取代 OpenClaw |

**连接方式（SSH 密钥已配置，见 §10）。两条通道并存，优先用 VPS（更稳，不依赖会抽风的 vicp.fun 公司 DNS）：**
- ✅ **VPS+frp 隧道（推荐，2026-06-26 起）**：`ssh -p 57279 yangyang@47.109.197.217`
  - 路径：开发机 → 阿里云 VPS `47.109.197.217:57279` → frp 隧道 → 树莓派 sshd:22。
  - 与花生壳那条的 known_hosts 指纹冲突时加 `-o HostKeyAlias=et116374mm892.vicp.fun`（同一台 Pi，复用 key）。
- **花生壳（旧，仍可用，Phase B 退役）**：`ssh -p 57279 yangyang@et116374mm892.vicp.fun`
  - ⚠️ 公司 DNS 偶发解析不了 vicp.fun：用 `nslookup et116374mm892.vicp.fun 8.8.8.8` 取中继 IP（`43.228.71.225`）+ `-o HostKeyAlias=et116374mm892.vicp.fun` 直连。
- plink（PuTTY）：把上面的 host 套进 `plink -ssh -P 57279 yangyang@<host> "<远程命令>"`。
- ⚠️ 在 Claude Code 里调用 plink/ssh 请用 **Bash 工具**，不要用 PowerShell（原因见 §9）。
- **隧道不通时排查**：连 VPS 自身用 `ssh root@47.109.197.217`（开发机公钥已装），看 `systemctl status frps`；Pi 上看 `systemctl status frpc`（检查 frpc 需先经花生壳通道连入）。frp 0.61.1 装在 `/usr/local/frp/`，配置 `*.toml`（**token 不在本文件**）。

---

## 2. 目录结构

仓库根：`/home/yangyang/Freeark/FreeArk/`（git 仓库，分支 `main`，远程 GitHub）

| 路径 | 说明 |
|---|---|
| `FreeArkWeb/backend/freearkweb/` | Django 后端根，`manage.py` 在此 |
| `FreeArkWeb/backend/freearkweb/freearkweb/` | Django 项目配置（`settings.py`、`asgi.py`、`wsgi.py`）|
| `FreeArkWeb/backend/freearkweb/freearkweb/asgi.py` | **ProtocolTypeRouter** (http→Django, ws→Channels) — uvicorn 入口 |
| `FreeArkWeb/backend/freearkweb/api/` | 主应用（models / views / management commands）|
| `FreeArkWeb/backend/freearkweb/api/consumers.py` | `ChatConsumer`（/ws/chat/，走 LangGraph）+ `MiniAppChatConsumer`（v1.8.0，/ws/miniapp/chat/，role=user 业主端，注入 UserScope 数据隔离） |
| `FreeArkWeb/backend/freearkweb/api/chat_backend.py` | 聊天后端工厂 `get_chat_adapter()` → `LangGraphAdapter`（OpenClaw 已退役，恒返回 LangGraph） |
| `FreeArkWeb/backend/freearkweb/api/langgraph_chat/` | LangGraph 编排（adapter / orchestrator / fa_tools / scope_enforcer / user_scope）；聊天唯一路径 |
| `FreeArkWeb/backend/freearkweb/api/routing.py` | Django Channels WebSocket URL 路由（/ws/chat/ + /ws/miniapp/chat/） |
| `FreeArkWeb/backend/freearkweb/api/fault_consumer/` | **故障事件消费模块**（state_machine.py 写入 fault_event 表、fault_classifier.py 生成 fault_message、constants.py 故障码字典等）— **修改后必须重启 `freeark-fault-consumer`** |
| `FreeArkWeb/backend/freearkweb/api/views_fault.py` / `serializers_fault.py` | 故障管理 REST API；改动重启 `freeark-backend` |
| `FreeArkWeb/backend/.env` | 生产专属环境配置（DB / ALLOWED_HOSTS / `DEEPSEEK_API_KEY` / 可选 `WECHAT_MINIAPP_APPID`+`WECHAT_MINIAPP_SECRET`...，**不入仓**）|
| `FreeArkWeb/frontend/` | Vue3 + Vite 前端；`dist/` 为构建产物 |
| `FreeArkWeb/frontend/src/views/ChatView.vue` | 「和方舟智能体聊天」页面 |
| `datacollection/` | PLC 数据采集（`run_task_scheduler.py`）|
| `venv/` | Python 虚拟环境；解释器 `venv/bin/python` |
| `systemctl/` | systemd unit 文件的**仓库副本（源文件）** |
| `logs/` | 应用日志（见 §8）|
| `docs/` | 项目文档 |
| `/home/yangyang/FreeArk_backup/` | 部署期备份目录（dist/service/nginx）|

⚠️ **生产工作树长期存在本地修改**，`git pull` 前必须确认本次拉取不触碰它们：
- `FreeArkWeb/backend/.env` — 生产专属环境配置（含 DB 凭据、`ALLOWED_HOSTS`、`DEEPSEEK_API_KEY` 等）
- `FreeArkWeb/frontend/package-lock.json` — 生产 ARM 依赖树
- `FreeArkWeb/backend/heartbeat_broker_config.json` — 心跳服务 broker（wss/mqtt）配置

---

## 3. systemd 服务清单

unit 文件部署于 `/etc/systemd/system/`；仓库 `systemctl/` 目录是**源副本**。
全部 `User=yangyang`、`WorkingDirectory=/home/yangyang/Freeark/FreeArk/`、`Restart=on-failure`。

| 服务 | 作用 | 入口 |
|---|---|---|
| `redis-server` | **Redis（127.0.0.1:6379）；当前仅缓存后端 db=1 在用**（db=0 Channel Layer 随 perf-P1a 回滚已停用）（apt 安装，开机自启）| apt 系统服务 |
| `freeark-backend` | **Django Web (Uvicorn ASGI, :8000)** | `uvicorn freearkweb.asgi:application --app-dir FreeArkWeb/backend/freearkweb --workers 1`（InMemoryChannelLayer 不支持多进程；perf-P1a 曾改 2，已回滚）|
| `freeark-mqtt-consumer` | 通用 MQTT 消费 | `manage.py mqtt_consumer_service` |
| **`freeark-fault-consumer`** | **故障事件 MQTT 消费 — fault_event 表的实际写入服务**（v0.6.0-FM 起）| `manage.py fault_consumer` |
| `freeark-plc-connection-monitor` | PLC 连接状态监控 | `manage.py plc_connection_monitor` |
| `freeark-plc-cleanup` | plc_data 清理（每周日 02:00）| `manage.py plc_data_clean_up_service` |
| `freeark-dph-cleanup` | device_param_history 清理（每天 03:00）| `manage.py dph_cleanup_service` |
| `freeark-screen-heartbeat` | 屏幕心跳消费（mqtt/wss 双协议）| `manage.py screen_heartbeat_consumer` |
| `freeark-daily-usage` | 日用量统计 | `manage.py daily_usage_service` |
| `freeark-monthly-usage` | 月用量统计 | `manage.py monthly_usage_service` |
| `freeark-task-scheduler` | 任务调度 | `datacollection/run_task_scheduler.py` |
| `freeark-fault-cleanup.timer` | fault_event 清理 timer（v0.6.0-FM 起） | systemd timer 单元 |

> 💡 **无独立聊天服务**：v1.7.0 退役 OpenClaw 后，聊天编排（LangGraph）在 `freeark-backend` 进程内完成，**没有** openclaw-gateway 之类的独立服务/端口需要看护。Pi 上仍保留 pipewire/pulseaudio/gnome-keyring 等系统用户服务（与 FreeArk 无关，linger 因它们而保留）。

> 💡 **scheduled 服务的 inactive 是正常的**：`freeark-dph-cleanup`、`freeark-plc-cleanup` 等定时类服务在非执行时段 `is-active` 返回 `inactive`（dead），属正常状态。

> ⚠️ **`freeark-fault-consumer` 与 `freeark-mqtt-consumer` 是两个独立服务**，不要混淆。fault_event 写入路径走的是 `freeark-fault-consumer`（由 `api/fault_consumer/state_machine.py` 的 `insert_fault_event` 落库）；通用 MQTT 走 `freeark-mqtt-consumer`。修改 `api/fault_consumer/` 下任何文件**必须**重启 `freeark-fault-consumer`，否则新故障事件用旧逻辑写入（v0.6.3 部署期实测的坑：只重启 backend+mqtt-consumer 后 fault_message 仍是英文，排查 MySQL processlist 才定位）。

**常用命令：**
```bash
systemctl status <svc> --no-pager              # 系统服务
sudo systemctl restart <svc>                   # 重启系统服务
sudo journalctl -u <svc> -n 50 --no-pager      # 看系统服务日志

systemctl list-units 'freeark*' --no-pager     # 全部 freeark 服务一览
```

> 注：服务器上还有一个 GitHub Actions self-hosted runner（`actions.runner.*`）。当前生产部署实践为**手动 `git pull`**，不依赖该 runner 自动部署。

---

## 4. Web 架构与访问链路

```
浏览器/小程序 → nginx(:8080) ┬→ /                 静态文件 FreeArkWeb/frontend/dist/ (Vue SPA)
                            ├→ /api              反代 → http://192.168.31.51:8000 (Django, Uvicorn ASGI)
                            ├→ /api/miniapp/     同上（v1.8.0 业主端命名空间 + IsOwnerUser）
                            ├→ /ws/chat/         反代 → ws://127.0.0.1:8000 (Channels ChatConsumer)
                            ├→ /ws/miniapp/chat/ 反代 → ws://127.0.0.1:8000 (MiniAppChatConsumer, v1.8.0 业主端 + UserScope 隔离)
                            │                              ↓
                            │                       ChatConsumer.receive → get_chat_adapter()
                            │                              ↓ 进程内调用（无外部服务/端口）
                            │                       LangGraphAdapter (api/langgraph_chat/, 编排 + 工具)
                            │                              ↓ HTTPS (langchain-openai)
                            │                       DeepSeek v4-flash (公网 LLM)
                            └→ /mqtt-ws          反代 → http://192.168.31.98:32797/mqtt (现有 MQTT WS)
```

**关键文件**：
- nginx 站点配置：`/etc/nginx/sites-enabled/freeark`（监听 `:8080`，server_name `et116374mm892.vicp.fun 192.168.31.51`）
- Nginx `/ws/` 块要求 `proxy_http_version 1.1` + `Upgrade $http_upgrade` + `Connection "upgrade"` + `proxy_read_timeout 600s`（聊天可能很久）
- Django ASGI 入口：`freearkweb.asgi:application`（ProtocolTypeRouter；`http` → Django，`websocket` → AllowedHostsOriginValidator + URLRouter）
- Uvicorn 启动参数：`--host 0.0.0.0 --port 8000 --workers 1 --app-dir /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb`
  - **`--workers 1` 必需**：`settings.py` CHANNEL_LAYERS 为 `InMemoryChannelLayer`，不支持多进程（多 worker 会导致 WS 消息跨进程丢失）。
  - **perf-P1a（2026-05-31）曾试 `--workers 2` + RedisChannelLayer 解串行瓶颈，已回滚**：channels_redis 4.3.0 与 redis-py 8.0.0 不兼容（WS receive 触发 RESP3 读取超时）。重试前置：requirements 固定 redis-py 5.x 并在装好 Redis 的环境本地验证 WS 收发后再上生产。
- venv 必装：`channels uvicorn[standard] aiohttp wsproto channels_redis`（channels_redis 4.x 对应 channels 4.x；依赖纯 Python redis 包，ARM64 无需编译）

⚠️ **`sites-enabled/` 内还有 `default` 与 `freeark.bak.150500`**，`nginx -t` 会报 `conflicting server name` warning（非错误）；必要时清理。

⚠️ 外网 Web 访问端口经路由器端口映射，**具体外网端口本手册未记录**——需查路由器映射表或问运维。外网经 frp 透传 WebSocket 的连通性 **待实测**（RISK-007）。

### 4.1 ASGI 关键配置（聊天 = 进程内 LangGraph）

`.env` 必含字段（其他略）：
```
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,192.168.31.51,192.168.31.52,et116374mm892.vicp.fun
# ↑ 必须含 192.168.31.51（Pi 自身 IP）和外网域名；否则 AllowedHostsOriginValidator 会 403 拒绝 WS Origin
DEEPSEEK_API_KEY=<DeepSeek API key，LangGraph 直连 LLM 用，绝不入仓>
# 可选（v1.8.0 微信一键登录用；缺失时账号密码注册/绑定/隔离仍可用，仅微信登录返回 503）：
# WECHAT_MINIAPP_APPID=<微信小程序 AppID>
# WECHAT_MINIAPP_SECRET=<微信小程序 AppSecret>
```
> ⚠️ v1.7.0 起 `OPENCLAW_*` 与 `settings.py` 的 `CHAT_BACKEND` 均为**死配置**——`api/chat_backend.get_chat_adapter()` 恒返回 `LangGraphAdapter`，不读这些 env（生产 .env 的 `OPENCLAW_*` 已于 2026-06-26 删除）。`settings.py:CHAT_BACKEND` 那行残留无害（无人读），日后可顺手清理。

`settings.py` 必含：`'channels'` 在 INSTALLED_APPS；`CHANNEL_LAYERS` **当前生产用 `channels.layers.InMemoryChannelLayer`**（perf-P1a 曾改 `channels_redis.core.RedisChannelLayer` db=0，已回滚，见 §顶部快照）；测试分支（`_RUNNING_TESTS`）同用 `InMemoryChannelLayer`（不依赖 Redis 服务）。

**perf-P2 新增（看板 Redis 缓存）**：`CACHES` 生产分支改为 `django.core.cache.backends.redis.RedisCache`（db=1，与 channels db=0 隔离）；测试分支仍 `DummyCache`，不依赖 Redis。
- LOCATION: `redis://127.0.0.1:6379/1`（db=1，避免与 channels db=0 冲突）
- KEY_PREFIX: `fa_cache`（便于 redis-cli 手工排查：`redis-cli -n 1 keys 'fa_cache*'`）
- TIMEOUT: 30s（看板数据 TTL，与 P0 LocMemCache 一致）
- OPTIONS: `socket_connect_timeout=1, socket_timeout=1`（防 Redis 慢响应拖垮 worker）
- **降级策略**：Django 内置 RedisCache 无 IGNORE_EXCEPTIONS；降级兜底在 `cache_dashboard` 装饰器的 try/except 层实现。Redis 不可用时：cache.get 失败→降级为直查，cache.set 失败→静默忽略，看板接口始终返回 HTTP 200，不会 500。
- **redis-py 版本**：requirements.txt 固定 `redis>=5.0,<6.0`（兼容 channels_redis 4.x；P1-a 雷区：redis-py 8.x 与 channels_redis 4.x 不兼容，已固定避免）。
- **回滚**：settings.py CACHES 生产分支改回 LocMemCache（LOCATION='freeark-dashboard-cache'）即可，1 行变更，Redis 服务不受影响。

**多 worker 退化行为（perf-P1a 重试参考；当前 `--workers 1`，以下不生效，仅供重试 P1a 时评估）**
- **看板缓存（现为 Redis db=1）**：Redis 是跨进程共享缓存，多 worker 下命中率与一致性不受 worker 数影响（与曾经的进程内 LocMemCache 不同——这是迁移 Redis 的收益之一）。
- **`_activity_cache` 节流字典**（api/authentication.py，仍为进程内 dict）：多 worker 下每 worker 各自维护，同一 token 的节流 DB UPDATE 最多变为 N-worker 倍（2 worker = 最多 2×/5min），**超时判定仍以 DB 的 TokenActivity.last_active_at 为权威，会话超时（v0.9.0）行为完全正确**。
- **后台服务进程内 dict**（mqtt_handlers / fault_consumer 等）：这些服务是独立 systemd 进程，不受 uvicorn worker 数影响，行为完全不变。

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
| 后端通用 Python 代码（`api/` 等被多处引用的代码）| 重启 `freeark-backend` + 用到该代码的 worker 服务（含 `freeark-fault-consumer`）|
| 某个 management command 自身代码（如 `dph_cleanup_service.py`）| 只重启对应的那个服务 |
| **`api/fault_consumer/` 下任意文件**（state_machine.py、fault_classifier.py、constants.py、handlers.py 等）| **必须重启 `freeark-fault-consumer`**（fault_event 写入路径）；若同时被 views_fault.py / serializers_fault.py import（如 constants.py），**还要重启 `freeark-backend`** |
| `api/views_fault.py` / `api/serializers_fault.py` / `api/views.py` 等 REST API 视图 | 重启 `freeark-backend` |
| `settings.py` / `asgi.py` / `routing.py` / `consumers.py` / `chat_backend.py` / `langgraph_chat/*` | 重启 `freeark-backend`（ASGI 入口、WS 路由、聊天编排变更）|
| `.env`（`ALLOWED_HOSTS` / `DEEPSEEK_API_KEY` / `WECHAT_MINIAPP_*` 等）| 重启 `freeark-backend` + 全部 worker 服务（均加载 .env）|
| systemd unit 文件（`systemctl/*.service`）| `sudo cp systemctl/<unit> /etc/systemd/system/` → `sudo systemctl daemon-reload` → `sudo systemctl restart <svc>` |
| 前端代码 | 见 §7（重新构建 `dist/`，无需 reload nginx；如需保险 `sudo systemctl reload nginx`）|
| nginx 配置 | 改 `/etc/nginx/sites-enabled/freeark` → `sudo nginx -t` → `sudo systemctl reload nginx`（不要 restart，避免短停顿）|
| 数据库迁移（新 migration）| `venv/bin/python FreeArkWeb/backend/freearkweb/manage.py migrate api`（生产 MySQL；先 `showmigrations` 确认 pending）→ 重启引用新模型的服务（通常 `freeark-backend`）|
| 纯文档 / 测试 | 无需重启 |

**故障管理改动重启路径速查**（v0.6.3 BUG-FM-008 部署期教训）：

| 改了哪 | 服务 |
|---|---|
| 只改 `views_fault.py` / `serializers_fault.py`（API 读路径） | `freeark-backend` |
| 只改 `fault_consumer/fault_classifier.py` / `state_machine.py`（写路径） | `freeark-fault-consumer` |
| 改了 `fault_consumer/constants.py`（被两路同时 import）| **`freeark-backend` + `freeark-fault-consumer`** 两者都重启 |

**生效验证 SQL**（确认 fault_message 写入逻辑生效）：
```sql
SELECT id, fault_code, fault_message, created_at
FROM fault_event
WHERE created_at > '<重启时间戳>'
ORDER BY id DESC LIMIT 10;
```
看新行的 `fault_message` 是否符合新逻辑（如 v0.6.3 应为中文）。

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
- ⚠️ **聊天历史落 MySQL**（v1.7.0 LangGraph 化后）：对话写入 `api_chat_session` / `api_chat_message`（旧手册"OpenClaw 零写入"说法已过时）。
- v1.8.0 新增两张表：`owner_user_binding`（业主账号多对多绑定）、`wechat_binding`（微信 openid↔User），迁移 0041。

**日志**
- systemd 服务输出 → journald：`sudo journalctl -u <svc>`
- 聊天/LangGraph 异常 → 看 `freeark-backend` journald：`sudo journalctl -u freeark-backend -n 50`
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

**Redis 相关坑（perf-P2 缓存后端在用；perf-P1a Channel Layer 已回滚，以下含 P1a 重试参考）：**

- **redis-server bind 配置**：默认 `/etc/redis/redis.conf` 的 `bind 127.0.0.1 -::1`，确认无 `0.0.0.0`（安全要求：Redis 只绑 loopback，不对外暴露）。
- **`freeark-backend.service` 的 `After=redis-server.service`（perf-P2 已加，弱依赖 `Wants`）**：确保 Redis 在 backend 前启动。Redis 不可用/延迟启动时，看板缓存由 `cache_dashboard` 装饰器、故障数量缓存由 `fault_utils._safe_cache_*` 降级直查 DB（不会 500，日志记 WARNING）。
- **redis-py 版本约束（perf-P2）**：`requirements.txt` 固定 `redis>=5.0,<6.0`。channels_redis 4.x 实测需 redis-py 5.x；redis-py 8.x 不兼容（正是 P1a 回滚主因）。即使当前 Channel Layer 停用，缓存后端用同一 redis-py，**勿升级到 8.x**。
- **（P1a 重试参考）Redis 未启动 → 首个 WS 请求报错**：`channels_redis` 惰性连接，启用 RedisChannelLayer 后第一个 WebSocket 请求若 Redis 不可用会抛 `ConnectionRefusedError`。排查：`systemctl is-active redis-server`；`redis-cli ping` 应返 `PONG`。
- **（P1a 重试参考）hiredis 在 ARM64 上**：channels_redis 会尝试 `import hiredis`，若不可用自动降级纯 Python redis 客户端（无副作用）。安装时若 hiredis 编译报错，`pip install channels_redis --no-deps && pip install redis` 绕过即可。
- **（P1a 重试参考）多 worker 下 WebSocket 连接**：启用 `--workers 2` 时，每个 WS 连接由握手 worker 独占，负载均衡由 OS 在 accept() 层完成；长连接不在 worker 间迁移，无消息丢失风险。
- **P1a 回滚现状**：`settings.py` CHANNEL_LAYERS 已为 `InMemoryChannelLayer`、systemd unit 已为 `--workers 1`（**当前生产状态**）。如需重试 P1a：固定 redis-py 5.x → 本地验证 WS 收发 → 改 CHANNEL_LAYERS + `--workers 2` → `daemon-reload` + `restart freeark-backend`，无需停 Redis。

### 9.2 LangGraph 聊天已知点（v1.7.0 起；取代原 OpenClaw 段）

- 聊天后端 = 进程内 `LangGraphAdapter`（`api/langgraph_chat/`），**无独立服务/端口**；`get_chat_adapter()` 恒返回它，不读 `CHAT_BACKEND`/`OPENCLAW_*`。
- venv 必装：`langgraph`、`langgraph-checkpoint`、`langchain-core`、`langchain-openai`、`openai`（当前实测 langgraph 0.3.34 / langchain-core 0.3.86 / langchain-openai 0.3.35 / openai 2.40.0）。
- LLM = DeepSeek v4-flash，经 `langchain-openai` 走 OpenAI 兼容协议，key 在 `.env` 的 `DEEPSEEK_API_KEY`；Pi 出网走 wlan0（注意已知 WiFi 省电偶发劣化，长查询可能超时）。
- 聊天对话历史**落 MySQL**（`api_chat_session`/`api_chat_message`）。
- v1.8.0 业主端隔离：`MiniAppChatConsumer.connect()` 构造 `UserScope` 注入 LangGraph State，`ScopeEnforcer` 在工具调用前强制范围（代码强制非提示词）；`user_scope=None`(admin/operator) 全程直通，零行为变化。
- **聊天冒烟（不依赖 WS 客户端）**：在 venv 里跑一段 `asyncio` 调 `get_chat_adapter().stream_chat(message=..., session_key=...)`，能收到 `kind in {content,reasoning}` 的 chunk 即正常（脚本须 `sys.path.insert(0, 项目目录)` + `DJANGO_SETTINGS_MODULE=freearkweb.settings` + `django.setup()`）。
- onnxruntime 启动告警 `Failed to detect devices under /sys/class/drm/cardN`（RAG OCR 模块找不到 GPU 自动转 CPU）无害，可忽略。

---

## 10. SSH 密钥认证设置

> ✅ **当前状态（2026-05-22；2026-06-26 增 VPS 通道）**：开发机 `~/.ssh/id_ed25519` 的公钥已装到生产树莓派
> `~/.ssh/authorized_keys`，免密登录可用。两条通道（同一把密钥、同一台 Pi）：
> - 推荐 `ssh -p 57279 yangyang@47.109.197.217`（VPS+frp 隧道）
> - 旧 `ssh -p 57279 yangyang@et116374mm892.vicp.fun`（花生壳）
>
> 同一把公钥也已装到 **VPS 的 root**（`ssh root@47.109.197.217`，用于管理 frps/nginx）。OpenSSH 自动用默认密钥，无需 `-i`。下面的步骤仅供换新开发机 / 重装密钥时参考。

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

## 11. LangGraph 聊天链路排查清单

发生聊天异常时按顺序排查（聊天 = `freeark-backend` 进程内 LangGraph，无独立服务）：

```bash
# 1. backend 是 Uvicorn 且有 WebSocket 后端
systemctl status freeark-backend --no-pager | grep -E "uvicorn|Active"
sudo journalctl -u freeark-backend -n 30   # 不应见 "Unsupported upgrade request" / Traceback

# 2. Nginx 含 /ws/ location（/ws/chat/ 与 /ws/miniapp/chat/ 都走同一 upstream）
grep -A 2 "location /ws/" /etc/nginx/sites-enabled/freeark | head -3

# 3. ALLOWED_HOSTS 含 Pi 实际访问 IP / 域名（否则 WS Origin 403）
grep "^ALLOWED_HOSTS" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/.env

# 4. DEEPSEEK_API_KEY 已配置（只看键名是否有值，不打印值）
grep -q "^DEEPSEEK_API_KEY=.\+" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/.env && echo "KEY_PRESENT" || echo "KEY_MISSING"

# 5. 聊天后端工厂确实返回 LangGraph
cd /home/yangyang/Freeark/FreeArk &&
  venv/bin/python FreeArkWeb/backend/freearkweb/manage.py shell -c "from api.chat_backend import get_chat_adapter; print(get_chat_adapter().__name__)"
  # 应输出 LangGraphAdapter

# 6. 真实聊天冒烟（调 stream_chat 实打 DeepSeek）——见 §9.2 末尾脚本要点：
#    sys.path.insert(0, 项目目录) + DJANGO_SETTINGS_MODULE=freearkweb.settings + django.setup()
#    async for kind,content in get_chat_adapter().stream_chat(message="你好", session_key="smoke"):
#    收到 kind in {content,reasoning} 的 chunk 即正常。
```

---

## 附：维护说明

本手册信息采集于 **2026-05-23（OpenClaw 集成 + ASGI 迁移完成日）**，**2026-05-29 补 `freeark-fault-consumer` 与 `freeark-fault-cleanup.timer`**（v0.6.3 部署期发现遗漏），**2026-05-31 perf-P1a（Redis Channel Layer + `--workers 2`）已回滚（channels_redis↔redis-py 8.x 不兼容），退回 InMemoryChannelLayer + `--workers 1`**，**2026-05-31 perf-P2（看板/故障数量接口 Redis 缓存后端 db=1 + redis-py 5.x 固定 + 缓存降级兜底）**，**2026-06-26 v1.7.0+v1.8.0 部署：聊天后端 OpenClaw→进程内 LangGraph，OpenClaw 已从生产完全卸载（服务/npm 包/配置/token/nginx UI/.env OPENCLAW_* 全清）；新增 /api/miniapp/ 业主端命名空间 + /ws/miniapp/chat/ + 两张表（owner_user_binding/wechat_binding，迁移 0041）；§11 排查清单与 §1/§2/§3/§4/§6/§8/§9.2 已据此重写，原 §12 OpenClaw Control UI 章节已整段删除**。基础设施变更后请同步更新本文件。

易变项（服务启动参数、nginx 配置、外网端口映射、数据库表规模、聊天后端/依赖版本等）用前需实测复核——
切勿把过时数值当事实（历史教训：
- 曾误把 `innodb_buffer_pool_chunk_size` 当成 `innodb_buffer_pool_size`，并长期沿用过时数值；
- 曾基于社区文章假设 OpenClaw HTTP SSE 接口存在，实测全 404，浪费一轮架构设计；
- 2026-05-29 部署 v0.6.3（BUG-FM-008 故障描述中文化）时，本 skill 当时列的服务清单遗漏了 `freeark-fault-consumer`，第一轮重启只动了 `backend + mqtt-consumer`，新 fault_event 仍按旧英文逻辑写入；查 MySQL processlist 才发现真正的写入服务是 `freeark-fault-consumer`，补重启后才生效）。

**部署前推荐先实跑** `systemctl list-units 'freeark-*' --no-pager` 比对当前生产真实清单与本文档，发现差异立刻就地修订本文件。
