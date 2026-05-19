# 测试计划

**文档编号**: TEST-PLAN-DEVICE-SETTINGS-001
**项目名称**: FreeArk 设备参数设置功能
**版本**: 0.3.0
**状态**: APPROVED
**创建日期**: 2026-05-19
**作者**: test-engineer (via pm-orchestrator)

---

## 1. 测试范围

本轮测试覆盖 v0.3.0-APPROVED 需求/架构/实现文档所定义的"设备参数设置"功能，包含以下新增/修改文件：

**新增**:
- `FreeArkWeb/backend/freearkweb/api/migrations/0023_plcwriterecord.py`
- `FreeArkWeb/backend/freearkweb/api/serializers_device_settings.py`
- `FreeArkWeb/backend/freearkweb/api/views_device_settings.py`
- `datacollection/plc_write_subscriber.py`
- `FreeArkWeb/frontend/src/composables/useMqttWebSocket.js`
- `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue`
- `FreeArkWeb/frontend/src/views/PlcWriteRecordView.vue`

**修改**:
- `FreeArkWeb/backend/freearkweb/api/models.py` (PLCWriteRecord 模型)
- `FreeArkWeb/backend/freearkweb/api/urls.py` (3 个新路由)
- `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` (_handle_write_ack)
- `datacollection/improved_data_collection_manager.py`

---

## 2. 基础设施约束

- 测试数据库: SQLite in-memory（`test_settings.py` 强制配置，禁止连接 192.168.31.98:3306）
- 禁止 Docker / docker-compose
- 禁止测试中连接真实 PLC / 真实 MQTT broker
- 禁止硬编码生产 IP（所有外部依赖通过 mock/fixture 替代）
- 运行环境: Windows 11 + Python 3.10+ + SQLite

---

## 3. 单元测试计划

测试文件: `FreeArkWeb/backend/freearkweb/api/tests/test_device_settings.py`

### 3.1 PLCWriteRecord 模型

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| UT-M-01 | 创建 PLCWriteRecord，默认 status=pending | status 字段默认值正确 |
| UT-M-02 | request_id 唯一约束 | 重复 request_id 抛 IntegrityError |
| UT-M-03 | __str__ 方法 | 包含 request_id / specific_part / param_name / status |
| UT-M-04 | status 选项枚举（pending/success/failed/timeout） | 四个值都可存储 |
| UT-M-05 | acked_at 默认 null，可更新 | nullable 字段行为正确 |

### 3.2 序列化器

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| UT-S-01 | PLCWriteRecordSerializer 序列化有效模型 | 所有必要字段存在 |
| UT-S-02 | DeviceSettingWriteSerializer 验证有效数据 | is_valid() = True |
| UT-S-03 | DeviceSettingWriteSerializer 拒绝空 specific_part | is_valid() = False |
| UT-S-04 | DeviceSettingWriteSerializer 拒绝空 param_name | is_valid() = False |
| UT-S-05 | DeviceSettingWriteSerializer 拒绝超长 new_value (>50) | is_valid() = False |

### 3.3 _is_writable 辅助函数

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| UT-W-01 | *_temp_setting 后缀 → writable=True | True |
| UT-W-02 | *_switch 后缀 → writable=True | True |
| UT-W-03 | *_temperature 后缀 → writable=False | False |
| UT-W-04 | *_humidity 后缀 → writable=False | False |
| UT-W-05 | *_dew_point_setting 后缀 → writable=False | False |
| UT-W-06 | *_error 后缀 → writable=False | False |
| UT-W-07 | *_alert 后缀 → writable=False | False |
| UT-W-08 | 未知后缀 → writable=False | False |

### 3.4 mqtt_consumer._handle_write_ack

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| UT-ACK-01 | success=True：PLCWriteRecord.status 更新为 success，acked_at 填充 | status='success' |
| UT-ACK-02 | success=False：PLCWriteRecord.status 更新为 failed，error_message 写入 | status='failed' |
| UT-ACK-03 | 缺失 request_id：静默跳过，不更新 DB | DB 记录未变化 |
| UT-ACK-04 | 幂等性：status 非 pending 时，再次 ack 不更新 | 仍为原 status |
| UT-ACK-05 | bytes 类型 payload 自动解码 | 解码成功，正常处理 |

### 3.5 PLCWriteSubscriber（datacollection）

测试文件: `datacollection/tests/test_plc_write_subscriber.py`

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| UT-SUB-01 | _on_command 正常路径: param 在 plc_config → 调用 _write_plc | _write_plc 被调用一次 |
| UT-SUB-02 | _on_command 字段不完整 → 跳过，不调用 _write_plc | _write_plc 未被调用 |
| UT-SUB-03 | param_name 不在 plc_config → 发布失败回执 | _publish_ack(success=False) |
| UT-SUB-04 | 幂等性：同一 request_id 第二次调用跳过 | _write_plc 只调用一次 |
| UT-SUB-05 | _write_plc snap7 成功 → _publish_ack(success=True) | ack 发布 success=True |
| UT-SUB-06 | _write_plc snap7 失败 → _publish_ack(success=False, error_message) | ack 发布 success=False |
| UT-SUB-07 | _publish_ack 构建正确 topic 格式 | topic = ack/{specific_part} |
| UT-SUB-08 | bytes 类型 payload → 自动解析为 dict | 正常处理 |

