# 架构设计文档

```
file_header:
  document_id: ARCH-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 架构设计
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
    - docs/requirements/v0.6.1_fault_mgmt_ux/user_stories.md
    - docs/architecture/architecture_design_v0.6.0_fault_management.md
    - FreeArkWeb/frontend/src/components/Layout.vue
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - FreeArkWeb/frontend/src/components/CascadingSelector.vue
    - FreeArkWeb/backend/freearkweb/api/views_fault.py
    - FreeArkWeb/backend/freearkweb/api/serializers_fault.py
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py
    - FreeArkWeb/backend/freearkweb/api/models.py
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-28 | 初始草稿，基于代码实地调研，覆盖 ADR-UX-01~ADR-UX-06，对应需求 FR-FM-UX-01~04 及用户裁决 OQ-01~05 |

---

## 1. 设计目标与约束

### 1.1 版本定位

本版本（v0.6.1-FM-UX）是 v0.6.0-FM（MQTT 故障持久化 + 故障管理页面）的纯 UX 调整版本，**不改动** `fault_event` 表 schema，**不引入**新 DB migration，**不引入**新第三方依赖。

| 版本 | 已有 | 本版本新增/修改 |
|------|------|----------------|
| v0.6.0-FM | 故障消费服务、fault_event 表、REST API、FaultManagementView | 导航入口、级联选择房号过滤、设备名映射、默认筛选三态控件 |

### 1.2 关键约束（继承自 v0.6.0，补充 UX 层约束）

- 不修改 `fault_event` 表 schema（无新 migration）。
- 不引入新第三方库（前后端均沿用现有依赖）。
- 后端单进程（uvicorn `--workers 1`）；进程内缓存策略不依赖多进程共享。
- 所有新接口沿用 `IsAuthenticated` 权限，不新增权限模型。
- 生产部署路径：plink + git pull，禁止 pscp 逐文件上传。
- `CascadingSelector.vue` 组件本身**不修改**，仅复用。
- `fault_utils.py` 和 `fault_consumer/` 现有文件：最小侵入，仅追加 `PRODUCT_CODE_LABELS` 常量。

### 1.3 性能预算

| 指标 | 目标 | 说明 |
|------|------|------|
| `fault-events` 接口 P95 响应 | ≤ 800ms | 含 device_name 查表（dict O(1)，无 ORM JOIN） |
| `device_name` 序列化额外耗时 | < 5ms / 100 行 | 进程内 dict 查表，无 IO |
| 缓存字典内存占用 | < 1 MB | 实测 19 条 distinct device_sn，远低于触发阈值 |

---

## 2. 架构决策记录（ADR）

### ADR-UX-01：左侧导航新增"故障管理"入口（FR-FM-UX-01）

**问题**：需要在 `Layout.vue` 的"设备管理"子菜单中添加"故障管理"入口，同步移除 `DeviceManagementDeviceListView.vue` 右上角的同名跳转按钮。

**代码现状（实地调研）**：
- `Layout.vue` 第 47–53 行：`<el-sub-menu index="device-management">` 当前仅含一个子项 `<el-menu-item index="/device-management/device-list">设备列表</el-menu-item>`。
- `DeviceManagementDeviceListView.vue` 第 23–29 行：`<el-button type="warning" @click="$router.push({ name: 'FaultManagement' })">故障管理</el-button>`，位于页头 `justify-content: space-between` 的 flex 布局右侧。
- `router/index.js`：路由 `{ path: '/device-management/faults', name: 'FaultManagement', ... }` 已存在，**无需改路由**。
- `Layout.vue` 的 `activeMenu = router.currentRoute.value.path`，`<el-menu router>` 模式已自动处理激活高亮，新增 `<el-menu-item index="/device-management/faults">` 后高亮逻辑天然正确，无需额外代码。
- `unique-opened` 属性已在 `<el-menu>` 上生效，添加新子项不影响其他子菜单收起行为。

**方案评估**：

| 方案 | 说明 | 评估 |
|------|------|------|
| A：仅新增导航菜单子项，保留右上角按钮 | 两个入口并存 | 违反 FR-FM-UX-01 "移除旧入口"要求，用户体验不一致 |
| B：新增导航菜单子项 + 移除右上角按钮（本方案） | 入口唯一化 | 满足 FR-FM-UX-01，布局随按钮移除可简化 flex（去掉 `justify-content: space-between`，页头恢复纯标题展示）|

**决策**：采用方案 B。

**变更细节**：

`Layout.vue`（追加一行，不修改其他逻辑）：
```html
<!-- 原有 -->
<el-menu-item index="/device-management/device-list">设备列表</el-menu-item>
<!-- 新增 -->
<el-menu-item index="/device-management/faults">故障管理</el-menu-item>
```

`DeviceManagementDeviceListView.vue`（移除按钮及简化布局）：
- 删除第 23–29 行的 `<el-button ... >故障管理</el-button>`。
- 页头外层 div 从 `style="display: flex; align-items: center; justify-content: space-between;"` 简化为去掉 flex 布局（仅展示标题 h2 + 副标题 p），或保留 flex 但去掉 `justify-content: space-between`，由开发者酌情处理。

**不需要改动的文件**：`router/index.js`（路由已存在），`FaultManagementView.vue`（路由注册无变化）。

---

### ADR-UX-02：房号搜索控件 — 前端适配层位置决策（FR-FM-UX-02 · OQ-02）

**问题**：`CascadingSelector` 输出 3 段 `room_no`（如 `3-1-702`），`fault_event.specific_part` 为 4 段（如 `3-1-7-702`）。用户裁决：保持后端参数名 `specific_part` 不变，前端做格式适配。适配层放在哪里？

**背景（CascadingSelector 内部机制，实地调研）**：
- 选房号（叶子节点，level=2）后，组件设置三个 hidden input：`selectedBuilding`（如 `3`）、`selectedUnit`（如 `1`）、`pureRoomNumber`（如 `702`）。
- 选楼栋/单元（中间节点）后，设置 `selectedBuilding`、`selectedUnit`，但 `pureRoomNumber` 为空。
- 组件无楼层（floor）信息——`building_data.js` 的树结构为楼栋→单元→房号，**不含楼层层级**。因此，从 CascadingSelector 的输出无法直接得到 4 段 `specific_part` 中的楼层段（第三段，如 `7`）。

**4 段拼装可行性分析**：
- 若楼层段已知（例如通过查询 `building_data.js` 或额外静态映射），理论上可在前端 `@change` 回调中拼成 `{building}-{unit}-{floor}-{room}`。
- 但 `building_data.js` 当前结构为楼栋→单元→房号（3 层），**不含楼层字段**，无法从现有静态数据中推导楼层段，除非修改 `building_data.js` 或新增房号→楼层映射表。
- 修改 `building_data.js` 超出本版本最小侵入范围，且需要逐一填入楼层信息，代价高。

**决策：采用 icontains 容错方案（不做 4 段精确拼装）**。

**理由**：
1. 楼层信息在 `CascadingSelector` 现有输出中不可得，4 段精确拼装无法在不改 `building_data.js` 的前提下实现。
2. icontains 匹配已在 `views_fault.py`（第 79–81 行）实现并运行良好。
3. 实测数据：一个 3 段 `room_no`（如 `3-1-702`）对应的 `specific_part` 格式为 `3-1-7-702`。执行 `icontains('3-1-702')` 等价于 `LIKE '%3-1-702%'`，在 4 段中精确命中 `3-1-7-702`，不存在误命中（因 `3-1-702` 作为子串不可能出现在其他结构中）。
4. 需求规格 §FR-FM-UX-02 的"注意"块也评估了 `icontains` 可行性；用户裁决（OQ-02）明确允许"icontains 容错"作为降级路径。

**前端适配层设计（组件 `@change` 回调，不使用 axios 拦截器）**：

适配逻辑放在 `FaultManagementView.vue` 的 CascadingSelector `@change` 回调（或等价的响应式 watch），**不放在 axios 拦截器**。

理由：axios 拦截器是全局的，会影响其他接口，职责不明；回调中处理本组件的参数组装更内聚、可测。

```
CascadingSelector 选中后 → 读取 hidden inputs (fmBuilding / fmUnit / fmRoom) →
  若三者均有值 → specific_part = `{building}-{unit}-{room}` 传入（icontains 可命中）
  若仅 building + unit → specific_part = `{building}-{unit}` 传入（startswith 等价）
  若仅 building → specific_part = `{building}` 传入
  若均为空 → specific_part 参数不传（不过滤）
