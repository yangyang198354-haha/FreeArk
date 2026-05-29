# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.7.0-CW
  title: 结露预警管理页面 — 需求规格说明书
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-29
  last_updated: 2026-05-30 (v0.3.0)
  status: APPROVED
  references:
    - scripts/tmp/sniff_2860fae9a34ab8a9_20260525_235217.ndjson
    - docs/requirements/v0.6.0_fault_management/requirements_spec.md
    - docs/requirements/v0.6.4_fault_mgmt_room_column/requirements_spec.md
    - docs/architecture/architecture_design_v0.6.4_fault_mgmt_room_column.md
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/state_machine.py
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py
    - FreeArkWeb/backend/freearkweb/api/models.py (FaultEvent, ScreenConnectivityStatus)
    - FreeArkWeb/backend/freearkweb/api/views_fault.py
    - FreeArkWeb/frontend/src/components/Layout.vue
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-29 | 初始草稿，基于抓包实测与故障管理既有范式调研；含开放问题 OQ-01~OQ-11 |
| 0.2.0-APPROVED | 2026-05-30 | 按用户裁决定稿：OQ-01~OQ-11 全部决议落地；删除开放问题节；更新差异表、数据模型、范围表、状态机规则 |
| 0.3.0-APPROVED | 2026-05-30 | DEV-CHECK-01/02 用户答复 + 抓包验证后升级为已确认约束：(1) DEV-CHECK-01：product_code 120003/260001 均携带 condensation_alarm，不做白名单过滤，已确认。(2) DEV-CHECK-02（重要设计约束）：system_switch 与 condensation_alarm 通常来自不同 deviceSn/不同报文；system_switch 来自同 specific_part 水力模块最近已知值；新增架构遗留确认项 ARCH-PENDING-01（specific_part → 水力模块对应关系的建立方式）。同步更新 FR-CW-01 快照规则、§2.3 差异表、§6.2 假设 A-02、§6.3 DEV-CHECK、§7 风险表。 |

---

## 版本号决策记录

**决策**：本需求采用 **v0.7.0** 作为版本号。

**理由**：
- 当前仓库最新迭代为 v0.6.4（故障管理房间列），v0.6.x 系列已在故障管理功能上形成完整体系。
- 结露预警是独立的新业务模块（新数据表 / 新 systemd 服务 / 新前端页面 / 独立状态机实例），语义上与故障管理同级，值得 minor 版本跃迁。
- v0.7.0 在需求、架构、部署文档目录下均未被占用，是最干净的选择。
- v0.6.5 已在 v0.6.4 架构文档中被提名为 DeviceConfig/seed_device_config 改动的候选槽位，预留不动。

---

## 1. 背景与动因

### 1.1 项目背景

FreeArk 平台自 v0.6.0 起已具备完整的故障管理能力（MQTT 驱动 → 进程内状态机 → `fault_event` 数据表 → 前端管理页面）。该架构在 v0.6.1~v0.6.4 持续迭代完善，目前稳定运行于生产环境。

在 MQTT 上行报文（`DeviceStatusUpdate`）中，各房间温控面板除上报故障码外，还上报 `condensation_alarm`（结露报警）、`dew_point_temp`（露点温度）、`NTC_temp`（NTC 温度）、`humidity`（湿度）等与结露相关的字段。当前平台对这些字段**不做任何持久化或展示**，导致运维人员无法追踪结露预警历史、无法判断某住户是否曾经发生过结露风险。

### 1.2 需求来源

用户原始需求（2026-05-29）：

> 在设备管理菜单下新增「结露预警」子项，基于 `condensation_alarm` 字段的状态机与故障管理完全一致（发生→活跃→恢复），支持「未回复/已回复/全部」筛选，并展示房号、大屏在线状态、系统开关、预警类型/内容/露点温度/NTC 温度/湿度/预警发生时间/最后活跃/恢复时间等字段。

### 1.3 版本定位

| 版本 | 主要变更 |
|------|---------|
| v0.6.4-FM-ROOM | 故障管理房间列 + 设备类型过滤重组（已生产上线） |
| **v0.7.0-CW** | **结露预警管理页面（本版本）** |

---

## 2. 与故障管理的复用关系与差异点

本节是本版本需求的核心，明确结露预警（CW）与故障管理（FM）的复用边界。

### 2.1 完全复用项

