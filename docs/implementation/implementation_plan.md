# 实现计划

**文档编号**: IMPL-PLAN-DEVICE-SETTINGS-001
**项目名称**: FreeArk 设备参数设置功能
**版本**: 1.0.0
**状态**: COMPLETED
**日期**: 2026-05-19
**作者**: software-developer (via pm-orchestrator)

---

## 实现顺序与各步骤完成状态

| 步骤 | 内容 | 文件 | 状态 |
|------|------|------|------|
| 1 | DB Migration — PLCWriteRecord 模型 | `api/models.py` + `migrations/0023_plcwriterecord.py` | DONE |
| 2 | Serializers | `api/serializers_device_settings.py` | DONE |
| 3 | Backend Views | `api/views_device_settings.py` | DONE |
| 4 | URL 注册 | `api/urls.py` | DONE |
| 5 | MQTT consumer 追加 ack 订阅 + 处理 | `api/mqtt_consumer.py` | DONE |
| 6 | PLCWriteSubscriber | `datacollection/plc_write_subscriber.py` | DONE |
| 7 | 集成到 ImprovedDataCollectionManager | `datacollection/improved_data_collection_manager.py` | DONE |
| 8 | frontend mqtt 依赖 | `frontend/package.json` | DONE |
| 9 | useMqttWebSocket composable | `frontend/src/composables/useMqttWebSocket.js` | DONE |
| 10 | DeviceManagementDeviceListView 添加"设置"按钮 | `frontend/src/views/DeviceManagementDeviceListView.vue` | DONE |
| 11 | DeviceSettingsPanelView 新增 | `frontend/src/views/DeviceSettingsPanelView.vue` | DONE |
| 12 | PlcWriteRecordView 新增（只读） | `frontend/src/views/PlcWriteRecordView.vue` | DONE |
| 13 | Router 注册 PlcWriteRecordView | `frontend/src/router/index.js` | DONE |

## 本期明确不实现

- 回滚接口（`POST /api/device-settings/rollback/`）— 延后至下期
- 审计日志页面"回滚"按钮 — 延后至下期

---

## v0.4.0 增量实现（2026-05-19，P1~P5 + D1~D3）

| 步骤 | 内容 | 文件 | 状态 |
|------|------|------|------|
| 1 | D1: Migration 0024 — PLCWriteRecord 追加 batch_request_id | `api/migrations/0024_plcwriterecord_batch_request_id.py` + `api/models.py` | DONE |
| 2 | P3: param_value_label 常量文件 | `api/param_value_label.py` | DONE |
| 3 | P3+P4+P5+P2: views_device_settings 重写 | `api/views_device_settings.py` | DONE |
| 4 | P4: serializers 改为批量 schema | `api/serializers_device_settings.py` | DONE |
| 5 | P4: mqtt_consumer _handle_write_ack 适配 items 数组 | `api/mqtt_consumer.py` | DONE |
| 6 | P4+P2: plc_write_subscriber 批量 items 处理 + 诊断日志 | `datacollection/plc_write_subscriber.py` | DONE |
| 7 | P3+P4+P5+D3: DeviceSettingsPanelView 重写（批量提交 + value_options + timeout 文案）| `frontend/src/views/DeviceSettingsPanelView.vue` | DONE |
| 8 | Q12: PlcWriteRecordView 追加 raw(label) 格式展示 | `frontend/src/views/PlcWriteRecordView.vue` | DONE |
| 9 | 架构补录用户最终决策 D1~D3 | `docs/architecture/architecture_design.md` | DONE |
| 10 | 测试更新（匹配新协议，不运行）| `tests/test_device_settings*.py` + `datacollection/tests/test_plc_write_subscriber.py` | DONE |

### v0.4.0 明确不实现

- 后端服务端定时 pending→timeout 扫描（D3 决策：仅前端 30s 超时推断）
- API 旧单字段接口兼容层（D2 决策：不做兼容，同步部署）
