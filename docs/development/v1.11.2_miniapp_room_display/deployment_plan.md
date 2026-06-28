# v1.11.2 小程序房间名展示 — 生产部署计划

> 状态：**待用户最终 CONFIRM 后执行**。本文档仅为计划，未执行任何生产操作。
> 编制：主线（pm-orchestrator GROUP_E 子代理因 session limit 中断，由主线补齐）
> 日期：2026-06-28

## 1. 变更摘要

| 项 | 值 |
|----|----|
| 变更文件 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（仅此 1 个，+24/-4）|
| 新增测试 | `FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_v1120.py`（11 用例，本地 11/11 OK）|
| 数据库迁移 | **无** |
| 新增依赖 | **无** |
| 前端构建 | **不需要**（展示逻辑在后端，小程序不变）|
| DB 字段变更 | **无**（不动共享 `DeviceConfig.sub_type_display`，Web 端零影响）|

核心改动：新增 `PANEL_DISPLAY_MAP` 常量，`miniapp_owner_realtime_params` 中
`display` 改为 `PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)`，
panel_* 显示纯房间名（书房/次卧/主卧/儿童房），系统级 sub_type 走 fallback 保持原值。

## 2. 重启范围

| 服务 | 是否重启 | 原因 |
|------|---------|------|
| `freeark-backend` | **是** | 改的是 REST 视图（HTTP/ASGI 入口进程）|
| 其它 worker/consumer | 否 | 无任何 consumer/worker import 此视图文件 |
| nginx | 否 | 无配置变更 |

## 3. 前置：本地提交并推送

> ⚠️ 生产工作树存在长期本地修改；本次提交**仅纳入 v1.11.2 相关文件**，不得扫入无关改动
> （`miniprogram/package-lock.json`、`miniprogram/vite.config.js`、`scripts/analysis/*`、其它版本 docs）。

纳入提交的文件：
- `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`
- `FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_v1120.py`
- `docs/architecture/v1.11.2_miniapp_room_display/`
- `docs/development/v1.11.2_miniapp_room_display/`
- `docs/testing/v1.11.2_miniapp_room_display/`

```bash
git add FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py \
        FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_v1120.py \
        docs/architecture/v1.11.2_miniapp_room_display \
        docs/development/v1.11.2_miniapp_room_display \
        docs/testing/v1.11.2_miniapp_room_display
git commit -F <消息文件>     # 中文消息走 -F 或 Bash，避免 PowerShell 拆词
git push origin main
```

## 4. 生产部署步骤（SSH 树莓派）

```bash
# 连接（VPS+frp 通道优先）
ssh -p 57279 yangyang@47.109.197.217

# 1. 核对工作树干净、确认拉取不触碰 .env / package-lock.json / heartbeat_broker_config.json
cd /home/yangyang/Freeark/FreeArk
git status
git fetch origin && git diff --name-only HEAD origin/main   # 应只含 v1.11.2 文件

# 2. 拉取（应为 fast-forward）
git pull origin main

# 3. 验证代码落地
grep -n "PANEL_DISPLAY_MAP" FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py
git log -1 --oneline

# 4. 重启后端
sudo systemctl restart freeark-backend
systemctl status freeark-backend --no-pager | grep Active
sudo journalctl -u freeark-backend -n 30 --no-pager   # 无 Traceback

# 5. 健康检查
curl -s http://127.0.0.1:8080/api/health/    # {"status":"ok",...}
```

## 5. 部署后验证

- 后端 `active (running)`，journald 无异常堆栈。
- （可选）Django shell 确认常量已加载：
  ```bash
  venv/bin/python FreeArkWeb/backend/freearkweb/manage.py shell -c \
    "from api.views_miniapp_device_settings import PANEL_DISPLAY_MAP; print(PANEL_DISPLAY_MAP)"
  ```
- 业务验证：业主端小程序进入设备面板页，确认温控面板卡片标题显示为
  **书房 / 次卧 / 主卧 / 儿童房**（无"-温控面板"后缀），系统级面板（主温控/新风）显示不变。
- 重点核对反直觉项：原 panel_bedroom 房间显示「次卧」、原 panel_children_room 显示「主卧」。

## 6. 回滚方案

改动仅 1 个文件、无迁移、无依赖、无 DB 变更，回滚极简：

```bash
cd /home/yangyang/Freeark/FreeArk
git revert <本次commit> --no-edit && git push    # 或 git reset --hard <上一个HEAD>（仅生产树）
git pull origin main
sudo systemctl restart freeark-backend
```

风险等级：**低**。最坏情况（面板标题显示异常）不影响参数读写、不影响 Web、不影响其它服务。

## 7. 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| 提交误纳入无关改动 | 中 | 显式 `git add` 指定文件，提交前 `git status` 复核 |
| session limit 中途中断部署 | 中 | 步骤幂等可重入；中断后重连续跑剩余步骤即可 |
| Web 端受影响 | 极低 | 未动 DB 字段，Web 走 `views.py` 独立路径 |
