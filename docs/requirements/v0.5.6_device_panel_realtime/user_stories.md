# 用户故事清单

```
file_header:
  document_id: US-v0.5.6
  title: 设备面板实时数据刷新 — 用户故事清单
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/requirements/v0.5.6_device_panel_realtime/requirements_spec.md
```

---

## US-001：打开设备面板时自动触发按需采集

**作为** 物业运维人员，  
**我希望** 打开某个住户的设备面板页面后，能在 15 秒内看到来自最新一次 PLC 实际读取的数据，  
**以便** 我能快速准确地判断该户设备的当前运行状态，而不是看到最多 10 分钟前的过期快照。

### 验收标准（Given/When/Then）

**AC-001-1：页面打开触发按需采集**
- Given 用户导航至 `/device-cards?specific_part=X` 页面
- When 页面 `mounted` 生命周期执行
- Then 前端向 `POST /api/devices/ondemand-refresh/` 发起请求，携带 `specific_part=X`
- And 后端返回 `202 Accepted`，采集任务已提交

**AC-001-2：15 秒内完成端到端更新**
- Given 按需采集请求已发出，PLC 设备在线
- When datacollection 完成该专有部分的 PLC 读取并发布 MQTT 结果
- Then consumer 独立 worker 在收到结果后 5 秒内完成 `plc_latest_data` 写入
- And 前端在收到 done 通知后重新拉取数据并更新页面
- And 从页面打开到数据完成更新的端到端时间 ≤ 15 秒（P95）

**AC-001-3：采集结果 collected_at 晚于请求发出时间**
- Given 按需采集成功完成
- When 前端更新页面数据
- Then 所有参数的 `collected_at` 均 ≥ 请求发出时间（证明数据来自本次实时采集）

**AC-001-4：PLC 不可达时的降级**
- Given 某专有部分的 PLC 设备离线（无法建立 S7 连接）
- When 按需采集执行
- Then datacollection 在超时后（不超过 10 秒）发布失败结果或直接不发布 result
- And 前端保持展示上一次已有数据（不清空页面），并在统一时间戳处显示上次更新时间
- And 控制台/日志中有明确错误记录

---

## US-002：页面打开期间每 30 秒自动刷新

**作为** 物业运维人员，  
**我希望** 设备面板在我持续查看期间能每 30 秒自动获取最新 PLC 数据，  
**以便** 我无需手动操作就能持续监控设备实时状态变化（如温度、开关状态切换）。

### 验收标准（Given/When/Then）

**AC-002-1：30 秒自动触发下一次按需采集**
- Given 设备面板页面处于打开状态，上次按需采集已完成（done 通知已收到）
- When 从上次请求发出起已过 30 秒
- Then 前端自动触发下一次 `POST /api/devices/ondemand-refresh/`
- And 该 30 秒定时器与原有 `refreshTimer` 使用同一套计时机制（合并）

**AC-002-2：防重入——采集进行中不重复发送**
- Given 按需采集请求已发出，尚未收到 done 通知
- When 30 秒定时器到期触发
- Then 前端跳过本次触发（不发送新请求），等待当前采集完成
- And 当前采集完成后，定时器重置为 30 秒开始下一轮

**AC-002-3：页面关闭时定时器清除**
- Given 设备面板页面正在进行 30 秒周期轮询
- When 用户关闭或离开该页面（`beforeUnmount`）
- Then 定时器被清除，不再发送任何按需采集请求
- And MQTT WebSocket 连接断开

---

## US-003：去掉刷新按钮，数据自动更新

**作为** 物业运维人员，  
**我希望** 设备面板不再有"刷新"按钮，数据能在后台完成采集后自动更新到页面，  
**以便** 操作更简洁，我无需主动感知何时需要刷新。

### 验收标准（Given/When/Then）

**AC-003-1：刷新按钮已从 UI 移除**
- Given 用户打开设备面板页面
- When 页面完全加载完成
- Then 顶部导航栏中不存在"刷新"按钮（`nav-refresh-btn`）
- And 不存在任何手动触发采集的按钮

**AC-003-2：done 通知触发页面自动更新**
- Given 按需采集完成，consumer 已发布 done 通知至 MQTT topic `/datacollection/plc/ondemand/done/<specific_part>`
- When 前端 MQTT WebSocket 收到该通知
- Then 前端立即调用 `fetchData()` 从 `/api/devices/realtime-params/` 拉取最新数据
- And 所有参数标签的显示值在不刷新整页的情况下就地更新

**AC-003-3：MQTT 不可用时降级为轮询**
- Given 前端 MQTT WebSocket 连接失败或断开
- When 30 秒定时器到期
- Then 前端直接调用 `fetchData()` 读取 DB 快照数据（不发起按需采集请求）
- And 页面显示数据，仅时效性较低，用户无感知错误提示

---

## US-004：统一时间戳替代分散时间显示

**作为** 物业运维人员，  
**我希望** 设备面板只显示一个统一的数据更新时间，格式为`上次数据更新于：YYYY-MM-DD hh:mm:ss`，  
**以便** 我一眼就能判断当前看到的数据是何时采集的，不必去每个子系统列查看零散的 `HH:mm` 时间。

### 验收标准（Given/When/Then）

**AC-004-1：统一时间戳显示**
- Given 设备面板展示了参数数据
- When 页面完成渲染
- Then 页面某位置（建议面板顶部或底部）显示 `上次数据更新于：YYYY-MM-DD hh:mm:ss`
- And 该时间戳的值为所有参数 `collected_at` 中的最大值（最新时间）
- And 格式严格为 24 小时制 `YYYY-MM-DD HH:MM:SS`