---

## 4. 集成测试计划

测试文件: `FreeArkWeb/backend/freearkweb/api/tests/test_device_settings_integration.py`

所有测试走真实 Django ORM + SQLite，DRF 真实路由，mock 仅限外部依赖（MQTT client）。

### 4.1 GET /api/device-settings/params/{specific_part}/

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| IT-PARAMS-01 | 有效 specific_part，有 DeviceConfig + PLCLatestData → 返回分组结果 | HTTP 200，groups 非空 |
| IT-PARAMS-02 | 无对应 PLCLatestData → current_value=None，不报错 | HTTP 200，current_value null |
| IT-PARAMS-03 | is_writable 字段正确（_temp_setting=True, _temperature=False） | 字段值与预期一致 |
| IT-PARAMS-04 | 未认证请求 → 401 | HTTP 401 |
| IT-PARAMS-05 | is_active=False 的 DeviceConfig 不出现在响应 | 响应不含 inactive 参数 |
| IT-PARAMS-06 | DeviceAttrDef 关联正确（attr_value_type/num_value_json/select_values_json） | 关联字段存在 |

### 4.2 POST /api/device-settings/write/

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| IT-WRITE-01 | 合法请求（可写参数）→ 202，PLCWriteRecord 创建，MQTT publish 被调用 | status=202，DB 有记录 |
| IT-WRITE-02 | param_name 为只读后缀 → 400 | HTTP 400 |
| IT-WRITE-03 | specific_part 无对应 OwnerInfo → 404 | HTTP 404 |
| IT-WRITE-04 | 序列化器验证失败（缺字段）→ 400 | HTTP 400 |
| IT-WRITE-05 | MQTT publish 失败 → 503，PLCWriteRecord.status=failed | HTTP 503，status=failed |
| IT-WRITE-06 | 未认证请求 → 401 | HTTP 401 |

### 4.3 GET /api/device-settings/records/

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| IT-RECORDS-01 | 无过滤 → 返回全部记录（分页） | HTTP 200，count 正确 |
| IT-RECORDS-02 | specific_part 过滤 | 仅返回对应记录 |
| IT-RECORDS-03 | status 过滤 | 仅返回对应 status 记录 |
| IT-RECORDS-04 | operator 过滤 | 仅返回对应操作人记录 |
| IT-RECORDS-05 | start_time / end_time 过滤 | 时间范围过滤正确 |
| IT-RECORDS-06 | 分页：page_size 参数有效 | 返回对应数量 |
| IT-RECORDS-07 | 未认证请求 → 401 | HTTP 401 |

---

## 5. E2E 测试计划

测试文件: `FreeArkWeb/backend/freearkweb/api/tests/test_device_settings_e2e.py`

E2E 测试通过 Django TestCase + in-process mock MQTT（不启动真实 broker）+ mock snap7 模拟完整链路。

### 5.1 Happy Path（写入成功）

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| E2E-01 | POST write → PLCWriteRecord pending → 模拟 ack(success=True) → status=success | DB status='success'，acked_at 非空 |

### 5.2 PLC 写失败路径

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| E2E-02 | POST write → 模拟 ack(success=False, error_message) → status=failed | DB status='failed'，error_message 写入 |

### 5.3 MQTT 不可达路径

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| E2E-03 | MQTT publish 异常 → 503 响应，PLCWriteRecord.status=failed | HTTP 503，DB status='failed' |

### 5.4 幂等回执路径

| 用例 ID | 描述 | 断言 |
|---------|------|------|
| E2E-04 | 同一 request_id ack 两次 → 状态只更新一次，第二次无副作用 | DB 记录唯一，acked_at 为首次时间 |

---

## 6. 前端测试计划

前端暂无 Vitest 配置（package.json 中无测试脚本，devDependencies 无 @vue/test-utils/vitest）。

**本轮前端测试策略**: 记录缺失，补充 vitest + @vue/test-utils 依赖后可扩展，当前前端测试标记为 SKIPPED（环境缺失），不影响后端门控。

---

## 7. 通过率门控

| 层级 | 目标通过率 | 本轮要求 |
|------|----------|---------|
| 单元测试 | ≥ 95% | 硬性要求 |
| 集成测试 | ≥ 90% | 硬性要求 |
| E2E 测试 | 100% | 全部通过 |
| 前端测试 | — | SKIPPED（环境缺失） |

---

## 8. 测试执行命令

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb

# 单元测试（含集成测试、E2E 测试，全量执行）
python manage.py test api.tests.test_device_settings api.tests.test_device_settings_integration api.tests.test_device_settings_e2e --settings=freearkweb.test_settings --verbosity=2

