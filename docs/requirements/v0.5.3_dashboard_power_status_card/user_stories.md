# 用户故事与验收标准

```
file_header:
  document_id: US-v0.5.3
  title: 系统看板「系统开机状况」卡片 — 用户故事
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3
  created_at: 2026-05-20
  status: DRAFT
  references:
    - docs/requirements/v0.5.3_dashboard_power_status_card/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/views.py
    - FreeArkWeb/backend/freearkweb/api/models.py
    - plc_config.json
```

---

## 用户故事索引

| US-ID | 简述 | 优先级 | 关联需求 |
|-------|------|--------|---------|
| US-001 | 运营人员查看全楼开机台数和开机比率 | P0 | REQ-FUNC-001, REQ-FUNC-002 |
| US-002 | 运营人员查看各运行模式的设备台数分布 | P0 | REQ-FUNC-001, REQ-FUNC-002 |
| US-003 | PLC 离线设备不计入开机统计 | P0 | REQ-FUNC-001 AC-101 |
| US-004 | 系统开关为"关"的设备不计入开机统计 | P0 | REQ-FUNC-001 AC-102 |
| US-005 | 仅开机设备的运行模式才纳入模式分布统计 | P0 | REQ-FUNC-001 AC-109 |
| US-006 | 卡片无设备数据时安全降级显示 | P0 | REQ-FUNC-001 AC-104 |
| US-007 | 新卡片与现有卡片风格一致 | P1 | REQ-UI-001 |
| US-008 | API 响应不引入慢查询 | P0 | REQ-PERF-001 |
| US-009 | 开机设备无运行模式记录时的边界处理 | P1 | REQ-FUNC-001 AC-110 + OQ-002 |

---

## US-001：运营人员查看全楼开机台数和开机比率

**角色**：运营人员（已登录系统的管理员/普通用户）

**用户故事**：

> 作为运营人员，
> 我希望在系统看板上一眼看到当前全楼有多少台设备处于开机状态以及开机比率，
> 以便快速了解整栋楼的系统运行规模。

**验收标准**：

**Scenario 1：正常多台设备混合开关机状态**
- Given 系统中共有 10 台设备在 PLCConnectionStatus 中有记录
- And 其中 6 台 `connection_status='online'` 且 `system_switch.value=1`（满足开机两个条件）
- And 其余 4 台或 PLC offline 或 system_switch=0
- When 运营人员访问系统看板 `HomeView` 页面
- Then API `GET /api/dashboard/power-status/` 返回 `powered_on_count=6`, `total_count=10`, `power_on_rate=60.0`
- And 前端「系统开机状况」卡片显示「开机 6 台」「60.00%」「共 10 台」

**Scenario 2：所有设备均开机**
- Given 系统中共有 5 台设备，均满足开机两个条件
- When API 被调用
- Then 返回 `powered_on_count=5`, `total_count=5`, `power_on_rate=100.0`

**Scenario 3：所有设备均关机**
- Given 系统中共有 5 台设备，均不满足开机条件（PLC offline 或 system_switch=0）
- When API 被调用
- Then 返回 `powered_on_count=0`, `total_count=5`, `power_on_rate=0.0`

---

## US-002：运营人员查看各运行模式的设备台数分布

**角色**：运营人员

**用户故事**：

> 作为运营人员，
> 我希望看到当前开机设备中分别有多少台处于制冷、制热、通风、除湿模式，
> 以便了解当前建筑的整体能源使用模式。

**验收标准**：

**Scenario 1：四种模式均有设备**
- Given 当前共 8 台开机设备（PLC online + system_switch 非零）
- And 其中 3 台 `operation_mode.value=1`，2 台 value=2，2 台 value=3，1 台 value=4
- When API 被调用
- Then 返回 `mode_distribution = { "cooling": 3, "heating": 2, "ventilation": 2, "dehumidification": 1 }`

**Scenario 2：仅有部分模式有设备**
- Given 当前共 4 台开机设备，全部 `operation_mode.value=1`（制冷）
- When API 被调用
- Then 返回 `mode_distribution = { "cooling": 4, "heating": 0, "ventilation": 0, "dehumidification": 0 }`

**Scenario 3：前端卡片正确渲染四行模式分布**
- Given API 返回 `mode_distribution = { "cooling": 3, "heating": 2, "ventilation": 2, "dehumidification": 1 }`
- When 前端渲染「系统开机状况」卡片
- Then 卡片中分别显示「制冷 3 台」「制热 2 台」「通风 2 台」「除湿 1 台」

---

## US-003：PLC 离线设备不计入开机统计

**角色**：系统（数据准确性规则）

**用户故事**：

> 作为系统，
> 我需要确保 PLC 连接状态为 offline 的设备不被计为「开机」，
> 以保证开机统计反映真实的在线设备状态。

**验收标准**：

