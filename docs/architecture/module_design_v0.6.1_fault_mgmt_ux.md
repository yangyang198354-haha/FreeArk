# 模块设计文档

```
file_header:
  document_id: MOD-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 模块设计
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.1_fault_mgmt_ux.md
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
    - FreeArkWeb/frontend/src/components/Layout.vue
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - FreeArkWeb/frontend/src/components/CascadingSelector.vue
    - FreeArkWeb/backend/freearkweb/api/serializers_fault.py
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-28 | 初始草稿，基于代码实地调研，覆盖全部 4 个 FR-FM-UX 需求的模块变更 |

---

## 1. 模块清单

### 1.1 新增模块

| 模块 ID | 文件路径 | 类型 | 需求覆盖 |
|---------|---------|------|---------|
| MOD-BE-UX-01 | `FreeArkWeb/backend/freearkweb/api/device_name_cache.py` | 后端 Python 模块（新增文件）| FR-FM-UX-03 · OQ-03 |

### 1.2 修改模块

| 模块 ID | 文件路径 | 类型 | 变更摘要 | 需求覆盖 |
|---------|---------|------|---------|---------|
| MOD-FE-UX-01 | `FreeArkWeb/frontend/src/components/Layout.vue` | 前端 Vue 组件 | 追加「故障管理」子菜单项 | FR-FM-UX-01 |
| MOD-FE-UX-02 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 前端 Vue 组件 | 删除页头右上角「故障管理」按钮 | FR-FM-UX-01 |
| MOD-FE-UX-03 | `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 前端 Vue 组件 | 多项 UX 调整（详见 §3）| FR-FM-UX-02/03/04 |
| MOD-BE-UX-02 | `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py` | 后端常量模块 | 追加 `PRODUCT_CODE_LABELS` 字典 | FR-FM-UX-03 · OQ-05 |
| MOD-BE-UX-03 | `FreeArkWeb/backend/freearkweb/api/serializers_fault.py` | DRF Serializer | 新增 `device_name`、`device_type_label` 字段 | FR-FM-UX-03 |

### 1.3 不修改的模块（明确声明）

| 文件路径 | 原因 |
|---------|------|
| `FreeArkWeb/backend/freearkweb/api/views_fault.py` | `specific_part` icontains 逻辑不变；`is_active` 过滤逻辑不变；不加新参数 |
| `FreeArkWeb/backend/freearkweb/api/models.py` | `fault_event` schema 不变，不加 migration |
| `FreeArkWeb/frontend/src/components/CascadingSelector.vue` | 仅复用，不修改组件内部逻辑 |
| `FreeArkWeb/frontend/src/router/index.js` | 路由 `FaultManagement` 已存在，不改 |
| `FreeArkWeb/backend/freearkweb/api/fault_consumer/*.py`（除 constants.py）| 故障消费主流程不变 |
| `FreeArkWeb/backend/freearkweb/api/fault_utils.py` | v0.5.3-FCC 模块，只读引用 |
| `/etc/systemd/system/freeark-*.service` / `.timer` | 无新增服务，无需改 systemd |

---

## 2. 模块详细设计

---

### MOD-BE-UX-01：`api/device_name_cache.py`（新增）

**职责**：提供进程内 `device_sn → device_name` 字典缓存，供 `FaultEventSerializer` 在序列化时以 O(1) 查表获取设备友好名称。

**文件路径**：`FreeArkWeb/backend/freearkweb/api/device_name_cache.py`

**接口定义**：

