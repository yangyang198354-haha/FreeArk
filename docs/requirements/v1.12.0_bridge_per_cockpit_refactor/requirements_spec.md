# 需求规格说明书

**文档编号**: REQ-SPEC-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 0.1.0
**状态**: APPROVED
**创建日期**: 2026-07-08
**作者**: sub_agent_requirement_analyst
**上游任务**: 重写舰桥页面子系统状态判定逻辑，从全局聚合改为 per-座舱（specific_part）粒度，数据对齐 Web 设备面板

---

## 版本历史

| 版本  | 日期       | 变更摘要 |
|-------|------------|---------|
| 0.1.0 | 2026-07-08 | 初始草稿，基于 PM 业务需求输入 |

---

## 1. 执行摘要

### 1.1 业务背景

FreeArk 微信小程序舰桥页面（`miniprogram/pages/home/index.vue`）当前有四个子系统模块卡片：新风模块、水力模块、空气品质模块、能耗表。点开卡片弹出 FaultDrawer 抽屉，显示故障事件和设备参数。

经过代码分析发现以下关键问题：
1. **子系统状态是全局聚合，不是 per-座舱的**：新风/水力/空气品质的状态来自 `GET /api/dashboard/device-fault-summary/`（`views.py:1563`），该 API 对 `FaultEvent` 表做全局 COUNT，不带 `specific_part` 过滤，所有座舱看到的子系统状态完全一样。
2. **能耗模块状态来源不合理**：走的是全局 PLC 在线率 + 关键词匹配全局 FaultEvent 的混合逻辑，与本座舱的实际能耗设备无关。
3. **Web 设备面板是 per-specific_part 的**：`DeviceCardsView.vue` 调用 `GET /api/devices/realtime-params/?specific_part={sp}` 返回该 specific_part 的 PLC 寄存器最新值，按 `group → sub_type → params` 嵌套，子系统类型白名单为 `['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']`。小程序应与 Web 保持一致。
4. **不同专有部分的设备配置不同**：有些户可能没有新风、没有水力模块等，舰桥页面应当根据该 specific_part 实际拥有的设备动态显示。

_来源引用：PM 需求输入"子系统状态是全局聚合，不是 per-座舱的"、"Web 设备面板是 per-specific_part 的"、"不同专有部分的模块/房间可能不同"。_

### 1.2 需求总览

| 类别 | 数量 |
|------|------|
| 功能需求（REQ-FUNC） | 13 条 |
| 非功能需求（REQ-NFUNC） | 4 条 |
| 用户故事（US） | 8 条 |
| 推断性需求（[INFERRED]） | 0 条 |

### 1.3 范围

**本版本包含：**
- 小程序舰桥页面子系统模块（新风/水力/空气品质/能耗）状态判定逻辑重构为 per-座舱粒度
- 子系统状态数据来源从全局 FaultEvent 聚合改为座舱 PLC 实时参数
- 能耗模块状态从全局 PLC 在线率 + 关键词匹配改为座舱能耗表 PLC 参数判定
- FaultDrawer 抽屉的设备参数展示对齐 Web `DeviceCardsView.vue` 系统设备面板
- 根据座舱（specific_part）实际拥有的设备动态决定显示哪些子系统模块
- 根据座舱实际结构动态决定显示哪些房间
- 新风机 `fresh_air_fault_status` 位域逐 bit 展开为具名故障

**本版本明确不包含：**
- 赛博朋克视觉风格的任何修改（仅更改数据读取和状态判定逻辑）
- admin/operator 角色的 Material Design 仪表盘的任何修改
- Web 端（`DeviceCardsView.vue`）的任何行为变更
- 后端新增 API（复用现有 `GET /api/miniapp/owner/realtime-params/`、`GET /api/miniapp/owner/structure/`、`GET /api/miniapp/owner/connectivity/`）
- ArkTabBar 或其他 tab 页面的改动
- 故障创建/编辑/恢复操作（仅展示）

_来源引用：PM 需求输入"保持现有 cyberpunk 视觉风格不变，只改数据读取和状态判定逻辑"、约束"后端已有 API 端点"、"需向后兼容，不破坏现有 admin/operator 的 Material Design 布局"。_

