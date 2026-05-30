# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v1.0.0-DASHBOARD-REDESIGN
  title: 系统看板重设计 + 设备列表凝露提醒列 — 需求规格说明书
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v1.0.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: APPROVED
  references:
    - FreeArkWeb/frontend/src/views/HomeView.vue（系统看板组件，已阅）
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue（设备列表，已阅）
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue（故障管理，已阅）
    - FreeArkWeb/frontend/src/views/CondensationWarningView.vue（结露预警，已阅）
    - FreeArkWeb/frontend/src/router/index.js（路由，已阅）
    - FreeArkWeb/backend/freearkweb/api/views.py（dashboard API 群，已阅）
    - FreeArkWeb/backend/freearkweb/api/views_fault.py（故障 API，已阅）
    - FreeArkWeb/backend/freearkweb/api/views_condensation.py（凝露 API，已阅）
    - FreeArkWeb/backend/freearkweb/api/models.py（CondensationWarningEvent, FaultEvent，已阅）
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py（sub_type 常量，已阅）
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-30 | 初始草稿，基于代码库调研结果撰写 |
| 1.0.0-APPROVED | 2026-05-30 | 依据用户确认的 Q1~Q7 答案全面定稿：修正凝露为 1 列、确定影响户数口径、确定故障数按记录条数、温控面板纳入 5 个 sub_type（含 living_room_main）、看板 4 组分组标题行方案、各子设备总数取 DeviceNode 表、product_code 全部明确 |

---

## 1. 背景与目标

### 1.1 背景

FreeArk 系统当前处于 v0.9.0，已实现：
- 故障管理（v0.6.x）：支持 sub_type（设备子类型）过滤，URL 为 `/device-management/faults`，前端参数名 `sub_type`，取值来自 `constants.py` 的 `SUB_TYPE_LABELS` 字典
- 结露预警（v0.7.0）：独立页面 `/device-management/condensation-warnings`，后端模型 `CondensationWarningEvent`（字段 `is_active`、`specific_part`），API `GET /api/devices/condensation-warning-events/`
- 设备列表（`/device-management/device-list`）：每行为一个专有部分（住户单元），现有列：楼栋、单元、户号、大屏状态、PLC状态、PLC上次心跳、系统开关、运行模式、故障数量、操作
- 系统看板（`/home`）：现有卡片包括总电量查询、系统开机状况、今日用电量、本月用电量、PLC在线、大屏在线、总设备数，以及用电趋势图、系统运行状态、最近活动

### 1.2 目标

1. **REQ-OBJ-01**：在设备列表为每个专有部分增加 1 列凝露/结露提醒，运营人员可在设备列表页快速识别当前有未恢复凝露预警的住户。
2. **REQ-OBJ-02**：在系统看板新增故障与子设备统计卡片，运营人员无需跳转即可获得全局故障概况，并可一键跳转至对应过滤视图。
3. **REQ-OBJ-03**：对系统看板整体布局进行 4 组分组重排，提升视觉层次感与可用性，并为所有统计卡片增加 hover 动效。

---

## 2. 利益相关人

| 角色 | 诉求 |
|------|------|
| 运营人员（主要用户） | 在设备列表快速发现有凝露提醒的住户；在看板一眼获取全局故障数量与子设备故障概况 |
| 系统管理员 | 看板卡片内容准确、加载快速；新卡片点击跳转行为与现有故障管理过滤一致 |

---

## 3. 功能需求

### 3.1 模块 A：设备列表凝露提醒列（REQ-FUNC-CL）

#### REQ-FUNC-CL-01 新增凝露提醒列（已定稿）

**描述**：在设备列表表格中**仅新增 1 列**「凝露提醒」，显示该专有部分当前是否有**未恢复（is_active=true）**的结露预警。原草稿中描述的"2 列"为笔误，经用户确认为 1 列，无第二列。

**展示规则**：
- 有未恢复结露预警：显示文字「有」，文字颜色为橙色（`#E6A23C`，与系统 warning 色统一）
- 无未恢复结露预警：显示文字「无」，颜色为正常灰色（`#909399`）

**列位置**：插入在「故障数量」列之后、「操作」列之前。