```python
"""
device_name_cache.py — 设备名称进程内缓存（MOD-BE-UX-01, v0.6.1-FM-UX）

职责：
  - 缓存 DeviceNode.device_sn → DeviceNode.device_name 映射
  - 供 FaultEventSerializer.get_device_name 调用，O(1) 无 IO

设计约束：
  - 不引入 Redis / LocMemCache，使用纯 Python dict
  - TTL = 60s（DeviceNode 几乎不变更，60s 足够）
  - 懒加载：首次调用 get_device_name_by_sn 时触发 _load_cache()
  - 多 worker 说明：若 uvicorn workers > 1，各进程各自维护独立 dict，
    数据一致（DeviceNode 不变），仅各自首次构建，不影响正确性
  - 线程安全：依赖 CPython GIL 保障基本 dict 操作原子性；不加锁（幂等重建）
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 模块级缓存状态
_cache: dict[int, str] = {}          # key: int(device_sn), value: device_name
_cache_loaded_at: float = 0.0        # 最后加载时间（monotonic）
_TTL_SECONDS: float = 60.0           # 缓存 TTL：60 秒


def get_device_name_by_sn(sn: int) -> Optional[str]:
    """根据 device_sn（int）查询设备名称。

    自动处理 TTL 过期重建，O(1) dict 查表。

    Args:
        sn: 整数设备序列号（FaultEvent.device_sn 转 int 后调用）

    Returns:
        device_name 字符串（如 "新风机"），或 None（未命中）
    """
    _ensure_cache_fresh()
    return _cache.get(sn)


def _ensure_cache_fresh() -> None:
    """检查 TTL，过期则重建缓存。"""
    now = time.monotonic()
    if now - _cache_loaded_at > _TTL_SECONDS:
        _load_cache()


def _load_cache() -> None:
    """从 DeviceNode 全量加载 distinct (device_sn, device_name) 到 _cache。

    执行一次 SELECT，量级约 19 条，耗时 < 1ms。
    使用 distinct=True 去重（同一 device_sn 可在多个 specific_part 下出现）。
    """
    global _cache, _cache_loaded_at
    try:
        from .models import DeviceNode  # 延迟导入，避免循环引用
        # distinct device_sn 映射：实测 19 条，取最先出现的 device_name（业务上同 sn 对应同 name）
        pairs = DeviceNode.objects.values_list('device_sn', 'device_name')
        new_cache: dict[int, str] = {}
        for sn, name in pairs:
            if sn not in new_cache and name:
                new_cache[sn] = name
        _cache = new_cache
        _cache_loaded_at = time.monotonic()
        logger.debug('device_name_cache 重建完成，共 %d 条', len(_cache))
    except Exception as exc:
        logger.error('device_name_cache 加载失败: %s', exc, exc_info=True)
        # 失败不崩溃；_cache 保留旧值（可能为空），下次请求再试


def invalidate_device_name_cache() -> None:
    """手动失效钩子。

    执行后，下次 get_device_name_by_sn 调用将触发 _load_cache() 重建。
    本期（v0.6.1-FM-UX）不接入触发器；预留供未来 device_tree_sync 完成后调用。

    用法示例（device_tree_sync.py 完成后）：
        from api.device_name_cache import invalidate_device_name_cache
        invalidate_device_name_cache()
    """
    global _cache_loaded_at
    _cache_loaded_at = 0.0
    logger.info('device_name_cache 已手动失效，下次查询将重建')
```

**内存占用估算**：
- 19 条 entry，每条：key int（28 bytes）+ value str（约 40 bytes + object overhead）≈ 100 bytes
- 总计：约 2 KB，远低于任何触发阈值。

**依赖**：`api.models.DeviceNode`（延迟导入，避免启动时循环引用）。

---

### MOD-FE-UX-01：`Layout.vue`（修改）

**变更范围**：仅在 `<el-sub-menu index="device-management">` 内追加一个 `<el-menu-item>`，**共 1 行改动**。

**精确变更位置**（基于实地调研，第 52 行后追加）：

```html
<!-- 修改前（第 47–53 行）-->
<el-sub-menu index="device-management">
  <template #title>
    <el-icon><List /></el-icon>
    <span>设备管理</span>
  </template>
  <el-menu-item index="/device-management/device-list">设备列表</el-menu-item>
</el-sub-menu>

<!-- 修改后 -->
<el-sub-menu index="device-management">
  <template #title>
    <el-icon><List /></el-icon>
    <span>设备管理</span>
  </template>
  <el-menu-item index="/device-management/device-list">设备列表</el-menu-item>
  <el-menu-item index="/device-management/faults">故障管理</el-menu-item>  <!-- 新增 -->
</el-sub-menu>
```

