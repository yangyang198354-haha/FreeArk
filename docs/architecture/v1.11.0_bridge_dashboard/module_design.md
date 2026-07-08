<file_header>
  <project_name>FreeArk_BridgeDashboard</project_name>
  <flow_mode>PARTIAL_FLOW</flow_mode>
  <group_id>GROUP_B</group_id>
  <phase_id>PHASE_04</phase_id>
  <author_agent>sub_agent_system_architect</author_agent>
  <inception_timestamp>2026-07-08T00:00:00Z</inception_timestamp>
  <status>DRAFT</status>
  <input_files>
    <file path="docs/requirements/v1.11.0_bridge_dashboard/requirements_spec.md" status="APPROVED" />
    <file path="docs/requirements/v1.11.0_bridge_dashboard/user_stories.md" status="APPROVED" />
  </input_files>
</file_header>

# 模块设计 — v1.11.0 Bridge Dashboard（舰桥仪表盘重写）

**文档编号**：MOD-DES-v1110-BD-001
**项目名称**：FreeArk 微信小程序舰桥仪表盘重写
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-07-08
**配套文档**：`architecture_design.md`（同目录）

---

## 1. 模块总览

| MOD-ID | 模块名 | 类型 | 层级 | 职责 | 依赖于 |
|--------|--------|------|------|------|--------|
| MOD-BD-001 | pages/home/index.vue | Page | 页面编排层 | 舰桥页面入口，编排 composable 与子组件 | MOD-BD-002, MOD-BD-004~010 |
| MOD-BD-002 | useBridgeDashboard | Composable | 逻辑层 | 仪表盘数据获取、状态聚合、轮询管理、座舱切换 | api.js, ownerStore, authStore, PagePoller, arkZoneMap |
| MOD-BD-003 | useAnimationControl | Composable | 逻辑层 | CSS 动画暂停/恢复控制（基于页面可见性） | 无 |
| MOD-BD-004 | ShipHull.vue | Component | 展示层 | 战舰外壳容器（网格、扫描线、clip-path 轮廓） | 无 |
| MOD-BD-005 | SubsystemCompartment.vue | Component | 展示/交互层 | 子系统隔舱（新风/能耗/水力/空气品质）渲染与点击 | MOD-BD-002（via props） |
| MOD-BD-006 | RoomCompartment.vue | Component | 展示/交互层 | 房间隔舱渲染与点击 | MOD-BD-002（via props） |
| MOD-BD-007 | FaultDrawer.vue | Component | 展示/交互层 | 半屏故障/预警列表抽屉 | MOD-BD-002（via props） |
| MOD-BD-008 | HealthIndicator.vue | Component | 展示层 | 整体健康状态菱形 LED 指示器 | 无 |
| MOD-BD-009 | PlcIndicator.vue | Component | 展示层 | PLC 在线状态独立指示器 | 无 |
| MOD-BD-010 | CabinSwitcher.vue | Component | 展示/交互层 | 多座舱切换 picker | MOD-BD-002（via props/emit） |
| MOD-BD-011 | utils/api.js（扩展） | Utility | 数据访问层 | API 封装——新增 `getDashboardDeviceFaultSummary()` | http.js |

---

## 2. 模块详情

---

### MOD-BD-001: pages/home/index.vue（舰桥页面）

- **职责**: 舰桥仪表盘页面入口。编排 `useBridgeDashboard` composable 与子组件，管理页面生命周期（onShow/onHide/onPullDownRefresh），处理加载态/空态/错误态的条件渲染。仅渲染 owner（role=user）路径——admin/operator 路径保留原有 Material Design 视图（不修改）。

- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-010, REQ-FUNC-011; REQ-NFUNC-001, REQ-NFUNC-002, REQ-NFUNC-003, REQ-NFUNC-004, REQ-NFUNC-005
- **覆盖用户故事**: US-01, US-02, US-03, US-04, US-05, US-06

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-001-01 | 页面生命周期 | `onShow()` | 页面显示时调用 composable.start()，恢复动画 |
  | IFC-BD-001-02 | 页面生命周期 | `onHide()` | 页面隐藏时调用 composable.stop()，暂停动画 |
  | IFC-BD-001-03 | 页面生命周期 | `onPullDownRefresh()` | 下拉刷新触发 composable.refresh(true)，完成后 `uni.stopPullDownRefresh()` |
  | IFC-BD-001-04 | Props（→SubsystemCompartment） | `subsystem: {id, name, status, faultCount, productCode}` | 子系统隔舱数据对象 |
  | IFC-BD-001-05 | Props（→RoomCompartment） | `room: {id, name, status, faultCount, warningCount}` | 房间隔舱数据对象 |
  | IFC-BD-001-06 | Props（→FaultDrawer） | `compartment: {type, id, name, faultEvents[]} \| null` | 当前打开的隔舱数据 |
  | IFC-BD-001-07 | Event（←SubsystemCompartment） | `@open="onCompartmentOpen(subsystem)"` | 子系统隔舱点击 |
  | IFC-BD-001-08 | Event（←RoomCompartment） | `@open="onCompartmentOpen(room)"` | 房间隔舱点击 |
  | IFC-BD-001-09 | Event（←FaultDrawer） | `@close="onCompartmentClose()"` | 抽屉关闭 |
  | IFC-BD-001-10 | Event（←CabinSwitcher） | `@change="onCabinChange(specificPart)"` | 座舱切换 |

- **依赖模块**: MOD-BD-002 (useBridgeDashboard), MOD-BD-003 (useAnimationControl), MOD-BD-004~010 (子组件), `store/auth.js` (useAuthStore), 现有 ArkTabBar 组件

- **外部依赖**: 无

- **备注**: 
  - 现有 `index.vue` 中 admin/operator 的 `<view v-else class="admin-page">` 分支完整保留，不做任何修改。
  - 现有 `owner-page` 模板分支完全重写。
  - 保留 `goBind()` 跳转绑定页的逻辑。

---

### MOD-BD-002: useBridgeDashboard（Composable）

- **职责**: 封装舰桥仪表盘的全部数据获取、状态聚合、轮询启停、座舱切换逻辑。对外暴露 reactive 状态对象和操作方法。内部使用 `Promise.allSettled` 并行请求 6 个 API，支持单 API 失败容错。

- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-005, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-011; REQ-NFUNC-003, REQ-NFUNC-005
- **覆盖用户故事**: US-01, US-04, US-05, US-06

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-002-01 | Reactive State | `loading: Boolean` | 首次加载中标志 |
  | IFC-BD-002-02 | Reactive State | `refreshing: Boolean` | 刷新中标志（不覆盖隔舱数据） |
  | IFC-BD-002-03 | Reactive State | `error: String \| null` | 全局错误消息（全部 API 失败时） |
  | IFC-BD-002-04 | Reactive State | `bindings: Array<{specific_part, location_name}>` | 绑定座舱列表 |
  | IFC-BD-002-05 | Reactive State | `selectedSp: String` | 当前选中 specific_part |
  | IFC-BD-002-06 | Reactive State | `selectedLabel: String` | 当前座舱显示名称 |
  | IFC-BD-002-07 | Reactive State | `overallStatus: {level: 'syncing'\|'normal'\|'warning'\|'fault', text: String}` | 整体健康状态 |
  | IFC-BD-002-08 | Reactive State | `subsystems: Array<SubsystemState>` | 子系统隔舱状态列表（详见下方类型定义） |
  | IFC-BD-002-09 | Reactive State | `rooms: Array<RoomState>` | 房间隔舱状态列表（详见下方类型定义） |
  | IFC-BD-002-10 | Reactive State | `plcOnline: Number` | PLC 在线数 |
  | IFC-BD-002-11 | Reactive State | `plcTotal: Number` | PLC 总数 |
  | IFC-BD-002-12 | Reactive State | `condensationCount: Number` | 活跃结露预警总数 |
  | IFC-BD-002-13 | Reactive State | `activeCompartment: CompartmentDetail \| null` | 当前打开的隔舱详情（用于 FaultDrawer） |
  | IFC-BD-002-14 | Reactive State | `subsystemErrors: Object<id, String>` | 各子系统隔舱的独立错误消息 |
  | IFC-BD-002-15 | Method | `start(): void` | 启动：拉取初始数据 + 启动 30s 轮询 |
  | IFC-BD-002-16 | Method | `stop(): void` | 停止轮询 |
  | IFC-BD-002-17 | Method | `refresh(force?: Boolean): Promise<void>` | 手动刷新（force=true 时绕过缓存） |
  | IFC-BD-002-18 | Method | `switchCockpit(sp: String): Promise<void>` | 切换到指定 specific_part 座舱 |
  | IFC-BD-002-19 | Method | `openCompartment(compartment: {type: 'subsystem'\|'room', id: String}): void` | 打开隔舱详情 |
  | IFC-BD-002-20 | Method | `closeCompartment(): void` | 关闭隔舱详情 |
  | IFC-BD-002-21 | Lifecycle Hook | `onShow: () => void` | 需由页面 `onShow` 传入 |
  | IFC-BD-002-22 | Lifecycle Hook | `onHide: () => void` | 需由页面 `onHide` 传入 |

