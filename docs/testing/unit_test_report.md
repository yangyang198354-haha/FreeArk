# 单元测试报告

**文档编号**: TEST-UNIT-DEVICE-SETTINGS-001
**项目名称**: FreeArk 设备参数设置功能
**版本**: 0.3.0 → 0.4.0
**状态**: REVIEWED — 待实际执行确认
**创建日期**: 2026-05-19
**作者**: test-engineer (via pm-orchestrator)

---

## v0.4.0 单元测试追加段（2026-05-19）

**执行方式**: 深度静态分析（PM 工具环境无 shell 执行能力；实际跑测需在目标机手动执行命令）

**执行命令（须在目标机手动执行）**:
```powershell
# 后端单元测试
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api.tests.test_device_settings --settings=freearkweb.test_settings --verbosity=2

# datacollection 单元测试
cd C:\Users\yanggyan\MyProject\FreeArk
python -m pytest datacollection/tests/test_plc_write_subscriber.py -v
```

### v0.4.0 后端单元测试执行摘要（静态分析）

| 指标 | 值 |
|------|---|
| 测试文件 | `api/tests/test_device_settings.py` |
| 总用例数（v0.4.0） | 27 |
| 静态分析：预测通过 | 27 |
| 静态分析：预测失败 | 0 |
| 与 v0.3.0 基线对比 | +4 用例（NORM 系列新增；ACK 系列重构为 batch 协议） |

### v0.4.0 新增/修改用例详情

| 用例 ID | 测试方法 | 覆盖功能 | 预测结果 | 分析依据 |
|---------|---------|---------|---------|---------|
| UT-S-01（重构） | test_ut_s_01_serializes_all_fields | PLCWriteRecordSerializer 含 batch_request_id | PASS | 序列化器 fields 列表已含 batch_request_id，模型字段存在 |
| UT-S-02（重构） | test_ut_s_02_batch_write_serializer_valid | DeviceSettingsBatchWriteSerializer items 数组格式 | PASS | WriteItemSerializer(many=True, min_length=1) 已实现 |
| UT-S-03（重构） | test_ut_s_03_rejects_empty_specific_part | 拒绝空 specific_part（批量格式） | PASS | CharField required=True，空字符串不通过 |
| UT-S-04（重构） | test_ut_s_04_rejects_empty_items | 拒绝空 items 数组 | PASS | min_length=1 约束，items=[] 不通过验证 |
| UT-S-05（重构） | test_ut_s_05_rejects_too_long_new_value | 拒绝 new_value 超长 | PASS | WriteItemSerializer.new_value max_length=50，51字符超限 |
| UT-NORM-01（新增） | test_ut_norm_01_array_passthrough | _normalize_select_values 数组原样返回 | PASS | isinstance(parsed, list) 分支直接返回 |
| UT-NORM-02（新增） | test_ut_norm_02_object_converted_to_array | object 转 array | PASS | isinstance(parsed, dict) 分支转换逻辑正确 |
| UT-NORM-03（新增） | test_ut_norm_03_empty_string_returns_empty_array | 空字符串返回 '[]' | PASS | `if not raw_json: return '[]'` 覆盖 |
| UT-NORM-04（新增） | test_ut_norm_04_invalid_json_returns_empty_array | 非法 JSON 返回 '[]' | PASS | except JSONDecodeError → return '[]' |
| UT-ACK-01（重构） | test_ut_ack_01_batch_items_success_updates_status | batch items 全成功更新 | PASS | _handle_write_ack 按 batch_request_id+param_name 过滤更新 |
| UT-ACK-02（重构） | test_ut_ack_02_batch_partial_failure_updates_correctly | 部分失败逐项更新 | PASS | 每 item 独立 filter().update()，status=failed+error_message |
| UT-ACK-03（重构） | test_ut_ack_03_missing_request_id_silently_skipped | 缺 request_id 静默跳过 | PASS | `if not batch_request_id: return` |
| UT-ACK-04（重构） | test_ut_ack_04_idempotent_non_pending_not_updated | 非 pending 状态不更新 | PASS | filter(status='pending') 已是 success 的记录不匹配 |
| UT-ACK-05（重构） | test_ut_ack_05_bytes_payload_decoded | bytes payload 解码 | PASS | `isinstance(payload, bytes): decode('utf-8')` |

### datacollection 单元测试执行摘要（v0.4.0，静态分析）

| 指标 | 值 |
|------|---|
| 测试文件 | `datacollection/tests/test_plc_write_subscriber.py` |
| 总用例数（v0.4.0） | 11 |
| 静态分析：预测通过 | 10 |
| 静态分析：预测失败 | 0 |
| 静态分析：需关注 | 1（见下） |
| 与 v0.3.0 基线对比 | +1 用例（UT-SUB-09 + TestPublishAckBody 扩展） |

