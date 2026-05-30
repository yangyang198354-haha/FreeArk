# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.8.1-DEVICE-PANEL
  title: 设备面板精化 — 需求规格说明书
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.8.1
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT — 待用户确认
  references:
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue (v0.8.0, commit 3ad7afd)
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue (pre-v0.8.0, commit 4765cf4)
    - docs/requirements/v0.8.0_ui_fixes/requirements_spec.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-30 | 初始草稿，基于代码精确审阅产出（4 条需求：复原+3条新增） |

---

## 1. 背景与范围

### 1.1 背景

v0.8.0 已部署，其中 REQ-UI-005-B 的实现与用户真实意图不符：用户期望将"详细数据面板卡片区"分为两行（温控面板行 + 系统设备行），而 v0.8.0 错误地将"顶部导航栏 Tab 区"拆成了两行。v0.8.1 的目标是：

1. 撤销 v0.8.0 对顶部导航栏的两行改动，恢复原有单行导航栏形态。
2. 在正确的区域（详细数据面板卡片区）实现两行分类布局。
3. 新增三项 UI 细节改进：两行可折叠、故障红底标签、凝露提醒值映射与黄色标签。

### 1.2 涉及文件

| 文件 | 修改类型 |
|------|---------|
| `FreeArkWeb/frontend/src/views/DeviceCardsView.vue` | 唯一修改目标，所有改动均在此文件 |

### 1.3 不在范围内

- 后端 API 接口变更
- 数据库结构或业务逻辑变更
- 其他 Vue 组件文件
- 路由配置

---

## 2. 代码现状分析（需求锚定基础）

### 2.1 页面区域划分

DeviceCardsView.vue（v0.8.0 现状）包含以下两个关键区域，**本轮需求涉及的修改必须精确区分这两个区域**：

**区域 A：顶部导航栏 Tab 区**（HTML 第 27–84 行）
```html
<div class="panel-nav-bar">
  <!-- 第一行：温控面板组（v0.8.0 新增） -->
  <div class="nav-row nav-row--thermostat"> ... </div>
  <!-- 行间分隔（v0.8.0 新增） -->
  <div class="nav-row-separator" />
  <!-- 第二行：系统设备组（v0.8.0 新增） -->
  <div class="nav-row nav-row--system"> ... </div>
  <!-- 加载指示器 -->
  <div v-if="ondemandInFlight" class="nav-loading-indicator"> ... </div>
</div>
```
此区域在 v0.8.0 中被改为两行布局。**本轮需求要求恢复为单行。**

**区域 B：详细数据面板卡片区**（HTML 第 93–120 行）
```html
<div v-else class="cards-grid">
  <template v-for="(groupData, groupKey) in deviceData" :key="groupKey">
    <div v-for="(subTypeData, subKey) in groupData.sub_types" :key="subKey" class="subtype-col">
      <div class="col-header"> ... </div>
      <div class="params-list"> ... </div>
    </div>
  </template>
</div>
```
当前为 CSS Grid 自适应布局，所有子类型卡片平铺在一个网格中，无温控/系统设备分类。**本轮需求要求将此区域改为两行分类布局。**

### 2.2 v0.8.0 引入的需要撤销的改动

以下改动均在 commit `3ad7afd` 中引入，需在 v0.8.1 中撤销：

**模板层**（需撤销）：
- `nav-row nav-row--thermostat` 块（含 `thermostatTabs` 的遍历）
- `nav-row-separator` 分隔线
- `nav-row nav-row--system` 块（含 `systemTabs` 的遍历）

**Script 层**（需撤销的 computed 属性）：
- `thermostatTabOrder`：温控白名单数组
- `systemTabOrder`：系统设备白名单数组
- `thermostatTabs`：从 `deviceData` 提取温控 Tab 列表
- `systemTabs`：从 `deviceData` 提取系统设备 Tab 列表

**CSS 层**（需撤销）：
- `.nav-row` 样式块（含 `flex-wrap: wrap`, `padding: 4px 0`）
- `.nav-row-separator` 样式块
- `.nav-category-label` 样式块（加粗蓝色分类标签）
- `.panel-nav-bar` 的 `flex-direction: column` 改动（恢复为原 `flex-direction: row`）