- **类型定义**:

  ```typescript
  // 子系统隔舱状态
  type SubsystemState = {
    id: string                           // 'fresh-air' | 'energy' | 'hydraulic' | 'air-quality'
    name: string                         // 显示名称
    status: 'normal' | 'warning' | 'fault' | 'idle'  // 最严重状态
    faultCount: number                   // 活跃故障数
    warningCount: number                 // 活跃预警数（不含故障）
    productCode: number | null           // 关联 product_code（新风=130004, 水力=270001, 空气品质=100007, 能耗=null）
    dataSource: string                   // 数据来源说明（调试用）
  }

  // 房间隔舱状态
  type RoomState = {
    id: string                           // room_id
    name: string                         // 房间名
    status: 'normal' | 'warning' | 'fault' | 'idle'
    faultCount: number                   // 活跃故障数（severity=error）
    warningCount: number                 // 活跃预警数（severity=warning + 结露预警）
    hasCondensation: boolean             // 是否有活跃结露预警
  }

  // 隔舱详情（打开抽屉时构造）
  type CompartmentDetail = {
    type: 'subsystem' | 'room'
    id: string
    name: string
    status: string
    faultEvents: Array<{
      id: number
      deviceName: string
      deviceTypeLabel: string
      severity: string                   // 'error' | 'warning' | 'condensation'
      faultType: string
      faultMessage: string
      firstSeenAt: string
      roomName: string
    }>
  }
  ```

- **内部函数（纯函数管道，可单测）**:

  | 内部函数 | 签名 | 说明 |
  |---------|------|------|
  | `aggregateSubsystemStatus(deviceFaultSummary, plcRate, faultEvents)` | `→ SubsystemState[]` | 从 device-fault-summary 响应 + PLC 在线率 + FaultEvent 推导 4 个子系统状态 |
  | `aggregateRoomStatus(structure, faultEvents, condensationCount)` | `→ RoomState[]` | 从骨架结构 + FaultEvent（按 room_name 分组）推导房间状态 |
  | `computeOverallStatus(subsystems, rooms)` | `→ {level, text}` | 聚合所有子系统+房间状态，取最严重 |
  | `deriveEnergyStatus(plcRate, faultEvents)` | `→ SubsystemState` | 能耗子系统状态推导（过滤能效相关 FaultEvent） |
  | `filterFaultEventsByCompartment(faultEvents, compartment)` | `→ FaultEvent[]` | 按隔舱类型过滤故障事件列表 |
  | `severityToStatus(severity)` | `→ 'normal' \| 'warning' \| 'fault'` | FaultEvent.severity 映射到内部状态 |

