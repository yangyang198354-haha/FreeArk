<file_header>
  <project_name>FreeArk_BridgeDashboard</project_name>
  <flow_mode>PARTIAL_FLOW</flow_mode>
  <group_id>GROUP_B</group_id>
  <phase_id>PHASE_03</phase_id>
  <author_agent>sub_agent_system_architect</author_agent>
  <inception_timestamp>2026-07-08T00:00:00Z</inception_timestamp>
  <status>DRAFT</status>
  <input_files>
    <file path="docs/requirements/v1.11.0_bridge_dashboard/requirements_spec.md" status="APPROVED" />
    <file path="docs/requirements/v1.11.0_bridge_dashboard/user_stories.md" status="APPROVED" />
  </input_files>
</file_header>

# 系统架构设计 — v1.11.0 Bridge Dashboard（舰桥仪表盘重写）

**文档编号**：ARCH-DES-v1110-BD-001
**项目名称**：FreeArk 微信小程序舰桥仪表盘重写
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-07-08
**输入文档**：
- `docs/requirements/v1.11.0_bridge_dashboard/requirements_spec.md`（全部 9 项已闭环，PM 已确认）
- `docs/requirements/v1.11.0_bridge_dashboard/user_stories.md`（6 个用户故事，PM 已确认）
- `miniprogram/pages/home/index.vue`（现有舰桥页面，代码勘察）
- `miniprogram/utils/api.js`（现有 API 封装清单）
- `miniprogram/store/owner.js`（现有业主 Store）
- `miniprogram/store/auth.js`（现有认证 Store）
- `miniprogram/utils/poller.js`（现有轮询器）
- `miniprogram/components/ArkTabBar.vue`（现有底栏）
- `miniprogram/subpackages/game/arkZoneMap.js`（现有故障判定工具函数）

---

## 1. 架构概览

### 1.1 背景与本期变更定位

v1.5.0 建立了微信小程序基线，`pages/home/index` 页面当前包含两套视觉体系：业主（role=user）的赛博朋克战舰主题户型俯视图，以及管理员/运维（admin/operator）的 Material Design 仪表盘。本次 v1.11.0_bridge_dashboard 仅重写 **owner（user）** 视角的舰桥页面，目标：

1. **统一赛博朋克视觉**：将舰桥页面从当前"户型俯视图+温度数值"改写为"2D 战舰 X 射线透视仪表盘"，仅展示故障/预警状态，移除所有运行参数。
2. **扩展子系统隔舱**：从当前 2-4 个通用模块（主机/风机/面板）扩展为 4 个明确定义的子系统隔舱（新风/能耗/水力模块/空气品质）。
3. **增加交互能力**：隔舱点击弹出半屏抽屉查看故障详情。
4. **增加独立指示器**：PLC 在线状态独立指示器 + 结露预警独立计数角标。
5. **维护零后端改动**：所有数据来自现有 API，仅在 `api.js` 中新增一个已有的 `/api/dashboard/device-fault-summary/` 端点的前端封装。

**关键约束（不重新质疑）**：

| 约束 | 来源 |
|------|------|
| C-01 赛博朋克风格一致：色板、动画、装饰元素复用现有体系 | REQ-NFUNC-001；需求 §2.1 |
| C-02 仅警告和故障：不展示任何运行参数（温度、kWh、CO2等） | REQ-FUNC-010 |
| C-03 角色数据隔离：owner 仅见绑定 specific_part 数据，走 `/api/miniapp/owner/` | REQ-NFUNC-003；v1.8.0 体系 |
| C-04 零后端改动：数据全部来自现有 API | 需求 §1.3 |
| C-05 不改变其他页面：ArkTabBar、聊天页等保持原样 | 需求 §1.3 |
| P0 仅 user 角色：admin/operator 视图不在本版本范围 | PM 确认 |

### 1.2 整体架构图（文字）

```
[pages/home/index.vue — 重写后（仅 owner 路径）]
    │
    ├─ onShow ──►  useBridgeDashboard().start()
    │               │
    │               ├─ 并行拉取（Promise.allSettled）:
    │               │   api.getOwnerStructure(sp)          → 房间骨架
    │               │   api.getDashboardDeviceFaultSummary() → 子系统故障汇总【新增封装】
    │               │   api.getDashboardPlcOnlineRate()     → PLC 在线率
    │               │   api.getFaultEvents(sp, active)      → 活跃故障事件
    │               │   api.getCondensationWarningCount()   → 结露预警计数
    │               │   api.getBindStatus()                → 绑定列表（多座舱）
    │               │
    │               ├─ 30s 轮询 ──► PagePoller（复用现有）
    │               │
    │               └─ 状态聚合 ──► reactive dashboardState
    │                                ├─ overallStatus: {level, text}
    │                                ├─ subsystemCompartments[]
    │                                ├─ roomCompartments[]
    │                                ├─ plcStatus
    │                                └─ condensationCount
    │
    ├─ 模板渲染:
    │   HealthIndicator          ← overallStatus
    │   CondensationBadge        ← condensationCount
    │   CabinSwitcher            ← bindings[]
    │   ShipHull (背景容器)
    │     ├─ ShipNose            (FREEARK 铭牌)
    │     ├─ SubsystemDock       ← subsystemCompartments[]
    │     ├─ ShipSpine           (动力脊线动画)
    │     ├─ RoomGrid            ← roomCompartments[]
    │     ├─ ShipTail            (引擎脉冲)
    │     └─ PlcIndicator        ← plcStatus
    │   FaultDrawer              ← 隔舱点击事件
    │   ArkTabBar                (现有，不动)
    │
    └─ 样式: 复用现有 @keyframes（ownerScan/pulseSoft/powerFlow/damageBlink/enginePulse）
              扩展隔舱 clip-path 造型、颜色编码规则
```