| 维度 | 复用内容 |
|------|---------|
| 进程内状态机逻辑 | `state_machine.py` 的 T1（INSERT 活跃）/ T2（更新内存）/ T3（UPDATE 恢复）三条状态转移规则；进程重启时从 DB 重建状态机（LIMIT 10000 保护）；IntegrityError 兜底逻辑 |
| 状态字段语义 | `is_active`（活跃中 vs 已恢复）+ `first_seen_at`（首次出现）+ `last_seen_at`（最后活跃，内存维护）+ `recovered_at`（恢复时间） |
| 房号过滤工具 | `utils_room_filter.py` 中的房号段数匹配规则（3 段 `room_no` → 4 段 `specific_part` 前后缀组合匹配，BUG-FM-004 修复已积累） |
| 级联选择器控件 | `CascadingSelector.vue` 房号三级联动 |
| 分页控件 | PageNumberPagination，默认 20/页，最大 100/页 |
| 时间范围过滤 | `first_seen_after` / `first_seen_before`，默认最近 7 天 |
| 回复状态三态控件 | `<el-radio-group>`：「未回复（默认）/ 已回复 / 全部」（对应 `is_active` 参数 `true/false/不传`）；语义见 §2.2 |
| MQTT 消费侧框架 | 订阅 `/screen/upload/screen/to/cloud/+`；从 OwnerInfo 通过 screenMAC 解析 specific_part；`close_old_connections()` 保活；`loop_forever(retry_first_connection=True)` 自动重连 |
| 部署模式 | 新增独立 systemd 服务 `freeark-condensation-consumer`，plink + git pull 部署，禁止 pscp |
| 数据清理服务 | 新增 `freeark-condensation-cleanup`，每天 03:30 分批硬删除 90 天以上已恢复记录（活跃记录豁免删除） |
| 权限 | 所有接口沿用 `IsAuthenticated` |
| 导航菜单入口 | 在 `Layout.vue` 的「设备管理」`<el-sub-menu>` 下新增子项 `结露预警`，路径 `/device-management/condensation-warnings` |
| 防抖策略 | 与故障管理保持一致，不额外引入防抖；反复抖动（condensation_alarm 0→1→0→1）的每次 0→1 均产生独立预警记录（由 UNIQUE 约束依赖 first_seen_at 区分） |
| last_seen_at 维护策略 | 进程内内存维护，异常退出时丢失（不额外定期刷写），与故障管理行为一致 |

### 2.2 「回复」语义的权威定义

**用户裁决（2026-05-30）：「回复」完全等同于设备自动恢复，不引入人工标记字段。**

UI 标签与 `is_active` 字段的映射关系如下：

| UI 标签 | is_active 值 | 语义 |
|---------|-------------|------|
| **未回复** | `True` | 结露报警仍在活跃中，设备尚未恢复正常（condensation_alarm 持续非 0） |
| **已回复** | `False` | 设备已自动恢复正常（condensation_alarm 回到 0），系统执行 T3 转移 |

**重要约束**：
- 本功能**不存在**「人工回复」操作（无「标记已回复」按钮，无 is_replied 字段）。
- 「已回复」的唯一触发路径：MQTT 报文中 condensation_alarm=0，状态机执行 T3（UPDATE is_active=False, recovered_at=now()）。
- 本文档所有「回复」出现处均锚定至上述语义，实现人员不得自行扩展为人工操作。

### 2.3 与故障管理的差异点（定稿版）

