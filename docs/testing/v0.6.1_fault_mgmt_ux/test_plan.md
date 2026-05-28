# 测试计划 — v0.6.1-FM-UX 故障管理 UX 调整

```
file_header:
  document_id: TEST-PLAN-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 测试计划
  author_agent: sub_agent_test_engineer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
    - docs/requirements/v0.6.1_fault_mgmt_ux/user_stories.md
    - docs/architecture/architecture_design_v0.6.1_fault_mgmt_ux.md
    - docs/implementation/v0.6.1_fault_mgmt_ux/implementation_plan.md
    - docs/implementation/v0.6.1_fault_mgmt_ux/code_review_report.md
```

---

## 1. 测试范围

### 1.1 纳入范围

| 测试层 | 覆盖对象 | 工具 |
|--------|---------|------|
| 单元测试（Unit） | `api/device_name_cache.py`（5 个场景） | Django TestCase + unittest.mock |
| 集成测试（Integration） | `api/serializers_fault.py`（新字段序列化 + API 端到端） | Django TestCase + DRF APIClient + SQLite |
| 回归测试（Regression） | `tests_fault_event.py` 中的 `TestFaultEventSerializer` | 同上 |
| 手动 E2E（Manual E2E） | 前端 Vue 页面（Layout.vue, FaultManagementView.vue, DeviceManagementDeviceListView.vue） | 浏览器手动测试 |

### 1.2 排除范围

| 排除项 | 原因 |
|--------|------|
| 前端 JavaScript 单元测试 | 无 Vitest/Jest 基建，前端测试通过手动 E2E 覆盖 |
| 生产 MySQL 性能测试 | 本阶段仅 SQLite 测试，MySQL P95 指标在生产部署后验证 |
| MQTT 故障消费服务集成测试 | v0.6.0-FM 已覆盖，本版本未改动该模块 |

---

## 2. 覆盖矩阵（FR-FM-UX × 测试层）

| 需求 | 描述 | 单元测试 | 集成测试 | E2E |
|------|------|---------|---------|-----|
| **FR-FM-UX-01** | 导航入口变更（Layout.vue + 移除设备列表按钮） | N/A | N/A | E2E-01, E2E-02 |
| **FR-FM-UX-02** | 房号 CascadingSelector + specific_part 参数 | N/A | INT-05 | E2E-03 |
| **FR-FM-UX-03** | 设备名称三级降级渲染 | TC-DNC-01~05 | INT-01~04 | E2E-04 |
| **FR-FM-UX-04** | 默认筛选"只看未恢复" + URL 参数优先 | N/A | INT-06 | E2E-05 |

---

## 3. 单元测试用例规划

### 3.1 device_name_cache 单元测试

测试文件：`api/tests/test_device_name_cache_v061.py`

