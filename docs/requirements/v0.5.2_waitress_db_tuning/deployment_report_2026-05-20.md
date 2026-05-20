# FreeArk v0.5.2 生产部署实际执行报告 — Waitress 线程数与数据库连接调优

**日期**：2026-05-20
**目标**：`192.168.31.51`（树莓派，用户 `yangyang`）
**基线**：`8eed4d0` → **目标**：`f15dd5d`（含 `ce06d65` 线程调优 + `f15dd5d` PYTHONUNBUFFERED）
**部署方式**：plink SSH + 生产服务器 `git pull` 快进（沿用 v0.5.0/v0.5.1 既有部署 recipe）
**执行人**：Claude Code（受用户明确 CONFIRM 授权后通过 plink 代为执行）
**最终状态**：`DEPLOYED_SUCCESSFULLY`

---

## 1. 变更内容

| 类别 | 文件 | 改动 |
|---|---|---|
| 后端 | `start_waitress_server.py` | `serve()` 参数化，从环境变量读取 `WAITRESS_THREADS`(默认16) / `WAITRESS_CHANNEL_TIMEOUT`(默认120) / `WAITRESS_CONNECTION_LIMIT`(默认100)，并显式传入 |
| 配置 | `systemctl/freeark-backend.service` | `[Service]` 增加 `Environment=PYTHONUNBUFFERED=1`，使启动日志实时进 journal |
| 测试 | `test_waitress_config_v052.py` | 新增 12 项单元测试，SQLite 全通过 |
| 测试 | `test_dashboard_perf.py` | 新增只读并发压测脚本（生产环境验证用） |
| 文档 | `docs/requirements/v0.5.2_waitress_db_tuning/` | 需求规格 / 用户故事 / 架构设计 / 模块设计 |

> `settings.py` **无变更**：`CONN_MAX_AGE=300` 保持原值，未添加 `reconnect=True`（决策 D-4/D-5）。

---

## 2. 实际执行步骤与证据

| Step | 操作 | 关键证据 |
|---|---|---|
| 1 | 本地 `git commit`（线程调优 + 测试 + 文档） | commit `ce06d65`，7 files changed, +1597/-1 |
| 2 | 本地 `git push origin main` | `8eed4d0..ce06d65  main -> main` |
| 3 | 服务器预检 | SSH 通；服务 `active`；HEAD `8eed4d0`；`.env`/`package-lock.json`/`*.bak` 本地修改保留（与本次无关，未触碰） |
| 4 | 服务器 `git pull origin main` | `Updating 8eed4d0..ce06d65`，Fast-forward，7 files |
| 5 | `systemctl restart freeark-backend` | 重启后 `is-active=active` |
| 6 | waitress 线程数验证 | `/proc/<PID>/status` → `Threads: 17`（16 工作线程 + 1 主线程；旧默认 `threads=4` 时仅 ~5） |
| 7 | API 冒烟 | `curl 127.0.0.1:8000/api/` → `HTTP 404`，`time_total=0.014s`（服务存活、响应快） |
| 8 | 本地 `git commit`（PYTHONUNBUFFERED） | commit `f15dd5d`，1 file changed, +2 |
| 9 | 本地 `git push origin main` | `ce06d65..f15dd5d  main -> main` |
| 10 | 服务器 `git pull` + `sudo cp` unit 文件至 `/etc/systemd/system/` + `daemon-reload` | `systemctl cat` 确认 `Environment=PYTHONUNBUFFERED=1` 已进生效 unit |
| 11 | `systemctl restart freeark-backend` | 重启后 `is-active=active` |
| 12 | 启动日志验证 | journal 出现 `Waitress 启动参数: threads=16, channel_timeout=120s, connection_limit=100`；`/proc/<PID>/environ` 含 `PYTHONUNBUFFERED=1`；`Threads: 17` |

---

## 3. 验证矩阵（agent 可独立执行部分）