| 维度 | 故障管理（FM） | 结露预警（CW） | 裁决依据 |
|------|-------------|-------------|---------|
| 触发字段 | 多个故障字段（`error_N`、`comm_fault_timeout`、命名型故障码等） | 单一字段 `condensation_alarm`（int(value)!=0 即触发；0 或无法转 int 均视为正常） | 用户裁决 OQ-07 |
| condensation_alarm 分级 | N/A | **只有有/无两态**（0=无预警，非0=有预警，无级别区分） | 用户裁决 OQ-07 |
| 数据表 | `fault_event` | `condensation_warning_event`（**独立新建**） | 用户裁决 OQ-02 |
| 额外快照字段 | 无 | `dew_point_temp`、`NTC_temp`、`humidity`、`system_switch`，**取触发时刻快照（各字段来源见下行）** | 用户裁决 OQ-05 |
| system_switch 快照来源（已确认约束） | N/A | **dew_point_temp / ntc_temp / humidity**：取自触发报文同条 items[] 快照（同 deviceSn）。**system_switch**：(1) 若触发报文同一 deviceSn 的 items[] 中含 system_switch，直接取；(2) 否则取同 specific_part 关联水力模块的最近已知 system_switch 值（来源由架构设计确定，见 ARCH-PENDING-01）；(3) 均不可用则存 "unknown"。**背景**：抓包确认 condensation_alarm（温控面板 120003, deviceSn 22549/22550/22551）与 system_switch（水力模块 260001/270001/10016）通常来自不同 deviceSn 和不同 MQTT 报文，不可从同一触发报文直接取。116 条含 condensation_alarm 报文中仅 29 条（260001 设备）同报文含 system_switch，属特例。 | 用户答复 DEV-CHECK-02 + 抓包验证（2026-05-30 已确认） |
| 故障类型/严重级别 | `fault_type`（comm/sensor/fresh_air/other_error）+ `severity`（error/warning） | 无 fault_type 分类；`warning_type` 固定为 "结露预警"，`warning_message` 固定为 "结露报警" | 用户裁决 OQ-04（默认假设，开发前可复核） |
| 设备覆盖范围 | 所有上报设备 | 凡 `items[]` 中出现 `condensation_alarm` 的房间面板设备（通用处理，不写死 product_code）；具体 product_code 集合为开发阶段核实项（见 §6.3） | 用户裁决 OQ-03 |
| 「大屏在线状态」列 | 无 | 有；列表**每行**实时计算，查询时对该页所有 specific_part 做 IN 查询 `ScreenConnectivityStatus`（last_seen_at ≤ 15 分钟即在线） | 用户裁决 OQ-08 |
| 「系统开关」列 | 无 | 有；来自 T1 INSERT 时快照的 `system_switch` 字段 | 用户裁决 OQ-05 |
| 状态机 key | `(specific_part, device_sn, fault_code)` | `(specific_part, device_sn)`（无 fault_code 维度，每台设备同一时刻只存在一条活跃预警） | 触发字段唯一性 |
| 人工回复操作 | 无 | **无**（「回复」=设备自动恢复，见 §2.2） | 用户裁决 OQ-01 |
| 清理策略 | `freeark-fault-cleanup`，保留 90 天 | `freeark-condensation-cleanup`，同策略，独立服务 | 设计对齐 |

---

## 3. 范围

### 3.1 本版本范围内（In Scope）

| 编号 | 范围项 |
|------|--------|
| S-01 | 新增独立 systemd 服务 `freeark-condensation-consumer`，订阅 MQTT 上行 topic，识别 `condensation_alarm` 字段，写入 `condensation_warning_event` 表 |
| S-02 | 进程内状态机（Python dict），复用故障管理 T1/T2/T3 转移模式，key 为 `(specific_part, device_sn)` |
| S-03 | 「设备管理」子菜单新增「结露预警」页面（`CondensationWarningView.vue`），路径 `/device-management/condensation-warnings` |
| S-04 | 过滤器：回复状态（三态 is_active）、房号（CascadingSelector + 段数映射）、时间段（`first_seen_at` 区间，默认最近 7 天） |
| S-05 | 列表字段：房号、房间、大屏是否在线、系统开关、预警类型、预警内容、露点温度、NTC 温度、湿度、预警发生时间、最后活跃、恢复时间 |
| S-06 | 后端 REST API：`GET /api/devices/condensation-warning-events/`，支持分页 + 多维过滤 |
| S-07 | 新增 `freeark-condensation-cleanup` systemd 服务，每天 03:30 分批清理 90 天以上已恢复记录 |

### 3.2 本版本范围外（Out of Scope）

| 编号 | 排除项 | 说明 |
|------|--------|------|
| OOS-01 | 人工标记「回复」操作 | 已裁决（OQ-01）：「回复」= 设备自动恢复，不做人工标记 |
| OOS-02 | 告警通知（钉钉/短信/邮件） | 本期仅做记录与查询，与故障管理保持一致 |
| OOS-03 | 「防冻预警」模块 | 上行报文无防冻预警字段，不在本期范围 |
| OOS-04 | 结露预警与故障管理合并为同一数据表 | 已裁决（OQ-02）：独立新表 |
| OOS-05 | `condensation_alarm` 非 0 值的多级告警 | 已裁决（OQ-07）：只有有/无两态 |
| OOS-06 | condensation_alarm 防抖 | 已裁决（OQ-09）：与故障管理一致，不做防抖 |

---

## 4. 功能需求

### FR-CW-01：MQTT 结露预警订阅服务（systemd）

**描述**：新增独立 Django Management Command `condensation_consumer`，由 systemd 服务 `freeark-condensation-consumer` 管理，订阅 MQTT upload topic，识别 `condensation_alarm` 字段并持久化结露预警事件。

