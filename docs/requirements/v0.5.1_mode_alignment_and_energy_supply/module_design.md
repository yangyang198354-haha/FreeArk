# v0.5.1 模块设计文档

**版本**：v0.5.1 | **日期**：2026-05-20

## 模块变更详情

### M1: param_value_label.py

- `PARAM_VALUE_LABELS["_mode"]`：键从 0-3 改为 1-4（制冷/制热/通风/除湿）
- `PARAM_EXACT_VALUE_LABELS`：新增 `'central_energy_supply': {"1":"制冷","2":"制热","3":"无"}`
- `get_display_value('operation_mode', 0)`：兼容旧值 0，展示"制冷"（通过 COMPAT_MODE_0 fallback）

### M2: views_device_settings.py

- `WRITABLE_PARAM_NAMES`：追加 `'central_energy_supply'`

### M3: plc_write_manager.py

- 类常量：新增 `MODE_DEHUMIDIFICATION = 4`
- `write_mode_for_building`：有效值扩展为 `[1,2,3,4]`；仅写 `operation_mode`（DB14 offset=89），移除 central_energy_supply 联动写入
- 注释：方法 docstring 更新"4=除湿"

### M4: plc_data_viewer_gui.py

- 删除 line 478-482 的 mode=4 静默降级逻辑（if mode_value==4 分支）

### M5: DeviceCardsView.vue

- `central_energy_supply` 展示逻辑：`v===0?'无':'有'` → `{1:'制冷',2:'制热',3:'无'}[v] ?? '无'`

### M6: plc_config.json

- `operation_mode` 字段新增 `"enum_values"` 注释对象

### M7: test_device_settings_v050.py（测试同步）

- `test_UT_W_13` 断言改为 `assertTrue(_is_writable('central_energy_supply'))`
- `test_IT_REG_06` 断言改为 `assertTrue(_is_writable('central_energy_supply'))`
- 新增 v0.5.1 测试类（枚举值域、可写验证、兼容展示）