### 1.4 关键约束

- **C-01 零后端改动**：所有数据来自现有小程序业主 API（`/api/miniapp/owner/` 系列），不新增或修改后端接口。_来源：PM 约束"后端已有 GET /api/miniapp/owner/realtime-params/ 端点"。_
- **C-02 视觉风格不变**：赛博朋克色板、字体、动画、装饰元素保持现状，仅修改 `useBridgeDashboard.js` 中的状态聚合逻辑和相关数据读取路径。_来源：PM 约束"保持现有 cyberpunk 视觉风格不变"。_
- **C-03 向后兼容 admin/operator**：`admin/operator` 路径走 Material Design 布局，本版本不触碰该路径的任何代码。_来源：PM 约束"需向后兼容，不破坏现有 admin/operator 的 Material Design 布局"。_
- **C-04 角色数据隔离保持**：owner（role=user）仅可见其绑定 specific_part 的数据，通过业主专属 API 获取，受 IsOwnerUser 中间件鉴权保护。_来源：v1.8.0 业主隔离体系，本版本不修改鉴权逻辑。_
- **C-05 代码直接提交 main**：不新建分支。_来源：PM 约束。_

---

## 2. 现有系统关键事实（需求依据）

> 本节引用 PM 提供的代码探索结果，作为需求推理的事实基础。

### 2.1 受影响的文件清单

| 文件 | 当前行为 | 需要变更 |
|------|---------|---------|
| `miniprogram/composables/useBridgeDashboard.js` | 子系统状态来自 `getDashboardDeviceFaultSummary()`（全局）和 `getDashboardPlcOnlineRate()`（全局）；`deriveEnergyStatus()` 用关键词匹配全局 FaultEvent | 子系统状态改用 `getOwnerRealtimeParams(sp)` 的 PLC 实时参数判定；移除对全局聚合 API 的依赖 |
| `miniprogram/pages/home/index.vue` | 调用 `useBridgeDashboard().state.subsystems` 渲染子系统隔舱 | 接口不变（composable 输出结构保持一致），模板无需修改 |
| `miniprogram/store/owner.js` (ownerStore) | 管理座舱绑定、设备结构、实时参数 | 可能需增加实时参数缓存便利方法（视实现需要） |
| `miniprogram/utils/api.js` | 封装 `getOwnerRealtimeParams(sp)`、`getOwnerStructure(sp)` 等方法 | 无需修改（已有端点） |

_来源引用：PM 需求输入"小程序端已有 api.getOwnerRealtimeParams(sp)、api.getOwnerStructure(sp)"。_

### 2.2 现有 API 端点

| 端点 | 方法 | 鉴权 | 行为 |
|------|------|------|------|
| `GET /api/miniapp/owner/realtime-params/?specific_part={sp}` | GET | IsOwnerUser | 返回该户 PLC 实时参数，keyed by device_sn |
| `GET /api/miniapp/owner/structure/?specific_part={sp}` | GET | IsOwnerUser | 返回 rooms（房间列表）+ system_devices（系统设备列表）+ 设备骨架 |
| `GET /api/miniapp/owner/connectivity/?specific_part={sp}` | GET | IsOwnerUser | 返回 PLC 在线状态 + 大屏心跳状态 |
| `GET /api/dashboard/device-fault-summary/` | GET | 需登录 | 全局 FaultEvent 按 device_type 聚合 COUNT（将移除依赖） |
| `GET /api/dashboard/plc-online-rate/` | GET | 需登录 | 全局 PLC 在线数/总数（将移除依赖） |
| `GET /api/fault-events/?specific_part={sp}&is_active=true` | GET | 需登录 | 该 specific_part 的活跃 FaultEvent 列表（保留用于抽屉故障事件展示） |

_来源引用：PM 需求输入"小程序端已有"清单 + `FreeArkWeb\backend\freearkweb\api\urls_miniapp.py` 代码核查。_

### 2.3 Web 参考实现（`DeviceCardsView.vue`）

