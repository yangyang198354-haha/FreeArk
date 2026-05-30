# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.8.0-UI
  title: UI 修复批次 — 需求规格说明书
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.8.0-ui-fixes
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: APPROVED
  references:
    - FreeArkWeb/frontend/src/views/CondensationWarningView.vue
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - FreeArkWeb/frontend/src/views/DeviceManagementSettingsView.vue
    - FreeArkWeb/frontend/src/router/index.js
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-30 | 初始草稿，基于代码现状审阅整理 5 条 UI 修复需求 |
| 0.2.0-APPROVED | 2026-05-30 | 用户确认：返回方式改为同标签页内 router.push 跳转（方案2），废弃 window.open 新标签页方案；REQ-UI-002/003/004 相应更新 |

---

## 1. 背景与范围

### 1.1 背景

v0.7.0 结露预警管理页面发布后，用户反馈了若干 UI 一致性与交互问题。这些问题均为纯前端修改，不涉及后端 API 变更，也不涉及数据库结构调整。

### 1.2 涉及页面

| 页面 | 路由 | 组件文件 |
|------|------|---------|
| 结露预警管理 | /device-management/condensation-warnings | CondensationWarningView.vue |
| 故障管理 | /device-management/faults | FaultManagementView.vue |
| 设备面板 | /device-cards | DeviceCardsView.vue |
| 设备管理 - 设备列表 | /device-management/device-list | DeviceManagementDeviceListView.vue |

### 1.3 不在范围内

- 后端 API 接口变更
- 数据库模型变更
- 新增 MQTT 消费者或采集逻辑
- 其他页面（非上表所列）

---

## 2. 需求详述

### REQ-UI-001：结露预警页面 - 恢复状态开关文案修正

**来源**：用户反馈 #1

**现状（代码证据）**：
`CondensationWarningView.vue` 第 17-19 行：
```html
<el-radio-button value="true">未回复</el-radio-button>
<el-radio-button value="false">已回复</el-radio-button>
```
代码注释（第 190 行）也写有"label 用'回复'而非'恢复'"，这是已知与故障管理不一致的遗留问题。

**故障管理对比（FaultManagementView.vue 第 17-18 行）**：
```html
<el-radio-button value="true">未恢复</el-radio-button>
<el-radio-button value="false">已恢复</el-radio-button>
```
以及状态列 Tag（第 179 行）`{{ row.is_active ? '未恢复' : '已恢复' }}`。

**需求**：将结露预警页面的状态筛选按钮文案从"未回复/已回复"统一修改为"未恢复/已恢复"，与故障管理页面保持一致。

**变更范围**：`CondensationWarningView.vue` 模板区两处文案，无逻辑变更。

---

### REQ-UI-002：结露预警页面 - 新增"操作"列（设备面板链接）

**来源**：用户反馈 #2

**现状（代码证据）**：
`CondensationWarningView.vue` 表格共 12 列（第 68-142 行），最后一列为"恢复时间"，**无操作列**。

**参照目标（FaultManagementView.vue 第 183-194 行）**：
```html
<el-table-column label="操作" min-width="120" fixed="right">
  <template #default="{ row }">
    <el-button link type="primary" size="small" @click="handleViewDevicePanel(row)">
      查看设备面板
    </el-button>
  </template>
</el-table-column>
```
以及对应的 `handleViewDevicePanel` 函数（第 447-453 行）通过 `router.resolve` + `window.open` 在新标签页打开 `/device-cards?specific_part=...`。

**需求**：在结露预警表格最右侧新增"操作"列，`fixed="right"`，列宽 `min-width="120"`，列内提供一个 `el-button link type="primary" size="small"` 链接按钮，文案为**"设备面板"**（见 REQ-UI-003，与故障管理统一后的文案保持一致）。

**跳转方式（用户方案2确认，2026-05-30）**：点击时使用 `router.push` 在**当前标签页内**跳转到 `/device-cards?specific_part={row.specific_part}&from=condensation-warnings`。不再使用 `window.open('_blank')` 新标签页。

**注意**：结露预警页面当前使用 `<script setup>` 语法，需在 script 中引入 `useRouter`，添加 `handleViewDevicePanel` 函数。

---

### REQ-UI-003：故障管理页面 - "操作"列链接文案缩短

**来源**：用户反馈 #3

**现状（代码证据）**：
`FaultManagementView.vue` 第 190 行：
```html
查看设备面板
```

**需求**：将该按钮文案从"查看设备面板"改为"设备面板"，列宽可相应从 `min-width="120"` 收窄为 `min-width="100"`（可选，根据实际效果决定）。

**跳转方式调整（用户方案2确认，2026-05-30）**：故障管理的 `handleViewDevicePanel` 函数同步从 `window.open('_blank')` 改为 `router.push` 当前标签页跳转（见 REQ-UI-004）。