**输入**：
- MQTT broker 连接参数（复用 `heartbeat_broker_config.json` 格式，独立 client_id，如 `freeark-condensation-consumer`）
- 订阅 topic：`/screen/upload/screen/to/cloud/+`（通配符，与 fault_consumer 一致）
- `DeviceStatusUpdate` 报文（`header.name = "DeviceStatusUpdate"`）

**处理规则**：
1. 从报文 `payload.data.items[]` 中提取 `condensation_alarm` 字段值（attrTag="condensation_alarm"）
2. 同时从**同一报文**的 `items[]` 中提取快照字段：`dew_point_temp`、`NTC_temp`、`humidity`、`system_switch`（T1 INSERT 时落库）
3. 通过 screenMAC → specific_part 映射（从 OwnerInfo 加载）定位房号
4. 通过 `deviceSn` 定位 `device_sn`；通过 `productCode` 记录 `product_code`
5. 将结露报警状态送入进程内状态机（FR-CW-02）

**判定规则**（`condensation_alarm` 是否处于预警态）：
- 预警态：`int(value) != 0`（非零整数值）
- 正常态：`int(value) == 0`（字符串 "0" 或整数 0）
- 解析失败：value 无法转 int → 视为正常态，记录 WARNING 日志（安全兜底）

**快照字段提取规则**（OQ-05 裁决 + DEV-CHECK-02 已确认约束）：
- `dew_point_temp`、`ntc_temp`、`humidity`：取触发时刻同一条 MQTT 报文同一 deviceSn 的 `items[]` 中对应 attrTag 值；该报文无此 attrTag 则存 NULL。
- `system_switch`（已确认跨设备来源，不同于上述三字段）：
  1. **优先**：若触发报文同一 deviceSn 的 `items[]` 中含 `system_switch` attrTag，直接取该值（适用于 260001 等同时上报两字段的设备）。
  2. **兜底**：若触发报文中无 `system_switch`（典型情况：温控面板 120003 的报文只含 condensation_alarm 而无 system_switch），则取同 `specific_part` 关联水力模块的最近已知 `system_switch` 值。该值的具体数据来源（plc_latest_data 缓存 / 设备状态表 / 其他）由架构设计阶段确定（见 §6.3 ARCH-PENDING-01）。
  3. **最终兜底**：若上述两步均无法取到有效值，存 `"unknown"`。
- **已确认背景约束（DEV-CHECK-02，2026-05-30）**：抓包（sniff_2860fae9a34ab8a9_20260525_235217.ndjson）确认：
  - 温控面板 120003（deviceSn 22549/22550/22551）的报文中**无** system_switch 字段。
  - system_switch 来自 260001 / 270001 / 10016 等水力模块/能源设备。
  - 116 条含 condensation_alarm 的报文中，仅 29 条（均属 260001）同报文含 system_switch。
  - 因此消费侧**必须**维护"每个 specific_part → 水力模块最近 system_switch 值"的映射，不能假设同一报文可同时取到两字段。

**设备范围**（OQ-03 裁决 + DEV-CHECK-01 已确认）：
- 凡 `items[]` 中出现 `condensation_alarm` attrTag 的设备均处理，**不对 product_code 做白名单硬过滤**（已确认结论）。
- **已确认来源（DEV-CHECK-01，2026-05-30）**：抓包验证显示 condensation_alarm 出现在：
  - **product_code 120003**（温控面板，deviceSn 22549/22550/22551）—— 主要来源。
  - **product_code 260001**（水力模块，deviceSn 22001）—— 该设备同时上报 condensation_alarm 与 system_switch。
  - 可能还存在其他 product_code，消费侧通用处理，将 product_code 记录到 DB 以供后续分析。

**约束**：
- 服务命名 `freeark-condensation-consumer`，独立实现，不与 `freeark-fault-consumer` 共享代码文件
- 复用 paho-mqtt 1.x API（`>=1.6.1,<2.0`）
- 每次 DB 操作前调用 `django.db.close_old_connections()`
- systemd 配置：`Restart=on-failure, RestartSec=30s`

---

### FR-CW-02：结露预警事件状态机（进程内内存表）

**描述**：进程内 Python dict 维护活跃中的结露预警状态，实现 T1/T2/T3 三条转移规则。

**状态机 Key**：`(specific_part, device_sn)` → `{event_id: int, is_active: bool, last_seen_at: datetime}`

> **注**：与故障管理不同，key 不含 `fault_code` 维度，因为触发源只有一个字段 `condensation_alarm`。每台设备同一时刻只存在一条活跃结露预警记录。

**状态转移规则**（复用 fault_consumer/state_machine.py 设计）：

