# 需求规格说明书增量 — FreeArk v0.5.7 按房型过滤设备面板与采集点裁剪

```
file_header:
  document_id: REQ-SPEC-v0.5.7
  title: FreeArk v0.5.7 — 按房型过滤设备面板、参数设置与 PLC 采集点裁剪
  author_agent: sub_agent_system_architect (via PM Orchestrator, incremental revision)
  project: FreeArk 能耗采集平台
  version: v0.5.7-fix2
  created_at: 2026-05-22
  revised_at: 2026-05-23
  status: APPROVED
  revision_note: |
    PM 决策锁定（2026-05-22）：
    - OQ-v0.5.7-02 = 方案 B（设备树未同步时仅显示系统级面板，panel_* 全部隐藏）
    - OQ-v0.5.7-03 = 不纳入本版本（存量清理留后续，FR-v0.5.7-06 标记为本版本不实施）
    - OQ-v0.5.7-04 = 纳入本版本（采集侧裁剪必须实现，FR-v0.5.7-05 升级为必须项）
    fix2 修订（2026-05-23，生产验证 bug 修复）：
    - FR-v0.5.7-01 补充验收标准校正条目（FR-CORR-v0.5.7-01）：
      4 房户型识别口径由「房间总数 ≥ 4」更正为「同时含书房 AND 含儿童房」。
      根据生产全量 40 个专有部分扫描结果，书房存在与否 100% 吻合四房/三房划分，
      无例外，取代原启发式房间数判断。
  base_document: docs/requirements_spec.md (v1.0.0)
  references:
    - FreeArkWeb/backend/freearkweb/api/models.py
    - FreeArkWeb/backend/freearkweb/api/views.py (get_device_realtime_params, L1595)
    - FreeArkWeb/backend/freearkweb/api/views_device_settings.py (device_settings_params)
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (PLCLatestDataHandler, PLCDataHandler)
    - FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py
    - datacollection/resource/plc_config.json
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue
    - FreeArkWeb/frontend/src/views/DeviceManagementSettingsView.vue
```

---

## 1. 背景与问题陈述

### 1.1 问题来源

来源：PM（用户）2026-05-22 描述，结合代码与数据模型的实证分析。

FreeArk 平台服务多种户型（三房、四房等），各户型的实际房间数量不同。例如专有部分 `9-1-10-1001` 有 6 个房间（含书房），而 `9-1-10-1002` 只有 5 个房间（无书房）。

**当前问题**：设备面板（`DeviceCardsView.vue`）、参数设置（`DeviceSettingsPanelView.vue`）均基于统一的 `DeviceConfig` 模板渲染，不区分户型，导致：
1. 不存在的房间的面板（如 `9-1-10-1002` 的「儿童房-温控面板」）仍然显示，但数据为 0 或通讯故障。
2. `plc_latest_data` 和 `device_param_history` 持续写入这些无效数据点。
3. 前端定时刷新和按需采集轮询这些不存在的数据点，浪费资源。
4. 参数设置页面同样显示不存在的房间的温控面板参数，可能导致误操作。

### 1.2 推论验证结论（代码实证）

以下 5 条推论通过代码分析全部得到证实：

| # | 推论 | 验证结论 | 证据来源 |
|---|------|---------|---------|
| 1 | 不同专有部分房间数量不一致 | **证实** | `device_room` 表（`DeviceRoom` model）由设备树同步填充，各专有部分 `floors→rooms` 数量独立；`OwnerManagementView.vue` 展示 `room_count` 字段 |
| 2 | 不存在的房间其 PLC 读数为 0 或通讯故障 | **证实** | `plc_config.json` 中 `fourth_children_room_*` 系列参数有对应 DB14 offset（1564~1578），PLC 全量暴露这些地址；三房户型物理设备缺失时读到通讯故障（`children_room_communication_error` offset=1418 等），`PLCLatestDataHandler` 判定 `success=True`（通讯故障是 PLC 可读到的有效整数值）并落库 |
| 3 | PLC 程序全量提供所有偏移量，兼容所有户型 | **证实** | `datacollection/resource/plc_config.json` 统一定义全部参数，无户型区分；所有专有部分共用同一配置文件进行采集 |
| 4 | 设备面板使用统一 DeviceConfig 模板，无法按户型过滤 | **证实** | `views.py:get_device_realtime_params()` L1625：`DeviceConfig.objects.filter(is_active=True)`，**不含** `specific_part` 过滤；`device_settings_params()` 同样如此（L137-141）。当前唯一的隐性过滤是「PLCLatestData 中无记录则跳过」（L1652-1654），但通讯故障等非零值已有记录，无法起到过滤效果 |
| 5 | plc_latest_data / device_param_history 写入冗余数据 | **证实** | `PLCLatestDataHandler._bulk_upsert()`（mqtt_handlers.py L847）无房型约束，全量 upsert；`_write_history()` 同样无约束，每小时追加一条；`PLCDataHandler.batch_save_plc_data()` 也无房型约束 |