- **依赖模块**: `@/utils/api` (api 对象), `@/store/owner` (useOwnerStore——仅用于 bindings 缓存), `@/store/auth` (useAuthStore——role 校验), `@/utils/poller` (PagePoller), `@/subpackages/game/arkZoneMap` (worseStatus, STATUS_RANK)

- **外部依赖**: 无

- **备注**: 
  - `start()` 中先调用 `ownerStore.ensureBindings({ allowStale: true })` 获取缓存座舱列表加速首屏，再直接调用 API（绕过 Store 缓存）获取最新仪表盘数据。
  - 数据刷新失败时，保持上次成功数据的隔舱状态不变，仅更新 `subsystemErrors[id]`。
  - `faultEvents` 在 composable 中以 `Map<roomName, FaultEvent[]>` 结构缓存，加速房间隔舱查询。

---

### MOD-BD-003: useAnimationControl（Composable）

- **职责**: 根据页面可见性控制战舰透视图的全部 CSS 动画的暂停/恢复。通过向页面根元素注入条件 class 实现。

- **覆盖需求**: REQ-NFUNC-002

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-003-01 | Reactive State | `animationsPaused: Boolean` | true=动画暂停，false=动画运行 |
  | IFC-BD-003-02 | Method | `pause(): void` | 暂停动画（设置 animationsPaused=true） |
  | IFC-BD-003-03 | Method | `resume(): void` | 恢复动画（设置 animationsPaused=false） |
  | IFC-BD-003-04 | Lifecycle Hook | `onShow: () => void` | 页面可见回调 |
  | IFC-BD-003-05 | Lifecycle Hook | `onHide: () => void` | 页面不可见回调 |

- **依赖模块**: 无

- **外部依赖**: 无

- **备注**: 
  - 模板中使用：`<view :class="{ 'animations-paused': animationsPaused }">` 包裹战舰透视图区域。
  - CSS 规则：`.animations-paused * { animation-play-state: paused !important; }`
  - 若微信版本不支持 `animation-play-state`，降级方案：暂停时移除 animation class，恢复时重新添加。

---

### MOD-BD-004: ShipHull.vue（战舰外壳容器）

- **职责**: 渲染战舰透视图的外壳容器，包括：clip-path 多边形战舰轮廓、深色渐变背景、80rpx 网格叠加层、HUD 扫描线。包裹所有内部隔舱子组件。整体边框颜色随 `overallStatus.level` 变化（正常=青边框，预警=黄边框，告警=红边框）。

- **覆盖需求**: REQ-FUNC-004, REQ-NFUNC-001

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-004-01 | Props | `status: 'normal' \| 'warning' \| 'fault' \| 'syncing' \| 'idle'` | 战舰整体状态（控制边框颜色） |
  | IFC-BD-004-02 | Props | `animationsPaused: Boolean` | 是否暂停动画 |
  | IFC-BD-004-03 | Slot | `default` | 战舰内部内容（子系统 dock + 动力脊线 + 房间网格 + 舰尾引擎） |

- **依赖模块**: 无

- **外部依赖**: 无

- **备注**: 
  - 复用现有 `ship-shell` 的 clip-path（`polygon(50% 0, 94% 7%, 100% 49%, 91% 95%, 50% 100%, 9% 95%, 0 49%, 6% 7%)`）。
  - CSS 动画复用：`ownerScan`（HUD 扫描线 5s）、`pulseSoft`（装饰点脉动 1.8s）。
  - 边框 class 绑定：`state-${status}`。

---

### MOD-BD-005: SubsystemCompartment.vue（子系统隔舱）

- **职责**: 渲染单个子系统隔舱（新风/能耗/水力模块/空气品质）。显示子系统图标、名称、故障/预警计数。颜色编码：正常=青蓝边框+绿色状态点，预警=黄边框+黄发光状态点，告警=红边框+红发光状态点+损伤闪烁动画。点击触发 `@open` 事件。