---

### REQ-UI-004：设备面板"返回"按钮 - 按来源页面动态返回

**来源**：用户反馈 #4

**现状（代码证据）**：
`DeviceCardsView.vue` `goBack()` 方法（第 237-241 行）：
```javascript
goBack() {
  if (window.history.length > 1) {
    this.$router.back()
  } else {
    this.$router.push('/device-management/device-list')
  }
},
```
当前逻辑：有历史记录时调用 `router.back()`，否则兜底到设备列表。

进入设备面板的三个来源（均改为同标签页跳转，用户方案2确认，2026-05-30）：
1. 设备管理 - 设备列表（`DeviceManagementDeviceListView.vue` 第 405 行）：`router.push('/device-cards?specific_part=...')`，同页跳转（已是正确方式，无需修改）。
2. 故障管理（`FaultManagementView.vue`）：**改为** `router.push` 当前标签页跳转，附加 `from=fault-management`。废弃原 `window.open('_blank')` 方式。
3. 结露预警（REQ-UI-002 新增）：使用 `router.push` 当前标签页跳转，附加 `from=condensation-warnings`。

**跳转方案（用户方案2，2026-05-30 最终确认）**：所有"设备面板"入口统一使用同标签页内 `router.push` 跳转，通过 query 参数 `from` 携带来源标识，设备面板"返回"按钮读取 `from` 参数路由回来源页。

**需求**：
1. 故障管理和结露预警在跳转到设备面板时，使用 `router.push` 并在 query 中附加 `from` 参数：
   - 故障管理：`from=fault-management`
   - 结露预警：`from=condensation-warnings`
   - 设备列表：无需修改（同页跳转，原有 `router.back()` 逻辑可正常工作）
2. `DeviceCardsView.vue` 的 `goBack()` 方法修改为读取 `$route.query.from`，按来源决定跳转目标：
   - `from=fault-management` → `router.push('/device-management/faults')`
   - `from=condensation-warnings` → `router.push('/device-management/condensation-warnings')`
   - `from=device-list` 或无 `from` 参数 → 保持现有逻辑（`router.back()` 或兜底设备列表）
3. "返回"按钮文案保持不变（仍为"返回"）。

**变更范围**：
- `FaultManagementView.vue`：`handleViewDevicePanel` 改为 `router.push`，附加 `from=fault-management`，删除 `router.resolve` + `window.open` 模式。
- `CondensationWarningView.vue`：`handleViewDevicePanel`（REQ-UI-002 新增）使用 `router.push`，附加 `from=condensation-warnings`。
- `DeviceCardsView.vue`：`goBack()` 方法改为读取 `from` 参数后按条件跳转。

---

### REQ-UI-005：设备面板 - 按钮样式统一与 Tab 导航栏分行布局

**来源**：用户反馈 #5

本需求拆分为两个子需求：

#### REQ-UI-005-A：返回与参数设置按钮样式统一 + 间距

**现状（代码证据）**：

`DeviceCardsView.vue` 头部（第 16-24 行）：
```html
<div class="panel-header-left">
  <el-button :icon="ArrowLeft" size="small" @click="goBack">返回</el-button>
  <h2 class="panel-title">设备面板</h2>
  <p class="page-subtitle">专有部分：{{ specificPart }}</p>
</div>
<div class="panel-header-right">
  <el-button type="warning" size="small" @click="goToSettings">参数设置</el-button>
</div>
```
CSS（第 537-573 行）：
- `.panel-page-header`：flex，`justify-content: space-between`，`padding: 12px 0`
- `.panel-header-left`：flex column，`gap: 4px`，按钮 `align-self: flex-start`
- `.panel-header-right`：flex，`align-items: center`，`padding-top: 2px`

当前问题：
1. "返回"按钮（`size="small"` + `icon`）与全站其他页面（如 `DeviceManagementSettingsView.vue` 第 10 行同款）视觉上接近，但 `DeviceCardsView` 中两个按钮分别位于 header 左侧和右侧，布局上可能导致"返回"按钮贴近左边缘，"参数设置"按钮贴近右边缘，缺少与页面内容区域的横向 margin。
2. "返回"按钮使用默认（无 type 属性），"参数设置"使用 `type="warning"` 黄色，但 `DeviceManagementSettingsView.vue` 的"返回"也是默认色，两处基本一致。全站其他操作按钮宽度、字体大小与这两个按钮是否一致需要统一。

**需求**：
1. 两个按钮统一尺寸规格：均使用 `size="small"`，最小宽度 `min-width: 80px`，字体大小跟随 Element Plus small button 默认（12px）。
2. 在 `.panel-page-header` 的 padding 中加入左右 margin（建议 `padding: 12px 16px`，即与 `.cards-grid` 的 `padding: var(--space-4)` 对齐），确保两个按钮不贴近页面左右边缘。
3. "参数设置"按钮保持 `type="warning"`（与现有设计一致），"返回"按钮保持默认样式（无 type）。