**重要补充说明**（推论 4 的精确化）：

当前 `get_device_realtime_params()` 的逻辑是：先枚举 DeviceConfig，再从 PLCLatestData 中查找对应记录。当不存在的房间（如儿童房）的参数被 PLC 读到并因通讯故障标记为非零值写入 PLCLatestData 后，这些参数确实存在于数据库中，因此 `latest_by_param.get(cfg.param_name)` 不会返回 None，面板会显示这些数据（通讯故障=1 等无效值）。这与 PM 观察到的现象完全一致。

---

## 2. 业务目标

| 编号 | 目标 |
|------|------|
| BG-01 | 设备面板仅显示该专有部分实际存在的房间的温控面板，消除无效面板展示 |
| BG-02 | 参数设置页面仅显示实际存在的房间的可写参数，避免对不存在设备的误操作 |
| BG-03 | 后端仅对实际存在的房间数据点落库，减少 plc_latest_data 和 device_param_history 的冗余数据 |
| BG-04 | 前端定时刷新与按需采集仅轮询实际存在的数据点，减少无效 PLC 读操作 |
| BG-05 | 以「业主信息-设备树（DeviceFloor/DeviceRoom）」中的房间数据作为房型真值来源（SSOT） |

---

## 3. 约束与假设

| 编号 | 约束/假设 |
|------|---------|
| C-v0.5.7-01 | 房型真值来源为 `device_room` 表中已同步的房间名（`ori_room_name`），该数据已由「同步设备树」功能从屏侧采集 |
| C-v0.5.7-02 | `DeviceConfig.sub_type` 与 `DeviceRoom.ori_room_name`（或 `room_name`）之间需要建立映射关系；具体映射策略由架构阶段决策 |
| C-v0.5.7-03 | 若某专有部分尚未完成设备树同步（即 `device_room` 表中无该 specific_part 的记录），系统行为需明确定义（降级策略待架构确认） |
| C-v0.5.7-04 | PLC 采集侧（datacollection 进程）的房型裁剪**已纳入本版本**（PM OQ-v0.5.7-04 决策）。具体改造：后端按需采集接口在发布 MQTT ondemand 指令时，在 payload 中附带 `allowed_params` 白名单；采集侧 `OndemandCollectSubscriber` 读取白名单后仅读取白名单内的 PLC 地址。风险评估见 ADR-v0.5.7-06-rev1。 |
| C-v0.5.7-05 | 已存在于 plc_latest_data 和 device_param_history 的冗余数据的清理策略：**本版本不实施**（PM OQ-v0.5.7-03 决策），存量数据保留，后续单独处理。 |
| C-v0.5.7-06 | 不引入新的数据库表（利用现有 DeviceFloor / DeviceRoom 表） |
| C-v0.5.7-07 | 不修改 PLC 采集侧（datacollection）进程的核心采集逻辑，仅在 MQTT 消费/落库侧增加过滤（若本次包含该需求） |

---

## 4. 功能性需求（FR）

### FR-v0.5.7-01：设备面板按房型动态渲染

**来源**：PM 描述「设备面板应当根据业主信息-设备数明细中的房间信息来显示」

**描述**：
- `GET /api/devices/realtime-params/?specific_part={sp}` 接口的响应中，温控面板类子类型（`panel_study_room`、`panel_bedroom`、`panel_children_room`、`panel_fourth_children`）**仅在**该专有部分的 `device_room` 表中存在对应房间时才出现。
- 主温控（`main_thermostat`）、新风（`fresh_air`）、能耗表（`energy_meter`）、水力模块（`hydraulic_module`）、空气品质（`air_quality`）不受房型约束，始终显示（若有数据）。
- 若该专有部分尚未同步设备树，系统应降级处理（见 C-v0.5.7-03）。

**验收标准（针对代码实证）**：
- `device_room` 表中 `specific_part=9-1-10-1002` 无「儿童房」对应记录时，API 响应中不应包含 `panel_fourth_children` 子类型。
- `device_room` 表中 `specific_part=9-1-10-1001` 有「书房」对应记录时，API 响应中应包含 `panel_study_room` 子类型（若有 PLCLatestData 记录）。

**FR-CORR-v0.5.7-01（fix2 校正条目，2026-05-23）：四房户型识别口径**