| 元素 | 关键定义 |
|------|---------|
| 系统设备子类型白名单 | `SYSTEM_SUB_KEYS = ['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']` |
| 故障参数集合 | `FAULT_PARAMS`（25 个具名字段），值 != 0 则为故障 |
| 新风机故障位展开 | `FRESH_AIR_FAULT_BITS`（9 个 bit）：风机状态故障、出风温度异常状态、进风温度传感器故障、回水温度传感器故障、进水温度传感器故障、加湿器故障、新风水阀故障、防冻保护故障、出风温度传感器故障 |
| 故障判定逻辑 | `getValueClass(param_name, value)`：非零值且属于 FAULT_PARAMS 或匹配 `error_\d+` → 红色告警样式 |
| 数据来源 | `GET /api/devices/realtime-params/?specific_part={sp}` → 按 `group → sub_type → params` 嵌套 |

_来源引用：PM 需求输入"FAULT_PARAMS Set 包含所有故障字段名"、"fresh_air_fault_status 按 9 个 bit 逐位展开" + `FreeArkWeb\frontend\src\views\DeviceCardsView.vue` 代码核查。_

### 2.4 后端故障判定权威规则（`fault_utils.py`）

| 元素 | 定义 |
|------|------|
| `FAULT_PARAM_NAMES` | frozenset（26 个具名故障字段）：25 个 FAULT_PARAMS + `comm_fault_timeout` |
| `_ERROR_N_PATTERN` | `re.compile(r'^error_\d+$')` — PLC 故障码位字段匹配 |
| `is_fault_param(param_name)` | `param_name in FAULT_PARAM_NAMES or _ERROR_N_PATTERN.match(param_name)` |
| `count_faults_for_row(param_name, value)` | `fresh_air_fault_status` → popcount（bit_count）；其他故障字段且 value != 0 → 1 |
| `compute_fault_count_v2(records)` | `sum(count_faults_for_row(pn, v) for pn, v in records)` |

_来源引用：`FreeArkWeb\backend\freearkweb\api\fault_utils.py` 代码核查。_

---

## 3. 功能需求

---

### REQ-FUNC-001：新风模块 per-座舱状态判定

**描述**：系统应当根据当前座舱（specific_part）的新风设备 PLC 实时参数判定新风模块的状态（正常/预警/故障），而非使用全局 `device-fault-summary` API 聚合值。

**来源引用**："子系统模块数据对齐 Web 设备面板：小程序舰桥的新风……应当读取当前座舱（specific_part）的 PLC 实时参数" + "新风/水力/空气品质的状态来自 GET /api/dashboard/device-fault-summary/……这个 API 对 FaultEvent 表做全局 COUNT，不带 specific_part 过滤"

**优先级**：Must Have

**判定规则**：
- 从 `getOwnerRealtimeParams(sp)` 返回的 PLC 参数中，筛选归属于新风设备的字段
- 检查 FAULT_PARAMS 中属于新风的字段（`fresh_air_unit_stop_error`、`fresh_air_unit_communication_error`）
- 对 `fresh_air_fault_status` 执行位域 popcount（每置 1 的 bit 计 1 个故障）
- 任一故障字段非零 → 故障状态；全部为零 → 正常状态
- 设备不存在（structure 中无 fresh_air 设备）→ 不显示新风模块

---

### REQ-FUNC-002：水力模块 per-座舱状态判定

**描述**：系统应当根据当前座舱的水力模块设备 PLC 实时参数判定水力模块的状态，而非使用全局 `device-fault-summary` API 聚合值。

**来源引用**："子系统模块数据对齐 Web 设备面板：小程序舰桥的……水力……应当读取当前座舱（specific_part）的 PLC 实时参数"

**优先级**：Must Have

**判定规则**：
- 从 `getOwnerRealtimeParams(sp)` 返回的 PLC 参数中，筛选归属于水力模块设备的字段
- 检查 FAULT_PARAMS 中属于水力模块的字段（`hydraulic_module_low_temp_error`）
- 非零 → 故障状态；为零 → 正常状态
- 设备不存在 → 不显示水力模块

---

### REQ-FUNC-003：空气品质模块 per-座舱状态判定

**描述**：系统应当根据当前座舱的空气品质传感器 PLC 实时参数判定空气品质模块的状态，而非使用全局 `device-fault-summary` API 聚合值。

