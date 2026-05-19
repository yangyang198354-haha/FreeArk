# 需求规格说明书

**文档编号**: REQ-SPEC-DEVICE-SETTINGS-001  
**项目名称**: FreeArk 设备参数设置功能  
**版本**: 0.4.0-APPROVED  
**状态**: APPROVED（v0.4.0：2026-05-19 Q10~Q12 全部用户决策落地；Q13 标注延后开发自查；PM 门控通过）  
**创建日期**: 2026-05-19  
**最后更新**: 2026-05-19  
**作者**: requirement-analyst (via pm-orchestrator)  
**审核**: pm-orchestrator（v0.4.0 Q10~Q12 决策落地审核通过）

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0 | 2026-05-19 | 初始草稿 |
| 0.2.0 | 2026-05-19 | Open Questions Q1~Q9 全部决策落地 |
| 0.3.0-APPROVED | 2026-05-19 | 端口确认 32797；移除本期回滚范围；审核通过，已生产部署（commit b260f25） |
| 0.4.0-DRAFT | 2026-05-19 | 生产实测反馈调整：5 项变更（P1~P5）。P1/P2 为 Bug 修复需求，P3/P4/P5 为范围变更。新增 Open Questions Q10~Q13 留给架构师决策。 |
| 0.4.0-APPROVED | 2026-05-19 | Q10~Q12 用户决策全部落地：Q10→一条 MQTT 多 item；Q11→后端 Python 常量文件；Q12→new_value 存 PLC 原始值；Q13→延后至开发阶段自查。PM 门控通过，文档状态升级为 APPROVED。 |

---

## 1. 业务背景与目标

### 1.1 背景

FreeArk 是一套面向三恒暖通系统的物联网管理平台。采集侧（`datacollection`）通过 Siemens S7 协议读取各户 PLC 参数，并经由 MQTT broker 推送至后端；后端（Django + MySQL）将参数持久化到 `plc_latest_data` 表，前端展示在"设备管理"的设备列表页（`DeviceManagementDeviceListView`）。

当前设备列表操作列已有"设备面板"（跳转至实时卡片）和"PLC历史"（弹窗查看历史参数）两个入口。业主或运维人员无法在 Web 端主动向 PLC **下发设置值**，必须依赖现场操作或专用工具。

### 1.2 目标

在设备列表操作列新增**"设置"**按钮，允许授权用户在 Web 端对指定专有部分的 PLC 参数进行设置，包括：
- 查看主温控（`main_thermostat`）和各子面板（`panel_*`）的可设置属性及当前值；
- 通过 MQTT 下发设置命令至 `datacollection` 层；
- `datacollection` 层收到命令后写入 PLC，并将结果回写至数据库及通过 MQTT 回执；
- 设置页面能自动刷新，展示最新的写入结果。

---

## 2. 功能性需求

### FR1 — 设备列表"设置"按钮入口

**来源**: 用户原始需求第 1 条——"设备列表页面的操作列，新增一个设置按钮"

| 编号 | 需求描述 |
|------|----------|
| FR1-1 | 在 `DeviceManagementDeviceListView` 的操作列中，在现有"设备面板"和"PLC历史"按钮之后，新增"设置"按钮。 |
| FR1-2 | 点击"设置"按钮后，打开一个设置面板（模态弹窗或侧边抽屉，架构阶段决定具体交互形式），目标对象为该行的 `specific_part`。 |
| FR1-3 | 只有通过身份认证的用户（`IsAuthenticated`）才能看到并点击"设置"按钮；未登录用户不展示该按钮。 |

**约束**: `specific_part` 是跨系统的唯一设备标识符，格式为四段（如 `3-1-7-702`），来自 `OwnerInfo` 表。

---

### FR2 — 设置面板的展示（参数定义来源于 device_config + device_attr_def 协同）

**来源**: 用户原始需求第 1 条——"可以打开面板对主温控和各个面板进行设置，并能看到相应的值。设置的方式可以参考 device_attr_def 内的定义"

**[v0.4.0 变更记录]**
- **P5（范围调整）**: 设置面板仅显示可写属性（`is_writable=true`），隐藏只读属性，影响 FR2-1、FR2-2。
- **P3（UX 需求变更）**: UI 展示值与输入控件使用人类可读形态，影响 FR2-2、FR2-3、新增 FR2-6。
- **P4（UX 需求变更）**: 改"逐字段下发"为"批量下发"，影响 FR2-2，新增 FR2-7。
- **P1（Bug 修复）**: 枚举下拉菜单选项为空，补充 FR2-3 验收条件。