| 用例 ID | 类 | 测试方法 | 测试场景 | 预期结果 | FR/ADR |
|--------|-----|---------|---------|---------|--------|
| TC-DNC-01a | TestGetDeviceNameBySnHit | test_hit_returns_device_name | mock _load_cache 注入 {22155: '新风'} → get(22155) | 返回 '新风' | FR-FM-UX-03 / ADR-UX-03 |
| TC-DNC-01b | TestGetDeviceNameBySnHit | test_hit_with_real_db_fixture | SQLite 无 DeviceNode 记录 → get(22155) | 返回 None（不崩溃） | AQ-01 |
| TC-DNC-01c | TestGetDeviceNameBySnHit | test_multiple_calls_hit_cache_only_loads_once | TTL 未过期时，3 次调用只加载一次 | _load_cache 调用 1 次 | ADR-UX-03 / ADR-UX-06 |
| TC-DNC-02a | TestGetDeviceNameBySnMiss | test_miss_returns_none | sn=99999 不在缓存中 | 返回 None | FR-FM-UX-03 |
| TC-DNC-02b | TestGetDeviceNameBySnMiss | test_empty_cache_after_load_returns_none | 加载后 DeviceNode 无记录 | 返回 None | ADR-UX-03 |
| TC-DNC-03a | TestTtlExpiry | test_ttl_expired_triggers_reload | mock monotonic 推进 100s (>60s TTL) | _load_cache 被调用 1 次 | ADR-UX-03 |
| TC-DNC-03b | TestTtlExpiry | test_ttl_not_expired_skips_reload | monotonic 推进 30s (<60s TTL) | _load_cache 不被调用 | ADR-UX-03 |
| TC-DNC-03c | TestTtlExpiry | test_exactly_at_ttl_boundary_triggers_reload | diff=60.0s（不超过 TTL，条件 > 60.0 = False）| _load_cache 不调用 | ADR-UX-03 |
| TC-DNC-03d | TestTtlExpiry | test_just_over_ttl_triggers_reload | diff=60.1s（超过 TTL）| _load_cache 调用 1 次 | ADR-UX-03 |
| TC-DNC-04a | TestInvalidateCache | test_invalidate_sets_loaded_at_to_zero | 调用 invalidate 后 _cache_loaded_at = 0.0 | _cache_loaded_at == 0.0 | ADR-UX-03 |
| TC-DNC-04b | TestInvalidateCache | test_invalidate_then_get_triggers_load | invalidate → get(22155) 触发重建 | _load_cache 调用 1 次，返回新值 | ADR-UX-03 |
| TC-DNC-04c | TestInvalidateCache | test_invalidate_idempotent | 多次 invalidate 不崩溃 | _cache_loaded_at == 0.0 | ADR-UX-06 |
| TC-DNC-05a | TestLoadCacheExceptionSafety | test_exception_does_not_raise_to_caller | _load_cache 内抛异常 → get 不崩溃 | 返回 None，不抛异常 | ADR-UX-03 / ADR-UX-06 |
| TC-DNC-05b | TestLoadCacheExceptionSafety | test_exception_preserves_old_cache | 异常发生时旧 _cache 保留 | _cache 旧值不变 | ADR-UX-03 |

**单元测试汇总：14 个用例**

### 3.2 FaultEventSerializer 集成测试

测试文件：`api/tests/test_fault_event_serializer_v061.py`

| 用例 ID | 类 | 测试方法 | 测试场景 | 预期结果 | FR/ADR |
|--------|-----|---------|---------|---------|--------|
| TC-SER-01a | TestSerializerNewFieldsPresent | test_device_name_field_present | API 响应含 device_name 字段 | 字段存在 | FR-FM-UX-03 |
| TC-SER-01b | TestSerializerNewFieldsPresent | test_device_type_label_field_present | API 响应含 device_type_label 字段 | 字段存在 | FR-FM-UX-03 |
| TC-SER-01c | TestSerializerNewFieldsPresent | test_both_new_fields_exist_simultaneously | 两字段同时存在 | 均存在 | FR-FM-UX-03 |
| TC-SER-02a | TestSerializerMainPath | test_device_sn_hit_returns_device_name | device_sn=22155 命中 → device_name='新风' | device_name='新风' | FR-FM-UX-03 / ADR-UX-03 |
| TC-SER-02b | TestSerializerMainPath | test_device_sn_hit_supersedes_product_code | 主路径命中时 device_name 非 None | device_name='新风', device_type_label='新风机' | FR-FM-UX-03 |
| TC-SER-02c | TestSerializerMainPath | test_cache_already_warm_no_reload | 缓存预热后不触发重载 | _load_cache 不调用 | ADR-UX-03 / ADR-UX-06 |
| TC-SER-03a | TestSerializerFallbackOne | test_cache_miss_product_code_hit_returns_type_label | cache miss + product_code='270001' → device_type_label='水力模块' | device_name=None, device_type_label='水力模块' | FR-FM-UX-03 / ADR-UX-05 |
| TC-SER-03b | TestSerializerFallbackOne | test_various_known_product_codes | 7 条 PRODUCT_CODE_LABELS 全部正确映射 | 各 product_code 返回正确 label | ADR-UX-05 / OQ-05 |
| TC-SER-04a | TestSerializerFallbackTwo | test_both_miss_returns_null_null | cache miss + 未知 product_code → 双 null | device_name=None, device_type_label=None | FR-FM-UX-03 |
| TC-SER-04b | TestSerializerFallbackTwo | test_null_null_preserves_device_sn_field | 双 null 时 device_sn 字段仍存在 | device_sn 存在且正确 | FR-FM-UX-03 |
| TC-SER-05a | TestSerializerEdgeCases | test_non_numeric_device_sn_returns_none_gracefully | device_sn='SN001' 不崩溃，返回 None | device_name=None, 状态码 200 | FR-FM-UX-03 |
| TC-SER-05b | TestSerializerEdgeCases | test_empty_device_sn_returns_none_gracefully | device_sn='' 不崩溃 | device_name=None | FR-FM-UX-03 |
| TC-SER-05c | TestSerializerEdgeCases | test_all_v061_fields_in_serializer_output | 全部 16 个字段（含 2 个新字段）在响应中 | 所有字段存在 | FR-FM-UX-03 |

