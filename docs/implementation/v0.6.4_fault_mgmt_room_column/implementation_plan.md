# 实现计划文档

```
file_header:
  document_id: IMPL-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 实现计划
  author_agent: sub_agent_software_developer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.4_fault_mgmt_room_column.md (v0.4.0-APPROVED)
    - docs/architecture/module_design_v0.6.4_fault_mgmt_room_column.md (APPROVED)
```

---

## 1. 实现范围

本实现覆盖架构文档附录 G（GROUP_C 实现操作清单 v0.4.0 修正版，7 步）定义的全部变更。

**明确排除（非 v0.6.4 范围）**：
- `seed_device_config.py` 改动（DeviceConfig 表 sub_type 重组）
- DeviceConfig 表任何变更
- 生产部署（由后续 GROUP_E 负责）

---

## 2. 实现步骤摘要

| 步骤 | 文件 | 变更类型 | 状态 |
|------|------|---------|------|
| 1 | `api/fault_consumer/constants.py` | 修改（三字典重写 + VALID_ROOM_NAMES） | 完成 |
| 2 | `api/fault_consumer/room_lookup.py` | 新建 | 完成 |
| 3 | `api/models.py` | 修改（FaultEvent 新增 room_name + room_id） | 完成 |
| 4 | `api/migrations/0027_fault_event_room_columns.py` | 新建（DDL） | 完成 |
| 5 | `api/migrations/0028_fault_event_backfill_room.py` | 新建（数据回填） | 完成 |
| 6a | `api/fault_consumer/state_machine.py` | 修改（_t1_insert room_lookup 调用） | 完成 |
| 6b | `api/serializers_fault.py` | 修改（room_name/room_id 字段输出） | 完成 |
| 6c | `api/views_fault.py` | 修改（room_name 过滤参数） | 完成 |
| 7 | `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 修改（房间列 + 房间过滤器） | 完成 |

---

## 3. 各步骤详情

### 步骤 1：constants.py 重写

**变更**：
- SUB_TYPE_ROOM_FILTER：旧 `living_room_thermostat / study_room_thermostat / bedroom_thermostat / children_room_thermostat / fourth_children_room_thermostat` 替换为 `living_room_main / master_bedroom_panel / secondary_bedroom_panel / children_room_panel / study_room_panel`。
- SUB_TYPE_LABELS：同步更新 key 及中文标签（`第四儿童房温控面板` 条目删除）。
- SUB_TYPE_TO_FAULT_CODES：重组命名型 fault_code 列表（向后兼容 OR 路径，生产实际不使用）。
- 新增 `VALID_ROOM_NAMES: frozenset = frozenset(['客厅', '主卧', '次卧', '儿童房', '书房'])`。
- 保持不变：`EXACT_FAULT_MAP / SUFFIX_FAULT_RULES / PRODUCT_CODE_LABELS / DEVICE_NAME_OVERRIDE / ERROR_CODE_LABELS / FAULT_TYPE_LABELS`。

**关键约束遵从**：
- 按架构文档附录 B §3.0.1-3.0.3 的 unified diff 精确实现，无自由发挥。

### 步骤 2：room_lookup.py 新建

**接口**：`get_room_for_device(device_sn: str) -> tuple[str | None, int | None]`

**行为**：
- `int(device_sn)` 转换失败 → 返回 `(None, None)`，不抛异常
- DeviceNode 不存在 / room 未关联 → 返回 `(None, None)`
- DB 异常 → `logger.error(...)` + 返回 `(None, None)`
- 成功 → 返回 `(dn.room.ori_room_name, dn.room_id)`

### 步骤 3：models.py FaultEvent 新增字段

```python
room_name = models.CharField(max_length=50, null=True, blank=True, verbose_name='房间名称', ...)
room_id = models.ForeignKey('DeviceRoom', on_delete=models.SET_NULL, null=True, blank=True, ...)
```

### 步骤 4：migration 0027（DDL）

- `AddField room_name`：VARCHAR(50) NULL
- `AddField room_id`：FK to api.DeviceRoom, ON DELETE SET NULL, NULL

依赖：`('api', '0026_add_fault_event')`

### 步骤 5：migration 0028（数据回填）

- `RunPython backfill_room`：构建 `str(dn.device_sn) -> (ori_room_name, room.id)` 字典，批量 bulk_update fault_event（chunk_size=500）
- `reverse_code=reverse_backfill_room`：`UPDATE fault_event SET room_name=NULL, room_id=NULL`
- 类型对齐：`str(dn.device_sn)` 将 IntegerField 转为字符串，与 `FaultEvent.device_sn`（VARCHAR）自然匹配

依赖：`('api', '0027_fault_event_room_columns')`

### 步骤 6a：state_machine._t1_insert

在 `FaultEvent.objects.create()` 前插入：
```python
from .room_lookup import get_room_for_device
room_name, room_id = get_room_for_device(device_sn)
```
create() 调用增加 `room_name=room_name, room_id=room_id` 参数。

**T2/T3 路径不变**（不涉及 room 字段）。

### 步骤 6b：serializers_fault.py

新增 `room_id = serializers.IntegerField(source='room_id_id', allow_null=True, read_only=True)`。
Meta.fields 追加 `'room_name'`（Model 直接字段）和 `'room_id'`（显式声明字段）。

### 步骤 6c：views_fault.py

新增 import `VALID_ROOM_NAMES`。
在 is_active 过滤之前追加 room_name 过滤逻辑：
```python
room_names = request.query_params.getlist('room_name')
if room_names:
    valid_room_names = [r for r in room_names if r in VALID_ROOM_NAMES]
    if valid_room_names:
        qs = qs.filter(room_name__in=valid_room_names)
```

### 步骤 7：FaultManagementView.vue

- 表格新增"房间"列（`prop="room_name"`，`{{ scope.row.room_name || '-' }}`）。
- 过滤器区域新增房间多选（`v-model="filters.room_names"`，选项 `ROOM_OPTIONS` 静态写死）。
- `filters` reactive 追加 `room_names: []`。
- `fetchFaultEvents()` URLSearchParams 追加 `room_name` 多值 append。
- `handleReset()` 追加 `filters.room_names = []`。

---

## 4. 关键设计决策

| 决策 | 选择 | 依据 |
|------|------|------|
| room_name 存储方式 | 冗余列（方案 B+） | ADR-v0.6.4-01：避免运行时 JOIN，P95 ≤800ms |
| room 查找时机 | T1 INSERT 时调用 room_lookup | ADR-v0.6.4-03：T2/T3 不写 room 字段 |
| 过滤器选项数据源 | ROOM_OPTIONS 静态写死 | 主线 PM 指令：前端不调用接口获取房间选项 |
| migration 类型对齐 | `str(dn.device_sn)` 作为 dict key | db_evidence.md 验证：ORM 路径自动处理类型差异 |

---

## 5. 不在本实现范围

- `seed_device_config.py`（DeviceConfig 表 sub_type 重组）— 降级为 v0.6.5
- 生产 SSH / git pull / systemd 重启 — GROUP_E 范围
- E2E 浏览器自动化测试 — GROUP_D 测试工程师负责
