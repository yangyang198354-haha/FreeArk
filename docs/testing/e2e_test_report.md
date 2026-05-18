# E2E 测试报告

**文档编号**: TEST-E2E-DEVICE-SETTINGS-001
**项目名称**: FreeArk 设备参数设置功能
**版本**: 0.3.0
**状态**: REVIEWED — 待实际执行确认
**创建日期**: 2026-05-19
**作者**: test-engineer (via pm-orchestrator)

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