**来源引用**："子系统模块数据对齐 Web 设备面板：小程序舰桥的……空气品质……应当读取当前座舱（specific_part）的 PLC 实时参数"

**优先级**：Must Have

**判定规则**：
- 从 `getOwnerRealtimeParams(sp)` 返回的 PLC 参数中，筛选归属于空气品质传感器的字段
- 检查 FAULT_PARAMS 中属于空气品质的字段（`air_quality_sensor_communication_error`）
- 非零 → 故障状态；为零 → 正常状态
- 设备不存在 → 不显示空气品质模块

---

### REQ-FUNC-004：能耗模块 per-座舱状态判定

**描述**：系统应当根据当前座舱的能耗表 PLC 实时参数判定能耗模块的状态，替换当前"全局 PLC 在线率 + 关键词匹配全局 FaultEvent"的判定逻辑。

**来源引用**："能耗模块更奇怪：走的是全局 PLC 在线率 + 关键词匹配全局 FaultEvent 的混合逻辑" + "子系统模块数据对齐 Web 设备面板：小程序舰桥的……能耗……应当读取当前座舱（specific_part）的 PLC 实时参数"

**优先级**：Must Have

**判定规则**：
- 从 `getOwnerRealtimeParams(sp)` 返回的 PLC 参数中，筛选归属于能耗表（energy_meter）设备的字段
- 检查 FAULT_PARAMS 中属于能耗表的字段（`energy_meter_status_communication_error`）以及任何匹配 `error_\d+` 的能耗设备字段
- 任一故障字段非零 → 故障状态；全部为零 → 正常状态
- 设备不存在 → 不显示能耗模块
- 移除对 `ENERGY_KEYWORDS` 关键词匹配和全局 PLC 在线率的依赖

---

### REQ-FUNC-005：按专有部分动态显示子系统模块

**描述**：系统应当根据 `getOwnerStructure(sp)` 返回的 `system_devices` 列表，仅显示该 specific_part 实际拥有的子系统模块，不该有的模块不显示。

**来源引用**："有些户可能没有新风、没有水力模块等" + "舰桥页面应当根据该 specific_part 实际拥有的设备动态显示，不该有的模块不应显示"

**优先级**：Must Have

**判定规则**：
- 读取 `getOwnerStructure(sp)` 中 `system_devices` 数组的设备子类型（sub_type 字段）
- 子类型与 Web 系统设备白名单 `['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']` 匹配
- 匹配到的类型 → 显示对应子系统模块
- 未匹配到的类型 → 不显示该子系统模块
- `subsystems` 数组仅包含该座舱实际拥有的子系统，无对应设备的子系统不出现在渲染列表中

---

### REQ-FUNC-006：按专有部分动态显示房间

**描述**：系统应当根据 `getOwnerStructure(sp)` 返回的 `rooms` 列表，仅显示该 specific_part 实际拥有的房间，房间结构因户而异。

**来源引用**："房间结构也因户而异" + "根据该 specific_part 实际拥有的设备决定显示哪些……房间"

**优先级**：Must Have

**判定规则**：
- 以 `getOwnerStructure(sp)` 的 `rooms` 数组为准
- 出现于 FaultEvent 但不在结构中的房间：不再作为独立房间隔舱渲染（若该座舱有此房间的故障，则由结构数据保证覆盖）
- 未匹配到结构的孤立 FaultEvent 房间：降级为在所属子系统面板中展示，不单独创建房间隔舱

---

### REQ-FUNC-007：FaultDrawer 设备参数对齐 Web 设备面板

**描述**：当业主点击子系统卡片弹出 FaultDrawer 时，抽屉内的设备参数部分应当与 Web 端 `DeviceCardsView.vue` 对应系统设备 sub-panel 内容一致。

**来源引用**："抽屉内容对齐：点击子系统卡片弹出的 FaultDrawer，其设备参数部分应和 Web 设备面板对应 sub-panel 内容一致" + "小程序抽屉打开后应该展示和 Web 设备面板的子系统面板一致的内容"

**优先级**：Must Have

