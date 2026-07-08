<file_header>
  <project_name>v1.12.0_bridge_per_cockpit_refactor</project_name>
  <file_name>architecture_design.md</file_name>
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

# 架构设计文档 — 小程序舰桥 per-座舱重构

**文档编号**: ARCH-DESIGN-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 1.0.0
**状态**: APPROVED
**创建日期**: 2026-07-08
**作者**: sub_agent_system_architect

---

## 版本历史

| 版本  | 日期       | 变更摘要 |
|-------|------------|---------|
| 1.0.0 | 2026-07-08 | 初始架构设计，8 个 ADR，覆盖 13 REQ-FUNC + 4 REQ-NFUNC |

---

## 架构概览

### 架构风格

模块化单体前端（uni-app Vue 3 Composition API），复用现有后端 API，**零后端改动**。

### 核心变更摘要

当前舰桥页面的子系统状态（新风/水力/空气品质/能耗）来自两个全局 API：
1. `GET /api/dashboard/device-fault-summary/` — 全局 FaultEvent 聚合，不带 `specific_part` 过滤
2. `GET /api/dashboard/plc-online-rate/` — 全局 PLC 在线率

重构后，所有子系统状态判定改为基于 per-座舱（specific_part）的 PLC 实时参数，数据来源于：
1. `GET /api/miniapp/owner/realtime-params/?specific_part={sp}` — 已在 `_doFetch()` 中调用（索引 6）
2. `GET /api/miniapp/owner/structure/?specific_part={sp}` — 已在 `_doFetch()` 中调用（索引 0）

**关键依据**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-009, REQ-FUNC-010

### 数据流转变图

```
BEFORE (v1.11.3 — 全局聚合):
┌──────────────────────────────────────────────────────────┐
│  useBridgeDashboard._doFetch()                            │
│                                                            │
│  [0] getOwnerStructure(sp)          → _structureCache     │
│  [1] getDashboardDeviceFaultSummary → faultSummary ──┐    │
│  [2] getDashboardPlcOnlineRate      → plcRate ───────┤    │
│  [3] getFaultEvents(&sp)            → faultEvents ───┤    │
│  [6] getOwnerRealtimeParams(sp)     → _realtimeCache  │    │
│  [7] getOwnerConnectivity(sp)       → conn indicators │    │
│                                            │           │    │
│         aggregateSubsystemStatus(faultSummary, plcRate,   │
│                                  faultEvents, cockpitPlc) │
│              │                     │           │          │
│              ▼                     ▼           ▼          │
│    freshAir ← faultSummary   energy ← plcRate+faultEvents │
│    hydraulic ← faultSummary                               │
│    airQuality ← faultSummary                              │
│                                                            │
│  PROBLEM: All cockpits see identical subsystem status!     │
└──────────────────────────────────────────────────────────┘

AFTER (v1.12.0 — per-座舱 PLC 参数):
┌──────────────────────────────────────────────────────────┐
│  useBridgeDashboard._doFetch()                            │
│                                                            │
│  [0] getOwnerStructure(sp)       → structure ───────┐     │
│  [1] REMOVED (device-fault-summary)                 │     │
│  [2] REMOVED (plc-online-rate)                      │     │
│  [3] getFaultEvents(&sp)         → faultEvents ────┤     │
│  [6] getOwnerRealtimeParams(sp)  → realtimeParams ─┤     │
│  [7] getOwnerConnectivity(sp)    → conn indicators  │     │
│                                          │           │     │
│     aggregateSubsystemStatus(structure, realtimeParams)   │
│              │              │                              │
│              ▼              ▼                              │
│    system_devices[].sub_type  → 决定显示哪些子系统         │
│    realtimeParams[device_sn]  → 每个设备 PLC 参数           │
│    fault_utils 等效逻辑      → 判定故障/正常               │
│                                                            │
│  RESULT: Each cockpit sees its OWN device status!          │
└──────────────────────────────────────────────────────────┘
```

### 约束确认

