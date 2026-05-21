# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.5.6
  title: 设备面板实时数据刷新 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue
    - FreeArkWeb/backend/freearkweb/api/views.py (get_device_realtime_params)
    - FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (PLCLatestDataHandler)
    - datacollection/improved_data_collection_manager.py
    - datacollection/task_scheduler.py
    - docs/requirements/v0.5.5_connection_status_lock_opt/requirements_spec.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，基于用户需求描述与代码勘察 |

---

## 1. 背景与动因

### 1.1 业务背景

FreeArk 楼宇 PLC 数据采集平台的**设备面板页面**（`DeviceCardsView.vue`）展示指定专有部分的所有实时参数，数据来源为 `plc_latest_data` 表，由 `datacollection` 服务通过 `TaskScheduler` 周期性（当前配置约 10 分钟一轮，能耗参数约 6 分钟）采集，经 MQTT 消息队列传至 Django `mqtt_consumer_service`，由 `PLCLatestDataHandler` 写入数据库。

### 1.2 现存问题

| 维度 | 当前状况 |
|------|---------|
| 数据实时性 | 用户打开设备面板时，看到的数据最大可滞后约 10 分钟（采集周期）加 MQTT 队列排队时延（高峰期数分钟） |
| 刷新机制 | 页面顶部有"刷新"按钮，但点击后仅重新读取 `plc_latest_data` 中的存量数据，不触发 PLC 重新采集 |
| 页面自动刷新 | 已有 30 秒定时器（`startAutoRefresh`）轮询 `/api/devices/realtime-params/`，但同样只读 DB 存量 |
| 时间戳显示 | 每个子系统列（sub_type）独立显示采集时间（`getCollectedAt`），格式为 `HH:mm`；无统一汇总时间戳，不直观 |

### 1.3 性能约束（继承自前序版本）

生产环境已知隐患：
- `device_param_history` 已清理（v0.5.2 P0-1），`innodb_buffer_pool_size` 已扩至 2 GB（v0.5.2 P0-2）
- 本需求**新增的按需采集查询只读 `plcdatalatest`（即 `plc_latest_data`）或限定范围**，禁止触发 `device_param_history` 大表全扫
- `datacollection` 服务运行在生产树莓派（192.168.31.51），PLC 设备通过局域网 S7 协议连接；按需采集需控制并发，避免影响周期采集

---

## 2. 需求范围

本版本（v0.5.6）仅覆盖**设备面板（DeviceCardsView）的专有通道按需实时刷新能力**，不修改：
- 周期性采集链路的任何现有逻辑
- 其他页面（PLC 状态、Dashboard、历史报表等）
- `DeviceSettingsPanelView`（设备参数设置面板）

---

## 3. 功能需求

### REQ-FUNC-001：按需采集专有通道

**描述**：当用户打开设备面板页面时，前端通过**专有的 HTTP 请求通道**向后端发起按需数据刷新请求；后端转发请求至 `datacollection` 服务；`datacollection` 立即（单独）执行一次针对该专有部分的 PLC 数据采集，并将结果发布至专有 MQTT topic；consumer 通过**独立 worker（不与常规 energy/general 消息共用队列，不排队等待）**将数据写入 `plc_latest_data`。

**来源**：用户需求第 1 条

**验收标准**：
- Given 用户打开某专有部分的设备面板页面
- When 页面加载完成
- Then 在 15 秒内，前端能展示来自该次专有采集的最新数据（即数据的 `collected_at` 晚于页面打开时间）

**约束**：
- AC-001-1：按需采集只采集该专有部分（single `specific_part`）的所有配置参数，不触发全量采集
- AC-001-2：按需采集走独立 MQTT topic（`/datacollection/plc/ondemand/result/<specific_part>`），不写入常规 energy/general 队列
- AC-001-3：consumer 为该 topic 设置独立 worker 线程（独立于现有 energy/general worker），确保按需消息零等待
- AC-001-4：`datacollection` 接收到按需请求后，若该专有部分 PLC IP 不可解析（不在配置中），返回 404，不执行采集
- AC-001-5：单次按需采集的 DB 写入路径与现有 `PLCLatestDataHandler._bulk_upsert` 相同，只写 `plc_latest_data`，不写 `device_param_history`

### REQ-FUNC-002：页面打开期间周期性按需轮询

**描述**：设备面板页面处于打开状态期间，每 30 秒自动触发一次 REQ-FUNC-001 的按需采集请求。页面关闭（beforeUnmount）时停止。

**来源**：用户需求第 2 条

**验收标准**：
- Given 设备面板页面已打开
- When 距离上次刷新已过 30 秒
- Then 前端自动发起一次按需采集请求，页面数据在请求完成后更新
- And 页面关闭时，定时器被清除，不再发送请求

**约束**：
- AC-002-1：30 秒轮询定时器与现有 30 秒 `refreshTimer`（`startAutoRefresh`）合并为一个机制；按需请求触发后等待响应再更新 UI，而不是定时轮询 DB 快照
- AC-002-2：若按需请求正在进行中（已发出但未收到 MQTT 结果通知），不重复发送新请求（防重入）

### REQ-FUNC-003：去掉刷新按钮，标签自动更新

**描述**：移除设备面板顶部导航栏中的"刷新"按钮；当按需采集的新数据写入 `plc_latest_data` 后，页面上的参数值标签自动更新，无需用户手动触发。

**来源**：用户需求第 3 条

**验收标准**：
- Given 设备面板页面打开，按需采集结果已到达
- When consumer 完成 `plc_latest_data` 写入，通过专有 MQTT topic 通知前端
- Then 前端收到通知后立即重新拉取 `/api/devices/realtime-params/` 并更新所有参数标签
- And 页面顶部导航栏不再显示"刷新"按钮

