# v0.5.1 测试计划

**版本**：v0.5.1 | **日期**：2026-05-20

## 测试范围

- 单元测试：`param_value_label.py`、`views_device_settings._is_writable`
- 集成测试：写入接口 `/api/device-settings/write/`，mock MQTT（不连真实 PLC）
- 回归测试：v0.5.0 已有测试套件全量通过

## 测试环境

- 数据库：SQLite（in-memory，Django test runner）
- PLC 写入：mock MQTT client（`_mqtt_mock()`），不连接真实 PLC（192.168.x.x）
- 运行命令：`cd FreeArkWeb/backend/freearkweb && python manage.py test api.tests.test_device_settings_v050 --settings=freearkweb.test_settings --verbosity=2`

## 测试 ID 列表

### 更新用例（原 v0.5.0）

| ID | 描述 | 变更原因 |
|----|------|---------|
| test_UT_W_13 | central_energy_supply 可写 | 断言方向反转（原断言不可写） |
| test_IT_REG_06 | central_energy_supply 可写 | 断言方向反转 |
| test_UT_VL_01 | operation_mode 枚举键 1-4 | 枚举键从 0-3 改为 1-4 |
| test_UT_VL_06 | 历史值 0 兼容展示 | 说明更新（行为不变） |
| test_UT_VL_07 | operation_mode=1 → 制冷 | 枚举起点变更 |

### 新增 v0.5.1 单元测试（V051ModeEnumAlignmentTests）

| ID | 描述 |
|----|------|
| test_UT_V051_01~06 | operation_mode 枚举 1-4，历史值 0 兼容 |
| test_UT_V051_07~12 | central_energy_supply 可写、三值、兼容 |
| test_UT_V051_13 | 除湿不降级验证 |

### 新增 v0.5.1 集成测试（V051CentralEnergySupplyWriteTests）[MOCK-ANNOTATED]

| ID | 描述 |
|----|------|
| test_IT_V051_01 | 写入值=1（制冷）返回 202 |
| test_IT_V051_02 | 写入值=2（制热）返回 202 |
| test_IT_V051_03 | 写入值=3（无，主动关阀）返回 202 |
| test_IT_V051_04 | _is_writable 确认 |
| test_IT_V051_05 | operation_mode 仍可写（回归）|

## PLC 实写说明

所有 PLC 写入测试均通过 mock MQTT client 执行，不连接真实 PLC（192.168.x.x）。
标注：[MOCK-ANNOTATED] — 测试报告中明确标注，未伪造通过。