| 检查项 | 预期 | 实际 | 通过 |
|---|---|---|---|
| 服务状态 | `active` | `active`（MainPID 2842） | ✅ |
| waitress 线程数 | 16 工作线程（总 ~17） | `Threads: 17` | ✅ |
| 启动参数生效 | threads=16 / timeout=120 / conn=100 | journal 明示三值 | ✅ |
| 监听端口 | `0.0.0.0:8000` | `ss` 确认 python(pid 2842) 监听 `:8000` | ✅ |
| API 响应 | 返回 HTTP 状态码 | `HTTP 404`，14ms | ✅ |
| PYTHONUNBUFFERED | 进程环境含该变量 | `/proc/<PID>/environ` 确认 | ✅ |
| 启动日志可观测 | journal 含 Waitress 启动参数行 | 确认出现 | ✅ |
| `settings.py` | 无变更 | `CONN_MAX_AGE=300` 保持，未加 `reconnect=True` | ✅ |
| 数据库迁移 | 无 | 无 model 变更，未产生 migration | ✅ |

---

## 4. 偏差与说明

1. **D-3 前置检查（生产 MySQL `max_connections`）**：用户已自行核实为 `151`（标准默认值）。16 个持久连接远低于安全阈值（121），无需调整。
2. **未应用 M2 systemd 环境变量 override（`WAITRESS_*`）**：代码默认值 16/120/100 与用户确认的目标值（决策 D-1/D-2）完全一致，直接采用默认值即可消除「转圈归零」，无需额外注入环境变量。如未来需偏离默认值，再按 `module_design.md` M2 添加 systemd override。
3. **PYTHONUNBUFFERED 为部署中发现并修复的可观测性缺陷**：首次部署（`ce06d65`）后发现 systemd 下 Python 父进程 stdout 默认缓冲，`start_waitress_server.py` 的启动 `print`（含「Waitress 启动参数」）不进 journal，导致无法从日志确认实际线程数。遂追加 commit `f15dd5d` 在 unit 文件注入 `PYTHONUNBUFFERED=1`，已验证日志恢复实时输出。
4. **未单独生成 `cicd_pipeline.md` / `deployment_plan.md`**：沿用 v0.5.0/v0.5.1 既定做法，按 plink + `git pull` recipe 直接执行。
5. **仅重启 `freeark-backend` 一个服务**：本次变更不涉及 datacollection / mqtt-consumer / nginx / 前端。
6. **API 冒烟返回 404**：`/api/` 裸路径无路由，返回 HTTP 状态码即证明 WSGI 服务存活；功能性验收见第 5 节。

---

## 5. 待用户人工验收（agent 无法操作浏览器 UI）

登录前端系统看板验证：

| 编号 | 验收项 | 预期 |
|---|---|---|
| AC-01 | 打开系统看板首页 | 「总电量查询 / 今日用电量 / 本月用电量」等 7 个面板正常加载，不再长时间转圈后归零 |
| AC-02 | 多标签页并发刷新看板 | 并发请求不再因 4 线程上限排队超时（16 线程下应顺畅） |
| AC-03 | （可选）在 Pi 上运行 `test_dashboard_perf.py` | 量化各面板 API 并发耗时与失败率 |

---

## 6. 回滚方案

- **代码 + 配置回滚**（⚠ 需用户 CONFIRM）：
  ```
  cd /home/yangyang/Freeark/FreeArk && git reset --hard 8eed4d0
  sudo cp systemctl/freeark-backend.service /etc/systemd/system/freeark-backend.service
  sudo systemctl daemon-reload && sudo systemctl restart freeark-backend
  ```
  回滚到 `8eed4d0` 将同时回退 `start_waitress_server.py`（恢复 waitress 默认 4 线程）与 unit 文件（移除 `PYTHONUNBUFFERED`）。
- **无 DB 变更**，无需 DB 回滚。
- **无前端变更**，无需前端回滚。

---

## 7. 最终判定

```
final_status: DEPLOYED_SUCCESSFULLY
(待用户完成 AC-01~AC-02 看板 UI 验收后确认无回滚)
```