#### REQ-UI-005-B：设备面板 Tab 导航栏分行布局

**现状（代码证据）**：

`DeviceCardsView.vue` 导航栏（第 27-67 行）：所有 Tab 条目通过 `v-for` 遍历 `deviceData` 的 `sub_types`，以 `display: flex; flex-wrap: nowrap; overflow-x: auto` 横向单行平铺，顺序依赖后端数据返回顺序。

已知的 sub_type key 及对应分类（来自 TEMP_PARAMS / SWITCH_PARAMS 等常量推断，以及 `panel_study_room` 特殊处理逻辑第 31-43 行）：
- **温控面板组**（随房间数变化，4 个或 5 个）：
  - `panel_living_room`（客厅）
  - `panel_study_room`（书房/主卧）
  - `panel_bedroom`（次卧）
  - `panel_children_room`（儿童房）
  - `panel_fourth_children_room`（第二儿童房，5 房时存在）
- **公共设备组**（固定 4 个）：
  - `fresh_air`（新风）
  - `energy_meter`（能耗）
  - `hydraulic_module`（水力）
  - `air_quality`（空气）

当前布局问题：所有 Tab 依次平铺在一行，房间多时横向溢出需滚动，且无分类标识，不易区分"温控"与"公共设备"。

**需求**：
1. 将导航栏改为**两行布局**：
   - **第一行**：分类标签"温控面板 ▸"（含原有历史数据链接）+ 温控面板组各 Tab（按 `panel_living_room`、`panel_study_room`、`panel_bedroom`、`panel_children_room`、`panel_fourth_children_room` 顺序，5 房设备有 5 个，4 房设备有 4 个）
   - **第二行**：公共设备组各 Tab（`fresh_air` 新风、`energy_meter` 能耗、`hydraulic_module` 水力、`air_quality` 空气，顺序固定）
2. 两行各自 `flex-wrap: wrap`（而非 `nowrap`），宽度不足时自然换行，不再依赖横向滚动。
3. 行间有明确的视觉分隔（如 `border-top` 或 `padding-top` 间距）。
4. 每行可加分类文字标签（如"温控面板"、"系统设备"）以提升可读性，样式参考现有 `.nav-label` 但加粗区分。
5. 温控面板的"历史数据 ›"链接（`goToRoomHistory`）保留在温控面板行内。
6. 各子系统的"历史数据 ›"链接（`goToHistory`）保留在对应 Tab 内。

**实现约束**：
- 后端数据 `deviceData` 的结构不变（仍通过 `groupKey / subKey` 遍历），仅改前端渲染逻辑。
- 温控 Tab 的识别方式：`subKey` 以 `panel_` 开头，或通过已知 key 集合白名单判断。
- 公共设备 Tab 的识别方式：`subKey` 在 `['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']` 内。

---

## 3. 约束与假设

| ID | 类型 | 内容 |
|----|------|------|
| C-01 | 约束 | 所有修改仅限前端 Vue 组件，不涉及后端 API 或数据库 |
| C-02 | 约束 | 使用 Element Plus 组件库（已有依赖），不引入新 UI 库 |
| C-03 | 约束 | 不改变任何 API 请求参数或响应结构 |
| A-01 | 假设 | 结露预警记录的 `specific_part` 字段与故障管理相同格式，可直接用于 `/device-cards?specific_part=` 跳转 |
| A-02 | 假设 | 设备面板导航栏中温控 Tab 的 `subKey` 均以 `panel_` 开头，公共设备 Tab 的 `subKey` 为 `fresh_air / energy_meter / hydraulic_module / air_quality` 之一 |

---

## 4. 需求汇总表

| 需求 ID | 描述 | 涉及文件 | 优先级 | 依赖 |
|---------|------|---------|--------|------|
| REQ-UI-001 | 结露预警状态文案"回复"→"恢复" | CondensationWarningView.vue | P1 | 无 |
| REQ-UI-002 | 结露预警新增"操作"列（设备面板链接） | CondensationWarningView.vue | P1 | REQ-UI-003（文案对齐） |
| REQ-UI-003 | 故障管理链接文案"查看设备面板"→"设备面板" | FaultManagementView.vue | P1 | 无 |
| REQ-UI-004 | 设备面板返回按钮按来源动态跳转 | DeviceCardsView.vue、FaultManagementView.vue、CondensationWarningView.vue | P1 | REQ-UI-002 |
| REQ-UI-005-A | 返回/参数设置按钮样式统一 + 间距 | DeviceCardsView.vue | P2 | 无 |
| REQ-UI-005-B | 设备面板 Tab 导航栏分两行分类布局 | DeviceCardsView.vue | P2 | 无 |
