# 模块设计文档

```
file_header:
  document_id: MOD-v1.0.0-DASHBOARD-REDESIGN
  title: 系统看板重设计 + 设备列表凝露提醒列 — 模块设计
  author_agent: sub_agent_system_architect
  project: FreeArk 住宅能耗/暖通监控平台
  version: v1.0.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v1.0.0_dashboard_redesign.md
    - docs/requirements/v1.0.0_dashboard_redesign_device_condensation/requirements_spec.md
```

---

## 模块清单

| 模块编号 | 类型 | 文件 | 操作 | 依赖需求 |
|---------|------|------|------|---------|
| MOD-BE-CL-01 | 后端 | `api/views.py` → `device_management_device_list` | 修改 | REQ-FUNC-CL-01, REQ-NFR-PERF-02 |
| MOD-BE-DC-01 | 后端 | `api/views.py` → `dashboard_fault_summary`（新函数） | 新增 | REQ-FUNC-DC-01, REQ-FUNC-DC-06 |
| MOD-BE-DC-02 | 后端 | `api/views.py` → `dashboard_device_fault_summary`（新函数） | 新增 | REQ-FUNC-DC-02~06 |
| MOD-BE-URL-01 | 后端 | `api/urls.py` | 修改 | MOD-BE-DC-01, MOD-BE-DC-02 |
| MOD-FE-CL-01 | 前端 | `DeviceManagementDeviceListView.vue` | 修改 | REQ-FUNC-CL-01 |
| MOD-FE-DC-01 | 前端 | `HomeView.vue` | 修改 | REQ-FUNC-DC-01~06, REQ-FUNC-UX-01~03 |
| MOD-FE-FM-01 | 前端 | `FaultManagementView.vue` | 修改 | REQ-NFR-COMPAT-01 |

---

## MOD-BE-CL-01：device_management_device_list 修改规范

### 改动位置

`views.py` → `device_management_device_list()` 函数，在 step 9a（批量获取故障数量）之后、结果序列化循环之前，插入 step 9b。

### 插入代码（step 9b）

```python
# ---- 9b. 批量获取凝露提醒状态（REQ-FUNC-CL-01, REQ-NFR-PERF-02）----
from .models import CondensationWarningEvent
page_specific_parts_for_cond = [owner.specific_part for owner in page_rows]
active_condensation_set = set(
    CondensationWarningEvent.objects.filter(
        specific_part__in=page_specific_parts_for_cond,
        is_active=True,
    ).values_list('specific_part', flat=True).distinct()
)
```

### 响应字段追加

在 `results.append({...})` 中，`fault_count` 字段之后追加：
```python
'has_active_condensation': owner.specific_part in active_condensation_set,
```

### 变更影响评估

- **向后兼容**：仅新增字段，不修改现有字段，前端旧版本自动忽略新字段
- **查询开销**：新增 1 次 IN 查询（`CondensationWarningEvent` 表），不影响现有 ORM 链路
- **缓存**：不添加缓存（见 ADR-v100-01）

---

## MOD-BE-DC-01：dashboard_fault_summary 函数规范

### 函数签名

```python
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_fault_summary(request):
    """GET /api/dashboard/fault-summary/
    返回当前未恢复故障总数及影响户数（specific_part 去重计数）。
    REQ-FUNC-DC-01 / US-DC-01
    """
```

### 完整实现逻辑

```python
from .models import FaultEvent

active_qs = FaultEvent.objects.filter(is_active=True)
active_fault_count = active_qs.count()
affected_unit_count = active_qs.values('specific_part').distinct().count()

return Response({
    'success': True,
    'data': {
        'active_fault_count': active_fault_count,
        'affected_unit_count': affected_unit_count,
    }
})
```

### 错误处理

使用 `try/except Exception` 包裹，返回 `{'success': False, 'error': str(e)}`，HTTP 500。

---

## MOD-BE-DC-02：dashboard_device_fault_summary 函数规范

### 函数签名

```python
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_device_fault_summary(request):
    """GET /api/dashboard/device-fault-summary/
    一次返回四类子设备的 total（DeviceNode）和 fault_count（FaultEvent is_active）。
    REQ-FUNC-DC-02~06 / REQ-FUNC-DC-06
    """
```

### 常量定义（在函数内部）

```python
THERMOSTAT_SUB_TYPES = [
    'master_bedroom_panel',
    'secondary_bedroom_panel',
    'children_room_panel',
    'study_room_panel',
    'living_room_main',
]
```

### 完整实现逻辑

```python
from .models import FaultEvent, DeviceNode

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

return Response({'success': True, 'data': data})
```

### product_code 类型注意

`DeviceNode.product_code` 为 `CharField`，查询时必须用字符串（`'100007'`），不得用整数（`100007`）。

---

## MOD-BE-URL-01：urls.py 新增路由规范

在现有 `dashboard/power-status/` 路由之后追加：
```python
path('dashboard/fault-summary/', views.dashboard_fault_summary, name='dashboard-fault-summary'),
path('dashboard/device-fault-summary/', views.dashboard_device_fault_summary, name='dashboard-device-fault-summary'),
```

