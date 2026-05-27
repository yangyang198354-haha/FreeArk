# 测试计划

```
file_header:
  document_id: DEV-TEST-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 测试计划
  author_agent: sub_agent_test_engineer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.0_fault_management.md
    - docs/architecture/module_design_v0.6.0_fault_management.md
    - docs/development/v0.6.0_fault_management/implementation_plan.md
    - docs/development/v0.6.0_fault_management/code_review_report.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始测试计划，P0/P1 全覆盖 |

---

## 1. 测试目标

验证 v0.6.0 故障管理模块的以下能力：

1. **故障分类纯函数**（fault_classifier.py）：正确识别故障候选字段、判断活跃态、映射类型和严重级别。
2. **状态机转移逻辑**（state_machine.py）：T1/T2/T3 按设计工作，内存与 DB 一致。
3. **REST API**（views_fault.py）：过滤、分页、排序、认证均符合规范。
4. **序列化器**（serializers_fault.py）：输出字段完整、类型正确、datetime ISO8601 格式。
5. **清理命令**（fault_cleanup.py）：dry-run 不删除、分批删除、天数边界正确。
6. **端到端集成**：_handle_message → state_machine → DB 链路可跑通。

---

## 2. 测试范围

### 2.1 包含范围

| 优先级 | 测试类别 | 覆盖文件 |
|-------|---------|---------|
| P0 | 单元测试 | fault_classifier.py, state_machine.py, views_fault.py, serializers_fault.py, fault_cleanup.py |
| P1 | 集成测试 | fault_consumer.py + state_machine + DB 端到端；API + 真实 SQLite |
| P2 | E2E（手工/可选）| Vue 前端组件（FaultManagementView.vue）|

### 2.2 排除范围

- 生产 MySQL 数据库（所有测试使用 SQLite）
- paho-mqtt 真实 Broker 连接（全部 mock）
- systemd 服务启动（部署阶段验证）

---

## 3. 测试环境

| 项目 | 值 |
|------|---|
| 测试库 | SQLite（Django `test` 命令自动切换，见 settings._RUNNING_TESTS）|
| 测试框架 | Django TestCase + unittest.mock |
| 运行命令 | `python manage.py test api.tests_fault_event --settings=freearkweb.settings` |
| 工作目录 | `FreeArkWeb/backend/freearkweb/` |
| 外部依赖 mock | paho-mqtt、OwnerInfo DB 查询（通过 _MacCache._cache 直接注入）|

---

## 4. 测试用例清单

### 4.1 P0 单元测试

#### 4.1.1 is_fault_candidate（11 个用例）

| 用例 ID | 输入 | 期望结果 |
|--------|------|---------|
| TC-FC-001 | `comm_fault_timeout` | True |
| TC-FC-002 | `living_room_temp_sensor_error` | True |
| TC-FC-003 | `fresh_air_fault_bit_7` | True |
| TC-FC-004 | `error_82` | True |
| TC-FC-005 | `temperature` | False |
| TC-FC-006 | `fresh_air_fault_status` | False（位域整体，非 bit_N）|
| TC-FC-007 | `''` | False |
| TC-FC-008 | `fresh_air_fault_bit_` | False（无数字后缀）|
| TC-FC-009 | `fresh_air_fault_bit_abc` | False |
| TC-FC-010 | `error_` | False（无数字）|
| TC-FC-011 | `errorx` | False |

#### 4.1.2 is_fault_active（16 个用例）

| 用例 ID | param_name | value | 期望结果 |
|--------|-----------|-------|---------|
| TC-FA-001 | comm_fault_timeout | 'normal' | False |
| TC-FA-002 | comm_fault_timeout | 'timeout' | True |
| TC-FA-003 | comm_fault_timeout | None | False |
| TC-FA-004 | error_1 | 0 | False |
| TC-FA-005 | error_1 | '0' | False |
| TC-FA-006 | error_82 | '82' | True |
| TC-FA-007 | error_1 | None | False |
| TC-FA-008 | fresh_air_fault_bit_0 | 0 | False |
| TC-FA-009 | fresh_air_fault_bit_7 | '1' | True |
| TC-FA-010 | fresh_air_fault_bit_0 | None | False |
| TC-FA-011 | fresh_air_fault_bit_0 | 'abc' | False |
| TC-FA-012 | living_room_temp_sensor_error | 0 | False |
| TC-FA-013 | living_room_temp_sensor_error | 1 | True |
| TC-FA-014 | living_room_temp_sensor_error | None | False |
| TC-FA-015 | living_room_temp_sensor_error | False | False |
| TC-FA-016 | living_room_temp_sensor_error | True | True |

#### 4.1.3 get_fault_type_and_severity（11 个用例）

| 用例 ID | 输入 | 期望 fault_type | 期望 severity |
|--------|------|--------------|-------------|
| TC-FTS-001 | comm_fault_timeout | comm | error |
| TC-FTS-002 | fresh_air_unit_stop_error | fresh_air | error |
| TC-FTS-003 | living_room_communication_error | comm | error |
| TC-FTS-004 | bedroom_temp_sensor_error | sensor | error |
| TC-FTS-005 | study_room_humidity_sensor_error | sensor | error |
| TC-FTS-006 | fresh_air_fault_bit_3 | fresh_air | warning |
| TC-FTS-007 | error_82 | other_error | error |
| TC-FTS-008 | totally_unknown_param | other_error | error |
| TC-FTS-009 | hydraulic_module_low_temp_error | other_error | error |
| TC-FTS-010 | energy_meter_status_communication_error | comm | error |
| TC-FTS-011 | fresh_air_unit_communication_error | comm | error（精确匹配优先）|

#### 4.1.4 get_fault_message（5 个用例）

| 用例 ID | 输入 | 期望 |
|--------|------|------|
| TC-FM-001 | comm_fault_timeout | 不含下划线 |
| TC-FM-002 | comm_fault_timeout | 首字母大写 |
| TC-FM-003 | 400 字符长参数名 | len ≤ 255 |
| TC-FM-004 | living_room_temp_sensor_error | 'Living room temp sensor error' |
| TC-FM-005 | fresh_air_fault_bit_7 | 'Fresh air fault bit 7' |

#### 4.1.5 状态机转移（9 个用例）

| 用例 ID | 场景 | 期望 |
|--------|------|------|
| TC-SM-001 | T1: 首次故障 | INSERT DB + 内存新增 |
| TC-SM-002 | T1: DB 字段验证 | specific_part/device_sn/product_code/fault_code 一致 |
| TC-SM-003 | T2: 故障持续 | DB 行数不变 + 内存 last_seen_at 更新 |
| TC-SM-004 | T3: 故障恢复 | DB is_active=False + recovered_at 非空 |
| TC-SM-005 | T3: 内存更新 | state.is_active=False |
| TC-SM-006 | 正常报文无先验状态 | 无 DB 写入 |
| TC-SM-007 | T1→T2×3→T3 完整序列 | 1 条 DB 行，is_active=False |
| TC-SM-008 | 两个不同 key 独立 | 2 条 DB 行，2 条内存状态 |
| TC-SM-009 | rebuild_from_db LIMIT | 超 10000 条时仅加载 10000 |

#### 4.1.6 rebuild_from_db（4 个用例）

| 用例 ID | 场景 | 期望 |
|--------|------|------|
| TC-RDB-001 | 空库 | count=0，内存为空 |
| TC-RDB-002 | 2 条活跃 | count=2 |
| TC-RDB-003 | 1 条非活跃 | count=0（不加载）|
| TC-RDB-004 | 重建前有旧状态 | 旧状态被清空 |

#### 4.1.7 views_fault（21 个用例）

见代码 TestFaultEventListAuth, TestFaultEventListPagination, TestFaultEventListFilters,
TestFaultEventListDefaultTimeRange, TestFaultEventCategories。

#### 4.1.8 serializers_fault（10 个用例）

见代码 TestFaultEventSerializer。

#### 4.1.9 fault_cleanup（10 个用例）

见代码 TestFaultCleanupCommand。

### 4.2 P1 集成测试

#### 4.2.1 _handle_message + state_machine + DB（7 个用例）

见代码 TestHandleMessageIntegration。

#### 4.2.2 API + DB 集成（5 个用例）

见代码 TestFaultEventAPIIntegration。

---

## 5. 测试约束

1. 全部使用 SQLite；禁止连接生产 MySQL（192.168.31.98:3306）。
2. paho-mqtt 连接全部通过 `_MacCache._cache` 直接注入跳过 DB 刷新，无真实 MQTT 连接。
3. 测试文件路径：`FreeArkWeb/backend/freearkweb/api/tests_fault_event.py`
4. 至少通过：`python manage.py test api.tests_fault_event`

---

## 6. 通过标准

| 指标 | 阈值 |
|------|------|
| 单元测试通过率 | 100%（P0 全通过）|
| 集成测试通过率 | 100%（P1 全通过）|
| 失败用例 | 0 个 FAIL |
| 跳过用例 | 允许 0 个（无需 skip）|
