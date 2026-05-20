# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.5.3
  title: 系统看板「系统开机状况」卡片 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3
  created_at: 2026-05-20
  status: DRAFT
  references:
    - FreeArkWeb/frontend/src/views/HomeView.vue
    - FreeArkWeb/backend/freearkweb/api/views.py
    - FreeArkWeb/backend/freearkweb/api/models.py
    - plc_config.json
    - docs/requirements/v0.5.1_mode_alignment_and_energy_supply/requirements_spec.md (REQ-FUNC-001 — mode 枚举权威来源)
    - sdlc/perf_analysis_report.md
```

---

## 1. 背景与动因

### 1.1 项目背景

FreeArk 能耗采集平台系统看板（`HomeView.vue`）当前包含「总电量查询」卡片及若干统计卡片（今日用电量、本月用电量、PLC 在线、大屏在线、总设备数）。

在 v0.5.2 完成看板 API 性能调优（参考 `sdlc/perf_analysis_report.md`）后，用户提出新增一个运营视角的状态卡片，以便实时掌握全楼设备的**当前开机状况**和**运行模式分布**。

### 1.2 需求来源

用户原始需求（2026-05-20）：

> 在系统看板页面新增一个卡片，位置在「总电量查询」卡片的右边，卡片名称「系统开机状况」，显示：（1）开机率：开机台数 + 开机比率；（2）运行模式分布：制冷/制热/通风/除湿各多少台。

### 1.3 版本定位

| 版本 | 主要变更 |
|------|---------|
| v0.5.0 | 设备设置面板 |
| v0.5.1 | mode 枚举对齐（operation_mode: 1=制冷,2=制热,3=通风,4=除湿） |
| v0.5.2 | 看板 API 性能调优（waitress 线程数、CONN_MAX_AGE） |
| **v0.5.3** | **系统看板新增「系统开机状况」卡片（本版本）** |

---

## 2. 需求范围

### 2.1 版本内容

| 包含 | 不包含 |
|------|--------|
| 新增后端 API `dashboard_power_status`（`/api/dashboard/power-status/`） | 修改现有任何 API |
| 前端 `HomeView.vue` 新增「系统开机状况」卡片 | 新增独立页面或路由 |
| 卡片在「总电量查询」右侧的布局 | 历史趋势图、时间段筛选 |
| 开机台数、总台数、开机率统计 | 单设备下钻详情 |
| 四种运行模式（制冷/制热/通风/除湿）台数统计 | mode 枚举的修改（v0.5.1 已定） |

### 2.2 不变更项

- 现有任何看板 API 的接口签名与响应结构。
- 认证、权限、MQTT 通信架构。
- `PLCConnectionStatus`、`PLCLatestData` 数据模型结构（只读查询，不写入）。
- v0.5.1 确立的 mode 枚举（1=制冷,2=制热,3=通风,4=除湿），本版本直接引用，不再重定义。

---

## 3. 数据来源分析（关键上下文核实结论）

> 本节是需求分析阶段对代码库的查明结论，设计阶段应以此为准。若有与代码不符之处，以开放问题（第 6 节）为准。

### 3.1 PLC 连接状态（"开机"条件 A）

- **数据源**：`PLCConnectionStatus` 表（Django model）
- **判定字段**：`connection_status`，枚举值 `'online'` = 在线，`'offline'` = 离线
- **记录口径**：每台设备一条记录（`specific_part` 唯一约束），即此表总行数 = 系统管理的设备总台数
- **已有复用点**：`dashboard_plc_online_rate` API（`views.py` 约 L883）已用 `PLCConnectionStatus` 的单次聚合查询（`Count` + `Case/When`）完成统计，新 API 可复用同一查询模式
- **已有索引**：`connection_status`、`(connection_status, building, unit)` 组合索引

### 3.2 系统开关状态（"开机"条件 B）

- **数据源**：`PLCLatestData` 表（Django model，`db_table='plc_latest_data'`）
- **判定参数**：`param_name='system_switch'`，对应 `plc_config.json` 中 `system_switch`（DB14, offset=91, data_type=byte，描述"系统开关"）
- **值语义**（来自 `views.py` 已有逻辑，约 L1864-1867）：
  - `value == 0` 或 `value IS NULL` = 关
  - `value != 0`（通常为 1） = 开
- **已有索引**：`(specific_part, param_name)` 唯一约束（可作为过滤索引）

> **[CONFIRMED]** 用户需求中的 `system_mode`（"开"的判定条件）在代码库实际对应 `PLCLatestData.param_name='system_switch'`，非独立模型字段。本文档后续统一称 `system_switch`。

### 3.3 运行模式（mode 字段）

- **数据源**：`PLCLatestData` 表
- **判定参数**：`param_name='operation_mode'`，对应 `plc_config.json` 中 `operation_mode`（DB14, offset=89, data_type=byte，描述"运行模式"）
- **值枚举**（来源：v0.5.1 REQ-FUNC-001，commit 72363d6，已在 `plc_config.json` 和 `views.py` 同步生效）：

| 值 | 含义 |
|----|------|
| 1  | 制冷 |
| 2  | 制热 |
| 3  | 通风 |
| 4  | 除湿 |

- **`_OPERATION_MODE_MAP`**：`{1: '制冷', 2: '制热', 3: '通风', 4: '除湿'}`（定义于 `views.py` L1901，已在设备列表 API 中使用）

### 3.4 "总台数"口径

**确认口径**：以 `PLCConnectionStatus` 表总行数为准（`PLCConnectionStatus.objects.count()`），与 `dashboard_plc_online_rate` 的 `total_count` 口径一致，避免口径分歧。

> **[OPEN QUESTION OQ-001]** 见第 6.1 节——若 `PLCConnectionStatus` 与 `PLCLatestData` 中的 `specific_part` 集合存在差异（即某些设备有连接状态记录但无最新参数记录，或反之），总台数口径和运行模式统计的分母可能与用户预期不符。需用户确认。

---

## 4. 功能需求

### REQ-FUNC-001：新增看板 API — 系统开机状况统计

**来源**：用户原始需求 §「开机情况」
**优先级**：P0

**接口规格**：

```
GET /api/dashboard/power-status/
认证：IsAuthenticated（与现有看板 API 保持一致）
无需查询参数（统计当前实时状态快照）
```

**响应结构**：

```json
{
  "success": true,
  "data": {
    "powered_on_count": <int>,
    "total_count": <int>,
    "power_on_rate": <float>,
    "mode_distribution": {
      "cooling": <int>,
      "heating": <int>,
      "ventilation": <int>,
      "dehumidification": <int>
    }
  }
}
```

**字段定义**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `powered_on_count` | int | 当前开机台数（同时满足：PLC online + system_switch != 0） |
| `total_count` | int | 系统管理的设备总台数（`PLCConnectionStatus` 表总行数） |
| `power_on_rate` | float | 开机比率，`round(powered_on_count / total_count * 100, 2)`，total_count=0 时返回 0.0 |
| `mode_distribution.cooling` | int | `operation_mode=1` 且满足开机条件的设备台数 |
| `mode_distribution.heating` | int | `operation_mode=2` 且满足开机条件的设备台数 |
| `mode_distribution.ventilation` | int | `operation_mode=3` 且满足开机条件的设备台数 |
| `mode_distribution.dehumidification` | int | `operation_mode=4` 且满足开机条件的设备台数 |

**"开机"判定规则（两个条件必须同时满足）**：

- 条件 A：`PLCConnectionStatus.connection_status = 'online'`（PLC 处于连接状态）
- 条件 B：`PLCLatestData.param_name = 'system_switch'` 且 `value IS NOT NULL` 且 `value != 0`（系统开关为开）

两个条件通过 `specific_part` 字段关联（均以四段格式，如 `"3-1-7-702"`）。

**运行模式统计约束**：

- 只统计满足"开机"两个条件的设备的 `operation_mode`。
- 即：`mode_distribution` 四个值之和 `<= powered_on_count`（若某台开机设备无 `operation_mode` 记录，则不计入任何分类）。
- `mode_distribution` 各项只包含 mode=1/2/3/4 的设备，mode 为其他值（0、null 或超范围）的设备不计入任何分类（参见 OQ-002）。

**验收标准（Given/When/Then）**：

- AC-101：Given 某设备 `PLCConnectionStatus.connection_status='offline'` When 调用 API Then 该设备不计入 `powered_on_count`
- AC-102：Given 某设备 `PLCConnectionStatus.connection_status='online'` 且 `system_switch.value=0` When 调用 API Then 该设备不计入 `powered_on_count`
- AC-103：Given 某设备 PLC online 且 `system_switch.value=1`（非零） When 调用 API Then 该设备计入 `powered_on_count`
- AC-104：Given `total_count=0`（无设备记录） When 调用 API Then `power_on_rate=0.0`（不触发除零错误）
- AC-105：Given 某设备开机（满足两个条件）且 `operation_mode.value=1` When 调用 API Then 该设备计入 `mode_distribution.cooling`
- AC-106：Given 某设备开机且 `operation_mode.value=2` When 调用 API Then 计入 `mode_distribution.heating`
- AC-107：Given 某设备开机且 `operation_mode.value=3` When 调用 API Then 计入 `mode_distribution.ventilation`
- AC-108：Given 某设备开机且 `operation_mode.value=4` When 调用 API Then 计入 `mode_distribution.dehumidification`
- AC-109：Given 某设备 PLC offline（不满足条件 A）When 调用 API Then 该设备的 `operation_mode` 不计入任何 `mode_distribution` 分类
- AC-110：Given 某设备满足开机条件但无 `operation_mode` 记录（`PLCLatestData` 中无对应行） When 调用 API Then `powered_on_count` 包含该设备，但 `mode_distribution` 四个分类均不计入该设备

---

### REQ-FUNC-002：前端「系统开机状况」卡片

**来源**：用户原始需求 §「卡片位置与内容」
**优先级**：P0

**卡片位置**：在「总电量查询」卡片的**右侧**。当前「总电量查询」在 `HomeView.vue` 的 `.total-energy-section` 区域；新卡片应与其并排展示，布局方式参考同页面「PLC 在线」「大屏在线」等现有卡片的 flex/grid 风格（见 `.stats-cards` 区域）。

**卡片标题**：系统开机状况

**卡片内容展示**：

1. **开机情况区域**：
   - 开机台数（大字体数值，参考 `.stat-value` 样式）
   - 开机比率（百分比，格式：`XX.XX%`，参考 `.stat-sub` 样式）
   - 总台数（辅助信息，格式：`共 N 台`）

2. **运行模式分布区域**：
   - 四行展示：制冷 N 台 / 制热 N 台 / 通风 N 台 / 除湿 N 台
   - 样式须与同页面其他卡片内容统一（Element Plus 组件、字体大小、颜色方案）

**加载状态**：卡片在 API 请求期间显示 `v-loading` 加载遮罩（与现有卡片一致）。

**错误处理**：API 请求失败时，所有数值保持初始值 0，不抛出未处理异常（与现有卡片 catch 处理一致）。

**刷新策略**：页面首次加载时调用（`onMounted`），无需自动轮询（与现有卡片一致）。

**验收标准**：

- AC-201：Given 页面加载 When HomeView 渲染完成 Then 「系统开机状况」卡片出现在「总电量查询」右侧
- AC-202：Given API 返回 `powered_on_count=5, total_count=10, power_on_rate=50.0` When 卡片渲染 Then 显示「5 台开机」「50.00%」「共 10 台」
- AC-203：Given API 返回 mode_distribution When 卡片渲染 Then 分别显示「制冷 N 台」「制热 N 台」「通风 N 台」「除湿 N 台」
- AC-204：Given API 请求中 When v-loading 生效 Then 卡片显示加载动画，与同页面其他卡片行为一致
- AC-205：Given 卡片风格 Then 使用 Element Plus `el-card` 组件，字体/颜色与现有 `.stat-card` 风格一致

---

## 5. 非功能需求

### REQ-PERF-001：API 查询性能

**来源**：用户非功能性要求 + 项目已知性能关注点（`sdlc/perf_analysis_report.md`）
**优先级**：P0

**约束**：

1. **不引入慢查询/全表扫描**：新 API 的所有查询必须走索引，不允许 `COUNT(*)` 配合多次子查询形式的 N+1 问题。
2. **单次聚合原则**：参考 `dashboard_plc_online_rate` 的实现模式（单次 `aggregate` + `Count/Case/When`），新 API 应尽量在数据库层完成聚合，减少 Python 层的遍历。
3. **JOIN 替代 N+1**：`PLCConnectionStatus` 与 `PLCLatestData` 的关联查询应使用 SQL-level JOIN（ORM `annotate(Subquery)` 或 `filter(Q)` + `aggregate`），而非对每条记录逐行查询 `PLCLatestData`。
4. **已有索引覆盖**：
   - `PLCConnectionStatus.connection_status` 有单列索引 — 可直接过滤
   - `PLCLatestData.(specific_part, param_name)` 有唯一约束（等效索引）— JOIN 条件可走索引
   - `PLCLatestData.param_name` 有单列索引

> [OPEN QUESTION OQ-003] 设计阶段需评估：当设备数量增长到数百台时，`PLCLatestData` 的 Subquery JOIN 是否仍在可接受的响应时间内（推测 <200ms），或是否需要 `prefetch_related` / 专用聚合视图。此问题留给架构师在 GROUP_B 阶段决策。

**目标响应时间**：新 API 在当前生产规模下（推测 <200 台设备）响应时间应与 `dashboard_plc_online_rate` 同量级（预计 <100ms 数据库查询时间）。

### REQ-PERF-002：无新数据库表或迁移

**约束**：本版本只读查询现有 `PLCConnectionStatus` 和 `PLCLatestData` 表，不新增表、不修改 Schema，不产生数据库迁移文件。

### REQ-UI-001：界面风格一致性

**来源**：用户非功能性要求 §「前端卡片界面风格须与其他 tab/卡片统一」

**约束**：

- 使用 Element Plus `el-card` 组件
- 数值展示使用与 `.stat-value`、`.stat-sub`、`.stat-label` 相同的 CSS 类或样式规范
- 图标使用 Element Plus Icons（与页面现有图标库一致）
- 卡片尺寸和间距遵循页面现有的 `.stats-cards` flex/grid 布局约束

---

## 6. 开放问题（Open Questions）

> 以下问题在需求分析阶段已尽量查明，但仍存在需要用户确认的歧义点。**在用户答复之前，设计与开发阶段应以最保守的假设推进，并在开放问题处添加 TODO 标注。**

### OQ-001：总台数口径 — PLCConnectionStatus 是否涵盖所有预期设备？

**问题描述**：本文档以 `PLCConnectionStatus` 表总行数（N）作为「总台数」，与 `dashboard_plc_online_rate` 口径一致。但若存在以下情况，用户可能对「总台数」的预期与该口径不一致：

- 某些设备已在业务层管理（如 `OwnerInfo`），但尚未产生 `PLCConnectionStatus` 记录（从未上线过的新设备）
- `PLCConnectionStatus` 中存在已废弃设备的记录（不应再参与统计）

**需要用户确认**：

1. 「总台数」是否以 `PLCConnectionStatus` 表实际行数为准（等同于「曾经联网过的设备数」）？
2. 还是应以 `OwnerInfo` 中已绑定设备数（`bind_status='已绑定'`）为准？
3. 还是以其他口径？

**默认假设（用户未答复时）**：采用 `PLCConnectionStatus` 总行数，与 `dashboard_plc_online_rate` 保持一致。

---

### OQ-002：mode 为 0、null 或超范围值的设备如何处理？

**问题描述**：从 `PLCLatestData` 查询 `operation_mode` 时，可能出现以下边界情况：

| 情况 | 描述 |
|------|------|
| `operation_mode` 记录不存在 | `PLCLatestData` 中无该设备的 `param_name='operation_mode'` 行 |
| `value IS NULL` | 记录存在但 value 为空 |
| `value = 0` | v0.5.1 修复前的历史数据（旧枚举 0=制冷） |
| `value` 不在 {1,2,3,4} | 其他异常值 |

**需要用户确认**：

1. 开机设备中，`operation_mode` 记录不存在 / value 为 null / value=0 的设备，是否需要在卡片上以「未知模式 N 台」形式单独显示？
2. 还是直接忽略（不显示），只展示 1/2/3/4 四类？

**默认假设（用户未答复时）**：忽略边界值，只展示 1/2/3/4 四类，不显示「未知模式」。

---

### OQ-003：开机状况卡片是否需要手动刷新按钮？

**问题描述**：当前看板「PLC 在线率」等卡片无刷新按钮，页面加载一次后不自动更新。「系统运行状态」卡片有「刷新」按钮。

**需要用户确认**：「系统开机状况」卡片是否需要提供手动刷新按钮？

**默认假设（用户未答复时）**：不提供刷新按钮，与「PLC 在线率」卡片保持一致（仅页面加载时请求一次）。

---

### OQ-004：「总电量查询」与「系统开机状况」并排的布局方式

**问题描述**：当前 `HomeView.vue` 中「总电量查询」在 `.total-energy-section`（独占一行），下方才是 `.stats-cards`（多卡片横排）。若新卡片需要与「总电量查询」**严格并排同一行**，需要调整布局结构（将两个卡片放入 flex 容器）。若允许「系统开机状况」卡片紧邻「总电量查询」下方或在统计卡片区域第一位，布局改动最小。

**需要用户确认**：「总电量查询」右边，是指：
1. 在同一行水平并排（需要调整现有布局结构，使两个卡片在同一 flex 行）？
2. 还是在统计卡片区域（`.stats-cards`）的最左侧（即排在「今日用电量」卡片前面）？

**默认假设（用户未答复时）**：严格按照「同一行水平并排」，将「总电量查询」区域改为 flex 行，「系统开机状况」卡片并排在其右侧。

---

## 7. 需求追踪矩阵

| 需求 ID | 名称 | 优先级 | 数据来源 | 前端卡片 | 后端 API |
|---------|------|--------|---------|---------|---------|
| REQ-FUNC-001 | 新增 power-status API | P0 | PLCConnectionStatus + PLCLatestData | - | dashboard_power_status |
| REQ-FUNC-002 | 前端「系统开机状况」卡片 | P0 | REQ-FUNC-001 响应 | HomeView.vue | - |
| REQ-PERF-001 | API 查询性能（无慢查询） | P0 | 代码库性能历史 | - | dashboard_power_status |
| REQ-PERF-002 | 无新 DB 迁移 | P0 | 开发约束 | - | - |
| REQ-UI-001 | UI 风格一致性 | P1 | 用户需求 | HomeView.vue | - |

---

## 8. 术语表

| 术语 | 定义 |
|------|------|
| 开机 | PLC 连接状态 = 'online' 且 system_switch.value != 0（两个条件同时满足） |
| system_switch | PLCLatestData 中 param_name='system_switch' 的记录，value=0 表示关，非零表示开 |
| operation_mode | PLCLatestData 中 param_name='operation_mode' 的记录，1=制冷,2=制热,3=通风,4=除湿 |
| 总台数 | PLCConnectionStatus 表总行数（默认口径，待 OQ-001 确认） |
| 开机率/开机比率 | powered_on_count / total_count × 100%，保留两位小数 |
| specific_part | 四段设备标识，格式如 "3-1-7-702"，跨表关联的主键字段 |