**集成测试汇总：13 个用例**

---

## 4. 回归测试范围

### 4.1 已有测试文件（tests_fault_event.py）

已有测试文件中 `TestFaultEventSerializer`（P0-10）的 `EXPECTED_FIELDS` 列表不含 v0.6.1 新增字段 `device_name` 和 `device_type_label`。

评估结论：
- 旧测试中 `test_all_expected_fields_present` 验证的是 14 个已有字段 —— 这些字段仍然存在，**旧测试不会因新字段导致失败**。
- 新字段仅为追加，不影响已有字段存在性。
- 无需修改 `tests_fault_event.py`；新字段验证由 `test_fault_event_serializer_v061.py` 的 `TC-SER-05c` 覆盖。

---

## 5. 手动 E2E 测试用例（前端）

测试环境：本地 `npm run dev` + 后端 `python manage.py runserver`（或生产环境）

| E2E ID | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|--------|------|---------|---------|---------|
| **E2E-01** | 导航菜单"故障管理"入口 | 登录，在任意页面 | 展开左侧"设备管理"子菜单 | 看到"设备列表"和"故障管理"两个子项 |
| **E2E-02** | 设备列表页右上角按钮已移除 | 已登录 | 访问 `/device-management/device-list` | 页头只有标题 h2 和副标题 p，无橙色"故障管理"按钮 |
| **E2E-03** | 房号 CascadingSelector 过滤 | 在故障管理页 | 选择楼栋=3, 单元=1, 房号=702，点击查询 | Network 面板请求含 `specific_part=3-1-702`；表格只显示 specific_part 含 "3-1-702" 的记录 |
| **E2E-04** | 设备名称列显示 | 故障列表有数据 | 查看表格"设备名称"列 | 已知 device_sn 的行显示中文名（如"新风"）；未识别行显示 SN+"未识别"标签 |
| **E2E-05** | 默认筛选"未恢复" + URL 参数优先 | 无 URL 参数进入页面 | 访问 `/device-management/faults` | radio-group "未恢复"按钮高亮，接口请求含 `is_active=true`；访问 `?is_active=false` 时"已恢复"高亮 |

---

## 6. 测试通过标准（门控）

| 指标 | 目标 | 说明 |
|------|------|------|
| 单元测试通过率 | **100%** | 14/14 用例全部 PASS（门控严格：不允许跳过或改期望） |
| 集成测试通过率 | **100%** | 13/13 用例全部 PASS |
| E2E 手动测试 | 5/5 场景 PASS | 由用户在浏览器中手动验证 |
| 回归测试 | 全部 tests_fault_event.py 用例无退化 | 原有 tests_fault_event.py 测试套件通过率不低于 v0.6.0 水平 |