**判定规则**：
- 点击新风卡片 → 抽屉展示新风设备 PLC 参数列表（与 Web `fresh_air` 列一致）
- 点击水力模块卡片 → 抽屉展示水力模块设备 PLC 参数列表（与 Web `hydraulic_module` 列一致）
- 点击空气品质卡片 → 抽屉展示空气品质传感器 PLC 参数列表（与 Web `air_quality` 列一致）
- 点击能耗卡片 → 抽屉展示能耗表 PLC 参数列表（与 Web `energy_meter` 列一致）
- 点击房间卡片 → 抽屉展示该房间内设备 PLC 参数列表
- 参数展示格式与 Web 一致（display_name + 格式化后的值，故障字段红色高亮）

---

### REQ-FUNC-008：新风机故障位域展开

**描述**：当展示新风机设备参数时，系统应当将 `fresh_air_fault_status` 位域值按 9 个 bit 逐位展开为具名故障项，与 Web `DeviceCardsView.vue` 的 `FRESH_AIR_FAULT_BITS` 定义一致。

**来源引用**："新风机故障位展开：fresh_air_fault_status 按 9 个 bit 逐位展开" + "FRESH_AIR_FAULT_BITS = ['风机状态故障', '出风温度异常状态', ...]"

**优先级**：Must Have

**bit 定义**（与 Web 一致）：

| Bit | 故障名称 |
|-----|---------|
| 0 | 风机状态故障 |
| 1 | 出风温度异常状态 |
| 2 | 进风温度传感器故障 |
| 3 | 回水温度传感器故障 |
| 4 | 进水温度传感器故障 |
| 5 | 加湿器故障 |
| 6 | 新风水阀故障 |
| 7 | 防冻保护故障 |
| 8 | 出风温度传感器故障 |

**判定规则**：
- 取 `fresh_air_fault_status` 整数值
- `(value >> bit_index) & 1 === 1` → 该 bit 对应故障激活
- 每个激活的 bit 显示为一条独立故障项
- 所有 bit 均为 0 → 新风机无故障
- 该展开逻辑同时用于：子系统状态计数（popcount）、抽屉参数展示

---

### REQ-FUNC-009：移除对全局 device-fault-summary API 的依赖

**描述**：`useBridgeDashboard.js` 的 `_doFetch()` 方法应当移除对 `api.getDashboardDeviceFaultSummary()` 的调用，子系统状态不再需要该 API 的数据。

**来源引用**："新风/水力/空气品质的状态来自 GET /api/dashboard/device-fault-summary/……这个 API 对 FaultEvent 表做全局 COUNT，不带 specific_part 过滤" + "子系统模块数据对齐 Web 设备面板"

**优先级**：Must Have

**变更范围**：
- 移除 `_doFetch()` 中 `Promise.allSettled` 的第 1 项（`api.getDashboardDeviceFaultSummary()`）
- 移除 `aggregateSubsystemStatus()` 中对 `faultSummary` 参数的依赖
- 替代数据源：`api.getOwnerRealtimeParams(sp)` 的 PLC 实时参数（已在 `_doFetch` 第 6 项获取）

---

### REQ-FUNC-010：移除对全局 PLC 在线率 API 的依赖（能耗模块）

**描述**：能耗模块状态判定应当移除对 `api.getDashboardPlcOnlineRate()` 的依赖，改用座舱能耗设备的 PLC 实时参数。

**来源引用**："能耗模块更奇怪：走的是全局 PLC 在线率" + "应当读取当前座舱（specific_part）的 PLC 实时参数"

**优先级**：Must Have

**变更范围**：
- 移除 `deriveEnergyStatus()` 中对 `plcRate` 参数的依赖
- 移除 `aggregateSubsystemStatus()` 中对 `plcRate` 参数的依赖
- `_doFetch()` 中可移除 `api.getDashboardPlcOnlineRate()` 调用（第 2 项），若无其他模块仍需此数据
  - 注：当前仅有能耗模块使用此数据；`state.plcOnline`/`state.plcTotal` 仅用于 admin/operator 路径
  - admin/operator 路径独立获取自己的数据，不依赖此调用
  - [INFERRED — requires PM confirmation] 若确认 admin/operator 路径不依赖 `_doFetch` 中的 PLC 在线率，可完全移除该调用