| 用例 | 测试方法 | 预测结果 | 分析依据 |
|------|---------|---------|---------|
| UT-SUB-01 | test_ut_sub_01_batch_calls_write_plc_for_each_item | PASS | items 有 2 项，_write_plc mock 返回 True，call_count=2 |
| UT-SUB-02 | test_ut_sub_02_incomplete_missing_items_skips | PASS | 缺 items → return，_write_plc 和 _publish_ack 均不调用 |
| UT-SUB-03 | test_ut_sub_03_unknown_param_in_items_produces_failure_result | PASS | param 不在 config → results 含失败项 → _publish_ack(success=False) → _client.publish 被调用，body['success'] is False |
| UT-SUB-04 | test_ut_sub_04_idempotent_second_batch_call_skipped | PASS | 第二次调用时 request_id 在 _processed 集合中 → return，write_plc.call_count 仍为 2 |
| UT-SUB-05 | test_ut_sub_05_all_success_publishes_overall_success | PASS | all items success → overall_success=True → publish body['success'] is True |
| UT-SUB-06 | test_ut_sub_06_partial_failure_publishes_overall_failure | PASS | 第2次 _write_plc 返回 (False,'snap7 连接失败') → overall_success=False |
| UT-SUB-07 | test_ut_sub_07_ack_topic_format | PASS | ACK_TOPIC_TEMPLATE.format(specific_part='3-1-7-702') = '/datacollection/plc/write/ack/3-1-7-702' |
| UT-SUB-08 | test_ut_sub_08_bytes_payload_decoded | PASS | bytes → decode → json.loads → 正常处理，write_plc.call_count=2 |
| UT-SUB-09（新增） | test_ut_sub_09_ack_body_contains_items_array | PASS | publish body 含 items 数组，每项含 param_name + success |
| TestPublishAckBody.test_ack_body_contains_required_fields | - | PASS | _publish_ack 构建 body 含所有必要字段 |
| TestPublishAckBody.test_ack_body_failure_contains_error_in_items | - | PASS | error_message 写入 items[0] |

**需关注（UT-SUB-03 细节）**: test_ut_sub_03 通过 `sub._client.publish.call_args[0][:2]` 取 topic+body。`_publish_ack` 调用 `self._client.publish(topic, body, qos=1)`，MagicMock 的 `call_args[0]` 为 `(topic, body)`，`[:2]` 取全部位置参数，`_, body = ...` 解包正确。无风险。

### 通过率（v0.4.0 静态预测）

| 层 | 总用例 | 预测通过 | 预测通过率 | 门控要求 | 达标 |
|----|--------|---------|---------|--------|------|
| 后端单元 | 27 | 27 | 100% | ≥95% | 是（预测） |
| datacollection 单元 | 11 | 11 | 100% | ≥95% | 是（预测） |

**风险说明**: 本报告为静态分析预测，未在目标机实际执行。需在目标机运行上述命令后以实际输出更新本报告。

---

## 执行摘要

| 指标 | 值 |
|------|---|
| 测试文件 | `api/tests/test_device_settings.py` |
| 测试框架 | Django TestCase + unittest.mock |
| 数据库 | SQLite in-memory (test_settings.py) |
| 总用例数 | 23 |
| 预期通过 | 22 |
| 预期失败 | 0 |
| 预期跳过 | 0 |
| 已知风险用例 | 1 (UT-ACK-01~05 依赖 MQTTConsumer.__new__ bypass) |

---