```

**后端不变**：`views_fault.py` 中 `specific_part` 参数的 icontains 逻辑保持原样，无需修改。参数名仍为 `specific_part`（与 OQ-02 裁决一致）。

**前端参数名保持 `specific_part`（不改名为 `room_no`）**，因为后端接口名称不变。

---

### ADR-UX-03：设备名称缓存模块（FR-FM-UX-03 · OQ-03）

**问题**：如何高效地将 `fault_event.device_sn`（VARCHAR，值为整数字符串如 `"22155"`）映射到 `device_name`（如 `"新风机"`），满足 P95 ≤ 800ms 和序列化额外耗时 < 5ms 的性能预算？

**背景（用户裁决 OQ-03 + 实测数据）**：
- `device_node` 表全表 6124 行，distinct `device_sn` 仅 19 条。
- 同一 `device_sn` 在不同 `specific_part` 下映射同一 `device_name`（业务上是设备型号），无歧义，可用纯 `device_sn` 作为 key。
- 进程内缓存字典，量级极小，远低于任何触发阈值。

**方案评估**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A：每次序列化时执行 ORM JOIN（FaultEvent → OwnerInfo → DeviceFloor → DeviceRoom → DeviceNode，4 次关联） | 数据实时 | 每次查询 N 行故障记录触发 N 次或 1 次关联查询；JOIN 路径 4 层，MySQL 在小表上可接受但不必要；达到 P95 ≤ 800ms 存在不确定性 |
| B：prefetch_related 批量预取 DeviceNode | 减少 N+1 | 路径同样 4 层关联；需要 select_related / prefetch_related 链；增加 QuerySet 复杂度；不满足 FR-FM-UX-03 "不引入 ORM JOIN"要求 |
| C：进程内 dict 缓存，启动时一次性加载（本方案） | O(1) 查表；无 IO；启动时 19 条记录加载 < 1ms；内存 < 1MB | 进程重启后需重建（启动时自动完成，无感知）；多 worker 时各自独立（当前 workers=1，无影响）|

**决策**：采用方案 C（进程内 dict 缓存）。

**新增模块**：`FreeArkWeb/backend/freearkweb/api/device_name_cache.py`

**缓存模块接口规范**：

```python
# device_name_cache.py
# 模块级 dict：key=int(device_sn), value=str(device_name)
_cache: dict[int, str] = {}
_cache_loaded_at: float = 0.0
_TTL_SECONDS: float = 60.0

