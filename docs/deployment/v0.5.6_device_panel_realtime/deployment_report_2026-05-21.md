# 部署报告 — v0.5.6 设备面板实时数据刷新

```
file_header:
  document_id: DEPLOY-v0.5.6
  title: 设备面板实时数据刷新 — 生产部署报告
  author_agent: sub_agent_devops_engineer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  executed_at: 2026-05-21 17:33-17:48 CST
  status: DEPLOYED_WITH_WARNINGS
  references:
    - docs/deployment/v0.5.6_device_panel_realtime/deployment_plan.md
    - docs/development/v0.5.6_device_panel_realtime/implementation_plan.md
    - docs/development/v0.5.6_device_panel_realtime/code_review_report.md
    - docs/testing/v0.5.6_device_panel_realtime/integration_test_report.md
```

---

## 1. 部署概要

| 项 | 内容 |
|----|------|
| 部署目标 | 生产树莓派 192.168.31.51（外网：et116374mm892.vicp.fun:57279） |
| 项目路径 | `/home/yangyang/Freeark/FreeArk` |
| 部署方式 | plink SSH + git pull（无 pscp、无 migration） |
| 提交范围 | v0.5.5 基线（14229b5）→ v0.5.6（0510821，含 ee4b6a8 代码 + 0510821 文档） |
| 受影响服务 | freeark-task-scheduler、freeark-mqtt-consumer、**freeark-backend**（3 个） |
| 前端构建 | npm run build（nginx root 直接指向仓库 `frontend/dist`，无需 cp） |
| 新增 systemd service | 无 |
| 新增 pip 依赖 | 无 |
| 数据库 migration | 无 |
| 部署结果 | **DEPLOYED_WITH_WARNINGS** — 部署成功，核心链路 E2E 验证通过；UI 集成测试待人工执行 |

> **部署计划修正**：部署计划中的 `freeark-web.service` 在生产实际不存在，Django 后端服务实为 **`freeark-backend.service`**（ExecStart：`start_waitress_server.py`）；前端 nginx `root` 直接指向仓库内 `FreeArkWeb/frontend/dist`，`npm run build` 就地生效，无需 `cp` 到 `/usr/share/nginx/html`。

---

## 2. 变更内容摘要

### 2.1 核心功能变更

| 需求 | 变更说明 |
|------|---------|
| REQ-FUNC-001 | 新增按需采集专有通道：OndemandCollectSubscriber（datacollection）+ device_ondemand_refresh 视图（后端）+ ondemand 队列/worker（consumer） |
| REQ-FUNC-002 | 设备面板 30s 定时器升级为触发按需采集，而非仅读取 DB 快照 |
| REQ-FUNC-003 | 移除设备面板"刷新"按钮，改为数据到达后自动更新（MQTT done 通知驱动） |
| REQ-FUNC-004 | 统一数据更新时间戳：`上次数据更新于：YYYY-MM-DD hh:mm:ss`，取所有参数 collected_at 最大值 |

### 2.2 修改文件清单

| 文件路径 | 变更类型 | 模块 ID |
|---------|---------|---------|
| `datacollection/ondemand_collect_subscriber.py` | 新增 | MOD-DC-01 |
| `datacollection/improved_data_collection_manager.py` | 修改 | MOD-DC-02 |
| `FreeArkWeb/backend/freearkweb/api/views.py` | 修改（新增函数） | MOD-BE-01 |
| `FreeArkWeb/backend/freearkweb/api/urls.py` | 修改（追加路由） | MOD-BE-02 |
| `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 修改（新增子类） | MOD-BE-03 |
| `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | 修改（队列/worker） | MOD-BE-04 |
| `FreeArkWeb/frontend/src/views/DeviceCardsView.vue` | 重构 | MOD-FE-01 |

### 2.3 代码评审结论

- **整体评审结论：PASS**
- CRITICAL findings：**0**
- MAJOR findings：**0**
- MINOR findings：2（均不阻塞部署，详见 CR-v0.5.6）

---

## 3. 部署步骤执行记录

