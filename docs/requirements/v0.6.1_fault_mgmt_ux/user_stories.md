# 用户故事与验收标准

```
file_header:
  document_id: REQ-US-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 用户故事
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
    - docs/requirements/v0.6.0_fault_management/user_stories.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-28 | 初始草稿，覆盖 FR-FM-UX-01~04，每条需求含 1~2 个用户故事 |

---

## US-FM-UX-01：故障管理入口位置变更

### 用户故事

**US-FM-UX-01-A：通过导航菜单进入故障管理**

> As a 运维人员，
> I want to 在左侧"设备管理"子菜单中直接找到"故障管理"入口，
> So that 不必先进入设备列表页再点击按钮，导航路径更短。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-01-A-01 | Given 用户已登录，当前在任意页面，左侧导航"设备管理"子菜单处于收起状态 | When 用户点击"设备管理"展开子菜单 | Then 子菜单展开，显示"设备列表"和"故障管理"两个子项，顺序为：设备列表在前，故障管理在后 |
| AC-01-A-02 | Given 左侧"设备管理"子菜单已展开 | When 用户点击"故障管理"子项 | Then 路由跳转到 `/device-management/faults`，"故障管理"子项呈现激活高亮状态（蓝色/白色，与其他激活菜单项一致）|
| AC-01-A-03 | Given 用户当前在 `/device-management/faults` 页面 | When 用户刷新页面 | Then 左侧导航"设备管理"子菜单自动展开，"故障管理"子项保持激活高亮 |

---

**US-FM-UX-01-B：设备列表页右上角不再出现故障管理按钮**

> As a 运维人员，
> I want to 设备列表页右上角不出现冗余的"故障管理"跳转按钮，
> So that 页面结构更清晰，入口统一在左侧导航。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-01-B-01 | Given 用户已登录 | When 用户导航到 `/device-management/device-list` | Then 页面右上角不存在橙色（`type="warning"`）"故障管理"按钮；页头仅展示标题"设备列表"和副标题文字 |
| AC-01-B-02 | Given 设备列表页右上角按钮已移除 | When 用户在设备列表页正常使用搜索和查看功能 | Then 其他功能（搜索、分页、设备面板、PLC历史、设置按钮）行为不受影响 |

---

## US-FM-UX-02：房号搜索控件统一

### 用户故事

**US-FM-UX-02-A：在故障管理页用级联选择器选择具体房号**

> As a 运维人员，
> I want to 在故障管理页用与设备列表一致的级联选择器（楼栋/单元/房号三级）选择房号，
> So that 操作方式统一，不需要记住"3-1-702"格式后手动输入。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-02-A-01 | Given 用户在故障管理页 | When 用户点击"房号"控件 | Then 展开与设备列表相同样式的级联选择器，可逐级选择楼栋、单元、房号 |
| AC-02-A-02 | Given 级联选择器已展示 | When 用户在输入框直接输入 `3-1-702` | Then 自动匹配并选中"3栋1单元702号"，选择器显示 `3栋1单元702号` |
| AC-02-A-03 | Given 用户选中 `3栋1单元702号`（对应 specific_part 前缀 `3-1-`，后缀 `-702`） | When 用户点击"查询"按钮 | Then 列表只返回 `specific_part` 属于 `3-1-` 开头且 `-702` 结尾的故障记录（即 3 栋 1 单元 702 房的故障） |
| AC-02-A-04 | Given 用户选中"3栋1单元"（楼栋+单元，无具体房号） | When 用户点击"查询" | Then 列表返回所有 `specific_part` 以 `3-1-` 开头的故障记录（3 栋 1 单元所有房间） |
| AC-02-A-05 | Given 用户选中"3栋"（仅楼栋） | When 用户点击"查询" | Then 列表返回所有 `specific_part` 以 `3-` 开头的故障记录 |
| AC-02-A-06 | Given 级联选择器已选中某房号 | When 用户点击选择器的"×"清除按钮 | Then 房号过滤条件清空，下次查询返回不限房号的结果 |

---

**US-FM-UX-02-B：原文本输入框不再出现**

> As a 运维人员，
> I want to 故障管理页的"房号"过滤区只有级联选择器一种控件，
> So that 不存在两套交互方式引发混淆。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-02-B-01 | Given 用户在故障管理页 | When 页面加载完成 | Then 过滤栏中不存在 `placeholder="输入房号模糊搜索"` 的文本输入框，取而代之是 CascadingSelector 组件 |

---

## US-FM-UX-03：设备 SN 替换为设备类型名称

### 用户故事

**US-FM-UX-03-A：故障列表展示设备类型名称**

> As a 运维人员，
> I want to 故障列表的设备列显示"新风机"、"能耗表"、"水力模块"等设备类型名称，
> So that 不需要对照 SN 号码表即可快速识别是哪类设备出了故障。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-03-A-01 | Given `device_node` 表中存在记录：`device_sn=22155`，`device_name="新风机"`，且该记录关联的 `OwnerInfo.specific_part` 与某 `fault_event.specific_part` 相同 | When 故障管理接口返回含 `device_sn="22155"` 的故障记录 | Then 该响应中 `device_name` 字段值为 `"新风机"`；前端表格"设备名称"列显示文本 `"新风机"`，不出现 `"22155"` |
| AC-03-A-02 | Given `device_node` 表中不存在 `device_sn=99999` 的记录，但 `fault_event` 中存在该 SN，且 `product_code="270001"` | When 故障管理接口返回含 `device_sn="99999"` 的记录 | Then `device_name` 字段为 null，`device_type_label` 字段返回 `"水力模块"`（来自 `PRODUCT_CODE_LABELS["270001"]`）；前端显示 `"水力模块"` |
| AC-03-A-03 | Given `device_node` 无记录，且 `product_code` 无已知映射 | When 接口返回该记录 | Then `device_name` 和 `device_type_label` 均为 null；前端显示 `"22155（未识别）"` 或类似包含原始 SN 且有视觉提示的文本 |
| AC-03-A-04 | Given v0.6.0-FM 上线后写入的历史 fault_event 记录（`device_sn` 值不变） | When 故障管理接口查询历史数据 | Then 历史记录同样能正确返回 `device_name`（通过运行时 JOIN），不受写入时间影响 |

---

**US-FM-UX-03-B：原始 device_sn 不在主展示列**

> As a 运维人员，
> I want to 故障列表主要列区域不直接显示数字 SN，
> So that 列表更易读，减少无意义数字干扰运维判断。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-03-B-01 | Given 故障管理页表格已加载 | When 用户查看"设备名称"列 | Then 列标题为"设备名称"（或"设备类型"），不为"设备SN"；该列优先显示 `device_name`，其次 `device_type_label`，最后才回退到 `device_sn + （未识别）` |
| AC-03-B-02 | Given 接口响应中同时含 `device_sn`、`device_name` 字段 | When 前端渲染 | Then `device_sn` 字段仍在响应体中（供调试），但不作为独立列展示；`device_name` 列为主展示列 |

---

## US-FM-UX-04：默认筛选"只看未恢复"

### 用户故事

**US-FM-UX-04-A：首次打开故障管理页默认只看活跃故障**

> As a 运维人员，
> I want to 打开故障管理页时默认只看当前未恢复的故障，
> So that 立即看到需要处理的问题，不被已恢复记录干扰。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-04-A-01 | Given 用户已登录，`fault_event` 表中同时存在 `is_active=true` 和 `is_active=false` 的记录 | When 用户首次打开 `/device-management/faults`（URL 不带任何查询参数） | Then 筛选控件"未恢复"选项处于选中激活态；列表接口请求携带 `is_active=true`；返回结果全部为 `is_active=true` 的记录，`is_active=false` 的记录不在列表中 |
| AC-04-A-02 | Given 页面已加载，筛选控件当前为"未恢复" | When 用户切换到"全部" | Then 筛选控件"全部"选项激活；列表接口请求不携带 `is_active` 参数；返回结果包含所有记录（含已恢复）|
| AC-04-A-03 | Given 页面已加载，筛选控件当前为"未恢复" | When 用户切换到"已恢复" | Then 筛选控件"已恢复"选项激活；列表接口请求携带 `is_active=false`；返回结果全部为 `is_active=false`（已恢复）的记录 |

---

**US-FM-UX-04-B：URL 参数优先于默认值**

> As a 开发人员或运维人员，
> I want to 通过 URL 直接控制 is_active 筛选状态，
> So that 可以通过外部链接直接跳转到特定筛选状态的故障视图（如直链"全部故障"页）。

**验收标准：**

| ID | Given | When | Then |
|----|-------|------|------|
| AC-04-B-01 | Given 用户通过 URL `/device-management/faults?is_active=false` 进入故障管理页 | When 页面渲染完成 | Then 筛选控件"已恢复"选项处于激活态（而非默认的"未恢复"）；列表接口请求携带 `is_active=false` |
| AC-04-B-02 | Given 用户通过 URL `/device-management/faults?is_active=true` 进入 | When 页面渲染完成 | Then 筛选控件"未恢复"激活，列表携带 `is_active=true`（与默认行为一致）|
| AC-04-B-03 | Given 用户通过 URL `/device-management/faults`（无 `is_active` 参数）进入 | When 页面渲染完成 | Then 应用前端默认值：筛选控件"未恢复"激活，列表携带 `is_active=true` |

---

## 覆盖矩阵

| 需求编号 | 需求标题 | 用户故事 | AC 数量 |
|---------|---------|---------|--------|
| FR-FM-UX-01 | 故障管理入口位置变更 | US-FM-UX-01-A, US-FM-UX-01-B | 5 |
| FR-FM-UX-02 | 房号搜索控件统一 | US-FM-UX-02-A, US-FM-UX-02-B | 7 |
| FR-FM-UX-03 | 设备 SN 替换为设备类型名称 | US-FM-UX-03-A, US-FM-UX-03-B | 6 |
| FR-FM-UX-04 | 默认筛选"只看未恢复" | US-FM-UX-04-A, US-FM-UX-04-B | 6 |
| **合计** | | 8 个用户故事 | **24 条 AC** |
