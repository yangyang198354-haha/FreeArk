<file_header>
  <project_name>v1.12.0_bridge_per_cockpit_refactor</project_name>
  <file_name>module_design.md</file_name>
  <file_type>architecture</file_type>
  <author>sub_agent_system_architect</author>
  <created_at>2026-07-08T12:00:00+08:00</created_at>
  <version>1.0.0</version>
  <status>DRAFT</status>
  <upstream_inputs>
    <input path="docs/requirements/v1.12.0_bridge_per_cockpit_refactor/requirements_spec.md" status="APPROVED"/>
    <input path="docs/requirements/v1.12.0_bridge_per_cockpit_refactor/user_stories.md" status="APPROVED"/>
  </upstream_inputs>
</file_header>

# 模块设计文档 — 小程序舰桥 per-座舱重构

**文档编号**: MOD-DESIGN-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 1.0.0
**状态**: APPROVED
**创建日期**: 2026-07-08
**作者**: sub_agent_system_architect

---

## 模块总览

| MOD-ID | 模块名 | 层级 | 职责 | 变更类型 | 依赖于 |
|--------|--------|------|------|---------|--------|
| MOD-BD-002 | useBridgeDashboard | Composables | 舰桥仪表盘数据获取、状态聚合、轮询、座舱切换 | **修改** | MOD-API, MOD-OWNER-STORE, MOD-FAULT-UTILS, PagePoller |
| MOD-FAULT-UTILS | faultUtils | Utils | 故障字段判定、故障计数、新风机 bit 展开（纯函数） | **新增** | 无 |
| MOD-PAGE-HOME | index.vue (owner 分支) | Pages | 舰桥页面模板与组合式 API 入口 | **微改** | MOD-BD-002, MOD-BD-003, MOD-BD-005~007 |
| MOD-API | api.js | Utils | API 调用封装 | **不修改** | http.js |
| MOD-OWNER-STORE | owner.js (useOwnerStore) | Store | 业主数据缓存与去重 | **不修改** | MOD-API |
| MOD-BD-003 | useAnimationControl | Composables | 动画生命周期控制 | **不修改** | — |
| MOD-BD-005 | SubsystemCompartment | Components | 子系统隔舱渲染 | **不修改** | — |
| MOD-BD-006 | RoomCompartment | Components | 房间隔舱渲染 | **不修改** | — |
| MOD-BD-007 | FaultDrawer | Components | 故障详情抽屉 | **不修改** | — |

---

## 模块详情

---

### MOD-FAULT-UTILS: 故障判定纯函数模块（新增）

- **文件路径**: `miniprogram/utils/faultUtils.js`
- **职责**: 提供与后端 `fault_utils.py` 等效的故障字段判定、故障计数、新风机 bit 展开等纯函数。所有函数无副作用、无外部依赖、输入输出确定。
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-008, REQ-FUNC-012
- **覆盖用户故事**: US-01, US-02, US-03, US-04, US-08

**公开接口契约:**

```
IFC-FU-001: isFaultParam(paramName: String) → Boolean
  判断参数名是否属于故障字段集合。
  规则: paramName in FAULT_PARAM_NAMES 或 匹配正则 /^error_\d+$/
  注意: fresh_air_fault_status 不属于此函数覆盖范围（由 countFaultsForRow 单独处理）

IFC-FU-002: countFaultsForRow(paramName: String, value: Number|null|undefined) → Number
  计算单行参数的故障贡献值。
  规则:
    - value 为 null/undefined/0 → 返回 0
    - paramName === 'fresh_air_fault_status' → popcount (每个置 1 的 bit 计 1)
    - isFaultParam(paramName) && value !== 0 → 返回 1
    - 其他 → 返回 0

IFC-FU-003: computeFaultCount(params: Array<{paramName: String, value: Number}>) → Number
  批量计算一组参数的故障总数。
  规则: 对每个参数调用 countFaultsForRow，累加结果。
  返回: 非负整数

IFC-FU-004: expandFreshAirFaultBits(value: Number) → Array<{bitIndex: Number, name: String, active: Boolean}>
  将 fresh_air_fault_status 位域值展开为 9 个具名故障 bit 项。
  规则: ((value >> bitIndex) & 1) === 1 → active=true
  返回: 9 个元素的数组，顺序与 FRESH_AIR_FAULT_BITS 一致

IFC-FU-005: isFaultValueForDisplay(paramName: String, value: Number) → Boolean
  判断参数值是否应在 UI 中以故障样式（红/橙）展示。
  规则: isFaultParam(paramName) && value !== 0 && value != null
        或 paramName === 'fresh_air_fault_status' && value !== 0
        或 匹配 /^error_\d+$/ && value !== 0
```