---

## MOD-FE-CL-01：DeviceManagementDeviceListView.vue 改动规范

### 模板改动

在 `<el-table>` 中，找到「故障数量」列（`label="故障数量"`）之后，「操作」列（`label="操作"`）之前，插入：

```html
<!-- REQ-FUNC-CL-01: 凝露提醒列 -->
<el-table-column label="凝露提醒" width="100" align="center">
  <template #default="{ row }">
    <span :style="{ color: row.has_active_condensation ? '#E6A23C' : '#909399', fontWeight: 600 }">
      {{ row.has_active_condensation ? '有' : '无' }}
    </span>
  </template>
</el-table-column>
```

### Script 改动

无需任何 script 改动。`has_active_condensation` 字段直接来自后端响应，`fetchList()` 已将响应 results 直接赋给 `tableData`。

---

## MOD-FE-DC-01：HomeView.vue 改动规范

### Script 新增状态

在现有 `loading`、`summary` 等 ref 定义处新增：
```javascript
// 故障总数卡片数据（US-DC-01）
const faultSummary = ref({ active_fault_count: 0, affected_unit_count: 0 })
const loadingFaultSummary = ref(false)

// 子设备故障数据（US-DC-02~05）
const deviceFaultSummary = ref({
  air_quality_sensor:  { total: 0, fault_count: 0 },
  thermostat_panels:   { total: 0, fault_count: 0 },
  fresh_air_unit:      { total: 0, fault_count: 0 },
  hydraulic_module:    { total: 0, fault_count: 0 },
})
const loadingDeviceFaultSummary = ref(false)
```

### Script 新增 API 函数

```javascript
const fetchFaultSummary = async () => {
  loadingFaultSummary.value = true
  try {
    const res = await api.get('/api/dashboard/fault-summary/')
    if (res?.success) faultSummary.value = res.data
  } catch (e) {
    console.error('fetchFaultSummary error:', e)
  } finally {
    loadingFaultSummary.value = false
  }
}

const fetchDeviceFaultSummary = async () => {
  loadingDeviceFaultSummary.value = true
  try {
    const res = await api.get('/api/dashboard/device-fault-summary/')
    if (res?.success) deviceFaultSummary.value = res.data
  } catch (e) {
    console.error('fetchDeviceFaultSummary error:', e)
  } finally {
    loadingDeviceFaultSummary.value = false
  }
}
```

### Script 新增路由跳转函数

需先确认 HomeView.vue 已导入 `useRouter`。如未导入，在 `import` 段追加：
```javascript
import { useRouter } from 'vue-router'
// ...
const router = useRouter()
```

跳转函数：
```javascript
// US-DC-01~05: 跳转到故障管理并预设过滤参数
const goToFaults = (subTypes = [], isActive = true) => {
  const query = { is_active: String(isActive) }
  if (subTypes.length === 1) {
    query.sub_type = subTypes[0]
  } else if (subTypes.length > 1) {
    query.sub_type = subTypes
  }
  router.push({ name: 'FaultManagement', query })
}
```

### Script onMounted 追加

在现有 `onMounted` 中，追加：
```javascript
fetchFaultSummary()
fetchDeviceFaultSummary()
```

### 模板重构结构

原有的 `<div class="stats-cards">` 区域替换为 4 组结构，各组包含一个 `.group-title` div 和一个 `.stats-cards` 行：

```html
<!-- 分组 1：能耗概览 -->
<div class="group-title">能耗概览</div>
<div class="stats-cards">
  <!-- 今日用电量卡片（现有，迁入此组） -->
  <!-- 本月用电量卡片（现有，迁入此组） -->
</div>

<!-- 分组 2：设备状态 -->
<div class="group-title">设备状态</div>
<div class="stats-cards">
  <!-- PLC在线卡片（现有，迁入此组） -->
  <!-- 大屏在线卡片（现有，迁入此组） -->
  <!-- 总设备数卡片（现有，迁入此组） -->
  <!-- 系统开机状况卡片（现有，迁入此组） -->
</div>

<!-- 分组 3：故障与子设备 -->
<div class="group-title">故障与子设备</div>
<div class="stats-cards">
  <!-- 当前故障总数卡片（新增） -->
  <!-- 空气品质传感器卡片（新增） -->
  <!-- 温控面板卡片（新增） -->
  <!-- 新风卡片（新增） -->
  <!-- 水力模块卡片（新增） -->
</div>

<!-- 分组 4：趋势与日志 -->
<div class="group-title">趋势与日志</div>
<div class="charts-section">
  <!-- 近7天用电趋势图（现有，迁入此组） -->
  <!-- 系统运行状态（现有，迁入此组） -->
</div>
<!-- 最近活动（现有，迁入此组） -->
<div class="recent-activities">...</div>
```

### 新增卡片模板规范

每张新增卡片使用 `el-card class="stat-card"` 确保继承 hover 动效；加 `style="cursor: pointer"` 和 `@click` 事件：

