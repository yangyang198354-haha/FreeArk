# 用户故事 — 设备列表故障筛选

```
file_header:
  document_id: US-FFF-001
  project: FreeArk — freeark_device_list_fault_filter
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_requirement_analyst (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  depends_on: REQ-SPEC-FFF-001
  id_start: US-FFF-001（新序列）
```

---

## 故事地图概览

```
Epic: 通过故障筛选快速定位有问题的设备

  前端交互
    US-FFF-001  故障状态下拉控件
    US-FFF-002  重置时清除故障过滤

  后端过滤
    US-FFF-003  API has_fault 过滤
    US-FFF-004  API no_fault 过滤
    US-FFF-005  多条件 AND 叠加
    US-FFF-006  fault_count=None 设备排除

  分页联动
    US-FFF-007  分页 total 反映过滤后总数
```

---

## US-FFF-001：故障状态下拉控件

**来源**：REQ-FUNC-FFF-01

**As** 物业运维人员，
**I want** 在设备列表过滤栏看到"故障状态"下拉，可选"仅有故障"或"仅无故障"，
**So that** 我能快速筛选出当前有故障的设备进行处理，或确认无故障设备的范围。

**验收标准**：

- **AC-FFF-001-01**：Given 用户打开设备列表页，When 页面加载完成，Then 过滤栏中存在"故障状态"下拉（位于"运行模式"下拉之后），默认显示"故障状态"占位文字（未选择状态）。
- **AC-FFF-001-02**：Given 用户展开"故障状态"下拉，When 下拉列表出现，Then 可见三个选项：空占位（"故障状态"）、"仅有故障"、"仅无故障"。
- **AC-FFF-001-03**：Given 用户选择"仅有故障"，When 选项被选中，Then 立即触发 `handleSearch`，列表刷新，仅展示 `fault_count > 0` 的设备，分页 total 更新。
- **AC-FFF-001-04**：Given 用户选择"仅无故障"，When 选项被选中，Then 立即触发 `handleSearch`，列表仅展示 `fault_count == 0` 的设备，分页 total 更新。
- **AC-FFF-001-05**：Given 用户点击 clearable 清除按钮（×），When 选择被清空，Then 触发 `handleSearch`，故障状态过滤解除，列表恢复全量（含其他已生效的过滤条件）。

**依赖**：US-FFF-003（后端 has_fault 过滤）、US-FFF-004（后端 no_fault 过滤）

---

## US-FFF-002：重置时清除故障过滤

**来源**：REQ-FUNC-FFF-01 AC-FFF-01-04

**As** 物业运维人员，
**I want** 点击"重置"按钮时，故障状态下拉也一并清空，
**So that** 重置操作能还原到完全无过滤的基线状态，与其他过滤项行为一致。

**验收标准**：

- **AC-FFF-002-01**：Given 用户已选择"仅有故障"且列表处于过滤状态，When 用户点击"重置"按钮，Then "故障状态"下拉恢复空（未选择），其余所有过滤条件（楼栋/单元/大屏/PLC/开关/模式）同步清空，`currentPage` 重置为 1，列表刷新为全量。
- **AC-FFF-002-02**：Given 用户未选择任何过滤条件，When 用户点击"重置"按钮，Then 无异常，列表正常刷新。

**依赖**：US-FFF-001

---

## US-FFF-003：API has_fault 过滤

**来源**：REQ-FUNC-FFF-02

**As** 前端组件，
**I want** 向 `/api/device-management/device-list/?fault_status=has_fault` 发起请求，
**So that** 后端仅返回 `fault_count > 0` 的设备分页结果，且 `count` 为过滤后总数。

**验收标准**：

- **AC-FFF-003-01**：Given 请求 `GET /api/device-management/device-list/?fault_status=has_fault&page=1&page_size=20`，When 后端处理，Then 响应 `results` 数组中每条记录满足 `fault_count > 0`，`count` 等于当前满足条件的设备总数。
- **AC-FFF-003-02**：Given `fault_count=None` 的设备存在，When 请求 `?fault_status=has_fault`，Then 该设备不出现在结果中。
- **AC-FFF-003-03**：Given 后端使用 `get_fault_count_batch_cached` 获取故障数，When `fault_status=has_fault` 过滤执行，Then 不产生额外的直接 DB 查询（利用已有批量结果过滤）。