### 1.3 架构风格

**页面级组件 + Composables 分离**。与现有 `pages/home/index.vue` 模式一致：单个页面文件作为编排入口，通过 Vue 3 Composition API 的 composable 函数分离数据获取、状态聚合、轮询逻辑。模板中使用内联子组件（非独立 `.vue` 文件，保持单文件组件惯例以避免小程序分包体积膨胀）。

选择理由：
- 与现有代码库模式一致（当前 `index.vue` 已使用 `useAuthStore`、`useOwnerStore`、`PagePoller`、computed 聚合）
- uni-app mp-weixin 构建对嵌套组件支持良好，但深层组件树增加编译产物体积
- 本页面逻辑自包含，无需被其他页面复用子组件
- 遵循 C-04 零后端改动、C-05 不改变其他页面

---

## 2. 架构决策记录（ADRs）

---

### ADR-BD-01：数据获取与状态管理模式

- **Status**: Accepted
- **Context**: 
  舰桥页面需要聚合来自 6 个不同 API 端点的数据（REQ-FUNC-001~003、005、007~009），且需支持 30 秒周期性刷新（REQ-FUNC-009）、多座舱切换（REQ-FUNC-005）、以及单 API 失败的容错降级（REQ-FUNC-011、REQ-NFUNC-005）。现有 `useOwnerStore`（Pinia）已管理 bindings/structure/realtime 数据的缓存，但其缓存 TTL 为 60s~30 天不等，与舰桥 30 秒刷新周期的需求有差距。现有 `PagePoller` 是一个简单的 interval 封装。

- **Options**:
  - **Option A: 页面级 Composable（useBridgeDashboard）**
    - 描述：新建 `miniprogram/composables/useBridgeDashboard.js`，封装所有仪表盘数据获取、状态聚合、轮询启停逻辑。返回 reactive 状态对象供模板直接使用。利用 `useOwnerStore` 的缓存优先策略（ensureBindings/ensureStructure 的 allowStale 模式）加速首屏，同时直接调用 API（绕过 Store 缓存）进行周期性刷新。
    - 优点：关注点分离清晰；composable 可脱离页面独立测试；不影响现有 Store 的缓存策略；与现有 `index.vue` 中 `loadOwnerHome()` 函数的模式演进一致。
    - 缺点：引入新文件（`composables/`）；需处理多座舱切换时的状态重置。
  - **Option B: 扩展 useOwnerStore（Pinia Store 扩展）**
    - 描述：在 `store/owner.js` 中新增 dashboard-specific 状态字段（如 `dashboardFaultSummary`、`dashboardPlcOnlineRate`），利用 Pinia 的响应式体系管理所有仪表盘数据。
    - 优点：全局状态，多页面可共享（如果未来其他页面需要仪表盘数据）。
    - 缺点：Store 职责膨胀——owner.js 已管理 bindings/structure/realtime/config 四类数据，再加入 dashboard 数据使其边界模糊；舰桥数据的高频刷新（30s）与 Store 的长 TTL 缓存策略冲突；多座舱切换时需要复杂的 Store 状态清理逻辑。
  - **Option C: 页面内联（无抽象）**
    - 描述：所有数据获取逻辑写在 `index.vue` 的 `<script setup>` 中，使用 `ref`/`reactive` 管理状态。
    - 优点：零新增文件；与当前 `index.vue` 模式完全一致。
    - 缺点：`<script setup>` 将超过 400 行（现有已达 300 行）；数据逻辑与模板耦合，难以测试；复用性为零。

- **Decision**: 选择 **Option A（页面级 Composable）**。
  理由：
  - REQ-FUNC-009 要求 30s 轮询刷新，Option A 可在 composable 内封装 poller 生命周期（onShow 启动、onHide 停止），模板代码保持简洁。
  - REQ-FUNC-005 要求多座舱切换时刷新数据——composable 可接受 `specificPart` 参数，切换时重新执行 fetch，比修改全局 Pinia Store 更安全。
  - REQ-NFUNC-005 要求单 API 失败容错——composable 使用 `Promise.allSettled` + 独立错误状态字段，粒度比 Store 级别更细。
  - C-05 约束不改变其他页面——Option A 是纯增量，Option B 修改共享 Store 可能有副作用。

- **Consequences**:
  - 正向：新增 `miniprogram/composables/useBridgeDashboard.js`（约 150-200 行），职责单一，可独立进行逻辑测试。页面 `index.vue` 的 `<script setup>` 保持精简（约 50-80 行编排代码）。
  - 负向：引入 `composables/` 目录新模式（现有代码库无此目录）；需确保 composable 内的 `onShow`/`onHide` 生命周期钩子在页面上下文中正确工作（uni-app 的 `onShow` 仅在页面级组件中可用，composable 中调用需从页面传入或使用 `getCurrentInstance`）。

