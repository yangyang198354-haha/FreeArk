# 架构设计文档

```
file_header:
  document_id: ARCH-v0.5.6
  title: 设备面板实时数据刷新 — 架构设计文档
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/requirements/v0.5.6_device_panel_realtime/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py
    - datacollection/improved_data_collection_manager.py
    - datacollection/task_scheduler.py
    - datacollection/plc_write_subscriber.py
    - FreeArkWeb/frontend/src/composables/useMqttWebSocket.js
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue
```

---

## 1. 架构总览

### 1.1 现有数据流（v0.5.5）

```
[TaskScheduler]──(周期, ~10min)──[ImprovedDataCollectionManager]
       │                                   │
       │  多 IntervalGroup 线程              │ PLC S7 批量读取
       │                                   ↓
       │                         [MQTT Broker 192.168.31.98:32788]
       │                                   │
       │                     topic: /datacollection/plc/to/collector/<id>
       │                                   ↓
       │                         [MQTTConsumer]
       │                           ├─ energy_queue (3 workers)
       │                           │    └─ PLCDataHandler + ConnectionStatusHandler + PLCLatestDataHandler
       │                           └─ general_queue (6 workers)
       │                                └─ PLCDataHandler + PLCLatestDataHandler
       │
[前端 DeviceCardsView]──(30s 定时)──GET /api/devices/realtime-params/──→[Django views]──→ plc_latest_data (MySQL)
```

**关键问题**：前端每 30 秒读取一次 DB 快照，但快照数据最新也是 ~10 分钟前的采集结果。按需刷新按钮仅重读 DB，并不触发新采集。

### 1.2 新增数据流（v0.5.6）

```
[前端 DeviceCardsView]
  │  (mounted + 每 30s)
  │  POST /api/devices/ondemand-refresh/ {specific_part}
  ↓
[Django views] ── 发布 MQTT 指令 ──→ [MQTT Broker]
                                           │
                    topic: /datacollection/plc/ondemand/request/<specific_part>
                                           │
                                           ↓
                              [OndemandCollectSubscriber]  ← 新增，在 datacollection 服务中
                                           │
                                    (单设备 PLC 读取)
                                           │
                                           ↓
                               [MQTT Broker]
                      topic: /datacollection/plc/ondemand/result/<specific_part>
                                           │
                                           ↓
                              [MQTTConsumer]
                              ondemand_queue (1 worker)   ← 新增
                                    └─ PLCLatestDataHandler (只写 plc_latest_data)
                                    └─ 发布 done 通知
                                           │
                    topic: /datacollection/plc/ondemand/done/<specific_part>
                                           │
              [MQTT WebSocket (nginx 反代 /mqtt-ws/)]
                                           │
                                           ↓
                              [前端 useMqttWebSocket]
                                    │  收到 done 通知
                                    ↓
                              fetchData() → GET /api/devices/realtime-params/ → plc_latest_data
                                    │
                                    ↓
                              参数标签就地更新 + 统一时间戳刷新
```

---

## 2. 架构决策记录（ADR）

### ADR-001：后端向 datacollection 发送指令的通道选择

**决策背景**：后端需要向运行在同一树莓派上的 datacollection 服务下达"立即采集指定设备"的指令。

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 方案 A（MQTT 指令 topic）| 后端向 MQTT broker 发布指令，datacollection 订阅 | 无需新增通信通道；broker 已存在；与 PLCWriteSubscriber 模式一致 | datacollection 订阅 broker 有延迟（通常 <100ms）；需新增订阅逻辑 |
| 方案 B（HTTP 接口）| datacollection 暴露 HTTP API（如 Flask），后端 HTTP 调用 | 同步，可立即得知 datacollection 已接受请求 | 需在 datacollection 中额外维护 HTTP 服务；生产环境端口管理增加复杂度 |
| 方案 C（本地 Unix Socket）| 进程间通信 | 零网络开销 | 实现复杂度高；不适合跨服务解耦；树莓派同进程限制 |

**决策：方案 A（MQTT 指令 topic）** — **Accepted（用户已确认，2026-05-21，OQ-001）**

