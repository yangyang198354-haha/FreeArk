# 代码评审报告 — v0.6.1-FM-UX 故障管理 UX 调整

```
file_header:
  document_id: CODE-REVIEW-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 代码自评报告
  author_agent: sub_agent_software_developer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/implementation/v0.6.1_fault_mgmt_ux/implementation_plan.md
    - docs/architecture/architecture_design_v0.6.1_fault_mgmt_ux.md
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
```

---

## 1. 实现概览

本版本（v0.6.1-FM-UX）共涉及 6 个文件，净增约 +133 行：

| # | 文件路径 | 操作 | 净变更行数 | 对应模块 |
|---|---------|------|-----------|---------|
| 1 | `FreeArkWeb/backend/freearkweb/api/device_name_cache.py` | 新增 | +101 行（含注释/docstring） | MOD-BE-UX-01 |
| 2 | `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py` | 追加 | +15 行 | MOD-BE-UX-02 |
| 3 | `FreeArkWeb/backend/freearkweb/api/serializers_fault.py` | 修改 | +25 行 | MOD-BE-UX-03 |
| 4 | `FreeArkWeb/frontend/src/components/Layout.vue` | 追加 | +1 行 | MOD-FE-UX-01 |
| 5 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 修改（删除） | -7 行（净删除） | MOD-FE-UX-02 |
| 6 | `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 多处修改 | +约 70 行（含注释净增） | MOD-FE-UX-03 |

实际净增约 +205 行（含注释和 docstring），可执行逻辑净增约 +133 行，与 implementation_plan 估计一致。

---

## 2. 自评清单

### 2.1 功能需求（FR）达成率：4/4 = 100%

| FR 编号 | 需求描述 | 达成 | 证据（文件:行号）|
|--------|---------|:----:|----------------|
| **FR-FM-UX-01** | 故障管理入口从设备列表右上角按钮移入左侧导航子菜单 | ✓ | `Layout.vue:53` 新增 `<el-menu-item index="/device-management/faults">故障管理</el-menu-item>`；`DeviceManagementDeviceListView.vue:14-21` 页头区域已简化为纯 `<div>` 包含 `<h2>` 和 `<p class="page-subtitle">`，右上角按钮已删除 |
| **FR-FM-UX-02** | 房号搜索控件改为 CascadingSelector，支持 specific_part icontains 容错 | ✓ | `FaultManagementView.vue:24-36` 引入 `CascadingSelector`，id 为 `fmBuilding/fmUnit/fmRoom`；`:281-294` 实现 `getSelectedSpecificPart()` 读取 hidden input 并组装参数；`:319-321` 传 `specific_part` 参数给后端（icontains） |
| **FR-FM-UX-03** | 故障列表"设备SN"列改为显示设备类型名称，三级降级渲染 | ✓ | `device_name_cache.py:37-50` 实现主路径 `get_device_name_by_sn()`；`serializers_fault.py:35-56` 新增 `device_name`/`device_type_label` 两个 `SerializerMethodField`；`FaultManagementView.vue:110-118` 前端三级降级渲染（device_name → device_type_label → device_sn+未识别 tag）|
| **FR-FM-UX-04** | 页面默认筛选"只看未恢复"，支持三态控件和 URL 参数优先 | ✓ | `FaultManagementView.vue:15-20` 三态 `<el-radio-group>`；`:221` 默认 `filterIsActive = ref('true')`；`:413-420` `onMounted` 读取 `route.query.is_active` 实现 URL 参数优先；`:334-339` `fetchFaultEvents` 三态传参逻辑 |

### 2.2 架构决策（ADR）落地率：6/6 = 100%

| ADR 编号 | 决策内容 | 落地 | 证据（文件:行号）|
|---------|---------|:----:|----------------|
| **ADR-UX-01** | 新增导航菜单子项 + 移除右上角按钮（方案B） | ✓ | `Layout.vue:53` 新增子项；`DeviceManagementDeviceListView.vue:14-21` 已简化，无 `justify-content: space-between` flex 布局，无 `<el-button>`，仅保留 `<div class="page-header">` 含 `<h2>` 和 `<p>` |
| **ADR-UX-02** | icontains 容错方案，前端组装 specific_part，不改后端参数名 | ✓ | `FaultManagementView.vue:281-294` `getSelectedSpecificPart()` 用 `document.getElementById` 读 hidden input 后组装 3 段字符串；`:319-321` 传 `params.specific_part = sp`；后端 `views_fault.py` 未改动 |
| **ADR-UX-03** | 进程内 dict 缓存，TTL=60s，懒加载，O(1) 查表 | ✓ | `device_name_cache.py:28-30` 模块级 `_cache/_cache_loaded_at/_TTL_SECONDS`；`:72-76` `_ensure_cache_fresh()` TTL 检查；`:79-100` `_load_cache()` 含延迟导入、去重逻辑、异常不崩溃 |
| **ADR-UX-04** | `<el-radio-group>` 三态，URL 参数优先，`filterIsActive` 独立变量 | ✓ | `FaultManagementView.vue:186-192` import 含 `useRoute`；`:192` `const route = useRoute()`；`:221` `const filterIsActive = ref('true')`；`:413-424` onMounted 初始化逻辑 |
| **ADR-UX-05** | `PRODUCT_CODE_LABELS` 追加到 `constants.py`，7 条硬编码映射 | ✓ | `constants.py:134-142` 新增 `PRODUCT_CODE_LABELS` 字典，7 条映射与用户裁决 OQ-05 完全一致 |
| **ADR-UX-06** | 不加锁，依赖 GIL 幂等性，模块 docstring 注明 | ✓ | `device_name_cache.py:15` docstring 明确说明"依赖 CPython GIL 保障基本 dict 操作原子性；不加锁（幂等重建）"，并注明 ADR-UX-06 |

### 2.3 架构层裁决（AQ）执行率：3/3 = 100%

| AQ 编号 | 裁决内容 | 执行 | 证据（文件:行号）|
|--------|---------|:----:|----------------|
| **AQ-01** | 懒加载方案A：首次 `get_device_name_by_sn` 调用时触发，不在 `AppConfig.ready()` 预热 | ✓ | `device_name_cache.py:49` `get_device_name_by_sn` 调用 `_ensure_cache_fresh()`；`:88` `_load_cache` 中延迟导入 `from .models import DeviceNode`；`apps.py` 未修改 |
| **AQ-02** | `document.getElementById('fmBuilding/fmUnit/fmRoom').value` 模式（与 DeviceManagementDeviceListView 第310-319行保持一致）| ✓ | `FaultManagementView.vue:283-285` 完全采用 `document.getElementById` 读取 hidden input，与设备列表同一模式 |
| **AQ-03** | `handleReset()` 将 `filterIsActive` 恢复为 `'true'`（与首次进入默认值一致）| ✓ | `FaultManagementView.vue:380` `filterIsActive.value = 'true'` 在 `handleReset` 中显式设置，注释标注 `FR-FM-UX-04 + AQ-03` |

---

## 3. 实现偏差

经逐行比对 implementation_plan 与实际落盘代码，发现以下轻微偏差，均属无害优化，**不影响需求达成，不需回滚**：

### 偏差-01：`device_name_cache.py` 行数超出估计

- **计划值**：约 80 行（净代码）
- **实际值**：101 行（含详细 docstring、模块注释、ADR 引用注释）
- **原因**：开发者添加了模块级 docstring（22 行），记录 AQ-01、ADR-UX-06 等架构决策，提高可维护性
- **影响**：零，注释不影响逻辑

### 偏差-02：`serializers_fault.py` 中 `get_device_type_label` 调用 `str(obj.product_code)` 而架构文档示例代码为 `obj.product_code`

- **计划值**（ARCH doc `serializers_fault.py` 示例）：`PRODUCT_CODE_LABELS.get(obj.product_code)`
- **实际值**（`serializers_fault.py:56`）：`PRODUCT_CODE_LABELS.get(str(obj.product_code))`
- **原因**：`FaultEvent.product_code` 字段为 `VARCHAR`，但生产 MQTT 报文中 `productCode` 值为整数（如 `270001`），Django ORM 可能保存为字符串或整数字符串；显式 `str()` 转换确保与 `PRODUCT_CODE_LABELS` key（均为字符串，如 `'270001'`）匹配
- **影响**：正向改善兜底一命中率，与需求意图一致；不存在副作用

### 偏差-03：`FaultManagementView.vue` 新增 `<p class="page-notice">` 提示文本

- **计划值**：implementation_plan 未提及新增页面提示文案
- **实际值**（`FaultManagementView.vue:7-10`）：新增了一段橙色提示框，说明"故障历史数据来自 MQTT 驱动写入，与设备列表页的实时故障数量统计独立"
- **原因**：提升用户理解，避免数据口径混淆
- **影响**：纯 UX 优化，无逻辑影响；CSS style 中新增 `.page-notice` 样式（`FaultManagementView.vue:446-456`）

### 偏差-04：`DeviceManagementDeviceListView.vue` 页头保留了外层 `<div class="page-header">` 包裹

- **计划值**（impl plan §TASK-05）："简化后页头区域直接包含 `<h2>` 和 `<p class="page-subtitle">` 两个元素，不用 flex 包裹"
- **实际值**（`DeviceManagementDeviceListView.vue:14-21`）：`<div class="page-header">` 包裹 `<div>` 再包裹 `<h2>` 和 `<p>`
- **原因**：保留语义化 `page-header` class 便于 CSS 一致性（全站统一，与其他页面同构）
- **影响**：无功能影响，HTML 结构与其他视图文件风格一致

---

## 4. 后续测试建议（移交 test-engineer）

### 4.1 单元测试（后端 Python）

| 优先级 | 测试对象 | 关键场景 | 建议工具 |
|--------|---------|---------|---------|
| P0 | `device_name_cache.get_device_name_by_sn` | 命中（mock DeviceNode 含 sn=22155）/ 未命中（返回 None）/ TTL 过期触发重建（mock `time.monotonic`）/ `invalidate_device_name_cache()` 后重建 / `_load_cache` 异常不崩溃 | Django TestCase + mock |
| P0 | `FaultEventSerializer` | 输出含 `device_name` 字段 / device_sn 命中 cache → device_name / cache miss + product_code 命中 PRODUCT_CODE_LABELS → device_type_label / 双 miss → 两字段均为 None | Django TestCase + APIClient |

### 4.2 集成测试

| 优先级 | 测试场景 | 验收标准 |
|--------|---------|---------|
| P1 | `GET /api/devices/fault-events/` 响应含 `device_name`/`device_type_label` 字段 | 字段存在，类型为 str 或 null |
| P1 | device_sn=22155（已知新风机 sn）序列化结果 | `device_name == "新风"` 或同一 DeviceNode.device_name 值 |
| P1 | 已有 `tests_fault_event.py` 中 `TestFaultEventSerializer.EXPECTED_FIELDS` 未包含新字段 | 需更新 `EXPECTED_FIELDS` 列表，补充 `device_name` 和 `device_type_label` 验证 |

### 4.3 前端手动验收（无 Jest 基建）

| 场景 | 验收标准 |
|------|---------|
| 左侧导航"设备管理"展开 | 子菜单含"设备列表"和"故障管理"两项，高亮逻辑正确 |
| `/device-management/device-list` 页头 | 无"故障管理"橙色按钮 |
| 进入 `/device-management/faults`（无 URL 参数）| radio-group "未恢复"默认高亮，接口请求含 `is_active=true` |
| 房号 CascadingSelector 选 `3-1-702` 后搜索 | 接口请求含 `specific_part=3-1-702`（浏览器 Network 面板验证）|
| 故障列表"设备名称"列 | 已知设备行显示中文名（如"新风"），兜底行显示 device_sn+"未识别"tag |