**数据来源**（已定稿）：
- 后端在设备列表 API（`GET /api/device-management/device-list/`）响应中，为每条记录注入 `has_active_condensation` 布尔字段
- 数据来自 `CondensationWarningEvent` 表，条件：`specific_part = 对应户号`，`is_active = True`
- 使用 `CondensationWarningEvent` 的 `specific_part` 字段与 `is_active` 字段批量查询

**性能约束**：
- 批量查询（IN 查询），不得对每行单独查询，参考 `fault_count` 的批量模式（`get_fault_count_batch_cached`）

---

### 3.2 模块 B：系统看板新增故障与子设备卡片（REQ-FUNC-DC）

#### REQ-FUNC-DC-01 当前故障总数卡片（已定稿）

**描述**：新增「当前故障总数」统计卡片，显示系统内当前所有**未恢复（is_active=true）**故障事件的汇总信息。

**展示内容**：
- 主数值：当前未恢复故障总数（`FaultEvent.is_active=True` 的记录总条数）
- 副信息：**影响户数**（口径已定稿：有未恢复故障的 `specific_part` 去重计数，即 `FaultEvent.objects.filter(is_active=True).values('specific_part').distinct().count()`）
- 图标：建议使用 warning/bell 类图标，颜色为 danger（`#F56C6C`）

**交互**：点击卡片跳转至故障管理页面（`/device-management/faults`），预设 `is_active=true` 过滤。

**后端接口**：新增 `GET /api/dashboard/fault-summary/`，返回：
```json
{
  "success": true,
  "data": {
    "active_fault_count": 42,
    "affected_unit_count": 38
  }
}
```
其中 `affected_unit_count` = `FaultEvent` 中 `is_active=True` 的 `specific_part` 去重计数。

#### REQ-FUNC-DC-02 空气品质传感器卡片（已定稿）

**描述**：新增「空气品质传感器」统计卡片。

**展示内容**：
- 子设备总数：从 `DeviceNode` 表按 `product_code=100007` 统计实际在库设备数
- 故障数：`sub_type=air_quality_sensor` 当前未恢复故障**记录条数**（`FaultEvent.objects.filter(sub_type='air_quality_sensor', is_active=True).count()`，按故障记录条数统计，非住户去重数）
- 图标：空气/传感器相关图标，颜色建议为 warning 色

**交互**：点击跳转到故障管理页面，预选 `sub_type=air_quality_sensor`，`is_active=true`。

跳转路径：
```
router.push({ name: 'FaultManagement', query: { sub_type: 'air_quality_sensor', is_active: 'true' } })
```

**FaultManagementView 兼容性需求**：`FaultManagementView.vue` 的 `onMounted` 需补充读取 URL query 参数 `sub_type`（支持多值）、`is_active`，并初始化对应过滤状态后自动触发查询（见 REQ-NFR-COMPAT-01）。

#### REQ-FUNC-DC-03 温控面板卡片（已定稿）

**描述**：新增「温控面板」统计卡片，汇总**所有温控面板（含客厅主温控）**，共 5 个 sub_type。

**sub_type 覆盖范围（已定稿，含 living_room_main）**：
| sub_type | 说明 | product_code |
|----------|------|--------------|
| master_bedroom_panel | 主卧温控面板 | 120003 |
| secondary_bedroom_panel | 次卧温控面板 | 120003 |
| children_room_panel | 儿童房温控面板 | 120003 |
| study_room_panel | 书房温控面板 | 120003 |
| living_room_main | 客厅主温控 | 260001 |

**展示内容**：
- 温控面板总数：从 `DeviceNode` 表，`product_code IN (120003, 260001)` 的设备总数（5 个 sub_type 对应设备合计）
- 故障数：涉及上述 5 个 sub_type 的未恢复故障**记录条数**（`FaultEvent.objects.filter(sub_type__in=[...5个sub_type...], is_active=True).count()`）

**交互**：点击跳转到故障管理页面，预选全部 5 个 sub_type（URL 重复参数形式）：
```
router.push({
  name: 'FaultManagement',
  query: {
    sub_type: [
      'master_bedroom_panel',
      'secondary_bedroom_panel',
      'children_room_panel',
      'study_room_panel',
      'living_room_main'
    ],
    is_active: 'true'
  }
})
```