**理由**：
1. 整个系统已以 MQTT 为通信骨干（PLCWriteSubscriber 已证明该模式可行）
2. 无需引入新通信机制，降低运维复杂度
3. MQTT 订阅延迟 < 100ms，对于 15 秒的端到端目标可忽略
4. 后端发布失败（broker 不可用）时可返回 503，前端降级为 30 秒 DB 轮询

**Topic 设计**：
```
/datacollection/plc/ondemand/request/<specific_part>
```
Payload（JSON）：
```json
{"specific_part": "X", "requested_at": "2026-05-21 10:00:00"}
```

---

### ADR-002：ondemand 结果 consumer 的独立 worker 设计

**决策背景**：按需采集结果消息需要不排队等待常规 energy/general 消息的处理，否则在队列积压时（如 energy 队列积压约 97% 满载，见 data_collection_pipeline_perf_analysis）仍会有几分钟的等待延迟，违背 15 秒端到端目标。

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 方案 A（独立队列 + 1 个 worker）| 新增 `_ondemand_queue`，1 个专属 worker | 完全零等待；不影响 energy/general 路径 | 增加 1 个 Django worker 线程 |
| 方案 B（复用 general_queue）| ondemand 消息进 general_queue | 无需改 consumer 架构 | general_queue 满载时 ondemand 消息也会排队；不满足 15 秒目标 |
| 方案 C（优先队列）| 单队列，ondemand 消息插队 | 消息有优先级 | Python `queue.Queue` 不支持优先级；需换 `queue.PriorityQueue` 并修改所有入队出队逻辑，改动面大 |

**决策：方案 A（独立队列 + 1 个 worker）** — **Accepted（用户已确认，2026-05-21，OQ-002：1 个线程）**

**理由**：
1. 按需消息的 QPS 极低（每 30 秒最多 1 条/设备），独立 1 个 worker 线程成本微乎其微
2. 与现有双队列模式（energy + general）完全对称，扩展清晰
3. 树莓派资源有限，1 个额外 daemon 线程影响极小

**Worker 定义**：
```
worker 名称: mqtt-ondemand-worker-0
队列: _ondemand_queue (maxsize=100)
handler 链: [PLCLatestDataHandler()]  // 只写 plc_latest_data，不写 device_param_history
```

---

### ADR-003：前端自动更新触发机制

**决策背景**：当 consumer 完成 `plc_latest_data` 写入后，前端需要被通知以立即更新 UI，而不是等待下一个 30 秒定时器。

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 方案 A（MQTT WebSocket done 通知）| consumer 发布 done topic，前端 MQTT WebSocket 订阅 | 实时性好；已有 `useMqttWebSocket.js` 基础设施；模式与 write_ack 通知一致 | MQTT WebSocket 不可用时失效（需降级） |
| 方案 B（HTTP 长轮询）| 前端每 2 秒 poll 专用接口，接口等待 done 事件后返回 | 无需 MQTT WebSocket | 实现复杂；长连接占服务端资源；与现有架构不一致 |
| 方案 C（Server-Sent Events）| 后端 SSE 推送 done 事件 | 单向流，语义清晰 | Django 需额外配置；生产 waitress WSGI 不支持 SSE 的流式响应 |

**决策：方案 A（MQTT WebSocket done 通知）** — **Accepted（用户已确认，2026-05-21，OQ-004：QoS 0）**

**理由**：
1. `DeviceSettingsPanelView` 已使用 `useMqttWebSocket` 订阅 write_ack，同样模式对 done 通知完全可复用
2. nginx 反代 `/mqtt-ws/` 路径已就绪，无需新增基础设施
3. 降级策略已在需求中定义（MQTT 不可用则 30 秒 DB 轮询兜底），UX 可接受

**Done Topic 设计**：
```
/datacollection/plc/ondemand/done/<specific_part>
```
Payload（JSON）：
```json
{"specific_part": "X", "collected_at": "2026-05-21 10:00:05"}
```
QoS = 0（consumer 已发布即可，无需确认；前端有 30 秒兜底）

---

### ADR-004：按需采集是否写 device_param_history