| 约束编号 | 内容 | 架构遵守情况 |
|---------|------|-------------|
| C-01 | 零后端改动 | 所有数据来自现有 `/api/miniapp/owner/` 端点 |
| C-02 | 视觉风格不变 | 仅修改 `useBridgeDashboard.js` 数据逻辑，不改 CSS/模板 |
| C-03 | 向后兼容 admin/operator | admin/operator 路径使用独立的 `fetchDashboard()`，不依赖 `useBridgeDashboard` |
| C-04 | 角色数据隔离保持 | IsOwnerUser 中间件不变，由后端鉴权 |
| C-05 | 代码直接提交 main | 架构层面无分支策略影响 |

---

## 架构决策记录（ADRs）

---

### ADR-001: 子系统状态数据源 — 全局聚合 vs Per-座舱 PLC 参数

- **Status**: Accepted
- **Context**: 当前 `useBridgeDashboard.js` 的 `aggregateSubsystemStatus()` 从 `GET /api/dashboard/device-fault-summary/` 获取子系统状态。该 API 对 `FaultEvent` 表做全局 COUNT，不带 `specific_part` 过滤，导致所有座舱看到的子系统状态完全一致。需求明确要求子系统状态反映本座舱设备状态（REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004）。
- **Options**:
  - **Option A: 后端新增加 `specific_part` 参数的故障聚合 API**
    - 描述: 在后端新建或修改 API，使 `device-fault-summary` 支持 `?specific_part={sp}` 过滤
    - 优点: 后端统一故障判定逻辑；前端调用简单
    - 缺点: 违反 C-01 零后端改动约束；增加后端开发、测试、部署成本
  - **Option B: 前端从已有 `getOwnerRealtimeParams(sp)` + `getOwnerStructure(sp)` 读取 per-座舱 PLC 参数，前端等效实现故障判定**
    - 描述: 移除对全局 `device-fault-summary` 的依赖，利用 `_doFetch()` 中已有的第 0 项（structure）和第 6 项（realtimeParams），在 `aggregateSubsystemStatus()` 中直接判定
    - 优点: 零后端改动（满足 C-01）；数据天然 per-座舱隔离；数据与 Web 设备面板同源（`/api/miniapp/owner/realtime-params/` 后端调用与 `/api/devices/realtime-params/` 同逻辑）
    - 缺点: 前端需复制 `fault_utils.py` 的判定规则；增加前端计算量（微小，仅遍历座舱设备参数）
- **Decision**: 选择 Option B。理由：(1) 严格遵守 C-01 零后端改动约束；(2) 数据天然 per-座舱，无需后端额外过滤；(3) 数据与 Web 端 `DeviceCardsView.vue` 同源，天然对齐；(4) 两个必要 API 已存在于 `_doFetch()` 中，移除冗余调用反而减少网络请求。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-001~004 的 per-座舱粒度；减少 2 个 API 调用；数据源头与 Web 端一致
  - 负向: 前端需维护一套与 `fault_utils.py` 对齐的故障判定逻辑（见 ADR-002）；若后端故障判定逻辑变更，前端需同步更新

---

### ADR-002: 故障判定逻辑 — 前端等效实现 vs 后端 API

- **Status**: Accepted
- **Context**: 子系统状态判定需要识别哪些 PLC 参数是故障字段、如何计算故障数。后端 `fault_utils.py` 定义了权威规则：`FAULT_PARAM_NAMES`（26 个具名字段）、`_ERROR_N_PATTERN`（正则 `^error_\d+$`）、`count_faults_for_row()`（普通故障字段计 1，`fresh_air_fault_status` 按 popcount 计 bit 数）。需求 REQ-FUNC-012 要求前端判定规则与后端一致。
- **Options**:
  - **Option A: 新增后端 per-座舱故障计数 API**
    - 描述: 后端新增 `GET /api/miniapp/owner/fault-count/?specific_part={sp}` 返回预计算的故障数
    - 优点: 判定逻辑单一权威来源；前端只需读取数字
    - 缺点: 违反 C-01；`fault_utils.compute_fault_count_v2()` 的后端计算依赖 `PLCLatestData` DB 表，与前端从 `getOwnerRealtimeParams` 拿到的内存数据路径不同，反而可能数据不一致
  - **Option B: 前端纯函数等效实现 `fault_utils.py` 的判定规则**
    - 描述: 在 `useBridgeDashboard.js` 或独立工具模块中实现 `isFaultParam(paramName)`、`countFaultsForRow(paramName, value)`、`computeFaultCount(params)` 三个纯函数，规则与 `fault_utils.py` 完全一致
    - 优点: 零后端改动；计算发生在数据消费端，一致性好；纯函数易于单元测试；规则改动只需改一处 JS 文件
    - 缺点: 存在前后端规则漂移风险（需人工同步）
