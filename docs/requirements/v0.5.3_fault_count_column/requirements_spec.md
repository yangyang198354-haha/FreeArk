# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.5.3-FCC
  title: 设备列表「故障数量」列 + OpenClaw 故障查询工具 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3-fault-count-column
  created_at: 2026-05-26
  status: DRAFT
  references:
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue  (故障字典权威来源)
    - FreeArkWeb/backend/freearkweb/api/models.py
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/screen_heartbeat_consumer.py
    - FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py
    - agents/freeark-skill/SKILL.md
    - docs/requirements/v0.5.3_dashboard_power_status_card/requirements_spec.md
    - docs/requirements/v0.5.6_device_panel_realtime/requirements_spec.md
```

---

## 1. 背景与动因

### 1.1 项目背景

FreeArk 能耗采集平台的「设备列表」页（`DeviceManagementDeviceListView.vue`）已支持按专有部分（dedicated section）分页展示设备运行状态，包括大屏状态、PLC 状态、系统开关、运行模式、操作入口等列。

「设备面板」页（`DeviceCardsView.vue`）已实现子设备级别的故障状态展示，通过 `FAULT_PARAMS` 集合和 `comm_fault_timeout` 字段定义故障语义，但该信息仅在进入单个设备详情后才可见，无法在列表层级快速感知故障情况。

运维人员在管理多户（最多数十个专有部分）时，需要能在设备列表页一眼看出哪些专有部分存在故障，以便优先处理，减少进入每个设备面板逐一检查的操作负担。

此外，OpenClaw（AI 运维助手，部署在 Pi 127.0.0.1:18789）目前尚无故障查询能力，运维人员无法通过自然语言询问哪些设备有故障。

### 1.2 需求来源

用户原始需求（2026-05-26）：

> 1. 在「设备列表」页面，对于分页显示的专有部分（dedicated section）列表中，在「运行模式」列和「操作」列之间加入一列叫做「故障数量」，统计该专有部分各个子设备故障数量的总和。
> 2. 用字体颜色标记故障数量：没有故障（=0）显示为绿色；故障数量非零则该数字标记为红色。
> 3. 给 OpenClaw 对应开放调用相关 API 查询故障数的接口，并更新其 skill（即让大模型助手能通过工具调用查询故障数）。
> 4. 先更新需求文档、用户故事、设计文档，确认后再开始开发。

### 1.3 版本定位

| 版本 | 主要变更 |
|------|---------|
| v0.5.6 | 设备面板实时参数（MQTT 按需采集） |
| v0.5.7 | CSRF Bug 修复、房型过滤 |
| v0.5.8 | device_param_history 清理健壮性 |
| v0.5.9 | 心跳 Broker 配置化 |
| **v0.5.3-FCC** | **设备列表「故障数量」列 + OpenClaw 故障查询工具（本版本）** |

> 注：本版本编号沿用 v0.5.3 前缀（与 dashboard_power_status_card 子版本并列），完整标识为 v0.5.3-fault-count-column（FCC）。

---

## 2. 需求范围

### 2.1 版本内容

| 包含 | 不包含 |
|------|--------|
| 「设备列表」页「运行模式」列与「操作」列之间新增「故障数量」列 | 修改「设备面板」页现有故障展示逻辑 |
| 故障数量列颜色标记（0=绿色，非0=红色） | 故障明细弹窗/下钻页面 |
| 后端 REST API：按 specific_part 查询故障数 | 故障按严重程度加权计算 |
| 后端故障数缓存机制（避免 device_param_history 全表扫描） | MQTT 故障报警推送 / 通知 |
| **故障数据仅从 `plc_latest_data` 表读取**（OQ-01 裁决，不依赖 MQTT upload 报文） | MQTT 事件驱动缓存失效（已废止，改用短 TTL 定时刷新） |
| OpenClaw skill 新增故障查询工具（2 个工具定义） | OpenClaw Gateway 本体改动 |
| 复用 `DeviceCardsView.vue` 中 `FAULT_PARAMS` 集合及 `comm_fault_timeout` 的故障定义 | 重新定义故障字典或故障码语义 |

### 2.2 不变更项

- `DeviceCardsView.vue` 的故障展示逻辑保持不变（向后兼容）
- 现有 API 的请求/响应结构不变
- `device_param_history` 表结构不变（该表膨胀至 3766 万行/11.3GB，本版本设计严格避免对其全表扫描）
- `PLCLatestData` 表结构不变

---

## 3. 术语定义

| 术语 | 定义 |
|------|------|
| 专有部分（dedicated section） | FreeArk 设备组织层级中的一户，格式如 `3-1-7-702`（楼-单元-层-户），对应 `OwnerInfo.specific_part` |
| 子设备（sub-device） | 一个专有部分下的具体设备实例，由 `PLCLatestData` 中 `specific_part + param_name` 区分 |
| 故障位（fault bit） | 单个 `error_<N>` 字段或 `comm_fault_timeout` 字段处于异常状态 |
| 故障计数（fault count） | 一个专有部分下所有子设备的故障位总数（每个非正常状态字段计为 1） |
| 故障判定 | `comm_fault_timeout != "normal"` 或任意 `error_<N> != "0"` 则该位为故障 |
| FAULT_PARAMS | `DeviceCardsView.vue` 中定义的故障参数名集合（权威故障字典） |
| 故障位图（fault bitmap） | 内存中以 specific_part 为键，记录各故障位当前状态的数据结构 |
| screenMAC | 大屏唯一标识符，对应 `OwnerInfo.unique_id` |

---

## 4. 功能需求

### 4.1 REQ-FUNC-FC-01：设备列表「故障数量」列

**来源引用**：用户原始需求第 1 条

**描述**：在「设备列表」页面表格（`DeviceManagementDeviceListView.vue`）中，在「运行模式」列（`el-table-column label="运行模式"`）与「操作」列（`el-table-column label="操作"`）之间插入一列，列名为「故障数量」。

**验收标准**：
- AC-FC-01-01：「故障数量」列位于「运行模式」列右侧、「操作」列左侧，列宽固定 100px，居中对齐。
- AC-FC-01-02：列值显示该专有部分当前的故障计数整数（如 `0`、`3`、`12`）。
- AC-FC-01-03：当故障数量为 0 时，数字颜色为绿色（语义色 token：`--color-success` / Element Plus `success` 类型，参考 `DeviceCardsView.vue` 中 `.status-ok` 的颜色定义）。
- AC-FC-01-04：当故障数量大于 0 时，数字颜色为红色（语义色 token：`--color-danger` / Element Plus `danger` 类型，参考 `DeviceCardsView.vue` 中 `.status-fault` 的颜色定义）。
- AC-FC-01-05：颜色渲染使用内联样式或与 `DeviceCardsView.vue` 对齐的 CSS class，不使用 `el-tag`（避免破坏列宽与视觉风格）。
- AC-FC-01-06：数据加载中时显示 `—`（Em dash 占位符），与其他列的加载状态一致。
- AC-FC-01-07：「故障数量」列不作为筛选/排序条件（v0.5.3-FCC 不实现列头点击排序）。

### 4.2 REQ-FUNC-FC-02：故障数量数据来源

**来源引用**：用户原始需求第 1 条 + 背景信息 B

**描述**：「故障数量」列的数据通过后端提供，前端不在本地计算。后端在返回设备列表分页数据时，在每行数据中附带 `fault_count` 字段。

> **OQ-01 裁决（2026-05-26）**：故障数据来源**仅从 `plc_latest_data` 表（Django model：`PLCLatestData`，所在 app：`api`）读取**，暂时不依赖 MQTT upload 报文作为触发源。这是数据库表 `plc_latest_data` 中由 `PLCLatestDataHandler._bulk_upsert()` 落库的最新参数值，以 `(specific_part, param_name)` 为唯一键。

**验收标准**：
- AC-FC-02-01：后端 `/api/device-management/device-list/` 响应的每条 result 中新增 `fault_count` 字段（整数，≥0）。
- AC-FC-02-02：`fault_count` 代表该 `specific_part` 下所有子设备当前故障位的总数，计算数据来源为 `plc_latest_data` 表。
- AC-FC-02-03：`fault_count` 的计算规则：对该 `specific_part` 下 `PLCLatestData` 中所有符合故障字段名称的参数，统计值不正常的数量（详见 REQ-FUNC-FC-03）；故障数量最多有 30~60 秒的缓存延迟（由 TTL 控制，详见 REQ-NFR-FC-03）。
- AC-FC-02-04：若某 `specific_part` 在 `PLCLatestData` 中无任何记录，则 `fault_count` 返回 `null`（前端展示为 `—`）。

### 4.3 REQ-FUNC-FC-03：故障判定规则

**来源引用**：背景信息 A（MQTT 抓包分析确认）

**描述**：故障判定规则必须与 `DeviceCardsView.vue` 中已有的故障定义完全一致，不得重新发明新规则。

故障字段分为两类：

| 类别 | 字段名格式 | 正常值 | 故障值 |
|------|-----------|--------|--------|
| PLC 通信故障 | `comm_fault_timeout` | `"normal"` 对应存储值 `0` | 非 `normal`，对应存储值非 `0` |
| 具体故障码位 | `error_<N>`（N 为整数，如 `error_82`、`error_703`） | `"0"` 对应存储值 `0` | `"1"` 或非 `0`，对应存储值非 `0` |

**故障判定逻辑**（Python 伪代码）：
```
对 specific_part 下的 PLCLatestData 记录集 R：
  fault_count = 0
  for record in R:
    if record.param_name == 'comm_fault_timeout' and record.value != 0:
      fault_count += 1
    elif record.param_name 以 'error_' 开头 and record.value != 0:
      fault_count += 1
  return fault_count
