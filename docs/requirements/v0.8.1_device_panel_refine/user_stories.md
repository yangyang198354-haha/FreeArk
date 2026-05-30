# 用户故事与验收标准

```
file_header:
  document_id: US-v0.8.1-DEVICE-PANEL
  title: 设备面板精化 — 用户故事
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.8.1
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT — 待用户确认
  references:
    - docs/requirements/v0.8.1_device_panel_refine/requirements_spec.md
```

---

## US-001：顶部导航栏恢复单行形态（对应 REQ-UI-006）

**As** 运维人员，  
**I want** 设备面板顶部导航栏回到 v0.8.0 之前的单行形态，  
**So that** 我可以通过熟悉的单行 Tab 快速识别当前专有部分下的各子系统，不被分成两行的陌生布局困惑。

### 验收标准

**AC-001-1（模板结构）**
- Given 用户打开设备面板页面（有数据）
- When 页面渲染完成
- Then 顶部导航栏区域内不存在 `nav-row--thermostat` 和 `nav-row--system` 两个分行容器；不存在 `nav-row-separator` 分隔线元素

**AC-001-2（单行展示）**
- Given 用户打开设备面板页面（有数据）
- When 页面渲染完成
- Then 所有子系统 Tab 标签（温控面板类 + 系统设备类）展示在同一行内，与 commit `4765cf4` 原始版本视觉一致

**AC-001-3（历史数据链接保留）**
- Given 用户打开设备面板页面
- When 查看顶部导航栏
- Then "历史数据 ›"链接（`goToRoomHistory`）在导航栏中可见并可点击；点击后跳转到 RoomHistory 页面不报错

**AC-001-4（加载指示器保留）**
- Given 页面正在进行按需采集（`ondemandInFlight === true`）
- When 查看顶部导航栏
- Then 加载旋转图标和"采集中…"文字可见，功能不受导航栏复原影响

**AC-001-5（Script 清理）**
- Given 开发者审阅代码
- When 查看 DeviceCardsView.vue 的 `computed` 选项
- Then 不存在 `thermostatTabOrder`、`systemTabOrder`、`thermostatTabs`、`systemTabs` 四个计算属性

---

## US-002：详细数据面板卡片区温控/系统设备分两行显示（对应 REQ-UI-007）

**As** 运维人员，  
**I want** 设备面板下方的详细参数卡片按"温控面板"和"系统设备"分为两行展示，  
**So that** 我能一眼区分各房间温控状态（第一行）与系统设备状态（第二行），减少视觉混乱。

### 验收标准

**AC-002-1（温控行存在）**
- Given 用户打开设备面板页面且数据已加载
- When 查看详细数据面板卡片区
- Then 页面中存在一个"温控面板行"容器，其中包含且仅包含 `subKey` 以 `panel_` 开头的所有子类型卡片（如客厅、书房、次卧等，4 房 4 个，5 房 5 个）

**AC-002-2（系统设备行存在）**
- Given 用户打开设备面板页面且数据已加载
- When 查看详细数据面板卡片区
- Then 页面中存在一个"系统设备行"容器，其中包含且仅包含 `subKey` 属于 `['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']` 的子类型卡片

**AC-002-3（行间分隔）**
- Given 用户打开设备面板页面且数据已加载
- When 查看两行之间的区域
- Then 温控面板行与系统设备行之间有可识别的视觉分隔（行标题文字或分隔线），温控内容与系统设备内容不混排

**AC-002-4（卡片内容不变）**
- Given 用户打开设备面板页面且数据已加载
- When 查看任意一张子类型卡片
- Then 卡片内部的参数列表、显示值、格式化逻辑与 v0.8.0 相同（`.col-header`、`.params-list`、`.param-row` 结构不变）

**AC-002-5（响应式布局）**
- Given 用户在不同宽度的浏览器窗口下查看设备面板
- When 浏览器窗口宽度小于同时展示所有卡片所需的宽度
- Then 每行内卡片自动换行（不出现横向滚动条），布局不破损

---

## US-003：两行面板支持独立折叠（对应 REQ-UI-008）

**As** 运维人员，  
**I want** 温控面板行和系统设备行各自有收折/展开按钮，  
**So that** 当我只关注某一类设备时可以收起另一行，节省屏幕空间。

### 验收标准

**AC-003-1（默认展开）**
- Given 用户初次打开设备面板页面
- When 数据加载完成后查看详细面板区
- Then 温控面板行和系统设备行均处于展开状态，所有卡片可见

**AC-003-2（独立折叠——温控行）**
- Given 温控面板行处于展开状态
- When 用户点击温控面板行的折叠控件（箭头或收起按钮）
- Then 温控面板行的所有子类型卡片隐藏，行标题与折叠控件依然可见；系统设备行不受影响，保持原状态