---

### ADR-BD-02：故障状态聚合管道

- **Status**: Accepted
- **Context**:
  舰桥页面需要从多个数据源聚合故障/预警状态（REQ-FUNC-001~003、007~008）：
  - 子系统隔舱：`/api/dashboard/device-fault-summary/`（四类设备故障计数）+ `/api/dashboard/plc-online-rate/`（能耗子系统 PLC 在线率）
  - 房间隔舱：`/api/miniapp/owner/structure/`（房间结构）+ `/api/devices/fault-events/`（活跃故障事件，按 room_name 分组）+ `/api/devices/condensation-warning-events/`（结露预警）
  - 整体健康：所有子系统+房间状态的聚合
  - 能耗子系统：PLC 在线率 + FaultEvent 中能效相关记录过滤（OQ-01 方案 A）

  现有 `arkZoneMap.js` 提供了 `attrSeverity()` 和 `worseStatus()` 两个纯函数，用于从 MQTT 实时属性判定故障严重度，状态等级定义为 `{ idle: -1, normal: 0, warning: 1, fault: 2 }`（STATUS_RANK）。但舰桥的数据源是 HTTP API 的 FaultEvent（含 `severity` 字段：error→fault, warning→warning），与 MQTT attr 的判定逻辑路径不同。

- **Options**:
  - **Option A: 新建 composable 内纯函数聚合管道**
    - 描述：在 `useBridgeDashboard` 中定义纯函数聚合管道：`aggregateSubsystemStatus(faultSummary, plcRate)` → subsystem 状态列表；`aggregateRoomStatus(structure, faultEvents, condensationEvents)` → room 状态列表；`computeOverallStatus(subsystems, rooms)` → 四级状态。复用 `arkZoneMap.js` 的 `worseStatus` 和 `STATUS_RANK`。
    - 优点：纯函数可独立单测；不引入新依赖；管道步骤清晰（数据获取→按维度分组→逐级聚合→最终状态）。
    - 缺点：需从 FaultEvent 的 `severity` 字段（"error"/"warning"）映射到内部状态模型（fault/warning），需额外映射层。
  - **Option B: 后端聚合（新增 API）**
    - 描述：新增一个 `/api/dashboard/bridge-summary/` 端点，后端完成所有聚合逻辑，前端仅渲染。
    - 优点：前端极简；聚合逻辑集中。
    - 缺点：**违反 C-04 零后端改动**，直接否决。
  - **Option C: 扩展 arkZoneMap.js 工具函数**
    - 描述：在 `arkZoneMap.js` 中新增 `aggregateFaultEvents()`、`computeCompartmentStatus()` 等导出函数。
    - 优点：复用现有模块。
    - 缺点：`arkZoneMap.js` 是为 MQTT 实时流（DeviceStatusUpdate attrs）设计的故障判定模块，其核心逻辑（`isFaultActive`、`attrSeverity`）依赖于 MQTT 属性命名约定（如 `error_N`、`comm_fault_timeout`）。HTTP API 的 FaultEvent 模型完全不同（有 `severity`、`fault_type`、`is_active` 字段），强行混入会导致模块职责混乱。

- **Decision**: 选择 **Option A（Composable 内纯函数聚合管道）**。
  理由：
  - REQ-FUNC-001 定义的四级判定规则（任何 error→告警，否则 warning→预警，否则 normal→正常）在 composable 中以纯函数实现最为直接。
  - REQ-FUNC-007 的结露预警双层级展示（独立角标 + 房间隔舱融合）需要在管道中并行计算两个输出，纯函数管道可以精确控制计算路径。
  - REQ-FUNC-002 的能耗子系统需要前端推导（OQ-01 方案 A），纯函数管道易于扩展过滤逻辑。
  - C-04 禁止后端改动。
  - 仅复用 `arkZoneMap.js` 的两个基础工具（`worseStatus`、`STATUS_RANK`），不修改其核心逻辑。

- **Consequences**:
  - 正向：聚合逻辑集中在 composable 中的 4-5 个纯函数，每个函数 10-30 行，可独立单测。状态判定规则与 REQ-FUNC-001~003 的定义一对一可追溯。
  - 负向：FaultEvent.severity 的 "error"→"fault" 映射是一次性的约定，若后端修改 severity 枚举值，前端需同步更新映射（风险低——severity 是后端 `fault_classifier.py` 的稳定输出）。

---

### ADR-BD-03：战舰透视图的视觉渲染方案

- **Status**: Accepted
- **Context**:
  REQ-FUNC-004 要求呈现"2D 赛博朋克风格太空战舰 X 射线透视蓝图"，PM 已确认详细设计方向（I-05）：
  - 六段式布局：舰首标识 → 子系统 dock → 动力脊线 → 房间网格 → 舰尾引擎
  - 隔舱颜色编码：正常=青蓝色霓虹线 `#27f5b5`，预警=橙红闪烁 `#ffd400`，告警=红色损伤闪烁 `#ff315d`，待机=暗紫色弱光线
  - 赛博朋克视觉体系：背景 `#05070f`，主色 `#2ff4e0`/`#00e5ff`，紫色 `#7c3aed`，网格叠加、HUD 扫描线、动力流/引擎脉冲/损伤闪烁动画
  - 负向约束：禁止 3D 渲染、写实照片

  现有 `index.vue` 已实现六段式布局（`ship-shell` → `ship-nose` → `system-dock` → `ship-spine` → `room-grid` → `ship-tail`）和全套 CSS 动画（`ownerScan`、`pulseSoft`、`powerFlow`、`fanSpin`、`damageBlink`、`enginePulse`），但隔舱造型相对简陋（简单的 clip-path 多边形），且子系统和房间隔舱各仅显示温度数值而不含故障计数。