**[Q1 已决策]** 参数定义来源：**两者协同使用**。
- **`DeviceConfig`**（`param_name` / `sub_type`）：负责参数分组展示（主温控、书房面板、次卧面板等分组结构）和 `display_name`（中文显示名）。
- **`DeviceAttrDef`**（`product_code` / `attr_tag`）：负责值域约束（枚举选项、数值范围）和控件类型（`attr_value_type`：1=枚举下拉、2=数值输入框）。
- 联结键：`DeviceConfig.param_name` 对应 `DeviceAttrDef.attr_tag`（两者在同一套命名体系下），通过 `DeviceAttrBinding` 关联的 `product_code` 进一步过滤当前设备的适用属性。

**[Q2 已决策]** 可写白名单：
- **可写（渲染输入控件）**：`*_temp_setting`（温度设定）、`*_switch`（开关类）。
- **只读（仅展示值，无输入控件）**：`*_dew_point_setting`（露点设定，实测）、`*_error` / `*_alert`（故障类）、`*_temperature` / `*_humidity`（实测类传感器值）。
- 可写判断规则：后端在返回参数列表时附带 `is_writable` 字段（`true`/`false`），前端依此决定渲染输入控件还是只读文本。

| 编号 | 需求描述 | v0.4.0 变更标注 |
|------|----------|---------------|
| FR2-1 | 设置面板按子设备类型分组展示参数，至少包含：主温控（`main_thermostat`）及已同步的各子面板（`panel_*`）。仅展示 `DeviceConfig.is_active=true` 且 `is_writable=true` 的参数；`is_writable=false` 的只读参数在设置面板中**不显示**。 | **P5 修订** |
| FR2-2 | 每个可写参数展示：显示名（`DeviceConfig.display_name`）、当前值（来自 `plc_latest_data`，以 `specific_part` + `param_name` 查询）。控件类型：枚举型渲染下拉框，数值型渲染数值输入框。展示值与控件输入值均使用人类可读形态（见 FR2-6）；`is_writable=false` 的参数不在面板内渲染任何控件或文本行。 | **P3 + P5 修订** |
| FR2-3 | 枚举型输入控件的选项来自 `DeviceAttrDef.select_values_json`；数值型输入控件的范围约束来自 `DeviceAttrDef.num_value_json`，前端须据此做范围校验（拦截超出范围的提交）。**【P1 Bug 修复验收】** 所有枚举/下拉类字段（含"系统开关"等`*_switch`类参数）必须从 `DeviceAttrDef.select_values_json` 加载选项列表，下拉菜单不得为空。若该字段对应的 `select_values_json` 为 null 或空数组，UI 须在该控件位置明确展示"选项加载失败，请检查 DeviceAttrDef 配置"，不可静默呈现空下拉。 | **P1 Bug 修复** |
| FR2-4 | 当前值的展示应实时反映 `plc_latest_data` 中的最新数据，不得展示过期缓存。 | 不变 |
| FR2-5 | 面板打开时，自动加载指定 `specific_part` 的所有可写参数（`is_writable=true`）及当前值，加载失败时展示错误提示，提供"刷新"操作。 | **P5 小幅修订** |
| FR2-6 | **【新增，P3】** UI 显示值与输入控件使用人类可读形态，后端与 PLC 通信仍按既定数据类型（int/bool/float）：枚举型字段须提供"PLC 原始值 ↔ 人类可读标签"的映射（如：`0` ↔ `"关"`，`1` ↔ `"开"`；模式类字段按实际含义映射）；数值型字段（如温度）仍以数字显示，但须附带单位（如"℃"）。`plc_write_record.new_value` 字段存储 PLC 实际写入的原始值（如 `"1"`），UI 展示时再做映射（见 Q13）。映射表来源见 Q11。 | **P3 新增** |
| FR2-7 | **【新增，P4】** 设置面板提供单一"提交"按钮（取代原逐字段下发按钮），用户可一次修改多个可写字段后统一下发；提交前提供"取消"操作（撤销本次面板内所有未提交改动，控件恢复至当前值）。批量下发的具体协议实现（单条 MQTT 多 item 还是前端循环 N 条）见 Q10，由架构师决策。 | **P4 新增** |

---

### FR3 — 设置值的 MQTT 下发链路

**来源**: 用户原始需求第 2 条——"设置的值在 web 端通过 mqtt 发送"

