# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - scripts/tmp/sniff_2860fae9a34ab8a9_20260525_235217.ndjson
    - FreeArkWeb/backend/freearkweb/api/fault_utils.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/screen_heartbeat_consumer.py
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - docs/architecture/architecture_design_v0.5.3_fault_count_column.md
    - docs/requirements/v0.5.3_fault_count_column/requirements_spec.md
    - docs/requirements/v0.5.9_heartbeat_broker_config/requirements_spec.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始草稿，基于 MQTT 抓包分析报告与用户原始需求，含开放问题 OQ-01~OQ-12 |
| 0.2.0-DRAFT | 2026-05-27 | 落地用户裁决（OQ-01/02/03/05/08/10/13）及默认值（OQ-04/06/07/09/11/12/14）；版本号从 v0.5.4 重编为 v0.6.0；数据模型最终化；新增风险条目 R-08/R-09/R-10；更新非功能需求 |

---

## 版本号决策记录

**决策**：本需求采用 **v0.6.0** 作为版本号（原草稿为 v0.5.4-FM）。

**理由**：

- v0.5.4 槽位已被 `mqtt_pipeline_perf_p1` 占用。
- v0.5.5、v0.5.6、v0.5.7、v0.5.9 均已被其他特性占用（见各 docs/requirements/、docs/architecture/ 目录）。
- v0.5.8 虽然空闲，但故障管理是一个独立的、用户可见的核心功能模块（新 systemd 服务 + 新 DB 表 + 新前端页面），语义上值得 minor 版本跃迁。
- **v0.6.0** 在 requirements、architecture、deployment、development 四个文档目录下均未被占用，是最干净的选择。

---

## 1. 背景与动因

### 1.1 项目背景

FreeArk 楼宇 PLC 数据采集平台通过 MQTT Broker（`wss://www.ttqingjiao.site:8084/mqtt`，EMQX WSS）接收各大屏上报的设备状态报文，topic 格式为 `/screen/upload/screen/to/cloud/<screenMAC>`。每条报文（`DeviceStatusUpdate`）携带某子设备在该采样时刻的完整状态快照，约 2 秒/条/子设备，单大屏 10 分钟内可产生 285 条以上。

现有系统（v0.5.3-FCC）已在「设备列表」页面显示当前快照的故障数量（从 `plc_latest_data` 表实时计算），但：

- **无时间维度**：无法追溯某故障何时发生、持续多久、何时恢复。
- **无历史记录**：设备重启或大屏重连后，历史故障信息丢失。
- **无专用故障视图**：运维人员无法按房号、时间段、故障类型快速检索历史故障。

### 1.2 需求来源

用户原始需求（2026-05-27）：

> 1. 自由方舟有一个 systemd 专门订阅这个 topic，里边的信息包含故障或者预警的，保存到数据库。
> 2. 这些信息因为会频繁的插入数据库，采用统一的缓存机制（进程内）和其他的业务处理保持一致，避免频繁的数据库读写。
> 3. 设备管理页面增加一个"故障管理"，能够根据房号、故障时间段、故障类型、故障设备过滤。表格分页，能显示相应信息，特别是故障码、故障信息，另外操作列可以查看设备面板。
> 4. 先更新需求和用户故事，确认后再开发。

### 1.3 版本定位

| 版本 | 主要变更 |
|------|---------|
| v0.5.3-FCC | 设备列表「故障数量」列（当前快照，plc_latest_data） |
| v0.5.9 | 心跳 Broker 配置化（heartbeat_broker_config.json） |
| **v0.6.0-FM** | **MQTT 故障事件持久化 + 故障管理页面（本版本）** |

---

## 2. 范围

### 2.1 本版本范围内（In Scope）