- **Options**:
  - **Option A: Vue 模板 + Scoped CSS（扩展现有模式）**
    - 描述：继续使用现有 `index.vue` 的模板+CSS 模式，扩展隔舱的 clip-path 多边形造型、增加故障计数标注、复用全部 `@keyframes` 动画、增加隔舱 @tap 事件绑定。子系统 dock 从 2-4 个通用模块扩展为 4 个命名隔舱。房间网格从 clip-path 异形多边形升级为更精细的赛博朋克舱室轮廓。
    - 优点：与现有代码 100% 兼容；所有 CSS 动画直接复用（REQ-NFUNC-001 约束）；uni-app 模板渲染在小程序中性能优异（无 Canvas/WebGL 开销）；开发效率高。
    - 缺点：纯 CSS clip-path 造型表达能力有限，无法实现复杂的管线连接线和舱室拓扑；大面积 clip-path 在低端设备上可能有合成性能问题。
  - **Option B: Canvas 2D 绘制**
    - 描述：使用 `<canvas>` 元素，通过 JavaScript 2D API 绘制整艘战舰透视图——包括舱室轮廓、管线连接、霓虹发光、动画。
    - 优点：绘制自由度极高，可实现复杂管线拓扑和舱室连接；动画帧率可控。
    - 缺点：开发成本高（估计 300+ 行 Canvas 绘制代码）；微信小程序中 Canvas 接口与 Web 标准有差异（需使用 uni-app 封装层）；CSS 动画无法复用（REQ-NFUNC-001 要求复用现有动画）；响应式布局困难；触摸事件需自行实现 hit-test；与现有模板驱动模式割裂。
  - **Option C: SVG 内联**
    - 描述：使用内联 SVG 元素绘制战舰透视图。
    - 优点：矢量缩放，清晰度好；CSS 可控制部分 SVG 属性。
    - 缺点：微信小程序 WXML 不渲染内联 SVG（仅支持 `<image src="data:image/svg+xml,...">` 间接引用）；间接引用的 SVG 无法用 CSS 动态改变颜色/动画；与现有模式完全不兼容。

- **Decision**: 选择 **Option A（Vue 模板 + Scoped CSS，扩展现有模式）**。
  理由：
  - REQ-NFUNC-001 是 Must Have 优先级，明确要求"复用现有 `@keyframes` 定义"，Option A 是唯一可直接复用现有 6 个 `@keyframes` 的方案。
  - 现有 `index.vue` 已证明 clip-path + CSS 动画 + 模板绑定方案在小程序中运行良好（约 700 行 CSS，动画流畅）。
  - 开发效率最高——基于现有代码扩展而非重写，符合 "基于现有业主战舰视图六段式布局扩展重构"（OQ-04 方案 A）。
  - 隔舱点击交互（REQ-FUNC-006）在模板中只需 `@tap` 绑定，Canvas 方案需自行实现 hit-test。

- **Consequences**:
  - 正向：开发周期短（模板+CSS 扩展为主）；所有 6 个现有动画直接复用；模板响应式绑定（`:class` 动态状态类）与现有模式一致。
  - 负向：clip-path 造型有一定局限——管线连接路由、复杂舱室轮廓需通过多层伪元素和 border 技巧模拟，CSS 复杂度可能增加 200-300 行；低端设备上多个 clip-path + box-shadow 叠加可能触发合成层过多，需在真机测试中验证性能（REQ-NFUNC-004 要求损伤闪烁 ≤3 次/秒，已满足）。
  - 风险缓解：若真机性能不满足 REQ-NFUNC-002 目标（300ms 视觉更新），可通过减少 box-shadow 叠加层数或使用 will-change 优化合成来降级。

---

### ADR-BD-04：隔舱点击交互——故障详情展示

- **Status**: Accepted
- **Context**:
  REQ-FUNC-006 要求点击任意子系统隔舱或房间隔舱时展示该隔舱对应的活跃故障/预警列表。PM 已确认 I-02 方案 A：半屏弹出抽屉（赛博朋克风格）。

  交互需求包括：半屏高度、深色半透明背景+青色发光边框、列表项带状态色左边框（红=故障/黄=预警）、底部关闭手柄、支持下拉关闭/点击遮罩关闭/返回手势关闭。正常隔舱点击展示"运行正常"提示。

  现有 `index.vue` 中隔舱点击仅有 `uni.showToast` 占位（`openRoom`/`openModule`），无实际抽屉组件。

