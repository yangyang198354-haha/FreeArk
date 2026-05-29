# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: APPROVED
  references:
    - docs/requirements/v0.6.4_fault_mgmt_room_column/db_evidence.md
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py (v0.6.3-FM)
    - FreeArkWeb/backend/freearkweb/api/views_fault.py (v0.6.3-FM)
    - FreeArkWeb/backend/freearkweb/api/models.py (DeviceNode, DeviceRoom, FaultEvent)
    - datacollection/resource/plc_config.json
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-29 | 初始草稿，基于 plc_config.json + constants.py + v0.6.1 调研，含 DB 实测待确认项 |
| 0.2.0-APPROVED | 2026-05-29 | 吸收 DB 实测结论（db_evidence.md status=COMPLETED）：关闭全部 OQ、更新假设验证状态、新增 AC-FM-011-05（fault_code 文本匹配非主路径）；status 升为 APPROVED |
| 0.3.0-APPROVED | 2026-05-29 | **范围修正（主线门控指令）**：明确 v0.6.4 范围不含 DeviceConfig / seed_device_config 改动。§1.3 移除 seed_device_config 硬约束条目，FR-FM-010 移除 seed_device_config 重建要求，§5.2 移除 seed_device_config 运维操作条目，兼容性矩阵移除 DeviceConfig 表重建条目。相关内容降级为未来工作（v0.6.5 考虑）。理由：fault_event_categories 接口直接 dump constants.py 字典（无 DB 查询），DeviceConfig 仅供设备设置页使用，与故障管理过滤器完全解耦。 |

---

## 1. 背景与动因

### 1.1 版本定位

| 版本 | 主要变更 |
|------|---------|
| v0.6.3-FM | 故障描述中文化 + 房号段数匹配修复（BUG-FM-004/005/006/007/008，已生产上线） |
| **v0.6.4-FM-ROOM** | **故障列表增加"房间"列 + 设备类型过滤器按实际房间语义重组 + fault_event 表增加 room_name/room_id 列（本版本）** |

### 1.2 需求来源

用户在 v0.6.3 上线后提出三个方向的改进（2026-05-29 决策汇总）：

1. 故障列表新增"房间"列，直接显示 `ori_room_name`（兜底策略：空时用 device_floor + sn 或 "-"）。
2. 设备类型过滤器从 PLC 寄存器前缀语义（`bedroom_thermostat`="三房主卧四房次卧"）重组为用户可理解的"实际房间"语义（`master_bedroom_panel`="主卧"），每个选项同时覆盖 3 房和 4 房对应的 PLC 寄存器组。
3. `fault_event` 表新增 `room_name`（冗余列）和 `room_id`（外键），在 fault_consumer 写入时同步填充，并对已有约 3094 行历史数据执行一次性回填 migration。

### 1.3 核心约束（本版本硬约束）

- schema 变更（fault_event 增列）需通过 Django migration，部署时严格遵守服务启停顺序。
- **v0.6.4 不执行 `seed_device_config --reset`**：DeviceConfig 表与故障管理过滤器完全解耦，该操作降级为 v0.6.5 考虑。
- 不修改 `fault_utils.py`（v0.5.3-FCC 只读模块）。
- 部署一律 plink + git pull，禁止 pscp。
- 部署期服务启停顺序：先停 `freeark-fault-consumer` → 跑 migration → 重启 `freeark-backend` + `freeark-mqtt-consumer` + `freeark-fault-consumer`。

---

## 2. 代码与 DB 调研摘要

### 2.1 PLC 寄存器 ↔ 实际房间映射（来自 plc_config.json description 字段）

> 权威来源：`datacollection/resource/plc_config.json`，所有 description 字段逐一核对。

| PLC 参数前缀 | description 原文 | 3 房语义 | 4 房语义 |
|------------|-----------------|---------|---------|
| `living_room_*` | "客厅" | 客厅 | 客厅 |
| `bedroom_*` | "三房主卧四房次卧" | 主卧 | 次卧 |
| `children_room_*` | "三房儿童房四房主卧" | 儿童房 | 主卧 |
| `study_room_*` | "三房次卧四房书房" | 次卧 | 书房 |
| `fourth_children_room_*` | "四房儿童房" | 不适用（无此寄存器） | 儿童房 |