**依赖**：无（后端独立实现）

---

## US-FFF-004：API no_fault 过滤

**来源**：REQ-FUNC-FFF-02

**As** 前端组件，
**I want** 向 `/api/device-management/device-list/?fault_status=no_fault` 发起请求，
**So that** 后端仅返回 `fault_count == 0` 的设备，`count` 反映过滤后总数。

**验收标准**：

- **AC-FFF-004-01**：Given 请求 `GET /api/device-management/device-list/?fault_status=no_fault`，When 后端处理，Then 响应 `results` 中每条记录满足 `fault_count == 0`，`count` 等于过滤后总数。
- **AC-FFF-004-02**：Given `fault_count=None` 的设备，When 请求 `?fault_status=no_fault`，Then 该设备不出现（数据缺失不等同于无故障）。
- **AC-FFF-004-03**：Given 请求不含 `fault_status` 参数，When 后端处理，Then 行为与 v0.5.3-FCC 现有行为完全一致（无额外过滤）。

**依赖**：无

---

## US-FFF-005：多条件 AND 叠加

**来源**：REQ-FUNC-FFF-01 AC-FFF-01-05 / REQ-FUNC-FFF-02 AC-FFF-02-04

**As** 物业运维人员，
**I want** 同时使用"故障状态"和其他过滤条件（如"楼栋 3""PLC在线"），
**So that** 可以精确定位特定楼栋/状态下有故障的设备，AND 语义符合直觉。

**验收标准**：

- **AC-FFF-005-01**：Given 用户设置 `room_no=3`（楼栋3）且 `fault_status=has_fault`，When 请求发出，Then 结果为"楼栋3"AND"fault_count>0"的交集。
- **AC-FFF-005-02**：Given 用户设置 `plc_status=online` 且 `fault_status=has_fault`，When 请求发出，Then 结果为 PLC 在线 AND 有故障的交集。

**依赖**：US-FFF-003、US-FFF-004

---

## US-FFF-006：fault_count=None 设备在过滤时排除

**来源**：REQ-FUNC-FFF-02 AC-FFF-02-05

**As** 系统，
**I want** `fault_count=None` 的设备（PLCLatestData 无记录）在 `has_fault`/`no_fault` 过滤中均不出现，
**So that** 避免将数据缺失误判为"无故障"，保持数据准确性。

**验收标准**：

- **AC-FFF-006-01**：Given 某设备的 `specific_part` 在 `PLCLatestData` 中无任何相关记录（`fault_count=None`），When 请求 `?fault_status=has_fault`，Then 该设备不出现在结果中。
- **AC-FFF-006-02**：Given 同上设备，When 请求 `?fault_status=no_fault`，Then 该设备也不出现在结果中。
- **AC-FFF-006-03**：Given 同上设备，When 请求不含 `fault_status` 参数，Then 该设备正常出现（`fault_count` 字段值为 `null`，前端展示"—"）。

**依赖**：无

---

## US-FFF-007：分页 total 反映过滤后总数

**来源**：REQ-FUNC-FFF-03

**As** 物业运维人员，
**I want** 开启故障状态过滤后，页面底部分页的"共 N 条"数字是过滤后的真实条目数，
**So that** 我能准确了解当前有故障/无故障设备的总数，而不是全量设备数。

**验收标准**：

- **AC-FFF-007-01**：Given 全量设备 300 条，过滤后有故障设备 45 条，When 请求 `?fault_status=has_fault&page=1&page_size=20`，Then `count=45`，`results` 返回前 20 条，前端分页显示"共 45 条"。
- **AC-FFF-007-02**：Given 用户在第 2 页时切换"故障状态"筛选，When `handleSearch` 触发，Then `currentPage` 重置为 1（防止越界），发起 `page=1` 请求。

**依赖**：US-FFF-003、US-FFF-004