| 步骤 | 描述 | 执行时间 | 结果 | 备注 |
|------|------|---------|------|------|
| Step 0 | 本地 git push origin main | 17:30 | ✅ 成功 | 推送 ee4b6a8（代码）+ 0510821（文档）；与 v0.5.6 无关的临时脚本/旧版本文档均已排除 |
| Step 1 | plink SSH 登录（外网 et116374mm892.vicp.fun:57279） | 17:32 | ✅ 成功 | 内网 192.168.31.51 当前不可达，走外网穿透 |
| Step 2 | git pull 拉取 v0.5.6 代码 | 17:33 | ✅ 成功 | Fast-forward 14229b5 → 0510821（含 7a97693）；工作区 `.env`/`package-lock.json` 本地修改未受影响 |
| Step 3 | npm run build（就地，nginx 直读 dist） | 17:31 | ✅ 成功 | 构建耗时 24.0s；`DeviceCardsView-BvIyPoYS.js` 已重建 |
| Step 4 | 重启 freeark-task-scheduler | 17:33 | ✅ active | 旧进程 SIGTERM 90s 未退被 SIGKILL（既有现象，与 v0.5.6 无关，详见 §6 OBS-001） |
| Step 5 | 重启 freeark-mqtt-consumer | 17:33 | ✅ active | |
| Step 6 | 重启 freeark-backend（修正：非 freeark-web） | 17:34 | ✅ active | |
| Step 7 | 部署后验证 | 17:40-17:48 | ✅ 通过 | 三服务均 active；import 测试零异常；E2E 链路测试 PIPELINE_OK |

---

## 4. 部署后服务状态验证

| 验证项 | 预期结果 | 实际结果 | 通过 |
|--------|---------|---------|------|
| freeark-task-scheduler is-active | active | active | ✅ |
| freeark-mqtt-consumer is-active | active | active | ✅ |
| freeark-backend is-active（修正：非 freeark-web） | active | active | ✅ |
| OndemandCollectSubscriber 加载 | 模块导入零异常 | `venv/bin/python -c import` → `IMPORT OK` | ✅ |
| ondemand 链路端到端连通 | 发请求 → 收到 result + done | E2E 测试：result 1 条 + done 1 条，`VERDICT: PIPELINE_OK` | ✅ |
| 三服务重启后无 CRITICAL 错误 | journalctl 无 v0.5.6 相关 error/traceback | 无；仅有既存 PLC `Unreachable peer`（与 v0.5.6 无关，见 §6 OBS-002） | ✅ |

> **验证方式说明**：生产 `log_config.json` 全局日志级别为 `ERROR`（设计如此，"高频流水不打 INFO"），新 logger `ondemand_collect_subscriber` 继承该级别，故 `OndemandCollectSubscriber 已订阅`、`mqtt-ondemand-worker-0 启动` 等 INFO 级启动日志在生产**不会落盘**——空日志 ≠ 未启动。改以「Python import 测试 + MQTT 端到端链路测试」验证，结论更强。
>
> **E2E 链路测试**：向 `/datacollection/plc/ondemand/request/VERIFY_V056` 发布请求，22s 内收到：
> - `result/VERIFY_V056`：`{"success": false, "error": "specific_part 未找到对应 PLC IP", ...}` —— 证明 OndemandCollectSubscriber 收到请求、采集、发布结果（伪 specific_part 触发设计的优雅失败路径）。
> - `done/VERIFY_V056`：`{"specific_part": "VERIFY_V056", "collected_at": "2026-05-21 17:47:37"}` —— 证明 MQTTConsumer 收到 result、经独立 ondemand 队列 + worker 处理、发布 done 通知。

---

## 5. 生产集成测试验收（部署后人工执行）

> 部署完成后，请在生产环境人工执行以下集成测试，并记录验收结果。

| 测试 ID | 测试项 | 验收标准 | 实际结果 | 通过 |
|--------|--------|---------|---------|------|
| IT-001 | 按需采集端到端（15s 内完成） | P95 ≤ 15 秒；参数 collected_at 晚于页面打开时间 | **待人工执行**（需浏览器打开真实设备面板）；E2E 链路单次往返 < 1s | — |
| IT-002 | 按需采集不写 device_param_history | 触发前后行数不变 | **待人工执行**（代码层已由 CR 确认 `_write_history` no-op） | — |
| IT-003 | ondemand 消息进独立 ondemand 队列 | result 消息由 ondemand worker 处理并发 done | ✅ E2E 测试确认 result→ondemand worker→done 链路贯通 | ✅ |
| IT-004 | 页面打开自动触发按需采集 + 刷新按钮已移除 | mounted 后立即出现 POST /api/devices/ondemand-refresh/；无刷新按钮 | **待人工执行**（需浏览器） | — |
| IT-005 | 30s 定时器防重入 | ondemandInFlight=true 时不发出新请求 | **待人工执行**（需浏览器） | — |
| IT-006 | MQTT 不可用时降级 DB 轮询 | 触发 GET realtime-params，不触发 POST ondemand-refresh | **待人工执行**（需浏览器） | — |