def get_device_name_by_sn(sn: int) -> str | None:
    """O(1) dict 查表，自动处理 TTL 过期重建。
    
    参数：sn 为整数（FaultEvent.device_sn 转 int 后调用）。
    返回：device_name 字符串，或 None（未命中）。
    """
    ...

def _load_cache() -> None:
    """从 DeviceNode 表全量加载 distinct (device_sn, device_name) 到 _cache。
    加载量级：19 条，耗时 < 1ms（Django ORM QuerySet）。
    """
    ...

def invalidate_device_name_cache() -> None:
    """手动失效钩子（本期不接入触发器，供未来 device_tree_sync 调用）。
    执行后下次 get_device_name_by_sn 调用将触发重建。
    """
    ...
```

**TTL 机制**：`_cache_loaded_at` 记录最后加载时间（`time.monotonic()`）。每次 `get_device_name_by_sn` 调用先检查 `monotonic() - _cache_loaded_at > _TTL_SECONDS`，是则调用 `_load_cache()`。TTL = 60 秒，满足"DeviceNode 几乎不变更，60s 已足够"的约束。

**多 worker 行为**：uvicorn 当前 `--workers 1`，dict 仅在单进程内存在，无并发安全问题。若未来扩 worker，各 worker 进程各自维护独立 dict，各自首次查表时分别触发加载；因 DeviceNode 数据几乎不变，各副本数据一致，不影响正确性，仅增加加载次数（仍可接受）。

**FaultEventSerializer 变更**：

```python
# serializers_fault.py（修改）
from .device_name_cache import get_device_name_by_sn
from .fault_consumer.constants import PRODUCT_CODE_LABELS