```
T1: [内存表 miss，或 key 存在但 is_active=False] + condensation_alarm 非 0
  → INSERT condensation_warning_event(
       is_active=True, first_seen_at=now(), last_seen_at=now(),
       快照字段: dew_point_temp/ntc_temp/humidity/system_switch
     )
  → 内存表写入: key → (event_id, is_active=True, last_seen_at=now())

T2: [内存表 hit, is_active=True] + condensation_alarm 非 0
  → 仅更新内存表 last_seen_at=now()（不写 DB）
  → 异常退出时此值丢失，接受（与故障管理一致）

T3: [内存表 hit, is_active=True] + condensation_alarm = 0
  → UPDATE condensation_warning_event
       SET recovered_at=now(), is_active=False, last_seen_at=内存中 last_seen_at 值
     WHERE id = event_id
  → 内存表更新: is_active=False

[进程重启]
  → 启动时查 DB: SELECT * FROM condensation_warning_event WHERE is_active=True LIMIT 10000
  → 重建内存表（last_seen_at 使用 DB 值，可能早于实际最后活跃时间，接受此误差）
  → IntegrityError 兜底：与 fault_consumer 一致（ON CONFLICT DO NOTHING 或 except IntegrityError: pass）
```

**约束**：
- 进程内内存表仅 `freeark-condensation-consumer` 使用；API 查询服务直查 DB
- 不设 TTL，进程重启时重建
- 无防抖逻辑（OQ-09 裁决）

---

### FR-CW-03：结露预警事件数据模型

**描述**：新增独立数据表 `condensation_warning_event`（OQ-02 裁决：独立新表）。

**字段清单（定稿版）**：

| 字段名 | 类型（需求语义） | 必填 | 说明 |
|--------|----------------|------|------|
| `id` | BigAutoField（PK） | 是 | 主键 |
| `specific_part` | VARCHAR(64) | 是 | 房号（四段格式，如 "3-1-7-702"）；INDEX |
| `device_sn` | VARCHAR(64) | 是 | 设备序列号（来自 MQTT `deviceSn`） |
| `product_code` | VARCHAR(32) | 是 | 产品编码（来自 MQTT `productCode`） |
| `room_name` | VARCHAR(50) | 否 | 冗余房间名，写入时通过 device_sn → DeviceNode → DeviceRoom 填充；NULL 兜底 |
| `room_id` | INT（FK→device_room.id, ON DELETE SET NULL） | 否 | 房间外键 |
| `warning_type` | VARCHAR(32) | 是 | 固定值："结露预警"（默认假设，开发前可复核；见 OQ-04） |
| `warning_message` | VARCHAR(255) | 是 | 固定值："结露报警"（默认假设，开发前可复核；见 OQ-04） |
| `condensation_alarm_value` | VARCHAR(16) | 否 | 触发时 `condensation_alarm` 的原始值（如 "1"），供调试 |
| `dew_point_temp` | VARCHAR(16) | 否 | 触发时刻露点温度快照（原始字符串，如 "20.5"）；NULL 表示报文未携带 |
| `ntc_temp` | VARCHAR(16) | 否 | 触发时刻 NTC 温度快照；NULL 表示报文未携带 |
| `humidity` | VARCHAR(16) | 否 | 触发时刻湿度快照；NULL 表示报文未携带 |
| `system_switch` | VARCHAR(8) | 否 | 触发时刻系统开关状态（"on"/"off"/"unknown"）；NULL 等同于 "unknown" |
| `first_seen_at` | DATETIME | 是 | 预警首次出现时间；INDEX |
| `last_seen_at` | DATETIME | 是 | 最近一次内存确认仍活跃的时间（进程内维护，异常退出时丢失，接受此误差） |
| `recovered_at` | DATETIME NULL | 否 | 预警恢复时间（T3 时写入）；NULL 表示仍活跃（is_active=True） |
| `is_active` | BOOL | 是 | True=未回复（活跃中），False=已回复（已恢复）；INDEX |
| `created_at` | DATETIME | 是 | auto_now_add |
| `updated_at` | DATETIME | 是 | auto_now |

> **注**：快照字段（dew_point_temp/ntc_temp/humidity/system_switch）均使用 VARCHAR 存储原始字符串，与 MQTT 报文原始值保持一致，避免类型转换引入的精度问题或解析异常。

**推荐索引**：
```
INDEX(specific_part, is_active)
INDEX(first_seen_at, is_active)
UNIQUE(specific_part, device_sn, first_seen_at)
```

> 注：UNIQUE 约束不含 `fault_code` 维度（结露预警 key 只有 specific_part + device_sn）。同一设备不同时刻的预警周期由 `first_seen_at` 区分。

