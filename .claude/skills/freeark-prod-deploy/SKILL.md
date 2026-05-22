---
name: freeark-prod-deploy
description: FreeArk 生产环境部署参考手册。当需要部署 FreeArk 到生产（树莓派）、SSH 连接生产服务器、重启/排查 systemd 服务、构建前端、连接或查询生产数据库、或排查生产部署问题时使用。包含访问方式、目录结构、服务清单、构建与重启流程、操作注意事项。本文件不含任何密码。
---

# FreeArk 生产环境部署手册

> **信息快照：2026-05-22。** 带 ⚠️ 的项为易变 / 用前需实测复核。
> **本文件不含任何密码。** SSH 用密钥认证（见 §10），数据库凭据在 `settings.py`、用 `dbshell` 间接使用。
> 本手册给"怎么做"，但每次部署仍须先实测"当前是什么样"（生产工作树状态、服务状态、本次拉取涉及的文件）。

## 何时用本 skill
部署 FreeArk 到生产、SSH 连生产树莓派、重启 systemd 服务、构建前端、连生产数据库、排查生产部署问题时。

---

## 1. 生产环境基本信息

| 项 | 值 |
|---|---|
| 生产服务器 | 树莓派 Raspberry Pi 5，hostname `raspberrypi` |
| 内网地址 | `192.168.31.51` |
| 外网访问 | 动态域名 `et116374mm892.vicp.fun`（经路由器端口映射）|
| SSH 端口 | 外网 `57279`（映射到内网 22）|
| SSH 用户 | `yangyang` |
| SSH 认证 | SSH 密钥（见 §10）。**本文件不存密码。** |
| sudo | 免密（NOPASSWD）|
| 部署纪律 | 一律 `ssh`/`plink` + `git pull`；**禁止 pscp 逐文件上传** |
| 生产数据库 | MySQL 9.4.0 @ `192.168.31.98:3306`，库名 `freeark` |

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
| `FreeArkWeb/backend/freearkweb/freearkweb/` | Django 项目配置（`settings.py`、`wsgi.py`、`start_waitress_server.py`）|
| `FreeArkWeb/backend/freearkweb/api/` | 主应用（models / views / management commands）|
| `FreeArkWeb/frontend/` | Vue3 + Vite 前端；`dist/` 为构建产物 |
| `datacollection/` | PLC 数据采集（`run_task_scheduler.py`）|
| `venv/` | Python 虚拟环境；解释器 `venv/bin/python` |
| `systemctl/` | systemd unit 文件的**仓库副本（源文件）** |
| `logs/` | 应用日志（见 §8）|
| `docs/` | 项目文档 |

⚠️ **生产工作树长期存在本地修改**，`git pull` 前必须确认本次拉取不触碰它们：
- `FreeArkWeb/backend/.env` — 生产专属环境配置
- `FreeArkWeb/frontend/package-lock.json` — 生产 ARM 依赖树

---

## 3. systemd 服务清单

unit 文件部署于 `/etc/systemd/system/`；仓库 `systemctl/` 目录是**源副本**。
全部 `User=yangyang`、`WorkingDirectory=/home/yangyang/Freeark/FreeArk/`、`Restart=on-failure`。

| 服务 | 作用 | 入口 |
|---|---|---|
| `freeark-backend` | Django Web（waitress，监听 :8000）| `start_waitress_server.py` |
| `freeark-mqtt-consumer` | MQTT 消费 | `manage.py mqtt_consumer_service` |
| `freeark-plc-connection-monitor` | PLC 连接状态监控 | `manage.py plc_connection_monitor` |
| `freeark-plc-cleanup` | plc_data 清理（每周日 02:00）| `manage.py plc_data_clean_up_service` |
| `freeark-dph-cleanup` | device_param_history 清理（每天 03:00）| `manage.py dph_cleanup_service` |
| `freeark-screen-heartbeat` | 屏幕心跳消费 | `manage.py screen_heartbeat_consumer` |
| `freeark-daily-usage` | 日用量统计 | `manage.py daily_usage_service` |
| `freeark-monthly-usage` | 月用量统计 | `manage.py monthly_usage_service` |
| `freeark-task-scheduler` | 任务调度 | `datacollection/run_task_scheduler.py` |

**常用命令：**
```bash
systemctl status <svc> --no-pager              # 状态
sudo systemctl restart <svc>                   # 重启
sudo journalctl -u <svc> -n 50 --no-pager      # 看日志（systemd 服务输出到 journald）
systemctl list-units 'freeark*' --no-pager     # 全部 freeark 服务一览
```

> 注：服务器上还有一个 GitHub Actions self-hosted runner（`actions.runner.*`）。当前生产部署实践为**手动 `git pull`**，不依赖该 runner 自动部署。

---

## 4. Web 架构与访问链路