- **Options**:
  - **Option A: 自定义 uni-app popup 组件（内联在 index.vue 中）**
    - 描述：在 `index.vue` 内使用 `v-if` 控制的条件渲染 + `<view>` 实现半屏抽屉。遮罩层固定定位覆盖全屏，抽屉面板从底部滑入（`transform: translateY` + `transition`）。列表使用 `scroll-view` 渲染 FaultEvent 数据。
    - 优点：完全控制样式（赛博朋克主题），无需依赖第三方 UI 库；与页面状态共享（直接访问 composable 中的 faultEvents 数据）；动画可用 CSS transition 实现，与现有动画体系一致。
    - 缺点：小程序中 `fixed` 定位在 scroll-view 嵌套场景下可能有层级问题；需自行处理手势关闭（`@touchmove` 监听滑动距离）。
  - **Option B: uni-ui `<uni-popup>` 组件**
    - 描述：引入 `@dcloudio/uni-ui` 的 `<uni-popup>` 组件，配置为 bottom 模式。
    - 优点：手势关闭、遮罩点击关闭已内置；兼容性好。
    - 缺点：引入额外 npm 依赖；默认样式为 Material Design 风格，需大量覆盖样式以匹配赛博朋克主题；uni-ui 的 popup 组件对半屏高度的控制可能不够精细。
  - **Option C: 导航到独立子页面**
    - 描述：点击隔舱后 `uni.navigateTo` 到一个新页面展示故障列表。
    - 优点：小程序原生页面转场动画；无需处理层级问题。
    - 缺点：打断了舰桥页面的沉浸式体验（用户离开了战舰透视图）；多隔舱快速切换时页面栈膨胀；不符合 PM 确认的半屏抽屉方案（I-02）。

- **Decision**: 选择 **Option A（自定义内联半屏抽屉）**。
  理由：
  - REQ-NFUNC-001 要求赛博朋克视觉一致性——自定义组件可精确使用现有色板和发光效果（`#2ff4e0` 边框、`box-shadow` 发光、`rgba(6,12,28,0.92)` 背景），无需覆盖第三方样式。
  - PM 确认 I-02 为"半屏弹出抽屉"——Option A 直接实现此交互，Option C 是全页面导航而非抽屉。
  - C-05 约束不改变其他页面——自包含在 `index.vue` 中，零外部影响。
  - 小程序中自定义 popup 是常见模式，ArkTabBar 已使用类似的 `fixed` 定位方案，有先例可循。

- **Consequences**:
  - 正向：抽屉样式与舰桥赛博朋克主题完美融合；可复用 `damageBlink` 动画于故障列表项；抽屉数据来自同一 composable，零额外数据请求。
  - 负向：需实现手势关闭逻辑（`touchstart`/`touchmove`/`touchend`）和关闭动画；`fixed` 定位在 iOS 小程序中可能有安全区域适配问题（需 `padding-bottom: env(safe-area-inset-bottom)`）。
  - 风险缓解：若 `fixed` 定位在 scroll-view 内失效，改用页面级 `position: absolute` + `z-index` 覆盖方案；参考 ArkTabBar 的安全区域适配模式。

---

### ADR-BD-05：PLC 在线状态集成方式

- **Status**: Accepted
- **Context**:
  REQ-FUNC-008 要求 PLC 在线状态作为独立指示器展示，不与整体健康度融合。PM 确认 I-04：独立指示器。
  
  数据来源：`/api/dashboard/plc-online-rate/`（返回 `{online_count, offline_count, total_count, rate}`）。
  状态判定：全部在线→正常（青蓝）；部分离线→预警（橙红闪烁）；全部离线→告警（红色）。

  现有 `index.vue` 的 admin 路径已有 PLC 在线率展示（`MetricCard` 组件 + `plcText` computed），但 owner 路径未使用 PLC 数据。

- **Options**:
  - **Option A: 独立 PLC 通讯链路状态条**
    - 描述：在战舰透视图的舰尾引擎区上方或侧边，添加一个独立的横向状态条（如"通讯链路"标签 + LED 状态灯 + 在线/离线计数）。样式与赛博朋克主题一致（青线边框、发光 LED）。
    - 优点：视觉上与隔舱体系明确分离（独立位置、独立造型）；符合 PM 确认的"独立指示器"要求；复用现有 API 和数据结构。
    - 缺点：舰尾区域空间有限，需在 layout 中精确规划位置。
  - **Option B: PLC 状态融入舰船引擎动画**
    - 描述：将 PLC 在线率映射为舰尾引擎的发光强度或脉冲频率——全部在线时引擎全亮青蓝脉冲，部分离线时脉冲变橙红且减弱，全部离线时引擎熄灭变红。
    - 优点：创意化展示，符合战舰主题。
    - 缺点：**模糊了"独立指示器"的要求**——将 PLC 状态与引擎动画耦合，用户难以区分"PLC 离线"与"引擎装饰效果"；违反 PM 确认的 I-04 独立性原则。
  - **Option C: 顶部 header 旁独立 LED 面板**
    - 描述：在页面顶部 `owner-header` 区域（健康指示器旁），增加一个小型 LED 面板显示 PLC 在线状态。
    - 优点：位置醒目，与整体健康指示器同级可见性；复用现有 header 布局。
    - 缺点：header 区域已有标题和健康指示器，再加 PLC 面板可能拥挤；与隔舱体系的视觉分离不如 Option A 明显。

- **Decision**: 选择 **Option A（独立 PLC 通讯链路状态条）**，位置定于舰尾引擎区与 ArkTabBar 之间。
  理由：
  - PM 确认 I-04 为独立指示器——Option A 在布局上与其他隔舱明确分离，用独立的水平状态条呈现。
  - REQ-FUNC-004 描述的布局中 PLC 指示器位于"舰尾引擎区之下的独立元素"，Option A 的舰尾下方位置与此一致。
  - 视觉区分度最高——"通讯链路"标签 + 青/黄/红 LED + "3/5 在线"文字，一眼可辨非隔舱元素。