| 编号 | 范围项 |
|------|--------|
| S-01 | 新增独立 systemd 服务 `freeark-fault-consumer`，使用通配符订阅 `/screen/upload/screen/to/cloud/+` 覆盖所有大屏，识别故障/恢复事件，写入 `fault_event` 表 |
| S-02 | 进程内状态机缓存：使用 `(specific_part, device_sn, fault_code) → (event_id, is_active)` 内存字典（Python dict），避免每条 MQTT 报文触发 DB 读写；进程重启时从 DB 重建 |
| S-03 | 「设备管理」模块下新增独立页面「故障管理」（`FaultManagementView.vue`），支持多维过滤 + 分页表格 |
| S-04 | 过滤维度：房号（`specific_part`，模糊匹配）、故障时间段（`first_seen_at` 区间，默认最近 7 天）、故障类型（`fault_type`，大类多选）、故障设备（sub_type 名，多选） |
| S-05 | 表格列：房号、设备标识、故障码、故障描述（本期同故障码字符串）、大类、严重级别、首次发生时间、最后活跃时间、恢复时间、是否活跃；筛选区上方「只看未恢复」toggle（默认 OFF） |
| S-06 | 操作列：「查看设备面板」按钮，跳转 `router.push({ name: 'DeviceCards', query: { specific_part: row.specific_part } })` |
| S-07 | 后端 REST API：支持故障事件查询（分页 + 多维过滤） |
| S-08 | 故障事件状态机：`active → recovered`（当同一 key 的故障字段恢复正常时更新 `recovered_at`, `is_active=False`）；每条 MQTT 报文都更新内存表 `last_seen_at`，但仅"首次出现"（is_active=False → True 跳变）写新记录 |
| S-09 | 新增 `freeark-fault-cleanup` systemd 服务，每天 03:30 分批硬删除 `first_seen_at < NOW() - INTERVAL 90 DAY` 的记录（与 `freeark-dph-cleanup` 同模式） |

### 2.2 本版本范围外（Out of Scope）

| 编号 | 排除项 | 说明 |
|------|--------|------|
| OOS-01 | Redis 缓存迁移（AB-001） | 仍使用进程内 Python dict 方案（比 LocMemCache 更轻量，专为状态机设计） |
| OOS-02 | 告警通知（钉钉/短信/邮件） | 本期仅做记录与查询；**用户裁决 OQ-09**：out of scope，记入演进路线 |
| OOS-03 | 故障码中文描述字典维护 UI | 本期 `fault_message` 字段直接写故障码字符串；字典表为未来增强项（AB-004） |
| OOS-04 | OpenClaw 故障历史查询工具 | 本期不扩展 OpenClaw skill |
| OOS-05 | 多进程/多实例部署 | freeark-fault-consumer 按单进程设计，状态机在进程内 |

---

## 3. 功能需求

### FR-FM-01：MQTT 故障订阅服务（systemd）

**描述**：新增独立 Django Management Command `fault_consumer`，由 systemd 服务 `freeark-fault-consumer` 管理，使用通配符订阅 MQTT upload topic，持续运行，识别 MQTT 报文中的故障字段并持久化故障事件。

**输入**：
- MQTT broker 连接参数（复用 `heartbeat_broker_config.json` 格式，独立 client_id）
- 订阅 topic：`/screen/upload/screen/to/cloud/+`（通配符，一次性覆盖所有大屏 MAC；**用户裁决 OQ-10**：broker ACL 已确认允许 `+` 通配符）
- `DeviceStatusUpdate` 报文（`header.name = "DeviceStatusUpdate"`，`payload.data.deviceSn`、`payload.data.productCode`、`payload.data.items[]`）

**输出**：
- `fault_event` 表新增记录（故障首次出现 / 重新触发时）
- `fault_event` 表更新 `last_seen_at` / `recovered_at` / `is_active`（重复出现 / 恢复时）
- 日志输出（journald）：每次状态变化、每次 DB 写入

**处理规则**：
1. 从报文 `items[]` 中识别故障字段（判定规则见 FR-FM-06）
2. 通过 MAC → specific_part 映射（从 `OwnerInfo` 表加载）定位 `specific_part`
3. 通过 `deviceSn` 定位 `device_sn`；`productCode` 记录为 `product_code`
4. 故障事件去重与状态机：见 FR-FM-02
5. 无需维护 screenMAC 白名单；broker 推什么订阅什么（**用户裁决 OQ-11**）

