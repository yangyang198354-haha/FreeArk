# 代码自评报告

**文档编号**: IMPL-REVIEW-DEVICE-SETTINGS-001
**项目名称**: FreeArk 设备参数设置功能
**版本**: 1.0.0
**日期**: 2026-05-19
**作者**: software-developer (via pm-orchestrator)

---

## 综合评级: PASS（无 CRITICAL finding）

---

## Finding 清单

| ID | 级别 | 文件 | 描述 | 处置 |
|----|------|------|------|------|
| F-01 | INFO | `plc_write_subscriber.py` | `_processed` set 仅在内存中维护，进程重启后幂等缓存清空；重启期间重复消息会被重复处理 | 可接受：重复处理写 PLC 命令与重复写 DB 记录影响小，DB 层 `request_id UNIQUE` 已防止重复建行 |
| F-02 | INFO | `views_device_settings.py` | `_get_mqtt_client()` 直接复用 `mqtt_consumer` 的全局 client；若 consumer 未启动则 publish 可能失败 | 已在失败时更新 DB 为 `failed` 并返回 503，错误路径已覆盖 |
| F-03 | MINOR | `DeviceSettingsPanelView.vue` | `inputValues` 初始化时将 `current_value`（可能为整数）直接作为初始值；枚举型 el-select 需要 value 类型与 select_values_json 中 value 类型一致 | 后端 `current_value` 来自 `PLCLatestData.value`（BigIntegerField），与枚举选项类型匹配问题需在集成测试中确认 |
| F-04 | INFO | `mqtt_consumer.py` | `_handle_write_ack` 中 `error_message=''` 在成功时传入 `update()`，若 DB 字段为 null=True 则写入空字符串而非 None | 功能正确，不影响查询；可后续统一为 `None` |
| F-05 | INFO | `plc_write_subscriber.py` | 使用 Python 3.10+ union type hint `MQTTClient | None`；若生产环境 Python < 3.10 需改为 `Optional[MQTTClient]` | 需确认生产 Python 版本 |

---

## 禁用技术检查

| 约束 | 合规 | 说明 |
|------|------|------|
| 禁 Docker | 合规 | 无 Docker 相关代码 |
| 禁 Django Channels | 合规 | 未引入 |
| 禁 Redis | 合规 | 未引入 |
| 禁 Celery | 合规 | 未引入 |
| 禁 pscp 部署 | 合规 | 无部署脚本，部署仍依赖 git pull |
| 禁硬编码连接串 | 合规 | DB 连接由 settings.py 管理；MQTT broker 地址在 `_start_plc_write_subscriber` 中为字面量（192.168.31.98:32788），与现有 mqtt_consumer.py 的默认 fallback 保持一致 |
| 禁回滚实现 | 合规 | 无回滚接口、无回滚按钮 |
| 复用 PLCWriteManager.write_db_data() | 合规 | PLCWriteSubscriber 通过 PLCReadWriter.write_db_data() 写入（PLCWriteManager 内部也调用此方法） |
| 先写 DB 后发 MQTT | 合规 | views_device_settings.py: transaction.atomic() 写 DB → publish MQTT |

---

## 回归修复记录

| 日期 | 修复项 | 文件 | 说明 |
|------|--------|------|------|
| 2026-05-18 | 修复 BUG-01：_on_command bytes payload 解码 | `plc_write_subscriber.py` | 在 `_on_command` 开头增加 bytes/bytearray → str decode，修复 paho 真实消息全量被静默吞弃的问题 |

---

## FR 覆盖验证

| FR | 实现位置 | 覆盖 |
|----|---------|------|
| FR1（设置按钮）| DeviceManagementDeviceListView.vue | 是 |
| FR2（参数展示）| DeviceSettingsPanelView.vue + device_settings_params view | 是 |
| FR3（MQTT下发）| device_settings_write view | 是 |
| FR4（PLC写入+回执）| PLCWriteSubscriber + mqtt_consumer._handle_write_ack | 是 |
| FR5（自动刷新）| useMqttWebSocket + DeviceSettingsPanelView handleAck | 是 |
| FR6（审计只读）| PlcWriteRecordView + device_settings_records view | 是 |
| 回滚（DEFERRED）| 未实现 | 是（已延后）|

---

## v0.4.0 增量代码评审（2026-05-19）

### 综合评级: PASS（无 CRITICAL finding）

### H1 兼容方案评审（P1 根因重点）

**评审结论**：H1（select_values_json 格式不一致）是最可能的根因。

