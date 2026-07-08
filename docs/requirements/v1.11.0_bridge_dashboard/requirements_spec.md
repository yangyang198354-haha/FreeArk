# 需求规格说明书

**版本**：v1.11.0_bridge_dashboard
**日期**：2026-07-08
**状态**：CONFIRMED（全部 9 项已闭环）
**作者**：sub_agent_requirement_analyst
**PM 确认**：Yang Yang, 2026-07-08
**上游任务**：重写微信小程序"舰桥"（Bridge）页面为赛博朋克风格仪表盘，仅显示各子系统和房间的警告与故障状态

---

## 1. 背景与范围

### 1.1 背景

FreeArk 微信小程序当前首页（`pages/home/index`）即为"舰桥"页面，存在两套视觉体系：业主（role=user）使用赛博朋克战舰主题户型俯视图，管理员/运维（admin/operator）使用传统 Material Design 仪表盘（白卡片+蓝色头+灰色底）。用户要求将舰桥页面**重写为纯 user 视角的赛博朋克风格仪表盘**，且**只关注警告和故障，不显示其他运行参数**。admin/operator 角色不在本需求范围内（PM 确认：P0 仅 user）。

_来源引用：用户需求原文："重写微信小程序（miniprogram/）的'舰桥'（Bridge）页面"、"舰桥页面和整个微信小程序保持赛博朋克（Cyberpunk）UI 风格一致"、"只关注警告和故障，不显示其他参数"。_

现有已知事实（来自 PM 提供的代码探索）：
- 小程序框架：uni-app（Vue 3 Composition API），构建目标 mp-weixin
- 赛博朋克视觉体系已建立：色板（背景 `#05070f`，主色 `#2ff4e0`/`#00e5ff`，紫色 `#7c3aed`，状态绿 `#27f5b5`、黄 `#ffd400`、红 `#ff315d`）、背景网格、HUD 扫描线、动力流/引擎脉冲/损伤闪烁动画、clip-path 多边形造型
- 后端已提供相关 API：故障汇总、设备分类故障汇总、PLC 在线率、故障事件列表、结露预警事件
- 业主端另有骨架结构接口和实时参数接口（KB: KE-REQ-004）

_来源引用：PM 代码探索 §1-§4。_

### 1.2 范围

**本版本包含：**
- 舰桥页面统一为赛博朋克风格 2D 战舰透视图仪表盘，**仅覆盖 owner（role=user）角色**
- 以下子系统的故障/警告状态展示：新风模块（fresh_air_unit）、能耗相关设备（energy）、水力模块（hydraulic_module）、空气品质传感器（air_quality_sensor）
- 各房间的设备故障/警告状态展示
- 子系统隔舱和房间隔舱的颜色编码（正常=青蓝色霓虹线，预警=橙红色闪烁线，待机=暗紫色弱光线）
- 整体舰船健康状态摘要指示（菱形 LED 四级状态）
- PLC 在线状态独立指示器（PM 确认：I-04）
- 隔舱点击查看故障详情的交互
- 业主多座舱切换（PM 确认：user 支持多座舱切换）
- 数据周期性刷新（30 秒间隔，PM 确认：I-01）与手动下拉刷新
- 容错降级处理（API 失败不白屏）

**本版本明确不包含：**
- 温度、湿度、能耗数值（kWh）等任何运行参数的显示
- admin/operator 角色的舰桥视图（PM 确认：P0 仅 user）
- web 端任何行为变更
- 后端新增 API（复用现有接口）
- 屏端 MQTT 协议交互
- ArkTabBar 或其他 tab 页面的改动
- 故障的创建/编辑/恢复操作（仅展示）

_来源引用：用户需求"只关注警告和故障，不显示其他参数"。_

### 1.3 关键约束