**[v0.4.0 变更记录]**
- **P2（Bug 修复）**: 端到端链路存在"下发通道异常"故障，补充 FR3 验收条件，要求端到端链路在非 mock 环境下可实际通达。
- **P4（UX 需求变更）**: 批量下发影响 FR3-1、FR3-2 的命令结构，具体协议见 Q10。

| 编号 | 需求描述 | v0.4.0 变更标注 |
|------|----------|---------------|
| FR3-1 | 用户在设置面板完成字段修改并点击"提交"后，Web 端（Django 后端）向 MQTT broker 发布设置命令消息。命令的载荷结构（单字段 vs 多字段批量）依据 Q10 的架构决策确定。 | **P4 修订** |
| FR3-2 | 设置命令消息须包含：`specific_part`、PLC IP（来自 `OwnerInfo.plc_ip_address`）、`param_name`（单字段）或 `items`（多字段批量时）、目标值（原始 PLC 值，非人类可读标签，见 FR2-6）、请求 ID（用于追踪回执）、发起用户。 | **P3 + P4 修订** |
| FR3-3 | MQTT 命令 topic 格式（**已确认**）：下发命令使用 `/datacollection/plc/write/command/{specific_part}`，回执使用 `/datacollection/plc/write/ack/{specific_part}`。与现有采集 topic `/datacollection/plc/to/collector/#` 不冲突。 | 不变 |
| FR3-4 | 后端收到前端设置请求后，同步在**独立操作记录表**（`plc_write_record`，见 FR6）写入 `status=pending` 记录（批量时每个字段独立一条），然后异步发布 MQTT 命令，立即返回 202 Accepted（附带 `request_id` 或 `request_ids` 列表）。 | **P4 小幅修订** |
| FR3-5 | MQTT 发布须使用至少 QoS 1，保证消息至少送达一次。 | 不变 |
| FR3-6 | **【新增，P2 Bug 修复验收】** 端到端链路必须实际可达（非 mock）：API → MQTT publish → PLCWriteSubscriber 订阅 → 写 PLC → 回执 → DB 更新。开发完成后必须提供可重现的**真实写入冒烟用例**（以真实 PLC 设备为目标，记录完整请求/响应日志），证明链路无异常。不得仅凭 unit test mock 通过验收。 | **P2 Bug 修复** |

**[Q3 已决策]** MQTT topic 命名规范：
- 命令下发：`/datacollection/plc/write/command/{specific_part}`
- 结果回执：`/datacollection/plc/write/ack/{specific_part}`

**[Q4 已决策]** 操作记录存储：**独立建表**（表名 `plc_write_record`），不复用 `device_param_history`。详见 FR6。

---

### FR4 — PLC 写入应用侧：订阅 → 写 PLC → 回执 → 落库

**来源**: 用户原始需求第 2 条——"往 plc 写值的应用通过订阅取得任务，成功写入后返回结果同时写入数据库"

经代码确认，`datacollection/plc_write_manager.py` 中已存在 `PLCWriteManager` 类，通过 snap7 协议直接写 PLC DB 区（`write_db_data(db_num, offset, value, data_type)`）。`plc_config.json` 中已定义各 `param_name` 对应的 `db_num`、`offset`、`data_type`。

**[v0.4.0 变更记录]**
- **P2（Bug 修复）**: 端到端链路存在故障，补充 FR4-4 错误分类，要求回执 `error_message` 能区分三类失败原因，辅助运维定位。
- **P3（UX 需求变更）**: 写 PLC 时使用 PLC 原始值（不使用人类可读标签），FR4-2 补充说明，`new_value` 存原始值。

