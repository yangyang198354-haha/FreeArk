# 用户故事与验收标准

```
file_header:
  document_id: US-v1.0.0-DASHBOARD-REDESIGN
  title: 系统看板重设计 + 设备列表凝露提醒列 — 用户故事
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v1.0.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: APPROVED
  references:
    - docs/requirements/v1.0.0_dashboard_redesign_device_condensation/requirements_spec.md
```

---

## 模块 A：设备列表凝露提醒列

### US-CL-01 查看凝露提醒状态

**As** 运营人员
**I want** 在设备列表看到每个住户的凝露提醒状态（有/无）
**So that** 我无需跳转到结露预警页面即可知道哪些住户当前有未恢复的凝露问题

**优先级**：P1
**依赖需求**：REQ-FUNC-CL-01
**前置条件**：
- 已登录系统
- 进入「设备管理 > 设备列表」页面（`/device-management/device-list`）

#### 验收标准

**AC-CL-01-01（有凝露提醒的住户）**
Given 专有部分 X 在 `condensation_warning_event` 表中有 `is_active=True` 的记录
When 运营人员进入设备列表页面（不设过滤，默认分页）
Then 专有部分 X 对应行的「凝露提醒」列显示文字「有」，且文字颜色为橙色（`#E6A23C` 或等价 warning 色变量）

**AC-CL-01-02（无凝露提醒的住户）**
Given 专有部分 Y 在 `condensation_warning_event` 表中没有 `is_active=True` 的记录（或无任何记录）
When 运营人员进入设备列表页面
Then 专有部分 Y 对应行的「凝露提醒」列显示文字「无」，颜色为灰色（`#909399` 或等价 placeholder 色变量）

**AC-CL-01-03（仅 1 列，无第二列）**
Given 运营人员进入设备列表页面
When 页面加载完成
Then 「故障数量」列之后、「操作」列之前恰好存在 1 列「凝露提醒」，不存在任何其他新增凝露相关列

**AC-CL-01-04（批量查询，不逐行请求）**
Given 分页大小为 20 条
When 设备列表加载一页数据
Then 后端在一次数据库 IN 查询中批量获取该页所有专有部分的凝露状态，不对每行发起独立查询（可通过 Django ORM QuerySet 查询日志验证）

**AC-CL-01-05（凝露恢复后正确更新）**
Given 专有部分 Z 之前有 is_active=True 的凝露预警，后被 `freeark-condensation-consumer` 标记为 is_active=False（recovered）
When 运营人员刷新设备列表
Then 专有部分 Z 的「凝露提醒」列显示「无」

---

## 模块 B：系统看板 — 故障总数卡片

### US-DC-01 查看当前故障总数

**As** 运营人员
**I want** 在系统看板上看到「当前故障总数」和「影响户数」
**So that** 我能即时掌握系统整体故障规模，无需进入故障管理列表翻页统计

**优先级**：P1
**依赖需求**：REQ-FUNC-DC-01

#### 验收标准

**AC-DC-01-01（卡片展示故障总数）**
Given 系统中当前有 N 条 `is_active=True` 的故障记录（跨所有 sub_type）
When 运营人员进入系统看板首页
Then「当前故障总数」卡片主数值显示 N

**AC-DC-01-02（卡片展示影响户数，口径为 specific_part 去重计数）**
Given 系统中有未恢复故障（`is_active=True`），涉及 M 个不同的 `specific_part` 值
When 运营人员查看「当前故障总数」卡片
Then 卡片副信息显示「影响 M 户」（M = `FaultEvent` 中 `is_active=True` 的 `specific_part` 去重计数）；若同一 specific_part 有多条未恢复故障，仍只计为 1 户

**AC-DC-01-03（点击跳转故障管理）**
Given 运营人员在系统看板看到「当前故障总数」卡片
When 运营人员点击该卡片
Then 路由跳转至 `/device-management/faults`，页面加载后默认显示未恢复（`is_active=true`）故障列表

**AC-DC-01-04（卡片有 hover 动效）**
Given 运营人员鼠标悬停在「当前故障总数」卡片上
When 鼠标 hover
Then 卡片执行上移 4px + 阴影增强的 CSS 过渡动画（与现有 `.stat-card:hover` 一致，250ms ease-out）

---

## 模块 B：系统看板 — 空气品质传感器卡片

### US-DC-02 查看空气品质传感器概况

**As** 运营人员
**I want** 在系统看板上看到空气品质传感器的总数和当前故障数
**So that** 我可以快速了解该类设备的健康状态，并一键进入故障详情

**优先级**：P1
**依赖需求**：REQ-FUNC-DC-02

#### 验收标准