class FaultEventSerializer(serializers.ModelSerializer):
    device_name = serializers.SerializerMethodField()
    device_type_label = serializers.SerializerMethodField()

    def get_device_name(self, obj):
        """主路径：device_sn → device_name（进程内 dict 查表）。"""
        try:
            sn = int(obj.device_sn)
        except (ValueError, TypeError):
            return None
        return get_device_name_by_sn(sn)  # None 表示未命中

    def get_device_type_label(self, obj):
        """兜底一：product_code → 友好名（PRODUCT_CODE_LABELS dict）。"""
        return PRODUCT_CODE_LABELS.get(obj.product_code)

    class Meta:
        model = FaultEvent
        fields = [
            'id', 'specific_part', 'device_sn', 'product_code',
            'fault_code', 'fault_type', 'fault_message', 'severity',
            'first_seen_at', 'last_seen_at', 'recovered_at', 'is_active',
            'created_at', 'updated_at',
            'device_name',       # 新增（主路径，可 null）
            'device_type_label', # 新增（兜底一，可 null）
        ]
        read_only_fields = fields
```

**三级降级（序列化层）**：

| 优先级 | 条件 | `device_name` 字段 | `device_type_label` 字段 | 前端展示 |
|--------|------|-------------------|------------------------|---------|
| 主路径 | `get_device_name_by_sn(int(sn))` 命中 | `"新风机"` | `null`（或同值） | 显示 `device_name` |
| 兜底一 | dict miss，但 `product_code` 在 `PRODUCT_CODE_LABELS` | `null` | `"水力模块"` | 显示 `device_type_label` |
| 兜底二 | 双重 miss | `null` | `null` | 前端显示 `device_sn + "（未识别）"` |

**模型层不动**，不新增迁移，不在 `fault_event` 表增加任何字段。

---

### ADR-UX-04：默认筛选三态控件（FR-FM-UX-04 · OQ-04）

**问题**：将 `FaultManagementView.vue` 的 `<el-switch>` 二态控件替换为 `<el-radio-group>` 三态控件，并实现 URL 参数优先逻辑。

**现状（代码实地调研）**：
- 第 14–20 行：`<el-switch v-model="filters.is_active_only" active-text="只看未恢复" inactive-text="显示全部" @change="handleSearch" />`。
- 第 196 行（`filters` 声明）：`is_active_only: false`，默认不过滤。
- `fetchFaultEvents`（第 282–284 行）：`if (filters.is_active_only) { params.is_active = 'true' }`——当前仅支持 true/不传两种状态，无法传 `is_active=false`。

**目标状态**：
- 新增响应式变量 `filterIsActive`（string），取值 `'true'` / `'false'` / `'all'`（对应三态），默认 `'true'`。
- 删除 `filters.is_active_only` 字段（不再使用 switch）。
- `onMounted` 中读取 `route.query.is_active`：
  - 值为 `'true'` → `filterIsActive.value = 'true'`
  - 值为 `'false'` → `filterIsActive.value = 'false'`
  - 未传或其他 → `filterIsActive.value = 'true'`（默认"未恢复"）
- `fetchFaultEvents` 中：
  - `filterIsActive === 'true'` → `params.is_active = 'true'`
  - `filterIsActive === 'false'` → `params.is_active = 'false'`
  - `filterIsActive === 'all'` → 不传 `is_active` 参数

**后端不变**：`views_fault.py` 第 113–121 行的 `is_active` 过滤逻辑已支持 `true/false/不传`，无需任何修改。

**`useRoute` 导入**：`FaultManagementView.vue` 当前已 `import { useRouter }` 但未 `import { useRoute }`，需补充 `import { useRoute } from 'vue-router'` 并在 `setup` 中调用 `const route = useRoute()`。

---

### ADR-UX-05：`PRODUCT_CODE_LABELS` 常量追加（FR-FM-UX-03 · OQ-05）

**问题**：兜底一的 `product_code → 友好名` 映射放在哪里？

**决策**：追加到 `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py`（现有文件末尾），命名为 `PRODUCT_CODE_LABELS`，与 `FAULT_TYPE_LABELS`、`SUB_TYPE_LABELS` 风格一致。

**理由**：
- 现有 `constants.py` 已集中维护故障相关常量（`FAULT_TYPE_LABELS`、`SUB_TYPE_LABELS`），`PRODUCT_CODE_LABELS` 语义相近，放此处最内聚。
- 不引入新文件、不引入 DB 表，满足最小侵入约束。
- `serializers_fault.py` 已经 `from .fault_consumer.constants import ...`，添加 `PRODUCT_CODE_LABELS` 到 import 即可。

**本期手工填入的映射（基于生产 device_list API 分析）**：

```python
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