- **Consequences**:
  - 正向：PLC 状态一目了然，不与隔舱颜色编码混淆；数据独立获取，PLC API 失败不影响其他隔舱。
  - 负向：舰尾下方新增 UI 元素，需在 scroll-view 底部预留空间；若未来 PLC 数量增长（如 >10 台），文字计数可能不够直观——当前生产环境 PLC 总数约 5 台，空间充足。

---

### ADR-BD-06：能耗子系统数据推导策略

- **Status**: Accepted
- **Context**:
  REQ-FUNC-002 要求能耗设备子系统隔舱展示故障/预警状态。与其他三个子系统（新风/水力/空气品质）不同，能耗子系统的数据来源并非单一的 `device-fault-summary` 分类——`/api/dashboard/device-fault-summary/` 的四类设备（fresh_air_unit, hydraulic_module, air_quality_sensor, other_devices）中不包含独立的"能耗"分类。

  PM 已确认 OQ-01 方案 A：舰桥层面推导——PLC 在线率作为能耗子系统的基础状态，同时过滤 FaultEvent 中与能源计量相关的记录（按 device_name 或 device_type_label 匹配），聚合为能耗子系统状态。

- **Options**:
  - **Option A: 前端纯推导（PM 已确认）**
    - 描述：调用 `/api/dashboard/plc-online-rate/` 获取计量 PLC 在线状态 + `/api/devices/fault-events/` 获取活跃故障事件并过滤能效相关记录（匹配 `device_type_label` 包含"能量"/"计量"/"能源"或 `product_code` 为 250001 等能量计品类）。
    - 优点：PM 已确认；零后端改动（C-04）；推导逻辑透明可审计。
    - 缺点：依赖 FaultEvent 数据中的 `device_type_label` 稳定性——若后端修改标签文本，前端过滤规则可能失效；PLC 在线率代理能耗状态存在语义偏差（PLC 在线但能耗设备可能无故障）。
  - **Option B: 请求后端新增分类**
    - 描述：请求后端在 `device-fault-summary` 中新增 `energy_devices` 分类。
    - 优点：数据精确；前端代码简洁。
    - 缺点：**违反 C-04 零后端改动**。
  - **Option C: 能耗子系统只展示 PLC 在线率，不聚合故障事件**
    - 描述：能耗隔舱仅基于 PLC 在线率着色（全部在线=正常、部分离线=预警、全部离线=告警），不显示故障计数。
    - 优点：实现极简；无过滤规则维护成本。
    - 缺点：丢失了能效设备的具体故障信息——用户无法知道"为什么能耗状态异常"。

- **Decision**: 选择 **Option A（前端纯推导）**。
  理由：
  - PM 已确认 OQ-01，不需重新争议。
  - C-04 约束强制零后端改动。
  - 实现为 composable 中一个纯函数 `deriveEnergyStatus(plcRate, faultEvents)`，过滤条件设计为可配置的关键词列表（如 `['能量', '计量', '能源', 'energy', 'meter']`），降低 `device_type_label` 变化的脆弱性。

- **Consequences**:
  - 正向：零后端改动，符合 C-04；推导逻辑在 composable 中自包含，易于调整和测试。
  - 负向：过滤规则基于文本匹配，存在误匹配或漏匹配风险。建议在开发阶段通过 console.debug 输出过滤结果，便于调试；若 PM 发现数据不准确，后续可微调关键词列表。
  - [ASSUMPTION — requires PM confirmation]：假设当前生产环境中与能耗相关的 FaultEvent 的 `device_type_label` 或 `device_name` 中包含可识别关键词（如"能量计"），且此约定在可预见的未来保持稳定。

---

### ADR-BD-07：组件层级——子组件拆分策略

- **Status**: Accepted
- **Context**:
  模板中需要渲染约 10 个视觉区域（舰首、4 子系统隔舱、动力脊线、5 房间隔舱、舰尾引擎、PLC 指示器、健康指示器、座舱切换器、结露角标、故障抽屉、加载/空态/错误态）。全部内联在 `index.vue` 中将使模板超过 300 行。同时 REQ-NFUNC-004 要求所有可点击隔舱 ≥44x44 逻辑像素。

  需要决定哪些视觉元素拆分为独立组件，哪些保持内联。