| 编号 | 需求描述 | v0.4.0 变更标注 |
|------|----------|---------------|
| FR4-1 | PLC 写入应用（运行于 `datacollection` 进程或独立进程）订阅写命令 MQTT topic，接收来自 FR3 的命令消息。 | 不变 |
| FR4-2 | 收到命令后，根据 `param_name` 查找 `plc_config.json` 中的 `db_num`、`offset`、`data_type`，通过 snap7 向目标 PLC IP 写入指定值。写入时使用 PLC 原始值（如整型 `1` 表示"开"），不使用 UI 层的人类可读标签（见 FR2-6，映射在 UI 层做）。 | **P3 补充说明** |
| FR4-3 | 写入成功后，向回执 MQTT topic 发布结果消息（包含：`request_id`、`specific_part`、`param_name`、写入值（PLC 原始值）、`success=true`、`written_at` 时间戳）。 | 不变 |
| FR4-4 | 写入失败后，向回执 MQTT topic 发布结果消息（包含：`request_id`、`success=false`、`error_message`、**结构化失败原因**）。**【P2 Bug 修复验收】** `error_message` 必须能区分以下三类失败，让运维可定位：① `"MQTT_UNREACHABLE"` — MQTT 通道不可达（broker 连接失败）；② `"SUBSCRIBER_NOT_CONSUMING"` — PLCWriteSubscriber 未订阅/未消费命令（命令超时未处理）；③ `"PLC_WRITE_FAILED: {detail}"` — PLC 写入失败（含 snap7 原始错误信息）。错误提示文案在 UI 层基于此分类展示，不得再笼统显示"下发通道异常"。 | **P2 Bug 修复** |
| FR4-5 | 无论成功或失败，回执消息同时更新 `plc_write_record` 表中对应 `request_id` 的记录（`status=success`/`failed`，补充 `acked_at`、`error_message`），字段至少包含：`specific_part`、`param_name`、`old_value`、`new_value`（PLC 原始值）、`success`、`error_message`、`acked_at`、`request_id`、`operator`、`status`。 | **P3 `new_value` 语义明确** |
| FR4-6 | 写入应用在 PLC 连接失败时（snap7 连接超时），视为写入失败，按 FR4-4 处理（错误类型归类为 `PLC_WRITE_FAILED`）。 | **P2 补充** |

---

### FR5 — 设置页面自动刷新写入结果（MQTT-over-WebSocket 实时推送）

**来源**: 用户原始需求第 3 条——"设置页面可以自动刷新结果"

**[Q5 已决策]** 刷新机制：采用 **MQTT-over-WebSocket 实时推送**，不使用轮询。前端订阅 `/datacollection/plc/write/ack/{specific_part}` topic（通过 WebSocket 连接 MQTT broker 的 WebSocket 端口 **32797**，broker 地址 `192.168.31.98:32797`），在收到回执消息时立即更新 UI。

| 编号 | 需求描述 |
|------|----------|
| FR5-1 | 设置面板打开时，前端通过 MQTT-over-WebSocket 订阅当前 `specific_part` 的回执 topic（`/datacollection/plc/write/ack/{specific_part}`），实时接收写入结果推送。 |
| FR5-2 | 用户下发设置命令后，UI 应在收到 MQTT 推送时（写入成功或失败）立即更新对应参数的当前值和写入状态（成功/失败标识），用户可见延迟 **≤ 10 秒**。 |
| FR5-3 | 自动刷新（MQTT 推送到达触发 UI 更新）期间不得重置用户已填写但未下发的输入框内容。 |
| FR5-4 | 命令下发后 30 秒内未收到任何回执，UI 展示"等待超时"状态，"确认"按钮恢复可点击，提供"重试"操作。 |
| FR5-5 | 面板关闭时，前端断开 WebSocket 订阅，释放连接资源。 |

---

## 3. 非功能性需求

### NFR-1 — 实时性

**[Q6 已决策]** 端到端延迟上限：**≤ 10 秒**（用户点击"确认"至 UI 呈现写入结果）。超时阈值 30 秒保持不变。

| 编号 | 需求描述 |
|------|----------|
| NFR-1-1 | 用户点击"确认"至 UI 呈现写入结果（成功或失败）的端到端延迟：正常情况下 **≤ 10 秒**（含 MQTT 传输 + PLC 写入 + 回执传输 + WebSocket 推送至 UI 更新）。 |
| NFR-1-2 | 超过 30 秒未收到回执，UI 呈现超时提示，"确认"按钮恢复可点击。 |

### NFR-2 — 失败处理

| 编号 | 需求描述 |
|------|----------|
| NFR-2-1 | PLC 写入失败（连接超时、snap7 错误）时，UI 展示具体错误原因（来自 FR4-4 的 `error_message`）。 |
| NFR-2-2 | MQTT 发布失败（broker 不可达）时，后端返回 503，UI 展示"下发通道异常，请稍后重试"。 |
| NFR-2-3 | 网络中断导致回执丢失时，UI 展示超时提示（FR5-4），并保留"重试"按钮，允许用户重新下发命令。 |
| NFR-2-4 | 用户在"设置"面板关闭后，未完成的写入任务依然在后台执行并记录结果（落库），不因 UI 关闭而丢弃。 |

### NFR-3 — 并发与幂等