**内部常量（与后端对齐）:**

| 常量 | 类型 | 值 | 对齐来源 |
|------|------|-----|---------|
| `FAULT_PARAM_NAMES` | `Set<String>` | 26 个具名故障字段 | `fault_utils.py` frozenset 逐字复制 |
| `ERROR_N_PATTERN` | `RegExp` | `/^error_\d+$/` | `fault_utils.py` `_ERROR_N_PATTERN` |
| `FRESH_AIR_FAULT_BITS` | `String[]` | 9 个中文故障名称 | `DeviceCardsView.vue` `FRESH_AIR_FAULT_BITS` 逐字复制 |
| `SYSTEM_SUB_KEYS` | `String[]` | `['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']` | `DeviceCardsView.vue` `SYSTEM_SUB_KEYS` |

**依赖模块**: 无（纯函数，零依赖）

**外部依赖**: 无

---

### MOD-BD-002: useBridgeDashboard（修改）

- **文件路径**: `miniprogram/composables/useBridgeDashboard.js`
- **职责**: 舰桥仪表盘组合式 API —— 数据获取（`_doFetch`）、状态聚合（`aggregateSubsystemStatus` 重写）、房间聚合（`aggregateRoomStatus` 微调）、轮询生命周期、座舱切换、抽屉开闭。本版本核心变更模块。
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-010, REQ-FUNC-011, REQ-FUNC-012, REQ-FUNC-013, REQ-NFUNC-003, REQ-NFUNC-004
- **覆盖用户故事**: US-01, US-02, US-03, US-04, US-05, US-06, US-07, US-08

**变更摘要（与当前代码比较）:**

| 函数/区域 | 变更类型 | 说明 |
|----------|---------|------|
| `ENERGY_KEYWORDS` 常量 | 删除 | 不再使用关键词匹配全局 FaultEvent |
| `PRODUCT_MAP` 常量 | 删除 | 子系统匹配改为 sub_type 白名单，不再使用 product_code |
| `severityToStatus()` | 保留 | 仍用于房间隔舱的 FaultEvent 严重度转换 |
| `isEnergyRelated()` | 删除 | 能耗状态不再依赖 FaultEvent 关键词匹配 |
| `deriveEnergyStatus()` | 删除 | 能耗模块回归统一判定管道（ADR-005） |
| `aggregateSubsystemStatus()` | **重写** | 接收 `(structure, realtimeParams)` 替代 `(faultSummary, plcRate, faultEvents, cockpitPlcStatus)` |
| `aggregateRoomStatus()` | 微调 | 移除 FaultEvent 孤儿房间追加逻辑（ADR-004 第 238-259 行） |
| `_doFetch()` | 修改 | 移除 `Promise.allSettled` 第 1、2 项（ADR-008）；重新编号；新增错误追踪 |
| `_buildCompartmentParams()` | 加强 | 使用 `sub_type` 匹配替代 `product_code`；移除 energy 补偿逻辑；集成 `expandFreshAirFaultBits` |
| `filterFaultEventsByCompartment()` | 修改 | 子系统匹配从 product_code → sub_type |
| `state.plcOnline` / `state.plcTotal` | 保留字段 | 不再更新值（保持接口兼容） |
| `state.subsystemErrors` | 修改 | 新增 `realtime-params`、`connectivity` 键；移除 `device-summary`、`plc` 键 |

**新增内部函数:**

