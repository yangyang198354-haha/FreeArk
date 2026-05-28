# 手动 E2E 测试清单 — v0.6.1-FM-UX 故障管理 UX 调整

```
file_header:
  document_id: E2E-CHECKLIST-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 手动 E2E 测试清单
  author_agent: sub_agent_test_engineer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
```

---

## 前置条件

- 后端已部署（`git pull` + `sudo systemctl restart freeark-backend`）
- 前端已重新构建（`npm run build` 或本地 `npm run dev`）
- 已登录系统（任意有效用户账号）
- 浏览器 Network 面板已打开（用于验证请求参数）

---

## E2E 测试用例

### E2E-01：左侧导航"故障管理"入口可见且可达

| 项目 | 内容 |
|------|------|
| **前置** | 已登录，当前在任意页面（如系统看板） |
| **操作步骤** | 1. 在左侧导航栏点击"设备管理"子菜单展开符号（或直接点击"设备管理"标题） |
| | 2. 观察展开后的子菜单项列表 |
| | 3. 点击"故障管理"子项 |
| **预期结果** | 展开后看到"设备列表"和"故障管理"两个子项；点击"故障管理"后浏览器跳转到 `/device-management/faults`，左侧导航"故障管理"高亮；页面正常加载故障列表 |
| **对应需求** | FR-FM-UX-01 / ADR-UX-01 |
| **测试结论** | [ ] PASS   [ ] FAIL |
| **失败说明** | （如失败，填写实际观察到的现象） |

---

### E2E-02：设备列表页右上角"故障管理"按钮已移除

| 项目 | 内容 |
|------|------|
| **前置** | 已登录 |
| **操作步骤** | 1. 点击左侧导航"设备管理" → "设备列表" |
| | 2. 观察页面右上角区域（页头 `<div class="page-header">` 内） |
| **预期结果** | 页头仅含标题"设备列表"和副标题"查看和管理所有设备的运行状态"，**无**橙色"故障管理"按钮 |
| **对应需求** | FR-FM-UX-01 / ADR-UX-01 |
| **测试结论** | [ ] PASS   [ ] FAIL |
| **失败说明** | |

---

### E2E-03：房号 CascadingSelector 过滤正确传参

| 项目 | 内容 |
|------|------|
| **前置** | 在故障管理页（`/device-management/faults`），打开 Network 面板 |
| **操作步骤** | 1. 在"房号"级联选择器中逐级选择楼栋=3，单元=1，房号=702 |
| | 2. 点击"查询"按钮 |
| | 3. 查看 Network 中对 `/api/devices/fault-events/` 的请求 URL |
| **预期结果** | 请求 URL 含 `specific_part=3-1-702`（或等价的 URL 编码形式 `specific_part=3-1-702`）；返回结果中所有记录的 `specific_part` 均包含 `3-1-702` 子串（如 `3-1-7-702`） |
| **附加验证** | 点击"重置"后，CascadingSelector 清空（三个下拉均回到占位符），重新查询时无 `specific_part` 参数 |
| **对应需求** | FR-FM-UX-02 / ADR-UX-02 / AQ-02 |
| **测试结论** | [ ] PASS   [ ] FAIL |
| **失败说明** | |

---

### E2E-04：设备名称列显示三级降级渲染

| 项目 | 内容 |
|------|------|
| **前置** | 在故障管理页，已有故障数据（含已知 device_sn 的记录） |
| **操作步骤** | 1. 不过滤房号，点击"状态"选 **全部**，点击"查询" |
| | 2. 观察表格"设备名称"列 |
| **预期结果（三级降级）** | **主路径**：device_sn=22155 等生产数据行显示 "新风" 或对应 `DeviceNode.device_name` 中文名 |
| | **兜底一**：device_name 缓存未命中但 product_code 在映射表中，显示 "水力模块"/"能耗表" 等友好名 |
| | **兜底二**：两者皆无，显示原始 device_sn 数字字符串 + `[未识别]` 小标签 |
| **附加验证** | 表格中不再有"设备SN"列标题（已替换为"设备名称"） |
| **对应需求** | FR-FM-UX-03 / ADR-UX-03 / ADR-UX-05 |
| **测试结论** | [ ] PASS   [ ] FAIL |
| **失败说明** | |

---

### E2E-05：默认筛选"未恢复" + URL 参数优先

| 项目 | 内容 |
|------|------|
| **前置** | 打开 Network 面板 |
| **操作步骤（默认值）** | 1. 直接访问 `/device-management/faults`（无 URL 参数） |
| | 2. 观察 radio-group 初始状态和 Network 请求 |
| **预期结果（默认值）** | radio-group "未恢复"按钮高亮；Network 中自动发出的请求含 `is_active=true`；列表仅显示未恢复故障 |
| **操作步骤（URL 参数优先）** | 3. 在地址栏访问 `/device-management/faults?is_active=false` |
| | 4. 观察 radio-group 状态和请求 |
| **预期结果（URL 参数）** | radio-group "已恢复"按钮高亮；请求含 `is_active=false` |
| **操作步骤（全部）** | 5. 点击 radio-group 中的"全部"按钮 |
| **预期结果（全部）** | 请求不含 `is_active` 参数；列表显示全部记录（含已恢复） |
| **附加验证** | 点击"重置"后，radio-group 回到"未恢复"高亮状态 |
| **对应需求** | FR-FM-UX-04 / ADR-UX-04 / AQ-03 |
| **测试结论** | [ ] PASS   [ ] FAIL |
| **失败说明** | |

---

## 汇总

| E2E ID | 场景 | 结论 |
|--------|------|------|
| E2E-01 | 左侧导航"故障管理"入口 | [ ] PASS / [ ] FAIL |
| E2E-02 | 设备列表页按钮已移除 | [ ] PASS / [ ] FAIL |
| E2E-03 | CascadingSelector 参数传递 | [ ] PASS / [ ] FAIL |
| E2E-04 | 设备名称三级降级渲染 | [ ] PASS / [ ] FAIL |
| E2E-05 | 默认筛选 + URL 参数优先 | [ ] PASS / [ ] FAIL |

**用户完成手动测试后，请填写每项结论，并将此文档更新状态为 APPROVED 或 NEEDS_FIX。**

---

## 已知限制

| 限制 | 说明 |
|------|------|
| device_name 显示依赖 DeviceNode 数据 | 若生产 DeviceNode 表有更新（新设备树同步），需重启 backend 使 device_name_cache 在 TTL 过期后自动刷新（最长 60 秒延迟） |
| 房号过滤精度 | icontains 模糊匹配（ADR-UX-02），极端情况（如同一 specific_part 前缀出现多处）可能有误命中，但根据实测生产数据结构，此情况不存在 |
| 前端测试无自动化 | 目前无 Vitest/Playwright 基建，所有前端验证须手动操作 |