- **覆盖需求**: REQ-FUNC-002, REQ-FUNC-006

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-005-01 | Props | `subsystem: SubsystemState` | 子系统状态数据（来自 MOD-BD-002） |
  | IFC-BD-005-02 | Props | `animationsPaused: Boolean` | 是否暂停动画 |
  | IFC-BD-005-03 | Event | `@open(subsystem: SubsystemState): void` | 隔舱点击事件 |
  | IFC-BD-005-04 | Computed | `statusClass: String` | `'state-normal' \| 'state-warning' \| 'state-fault' \| 'state-idle'` |
  | IFC-BD-005-05 | Computed | `displayName: String` | 隔舱显示名称（'新风模块' \| '能耗中枢' \| '水力模块' \| '空气品质'） |
  | IFC-BD-005-06 | Computed | `iconKind: String` | 隔舱图标类型（'fan' \| 'energy' \| 'hydraulic' \| 'air'） |

- **依赖模块**: 无（纯展示组件，通过 props 接收数据）

- **外部依赖**: 无

- **备注**: 
  - 最小触控区 ≥ 44x44 逻辑像素（REQ-NFUNC-004）。
  - 正常状态（status=normal）下不显示故障/预警计数，仅显示青色隔舱+绿色状态点。
  - 故障/预警计数显示格式：`faultCount > 0 ? `${faultCount} 故障` : warningCount > 0 ? `${warningCount} 预警` : ''`。
  - 损伤闪烁动画仅在 `status=fault` 时激活（复用 `damageBlink` keyframe）。
  - 隔舱图标使用 CSS 纯绘制（复用现有 `fan-top`/`host-top`/`panel-top` 模式），能耗隔舱设计为"电池/能量核心"造型。

---

### MOD-BD-006: RoomCompartment.vue（房间隔舱）

- **职责**: 渲染单个房间隔舱（客厅/主卧/次卧/书房/儿童房）。显示全息文字悬浮房间名、状态指示点、故障/预警计数。颜色编码与子系统隔舱一致。点击触发 `@open` 事件。

- **覆盖需求**: REQ-FUNC-003, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-010

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-006-01 | Props | `room: RoomState` | 房间状态数据（来自 MOD-BD-002） |
  | IFC-BD-006-02 | Props | `animationsPaused: Boolean` | 是否暂停动画 |
  | IFC-BD-006-03 | Props | `shapeIndex: Number` | 隔舱 clip-path 造型索引（0-3，四选一旋转） |
  | IFC-BD-006-04 | Event | `@open(room: RoomState): void` | 房间隔舱点击事件 |

- **依赖模块**: 无

- **外部依赖**: 无

- **备注**: 
  - 最小触控区 ≥ 44x44 逻辑像素（REQ-NFUNC-004）。
  - **禁止**展示温度数值、湿度、CO2 等任何运行参数——仅展示故障/预警计数和房间名（REQ-FUNC-010）。
  - 房间隔舱 clip-path 异形多边形复用现有 4 种造型（`room-shape-0` ~ `room-shape-3`），通过 CSS 实现。
  - 若为 5 个房间，grid 布局为 3+2 两行（flex-wrap: wrap）。
  - 结露预警融入房间时，在故障列表中以"结露预警"标签标注（REQ-FUNC-007）。

---

### MOD-BD-007: FaultDrawer.vue（故障抽屉）

- **职责**: 半屏弹出抽屉，展示隔舱对应的活跃故障/预警列表。深色半透明背景（`rgba(6,12,28,0.95)`）+ 青色发光边框。列表项带状态色左边框（红=故障 `#ff315d` / 黄=预警 `#ffd400`）。显示设备名、故障类型、严重程度、故障描述、首次发现时间。底部关闭手柄。无故障时显示"运行正常"提示。支持下拉关闭、点击遮罩关闭。