**is_active 语义约束**（锚定 §2.2）：
- 不引入 `is_replied`、`replied_at`、`replied_by` 字段（OQ-01 裁决）
- `is_active=False` 的唯一来源：状态机 T3 转移（设备自动恢复）

---

### FR-CW-04：结露预警管理页面（前端）

**描述**：在「设备管理」菜单下新增「结露预警」子页面，路径 `/device-management/condensation-warnings`，组件 `CondensationWarningView.vue`。

**导航菜单**（`Layout.vue` 变更）：
```
设备管理（展开节点，已有）
  ├── 设备列表（已有，index="/device-management/device-list"）
  ├── 故障管理（已有，index="/device-management/faults"）
  └── 结露预警（新增，index="/device-management/condensation-warnings"）
```

**过滤条件区**：

| 过滤项 | 控件 | 行为 |
|--------|------|------|
| 回复状态 | `<el-radio-group>` 三按钮 | 「未回复（默认）/ 已回复 / 全部」→ 请求参数 `is_active=true/false/不传`；UI 标签与 is_active 的映射见 §2.2 |
| 房号 | `CascadingSelector` | 与故障管理一致，三级联动，输出 3 段格式，后端做段数映射 |
| 时间段 | 日期范围选择器 | `first_seen_at` 落在 `[start, end]`；默认最近 7 天 |

**表格列（定稿）**：

| 列名 | 数据来源字段 | 说明 |
|------|------------|------|
| 房号 | `specific_part` | 四段格式 |
| 房间 | `room_name` | NULL 时显示 "-" |
| 大屏是否在线 | `is_screen_online`（后端计算注入） | "在线"（绿色）/ "离线"（灰色）；查询时实时计算（每行均显示） |
| 系统开关 | `system_switch` | "开启" / "关闭" / "-"（NULL 或 "unknown" 显示 "-"） |
| 预警类型 | `warning_type` | 固定显示"结露预警" |
| 预警内容 | `warning_message` | 固定显示"结露报警" |
| 露点温度 | `dew_point_temp` | NULL 时显示 "-"，有值时显示原始值 + 单位 °C |
| NTC 温度 | `ntc_temp` | NULL 时显示 "-"，有值时显示原始值 + 单位 °C |
| 湿度 | `humidity` | NULL 时显示 "-"，有值时显示原始值 + 单位 % |
| 预警发生时间 | `first_seen_at` | 本地时间（Asia/Shanghai） |
| 最后活跃 | `last_seen_at` | 本地时间（注：进程内维护，活跃预警此值可能偏早，属预期行为） |
| 恢复时间 | `recovered_at` | NULL 时显示 "-" |

**默认排序**：`-first_seen_at`（最新在前）

**分页**：每页默认 20 条，支持切换（10/20/50）

---

### FR-CW-05：「大屏是否在线」计算逻辑

**描述**：结露预警列表每行展示「大屏是否在线」字段（OQ-08 裁决：列表每行实时计算）。

**数据来源**：`ScreenConnectivityStatus` 表（已存在，`db_table='screen_connectivity_status'`）。

**在线判断规则**：
- `ScreenConnectivityStatus.last_seen_at` 距当前时间 ≤ 15 分钟 → **在线**（`is_screen_online=true`）
- 超过 15 分钟或无记录 → **离线**（`is_screen_online=false`）

**查询路径**：
```
当前页结果集中所有 specific_part
  → IN 查询 ScreenConnectivityStatus WHERE specific_part IN (...)
  → 取 last_seen_at，计算 now() - last_seen_at ≤ 15min
  → 注入每条记录的 is_screen_online 字段
```

**API 响应字段**：`is_screen_online: bool`（后端序列化时计算注入，不存储到 DB）

**性能预期**：每页 IN 查询最多 100 条 specific_part，ScreenConnectivityStatus 为小表，预计 < 50ms，可接受。

---

### FR-CW-06：结露预警查询 REST API

**描述**：新增后端接口供「结露预警」页面调用。

**接口**：`GET /api/devices/condensation-warning-events/`

**查询参数（定稿）**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `specific_part` | string（可选） | 房号，3 段/4 段均支持（与 views_fault.py 相同的段数映射逻辑） |
| `is_active` | "true"/"false"（可选） | 回复状态过滤；true=未回复/false=已回复/不传=全部 |
| `first_seen_after` | ISO8601（可选） | 时间段起点，默认 now()-7 天 |
| `first_seen_before` | ISO8601（可选） | 时间段终点 |
| `page` | integer | 默认 1 |
| `page_size` | integer | 默认 20，最大 100 |