来源：生产验证 bug 报告（2026-05-23）——`_match_panel_sub_types()` 中
`len(ori_room_names) >= 4` 在三房户型（房间总数同样 ≥ 4，含全屋/客厅等非卧室）
误触发 `panel_fourth_children`，导致 `9-1-10-1001` 与 `9-1-10-1002` 功能等同，
修复无效。

**生产全量扫描依据**（40 个专有部分，100% 吻合，无例外）：
- 4 房大户型（尾号 01/04）：房间集含「书房」→ 6 个房间
- 3 房小户型（尾号 02/03）：房间集不含「书房」→ 5 个房间
- 关键样本：
  - `9-1-10-1001` 房间集：主卧、书房、儿童房、全屋、客厅、次卧（含书房 → 四房）
  - `9-1-10-1002` 房间集：主卧、儿童房、全屋、客厅、次卧（无书房 → 三房）

**校正规则**：`panel_fourth_children` 的激活条件由「含儿童房 AND 房间数 ≥ 4」
更改为「**含书房 AND 含儿童房**」。

**新验收标准**：
- `9-1-10-1001`（含书房 + 含儿童房）：`panel_fourth_children` 激活
- `9-1-10-1002`（不含书房，仅含儿童房）：`panel_fourth_children` **不激活**
- 无「儿童房」关键词的任何户型：`panel_fourth_children` 不激活（无论是否有书房）

---

### FR-v0.5.7-02：参数设置页面按房型过滤温控面板参数

**来源**：PM 描述「参数设置页面也不应显示不存在的房间温控面板」

**描述**：
- `GET /api/device-settings/params/{specific_part}/` 接口的响应中，温控面板类参数分组同样按 `device_room` 表中的房间信息过滤。
- 非温控面板类参数（新风、水力模块等）不受影响。

---

### FR-v0.5.7-03：后端落库时过滤不存在房间的数据点（plc_latest_data）

**来源**：PM 描述「plc_latest_data 不再写入无效信息」

**描述**：
- `PLCLatestDataHandler` 在写入 `plc_latest_data` 前，应检查该 `specific_part` 的 `device_room` 表中是否存在与参数对应的房间。
- 对应房间不存在的温控面板参数（`panel_study_room`、`panel_bedroom`、`panel_children_room`、`panel_fourth_children` 下的参数），跳过落库。
- 非温控面板类参数（系统级参数、新风、能耗表、水力模块、空气品质）不受影响，照常写入。
- 过滤行为应记录 debug 日志，便于排查。

---

### FR-v0.5.7-04：后端落库时过滤不存在房间的数据点（device_param_history）

**来源**：PM 描述「device_param_history 不再写入无效信息」

**描述**：
- `PLCLatestDataHandler._write_history()` 中使用与 FR-v0.5.7-03 相同的房型过滤逻辑，过滤后的参数不写入 `device_param_history`。

---

### FR-v0.5.7-05：采集侧按需采集仅读取实际存在的数据点（**必须项，本版本实现**）

**来源**：PM 描述「定时刷新也不再采集不必要的信息」；PM OQ-v0.5.7-04 决策（2026-05-22 锁定）

**描述**：
- 前端 `DeviceCardsView.vue` 的 `triggerOndemandRefresh()` 调用 `POST /api/devices/ondemand-refresh/`。
- 后端按需采集接口在发布 MQTT ondemand 请求指令时，在 payload 中附带 `allowed_params` 字段（过滤后的参数名白名单）。
- 采集侧 `OndemandCollectSubscriber._execute_ondemand()` 读取 payload 中的 `allowed_params`，仅构建白名单内的 PLC 读取配置，**不发起**白名单外的 PLC 地址读取。
- 若 payload 中无 `allowed_params` 字段（向后兼容旧版 Django），采集侧降级为全量采集（原有行为）。
- 定时刷新（`startAutoRefresh()`）通过 `fetchData()` 从 DB 读取，FR-v0.5.7-03/04 实现后 DB 中自然无冗余数据，无需采集侧额外配合。

**验收标准（PM OQ-v0.5.7-04 口径）**：
- 按需采集触发后，采集侧**实际不发起**不存在房间参数的 PLC DB 地址读取（通过采集侧日志验证：`allowed_params` 白名单已过滤，未进行相应 DB offset 读取）。

---

### FR-v0.5.7-06：已有冗余数据的清理【本版本不实施】

**来源**：PM 描述「对 plc_latest_data / device_param_history 已有冗余数据的处理策略」

