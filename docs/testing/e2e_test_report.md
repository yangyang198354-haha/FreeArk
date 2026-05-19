# E2E 测试报告

**文档编号**: TEST-E2E-DEVICE-SETTINGS-001
**项目名称**: FreeArk 设备参数设置功能
**版本**: 0.3.0 → 0.4.0
**状态**: REVIEWED — 待实际执行确认
**创建日期**: 2026-05-19
**作者**: test-engineer (via pm-orchestrator)

---

## v0.4.0 E2E 测试追加段（2026-05-19）

**执行方式**: 深度静态分析（目标机实际执行命令见下方）

**执行命令（须在目标机手动执行）**:
```powershell
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api.tests.test_device_settings_e2e --settings=freearkweb.test_settings --verbosity=2
```

### v0.4.0 E2E 测试执行摘要（静态分析）

| 指标 | 值 |
|------|---|
| 测试文件 | `api/tests/test_device_settings_e2e.py` |
| 总用例数（v0.4.0） | 4 |
| 静态分析：预测通过 | 4 |
| 静态分析：预测失败 | 0 |
| 与 v0.3.0 基线对比 | 用例数不变，全部重构为批量协议（batch_request_id + items）|

### v0.4.0 E2E 用例详情

| 用例 ID | 测试类 | 覆盖路径 | 预测结果 | 分析依据 |
|---------|-------|---------|---------|---------|
| E2E-01 | E2EHappyPathTest | POST batch write → pending → ack items(success=True) → success | PASS | _handle_write_ack 按 batch_request_id+param_name 更新；acked_at 填充 |
| E2E-02 | E2EPLCWriteFailTest | POST batch write → pending → ack items(success=False) → failed | PASS | item success=False → status='failed', error_message='PLC 写入超时' |
| E2E-03 | E2EMQTTUnreachableTest | MQTT publish 异常 → 503, status=failed | PASS | ConnectionError → except → PLCWriteRecord.status='failed', error_message='MQTT broker 不可达' |
| E2E-04 | E2EIdempotentAckTest | 同 batch_request_id ack 两次 → 状态只更新一次 | PASS | 第二次 filter(status='pending') 匹配 0 行，acked_at 不变 |

**关键协议变更验证**: E2E-01/02 均使用 `batch_request_id` + `items` 数组格式的 ack payload，与 `_handle_write_ack` 的批量分支（`if items and isinstance(items, list)`）完全匹配。

### 通过率（v0.4.0 静态预测）

| 总用例 | 预测通过 | 预测通过率 | 门控要求 | 达标 |
|--------|---------|---------|--------|------|
| 4 | 4 | 100% | 100% | 是（预测） |

**风险说明**: 本报告为静态分析预测，未在目标机实际执行。需在目标机运行上述命令后以实际输出更新本报告。

---

## 执行摘要

| 指标 | 值 |
|------|---|
| 测试文件 | `api/tests/test_device_settings_e2e.py` |
| 测试框架 | Django TestCase + mock MQTT + mock snap7 |
| 覆盖路径 | 写入成功 / PLC失败 / MQTT不可达 / 幂等回执 |
| 总用例数 | 4 |
| 预期通过 | 4 |
| 预期失败 | 0 |

---

## 执行命令

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api.tests.test_device_settings_e2e --settings=freearkweb.test_settings --verbosity=2
```

---

## 用例详情

| 用例 ID | 名称 | 路径 | 预期结果 | 分析依据 |
|---------|------|------|---------|---------|
| E2E-01 | write_then_ack_success | POST write → pending → ack(success=True) → success | PASS | view 创建 pending 记录；_handle_write_ack 更新 status='success' |
| E2E-02 | ack_failure_marks_record_failed | POST write → pending → ack(success=False) → failed | PASS | _handle_write_ack 更新 status='failed', error_message='PLC 写入超时' |
| E2E-03 | mqtt_publish_exception_503 | MQTT publish 异常 → 503, status=failed | PASS | 异常被 except 捕获，PLCWriteRecord 更新 failed，返回 503 |
| E2E-04 | duplicate_ack_idempotent | 同 request_id ack 两次 → 仅第一次生效 | PASS | filter(status='pending') 第二次匹配0行，acked_at 不变 |

---

## 超时路径说明

30s 超时路径（前端 `setTimeout`）在 E2E 层属于前端行为，后端无对应状态机切换为 `timeout`；`timeout` 状态由运维脚本/定时任务写入（本期 DEFERRED）。故 E2E 测试中不覆盖 `timeout` 状态更新。

---

## 前端测试说明

**状态: SKIPPED — 环境缺失**

`FreeArkWeb/frontend/package.json` 中缺少以下依赖：
- `vitest`
- `@vue/test-utils`
- `@vitejs/plugin-vue` 已存在（可扩展）

**影响范围**: `DeviceSettingsPanelView.vue`、`useMqttWebSocket.js`、`PlcWriteRecordView.vue` 的组件单元测试无法在当前环境执行。

**建议**: 在 `devDependencies` 中添加 `vitest` 和 `@vue/test-utils`，后续迭代补充前端测试覆盖。此缺失不影响后端门控通过。