**关键推论（来自此映射）**：

新 sub_type `master_bedroom_panel`（主卧）需覆盖两组 PLC 寄存器：
- 3 房：`children_room_*`（三房儿童房四房主卧 → 3 房为主卧）
- 4 房：`bedroom_*`（三房主卧四房次卧 → 4 房为次卧；此处矛盾，见 §3.2 AC 详细说明）

实际上 ori_room_name 字段才是"真值"，device_room.ori_room_name 直接存储屏侧同步的中文房间名（"主卧"、"次卧"等）。方案 Y 的过滤器逻辑应基于 ori_room_name 关键词，而不是 PLC 寄存器前缀。

### 2.2 device_node 已知分布（v0.6.1 OQ-01 实测，2026-05-28）

| product_code | ori_room_name | 行数 | 推断户型 |
|-------------|--------------|------|---------|
| 260001（主温控）| 客厅 | 634 | 全部户型 |
| 120003（温控面板）| 次卧 | 634 | 全部户型 |
| 120003（温控面板）| 主卧 | 634 | 全部户型 |
| 120003（温控面板）| 儿童房 | 634 | 全部户型 |
| 120003（温控面板）| 书房 | 418 | 仅 4 房 |

推断：634 - 418 = 216 户为 3 房（无书房面板），418 户为 4 房（含书房面板）。
注：查询 4 结果填入后需确认以上数据仍准确。

### 2.3 现有 FaultEvent model（migration 0026）

当前 `fault_event` 表字段：`specific_part`, `device_sn`, `product_code`, `fault_code`, `fault_type`, `fault_message`, `severity`, `first_seen_at`, `last_seen_at`, `recovered_at`, `is_active`, `created_at`, `updated_at`。

不含房间字段，故障管理页只能通过 specific_part（如"3-1-6-602"）来隐式关联楼层/户型，无法直接展示"主卧"、"客厅"等语义化房间名。

### 2.4 state_machine.py 写入入口（T1 INSERT）

`_t1_insert()` 调用 `FaultEvent.objects.create(...)` 写入新故障。当前参数列表不含房间字段。新增 `room_name` + `room_id` 后，需在此处追加填充逻辑（device_sn → DeviceNode → DeviceRoom）。

---

## 3. 功能需求

### FR-FM-009：故障列表新增"房间"列（US-FM-009）

**描述**：故障管理表格新增"房间"列，展示该故障所属设备的房间名称。

**展示优先级（三级降级）**：

| 优先级 | 条件 | 展示内容 |
|--------|------|---------|
| 主路径 | `fault_event.room_name` 非空 | `room_name` 值（来自 `device_room.ori_room_name`，如"主卧"） |
| 兜底一 | `room_name` 为空，但 `specific_part` 和 `device_sn` 已知 | 后端通过运行时 JOIN 计算 `ori_room_name`，前端展示 |
| 兜底二 | 以上均无效 | 展示 "-" |

**数据来源**：`fault_event.room_name` 由 fault_consumer 写入时同步填充（US-FM-011）；历史数据通过 migration 回填（US-FM-011）。

**前端变更**：
- `FaultManagementView.vue` 表格新增 `room_name` 列，位置在设备名称列之后。
- 列宽建议 100px，与"故障码"列风格一致（居中对齐）。
- 支持按 `room_name` 过滤（见 FR-FM-009-filter）。

**FR-FM-009-filter：房间列过滤器**：
- 故障管理页过滤器区域新增"房间"下拉（`<el-select>` 单选或多选）。
- 候选项来源：当前筛选结果集中出现过的 `room_name` 值（动态），或全字典（"客厅", "主卧", "次卧", "儿童房", "书房"）。
- 后端接口 `/api/devices/fault-events/` 新增查询参数 `room_name`（string 或多值），在 `fault_event.room_name` 列上做精确匹配或 `__in` 过滤。
- 不传 `room_name` 参数则不过滤（与现有参数行为一致）。

