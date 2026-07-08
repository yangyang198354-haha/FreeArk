<file_header>
  <project_name>v1.12.0_bridge_per_cockpit_refactor</project_name>
  <file_name>implementation_plan.md</file_name>
  <file_type>implementation</file_type>
  <author>sub_agent_software_developer</author>
  <created_at>2026-07-08T12:00:00+08:00</created_at>
  <version>1.0.0</version>
  <status>WRITTEN</status>
  <upstream_inputs>
    <input path="docs/requirements/v1.12.0_bridge_per_cockpit_refactor/requirements_spec.md" status="APPROVED"/>
    <input path="docs/requirements/v1.12.0_bridge_per_cockpit_refactor/user_stories.md" status="APPROVED"/>
    <input path="docs/architecture/v1.12.0_bridge_per_cockpit_refactor/architecture_design.md" status="APPROVED"/>
    <input path="docs/architecture/v1.12.0_bridge_per_cockpit_refactor/module_design.md" status="APPROVED"/>
    <input path="docs/architecture/v1.12.0_bridge_per_cockpit_refactor/tech_stack.md" status="APPROVED"/>
  </upstream_inputs>
</file_header>

# 实现计划 — 小程序舰桥 per-座舱重构

**文档编号**: IMPL-PLAN-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 1.0.0
**创建日期**: 2026-07-08
**作者**: sub_agent_software_developer

---

## 实现概览

- **总模块数**: 3（1 新增 + 2 修改）
- **总文件数**: 3（1 新建 + 2 修改覆盖）
- **实现顺序**: 拓扑排序（零依赖模块优先）
- **架构偏差**: 无（严格遵循所有 ADR 决策）

---

## 模块依赖图（有向图）

```
MOD-FAULT-UTILS (faultUtils.js)  ← 零依赖，纯函数
         │
         ▼
MOD-BD-002 (useBridgeDashboard.js)  ← 依赖 MOD-FAULT-UTILS + MOD-API + MOD-OWNER-STORE
         │
         ▼
MOD-PAGE-HOME (index.vue)  ← 依赖 MOD-BD-002，本版本无需修改模板/CSS
```

## 拓扑排序结果

| 顺序 | MOD-ID | 模块名 | 文件路径 | 变更类型 | 前置依赖 | 复杂度 |
|------|--------|--------|---------|---------|---------|--------|
| 1 | MOD-FAULT-UTILS | faultUtils | `miniprogram/utils/faultUtils.js` | **新增** | 无 | L |
| 2 | MOD-BD-002 | useBridgeDashboard | `miniprogram/composables/useBridgeDashboard.js` | **修改** | MOD-FAULT-UTILS, MOD-API, MOD-OWNER-STORE | H |
| 3 | MOD-PAGE-HOME | index.vue | `miniprogram/pages/home/index.vue` | **不修改** | MOD-BD-002 | N/A |

**循环依赖检查**: 无循环依赖。MOD-FAULT-UTILS 位于最底层，MOD-BD-002 单向依赖 MOD-FAULT-UTILS，MOD-PAGE-HOME 单向依赖 MOD-BD-002。

---

## 模块实现计划

### 顺序 1: MOD-FAULT-UTILS — faultUtils.js（新增）

**文件**: `miniprogram/utils/faultUtils.js`

**职责**: 与后端 `fault_utils.py` 等效的故障字段判定、故障计数、新风机 bit 展开等纯函数集合。零外部依赖，所有函数输入输出确定。

**实现的接口**:

| IFC-ID | 函数 | 说明 |
|--------|------|------|
| IFC-FU-001 | `isFaultParam(paramName)` | 判断参数名是否属于故障字段集合 |
| IFC-FU-002 | `countFaultsForRow(paramName, value)` | 计算单行参数的故障贡献值 |
| IFC-FU-003 | `computeFaultCount(params)` | 批量计算一组参数的故障总数 |
| IFC-FU-004 | `expandFreshAirFaultBits(value)` | 将 fresh_air_fault_status 位域展开为 9 具名 bit 项 |
| IFC-FU-005 | `isFaultValueForDisplay(paramName, value)` | 判断参数值是否应以故障样式展示 |

