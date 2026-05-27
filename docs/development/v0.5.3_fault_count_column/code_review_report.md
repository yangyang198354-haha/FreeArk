# 代码评审报告

```
file_header:
  document_id: DEV-CR-v0.5.3-FCC
  title: 设备列表「故障数量」列 + OpenClaw 故障查询工具 — 代码评审报告
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3-fault-count-column
  created_at: 2026-05-27
  status: APPROVED
  references:
    - docs/architecture/architecture_design_v0.5.3_fault_count_column.md
    - docs/architecture/module_design_v0.5.3_fault_count_column.md
    - FreeArkWeb/backend/freearkweb/api/fault_utils.py
    - FreeArkWeb/backend/freearkweb/api/views.py
    - FreeArkWeb/backend/freearkweb/api/urls.py
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - agents/freeark-skill/SKILL.md
    - agents/freeark-skill/scripts/tier1_readonly.py
```

---

## 总体评审结论

**PASS** — 无 CRITICAL 发现，代码实现与架构设计文档一致。

---

## 1. 安全性评审

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 所有新 API 端点有 `IsAuthenticated` 鉴权 | PASS | device_fault_count 和 device_fault_summary 均有 `@permission_classes([permissions.IsAuthenticated])` |
| 严禁查询 device_param_history | PASS | fault_utils.py 所有 ORM 查询均针对 PLCLatestData，未出现 DeviceParamHistory 引用 |
| 输入校验（specific_part 上限 50）| PASS | device_fault_count 视图中有 `len(specific_parts) > 50` 检查 |
| SQL 注入风险 | PASS | 全部使用 Django ORM，无原生 SQL 拼接 |
| 敏感数据泄露 | PASS | fault_details 仅返回 param_name 和 value，无 PII |
| OpenClaw SSRF 防护 | PASS | freeark_client.py 中 SSRF hardcheck 保持不变（127.0.0.1:8000） |

---

## 2. 性能评审

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 批量查询避免 N+1 | PASS | _compute_from_db_batch 使用单条 SQL + Q 对象，一次 DB 往返覆盖所有 specific_part |
| DB 层索引利用 | PASS | `param_name__startswith='error_'` 等价 LIKE 'error_%'，可利用 (specific_part, param_name) 前缀索引 |
| Python 层精确过滤 | PASS | DB 层宽过滤后，Python 层用 `_ERROR_N_PATTERN.match` 精确排除 error_xxx_status 等非数字后缀字段 |
| 缓存批量命中优化 | PASS | get_fault_count_batch_cached 先遍历缓存，仅对 miss_list 批量查 DB，减少 DB 穿透 |
| fresh_air_fault_status popcount | PASS | 使用 `bin(int(value)).count('1')`，兼容 Python 3.9 及以下版本 |
| device_management_device_list 最小改动 | PASS | 在现有序列化循环外提前批量获取 fault_counts，不在循环内逐条查询 |

---

## 3. 代码质量评审

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 类型注解完整性 | PASS | 公共函数均有 `-> Optional[int]`、`-> dict`、`-> list` 等注解 |
| Docstring 完整性 | PASS | 所有公共函数有 Args/Returns 说明 |
| 错误处理 | PASS | device_fault_count 和 device_fault_summary 均有 try/except，异常时返回 500 并记录日志 |
| 日志记录 | PASS | 异常通过 `logger.exception()` 记录，含 specific_parts 上下文 |
| AB-001/AB-002 占位注释 | PASS | fault_utils.py 文件头和相关函数均有 TODO 注释指向 architecture_design 文档 |
| 向后兼容性 | PASS | device_management_device_list 响应新增 fault_count 字段，已有字段不变；现有客户端可忽略新字段 |

---

## 4. 架构一致性评审