**AC-DC-02-01（卡片展示总数和故障数）**
Given DeviceNode 表中 `product_code=100007` 的设备共 T 台，且当前 `sub_type=air_quality_sensor` 且 `is_active=True` 的故障记录共 F 条
When 运营人员进入系统看板
Then「空气品质传感器」卡片显示总数 T、故障数 F（F 为故障记录条数，非住户去重数）

**AC-DC-02-02（点击跳转并预选过滤）**
Given 运营人员点击「空气品质传感器」卡片
When 路由跳转至故障管理页面
Then 页面 URL 包含 `sub_type=air_quality_sensor&is_active=true`，页面加载后「设备类型」过滤器已选中「空气品质传感器」，且仅展示 `is_active=true` 的故障记录

**AC-DC-02-03（FaultManagementView 支持 URL sub_type 初始化）**
Given 通过 URL `?sub_type=air_quality_sensor&is_active=true` 直接访问故障管理页
When 页面 `onMounted` 执行
Then `filters.sub_types` 被初始化为 `['air_quality_sensor']`，`filterIsActive` 被初始化为 `'true'`，并自动触发一次查询

---

## 模块 B：系统看板 — 温控面板卡片

### US-DC-03 查看温控面板概况

**As** 运营人员
**I want** 在系统看板上看到所有温控面板（5 个 sub_type，含客厅主温控）的总数和故障数
**So that** 我可以快速判断温控面板整体健康状况

**优先级**：P1
**依赖需求**：REQ-FUNC-DC-03

#### 验收标准

**AC-DC-03-01（卡片展示 5 sub_type 合计总数和故障数）**
Given DeviceNode 表中 `product_code IN (120003, 260001)` 的设备共 T2 台，且涉及 master_bedroom_panel / secondary_bedroom_panel / children_room_panel / study_room_panel / living_room_main 这 5 个 sub_type 的未恢复故障记录共 F2 条
When 运营人员进入系统看板
Then「温控面板」卡片展示总数 T2 和故障数 F2（F2 为 5 个 sub_type 未恢复故障记录条数之和，非住户去重数）

**AC-DC-03-02（客厅主温控纳入统计）**
Given 系统中存在 sub_type=living_room_main（product_code=260001）的设备及其未恢复故障记录
When 运营人员查看「温控面板」卡片
Then 客厅主温控的设备数计入总数 T2，其未恢复故障记录条数计入故障数 F2

**AC-DC-03-03（点击跳转并预选全部 5 个 sub_type）**
Given 运营人员点击「温控面板」卡片
When 路由跳转至故障管理页面
Then URL 包含全部 5 个 sub_type 的重复参数（`?sub_type=master_bedroom_panel&sub_type=secondary_bedroom_panel&sub_type=children_room_panel&sub_type=study_room_panel&sub_type=living_room_main&is_active=true`），故障管理页过滤器显示已选中所有 5 种温控面板类型，展示 is_active=true 的故障记录

**AC-DC-03-04（FaultManagementView 支持 5 值 sub_type 多值初始化）**
Given 通过包含 5 个 `sub_type` 重复参数的 URL 直接访问故障管理页
When 页面 `onMounted` 执行
Then `filters.sub_types` 被初始化为包含上述 5 个 sub_type 值的数组，`filterIsActive` 被初始化为 `'true'`，并自动触发一次查询

---

## 模块 B：系统看板 — 新风卡片

### US-DC-04 查看新风设备概况

**As** 运营人员
**I want** 在系统看板上看到新风设备的总数和当前故障数
**So that** 我可以快速定位新风系统问题

**优先级**：P1
**依赖需求**：REQ-FUNC-DC-04

#### 验收标准

**AC-DC-04-01（卡片展示总数和故障数）**
Given DeviceNode 表中 `product_code=130004` 的设备共 T3 台，且 `sub_type=fresh_air_unit` 且 `is_active=True` 的故障记录共 F3 条
When 运营人员进入系统看板
Then「新风」卡片展示总数 T3 和故障数 F3（F3 为故障记录条数，非住户去重数）

**AC-DC-04-02（点击跳转并预选 fresh_air_unit 过滤）**
Given 运营人员点击「新风」卡片
When 路由跳转至故障管理页面
Then URL 包含 `sub_type=fresh_air_unit&is_active=true`，故障管理页过滤器已选中「新风机」

---

## 模块 B：系统看板 — 水力模块卡片

### US-DC-05 查看水力模块概况

**As** 运营人员
**I want** 在系统看板上看到水力模块的总数和当前故障数
**So that** 我可以快速掌握水力系统故障情况

**优先级**：P1
**依赖需求**：REQ-FUNC-DC-05

#### 验收标准

**AC-DC-05-01（卡片展示总数和故障数）**
Given DeviceNode 表中 `product_code=270001` 的设备共 T4 台，且 `sub_type=hydraulic_module` 且 `is_active=True` 的故障记录共 F4 条
When 运营人员进入系统看板
Then「水力模块」卡片展示总数 T4 和故障数 F4（F4 为故障记录条数，非住户去重数）