**约束**：
- 服务命名为 `freeark-fault-consumer`，骨架参考 `freeark-screen-heartbeat` 但独立实现，不复用代码
- 使用 paho-mqtt 1.x API（`>=1.6.1,<2.0`，与心跳服务版本一致）
- 每次 DB 操作前调用 `django.db.close_old_connections()`
- 启动时用 `loop_forever(retry_first_connection=True)` 实现自动重连

---

### FR-FM-02：故障事件去重与状态机（进程内内存表）

**描述**：使用进程内 Python dict 维护已知故障的状态，实现故障去重与 `last_seen_at` 更新节流。

**状态机设计（用户裁决 OQ-03，方案 C 变体）**：

采用**"首次出现写记录，重复上报只更新内存，恢复时更新 DB"**策略：

```
[内存表 miss，或 is_active=False] → 故障字段 active
  → INSERT fault_event(is_active=True, first_seen_at=now())
  → 内存表写入: key → (event_id, is_active=True)

[内存表 hit, is_active=True] → 故障字段 active
  → 仅更新内存表 last_seen_at（不写 DB）
  → 每条 MQTT 报文都更新内存中的 last_seen_at（OQ-03 裁决：内存更新无限制）

[内存表 hit, is_active=True] → 故障字段 normal/0
  → UPDATE fault_event SET recovered_at=now(), is_active=False, last_seen_at=内存中值 WHERE id=event_id
  → 内存表更新: is_active=False

[进程重启]
  → 启动时查 DB: SELECT * FROM fault_event WHERE is_active=True
  → 重建内存表（LIMIT 10000 保护）
  → 重建后收到重复 INSERT → DB unique 约束兜底，IntegrityError → 捕获改为 UPDATE
```

**内存表 Key**：`(specific_part, device_sn, fault_code)` → `{event_id: int, is_active: bool, last_seen_at: datetime}`

**约束**：
- 进程内内存表仅 `freeark-fault-consumer` 使用；freeark-backend（API 查询）直查 DB，不共享内存
- 内存表不设 TTL（进程重启时重建，不依赖 LocMemCache）
- 具体 DB 写入时机与事务设计由 system-architect 在架构阶段确认

---

### FR-FM-03：故障事件数据模型

**描述**：新增 `fault_event` 数据表，存储每次设备故障的历史记录。

**最终字段清单（用户裁决 OQ-01 后）**：

| 字段名 | 类型（需求语义） | 说明 |
|--------|----------------|------|
| `id` | BigAutoField（PK） | 主键 |
| `specific_part` | VARCHAR(64) | 房号（专有部分），关联 OwnerInfo；INDEX |
| `device_sn` | VARCHAR(64) | 设备序列号（来自 MQTT `deviceSn`，存字符串兼容非整数 SN） |
| `product_code` | VARCHAR(32) | 产品编码（来自 MQTT `productCode`） |
| `fault_code` | VARCHAR(64) | 故障码，如 `error_82`、`comm_fault_timeout`、`fresh_air_fault_bit_4` |
| `fault_type` | VARCHAR(16) | 故障大类：`comm` / `sensor` / `fresh_air` / `other_error` |
| `fault_message` | VARCHAR(255) | **本期同 fault_code 字符串**（无中文字典，用户裁决 OQ-05）；未来扩展为中文描述 |
| `severity` | VARCHAR(8) | 严重级别：`error` / `warning`（分级规则见 FR-FM-06） |
| `first_seen_at` | DATETIME | 故障首次出现时间（服务器接收时间 `timezone.now()`）；INDEX |
| `last_seen_at` | DATETIME | 最近一次内存确认仍活跃的时间（进程内维护，恢复时写回 DB） |
| `recovered_at` | DATETIME NULL | 故障恢复时间；NULL 表示仍活跃 |
| `is_active` | BOOL | 是否当前活跃；INDEX |
| `created_at` | DATETIME | 记录创建时间（auto_now_add） |
| `updated_at` | DATETIME | 记录最后更新时间（auto_now） |