- **C-01 赛博朋克风格一致**：舰桥页面必须与小程序现有赛博朋克视觉体系保持一致（色板、字体、动画、装饰元素），沿用 ArkTabBar 底栏。_来源：用户需求"保持赛博朋克 UI 风格一致"。_
- **C-02 仅警告和故障**：页面不展示任何正常运行参数（温度值、kWh 值、湿度值、压力值等），仅展示故障/预警计数、受影响设备/房间、严重程度。正常状态隔舱以青色/绿色表示"无异常"。_来源：用户需求"只关注警告和故障"。_
- **C-03 角色数据隔离**：owner（role=user）仅可见其绑定 specific_part 的数据；通过业主专属 API（`/api/miniapp/owner/`）获取，受 IsOwnerUser 中间件鉴权保护。_来源：v1.8.0 业主隔离体系（KB: KE-REQ-004），PM 确认 P0 仅 user。_
- **C-04 零后端改动**：本需求的数据全部来自现有后端 API，不要求新增或修改后端接口。_来源：PM 任务范围约束。_
- **C-05 不改变其他页面**：ArkTabBar、聊天页、指挥页、副官页、舰长休息室页等保持原样。_来源：PM 任务范围约束。_

---

## 2. 现有系统关键事实（需求依据，已 Read/Grep 核实）

### 2.1 赛博朋克视觉体系

| 元素 | 色值/参数 |
|------|----------|
| 背景底色 | `#05070f`（深空黑蓝） |
| 主强调色（全息青） | `#2ff4e0` / `#00e5ff` |
| 紫色强调 | `#7c3aed` |
| 状态-正常（绿） | `#27f5b5` + glow `box-shadow: 0 0 14rpx #27f5b5` |
| 状态-预警（黄） | `#ffd400` + glow `box-shadow: 0 0 14rpx #ffd400` |
| 状态-告警（红） | `#ff315d` + glow `box-shadow: 0 0 16rpx rgba(255,49,93,0.9)` |
| 文字-亮白 | `#f4fbff`、`#eaf6ff`、`#cde7f7` |
| 文字-暗青 | `rgba(143,217,255,0.5)` |
| 边框 | `rgba(47,244,224,0.22)` |
| 值数字字体 | Orbitron/Menlo monospace |
| 装饰动画 | 80rpx 网格叠加（青线 opacity 0.06）、HUD 扫描线（5s 周期）、动力流（2.8s）、引擎脉冲（1.8s）、损伤闪烁（1.1-1.2s） |

_来源引用：PM 代码探索 §2；`pages/home/index.vue`（业主视图完整 CSS）。_

### 2.2 后端 API

| API 端点 | 返回关键字段 | 小程序 api.js 封装 |
|----------|-------------|-------------------|
| `GET /api/dashboard/fault-summary/` | `{active_fault_count, affected_unit_count}` | `getDashboardFaultSummary()` |
| `GET /api/dashboard/device-fault-summary/` | 四类设备各 `{total, fault_count}` | **未封装**（需新增调用） |
| `GET /api/dashboard/plc-online-rate/` | `{online_count, offline_count, total_count, rate}` | `getDashboardPlcOnlineRate()` |
| `GET /api/dashboard/summary/` | `{today_kwh, month_kwh, date, month}` | `getDashboardSummary()`（**本需求不使用**） |
| `GET /api/devices/fault-events/` | DRF 分页 `{results, count}`（FaultEvent 详情） | `getFaultEvents()` |
| `GET /api/devices/condensation-warning-events/` | DRF 分页结露预警列表 | `getCondensationEvents()` / `getCondensationWarningCount()` |
| `GET /api/miniapp/owner/structure/` | `{rooms, system_devices}` 设备树骨架 | `getOwnerStructure()` |
| `GET /api/miniapp/owner/realtime-params/` | 业主专属实时参数 | `getOwnerRealtimeParams()` |

_来源引用：PM 代码探索 §4；`miniprogram/utils/api.js`（全量 API 封装清单）；`views.py:1563-1606`（`dashboard_device_fault_summary` 实现）。_

> 注意：`/api/dashboard/device-fault-summary/` 后端已实现并测试通过，但小程序 `api.js` 未封装该调用。需在本次实现中新增对该接口的调用封装。