- **Options**:
  - **Option A: 适度拆分——仅对可复用/复杂元素抽取组件**
    - 描述：抽取 5 个独立 `.vue` 组件：`ShipHull.vue`（战舰外壳容器+背景）、`SubsystemCompartment.vue`（子系统隔舱，v-for 复用）、`RoomCompartment.vue`（房间隔舱，v-for 复用）、`FaultDrawer.vue`（故障抽屉）、`HealthIndicator.vue`（健康指示器）。其余元素（舰首铭牌、动力脊线、舰尾引擎、PLC 状态条、座舱切换器、结露角标、加载/空态/错误态）保持内联。
    - 优点：将重复的 v-for 渲染项（子系统隔舱/房间隔舱）抽出为组件，模板更清晰；每个组件的样式自包含，CSS 不会相互污染（scoped）；可独立修改隔舱造型而不影响其他元素。
    - 缺点：组件间通信需要 props/emits 传递——隔舱点击事件需 emit 到页面再传给 FaultDrawer；增加编译产物体积。
  - **Option B: 全内联（零组件拆分）**
    - 描述：所有模板代码写在 `index.vue` 中，使用条件渲染和 v-for。
    - 优点：数据流最简（composable → 模板，无 props/emits）；零额外文件；编译产物最优。
    - 缺点：模板 >400 行难以维护；CSS scoped 全部在一个文件，选择器可能冲突；测试困难。
  - **Option C: 细粒度组件化（8+ 组件）**
    - 描述：为每个视觉区域创建独立组件（ShipNose, ShipSpine, ShipTail, PlcStatusBar, CabinSwitcher, CondensationBadge 等）。
    - 优点：每个组件极简（<50 行）；高度解耦。
    - 缺点：组件间通信链路过长（页面 → 多层 props → 深层 emits）；大量小组件增加编译产物体积（每个 `.vue` 文件编译为 wxml/wxss/js 各一份）；小程序分包有文件数限制。

- **Decision**: 选择 **Option A（适度拆分——5 个组件）**。
  理由：
  - REQ-FUNC-002 和 REQ-FUNC-003 有 4 个子系统隔舱和 5 个房间隔舱需通过 v-for 渲染，抽取 `SubsystemCompartment.vue` 和 `RoomCompartment.vue` 消除重复代码。
  - REQ-FUNC-006 的故障抽屉逻辑复杂（列表渲染、事件绑定、手势关闭），独立组件便于维护。
  - `ShipHull.vue` 封装战舰外壳容器（背景网格、HUD 扫描线），将 150+ 行装饰 CSS 隔离。
  - `HealthIndicator.vue` 封装四级状态菱形 LED 渲染逻辑。
  - 其余简单元素（舰首铭牌、动力脊线等）保持内联，避免过度拆分。

- **Consequences**:
  - 正向：组件边界清晰，每个组件 < 120 行；隔舱样式修改不波及其他元素；`FaultDrawer` 和 `SubsystemCompartment` 可独立进行交互测试。
  - 负向：需定义 props/emits 接口（见 module_design.md）；5 个新组件增加约 8KB 编译产物（小程序主包有 2MB 限制，当前远未触及）。

---

### ADR-BD-08：轮询与动画生命周期管理

- **Status**: Accepted
- **Context**:
  REQ-FUNC-009 要求 30 秒自动轮询 + 下拉手动刷新。REQ-NFUNC-002 要求页面不可见时停止轮询和 CSS 动画以节省资源。

  现有 `PagePoller` 仅管理 `setInterval`，不感知页面可见性。现有 `index.vue` 在 `onHide` 中调用 `poller.stop()`，但在 `onShow` 中需手动重启。CSS 动画（6 个 `@keyframes`）通过 `animation` 属性持续运行，不在任何生命周期中控制。

- **Options**:
  - **Option A: Composables 内封装生命周期管理**
    - 描述：在 `useBridgeDashboard` composable 中，接受 `onShow`/`onHide` 回调参数，内部管理 PagePoller 的启停。新增 `useAnimationControl` composable 用于管理 CSS 动画的暂停/恢复（通过动态添加/移除 class）。
    - 优点：页面仅需传入生命周期回调，composable 封装所有轮询/动画逻辑；符合 Vue 3 Composition API 最佳实践。
    - 缺点：CSS 动画的暂停在小程序中需通过条件 class 切换实现（`animation-play-state: paused` 在部分微信版本中不可靠）。
  - **Option B: 页面内联管理（现有模式）**
    - 描述：在 `index.vue` 的 `onShow` 中手动启动 poller，`onHide` 中停止。动画不加控制。
    - 优点：与现有代码 100% 一致。
    - 缺点：无法实现 REQ-NFUNC-002 的"停止 CSS 动画以节省资源"要求。
  - **Option C: 使用 `uni.onAppShow` / `uni.onAppHide` 全局管理**
    - 描述：在 App.vue 级别监听应用前后台切换，通过全局事件总线通知各页面暂停/恢复。
    - 优点：全局统一管理。
    - 缺点：过度设计——舰桥是唯一需要此逻辑的页面；全局事件总线引入隐式耦合。

- **Decision**: 选择 **Option A（Composables 内封装）**，CSS 动画通过动态 class 控制。
  理由：
  - REQ-NFUNC-002 要求"停止全部轮询和 CSS 动画以节省资源"——Option A 是唯一满足此要求的方案。
  - 实现方式：模板根元素绑定 `:class="{ 'animations-paused': !isPageVisible }"`，CSS 规则 `.animations-paused * { animation-play-state: paused !important; }` 全局暂停动画。PagePoller 在 `onShow` 回调中 `start()`，`onHide` 回调中 `stop()`。
  - composable 封装后，页面代码保持简洁。

- **Consequences**:
  - 正向：节省电池和 CPU——后台时全页面动画冻结，前台上恢复；页面不可见时 API 请求停止，减少服务端负载。
  - 负向：`animation-play-state: paused` 在微信小程序部分旧版本（<8.0.0）中支持不完善——若真机测试发现不生效，降级方案为：后台时移除动画 class（而非暂停），前台时重新添加（动画会从头播放，视觉上可接受）。

