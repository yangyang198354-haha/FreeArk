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

---

## v0.4.1 hotfix（2026-05-19）— MQTT broker 错配 + 前端吞错文案

### 故障证据摘要

| 证据 | 内容 |
|------|------|
| D1 | dist 已含 `batch_request_id`，`index.html` mtime May 19，新版已生效，排除缓存问题 |
| D2 | PLCWriteRecord 近 30 分钟 20 条记录全 `status=failed`，`error_message='MQTT broker 不可达'`，`specific_part=3-1-7-702` |
| D3 | backend log 近 10 分钟为空（APP_LOG_LEVEL=ERROR 屏蔽 INFO；publish 异常被 try/except 捕获后只入 DB 不出 log） |
| D4 | task-scheduler log 无任何"收到写命令"痕迹，PLCWriteSubscriber 根本未收到这批命令，broker 不一致根因坐实 |
| D7 | `mqtt_config.json` 不存在；两个 systemd unit 均无 MQTT 环境变量；100% 走代码 fallback |
| nginx | `POST /api/device-settings/write/` 返回 503，body 48 字节，确认请求已到达后端 |

### Bug A（后端，根因）

**文件**: `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py`

`MQTTConsumer.__init__` 中 MQTT broker 默认 fallback：
- 修复前：`host='192.168.31.97'`，`port=32795`（不存在的 broker）
- 修复后：`host='192.168.31.98'`，`port=32788`（与 PLCWriteSubscriber 生产 broker 一致）

生产环境无配置文件、无环境变量，必然走 fallback，错误 fallback 导致 publish 连接失败，后端记 `error_message='MQTT broker 不可达'` 并返回 503。

附加：`views_device_settings._check_broker_config_consistency` 的 warning 描述文字同步更新，说明正确目标值（192.168.31.98:32788）。

### Bug B（前端，吞错文案）

**文件**: `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue`

`handleBatchSubmit` catch 块原逻辑：
```javascript
batchError.value = e?.response?.data?.error || '下发通道异常'
```
`api.js` 使用原生 fetch，抛出普通 `Error` 对象，无 `.response.data` 结构，永远 fallback 到 `'下发通道异常'`，掩盖真实原因。

修复后逻辑（方案 1）：
```javascript
const rawMsg = e?.message || ''
const sepIdx = rawMsg.indexOf(' - ')
batchError.value = sepIdx !== -1 ? rawMsg.slice(sepIdx + 3) : '未知失败原因，请查看后端日志'
```

`api.js` `post` 方法抛出 Error.message 格式：`"API请求失败: <status> <statusText> - <backend error>"`

修复后前端展示文案示例：
1. 503 + body `{"error":"下发通道异常，请稍后重试"}` → 显示：**"下发通道异常，请稍后重试"**
2. 401 (认证失败，api.js 专有逻辑) → message 无 ` - ` 分隔符 → 显示：**"未知失败原因，请查看后端日志"**

### 变更范围

| 文件 | 变更内容 |
|------|---------|
| `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | Bug A：fallback broker 从 `192.168.31.97:32795` 改为 `192.168.31.98:32788` |
| `FreeArkWeb/backend/freearkweb/api/views_device_settings.py` | Bug A 附带：`_check_broker_config_consistency` warning 描述补全正确目标值 |
| `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue` | Bug B：catch 文案提取从 `e?.response?.data?.error` 改为 `e?.message` 解析 |

测试文件自查：`api/tests/test_device_settings*.py` 中无 broker IP 断言，无需调整。

### 明确不实现（本 hotfix）

- P2 30s timeout 文案细化
- 权限改造
- 其他模块（owner-management、logging、daily-usage）
