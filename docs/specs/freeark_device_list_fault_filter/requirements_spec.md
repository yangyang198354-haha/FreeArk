# 需求规格说明书 — 设备列表故障筛选

```
file_header:
  document_id: REQ-SPEC-FFF-001
  project: FreeArk — freeark_device_list_fault_filter
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_requirement_analyst (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  context_snapshot: >
    FreeArk v0.5.3-FCC（hotfix commit 0b726c9），
    DeviceManagementDeviceListView.vue（现有过滤栏含：楼栋/单元/户号级联、大屏状态、
    PLC状态、系统开关、运行模式 五维过滤），
    API GET /api/device-management/device-list/ 当前支持 room_no/screen_status/
    system_switch/plc_status/operation_mode/page/page_size，
    fault_count 字段已在响应 results 中但无对应过滤参数，
    BUG-FCC-001 hotfix 已确立故障判定权威口径（compute_fault_count_for_sections
    按 available_sub_types 过滤），
    分页上限 50 条/页，screen_status 过滤走 Python 全量拉取后过滤
  depends_on:
    - BUG-FCC-001 RCA（docs/troubleshooting/BUG-FCC-001_list_vs_panel_mismatch.md）
    - v0.5.3-FCC fault_count 列实现（commit 1aff9c7 + 0b726c9）
  id_start: REQ-FUNC-FFF-01（新序列，避免与既有 REQ-FUNC-FC-* 冲突）
```

---

## 0. 文档说明

本文档描述"设备列表页面按故障有无筛选"功能的**完整需求规格**。

**前置阅读要求**：实现人员必须先阅读 `docs/troubleshooting/BUG-FCC-001_list_vs_panel_mismatch.md`，
特别是 §3（根因）和 §4（修复方案），理解故障判定口径后再动手。

**不在本次范围内**：
- 故障明细弹窗/导出
- 故障告警通知系统
- 移动端适配

---

## 1. 背景与目标

### 1.1 用户原始需求

> "设备列表页面，可以根据故障有无进行筛选。"

### 1.2 现状分析

v0.5.3-FCC 上线了"故障数量"列（`fault_count`），用户可以**看到**每台设备的故障数字，
但无法**快速过滤**出"有故障"或"无故障"的设备子集。当设备数量达到数百台时，
用户必须逐页翻找才能发现有问题的设备，效率低下。

### 1.3 目标

在现有过滤栏中新增"故障状态"筛选项，允许用户按"有故障 / 无故障 / 全部"三个维度过滤设备列表，
结合分页机制高效定位故障设备。

---

## 2. 功能需求

### REQ-FUNC-FFF-01：前端过滤控件新增"故障状态"下拉

**描述**：在 `DeviceManagementDeviceListView.vue` 的过滤栏中，紧跟"运行模式"下拉之后，
新增一个"故障状态" `el-select` 下拉控件，提供三个选项：
- 全部（清空选择，不过滤，默认状态）
- 仅有故障（`fault_status=has_fault`）
- 仅无故障（`fault_status=no_fault`）

**来源**：用户原始需求；与现有"大屏状态""PLC状态""系统开关""运行模式"过滤栏保持一致的 UI 模式

**验收标准（AC-FFF-01）**：

- **AC-FFF-01-01**：Given 用户在"故障状态"下拉选择"仅有故障"，When 点击搜索或选择项变更，Then 列表仅展示 `fault_count > 0` 的设备，分页 `total` 反映过滤后的实际条目数。
- **AC-FFF-01-02**：Given 用户选择"仅无故障"，When 点击搜索，Then 列表仅展示 `fault_count == 0` 的设备。
- **AC-FFF-01-03**：Given 用户未选择任何选项（clearable 清空），When 列表刷新，Then 故障状态不参与过滤，等同原有行为。
- **AC-FFF-01-04**：Given 用户点击"重置"按钮，When 重置执行，Then "故障状态"下拉恢复到未选择（空）状态，其余过滤条件同步清空。
- **AC-FFF-01-05**：Given "故障状态"过滤与其他过滤条件（楼栋/单元/PLC状态等）同时生效，When 发起请求，Then 各过滤条件 AND 叠加生效（与现有其他过滤项行为一致）。