> 注：**不保留 `raw_payload_snippet`**（用户裁决 OQ-01）。
> 注：**不保留 `screen_mac`**（OQ-10 通配符方案确认后，screen_mac 对业务无额外价值，去掉以简化模型）。
> 注：`fault_code_dict` 表（OQ-05）本期**不创建**，中文字典为未来增强项（AB-004）。

**关键查询场景（供 system-architect 设计索引参考）**：

| 查询场景 | 涉及字段 |
|----------|----------|
| 按房号过滤活跃故障 | `specific_part`, `is_active` |
| 按时间段过滤 | `first_seen_at` |
| 按时间段 + 活跃状态 | `first_seen_at`, `is_active` |
| 进程重启重建缓存 | `is_active=True`（全表扫描，LIMIT 10000） |
| 清理过期记录 | `first_seen_at < threshold` |

**推荐索引（建议，由 system-architect 最终确认）**：
```
INDEX(specific_part, is_active)
INDEX(first_seen_at, is_active)
UNIQUE(specific_part, device_sn, fault_code, first_seen_at)  -- 防重；同一故障重新触发视为新行
```

> 具体 DDL 和 Django migration 由 system-architect 在架构阶段定。

---

### FR-FM-04：故障管理页面（前端）

**描述**：在「设备管理」模块下新增独立路由页面「故障管理」，路径 `/device-management/faults`，组件 `FaultManagementView.vue`。

**过滤条件区**（用户裁决 OQ-06 + OQ-07，均已落地）：

| 过滤项 | 控件 | 行为（已确定） |
|--------|------|-------------|
| 房号 | 输入框 | `LIKE '%input%'` 模糊匹配（**用户裁决 OQ-06**：contains 模糊） |
| 故障时间段 | 日期范围选择器 | `first_seen_at` 落在 `[start_time, end_time]` 区间；**前端默认填"最近 7 天"**（**默认采纳 OQ-06，可改**） |
| 故障类型 | 多选下拉 | 大类多选（`comm` / `sensor` / `fresh_air` / `other_error`）；大类→具体字段映射由后端常量定义并通过 API 暴露（**默认采纳 OQ-04，可改**） |
| 故障设备 | 多选下拉 | 按 sub_type 名多选（复用 v0.5.3-FCC 已有的 sub_type 集合）（**用户裁决 OQ-06**） |

**筛选区上方 toggle**（**默认采纳 OQ-07，可改**）：
- 「只看未恢复」toggle，默认 **OFF**
- 勾选时等价于追加 `WHERE is_active=True` 条件

**表格列**：

| 列名 | 字段 | 说明 |
|------|------|------|
| 房号 | `specific_part` | 专有部分 |
| 设备标识 | `device_sn` + sub_type | 显示 SN + 设备名 |
| 故障码 | `fault_code` | 原始编码字符串，如 `error_82` |
| 故障描述 | `fault_message` | 本期同 fault_code（OQ-05 裁决：无字典，显示编号字符串） |
| 故障类型 | `fault_type` | 大类标签 |
| 严重级别 | `severity` | error（红色） / warning（橙色） |
| 首次发生 | `first_seen_at` | 本地时间（Asia/Shanghai） |
| 最后活跃 | `last_seen_at` | 本地时间 |
| 恢复时间 | `recovered_at` | NULL 则显示"-" |
| 状态 | `is_active` | 活跃（红色）/已恢复（灰色） |
| 操作 | — | 「查看设备面板」按钮 |

**分页**：
- 每页默认 20 条，支持切换（10/20/50）

**操作列「查看设备面板」**（**用户裁决 OQ-12**）：
```javascript
router.push({ name: 'DeviceCards', query: { specific_part: row.specific_part } })
```
不附加子设备高亮参数（保持简单）。

---