**约束**：
- 列宽/表头/排序风格与现有 `fault_type`、`fault_message` 等列一致。
- 历史记录中 `room_name` 为空的行，前端显示 "-"，不崩溃。

---

### FR-FM-010：设备类型过滤器按"实际房间"5 类重组（US-FM-010）

**描述**：将设备类型过滤器（`sub_type`）从 PLC 寄存器语义（`bedroom_thermostat`="三房主卧四房次卧"）重组为用户可理解的"实际房间"5 类语义。

**新 sub_type 定义**：

| 新 sub_type | 中文标签 | 实际房间语义 | 对应 ori_room_name 关键词 | 对应 PLC 前缀（参考） |
|------------|---------|------------|------------------------|-------------------|
| `living_room_main` | 客厅主温控 | 客厅（3 房/4 房均有） | `客厅` | `living_room_*` |
| `master_bedroom_panel` | 主卧温控面板 | 主卧（3 房/4 房均有） | `主卧` | 3 房:`children_room_*`；4 房:`bedroom_*` 的部分（但以 ori_room_name 为准） |
| `secondary_bedroom_panel` | 次卧温控面板 | 次卧（3 房/4 房均有） | `次卧` | 3 房:`bedroom_*`；4 房:`study_room_*` 的部分（但以 ori_room_name 为准） |
| `children_room_panel` | 儿童房温控面板 | 儿童房（3 房/4 房均有） | `儿童房` | 3 房:`children_room_*` 部分；4 房:`fourth_children_room_*` |
| `study_room_panel` | 书房温控面板 | 书房（仅 4 房，3 房返回 0 条） | `书房` | 4 房:`study_room_*` 部分 |

> 注意：以 `device_room.ori_room_name` 关键词匹配为权威过滤路径，不依赖 PLC 寄存器前缀。PLC 寄存器前缀仅用于工程参考。

**产品编码约束（product_code）**：
- 所有温控面板新 sub_type 的 product_code 为 `120003`（主卧/次卧/儿童房/书房）或 `260001`（客厅）。
- `living_room_main`：product_code = `260001`，不做 ori_room_name 过滤（260001 天然只有客厅）。
- 其余 4 类：product_code = `120003`，通过 ori_room_name 关键词区分。

**验收标准（参见 user_stories.md US-FM-010）**：
- 3 房户型点击"书房温控面板"，该户故障记录返回 0 条（无书房设备）。
- 3-1-602（4 房），点击"儿童房温控面板"，返回 1 条（fault_code 含 `fourth_children_room_*`）。
- 3-1-602（4 房），点击"次卧温控面板"，返回 1 条（fault_code 含 `bedroom_*`，ori_room_name='次卧'）。
- 3-1-602（4 房），点击"主卧温控面板"，返回 1 条（fault_code 含 `children_room_*`，ori_room_name='主卧'）。
- 旧 sub_type 值（`bedroom_thermostat`、`children_room_thermostat`、`study_room_thermostat`、`fourth_children_room_thermostat`）从 API `fault-event-categories` 响应中移除，前端过滤器不再展示。
- 前端兼容处理：旧版 URL 中携带旧 sub_type 参数时，后端忽略（白名单校验已有，返回空集）。

**旧 sub_type 处置（constants.py 修改范围）**：
- `bedroom_thermostat`、`children_room_thermostat`、`study_room_thermostat`、`fourth_children_room_thermostat` 四个 sub_type 从 `SUB_TYPE_LABELS`、`SUB_TYPE_ROOM_FILTER`、`SUB_TYPE_TO_FAULT_CODES` 中移除。
- `living_room_thermostat` 更名为 `living_room_main`。
- `fresh_air_unit`、`hydraulic_module`、`energy_meter`、`air_quality_sensor` 四个非温控类 sub_type 保持不变。
- 过滤器分类源是 `constants.py` 中的 `SUB_TYPE_LABELS`，`fault_event_categories` 接口直接 dump 此字典，**无 DB 查询，无需 migration**。