- **Decision**: 选择 Option B。理由：(1) C-01 铁律不可违反；(2) 判定逻辑简单（集合成员判断 + bit popcount），前端等效实现无歧义；(3) 前后端各自使用各自的数据源（前端用 API 返回的实时参数，后端用 DB），即使走同一个 API 也无法保证数据时间戳一致，不如各自基于已有数据计算；(4) 规则序列化在代码中（`FAULT_PARAM_NAMES` frozenset → JS Set，`FRESH_AIR_FAULT_BITS` 数组），可写注释标注同步来源。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-012；判定逻辑可被子系统聚合和抽屉展示复用
  - 负向: 需要在 `fault_utils.py` 的 `FAULT_PARAM_NAMES` 或 `FRESH_AIR_FAULT_BITS` 变更时同步更新 JS 常量；建议在 `FAULT_PARAM_NAMES` 源码处添加注释提醒

---

### ADR-003: 子系统模块可见性 — 静态列表 vs 动态发现

- **Status**: Accepted
- **Context**: 当前 `aggregateSubsystemStatus()` 硬编码返回全部 4 个子系统（新风/水力/空气品质/能耗），不检查座舱是否实际拥有对应设备。需求 REQ-FUNC-005 明确要求根据 `getOwnerStructure(sp)` 返回的 `system_devices` 动态决定显示哪些子系统。
- **Options**:
  - **Option A: 保持 4 个子系统，增加 `visible` 标志位**
    - 描述: 始终返回 4 个 `SubsystemState` 对象，但根据 structure 中是否有对应设备设置 `visible: true/false`，模板层按 `v-if="sub.visible"` 过滤
    - 优点: 数据形状稳定，模板 `v-for` 无动态索引问题
    - 缺点: 浪费计算（无设备的子系统也遍历判定）；`subsystems` 数组长度不反映实际显示数；下游消费者需要过滤
  - **Option B: `subsystems` 数组仅包含实际拥有的子系统**
    - 描述: 从 `structure.system_devices` 提取 `sub_type`，与系统设备白名单 `['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']` 取交集，仅为匹配到的类型创建 `SubsystemState`
    - 优点: 数据即 UI——`subsystems` 数组长度 = 实际显示数；无浪费计算；模板 `v-for` 天然正确；与 Web 端 `SYSTEM_SUB_KEYS` 白名单对齐
    - 缺点: `subsystems` 动态长度需要模板能够处理（现有模板 `v-for="sub in dash.state.subsystems"` 已支持）
- **Decision**: 选择 Option B。理由：(1) 数据即 UI，减少模板层的条件判断；(2) 不浪费计算资源；(3) 与 Web 端白名单策略一致；(4) 现有 `subsystem-grid` 为 CSS Grid 2 列布局，1~4 个 item 均可自动适配。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-005；`subsystem-grid` 的 CSS Grid 布局对 1~4 个子系统自动适配
  - 负向: `faultTotal` 计算和 section 状态聚合需要遍历动态列表（现有逻辑已遍历数组，无影响）

---

### ADR-004: 房间列表来源 — FaultEvent 驱动 vs 结构驱动