**导出的常量**:

| 常量 | 类型 | 同步来源 |
|------|------|---------|
| `FAULT_PARAM_NAMES` | `Set<String>` (26 个) | `fault_utils.py` frozenset 逐字复制 |
| `ERROR_N_PATTERN` | `RegExp` | `fault_utils.py` `_ERROR_N_PATTERN` |
| `FRESH_AIR_FAULT_BITS` | `String[]` (9 个) | `DeviceCardsView.vue` 逐字复制 |
| `SYSTEM_SUB_KEYS` | `String[]` (4 个) | `DeviceCardsView.vue` 逐字复制 |

**实现要点**:
- 使用 `new Set()` 实现 O(1) 故障字段成员判断
- `countFaultsForRow` 对 `fresh_air_fault_status` 使用 popcount：`value.toString(2).split('1').length - 1`
- `ERROR_N_PATTERN` 使用 `/^error_\d+$/`（无 `u` flag，兼容华为安卓）
- `expandFreshAirFaultBits` 返回 9 元素数组，每元素 `{bitIndex, name, active}`
- 所有函数对 null/undefined 输入安全

---

### 顺序 2: MOD-BD-002 — useBridgeDashboard.js（修改）

**文件**: `miniprogram/composables/useBridgeDashboard.js`

**职责**: 舰桥仪表盘组合式 API。本版本核心变更模块，修改 7 个函数/区域。

**变更详情表**:

| # | 区域 | 变更类型 | 行号范围（旧） | 说明 |
|---|------|---------|-------------|------|
| 1 | `ENERGY_KEYWORDS` 常量 | **删除** | L26-29 | 能耗模块不再使用关键词匹配全局 FaultEvent |
| 2 | `PRODUCT_MAP` 常量 | **删除** | L32-36 | 子系统匹配改用 sub_type 白名单 |
| 3 | `isEnergyRelated()` | **删除** | L63-67 | 能耗状态不再依赖 FaultEvent 关键词匹配 |
| 4 | `deriveEnergyStatus()` | **删除** | L88-145 | 能耗模块回归统一判定管道（ADR-005） |
| 5 | `aggregateSubsystemStatus()` | **重写** | L154-199 | 新签名 `(structure, realtimeParams)`；per-座舱 PLC 参数判定；动态子系统列表 |
| 6 | `aggregateRoomStatus()` | **微调** | L208-262 | 移除 L238-259 孤儿房间追加逻辑（ADR-004） |
| 7 | `_doFetch()` | **修改** | L404-517 | 移除 Promise.allSettled 第 1、2 项；重新编号结果索引；新增错误追踪键 |
| 8 | `_buildCompartmentParams()` | **加强** | L606-673 | sub_type 匹配替代 product_code；移除 energy 补偿逻辑；集成 expandFreshAirFaultBits |
| 9 | `filterFaultEventsByCompartment()` | **修改** | L294-320 | 子系统匹配从 product_code → 基于 structure 的 device_sn 集合匹配 |
| 10 | 新增 import | **新增** | L15 | `import { ...faultUtils } from '@/utils/faultUtils'` |

**_doFetch 索引重新编号**:

| 旧索引 | API 调用 | 新索引 | 备注 |
|--------|---------|--------|------|
| 0 | `getOwnerStructure(sp)` | 0 | 不变 |
| 1 | `getDashboardDeviceFaultSummary()` | — | **删除**（ADR-008） |
| 2 | `getDashboardPlcOnlineRate()` | — | **删除**（ADR-008） |
| 3 | `getFaultEvents(sp)` | 1 | 重新编号 |
| 4 | `getCondensationWarningCount()` | 2 | 重新编号 |
| 5 | `getBindStatus()` | 3 | 重新编号 |
| 6 | `getOwnerRealtimeParams(sp)` | 4 | 重新编号 |
| 7 | `getOwnerConnectivity(sp)` | 5 | 重新编号 |