**DeviceConfig / seed_device_config（非本版本范围）**：
- `seed_device_config.py` 改动的是设备设置页 UI 卡片分组展示（DeviceConfig 表），与故障管理过滤器完全解耦，**v0.6.4 不执行此改动**，降级为 v0.6.5 考虑。

---

### FR-FM-011：fault_event 表新增 room_name + room_id 列（US-FM-011，方案 B+）

**描述**：在 `fault_event` 表新增两个列，提升查询效率和语义清晰度。

**新列定义**：

| 列名 | 类型 | 允许 NULL | 默认值 | 说明 |
|-----|-----|---------|--------|------|
| `room_name` | VARCHAR(50) | 是 | NULL | 冗余字段，存储 `device_room.ori_room_name`（如"主卧"）；fault_consumer T1 INSERT 时同步填充 |
| `room_id` | INT | 是 | NULL | 外键 → `device_room.id`，ON DELETE SET NULL；fault_consumer T1 INSERT 时同步填充 |

**写入侧逻辑（fault_consumer）**：

在 `state_machine._t1_insert()` 中，`FaultEvent.objects.create()` 调用前，执行设备到房间的反向查找：

```
device_sn（str）→ int(device_sn) → DeviceNode.device_sn（int）
→ DeviceNode.room（ForeignKey → DeviceRoom）
→ DeviceRoom.ori_room_name → fault_event.room_name
→ DeviceRoom.id → fault_event.room_id
```

异常处理：查找失败时（`DeviceNode` 不存在或 JOIN 失败），`room_name` 和 `room_id` 均保持 `NULL`，不影响正常故障写入。

**历史数据回填 migration**：
- 一次性 migration（独立 migration 文件，非 DDL migration）。
- 回填对象：`fault_event` 表中 `room_name IS NULL` 且 `device_sn` 可在 `device_node` 中找到对应记录的行（估计约 3094 行，量小）。
- 回填 SQL 核心逻辑：通过 device_sn → device_node → device_room 关联，UPDATE fault_event SET room_name, room_id。
- 回填需在 fault_consumer 停止期间执行（避免并发写入冲突）。

**DB Migration 规划**：
- migration 0027（DDL）：在 `fault_event` 表 ALTER TABLE 新增 `room_name` 和 `room_id` 列（允许 NULL）。
- migration 0028（数据）：执行历史数据回填，UPDATE `fault_event` 关联 `device_node`/`device_room`。
- 两个 migration 独立，允许 DDL 先上线，数据 migration 在维护窗口执行。

**外键约束**：
- `room_id` → `device_room.id` ON DELETE SET NULL（device_room 被清理不阻塞 fault_event，不引发 IntegrityError）。

**索引**：
- 新增复合索引 `(room_name, is_active)`（可选，取决于架构师评估过滤性能）。

**追加验收标准（AC-FM-011-05，来自 DB 实测 A-v0.6.4-03 修正）**：

> 重构后 `fault_code` 文本匹配不作为主过滤路径。主过滤路径为：`device_sn → device_node → device_room.ori_room_name`（复合键 `product_code + ori_room_name`）。`SUB_TYPE_TO_FAULT_CODES` 中的命名型 fault_code 保留为可选 OR 联合字段，仅用于兼容未来可能出现的命名型故障码，不对当前生产数据产生任何过滤效果。
>
> **依据**：生产数据库 fault_event 表中不存在任何字面 PLC 前缀格式的 fault_code（如 `bedroom_temp_sensor_error`、`fourth_children_room_*` 等）；实际 fault_code 全部为 `error_NNN`（数字码）与 `comm_fault_timeout`（通信超时统一码）。此事实由 constants.py L125-126 注释（"生产数据库中命名型 fault_code 实际上不存在"）及 db_evidence.md 查询 3 实测结果双重确认。
>
> **测试 oracle**：`fault_code REGEXP '(children_room|fourth_children_room|study_room|bedroom)'` 返回零行（db_evidence.md 查询 3 实测验证）。