#### REQ-FUNC-DC-04 新风卡片（已定稿）

**描述**：新增「新风」统计卡片，对应 `sub_type=fresh_air_unit`（product_code=130004）。

**展示内容**：
- 新风设备总数：从 `DeviceNode` 表按 `product_code=130004` 统计实际在库设备数
- 故障数：`sub_type=fresh_air_unit` 未恢复故障**记录条数**（`FaultEvent.objects.filter(sub_type='fresh_air_unit', is_active=True).count()`）

**交互**：点击跳转，预选 `sub_type=fresh_air_unit`，`is_active=true`。

#### REQ-FUNC-DC-05 水力模块卡片（已定稿）

**描述**：新增「水力模块」统计卡片，对应 `sub_type=hydraulic_module`（product_code=270001）。

**展示内容**：
- 水力模块总数：从 `DeviceNode` 表按 `product_code=270001` 统计实际在库设备数
- 故障数：`sub_type=hydraulic_module` 未恢复故障**记录条数**（`FaultEvent.objects.filter(sub_type='hydraulic_module', is_active=True).count()`）

**交互**：点击跳转，预选 `sub_type=hydraulic_module`，`is_active=true`。

#### REQ-FUNC-DC-06 新增卡片后端汇总接口（已定稿）

**描述**：新增 `GET /api/dashboard/device-fault-summary/` 接口，一次性返回所有子设备类型的总数与故障数，供看板一次性加载（避免 N 次独立接口调用）。

**各字段口径说明（已定稿）**：
- `total`：来自 `DeviceNode` 表，按 product_code 统计实际在库设备数
- `fault_count`：来自 `FaultEvent` 表，`is_active=True` 且 `sub_type` 匹配的**记录条数**（非住户去重数）
- 温控面板 `total` = `DeviceNode` 表 `product_code IN (120003, 260001)` 的总数
- 温控面板 `fault_count` = 5 个 sub_type（含 `living_room_main`）的未恢复故障记录总条数

响应结构：
```json
{
  "success": true,
  "data": {
    "air_quality_sensor":  { "total": 634, "fault_count": 5 },
    "thermostat_panels":   { "total": 3170, "fault_count": 12 },
    "fresh_air_unit":      { "total": 634, "fault_count": 3 },
    "hydraulic_module":    { "total": 634, "fault_count": 1 }
  }
}
```

注：`thermostat_panels` 聚合 5 个 sub_type（master_bedroom_panel、secondary_bedroom_panel、children_room_panel、study_room_panel、living_room_main），`total` 取 product_code 120003 + 260001 合计。

---

### 3.3 模块 C：系统看板布局重排与 Hover 动效（REQ-FUNC-UX）

#### REQ-FUNC-UX-01 卡片分组排列（已定稿）

**描述**：将看板所有卡片按 4 个逻辑类别分组排列，各组之间用**分组标题行**（带文字标题的分隔行）分隔。

**确定分组方案（已定稿，4 组）**：
| 分组 | 包含卡片 | 备注 |
|------|---------|------|
| 能耗概览 | 总电量查询、今日用电量、本月用电量 | 现有 |
| 设备状态 | PLC在线、大屏在线、总设备数、系统开机状况 | 现有 |
| 故障与子设备 | 当前故障总数、空气品质传感器、温控面板、新风、水力模块 | 新增 |
| 趋势与日志 | 近7天用电趋势图、系统运行状态、最近活动 | 现有 |

**分隔方式**：组间用分组标题行（文字形式，如 `<div class="group-title">能耗概览</div>`），不仅使用视觉分隔线。

#### REQ-FUNC-UX-02 Hover 动效

**描述**：所有统计类卡片（`stat-card` 样式）在鼠标悬停时产生上移 + 阴影增强的视觉动效。

**当前状态**：`HomeView.vue` 的 `.stat-card` 已有以下 CSS：
```css
.stat-card {
  transition: transform 250ms ease-out, box-shadow 250ms ease-out;
}
.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-card-hover);
}
```
新增的故障/子设备卡片须复用此样式类，确保动效一致。需确认 `--shadow-card-hover` CSS 变量已定义（防止降级时无阴影）。