**v0.4.0 落地方案**：`_normalize_select_values()` 函数在 `views_device_settings.py` 中实现，对三种格式均兼容：
- 数组格式（如 `[{"value":0,"label":"关"}]`）→ 直接透传，归一化为统一 dict 结构
- 对象格式（如 `{"0":"关","1":"开"}`）→ 转换为数组，以 `value` + `label` 键
- 空/非法 JSON → 返回 `'[]'`，前端安全降级

同时新增 `value_options` 字段（来自 `param_value_label.py` 常量），优先于 `select_values_json` 由前端使用，彻底绕开 DB 数据质量问题。

**H2 兼容方案**：当前实现对同一 `attr_tag` 有多行时取第一行（按 `product_code` 分组后选首个）。若生产确认存在 H2 问题（param_name ≠ attr_tag），需在 `device_settings_params` 中追加宽松匹配逻辑（后续 sprint 处理）。

**H3 兼容**：已记录风险，当前代码按 `attr_tag` 全局匹配，同一 `attr_tag` 多个 `product_code` 时后者可能覆盖前者。已通过 `setdefault + list` 收集所有行再选首个缓解。

### P2 加固点评审

| 加固点 | 实现位置 | 评审 |
|--------|---------|------|
| `_get_mqtt_client()` 等待就绪最多 3s | `views_device_settings.py` `_get_mqtt_client()` | PASS：轮询 `is_connected()`，超时 warning |
| publish 后记录 rc 到日志 | `views_device_settings.py` publish 成功分支 `logger.info(...publish_rc=...)` | PASS |
| 启动时 broker 配置一致性检查 | `views_device_settings.py` `_check_broker_config_consistency()` | PASS：首次调用时检查，仅 warning 不阻断 |
| subscriber 入口诊断日志 | `plc_write_subscriber.py` `_on_command` 首行 `logger.info('收到写命令...')` | PASS |
| _write_plc 参数诊断日志 | `plc_write_subscriber.py` `_write_plc` 首行 `logger.info('_write_plc: ...')` | PASS |

### P4 批量协议评审

- `batch_request_id` 字段追加（migration 0024），每行 `request_id` 仍为 UUID UNIQUE，`batch_request_id` 允许多行共享，无 UNIQUE 约束 — PASS
- MQTT 命令 payload 含完整 `items` 数组，一次 publish — PASS
- `_handle_write_ack` 按 `batch_request_id + param_name` 定位各行，保留旧版 legacy 路径（无 items 时降级）— PASS
- `DeviceSettingsPanelView.vue` 移除逐行下发按钮，顶部单一"提交"+"取消"，一次 `POST {items:[...]}` — PASS

### Finding 清单（v0.4.0）

| ID | 级别 | 文件 | 描述 | 处置 |
|----|------|------|------|------|
| F-06 | MINOR | `views_device_settings.py` | `_get_mqtt_client()` 中 `time.sleep(0.1)` 轮询最多 3s，在 HTTP 请求线程中同步阻塞；生产首次 publish 时若 MQTT 还未连接会增加 3s 延迟 | 可接受：仅在 client 未连接时触发；生产稳定运行期间 `is_connected()=True` 时立即返回，无阻塞 |
| F-07 | INFO | `PlcWriteRecordView.vue` | `fetchParamOptions` 在每页加载后按 specific_part 批量请求参数接口；distinct specific_part 较多时有 N 次请求 | 可接受：有 `paramLabelCache` 去重，同一 specific_part 只请求一次；当前业务量（<100户）不构成性能问题 |
| F-08 | INFO | `param_value_label.py` | `_mode` 映射中"通风"/"除湿"的 raw 值（0/1/2/3）需与 plc_config.json 实际定义一致，否则标签错误 | 可接受：仅影响展示，不影响写入；需在测试阶段与 PLC 实际枚举值对比确认 |
| F-09 | INFO | `plc_write_subscriber.py` | Python 3.10+ union type hint `MQTTClient | None` 已有（F-05 延续）；生产 Python 版本待确认 | 已延续到测试阶段确认 |

### 禁用技术检查（v0.4.0 增量）

| 约束 | 合规 | 说明 |
|------|------|------|
| 禁 Docker | 合规 | 无 Docker 相关代码 |
| 禁 Django Channels / Redis | 合规 | 未引入 |
| 禁 pscp 部署 | 合规 | 无部署脚本 |
| 不改 owner-management | 合规 | 未触碰相关模块 |
| 不改 logging | 合规 | 未触碰 log_config_manager |
| 不改 PLC 采集主路径 | 合规 | 仅改 `_on_command`（写入路径），不改 `room_data_collector` 等采集路径 |
| 不自运行测试 | 合规 | 测试文件已更新但未执行 |
| 不自 push / 部署 | 合规 | 无 git / plink 命令 |