---

### REQ-FUNC-FFF-02：后端 API 新增 `fault_status` 过滤参数

**描述**：`GET /api/device-management/device-list/` 新增可选查询参数 `fault_status`，
取值为 `has_fault`（`fault_count > 0`）或 `no_fault`（`fault_count == 0`）。
未传参数时行为与现在完全一致（不破坏既有契约）。

**来源**：REQ-FUNC-FFF-01 前端过滤联动；与后端现有 `plc_status`、`screen_status` 过滤参数模式一致

**实现约束**：
- 故障数查询必须使用 `fault_utils.get_fault_count_batch_cached`，不得绕过缓存层直接查 `PLCLatestData`。
- `fault_count=None` 的设备（PLCLatestData 无记录）：在 `has_fault` 过滤下排除，在 `no_fault` 过滤下也排除（语义：数据缺失，无法判断）。
- 由于 `fault_count` 不在 ORM `annotate` 层（故障数来自独立的 `PLCLatestData` 批量查询），该过滤必须走 **Python 层**（与 `screen_status` 过滤的处理方式相同）。
- 分页的 `total` 必须反映过滤后的实际条目数（与 `screen_status` 过滤机制保持一致）。

**验收标准（AC-FFF-02）**：

- **AC-FFF-02-01**：Given 请求 `?fault_status=has_fault`，When API 响应，Then `results` 中所有条目的 `fault_count > 0`，`count` 为过滤后总数。
- **AC-FFF-02-02**：Given 请求 `?fault_status=no_fault`，When API 响应，Then `results` 中所有条目的 `fault_count == 0`，`count` 为过滤后总数。
- **AC-FFF-02-03**：Given 请求不含 `fault_status` 参数，When API 响应，Then 行为与 v0.5.3-FCC 现有行为完全一致（`fault_count` 字段仍出现在结果中，无额外过滤）。
- **AC-FFF-02-04**：Given 请求 `?fault_status=has_fault&plc_status=online`，When API 响应，Then 结果为两个条件的交集（AND 逻辑）。
- **AC-FFF-02-05**：Given 某设备 `fault_count=None`（PLCLatestData 无记录），When 请求 `?fault_status=has_fault` 或 `?fault_status=no_fault`，Then 该设备不出现在结果中（数据缺失设备不参与判断）。
- **AC-FFF-02-06**：Given 请求 `?fault_status=invalid_value`，When API 响应，Then 忽略非法值，等同于未传该参数（容错处理，不返回 400）。

---

### REQ-FUNC-FFF-03：故障筛选时分页行为保持正确

**描述**：开启故障状态筛选后，分页控件展示的 `total` 为过滤后总条目数，
翻页行为与无过滤时一致。

**来源**：REQ-FUNC-FFF-01 / REQ-FUNC-FFF-02；防止分页与过滤联动时出现错误的总数显示

**验收标准（AC-FFF-03）**：

- **AC-FFF-03-01**：Given 过滤后总条目数为 N，When 前端展示分页，Then `el-pagination :total` 绑定值等于 N（而非全量设备总数）。
- **AC-FFF-03-02**：Given 用户在第 2 页时更改故障状态过滤，When `handleSearch` 触发，Then `currentPage` 重置为 1（与现有其他过滤项行为一致）。

---

## 3. 非功能需求

### REQ-NFR-FFF-01：性能——故障过滤不引入额外 DB 查询

**描述**：`fault_status` 过滤在 Python 层对已有的 `get_fault_count_batch_cached` 结果进行二次筛选，
不增加额外的 DB 查询（故障数已经在 step 9a 批量查询并缓存）。

**来源**：现有架构约束（`fault_utils.py` 严禁查询 `device_param_history` 表，仅查 `PLCLatestData`）

**验收标准**：Given 开启 `fault_status` 过滤，Then 后端 DB 查询数不超过不开启时的查询数（≤ 原有 N+1 基准，实际因批量查询仅 +1 SQL）。

### REQ-NFR-FFF-02：UI 一致性

**描述**：新增的"故障状态"过滤控件样式（宽度、`clearable`、`@change` 触发搜索）与现有"大屏状态""PLC状态"等 `el-select` 保持一致。