### 2.3 故障数据模型（FaultEvent）

关键字段：`specific_part`、`product_code`（如 130004/270001）、`fault_type`（comm/sensor/fresh_air/other_error）、`fault_message`、`severity`（error/warning）、`is_active`、`room_name`、`device_name`、`device_type_label`、`first_seen_at` / `last_seen_at` / `recovered_at`。

_来源引用：PM 代码探索 §5。_

### 2.4 设备品类（product_code 分组）

| 品类 | product_code | 用途 |
|------|-------------|------|
| 空气品质传感器 | `100007` | 监测 CO2/PM2.5 等 |
| 温控面板 | `120003`、`260001` | 房间温控（分室/主控） |
| 新风机组 | `130004` | 新风换气 |
| 水力模块 | `270001` | 集中供暖/制冷主机 |

_来源引用：PM 代码探索 §6；`views.py:1578-1583`。_

### 2.5 当前舰桥页面双视图现状

- **业主视图（role=user）**：赛博朋克战舰主题——`ship-shell`（clip-path 舰船轮廓）、`system-dock`（主机/风机/面板模块）、`ship-spine`（动力脊线+能量流动画）、`room-grid`（房间网格，房间 clip-path 异形隔舱）、损伤闪烁标记、温度数值显示（`temp-board` 和 `module-temp`）。_来源：`pages/home/index.vue:8-165`。_
- **管理员/运维视图（role!=user）**：Material Design 风格——白底 `#f5f5f5`、蓝色头 `#1a73e8`、MetricCard 指标卡（PLC 在线率、活跃故障数、结露预警数、今日 kWh）、快捷入口网格。**不遵循赛博朋克主题**。_来源：`pages/home/index.vue:167-259`。_
- **ArkTabBar**：4 tab（舰桥/指挥/副官/舰长休息室），深色半透明底+青顶线，active 态青发光 pill，SVG data-URI 图标。_来源：`components/ArkTabBar.vue`。_

---

## 3. 干系人与目标用户

| 角色 | 关注点 |
|------|--------|
| 业主（owner/user） | **唯一目标用户**（PM 确认：P0 仅 user）。查看自己绑定专有部分的房间和设备故障/预警状态，支持多座舱切换。不关注他人数据。 |

---

## 4. 功能性需求

### REQ-FUNC-001 整体舰船健康状态指示

**描述**：舰桥页面顶部展示一个整体健康状态指示器，聚合所有子系统和房间的最严重状态。判定规则：任何子系统或房间存在活跃故障（severity=error）→ 整体"告警"；否则任何子系统或房间存在预警（severity=warning 或活跃结露预警）→ 整体"预警"；全部正常（无活跃故障且无预警）→ 整体"正常"；数据加载中 → "同步中"。

指示器以菱形 LED + 文字标签呈现，颜色随状态变化（绿=正常、黄=预警、红=告警、灰=等待数据）。

**来源引用**：用户需求"通过仪表盘、图形、颜色显示'智能方舟座舱'各设备是否有错误、警告"；现有业主视图 `overallStatus` computed 四级状态逻辑（`pages/home/index.vue:350-359`）及 `owner-state` / `state-led` 视觉样式。

**优先级**：Must Have

**备注**：沿用现有 `state-{normal|warning|fault|idle}` 四级状态模型。

---

### REQ-FUNC-002 子系统隔舱状态展示

**描述**：2D 战舰透视图中，用独立隔舱表示以下子系统，各隔舱以颜色编码显示其最严重的故障状态，并标注活跃故障计数：