```
浏览器 → nginx(:8080) ┬→ /        静态文件 FreeArkWeb/frontend/dist/ (Vue SPA)
                      ├→ /api     反代 → http://192.168.31.51:8000 (Django/waitress)
                      └→ /mqtt-ws 反代 → http://192.168.31.98:32797/mqtt
```

- nginx 站点配置：`/etc/nginx/sites-enabled/freeark`（监听 `:8080`，server_name `et116374mm892.vicp.fun 192.168.31.51`）
- Django 后端：waitress，`host=0.0.0.0 port=8000`
- ⚠️ `sites-enabled/` 内还有 `default` 与 `freeark.bak.150500`，可能与 `freeark` 配置冲突，必要时清理。
- ⚠️ 外网 Web 访问端口经路由器端口映射，**具体外网端口本手册未记录**——需查路由器映射表或问运维。

---

## 5. 标准部署流程（后端 / 服务 / 文档变更）

1. **本地提交并推送**到 `main`：`git push origin main`。
   - ⚠️ PowerShell 5.1 下 `git commit -m` 若消息含中文、双引号或 `$()` 会被错误拆分。改用 `git commit -F <消息文件>`，或用 Bash 工具提交。
2. **核对拉取范围**：本地 `git diff --name-only <生产当前HEAD> <新HEAD>`，确认不含 `.env` / `package-lock.json`。
3. **生产拉取**：`cd /home/yangyang/Freeark/FreeArk && git pull origin main`（应为 fast-forward）。
4. **验证代码落地**：`grep` 关键改动确认已到生产文件；`git log -1 --oneline` 确认 HEAD。
5. **重启受影响服务**（见 §6）。
6. **验证**：服务 `active (running)`，`journalctl` 无异常堆栈。

---

## 6. 什么改动重启什么

| 改动内容 | 操作 |
|---|---|
| 后端通用 Python 代码（`api/` 等被多处引用的代码）| 重启 `freeark-backend` + 用到该代码的 worker 服务 |
| 某个 management command 自身代码（如 `dph_cleanup_service.py`）| 只重启对应的那个服务 |
| `settings.py` | 重启 `freeark-backend` + 全部 worker 服务（均加载 settings）|
| systemd unit 文件（`systemctl/*.service`）| `sudo cp systemctl/<unit> /etc/systemd/system/` → `sudo systemctl daemon-reload` → `sudo systemctl restart <svc>` |
| 前端代码 | 见 §7（重新构建 `dist/`）|
| nginx 配置 | 改 `/etc/nginx/sites-enabled/freeark` → `sudo nginx -t` → `sudo systemctl reload nginx` |
| 纯文档 / 测试 | 无需重启 |

> **关键坑**：仓库 `systemctl/` 里的 unit 文件只是源副本。`git pull` **不会**更新正在运行的 systemd——必须手动 `cp` 到 `/etc/systemd/system/` 并 `daemon-reload`。

---

## 7. 前端构建与部署

前端 = Vue3 + Vite，源在 `FreeArkWeb/frontend/`。

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend
# （可选）依赖变化时：npm install   ——注意生产 package-lock.json 有本地修改
cp -r dist dist_backup_$(date +%Y%m%d%H%M%S)   # 构建前备份旧产物（生产有此先例）
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

**日志**
- systemd 服务输出 → journald：`sudo journalctl -u <svc>`
- 应用文件日志 → `/home/yangyang/Freeark/FreeArk/logs/`（如 `multi_thread_plc_handler.log`、`mqtt_client.log` 等）
- ⚠️ `logs/` 下部分日志体积很大（PLC handler 日志单文件上百 MB），排查时用 `tail` 不要 `cat`。

---

## 9. 操作注意事项 / 已知坑

- **用 Bash 工具调用 plink/ssh，不要用 PowerShell。** PowerShell 5.1 对双引号、`$()`、`&` 的原生命令传参有缺陷，会把命令拆错。
- plink 首次连接新主机需缓存主机密钥；`-batch` 模式无法应答交互提示（密码 / 主机密钥确认）。
- 后台跑长任务：`nohup <cmd> </dev/null >日志文件 2>&1 &`。Python 命令加 `-u` 取消 stdout 缓冲，否则日志要等缓冲区满才落盘。
- `git pull` 前务必确认不会覆盖生产本地修改的 `.env` / `package-lock.json`。
- 数据库写操作 / 生产部署属高风险操作——执行前应取得明确确认。
- 测试用 SQLite：`python manage.py test`（settings.py 检测到 test 自动切 SQLite，不连生产 DB）。

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

## 附：维护说明

本手册信息采集于 **2026-05-22**。基础设施变更后请同步更新本文件。
易变项（服务启动参数、nginx 配置、外网端口映射、数据库表规模等）用前需实测复核——
切勿把过时数值当事实（历史教训：曾误把 `innodb_buffer_pool_chunk_size` 当成 `innodb_buffer_pool_size`，并长期沿用过时数值）。
