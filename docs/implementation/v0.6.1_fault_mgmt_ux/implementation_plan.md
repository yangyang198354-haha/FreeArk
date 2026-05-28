# 实现计划 — v0.6.1-FM-UX 故障管理 UX 调整

```
file_header:
  document_id: IMPL-PLAN-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 实现计划
  author_agent: sub_agent_software_developer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/architecture/module_design_v0.6.1_fault_mgmt_ux.md
    - docs/architecture/architecture_design_v0.6.1_fault_mgmt_ux.md
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
```

---

## 前置约束（架构层裁决补充）

| 编号 | 裁决内容 | 实现影响 |
|------|---------|---------|
| **AQ-01 = 懒加载方案 A** | `device_name_cache._load_cache()` 在首次 `get_device_name_by_sn()` 调用时懒加载，**不**在 `AppConfig.ready()` 预热 | `device_name_cache.py` 中 `_ensure_cache_fresh()` 通过 TTL 检查自动触发，无需 `apps.py` 改动 |
| **AQ-02 = `getElementById` 模式** | `FaultManagementView` 通过 `document.getElementById('fmBuilding/fmUnit/fmRoom').value` 读取 CascadingSelector 选中值 | 与 `DeviceManagementDeviceListView.vue:310-319` 现有写法一致，不引入 ref 实例属性 |
| **AQ-03 = 重置 → `'true'`（未恢复）** | `handleReset()` 将 `filterIsActive` 恢复为 `'true'`，与首次进入页面默认值一致 | `handleReset` 中显式设置 `filterIsActive.value = 'true'` |

---

## 任务清单（按执行顺序）

### TASK-01：新增 `api/device_name_cache.py`

| 属性 | 值 |
|------|---|
| 文件路径 | `FreeArkWeb/backend/freearkweb/api/device_name_cache.py` |
| 操作 | 新增 |
| 需求覆盖 | FR-FM-UX-03、OQ-03 |
| 模块 ID | MOD-BE-UX-01 |

**变更内容摘要**：
- 模块级 `_cache: dict[int, str]` + `_cache_loaded_at: float` + `_TTL_SECONDS = 60.0`
- `get_device_name_by_sn(sn: int) -> Optional[str]`：TTL 检查 + O(1) dict 查表
- `_ensure_cache_fresh()`：检查 TTL，过期则调 `_load_cache()`
- `_load_cache()`：延迟导入 `DeviceNode`，全量加载 distinct (device_sn, device_name)，去重取首条
- `invalidate_device_name_cache()`：手动失效钩子，将 `_cache_loaded_at` 置 0

**估计行数**：约 80 行

---

### TASK-02：修改 `api/fault_consumer/constants.py`

| 属性 | 值 |
|------|---|
| 文件路径 | `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py` |
| 操作 | 修改（末尾追加） |
| 需求覆盖 | FR-FM-UX-03、OQ-05 |
| 模块 ID | MOD-BE-UX-02 |

**变更内容摘要**：
- 在文件末尾 `FAULT_TYPE_LABELS` 字典之后追加 `PRODUCT_CODE_LABELS` 字典
- 映射内容：7 条 `product_code → 友好名`
- 不修改任何已有内容

**估计行数**：+12 行

---

### TASK-03：修改 `api/serializers_fault.py`

| 属性 | 值 |
|------|---|
| 文件路径 | `FreeArkWeb/backend/freearkweb/api/serializers_fault.py` |
| 操作 | 修改 |
| 需求覆盖 | FR-FM-UX-03 |
| 模块 ID | MOD-BE-UX-03 |

**变更内容摘要**：
- 新增 2 个 import：`get_device_name_by_sn`（from device_name_cache）、`PRODUCT_CODE_LABELS`（from fault_consumer.constants）
- 在 `FaultEventSerializer` 中新增 2 个 `SerializerMethodField`：`device_name`、`device_type_label`
- 新增对应 `get_device_name` 和 `get_device_type_label` 方法
- 在 `fields` 列表末尾追加 `'device_name'` 和 `'device_type_label'`
- 同步更新 `read_only_fields = fields`

**估计行数**：+25 行

---

### TASK-04：修改 `Layout.vue`

| 属性 | 值 |
|------|---|
| 文件路径 | `FreeArkWeb/frontend/src/components/Layout.vue` |
| 操作 | 修改（追加 1 行） |
| 需求覆盖 | FR-FM-UX-01 |
| 模块 ID | MOD-FE-UX-01 |