#### REQ-FUNC-UX-03 新卡片点击可跳转

**描述**：所有新增的故障/子设备统计卡片需有明显的可点击指示（`cursor: pointer`），点击后执行路由跳转。

---

## 4. 非功能需求

### REQ-NFR-PERF-01 看板加载性能

新增卡片的数据接口响应时间 P95 < 500ms（生产 MySQL 环境）。禁止在看板加载时对每个 sub_type 发起独立 API 调用（合并为一次接口）。

### REQ-NFR-PERF-02 设备列表凝露列性能

凝露提醒字段通过批量 IN 查询注入，不得对每行单独查询。参考故障数量批量模式。

### REQ-NFR-COMPAT-01 跳转参数兼容性（已定稿）

看板卡片跳转到故障管理页时，URL query 参数须与 `FaultManagementView` 的 `onMounted` 初始化逻辑匹配。

**必须在开发阶段修改 `FaultManagementView.vue` 的 `onMounted`**，补充以下初始化逻辑：
1. 读取 `route.query.sub_type`（支持单值字符串或多值数组）
2. 读取 `route.query.is_active`
3. 将上述值赋给对应的 `filters` 响应式状态，并自动触发一次查询

温控面板跳转传递 5 个 sub_type 的 URL 形式为重复参数（Vue Router 自动序列化数组为重复 key）：
```
?sub_type=master_bedroom_panel&sub_type=secondary_bedroom_panel&sub_type=children_room_panel&sub_type=study_room_panel&sub_type=living_room_main&is_active=true
```

### REQ-NFR-STYLE-01 设计一致性

新增卡片的颜色、字体、间距须遵循现有 Design Token（`var(--color-*)`, `var(--space-*)`, `var(--font-*)` 等），不引入自定义魔法数字。

---

## 5. 需求汇总表

| 需求编号 | 类型 | 优先级 | 模块 | 简述 | 状态 |
|---------|------|-------|------|------|------|
| REQ-FUNC-CL-01 | 功能 | P1 | 设备列表 | 凝露提醒「有/无」单列（橙色文字） | APPROVED |
| REQ-FUNC-DC-01 | 功能 | P1 | 系统看板 | 当前故障总数 + 影响户数（specific_part 去重）card | APPROVED |
| REQ-FUNC-DC-02 | 功能 | P1 | 系统看板 | 空气品质传感器 card（product_code=100007，故障按记录条数） | APPROVED |
| REQ-FUNC-DC-03 | 功能 | P1 | 系统看板 | 温控面板 card（5 sub_type 含 living_room_main，product_code 120003+260001） | APPROVED |
| REQ-FUNC-DC-04 | 功能 | P1 | 系统看板 | 新风 card（product_code=130004，故障按记录条数） | APPROVED |
| REQ-FUNC-DC-05 | 功能 | P1 | 系统看板 | 水力模块 card（product_code=270001，故障按记录条数） | APPROVED |
| REQ-FUNC-DC-06 | 功能 | P1 | 系统看板 | 后端 dashboard/device-fault-summary 汇总接口 | APPROVED |
| REQ-FUNC-UX-01 | 功能 | P2 | 系统看板 | 4 组分组排列，组间分组标题行 | APPROVED |
| REQ-FUNC-UX-02 | 功能 | P2 | 系统看板 | 所有统计卡片 Hover 动效（复用 .stat-card） | APPROVED |
| REQ-FUNC-UX-03 | 功能 | P2 | 系统看板 | 新卡片可点击跳转指示（cursor: pointer） | APPROVED |
| REQ-NFR-PERF-01 | 非功能 | P1 | 系统看板 | 看板加载 P95 < 500ms | APPROVED |
| REQ-NFR-PERF-02 | 非功能 | P1 | 设备列表 | 凝露批量查询 | APPROVED |
| REQ-NFR-COMPAT-01 | 非功能 | P1 | 故障管理 | FaultManagementView 补充 sub_type 多值 URL 参数初始化 | APPROVED |
| REQ-NFR-STYLE-01 | 非功能 | P2 | 全局 | Design Token 一致性 | APPROVED |