- **Status**: Accepted
- **Context**: 当前 `aggregateRoomStatus()` 以 `structure.rooms` 为主，同时也会把出现在 FaultEvent 但不在 structure 中的房间追加到列表末尾（第 238-259 行）。需求 REQ-FUNC-006 要求以结构数据为准，仅显示座舱实际拥有的房间。
- **Options**:
  - **Option A: 完全移除 FaultEvent 驱动的孤立房间发现**
    - 描述: `aggregateRoomStatus()` 仅遍历 `structure.rooms`，忽视不在结构中的 FaultEvent 房间
    - 优点: 房间列表严格与结构一致；简单
    - 缺点: 结构数据同步延迟时，新出现的 FaultEvent 房间可能暂时无对应隔舱展示
  - **Option B: 结构驱动为主，FaultEvent 孤立房间降级展示**
    - 描述: 以 `structure.rooms` 为主列表。对不在结构中的 FaultEvent 房间——不出现在独立房间隔舱列表中，但降级为在所属子系统面板的抽屉中展示
    - 优点: 房间隔舱严格对齐结构（满足 REQ-FUNC-006）；孤立故障事件不丢失（降级展示）
    - 缺点: 实现略复杂；孤立房间不创建独立隔舱可能让业主困惑
- **Decision**: 选择 Option A（以需求规范 REQ-FUNC-006 的明确指导为准）。理由：(1) REQ-FUNC-006 判定规则明确"以 `getOwnerStructure(sp)` 的 `rooms` 数组为准"，"未匹配到结构的孤立 FaultEvent 房间：降级为在所属子系统面板中展示，不单独创建房间隔舱"；(2) 结构数据 TTL 为 30 天（`STRUCTURE_TTL_MS`），数据稳定可靠；(3) 简化房间隔舱逻辑，移除 `knownNames` 去重和孤儿追加逻辑。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-006；房间隔舱列表 = structure.rooms，简单可控
  - 负向: 结构同步 delay 期间（如新增设备未同步结构），故障可能暂时无房间归属；降级展示需在 FaultDrawer 中处理（见 ADR-006）

---

### ADR-005: 能耗模块状态来源 — 混合 vs 纯 PLC 参数

- **Status**: Accepted
- **Context**: 当前 `deriveEnergyStatus()` 使用三层混合逻辑：(1) 全局 PLC 在线率 `plcRate`;(2) 座舱级 PLC 连通性 `cockpitPlcStatus`;(3) 全局 FaultEvent 关键词匹配 `ENERGY_KEYWORDS`。需求 REQ-FUNC-004 明确要求改用座舱能耗表 PLC 参数判定，移除对 `ENERGY_KEYWORDS` 和全局 PLC 在线率的依赖。
- **Options**:
  - **Option A: 保留部分全局数据作为辅助信号**
    - 描述: 保留座舱级 PLC 连通性（`cockpitPlcStatus`）作为离线预警信号，与能耗表参数故障 OR 运算
    - 优点: 在 PLC 完全离线时仍能给业主提示
    - 缺点: 模糊了 per-座舱 语义——PLC 离线时能耗表参数不可达，应显示为"同步中"而非"故障"；逻辑复杂化
  - **Option B: 纯 PLC 参数判定（与新风/水力/空气品质一致）**
    - 描述: 能耗模块状态仅由能耗表 PLC 参数中的故障字段（`energy_meter_status_communication_error` + `error_\d+` 能耗设备字段）判定。设备不存在 → 不显示；参数不可用 → "同步中"
    - 优点: 与 REQ-FUNC-001~003 子系统判定逻辑完全一致；移除 `ENERGY_KEYWORDS`、`deriveEnergyStatus()` 整函数；能耗模块回归为普通子系统
    - 缺点: PLC 离线时能耗模块只显示"同步中"（无特殊离线指示），但座舱顶部 connectivity bar 已独立显示 PLC 在线状态（REQ-NFUNC-002 不受影响）
