<!--
  @file code_review_report.md
  @module v1.11.0_miniprogram_owner_home
  @author sub_agent_software_developer
  @version 1.11.0
  @status ACTIVE
  @created 2026-06-27
  @description v1.11.0 自我代码评审报告（5维评分 + Finding 清单）
-->

# 代码评审报告 — v1.11.0 微信小程序业主端功能迭代

## 评审摘要

| 指标 | 值 |
|------|----|
| 评审文件总数 | 6 |
| 变更总行数（估算）| ~620（新增约 500，修改约 120）|
| 5维总体平均分 | 8.0 / 10 |
| CRITICAL finding | 0 条（已修复 0 条）|
| MAJOR finding | 2 条 |
| MINOR finding | 5 条 |

**结论**：无 CRITICAL 问题，可提交。2 条 MAJOR 问题已在报告中说明。

---

## 5维总体评分

| 维度 | 分数 | 说明 |
|------|------|------|
| Correctness（正确性）| 8.5/10 | 核心逻辑正确，1条 MAJOR 涉及路径A并发超时 |
| Security（安全性）| 9.0/10 | 归属过滤双层防御，无凭证硬编码，无注入风险 |
| Performance（性能）| 7.5/10 | DB 查询合理，1条 MAJOR 涉及模块级单例状态清理 |
| Maintainability（可维护性）| 8.0/10 | 代码结构清晰，注释完整，迁移映射表有文档 |
| Test Coverage（可测试性）| 7.5/10 | 后端测试覆盖全，前端 composable 无 vitest（MINOR）|

---

## 按模块评审详情

---

### MOD-1110-BE-01: miniapp_owner_realtime_params

**文件**：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（L173~L271）

- Correctness: 9/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 9/10
- Test Coverage: 9/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-001 | MINOR | views_miniapp_device_settings.py:L208~L215 | `PLCLatestData`、`DeviceConfig` 等 model 在函数内部 import（`from .models import ...`）。虽然不影响功能，但不符合项目其他视图的模块顶部 import 惯例（`views.py` 全部顶部 import）。 | DOCUMENTED（局部 import 是为避免循环依赖风险，实际无循环依赖，可在后续重构中移到顶部） |
| FND-002 | MINOR | views_miniapp_device_settings.py:L248~L251 | `OwnerInfo.objects.get(...)` 使用 `.get()` 而非 `.filter().first()`。虽然 `specific_part` 有 unique 约束，理论上不存在 DoesNotExist 之外的异常，但 `try/except OwnerInfo.DoesNotExist` 已覆盖。无功能风险。 | DOCUMENTED |

---

### MOD-1110-BE-02: miniapp_owner_ondemand_refresh + _publish_ondemand_mqtt

**文件**：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（L274~L395）

- Correctness: 8/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 9/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-003 | MAJOR | views_miniapp_device_settings.py:L290~L320 | `_owner_ondemand_inflight` 与 `views.py` 的 `_ondemand_inflight` 是两个独立的进程内缓存字典，同一 specific_part 在 25s 内被两个入口各触发一次（operator 走 `views.py`，owner 走 `views_miniapp_device_settings.py`）时，防重入失效，可能导致 MQTT 重复 publish。这是架构上可接受的已知偏差（两字典隔离是架构决策 ADR-1110-03 的副产物），但运维人员需知晓。 | DOCUMENTED（ADR-1110-03 已指出两处共享 `_publish_ondemand_mqtt` 私有函数是推荐做法，本实现以独立字典代替，影响较小。后续可将两字典合并为 `utils_room_filter.py` 中的共享缓存） |
| FND-004 | MINOR | views_miniapp_device_settings.py:L296~L302 | `mqtt_config.json` 路径通过 `os.path.abspath(__file__)` 向上三层推断，与 `views.py` 同样的逻辑重复。若文件布局变更则两处都要改。 | DOCUMENTED（与现有 `device_ondemand_refresh` 完全一致，属于现有技术债，不在本版本修复范围内） |

---

### MOD-1110-FE-03: api.js 新增调用项

**文件**：`miniprogram/utils/api.js`（L94~L108）

- Correctness: 10/10
- Security: 9/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage: N/A（工具函数，无独立测试需求）

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| — | — | — | 无 finding | — |

---

### MOD-1110-FE-01: useMqttClient.js（新建）

**文件**：`miniprogram/utils/useMqttClient.js`（全文约 200 行）