---

## 4. 非功能需求

### 4.1 性能

| 指标 | 目标值 | 说明 |
|------|--------|------|
| fault_event_list 接口 P95 响应时间（含 room_name 列） | ≤ 800ms | 新增 room_name 列为冗余字段，无额外 JOIN |
| T1 INSERT 延迟增加（room 查找） | ≤ 5ms | DeviceNode 表小（~6000 行），device_sn 有索引 |
| 历史数据回填（约 3094 行） | ≤ 60s | 小量更新，不影响在线查询 |

### 4.2 兼容性

| 要求 | 说明 |
|------|------|
| 旧版前端 URL 参数兼容 | 旧 sub_type 值被白名单拒绝，返回空结果集（不报错） |
| fault_event 历史数据 | 回填前 room_name=NULL，前端显示 "-"，不崩溃 |
| ~~DeviceConfig 表重建~~ | 不在 v0.6.4 范围（已降级为 v0.6.5），故障管理过滤器不依赖 DeviceConfig 表 |

### 4.3 安全

| 要求 | 说明 |
|------|------|
| 权限 | 所有接口沿用 `IsAuthenticated`，不引入新权限 |
| ORM 安全 | room_name 过滤通过 ORM 参数化，不拼接原生 SQL |
| 外键 ON DELETE SET NULL | device_room 被清理时不阻塞 fault_event 写入 |

---

## 5. 依赖与假设

### 5.1 依赖

| 依赖项 | 类型 | 说明 |
|--------|------|------|
| `device_node` 表（migration 0022） | DB 依赖 | 含 `device_sn`（int）、`room`（FK → DeviceRoom）字段 |
| `device_room` 表（migration 0022） | DB 依赖 | 含 `ori_room_name`（str）、`id` 字段 |
| `fault_consumer/state_machine.py` | 代码依赖 | T1 INSERT 入口，需追加 room 查找逻辑 |
| `fault_consumer/constants.py` | 代码依赖 | SUB_TYPE_LABELS/ROOM_FILTER/TO_FAULT_CODES 需同步重写 |
| `views_fault.py` | 代码依赖 | 新增 room_name 过滤参数 |
| `serializers_fault.py` | 代码依赖 | 新增 room_name/room_id 字段输出 |
| `FaultManagementView.vue` | 前端依赖 | 新增房间列和过滤器 |
| Django migration 0027/0028 | DB 变更 | DDL + 数据回填 |

### 5.2 运维操作依赖（需 DBA/运维执行）

| 操作 | 时机 | 说明 |
|------|------|------|
| migration 0027（DDL） | fault-consumer 停止后 | ALTER TABLE fault_event ADD COLUMN room_name / room_id |
| migration 0028（数据回填）| 维护窗口（fault-consumer 停止期间）| 约 3094 行 UPDATE |
| ~~`seed_device_config --reset`~~ | ~~不在 v0.6.4 范围~~ | DeviceConfig 表重建属设备设置页改动，降级为 v0.6.5 |

### 5.3 假设