**约束**：
- AC-003-1：自动更新机制使用现有 `useMqttWebSocket.js` composable 订阅 consumer 的完成通知 topic
- AC-003-2：前端订阅的通知 topic 为 `/datacollection/plc/ondemand/done/<specific_part>`（consumer 完成写入后由后端主动发布，或由 consumer 直接发布至 MQTT broker）
- AC-003-3：若 MQTT WebSocket 连接不可用，降级为当前 30 秒定时轮询 DB 快照的兜底行为

### REQ-FUNC-004：统一数据更新时间戳

**描述**：设备面板的专有部分区域只显示一个统一的数据更新时间戳，格式为：`上次数据更新于：YYYY-MM-DD hh:mm:ss`。不再为每个子系统列（sub_type）单独显示时间。

**来源**：用户需求第 4 条

**验收标准**：
- Given 设备面板展示了某专有部分的参数数据
- When 页面完成渲染或数据刷新完毕
- Then 页面某区域（建议顶部区域或面板底部）显示一行：`上次数据更新于：YYYY-MM-DD hh:mm:ss`
- And 该时间戳取所有参数中 `collected_at` 的最大值（最新时间）
- And 不再在每个子系统列（col-time）处单独展示 `HH:mm` 格式时间

**约束**：
- AC-004-1：时间戳格式严格为 `YYYY-MM-DD hh:mm:ss`（24 小时制）
- AC-004-2：若无任何参数有 `collected_at`，则显示 `—`（破折号）

---

## 4. 非功能需求

### REQ-NFR-001：按需采集性能

| 指标 | 目标 |
|------|------|
| 单次按需采集端到端延迟（请求发出至前端数据更新） | ≤ 15 秒（P95） |
| 对现有周期采集链路的影响 | 按需采集不抢占 energy/general MQTT 队列的 worker，不导致周期消息积压加重 |
| 对数据库的影响 | 按需采集只写 `plc_latest_data`（upsert），不触发历史表写入，单次写入行数 ≤ 单设备参数总数（约 50 行） |

### REQ-NFR-002：前端 UX

| 指标 | 目标 |
|------|------|
| 按需刷新进行中时 | 显示加载指示（loading 状态），防止用户疑惑 |
| 数据自动更新时 | 无需页面整体刷新，仅参数值标签就地更新 |
| 降级兜底 | MQTT WebSocket 不可用时，30 秒 DB 轮询不中断，用户无感知（UX 降级但不中断） |

### REQ-NFR-003：部署约束

- 物理机部署，禁 Docker
- 生产服务器：树莓派 192.168.31.51
- 生产 DB：MySQL 192.168.31.98:3306
- 部署方式：plink + git pull，禁止 pscp 逐文件上传

---

## 5. 系统边界与接口约束

### 5.1 按需采集请求通道

| 角色 | 位置 | 职责 |
|------|------|------|
| 前端（DeviceCardsView） | Vue SPA | 发起 HTTP POST /api/devices/ondemand-refresh/，携带 specific_part |
| 后端（Django views） | FreeArkWeb/backend | 接收请求，向 datacollection 发出 MQTT 指令（或 HTTP 调用），返回 202 Accepted |
| datacollection（TaskScheduler） | 树莓派 datacollection 服务 | 订阅专有 MQTT 指令 topic，收到请求后立即执行单设备采集，结果发布至结果 topic |
| consumer（MQTTConsumer） | Django mqtt_consumer_service | 订阅按需结果 topic，独立 worker 写入 plc_latest_data，完成后发布 done 通知 |
| 前端 MQTT WebSocket | Vue SPA | 订阅 done 通知 topic，触发 UI 更新 |

### 5.2 MQTT Topic 规划

| Topic | 方向 | 用途 |
|-------|------|------|
| `/datacollection/plc/ondemand/request/<specific_part>` | 后端 → datacollection | 按需采集指令 |
| `/datacollection/plc/ondemand/result/<specific_part>` | datacollection → consumer | 按需采集结果（与周期采集结果格式相同） |
| `/datacollection/plc/ondemand/done/<specific_part>` | consumer → 前端 | 按需写入完成通知，payload：`{"specific_part":"...","collected_at":"YYYY-MM-DD HH:MM:SS"}` |

### 5.3 不修改的现有接口

- `/api/devices/realtime-params/`：前端仍通过此接口拉取最新参数（MQTT done 通知到达后触发一次 GET 请求）
- `PLCLatestDataHandler._bulk_upsert`：复用现有 upsert 逻辑，按需结果走相同路径
- `energy_queue` / `general_queue`：不受影响

---

## 6. 开放问题（已全部决议）

> 所有开放问题已于 2026-05-21 由用户确认，决策如下：

| 编号 | 问题 | 决议 | 决策方案 |
|------|------|------|---------|
| OQ-001 | 后端向 datacollection 发送按需指令的通道 | **已决议** | **方案 A（MQTT 发布指令）**：通过 MQTT broker 发布指令 topic，datacollection 订阅后执行，不引入额外 HTTP 端口。 |
| OQ-002 | consumer 独立 worker 与现有 worker 的关系 | **已决议** | **1 个线程（单线程串行入库）**：新增 1 个 ondemand worker，单线程串行处理 ondemand 队列，与现有 energy/general 队列完全解耦。 |
| OQ-003 | 按需采集是否写 device_param_history | **已决议** | **不写入 device_param_history 历史表**：只 upsert `plc_latest_data`，严格遵循 AC-001-5，防止历史表再次膨胀。 |
| OQ-004 | done 完成通知 MQTT QoS | **已决议** | **QoS 0（最多一次）**：依赖前端 30 秒定时轮询兜底，无需消息确认开销。 |