1. **新风模块**：对应新风机组（product_code `130004`）。数据来源：`/api/dashboard/device-fault-summary/` 中的 `fresh_air_unit.fault_count`。
2. **能耗设备**：对应能源计量相关设备。数据来源：`/api/dashboard/plc-online-rate/`（计量 PLC 在线状态）+ `FaultEvent` 中与能耗设备相关的活跃故障（具体过滤方式见 OQ-01）。
3. **水力模块**：对应水力模块设备（product_code `270001`）。数据来源：`/api/dashboard/device-fault-summary/` 中的 `hydraulic_module.fault_count`。
4. **空气品质**：对应空气品质传感器（product_code `100007`）。数据来源：`/api/dashboard/device-fault-summary/` 中的 `air_quality_sensor.fault_count`。

每个隔舱的颜色编码规则：
- 无活跃故障 → 青色边框 + 绿色状态点（`#27f5b5`）
- 存在预警 → 黄色边框 + 黄色发光状态点（`#ffd400`）
- 存在故障 → 红色边框 + 红色发光状态点（`#ff315d`）+ 损伤闪烁动画

**来源引用**：用户需求"专有部分包括：新风、能耗、水力模块、空气品质"；`/api/dashboard/device-fault-summary/` API 四类数据（`views.py:1578-1601`）；现有业主视图 `system-dock` 模块颜色编码模式。

**优先级**：Must Have

**备注**：能耗子系统的具体数据聚合方式待 OQ-01 确认。

---

### REQ-FUNC-003 房间隔舱状态展示

**描述**：2D 战舰透视图中，每个房间（书房、次卧、主卧、儿童房、客厅等）以独立隔舱展示。隔舱内标注房间名。隔舱颜色编码反映该房间内所有设备的故障/预警综合状态：
- 房间内任一设备存在活跃故障（severity=error）→ 红色隔舱 + 损伤闪烁动画
- 房间内无故障但存在预警（severity=warning 或活跃结露预警）→ 黄色隔舱
- 房间内全部正常 → 青色隔舱 + 绿色状态点

隔舱标注活跃故障/预警计数（如"3 故障 / 2 预警"或简化为数字角标）。

**来源引用**：用户需求"各个房间的设备状态"；现有业主视图 `room-grid` / `roomCards` 逐房间状态渲染（`pages/home/index.vue:113-150`）；`/api/devices/fault-events/` API 按 `room_name` 分组可获取房间级故障列表。

**优先级**：Must Have

---

### REQ-FUNC-004 2D 战舰透视图可视化

**描述**：页面主体为一个"2D 赛博朋克风格太空战舰剖面透视图"，设计方向由 PM 确认（I-05）：

> 霸气巨型星际巡洋舰，船体结构极度复杂充满未来科技感，精密机械管线与霓虹能量回路遍布舰体，X 射线透视视角清晰展示全舰内部舱室布局，各功能区域用发光轮廓线明确标注。
>
> **功能舱区**（子系统隔舱）：新风系统模块、能耗中枢、水利循环模块、空气品质监测站。设备状态通过线条颜色区分——正常运行青蓝色霓虹线、预警状态橙红色闪烁线、待机状态暗紫色弱光线，模块背景色同步对应状态等级。
>
> **生活舱区**（房间隔舱）：客厅、主卧、次卧、书房、儿童房，每个房间用赛博朋克风格全息文字标签悬浮标注，房间内部有简约家居结构轮廓，房间边缘发光线条代表环境系统运行状态。
>
> **整体视觉**：背景为深邃宇宙深空，点缀遥远星云与微弱星光，舰体外部有冷蓝色引擎辉光，整体色调以深蓝、暗紫、霓虹青为主，高对比度，锐利清晰的线条感，矢量插画风格，8K 超清，极致细节，电影级光影，赛博朋克 UI 界面设计感，工程蓝图质感。
>
> **负向约束**：禁止 3D 渲染、写实照片、模糊、低分辨率、人物、生物、杂乱文字、多余水印、变形扭曲、脏污、破损、地面、星球表面、单调背景、色彩溢出。