- **覆盖需求**: REQ-FUNC-006, REQ-FUNC-007

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-007-01 | Props | `compartment: CompartmentDetail \| null` | 隔舱详情数据，null=关闭抽屉 |
  | IFC-BD-007-02 | Props | `visible: Boolean` | 抽屉可见性 |
  | IFC-BD-007-03 | Event | `@close(): void` | 抽屉关闭事件（遮罩点击/手势下拉/关闭手柄） |
  | IFC-BD-007-04 | Computed | `title: String` | 抽屉标题（`${compartment.name} — ${compartment.type === 'subsystem' ? '子系统' : '房间'}状态`） |
  | IFC-BD-007-05 | Computed | `hasEvents: Boolean` | 是否有故障/预警事件 |
  | IFC-BD-007-06 | Computed | `eventsBySeverity: Array` | 按严重程度排序的事件列表（error 在前，warning 在后） |

- **依赖模块**: 无（纯展示组件）

- **外部依赖**: 无

- **备注**: 
  - 抽屉高度：视口高度的 55% ~ 65%（`max-height: 65vh`），内容溢出时 `scroll-view` 纵向滚动。
  - 动画：打开时 `transform: translateY(0)` + `transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)`，关闭时 `transform: translateY(100%)`。
  - 安全区域适配：`padding-bottom: env(safe-area-inset-bottom)`。
  - 列表项格式：`[状态色左边框 6rpx] [设备名] [故障类型标签] [严重程度标签] [故障描述] [首次发现时间]`。
  - 结露预警事件标注为"结露预警"黄色标签。

---

### MOD-BD-008: HealthIndicator.vue（整体健康指示器）

- **职责**: 渲染舰桥页面顶部的整体健康状态菱形 LED 指示器。四级状态：正常（绿）、预警（黄）、告警（红）、同步中（灰）。显示对应文字标签。菱形 LED 带 `box-shadow` 发光效果。

- **覆盖需求**: REQ-FUNC-001

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-008-01 | Props | `status: {level: 'syncing'\|'normal'\|'warning'\|'fault', text: String}` | 整体健康状态 |
  | IFC-BD-008-02 | Props | `condensationCount: Number` | 结露预警总数（显示在指示器旁） |
  | IFC-BD-008-03 | Computed | `ledClass: String` | `'state-syncing' \| 'state-normal' \| 'state-warning' \| 'state-fault'` |

- **依赖模块**: 无

- **外部依赖**: 无

- **备注**: 
  - 复用现有 `owner-state` / `state-led` 样式（菱形 `transform: rotate(45deg)` + `box-shadow` 发光）。
  - 结露预警计数角标（CondensationBadge）在指示器旁独立显示（REQ-FUNC-007），如需独立封装可内联或作为此组件的 slot。

---

### MOD-BD-009: PlcIndicator.vue（PLC 独立指示器）

- **职责**: 渲染 PLC 在线状态独立指示器。显示"通讯链路"标签 + LED 状态灯 + 在线/离线计数（如"3/5 在线"）。样式与赛博朋克主题一致（青线边框、发光 LED）。位于舰尾引擎区下方。全部在线→正常青蓝，部分离线→预警橙红闪烁，全部离线→告警红色。

- **覆盖需求**: REQ-FUNC-008

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-009-01 | Props | `onlineCount: Number` | PLC 在线数 |
  | IFC-BD-009-02 | Props | `totalCount: Number` | PLC 总数 |
  | IFC-BD-009-03 | Props | `loading: Boolean` | 数据加载中 |
  | IFC-BD-009-04 | Computed | `status: 'normal' \| 'warning' \| 'fault' \| 'idle'` | onlineCount===totalCount→normal; onlineCount>0→warning; onlineCount===0→fault; loading→idle |
  | IFC-BD-009-05 | Computed | `label: String` | 显示文字（`${onlineCount}/${totalCount} 在线` \| '—' \| '同步中'） |

- **依赖模块**: 无

- **外部依赖**: 无

- **备注**: 
  - 视觉上明确区别于隔舱体系——使用水平状态条而非 clip-path 隔舱。
  - 全部在线时不闪烁，部分离线时使用 `pulseSoft` 动画（复用现有 keyframe），全部离线时使用 `damageBlink` 动画。

---

### MOD-BD-010: CabinSwitcher.vue（座舱切换器）