**变更内容摘要**：
- 在 `<el-sub-menu index="device-management">` 内，紧接 `设备列表` 子项后追加：
  `<el-menu-item index="/device-management/faults">故障管理</el-menu-item>`
- `<script>` 和 `<style>` 完全不改

**估计行数**：+1 行

---

### TASK-05：修改 `DeviceManagementDeviceListView.vue`

| 属性 | 值 |
|------|---|
| 文件路径 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` |
| 操作 | 修改（删除按钮，简化 flex 布局） |
| 需求覆盖 | FR-FM-UX-01 |
| 模块 ID | MOD-FE-UX-02 |

**变更内容摘要**：
- 删除页头 flex 容器外层 div（含 `style="display: flex; align-items: center; justify-content: space-between;"`）
- 删除内含的 `<el-button type="warning" @click="$router.push({ name: 'FaultManagement' })">故障管理</el-button>`
- 简化后页头区域直接包含 `<h2>` 和 `<p class="page-subtitle">` 两个元素，不用 flex 包裹
- `<script setup>` 和 `<style>` 完全不改

**估计行数**：-10 行（净删除）

---

### TASK-06：修改 `FaultManagementView.vue`

| 属性 | 值 |
|------|---|
| 文件路径 | `FreeArkWeb/frontend/src/views/FaultManagementView.vue` |
| 操作 | 修改（多处） |
| 需求覆盖 | FR-FM-UX-02、FR-FM-UX-03、FR-FM-UX-04 |
| 模块 ID | MOD-FE-UX-03 |

**变更内容摘要（template）**：
1. 删除 `.active-only-toggle` div 及内含 `<el-switch>`
2. 在 filter-bar 首个位置新增 `<el-form-item label="状态"><el-radio-group>` 三态控件
3. 删除 `<el-form-item label="房号"><el-input .../>` 文本框
4. 新增 `<el-form-item label="房号"><CascadingSelector ... ref="fmCascadingSelectorRef" />`，hidden input id 为 fmBuilding/fmUnit/fmRoom
5. 将 `<el-table-column prop="device_sn" label="设备SN">` 替换为 `<el-table-column label="设备名称">` 带三级降级渲染逻辑

**变更内容摘要（script）**：
1. 新增 `import { useRoute } from 'vue-router'`（补充）和 `import CascadingSelector from '@/components/CascadingSelector.vue'`
2. 新增 `const route = useRoute()` 和 `const filterIsActive = ref('true')`
3. 新增 `const fmCascadingSelectorRef = ref(null)`
4. 删除 `filters.specific_part` 字段 和 `filters.is_active_only` 字段
5. 新增 `getSelectedSpecificPart()` 函数
6. 修改 `onMounted`：先读取 `route.query.is_active` 初始化 `filterIsActive`（URL 参数优先）
7. 修改 `fetchFaultEvents`：删除 `filters.specific_part.trim()` 逻辑，改用 `getSelectedSpecificPart()`；删除 `filters.is_active_only` 逻辑，改用 `filterIsActive` 三态逻辑
8. 修改 `handleReset`：清空 CascadingSelector + 重置 `filterIsActive.value = 'true'`

**变更内容摘要（style）**：
- 删除 `.active-only-toggle { margin-bottom: 16px; }` CSS 块

**估计行数**：约 +50 / -25 行

---

## 不修改的文件

| 文件 | 原因 |
|------|------|
| `api/views_fault.py` | `specific_part` icontains 逻辑不变；`is_active` 过滤逻辑已支持三态 |
| `api/models.py` | `fault_event` schema 不变，不加 migration |
| `api/fault_consumer/*.py`（除 constants.py）| 故障消费主流程不变 |
| `frontend/src/components/CascadingSelector.vue` | 仅复用，不修改组件内部逻辑 |
| `frontend/src/router/index.js` | 路由 `FaultManagement`（`/device-management/faults`）已存在，不改 |

---

## 变更文件统计

| 文件 | 操作 | 估计净变更行数 |
|------|------|--------------|
| `api/device_name_cache.py` | 新增 | +80 行 |
| `api/fault_consumer/constants.py` | 追加 | +12 行 |
| `api/serializers_fault.py` | 修改 | +25 行 |
| `Layout.vue` | 追加 | +1 行 |
| `DeviceManagementDeviceListView.vue` | 删除 | -10 行 |
| `FaultManagementView.vue` | 多处修改 | +25 行（净） |
| **合计** | | **约 +133 行（净增）** |

---

## 实现层开放问题（如有）

暂无。所有架构决策已通过 AQ-01/AQ-02/AQ-03 裁决，实现路径明确。