**不需要改动的部分**：
- `<el-menu>` 的 `router`、`unique-opened`、`:collapse`、`activeMenu` 逻辑均已满足自动高亮需求，无需改动。
- `<script>` 部分（组件逻辑、图标导入等）**完全不改**。
- `<style>` 部分**完全不改**。

**验收标准**（对应 AC-01-A-01, AC-01-A-02, AC-01-A-03）：展开"设备管理"后显示"设备列表"和"故障管理"两个子项；点击"故障管理"路由跳转到 `/device-management/faults`；刷新后激活高亮保持。

---

### MOD-FE-UX-02：`DeviceManagementDeviceListView.vue`（修改）

**变更范围**：删除页头右上角的"故障管理"按钮，简化页头 flex 布局。

**精确变更位置**（基于实地调研，第 15–31 行区域）：

```html
<!-- 修改前（第 17–31 行，含故障管理按钮的 flex 布局）-->
<div style="display: flex; align-items: center; justify-content: space-between;">
  <div>
    <h2>设备列表</h2>
    <p class="page-subtitle">查看和管理所有设备的运行状态</p>
  </div>
  <!-- v0.6.0-FM：故障管理导航入口（MOD-FE-FM-03）-->
  <el-button
    type="warning"
    @click="$router.push({ name: 'FaultManagement' })"
  >
    故障管理
  </el-button>
</div>

<!-- 修改后（移除按钮，外层 div 去掉 flex 属性）-->
<div>
  <h2>设备列表</h2>
  <p class="page-subtitle">查看和管理所有设备的运行状态</p>
</div>
```

**不需要改动的部分**：
- 过滤栏、表格、分页、所有其他功能（搜索、CascadingSelector `dlBuilding/dlUnit/dlRoom`、PLC 历史弹窗、设备面板等）**完全不改**。
- `<script setup>` 部分**完全不改**（`$router.push` 引用删除后无悬挂引用，因为 Vue3 `$router` 来自 Options API；该页面是 `<script setup>` 模式，确认删除 `<el-button @click="$router.push(...)">` 不引入任何 orphan reference）。

**验收标准**（对应 AC-01-B-01, AC-01-B-02）：页面右上角不存在橙色"故障管理"按钮；其他功能不受影响。

---

### MOD-FE-UX-03：`FaultManagementView.vue`（修改）

**变更范围**：本版本最大改动文件，涉及多个功能点。

#### 3.1 删除原文本输入框（房号过滤，第 25–34 行）

```html
<!-- 删除整个 el-form-item -->
<el-form-item label="房号">
  <el-input
    v-model="filters.specific_part"
    placeholder="输入房号模糊搜索"
    clearable
    style="width: 160px"
    @clear="handleSearch"
    @keyup.enter="handleSearch"
  />
</el-form-item>
```

同步删除 `filters.specific_part` 字段（在 `filters` reactive 对象中）。

#### 3.2 引入 CascadingSelector 组件（替换文本框位置）

**import 追加**（`<script setup>` 顶部）：
```js
import CascadingSelector from '@/components/CascadingSelector.vue'
```

**template 追加**（原房号过滤 el-form-item 位置替换）：
```html
<el-form-item label="房号">
  <div style="display: inline-block; vertical-align: middle; width: 180px;">
    <CascadingSelector
      building-input-id="fmBuilding"
      building-input-name="fmBuilding"
      unit-input-id="fmUnit"
      unit-input-name="fmUnit"
      room-input-id="fmRoom"
      room-input-name="fmRoom"
      ref="fmCascadingSelectorRef"
    />
  </div>
</el-form-item>
```