- **职责**: 当用户绑定多个 specific_part 时，显示座舱切换 picker。使用 `<picker mode="selector">` 组件。显示当前选中座舱的 location_name 或 specific_part。切换时触发 `@change` 事件。

- **覆盖需求**: REQ-FUNC-005

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-010-01 | Props | `bindings: Array<{specific_part: String, location_name: String}>` | 绑定座舱列表 |
  | IFC-BD-010-02 | Props | `selectedIndex: Number` | 当前选中索引 |
  | IFC-BD-010-03 | Props | `visible: Boolean` | 是否显示切换器（bindings.length > 1 时为 true） |
  | IFC-BD-010-04 | Event | `@change(index: Number): void` | 座舱切换事件（传递选中索引） |
  | IFC-BD-010-05 | Computed | `labels: String[]` | picker range 标签列表 |
  | IFC-BD-010-06 | Computed | `currentLabel: String` | 当前座舱显示名 |

- **依赖模块**: 无

- **外部依赖**: 无

- **备注**: 
  - 复用现有 `unit-bar` / `unit-picker` 样式（深色半透明背景+青线边框+发光文字）。
  - `bindings.length <= 1` 时不显示此组件。

---

### MOD-BD-011: utils/api.js 扩展（新增 API 封装）

- **职责**: 在现有 `miniprogram/utils/api.js` 中新增 `getDashboardDeviceFaultSummary()` 方法，封装 `/api/dashboard/device-fault-summary/` 端点。

- **覆盖需求**: REQ-FUNC-002

- **公开接口契约**:

  | 接口 ID | 类型 | 签名 | 说明 |
  |---------|------|------|------|
  | IFC-BD-011-01 | Method | `getDashboardDeviceFaultSummary(): Promise<{success: Boolean, data: {fresh_air_unit: {total, fault_count}, hydraulic_module: {total, fault_count}, air_quality_sensor: {total, fault_count}, other_devices: {total, fault_count}}}>` | 获取四类设备的故障汇总 |
  | IFC-BD-011-02 | HTTP 端点 | `GET /api/dashboard/device-fault-summary/` | 后端已实现（views.py:1563-1606），仅前端未封装 |
  | IFC-BD-011-03 | 返回类型 | 同 MOD-BD-002.SubsystemState 的数据源映射 | fresh_air_unit → 新风, hydraulic_module → 水力, air_quality_sensor → 空气品质 |

- **依赖模块**: `@/utils/http`

- **外部依赖**: 后端 `/api/dashboard/device-fault-summary/` 端点（已存在）

- **备注**: 
  - 这是本次唯一需要修改的现有文件（仅新增一个方法，不改变现有方法）。
  - 实现：`getDashboardDeviceFaultSummary: () => http.get('/api/dashboard/device-fault-summary/')`。
  - 此 API 受 IsOperatorOrAbove 权限保护——但根据 `UserRoleApiGuardMiddleware`，`/api/dashboard/` 前缀不在白名单中，需验证 owner 角色是否有访问权限。若被拦截，需由 PM 协调后端将 `/api/dashboard/device-fault-summary/` 加入白名单或单独调整为 IsOwnerUser 鉴权。**[ASSUMPTION — requires PM confirmation]**。

---

## 3. 依赖关系图（文本格式）

```
MOD-BD-001 (index.vue) 
  ├── MOD-BD-002 (useBridgeDashboard) ──► api.js (MOD-BD-011), ownerStore, authStore, PagePoller, arkZoneMap
  ├── MOD-BD-003 (useAnimationControl) ──► (独立)
  ├── MOD-BD-004 (ShipHull) ──► (仅依赖 slot 内容)
  ├── MOD-BD-005 (SubsystemCompartment) ──► (纯展示，无依赖)
  ├── MOD-BD-006 (RoomCompartment) ──► (纯展示，无依赖)
  ├── MOD-BD-007 (FaultDrawer) ──► (纯展示，无依赖)
  ├── MOD-BD-008 (HealthIndicator) ──► (纯展示，无依赖)
  ├── MOD-BD-009 (PlcIndicator) ──► (纯展示，无依赖)
  ├── MOD-BD-010 (CabinSwitcher) ──► (纯展示，无依赖)
  └── ArkTabBar (现有，不修改)

MOD-BD-011 (api.js 扩展) ──► http.js (现有，不修改)
```