```

**验收标准**：
- AC-FC-03-01：`comm_fault_timeout` 的 `PLCLatestData.value` 非 0 时计为 1 个故障。
- AC-FC-03-02：`param_name` 匹配正则 `^error_\d+$` 且 `PLCLatestData.value` 非 0 时计为 1 个故障。
- AC-FC-03-03：其他参数名（如温度、湿度、开关）不纳入故障计数，即便其值异常。
- AC-FC-03-04：同一 `specific_part` 下同名参数只有一条最新记录（由 `PLCLatestData` 的 `unique_together = [['specific_part', 'param_name']]` 约束保证），不重复计数。

### 4.4 REQ-FUNC-FC-04：故障数量后端查询性能

**来源引用**：背景信息 C（`device_param_history` 膨胀严重）

**描述**：故障数量查询必须基于 `PLCLatestData` 表（每设备每参数仅一条最新记录），严禁查询 `DeviceParamHistory` 表（时序历史表，3766 万行/11.3GB）。

**验收标准**：
- AC-FC-04-01：故障数量计算查询仅访问 `plc_latest_data` 表，不访问 `device_param_history` 表。
- AC-FC-04-02：分页列表（默认 20 条/页）的故障数量聚合查询响应时间 P95 ≤ 500ms（在生产 MySQL 192.168.31.98:3306 上测量）。
- AC-FC-04-03：当引入缓存时，缓存命中时的响应时间 P95 ≤ 100ms。

### 4.5 REQ-FUNC-FC-05：故障数量独立查询 API

**来源引用**：用户原始需求第 3 条（OpenClaw 工具调用需要独立 API 端点）

**描述**：提供一个独立的 REST API 端点，支持查询单个或多个专有部分的当前故障数量，供 OpenClaw 工具调用和其他调用方使用。

**接口规格**：

```
GET /api/devices/fault-count/