### 2.3 故障信息渲染位置与现有样式（代码锚定）

**渲染位置**（第 111–116 行）：
```html
<span
  class="param-value"
  :class="getValueClass(param.param_name, param.value)"
>{{ formatValue(param.param_name, param.value) }}</span>
```

**判断逻辑**（第 478–483 行）：
```javascript
getValueClass(paramName, rawValue) {
  if (!this.isStatusParam(paramName)) return ''
  const v = rawValue === null || rawValue === undefined ? 0 : Number(rawValue)
  return v === 0 ? 'status-ok' : 'status-fault'
},
```

**现有故障样式**（CSS 第 824–828 行）：
```css
.status-fault {
  color: var(--color-status-fault);  /* 红色字体 */
  font-weight: 600;
}
```

当前：故障态（非零值）仅使用红色字体 + 加粗，**无背景色**。

**适用的故障参数范围**（`FAULT_PARAMS` 集合 + `fresh_air_fault_bit_*` 系列）：
- 温控面板各房间传感器故障字段（`*_temp_sensor_error`, `*_humidity_sensor_error`, 等）
- 新风机故障位（`fresh_air_fault_bit_0` 至 `fresh_air_fault_bit_8`）
- 通信故障字段（`*_communication_error`）
- 能耗表通信故障（`energy_meter_status_communication_error`）
- 空气质量传感器通信故障（`air_quality_sensor_communication_error`）

### 2.4 凝露提醒字段渲染位置与现有实现（代码锚定）

**匹配条件**（`formatValue` 方法第 561–564 行）：
```javascript
if (paramName === 'living_room_condensation_alert' ||
    paramName.endsWith('_condensation_alert')) {
  return String(v)   // 直接返回 "0" 或 "1"，未做语义映射
}
```

**值类别处理**：`getValueClass()` 当前对 `_condensation_alert` 参数**不返回任何 CSS class**（不在 `FAULT_PARAMS` 中，不以 `fresh_air_fault_bit_` 开头），因此凝露提醒字段目前：
- 无颜色区分
- 显示裸数字 `0` 或 `1`

**涉及的字段名称**（由命名规律推断，含覆盖所有房间的 5 个字段）：
- `living_room_condensation_alert`
- `study_room_condensation_alert`
- `bedroom_condensation_alert`
- `children_room_condensation_alert`
- `fourth_children_room_condensation_alert`

---

## 3. 需求详述

### REQ-UI-006：导航栏复原（撤销 v0.8.0 REQ-UI-005-B）

**类型**：修正（Revert）

**来源**：用户反馈，v0.8.0 REQ-UI-005-B 理解有误

**现状问题**：v0.8.0 将顶部导航栏 `.panel-nav-bar` 改成了两行（`nav-row--thermostat` + 分隔线 + `nav-row--system`），并新增了 `thermostatTabs`/`systemTabs` 计算属性和相关白名单数组。这与用户意图不符。

**需求**：将顶部导航栏 `.panel-nav-bar` 区域恢复为 v0.8.0 之前（commit `4765cf4`）的单行形态：
- 移除 `nav-row nav-row--thermostat`、`nav-row-separator`、`nav-row nav-row--system` 三个 div 及其内部全部内容。
- 恢复原先通过 `v-for` 遍历 `deviceData` 的单行 Tab 渲染方式。
- 移除 `thermostatTabOrder`、`systemTabOrder`、`thermostatTabs`、`systemTabs` 四个 computed 属性。
- 移除对应 CSS 类（`.nav-row`、`.nav-row-separator`、`.nav-category-label`、`.panel-nav-bar` 的 `flex-direction: column` 覆盖）。
- 恢复 `.panel-nav-bar` 为 `display: flex; flex-direction: row` 单行样式。
- "历史数据 ›"链接（`goToRoomHistory`）在复原后的单行导航中保留（位置参考 commit `4765cf4` 原始版本）。
- 加载指示器 `.nav-loading-indicator`（v0.5.6 引入）保留，不受此复原影响。

**验收关键点**：
- 复原后顶部导航栏与 commit `4765cf4` 中 `DeviceCardsView.vue` 的 `.panel-nav-bar` 结构完全一致（或功能等价）。
- 不存在 `thermostatTabs`、`systemTabs` 等新 computed 属性。