**注意**：hidden input id 使用 `fmBuilding/fmUnit/fmRoom`（区别于设备列表的 `dlBuilding/dlUnit/dlRoom`），避免同页面或跨页面的 id 冲突。

#### 3.3 specific_part 参数组装逻辑（新增函数）

```js
// 新增函数（在 fetchFaultEvents 之前定义）
function getSelectedSpecificPart() {
  const building = document.getElementById('fmBuilding')?.value || ''
  const unit = document.getElementById('fmUnit')?.value || ''
  const room = document.getElementById('fmRoom')?.value || ''

  if (building && unit && room) {
    return `${building}-${unit}-${room}`  // 如 "3-1-702"（icontains 命中 "3-1-7-702"）
  } else if (building && unit) {
    return `${building}-${unit}`          // 如 "3-1"（命中 3 栋 1 单元全部）
  } else if (building) {
    return building                       // 如 "3"（命中 3 栋全部）
  }
  return ''  // 不过滤
}
```

**在 `fetchFaultEvents` 中使用**（替换原 `filters.specific_part` 读取）：
```js
const sp = getSelectedSpecificPart()
if (sp) {
  params.specific_part = sp
}
```

**重置时清空 CascadingSelector**（`handleReset` 中新增）：
```js
// 通过 ref 调用组件的 clearSelection 方法
if (fmCascadingSelectorRef.value) {
  fmCascadingSelectorRef.value.clearSelection()
}
```

#### 3.4 删除 `<el-switch>` + 替换为 `<el-radio-group>`

**删除**（第 13–20 行的 `active-only-toggle` div 及 `<el-switch>`）：
```html
<!-- 删除 -->
<div class="active-only-toggle">
  <el-switch
    v-model="filters.is_active_only"
    active-text="只看未恢复"
    inactive-text="显示全部"
    @change="handleSearch"
  />
</div>
```

**新增**（在 filter-bar 内，作为第一个 el-form-item）：
```html
<el-form-item label="状态">
  <el-radio-group v-model="filterIsActive" @change="handleSearch">
    <el-radio-button value="true">未恢复</el-radio-button>
    <el-radio-button value="false">已恢复</el-radio-button>
    <el-radio-button value="all">全部</el-radio-button>
  </el-radio-group>
</el-form-item>
```

**新增响应式变量**（替换 `filters.is_active_only`）：
```js
const filterIsActive = ref('true')  // 默认"未恢复"
```

**删除** `filters.is_active_only` 字段（从 `filters` reactive 对象中移除）。

#### 3.5 URL 参数优先逻辑（FR-FM-UX-04）

**补充 import**：
```js
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'  // 补充 useRoute
```

**setup 中初始化**：
```js
const route = useRoute()
```

**onMounted 中读取 URL 参数**（在 `fetchCategories` 调用之前）：
```js
onMounted(async () => {
  // FR-FM-UX-04：URL 参数优先于默认值
  const urlIsActive = route.query.is_active
  if (urlIsActive === 'true' || urlIsActive === 'false') {
    filterIsActive.value = urlIsActive
  } else {
    filterIsActive.value = 'true'  // 默认"未恢复"
  }

  await fetchCategories()
  await fetchFaultEvents()
})
```

#### 3.6 `fetchFaultEvents` 中 is_active 传参更新

```js
// 替换原 if (filters.is_active_only) { params.is_active = 'true' }
if (filterIsActive.value === 'true') {
  params.is_active = 'true'
} else if (filterIsActive.value === 'false') {
  params.is_active = 'false'
}
// 'all' 时不传 is_active 参数
```

#### 3.7 重置函数更新

```js
function handleReset() {
  // 清空 CascadingSelector
  if (fmCascadingSelectorRef.value) {
    fmCascadingSelectorRef.value.clearSelection()
  }
  filters.fault_types = []
  filters.sub_types = []
  filters.dateRange = [...defaultDateRange]
  filterIsActive.value = 'true'  // 重置回默认"未恢复"
  currentPage.value = 1
  pageSize.value = 20
  fetchFaultEvents()
}
```

