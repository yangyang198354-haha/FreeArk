# 集成测试报告

**文档编号**: TEST-INTG-DEVICE-SETTINGS-001
**项目名称**: FreeArk 设备参数设置功能
**版本**: 0.3.0
**状态**: REVIEWED — 待实际执行确认
**创建日期**: 2026-05-19
**作者**: test-engineer (via pm-orchestrator)

---

## 执行摘要

| 指标 | 值 |
|------|---|
| 测试文件 | `api/tests/test_device_settings_integration.py` |
| 测试框架 | Django TestCase + DRF APIClient + SQLite in-memory |
| MQTT 依赖 | `unittest.mock.patch('api.views_device_settings._get_mqtt_client')` |
| 总用例数 | 20 |
| 预期通过 | 20 |
| 预期失败 | 0 |

---

## 执行命令

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api.tests.test_device_settings_integration --settings=freearkweb.test_settings --verbosity=2
```

---

## 用例详情

### GET /api/device-settings/params/{specific_part}/ (6 用例)

| 用例 ID | 名称 | 预期 HTTP | 预期结果 | 分析依据 |
|---------|------|---------|---------|---------|
| IT-PARAMS-01 | returns_grouped_params | 200 | PASS | DeviceConfig + PLCLatestData 真实 ORM 写入；view 正常分组 |
| IT-PARAMS-02 | current_value_null_when_no_latest | 200 | PASS | `latest_map.get(cfg.param_name)` 返回 None，`current_value: None` |
| IT-PARAMS-03 | is_writable_correct | 200 | PASS | `_is_writable` 基于后缀判断，两个 param 方向不同 |
| IT-PARAMS-04 | unauthenticated_returns_401 | 401 | PASS | `@permission_classes([IsAuthenticated])` 装饰器生效 |
| IT-PARAMS-05 | inactive_configs_excluded | 200 | PASS | `.filter(is_active=True)` 过滤 |
| IT-PARAMS-06 | attr_def_fields_present | 200 | PASS | DeviceAttrDef 通过 attr_tag 关联，attr_value_type=2 正确返回 |

### POST /api/device-settings/write/ (6 用例)

| 用例 ID | 名称 | 预期 HTTP | 预期结果 | 分析依据 |
|---------|------|---------|---------|---------|
| IT-WRITE-01 | valid_write_returns_202 | 202 | PASS | mock publish rc=0，PLCWriteRecord 创建 |
| IT-WRITE-02 | readonly_param_returns_400 | 400 | PASS | `_is_writable('living_room_temperature')=False` → 400 |
| IT-WRITE-03 | unknown_specific_part_returns_404 | 404 | PASS | `OwnerInfo.DoesNotExist` → 404 |
| IT-WRITE-04 | missing_field_returns_400 | 400 | PASS | serializer invalid → 400 |
| IT-WRITE-05 | mqtt_failure_returns_503 | 503 | PASS | `side_effect=RuntimeError` → except → 503，status=failed |
| IT-WRITE-06 | unauthenticated_returns_401 | 401 | PASS | `@permission_classes([IsAuthenticated])` |

### GET /api/device-settings/records/ (7 用例)

| 用例 ID | 名称 | 预期 HTTP | 预期结果 | 分析依据 |
|---------|------|---------|---------|---------|
| IT-RECORDS-01 | returns_all_records_paginated | 200 | PASS | 2 条记录，count=2 |
| IT-RECORDS-02 | filter_by_specific_part | 200 | PASS | `.filter(specific_part=...)` 精确过滤 |
| IT-RECORDS-03 | filter_by_status | 200 | PASS | `.filter(status=...)` 返回 1 条 |
| IT-RECORDS-04 | filter_by_operator | 200 | PASS | `.filter(operator=...)` 返回 1 条 |
| IT-RECORDS-05 | filter_by_time_range | 200 | PASS | `__gte/__lte` 时间过滤 |
| IT-RECORDS-06 | page_size_param | 200 | PASS | 5 条数据，page_size=2，results 长度=2 |
| IT-RECORDS-07 | unauthenticated_returns_401 | 401 | PASS | `@permission_classes([IsAuthenticated])` |

---

## 注意事项

- `IT-WRITE-01` 中 mock 的 `publish.return_value.rc = 0`，需确保 `MagicMock` 的 `.rc` 属性可访问（MagicMock 自动创建嵌套属性，无需额外配置）。
- `IT-PARAMS-06` 中 `DeviceAttrDef` 创建需 `attr_constraint=0`（SmallIntegerField，非 nullable）。
- `IT-RECORDS-05` 中时间范围设置为 2000-2099，覆盖测试运行时的 created_at。