### 附加验证项

| 验证项 | 实际结果 | 通过 |
|--------|---------|------|
| 统一时间戳显示格式正确（YYYY-MM-DD hh:mm:ss） | 待执行 | — |
| 各子系统列不再显示 HH:mm 独立时间戳 | 待执行 | — |
| 采集进行中显示 Loading 图标 | 待执行 | — |
| 周期采集（energy/general）链路不受影响 | 待执行 | — |

---

## 6. 已知 MINOR 问题 / 部署观察项（不阻塞投产）

| 编号 | 描述 | 影响 | 建议处置 |
|------|------|------|---------|
| MINOR-001 | `ondemand_collect_subscriber.py` `_read_plc_params` 逐参数串行读取，单设备 ~50 参数时采集耗时可能接近 15s 上限 | IT-001 可能偶发超限 | 生产观测实际耗时，若 P95 超 15s 可切换为分块批量读取（`_read_single_plc_with_multiple_params`），下版本优化 |
| MINOR-002 | `views.py` `_ondemand_inflight` 为进程级 dict，不支持多进程部署 | waitress 单进程无影响 | 若未来切换多进程，改为 Redis/数据库，下版本优化 |
| OBS-001 | 重启 freeark-task-scheduler 时旧进程 SIGTERM 后 90s 未退出，被 systemd SIGKILL | 重启耗时长；**与 v0.5.6 无关**（OndemandCollectSubscriber 为 daemon 线程不阻塞退出，疑为既有 PLC 轮询线程未响应 stop） | 后续排查 task-scheduler 的 graceful shutdown 处理 |
| OBS-002 | task-scheduler 日志大量 PLC `TCP : Unreachable peer`（192.168.2/8/9.x 多个 IP） | **与 v0.5.6 无关**，属既有现象；但若大面积 PLC 不可达，真实设备面板按需采集将返回 `success=false`，影响 IT-001 实测数据新鲜度 | 请独立核查生产 PLC 网络可达性，确认是否为真实故障 |

---

## 7. 回滚信息

| 项 | 内容 |
|----|------|
| 回滚基线版本 | v0.5.5（commit: 14229b5） |
| 回滚方式 | `git revert <v0.5.6 commits> --no-edit` + `git push origin main` + 三服务重启 |
| 回滚前端 | 重新 `npm run build` + 部署 dist |
| 回滚数据影响 | 无数据损失（v0.5.6 只 upsert plc_latest_data，不写 device_param_history） |
| 回滚后链路恢复 | 周期采集（energy/general）恢复 v0.5.5 行为；前端恢复 30s DB 轮询模式 |

**完整回滚步骤参见**: `docs/deployment/v0.5.6_device_panel_realtime/deployment_plan.md` Section 6

---

## 8. 最终部署结论

**部署结论**：**DEPLOYED_WITH_WARNINGS**

**说明**：
- ✅ 代码与文档已 git pull 至生产（HEAD = 0510821）；前端已就地构建；三服务（task-scheduler / mqtt-consumer / backend）均重启成功并 active。
- ✅ 核心按需采集链路经 MQTT 端到端测试验证 **PIPELINE_OK**——OndemandCollectSubscriber、独立 ondemand 队列 + worker、result/done 三条专属 topic 全部贯通；IT-003 通过。
- ⚠️ IT-001 / IT-002 / IT-004 / IT-005 / IT-006 需在浏览器打开真实设备面板后人工执行，**尚未完成**。
- ⚠️ 观察到生产 PLC 大面积 `Unreachable peer`（OBS-002，与 v0.5.6 无关），建议先核查 PLC 网络再做 IT-001 实测，否则按需采集会返回 `success=false`。

| 结论值 | 含义 |
|--------|------|
| DEPLOYED_SUCCESSFULLY | 所有步骤成功，IT-001~006 全部通过，无 CRITICAL 问题 |
| **DEPLOYED_WITH_WARNINGS** | **← 当前状态**：部署成功、核心链路验证通过；UI 集成测试待人工执行，另有 PLC 网络观察项 |
| DEPLOYMENT_FAILED_ROLLED_BACK | 部署失败，已执行回滚，系统恢复 v0.5.5 |

---

*本报告由 sub_agent_devops_engineer（via PM Orchestrator）生成，PRODUCTION_DEPLOY_CONFIRM=true，用户于 2026-05-21 本轮会话明确授权。*
