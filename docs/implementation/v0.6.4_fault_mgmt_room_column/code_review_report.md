# 代码评审报告

```
file_header:
  document_id: CR-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 代码评审报告
  author_agent: sub_agent_software_developer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: DRAFT
  reviewed_files:
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/room_lookup.py
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/state_machine.py
    - FreeArkWeb/backend/freearkweb/api/models.py
    - FreeArkWeb/backend/freearkweb/api/migrations/0027_fault_event_room_columns.py
    - FreeArkWeb/backend/freearkweb/api/migrations/0028_fault_event_backfill_room.py
    - FreeArkWeb/backend/freearkweb/api/serializers_fault.py
    - FreeArkWeb/backend/freearkweb/api/views_fault.py
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue
```

---

## 总体评估

**评审结论：PASS**

CRITICAL finding 数：0
HIGH finding 数：0
MEDIUM finding 数：2
LOW finding 数：3

所有变更均符合架构设计文档 v0.4.0-APPROVED 的规范要求，关键约束（禁止触碰 seed_device_config.py / DeviceConfig 表、代码注释无 emoji、constants.py 按照 unified diff 实现）均已遵从。

---

## CRITICAL Findings（0 条）

无 CRITICAL 问题。

---

## HIGH Findings（0 条）

无 HIGH 问题。

---

## MEDIUM Findings（2 条）

### M-001：serializers_fault.py room_name 字段显式声明缺失

**文件**：`FreeArkWeb/backend/freearkweb/api/serializers_fault.py`

**描述**：`room_id` 通过显式 `serializers.IntegerField(source='room_id_id', ...)` 声明（因为 Django FK 字段名为 `room_id` 但实际列名为 `room_id_id`，需要 source 映射）。`room_name` 是普通 CharField，DRF ModelSerializer 会自动从 Model 字段推断，因此加入 `Meta.fields` 列表即可。

**当前状态**：`room_name` 仅加入 `Meta.fields`（正确），无显式声明（正确，无需额外声明）。

**评估**：行为正确，`Meta.fields` 中的 `room_name` 由 DRF 自动处理 `FaultEvent.room_name` CharField。无需修复，但值得在注释中说明为何 room_name 不显式声明。

**建议**：在 `Meta.fields` 的 `'room_name'` 条目后添加注释说明 DRF 自动推断，提高可维护性。优先级：低（可跟随 LOW-001）。

**影响**：无功能影响，纯可维护性问题。标记为 MEDIUM 是因为不一致性（room_id 显式，room_name 隐式）可能令后续维护者困惑。

---

### M-002：migration 0028 reverse_backfill_room 使用 room_id_id 一致性

**文件**：`FreeArkWeb/backend/freearkweb/api/migrations/0028_fault_event_backfill_room.py`

**描述**：`reverse_backfill_room` 中使用 `FaultEvent.objects.all().update(room_name=None, room_id_id=None)`。在迁移框架的 `apps.get_model()` 上下文中，Django 使用历史模型，FK 字段通过 `room_id_id` 操作通常有效，但部分 Django 版本中历史模型的 FK 访问器行为可能与实际模型略有差异。

**评估**：在 Django 4.x / 5.x 中，`room_id_id=None` 在 `update()` 中等价于设置 FK 为 NULL，行为正确。参考架构文档附录 D §5.2 给出的代码，当前实现与规范一致。SQLite 测试环境下回滚路径已在规范中明确描述。

**建议**：在集成测试中显式验证 migration 0028 回滚后 room_name 和 room_id 均为 NULL（已包含在测试计划要求中）。当前代码无需修改，测试覆盖即可。

---

## LOW Findings（3 条）

### L-001：serializers_fault.py 注释完整性

**文件**：`FreeArkWeb/backend/freearkweb/api/serializers_fault.py`

**描述**：新增的 `room_id` SerializerField 声明在 `__init__` 中但 `Meta.fields` 列表的注释未同步说明 `room_name` 为 DRF 自动推断字段（vs `room_id` 为显式声明）。

**建议**：在 `Meta.fields` 的 `room_name` / `room_id` 两行添加行内注释，如 `# 新增（v0.6.4-FM-ROOM）DRF 自动推断` 和 `# 新增（v0.6.4-FM-ROOM）显式声明，source=room_id_id`。

**影响**：纯注释可维护性，无功能影响。

---

### L-002：views_fault.py fault_event_categories docstring 未更新

**文件**：`FreeArkWeb/backend/freearkweb/api/views_fault.py`

**描述**：`fault_event_categories` 函数 docstring 中 `sub_types` 示例仍引用旧 `living_room_thermostat`（`"value": "living_room_thermostat", "label": "客厅温控面板"`），未同步更新为新值。

**建议**：更新 docstring 示例为 `"value": "living_room_main", "label": "客厅主温控"`。

**影响**：仅 docstring，不影响运行时行为。

---

### L-003：FaultManagementView.vue 房间过滤器 placeholder 可考虑国际化

**文件**：`FreeArkWeb/frontend/src/views/FaultManagementView.vue`

**描述**：新增房间过滤器的 `placeholder="全部房间"` 为硬编码中文字符串。与现有代码（如"选择设备类型"等）风格一致，但若未来需要国际化支持，需统一处理。

**建议**：当前风格一致，无需修改。记录为技术债，若项目启动 i18n，统一处理。

**影响**：无功能影响，风格一致性问题。

---

## 合规性检查

| 检查项 | 结果 |
|--------|------|
| 未触碰 seed_device_config.py | 通过 |
| 未触碰 DeviceConfig 表 | 通过 |
| constants.py 三字典按 unified diff 实现 | 通过 |
| migration 字段类型对齐（str(dn.device_sn)） | 通过 |
| _t1_insert 在 create() 前调用 room_lookup | 通过 |
| room_lookup 失败返回 (None, None) 不抛异常 | 通过 |
| 前端 ROOM_OPTIONS 静态写死 | 通过 |
| 前端 room_name 兜底 row.room_name \|\| '-' | 通过 |
| 代码注释无 emoji | 通过 |
| VALID_ROOM_NAMES 白名单用于 views_fault.py | 通过 |
| migration 0027 依赖链正确（0026 -> 0027 -> 0028） | 通过 |
| room_id FK ON DELETE SET NULL | 通过 |

---

## 遗留注意事项（供测试工程师参考）

1. **views_fault.py sub_type 白名单逻辑**：`if st not in SUB_TYPE_LABELS` 现在会拒绝旧的 `living_room_thermostat / bedroom_thermostat` 等（这些不在新 `SUB_TYPE_LABELS` 中），旧过滤参数静默忽略。这是预期行为（ADR-v0.6.4-02 §2 "旧 sub_type 在过滤路径上已通过白名单静默忽略"）。集成测试应验证旧参数被静默忽略而非报错。

2. **migration 0028 SQLite 行为**：SQLite 测试 DB 通常无历史 FaultEvent 数据（或极少），migration 0028 回填行数可能为 0，这是预期行为。测试应构造 FaultEvent fixture 后再验证回填。

3. **room_id FK 在 SQLite 测试**：SQLite 不强制外键约束（需 PRAGMA foreign_keys=ON），测试需确认 room_id 值为有效 DeviceRoom.id 或 NULL，不依赖 SQLite 的外键强制机制。