基本结构（自上而下）：
- 舰首区域（FREEARK 标识铭牌）
- 子系统 dock 区（横向排列四个子系统隔舱）
- 动力脊线（横向能量流动画线条，贯穿舰体）
- 房间网格区（2 列或自适应网格排列各房间隔舱）
- 舰尾引擎区（脉冲发光引擎装饰）
- **PLC 在线状态独立指示器**（PM 确认：I-04，独立于隔舱体系）

**来源引用**：用户需求"最好能有一个 2D 可视化仪表盘——复杂战舰透视图，用线条和颜色勾勒舱室，显示状态"；PM 确认 I-05 详细设计方向；现有业主视图的 `ship-shell` → `ship-nose` → `system-dock` → `ship-spine` → `room-grid` → `ship-tail` 六段式布局（`pages/home/index.vue:60-155`）。

**优先级**：Must Have（PM 将原 Should Have 提升，设计方向已明确）

**备注**：隔舱具体 clip-path 造型、尺寸比例、管线连接路由由开发阶段基于上述设计方向自行设计。OQ-04 已确认方案 A。

---

### REQ-FUNC-005 业主专有视角（含多座舱切换）

**描述**：owner（role=user）进入舰桥页面时，仅展示其**已绑定 specific_part** 对应的房间隔舱和相关子系统状态。数据来源：
- 房间结构：`/api/miniapp/owner/structure/`（骨架）+ `/api/miniapp/owner/realtime-params/`（实时参数，用于判断故障/预警参数）
- 故障事件：`/api/devices/fault-events/?specific_part={sp}&is_active=true`（按 specific_part 过滤）

若用户绑定了多个专有部分，提供切换器（picker）在不同"座舱"之间切换，切换后刷新对应数据。若未绑定任何专有部分，展示"未链接座舱"空态并引导至绑定页。

**来源引用**：PM 代码探索 §3"Owner view"；现有业主视图 `bindings` 列表 + `unit-bar` 切换器（`pages/home/index.vue:28-40`）；v1.8.0 业主数据隔离体系；KB: KE-REQ-004。

**优先级**：Must Have

---

### REQ-FUNC-006 隔舱点击交互（钻取故障详情）

**描述**：用户点击任意子系统隔舱或房间隔舱时，以**半屏弹出抽屉**（赛博朋克风格）展示该隔舱对应的活跃故障/预警列表（PM 确认：I-02 方案 A）：

- **子系统隔舱点击**：展示该品类所有活跃 FaultEvent 记录，含设备名、故障类型（comm/sensor/fresh_air/other_error）、严重程度（error/warning）、故障描述、首次发现时间。若该品类无活跃故障，提示"该子系统运行正常"。
- **房间隔舱点击**：展示该房间内所有设备的活跃故障/预警，含设备名、故障类型、严重程度、故障描述、发现时间。结露预警事件一并列入。若该房间无故障，提示"该房间设备运行正常"。

抽屉样式：半屏高度，深色半透明背景+赛博朋克边框（青色发光），列表项带状态色左边框（红=故障/黄=预警），底部关闭手柄。

**来源引用**：用户需求"显示'智能方舟座舱'各设备是否有错误、警告"隐含需要查看具体故障信息；`/api/devices/fault-events/` API 提供逐条故障详情。PM 确认 I-02 方案 A。

**优先级**：Should Have

---

### REQ-FUNC-007 结露预警集成（含独立计数角标）

**描述**：结露预警（condensation warning）作为一类特殊的 warning 在舰桥中双层展示（PM 确认：I-03 方案 B）：

1. **全局独立计数角标**：在舰桥页面醒目位置（如健康指示器旁或独立预警面板）展示活跃结露预警总数，以独立角标/Badge 形态呈现（黄色发光 + 计数数字），与故障计数分列。
2. **房间隔舱**：存在活跃结露预警的房间隔舱显示黄色预警状态（与一般 warning 同级）。
3. **点击钻取**：点击受影响房间隔舱时，结露预警事件在故障列表中与一般 warning 一并列出，标注为"结露预警"。

**来源引用**：`/api/devices/condensation-warning-events/` API。PM 确认 I-03 方案 B。

