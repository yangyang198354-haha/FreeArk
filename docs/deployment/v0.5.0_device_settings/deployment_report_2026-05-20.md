# FreeArk v0.5.0 生产部署实际执行报告

**日期**：2026-05-20
**目标**：`192.168.31.51`（树莓派，用户 `yangyang`）
**基线**：v0.4.7（`b714db1`）→ **目标**：v0.5.0（`21d831f`）
**部署方式**：plink SSH + `git pull` + 在生产服务器构建前端（依内存中既有部署 recipe，不使用 devops-engineer 生成的 `deployment_plan.md` / `cicd_pipeline.md` / `production_runbook_*.md`，按用户指示这些为错误内容）
**执行人**：Claude Code（受用户 `PRODUCTION_DEPLOY_CONFIRM=true` 授权后通过 plink 代为执行）
**最终状态**：`DEPLOYED_SUCCESSFULLY`

---

## 1. 实际执行步骤与证据

| Step | 操作 | 关键证据 | 时间 |
|---|---|---|---|
| 1 | SSH 登录 `192.168.31.51` | `whoami=yangyang`，`hostname=raspberrypi`，`uname=Linux ... aarch64` | 01:34 |
| 2 | 生产端 `cd /home/yangyang/Freeark/FreeArk && git fetch origin && git pull --ff-only origin main` | `Updating b714db1..21d831f`，`Fast-forward`，24 files changed | 01:35 |
| 3 | 备份 nginx html → `/home/yangyang/nginx_html_bak_20260520_013623/`；记录 baseline `system_switch is_active=True` | `cp -a` 成功，备份目录存在 | 01:36 |
| 4 | `python manage.py check` + `migrate --check` + `seed_device_config` | check 通过；migrate --check 退出 0（无新增 migration）；seed 输出含 `[deactivated(updated)] system_switch -> main_thermostat (is_active=False)`；shell 二次断言 `system_switch.is_active=False` | 01:37–01:38 |
| 5 | `cd FreeArkWeb/frontend && npm run build` | `vite v6` 构建成功 23.53s，dist 全部时间戳 May 20 01:39，bundle hash `index-DmdRmXKM` → `index-OB0ZrgK8` | 01:39 |
| 6 | `sudo rsync -av --delete dist/ /usr/share/nginx/html/` + `sudo nginx -t && sudo nginx -s reload` + `sudo systemctl restart freeark-backend` | rsync 17 文件传输，`sent 3,798,389 bytes`；nginx -t OK；backend PID `15228 → 16867`，5 s 后 `active (running)` | 01:40–01:41 |
| 7 | 验证 | 见下表 | 01:42 |

---

## 2. 验证矩阵（agent 可独立执行的部分）

| 检查项 | 预期 | 实际 | 通过 |
|---|---|---|---|
| 监听端口 | 80 + 8000 + 8080 | `ss -tlnp` 确认 :80（nginx）、:8000（waitress, PID 16867）、:8080（nginx） | ✅ |
| nginx 前端首页 | HTTP 200 | `curl http://127.0.0.1:8080/` → `HTTP/1.1 200 OK`, `Last-Modified: 17:39:38 GMT` | ✅ |
| index.html 完整性 | dist 与 nginx html SHA256 一致 | 双方均为 `e8f5196938475b4f031d562621a8b604ee56d74ac55d32a2493d5d27149b69d4` | ✅ |
| Backend 路由 | `/api/device-settings/records/` 返回 401 而非 502/404 | HTTP 401，`{"detail":"Authentication credentials were not provided."}` | ✅ |
| Backend 重启 | PID 变化 + journalctl 启动无错 | PID 15228 → 16867；journalctl 显示 `Started ... 0 static files copied, 163 unmodified` | ✅ |
| Seed 关键变更 | `system_switch(main_thermostat).is_active = False` | DB 查询确认 `is_active=False`（基线为 True） | ✅ |
| v0.5.0 水力字段归属 | `operation_mode` / `away_energy_saving` / `central_energy_supply` / `hydraulic_module_inlet_temp` 的 `sub_type=hydraulic_module` 且 `is_active=True`，display_name 正确（"模式" / "离家节能标识" / "集中能源供给" / "二次水进水温度检测值"） | DB 查询全部匹配 | ✅ |
| 前端 bundle hash 变化 | 主 chunk hash 应改变 | `index-DmdRmXKM.js`（旧）→ `index-OB0ZrgK8.js`（新）；副 chunk `index-OzhOYD-U.js` 保持（与 v0.5.0 改动无关的代码） | ✅ |