---

### REQ-UI-007：详细数据面板卡片区分两行布局

**类型**：新增

**来源**：用户需求 #2

**现状**：区域 B（`.cards-grid`）将所有子类型卡片（温控面板 + 系统设备）不加区分地平铺在 CSS Grid 中，无分类分行。

**需求**：将 `.cards-grid` 区域改为两行分类布局：
- **第一行（温控面板行）**：展示所有 `subKey` 以 `panel_` 开头的子类型卡片（`panel_living_room`、`panel_study_room`、`panel_bedroom`、`panel_children_room`，5 房时加 `panel_fourth_children_room`）。卡片排列方式：同行内横向 flex 或 grid，数量 4 或 5 个随实际数据。
- **第二行（系统设备行）**：展示 `subKey` 属于 `['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']` 的子类型卡片。
- 两行之间有明确的视觉分隔（建议行标题标签 + 分隔线，或独立的行容器 + margin）。
- 每行可加分类标题（如"温控面板"、"系统设备"），样式可参考现有 `.col-title`。
- 原 `.subtype-col` 卡片内部结构（`.col-header`、`.params-list`、`.param-row`）**不变**。
- 原 CSS Grid 的 `auto-fill minmax(280px, 1fr)` 响应式逻辑可在每行内部继续使用，或改为每行 flex-wrap。

**实现约束**：
- 后端 API 响应 `deviceData` 的数据结构不变，仅改前端渲染逻辑。
- 两行的识别逻辑：温控行 → `subKey.startsWith('panel_')`；系统设备行 → `subKey` 在系统设备白名单内。
- 不影响 `expandParams`、`formatValue`、`getValueClass` 等方法。

---

### REQ-UI-008：详细数据面板两行各自可折叠

**类型**：新增

**来源**：用户需求 #3

**前置依赖**：REQ-UI-007（两行布局必须先存在）

**现状**：卡片区（区域 B）无折叠功能（v0.8.0 中折叠功能已被 AC-UI-003-01/02 明确移除）。

**需求**：
- 温控面板行和系统设备行**各自独立**拥有收折/展开控件。
- **默认状态：两行均展开**（collapsed = false）。
- 展开时显示该行所有卡片；收折时隐藏所有卡片，仅保留行标题与折叠控件可见。
- 折叠控件样式：建议在行标题右侧放置一个可点击的箭头图标（Element Plus `ArrowDown`/`ArrowUp` icon）或展开/收起文字按钮。
- 折叠状态存储在组件 `data` 中（如 `thermostatRowCollapsed: false`、`systemRowCollapsed: false`），随路由切换 `specificPart` 时重置为展开。
- 折叠/展开动画可选（Element Plus `el-collapse-transition` 或简单 `v-show`，以实现难度为准）。

---

### REQ-UI-009：故障信息样式改为红底标签

**类型**：新增

**来源**：用户需求 #4

**现状（代码锚定）**：`.status-fault` 类仅设置红色字体（`color: var(--color-status-fault); font-weight: 600;`），无背景色。

**需求**：将故障态参数值的视觉样式从"红色字体"改为"红底白字标签（徽章）"：
- 背景色：红色（与 `var(--color-status-fault)` 或 `var(--color-danger)` 一致）。
- 文字颜色：白色（`#ffffff`）。
- 样式形态：内边距（如 `padding: 1px 6px`）+ 圆角（如 `border-radius: 4px`），呈徽章/标签外观。
- 字体：不再加粗（去除 `font-weight: 600`），改为普通字重，白底反差已足够醒目。

**变更范围**：仅修改 CSS 中 `.status-fault` 的样式规则，不修改任何 JS 逻辑、模板或 `getValueClass` 方法。

**正常态（`.status-ok`）不受影响**，保持现有绿色字体样式。

---

### REQ-UI-010：凝露提醒字段值映射 + 黄色告警标签

**类型**：新增

**来源**：用户需求 #5

**现状（代码锚定）**：`formatValue` 方法对 `_condensation_alert` 字段返回 `String(v)`，直接展示 `"0"` 或 `"1"`；`getValueClass` 不对此字段应用任何 CSS class。