**决策背景**：周期采集会通过 `PLCLatestDataHandler._write_history()` 写入 `device_param_history`，每小时保留第一条（v0.5.4 P1-1 去重逻辑）。按需采集同样经过 `PLCLatestDataHandler.handle()`，是否同步写历史？

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 方案 A（不写历史）| ondemand worker 的 handler 链只调 `_bulk_upsert`，不调 `_write_history` | 轻量；不膨胀 device_param_history；完全不改变历史数据语义（历史只来自周期采集） | 按需采集的数据点不会出现在历史报表中（可接受，因为历史数据本来就是周期快照） |
| 方案 B（写历史）| 与周期采集同路径，调 `_write_history` | 历史数据更完整 | 存在膨胀风险；与 v0.5.4 P1-1 每小时去重逻辑交互（按需每 30 秒一条会被去重，只保留同小时第一条） |

**决策：方案 A（不写历史）** — **Accepted（用户已确认，2026-05-21，OQ-003）**

**理由**：
1. `device_param_history` 已历史膨胀（3600 万行，v0.5.2 处理），严格控制写入量
2. 按需采集的语义是"当下查看"，不是"补充历史时序数据"
3. 每小时去重缓存（`_general_hist_last_hour`）是进程内全局状态，按需采集插入同小时第一条后，同小时的周期采集会被去重跳过，造成历史数据语义混乱

**实现方式**：`OndemandPLCLatestDataHandler` 继承 `PLCLatestDataHandler`，覆盖 `handle()` 方法，仅调用 `_bulk_upsert(records)`，不调用 `_write_history(records)`。

---

### ADR-005：datacollection 接收指令的实现方式

**决策背景**：datacollection 已有 `PLCWriteSubscriber` 订阅 MQTT 接收 PLC 写入指令。按需采集指令属于类似的"从 broker 接收异步指令"模式。

**候选方案**：

| 方案 | 描述 |
|------|------|
| 方案 A（新建 OndemandCollectSubscriber）| 参照 PLCWriteSubscriber，新建独立订阅类，复用 ImprovedDataCollectionManager 的 `collect_data_for_building(param_filter=None)` 逻辑（限定为单设备） |
| 方案 B（扩展 PLCWriteSubscriber）| 在现有订阅类中增加 ondemand topic 的处理分支 | 改动小，但职责边界模糊（PLC 写入 vs. 数据采集是完全不同的职责）|

**决策：方案 A（新建 OndemandCollectSubscriber）** — **Accepted（2026-05-21，与 OQ-001 联动）**

**理由**：单一职责，易于单独测试和维护。

**关键约束**：
- 单设备采集使用 `ImprovedDataCollectionManager.collect_data_for_building()` 配合内联设备映射，或直接使用 `PLCManager` 的线程池执行单设备读取
- 结果发布至 `/datacollection/plc/ondemand/result/<specific_part>`，格式与周期采集结果完全一致
- 使用独立的 MQTT 客户端连接（不与 PLCWriteSubscriber 共用 paho client 实例）

---

## 3. 关键接口定义

### 3.1 后端 HTTP 接口

```
POST /api/devices/ondemand-refresh/
Authorization: Token <token>
Content-Type: application/json

Request:
{
    "specific_part": "X"   // 必填，格式 楼-单-层-户，如 "9-1-31-3104"
}

Response 202:
{
    "status": "accepted",
    "specific_part": "X"
}

Response 400:
{
    "detail": "specific_part 为必填项"
}

Response 503:
{
    "detail": "MQTT broker 不可达，无法提交采集请求"
}
```

### 3.2 MQTT Topic 汇总

| Topic | 发布方 | 订阅方 | Payload 结构 |
|-------|--------|--------|-------------|
| `/datacollection/plc/ondemand/request/<sp>` | Django views | OndemandCollectSubscriber | `{"specific_part":"sp","requested_at":"TS"}` |
| `/datacollection/plc/ondemand/result/<sp>` | OndemandCollectSubscriber | MQTTConsumer ondemand_queue | 与周期采集结果格式相同 (`{device_id:{...data...}}`) |
| `/datacollection/plc/ondemand/done/<sp>` | MQTTConsumer ondemand_worker | 前端 useMqttWebSocket | `{"specific_part":"sp","collected_at":"TS"}` |

### 3.3 与现有接口的复用关系