### ADR-UX-06：缓存失效策略与并发安全

**问题**：`device_name_cache.py` 的 dict 在多请求并发场景下是否需要加锁？

**分析**：
- Python GIL 保证 dict 读写在 CPython 中是线程安全的（基本操作原子化）。
- 当前 freeark-backend 使用 uvicorn `--workers 1`（单进程），即使有多线程请求并发，GIL 保障 dict 访问安全。
- `_load_cache()` 执行时仅涉及 19 条 `SELECT`，耗时 < 1ms，竞态窗口极小。最坏情况：两个并发请求同时触发 TTL 过期重建，执行两次相同查询——结果幂等，无副作用，可接受。

**决策**：本期不加锁（threading.Lock），依赖 GIL 和幂等性。若未来扩 worker 至多进程，各进程有独立 GIL，仍安全。在 `device_name_cache.py` 的模块 docstring 中注明此决策，供后续开发者参考。

---

## 3. 整体变更范围图

```
前端（Vue 3 / Vite）
├── Layout.vue
│   └── <el-sub-menu index="device-management"> 追加子项「故障管理」
│
├── DeviceManagementDeviceListView.vue
│   └── 删除页头右上角 <el-button>故障管理</el-button> 及简化 flex 布局
│
└── FaultManagementView.vue（UX 调整，主要改动）
    ├── 引入 CascadingSelector 组件（hidden input id: fmBuilding/fmUnit/fmRoom）
    ├── 删除 <el-input> 房号文本框 + filters.specific_part 文本输入逻辑
    ├── 新增组件 @change 回调，读取 hidden inputs → 组装 specific_part 参数（icontains 容错）
    ├── 删除 <el-switch is_active_only>，替换为 <el-radio-group filterIsActive>（三态）
    ├── onMounted 读取 route.query.is_active 初始化 filterIsActive（URL 参数优先）
    ├── fetchFaultEvents 更新 is_active 传参逻辑（true/false/不传）
    └── 表格列「设备SN」→「设备名称」，优先显示 device_name，次 device_type_label，兜底 device_sn+（未识别）

后端（Django / DRF）
├── api/fault_consumer/constants.py
│   └── 追加 PRODUCT_CODE_LABELS 字典（7 条 product_code → 友好名映射）
│
├── api/device_name_cache.py（新增文件）
│   ├── 模块级 _cache: dict[int, str]
│   ├── TTL = 60s，monotonic 时间戳控制
│   ├── get_device_name_by_sn(sn: int) -> str | None
│   ├── _load_cache()：SELECT DISTINCT device_sn, device_name FROM device_node
│   └── invalidate_device_name_cache()：本期不接触发器，预留钩子
│
└── api/serializers_fault.py（修改）
    ├── 新增 device_name（SerializerMethodField → get_device_name_by_sn）
    └── 新增 device_type_label（SerializerMethodField → PRODUCT_CODE_LABELS[product_code]）

不变的后端模块
├── api/views_fault.py（参数名 specific_part 不变，is_active 逻辑不变）
├── api/models.py（fault_event schema 不变，无新 migration）
├── api/fault_consumer/*.py（fault_consumer 主流程不变）
└── router/index.js（路由已存在，不改）
```

---

## 4. 数据流说明

### 4.1 房号过滤数据流（FR-FM-UX-02）