**当前故障总数卡片**：
```html
<el-card class="stat-card" v-loading="loadingFaultSummary"
         style="cursor: pointer" @click="goToFaults([], true)">
  <div class="stat-content">
    <div class="stat-info">
      <div class="stat-value" style="color: var(--color-danger)">
        {{ faultSummary.active_fault_count }}
      </div>
      <div class="stat-label">当前故障总数</div>
      <div class="stat-sub">影响 {{ faultSummary.affected_unit_count }} 户</div>
    </div>
    <div class="stat-icon" style="color: var(--color-danger)">
      <el-icon><Warning /></el-icon>
    </div>
  </div>
</el-card>
```

**子设备卡片（以空气品质传感器为例，其余同构）**：
```html
<el-card class="stat-card" v-loading="loadingDeviceFaultSummary"
         style="cursor: pointer" @click="goToFaults(['air_quality_sensor'], true)">
  <div class="stat-content">
    <div class="stat-info">
      <div class="stat-value">{{ deviceFaultSummary.air_quality_sensor.total }}</div>
      <div class="stat-label">空气品质传感器</div>
      <div class="stat-sub" :style="{ color: deviceFaultSummary.air_quality_sensor.fault_count > 0 ? 'var(--color-warning)' : 'var(--color-success)' }">
        故障 {{ deviceFaultSummary.air_quality_sensor.fault_count }} 台
      </div>
    </div>
    <div class="stat-icon" style="color: var(--color-warning)">
      <el-icon><Odometer /></el-icon>
    </div>
  </div>
</el-card>
```

**温控面板卡片（5 个 sub_type）**：
```html
<el-card class="stat-card" v-loading="loadingDeviceFaultSummary"
         style="cursor: pointer"
         @click="goToFaults([
           'master_bedroom_panel','secondary_bedroom_panel',
           'children_room_panel','study_room_panel','living_room_main'
         ], true)">
```

### 新增 CSS

在 `<style scoped>` 中追加：
```css
.group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary, #909399);
  padding: 16px 0 8px;
  border-bottom: 1px solid var(--border-color-lighter, #ebeef5);
  margin-bottom: 12px;
  letter-spacing: 0.5px;
  width: 100%;
}
```

### Icon 导入

如使用 `Warning`、`Odometer` 等 Element Plus 图标，需在 import 段追加：
```javascript
import { ..., Warning, Odometer } from '@element-plus/icons-vue'
```
（按实际选用图标调整，与现有 `Calendar`、`Document`、`Cpu` 等图标同一 import 路径）

---

## MOD-FE-FM-01：FaultManagementView.vue onMounted 改动规范

### 现有 onMounted（节选）

```javascript
onMounted(async () => {
  // FR-FM-UX-04：URL 参数优先于前端默认值
  const urlIsActive = route.query.is_active
  if (urlIsActive === 'true' || urlIsActive === 'false') {
    filterIsActive.value = urlIsActive
  } else {
    filterIsActive.value = 'true'
  }

  await fetchCategories()
  fetchFaultEvents()   // ← 原有末尾调用
})
```

### 补充改动（在 urlIsActive 读取之后、fetchCategories 之前追加）

```javascript
// REQ-NFR-COMPAT-01: 读取 URL sub_type 参数（支持单值字符串或多值数组）
const urlSubType = route.query.sub_type
if (urlSubType) {
  filters.sub_types = Array.isArray(urlSubType) ? [...urlSubType] : [urlSubType]
} else {
  // 无 URL sub_type 时不改变默认空数组
  // filters.sub_types 已在 reactive 初始化为 []
}
```

### 改动后完整 onMounted 结构

```javascript
onMounted(async () => {
  // 1. is_active 参数
  const urlIsActive = route.query.is_active
  if (urlIsActive === 'true' || urlIsActive === 'false') {
    filterIsActive.value = urlIsActive
  } else {
    filterIsActive.value = 'true'
  }

  // 2. sub_type 参数（REQ-NFR-COMPAT-01，多值支持）
  const urlSubType = route.query.sub_type
  if (urlSubType) {
    filters.sub_types = Array.isArray(urlSubType) ? [...urlSubType] : [urlSubType]
  }

  // 3. 加载分类选项（select 下拉数据）
  await fetchCategories()

  // 4. 自动触发查询（filters 已初始化完毕）
  fetchFaultEvents()
})
```

**注意**：现有代码使用 `const route = useRoute()`，已导入，无需额外导入。

---

## 接口契约摘要（前后端约定）

| 字段路径 | 类型 | 说明 |
|---------|------|------|
| `device-list.results[].has_active_condensation` | `boolean` | 该住户是否有未恢复凝露预警 |
| `fault-summary.data.active_fault_count` | `int` | 全量未恢复故障记录总条数 |
| `fault-summary.data.affected_unit_count` | `int` | 涉及住户去重计数（specific_part distinct） |
| `device-fault-summary.data.*.total` | `int` | DeviceNode 按 product_code 统计的在库设备数 |
| `device-fault-summary.data.*.fault_count` | `int` | FaultEvent is_active=True 且 sub_type 匹配的记录条数 |
