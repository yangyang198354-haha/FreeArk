# 架构设计文档

```
file_header:
  document_id: ARCH-v1.0.0-DASHBOARD-REDESIGN
  title: 系统看板重设计 + 设备列表凝露提醒列 — 架构设计
  author_agent: sub_agent_system_architect
  project: FreeArk 住宅能耗/暖通监控平台
  version: v1.0.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT
  references:
    - docs/requirements/v1.0.0_dashboard_redesign_device_condensation/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/views.py（device_management_device_list，已阅）
    - FreeArkWeb/backend/freearkweb/api/fault_utils.py（get_fault_count_batch_cached，已阅）
    - FreeArkWeb/backend/freearkweb/api/models.py（FaultEvent/CondensationWarningEvent/DeviceNode，已阅）
    - FreeArkWeb/backend/freearkweb/api/urls.py（已阅）
    - FreeArkWeb/frontend/src/views/HomeView.vue（已阅）
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue（已阅）
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue（已阅）
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 1.0.0-DRAFT | 2026-05-30 | 初始架构设计，增量设计，复用现有模式 |

---

## 1. 总体架构方向

本次变更为**纯增量式修改**，不引入新的中间件、服务进程或数据库表。所有改动在现有 Django REST + Vue 3 单体架构内完成，复用已有的 `LocMemCache` 缓存机制、`FaultEvent`/`CondensationWarningEvent`/`DeviceNode` 模型、以及前端现有 `stat-card` 样式体系。

**不涉及 freeark-fault-consumer 逻辑改动**（仅读取其写入的 FaultEvent 数据），无需重启 freeark-fault-consumer 服务。

---

## 2. 改动范围与模块映射

### 2.1 后端改动（views.py + urls.py，无新文件）

| 模块编号 | 位置 | 改动类型 | 说明 |
|---------|------|---------|------|
| MOD-BE-CL-01 | `api/views.py` → `device_management_device_list()` | 修改 | 在结果序列化段注入 `has_active_condensation` 字段，使用批量 IN 查询 |
| MOD-BE-DC-01 | `api/views.py` → 新函数 `dashboard_fault_summary()` | 新增 | `GET /api/dashboard/fault-summary/`，返回 active_fault_count + affected_unit_count |
| MOD-BE-DC-02 | `api/views.py` → 新函数 `dashboard_device_fault_summary()` | 新增 | `GET /api/dashboard/device-fault-summary/`，一次返回 4 类子设备的 total + fault_count |
| MOD-BE-URL-01 | `api/urls.py` | 修改 | 注册上述两条新路由 |

### 2.2 前端改动（3 个现有 Vue 文件，无新组件文件）

| 模块编号 | 位置 | 改动类型 | 说明 |
|---------|------|---------|------|
| MOD-FE-CL-01 | `DeviceManagementDeviceListView.vue` | 修改 | 在表格「故障数量」列之后插入「凝露提醒」列，展示 `has_active_condensation` |
| MOD-FE-DC-01 | `HomeView.vue` | 修改 | 新增 5 张统计卡片（故障总数 + 4 类子设备）；4 组分组重排；加载数据逻辑 |
| MOD-FE-FM-01 | `FaultManagementView.vue` | 修改 | `onMounted` 补充读取 `sub_type`（多值）+ `is_active` URL 参数并初始化过滤状态 |

---

## 3. 后端 API 设计

### 3.1 MOD-BE-CL-01：设备列表凝露提醒字段

**改动位置**：`views.py` → `device_management_device_list()` 函数，在 step 9（结果序列化）之前新增 step 9b。

**数据来源**：`CondensationWarningEvent` 模型，字段 `specific_part`（与 `OwnerInfo.specific_part` 格式一致）和 `is_active`。

**批量查询方案**（参照 `get_fault_count_batch_cached` 模式）：

```python
# 取当前页所有 specific_part
page_specific_parts = [owner.specific_part for owner in page_rows]