**优先级**：Should Have

---

### REQ-FUNC-008 PLC 在线状态集成（独立指示器）

**描述**：PLC 通信状态作为**独立指示器**展示在舰桥页面（PM 确认：I-04），不与整体健康度融合计算。全部在线 → 正常（青蓝）；部分离线 → 预警（橙红闪烁）；全部离线 → 告警（红色）。指示器独立于隔舱体系，以独立的 UI 元素呈现（如"通讯链路"状态条或独立 LED 面板）。

**来源引用**：`/api/dashboard/plc-online-rate/` API；PM 确认 I-04 独立指示器。

**优先级**：Should Have

---

### REQ-FUNC-009 数据周期性刷新

**描述**：舰桥页面在显示期间周期性拉取最新故障和状态数据，更新隔舱颜色和计数。刷新周期 **30 秒**（PM 确认：I-01，与现有 `PagePoller` 一致）。页面不可见时（`onHide`）停止轮询以节省资源。支持下拉手动刷新（`onPullDownRefresh`），刷新时显示加载指示器。

**来源引用**：现有 `PagePoller` 轮询器 30 秒周期（`pages/home/index.vue:707`）；`onPullDownRefresh` 手动刷新逻辑（`pages/home/index.vue:730-737`）；PM 确认 I-01。

**优先级**：Must Have

---

### REQ-FUNC-010 显式排除运行参数

**描述**：舰桥页面**不得**展示以下类型的运行参数数据（此为用户明确要求，非裁量）：
- 温度数值（设定温度、实际温度、露点温度等）
- 湿度数值（%RH）
- 能耗数值（kWh、累计用量等）
- CO2/PM2.5 浓度数值
- 压力数值
- 运行模式标签（制冷/制热/通风/除湿等）

页面仅展示：故障计数、预警计数、受影响设备/房间名、严重程度标签（error/warning）、故障类型标签。正常状态以颜色（青色/绿色）表示"无异常"而不展示具体健康参数。

**来源引用**：用户需求严格约束："只关注警告和故障，不显示其他参数"。

**优先级**：Must Have

**备注**：当前业主视图中的 `temp-board`（温度数值显示）、`module-temp`（模块温度文字）在重写后均须移除。

---

### REQ-FUNC-011 加载、空态与异常状态处理

**描述**：

- **加载态**：数据首次加载时展示赛博朋克风格的同步动画/骨架屏（如扫描线效果 + "正在同步方舟舱图…"文字），隔舱结构可先以灰色占位渲染。
- **空态**：owner 未绑定专有部分时展示"未链接座舱"提示 + "激活座舱"按钮（跳转绑定页），沿用现有 owner-empty 样式（`pages/home/index.vue:47-52`）。
- **API 失败**：单个 API 失败时，对应隔舱显示"离线"或"数据不可用"标记，其他隔舱正常展示。全部 API 失败时展示错误横幅（复用现有 owner-error 样式）和重试入口。如存在过期缓存数据，优先使用缓存保持隔舱结构可见，标注"数据可能已过时"。

**来源引用**：现有 ownerLoading/ownerError/owner-empty 模式（`pages/home/index.vue:43-52, 158-160`）；KB: KE-REQ-003 骨架缓存与降级策略。

**优先级**：Must Have

---

## 5. 非功能性需求

### REQ-NFUNC-001 赛博朋克视觉一致性

**描述**：舰桥页面的全部视觉元素必须与小程序现有赛博朋克视觉体系严格一致（详见 §2.1 色板和动画清单）。不得引入 Material Design 或其他非赛博朋克视觉元素。具体约束：
- 背景：深色底（`#05070f` 系列）+ 80rpx 网格叠加层（青线 opacity 0.06）
- 隔舱边框：青线，故障态切换为黄/红
- 状态发光效果：绿 `#27f5b5`（box-shadow 14rpx）、黄 `#ffd400`（14rpx）、红 `#ff315d`（16rpx）
- 动画：HUD 扫描线、动力流、引擎脉冲、损伤闪烁——全部复用现有 `@keyframes` 定义
- 数据标注字体：Orbitron/Menlo monospace
- 隔舱造型：clip-path polygon 异形多边形

