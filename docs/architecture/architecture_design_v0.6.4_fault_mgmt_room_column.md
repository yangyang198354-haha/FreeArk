# 架构设计文档

```
file_header:
  document_id: ARCH-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 架构设计
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: APPROVED
  references:
    - docs/requirements/v0.6.4_fault_mgmt_room_column/requirements_spec.md
    - docs/requirements/v0.6.4_fault_mgmt_room_column/db_evidence.md
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py (v0.6.3-FM)
    - FreeArkWeb/backend/freearkweb/api/views_fault.py (v0.6.3-FM)
    - FreeArkWeb/backend/freearkweb/api/models.py
    - datacollection/resource/plc_config.json
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-29 | 初始草稿，含 ADR-v0.6.4-01~05、PLC 映射附录 A、代码片段附录 B |
| 0.2.0-APPROVED | 2026-05-29 | 吸收 DB 实测结论（db_evidence.md COMPLETED）：新增 §2.1 主过滤路径说明 + 附录 F（error_code 反推表 oracle）；关闭全部 OD；migration 回填 SQL 增加类型对齐说明；status 升为 APPROVED |
| 0.3.0-APPROVED | 2026-05-29 | 附录 C 升级至行级精确版本：实读 seed_device_config.py 实际内容，确认 4 个 panel_* sub_type 条目（panel_study_room / panel_bedroom / panel_children_room / panel_fourth_children）、每条记录行号、11 个 param_name、完整 unified diff、--reset 后预期记录数及验证 SQL；新增附录 G（GROUP_C 开发操作清单）；确认 product_code 字段不在 DeviceConfig 模型中；结论：5 个新 sub_type 均可用单一 ori_room_name 关键词覆盖两种户型，无需户型判定 |
| 0.4.0-APPROVED | 2026-05-29 | **范围修正（主线门控指令）**：v0.6.4 范围明确限定为"故障管理页过滤器（constants.py 三字典）+ fault_event 表新增 room_name/room_id 列 + 前端 FaultManagementView 房间列和房间筛选器"。seed_device_config.py 改动（DeviceConfig 表 sub_type 重命名）属设备设置页卡片重组，不在 v0.6.4 范围内，降级为未来工作（v0.6.5 考虑）。附录 C 全段降级为"未来工作备忘"，不再属于 GROUP_C 实现范围。GROUP_C 操作清单从 11 步缩减为 7 步（移除步骤 9 seed_device_config），模块影响矩阵和部署顺序同步移除 seed_device_config 条目。附录 B 新增精确 unified diff（constants.py 旧 sub_type → 新 sub_type）。 |

---

## 1. 架构决策记录（ADR）

### ADR-v0.6.4-01：fault_event 房间字段实现选择（方案 B+）

**背景**：需在故障列表展示房间名称。

**备选方案**：
1. 方案 A（运行时 JOIN）：查询 fault_event 时 JOIN device_node → device_room，实时计算 ori_room_name。
2. 方案 B（冗余列 room_name）：fault_event 新增 room_name VARCHAR(50)，写入时填充。
3. 方案 B+（room_name + room_id）：在方案 B 基础上增加 room_id INT 外键（ON DELETE SET NULL）。

**决策**：采用方案 B+。

**理由**：
- 方案 A 需要每次查询额外 JOIN，且 JOIN 路径需经 device_node → device_room（2 表），加上 specific_part → owner_info 可能需 4 表 JOIN，性能不可控。
- 方案 B 的冗余 room_name 使查询端零额外 JOIN，P95 目标 ≤800ms 更稳固。
- 方案 B+ 增加 room_id 外键的意义：支持未来按 room_id 做结构化查询（如"房间维度统计"），且 ON DELETE SET NULL 确保 device_room 清理不引发数据丢失。
- 历史数据量（约 3094 行）极小，一次性回填 migration 代价低。

**权衡**：
- 冗余 room_name 在住户设备树重同步时不会自动更新（room_id 也不会）。评估：FaultEvent 是历史事件记录，其 room_name 应反映故障发生时的设备归属，与事后重同步无关，冗余是合理的。
- room_id ON DELETE SET NULL 意味着 room 被删除后历史故障仍保留，room_name 作为备份继续可用。

---

### ADR-v0.6.4-02：sub_type 重组策略（方案 B — 一次到位）

**背景**：现有 sub_type 语义为 PLC 寄存器组（`bedroom_thermostat`="三房主卧四房次卧"），用户理解成本高。

**备选方案**：
1. 方案 A（双轨兼容，新旧并存）：新增 5 个"房间"sub_type，保留旧 4 个，前端展示新 sub_type。
2. 方案 B（一次到位重组）：删除旧 4 个 sub_type（bedroom/children_room/study_room/fourth_children_room）并重建为 5 个房间 sub_type。

**决策**：采用方案 B（一次到位）。

**理由**：
- 旧 sub_type 从未在生产环境中被外部系统 API 消费（仅内部使用），不存在向下兼容压力。
- 双轨方案增加维护复杂度（6 个 sub_type vs 5 个），且旧 sub_type 语义混乱，双轨只会延长混乱期。
- views_fault.py 的 sub_type 白名单（`if st not in SUB_TYPE_LABELS`）会静默忽略旧 sub_type，旧参数无破坏性。

**v0.6.4 范围边界（v0.4.0 修正）**：
- v0.6.4 的重组范围**仅限于 `fault_consumer/constants.py` 三字典**（SUB_TYPE_ROOM_FILTER / SUB_TYPE_LABELS / SUB_TYPE_TO_FAULT_CODES）。
- 故障管理页过滤器数据源是 `constants.py`，与 DeviceConfig 表**完全无关**（`fault_event_categories` 接口直接 dump 字典，无 DB 查询）。
- `seed_device_config --reset` 改动的是设备设置页 UI 卡片分组展示（DeviceConfig 表），属于独立关注点，**降级为 v0.6.5 考虑，不在本次范围内**。

---

### ADR-v0.6.4-03：room 查找在 T1 INSERT 中的实现位置

**背景**：新 T1 INSERT 需要从 device_sn 反查 DeviceRoom。

**备选方案**：
1. state_machine._t1_insert() 内部直接查 DeviceNode.objects.filter(device_sn=int(sn)).select_related('room')。
2. 新增独立辅助函数 `get_room_for_device(device_sn: str) -> tuple[str | None, int | None]`，由 _t1_insert 调用。

**决策**：采用方案 2（独立辅助函数）。

**理由**：
- `_t1_insert` 已经较长，分离关注点。
- 辅助函数可独立单测，无需 mock 完整的 T1 INSERT 路径。
- 出错时返回 `(None, None)` 元组，调用方一行处理，不影响主路径。

**辅助函数签名**：
```python
def get_room_for_device(device_sn: str) -> tuple[str | None, int | None]:
    """从 device_sn 反查 DeviceRoom，返回 (ori_room_name, room_id)。
    查找失败时返回 (None, None)，不抛异常。
    """
```

---

### ADR-v0.6.4-04：fault_event 房间列 views_fault.py 过滤实现

**背景**：FR-FM-009-filter 需要按 room_name 过滤 fault_event。

**决策**：新增 `room_name` 查询参数，在 `fault_event.room_name` 列上做 `__in` 过滤（支持多值）。不走 device_room JOIN（因为 room_name 已是冗余列）。

**实现**：
```python
room_names = request.query_params.getlist('room_name')
if room_names:
    valid_room_names = [r for r in room_names if r in VALID_ROOM_NAMES]
    if valid_room_names:
        qs = qs.filter(room_name__in=valid_room_names)
```

其中 `VALID_ROOM_NAMES = frozenset(['客厅', '主卧', '次卧', '儿童房', '书房'])` 定义在 constants.py（白名单防止注入无效值）。

---

### ADR-v0.6.4-05：migration 0028（数据回填）的执行策略

**背景**：需对 fault_event 历史数据（~3094 行）回填 room_name + room_id。

**决策**：作为独立 Django migration（RunPython），通过 Django ORM 批量 UPDATE，在 fault_consumer 停止期间执行。

**核心回填逻辑**（见附录 C）：
- 查询所有 `fault_event WHERE room_name IS NULL`。
- 按 device_sn 分组，批量查 DeviceNode + DeviceRoom，构建 `{device_sn: (room_name, room_id)}` 字典。
- UPDATE fault_event 批量设置 room_name 和 room_id。
- 记录回填行数到 Django 日志。

**回滚策略**：migration 0028 是纯数据写入（room_name/room_id 原本为 NULL），回滚即将这两列重置为 NULL（migration 0028 的 reverse_sql：`UPDATE fault_event SET room_name=NULL, room_id=NULL`）。migration 0027（DDL）回滚：`ALTER TABLE fault_event DROP COLUMN room_name, DROP COLUMN room_id`（标准 Django migrate --reverse 支持）。

---

## 2. PLC ↔ 实际房间映射表（附录 A）

> 权威来源：`datacollection/resource/plc_config.json` 所有 description 字段逐一核对（2026-05-29）。

| PLC 参数前缀 | description 原文 | 3 房（ori_room_name） | 4 房（ori_room_name） | 新 sub_type | fault_code 前缀示例 |
|------------|-----------------|--------------------|--------------------|------------|-------------------|
| `living_room_*` | 客厅 | 客厅 | 客厅 | `living_room_main` | `living_room_temp_sensor_error` |
| `bedroom_*` | 三房主卧四房次卧 | 主卧 | 次卧 | `master_bedroom_panel`（3 房）/ `secondary_bedroom_panel`（4 房） | `bedroom_temp_sensor_error` |
| `children_room_*` | 三房儿童房四房主卧 | 儿童房 | 主卧 | `children_room_panel`（3 房）/ `master_bedroom_panel`（4 房） | `children_room_temp_sensor_error` |
| `study_room_*` | 三房次卧四房书房 | 次卧 | 书房 | `secondary_bedroom_panel`（3 房）/ `study_room_panel`（4 房） | `study_room_temp_sensor_error` |
| `fourth_children_room_*` | 四房儿童房 | 不适用 | 儿童房 | `children_room_panel`（4 房） | `fourth_children_room_temp_sensor_error` |

**关键洞察**：
- "按实际房间"过滤的正确权威是 `device_room.ori_room_name`，而不是 `fault_code` 前缀。
- `bedroom_*` fault_code 在 3 房户型的设备 ori_room_name="主卧"，在 4 房户型的设备 ori_room_name="次卧"——同一 PLC 寄存器前缀对应不同实际房间，这正是旧语义混乱的根源。
- 过滤路径不变（已有 device_node JOIN device_room ori_room_name__regex），只需更新 ori_room_name 关键词。

---

## 2.1 为什么主过滤路径是 device_sn→ori_room_name，SUB_TYPE_TO_FAULT_CODES 仅作 OR 联合补充

> 本节为 DB 实测（db_evidence.md，2026-05-29）完成后新增，记录架构选择的实测依据。

### 问题根源

v0.6.3 以前的实现在 `views_fault.py` 的 sub_type 过滤逻辑中，同时使用两条路径：

1. **fault_code 文本匹配路径**：`Q(fault_code__in=SUB_TYPE_TO_FAULT_CODES[st])` — 匹配命名型 fault_code（如 `bedroom_temp_sensor_error`）。
2. **device_sn 路径**：通过 `device_node JOIN device_room` 的 `ori_room_name__regex` 关键词，取满足条件的 `device_sn` 集合，`Q(device_sn__in=...)`。

### 实测发现（A-03 修正）

生产数据库 `fault_event` 表中，**不存在任何字面 PLC 前缀格式的 fault_code**。

```
-- db_evidence.md 查询 3 实测（2026-05-29）：
fault_code REGEXP '(children_room|fourth_children_room|study_room|bedroom)' → 零行