# datacollection 单元测试（独立 pytest，不依赖 Django ORM）
cd C:\Users\yanggyan\MyProject\FreeArk
python -m pytest datacollection/tests/test_plc_write_subscriber.py -v
```

---

## v0.4.0 测试覆盖矩阵追加（2026-05-19）

**版本**: 0.4.0
**变更范围**: 批量写入协议（P4 batch）、normalize select values（P1）、P2/P3/P5 加固

### 变更对比（v0.3.0 → v0.4.0）

| 维度 | v0.3.0 | v0.4.0 |
|------|--------|--------|
| 写入协议 | 单条 `DeviceSettingWriteSerializer` | 批量 `DeviceSettingsBatchWriteSerializer`（items 数组） |
| PLCWriteRecord | 无 batch_request_id | 新增 `batch_request_id` 字段（migration 0024） |
| ack 格式 | 单字段 `request_id` 匹配 | `batch_request_id` + `items[].param_name` 逐项匹配 |
| `_on_command` | 单条 write | 批量 items 循环写 PLC |
| `_normalize_select_values` | 无 | 新增（P1：object→array 规范化） |
| `device_settings_params` GET | 无 P5 过滤 | P5：后端过滤只读参数；P3：display_value/value_options |
| `device_settings_write` POST | 单条 | 批量，返回 batch_request_id + item_count |

### 新增 / 修改测试用例与 P1~P5/D1~D3 映射

| 测试文件 | 用例 ID | 覆盖功能点 | 映射需求 |
|---------|---------|---------|--------|
| test_device_settings.py | UT-S-01 | `batch_request_id` 在序列化字段中 | P4 批量 |
| test_device_settings.py | UT-S-02 | `DeviceSettingsBatchWriteSerializer` 批量格式验证 | P4 批量 |
| test_device_settings.py | UT-S-03 | 拒绝空 specific_part（批量格式） | P4 |
| test_device_settings.py | UT-S-04 | 拒绝空 items 数组 | P4 |
| test_device_settings.py | UT-S-05 | 拒绝 new_value 超长（批量 item） | P4 |
| test_device_settings.py | UT-NORM-01~04 | `_normalize_select_values` 四种输入格式 | P1 |
| test_device_settings.py | UT-ACK-01 | batch items 全成功更新 | P4 batch ack |
| test_device_settings.py | UT-ACK-02 | batch 部分失败逐项更新 | P4 batch ack |
| test_device_settings.py | UT-ACK-03~05 | missing request_id / 幂等 / bytes | P4 |
| test_device_settings_integration.py | IT-PARAMS-03 | P5 只读参数后端过滤 | P5 |
| test_device_settings_integration.py | IT-PARAMS-06 | attr_def 字段含 value_options/display_value | P3 |
| test_device_settings_integration.py | IT-PARAMS-07 | switch value_options 数组 | P3 |
| test_device_settings_integration.py | IT-PARAMS-08 | select_values_json object 规范化为 array | P1 |
| test_device_settings_integration.py | IT-WRITE-01 | 批量 POST 202，batch_request_id，item_count | P4 |
| test_device_settings_integration.py | IT-WRITE-04b | 空 items 返回 400 | P4 |
| test_device_settings_integration.py | GetRecordsTests | batch_request_id 字段在记录中 | P4 |
| test_device_settings_e2e.py | E2E-01~04 | 批量 ack 协议完整链路 | P4 |
| test_plc_write_subscriber.py | UT-SUB-01 | batch items 循环 write_plc | D1 datacollection |
| test_plc_write_subscriber.py | UT-SUB-03 | unknown param → items 中失败结果 | D1 |
| test_plc_write_subscriber.py | UT-SUB-05~06 | 全成功/部分失败 overall_success | D1 |
| test_plc_write_subscriber.py | UT-SUB-07 | ack topic 格式 | D2 |
| test_plc_write_subscriber.py | UT-SUB-09 | ack body 含 items 数组 | D2 |
| test_plc_write_subscriber.py | TestPublishAckBody | _publish_ack body 结构验证 | D2/D3 |

### v0.4.0 用例数量对比

| 测试层 | v0.3.0 | v0.4.0 | 变化 |
|-------|--------|--------|------|
| 后端单元（test_device_settings.py） | 23 | 27 | +4（NORM 系列 + ACK 重构为 batch） |
| 后端集成（integration） | 19 | 22 | +3（PARAMS-07/08 + WRITE-04b） |
| 后端 E2E | 4 | 4 | 不变（协议更新，用例维持） |
| datacollection（plc_write_subscriber） | 10 | 11 | +1（UT-SUB-09） |
| **合计** | **56** | **64** | **+8** |

### 通过率门控（v0.4.0，维持不变）

| 层级 | 目标通过率 | v0.4.0 要求 |
|------|----------|------------|
| 单元测试 | ≥ 95% | 硬性要求 |
| 集成测试 | ≥ 90% | 硬性要求 |
| E2E 测试 | 100% | 全部通过 |
| 前端测试 | — | SKIPPED（环境缺失，不阻塞门控） |