- **Decision**: 选择 Option B。理由：(1) REQ-FUNC-004 明确要求"移除对 `ENERGY_KEYWORDS` 关键词匹配和全局 PLC 在线率的依赖";(2) 统一 4 个子系统的判定逻辑，降低维护复杂度；(3) AC-04-03 验证"全局 PLC 在线率显示 50%，但座舱能耗表正常 → 能耗中枢显示正常"，Option B 天然满足。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-004, REQ-FUNC-010; `deriveEnergyStatus()` 整函数可删除；能耗模块回归为统一判定管道
  - 负向: 能耗表 PLC 离线时无法像以前那样从全局 PLC 在线率推断状态；但按需求规范，这是正确的行为——本座舱无数据即不臆断

---

### ADR-006: FaultDrawer 抽屉数据构建 — 独立请求 vs 缓存复用

- **Status**: Accepted
- **Context**: 当业主点击子系统/房间隔舱时，`openCompartment()` 需要构建设备参数列表供 `FaultDrawer` 展示。需求 REQ-FUNC-007 要求展示内容与 Web 设备面板一致，REQ-FUNC-013 要求基于结构+实时参数构建。当前 `_buildCompartmentParams()` 已从 `_structureCache` 和 `_realtimeParamsCache` 构建，但逻辑不完整（只按 product_code 匹配、energy 补偿逻辑粗糙）。
- **Options**:
  - **Option A: 打开抽屉时发起独立 API 请求**
    - 描述: `openCompartment()` 调用 `api.getOwnerRealtimeParams(sp)` + `api.getOwnerStructure(sp)` 获取最新数据
    - 优点: 数据最新
    - 缺点: 增加网络延迟（抽屉打开需等待请求）；重复获取已有数据；额外服务端负载
  - **Option B: 基于 `_structureCache` + `_realtimeParamsCache` 构建，利用 30s 轮询保持新鲜度**
    - 描述: 加强 `_buildCompartmentParams()` 逻辑：(1) 子系统隔舱——从 `structure.system_devices` 匹配 `sub_type`（非 product_code），遍历设备 PLC 参数；(2) 房间隔舱——从 `structure.rooms[].devices` 匹配，遍历设备参数；(3) `fresh_air_fault_status` 展开为 bit 故障项（ADR-007）
    - 优点: 零延迟（缓存命中）；数据一致性（与子系统状态判定用同一批数据）；无额外网络请求
    - 缺点: 数据最多落后 30 秒（轮询间隔）；`_structureCache` 和 `_realtimeParamsCache` 均可能为 null（需降级处理）
- **Decision**: 选择 Option B。理由：(1) 抽屉数据与子系统状态判定共享同一批缓存数据，保证一致性；(2) 30s 轮询间隔下数据新鲜度可接受（REQ-NFUNC-003）；(3) 不增加网络请求；(4) `_buildCompartmentParams()` 已有基本框架，加强匹配逻辑即可。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-007, REQ-FUNC-013; 抽屉展示与子系统状态数据同源；响应即刻
  - 负向: 缓存为 null 时的降级展示需明确定义（显示"同步中"）；`_buildCompartmentParams()` 的匹配逻辑需从 product_code 改为 sub_type（与 Web 白名单对齐）

---

### ADR-007: 新风机故障位展开 — 服务端展开 vs 客户端展开

- **Status**: Accepted
- **Context**: 新风机 `fresh_air_fault_status` 是一个 9-bit 位域值，每个 bit 代表一种独立故障。需求 REQ-FUNC-008 要求按 9 个 bit 逐位展开为具名故障，名称顺序与 Web `FRESH_AIR_FAULT_BITS` 一致。展开逻辑同时用于：(1) 子系统状态计数（popcount 计故障数）；(2) 抽屉参数展示（展开为具名故障项）。
- **Options**:
  - **Option A: 后端返回预展开的故障名称数组**
    - 描述: 在 `getOwnerRealtimeParams` 响应中将 `fresh_air_fault_status` 替换为已展开的具名故障列表
    - 优点: 前端无需位运算；权威来源于后端
    - 缺点: 违反 C-01；改变 API 响应格式（破坏其他消费者）；`fresh_air_fault_status` 原始值丢失
  - **Option B: 前端纯函数展开**
    - 描述: 实现 `expandFreshAirFaultBits(value)` 返回激活的 bit 索引及对应故障名称数组；`countFaultsForRow()` 中对该字段调用 `popcount`（`value.toString(2).split('1').length - 1` 或 `bitCount` 等效实现）
    - 优点: 零后端改动；`FRESH_AIR_FAULT_BITS` 数组与 Web 端源码逐字对齐（可写入注释标注同步来源）；原始值不丢失
    - 缺点: 若 bit 定义变更需同步更新 JS 数组
