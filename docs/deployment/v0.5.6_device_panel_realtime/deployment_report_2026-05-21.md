# 部署报告 — v0.5.6 设备面板实时数据刷新

```
file_header:
  document_id: DEPLOY-v0.5.6
  title: 设备面板实时数据刷新 — 生产部署报告
  author_agent: sub_agent_devops_engineer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: PENDING_EXECUTION
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
| 提交范围 | v0.5.5 基线（14229b5）→ v0.5.6 最新 commit |
| 受影响服务 | freeark-task-scheduler、freeark-mqtt-consumer、freeark-web（3 个） |
| 前端构建 | npm run build + 部署 dist |
| 新增 systemd service | 无 |
| 新增 pip 依赖 | 无 |
| 数据库 migration | 无 |
| 部署结果 | **待执行（PENDING_EXECUTION）** |

> **注**：本报告在部署计划生成时同步创建。部署执行后，操作人员应将各步骤结果、集成测试验收状态、以及最终部署结论回填至本报告的对应位置。

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

> 操作人员执行后请在此处记录各步骤结果。

| 步骤 | 描述 | 执行时间 | 结果 | 备注 |
|------|------|---------|------|------|
| Step 0 | 本地 git push origin main | — | 待执行 | |
| Step 1 | SSH 登录 192.168.31.51 | — | 待执行 | |
| Step 2 | git pull 拉取 v0.5.6 代码 | — | 待执行 | 记录实际拉取的 commit hash |
| Step 3 | npm run build + 部署 dist | — | 待执行 | 记录构建耗时 |
| Step 4 | 重启 freeark-task-scheduler | — | 待执行 | 确认 OndemandCollectSubscriber 启动日志 |
| Step 5 | 重启 freeark-mqtt-consumer | — | 待执行 | 确认 ondemand worker 启动日志 |
| Step 6 | 重启 freeark-web | — | 待执行 | |
| Step 7 | 部署后快速验证 | — | 待执行 | 三服务均 active，无崩溃日志 |

---

## 4. 部署后服务状态验证

> 操作人员执行后请在此处记录验证结果。

| 验证项 | 预期结果 | 实际结果 | 通过 |
|--------|---------|---------|------|
| freeark-task-scheduler is-active | active | 待执行 | — |
| freeark-mqtt-consumer is-active | active | 待执行 | — |
| freeark-web is-active | active | 待执行 | — |
| OndemandCollectSubscriber 启动日志（task-scheduler） | 日志含 `OndemandCollectSubscriber 已订阅` | 待执行 | — |
| ondemand worker 启动日志（mqtt-consumer） | 日志含 `mqtt-ondemand-worker-0` | 待执行 | — |
| 后端接口 400 验证（空 specific_part） | HTTP 400 | 待执行 | — |
| 三服务重启后无 CRITICAL 错误 | journalctl 无 error/critical/traceback | 待执行 | — |

---

## 5. 生产集成测试验收（部署后人工执行）

> 部署完成后，请在生产环境人工执行以下集成测试，并记录验收结果。

| 测试 ID | 测试项 | 验收标准 | 实际结果 | 通过 |
|--------|--------|---------|---------|------|
| IT-001 | 按需采集端到端（15s 内完成） | P95 ≤ 15 秒；参数 collected_at 晚于页面打开时间 | 待执行 | — |
| IT-002 | 按需采集不写 device_param_history | 触发前后行数不变 | 待执行 | — |
| IT-003 | ondemand 消息进 ondemand 队列 | consumer 日志显示 `queue=ondemand` | 待执行 | — |
| IT-004 | 页面打开自动触发按需采集 + 刷新按钮已移除 | mounted 后立即出现 POST /api/devices/ondemand-refresh/；无刷新按钮 | 待执行 | — |
| IT-005 | 30s 定时器防重入 | ondemandInFlight=true 时不发出新请求 | 待执行 | — |
| IT-006 | MQTT 不可用时降级 DB 轮询 | 触发 GET realtime-params，不触发 POST ondemand-refresh | 待执行 | — |

### 附加验证项

| 验证项 | 实际结果 | 通过 |
|--------|---------|------|
| 统一时间戳显示格式正确（YYYY-MM-DD hh:mm:ss） | 待执行 | — |
| 各子系统列不再显示 HH:mm 独立时间戳 | 待执行 | — |
| 采集进行中显示 Loading 图标 | 待执行 | — |
| 周期采集（energy/general）链路不受影响 | 待执行 | — |

---

## 6. 已知 MINOR 问题（不阻塞投产）

| 编号 | 描述 | 影响 | 建议处置 |
|------|------|------|---------|
| MINOR-001 | `ondemand_collect_subscriber.py` `_read_plc_params` 逐参数串行读取，单设备 ~50 参数时采集耗时可能接近 15s 上限 | IT-001 可能偶发超限 | 生产观测实际耗时，若 P95 超 15s 可切换为分块批量读取（`_read_single_plc_with_multiple_params`），下版本优化 |
| MINOR-002 | `views.py` `_ondemand_inflight` 为进程级 dict，不支持多进程部署 | waitress 单进程无影响 | 若未来切换多进程，改为 Redis/数据库，下版本优化 |

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

> 操作人员完成部署和集成测试后，请将以下结论更新为实际状态。

**部署结论**：PENDING_EXECUTION

| 结论值 | 含义 |
|--------|------|
| DEPLOYED_SUCCESSFULLY | 所有步骤成功，IT-001~006 全部通过，无 CRITICAL 问题 |
| DEPLOYED_WITH_WARNINGS | 部署成功，但部分集成测试未通过或有 MINOR 问题需跟踪 |
| DEPLOYMENT_FAILED_ROLLED_BACK | 部署失败，已执行回滚，系统恢复 v0.5.5 |

---

*本报告由 sub_agent_devops_engineer（via PM Orchestrator）生成，PRODUCTION_DEPLOY_CONFIRM=true，用户于 2026-05-21 本轮会话明确授权。*
