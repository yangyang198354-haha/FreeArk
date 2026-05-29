# 模块设计文档

```
file_header:
  document_id: MODULE-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 模块设计
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: APPROVED
  references:
    - docs/architecture/architecture_design_v0.6.4_fault_mgmt_room_column.md
    - docs/requirements/v0.6.4_fault_mgmt_room_column/requirements_spec.md
```

---

## 1. 模块清单

| 模块编号 | 文件 | 变更类型 | 主要职责 |
|---------|------|---------|---------|
| MOD-v0.6.4-01 | `api/fault_consumer/constants.py` | 修改 | sub_type 字典重写 + VALID_ROOM_NAMES |
| MOD-v0.6.4-02 | `api/fault_consumer/room_lookup.py` | 新增 | device_sn → DeviceRoom 反查辅助 |
| MOD-v0.6.4-03 | `api/fault_consumer/state_machine.py` | 修改 | T1 INSERT 追加 room_name/room_id 填充 |
| MOD-v0.6.4-04 | `api/models.py` | 修改 | FaultEvent 新增 room_name CharField + room_id FK |
| MOD-v0.6.4-05 | `api/migrations/0027_fault_event_room_columns.py` | 新增 | DDL migration |
| MOD-v0.6.4-06 | `api/migrations/0028_fault_event_backfill_room.py` | 新增 | 数据回填 migration |
| MOD-v0.6.4-07 | `api/views_fault.py` | 修改 | 新增 room_name 过滤参数 |
| MOD-v0.6.4-08 | `api/serializers_fault.py` | 修改 | 新增 room_name/room_id 字段序列化 |
| MOD-v0.6.4-09 | `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 修改 | 新增房间列 + 房间过滤器 |
| MOD-v0.6.4-10 | `seed_device_config.py`（路径待确认） | 修改 | 新 sub_type 条目 |

---

## 2. 各模块详细设计

### MOD-v0.6.4-01：constants.py

**变更摘要**：
- 删除：`living_room_thermostat`、`bedroom_thermostat`、`children_room_thermostat`、`study_room_thermostat`、`fourth_children_room_thermostat` 五条旧 sub_type 条目（从 3 个字典中全部移除）。
- 新增：`living_room_main`、`master_bedroom_panel`、`secondary_bedroom_panel`、`children_room_panel`、`study_room_panel` 五条新 sub_type 条目。
- 新增：`VALID_ROOM_NAMES: frozenset` 常量（白名单）。
- 不变：`fresh_air_unit`、`hydraulic_module`、`energy_meter`、`air_quality_sensor` 四条非温控 sub_type。
- 不变：`FAULT_TYPE_LABELS`、`ERROR_CODE_LABELS`、`PRODUCT_CODE_LABELS`、`DEVICE_NAME_OVERRIDE`、`EXACT_FAULT_MAP`、`SUFFIX_FAULT_RULES`。

**SUB_TYPE_TO_FAULT_CODES 重叠风险说明**：
`master_bedroom_panel` 和 `secondary_bedroom_panel`、`children_room_panel` 各自在 fault_codes 路径下包含重叠的 PLC 前缀 fault_code（如 `bedroom_*` 系列）。这在命名型 fault_code 路径下存在理论歧义，但因生产 DB 中命名型 fault_code 不存在（BUG-FM-005 确认，db_evidence.md 查询 3 实测再次验证），实际过滤完全依赖 ori_room_name 关键词路径，命名型路径仅为向后兼容保留。

**DB 实测结论（2026-05-29 新增）**：
- 生产 fault_event 中 `fault_code REGEXP 'bedroom|children_room|study_room|fourth_children_room'` 返回零行。
- constants.py L125-126 注释明确说明命名型 fault_code 在生产不存在。
- 过滤主路径确认为 `device_sn → device_node → device_room.ori_room_name`，与架构设计 §2.1 一致。

**测试要求**：
- 测试用例需验证每个新 sub_type 对应的 ori_room_name 关键词过滤能正确区分 3 房/4 房（见 US-FM-010 的 GWT）。
- 集成测试 oracle 参见架构设计附录 F（architecture_design_v0.6.4_fault_mgmt_room_column.md §11）。

---

### MOD-v0.6.4-02：room_lookup.py（新文件）

**接口定义**：
```python
def get_room_for_device(device_sn: str) -> tuple[str | None, int | None]
```

**内部逻辑**：
1. 尝试 `int(device_sn)` 转换，失败返回 (None, None)。
2. `DeviceNode.objects.select_related('room').filter(device_sn=sn_int).first()`。
3. 返回 `(dn.room.ori_room_name, dn.room_id)` 或 (None, None)。
4. 全路径 try/except，异常仅 log ERROR，不上抛。

**性能说明**：
- DeviceNode 表 ~6124 行，device_sn 列有索引（migration 0022）；每次查询 <1ms。
- T1 INSERT 每次新故障首次出现才调用（非高频），无需缓存。
- 如未来 T1 频率极高（如压测场景），可在 room_lookup.py 内部增加进程内 TTL 缓存（预留设计，本期不实现）。

**单测覆盖要求**：
- 正常 device_sn → (room_name, room_id) 返回。
- device_sn 不在 DeviceNode → (None, None)。
- device_sn 非整数字符串 → (None, None)。
- DB 异常 → (None, None) + ERROR 日志。

---

### MOD-v0.6.4-03：state_machine.py

**变更范围**：仅 `_t1_insert()` 函数。

**变更内容**：
1. 函数签名不变（不新增参数，room_name/room_id 由内部自行查找）。
2. 在 `FaultEvent.objects.create()` 调用前，追加：
   ```python
   from .room_lookup import get_room_for_device
   room_name, room_id = get_room_for_device(device_sn)
   ```
3. `FaultEvent.objects.create()` 调用增加 `room_name=room_name` 和 `room_id=room_id` 两个参数。
4. T2/T3 路径不涉及 room 字段（T2 不写 DB，T3 只更新 is_active/recovered_at/last_seen_at）。

**不变约束**：
- `rebuild_from_db()` 不变（从 DB 重建状态机，room 字段不影响重建逻辑）。
- `_t1_fallback_update()` 不变（UPDATE last_seen_at，不更新 room 字段）。

---

### MOD-v0.6.4-04：models.py

**变更范围**：`FaultEvent` 类。

**新增字段**：
```python
room_name = models.CharField(
    max_length=50, null=True, blank=True,
    verbose_name='房间名称',
)
room_id = models.ForeignKey(
    'DeviceRoom',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='fault_events',
    verbose_name='所属房间',
    db_column='room_id',
)
```

**Meta 索引（可选）**：
```python
models.Index(fields=['room_name', 'is_active'], name='idx_fault_room_active'),
```
是否添加由开发阶段性能测试决定（生产 fault_event 行数量级小，可能不需要）。

---

### MOD-v0.6.4-05 & 06：migrations

见架构设计附录 D（完整代码片段已给出）。

---

### MOD-v0.6.4-07：views_fault.py

**新增过滤参数**（在现有 `specific_part` 过滤块之后追加）：
```python
# --- room_name 过滤（FR-FM-009-filter，v0.6.4-FM-ROOM）---
from .fault_consumer.constants import VALID_ROOM_NAMES