- **Decision**: 选择 Option B。理由：(1) C-01 约束；(2) 位展开逻辑简单（9 个 if/循环），前端完全胜任；(3) `FRESH_AIR_FAULT_BITS` 数组可从 Web 源码直接复制，带注释标注同步来源。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-008；展开结果同时服务于状态计数和抽屉展示
  - 负向: bit 位定义变更需前后端同步（建议 Web 端 `FRESH_AIR_FAULT_BITS` 作为权威定义来源）

---

### ADR-008: API 调用移除策略与错误处理重构（OQ-01, OQ-02）

- **Status**: Accepted
- **Context**: 随着子系统状态判定改为 per-座舱 PLC 参数，`_doFetch()` 中的 `Promise.allSettled` 第 1 项（`getDashboardDeviceFaultSummary`）和第 2 项（`getDashboardPlcOnlineRate`）不再被子系统判定逻辑使用。需求 REQ-FUNC-009 和第 REQ-FUNC-010 分别要求移除这两项依赖。开放问题 OQ-01（PLC 在线率调用是否完全移除）和 OQ-02（`subsystemErrors['device-summary']` 保留/移除）需要在架构层面给出明确结论。
- **Options**:
  - **Option A: 保留两个 API 调用但标记为未使用**
    - 描述: 保留 `Promise.allSettled` 第 1、2 项，但不将其结果传给 `aggregateSubsystemStatus()`
    - 优点: 改动最小
    - 缺点: 浪费网络请求（每次轮询多 2 个无用 API 调用）；`subsystemErrors['device-summary']` 和 `subsystemErrors['plc']` 继续被设置但无消费者；语义混乱
  - **Option B: 完全移除两个全局 API 调用，重构错误处理**
    - 描述: (1) 从 `_doFetch()` 的 `Promise.allSettled` 中移除第 1、2 项；(2) 后续索引重新编号；(3) 移除 `subsystemErrors['device-summary']` 和 `subsystemErrors['plc']`；(4) 新增 `subsystemErrors['realtime-params']` 和 `subsystemErrors['connectivity']` 错误跟踪（第 6、7 项已有结果处理但错误未记录）；(5) 全局错误判断条件从 `'structure', 'device-summary', 'fault-events'` 改为 `'structure', 'realtime-params', 'fault-events'`
    - 优点: 减少 2 个网络请求/轮询周期；代码语义清晰；错误追踪与实际使用的 API 一致
    - 缺点: `state.plcOnline` 和 `state.plcTotal` 不再被更新（需确认无其他消费者——见下文 OQ-01 裁决）
- **Decision**: 选择 Option B。

  **OQ-01 裁决 — 完全移除 `getDashboardPlcOnlineRate()` 调用**:

  经代码审查确认：
  - Admin/operator 路径（`index.vue` 第 470-519 行 `fetchDashboard()`）**独立获取** `api.getDashboardPlcOnlineRate()`，完全不依赖 `useBridgeDashboard._doFetch()` 中的调用
  - Owner 路径中 `state.plcOnline` 和 `state.plcTotal`（第 360-361 行）仅在 `_doFetch()` 中赋值（第 470-471 行），且模板中不引用这两个字段——owner 模板使用 `state.plcCockpitStatus`（来自 `getOwnerConnectivity`）渲染顶部 connectivity bar
  - 唯一消费者是已废弃的 `deriveEnergyStatus()`（即将删除）
  - 因此，`getDashboardPlcOnlineRate()` 调用可**安全完全移除**。

  **OQ-02 裁决 — 移除 `subsystemErrors['device-summary']`**:

  移除 `getDashboardDeviceFaultSummary()` 调用后，对应的错误处理逻辑成为死代码。替代方案：
  - 新增 `subsystemErrors['realtime-params']` — 当 `getOwnerRealtimeParams(sp)` 失败时设置（用于 REQ-NFUNC-004 降级）
  - 新增 `subsystemErrors['connectivity']` — 当 `getOwnerConnectivity(sp)` 失败时设置
  - 更新全局错误检查条件
  - `subsystemErrors['device-summary']` 完全删除