#### 3.8 表格列：「设备SN」→「设备名称」

**修改表格列**（第 107 行，`prop="device_sn"` 列）：

```html
<!-- 修改前 -->
<el-table-column prop="device_sn" label="设备SN" min-width="100" />

<!-- 修改后 -->
<el-table-column label="设备名称" min-width="120">
  <template #default="{ row }">
    <span v-if="row.device_name">{{ row.device_name }}</span>
    <span v-else-if="row.device_type_label">{{ row.device_type_label }}</span>
    <span v-else>
      {{ row.device_sn }}
      <el-tag size="small" type="info" style="margin-left: 4px;">未识别</el-tag>
    </span>
  </template>
</el-table-column>
```

**说明**：
- 原始 `device_sn` 字段仍在 API 响应中（后端不删除），但不作为独立列展示，仅在兜底二时与"未识别"角标一同显示。
- `device_name` 和 `device_type_label` 字段由后端新增序列化字段提供。

#### 3.9 删除 `active-only-toggle` CSS（`<style scoped>`）

删除以下 CSS 块（不再有对应的 DOM 元素）：
```css
/* 删除 */
.active-only-toggle {
  margin-bottom: 16px;
}
```

---

### MOD-BE-UX-02：`api/fault_consumer/constants.py`（修改）

**变更范围**：仅在文件末尾追加 `PRODUCT_CODE_LABELS` 字典，**不修改现有任何内容**。

**追加内容**（在 `FAULT_TYPE_LABELS` 字典之后）：

```python
# ---------------------------------------------------------------------------
# product_code → 友好名映射（兜底一，MOD-BE-UX-02，v0.6.1-FM-UX）
# 主路径：device_node.device_name（进程内 dict 缓存）
# 兜底路径：此映射；基于生产 device_list API 分析（3-1-702 楼层设备清单）
# 维护方式：硬编码，由开发人员按需添加新 product_code
# ---------------------------------------------------------------------------

PRODUCT_CODE_LABELS: dict = {
    '10016':  '自由方舟（主机）',
    '270001': '水力模块',
    '130004': '新风机',
    '250001': '能耗表',
    '100007': '空气品质',
    '260001': '主温控',
    '120003': '温控面板',
}
```

---

### MOD-BE-UX-03：`api/serializers_fault.py`（修改）

**变更范围**：在现有 `FaultEventSerializer` 中新增两个 `SerializerMethodField`，以及对应的 `get_*` 方法。

**完整修改后的文件结构**（仅标注变更点）：

```python
"""
serializers_fault.py — FaultEvent DRF 序列化器（MOD-BE-FM-09/MOD-BE-UX-03，v0.6.1-FM-UX）
"""

from rest_framework import serializers
from .models import FaultEvent
from .device_name_cache import get_device_name_by_sn          # 新增 import
from .fault_consumer.constants import PRODUCT_CODE_LABELS      # 新增 import


class FaultEventSerializer(serializers.ModelSerializer):
    """FaultEvent 只读序列化器。

    v0.6.1-FM-UX 新增字段：
      device_name      — 主路径：进程内缓存 dict 查表，O(1)，无 ORM JOIN
      device_type_label — 兜底一：PRODUCT_CODE_LABELS[product_code]

    三级降级逻辑（前端负责最终渲染决策）：
      device_name 非 null   → 显示 device_name
      device_type_label 非 null → 显示 device_type_label
      均 null              → 显示 device_sn + "（未识别）"角标
    """

    # 新增（v0.6.1-FM-UX）
    device_name = serializers.SerializerMethodField()
    device_type_label = serializers.SerializerMethodField()

    # 新增 get_* 方法
    def get_device_name(self, obj):
        """主路径：device_sn（str）→ int → dict 查表 → device_name。"""
        try:
            sn = int(obj.device_sn)
        except (ValueError, TypeError):
            return None
        return get_device_name_by_sn(sn)

    def get_device_type_label(self, obj):
        """兜底一：product_code → PRODUCT_CODE_LABELS 友好名。"""
        return PRODUCT_CODE_LABELS.get(obj.product_code)

    class Meta:
        model = FaultEvent
        fields = [
            'id',
            'specific_part',
            'device_sn',
            'product_code',
            'fault_code',
            'fault_type',
            'fault_message',
            'severity',
            'first_seen_at',
            'last_seen_at',
            'recovered_at',
            'is_active',
            'created_at',
            'updated_at',
            'device_name',        # 新增（v0.6.1-FM-UX）
            'device_type_label',  # 新增（v0.6.1-FM-UX）
        ]
        read_only_fields = fields
```