查询参数：
  specific_part  string（必选）专有部分标识，如 "3-1-7-702"
                 支持逗号分隔多个，如 "3-1-7-702,3-1-7-703"（最多 50 个）

响应（200）：
  {
    "success": true,
    "data": [
      {
        "specific_part": "3-1-7-702",
        "fault_count": 3,
        "fault_details": [
          {"param_name": "comm_fault_timeout", "value": 1},
          {"param_name": "error_82", "value": 1},
          {"param_name": "error_703", "value": 1}
        ],
        "updated_at": "2026-05-26T10:30:00+08:00"
      }
    ],
    "queried_at": "2026-05-26T10:30:05+08:00"
  }

错误响应：
  400 Bad Request  — specific_part 缺失或超过 50 个
  401 Unauthorized — 未登录或 Token 无效
  404 Not Found    — specific_part 在 OwnerInfo 中不存在（数组中该项 fault_count=null）
  500 Internal Server Error — 数据库查询失败
```

**验收标准**：
- AC-FC-05-01：端点路径为 `GET /api/devices/fault-count/`。
- AC-FC-05-02：需要登录鉴权（使用现有 Token/Session 认证，与其他 `/api/devices/` 接口保持一致）。
- AC-FC-05-03：`fault_details` 数组仅包含当前处于故障状态（value != 0）的参数，按 `param_name` 升序排列。
- AC-FC-05-04：`updated_at` 返回该 `specific_part` 在 `PLCLatestData` 中所有相关故障字段的最新 `updated_at` 时间戳。
- AC-FC-05-05：单个 `specific_part` 查询响应时间 P95 ≤ 200ms（无缓存）。
- AC-FC-05-06：批量查询（50 个 specific_part）响应时间 P95 ≤ 2s（无缓存）。

### 4.6 REQ-FUNC-FC-06：OpenClaw skill 新增故障查询工具

**来源引用**：用户原始需求第 3 条

**描述**：在 `agents/freeark-skill/SKILL.md` 中追加两个新的 Tier-1 只读工具，用于让 OpenClaw（方舟龙虾）能通过自然语言查询设备故障数量。

**工具 1：`freeark_get_fault_count`**
- 用途：查询指定专有部分的故障数量和故障详情
- 必需参数：`specific_part`（字符串，支持逗号分隔多个，最多 50 个）
- 返回：故障数量整数 + 故障参数列表 + 数据时间戳

**工具 2：`freeark_get_fault_summary`**
- 用途：查询全系统（或指定楼栋/单元）有故障的专有部分汇总
- 可选参数：`building`（楼栋），`unit`（单元），`min_fault_count`（最少故障数过滤，默认 1）
- 返回：有故障的专有部分列表，按 `fault_count` 降序排列，最多返回 100 条

**验收标准**：
- AC-FC-06-01：`SKILL.md` 的 Tier-1 只读工具表格中新增 `freeark_get_fault_count` 和 `freeark_get_fault_summary`。
- AC-FC-06-02：工具描述清晰说明参数格式和返回结构，使大模型无需外部文档即可正确调用。
- AC-FC-06-03：两个工具均通过统一 CLI 入口调用（与现有 Tier-1 工具保持一致：`freeark_tool.py`）。
- AC-FC-06-04：工具名符合现有命名风格（`freeark_get_` 前缀 + 功能描述）。
- AC-FC-06-05：回退工具实现脚本（`freeark_tool.py`）中新增对两个工具的路由和调用逻辑——此项在确认需求/架构后、进入开发阶段时实现。

---

## 5. 非功能需求

### 5.1 REQ-NFR-FC-01：性能约束

**来源引用**：背景信息 C（`device_param_history` 膨胀问题）

- NFR-FC-01-01：所有故障数量查询严禁查询 `device_param_history` 表。
- NFR-FC-01-02：设备列表页加载（含故障数量）的总响应时间不应超过现有无故障数量列时的 +200ms 以上（即故障数量字段增加的开销 ≤ 200ms）。
- NFR-FC-01-03：缓存引入后，缓存热状态下列表页 P95 响应时间目标 ≤ 800ms（端到端，含前端渲染）。
- NFR-FC-01-04：（已废止，OQ-01 裁决后不再采用 MQTT 事件驱动缓存失效；缓存由短 TTL 自动刷新，见 REQ-NFR-FC-03。）

### 5.2 REQ-NFR-FC-02：向后兼容

- NFR-FC-02-01：`DeviceCardsView.vue`（设备面板）的故障展示功能不受影响，所有现有 `FAULT_PARAMS` 定义和颜色规则保持不变。
- NFR-FC-02-02：现有 `/api/device-management/device-list/` API 的其他字段结构不变，仅新增 `fault_count` 字段，已有客户端可忽略新字段（向后兼容扩展）。
- NFR-FC-02-03：OpenClaw skill 中现有 14 个 Tier-1 工具和 5 个 Tier-2 工具的行为不变，仅追加新工具定义。

### 5.3 REQ-NFR-FC-03：数据一致性

- NFR-FC-03-01：故障数量以 `PLCLatestData`（`plc_latest_data` 表）中的最新数据为准，**与 MQTT 上报时序解耦**；当 `PLCLatestDataHandler` 落库新数据后，故障数量在下次缓存 TTL 过期（30~60 秒）后即反映最新状态。
- NFR-FC-03-02：当 MQTT 长时间未收到某 specific_part 的上报（大屏离线），`PLCLatestData` 中的数据不自动清零，故障数量保持最后一次上报时的值，并在 `updated_at` 字段反映数据时效。
- NFR-FC-03-03：缓存 TTL 设定为 30~60 秒（由架构设计最终确认），过期后自动从 `plc_latest_data` 重新查询；冷启动时同样直接从 DB 计算，确保兜底准确性。
- NFR-FC-03-04：**故障数量的最大可见延迟 = 缓存 TTL**（即运维人员在故障发生后最多等待 TTL 秒刷新页面才能看到更新；详见 US-FC-05 AC-FC-05-01 的 30 秒约束）。

### 5.4 REQ-NFR-FC-04：安全与鉴权

- NFR-FC-04-01：`/api/devices/fault-count/` 端点需要用户登录（与其他设备 API 一致），不开放匿名访问。
- NFR-FC-04-02：OpenClaw 工具调用通过现有 FreeArk API Token 鉴权（`FREEARK_AGENT_TOKEN` 环境变量），与其他 Tier-1 工具一致。
- NFR-FC-04-03：故障详情（`fault_details`）仅返回参数名和值，不返回任何业主 PII 信息。

---

## 6. 故障字典（来自现有代码，仅引用不修改）

以下故障字段定义引自 `DeviceCardsView.vue`（`FAULT_PARAMS` 集合），**本需求文档不修改这些定义，仅引用作为故障计数依据**：

### 6.1 FAULT_PARAMS（按子设备分类）

| 子设备 | 参数名 | 故障含义 |
|--------|--------|---------|
| 客厅温控面板 | `living_room_temp_sensor_error` | 内置温度传感器故障 |
| 客厅温控面板 | `living_room_humidity_sensor_error` | 湿度传感器故障 |
| 客厅温控面板 | `living_room_external_temp_sensor_error` | 外置温度传感器故障 |
| 客厅温控面板 | `living_room_communication_error` | 通讯故障 |
| 书房温控面板 | `study_room_temp_sensor_error` | 内置温度传感器故障 |
| 书房温控面板 | `study_room_humidity_sensor_error` | 湿度传感器故障 |
| 书房温控面板 | `study_room_external_temp_sensor_error` | 外置温度传感器故障 |
| 书房温控面板 | `study_room_communication_error` | 通讯故障 |
| 主卧温控面板 | `bedroom_temp_sensor_error` | 内置温度传感器故障 |
| 主卧温控面板 | `bedroom_humidity_sensor_error` | 湿度传感器故障 |
| 主卧温控面板 | `bedroom_external_temp_sensor_error` | 外置温度传感器故障 |
| 主卧温控面板 | `bedroom_communication_error` | 通讯故障 |
| 儿童房温控面板 | `children_room_temp_sensor_error` | 内置温度传感器故障 |
| 儿童房温控面板 | `children_room_humidity_sensor_error` | 湿度传感器故障 |
| 儿童房温控面板 | `children_room_external_temp_sensor_error` | 外置温度传感器故障 |
| 儿童房温控面板 | `children_room_communication_error` | 通讯故障 |
| 第四儿童房温控面板 | `fourth_children_room_temp_sensor_error` | 内置温度传感器故障 |
| 第四儿童房温控面板 | `fourth_children_room_humidity_sensor_error` | 湿度传感器故障 |
| 第四儿童房温控面板 | `fourth_children_room_external_temp_sensor_error` | 外置温度传感器故障 |
| 第四儿童房温控面板 | `fourth_children_room_communication_error` | 通讯故障 |
| 新风机 | `fresh_air_unit_stop_error` | 新风机停机故障 |
| 新风机 | `fresh_air_unit_communication_error` | 新风机通讯故障 |
| 水利模块 | `hydraulic_module_low_temp_error` | 水利模块低温保护故障 |
| 能耗表 | `energy_meter_status_communication_error` | 能耗表通讯故障 |
| 空气品质传感器 | `air_quality_sensor_communication_error` | 空气品质传感器通讯故障 |

> **注意**：新风机还有一个 `fresh_air_fault_status` 字段，其值为位域整数，展开为 9 个 `fresh_air_fault_bit_0` 到 `fresh_air_fault_bit_8`（见 `DeviceCardsView.vue` `FRESH_AIR_FAULT_BITS` 常量）。这些位的计数方式需要架构阶段进一步确认（见开放问题 OQ-03）。

### 6.2 comm_fault_timeout 字段

`comm_fault_timeout` 来自 MQTT `DeviceStatusUpdate` 报文的顶层字段，正常值为字符串 `"normal"`，在 `PLCLatestData` 中存储为整数（`0` = 正常，非 `0` = 故障）。该字段的 `param_name` 为 `comm_fault_timeout`。

### 6.3 error_N 字段

`error_<N>` 字段（如 `error_82`、`error_703`）来自 MQTT `DeviceStatusUpdate` 报文，`param_name` 以 `error_` 前缀加整数编号。正常值为 `"0"`（存储为 `0`），异常为非零值。

> **说明**：FAULT_PARAMS 中的具体参数名（如 `living_room_temp_sensor_error`）与 `error_<N>` 是否有直接映射关系，需要业务方补充确认（见开放问题 OQ-01）。架构设计时可同时覆盖两种命名模式的检测。

---

## 7. 接口约束

### 7.1 前端数据来源约束

- 「故障数量」列数据由后端在分页列表 API 响应中携带，不单独发 XHR 请求。
- 前端不在本地计算故障数，所有业务逻辑在后端。

### 7.2 颜色语义 Token 约束

前端颜色渲染必须使用与 `DeviceCardsView.vue` 一致的语义 Token：

```css
/* 引自 DeviceCardsView.vue */
.status-ok   { color: var(--color-status-ok);    /* = var(--color-success) */ }
.status-fault { color: var(--color-status-fault); /* = var(--color-danger)  */ }
```

不得使用硬编码 hex 色值（如 `#67c23a`、`#f56c6c`），以保证主题一致性。