**来源**：前端一致性原则

**验收标准**：Given 新控件渲染，Then 宽度为 140px，具备 `clearable`，选择变更时自动触发搜索（`@change="handleSearch"`）。

### REQ-NFR-FFF-03：状态持久化（本期不做，记录为技术债）

**描述**：刷新页面不保留筛选状态（与现有其他过滤项行为一致，现有过滤项也不做 URL 路由同步）。
如未来有诉求，统一走路由 query 同步方案，不单独为故障筛选实现。

**来源**：PM 决策——保持与现有过滤栏行为一致，不单独引入复杂性

---

## 4. 故障判定语义（权威口径）

### 4.1 "有故障"的精确定义

`fault_count > 0`，其中 `fault_count` 由 `fault_utils.compute_fault_count_for_sections`（`get_fault_count_batch_cached`）返回，已含 BUG-FCC-001 hotfix：

- 对每个 `param_name`，通过 `_is_param_visible_for_section` 检查其 `sub_type` 是否在该专有部分的 `available_sub_types` 集合中。
- 户型不存在的房间字段（如 `fourth_children_room_communication_error` 但户型无第四儿童房）被排除，不计入故障数。
- `fresh_air_fault_status` 按位域 popcount 计算（每个置 1 的 bit = 1 个独立故障）。
- `comm_fault_timeout`、`error_<N>` 等 PLC 系统级字段（DeviceConfig 无条目）保留原行为，仍计入故障。

### 4.2 "无故障"的精确定义

`fault_count == 0`（PLCLatestData 有记录且经上述规则计算为 0）。

### 4.3 "数据缺失"的处理

`fault_count == None`（PLCLatestData 中无该 `specific_part` 的任何相关记录）：
前端展示"—"（现有行为），故障状态过滤时该设备不参与（既不算"有故障"也不算"无故障"）。

### 4.4 为什么不按"严重程度"或"特定 sub_type"细分

- 本期用户诉求仅为"有无"二元过滤，细分会增加 UI 复杂度且当前业务场景无此需求。
- 如未来需要按 sub_type 或严重程度筛选，可基于 `get_fault_details` API 单独设计。

---

## 5. 约束与设计边界

| 编号 | 约束 | 来源 |
|------|------|------|
| C-001 | 不修改 `fault_utils.py` 核心逻辑，本期只新增过滤参数 | 避免触碰已验证的 BUG-FCC-001 hotfix |
| C-002 | `fault_count` 过滤发生在 Python 层，不在 ORM annotate 层 | `PLCLatestData` 批量查询与 `OwnerInfo` queryset 属于不同数据流 |
| C-003 | 不引入新的 API 端点，在现有 `/api/device-management/device-list/` 上增量扩展 | 保持契约稳定 |
| C-004 | 不做前端纯客户端过滤（不能只过滤当前页，必须走后端以保证分页正确） | AC-FFF-02-01 / AC-FFF-03-01 |
| C-005 | `fault_status` 参数非法值静默忽略，不返回 400 | 防御性处理，与 `operation_mode` 非法值处理一致 |

---

## 6. 开放问题记录

| 编号 | 问题 | 当前决策 | 决策依据 |
|------|------|---------|---------|
| OQ-FFF-001 | "有故障"是否需要区分严重程度（如仅 CRITICAL） | **本期不做**：仅 fault_count > 0 二元判断 | 用户原始需求无此要求 |
| OQ-FFF-002 | 筛选状态是否需要 URL query 同步以便分享/刷新保持 | **本期不做**：与现有其他过滤项行为一致 | 保持一致性，避免单独引入复杂性 |
| OQ-FFF-003 | 开启"仅有故障"时，默认排序是否改为 fault_count 降序 | **本期不做**：排序保持 building/unit/room_number 升序不变 | 排序变更会改变分页语义，属于独立功能 |
| OQ-FFF-004 | `fault_count=None` 的设备是否需要单独的"数据缺失"筛选项 | **本期不做**：排除在两侧过滤之外 | 数据缺失属于设备配置问题，不是故障状态问题 |