**性能说明**：
- `get_device_name`：`int()` 转换 + dict `get()`，O(1)，无 IO，< 0.1ms/行。
- `get_device_type_label`：dict `get()`，O(1)，无 IO，< 0.01ms/行。
- 100 行序列化总额外耗时估算：< 5ms（满足性能预算）。

---

## 3. 接口变更汇总

### 3.1 前端 → 后端 API 接口变更

| 接口 | 参数变更 | 说明 |
|------|---------|------|
| `GET /api/devices/fault-events/` | 参数名 `specific_part` 不变；`is_active` 支持 `'true'/'false'/不传` 三态（原已支持，仅前端使用方式变更）| 后端代码不改 |
| `GET /api/devices/fault-events/` | 响应新增 `device_name`（string\|null）、`device_type_label`（string\|null）字段 | 后端序列化器新增字段 |

### 3.2 前端组件接口

| 组件 | 新增 prop/emit | 说明 |
|------|--------------|------|
| `CascadingSelector`（在 FaultManagementView 中使用）| `building-input-id="fmBuilding"` / `unit-input-id="fmUnit"` / `room-input-id="fmRoom"` | 沿用现有 prop，不新增；仅指定不同的 id 值以避免冲突 |

### 3.3 后端模块接口（新增）

| 函数签名 | 模块 | 说明 |
|---------|------|------|
| `get_device_name_by_sn(sn: int) -> Optional[str]` | `api/device_name_cache.py` | 主对外接口，O(1) dict 查表 |
| `invalidate_device_name_cache() -> None` | `api/device_name_cache.py` | 手动失效钩子（本期不接触发器）|

---

## 4. 需求覆盖矩阵

| 需求 | 模块 ID | 覆盖方式 |
|------|---------|---------|
| FR-FM-UX-01（导航入口）| MOD-FE-UX-01, MOD-FE-UX-02 | Layout.vue 追加子菜单项；DeviceListView 删除按钮 |
| FR-FM-UX-02（房号控件）| MOD-FE-UX-03 | FaultManagementView 引入 CascadingSelector，组装 specific_part |
| FR-FM-UX-03（设备名称）| MOD-BE-UX-01, MOD-BE-UX-02, MOD-BE-UX-03, MOD-FE-UX-03 | 缓存模块 + constants 追加 + 序列化器新增字段 + 前端表格列渲染 |
| FR-FM-UX-04（默认筛选）| MOD-FE-UX-03 | radio-group 替换 switch；onMounted URL 参数优先逻辑 |

---

## 5. 文件变更统计

| 文件 | 操作 | 变更行数估算 |
|------|------|------------|
| `api/device_name_cache.py` | 新增 | ~80 行 |
| `fault_consumer/constants.py` | 修改（追加）| +12 行 |
| `serializers_fault.py` | 修改 | +25 行（2 个方法 + 2 个字段声明 + 2 个 import）|
| `Layout.vue` | 修改（追加）| +1 行 |
| `DeviceManagementDeviceListView.vue` | 修改（删除）| -10 行（删除按钮 + 简化 div）|
| `FaultManagementView.vue` | 修改（多处）| +50 / -25 行（净增约 25 行）|

**总变更量**：约 200 行（新增 80 行 device_name_cache.py + 其余约 120 行净变更）。