---

## 3. 组件树

```
pages/home/index.vue (重写后 — owner 路径)
├── <view class="owner-page">                              [页面根容器]
│   ├── <view class="bg-base" />                           [背景渐变]
│   ├── <view class="bg-grid" />                           [网格叠加]
│   ├── <view class="hud-scan" />                          [HUD 扫描线]
│   ├── <view class="status-spacer" />                     [状态栏占位]
│   ├── <view class="owner-header">                        [顶部标题栏]
│   │   ├── <view class="owner-title-box">                 [标题+副标题]
│   │   ├── <HealthIndicator :status :condensationCount /> [整体健康指示器]
│   │   └── <CondensationBadge :count />                   [结露预警计数角标]
│   ├── <CabinSwitcher :bindings :selected @change />      [多座舱切换器]
│   ├── <view class="owner-tip" v-if="loading" />          [加载态]
│   ├── <view class="owner-empty" v-if="!bindings" />      [空态—未链接座舱]
│   ├── <view class="owner-error" v-if="error" />          [错误横幅]
│   ├── <ShipHull :status>                                 [战舰外壳容器]
│   │   ├── <view class="ship-nose">FREEARK</view>         [舰首铭牌]
│   │   ├── <view class="system-dock">                     [子系统隔舱区]
│   │   │   └── <SubsystemCompartment v-for />             [子系统隔舱×4]
│   │   ├── <view class="ship-spine" />                    [动力脊线+能量流]
│   │   ├── <view class="room-grid">                       [房间网格区]
│   │   │   └── <RoomCompartment v-for />                  [房间隔舱×5]
│   │   └── <view class="ship-tail" />                     [舰尾引擎×2]
│   └── <PlcIndicator :onlineCount :totalCount />          [PLC 独立指示器]
│   └── <FaultDrawer v-if :compartment @close />           [故障抽屉]
│   └── <ArkTabBar active="home" />                        [底栏—现有]
```

## 4. 数据流图

```
useBridgeDashboard(sp) Composable
│
├─ state (reactive):
│   loading: Boolean
│   error: String
│   bindings: Array
│   selectedSp: String
│   overallStatus: { level: 'normal'|'warning'|'fault'|'syncing', text: String }
│   subsystems: Array<{ id, name, status, faultCount, productCode }>
│   rooms: Array<{ id, name, status, faultCount, warningCount }>
│   plcOnline: Number, plcTotal: Number
│   condensationCount: Number
│   activeCompartment: Object | null  // 当前打开的隔舱，用于 FaultDrawer
│   isPageVisible: Boolean
│
├─ actions:
│   start()              → 拉取初始数据 + 启动轮询
│   stop()               → 停止轮询
│   refresh(force)       → 手动刷新（下拉调用）
│   switchCockpit(sp)    → 切换座舱
│   openCompartment(c)   → 打开隔舱抽屉
│   closeCompartment()   → 关闭隔舱抽屉
│
├─ internal:
│   fetchAll()           → Promise.allSettled(6 APIs)
│   aggregateStatus()    → 纯函数管道
│   poller: PagePoller   → 30s 间隔
│
└─ 输出 → 模板直接绑定 reactive state
```

## 5. 数据源到隔舱的映射

| 隔舱 | 数据源 API | 状态判定 |
|------|-----------|---------|
| 整体健康 | 全部 API 聚合 | 任何 error→fault；否则 warning→warning；否则 normal→normal；加载中→syncing |
| 新风隔舱 | `device-fault-summary.fresh_air_unit` | fault_count>0 → fault；否则 → normal |
| 能耗隔舱 | `plc-online-rate` + `fault-events` 过滤 | PLC 离线或故障匹配 → warning/fault；否则 → normal |
| 水力隔舱 | `device-fault-summary.hydraulic_module` | fault_count>0 → fault；否则 → normal |
| 空气品质隔舱 | `device-fault-summary.air_quality_sensor` | fault_count>0 → fault；否则 → normal |
| 房间隔舱×N | `owner/structure` + `fault-events`（按 room_name） + `condensation-warning-events` | 该房间任何 error→fault；否则 warning/结露→warning；否则 → normal |
| PLC 指示器 | `plc-online-rate` | 全部在线→normal；部分→warning；全离→fault |
| 结露角标 | `condensation-warning-events.count` | count>0 → 显示黄色 Badge |

## 6. 开放问题

- [ASSUMPTION — ADR-BD-06]：能耗子系统的前端过滤依赖于 FaultEvent 的 `device_type_label` 或 `device_name` 字段中包含可识别关键词（如"能量"、"计量"）。此假设需 PM 确认生产环境中相关设备的标签命名约定。
- [ASSUMPTION — ADR-BD-08]：`animation-play-state: paused` 在微信小程序中可通过条件 class 切换生效。若真机测试不通过，降级为移除/重新添加动画 class 方案。
- [ASSUMPTION — requires PM confirmation]：现有 `ownerStore.ensureBindings()` 和 `ownerStore.ensureStructure()` 的缓存策略（TTL 5min/30day）在舰桥 30s 轮询场景下不会产生数据不一致——轮询路径将直接调用 API 绕过 Store 缓存，首屏加载仍使用 Store 缓存加速。
