# BUG-FM-002 故障管理表零捕获：MQTT 报文字段映射错位

| 字段 | 值 |
|---|---|
| Bug ID | BUG-FM-002 |
| 影响版本 | v0.6.0 (commits `537c5a7`、`bf666f9`) |
| 修复版本 | `5ab1e91 fix(fault-mgmt): 修复 MQTT 报文字段映射` |
| 严重度 | P0（功能完全失效）|
| 首次发现 | 2026-05-27 23:30 用户验收 |
| 修复部署 | 2026-05-28 00:05 CST |
| 距首部署 | ≈ 1.5 小时 |

## 现象

v0.6.0 部署后 90 分钟，`device_fault_event` 表 `count = 0`。但：
- `freeark-fault-consumer` 进程 active running
- 已建立 ESTAB TCP 连接到 EMQX broker `171.213.194.195:8084`
- 已建立 MySQL 连接
- 进程无崩溃日志

## 根因（实测探针）

60 秒探针订阅 `/screen/upload/screen/to/cloud/#` 抓到 1683 条真实报文。报文结构与代码假设**三处不匹配**：

```json
// 实际报文（生产实测）：
{
  "header": {
    "ackCode": 1,
    "messageId": "6212",
    "name": "DeviceStatusUpdate",
    "screenMac": "7ae30fbf429887b3"
  },
  "payload": {                          ← 多了一层 "payload"
    "code": 200,
    "data": {
      "deviceSn": 21997,
      "productCode": 270001,
      "items": [
        {"attrTag": "primary_valve_opening", "attrValue": "0.1"}   ← attrTag/attrValue 不是 paramName/value
      ]
    }
  }
}
```

| 位置 | 代码原假设 | 实际值 | 影响 |
|---|---|---|---|
| `data` 路径 | `root.data` | `root.payload.data` | `data` = `{}`，`device_sn` 取不到 → 早早 `return` |
| item 字段名 | `paramName` | `attrTag` | 即便走到这步，`param_name = None` → `continue` |
| item 字段名 | `value` | `attrValue` | 同上 |

代码三处错误**叠加**形成"双重保险地跳过"——所有消息静默丢弃。

## 为什么测试没有发现

`tests_fault_event.py` 的 `TestHandleMessageIntegration` 用的 mock payload 也是 `{"header":..., "data":...}` 加 `paramName/value` 的旧格式——与代码假设**自洽**。因为团队此前未抓过真实生产报文，开发期凭推断写测试 fixture。

## 为什么没有日志报错

报文格式问题在代码逻辑层不是异常，是"`device_sn` 为空 → 返回"和"`param_name` 为空 → continue"。两者都是 `logger.debug()` 级别。Django LOGGING 默认不路由 DEBUG 到 stdout/journal，所以 systemd journal 完全静默。

## 命名差异的更深含义

| 路径 | 字段命名 |
|---|---|
| MQTT 实时上报（attrTag）| `primary_valve_opening`、`2nd_inwater_temp_detect`、`pau_through_temp`、`newwind_inlet_temp` |
| PLC 定时拉取（param_name）| `living_room_temp_sensor_error`、`comm_fault_timeout`、`error_82`、`fresh_air_fault_bit_3` |

**`attrTag` 与 `param_name` 是两套字段命名空间**：
- 探针 60s 仅看到遥测字段（attrTag），未观测到故障字段命名
- hotfix 上线后实际收到的故障 attrTag = `comm_fault_timeout`、`error_<N>` 等——**与 FAULT_PARAM_NAMES 一致**
- 结论：MQTT 用的故障字段命名与 PLC 拉取一致，遥测字段命名才有差异

## 修复方案

`_handle_message` 三处修改 + MAC 提取增加 `header.screenMac` 回退：

```python
# data 提取：优先 root.payload.data，回退 root.data
payload_obj = root.get('payload') or {}
data = payload_obj.get('data') or {}
if not data and 'data' in root:
    data = root.get('data') or {}

# item 字段：优先 attrTag/attrValue，回退 paramName/value
param_name = str(item.get('attrTag') or item.get('paramName') or '')
value = item.get('attrValue') if 'attrValue' in item else item.get('value')
```

保留旧格式兼容是为了不破坏已有 7 个测试，且不影响真实生产消息走新路径。

## 测试增强

新增 2 个真实报文格式回归测试：
- `test_real_payload_format_attr_tag_triggers_t1`：完整复刻探针 #1 的 payload 结构，验证 T1 入库
- `test_real_payload_non_fault_attr_tag_skipped`：验证遥测字段（primary_valve_opening 等）被 classifier 正确跳过

测试总数 110 → 112，全部通过。

## 验证

修复后 60 秒内：

```
FaultEvent total = 421
FaultEvent is_active = True : 418
FaultEvent is_active = False: 3   ← T3 状态转移也工作
```

故障类型样本（覆盖 `error_<N>` 和 `comm_fault_timeout` 两大类）：

| first_seen_at | specific_part | device_sn | fault_code | active |
|---|---|---|---|---|
| 2026-05-28 00:07:06 | 1-1-6-602 | 22157 | error_265 | T |
| 2026-05-28 00:06:44 | 1-2-16-1602 | 21997 | error_82 | T |
| 2026-05-28 00:06:17 | 8-1-8-803 | 22550 | error_733/734 | T |
| 2026-05-28 00:05:28 | 8-1-10-1002 | 22001 | error_679 | F ← T3 |
| 2026-05-28 00:05:05 | 8-1-27-2704 | 22553-22555 | comm_fault_timeout | T |

## 经验教训

1. **凭推断写测试 fixture 是高风险**。在开发 MQTT/外部协议适配器时，必须在 staging/dev 环境先抓真实样本固化为 fixture，而不是仅凭代码侧（state machine 等）的逻辑推导出预期格式。
2. **silent skip 必须升 log level**。生产 `device_sn 为空 → return` 这类 happy-path-but-zero-rows 现象，应在 INFO 级别记录 first-N-occurrences（带去重），否则零捕获故障无任何信号可查。
3. **MQTT 路径和 PLC 拉取路径的字段命名差异需要在 v0.5.3-FCC 的设计文档中显式记录**。当前 v0.6.0 的 fault_classifier 复用了 v0.5.3 的 `FAULT_PARAM_NAMES` 集合，正好命名一致是"运气好"，但遥测字段命名不同。后续如要处理 MQTT 中的非故障 attrTag，需要扩展白名单。

## 时间线

| 时间 | 事件 |
|---|---|
| 2026-05-27 23:14 | v0.6.0 首次部署完成（commit `bf666f9`） |
| 2026-05-27 23:30 | 用户验收：表 0 行 |
| 2026-05-27 23:35 | 探针脚本 60s 抓 1683 条报文，定位 3 处字段错位 |
| 2026-05-28 00:00 | hotfix commit `5ab1e91`，112 tests OK |
| 2026-05-28 00:03 | 生产 `git pull` + 重启 consumer |
| 2026-05-28 00:05 | 验证 `count=421`，活跃 418 |

## 关联

- 修复 commit：[`5ab1e91`](../../../../commit/5ab1e91)
- 探针脚本：`scripts/tmp/probe_mqtt.py`（临时排查工具，可保留）
- 受影响代码：`FreeArkWeb/backend/freearkweb/api/management/commands/fault_consumer.py:_handle_message`
- 受影响测试：`FreeArkWeb/backend/freearkweb/api/tests_fault_event.py:TestHandleMessageIntegration`