---

### REQ-FUNC-011：子系统状态聚合逻辑重构

**描述**：`aggregateSubsystemStatus()` 函数应当整体重构，从接收 `faultSummary` + `plcRate` + `faultEvents` 参数改为接收 `realtimeParams` + `structure` 参数，基于 PLC 实时参数执行 per-座舱状态判定。

**来源引用**：综合 REQ-FUNC-001 至 REQ-FUNC-005 的目标

**优先级**：Must Have

**新聚合逻辑**：
1. 从 `structure.system_devices` 中提取该座舱实际拥有的设备子类型
2. 对所有属于系统设备子类型白名单（fresh_air / energy_meter / hydraulic_module / air_quality）的设备
3. 从 `realtimeParams` 中获取该设备的所有 PLC 参数
4. 对每个设备，遍历其参数，调用故障判定逻辑（等价于 `fault_utils.is_fault_param()` + `count_faults_for_row()` 的前端等效实现）
5. 汇总各子系统的故障数，确定状态（有故障 → fault，无故障 → normal）
6. 仅输出该座舱实际拥有的子系统（无设备的子系统不出现在列表中）

---

### REQ-FUNC-012：故障参数判定规则保持与后端一致

**描述**：前端子系统状态判定所使用的故障字段集合和判定逻辑，应当与后端 `fault_utils.py` 的 `FAULT_PARAM_NAMES` + `count_faults_for_row()` 保持一致。

**来源引用**："状态判定逻辑和 Web 一致"

**优先级**：Must Have

**判定规则**（前端等效实现）：
- `FAULT_PARAM_NAMES`：25 个 FAULT_PARAMS 字段 + `comm_fault_timeout`
- `error_\d+` 正则匹配的字段也视为故障字段
- `fresh_air_fault_status`：按 popcount 计故障数
- 其他故障字段：value != 0 计 1 个故障
- value 为 null / undefined / 0 → 非故障

---

### REQ-FUNC-013：抽屉设备参数构建使用结构 + 实时数据

**描述**：`_buildCompartmentParams()` 函数应当基于 `getOwnerStructure(sp)` 的设备和 `getOwnerRealtimeParams(sp)` 的实时参数构建抽屉展示数据，确保与 Web 设备面板内容一致。

**来源引用**："抽屉内容对齐……小程序抽屉打开后应该展示和 Web 设备面板的子系统面板一致的内容"

**优先级**：Must Have

**判定规则**：
- 子系统隔舱打开：展示该子系统对应的所有设备（通过 product_code 匹配 structure.system_devices）
- 房间隔舱打开：展示该房间内的所有设备（通过 room_name 匹配 structure.rooms[].devices）
- 每个设备的参数列与 Web 一致（display_name + 格式化值）
- 新风机设备的 `fresh_air_fault_status` 展开为具名 bit 故障项
- 故障参数值红色/橙红色高亮（保持赛博朋克故障色系）

---

## 4. 非功能需求

---

### REQ-NFUNC-001：向后兼容 — admin/operator 路径不变

**描述**：admin/operator 角色的舰桥页面 Material Design 仪表盘应当保持完全不受影响，包括但不限于系统概览指标卡、快捷入口、故障计数、PLC 在线率等。

**来源引用**："需向后兼容，不破坏现有 admin/operator 的 Material Design 布局"

**优先级**：Must Have

**验收依据**：
- `index.vue` 中 `v-if="!isOwner"` 分支（admin-page）的模板和逻辑代码不得修改
- admin/operator 路径使用的 API 调用（`api.getDashboard*` 系列）保持原有行为

---

### REQ-NFUNC-002：赛博朋克视觉风格保持

**描述**：舰桥页面的所有视觉元素（色板、字体、动画、装饰、HUD 效果）应当保持不变，仅修改数据读取路径和状态判定逻辑。

**来源引用**："保持现有 cyberpunk 视觉风格不变，只改数据读取和状态判定逻辑"

**优先级**：Must Have