### FR-FM-05：故障事件查询 REST API

**描述**：新增后端接口供「故障管理」页面调用。

**接口**：`GET /api/devices/fault-events/`

**查询参数**（用户裁决 OQ-06 后最终版）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `specific_part` | string（可选） | 房号，`LIKE '%value%'` 模糊匹配 |
| `fault_type` | string（可选，多值） | 故障大类，多选（逗号分隔或重复参数） |
| `sub_type` | string（可选，多值） | 子设备名，多选 |
| `is_active` | boolean（可选） | 仅活跃故障（对应「只看未恢复」toggle） |
| `first_seen_after` | ISO8601（可选） | 时间段起点，默认 now - 7 天 |
| `first_seen_before` | ISO8601（可选） | 时间段终点 |
| `page` | integer | 分页，默认 1 |
| `page_size` | integer | 每页条数，默认 20，最大 100 |

**响应格式**：
```json
{
  "count": 总条数,
  "next": "分页 URL | null",
  "previous": "分页 URL | null",
  "results": [ { fault_event 对象 }, ... ]
}
```

**附加接口**：`GET /api/devices/fault-event-categories/`
- 返回大类 → 具体字段映射的后端常量（供前端故障类型过滤下拉使用，**默认采纳 OQ-04**）

**权限**：`IsAuthenticated`（与现有设备管理接口一致）

---

### FR-FM-06：故障类型与严重级别判定规则

**描述**：`fault_consumer` 服务写入 `fault_event.fault_type` 和 `severity` 时，按以下规则判定（**用户裁决 OQ-02 后最终版**）：

| 故障码模式 | `fault_type` | `severity` | 说明 |
|------------|-------------|-----------|------|
| `comm_fault_timeout` | `comm` | `error` | PLC 通信故障（用户裁决 OQ-02） |
| `*_communication_error` 后缀 | `comm` | `error` | 子设备通信故障（用户裁决 OQ-02） |
| `*_temp_sensor_error` 后缀 | `sensor` | `error` | 温度传感器故障（用户裁决 OQ-02） |
| `*_humidity_sensor_error` 后缀 | `sensor` | `error` | 湿度传感器故障（用户裁决 OQ-02） |
| `*_external_temp_sensor_error` 后缀 | `sensor` | `error` | 外部温度传感器故障（用户裁决 OQ-02） |
| `fresh_air_unit_stop_error` | `fresh_air` | `error` | 新风机停机故障（用户裁决 OQ-02） |
| `fresh_air_unit_communication_error` | `comm` | `error` | 新风机通信故障（用户裁决 OQ-02） |
| `fresh_air_fault_bit_*`（位域 bit） | `fresh_air` | `warning` | 新风位域故障位（用户裁决 OQ-02） |
| `hydraulic_module_low_temp_error` | `other_error` | `error` | 水力模块低温故障（用户裁决 OQ-02） |
| `energy_meter_status_communication_error` | `comm` | `error` | 电表通信故障（用户裁决 OQ-02） |
| `air_quality_sensor_communication_error` | `comm` | `error` | 空气质量传感器通信故障（用户裁决 OQ-02） |
| `error_<N>`（整数 N） | `other_error` | `error` | 所有 error_N 均为 error（用户裁决 OQ-02） |

> 注：`fault_type` 枚举值变更：原草稿 `plc_error` 统一改为 `other_error`（与前端大类对齐，**默认采纳 OQ-04，可改**）。

**故障触发判定**（判断某字段是否处于故障态）：
- `comm_fault_timeout`：值不等于 `"normal"` 时视为故障
- `error_<N>`：值不等于 `"0"`（字符串）且不等于 `0`（整数）时视为故障
- 其他具名故障字段（`FAULT_PARAM_NAMES`，见 fault_utils.py）：值不等于 `0` 时视为故障

---

### FR-FM-07：故障事件数据保留与清理服务

**描述**：新增独立 systemd 服务 `freeark-fault-cleanup`，定期清理过期故障记录（**用户裁决 OQ-08**）。

