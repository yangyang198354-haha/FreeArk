# v0.5.1 实施计划

**版本**：v0.5.1 | **日期**：2026-05-20 | **状态**：IMPLEMENTED

## 实施变更清单

| 文件 | 变更位置 | 变更内容 |
|------|---------|---------|
| `api/param_value_label.py` | `PARAM_VALUE_LABELS["_mode"]` | 键从 0-3 改为 1-4 |
| `api/param_value_label.py` | `PARAM_EXACT_VALUE_LABELS` | 新增 central_energy_supply 三值映射 |
| `api/param_value_label.py` | `get_display_value()` | 历史值 mode=0 兼容返回"制冷" |
| `api/views_device_settings.py` | `WRITABLE_PARAM_NAMES` | 追加 'central_energy_supply' |
| `datacollection/plc_write_manager.py` | 类常量 | 新增 MODE_DEHUMIDIFICATION=4 |
| `datacollection/plc_write_manager.py` | `write_mode_for_building()` | 有效值扩展 [1-4]；跳过 central_energy_supply 联动写 |
| `datacollection/plc_write_manager.py` | `get_mode_name()` | 含除湿 |
| `datacollection/plc_data_viewer_gui.py` | line 478-482 | 删除除湿静默降级逻辑 |
| `frontend/src/views/DeviceCardsView.vue` | line 311-318 | operation_mode 兼容 0；central_energy_supply 三值展示 |
| `plc_config.json` | `operation_mode` 字段 | 新增 enum_values 注释 |
| `api/tests/test_device_settings_v050.py` | `test_UT_W_13` | 断言改为可写 |
| `api/tests/test_device_settings_v050.py` | `test_IT_REG_06` | 断言改为可写 |
| `api/tests/test_device_settings_v050.py` | `test_UT_VL_01` | 枚举键更新为 1-4 |
| `api/tests/test_device_settings_v050.py` | `test_UT_VL_06/07` | 标签说明更新 |
| `api/tests/test_device_settings_v050.py` | 新增类 `V051ModeEnumAlignmentTests` | 13 个单元测试 |
| `api/tests/test_device_settings_v050.py` | 新增类 `V051CentralEnergySupplyWriteTests` | 5 个集成测试（mock MQTT）|