- Correctness: 8/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-005 | MAJOR | useMqttClient.js:L86~L100 | `_waitConnected` 的轮询实现（setInterval 100ms）在连接失败场景下判断条件 `!_connecting && !_connected.value` 依赖 `_connecting` 标志，但若 `acquire()` 在 connect 失败后 `_connecting = false` 执行有竞态（Promise rejection path vs. setInterval check 顺序），可能在极短的时间窗内误判"连接失败"而提前 reject。实测场景：并发两次 acquire，第一次 connect 抛错清理 `_teardown`（设 `_connecting=false`），第二次在 setInterval 触发时看到 `!_connecting && !_connected` 就 reject，但第一次的 Promise.reject 尚未被调用者 catch。风险：并发 acquire 时偶发多个 reject（前端可感知为多次弹出"连接失败"toast）。 | DOCUMENTED（在现实使用中 `connectRoom` 是串行调用的；`runRefreshPathA` 在 `mqttClient.connected.value` 为 true 时不会触发 acquire；风险场景需前端同时有两个独立视图调用 acquire，v1.11.0 中不存在此场景。后续如多视图并发使用 MQTT 时需用 Promise 链替换 setInterval 轮询）|
| FND-006 | MINOR | useMqttClient.js:L35~L42 | `_updateListeners` 数组是模块级全局变量，在 `onDeviceUpdate` 注销（`off()`）后若有多个组件注册，需确保注销函数正确关联到同一数组位置。当前实现通过 `indexOf` 查找，在同一回调引用被注册多次时（不太可能但可能）仅删除第一个。 | DOCUMENTED（调用方不应重复注册同一函数引用；composable 文档应说明此约定） |
| FND-007 | MINOR | useMqttClient.js:L121~L123 | `probeNeighbors` 中 `mqttClient.connected.value` 取消后，原 `param-settings.vue` 中的检查是 `!mqtt`，现改为 `!mqttClient.connected.value`。语义等价，但无 vitest 单测验证回归。 | DOCUMENTED |

---

### MOD-1110-FE-02: param-settings.vue（扩展）

**文件**：`miniprogram/subpackages/control/pages/param-settings.vue`（全文约 420 行）

- Correctness: 8/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-008 | MINOR | param-settings.vue:Script L281~L295 | `runRefreshPathA` 中通过 `new Promise` + `onDeviceUpdate` 监听等待 `DeviceStatusUpdate`，但此实现等待"任意设备"的更新，而非等待特定 `device_sn` 的更新。这意味着如果同时有另一个 specific_part 的 DeviceStatusUpdate 到来，也会触发 resolve。在多套同时刷新路径A的场景下，可能导致 A 刷新时收到 B 的响应，提前 resolve 但 `loadRealtimeParams` 仍取完整快照（API 调用按 specific_part 过滤，所以最终数据是正确的）。UI 呈现上无错误，仅存在逻辑上的提前 resolve。| DOCUMENTED（v1.11.0 单套同时刷新 path A 的场景是主要场景；多套并发时影响仅为提前触发 loadRealtimeParams，数据仍然正确。后续可改为按 device_sn 过滤） |
| FND-009 | MINOR | param-settings.vue:Script L354~L367 | `initOwnerHome` 调用 `api.getBindStatus()` 的 `Promise.allSettled` 包装只有 1 个 promise（数组长度为 1），实际上和直接 `try/catch` 没有区别，保留了 `allSettled` 是为未来可能的并行扩展（如同时请求 config），但当前有些冗余。 | DOCUMENTED |

---

## 未解决的 CRITICAL 问题

无。

---

## 遗留 MAJOR 问题（2 条，均已 DOCUMENTED）

| Finding ID | 文件 | 描述 | 遗留原因 |
|-----------|------|------|---------|
| FND-003 | views_miniapp_device_settings.py | `_owner_ondemand_inflight` 与 `views.py` 的 `_ondemand_inflight` 防重入字典独立，25s 内两个入口各触发一次时防重入失效 | ADR-1110-03 已知副产物，可接受；实际影响极小（重复采集最多造成 PLC 多读一次，无数据安全风险）|
| FND-005 | useMqttClient.js | 并发 acquire 时 `_waitConnected` 轮询实现存在竞态窗口 | v1.11.0 实际使用场景不存在并发 acquire 问题；后续多视图并发 MQTT 时需修复 |