**保留策略**：
- 保留天数：**90 天**（`first_seen_at < NOW() - INTERVAL 90 DAY` 的记录硬删除）
- 活跃故障（`is_active=True`）**不删除**，无论 first_seen_at 多早
- 执行时间：每天 **03:30**
- 执行方式：分批删除（每批 ≤ 1000 行，避免大事务锁表），与 `freeark-dph-cleanup` 同模式

**服务配置**：
```
freeark-fault-cleanup.service / .timer
  OnCalendar=*-*-* 03:30:00
  执行: python manage.py fault_cleanup --days=90 --batch-size=1000
```

---

## 4. 非功能需求

### 4.1 性能

| 指标 | 目标值 | 说明 |
|------|--------|------|
| MQTT 报文处理延迟 | ≤ 500ms / 条 | 缓存命中路径（内存表 hit）不写 DB |
| 故障事件 DB 写入延迟 | ≤ 2s（状态变化路径） | 仅"首次出现"和"恢复"时写 DB |
| 故障管理页面初次加载 | ≤ 3s（生产环境） | API 查询 + 前端渲染 |
| API 查询响应时间 | ≤ 1s（正常负载，有索引） | 树莓派 MySQL 9.4 @ 192.168.31.98 |
| fault_event 表行数上限 | 吸取 dph 36M 行教训；清理服务保障 90 天滚动窗口 | 预期月增量远小于 dph（事件驱动写入） |

### 4.2 可靠性

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 服务自动重启 | `Restart=on-failure, RestartSec=30s` | 参考心跳服务 systemd 配置 |
| MQTT 自动重连 | `loop_forever(retry_first_connection=True)` | broker 抖动时自动恢复 |
| 进程重启后状态机重建 | 启动时从 DB 加载所有 `is_active=True` 的记录重建内存表（**用户裁决 OQ-14**） | 避免进程重启后重复插入相同故障 |
| DB 连接超时保护 | 每次操作前 `close_old_connections()` | 与心跳服务一致 |
| 缺失 specific_part 映射时的容错 | 记录 WARNING 日志，跳过 | MAC 未在 OwnerInfo 注册时的降级处理 |

### 4.3 内存估算（新增，针对进程内状态机）

| 估算项 | 值 |
|--------|-----|
| 典型规模 | 100 楼 × 10 屏 × 9 设备 × 平均 5 故障码 = **45,000 条** |
| 每条内存占用 | 约 200 字节（key tuple + dict value，Python 对象开销） |
| 总估算 | 45,000 × 200 B ≈ **9 MB** |
| 结论 | 在树莓派（2~4 GB RAM）上完全可接受；无需内存上限保护（正常情况下活跃故障数远小于 45,000） |

> 注：进程启动重建查询加 `LIMIT 10000` 作为异常保护。

### 4.4 安全

| 要求 | 说明 |
|------|------|
| MQTT 连接使用 WSS（TLS） | broker `wss://www.ttqingjiao.site:8084/mqtt`，与心跳服务一致 |
| broker 凭证管理 | 存储在 `heartbeat_broker_config.json`（独立 client_id），不硬编码在代码中 |
| API 鉴权 | `IsAuthenticated`，与现有接口一致 |
| 日志中不输出 broker 密码 | 仅记录 host/port/protocol |

### 4.5 可维护性

| 要求 | 说明 |
|------|------|
| 日志级别 | DEBUG（状态判断）、INFO（状态变化、DB 写入）、WARNING（缓存 miss、映射缺失）、ERROR（连接失败、DB 异常） |
| journald 可查 | 使用 Python logging，systemd 自动捕获 |
| 测试策略 | 单元测试覆盖故障判定规则（`is_fault_field()`）；集成测试覆盖状态机（首次出现、重复上报、恢复）；使用 SQLite 测试 DB |

---

## 5. 数据需求

### 5.1 数据模型最终字段（完整版）