# 一次 IN 查询：获取有 is_active=True 的凝露预警的 specific_part 集合
from .models import CondensationWarningEvent
active_condensation_parts = set(
    CondensationWarningEvent.objects.filter(
        specific_part__in=page_specific_parts,
        is_active=True,
    ).values_list('specific_part', flat=True).distinct()
)
```

**响应字段注入**：在 results 列表每条记录中追加：
```json
"has_active_condensation": true | false
```

**性能约束满足**：一次 IN 查询覆盖当前页所有行，满足 REQ-NFR-PERF-02（不逐行查询）。`CondensationWarningEvent` 表体积远小于 `device_param_history`，无性能风险。

### 3.2 MOD-BE-DC-01：故障汇总接口

**路由**：`GET /api/dashboard/fault-summary/`

**权限**：`IsAuthenticated`（与现有 dashboard 接口一致）

**查询逻辑**：
```python
from .models import FaultEvent

active_qs = FaultEvent.objects.filter(is_active=True)
active_fault_count = active_qs.count()
affected_unit_count = active_qs.values('specific_part').distinct().count()
```

**响应格式**：
```json
{
  "success": true,
  "data": {
    "active_fault_count": <int>,
    "affected_unit_count": <int>
  }
}
```

**性能**：两条 COUNT 聚合 SQL，`FaultEvent` 表有 `is_active` 字段索引（已有 `idx_fault_time_active`），P95 < 500ms 可满足。

### 3.3 MOD-BE-DC-02：子设备故障汇总接口

**路由**：`GET /api/dashboard/device-fault-summary/`

**权限**：`IsAuthenticated`

**查询逻辑**（6 条 SQL，全部 COUNT 聚合，索引友好）：

```python
from .models import FaultEvent, DeviceNode

THERMOSTAT_SUB_TYPES = [
    'master_bedroom_panel', 'secondary_bedroom_panel',
    'children_room_panel', 'study_room_panel', 'living_room_main',
]

data = {
    'air_quality_sensor': {
        'total': DeviceNode.objects.filter(product_code='100007').count(),
        'fault_count': FaultEvent.objects.filter(
            sub_type='air_quality_sensor', is_active=True
        ).count(),
    },
    'thermostat_panels': {
        'total': DeviceNode.objects.filter(
            product_code__in=['120003', '260001']
        ).count(),
        'fault_count': FaultEvent.objects.filter(
            sub_type__in=THERMOSTAT_SUB_TYPES, is_active=True
        ).count(),
    },
    'fresh_air_unit': {
        'total': DeviceNode.objects.filter(product_code='130004').count(),
        'fault_count': FaultEvent.objects.filter(
            sub_type='fresh_air_unit', is_active=True
        ).count(),
    },
    'hydraulic_module': {
        'total': DeviceNode.objects.filter(product_code='270001').count(),
        'fault_count': FaultEvent.objects.filter(
            sub_type='hydraulic_module', is_active=True
        ).count(),
    },
}
```

**响应格式**：
```json
{
  "success": true,
  "data": {
    "air_quality_sensor":  { "total": <int>, "fault_count": <int> },
    "thermostat_panels":   { "total": <int>, "fault_count": <int> },
    "fresh_air_unit":      { "total": <int>, "fault_count": <int> },
    "hydraulic_module":    { "total": <int>, "fault_count": <int> }
  }
}
```

**product_code 类型说明**：`DeviceNode.product_code` 字段类型为 `CharField(max_length=20)`，查询时传字符串（`'100007'`），不传整数。

---

## 4. 前端模块设计

### 4.1 MOD-FE-CL-01：设备列表凝露提醒列

**改动文件**：`DeviceManagementDeviceListView.vue`

**模板改动**：在「故障数量」列（`prop="fault_count"`）之后、「操作」列之前插入：
```html
<el-table-column label="凝露提醒" width="100" align="center">
  <template #default="{ row }">
    <span :style="{ color: row.has_active_condensation ? '#E6A23C' : '#909399' }">
      {{ row.has_active_condensation ? '有' : '无' }}
    </span>
  </template>
