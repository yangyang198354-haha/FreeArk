# v0.9.0 会话不活动超时 + 登录刷新 last_login — 生产部署报告

- **日期**：2026-05-30
- **提交**：`d5b5ff6`
- **生产 HEAD**：`eb19665` → `d5b5ff6`（fast-forward）
- **部署人**：Claude Code（用户 CONFIRM 授权）
- **类型**：后端认证逻辑 + 数据库迁移 + 前端；重启 `freeark-backend`，前端 rebuild
- **SDLC 流程**：需求 → 架构 → 开发 → 测试 → 部署，逐阶段门控用户确认

## 需求范围

| 需求 | 内容 |
|------|------|
| REQ-AUTH-001 (P0) | 会话不活动超时：**滑动窗口 30 分钟**，每次有效请求刷新计时；超时返回 401；旧 token 失效不可复用；阈值走 settings 常量不硬编码 |
| REQ-AUTH-002 (P1) | 登录/注册成功后刷新 `api_customuser.last_login`（由 `login()` 的 `user_logged_in` 信号驱动，误差 ≤5s；登录失败不变） |
| REQ-AUTH-003 (P1) | 前端 401 统一处理：清 `localStorage.userToken` + auth_token cookie + CSRF 缓存、`ElMessage` 提示"会话已过期"、`router.replace` 跳登录、防循环重定向，集中在 `api.js` 的 `authenticatedFetch` |
| REQ-NFR-AUTH-001 (P0) | 刷新"最后活动时间"不得显著增加生产 MySQL 写压力：进程内节流，同一 token 默认 5 分钟内最多写一次 DB |

## 技术方案（架构决策）

- **OQ-001**：新增 `api/authentication.py` 的 `SlidingWindowTokenAuthentication`，继承 DRF `TokenAuthentication`，在 `authenticate_credentials` 末尾追加滑动窗口超时判定。回滚仅需改回 settings 一行，零数据迁移。
- **OQ-002**：新增 `TokenActivity` 模型（OneToOne 关联 authtoken Token 作主键，字段 `last_active_at`）+ 模块级进程内 dict `_activity_cache` 节流。worker 重启缓存清空则从 DB 重读（最坏提前 5 分钟超时，保守且安全）。
- **OQ-003 / OQ-005**：本版本不实现前端心跳续期与未保存数据保护（与降低写压力冲突 / UX 折衷，留后续版本）。
- **OQ-004**：保留现有 `login(request, user)` 路径刷新 last_login，零新增代码。
- **WebSocket（consumers.py）零改动**：已建立的 WS 长连接不纳入本版本超时（已接受的折衷）。
- **零新增第三方依赖**。

## 改动文件

| 文件 | 变更 |
|------|------|
| `api/authentication.py` | 新增 `SlidingWindowTokenAuthentication` + `_activity_cache` |
| `api/models.py` | 新增 `TokenActivity` 模型 |
| `api/migrations/0030_add_token_activity.py` | 新建 `api_token_activity` 表 |
| `api/views.py` | `user_login` / `user_register` 签发 token 后 `update_or_create` 初始活动时间（绕过节流） |
| `freearkweb/settings.py` | `DEFAULT_AUTHENTICATION_CLASSES` 换为新认证类；新增 `SESSION_INACTIVITY_TIMEOUT=1800`、`ACTIVITY_THROTTLE_SECONDS=300`（可由 `.env` 覆盖） |
| `frontend/src/utils/api.js` | `authenticatedFetch` 统一 401 处理 |
| `api/tests_session_timeout.py` | 新增 22 个测试用例 |
| `api/tests/test_owner_sprint2.py` | N+1 阈值 8→9（认证新增 1 次 O(1) 常量查询，非 N+1） |

## 测试结果（主控亲自复核，非子代理转述）