| 编号 | 假设内容 | 来源 | DB 验证状态 |
|------|---------|------|------------|
| A-v0.6.4-01 | 3-1-6-602（4 房）有 1 台 260001(客厅) + 4 台 120003(主卧/次卧/儿童房/书房) | 推断 | ✓ 成立 — db_evidence.md 查询 1 |
| A-v0.6.4-02 | 3 房户型只有 3 台 120003（主卧/次卧/儿童房），无书房面板 | 推断（634-418=216 户） | ✓ 成立 — db_evidence.md 查询 2（1-1-16-1601：4 台设备，无书房） |
| A-v0.6.4-03 | fault_event 中存在字面 PLC 前缀格式的 fault_code | 推断 | **✗ 不成立（已修正）** — db_evidence.md 查询 3：生产 fault_event 全部为 error_NNN + comm_fault_timeout，constants.py L125-126 注释已说明 |
| A-v0.6.4-04 | fourth_children_room 系故障对应设备 ori_room_name="儿童房" | 反推 | ✓ 成立（反向验证）— device_sn=22555 主码 error_799，反查 ori_room_name="儿童房" |
| A-v0.6.4-05 | ori_room_name 取值为标准中文房间名（"主卧"、"次卧"等），与新 sub_type 关键词匹配 | v0.6.1 OQ-01 实测 | ✓ 成立 — db_evidence.md 查询 4，取值集合 = {客厅,主卧,次卧,儿童房,书房} |
| A-v0.6.4-06 | DeviceNode.device_sn 转 int 后可唯一定位 DeviceRoom（无跨户重复导致歧义） | v0.6.1 OQ-03 裁决 | ✓ 已知（19 distinct sn；db_evidence 查询 1 闭环验证） |

---

## 6. 开放问题清单（已全部关闭，DB 实测完成 2026-05-29）

| 编号 | 问题描述 | 裁决结论 | 依据 |
|------|---------|---------|------|
| **OQ-v0.6.4-01** | `living_room_thermostat` 旧名称是否更名为 `living_room_main`？ | **已关闭**：更名 `living_room_main`，旧名白名单静默忽略（不报错）。ADR-v0.6.4-02 采纳方案 B 一次到位。 | 架构师裁决 + ADR-v0.6.4-02 |
| **OQ-v0.6.4-02** | migration 0028 是否需维护窗口执行？生产 fault_event 行数？ | **已关闭**：维护窗口执行（fault-consumer 停止期间）；生产 fault_event ≈ 3094 行，停机时间 <2 分钟。 | db_evidence.md 查询 3（top-20 分布，总量推算） |
| **OQ-v0.6.4-03** | 房间过滤器候选项：动态 vs 静态？ | **已关闭**：静态全字典（{客厅,主卧,次卧,儿童房,书房}），无需额外接口。 | db_evidence.md 查询 4：ori_room_name 取值集合恰好 5 类，完全固定 |
| **OQ-v0.6.4-04** | `children_room_panel` 的 ori_room_name 关键词是否已自然覆盖 `fourth_children_room_*` 故障记录？ | **已关闭**：是。生产 fault_event 中不存在字面 PLC 前缀 fault_code（A-v0.6.4-03 修正），所有"儿童房"相关记录通过 device_sn=22555 → ori_room_name='儿童房' 自然落入 `children_room_panel` 的 room_keywords=['儿童房'] 路径。 | db_evidence.md 查询 3 反向验证 |

---

## 7. 风险

| 风险编号 | 描述 | 概率 | 影响 | 缓解措施 |
|----------|------|------|------|---------|
| R-v0.6.4-01 | migration 0027 DDL（ALTER TABLE fault_event）在生产 MySQL 执行时触发表锁，影响在线查询（fault_event 当前约 3094 行，预计 <1s） | 低 | 低 | 确认生产行数后评估；行数小，快速 ALTER 不需要 pt-online-schema-change |
| R-v0.6.4-02 | sub_type 重命名期间旧 sub_type 仍在前端 localStorage 或缓存中，导致过滤器显示旧标签 | 低中 | 低 | 部署后刷新 `fault-event-categories` 接口即可，前端有动态加载 categories |
| R-v0.6.4-03 | DeviceNode 中部分 device_sn 无 room 关联（如早期脏数据 sn 1-6），T1 INSERT 的 room 查找失败，room_name=NULL | 低（已知 10 条脏数据，覆盖率 98.6%） | 低 | room_name=NULL 兜底显示 "-"，不影响故障写入 |
| R-v0.6.4-04 | DB 查询结果动摇假设（如 3-1-602 不是 4 房，或 ori_room_name 与预期不符） | 极低（基于 v0.6.1 已实测的分布数据） | 高（需重新设计 sub_type 映射） | 按用户守则：实测矛盾先停下来回主线，不私自调整假设 |