```
IFC-BD-002-23: aggregateSubsystemStatus(structure: Object, realtimeParams: Object) → Array<SubsystemState>
  新聚合逻辑:
  1. 从 structure.system_devices 中提取所有设备的 sub_type
  2. 与 SYSTEM_SUB_KEYS 取交集 → 确定该座舱实际拥有的子系统类型
  3. 对每个子系统类型:
     a. 找出该类型的所有设备（structure.system_devices.filter(d => d.sub_type === subType)）
     b. 收集这些设备在 realtimeParams 中的所有参数
     c. 调用 computeFaultCount(params) 得故障数
     d. 故障数 > 0 → 状态 'fault'；故障数 === 0 → 状态 'normal'
     e. 构建 SubsystemState 对象
  4. 返回仅包含该座舱实际拥有的子系统的数组

IFC-BD-002-24: getDeviceFaultFields(deviceParams: Object) → Array<{paramName: String, value: Number}>
  从设备实时参数对象中提取所有故障相关字段（用于状态计数和抽屉展示）

IFC-BD-002-25: buildDrawerParamsForSubsystem(subType: String) → Array<DeviceParamBlock>
  为指定子系统构建抽屉参数展示数据（ADR-006），按设备分组

IFC-BD-002-26: buildDrawerParamsForRoom(roomName: String) → Array<DeviceParamBlock>
  为指定房间构建抽屉参数展示数据
```

**公开接口契约（保持不变，向后兼容）:**

```
IFC-BD-002-15: start() → void
IFC-BD-002-16: stop() → void
IFC-BD-002-17: refresh(force: Boolean) → Promise<void>
IFC-BD-002-18: switchCockpit(sp: String) → Promise<void>
IFC-BD-002-19: openCompartment(compartment: Object) → void
IFC-BD-002-20: closeCompartment() → void
```

**Reactive State（保持不变，向后兼容）:**

```
IFC-BD-002-01: state.loading: Boolean
IFC-BD-002-02: state.refreshing: Boolean
IFC-BD-002-03: state.error: String|null
IFC-BD-002-04: state.bindings: Array
IFC-BD-002-05: state.selectedSp: String
IFC-BD-002-06: state.selectedLabel: String
IFC-BD-002-07: state.overallStatus: {level: String, text: String}
IFC-BD-002-08: state.subsystems: Array<SubsystemState>
IFC-BD-002-09: state.rooms: Array<RoomState>
IFC-BD-002-10: state.plcOnline: Number        // 不再更新，保留字段
IFC-BD-002-11: state.plcTotal: Number         // 不再更新，保留字段
IFC-BD-002-11a: state.plcCockpitStatus: String
IFC-BD-002-11b: state.screenCockpitStatus: String
IFC-BD-002-12: state.condensationCount: Number
IFC-BD-002-13: state.activeCompartment: Object|null
IFC-BD-002-14: state.subsystemErrors: Object  // 键集合变更
```

**依赖模块**:
- MOD-API（api.js）— 调用 `getOwnerStructure`, `getOwnerRealtimeParams`, `getFaultEvents`, `getCondensationWarningCount`, `getBindStatus`, `getOwnerConnectivity`
- MOD-OWNER-STORE（ownerStore）— 调用 `ensureBindings`, `setActiveSpecificPart`
- MOD-FAULT-UTILS（faultUtils.js）— 调用 `isFaultParam`, `countFaultsForRow`, `computeFaultCount`, `expandFreshAirFaultBits`
- PagePoller — 轮询实例化

**外部依赖**: `vue`（reactive, computed）, `@/utils/api`, `@/store/owner`, `@/utils/poller`, `@/subpackages/game/arkZoneMap`（worseStatus, STATUS_RANK）, `@/utils/faultUtils`

---

### MOD-PAGE-HOME: index.vue owner 分支（微改）

- **文件路径**: `miniprogram/pages/home/index.vue`
- **职责**: 舰桥页面模板。本版本对 owner 分支仅做极小调整（如有），保持视觉样式不变。
- **覆盖需求**: REQ-NFUNC-001（向后兼容）, REQ-NFUNC-002（视觉风格保持）

**变更范围（限定）:**

| 区域 | 变更类型 | 说明 |
|------|---------|------|
| `<template>` owner 分支 | **不修改** | `SubsystemCompartment`、`RoomCompartment`、`FaultDrawer` 组件均为数据驱动，模板不变 |
| `<script setup>` | **不修改** | `useBridgeDashboard()` 的公开接口保持不变 |
| `<style scoped>` owner 分支 | **不修改** | 赛博朋克色板、动画、布局不变（REQ-NFUNC-002） |
| `<template>` admin/operator 分支 | **不修改** | Material Design 仪表盘零改动（REQ-NFUNC-001） |
| `<script>` admin/operator `fetchDashboard()` | **不修改** | 独立获取全局 API，不受 `useBridgeDashboard` 变更影响 |

**公开接口契约**: 无（页面组件，无对外暴露的接口）