---

## 3. 受限部分（agent 无法执行，需用户验收）

以下功能必须人工登录前端 `http://192.168.31.51:8080/` 验证：

| 编号 | 验收项 | 预期 |
|---|---|---|
| AC-01 | 主温控分组 | 系统开关字段消失 |
| AC-02 | 水力模块 | 出现"模式"下拉，可编辑 |
| AC-03 | 水力模块 | 出现"离家节能标识"下拉，可编辑 |
| AC-04 | 脏值追踪 | 修改后提交按钮旁显示脏值数量 |
| AC-05 | 仅提交 dirty | DevTools Network 中 POST 仅含已修改参数 |
| AC-06 | operation_mode 写入 | 后端返回 HTTP 202（pending），非 400 |

---

## 4. 备份与回滚资源

- nginx html 快照：`/home/yangyang/nginx_html_bak_20260520_013623/`（v0.4.7 前端产物）
- DB 回滚要点（无新 migration）：把 `DeviceConfig(param_name='system_switch', sub_type='main_thermostat').is_active` 改回 `True`
- 代码回滚：`cd /home/yangyang/Freeark/FreeArk && git reset --hard b714db1`（**慎用**：未提交的 `.env` / `package-lock.json` 本地修改不受影响）

---

## 5. 数据库实际配置确认（更新内存）

Django runtime 实际使用：

```
ENGINE = django.db.backends.mysql
NAME   = freeark
HOST   = 192.168.31.98
PORT   = 3306
USER   = root
```

与内存记录一致。`.env` 中 `DB_ENGINE=sqlite3` 是 fallback 占位，`USE_SQLITE` 未启用时走 MySQL 分支。

---

## 6. 未跟踪文件与未提交修改

生产端 `git status` 仍存在的本地状态（与本次部署无关，刻意保留）：
- `modified: FreeArkWeb/backend/.env` — 生产 MySQL 凭据，**必须保留**
- `modified: FreeArkWeb/frontend/package-lock.json` — 含 `mqtt` 依赖树扩展（v0.4.6 hotfix 配套），与远端 `package.json` 一致，构建无误
- 3 个 `.bak` 文件（`.env.bak.*`、`urls.py.bak`、`views.py.bak`）— 历史快照，不影响生产

---

## 7. 偏差说明

1. **不使用 devops-engineer 生成的 Runbook / deployment_plan / cicd_pipeline**：按用户明确指示这些内容错误（PROJECT_ROOT 默认 `/opt/freeark` 与实际 `/home/yangyang/Freeark/FreeArk` 不符；SQLite 备份步骤与生产 MySQL 现实不符等）。采用内存知识库中既有 recipe（`feedback_deploy_via_git_pull.md`）。
2. **未对 MySQL 做 mysqldump**：本次 seed 仅改 1 行（system_switch is_active），baseline 已记录，回滚成本 1 条 SQL；权衡后跳过全量 dump。
3. **AC-01～AC-06 未执行**：agent 无法操作浏览器 UI，必须由用户登录验收。

---

## 8. 最终判定

```
final_status: DEPLOYED_SUCCESSFULLY
(待用户完成 AC-01~AC-06 UI 验收后确认无回滚)
```