-- 实际 fault_code 分布（top-20）：
comm_fault_timeout: 1294 行
error_679:           767 行
error_709:            95 行
error_739:            70 行
error_769:            48 行
error_799:            40 行
... （全部为 error_NNN 数字码 + 通信超时统一码）
```

constants.py L125-126 注释已明确说明这一事实：

> 注意：生产数据库中命名型 fault_code 实际上不存在（见 BUG-FM-005 RCA），本映射保留用于兼容未来可能出现的命名型故障码，以及 OR 联合过滤时的精确匹配。

### 架构结论

| 路径 | 生产有效性 | 结论 |
|------|-----------|------|
| `device_sn → device_node → device_room.ori_room_name`（复合键 `product_code + ori_room_name`） | **有效**：error_NNN 通过 device_sn 反查 DeviceRoom 精确定位房间（db_evidence 查询 3 反向验证闭环） | **主过滤路径** |
| `fault_code__in=SUB_TYPE_TO_FAULT_CODES[st]`（命名型 fault_code 匹配） | **当前无效**：生产 fault_event 无此类 fault_code | **OR 联合补充路径**，保留以兼容未来命名型码 |

**因此，v0.6.4 的 sub_type 过滤器重构不依赖、也不修改 `SUB_TYPE_TO_FAULT_CODES` 的语义**，只需确保 `SUB_TYPE_ROOM_FILTER` 的 `ori_room_name` 关键词正确覆盖所有房间类型。`SUB_TYPE_TO_FAULT_CODES` 继续保留为向后兼容的 OR 联合字段，待未来命名型 fault_code 真实出现时启用。

### 实测闭环验证（3-1-602 四房）

db_evidence.md 查询 3 反向结果证明 device_sn → ori_room_name 反查路径完全可靠：

| fault_code 主码 | device_sn | ori_room_name（device_room） | 新 sub_type |
|----------------|-----------|------------------------------|------------|
| error_679 | 22158 | 客厅 | `living_room_main` |
| error_709 | 22552 | 书房 | `study_room_panel` |
| error_739 | 22553 | 次卧 | `secondary_bedroom_panel` |
| error_769 | 22554 | 主卧 | `master_bedroom_panel` |
| error_799 | 22555 | 儿童房 | `children_room_panel` |

5 台设备、5 个房间、5 个 sub_type 一一对应，无歧义。

---

## 3. constants.py 三字典精确 unified diff + 重写后结构（附录 B）

> **v0.4.0 新增**：§3.0 给出精确 unified diff（旧名 → 新名），帮助开发者明确每个 key 的变化。§3.1 为重写后完整定义（代码片段，开发时直接照抄）。
>
> **旧 sub_type 实名（当前生产 constants.py v0.6.3-FM 中 SUB_TYPE_LABELS 的 key）**：
> - `living_room_thermostat`（客厅温控面板）
> - `study_room_thermostat`（书房温控面板）
> - `bedroom_thermostat`（主卧温控面板）
> - `children_room_thermostat`（儿童房温控面板）
> - `fourth_children_room_thermostat`（第四儿童房温控面板）
> - `fresh_air_unit`、`hydraulic_module`、`energy_meter`、`air_quality_sensor`（保持不变）

---

### 3.0 三字典精确 unified diff（旧 sub_type → 新 sub_type）

以下是 v0.6.4 对 `fault_consumer/constants.py` 三字典的精确变更，以 unified diff 格式呈现。

#### 3.0.1 SUB_TYPE_ROOM_FILTER unified diff

```diff
--- a/fault_consumer/constants.py (v0.6.3-FM SUB_TYPE_ROOM_FILTER)
+++ b/fault_consumer/constants.py (v0.6.4-FM-ROOM SUB_TYPE_ROOM_FILTER)

 SUB_TYPE_ROOM_FILTER: dict = {
-    'living_room_thermostat':           (['260001'], []),
-    'study_room_thermostat':            (['120003'], ['书房', '次卧']),
-    'bedroom_thermostat':               (['120003'], ['主卧']),
-    'children_room_thermostat':         (['120003'], ['儿童房']),
-    'fourth_children_room_thermostat':  (['120003'], ['儿童房']),
+    'living_room_main':                 (['260001'], []),
+    'master_bedroom_panel':             (['120003'], ['主卧']),
+    'secondary_bedroom_panel':          (['120003'], ['次卧']),
+    'children_room_panel':              (['120003'], ['儿童房']),
+    'study_room_panel':                 (['120003'], ['书房']),
     'fresh_air_unit':                   (['130004'], []),
     'hydraulic_module':                 (['270001'], []),
     'energy_meter':                     (['250001'], []),
     'air_quality_sensor':               (['100007'], []),
+    # 新增白名单常量（供 views_fault.py room_name 过滤参数校验）
 }
+
+VALID_ROOM_NAMES: frozenset = frozenset(['客厅', '主卧', '次卧', '儿童房', '书房'])
```

**变更说明**：
- `living_room_thermostat` → `living_room_main`（语义从"客厅温控面板"更名为"客厅主温控"，product_code=260001 不变，room_keywords=[] 不变）
- `study_room_thermostat` + `bedroom_thermostat` 的 room_keywords 重组：旧方案将两者合并在 study_room_thermostat 中用 `['书房','次卧']` 匹配，新方案按物理房间拆分为 `secondary_bedroom_panel`（次卧）和 `study_room_panel`（书房）两个独立 key。
- `bedroom_thermostat`（主卧）→ `master_bedroom_panel`（主卧），room_keywords `['主卧']` 不变。
- `children_room_thermostat`（儿童房）→ `children_room_panel`（儿童房），room_keywords `['儿童房']` 不变。
- `fourth_children_room_thermostat` 删除（原来与 `children_room_thermostat` 完全重叠，均映射到 `['儿童房']`，合并到 `children_room_panel`）。
- 净变化：9 个 key → 9 个 key（5 个非温控保持不变，4 个旧温控 key 替换为 5 个新 key，合计相同）。

#### 3.0.2 SUB_TYPE_LABELS unified diff

```diff
--- a/fault_consumer/constants.py (v0.6.3-FM SUB_TYPE_LABELS)
+++ b/fault_consumer/constants.py (v0.6.4-FM-ROOM SUB_TYPE_LABELS)

 SUB_TYPE_LABELS: dict = {
-    'living_room_thermostat':           '客厅温控面板',
-    'study_room_thermostat':            '书房温控面板',
-    'bedroom_thermostat':               '主卧温控面板',
-    'children_room_thermostat':         '儿童房温控面板',
-    'fourth_children_room_thermostat':  '第四儿童房温控面板',
+    'living_room_main':                 '客厅主温控',
+    'master_bedroom_panel':             '主卧温控面板',
+    'secondary_bedroom_panel':          '次卧温控面板',
+    'children_room_panel':              '儿童房温控面板',
+    'study_room_panel':                 '书房温控面板',
     'fresh_air_unit':                   '新风机',
     'hydraulic_module':                 '水力模块',
     'energy_meter':                     '能耗表',
     'air_quality_sensor':               '空气品质传感器',
 }