**循环依赖检查**: 无循环依赖。所有箭头单向：页面 → Composable → API/Store；页面 → 组件（Props 向下，Events 向上）。

## 4. 需求-模块覆盖矩阵

| 需求 ID | 覆盖模块 | 状态 |
|---------|---------|------|
| REQ-FUNC-001 (整体健康) | MOD-BD-002 (聚合逻辑) + MOD-BD-008 (展示) | 已覆盖 |
| REQ-FUNC-002 (子系统隔舱) | MOD-BD-002 (聚合逻辑) + MOD-BD-005 (展示) + MOD-BD-011 (API) | 已覆盖 |
| REQ-FUNC-003 (房间隔舱) | MOD-BD-002 (聚合逻辑) + MOD-BD-006 (展示) | 已覆盖 |
| REQ-FUNC-004 (战舰透视图) | MOD-BD-004 (外壳) + MOD-BD-005 (子系统) + MOD-BD-006 (房间) + MOD-BD-001 (页面布局) | 已覆盖 |
| REQ-FUNC-005 (业主视角/多座舱) | MOD-BD-002 (切换逻辑) + MOD-BD-010 (切换器) | 已覆盖 |
| REQ-FUNC-006 (隔舱点击) | MOD-BD-005 + MOD-BD-006 (点击事件) + MOD-BD-007 (抽屉) + MOD-BD-002 (数据准备) | 已覆盖 |
| REQ-FUNC-007 (结露预警) | MOD-BD-002 (聚合逻辑) + MOD-BD-008 (角标) + MOD-BD-006 (房间融合) + MOD-BD-007 (列表) | 已覆盖 |
| REQ-FUNC-008 (PLC 指示器) | MOD-BD-002 (数据获取) + MOD-BD-009 (展示) | 已覆盖 |
| REQ-FUNC-009 (数据刷新) | MOD-BD-002 (轮询+手动刷新) + MOD-BD-001 (下拉事件) | 已覆盖 |
| REQ-FUNC-010 (排除运行参数) | MOD-BD-006 (仅渲染故障计数) + MOD-BD-005 (不渲染参数值) | 已覆盖 |
| REQ-FUNC-011 (加载/空态/异常) | MOD-BD-001 (条件渲染) + MOD-BD-002 (error/loading 状态) | 已覆盖 |
| REQ-NFUNC-001 (赛博朋克一致性) | MOD-BD-004 (背景/网格/扫描线) + 全局 CSS 复用 | 已覆盖 |
| REQ-NFUNC-002 (页面性能) | MOD-BD-002 (30s轮询) + MOD-BD-003 (动画暂停) | 已覆盖 |
| REQ-NFUNC-003 (数据隔离) | MOD-BD-002 (使用业主 API + Token 鉴权) | 已覆盖 |
| REQ-NFUNC-004 (可触性) | MOD-BD-005 + MOD-BD-006 (≥44x44 触控区) | 已覆盖 |
| REQ-NFUNC-005 (容错降级) | MOD-BD-002 (Promise.allSettled + 独立错误状态) | 已覆盖 |

**需求覆盖缺口**: 0。全部 11 个功能需求和 5 个非功能需求均有对应模块覆盖。

## 5. 接口类型汇总

| 接口类别 | 数量 | 说明 |
|---------|------|------|
| Props (父→子) | 18 | 组件接收数据 |
| Events (子→父) | 7 | 隔舱点击、抽屉关闭、座舱切换 |
| Reactive State (Composable→模板) | 14 | useBridgeDashboard 暴露状态 |
| Methods (Composable→模板) | 8 | 启动/停止/刷新/切换/打开/关闭 |
| API Methods (api.js) | 1 (新增) | getDashboardDeviceFaultSummary |
| Slots | 1 | ShipHull 默认插槽 |