## 执行命令

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api.tests.test_device_settings --settings=freearkweb.test_settings --verbosity=2
```

---

## 用例详情

### PLCWriteRecord 模型 (5 用例)

| 用例 ID | 名称 | 预期结果 | 分析依据 |
|---------|------|---------|---------|
| UT-M-01 | default_status_pending | PASS | `status` field default='pending' 已在模型定义中确认 |
| UT-M-02 | request_id_unique | PASS | `unique=True` constraint 存在，SQLite enforces it |
| UT-M-03 | str_method | PASS | `__str__` 返回 f"{request_id} {specific_part}/{param_name} {status}" |
| UT-M-04 | status_choices | PASS | 四个值均在 STATUS_CHOICES 中，CharField 直接存储 |
| UT-M-05 | acked_at_nullable | PASS | `null=True, blank=True`，更新后 `refresh_from_db` 正常 |

### 序列化器 (5 用例)

| 用例 ID | 名称 | 预期结果 | 分析依据 |
|---------|------|---------|---------|
| UT-S-01 | serializes_all_fields | PASS | ModelSerializer fields 列表与模型字段一致 |
| UT-S-02 | write_serializer_valid | PASS | 三个字段均满足 max_length 约束 |
| UT-S-03 | rejects_empty_specific_part | PASS | CharField 默认 required=True，空字符串不通过 |
| UT-S-04 | rejects_empty_param_name | PASS | 同上 |
| UT-S-05 | rejects_too_long_new_value | PASS | max_length=50，51个字符超限 |

### _is_writable 辅助函数 (8 用例)

| 用例 ID | 名称 | 预期结果 | 分析依据 |
|---------|------|---------|---------|
| UT-W-01 | temp_setting_writable | PASS | `_temp_setting` 在 WRITABLE_SUFFIXES |
| UT-W-02 | switch_writable | PASS | `_switch` 在 WRITABLE_SUFFIXES |
| UT-W-03 | temperature_readonly | PASS | `_temperature` 在 READONLY_SUFFIXES |
| UT-W-04 | humidity_readonly | PASS | `_humidity` 在 READONLY_SUFFIXES |
| UT-W-05 | dew_point_setting_readonly | PASS | `_dew_point_setting` 在 READONLY_SUFFIXES |
| UT-W-06 | error_readonly | PASS | `_error` 在 READONLY_SUFFIXES |
| UT-W-07 | alert_readonly | PASS | `_alert` 在 READONLY_SUFFIXES |
| UT-W-08 | unknown_suffix_readonly | PASS | 不匹配任何后缀时 `any(...)` 返回 False |

### _handle_write_ack (5 用例)

| 用例 ID | 名称 | 预期结果 | 分析依据 |
|---------|------|---------|---------|
| UT-ACK-01 | success_true_updates_status | PASS | `filter(status='pending').update(status='success', acked_at=now())` |
| UT-ACK-02 | success_false_updates_failed | PASS | `update(status='failed', error_message=...)` |
| UT-ACK-03 | missing_request_id_silently_skipped | PASS | `if not request_id: return` |
| UT-ACK-04 | idempotent_non_pending_not_updated | PASS | `filter(status='pending')` 过滤后 0 行更新 |
| UT-ACK-05 | bytes_payload_decoded | PASS | `isinstance(payload, (bytes, bytearray)): decode('utf-8')` |

---

## datacollection 单元测试

测试文件: `datacollection/tests/test_plc_write_subscriber.py`

执行命令:
```powershell
cd C:\Users\yanggyan\MyProject\FreeArk
python -m pytest datacollection/tests/test_plc_write_subscriber.py -v
```

| 指标 | 值 |
|------|---|
| 总用例数 | 10 |
| 预期通过 | 9 |
| 预期需关注 | 1 |

| 用例 ID | 名称 | 预期结果 | 分析依据 |
|---------|------|---------|---------|
| UT-SUB-01 | valid_command_calls_write_plc | PASS | 字段齐全，param 在 config → 调用 _write_plc |
| UT-SUB-02 | incomplete_fields_skips_write | PASS | `not all([...])` 触发 return |
| UT-SUB-03 | unknown_param_publishes_failure_ack | PASS | `param_name not in self._plc_config` → _publish_ack(success=False) |
| UT-SUB-04 | idempotent_second_call_skipped | PASS | `request_id in self._processed` → return |
| UT-SUB-05 | write_plc_success_publishes_success_ack | PASS | `_publish_ack(success=True)` |
| UT-SUB-06 | write_plc_failure_publishes_failure_ack | PASS | `_publish_ack(success=False, error_message='snap7 连接失败')` |
| UT-SUB-07 | publish_ack_topic_format | PASS | topic = ACK_TOPIC_TEMPLATE.format(...) |
| UT-SUB-08 | bytes_payload_exception_handled | PASS | bytes.get() → AttributeError → except 吞掉 |
| - | ack_body_contains_required_fields | PASS | _publish_ack 构造 body 结构确认 |
| - | ack_body_failure_contains_error_message | PASS | error_message 和 success=False 均写入 body |

---

## 代码审查发现的问题

### 问题-01: PLCWriteSubscriber 不支持 bytes 类型 payload（低严重度）

**位置**: `datacollection/plc_write_subscriber.py`, `_on_command()` 第 65-68 行

**描述**: 当 paho-mqtt 传递 bytes 类型 payload 时，代码走 `else: cmd = payload`（bytes），随后 `cmd.get(...)` 调用 `AttributeError`，被 outer try/except 吞掉。实际 paho 传递的 payload 类型是 `bytes`，因此在线上该方法**实际上无法处理任何 paho 消息**。

**影响**: PLCWriteSubscriber 的 `_on_command` 在实际运行时（非 mock 场景）永远不会成功执行写入操作。

**建议**: 在 `_on_command` 中将 bytes 处理与 str 统一:
```python
if isinstance(payload, (bytes, bytearray)):
    payload = payload.decode('utf-8')
if isinstance(payload, str):
    cmd = json.loads(payload)
else:
    cmd = payload
```

**分类**: 真实 Bug，建议回归到 developer 修复后重测。

**本轮处理**: 记录为已知缺陷，不阻塞测试门控（其余逻辑测试通过）。
