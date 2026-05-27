# 实现计划

```
file_header:
  document_id: DEV-IMPL-v0.5.3-FCC
  title: 设备列表「故障数量」列 + OpenClaw 故障查询工具 — 实现计划
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3-fault-count-column
  created_at: 2026-05-27
  status: COMPLETED
  references:
    - docs/architecture/architecture_design_v0.5.3_fault_count_column.md
    - docs/architecture/module_design_v0.5.3_fault_count_column.md
```

---

## 1. 模块实现状态

| 模块 ID | 文件路径 | 操作 | 状态 |
|---------|---------|------|------|
| MOD-BE-FC-01 | `FreeArkWeb/backend/freearkweb/api/fault_utils.py` | 新增 | DONE |
| MOD-BE-FC-02 | `FreeArkWeb/backend/freearkweb/api/views.py` | 修改 | DONE |
| MOD-BE-FC-03 | `FreeArkWeb/backend/freearkweb/api/urls.py` | 修改 | DONE |
| MOD-BE-FC-04 | `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | **不修改**（OQ-01 裁决）| SKIPPED |
| MOD-FE-FC-01 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 修改 | DONE |
| MOD-SKILL-FC-01 | `agents/freeark-skill/SKILL.md` | 修改 | DONE |
| MOD-SKILL-FC-02 | `agents/freeark-skill/scripts/tier1_readonly.py` | 修改 | DONE |

---

## 2. 实现要点说明

### MOD-BE-FC-01 fault_utils.py（新增，约 210 行）

- `FAULT_PARAM_NAMES`: 26 个具名故障字段（25 FAULT_PARAMS + comm_fault_timeout）
- `is_fault_param()`: 覆盖 FAULT_PARAM_NAMES 和 `^error_\d+$` 正则
- `count_faults_for_row()`: fresh_air_fault_status 做 popcount，其他故障字段值非零计 1
- `compute_fault_count_v2()`: 批量包装
- `_compute_from_db_batch()`: 单条 SQL + Q 对象，Python 层 pivot；DB 层用 LIKE 'error_%'，Python 层精确正则过滤
- `get_fault_count_cached()` / `get_fault_count_batch_cached()`: LocMemCache TTL=60s
- `invalidate_fault_count_cache()`: 备用钩子，本期不调用（AB-002 占位）
- `get_fault_details()` / `get_fault_details_updated_at()`: 供独立 API 使用

### MOD-BE-FC-02 views.py（修改）

- 追加 `from django.utils.timezone import now as django_now` 导入
- `device_management_device_list()`: 在序列化前提取 page_specific_parts，调用 `get_fault_count_batch_cached()`，将 `fault_count` 写入每条 result
- 新增 `device_fault_count()`: GET /api/devices/fault-count/，支持逗号分隔多个 specific_part（≤50），返回 fault_count + fault_details + updated_at
- 新增 `device_fault_summary()`: GET /api/devices/fault-summary/，支持 building/unit/min_fault_count 过滤，按 fault_count 降序，最多 100 条

### MOD-BE-FC-03 urls.py（修改）

在 `devices/ondemand-refresh/` 之后追加：
- `path('devices/fault-count/', views.device_fault_count, name='device-fault-count')`
- `path('devices/fault-summary/', views.device_fault_summary, name='device-fault-summary')`

### MOD-FE-FC-01 DeviceManagementDeviceListView.vue（修改）

在「运行模式」列（line 138）与「操作」列（line 139）之间插入「故障数量」列：
- `v-if fault_count === null || undefined` → 显示 `—`（灰色 #909399）
- `v-else` → 颜色 `var(--color-success)`（0）或 `var(--color-danger)`（>0），fontWeight 600
- 宽度 100px，居中对齐
- script 无需修改（fault_count 直接来自 API 响应）

### MOD-SKILL-FC-01 SKILL.md（修改）

- frontmatter description 更新为「16 个 Tier-1」
- Tier-1 工具表格追加 `freeark_get_fault_count` 和 `freeark_get_fault_summary` 两行
- 追加工具详细说明（参数 schema、返回示例、CLI 调用示例）
- 版本号从 v2.1.0 升级至 v2.2.0

### MOD-SKILL-FC-02 tier1_readonly.py（修改）

- 新增 `freeark_get_fault_count()`: 调用 GET /api/devices/fault-count/，生成 summary 字段
- 新增 `freeark_get_fault_summary()`: 调用 GET /api/devices/fault-summary/，生成 summary 字段
- TIER1_HANDLERS 字典追加两个新工具的路由

---

## 3. 关键设计决策落地

| 决策 | 落地方式 |
|------|---------|
| ADR-FC-001 LocMemCache TTL=60s | fault_utils._FAULT_CACHE_TTL = 60 |
| ADR-FC-003 fresh_air_fault_status popcount | count_faults_for_row() bin(int(v)).count('1') |
| ADR-FC-006 count_faults_for_row | 新函数，compute_fault_count_v2 调用之 |
| 批量 SQL 避免 N+1 | _compute_from_db_batch() 单条 SQL + Q 对象 |
| LIKE 'error_%' + Python 精确正则 | DB 层用 param_name__startswith='error_'，Python 层 _ERROR_N_PATTERN.match |
| AB-002 占位钩子 | invalidate_fault_count_cache() 保留不调用 |

---

## 4. 文件变更汇总

### 新增文件

| 文件路径 | 行数（估算）|
|---------|-----------|
| `FreeArkWeb/backend/freearkweb/api/fault_utils.py` | ~215 行 |
| `FreeArkWeb/backend/freearkweb/api/tests_fault_count.py` | ~380 行 |
| `docs/development/v0.5.3_fault_count_column/implementation_plan.md` | 本文件 |
| `docs/development/v0.5.3_fault_count_column/code_review_report.md` | 见另文件 |

### 修改文件

| 文件路径 | 修改说明 |
|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/views.py` | +1 import；device_management_device_list 追加 fault_count 字段；新增 device_fault_count 和 device_fault_summary 两个视图函数（约 +160 行）|
| `FreeArkWeb/backend/freearkweb/api/urls.py` | 追加 2 条 path（+3 行）|
| `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 追加「故障数量」列（+17 行）|
| `agents/freeark-skill/SKILL.md` | 更新 frontmatter、Tier-1 工具表格、版本号，追加工具详细说明（约 +80 行）|
| `agents/freeark-skill/scripts/tier1_readonly.py` | 新增 2 个工具函数 + TIER1_HANDLERS 条目（约 +60 行）|