```
fault_event (新增)
  id             BIGINT PK
  specific_part  VARCHAR(64)  INDEX
  device_sn      VARCHAR(64)
  product_code   VARCHAR(32)
  fault_code     VARCHAR(64)
  fault_type     VARCHAR(16)   -- 'comm' / 'sensor' / 'fresh_air' / 'other_error'
  fault_message  VARCHAR(255)  -- 本期同 fault_code 字符串（OQ-05：无字典）
  severity       VARCHAR(8)    -- 'error' / 'warning'
  first_seen_at  DATETIME      INDEX
  last_seen_at   DATETIME
  recovered_at   DATETIME NULL
  is_active      BOOL          INDEX
  created_at     DATETIME      auto_now_add
  updated_at     DATETIME      auto_now

  UNIQUE(specific_part, device_sn, fault_code, first_seen_at)
  INDEX(specific_part, is_active)
  INDEX(first_seen_at, is_active)
```

> 注：`fault_code_dict` 表**本期不创建**（OQ-05 裁决）。

### 5.2 数据量估算

- 正常运行期：DB 写入频率极低（仅故障发生/恢复时，事件驱动）
- 故障爆发期：状态机去重确保每个 `(specific_part, device_sn, fault_code)` 组合在同一活跃周期内只写一次 INSERT
- 与 device_param_history（每次全量写入）不同，预期月级别增量远小于 dph
- 90 天清理保障表行数可控

### 5.3 数据保留策略（已确定，用户裁决 OQ-08）

- 保留天数：90 天（`first_seen_at` 计算）
- 清理方式：硬删除，分批（每批 ≤ 1000 行）
- 清理服务：`freeark-fault-cleanup`，每天 03:30 执行
- 活跃故障（`is_active=True`）不受清理影响

---

## 6. 依赖与假设

### 6.1 依赖

| 依赖项 | 类型 | 说明 |
|--------|------|------|
| v0.5.3-FCC `fault_utils.py` | 代码依赖 | `FAULT_PARAM_NAMES`、`_ERROR_N_PATTERN` 可复用；`invalidate_fault_count_cache` 钩子本期不调用（保持 AB-002 待决状态） |
| `heartbeat_broker_config.json` | 配置依赖 | broker 连接参数，fault_consumer 沿用格式，使用独立 client_id |
| `OwnerInfo.unique_id` (screenMAC) | DB 依赖 | MAC → specific_part 映射必须预先在 OwnerInfo 表中存在 |
| paho-mqtt `>=1.6.1,<2.0` | 库依赖 | 已在 requirements.txt 中，无需新增 |
| MySQL 9.4 @ 192.168.31.98 | 生产 DB | 新表 migration 需在生产 DB 执行 |

### 6.2 假设

| 编号 | 假设内容 |
|------|---------|
| A-01 | broker ACL 允许通配符订阅 `/screen/upload/screen/to/cloud/+`（**用户裁决 OQ-10 已确认**） |
| A-02 | `DeviceStatusUpdate` 报文格式与 2026-05-25 抓包样本一致，不会有破坏性变更 |
| A-03 | `error_<N>` 值为 `"0"`（字符串）表示正常，非零表示故障 |
| A-04 | `comm_fault_timeout` 值为 `"normal"`（字符串）表示正常，其他值表示故障 |
| A-05 | 单进程 freeark-fault-consumer 足以处理当前规模 |
| A-06 | 生产服务器树莓派 192.168.31.51 可承载再增加两个 systemd 常驻服务（fault-consumer + fault-cleanup） |
| A-07 | 前端路由复用现有 Vue Router 的设备管理模块 |
| A-08 | 无需维护 screenMAC 白名单，broker 推什么订阅什么（**用户裁决 OQ-11**） |

---

## 7. 风险