**依赖模块**:
- MOD-BD-002（useBridgeDashboard）— `state`, `start`, `stop`, `refresh`, `switchCockpit`, `openCompartment`, `closeCompartment`, `hasNoBindings`, `selectedBindingIndex`, `showCabinSwitcher`
- MOD-BD-003（useAnimationControl）— `animationsPaused`, `onShow`, `onHide`
- MOD-BD-005（SubsystemCompartment）
- MOD-BD-006（RoomCompartment）
- MOD-BD-007（FaultDrawer）
- ArkTabBar, authStore, PagePoller, api

---

## 需求覆盖率矩阵

| 需求 ID | 覆盖模块 | 覆盖接口 | 覆盖用户故事 |
|---------|---------|---------|------------|
| REQ-FUNC-001 | MOD-BD-002, MOD-FAULT-UTILS | IFC-FU-001~004, IFC-BD-002-23 | US-01 |
| REQ-FUNC-002 | MOD-BD-002, MOD-FAULT-UTILS | IFC-FU-001~003, IFC-BD-002-23 | US-02 |
| REQ-FUNC-003 | MOD-BD-002, MOD-FAULT-UTILS | IFC-FU-001~003, IFC-BD-002-23 | US-03 |
| REQ-FUNC-004 | MOD-BD-002, MOD-FAULT-UTILS | IFC-FU-001~003, IFC-BD-002-23 | US-04 |
| REQ-FUNC-005 | MOD-BD-002 | IFC-BD-002-23（SYSTEM_SUB_KEYS 交集过滤） | US-05 |
| REQ-FUNC-006 | MOD-BD-002 | aggregateRoomStatus（移除孤儿房间逻辑） | US-06 |
| REQ-FUNC-007 | MOD-BD-002 | IFC-BD-002-25, IFC-BD-002-26 | US-07 |
| REQ-FUNC-008 | MOD-FAULT-UTILS | IFC-FU-004, FRESH_AIR_FAULT_BITS | US-08 |
| REQ-FUNC-009 | MOD-BD-002 | _doFetch（移除第 1 项） | — |
| REQ-FUNC-010 | MOD-BD-002 | _doFetch（移除第 2 项），删除 deriveEnergyStatus | US-04 |
| REQ-FUNC-011 | MOD-BD-002 | IFC-BD-002-23（整体重写） | US-05 |
| REQ-FUNC-012 | MOD-FAULT-UTILS | IFC-FU-001~003, FAULT_PARAM_NAMES | US-01~04 |
| REQ-FUNC-013 | MOD-BD-002 | IFC-BD-002-25, IFC-BD-002-26 | US-07 |
| REQ-NFUNC-001 | MOD-PAGE-HOME | admin/operator 路径零修改 | — |
| REQ-NFUNC-002 | MOD-PAGE-HOME, MOD-BD-005~007 | 零 CSS/模板/动画修改 | — |
| REQ-NFUNC-003 | MOD-BD-002 | PagePoller(30s) 不变 | — |
| REQ-NFUNC-004 | MOD-BD-002 | _doFetch 降级处理 + subsystemErrors | — |

**覆盖率验证**: 13/13 REQ-FUNC 覆盖，4/4 REQ-NFUNC 覆盖。无遗漏。

---

## 依赖关系图（文本格式）

```
MOD-FAULT-UTILS (faultUtils.js)
  └── (零依赖，纯函数模块)

MOD-BD-002 (useBridgeDashboard.js)
  ├── MOD-API (api.js)                     — 调用 6 个 API 方法
  ├── MOD-OWNER-STORE (ownerStore)         — ensureBindings, setActiveSpecificPart
  ├── MOD-FAULT-UTILS (faultUtils.js)      — isFaultParam, countFaultsForRow, computeFaultCount, expandFreshAirFaultBits
  └── PagePoller, arkZoneMap               — 轮询、状态比较工具

MOD-PAGE-HOME (index.vue owner 分支)
  ├── MOD-BD-002 (useBridgeDashboard)      — state, start, stop, refresh, switchCockpit, openCompartment, closeCompartment
  ├── MOD-BD-003 (useAnimationControl)     — animationsPaused, onShow, onHide
  ├── MOD-BD-005 (SubsystemCompartment)    — 子组件，数据通过 props 传递
  ├── MOD-BD-006 (RoomCompartment)         — 子组件，数据通过 props 传递
  ├── MOD-BD-007 (FaultDrawer)            — 子组件，数据通过 props 传递
  └── ArkTabBar, authStore                 — 共享依赖

MOD-PAGE-HOME (index.vue admin/operator 分支)
  ├── MOD-API (api.js)                     — 独立调用 getDashboardPlcOnlineRate 等
  └── PagePoller, MetricCard               — 轮询与 UI

未修改模块（无依赖变更）:
  MOD-API → http.js
  MOD-OWNER-STORE → MOD-API
  MOD-BD-003 → (独立)
  MOD-BD-005 → (纯展示组件，通过 props 驱动)
  MOD-BD-006 → (纯展示组件，通过 props 驱动)
  MOD-BD-007 → (纯展示组件，通过 props 驱动)
```