**AC-004-2：各子系统列不再单独显示时间**
- Given 设备面板展示多个子系统列（sub_type 列）
- When 用户查看任意子系统列的列头（col-header）
- Then 列头中不显示 `HH:mm` 格式的单独时间（`col-time` 元素移除或不渲染）

**AC-004-3：无数据时显示占位符**
- Given 当前专有部分在 `plc_latest_data` 中无任何参数记录（或所有 `collected_at` 为 null）
- When 页面渲染时间戳区域
- Then 显示 `上次数据更新于：—`

---

## US-005：后端提供按需采集触发接口

**作为** Django 后端，  
**我希望** 提供 `POST /api/devices/ondemand-refresh/` 接口，接收前端按需采集请求后，向 `datacollection` 服务发出指令，  
**以便** 前端无需了解 MQTT 内部通道细节，统一由后端作为协调中心。

### 验收标准（Given/When/Then）

**AC-005-1：接口正常路径**
- Given 已认证用户发送 `POST /api/devices/ondemand-refresh/` 携带 `{"specific_part": "X"}`
- When 后端接收请求
- Then 后端向 MQTT broker 发布一条指令到 `/datacollection/plc/ondemand/request/X`
- And 接口返回 `202 Accepted`，body `{"status": "accepted", "specific_part": "X"}`

**AC-005-2：接口参数校验**
- Given 请求体缺少 `specific_part` 字段或字段值为空字符串
- When 后端接收请求
- Then 接口返回 `400 Bad Request`，body 包含可读错误描述

**AC-005-3：MQTT 发布失败的处理**
- Given 后端向 MQTT broker 发布指令时发生异常
- When 发布失败
- Then 接口返回 `503 Service Unavailable`，body 包含错误说明
- And 日志中记录 MQTT 发布异常

---

## US-006：datacollection 响应按需采集指令

**作为** `datacollection` 服务（TaskScheduler），  
**我希望** 订阅按需采集指令 topic，收到指令后立即执行单设备采集并发布结果，  
**以便** 设备面板的按需刷新请求能被及时响应，不受周期调度的干扰。

### 验收标准（Given/When/Then）

**AC-006-1：订阅并响应按需指令**
- Given datacollection 服务已启动，PLCWriteSubscriber 或新增 OndemandCollectSubscriber 正在运行
- When MQTT broker 上发布一条 `/datacollection/plc/ondemand/request/<specific_part>` 消息
- Then datacollection 在 5 秒内开始执行该 `specific_part` 的 PLC 数据读取
- And 采集完成后将结果发布至 `/datacollection/plc/ondemand/result/<specific_part>`（结构与周期采集 MQTT 消息相同）

**AC-006-2：按需采集不影响周期采集**
- Given 周期采集任务正在进行（TaskScheduler 的某 group 线程正在执行）
- When 同时收到按需采集指令
- Then 按需采集在独立线程（ondemand 线程池）中执行，不阻塞也不被阻塞
- And 周期采集结果与按需采集结果互不干扰，分别发布至各自 topic

**AC-006-3：单设备采集结果格式**
- Given datacollection 完成单设备采集
- When 发布 MQTT 结果消息
- Then 消息 payload 格式与 `improved_data_collection_manager.send_results_to_mqtt` 的格式完全一致（`{device_id: {PLC IP地址: ..., data: {param_name: {value, success, message, timestamp}, ...}}}`）

---

## US-007：consumer 的独立 ondemand worker 处理结果

**作为** Django `MQTTConsumer`，  
**我希望** 为按需采集结果 topic 配置独立 worker 和独立队列，  
**以便** 按需消息能被立即处理，不需排在常规 energy/general 消息后面等待。

### 验收标准（Given/When/Then）

**AC-007-1：独立队列接收**
- Given MQTTConsumer 已启动，已订阅 `/datacollection/plc/ondemand/result/#`
- When 收到 ondemand result 消息
- Then 消息被放入 `_ondemand_queue`（独立队列，不进 `_energy_queue` 或 `_general_queue`）

**AC-007-2：独立 worker 处理**
- Given `_ondemand_queue` 有待处理的 ondemand result 消息
- When ondemand worker 线程（`mqtt-ondemand-worker-0`）从队列取出消息
- Then worker 调用 `PLCLatestDataHandler.handle()` 完成 `plc_latest_data` upsert（不写 `device_param_history`，与 AC-001-5 保持一致）
- And 不调用 `PLCDataHandler` 也不调用 `ConnectionStatusHandler`

**AC-007-3：写入完成后发布 done 通知**
- Given ondemand worker 完成 `plc_latest_data` upsert
- When upsert 成功执行
- Then consumer 向 MQTT broker 发布 `/datacollection/plc/ondemand/done/<specific_part>`，payload `{"specific_part":"...","collected_at":"YYYY-MM-DD HH:MM:SS"}`（取本次写入的最大 `collected_at`）
- And QoS = 0

---

## 故事地图与依赖关系

```
US-005 (后端接口)
    └─ 被 US-001 前端调用
    └─ 向 MQTT 发布 → US-006 (datacollection)
        └─ 采集结果 → US-007 (consumer worker)
            └─ done 通知 → US-003 (前端自动更新)
US-001 ──→ US-002 (30 秒周期复用 US-001)
US-004 (时间戳) 依赖 US-003 触发刷新
```