```
用户操作 CascadingSelector
  → 选叶子节点（具体房号）→ fmBuilding="3", fmUnit="1", fmRoom="702"
  → 选中间节点（单元）   → fmBuilding="3", fmUnit="1", fmRoom=""
  → 选根节点（楼栋）     → fmBuilding="3", fmUnit="",  fmRoom=""

FaultManagementView.vue @change 回调
  → 读取 document.getElementById('fmBuilding/fmUnit/fmRoom').value
  → 组装 specific_part：
      三者均有 → "{building}-{unit}-{room}"（如 "3-1-702"）
      仅 building+unit → "{building}-{unit}"（如 "3-1"）
      仅 building     → "{building}"（如 "3"）
      均空           → 不传（无过滤）

GET /api/devices/fault-events/?specific_part=3-1-702
  → views_fault.fault_event_list
  → qs.filter(specific_part__icontains='3-1-702')
  → MySQL: WHERE specific_part LIKE '%3-1-702%'
  → 命中: specific_part="3-1-7-702" ✓（"3-1-702" 是 "3-1-7-702" 的子串）
  → 误命中风险: "3-1-702" 不可能作为子串出现在 "3-2-7-702" 等其他房号中 ✓
```

### 4.2 设备名称查表数据流（FR-FM-UX-03）

```
GET /api/devices/fault-events/
  → QuerySet: FaultEvent.objects.filter(...).order_by('-first_seen_at')
  → Pagination: page N（N 行记录，无 ORM JOIN）
  → FaultEventSerializer(page, many=True)
    → 对每行 obj：
      1. get_device_name(obj):
         sn = int(obj.device_sn)  # e.g. 22155
         get_device_name_by_sn(22155)
           → 检查 TTL（monotonic 时间戳）
           → 命中缓存 dict → return "新风机"（O(1)）
           → TTL 过期 → _load_cache() → DeviceNode.objects.values_list → 填充 dict → return
      2. get_device_type_label(obj):
         PRODUCT_CODE_LABELS.get(obj.product_code)  # e.g. "130004" → "新风机"
  → 响应含 device_name, device_type_label 字段

前端 FaultManagementView.vue 表格列渲染（设备名称列）：
  device_name ? 显示 device_name
  : device_type_label ? 显示 device_type_label
  : 显示 `${row.device_sn}（未识别）`
```

### 4.3 默认筛选数据流（FR-FM-UX-04）

```
用户进入 /device-management/faults（无 URL 参数）
  → onMounted → route.query.is_active = undefined → filterIsActive = 'true'（默认）
  → fetchFaultEvents → params.is_active = 'true'
  → GET /api/devices/fault-events/?is_active=true（返回未恢复故障）

用户进入 /device-management/faults?is_active=false
  → onMounted → route.query.is_active = 'false' → filterIsActive = 'false'
  → fetchFaultEvents → params.is_active = 'false'
  → GET /api/devices/fault-events/?is_active=false（返回已恢复故障）

用户切换 radio-group → 全部
  → filterIsActive = 'all'
  → handleSearch → fetchFaultEvents → is_active 参数不传
  → GET /api/devices/fault-events/（返回所有记录）
```

---

## 5. 安全性设计

| 方面 | 设计 |
|------|------|
| 权限 | 所有接口沿用 `IsAuthenticated`，不引入新权限 |
| SQL 注入 | `specific_part` 仍经 Django ORM icontains 参数化，不拼接原生 SQL |
| 缓存污染 | `device_name_cache.py` 仅在后端进程内存中，不暴露外部接口，无注入面 |
| 输入校验 | `filterIsActive` 在前端限定为 `'true'/'false'/'all'` 三值；后端对非 `true/false` 值静默忽略（已有逻辑） |

---

## 6. 测试策略草案（供 test-engineer 阶段参考）

### 6.1 单元测试边界

| 测试对象 | 测试场景 | 工具 |
|----------|---------|------|
| `get_device_name_by_sn` | 命中返回 device_name；未命中返回 None；TTL 过期后触发 reload；int(sn) 转换失败时兜底 | pytest + SQLite |
| `PRODUCT_CODE_LABELS` 兜底 | `get_device_type_label` 命中已知 product_code；未知 product_code 返回 null | pytest |
| `FaultEventSerializer` | 含 device_name 字段；含 device_type_label 字段；双 null 时字段为 null | pytest + DRF APIClient |
| `invalidate_device_name_cache` | 调用后再次 get 触发 reload | pytest |

### 6.2 集成测试边界

| 测试场景 | 验收标准 |
|----------|---------|
| URL 参数 `is_active=false` 优先于前端默认 | onMounted 后 filterIsActive = 'false'，请求携带 `is_active=false` |
| CascadingSelector 选完后 fault-events 请求的 specific_part 形态 | 选 `3-1-702` → 请求携带 `specific_part=3-1-702` |
| device_name 缓存 + 序列化 | device_sn=22155 → device_name="新风机" |