**循环依赖验证**: 已检查所有依赖边，无循环依赖。`MOD-FAULT-UTILS` 为零依赖纯函数模块，位于依赖图最底层。`MOD-BD-002` 单向依赖 `MOD-FAULT-UTILS`。`MOD-PAGE-HOME` 单向依赖 `MOD-BD-002`。

---

## 数据流图（详细）

```
                           ┌─────────────┐
                           │   start()   │
                           └──────┬──────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │      _doFetch(sp)        │
                    │                          │
                    │  Promise.allSettled([    │
                    │    [0] getOwnerStructure │──→ _structureCache
                    │    [1] getFaultEvents    │──→ _faultEventsCache
                    │    [2] getCondensation   │──→ state.condensationCount
                    │    [3] getBindStatus     │──→ state.bindings
                    │    [4] getOwnerRealtime  │──→ _realtimeParamsCache
                    │    [5] getOwnerConnect   │──→ state.plcCockpitStatus
                    │  ])                      │     state.screenCockpitStatus
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  aggregateSubsystemStatus│
                    │  (structure, realtime)   │
                    │                          │
                    │  1. 提取 system_devices  │
                    │  2. sub_type ∩ SUB_KEYS  │
                    │  3. 对每个子系统:         │
                    │     ┌──────────────────┐ │
                    │     │ getDeviceFaultFields│
                    │     │ computeFaultCount  │ │
                    │     │ → status, count   │ │
                    │     └──────────────────┘ │
                    │  4. → state.subsystems   │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  aggregateRoomStatus     │
                    │  (structure, faultEvents)│
                    │                          │
                    │  1. rooms = structure    │
                    │     .rooms only          │
                    │  2. 每个房间:             │
                    │     faultEvents.filter   │
                    │     → status, counts     │
                    │  3. → state.rooms        │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │  computeOverallStatus    │
                    │  → state.overallStatus   │
                    └──────────────────────────┘

                    ┌─────────────────────────┐
                    │   openCompartment(c)     │
                    │                          │
                    │  _buildCompartmentParams │
                    │  (structure + realtime)  │
                    │  按 sub_type 匹配设备    │
                    │  expandFreshAirFaultBits │
                    │  → compartmentParams     │
                    │                          │
                    │  filterFaultEvents       │
                    │  (按 sub_type/room)      │
                    │  → faultEvents           │
                    └──────────────────────────┘
```

---

## 接口类型定义

```typescript
// ── SubsystemState ──────────────────────────────
type SubsystemState = {
  id: string           // 'fresh-air' | 'hydraulic' | 'air-quality' | 'energy'
  name: string         // 中文显示名
  status: 'normal' | 'fault' | 'idle'
  faultCount: number   // 故障字段非零计数（含 popcount 贡献）
  warningCount: number // 本版本始终为 0（owner 路径无 warning 概念）
  dataSource: string   // 'plc-realtime-params'
}

// ── RoomState ───────────────────────────────────
type RoomState = {
  id: string
  name: string
  status: 'normal' | 'fault' | 'warning'
  faultCount: number
  warningCount: number
  hasCondensation: boolean
}

// ── DeviceParamBlock (抽屉展示用) ───────────────
type DeviceParamBlock = {
  deviceSn: string
  deviceName: string
  subType: string       // 新增，用于前端匹配
  attrs: ParamAttr[]
}

type ParamAttr = {
  tag: string           // PLC 参数名（如 fresh_air_fault_status）
  displayName: string   // 来自 structure 或 Web 对齐的显示名
  value: number | null
  isFault: boolean      // isFaultValueForDisplay(tag, value)
  // 仅 fresh_air_fault_status:
  expandedBits?: Array<{bitIndex: number, name: string, active: boolean}>
}
```