**验收依据**：
- CSS、模板结构、动画 composable 代码不变
- `SubsystemCompartment`、`RoomCompartment`、`FaultDrawer` 组件的样式和视觉不变
- 颜色映射规则不变（normal → 青蓝 `#2ff4e0`，fault → 红 `#ff315d`）

---

### REQ-NFUNC-003：数据刷新机制保持

**描述**：现有的 30 秒轮询间隔（`POLL_INTERVAL_MS = 30000`）、手动下拉刷新、座舱切换时全量重新获取的机制应当保持不变。

**来源引用**：现有 `useBridgeDashboard.js` 的 `PagePoller(30s)` 行为 + v1.11.0 舰桥需求规范

**优先级**：Must Have

---

### REQ-NFUNC-004：容错降级

**描述**：当 `getOwnerRealtimeParams(sp)` 或 `getOwnerStructure(sp)` 返回失败时，系统应当优雅降级，不白屏。

**来源引用**：现有 `useBridgeDashboard.js` 的 `Promise.allSettled` + `subsystemErrors` 容错模式

**优先级**：Should Have

**降级规则**：
- `getOwnerRealtimeParams(sp)` 失败 → 子系统状态显示为"同步中"（idle），不显示故障计数
- `getOwnerStructure(sp)` 失败 → 显示全部 4 个子系统（回退到白名单全量），不按设备过滤
- 两者均失败 → 保持现有错误横幅"数据加载失败，请下拉刷新重试"

---

## 5. 超出范围（Out of Scope）

| 编号 | 排除项 | 依据 |
|------|--------|------|
| OS-01 | 修改赛博朋克视觉风格（颜色、动画、字体、布局） | PM 约束"只改数据读取和状态判定逻辑" |
| OS-02 | 修改 admin/operator 的 Material Design 仪表盘 | PM 约束"不破坏现有 admin/operator 的 Material Design 布局" |
| OS-03 | 后端新增或修改 API | PM 约束"复用现有接口" |
| OS-04 | 修改 ArkTabBar 或其他 tab 页面 | PM 约束范围 |
| OS-05 | 修改故障的创建/编辑/恢复操作 | 现有范围仅覆盖展示 |
| OS-06 | 修改 Web 端 `DeviceCardsView.vue` | 本需求仅对齐小程序至 Web 现有行为 |
| OS-07 | 修改 `SubsystemCompartment.vue`、`RoomCompartment.vue`、`FaultDrawer.vue` 组件的视觉样式 | 数据驱动，组件内部样式不动 |

---

## 6. 待确认推断项

> 本版本无 [INFERRED] 标注的需求条目。所有需求均可追溯至 PM 原始业务需求或现有代码核查事实。

---

## 7. 开放问题

| 编号 | 问题 | 优先级 |
|------|------|--------|
| OQ-01 | 是否完全移除 `_doFetch()` 中 `api.getDashboardPlcOnlineRate()` 的调用？当前仅能耗模块使用，若 admin/operator 路径独立获取 PLC 数据则可安全移除。（见 REQ-FUNC-010 备注） | LOW |
| OQ-02 | `aggregateSubsystemStatus()` 中的 `device-fault-summary` 移除后，`subsystemErrors['device-summary']` 错误处理是否保留？当前仅 owner 路径使用该错误 key。 | LOW |

---

## 附录 A：子系统与 PLC 故障字段映射

| 子系统 | 子系统 ID | product_code（Web） | 相关 FAULT_PARAMS 字段 |
|--------|----------|---------------------|----------------------|
| 新风模块 | fresh-air | 130004 | `fresh_air_unit_stop_error`、`fresh_air_unit_communication_error`、`fresh_air_fault_status`（位域） |
| 水力模块 | hydraulic | 270001 | `hydraulic_module_low_temp_error` |
| 空气品质 | air-quality | 100007 | `air_quality_sensor_communication_error` |
| 能耗中枢 | energy | — | `energy_meter_status_communication_error`、匹配 `error_\d+` 的能耗设备字段 |

_注：Web 端 product_code 和 sub_type 的对应关系由后端 `/api/devices/realtime-params/` 的 group→sub_type 嵌套结构自动维护。小程序通过 structure.system_devices 的 sub_type 字段匹配。_