**响应格式**（与故障管理接口结构一致）：
```json
{
  "count": 总条数,
  "next": "分页 URL | null",
  "previous": "分页 URL | null",
  "results": [
    {
      "id": 1,
      "specific_part": "3-1-7-702",
      "room_name": "主卧",
      "device_sn": "22554",
      "product_code": "120003",
      "warning_type": "结露预警",
      "warning_message": "结露报警",
      "condensation_alarm_value": "1",
      "dew_point_temp": "20.5",
      "ntc_temp": "18.0",
      "humidity": "65",
      "system_switch": "on",
      "is_screen_online": true,
      "first_seen_at": "2026-05-29T10:00:00+08:00",
      "last_seen_at": "2026-05-29T10:05:00+08:00",
      "recovered_at": null,
      "is_active": true
    }
  ]
}
```

**权限**：`IsAuthenticated`

---

### FR-CW-07：结露预警数据清理服务

**描述**：新增独立 systemd 服务 `freeark-condensation-cleanup`，定期清理过期预警记录。

**策略**（与故障管理清理策略一致）：
- 保留天数：90 天（`first_seen_at < NOW() - INTERVAL 90 DAY` 的记录硬删除）
- 活跃预警（`is_active=True`）不删除，无论 `first_seen_at` 多早
- 执行时间：每天 03:30
- 分批删除，每批 ≤ 1000 行

---

## 5. 非功能需求

### 5.1 性能

| 指标 | 目标值 | 说明 |
|------|--------|------|
| MQTT 报文处理延迟（T2 路径） | ≤ 500ms / 条 | T2 路径只更新内存，无 DB 操作 |
| 预警事件 DB 写入延迟（T1/T3 路径） | ≤ 2s | 仅首次出现和恢复时写 DB |
| 结露预警列表接口 P95 响应时间 | ≤ 1s（正常负载，有索引） | 树莓派 MySQL @ 192.168.31.98 |
| `is_screen_online` 计算开销 | ≤ 50ms | 每页 IN 查询 ScreenConnectivityStatus（小表，有索引） |

### 5.2 可靠性

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 服务自动重启 | `Restart=on-failure, RestartSec=30s` | 与故障管理服务一致 |
| 进程重启后状态机重建 | 启动时加载 `is_active=True` 记录（LIMIT 10000） | 避免重启后重复插入 |
| last_seen_at 丢失容忍 | 接受进程异常退出导致 last_seen_at 偏早的误差 | 与故障管理一致（OQ-06/OQ-10 裁决） |

### 5.3 安全

| 要求 | 说明 |
|------|------|
| API 鉴权 | `IsAuthenticated`，与现有接口一致 |
| ORM 安全 | 所有过滤通过 Django ORM，禁止拼接原生 SQL |
| broker 凭证 | 独立 client_id，凭证存 `heartbeat_broker_config.json`，不硬编码 |

---

## 6. 依赖、假设与开发阶段核实项

### 6.1 依赖

| 依赖项 | 类型 | 说明 |
|--------|------|------|
| `OwnerInfo` 表 | DB 依赖 | screenMAC → specific_part 映射 |
| `ScreenConnectivityStatus` 表 | DB 依赖 | 大屏在线状态计算（查询时 IN 查询） |
| `DeviceNode` / `DeviceRoom` 表 | DB 依赖 | device_sn → room_name 映射（T1 INSERT 时填充） |
| `heartbeat_broker_config.json` | 配置依赖 | MQTT broker 连接参数，独立 client_id |
| paho-mqtt `>=1.6.1,<2.0` | 库依赖 | 已在 requirements.txt，无需新增 |
| MySQL 9.4 @ 192.168.31.98 | 生产 DB | 新表 migration 在生产 DB 执行 |
| `CascadingSelector.vue` | 前端依赖 | 房号三级联动组件，复用不修改 |

### 6.2 假设

| 编号 | 假设内容 |
|------|---------|
| A-01 | MQTT broker ACL 允许通配符订阅（已在故障管理 v0.6.0 OQ-10 确认） |
| A-02 | **[已修订，DEV-CHECK-01 确认]** `condensation_alarm` 字段主要来自温控面板（product_code 120003），但抓包也在水力模块 260001 中发现。消费侧采用通用处理策略，不假设字段仅来自温控面板。 |
| A-03 | 同一设备的 `condensation_alarm` 字段在同一 MQTT 报文中只出现一次（每个 deviceSn 每条报文只有一个 `condensation_alarm` 条目） |
| A-04 | 生产环境中 `ScreenConnectivityStatus.specific_part` 的格式与 `condensation_warning_event.specific_part` 一致（均为四段格式），可直接等值匹配 |
| A-05 | 树莓派 192.168.31.51 可承载再增加两个 systemd 常驻服务（condensation-consumer + condensation-cleanup） |