room_names = request.query_params.getlist('room_name')
if room_names:
    valid_room_names = [r for r in room_names if r in VALID_ROOM_NAMES]
    if valid_room_names:
        qs = qs.filter(room_name__in=valid_room_names)
```

**接口文档更新**：在函数 docstring 的"查询参数"表中追加 `room_name` 行。

---

### MOD-v0.6.4-08：serializers_fault.py

**新增字段**（在现有 `device_name` 字段之后）：
```python
room_name = serializers.CharField(source='room_name', allow_null=True, read_only=True)
room_id   = serializers.IntegerField(source='room_id_id', allow_null=True, read_only=True)
```

将 `room_name`、`room_id` 加入 `Meta.fields` 列表。

---

### MOD-v0.6.4-09：FaultManagementView.vue

**表格列新增**：
```vue
<!-- 在"设备名称"列之后插入 -->
<el-table-column prop="room_name" label="房间" width="100" align="center">
  <template #default="scope">
    {{ scope.row.room_name || '-' }}
  </template>
</el-table-column>
```

**过滤器新增**：
```vue
<!-- 在现有过滤器区域追加 -->
<el-form-item label="房间">
  <el-select v-model="filters.room_name" multiple clearable placeholder="全部房间">
    <el-option v-for="room in ROOM_OPTIONS" :key="room" :label="room" :value="room"/>
  </el-select>
</el-form-item>
```

```javascript
// 常量
const ROOM_OPTIONS = ['客厅', '主卧', '次卧', '儿童房', '书房']

// filters 对象新增
room_name: []

// fetchFaultEvents() URLSearchParams 追加
filters.room_name.forEach(r => params.append('room_name', r))
```

---

### MOD-v0.6.4-10：seed_device_config.py

**注**：开发阶段需先确认 `seed_device_config.py` 实际文件路径和现有 sub_type 条目格式，再做精确修改。本文档以语义为准（见架构设计附录 C），实现细节由 sub_agent_software_developer 补充。

---

## 3. 依赖关系图

```
constants.py (MOD-01)
    ↓ import
views_fault.py (MOD-07)     ← 新增 room_name 过滤
state_machine.py (MOD-03)
    ↑ import
room_lookup.py (MOD-02)     ← T1 INSERT 调用

models.py (MOD-04)
    ↑ import
migrations/0027 (MOD-05)    ← DDL ALTER TABLE
migrations/0028 (MOD-06)    ← 数据回填 UPDATE

serializers_fault.py (MOD-08)
    ↑ import
views_fault.py (MOD-07)

FaultManagementView.vue (MOD-09)
    ← 前端，调用 views_fault.py API
```

**循环依赖检查**：无循环依赖。
- `room_lookup.py` 只 import `api.models`（内部延迟 import，同现有 state_machine.py 模式）。
- `constants.py` 无 import，纯常量模块（同现状）。

---

## 4. 测试覆盖要求摘要

| 模块 | 测试类型 | 关键场景 |
|------|---------|---------|
| room_lookup.py | 单元测试 | 正常/无关联/非整数/DB异常 四场景 |
| state_machine.py | 单元测试 | T1 INSERT 后 fault_event.room_name 正确写入 |
| views_fault.py | 集成测试 | room_name 过滤参数有效；白名单拒绝无效值 |
| constants.py | 单元测试 | 新 sub_type 在白名单中；旧 sub_type 不在白名单 |
| migration 0028 | 集成测试 | 回填前后 room_name 行数变化符合预期 |
| FaultManagementView.vue | E2E/组件测试 | 房间列展示；"-"兜底；房间过滤器有效 |
| AC-010-04（书房 3 房返回 0 条）| 集成测试 | `study_room_panel` + 3 房 specific_part → 0 行 |