**subsystemErrors 键变更**:

| 键名 | 状态 | 说明 |
|------|------|------|
| `structure` | 保留 | 不变 |
| `device-summary` | **删除** | 对应已删除的 API 调用 |
| `plc` | **删除** | 对应已删除的 API 调用 |
| `fault-events` | 保留 | 不变 |
| `realtime-params` | **新增** | getOwnerRealtimeParams 失败时设置 |
| `connectivity` | **新增** | getOwnerConnectivity 失败时设置 |

**全局错误检查条件变更**:

旧: `['structure', 'device-summary', 'fault-events'].every(k => state.subsystemErrors[k])`
新: `['structure', 'realtime-params', 'fault-events'].some(k => state.subsystemErrors[k])`

**聚合调用变更**:

旧: `aggregateSubsystemStatus(faultSummary || {}, plcRate, faultEvents, state.plcCockpitStatus)`
新: `aggregateSubsystemStatus(structure || {}, _realtimeParamsCache)`

---

### 顺序 3: MOD-PAGE-HOME — index.vue（不修改）

**文件**: `miniprogram/pages/home/index.vue`

**分析结论**: 经过模板和脚本审查，`index.vue` 中 owner 分支的 `<template>` 和 `<script setup>` 均通过 `useBridgeDashboard()` 的公开接口消费数据，不直接操作内部逻辑。由于 `useBridgeDashboard` 的回返接口（`state.subsystems`、`state.rooms`、`state.loading` 等字段签名）保持不变，模板无需任何修改。admin/operator 分支完全独立，不依赖 `useBridgeDashboard`。

**变更**: 无。

---

## 架构偏差记录

**无架构偏差。** 所有实现严格遵循以下 ADR 决策：

| ADR | 决策 | 遵循情况 |
|-----|------|---------|
| ADR-001 | 子系统状态从 per-座舱 PLC 参数读取 | aggregateSubsystemStatus 重写为接收 structure + realtimeParams |
| ADR-002 | 前端等效实现 fault_utils.py | faultUtils.js 纯函数，常量逐字复制 |
| ADR-003 | subsystems 数组仅含实际拥有的子系统 | SYSTEM_SUB_KEYS 交集过滤 |
| ADR-004 | 房间列表以结构为准 | 移除孤儿房间追加逻辑 |
| ADR-005 | 能耗模块纯 PLC 参数判定 | 删除 deriveEnergyStatus、ENERGY_KEYWORDS |
| ADR-006 | 抽屉数据基于缓存复用 | _buildCompartmentParams 使用 _structureCache + _realtimeParamsCache |
| ADR-007 | 前端位域展开 | expandFreshAirFaultBits 纯函数 |
| ADR-008 | 完全移除全局 API 调用 | 删除 _doFetch 中第 1、2 项；OQ-01/OQ-02 已裁决 |

---

## 技术栈合规

| 约束 | 遵循情况 |
|------|---------|
| 纯 JS (ES6+), 零新增依赖 | 仅用 Set、RegExp、箭头函数、模板字符串 |
| 禁止 `\p{}` Unicode 正则 | 所有正则使用标准 `/^error_\d+$/`（无 `u` flag） |
| 零后端改动 | 复用现有 `/api/miniapp/owner/` 端点 |
| admin/operator 路径零修改 | index.vue 的 admin/operator 分支代码不变 |
| 视觉风格/模板/CSS 零修改 | 仅修改 useBridgeDashboard.js 数据逻辑 |
| 代码直接提交 main | 单 commit，不新建分支 |

---

## 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| R-04: `_doFetch` 索引重新编号导致类型错位 | Low | 逐行核对所有 `results[N]` 引用；（本计划已明确列出所有索引映射） |
| R-01: 前后端故障判定规则漂移 | Medium | faultUtils.js 常量处标注同步来源注释 |
| R-02: structure 同步延迟 | Medium | REQ-NFUNC-004 降级：structure 为空时回退到 SYSTEM_SUB_KEYS 全量显示 |