**来源引用**：用户需求"舰桥页面和整个微信小程序保持赛博朋克（Cyberpunk）UI 风格一致"；PM 代码探索 §2 完整色板与视觉元素清单。

**优先级**：Must Have

---

### REQ-NFUNC-002 页面性能

**描述**：
- 数据刷新周期：**30 秒**（PM 确认：I-01）
- 单次刷新（仅更新隔舱颜色和计数，不重建 DOM）：应在 300ms 内完成视觉更新
- 首次冷加载：隔舱骨架应尽快渲染（目标 < 2 秒），数据可异步填充
- 页面进入后台（`onHide`）时停止全部轮询和 CSS 动画以节省资源

**来源引用**：现有 `PagePoller` 的 onHide 停止策略（`pages/home/index.vue:726-728`）；PM 确认 I-01。KB: KE-REQ-003 两阶段渲染模式。

**优先级**：Should Have

---

### REQ-NFUNC-003 角色数据隔离与安全

**描述**：
- owner 角色调用业主专属 API（`/api/miniapp/owner/`）并受 IsOwnerUser 中间件鉴权保护，仅返回其绑定 specific_part 的数据。
- 所有 API 调用受 Token 鉴权保护（v1.6.0 RBAC）。

**来源引用**：PM 代码探索 §3；v1.8.0 业主隔离体系（KB: KE-REQ-004）；v1.6.0 三角色 RBAC；`views.py:1564` 接口定义。

**优先级**：Must Have

---

### REQ-NFUNC-004 移动端可读性与可触性

**描述**：
- 所有可点击隔舱的最小触摸区域应不小于 44x44 逻辑像素（微信小程序推荐最小触摸目标）
- 隔舱内文字（房间名、故障计数）在 375px 逻辑宽度屏幕上清晰可读
- 隔舱数量较多时页面可纵向滚动，无需缩放
- 损伤闪烁动画闪烁频率不超过每秒 3 次，降低视觉疲劳

**来源引用**：微信小程序设计指南推荐值。

**优先级**：Should Have

---

### REQ-NFUNC-005 容错降级

**描述**：
- 单个数据源 API 失败时，对应隔舱显示"数据不可用"标记，其余隔舱正常展示
- 全部 API 均失败时展示明确错误提示和重试入口，**禁止白屏**
- 如存在过期缓存数据，优先使用缓存渲染隔舱结构，标注时效性提示
- 错误信息不得包含技术栈敏感信息（数据库连接错误、堆栈跟踪等），仅展示用户可理解提示

**来源引用**：KB: KE-REQ-003 降级策略（"网络失败时优先使用过期缓存，保留骨架不白屏"）；现有 owner-error 横幅设计。

**优先级**：Must Have

---

## 6. 假设

- A-01：`/api/dashboard/device-fault-summary/` 接口未被小程序 `api.js` 封装，需在本次实现中新增封装调用。API 鉴权策略已就绪。
- A-02：能耗子系统的故障状态可通过现有数据源推导（见 OQ-01），无需新增后端 API。
- A-03：现有赛博朋克视觉体系的 CSS 关键帧动画（scan、pulse、powerFlow、damageBlink、enginePulse、pulseSoft）在舰桥重写中可直接复用。
- A-04：ArkTabBar 的"舰桥" tab 仍指向现有首页路径（`/pages/home/index`），本次重写覆盖该页面文件。
- A-05：后端 FaultEvent 数据满足实时性要求——fault-consumer 在故障发生/恢复时及时更新 `is_active` 和 `recovered_at`。
- A-06：`/api/devices/fault-events/` 接口支持按 `specific_part` 过滤（用于 owner 视角按绑定 specific_part 查询），`api.js` 已支持传参。

---

## 7. 超出范围（Out of Scope）