**AC-DC-05-02（点击跳转并预选 hydraulic_module 过滤）**
Given 运营人员点击「水力模块」卡片
When 路由跳转至故障管理页面
Then URL 包含 `sub_type=hydraulic_module&is_active=true`，故障管理页过滤器已选中「水力模块」

---

## 模块 C：系统看板布局重排

### US-UX-01 看板卡片按 4 类分组排列

**As** 运营人员
**I want** 系统看板的卡片按「能耗概览 | 设备状态 | 故障与子设备 | 趋势与日志」4 组展示，组间有分组标题行
**So that** 我在查看看板时能快速定位所需类型的信息，视觉更清晰

**优先级**：P2
**依赖需求**：REQ-FUNC-UX-01

#### 验收标准

**AC-UX-01-01（4 组分组标题行可识别）**
Given 运营人员进入系统看板
When 页面加载完成
Then 看板从上到下依次出现「能耗概览」、「设备状态」、「故障与子设备」、「趋势与日志」4 个分组标题行，每个标题行在视觉上清晰区分相邻卡片组

**AC-UX-01-02（各组卡片归属正确）**
Given 运营人员进入系统看板
When 页面加载完成
Then 「能耗概览」组含：总电量查询、今日用电量、本月用电量；「设备状态」组含：PLC在线、大屏在线、总设备数、系统开机状况；「故障与子设备」组含：当前故障总数、空气品质传感器、温控面板、新风、水力模块；「趋势与日志」组含：近7天用电趋势图、系统运行状态、最近活动；无卡片缺漏或错置

**AC-UX-01-03（现有卡片不丢失）**
Given 原看板已有的全部卡片（总电量查询、今日用电量、本月用电量、PLC在线、大屏在线、总设备数、系统开机状况、近7天用电趋势图、系统运行状态、最近活动）
When 布局重排后进入系统看板
Then 上述全部现有卡片仍然展示，无任何卡片因重排而消失

---

### US-UX-02 所有统计卡片具有 Hover 动效

**As** 运营人员
**I want** 鼠标悬停时卡片有轻微上移动画
**So that** 页面有活泼的交互感，可点击的元素有明显视觉反馈

**优先级**：P2
**依赖需求**：REQ-FUNC-UX-02

#### 验收标准

**AC-UX-02-01（新增卡片继承 hover 样式）**
Given 运营人员进入系统看板
When 鼠标悬停在任意一张新增的故障/子设备统计卡片上（故障总数、空气品质传感器、温控面板、新风、水力模块中任意一张）
Then 卡片以 250ms ease-out 动画上移 4px 并显示增强阴影，松开鼠标后恢复原位

**AC-UX-02-02（现有卡片 hover 行为不受影响）**
Given 运营人员进入系统看板
When 鼠标悬停在现有的统计卡片（今日用电量、PLC在线等）上
Then 动效行为与改造前完全一致（无回归）

---

### US-UX-03 新增卡片具有明确的点击指示

**As** 运营人员
**I want** 可跳转的卡片在视觉上表明可以点击
**So that** 我不需要猜测哪些卡片可以交互

**优先级**：P2
**依赖需求**：REQ-FUNC-UX-03

#### 验收标准

**AC-UX-03-01（可点击卡片有 pointer 光标）**
Given 运营人员鼠标移入新增的故障/子设备统计卡片
When 光标进入卡片区域
Then 光标变为 `pointer` 样式（手型）

---

## 用户故事汇总

| US 编号 | 优先级 | 模块 | 标题 | 状态 |
|---------|-------|------|------|------|
| US-CL-01 | P1 | 设备列表 | 凝露提醒「有/无」单列（橙色文字，仅 1 列） | APPROVED |
| US-DC-01 | P1 | 系统看板 | 当前故障总数卡片（影响户数=specific_part 去重计数） | APPROVED |
| US-DC-02 | P1 | 系统看板 | 空气品质传感器卡片（总数来自 DeviceNode，故障按记录条数） | APPROVED |
| US-DC-03 | P1 | 系统看板 | 温控面板卡片（5 sub_type 含 living_room_main，故障按记录条数） | APPROVED |
| US-DC-04 | P1 | 系统看板 | 新风卡片（总数来自 DeviceNode，故障按记录条数） | APPROVED |
| US-DC-05 | P1 | 系统看板 | 水力模块卡片（总数来自 DeviceNode，故障按记录条数） | APPROVED |
| US-UX-01 | P2 | 系统看板 | 看板 4 组分组排列（分组标题行） | APPROVED |
| US-UX-02 | P2 | 系统看板 | Hover 动效（复用 .stat-card） | APPROVED |
| US-UX-03 | P2 | 系统看板 | 可点击跳转指示（cursor: pointer） | APPROVED |