**Scenario 1：PLC 离线设备被排除**
- Given 设备 A：`PLCConnectionStatus.connection_status='offline'`，`PLCLatestData.system_switch.value=1`
- When API `GET /api/dashboard/power-status/` 被调用
- Then 设备 A 不计入 `powered_on_count`

**Scenario 2：PLC 离线设备的模式不计入分布**
- Given 设备 B：`PLCConnectionStatus.connection_status='offline'`，`PLCLatestData.operation_mode.value=1`
- When API 被调用
- Then 设备 B 不计入 `mode_distribution.cooling`

**Scenario 3：PLCConnectionStatus 中无记录的设备不参与统计**
- Given 某设备在 `PLCLatestData` 中有 system_switch 和 operation_mode 记录
- And 但该设备在 `PLCConnectionStatus` 中无记录（specific_part 不存在）
- When API 被调用
- Then 该设备既不计入 `total_count`，也不计入 `powered_on_count`

---

## US-004：系统开关为"关"的设备不计入开机统计

**角色**：系统（数据准确性规则）

**用户故事**：

> 作为系统，
> 我需要确保 PLC 在线但 system_switch 为关（value=0）的设备不被计为「开机」，
> 因为 PLC 在线不等于空调主机正在运行。

**验收标准**：

**Scenario 1：PLC 在线但开关为关**
- Given 设备 C：`PLCConnectionStatus.connection_status='online'`
- And `PLCLatestData.param_name='system_switch', value=0`
- When API 被调用
- Then 设备 C 不计入 `powered_on_count`

**Scenario 2：PLC 在线且无 system_switch 记录（视为关）**
- Given 设备 D：`PLCConnectionStatus.connection_status='online'`
- And `PLCLatestData` 中无该设备的 `param_name='system_switch'` 记录（value 不可得）
- When API 被调用
- Then 设备 D 不计入 `powered_on_count`（无法确认开机，保守处理为未开机）
- [注意] 此场景属于 OQ-002 关联边界，实现时需与用户确认处理策略

**Scenario 3：PLC 在线且 system_switch.value=1（开）**
- Given 设备 E：`PLCConnectionStatus.connection_status='online'`，`system_switch.value=1`
- When API 被调用
- Then 设备 E 计入 `powered_on_count`

---

## US-005：仅开机设备的运行模式才纳入模式分布统计

**角色**：系统（数据准确性规则）

**用户故事**：

> 作为系统，
> 我需要确保运行模式分布只统计当前真正在运行的设备，
> 以避免「已关机设备的历史 mode 值」污染模式分布数据。

**验收标准**：

**Scenario 1：关机设备的 mode 不影响分布**
- Given 设备 F：PLC offline（不满足条件 A），`operation_mode.value=1`
- Given 设备 G：PLC online 但 `system_switch=0`（不满足条件 B），`operation_mode.value=2`
- Given 设备 H：PLC online 且 `system_switch=1`（满足开机），`operation_mode.value=3`
- When API 被调用
- Then `mode_distribution = { "cooling": 0, "heating": 0, "ventilation": 1, "dehumidification": 0 }`
- And 设备 F 的 mode=1 和设备 G 的 mode=2 均不被计入

**Scenario 2：mode_distribution 四项之和不超过 powered_on_count**
- Given `powered_on_count=5`
- And 其中 2 台有有效 operation_mode 记录（值在 1-4 范围内），3 台无有效记录
- When API 被调用
- Then `cooling + heating + ventilation + dehumidification = 2`（<= 5）

---

## US-006：卡片无设备数据时安全降级显示

**角色**：系统（健壮性）

**用户故事**：

> 作为系统，
> 我需要在没有任何设备记录时安全地返回零值，
> 以防止前端显示错误或后端发生除零异常。

**验收标准**：

**Scenario 1：PLCConnectionStatus 表为空（total_count=0）**
- Given `PLCConnectionStatus` 表中无任何记录（`total_count=0`）
- When API 被调用
- Then 返回 `{ "success": true, "data": { "powered_on_count": 0, "total_count": 0, "power_on_rate": 0.0, "mode_distribution": { "cooling": 0, "heating": 0, "ventilation": 0, "dehumidification": 0 } } }`
- And API 返回 HTTP 200（不触发 500 错误）

**Scenario 2：前端初始状态下数值为 0**
- Given API 尚未返回（请求中）
- When 前端卡片渲染
- Then 所有数值显示 0（不显示 undefined 或 NaN）

---

## US-007：新卡片与现有卡片风格一致

**角色**：运营人员（UI/UX）

**用户故事**：

> 作为运营人员，
> 我希望新增的「系统开机状况」卡片与看板其他卡片在视觉上保持一致，
> 以便提供统一的使用体验。

**验收标准**：

**Scenario 1：卡片组件一致**
- Given 「系统开机状况」卡片代码
- When 视觉审查
- Then 使用 Element Plus `el-card` 组件（与「PLC 在线」「今日用电量」卡片相同）

