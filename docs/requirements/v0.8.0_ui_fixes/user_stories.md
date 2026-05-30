# 用户故事清单

```
file_header:
  document_id: US-v0.8.0-UI
  title: UI 修复批次 — 用户故事清单
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.8.0-ui-fixes
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: APPROVED
  references:
    - docs/requirements/v0.8.0_ui_fixes/requirements_spec.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-30 | 初始草稿，对应 requirements_spec.md v0.1.0-DRAFT |
| 0.2.0-APPROVED | 2026-05-30 | 用户方案2确认：设备面板跳转改为同标签页 router.push，废弃 window.open 新标签页。US-UI-002/003/004 验收标准同步更新 |

---

## US-UI-001：结露预警状态筛选文案统一

**对应需求**：REQ-UI-001

**作为**一名运维人员，
**我希望**结露预警页面的状态筛选按钮显示"未恢复/已恢复"，
**以便**与故障管理页面的术语完全一致，避免混淆"回复"（应答行为）和"恢复"（状态恢复）的语义。

### 验收标准

**AC-UI-001-01：筛选按钮文案**
- Given：用户进入结露预警页面（`/device-management/condensation-warnings`）
- When：查看页面顶部状态筛选区的 el-radio-group
- Then：三个按钮文案分别为"未恢复"、"已恢复"、"全部"（原"未回复"、"已回复"、"全部"）

**AC-UI-001-02：筛选行为不变**
- Given：用户点击"未恢复"筛选按钮
- When：列表重新加载
- Then：仅显示 `is_active=true` 的结露预警记录，行为与修改前完全相同（仅文案变化，逻辑不变）

**AC-UI-001-03：默认状态一致**
- Given：用户首次进入结露预警页面（无 URL 参数）
- When：页面加载完成
- Then：默认选中"未恢复"（`filterIsActive` 初始值为 `'true'`），行为不变

---

## US-UI-002：结露预警表格增加"设备面板"操作列

**对应需求**：REQ-UI-002

**作为**一名运维人员，
**我希望**在结露预警列表中能直接点击进入对应设备的设备面板，
**以便**快速查看触发结露预警的设备实时参数，无需先跳转到设备列表再查找。

### 验收标准

**AC-UI-002-01：操作列存在**
- Given：用户进入结露预警页面，列表已加载数据
- When：查看表格右侧
- Then：最右侧存在一列，列标题为"操作"，固定在右侧（`fixed="right"`），`min-width="120"`

**AC-UI-002-02：操作列按钮**
- Given：结露预警列表中有至少一条数据
- When：用户查看每行的"操作"列
- Then：每行均有一个 `el-button link type="primary" size="small"` 按钮，文案为"设备面板"

**AC-UI-002-03：点击同标签页跳转（用户方案2，2026-05-30 更新）**
- Given：用户点击某条结露预警记录的"设备面板"按钮
- When：点击事件触发
- Then：在当前标签页内通过 `router.push` 跳转到 `/device-cards?specific_part={row.specific_part}&from=condensation-warnings`，不打开新标签页

**AC-UI-002-04：specific_part 正确传递**
- Given：结露预警记录的 `specific_part` 为 `"3-1-7-702"`
- When：用户点击该行的"设备面板"按钮
- Then：当前页面跳转后 URL 中 `specific_part` 参数值为 `"3-1-7-702"`（URL 编码），`from` 参数为 `"condensation-warnings"`

---

## US-UI-003：故障管理"操作"列文案缩短

**对应需求**：REQ-UI-003

**作为**一名运维人员，
**我希望**故障管理页面的"操作"列按钮文案改为简洁的"设备面板"，
**以便**与结露预警页面（REQ-UI-002）及设备列表页面（现有文案"设备面板"）保持全站一致。

### 验收标准

**AC-UI-003-01：文案变更**
- Given：用户进入故障管理页面（`/device-management/faults`），列表已加载数据
- When：查看表格"操作"列
- Then：按钮文案为"设备面板"（原"查看设备面板"）

**AC-UI-003-02：跳转方式（用户方案2，2026-05-30 更新）**
- Given：用户点击故障管理中某条记录的"设备面板"按钮
- When：点击事件触发
- Then：在当前标签页内通过 `router.push` 跳转到对应设备面板，URL 中 `specific_part` 参数正确，`from=fault-management`（不再使用 window.open 新标签页）

**AC-UI-003-03：全站一致性**
- Given：用户在设备列表、故障管理、结露预警三个页面分别查看"操作"列
- When：对比三个页面的跳转设备面板按钮
- Then：三处按钮文案均为"设备面板"，无一使用"查看设备面板"

---

## US-UI-004：设备面板"返回"按钮按来源页面动态跳转

**对应需求**：REQ-UI-004

**作为**一名运维人员，
**我希望**从不同页面进入设备面板后，点击"返回"按钮能回到我出发的那个页面，
**以便**在查看完设备参数后高效地继续处理故障或预警，而不是被跳转到无关的设备列表。

### 验收标准

**AC-UI-004-01：故障管理跳转时附带 from 参数**
- Given：故障管理页面 `handleViewDevicePanel` 函数通过 `router.resolve` 生成设备面板 URL
- When：生成的 URL
- Then：URL 中包含 `from=fault-management` query 参数，例如 `/device-cards?specific_part=3-1-7-702&from=fault-management`

**AC-UI-004-02：结露预警跳转时附带 from 参数**
- Given：结露预警页面（REQ-UI-002 新增的）`handleViewDevicePanel` 函数通过 `router.resolve` 生成设备面板 URL
- When：生成的 URL
- Then：URL 中包含 `from=condensation-warnings` query 参数

**AC-UI-004-03：来自故障管理时"返回"跳回故障管理（用户方案2，2026-05-30 更新）**
- Given：用户从故障管理页面点击"设备面板"按钮，通过 router.push 在当前标签页进入设备面板（URL 中含 `from=fault-management`）
- When：用户点击设备面板的"返回"按钮
- Then：当前标签页跳转到 `/device-management/faults`

**AC-UI-004-04：来自结露预警时"返回"跳回结露预警（用户方案2，2026-05-30 更新）**
- Given：用户从结露预警页面点击"设备面板"按钮，通过 router.push 在当前标签页进入设备面板（URL 中含 `from=condensation-warnings`）
- When：用户点击设备面板的"返回"按钮
- Then：当前标签页跳转到 `/device-management/condensation-warnings`

**AC-UI-004-05：无 from 参数或 from=device-list 时，原有逻辑不变**
- Given：用户从设备列表同页跳转进入设备面板（URL 无 `from` 参数，或 `from=device-list`）
- When：用户点击"返回"按钮
- Then：行为与修改前一致：`window.history.length > 1` 时 `router.back()`，否则跳转 `/device-management/device-list`

**AC-UI-004-06：from 参数为未知值时安全兜底**
- Given：URL 中 `from` 参数为非预定义值（如 `from=unknown`）
- When：用户点击"返回"按钮
- Then：兜底跳转到 `/device-management/device-list`，不抛出错误

---

## US-UI-005-A：设备面板按钮样式统一与页面边距

**对应需求**：REQ-UI-005-A

**作为**一名运维人员，
**我希望**设备面板顶部的"返回"和"参数设置"按钮外观与全站其他页面按钮一致，且不紧贴页面边缘，
**以便**视觉体验统一，按钮有足够的可点击区域。

### 验收标准

**AC-UI-005A-01：按钮尺寸一致**
- Given：用户进入设备面板页面
- When：查看顶部的"返回"和"参数设置"两个按钮
- Then：两个按钮均为 `size="small"`，最小宽度 `min-width: 80px`（通过 CSS 设置），字体大小与全站 small button 一致

**AC-UI-005A-02：页面左右边距**
- Given：用户进入设备面板页面
- When：查看顶部 header 区域
- Then：`.panel-page-header` 具有左右 padding（不小于 16px），"返回"按钮左侧不贴近页面左边缘，"参数设置"按钮右侧不贴近页面右边缘

**AC-UI-005A-03：与 DeviceManagementSettingsView 对比一致**
- Given：用户分别打开设备面板（`/device-cards`）和参数设置页面（`/device-management/device-settings`）
- When：对比两个页面的"返回"按钮
- Then：两处"返回"按钮视觉样式相同（均默认色 + ArrowLeft 图标 + small size）

---

## US-UI-005-B：设备面板 Tab 导航栏分两行分类布局

**对应需求**：REQ-UI-005-B

**作为**一名运维人员，
**我希望**设备面板的 Tab 导航栏按"温控面板"和"系统设备"分两行展示，
**以便**快速定位某类设备参数，不必在一长串 Tab 中水平滚动寻找。

### 验收标准

**AC-UI-005B-01：第一行显示温控面板 Tab**
- Given：用户进入某 4 房设备的设备面板
- When：查看 Tab 导航栏第一行
- Then：第一行包含分类标题"温控面板"及 4 个温控 Tab（客厅、主卧/书房、次卧、儿童房），每个 Tab 显示正确的房间名称

**AC-UI-005B-02：5 房设备第一行有 5 个 Tab**
- Given：用户进入某 5 房设备的设备面板（包含 `panel_fourth_children_room`）
- When：查看 Tab 导航栏第一行
- Then：第一行温控 Tab 共 5 个，第二个儿童房 Tab 也正确显示

**AC-UI-005B-03：第二行显示系统设备 Tab**
- Given：用户进入任意设备的设备面板
- When：查看 Tab 导航栏第二行
- Then：第二行显示"新风"、"能耗"、"水力"、"空气"4 个 Tab（固定，与房间数无关）

**AC-UI-005B-04：两行有明显视觉分隔**
- Given：用户进入设备面板
- When：查看 Tab 导航栏
- Then：第一行与第二行之间有可见的视觉分隔（border 或 padding-top ≥ 8px），用户能明确区分两个分类行

**AC-UI-005B-05：不依赖横向滚动**
- Given：用户在标准宽度（≥1024px）浏览器中查看设备面板
- When：查看 Tab 导航栏
- Then：所有 Tab 均在视口内可见，无需横向滚动（两行各自 flex-wrap 自然换行）

**AC-UI-005B-06："历史数据"链接保留**
- Given：用户进入设备面板，Tab 导航栏已渲染
- When：查看温控面板行
- Then：温控面板行内仍有"历史数据 ›"链接（`goToRoomHistory`），点击行为不变

**AC-UI-005B-07：各系统设备历史数据链接保留**
- Given：用户进入设备面板，Tab 导航栏已渲染
- When：查看第二行的各系统设备 Tab（`main_thermostat`、`fresh_air`、`energy_meter`、`hydraulic_module`）
- Then：对应 Tab 内仍有"历史数据 ›"链接，点击行为不变

---

## 用户故事汇总

| US ID | 标题 | 对应需求 | 验收标准数量 | 优先级 |
|-------|------|---------|------------|--------|
| US-UI-001 | 结露预警状态筛选文案统一 | REQ-UI-001 | 3 | P1 |
| US-UI-002 | 结露预警新增"设备面板"操作列 | REQ-UI-002 | 4 | P1 |
| US-UI-003 | 故障管理操作列文案缩短 | REQ-UI-003 | 3 | P1 |
| US-UI-004 | 设备面板返回按钮按来源动态跳转 | REQ-UI-004 | 6 | P1 |
| US-UI-005-A | 设备面板按钮样式统一与边距 | REQ-UI-005-A | 3 | P2 |
| US-UI-005-B | 设备面板 Tab 分两行分类布局 | REQ-UI-005-B | 7 | P2 |