**AC-003-3（独立折叠——系统设备行）**
- Given 系统设备行处于展开状态
- When 用户点击系统设备行的折叠控件
- Then 系统设备行的所有子类型卡片隐藏，行标题与折叠控件依然可见；温控面板行不受影响

**AC-003-4（再次点击展开）**
- Given 某行处于收折状态
- When 用户点击该行的折叠控件
- Then 该行的所有子类型卡片重新可见

**AC-003-5（切换 specificPart 后重置）**
- Given 用户在某专有部分下将温控行收起
- When 用户切换到另一个专有部分（`specificPart` 变更）
- Then 新专有部分的面板中两行均恢复展开状态

---

## US-004：故障参数值以红底白字标签展示（对应 REQ-UI-009）

**As** 运维人员，  
**I want** 当某设备参数处于故障状态时，其值以红色背景的标签样式显示，  
**So that** 我在扫视参数列表时能立刻注意到故障信息，比纯红色字体更加醒目。

### 验收标准

**AC-004-1（故障态有红色背景）**
- Given 某故障参数（`FAULT_PARAMS` 集合内或 `fresh_air_fault_bit_*`）的值不为 0
- When 该参数的值在参数列表中渲染
- Then 该值的显示元素有红色背景色（background-color 为红色），文字颜色为白色，外观呈徽章/标签形态（有内边距和圆角）

**AC-004-2（正常态无红色背景）**
- Given 某故障参数的值为 0
- When 该参数的值在参数列表中渲染
- Then 该值不显示红色背景，沿用 `.status-ok` 绿色字体样式，外观与 v0.8.0 正常态相同

**AC-004-3（其他参数不受影响）**
- Given 非故障参数（如温度、湿度、开关等）
- When 其值在参数列表中渲染
- Then 不显示任何背景色标签，保持原有文本样式

**AC-004-4（JS 逻辑不变）**
- Given 开发者审阅代码
- When 查看 `getValueClass`、`isStatusParam`、`FAULT_PARAMS` 相关代码
- Then 逻辑与 v0.8.0 完全一致，仅 CSS `.status-fault` 样式定义发生改变

---

## US-005：凝露提醒字段显示"无"或黄色"告警"标签（对应 REQ-UI-010）

**As** 运维人员，  
**I want** 各房间温控面板的"凝露提醒"字段显示语义化文字（而非裸数字 0/1），且告警状态有黄色视觉标识，  
**So that** 我无需记忆 0/1 的含义就能直接判断当前是否存在凝露风险。

### 验收标准

**AC-005-1（值 0 显示"无"）**
- Given 某房间的 `*_condensation_alert` 参数值为 `0`
- When 该参数在温控面板卡片中渲染
- Then 显示的文本为"无"，不显示裸数字 `0`

> **[PENDING-CONFIRM]** 此验收标准基于"0 是**无**"的解读（需用户确认，见 Q-001）

**AC-005-2（值 1 显示"告警"并带黄色标签）**
- Given 某房间的 `*_condensation_alert` 参数值为 `1`
- When 该参数在温控面板卡片中渲染
- Then 显示的文本为"告警"；该值的显示元素有黄色背景、深色文字，外观呈徽章/标签形态（有内边距和圆角）

**AC-005-3（值 0 无警告样式）**
- Given `*_condensation_alert` 参数值为 `0`
- When 该参数在参数列表中渲染
- Then 不显示黄色背景，不显示任何告警颜色（普通文本样式或绿色字体均可）

**AC-005-4（覆盖所有房间）**
- Given 页面展示了 4 房或 5 房的所有温控面板卡片
- When 查看每个面板中凝露提醒字段
- Then `living_room_condensation_alert`、`study_room_condensation_alert`、`bedroom_condensation_alert`、`children_room_condensation_alert`（以及 5 房时的 `fourth_children_room_condensation_alert`）均按上述映射规则显示，无遗漏

**AC-005-5（故障标签与凝露标签样式独立）**
- Given 同一个面板卡片中同时存在故障参数（非零）和凝露告警参数（值 1）
- When 两者均渲染
- Then 故障参数显示红底白字标签，凝露参数显示黄底深色字标签，两者样式相互独立，无混用

---

## 待确认项汇总

| ID | 关联用户故事 | 问题描述 | 请用户回复 |
|----|------------|---------|----------|
| Q-001 | US-005 / AC-005-1 | 凝露提醒值 `0` 的显示文本：用户原话"0 是五"疑为笔误，本文档采用"0 是**无**"。是否正确？ | 请确认：A) 正确，0 → "无" / B) 不正确，0 → "（请指定文字）" |