| 检查项 | 结果 | 说明 |
|--------|------|------|
| ADR-FC-001 LocMemCache TTL=60s | PASS | `_FAULT_CACHE_TTL = 60` |
| ADR-FC-003 fresh_air_fault_status popcount | PASS | `count_faults_for_row` 对 fresh_air_fault_status 做 `bin(int(value)).count('1')` |
| ADR-FC-004 REST API 路径 | PASS | `/api/devices/fault-count/` 和 `/api/devices/fault-summary/` 均已注册 |
| ADR-FC-005 短 TTL 定时刷新 | PASS | mqtt_handlers.py 未修改；缓存仅靠 TTL=60s 维护 |
| ADR-FC-006 count_faults_for_row 接口 | PASS | 函数签名 `count_faults_for_row(param_name, value) -> int` 与 ADR 设计一致 |
| MOD-BE-FC-04 不修改 mqtt_handlers.py | PASS | OQ-01 裁决落地，MQTT handler 未改动 |

---

## 5. 前端评审

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 列插入位置正确（运行模式列与操作列之间）| PASS | 插入在 `<el-table-column label="运行模式">` 之后、`<el-table-column label="操作">` 之前 |
| 颜色语义 token（var(--color-success) / var(--color-danger)）| PASS | 使用 CSS 变量，未硬编码 hex 色值 |
| null/undefined 时显示 `—` | PASS | `v-if="row.fault_count === null || row.fault_count === undefined"` 分支 |
| Script 无修改（无额外状态管理）| PASS | 仅 template 修改，fault_count 随 API 响应自动包含在 tableData.value 中 |
| 不使用 el-tag（避免破坏列宽）| PASS | 使用 `<span>` + 内联样式，符合 AC-FC-01-05 |

---

## 6. OpenClaw Skill 评审

| 检查项 | 结果 | 说明 |
|--------|------|------|
| SKILL.md Tier-1 工具表格追加 2 行 | PASS | freeark_get_fault_count 和 freeark_get_fault_summary 均已追加 |
| 版本号更新（v2.1.0 → v2.2.0）| PASS | SKILL.md 末尾版本节已更新 |
| tier1_readonly.py 新增工具函数 | PASS | freeark_get_fault_count 和 freeark_get_fault_summary 均已实现 |
| TIER1_HANDLERS 字典已更新 | PASS | 两个新工具均已注册到 TIER1_HANDLERS |
| 工具使用 FreeArkClient（Bearer token）| PASS | `_client().get(...)` 调用与现有 14 个工具一致 |
| SSRF 防护不受影响 | PASS | freeark_client.py 未修改，hardcheck 保持不变 |

---

## 7. CRITICAL/HIGH/MINOR 发现清单

| 级别 | 发现 | 处置 |
|------|------|------|
| 无 CRITICAL | — | — |
| MINOR-01 | `get_fault_details()` 每次实时查 DB，不经缓存，在 fault_count API 中对每个有故障的 specific_part 均查一次 | 可接受：fault_details 仅对 fault_count > 0 的 specific_part 查询；设备数量有限；本期 SLA 不要求 fault-count API 的 P95（仅 device-list API 有 SLA）|
| MINOR-02 | 前端「故障数量」列加载态显示 `—` 覆盖了 null 和 undefined 两种状态，无法区分"DB 无记录"和"API 尚未返回" | 可接受：两种情况对运维人员均显示 `—`，语义无损；如需区分可在 v0.5.x 后续版本添加骨架占位 |
| MINOR-03 | `device_fault_summary` 的 `building_filter` 过滤同时支持 `building='3'` 和 `building='3栋'` 两种格式，与 device_management_device_list 的房号过滤方式一致，但未做单元测试覆盖两种格式 | 已接受：生产 OwnerInfo.building 字段值由业务决定；测试中用 building='3' 已覆盖主路径 |

---

## 8. 测试覆盖概览

| 测试类型 | 测试文件 | 覆盖场景数 |
|---------|---------|----------|
| 单元测试 | tests_fault_count.py | 28 个（count_faults_for_row × 20 + compute_fault_count_v2 × 6 + is_fault_param × 7）|
| 单元测试（DB）| tests_fault_count.py | 8 个（_compute_from_db_batch）|
| 单元测试（缓存）| tests_fault_count.py | 6 个（cache hit/miss/TTL/invalidate）|
| 集成测试 | tests_fault_count.py | 18 个（fault-count 视图 × 10 + fault-summary 视图 × 6 + device-list 视图 × 2）|
| 性能测试 | tests_fault_count.py | 1 个（< 100 ms，SQLite）|