### 6.3 E2E 验收

| 场景 | 验收标准 |
|------|---------|
| 左侧导航点击「故障管理」可达 | 路由到 `/device-management/faults`，页面正常加载 |
| 设备列表右上角按钮已移除 | `/device-management/device-list` 页头无"故障管理"按钮 |
| 设备名展示样例 | 故障管理表格中 `device_sn=22155` 的行显示 `"新风机"`（而非 `"22155"`） |
| 三态控件默认态 | 无 URL 参数进入页面，`<el-radio-group>` "未恢复"选项高亮，请求携带 `is_active=true` |

---

## 7. 生产部署说明（概要）

v0.6.1-FM-UX 无 DB migration，无 systemd 服务变更，部署极简：

```
# 1. 在生产服务器执行（plink + git pull）
git pull origin main

# 2. 重启后端服务（使 device_name_cache 模块初始化生效）
sudo systemctl restart freeark-backend

# 3. 重新构建前端（Vite build）
cd FreeArkWeb/frontend && npm run build

# 4. 验证
# 浏览器访问 /device-management/device-list → 确认无"故障管理"按钮
# 浏览器访问 /device-management/faults → 确认左侧导航高亮"故障管理"
# 故障管理页默认加载未恢复故障（radio-group "未恢复"激活）
# 表格"设备名称"列显示中文设备名而非纯 SN 数字
```

**rollback**：无 migration，`git revert` 后重启 freeark-backend 即可回滚，前端重新 build。

---

## 8. 架构待办（Architecture Backlog）

| 编号 | 标题 | 优先级 | 触发条件 |
|------|------|--------|---------|
| AB-UX-001 | 将楼层字段加入 `building_data.js`，支持 4 段 specific_part 精确匹配 | 低 | 若 icontains 出现误命中投诉时 |
| AB-UX-002 | `invalidate_device_name_cache` 接入 `device_tree_sync` 完成信号 | 低 | device_tree_sync 功能实现后 |
| AB-UX-003 | `PRODUCT_CODE_LABELS` 迁移到 DB 表，支持运维人员在线维护 | 低 | 设备品类频繁变更时 |

---

## 9. 架构层开放问题

| 编号 | 问题 | 影响范围 | 需用户裁决 |
|------|------|---------|----------|
| **AQ-01** | `device_name_cache.py` 首次 `_load_cache()` 在哪个时机触发？方案A：首次调用 `get_device_name_by_sn` 时懒加载（简单，但第一个请求会略慢 < 1ms）。方案B：Django `AppConfig.ready()` 时预热加载（需在 `apps.py` 注册，改动微小但需确认现有 `apps.py` 结构）。两者均可接受，推荐方案A（更简单，无需改 apps.py）。 | `device_name_cache.py` 实现 | **无需裁决，推荐方案A（懒加载），开发者可直接采用** |
| **AQ-02** | `FaultManagementView.vue` 的 CascadingSelector 读取 hidden input 的方式：通过 `document.getElementById('fmBuilding').value` 还是通过 `ref` 获取组件实例后调用其内部属性（`cascadingSelectorRef.value.selectedBuilding`）？前者简单但依赖 DOM id；后者更 Vue 风格但需确认 CascadingSelector expose 了哪些属性（现有组件用 Options API，未显式 expose）。 | `FaultManagementView.vue` 实现 | **无需裁决；推荐用 `document.getElementById`（与设备列表现有实现一致，`DeviceManagementDeviceListView.vue` 第 310–319 行已有此模式）** |
| **AQ-03** | `handleReset()` 重置时，是否同时重置 `filterIsActive` 为 `'true'`（默认"未恢复"）？当前 v0.6.0 的 `handleReset` 将 `is_active_only` 置 false（显示全部）。新版本重置语义是否应与"默认进入"行为一致（重置 = 回到默认 = "未恢复"）？建议：重置时 `filterIsActive = 'true'`（与首次进入行为一致）。若用户有不同偏好，在此注明。 | `FaultManagementView.vue` UX 行为 | **建议重置恢复为"未恢复"默认态（与首次进入一致）；若用户希望重置为"全部"，请告知** |