以下功能明确不属于本版本范围：
- 温度、湿度、能耗数值（kWh）、CO2/PM2.5 浓度等"运行参数"的显示（用户明确排除）
- 后端新增或修改 API（C-04）
- ArkTabBar 或其他 tab 页面（指挥、副官、舰长休息室）的改动（C-05）
- web 端仪表盘的任何改动
- 实时 MQTT 推送（本版本使用 HTTP 周期性轮询，与现有模式一致）
- 隔舱布局的拖拽自定义或个性化配置
- 故障的创建、编辑、恢复操作（舰桥仅展示，操作在故障管理页完成）
- 隔舱对应设备的状态控制（开关、调参等——由参数设置页负责）

---

## 8. 推断项确认状态

| 编号 | 涉及需求 | 推断内容 | PM 决定 |
|------|---------|---------|---------|
| I-01 | REQ-NFUNC-002 | 性能目标 | ✅ **已确认**：刷新 30 秒间隔即可（PM："刷新30秒间隔就可以了"） |
| I-02 | REQ-FUNC-006 | 隔舱点击后故障列表的展示形态 | ✅ **已确认**：弹出层（半屏抽屉，赛博朋克风格）（PM："A"） |
| I-03 | REQ-FUNC-007 | 结露预警是否需要独立全局计数展示 | ✅ **已确认**：额外加独立计数角标（PM："B"） |
| I-04 | REQ-FUNC-008 | PLC 在线状态展示形式 | ✅ **已确认**：独立指示器（PM："独立指示器"） |
| I-05 | REQ-FUNC-004 | 战舰透视图设计方向 | ✅ **已确认**：PM 提供详细设计方向（2D 赛博朋克太空战舰剖面透视图，见 REQ-FUNC-004） |

---

## 9. 开放问题（全部已闭环）

### OQ-01 能耗子系统数据源 ✅ 已确认

**PM 决定：方案 A**。在舰桥层面推导——将 PLC 在线率（`/api/dashboard/plc-online-rate/`）作为能耗子系统的基础状态，同时过滤 `FaultEvent` 中与能源计量相关的记录（按 device_name 或 device_type_label 匹配），聚合为能耗子系统状态。零后端改动，符合 C-04。

### OQ-02 ~~管理/运维视角的房间隔舱组织方式~~ ✅ 已消解

因 PM 确认 P0 仅 user 角色，本问题自然消解。user 仅查看当前选中座舱的房间，无多专有部分打平问题。

### OQ-03 温控面板的归属 ✅ 已确认

**PM 决定：方案 A**。不单独设立"温控面板"子系统隔舱，温控面板的故障直接体现在所属房间的隔舱状态中。

### OQ-04 战舰透视图的隔舱布局 ✅ 已确认

**PM 决定：方案 A**。开发阶段基于现有业主战舰视图六段式布局扩展重构，子系统 dock 扩展到 4 个隔舱。结合 PM 提供的详细设计方向（见 REQ-FUNC-004）。

---

## 10. 备注

- 本需求由 sub_agent_requirement_analyst 产出，依据 PM 提供的用户需求原文 + 代码探索发现 + 对 `pages/home/index.vue`、`utils/api.js`、`views.py` 等关键文件的直接阅读验证。
- 知识库命中并已应用：KE-REQ-003（骨架缓存与降级策略→REQ-FUNC-012、REQ-NFUNC-005）、KE-REQ-004（业主端领域知识→REQ-FUNC-006 及 C-03）。
- 当前舰桥页面（v1.5.0 时期的产物）已采用赛博朋克战舰主题的业主视图，本次重写在此基础上：提升战舰透视图视觉效果（按 PM 设计方向）、增加子系统隔舱品类（新风/能耗/水力/空气品质）、移除所有运行参数展示、补充隔舱点击交互、增加 PLC 独立指示器。
- 进入开发阶段前，§8 待确认推断项（5 条）和 §9 开放问题（4 条）需 PM 闭环。