**需求**：

#### 10.1 值映射
将 `formatValue` 中凝露提醒字段的返回值从 `String(v)` 改为语义化文本：
- `v === 0` → 显示 `"无"`
- `v === 1` → 显示 `"告警"`

> **[PENDING-CONFIRM]** 用户原话为"0 是五"，疑为"0 是**无**"的笔误（语音/输入误差）。本文档采用"0 → 无"解读。**请用户在确认需求时明确验证此语义是否正确。**

#### 10.2 样式区分
- `v === 0`（"无"）：使用无特殊样式的普通文本，或沿用正常态的绿色字体（`.status-ok` 类），与故障参数"正常"态保持视觉一致。
- `v === 1`（"告警"）：使用**黄底深色字标签**样式（独立 CSS 类 `.status-condensation-alert`），视觉形态与 REQ-UI-009 的红底故障标签同款，区别在于颜色：
  - 背景色：黄色（建议 `#faad14` 或 `var(--el-color-warning, #e6a23c)`）
  - 文字颜色：深色（`#7d4e00` 或 `#333`，确保对比度）
  - 内边距与圆角同 REQ-UI-009

#### 10.3 实现方式
- `formatValue`：修改 `_condensation_alert` 分支的返回值。
- `getValueClass`：新增对 `_condensation_alert` 字段的判断，`v === 1` 时返回 `'status-condensation-alert'`，`v === 0` 时返回 `'status-ok'`（或空字符串）。
- CSS：新增 `.status-condensation-alert` 样式类。
- **不需要**修改 `FAULT_PARAMS` 集合（凝露提醒不属于故障参数，两种样式独立维护）。

---

## 4. 约束与假设

| ID | 类型 | 内容 |
|----|------|------|
| C-01 | 约束 | 所有修改仅限 `DeviceCardsView.vue`，不涉及后端 API 或数据库 |
| C-02 | 约束 | 使用 Element Plus 已有组件与 CSS 变量，不引入新依赖 |
| C-03 | 约束 | 后端数据结构（`deviceData` 响应格式）不变 |
| C-04 | 约束 | 折叠功能（REQ-UI-008）不影响已渲染的 params 数据，仅控制显示/隐藏 |
| A-01 | 假设 | 温控子类型 `subKey` 均以 `panel_` 开头（白名单：`panel_living_room`, `panel_study_room`, `panel_bedroom`, `panel_children_room`, `panel_fourth_children_room`） |
| A-02 | 假设 | 系统设备子类型 `subKey` 固定为 `fresh_air`, `energy_meter`, `hydraulic_module`, `air_quality` |
| A-03 | 待确认 | 凝露提醒值 `0` 的语义为"无"，用户原话"0 是五"疑为"无"的笔误——**需用户确认** |

---

## 5. 需求汇总表

| 需求 ID | 描述 | 类型 | 变更区域 | 优先级 | 依赖 |
|---------|------|------|---------|--------|------|
| REQ-UI-006 | 顶部导航栏复原（撤销 v0.8.0 两行布局） | 修正 | 模板+Script+CSS | P0（必须先做） | 无 |
| REQ-UI-007 | 详细数据面板卡片区分两行（温控行+系统设备行） | 新增 | 模板+CSS | P1 | REQ-UI-006 |
| REQ-UI-008 | 两行面板可折叠，默认展开 | 新增 | 模板+data+CSS | P2 | REQ-UI-007 |
| REQ-UI-009 | 故障信息样式改为红底白字标签 | 新增 | CSS only | P1 | 无 |
| REQ-UI-010 | 凝露提醒 0→"无"/1→"告警"（黄色标签） | 新增 | formatValue+getValueClass+CSS | P1 | 无 |

---

## 6. 待确认项（用户需在开发前回复）

| ID | 来源需求 | 问题 | 选项 |
|----|---------|------|------|
| Q-001 | REQ-UI-010 | 凝露提醒 `v === 0` 的显示文本：用户原话"0 是五"是否为"0 是**无**"的笔误？ | A: 是，0 → "无" / B: 不是，0 → "五"（或其他文字，请指定） |