</el-table-column>
```

**Script 改动**：无需新增 state 或 API 调用，`has_active_condensation` 直接来自后端 `device_management_device_list` 接口的 results 字段。

### 4.2 MOD-FE-DC-01：HomeView 新增卡片与分组重排

**改动文件**：`HomeView.vue`

**新增 reactive 状态**：
```javascript
const faultSummary = ref({ active_fault_count: 0, affected_unit_count: 0 })
const deviceFaultSummary = ref({
  air_quality_sensor:  { total: 0, fault_count: 0 },
  thermostat_panels:   { total: 0, fault_count: 0 },
  fresh_air_unit:      { total: 0, fault_count: 0 },
  hydraulic_module:    { total: 0, fault_count: 0 },
})
const loading = reactive({ ..., faultSummary: false, deviceFaultSummary: false })
```

**新增 API 调用函数**：
```javascript
const fetchFaultSummary = async () => {
  loading.faultSummary = true
  const res = await api.get('/api/dashboard/fault-summary/')
  if (res?.success) faultSummary.value = res.data
  loading.faultSummary = false
}

const fetchDeviceFaultSummary = async () => {
  loading.deviceFaultSummary = true
  const res = await api.get('/api/dashboard/device-fault-summary/')
  if (res?.success) deviceFaultSummary.value = res.data
  loading.deviceFaultSummary = false
}
```

**onMounted 中追加调用**：`fetchFaultSummary()` 和 `fetchDeviceFaultSummary()`。

**路由跳转函数**：
```javascript
const goToFaults = (subTypes = [], isActive = true) => {
  const query = { is_active: String(isActive) }
  if (subTypes.length > 0) query.sub_type = subTypes
  router.push({ name: 'FaultManagement', query })
}
```

**模板重构**：将原 `stats-cards` 区域替换为 4 组带分组标题的结构，所有新增卡片使用 `stat-card` class 复用 hover 动效，可点击卡片加 `cursor: pointer` 和 `@click` 事件。

**分组标题样式**（新增 CSS class `group-title`）：
```css
.group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  padding: 12px 0 6px;
  border-bottom: 1px solid var(--border-color-lighter);
  margin-bottom: 12px;
  letter-spacing: 0.5px;
}
```

### 4.3 MOD-FE-FM-01：FaultManagementView onMounted 补充参数读取

**改动文件**：`FaultManagementView.vue`

**现有状态**：`onMounted` 已读取 `route.query.is_active`，但未读取 `sub_type`。

**补充逻辑**（在现有 `urlIsActive` 读取之后追加）：
```javascript
// REQ-NFR-COMPAT-01: 读取 URL sub_type（单值字符串或多值数组）
const urlSubTypes = route.query.sub_type
if (urlSubTypes) {
  filters.sub_types = Array.isArray(urlSubTypes) ? urlSubTypes : [urlSubTypes]
} else {
  filters.sub_types = []
}
```

在 `fetchCategories()` 之后（或其 await 完成之后），确保调用 `fetchFaultEvents()` 触发一次查询。现有 onMounted 末尾已有 `fetchFaultEvents()` 调用，只需确保 `filters.sub_types` 在此之前已被赋值。

---

## 5. 数据流图

```
用户进入设备列表
  → 前端 GET /api/device-management/device-list/
  → 后端 device_management_device_list()
      → OwnerInfo.objects.all()（现有逻辑）
      → get_fault_count_batch_cached(page_specific_parts)（现有逻辑）
      → CondensationWarningEvent.objects.filter(
            specific_part__in=page_specific_parts, is_active=True
          ).values_list('specific_part', flat=True)  ← 新增一次 IN 查询
      → 序列化时注入 has_active_condensation
  → 前端渲染「凝露提醒」列

用户进入系统看板
  → 前端并发调用（但各自独立非阻塞）：
      GET /api/dashboard/summary/              （现有）
      GET /api/dashboard/plc-online-rate/      （现有）
      GET /api/dashboard/screen-online-rate/   （现有）
      GET /api/dashboard/total-energy/         （现有）
      GET /api/dashboard/power-status/         （现有）
      GET /api/dashboard/fault-summary/        ← 新增
      GET /api/dashboard/device-fault-summary/ ← 新增
  → 前端渲染 4 组分组卡片

用户点击子设备卡片
  → router.push({ name: 'FaultManagement', query: { sub_type: [...], is_active: 'true' } })
  → FaultManagementView onMounted 读取 query 参数
  → 初始化 filters.sub_types + filterIsActive
  → 自动触发 fetchFaultEvents()