---

## 8. 版本约束与里程碑

| 里程碑 | 交付物 |
|--------|--------|
| M1：需求确认 | 本文档 + user_stories.md |
| M2：架构确认 | architecture_design.md + module_design.md |
| M3：开发完成 | 后端 API + 前端列 + SKILL.md 更新 + freeark_tool.py 更新 |
| M4：测试通过 | 单元测试 + 集成测试报告 |
| M5：部署上线 | 通过 git pull 部署到 192.168.31.51 |

---

## 附录 A：引用文件说明

| 文件 | 引用原因 |
|------|---------|
| `DeviceCardsView.vue` | `FAULT_PARAMS`、`FRESH_AIR_FAULT_BITS`、颜色 Token 定义的权威来源 |
| `DeviceManagementDeviceListView.vue` | 待修改的设备列表前端组件 |
| `models.py` | `PLCLatestData`、`OwnerInfo` 模型定义 |
| `mqtt_handlers.py` | 现有 MQTT 消息处理流程（故障位图更新将插入此处） |
| `screen_heartbeat_consumer.py` | MQTT broker 配置参考（`DeviceStatusUpdate` 报文来自同一 broker） |
| `openclaw_adapter.py` | OpenClaw 集成现有实现（工具调用通过 FreeArk REST API，不直接调用 OpenClaw） |
| `agents/freeark-skill/SKILL.md` | 待追加工具定义的 Skill 文件 |