- **新增 22 个 session_timeout 测试：全部通过**（滑动窗口刷新/超时 401/旧 token 失效/节流不重复写库/last_login 刷新/CASCADE 清理等）。
- 子代理交付时**未执行测试**（误判本地无 Django），主控亲自跑发现并修复 3 处：
  - `test_tc_register_01`（400）：测试缺 `password2` 字段 → 补齐（测试缺陷）。
  - `test_tc_login_06`（401）：重登前未清 client 过期凭证 → `self.client.credentials()`（测试缺陷）。
  - `test_tc_us03_008_no_n_plus_1`（9>8）：认证新增 1 次常量查询 → 阈值上调至 9（本次唯一回归，已处理）。
- **全套件回归对比**（HEAD 干净 worktree 基线）：基线 1176 测试 25 失败 + 7 错误；本分支 1198 测试**同样 25 失败 + 7 错误** + 22 新测试全过 → **本次改动零净回归**（那 25+7 为与本次无关的预存失败）。

## 部署步骤

1. 本地提交 + push origin main（`d5b5ff6`，13 文件，不触碰 .env/package-lock/heartbeat_broker_config.json）。
2. SSH：外网 `et116374mm892.vicp.fun:57279` 偶发 `kex_exchange_identification: Connection closed`（花生壳/frp 隧道瞬断），改用 **LAN `192.168.31.51:22`** 直连（开发机同网段，更稳）。
3. 生产 `git pull origin main` → fast-forward 至 `d5b5ff6`，生产本地修改（.env / heartbeat / package-lock）完整保留，无冲突。
4. `sqlmigrate` 预检 DDL（仅 CREATE TABLE 新表）→ `migrate api 0030` → `api_token_activity` 表已建。
5. 重启 `freeark-backend`（settings 认证类 + 新 authentication/models/views 属 Web 路径；worker 不涉 DRF 认证，未重启，避免打断 MQTT/故障消费）。
6. 前端 `cp -r dist <备份>` + `npm run build` → `✓ built in 19.44s`，nginx 直接服务 dist/ 即时生效。

## 验证（生产实弹，非转述）

| 项 | 证据 |
|----|------|
| 新认证路径 | 带有效 token 打 `/api/auth/me/` → **HTTP 200**；无 token → **401** |
| 活动时间写入 | 认证后该 token 的 `TokenActivity` 行 = 1 |
| 迁移落地 | `SHOW TABLES LIKE 'api_token_activity'` 返回该表 |
| 前端产物 | `dist/assets/index-DWb1xdtQ.js` 含 "会话已过期" |
| 服务健康 | `api/health` → 200；`freeark-backend` / `fault-consumer` / `mqtt-consumer` 全 `active running` |
| 日志 | backend 重启后无 error/traceback |

## 配置项（生产可覆盖）

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `SESSION_INACTIVITY_TIMEOUT` | 1800（秒）| 不活动超时阈值（30 分钟）|
| `ACTIVITY_THROTTLE_SECONDS` | 300（秒）| 活动时间写库节流阈值（5 分钟）|

## 回滚方案

- **代码回滚**：将 `settings.py` 的 `DEFAULT_AUTHENTICATION_CLASSES[0]` 改回 `rest_framework.authentication.TokenAuthentication`，重启 `freeark-backend` 即恢复旧行为（永不超时）。无需回滚 DB（`api_token_activity` 表留存不影响旧逻辑）。
- **前端回滚**：还原 `/home/yangyang/FreeArk_backup/dist_backup_<时间戳>` 到 `dist/`。

## 已知折衷 / 待观察

- **存量 token 立即生效**：部署时生产有 4 个 token，新规则即时约束；当前在线用户 30 分钟无操作后下次访问需重新登录（即需求目标）。
- **WebSocket 不纳入超时**：已建立的 WS 长连接不会因超时被踢断，下次 HTTP 请求才 401。
- **多 worker 局限**：当前 Uvicorn `--workers 1`，节流 dict 单进程一致；若未来多 worker，各进程独立缓存会使节流/超时判定不一致（最坏提前 5 分钟超时，仍安全）。