- **Consequences**:
  - 正向: 满足 REQ-FUNC-009, REQ-FUNC-010；每次轮询减少 2 个 HTTP 请求；错误追踪与实际数据流一致
  - 负向: `state.plcOnline`、`state.plcTotal` 字段保留但不再更新（保持接口兼容）；移除后若未来 admin/operator 路径需要 owner composable 提供 PLC 数据，需重新设计（当前无此需求）

---

## 组件依赖关系图

```
index.vue (MOD-PAGE-HOME)
├── [owner 分支] useBridgeDashboard (MOD-BD-002) ← 本版本主要修改
│   ├── api.js (MOD-API) — 不修改
│   ├── ownerStore (MOD-OWNER-STORE) — 不修改
│   ├── faultUtils.js (MOD-FAULT-UTILS) ← 新增，纯函数
│   └── PagePoller — 不修改
├── [owner 分支] useAnimationControl — 不修改
├── [owner 分支] SubsystemCompartment — 不修改（数据驱动）
├── [owner 分支] RoomCompartment — 不修改（数据驱动）
├── [owner 分支] FaultDrawer — 不修改（数据驱动）
├── [admin/operator 分支] fetchDashboard() — 不修改（完全独立）
└── ArkTabBar — 不修改
```

## 数据源-子系统映射表

| 子系统 | 子系统 ID | sub_type（Web 白名单） | 数据结构来源 | 故障判定字段 | 设备不存在时 |
|--------|----------|----------------------|------------|-------------|------------|
| 新风模块 | fresh-air | fresh_air | `structure.system_devices[sub_type=fresh_air]` → `realtimeParams[device_sn]` | `fresh_air_unit_stop_error`, `fresh_air_unit_communication_error`, `fresh_air_fault_status`（位域 popcount） | 不显示 |
| 水力模块 | hydraulic | hydraulic_module | `structure.system_devices[sub_type=hydraulic_module]` → `realtimeParams[device_sn]` | `hydraulic_module_low_temp_error` | 不显示 |
| 空气品质 | air-quality | air_quality | `structure.system_devices[sub_type=air_quality]` → `realtimeParams[device_sn]` | `air_quality_sensor_communication_error` | 不显示 |
| 能耗中枢 | energy | energy_meter | `structure.system_devices[sub_type=energy_meter]` → `realtimeParams[device_sn]` | `energy_meter_status_communication_error` + 匹配 `error_\d+` 的能耗设备字段 | 不显示 |

注：Web 端 `SYSTEM_SUB_KEYS = ['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']`。小程序通过 `structure.system_devices[].sub_type` 匹配这些值。

---

## 开放问题

| 编号 | 问题 | 状态 | 备注 |
|------|------|------|------|
| OQ-01 | 是否完全移除 `getDashboardPlcOnlineRate()` 调用？ | **已解决** — 完全移除，见 ADR-008 | admin/operator 路径独立获取，owner 路径无消费者 |
| OQ-02 | `subsystemErrors['device-summary']` 保留/移除？ | **已解决** — 移除，替换为 `realtime-params` 和 `connectivity` 错误追踪，见 ADR-008 | — |

---

## [ASSUMPTION] 标注项

本版本无 `[ASSUMPTION]` 标注项。所有架构决策均可追溯至已批准的需求条目（REQ-FUNC-* / REQ-NFUNC-*）或现有代码核查事实。