| 编号 | 需求描述 |
|------|----------|
| NFR-3-1 | 同一 `specific_part` 的同一 `param_name`，在前一次写入结果未返回期间，"确认"按钮应置为不可点击（loading 状态），防止重复下发。 |
| NFR-3-2 | 若多个用户同时对同一 `specific_part` 发起写操作，后端不得互相覆盖命令记录；每次写操作应有独立的 `request_id`。 |
| NFR-3-3 | 重复的 `request_id` 回执消息应被幂等处理（不重复写库）。 |

**[Q7 已决策]** 并发写锁定：该场景**不实际存在**，无需实现"先写者占用"锁机制。每次写操作保持独立 `request_id` 即可（原 NFR-3-2 保留）。

### NFR-4 — 安全

| 编号 | 需求描述 |
|------|----------|
| NFR-4-1 | 设置命令的后端接口须验证 Token（`IsAuthenticated`），未认证请求直接返回 401。 |
| NFR-4-2 | 每次写操作记录发起用户（`operator` 字段），作为最基本的操作留痕。 |

**[Q8 已决策]** 权限粒度：**所有登录用户均可写任意设备**，不区分角色（admin/user 均等权限）。后端只验证 Token（`IsAuthenticated`），不做 `specific_part` 所有权过滤。

**[Q9 已决策]** 审计日志与回滚：**需要审计日志查询页面**（独立 FR6，本期只读）。**回滚功能延后至下期**（2026-05-19 用户确认），见第 4 节 Out of Scope 第 6 条。

---

## 4. 范围外（Out of Scope）

以下内容**明确不在**本次迭代范围内：

1. 批量设置：一次操作对多个 `specific_part` 批量写参数。
2. 定时/计划设置：按时间计划自动下发参数值。
3. 新风机、水力模块、能耗表、空气品质传感器等设备的参数设置（本次仅对 `main_thermostat` 和 `panel_*` 的面板参数进行需求建模，其他 sub_type 的可写性待明确后可在后续迭代加入）。
4. 移动端 / 微信小程序设置入口。
5. 修改 `plc_config.json` 中的 PLC 地址映射本身（参数地址由现场配置决定，不在 Web 设置范围）。
6. **回滚功能（延后至下期）**：审计日志页面对 `status=success` 记录的"回滚"操作（将 `old_value` 重新下发）。本期审计日志页面为只读查询；`plc_write_record` 表的 `error_message` 字段本期保留（下期回滚时可写入 `rollback_from={source_request_id}`），本期不写入回滚溯源信息。

---

## 5. FR6 — 审计日志查询页面（只读，新增）

**来源**: 用户决策 Q9 ——"需要审计日志查询页面"

**本期范围说明**：本期 FR6 仅实现**只读**查询，不含回滚功能。回滚延后至下期实现（见第 4 节 Out of Scope）。

| 编号 | 需求描述 |
|------|----------|
| FR6-1 | 在 Web 端新增"设置记录"（或"审计日志"）查询页面，允许已登录用户查询 `plc_write_record` 表中的操作记录。 |
| FR6-2 | 查询条件支持：`specific_part`（精确或模糊）、时间范围（`created_at`）、操作人（`operator`）、操作结果（`status`：pending/success/failed）。 |
| FR6-3 | 查询结果列表展示字段：`request_id`、`specific_part`、`param_name`、`old_value`（写入前）、`new_value`（写入目标值）、`operator`、`status`、`created_at`（下发时间）、`acked_at`（回执时间）、`error_message`（失败原因，若有）。 |
| FR6-4 | 列表支持分页（每页 20 条），按 `created_at` 降序排列。 |

**独立操作记录表字段设计（`plc_write_record`）**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | BIGINT AUTO_INCREMENT | 主键 |
| `request_id` | VARCHAR(64) UNIQUE | 唯一写入请求 ID（UUID） |
| `specific_part` | VARCHAR(20) | 目标设备标识 |
| `param_name` | VARCHAR(100) | 参数名 |
| `old_value` | VARCHAR(50) | 写入前的当前值（来自 `plc_latest_data`，写命令下发时快照） |
| `new_value` | VARCHAR(50) | 目标写入值 |
| `operator` | VARCHAR(150) | 发起用户 username |
| `status` | VARCHAR(20) | 状态：`pending` / `success` / `failed` / `timeout` |
| `error_message` | TEXT NULL | 失败原因（失败时填写） |
| `created_at` | DATETIME | 命令下发时间（后端写入） |
| `acked_at` | DATETIME NULL | 收到 PLC 回执时间 |

---

## 6. Open Questions