**PM 决策**（OQ-v0.5.7-03，2026-05-22）：**本版本不实施**。v0.5.7 只保证新数据不再落库无效记录，存量冗余数据保留，后续单独处理。不开发 `cleanup_invalid_device_params` 管理命令。

**描述**（留存供后续版本参考）：
- 为已存在的冗余数据提供可选的清理机制（management command 或迁移脚本），执行后删除不存在房间的数据点。
- 后续版本（v0.5.8 或独立 bugfix）实施时，参考 M6 模块设计草案。

---

## 5. 非功能性需求（NFR）

### NFR-v0.5.7-01：房型过滤应为缓存友好设计

**来源**：性能考量

- `device_room` 查询结果（某专有部分的有效房间列表）应考虑内存缓存或简单本地缓存，避免每次 API 请求都查库。建议缓存 TTL 与设备树同步周期对齐。

### NFR-v0.5.7-02：降级行为明确定义

**来源**：C-v0.5.7-03；PM OQ-v0.5.7-02 决策（2026-05-22 锁定）

- **已锁定方案 B**（PM OQ-v0.5.7-02 决策）：若某专有部分尚未同步设备树（`device_floor` 表中无该 specific_part 记录），系统仅显示系统级面板（`main_thermostat`、`fresh_air`、`energy_meter`、`hydraulic_module`、`air_quality`），所有 `panel_*` 房间温控面板隐藏。
- 此策略适用于设备面板（FR-v0.5.7-01）和参数设置页面（FR-v0.5.7-02）。

### NFR-v0.5.7-03：向后兼容性

**来源**：架构约束

- 对既有已同步设备树的专有部分，行为应与期望一致（显示正确的房间面板）。
- 对 API 响应结构，不引入 breaking change：响应结构不变，仅过滤掉不存在的 sub_type。

---

## 6. 影响分析

### 6.1 受影响的后端模块

| 模块/文件 | 变更类型 | 变更说明 |
|-----------|---------|---------|
| `api/views.py` → `get_device_realtime_params()` | 修改 | 增加房型过滤逻辑（按 device_room 过滤 sub_type） |
| `api/views_device_settings.py` → `device_settings_params()` | 修改 | 同上，过滤温控面板参数分组 |
| `api/mqtt_handlers.py` → `PLCLatestDataHandler` | 修改 | `_bulk_upsert()` 和 `_write_history()` 增加房型过滤 |
| `api/views.py` → 按需采集接口（`ondemand_refresh`） | 修改（可选） | 传递过滤后的参数列表给采集侧 |
| `api/models.py` | 无变更 | 现有 DeviceRoom 表已满足需求 |

### 6.2 受影响的前端模块

| 文件 | 变更类型 | 变更说明 |
|------|---------|---------|
| `DeviceCardsView.vue` | 无需修改 | 后端过滤后，前端渲染逻辑无需改动（已有空 sub_type 的移除逻辑） |
| `DeviceManagementSettingsView.vue` / `DeviceSettingsPanelView.vue` | 无需修改 | 后端过滤后前端自然正确 |

### 6.3 受影响的数据表

| 表名 | 影响 |
|------|------|
| `plc_latest_data` | 减少写入（不存在房间的参数不再落库）；已有数据可选清理 |
| `device_param_history` | 减少写入；已有数据可选清理 |
| `device_room` | 读取（作为房型真值来源，无写入） |
| `device_floor` | 读取（通过 owner→floors→rooms 关联查询） |

---

## 7. 开放问题与待决策项

| 编号 | 问题 | 状态 | PM 决策 |
|------|------|------|--------|
| OQ-v0.5.7-01 | `DeviceConfig.sub_type` 与 `DeviceRoom.ori_room_name` 的映射规则如何定义？ | **已决策** | 静态映射表，架构阶段确定（ADR-v0.5.7-02） |
| OQ-v0.5.7-02 | 未完成设备树同步的专有部分降级策略？ | **已决策**（2026-05-22） | **方案 B**：仅显示系统级面板，所有 `panel_*` 隐藏 |
| OQ-v0.5.7-03 | 已有冗余数据是否清理？ | **已决策**（2026-05-22） | **不纳入本版本**，存量数据保留，后续单独处理 |
| OQ-v0.5.7-04 | 采集侧（datacollection）裁剪是否纳入本版本？ | **已决策**（2026-05-22） | **纳入本版本**（与架构初稿 ADR-06 相反），必须实现 FR-v0.5.7-05 |
| OQ-v0.5.7-05 | 缓存策略：进程内字典缓存 vs Django cache framework？ | **已决策** | 进程内字典缓存，TTL=300s，设备树同步后主动清除（ADR-v0.5.7-05） |