```

**变更说明**：
- `fourth_children_room_thermostat`（第四儿童房温控面板）整条删除，不再在前端过滤器中显示。
- 其余温控类 key 按上述重命名映射更新。
- 非温控 4 条（`fresh_air_unit` / `hydraulic_module` / `energy_meter` / `air_quality_sensor`）label 内容不变，仅保留原值。

#### 3.0.3 SUB_TYPE_TO_FAULT_CODES unified diff

```diff
--- a/fault_consumer/constants.py (v0.6.3-FM SUB_TYPE_TO_FAULT_CODES)
+++ b/fault_consumer/constants.py (v0.6.4-FM-ROOM SUB_TYPE_TO_FAULT_CODES)

 SUB_TYPE_TO_FAULT_CODES: dict = {
-    'living_room_thermostat': [
+    'living_room_main': [
         'living_room_temp_sensor_error',
         'living_room_humidity_sensor_error',
         'living_room_external_temp_sensor_error',
         'living_room_communication_error',
     ],
-    'study_room_thermostat': [
-        'study_room_temp_sensor_error',
-        'study_room_humidity_sensor_error',
-        'study_room_external_temp_sensor_error',
-        'study_room_communication_error',
-    ],
-    'bedroom_thermostat': [
-        'bedroom_temp_sensor_error',
-        'bedroom_humidity_sensor_error',
-        'bedroom_external_temp_sensor_error',
-        'bedroom_communication_error',
-    ],
-    'children_room_thermostat': [
-        'children_room_temp_sensor_error',
-        'children_room_humidity_sensor_error',
-        'children_room_external_temp_sensor_error',
-        'children_room_communication_error',
-    ],
-    'fourth_children_room_thermostat': [
-        'fourth_children_room_temp_sensor_error',
-        'fourth_children_room_humidity_sensor_error',
-        'fourth_children_room_external_temp_sensor_error',
-        'fourth_children_room_communication_error',
-    ],
+    # master_bedroom_panel 覆盖 2 个 PLC 前缀：children_room_*（4 房主卧）+ bedroom_*（3 房主卧）
+    'master_bedroom_panel': [
+        'children_room_temp_sensor_error',
+        'children_room_humidity_sensor_error',
+        'children_room_external_temp_sensor_error',
+        'children_room_communication_error',
+        'bedroom_temp_sensor_error',
+        'bedroom_humidity_sensor_error',
+        'bedroom_external_temp_sensor_error',
+        'bedroom_communication_error',
+    ],
+    # secondary_bedroom_panel 覆盖 2 个 PLC 前缀：bedroom_*（4 房次卧）+ study_room_*（3 房次卧）
+    'secondary_bedroom_panel': [
+        'bedroom_temp_sensor_error',
+        'bedroom_humidity_sensor_error',
+        'bedroom_external_temp_sensor_error',
+        'bedroom_communication_error',
+        'study_room_temp_sensor_error',
+        'study_room_humidity_sensor_error',
+        'study_room_external_temp_sensor_error',
+        'study_room_communication_error',
+    ],
+    # children_room_panel 覆盖 2 个 PLC 前缀：children_room_*（3 房儿童房）+ fourth_children_room_*（4 房儿童房）
+    'children_room_panel': [
+        'children_room_temp_sensor_error',
+        'children_room_humidity_sensor_error',
+        'children_room_external_temp_sensor_error',
+        'children_room_communication_error',
+        'fourth_children_room_temp_sensor_error',
+        'fourth_children_room_humidity_sensor_error',
+        'fourth_children_room_external_temp_sensor_error',
+        'fourth_children_room_communication_error',
+    ],
+    # study_room_panel 仅 4 房书房，PLC 前缀 study_room_*（3 房时该 PLC 前缀对应次卧，归入 secondary_bedroom_panel）
+    'study_room_panel': [
+        'study_room_temp_sensor_error',
+        'study_room_humidity_sensor_error',
+        'study_room_external_temp_sensor_error',
+        'study_room_communication_error',
+    ],
     'fresh_air_unit': [
         'fresh_air_unit_stop_error',
         'fresh_air_unit_communication_error',
     ],
     'hydraulic_module': ['hydraulic_module_low_temp_error'],
     'energy_meter':     ['energy_meter_status_communication_error'],
     'air_quality_sensor': ['air_quality_sensor_communication_error'],
 }
```

**注意**：`master_bedroom_panel` 与 `children_room_panel` 的 fault_code 列表中均含 `children_room_*` 系列；`master_bedroom_panel` 与 `secondary_bedroom_panel` 均含 `bedroom_*` 系列。这在命名型 fault_code 路径下会有重叠，但生产 DB 中命名型 fault_code 实际不存在（BUG-FM-005 RCA），实际过滤效果完全由 SUB_TYPE_ROOM_FILTER 的 ori_room_name 路径决定。SUB_TYPE_TO_FAULT_CODES 仅作向后兼容 OR 路径保留。

---

### 3.1 重写后完整代码（附录 B 原内容，供开发照抄）

```python
# fault_consumer/constants.py — v0.6.4-FM-ROOM 版本
# ADR-v0.6.4-02：一次到位重组，删除旧 4 个 bedroom/children_room/study_room/fourth_children_room sub_type
# ADR-v0.6.4-04：新增 VALID_ROOM_NAMES 常量供 views_fault.py 白名单校验

# ── 新 sub_type → (product_codes, room_keywords) ──────────────────────────────
# room_keywords 基于 device_room.ori_room_name，OR 模式匹配。
# 每个 sub_type 的 room_keywords 覆盖 3 房和 4 房两种户型对应的 ori_room_name。
#
# 权威来源（各 sub_type 对应关系说明）：
#   living_room_main:       260001 客厅（3/4 房均有，不需 ori_room_name 过滤）
#   master_bedroom_panel:   120003 主卧（3 房=children_room_* 对应的 ori_room_name="主卧"
#                                        4 房=bedroom_* 对应的 ori_room_name="主卧"←待 DB 确认）
#                           过滤关键词：['主卧']（直接按 ori_room_name，不依赖 PLC 前缀）
#   secondary_bedroom_panel:120003 次卧（3 房=bedroom_* 对应 ori_room_name="次卧"
#                                        4 房=study_room_* 对应 ori_room_name="次卧"←待 DB 确认）
#                           过滤关键词：['次卧']
#   children_room_panel:    120003 儿童房（3 房=children_room_* 对应 ori_room_name="儿童房"
#                                          4 房=fourth_children_room_* 对应 ori_room_name="儿童房"）
#                           过滤关键词：['儿童房']
#   study_room_panel:       120003 书房（仅 4 房，study_room_* 对应 ori_room_name="书房"）
#                           过滤关键词：['书房']

SUB_TYPE_ROOM_FILTER: dict = {
    # 非温控类（保持不变）
    'living_room_main':           (['260001'], []),           # 客厅，product_code 天然唯一，不需关键词
    'fresh_air_unit':             (['130004'], []),
    'hydraulic_module':           (['270001'], []),
    'energy_meter':               (['250001'], []),
    'air_quality_sensor':         (['100007'], []),
    # 温控面板类（新语义，按 ori_room_name 关键词过滤）
    'master_bedroom_panel':       (['120003'], ['主卧']),
    'secondary_bedroom_panel':    (['120003'], ['次卧']),
    'children_room_panel':        (['120003'], ['儿童房']),
    'study_room_panel':           (['120003'], ['书房']),
}

# ── SUB_TYPE_LABELS（供 fault-event-categories 接口）───────────────────────────
SUB_TYPE_LABELS: dict = {
    'living_room_main':           '客厅主温控',
    'master_bedroom_panel':       '主卧温控面板',
    'secondary_bedroom_panel':    '次卧温控面板',
    'children_room_panel':        '儿童房温控面板',
    'study_room_panel':           '书房温控面板',
    'fresh_air_unit':             '新风机',
    'hydraulic_module':           '水力模块',
    'energy_meter':               '能耗表',
    'air_quality_sensor':         '空气品质传感器',
}

# ── SUB_TYPE_TO_FAULT_CODES（命名型 fault_code 向后兼容路径）─────────────────
# 注意：生产 DB 中命名型 fault_code 实际上不存在（见 BUG-FM-005 RCA）。
# 保留此映射供未来可能出现的命名型故障码，以及 OR 联合过滤时的精确匹配。
SUB_TYPE_TO_FAULT_CODES: dict = {
    'living_room_main': [
        'living_room_temp_sensor_error',
        'living_room_humidity_sensor_error',
        'living_room_external_temp_sensor_error',
        'living_room_communication_error',
    ],
    # master_bedroom_panel 覆盖 2 个 PLC 寄存器前缀的命名型 fault_code：
    'master_bedroom_panel': [
        # 4 房主卧（children_room_* PLC 前缀）
        'children_room_temp_sensor_error',
        'children_room_humidity_sensor_error',
        'children_room_external_temp_sensor_error',
        'children_room_communication_error',
        # 3 房主卧（bedroom_* PLC 前缀）
        'bedroom_temp_sensor_error',
        'bedroom_humidity_sensor_error',
        'bedroom_external_temp_sensor_error',
        'bedroom_communication_error',
    ],
    # secondary_bedroom_panel 覆盖 2 个 PLC 寄存器前缀的命名型 fault_code：
    'secondary_bedroom_panel': [
        # 4 房次卧（bedroom_* PLC 前缀）— 与 3 房主卧共用，依赖 ori_room_name 区分
        'bedroom_temp_sensor_error',
        'bedroom_humidity_sensor_error',
        'bedroom_external_temp_sensor_error',
        'bedroom_communication_error',
        # 3 房次卧（study_room_* PLC 前缀）
        'study_room_temp_sensor_error',
        'study_room_humidity_sensor_error',
        'study_room_external_temp_sensor_error',
        'study_room_communication_error',
    ],
    # children_room_panel 覆盖 2 个 PLC 寄存器前缀的命名型 fault_code：
    'children_room_panel': [
        # 3 房儿童房（children_room_* PLC 前缀）— 与 4 房主卧共用，依赖 ori_room_name 区分
        'children_room_temp_sensor_error',
        'children_room_humidity_sensor_error',
        'children_room_external_temp_sensor_error',
        'children_room_communication_error',
        # 4 房儿童房（fourth_children_room_* PLC 前缀）
        'fourth_children_room_temp_sensor_error',
        'fourth_children_room_humidity_sensor_error',
        'fourth_children_room_external_temp_sensor_error',
        'fourth_children_room_communication_error',
    ],
    'study_room_panel': [
        # 4 房书房（study_room_* PLC 前缀）— 与 3 房次卧共用，依赖 ori_room_name 区分
        'study_room_temp_sensor_error',
        'study_room_humidity_sensor_error',
        'study_room_external_temp_sensor_error',
        'study_room_communication_error',
    ],
    'fresh_air_unit': [
        'fresh_air_unit_stop_error',
        'fresh_air_unit_communication_error',
    ],
    'hydraulic_module': ['hydraulic_module_low_temp_error'],
    'energy_meter':     ['energy_meter_status_communication_error'],
    'air_quality_sensor': ['air_quality_sensor_communication_error'],
}

# ── 房间名白名单（供 views_fault.py room_name 过滤参数校验）───────────────────
VALID_ROOM_NAMES: frozenset = frozenset(['客厅', '主卧', '次卧', '儿童房', '书房'])
```

**重要说明**：`master_bedroom_panel` 和 `secondary_bedroom_panel` 的 SUB_TYPE_TO_FAULT_CODES 列表存在 fault_code 重叠（均含 `bedroom_*` 系列）。这在命名型 fault_code 路径下会产生歧义，但生产 DB 中命名型 fault_code 实际不存在（BUG-FM-005 RCA 已确认）。实际过滤效果完全依赖 `SUB_TYPE_ROOM_FILTER` 的 ori_room_name 关键词路径（精确按房间区分），命名型 fault_code 路径仅作向后兼容保留。

---

## 4. seed_device_config 重建方案（附录 C）— 未来工作备忘（非 v0.6.4 范围）

> **v0.4.0 降级声明**：本附录内容**不属于 v0.6.4 实现范围**。
>
> **原因**：`seed_device_config.py` 改动的是 `DeviceConfig` 表，供**设备设置页** UI 卡片分组展示使用，与故障管理页过滤器无任何关联。故障管理页过滤器数据源是 `constants.py`（直接 dump 字典，零 DB 查询），`DeviceConfig.objects` 在 `views_fault.py` / `serializers_fault.py` / `fault_consumer/` 中均无引用。
>
> **现状**：DeviceConfig 表中旧 panel_* sub_type 名称（`panel_study_room` / `panel_bedroom` / `panel_children_room` / `panel_fourth_children`）与故障管理功能完全解耦，不需要在 v0.6.4 中同步重命名。
>
> **建议**：DeviceConfig 表 sub_type 重组（设备设置页卡片重组）若有需要，单独立项 v0.6.5，届时从本附录的行级精确备忘中取用内容。
>
> ---
> 以下为 v0.3.0 行级精确备忘，保留供 v0.6.5 参考，**GROUP_C 开发人员不需要执行本附录任何内容**。
>
> 实读路径：`FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py`（634 行）

---

### 4.0 前置关键发现：DeviceConfig 模型无 product_code 字段

`api/models.py` 中 `DeviceConfig` 模型（L365-392）的字段集为：
```
param_name, display_name, group, sub_type, group_display, sub_type_display, is_active, created_at
```

**DeviceConfig 没有 product_code 字段**。`product_code` 是 `DeviceNode` 模型的字段，不属于 DeviceConfig。因此 ADR-v0.6.4-02 中"新 sub_type 携带 product_code 约束"的描述是指 `SUB_TYPE_ROOM_FILTER`（constants.py 中），而非 `seed_device_config.py` 的记录字段。这一点之前架构文档隐含但未显式澄清，此处确认：seed_device_config 变更范围**仅限于 sub_type / sub_type_display 重命名**，不涉及 product_code 字段。

---

### 4.1 实际 panel_* 条目清单（源码行号精确）

seed_device_config.py 中共有 **4 个温控面板类 sub_type**，每个有 **11 个 param_name 条目**：

#### 4.1.1 panel_study_room（书房-温控面板）

> 文件注释行 L124：`# ── 书房-温控面板 ──────────...`
> **注意：注释"书房"但实际 PLC 前缀是 `study_room_*`；在 3 房户型 study_room_* 对应次卧，在 4 房户型对应书房**（见 plc_config.json description "三房次卧四房书房"）

| 行号 | param_name | display_name | sub_type | sub_type_display |
|------|-----------|--------------|----------|-----------------|
| L126-132 | `study_room_ntc_temperature` | NTC温度 | `panel_study_room` | 书房-温控面板 |
| L133-140 | `study_room_condensation_alert` | 凝露提醒 | `panel_study_room` | 书房-温控面板 |
| L141-148 | `study_room_dew_point_setting` | 面板露点温度 | `panel_study_room` | 书房-温控面板 |
| L149-156 | `study_room_humidity` | 湿度 | `panel_study_room` | 书房-温控面板 |
| L157-164 | `study_room_switch` | 开关 | `panel_study_room` | 书房-温控面板 |
| L165-172 | `study_room_temperature` | 温度 | `panel_study_room` | 书房-温控面板 |
| L173-180 | `study_room_temp_setting` | 设定温度 | `panel_study_room` | 书房-温控面板 |
| L181-188 | `study_room_temp_sensor_error` | 内置温度传感器故障 | `panel_study_room` | 书房-温控面板 |
| L189-196 | `study_room_humidity_sensor_error` | 湿度传感器故障 | `panel_study_room` | 书房-温控面板 |
| L197-204 | `study_room_external_temp_sensor_error` | 外置温度传感器故障 | `panel_study_room` | 书房-温控面板 |
| L205-212 | `study_room_communication_error` | 通讯故障 | `panel_study_room` | 书房-温控面板 |

#### 4.1.2 panel_bedroom（次卧-温控面板）

> 文件注释行 L214：`# ── 次卧-温控面板 ──────────...`
> **注意：注释"次卧"但实际 PLC 前缀是 `bedroom_*`；在 3 房户型对应主卧，在 4 房户型对应次卧**（plc_config.json description "三房主卧四房次卧"）

| 行号 | param_name | display_name | sub_type | sub_type_display |
|------|-----------|--------------|----------|-----------------|
| L216-222 | `bedroom_ntc_temperature` | NTC温度 | `panel_bedroom` | 次卧-温控面板 |
| L223-230 | `bedroom_condensation_alert` | 凝露提醒 | `panel_bedroom` | 次卧-温控面板 |
| L231-238 | `bedroom_dew_point_setting` | 面板露点温度 | `panel_bedroom` | 次卧-温控面板 |
| L239-246 | `bedroom_humidity` | 湿度 | `panel_bedroom` | 次卧-温控面板 |
| L247-254 | `bedroom_switch` | 开关 | `panel_bedroom` | 次卧-温控面板 |
| L255-262 | `bedroom_temperature` | 温度 | `panel_bedroom` | 次卧-温控面板 |
| L263-270 | `bedroom_temp_setting` | 设定温度 | `panel_bedroom` | 次卧-温控面板 |
| L271-278 | `bedroom_temp_sensor_error` | 内置温度传感器故障 | `panel_bedroom` | 次卧-温控面板 |
| L279-286 | `bedroom_humidity_sensor_error` | 湿度传感器故障 | `panel_bedroom` | 次卧-温控面板 |
| L287-294 | `bedroom_external_temp_sensor_error` | 外置温度传感器故障 | `panel_bedroom` | 次卧-温控面板 |
| L295-302 | `bedroom_communication_error` | 通讯故障 | `panel_bedroom` | 次卧-温控面板 |

#### 4.1.3 panel_children_room（主卧-温控面板）

> 文件注释行 L304：`# ── 主卧-温控面板 ──────────...`
> **注意：注释"主卧"但实际 PLC 前缀是 `children_room_*`；在 3 房户型对应儿童房，在 4 房户型对应主卧**（plc_config.json description "三房儿童房四房主卧"）

| 行号 | param_name | display_name | sub_type | sub_type_display |
|------|-----------|--------------|----------|-----------------|
| L306-312 | `children_room_ntc_temperature` | NTC温度 | `panel_children_room` | 主卧-温控面板 |
| L313-320 | `children_room_condensation_alert` | 凝露提醒 | `panel_children_room` | 主卧-温控面板 |
| L321-328 | `children_room_dew_point_setting` | 面板露点温度 | `panel_children_room` | 主卧-温控面板 |
| L329-336 | `children_room_humidity` | 湿度 | `panel_children_room` | 主卧-温控面板 |
| L337-344 | `children_room_switch` | 开关 | `panel_children_room` | 主卧-温控面板 |
| L345-352 | `children_room_temperature` | 温度 | `panel_children_room` | 主卧-温控面板 |
| L353-360 | `children_room_temp_setting` | 设定温度 | `panel_children_room` | 主卧-温控面板 |
| L361-368 | `children_room_temp_sensor_error` | 内置温度传感器故障 | `panel_children_room` | 主卧-温控面板 |
| L369-376 | `children_room_humidity_sensor_error` | 湿度传感器故障 | `panel_children_room` | 主卧-温控面板 |
| L377-384 | `children_room_external_temp_sensor_error` | 外置温度传感器故障 | `panel_children_room` | 主卧-温控面板 |
| L385-392 | `children_room_communication_error` | 通讯故障 | `panel_children_room` | 主卧-温控面板 |

#### 4.1.4 panel_fourth_children（儿童房-温控面板）

> 文件注释行 L394：`# ── 儿童房-温控面板 ──────────...`
> **注意：PLC 前缀是 `fourth_children_room_*`；仅存在于 4 房户型，对应儿童房**（plc_config.json description "四房儿童房"）

| 行号 | param_name | display_name | sub_type | sub_type_display |
|------|-----------|--------------|----------|-----------------|
| L396-402 | `fourth_children_room_ntc_temperature` | NTC温度 | `panel_fourth_children` | 儿童房-温控面板 |
| L403-410 | `fourth_children_room_condensation_alert` | 凝露提醒 | `panel_fourth_children` | 儿童房-温控面板 |
| L411-418 | `fourth_children_room_dew_point_setting` | 面板露点温度 | `panel_fourth_children` | 儿童房-温控面板 |
| L419-426 | `fourth_children_room_humidity` | 湿度 | `panel_fourth_children` | 儿童房-温控面板 |
| L427-434 | `fourth_children_room_switch` | 开关 | `panel_fourth_children` | 儿童房-温控面板 |
| L435-442 | `fourth_children_room_temperature` | 温度 | `panel_fourth_children` | 儿童房-温控面板 |
| L443-450 | `fourth_children_room_temp_setting` | 设定温度 | `panel_fourth_children` | 儿童房-温控面板 |
| L451-458 | `fourth_children_room_temp_sensor_error` | 内置温度传感器故障 | `panel_fourth_children` | 儿童房-温控面板 |
| L459-466 | `fourth_children_room_humidity_sensor_error` | 湿度传感器故障 | `panel_fourth_children` | 儿童房-温控面板 |
| L467-474 | `fourth_children_room_external_temp_sensor_error` | 外置温度传感器故障 | `panel_fourth_children` | 儿童房-温控面板 |
| L475-482 | `fourth_children_room_communication_error` | 通讯故障 | `panel_fourth_children` | 儿童房-温控面板 |

---

### 4.2 旧 → 新 sub_type 精确对照（含户型语义与分裂分析）

> PLC params 对于每个条目全部**保持不变**（param_name 不变，只改 sub_type 和 sub_type_display）。没有任何条目需要合并或拆分参数。

| 旧 sub_type | 旧 sub_type_display | 旧 PLC 前缀 | 新 sub_type | 新 sub_type_display | 3 房语义 | 4 房语义 | 是否按户型分裂 |
|------------|-------------------|------------|------------|-------------------|---------|---------|-------------|
| `panel_study_room` (L124-212) | 书房-温控面板 | `study_room_*` | `secondary_bedroom_panel` | 次卧-温控面板 | 次卧（study_room_* 在 3 房是次卧） | 书房（study_room_* 在 4 房是书房） | **不分裂**：ori_room_name 区分（次卧 vs 书房，各归不同 sub_type） |
| `panel_bedroom` (L214-302) | 次卧-温控面板 | `bedroom_*` | `master_bedroom_panel`（3 房）/ `secondary_bedroom_panel`（4 房） | 主卧-温控面板 / 次卧-温控面板 | 主卧（bedroom_* 在 3 房是主卧） | 次卧（bedroom_* 在 4 房是次卧） | **不分裂**：同一批 param_name 在 DeviceConfig 中对应同一个 sub_type 条目；过滤时由 ori_room_name 自动路由到正确 sub_type |
| `panel_children_room` (L304-392) | 主卧-温控面板 | `children_room_*` | `children_room_panel`（3 房）/ `master_bedroom_panel`（4 房） | 儿童房-温控面板 / 主卧-温控面板 | 儿童房（children_room_* 在 3 房是儿童房） | 主卧（children_room_* 在 4 房是主卧） | **不分裂**（同上） |
| `panel_fourth_children` (L394-482) | 儿童房-温控面板 | `fourth_children_room_*` | `children_room_panel` | 儿童房-温控面板 | 不适用（3 房无此 PLC 设备） | 儿童房（fourth_children_room_* 仅 4 房） | **不分裂** |

**关键说明**：

`panel_bedroom` 的 11 个 param_name（`bedroom_*`）在 DeviceConfig 中应归属哪个新 sub_type？答案如下：

- `bedroom_*` 参数在**生产运行时**的物理房间，取决于该户型——3 房是主卧，4 房是次卧。
- DeviceConfig 是**静态元数据**，只定义"这批参数叫什么、属于哪个 sub_type"，不感知运行时房间。
- v0.6.4 的过滤路径是 `device_sn → ori_room_name`（主路径），DeviceConfig 的 sub_type 仅用于 UI 卡片分组展示，不参与过滤决策。
- **结论**：`bedroom_*` 参数在 DeviceConfig 中统一归入 `secondary_bedroom_panel`（次卧-温控面板）。理由：4 房户型是多数（418/634），bedroom_* 在大多数户型代表次卧；且 sub_type 在 UI 卡片展示，而过滤器走 ori_room_name，两者不冲突。**3 房住户看到的"次卧"卡片，其内容实际来自该住户 PLC 的 bedroom_* 参数（彼时 ori_room_name="主卧"），这是正确行为——过滤器按"主卧"取到 bedroom_* 的数据，卡片展示按 sub_type 分组**。
- 同理，`children_room_*` 参数统一归入 `master_bedroom_panel`（主卧-温控面板），因为 4 房大多数情况 children_room_* 代表主卧。

**param_name 变更规则**：所有 11 个 param_name 字段值不变，只改 sub_type 和 sub_type_display 两个字段。

---

### 4.3 5 个新 sub_type 的单关键词覆盖两种户型：结论与验证

#### 4.3.1 结论：不需要户型判定，单 ori_room_name 关键词足够

**核心洞察**（v0.5.7 `_match_panel_sub_types` 需要户型判定的根因）：

v0.5.7 用 `has_study_room AND has_children_room → 四房` 做户型判定，是因为旧 sub_type 是按 **PLC 寄存器前缀**命名的（`bedroom_thermostat` = 一个 PLC 前缀对应两个物理房间），所以必须先判断户型才知道"bedroom 前缀"应该被叫做"主卧还是次卧"。

新方案按**实际物理房间名**命名，每个 sub_type 直接对应一个物理房间名，过滤条件是 `ori_room_name`：
- `master_bedroom_panel` → `ori_room_name IN ['主卧']`
- `secondary_bedroom_panel` → `ori_room_name IN ['次卧']`
- `children_room_panel` → `ori_room_name IN ['儿童房']`
- `study_room_panel` → `ori_room_name IN ['书房']`
- `living_room_main` → `product_code='260001'`（不需要 ori_room_name）

过滤时先取 `product_code=120003` 的所有 DeviceNode，再按 `ori_room_name IN ['主卧']` 过滤——数据库会自然返回该户型实际有的设备。3 房有主卧（device_sn=22550，ori_room_name='主卧'），4 房也有主卧（device_sn=22554，ori_room_name='主卧'）——**两种户型的 ori_room_name 都叫"主卧"，所以单关键词 `['主卧']` 在两种户型都能命中，无需户型判定**。

#### 4.3.2 DB 实测验证（来自 db_evidence.md）

**4 房（3-1-6-602，specific_part 3-1-6-602）**：
```
device_sn=22554, product_code=120003, ori_room_name='主卧'  → master_bedroom_panel ✓
device_sn=22553, product_code=120003, ori_room_name='次卧'  → secondary_bedroom_panel ✓
device_sn=22555, product_code=120003, ori_room_name='儿童房' → children_room_panel ✓
device_sn=22552, product_code=120003, ori_room_name='书房'  → study_room_panel ✓
device_sn=22158, product_code=260001, ori_room_name='客厅'  → living_room_main ✓
```

**3 房（1-1-16-1601）**：
```
device_sn=22550, product_code=120003, ori_room_name='主卧'  → master_bedroom_panel ✓（同一关键词命中）
device_sn=22551, product_code=120003, ori_room_name='次卧'  → secondary_bedroom_panel ✓
device_sn=22549, product_code=120003, ori_room_name='儿童房' → children_room_panel ✓
（无书房设备）                                              → study_room_panel 返回 0 条 ✓（预期行为）
device_sn=22001, product_code=260001, ori_room_name='客厅'  → living_room_main ✓
```

**关键确认**：
- `master_bedroom_panel` 用 `['主卧']` 关键词：3 房 device_sn=22550（ori_room_name='主卧'）命中，4 房 device_sn=22554（ori_room_name='主卧'）命中。单关键词足够，不需要户型判定。
- `living_room_main` 只靠 `product_code=260001` 单条件足够，无需 ori_room_name。理由：db_evidence 查询 4 显示，生产中 product_code=260001 只出现在 ori_room_name='客厅'（634 行全部），没有任何其他房间的 260001 设备。
- `study_room_panel` 在 3 房户型自然零结果：3 房没有 ori_room_name='书房' 的 DeviceRoom（db_evidence 查询 2 确认：1-1-16-1601 只有 4 台设备，无书房）。这是**预期的正确行为**——用户在 3 房住户界面点"书房温控面板"，系统返回 0 条，语义正确。

---

### 4.4 完整 Unified Diff（seed_device_config.py）

```diff
--- a/FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py
+++ b/FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py
@@ -1,18 +1,18 @@
 """
 Management command: seed_device_config
 用途：初始化暖通系统的 DeviceConfig 元数据（param_name -> group/sub_type 映射）

 用法：
   python manage.py seed_device_config           # 创建缺失条目，跳过已存在
   python manage.py seed_device_config --reset   # 先删除全部再重建

 sub_type 对应关系（三恒系统定义）：
   main_thermostat       → 主温控（客厅面板 + 系统开关）
-  panel_study_room      → 书房-温控面板
-  panel_bedroom         → 次卧-温控面板
-  panel_children_room   → 主卧-温控面板
-  panel_fourth_children → 儿童房-温控面板
+  living_room_main      → 客厅主温控（原 main_thermostat 保留，新增 living_room_main 别名）
+  master_bedroom_panel  → 主卧-温控面板（覆盖 3 房儿童房*前缀 + 4 房主卧*前缀）
+  secondary_bedroom_panel → 次卧-温控面板（覆盖 3 房次卧*前缀 + 4 房次卧*前缀）
+  children_room_panel   → 儿童房-温控面板（覆盖 3 房儿童房*前缀 + 4 房儿童房*前缀）
+  study_room_panel      → 书房-温控面板（仅 4 房，3 房返回 0 条）
   fresh_air             → 新风（含加湿参数、风量设置）
   energy_meter          → 能耗表
   hydraulic_module      → 水力模块（含运行模式、节能、集中能源供给）
   air_quality           → 空气品质（CO₂、PM2.5）
 """

@@ -121,130 +121,130 @@
     # ── 书房-温控面板 ──────────────────────────────────────────────────────
     {
         'param_name': 'study_room_ntc_temperature',
         'display_name': 'NTC温度',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_condensation_alert',
         'display_name': '凝露提醒',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_dew_point_setting',
         'display_name': '面板露点温度',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_humidity',
         'display_name': '湿度',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_switch',
         'display_name': '开关',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_temperature',
         'display_name': '温度',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_temp_setting',
         'display_name': '设定温度',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_temp_sensor_error',
         'display_name': '内置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_humidity_sensor_error',
         'display_name': '湿度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_external_temp_sensor_error',
         'display_name': '外置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'study_room_communication_error',
         'display_name': '通讯故障',
         'group': 'hvac',
-        'sub_type': 'panel_study_room',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '书房-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },

     # ── 次卧-温控面板 ──────────────────────────────────────────────────────
+    # NOTE v0.6.4: bedroom_* PLC 前缀在 3 房=主卧、4 房=次卧；
+    # DeviceConfig 按 4 房大多数语义归入 secondary_bedroom_panel（次卧）；
+    # 过滤器走 ori_room_name 路径，3 房 bedroom_* 设备 ori_room_name='主卧'，
+    # 会被 master_bedroom_panel 的 room_keywords=['主卧'] 命中，不会被此条目混淆。
     {
         'param_name': 'bedroom_ntc_temperature',
         'display_name': 'NTC温度',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_condensation_alert',
         'display_name': '凝露提醒',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_dew_point_setting',
         'display_name': '面板露点温度',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_humidity',
         'display_name': '湿度',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_switch',
         'display_name': '开关',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_temperature',
         'display_name': '温度',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_temp_setting',
         'display_name': '设定温度',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_temp_sensor_error',
         'display_name': '内置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_humidity_sensor_error',
         'display_name': '湿度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_external_temp_sensor_error',
         'display_name': '外置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },
     {
         'param_name': 'bedroom_communication_error',
         'display_name': '通讯故障',
         'group': 'hvac',
-        'sub_type': 'panel_bedroom',
+        'sub_type': 'secondary_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '次卧-温控面板',
+        'sub_type_display': '次卧-温控面板',
     },

     # ── 主卧-温控面板 ──────────────────────────────────────────────────────
+    # NOTE v0.6.4: children_room_* PLC 前缀在 3 房=儿童房、4 房=主卧；
+    # DeviceConfig 按 4 房大多数语义归入 master_bedroom_panel（主卧）；
+    # 3 房 children_room_* 设备 ori_room_name='儿童房'，
+    # 被 children_room_panel 的 room_keywords=['儿童房'] 命中，语义正确。
     {
         'param_name': 'children_room_ntc_temperature',
         'display_name': 'NTC温度',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_condensation_alert',
         'display_name': '凝露提醒',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_dew_point_setting',
         'display_name': '面板露点温度',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_humidity',
         'display_name': '湿度',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_switch',
         'display_name': '开关',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_temperature',
         'display_name': '温度',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_temp_setting',
         'display_name': '设定温度',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_temp_sensor_error',
         'display_name': '内置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_humidity_sensor_error',
         'display_name': '湿度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_external_temp_sensor_error',
         'display_name': '外置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },
     {
         'param_name': 'children_room_communication_error',
         'display_name': '通讯故障',
         'group': 'hvac',
-        'sub_type': 'panel_children_room',
+        'sub_type': 'master_bedroom_panel',
         'group_display': '暖通',
-        'sub_type_display': '主卧-温控面板',
+        'sub_type_display': '主卧-温控面板',
     },

     # ── 儿童房-温控面板 ────────────────────────────────────────────────────
+    # NOTE v0.6.4: fourth_children_room_* PLC 前缀仅存在于 4 房户型，对应儿童房。
+    # 归入 children_room_panel（儿童房-温控面板）。
     {
         'param_name': 'fourth_children_room_ntc_temperature',
         'display_name': 'NTC温度',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_condensation_alert',
         'display_name': '凝露提醒',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_dew_point_setting',
         'display_name': '面板露点温度',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_humidity',
         'display_name': '湿度',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_switch',
         'display_name': '开关',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_temperature',
         'display_name': '温度',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_temp_setting',
         'display_name': '设定温度',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_temp_sensor_error',
         'display_name': '内置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_humidity_sensor_error',
         'display_name': '湿度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_external_temp_sensor_error',
         'display_name': '外置温度传感器故障',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
     {
         'param_name': 'fourth_children_room_communication_error',
         'display_name': '通讯故障',
         'group': 'hvac',
-        'sub_type': 'panel_fourth_children',
+        'sub_type': 'children_room_panel',
         'group_display': '暖通',
-        'sub_type_display': '儿童房-温控面板',
+        'sub_type_display': '儿童房-温控面板',
     },
```

> **无新增条目**：main_thermostat（客厅）的 12 个条目（L25-122）保持原 sub_type 不变，不在本次 diff 范围内。living_room_main 作为 fault 过滤器中的 sub_type 标识，与 DeviceConfig 的 main_thermostat sub_type 分属两个系统，无冲突：DeviceConfig 定义 UI 卡片分组，fault 过滤器用 SUB_TYPE_ROOM_FILTER 映射，二者解耦。

---

### 4.5 --reset 后 DeviceConfig 表预期记录数

**计算依据**：

| sub_type（新） | param_name 数量 | 来源 PLC 前缀 | is_active 全部为 True 除外 |
|--------------|----------------|-------------|--------------------------|
| `main_thermostat` | 12（含 1 条 is_active=False） | `living_room_*` + `system_switch` | system_switch is_active=False（L73） |
| `secondary_bedroom_panel` | 11 + 11 = 22 | `study_room_*`（11 条）+ `bedroom_*`（11 条） | 全部 True |
| `master_bedroom_panel` | 11 | `children_room_*` | 全部 True |
| `children_room_panel` | 11 | `fourth_children_room_*` | 全部 True |
| `fresh_air` | 17 | `fan_*` + `humidification_*` + `fresh_air_*` + `coil_*` + `supply_*` + `system_air_*` | 全部 True |
| `energy_meter` | 4 | `total_cold/hot_quantity` + `work_time` + `energy_meter_status_*` | 全部 True |
| `hydraulic_module` | 8 | `hydraulic_module_*` + `away_energy_saving` + `central_energy_supply` + `operation_mode` + `system_switch` | 全部 True |
| `air_quality` | 3 | `co2` + `pm25` + `air_quality_sensor_*` | 全部 True |

**注意**：`study_room_panel`（书房-温控面板）在新方案中**不在 DeviceConfig 中出现**，因为书房面板的 PLC 参数（`study_room_*`）已被归入 `secondary_bedroom_panel`。`study_room_panel` 仅作为 fault 过滤器（SUB_TYPE_ROOM_FILTER）中的 sub_type 使用，代表的是按 ori_room_name='书房' 过滤的逻辑分组，不需要 DeviceConfig 条目（DeviceConfig 只用于 UI 卡片参数分组展示）。

**--reset 后总记录数**：12 + 22 + 11 + 11 + 17 + 4 + 8 + 3 = **88 条**

（与 --reset 前相同总数：原来 4 个 panel_* 各 11 条 = 44 条，新方案 secondary_bedroom_panel=22 + master_bedroom_panel=11 + children_room_panel=11 = 44 条，总数不变。）

---

### 4.6 验证 SQL

```sql
-- 验证温控面板类 sub_type 记录（期望返回 4 行）
SELECT sub_type, sub_type_display, COUNT(*) AS param_count
FROM device_config
WHERE sub_type IN (
    'secondary_bedroom_panel',
    'master_bedroom_panel',
    'children_room_panel',
    'main_thermostat'
)
GROUP BY sub_type, sub_type_display
ORDER BY sub_type;

-- 期望输出：
-- children_room_panel   | 儿童房-温控面板 | 11
-- master_bedroom_panel  | 主卧-温控面板   | 11
-- secondary_bedroom_panel | 次卧-温控面板 | 22
-- main_thermostat       | 主温控         | 12

-- 任务要求的验证 SQL（含 living_room_main 若存在）：
SELECT sub_type, sub_type_display
FROM device_config
WHERE sub_type LIKE '%_panel' OR sub_type LIKE '%_main'
ORDER BY sub_type;

-- 期望返回 3 行（living_room_main 不在 DeviceConfig 中，仅在 constants.py）：
-- children_room_panel   | 儿童房-温控面板
-- master_bedroom_panel  | 主卧-温控面板
-- secondary_bedroom_panel | 次卧-温控面板

-- 完整 sub_type 分布验证（--reset 后）：
SELECT sub_type, sub_type_display, COUNT(*) AS param_count,
       SUM(CASE WHEN is_active=0 THEN 1 ELSE 0 END) AS inactive_count
FROM device_config
GROUP BY sub_type, sub_type_display
ORDER BY sub_type;
```

> **说明**：`living_room_main` 作为新 sub_type 仅存在于 constants.py 的 `SUB_TYPE_ROOM_FILTER`，不在 DeviceConfig 中（客厅相关参数在 DeviceConfig 中的 sub_type 仍为 `main_thermostat`）。因此验证 SQL `WHERE sub_type LIKE '%_main'` 返回 0 行。这不是 bug，是设计决策：DeviceConfig 供 UI 卡片展示，fault 过滤器供故障管理视图，两个系统的 sub_type 命名空间独立。如需要 living_room_main 也出现在 DeviceConfig，需额外在 seed 中为 `living_room_*` 参数添加 sub_type='living_room_main' 的条目（增加 12 条），但这超出 v0.6.4 范围，不建议此时引入。

---

### 4.7 执行步骤（DBA 操作）

```bash
# 部署 v0.6.4 后，在生产服务器执行：
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py seed_device_config --reset
```

--reset 标志清空 DeviceConfig 表后重建，不影响 fault_event/device_node 等其他表。预期输出：`Done: created 88, skipped 0`（含 1 条 deactivated 的 system_switch）。

---

## 5. fault_event 表 Migration DDL + 回填（附录 D）

### 5.1 migration 0027（DDL）

```python
# api/migrations/0027_fault_event_room_columns.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0026_add_fault_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='faultevent',
            name='room_name',
            field=models.CharField(
                max_length=50, null=True, blank=True,
                verbose_name='房间名称',
                help_text='冗余字段，存储 device_room.ori_room_name，fault_consumer T1 写入时填充'
            ),
        ),
        migrations.AddField(
            model_name='faultevent',
            name='room_id',
            field=models.ForeignKey(
                to='api.DeviceRoom',
                on_delete=models.SET_NULL,
                null=True, blank=True,
                related_name='fault_events',
                verbose_name='所属房间',
                db_column='room_id',
            ),
        ),
        # 可选：复合索引（按需添加，取决于 room_name 过滤频率）
        # migrations.AddIndex(
        #     model_name='faultevent',
        #     index=models.Index(fields=['room_name', 'is_active'], name='idx_fault_room_active'),
        # ),
    ]
```

### 5.2 migration 0028（数据回填）

```python
# api/migrations/0028_fault_event_backfill_room.py
from django.db import migrations

def backfill_room(apps, schema_editor):
    """回填 fault_event.room_name + room_id，通过 device_sn → device_node → device_room 关联。"""
    FaultEvent = apps.get_model('api', 'FaultEvent')
    DeviceNode = apps.get_model('api', 'DeviceNode')

    # 构建 device_sn → (room_name, room_id) 字典
    sn_to_room = {}
    for dn in DeviceNode.objects.select_related('room').all():
        sn_key = str(dn.device_sn)
        if sn_key not in sn_to_room:
            sn_to_room[sn_key] = (dn.room.ori_room_name, dn.room.id)

    # 批量更新 fault_event（分批，避免大事务）
    total_updated = 0
    batch_size = 500
    qs = FaultEvent.objects.filter(room_name__isnull=True)
    batch = []
    for fe in qs.iterator(chunk_size=batch_size):
        room_info = sn_to_room.get(fe.device_sn)
        if room_info:
            fe.room_name = room_info[0]
            fe.room_id_id = room_info[1]   # Django FK 字段的实际列名
            batch.append(fe)
        if len(batch) >= batch_size:
            FaultEvent.objects.bulk_update(batch, ['room_name', 'room_id_id'])
            total_updated += len(batch)
            batch = []
    if batch:
        FaultEvent.objects.bulk_update(batch, ['room_name', 'room_id_id'])
        total_updated += len(batch)

    print(f'[migration 0028] 回填完成，共更新 {total_updated} 行')


def reverse_backfill_room(apps, schema_editor):
    """回滚：重置所有 fault_event 的 room_name 和 room_id 为 NULL。"""
    FaultEvent = apps.get_model('api', 'FaultEvent')
    FaultEvent.objects.all().update(room_name=None, room_id_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0027_fault_event_room_columns'),
    ]

    operations = [
        migrations.RunPython(backfill_room, reverse_code=reverse_backfill_room),
    ]
```

**注意事项**：
- `room_id_id` 是 Django ForeignKey 在 bulk_update 中操作的实际列名（Django 自动在 FK 字段名后加 `_id`）。
- migration 0028 在 fault_consumer 停止期间执行，避免并发写入干扰。
- `iterator(chunk_size=500)` 避免全量加载到内存。
- 回填期间执行时间预估：3094 行 / 500 批次 = 7 批，≤10 秒。
- **类型对齐约束（重要）**：`fault_event.device_sn` 在 DB 层是 `CHAR/VARCHAR`，而 `device_node.device_sn` 是 `INT`。原生 SQL 回填需显式 CAST：
  ```sql
  UPDATE fault_event fe
  LEFT JOIN device_node dn ON CAST(dn.device_sn AS CHAR) = fe.device_sn
  LEFT JOIN device_room dr ON dn.room_id = dr.id
  SET fe.room_name = dr.ori_room_name,
      fe.room_id   = dr.id
  WHERE fe.room_name IS NULL;
  ```
  Django ORM 回填代码（migration 0028）通过 `str(dn.device_sn)` 作为字典 key、以 `fe.device_sn`（已是字符串）查找，自动处理类型差异，无需额外 CAST。db_evidence.md 查询 3 反查已用 `CAST(dn.device_sn AS CHAR) = fe.device_sn` 验证此路径可行。

---

## 6. get_room_for_device 辅助函数（附录 E）

放置位置：`fault_consumer/state_machine.py` 或新建 `fault_consumer/room_lookup.py`（推荐后者，保持 state_machine.py 职责单一）。

```python
# fault_consumer/room_lookup.py — v0.6.4-FM-ROOM 新增
"""
room_lookup.py — device_sn → DeviceRoom 反查辅助（MOD-BE-FM-v0.6.4）

职责：为 T1 INSERT 提供 room_name + room_id 填充数据。
设计约束：
  - 无进程内缓存（DeviceRoom 同步频率低，但变更不可预测，简单直查 DB）
  - 查找失败时返回 (None, None)，不抛异常，不影响 T1 主路径
  - 只在 T1 路径调用（新故障首次出现），不在 T2/T3 调用（不写 room 字段）
"""

import logging

logger = logging.getLogger(__name__)


def get_room_for_device(device_sn: str) -> tuple[str | None, int | None]:
    """从 device_sn 反查 DeviceRoom，返回 (ori_room_name, room_id)。

    查找失败（DeviceNode 不存在 / room 未关联）时返回 (None, None)，不抛异常。

    Args:
        device_sn: FaultEvent.device_sn（字符串型，如 "22549"）

    Returns:
        (ori_room_name, room_id) 或 (None, None)
    """
    try:
        from api.models import DeviceNode
        sn_int = int(device_sn)
        dn = (
            DeviceNode.objects
            .select_related('room')
            .filter(device_sn=sn_int)
            .first()
        )
        if dn and dn.room:
            return dn.room.ori_room_name, dn.room_id
        return None, None
    except (ValueError, TypeError):
        # device_sn 不是有效整数（如脏数据 sn="abc"）
        logger.debug('get_room_for_device: device_sn 无法转为 int: %s', device_sn)
        return None, None
    except Exception as exc:
        logger.error('get_room_for_device 异常: %s device_sn=%s', exc, device_sn)
        return None, None
```

**state_machine._t1_insert() 调用方式**：

```python
# 在 FaultEvent.objects.create() 之前插入：
from .room_lookup import get_room_for_device

room_name, room_id = get_room_for_device(device_sn)

fe = FaultEvent.objects.create(
    specific_part=specific_part,
    device_sn=device_sn,
    product_code=product_code,
    fault_code=fault_code,
    fault_type=fault_type,
    fault_message=fault_message,
    severity=severity,
    first_seen_at=received_at,
    last_seen_at=received_at,
    recovered_at=None,
    is_active=True,
    room_name=room_name,    # 新增
    room_id=room_id,        # 新增（ForeignKey，传 id 值）
)
```

---

## 7. 回滚预案

### 7.1 migration 0027 回滚（DDL 回滚）

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
venv/bin/python manage.py migrate api 0026
```

Django 的 AlterField/AddField 支持 migrate --back，会执行 `ALTER TABLE fault_event DROP COLUMN room_name, DROP COLUMN room_id`。

**注意**：migration 0027 回滚前必须先回滚 migration 0028（如已执行），否则外键约束会导致 DROP COLUMN 报错。

### 7.2 migration 0028 回滚（数据回滚）

```bash
venv/bin/python manage.py migrate api 0027
```

执行 `reverse_backfill_room()`：`UPDATE fault_event SET room_name=NULL, room_id=NULL`（3094 行，<5s）。

### 7.3 sub_type 重组回滚（代码回滚）

git revert 对应 commit 后，重新部署：
```bash
git revert <v0.6.4-commit-hash>
git push origin main
# 生产：git pull → 重启 freeark-backend + freeark-fault-consumer
# 注意：seed_device_config 需重新运行旧版 --reset
```

旧 sub_type 回滚不需要 DB 操作（sub_type 白名单静默忽略未知值）。

### 7.4 旧 sub_type 灰度策略

**结论：不需要灰度双跑。**

理由：
- 旧 sub_type 在过滤路径上已通过白名单（`if st not in SUB_TYPE_LABELS`）静默忽略，旧参数不会崩溃，只会返回空结果。
- 生产无外部调用方（仅内部前端使用），前端升级后旧 sub_type 参数消失。
- 短暂双跑只增加维护复杂度，无实质收益。

---

## 8. 模块影响矩阵

| 模块 | 文件 | 变更类型 | 影响级别 |
|------|------|---------|---------|
| 故障消费常量 | `api/fault_consumer/constants.py` | 重写 SUB_TYPE_* 三个字典 + 新增 VALID_ROOM_NAMES | HIGH |
| 故障消费状态机 | `api/fault_consumer/state_machine.py` | _t1_insert 追加 room 查找 + create 参数 | MEDIUM |
| 房间查找辅助 | `api/fault_consumer/room_lookup.py` | 新增文件 | NEW |
| 故障 REST 视图 | `api/views_fault.py` | 新增 room_name 过滤参数 | LOW |
| 故障序列化器 | `api/serializers_fault.py` | 新增 room_name/room_id 字段输出 | LOW |
| 数据模型 | `api/models.py` | FaultEvent 新增 room_name CharField + room_id FK | MEDIUM |
| DB Migration | `api/migrations/0027_*.py` | DDL：ALTER TABLE + 外键 | HIGH（DB 操作） |
| DB Migration | `api/migrations/0028_*.py` | 数据回填：UPDATE | HIGH（DB 操作） |
| 前端故障管理 | `FaultManagementView.vue` | 新增房间列 + 房间过滤器 | MEDIUM |
| ~~配置初始化~~ | ~~`seed_device_config.py`~~ | ~~新 sub_type 条目~~ | **移出 v0.6.4 范围**（见附录 C 降级声明，v0.6.5 考虑） |

---

## 9. 部署顺序（概要）

1. git pull 落地新代码（backend/frontend）。
2. 停止 `freeark-fault-consumer`（避免新 T1 INSERT 与 migration 冲突）。
3. 执行 migration 0027（DDL ALTER TABLE）。
4. 执行 migration 0028（数据回填）。
5. 重启 `freeark-backend`（含新 constants.py、views_fault.py、serializers_fault.py）。
6. 重启 `freeark-mqtt-consumer`（constants.py 被引用，需重载）。
7. 重启 `freeark-fault-consumer`（新 state_machine.py + room_lookup.py）。
8. 前端 npm run build + 部署 dist/。
9. 验证：新故障写入 room_name 正确；过滤器 5 类房间标签正确；历史数据房间列显示正确。

> **v0.4.0 修正**：移除步骤 5（`seed_device_config --reset`）。DeviceConfig 表重建属设备设置页卡片重组，不在 v0.6.4 范围内，见附录 C 降级声明。
>
> 完整部署计划由 sub_agent_devops_engineer 在 GROUP_E 阶段产出。

---

## 10. 开放决策（已全部关闭，DB 实测完成 2026-05-29）

| 编号 | 内容 | 裁决结论 | 依据 |
|------|------|---------|------|
| OD-v0.6.4-A01 | 3-1-602 的 5 台设备 ori_room_name 分布是否与假设一致 | **已关闭 ✓**：完全一致。22158=客厅，22552=书房，22553=次卧，22554=主卧，22555=儿童房。SUB_TYPE_ROOM_FILTER 关键词已正确。 | db_evidence.md 查询 1 |
| OD-v0.6.4-A02 | `fourth_children_room_*` 故障在 fault_event 中是否存在？对应 ori_room_name 是否="儿童房"？ | **已关闭 ✓（修正后成立）**：字面 PLC 前缀 fault_code 不存在；但 device_sn=22555 主码 error_799 反查 ori_room_name="儿童房"，自然落入 children_room_panel room_keywords=['儿童房']，无需特殊处理。 | db_evidence.md 查询 3 反向验证 |
| OD-v0.6.4-A03 | fault_event 总行数确认 | **已关闭 ✓**：生产 fault_event ≈ 3094 行（top-20 fault_code 累计量推算），migration 0028 执行时间 ≤10 秒。 | db_evidence.md 查询 3 分布表 |

---

## 11. error_code 反推表 oracle（附录 F）

> 本附录作为 v0.6.4 集成测试和 E2E 测试的 oracle 参考。来源：db_evidence.md 查询 3 反向验证（2026-05-29 生产数据）。

### 3-1-6-602（4 房户型）device_sn ↔ ori_room_name ↔ 主 fault_code 对应关系

| fault_code 主码 | device_sn | ori_room_name | product_code | 推断 PLC 前缀（参考） | 新 sub_type |
|----------------|-----------|---------------|-------------|---------------------|------------|
| error_679 | 22158 | 客厅 | 260001（主温控） | `living_room_*` | `living_room_main` |
| error_709 | 22552 | 书房 | 120003（温控面板） | `study_room_*` | `study_room_panel` |
| error_739 | 22553 | 次卧 | 120003（温控面板） | `bedroom_*` | `secondary_bedroom_panel` |
| error_769 | 22554 | 主卧 | 120003（温控面板） | `children_room_*` | `master_bedroom_panel` |
| error_799 | 22555 | 儿童房 | 120003（温控面板） | `fourth_children_room_*` | `children_room_panel` |

**异常留档**：device_sn=22554（主卧）出现 1 条 error_709（书房 code），孤例（vs 主码 error_769 的 33 条）。分析为单次硬件交叉或日志误标。v0.6.4 方案完全走 device_sn → ori_room_name 路径，此异常不影响过滤结果（22554 的 ori_room_name="主卧"不变）。留档观察，无需修复。

### 测试用例 oracle（集成测试参照）

| 测试场景 | 输入 | 期望输出 |
|---------|------|---------|
| `specific_part=3-1-6-602` + `sub_type=master_bedroom_panel` | device_sn=22554，ori_room_name='主卧' | 返回含 error_769 的故障记录；22554 的 1 条 error_709 仍包含（因 device_sn=22554 ori_room_name='主卧'，符合条件） |
| `specific_part=3-1-6-602` + `sub_type=children_room_panel` | device_sn=22555，ori_room_name='儿童房' | 返回含 error_799 的故障记录 |
| `specific_part=3-1-6-602` + `sub_type=study_room_panel` | device_sn=22552，ori_room_name='书房' | 返回含 error_709 的故障记录 |
| `specific_part=1-1-16-1601`（3 房）+ `sub_type=study_room_panel` | 无书房设备 | 返回 0 条（ori_room_name='书房' 无设备） |
| `room_name=儿童房` 过滤 | fault_event.room_name='儿童房' | 仅返回 room_name='儿童房' 的行 |

---

## 12. GROUP_C 实现操作清单（附录 G）— v0.4.0 修正版（7 步）

> **v0.4.0 修正**：从 11 步缩减为 7 步。已移除原步骤 9（seed_device_config --reset），原步骤 10→前端、原步骤 11→单元测试分别改为步骤 7 和步骤附加（可选）。移除依据见 ADR-v0.6.4-02 v0.6.4 范围边界说明和附录 C 降级声明。
>
> 本清单供开发者照抄执行，每一步含 commit message 模板和验证命令。
> 前提：开发分支从 main 切出，本地 SQLite 测试 DB 已准备好。

---

### 步骤 1：修改 `fault_consumer/constants.py`（SUB_TYPE_ROOM_FILTER + SUB_TYPE_LABELS + SUB_TYPE_TO_FAULT_CODES + VALID_ROOM_NAMES）

**文件**：`FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py`

**操作**：将文件中 SUB_TYPE_ROOM_FILTER、SUB_TYPE_LABELS、SUB_TYPE_TO_FAULT_CODES 三个字典以及新增 VALID_ROOM_NAMES 常量，完整替换为附录 B（§3）的代码内容。

**验证命令**：
```bash
cd FreeArkWeb/backend/freearkweb
python -c "
from api.fault_consumer.constants import SUB_TYPE_ROOM_FILTER, SUB_TYPE_LABELS, VALID_ROOM_NAMES
assert set(SUB_TYPE_ROOM_FILTER.keys()) >= {'living_room_main','master_bedroom_panel','secondary_bedroom_panel','children_room_panel','study_room_panel'}
assert set(SUB_TYPE_LABELS.keys()) == set(SUB_TYPE_ROOM_FILTER.keys())
assert VALID_ROOM_NAMES == frozenset(['客厅','主卧','次卧','儿童房','书房'])
print('constants.py OK')
"
```

**Commit message**：
```
refactor(fault-mgmt): v0.6.4 重组 SUB_TYPE_ROOM_FILTER 为 5 房间类 + 新增 VALID_ROOM_NAMES

- living_room_main / master_bedroom_panel / secondary_bedroom_panel
  / children_room_panel / study_room_panel 替换旧 bedroom_thermostat 等
- 过滤路径改为 ori_room_name 关键词，不依赖 fault_code 文本匹配
- 新增 VALID_ROOM_NAMES 白名单供 views_fault.py 使用
- SUB_TYPE_TO_FAULT_CODES 保留为向后兼容 OR 路径（生产无命名型 fault_code）

Refs: ADR-v0.6.4-02, BUG-FM-005, db_evidence.md A-03
```

---

### 步骤 2：新增 `fault_consumer/room_lookup.py`

**文件**：`FreeArkWeb/backend/freearkweb/api/fault_consumer/room_lookup.py`（新建）

**操作**：照抄附录 E（§6）的完整代码创建文件。

**验证命令**：
```bash
python -c "
from api.fault_consumer.room_lookup import get_room_for_device
# 测试不存在的 sn，期望返回 (None, None) 不抛异常
result = get_room_for_device('999999999')
assert result == (None, None), f'期望 (None, None)，实际 {result}'
# 测试非法 sn，期望返回 (None, None) 不抛异常
result = get_room_for_device('abc')
assert result == (None, None), f'期望 (None, None)，实际 {result}'
print('room_lookup.py OK')
"
```

**Commit message**：
```
feat(fault-consumer): 新增 room_lookup.py — device_sn 反查 DeviceRoom 辅助函数

- get_room_for_device(device_sn) -> (ori_room_name, room_id) | (None, None)
- 查找失败不抛异常，不影响 T1 主路径
- 单独文件保持 state_machine.py 职责单一

Refs: ADR-v0.6.4-03
```

---

### 步骤 3：修改 `api/models.py`（FaultEvent 新增 room_name + room_id）

**文件**：`FreeArkWeb/backend/freearkweb/api/models.py`

**操作**：在 `FaultEvent` 模型类中追加两个字段（附录 D §5.1 中的字段定义）。

**验证命令**：
```bash
python manage.py check api
# 期望：System check identified no issues (0 silenced).
```

**Commit message**：
```
feat(models): FaultEvent 新增 room_name CharField + room_id FK

- room_name: VARCHAR(50) null=True，冗余存储 device_room.ori_room_name
- room_id: FK to DeviceRoom ON DELETE SET NULL
- fault_consumer T1 写入时填充，历史数据由 migration 0028 回填

Refs: ADR-v0.6.4-01
```

---

### 步骤 4：生成并编写 migration 0027（DDL）

**操作**：
```bash
python manage.py makemigrations api --name fault_event_room_columns
# 检查生成的 migration 文件是否与附录 D §5.1 一致（AddField × 2）
```

若 makemigrations 生成结果与附录 D 不完全一致，手动对齐（主要注意 ON DELETE 语义是 SET_NULL）。

**验证命令**：
```bash
# 在 SQLite 测试 DB 上执行：
python manage.py migrate api --run-syncdb 2>&1 | head -20
python -c "
import django; django.setup()
from api.models import FaultEvent
fe = FaultEvent()
assert hasattr(fe, 'room_name'), 'room_name 字段缺失'
assert hasattr(fe, 'room_id'), 'room_id 字段缺失'
print('migration 0027 字段 OK')
"
```

**Commit message**：
```
feat(migration): 0027 fault_event 新增 room_name / room_id 列 (DDL)

- ALTER TABLE fault_event ADD COLUMN room_name VARCHAR(50) NULL
- ALTER TABLE fault_event ADD COLUMN room_id INT NULL FK device_room(id)
- ON DELETE SET NULL，历史事件保留

Refs: ADR-v0.6.4-01, ADR-v0.6.4-05
```

---

### 步骤 5：编写 migration 0028（数据回填）

**操作**：手动创建 `api/migrations/0028_fault_event_backfill_room.py`，内容照抄附录 D §5.2。

**验证命令**（SQLite 测试 DB）：
```bash
python manage.py migrate api 0028
python -c "
import django; django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute('SELECT COUNT(*) FROM fault_event WHERE room_name IS NOT NULL')
    cnt = c.fetchone()[0]
    print(f'回填后 room_name 非空行数: {cnt}')
    # SQLite 测试 DB 可能无历史数据，cnt=0 也可接受
"
# 测试回滚：
python manage.py migrate api 0027
python -c "
import django; django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute('SELECT COUNT(*) FROM fault_event WHERE room_name IS NOT NULL')
    cnt = c.fetchone()[0]
    assert cnt == 0, f'回滚后 room_name 应为全 NULL，实际 {cnt} 行非空'
    print('migration 0028 回滚 OK')
"
python manage.py migrate api 0028  # 恢复
```

**Commit message**：
```
feat(migration): 0028 fault_event 历史数据回填 room_name / room_id

- RunPython backfill_room: device_sn → DeviceNode → DeviceRoom → room_name/room_id
- 批量 bulk_update chunk_size=500，预计 3094 行 ≤10s
- reverse_backfill_room: UPDATE SET room_name=NULL, room_id=NULL
- 注意：device_sn 类型差异由 str(dn.device_sn) 处理（无需 CAST）

Refs: ADR-v0.6.4-05
```

---

### 步骤 6：修改 `fault_consumer/state_machine.py`（_t1_insert 追加 room 查找）

**文件**：`FreeArkWeb/backend/freearkweb/api/fault_consumer/state_machine.py`

**操作**：在 `_t1_insert` 方法中，在 `FaultEvent.objects.create()` 调用前插入附录 E（§6）给出的 room_lookup 调用代码，并在 create() 参数列表中增加 `room_name=room_name, room_id=room_id`。

**验证命令**：
```bash
python -c "
import inspect
from api.fault_consumer.state_machine import FaultStateMachine
src = inspect.getsource(FaultStateMachine._t1_insert)
assert 'get_room_for_device' in src, '_t1_insert 未调用 get_room_for_device'
assert 'room_name=room_name' in src, '_t1_insert FaultEvent.create 缺 room_name 参数'
print('state_machine._t1_insert OK')
"
```

**Commit message**：
```
feat(fault-consumer): _t1_insert 写入 room_name + room_id

- 调用 room_lookup.get_room_for_device(device_sn) 获取房间信息
- 查找失败时 (None, None) 不影响主路径（FaultEvent 仍正常写入）
- 新故障自此起写入 room_name/room_id，无需手动回填

Refs: ADR-v0.6.4-03
```

---

### 步骤 7：修改 `api/serializers_fault.py`（新增 room_name/room_id 字段输出）

**文件**：`FreeArkWeb/backend/freearkweb/api/serializers_fault.py`

**操作**：在 FaultEvent 序列化器的 `fields` 列表（或 Meta.fields）中追加 `'room_name'` 和 `'room_id'`。

**验证命令**：
```bash
python -c "
from api.serializers_fault import FaultEventSerializer
fields = FaultEventSerializer().fields.keys()
assert 'room_name' in fields, 'serializer 缺 room_name'
assert 'room_id' in fields, 'serializer 缺 room_id'
print('serializers_fault.py OK')
"
```

**Commit message**：
```
feat(serializer): FaultEventSerializer 暴露 room_name / room_id 字段

Refs: ADR-v0.6.4-01
```

---

### 步骤 8：修改 `api/views_fault.py`（新增 room_name 过滤参数）

**文件**：`FreeArkWeb/backend/freearkweb/api/views_fault.py`

**操作**：按 ADR-v0.6.4-04（§1.4）给出的代码片段，在 fault_event 列表视图的过滤逻辑中追加 `room_name` 参数处理（`request.query_params.getlist('room_name')` + VALID_ROOM_NAMES 白名单 + `qs.filter(room_name__in=...)`）。

**验证命令**：
```bash
# 启动 runserver，curl 测试（或用 Django test client）：
python manage.py test api.tests.test_views_fault -v 2
# 如无现成测试，至少验证 import 正常：
python -c "
from api.views_fault import FaultEventListView
import inspect
src = inspect.getsource(FaultEventListView.get)
assert 'room_name' in src or 'VALID_ROOM_NAMES' in src, 'views_fault 缺 room_name 过滤'
print('views_fault.py OK')
"
```

**Commit message**：
```
feat(views): fault_event 列表新增 room_name 过滤参数

- GET /api/fault-events/?room_name=主卧 支持多值（getlist）
- VALID_ROOM_NAMES 白名单防注入：{'客厅','主卧','次卧','儿童房','书房'}
- 直接过滤 fault_event.room_name 列，无 JOIN

Refs: ADR-v0.6.4-04
```

---

### ~~步骤 9：seed_device_config.py 修改~~ — 已移出 v0.6.4 范围

> **v0.4.0 删除**：seed_device_config 改动属设备设置页卡片重组，与故障管理页过滤器无关。DeviceConfig 表不参与 fault_event_categories 接口（该接口直接 dump constants.py 字典），故此步骤从 GROUP_C 清单中移除。若需重组，见附录 C 未来工作备忘，届时单独立项 v0.6.5。

---

### 步骤 7（原步骤 10）：前端修改（FaultManagementView.vue）

**文件**：`FreeArkWeb/frontend/src/views/FaultManagementView.vue`（或实际路径）

**操作**（需前端开发确认实际组件结构）：
1. 在故障列表表格中追加"房间"列，绑定 `row.room_name`（后端序列化器已输出）。
2. 更新设备类型下拉选项：将旧的 `panel_study_room` 等替换为 `sub_type_display`（来自 `SUB_TYPE_LABELS`）。后端 `/api/fault-event-categories/` 接口已返回新标签，前端直接使用接口返回值，无需硬编码。
3. 若有房间过滤器，新增或更新 `room_name` 多选控件，选项为 `['客厅','主卧','次卧','儿童房','书房']`。

**验证命令**：
```bash
npm run build 2>&1 | tail -10
# 期望：无编译错误，dist/ 生成成功
```

**Commit message**：
```
feat(frontend): 故障管理 - 新增房间列 + 更新设备类型标签（v0.6.4）

- 表格新增 room_name 列
- 设备类型选项从接口 /api/fault-event-categories/ 动态获取（已含新标签）
- 房间过滤器支持 5 类：客厅/主卧/次卧/儿童房/书房

Refs: ADR-v0.6.4-04
```

---

### 可选步骤（原步骤 11）：单元测试

**新增/更新测试文件**：

```bash
# 1. room_lookup 单元测试（无 DB 依赖，mock DeviceNode）
python -m pytest FreeArkWeb/backend/freearkweb/api/tests/test_room_lookup.py -v

# 2. constants 结构验证测试
python -m pytest FreeArkWeb/backend/freearkweb/api/tests/test_constants.py -v

# 3. views_fault room_name 过滤测试
python manage.py test api.tests.test_views_fault.FaultEventRoomFilterTest -v 2
```

**Commit message**：
```
test(fault-mgmt): v0.6.4 room_lookup / constants / views_fault 单元测试

- get_room_for_device: 正常路径 + DeviceNode 不存在 + 非法 sn
- SUB_TYPE_ROOM_FILTER 结构断言
- room_name 过滤：主卧/次卧/儿童房/书房/客厅 各 1 个 fixture

Refs: GROUP_D 测试计划
```

---

### GROUP_C 完成后的交付物清单（v0.4.0 修正版，7 步）

| 步骤 | 文件 | 变更类型 | 描述 |
|------|------|---------|------|
| 步骤 1 | `api/fault_consumer/constants.py` | 修改 | SUB_TYPE_* 三字典 + VALID_ROOM_NAMES |
| 步骤 2 | `api/fault_consumer/room_lookup.py` | 新增 | device_sn 反查辅助函数 |
| 步骤 3 | `api/models.py` | 修改 | FaultEvent room_name + room_id 字段 |
| 步骤 4 | `api/migrations/0027_fault_event_room_columns.py` | 新增 | DDL migration |
| 步骤 5 | `api/migrations/0028_fault_event_backfill_room.py` | 新增 | 数据回填 migration |
| 步骤 6 | `api/fault_consumer/state_machine.py` | 修改 | _t1_insert room_lookup 调用 |
| 步骤 6 | `api/serializers_fault.py` | 修改 | room_name/room_id 字段输出 |
| 步骤 6 | `api/views_fault.py` | 修改 | room_name 过滤参数 |
| 步骤 7 | `FaultManagementView.vue` | 修改 | 房间列 + 设备类型标签更新 |
| ~~步骤 9（已移除）~~ | ~~`api/management/commands/seed_device_config.py`~~ | ~~修改~~ | **不在 v0.6.4 范围**，见附录 C |

GROUP_C 代码完成后，提交 GROUP_D 评审（测试计划）前需在本地 SQLite 跑通步骤 1-7 的所有验证命令。