**Scenario 2：加载状态一致**
- Given 「系统开机状况」卡片
- When 前端发起 API 请求期间
- Then 卡片显示 `v-loading` 遮罩（与 `loading.plcRate` 等行为一致）

**Scenario 3：数值样式一致**
- Given 卡片中的开机台数数值
- When 与「PLC 在线」卡片的 `online_count` 显示对比
- Then 使用相同的 CSS 类或等价样式（`.stat-value` 或同等 class）

---

## US-008：API 响应不引入慢查询

**角色**：系统管理员（运维）

**用户故事**：

> 作为系统管理员，
> 我希望新增的「系统开机状况」API 不引入全表扫描或 N+1 查询，
> 以避免重现 v0.5.2 之前看板 API 的超时问题。

**验收标准**：

**Scenario 1：单次聚合查询**
- Given `dashboard_power_status` API 视图函数实现
- When 代码审查
- Then 对 `PLCConnectionStatus` 和 `PLCLatestData` 的联合统计在一次数据库查询（或不超过 2 次独立聚合查询）内完成
- And 不存在 Python 层 for 循环对每台设备逐行查询数据库的模式（无 N+1）

**Scenario 2：走索引**
- Given `PLCConnectionStatus` 的 `connection_status` 字段有索引
- And `PLCLatestData` 的 `(specific_part, param_name)` 有唯一约束（等效复合索引）
- When API 查询执行
- Then 过滤条件 `connection_status='online'` 和 `param_name='system_switch'` / `param_name='operation_mode'` 均走索引（无全表扫描）

---

## US-009：开机设备无运行模式记录时的边界处理

**角色**：系统（数据健壮性）

**用户故事**：

> 作为系统，
> 我需要处理某台开机设备在 PLCLatestData 中没有 operation_mode 记录的情况，
> 以确保 powered_on_count 不会因此被低估。

**验收标准**：

**Scenario 1：开机设备无 operation_mode 记录**
- Given 设备 I：PLC online + `system_switch.value=1`（满足开机）
- And `PLCLatestData` 中无该设备的 `param_name='operation_mode'` 记录
- When API 被调用
- Then `powered_on_count` 包含设备 I（开机台数计算不依赖 operation_mode 是否存在）
- And `mode_distribution` 四个字段均不计入设备 I

**Scenario 2：开机设备 operation_mode.value=0（历史边界数据）**
- Given 设备 J：PLC online + `system_switch=1`（满足开机）
- And `PLCLatestData.operation_mode.value=0`（v0.5.1 前的历史数据，按旧枚举含义为「制冷」，但按当前枚举无意义）
- When API 被调用
- Then `powered_on_count` 包含设备 J
- And `mode_distribution` 四个分类均不计入设备 J（0 不在 {1,2,3,4} 范围内）
- [注意] 此场景与 OQ-002 挂钩，实现前需用户确认是否需要显示「未知模式 N 台」

---

## 附录：验收标准汇总（按 REQ-ID 排列）

| AC-ID | 关联 REQ | 描述 | 关联 US |
|-------|---------|------|---------|
| AC-101 | REQ-FUNC-001 | PLC offline 设备不计入 powered_on_count | US-003 |
| AC-102 | REQ-FUNC-001 | system_switch=0 设备不计入 powered_on_count | US-004 |
| AC-103 | REQ-FUNC-001 | PLC online + system_switch 非零 = 开机，计入 powered_on_count | US-001 |
| AC-104 | REQ-FUNC-001 | total_count=0 时 power_on_rate=0.0，不触发除零 | US-006 |
| AC-105 | REQ-FUNC-001 | 开机 + operation_mode=1 → mode_distribution.cooling++ | US-002 |
| AC-106 | REQ-FUNC-001 | 开机 + operation_mode=2 → mode_distribution.heating++ | US-002 |
| AC-107 | REQ-FUNC-001 | 开机 + operation_mode=3 → mode_distribution.ventilation++ | US-002 |
| AC-108 | REQ-FUNC-001 | 开机 + operation_mode=4 → mode_distribution.dehumidification++ | US-002 |
| AC-109 | REQ-FUNC-001 | 非开机设备的 operation_mode 不计入任何 mode_distribution 分类 | US-005 |
| AC-110 | REQ-FUNC-001 | 开机设备无 operation_mode 记录时，powered_on_count 仍计入，mode_distribution 四项均不计入 | US-009 |
| AC-201 | REQ-FUNC-002 | 前端卡片出现在「总电量查询」右侧 | US-007 |
| AC-202 | REQ-FUNC-002 | 前端正确显示开机台数、开机率、总台数 | US-001 |
| AC-203 | REQ-FUNC-002 | 前端正确显示四种模式台数 | US-002 |
| AC-204 | REQ-FUNC-002 | API 请求中卡片显示 v-loading | US-007 |
| AC-205 | REQ-FUNC-002 | 使用 el-card + 与现有卡片一致的样式 | US-007 |