| 组件 | 复用方式 |
|------|---------|
| `PLCLatestDataHandler._bulk_upsert()` | ondemand worker 直接调用，写 `plc_latest_data` |
| `useMqttWebSocket.js` | 前端订阅 done topic，与 write_ack 模式相同 |
| `GET /api/devices/realtime-params/` | done 通知到达后前端主动 GET 更新数据 |
| `ImprovedDataCollectionManager` 的 PLC 读取核心 | OndemandCollectSubscriber 复用（限定单设备） |

---

## 4. 组件依赖图

```
[前端 DeviceCardsView.vue]
    依赖 → useMqttWebSocket.js (订阅 done topic)
    依赖 → api.js POST /api/devices/ondemand-refresh/
    依赖 → api.js GET /api/devices/realtime-params/

[Django views (ondemand_refresh)]
    依赖 → paho-mqtt client (发布 request topic)
    依赖 → PLCLatestData model (read, via get_device_realtime_params)

[OndemandPLCLatestDataHandler (新增)]
    继承 → PLCLatestDataHandler
    覆盖 → handle()，仅调 _bulk_upsert()，不调 _write_history()

[MQTTConsumer (扩展)]
    新增 → _ondemand_queue (独立队列)
    新增 → mqtt-ondemand-worker-0 线程
    新增 → 订阅 /datacollection/plc/ondemand/result/# topic
    新增 → 完成后发布 /datacollection/plc/ondemand/done/<sp>

[OndemandCollectSubscriber (新增，datacollection 服务)]
    继承/参照 → PLCWriteSubscriber 的 MQTT 订阅模式
    依赖 → ImprovedDataCollectionManager（PLC 读取核心）
    依赖 → MQTTClient（发布结果 topic）
    订阅 → /datacollection/plc/ondemand/request/#
```

---

## 5. 与现有链路的解耦保证

| 解耦维度 | 设计保证 |
|---------|---------|
| MQTT 队列隔离 | ondemand result 消息进 `_ondemand_queue`，通过 topic prefix 路由（`/datacollection/plc/ondemand/result/`），不进 energy/general 队列 |
| DB 写入路径隔离 | ondemand worker 只写 `plc_latest_data`（upsert），不写 `device_param_history`，不调用 `PLCDataHandler`、`ConnectionStatusHandler` |
| PLC 读取隔离 | OndemandCollectSubscriber 使用独立 MQTT 客户端和独立线程池（单线程即可），不与 TaskScheduler 的 IntervalGroup 线程共享资源 |
| 周期采集不受影响 | TaskScheduler 的 `_group_loop` 不感知 ondemand 指令；两者通过不同 MQTT topic 完全独立 |

---

## 6. 部署视图

所有组件运行在同一台物理服务器（树莓派 192.168.31.51），共享 MQTT Broker（192.168.31.98:32788）：

```
树莓派 192.168.31.51
├── [systemd] freeark-task-scheduler.service  (datacollection TaskScheduler + PLCWriteSubscriber)
│       └── 新增: OndemandCollectSubscriber 在 ImprovedDataCollectionManager.start() 中启动
│
├── [systemd] freeark-mqtt-consumer.service   (Django mqtt_consumer_service)
│       └── 新增: ondemand_queue + 1 worker + 订阅 ondemand result topic
│
├── [systemd] freeark-web.service             (Django Waitress)
│       └── 新增: POST /api/devices/ondemand-refresh/ 视图
│
└── [nginx]
        └── /mqtt-ws/ 反代 MQTT WebSocket（已就绪）
```

**无新增 systemd service**，所有变更均在已有 service 内追加逻辑。

---

## 7. 风险与缓解措施

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| 树莓派 CPU/内存压力：按需采集每 30 秒并发触发多个用户同一设备 | 中 | 后端对同一 `specific_part` 进行防重入（请求锁，TTL=30s），同一设备同一时间最多 1 个采集任务 |
| MQTT ondemand done 消息丢失（QoS=0）| 低 | 前端 30 秒 DB 轮询作为兜底，最多 30 秒后降级更新 |
| OndemandCollectSubscriber 崩溃导致按需采集失效 | 低 | 采用守护线程，崩溃后不影响 TaskScheduler 主循环；前端降级 30 秒轮询 |
| 大量用户同时打开不同设备面板，产生大量并发 PLC 请求 | 中 | OndemandCollectSubscriber 维护一个有界待处理队列（maxsize=20），超出拒绝（后端返回 503，前端降级） |