| 风险编号 | 描述 | 来源 | 概率 | 影响 | 缓解措施 |
|----------|------|------|------|------|---------|
| R-01 | fault_event 表膨胀（类比 device_param_history 36M 行 / 11.3GB 教训） | KB KE-PM-008 | 中（正常低，故障频发期高） | 高 | 90 天清理服务；状态机去重控制写入频率；监控表行数 |
| R-02 | 进程内缓存与 API 查询服务（freeark-backend）状态不一致 | 架构约束 | 高 | 低 | 明确说明 fault_consumer 缓存仅用于写入去重；API 直查 DB |
| R-03 | broker ACL 变更不再允许通配符订阅 | 用户裁决 OQ-10 | 低（当前已确认允许） | 高 | **风险已知**：当 broker ACL 收紧时，fallback 到按 MAC 订阅（从 OwnerInfo 动态加载 MAC 列表逐个订阅）；此风险记入架构待办 |
| R-04 | MQTT 报文格式在大屏固件升级后变化，导致解析失败 | 外部依赖 | 低 | 中 | 日志记录解析失败的原始报文前 256 字节；告警并跳过，不崩溃 |
| R-05 | AB-002 与本需求的缓存失效钩子冲突 | 架构 backlog | 低 | 中 | 本期 `invalidate_fault_count_cache` 默认不调用；AB-002 待决状态不变 |
| R-06 | 树莓派 MySQL 9.4 在 migration 执行期间短暂锁表 | 生产 DB 约束 | 低 | 中 | migration 在低负载时段执行；新表不影响现有表 |
| R-07 | 故障码字典缺失，前端只能显示原始编码 | OQ-05 裁决 | 确定（本期无字典） | 中（可接受） | 本期 `fault_message` 直接写故障码字符串；字典为 AB-004 |
| **R-08** | **broker ACL 收紧不再允许通配符订阅 → fallback 到逐 MAC 订阅** | **OQ-10 裁决后新增** | 低（当前已确认） | 高 | fallback 方案：从 OwnerInfo 动态读取 MAC 列表，逐个订阅；需维护 MAC 列表更新机制 |
| **R-09** | **进程崩溃丢失内存状态机 → 重启时从 DB 重建** | **OQ-03 方案 C + NFR** | 高（重启必然发生） | 低（重建后恢复） | 重启时加载 `is_active=True` 记录重建；DB unique 约束兜底防重复 INSERT；重建查询 LIMIT 10000 |
| **R-10** | **MQTT 漏消息导致"已恢复故障"仍显示 active（stale active）** | **进程内状态机设计** | 低中（网络抖动时发生） | 中 | 监控层面：心跳超时（如 10 分钟内无同一设备任何上报）可触发 stale 标记（`is_active` 保持，但加 `stale=True` 标记）；**本期不实现 stale 机制**，记录为架构待办 |

---

## 8. 与现有架构的关联

### 8.1 与 AB-002 的关系

v0.5.3-FCC 架构文档记录了 AB-002（MQTT 驱动 fault_count_cache 失效）。本需求与 AB-002 存在交集，但定位不同：

- **本需求（v0.6.0-FM）**：fault_consumer 订阅 → 写入 `fault_event` 表（故障历史事件）
- **AB-002 原意**：在 `PLCLatestDataHandler._bulk_upsert()` 中调用失效钩子，用 MQTT 取代 60s TTL 被动刷新

本期策略：fault_consumer 写入 fault_event 时，**不调用** `invalidate_fault_count_cache`（保持 AB-002 待决状态）；`fault_utils.py` 已预留接口（无需修改）。

### 8.2 与 v0.5.3-FCC 的关系

| 维度 | v0.5.3-FCC（已有） | v0.6.0-FM（本需求） |
|------|-------------------|--------------------|
| 数据源 | `plc_latest_data`（当前快照） | `fault_event`（历史事件，时间维度） |
| 触发方式 | API 请求时计算 | MQTT 报文驱动写入 |
| 缓存目的 | 避免 API 每次查 DB | 避免每条 MQTT 报文触发 DB 操作 |
| 故障语义 | "当前有多少故障" | "某故障何时发生、何时恢复" |
| 前端位置 | 设备列表页「故障数量」列 | 独立「故障管理」页面 |