### 6.3 已确认约束项与架构遗留确认项

#### 6.3.1 已确认约束（原 DEV-CHECK，已通过用户答复 + 抓包验证关闭）

| 编号 | 核实结论（已确认） | 影响范围 | 确认时间 |
|------|-----------------|---------|---------|
| **DEV-CHECK-01（已确认）** | condensation_alarm 出现在 product_code **120003**（温控面板，主要来源）和 **260001**（水力模块，同时含 system_switch）。消费侧**不做 product_code 白名单硬过滤**；凡 items[] 中出现 condensation_alarm attrTag 的报文均处理；将 product_code 写入 DB 记录供后续分析（已实现：`product_code` 字段存在于数据模型）。 | `condensation_consumer` 的设备过滤逻辑 | 2026-05-30（抓包 sniff_2860fae9a34ab8a9_20260525_235217.ndjson 验证） |
| **DEV-CHECK-02（已确认 — 重要设计约束）** | system_switch 与 condensation_alarm **通常来自不同 deviceSn、不同 MQTT 报文**：温控面板 120003（deviceSn 22549/22550/22551）的报文中无 system_switch；system_switch 来自水力模块/能源设备（260001/270001/10016）。116 条含 condensation_alarm 报文中仅 29 条（260001 同报文含两字段）属特例。**消费侧必须维护"每个 specific_part → 水力模块最近 system_switch 值"映射**（兜底取不到则存 "unknown"）。具体映射数据来源留待架构设计（见 ARCH-PENDING-01）。 | T1 INSERT 时 system_switch 快照字段的取值逻辑；消费侧需维护状态缓存 | 2026-05-30（用户答复 + 抓包验证） |

#### 6.3.2 架构遗留确认项（不阻塞需求，架构设计阶段落地）

| 编号 | 待确认内容 | 影响范围 | 备注 |
|------|---------|---------|------|
| **ARCH-PENDING-01** | `specific_part` 与"同 specific_part 水力模块设备"的对应关系如何建立。候选方案：(A) 查询 `plc_latest_data` 表（已有）中该 specific_part 下 product_code ∈ {260001,270001,...} 的最近 system_switch 值；(B) 查询设备拓扑/DeviceNode 表获得 deviceSn → specific_part 映射后反查；(C) 消费侧监听所有报文，维护 `{specific_part: system_switch}` 内存缓存（类似进程内状态机）。**架构设计阶段须选定方案并确认数据来源字段/表名，需求阶段不强制落地。** | condensation_consumer T1 INSERT 的 system_switch 兜底逻辑实现方式 | 用户原文："可来自已有的 plc_latest_data / 设备状态缓存，请在需求中标注，留待架构设计确定数据来源" |

---

## 7. 风险

| 风险编号 | 描述 | 概率 | 影响 | 缓解措施 |
|----------|------|------|------|---------|
| R-01 | `condensation_alarm` 在生产环境长期保持为 "0"（即从未触发），导致新增功能无法被真实验证 | 中（取决于季节/温度） | 低（功能完整，仅缺测试数据） | 提供手工模拟测试方案（向 MQTT broker 注入测试报文，condensation_alarm=1） |
| R-02 | **[已确认，DEV-CHECK-02 关闭]** dew_point_temp/ntc_temp/humidity 与 condensation_alarm 同报文出现（同 120003 设备）；system_switch **确认来自不同报文/不同 deviceSn**，需跨报文取最近已知值。若 specific_part → 水力模块映射取不到（设备未上线/无历史数据），system_switch 存 "unknown"。 | 低（"unknown" 可接受；ARCH-PENDING-01 解决后影响进一步降低） | 低 | 快照字段全部允许 NULL/unknown；system_switch 优先同报文取，兜底最近已知值，最终兜底 "unknown"（已写入 FR-CW-01 规则） |
| R-03 | 新增两个 systemd 服务（condensation-consumer + condensation-cleanup）对树莓派资源有额外消耗 | 低（进程内存占用小） | 低 | 生产上线后监控 CPU/内存 |
| R-04 | 生产环境 MySQL migration 执行新表 DDL 时的锁表问题 | 低（新表无现有数据，DDL 极快） | 低 | 部署窗口执行；新表不影响现有表 |