### Q1~Q9（v0.3.0 已全部决策）

| 编号 | 决策摘要 | 落地位置 |
|------|---------|---------|
| Q1 | DeviceConfig + DeviceAttrDef 协同 | FR2 |
| Q2 | 温度/开关可写；露点/故障/实测只读 | FR2-2 |
| Q3 | `/datacollection/plc/write/command/{sp}` + `/ack/{sp}` | FR3-3 |
| Q4 | 独立建表 `plc_write_record` | FR3-4、FR6 |
| Q5 | MQTT-over-WebSocket 实时推送 | FR5 |
| Q6 | 端到端 ≤ 10 秒，超时 30 秒 | NFR-1 |
| Q7 | 不存在并发写同一户场景，无需锁 | NFR-3 |
| Q8 | 所有登录用户均可写 | NFR-4 |
| Q9 | 需要审计日志查询页面（只读，本期）；回滚延后至下期 | FR6 |

### Q10~Q13（v0.4.0 新增，已全部决策）

| 编号 | 问题描述 | 决策结果 | 影响范围 |
|------|---------|---------|---------|
| Q10 | **批量下发协议** | **已决策（用户 2026-05-19）**：采用"一条 MQTT 命令多 item"方案，payload 结构：`{ request_id, specific_part, operator, items: [{param_name, new_value, data_type}], submitted_at }`，单个 request_id 对整批命令。后端 `device_settings_write` 接口需改造为接受 `items` 数组；PLCWriteSubscriber 需循环处理每个 item。 | FR2-7、FR3-1、FR3-2、FR3-4、FR4-1 |
| Q11 | **人类可读映射表来源** | **已决策（用户 2026-05-19）**：使用**后端 Python 常量文件**（如 `api/param_value_label.py`），无 DB migration。GET `/params/<specific_part>/` 返回时附带 `value_options: [{raw, label}]`（dropdown 选项）和当前值的 `display_value`；前端只负责展示，零业务逻辑。 | FR2-6、FR2-3 |
| Q12 | **`plc_write_record.new_value` 存储语义** | **已决策（用户 2026-05-19）**：`new_value` 存 PLC 原始值（如 `"1"`），不存人类可读标签。审计日志页（US-9）展示时由前端（或 API）做映射（如展示 `"1 (开)"`）。无 DB schema 变化，零 migration。 | FR2-6、FR4-5、FR6-3 |
| Q13 | **`select_values_json` 当前数据状态（P1 根因）** | **已决策（2026-05-19）**：P1 根因留给开发阶段自查，analyst 不在需求阶段做代码级定位。开发阶段需核查 `DeviceAttrDef.select_values_json` 数据是否为空、`views_device_settings.py` `attr_tag` 匹配逻辑是否正确、前端 `parseSelectOptions` 是否正确解析。 | FR2-3（P1 Bug 修复） |

---

## 附录 A：已确认的领域事实（来自代码验证）

| 事实 | 来源文件 |
|------|---------|
| 操作列已存在"设备面板"和"PLC历史"两个按钮 | `DeviceManagementDeviceListView.vue` 第 136-155 行 |
| `DeviceConfig` 表字段：`param_name`, `display_name`, `group`, `sub_type`, `sub_type_display`, `is_active` | `models.py` 第 366-392 行 |
| `DeviceAttrDef` 表字段：`product_code`, `attr_tag`, `attr_value_type`（1=枚举/2=数值）, `attr_constraint`, `select_values_json`, `num_value_json` | `models.py` 第 542-565 行 |
| 现有采集 MQTT topic：`/datacollection/plc/to/collector/#` | `mqtt_consumer_service.py` 第 62 行 |
| PLC 写入能力已存在（snap7），`PLCWriteManager._write_single_plc_with_mode` 中通过 `write_db_data(db_num, offset, value, data_type)` 写入 | `plc_write_manager.py` 第 268-327 行 |
| `plc_config.json` 已定义各 param 的 `db_num`, `offset`, `data_type`（如 `living_room_temp_setting`: db14/offset1336/int16） | `plc_config.json` 全文 |
| `PLCLatestData` 表存储每个 `(specific_part, param_name)` 的最新值 | `models.py` 第 327-362 行 |
| 用户角色：`admin` 和 `user` 两种，Token 鉴权 | `models.py` 第 9-13 行，`views.py` 第 59-69 行 |
| MQTT broker 地址：`192.168.31.97:32795`（来自 `mqtt_consumer.py`） | `mqtt_consumer.py` 第 62-63 行 |