```

---

## 6. ADR（架构决策记录）

### ADR-v100-01：凝露批量查询不缓存

**决策**：凝露批量 IN 查询不使用 LocMemCache 缓存。

**备选方案**：
- 方案 A（选定）：直接查询，不缓存
- 方案 B：仿照 `get_fault_count_batch_cached` 增加缓存

**理由**：`CondensationWarningEvent` 表体积远小于 `PLCLatestData`（凝露事件按住户/时间段计，预估数百行级别），IN 查询延迟可忽略。增加缓存会引入 TTL 过期带来的数据陈旧风险，且维护成本不值得。可在后续版本按需加入。

### ADR-v100-02：两个新 dashboard 接口不缓存

**决策**：`dashboard_fault_summary` 和 `dashboard_device_fault_summary` 均直查 DB，不缓存。

**备选方案**：
- 方案 A（选定）：直接 COUNT 聚合，不缓存
- 方案 B：添加 60s TTL 缓存

**理由**：FaultEvent 表已有 `idx_fault_time_active` 索引覆盖 `is_active` 过滤；DeviceNode 表按 `product_code` 有索引；COUNT 聚合代价极低（P95 << 500ms）。看板不是高频实时刷新场景，首次缓存收益低，先直查，必要时再加缓存。

### ADR-v100-03：HomeView 使用 router 实例

**决策**：HomeView.vue 已使用 `import { useRouter } from 'vue-router'`，直接复用。若未导入则需补充导入。

### ADR-v100-04：新增 API 函数位置

**决策**：两个新函数追加在 `views.py` 现有 dashboard 函数群之后，不新建文件。

**理由**：本次变更量小，现有 `views.py` 中所有 dashboard 接口已在一起（`dashboard_total_energy`、`dashboard_summary` 等），新增函数保持同一文件内聚合，便于维护。

---

## 7. 接口变更汇总表

| 接口 | 类型 | 影响范围 |
|------|------|---------|
| `GET /api/device-management/device-list/` | 修改（新增响应字段） | 向后兼容，前端新增列 |
| `GET /api/dashboard/fault-summary/` | 新增 | HomeView.vue |
| `GET /api/dashboard/device-fault-summary/` | 新增 | HomeView.vue |

---

## 8. 无数据库 migration 说明

本次变更**不引入新的 Django model**，不需要数据库 migration。所有改动均为：
- 后端：新增视图函数 + 新增 URL 路由 + 修改现有视图函数
- 前端：修改 3 个现有 Vue 文件

---

## 9. 需求覆盖矩阵

| 需求编号 | 对应模块 | 覆盖状态 |
|---------|---------|---------|
| REQ-FUNC-CL-01 | MOD-BE-CL-01 + MOD-FE-CL-01 | COVERED |
| REQ-FUNC-DC-01 | MOD-BE-DC-01 + MOD-FE-DC-01 | COVERED |
| REQ-FUNC-DC-02 | MOD-BE-DC-02 + MOD-FE-DC-01 | COVERED |
| REQ-FUNC-DC-03 | MOD-BE-DC-02 + MOD-FE-DC-01 | COVERED |
| REQ-FUNC-DC-04 | MOD-BE-DC-02 + MOD-FE-DC-01 | COVERED |
| REQ-FUNC-DC-05 | MOD-BE-DC-02 + MOD-FE-DC-01 | COVERED |
| REQ-FUNC-DC-06 | MOD-BE-DC-02 | COVERED |
| REQ-FUNC-UX-01 | MOD-FE-DC-01 | COVERED |
| REQ-FUNC-UX-02 | MOD-FE-DC-01（复用 .stat-card） | COVERED |
| REQ-FUNC-UX-03 | MOD-FE-DC-01（cursor: pointer） | COVERED |
| REQ-NFR-PERF-01 | MOD-BE-DC-01/DC-02（COUNT聚合+索引） | COVERED |
| REQ-NFR-PERF-02 | MOD-BE-CL-01（IN批量查询） | COVERED |
| REQ-NFR-COMPAT-01 | MOD-FE-FM-01 | COVERED |
| REQ-NFR-STYLE-01 | MOD-FE-DC-01（.stat-card + Design Token） | COVERED |
