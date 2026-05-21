# 代码评审报告

```
file_header:
  document_id: CR-v0.5.6
  title: 设备面板实时数据刷新 — 代码评审报告
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/development/v0.5.6_device_panel_realtime/implementation_plan.md
```

---

## 评审结论

**整体结论：PASS（无 CRITICAL finding）**

---

## 逐文件评审

### datacollection/ondemand_collect_subscriber.py（新增）

| 维度 | 评审结论 |
|------|---------|
| 职责边界 | PASS — 专注于订阅 request topic、执行单设备采集、发布 result topic，无职责扩散 |
| 防重入 | PASS — `_pending` set + `_pending_lock`，同一 specific_part 只有 1 个并发任务 |
| 防过载 | PASS — `maxsize=20` 有界 pending set，超出丢弃 |
| 串行执行 | PASS — `ThreadPoolExecutor(max_workers=1)`，符合 OQ-002 决议 |
| 独立客户端 | PASS — 独立 MQTTClient 实例，不与 PLCWriteSubscriber 共用 |
| 失败处理 | PASS — PLC 不可达时发布含空 data 的 result，consumer 能感知 |
| 启动隔离 | PASS — `_run` 在守护线程运行，崩溃不影响 TaskScheduler |
| 历史表路径 | PASS — 不涉及 device_param_history |

**MINOR findings（不阻塞部署）：**
- `_read_plc_params` 逐参数串行读取，对于参数量大（约 50 参数）的设备，采集耗时可能接近 15s 上限。生产环境需观测实际耗时，若超限可后续切换为 `_read_single_plc_with_multiple_params`（分块批量读取）。

### datacollection/improved_data_collection_manager.py（修改）

| 维度 | 评审结论 |
|------|---------|
| 隔离性 | PASS — `_start_ondemand_collect_subscriber` 失败不传播到 `start()`，try/except 完整 |
| 日志 | PASS — 启动成功/失败均有明确日志 |

### FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py（修改）

| 维度 | 评审结论 |
|------|---------|
| 继承设计 | PASS — 覆盖 `_write_history()` 为 no-op，最小改动，逻辑清晰（ADR-004）|
| 历史表保护 | PASS — 父类 `handle()` 调用链：`_bulk_upsert()` + `_write_history()`，子类 no-op 覆盖保证不写历史 |

### FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py（修改）

| 维度 | 评审结论 |
|------|---------|
| 路由优先级 | PASS — ondemand result 在 on_message 中优先匹配，不误入 energy/general 队列 |
| 队列隔离 | PASS — `_ondemand_queue` 独立，maxsize=100 |
| Worker 启动 | PASS — 1 个 ondemand worker，在 start() 中与 energy/general workers 统一管理 |
| Done 通知 QoS | PASS — QoS=0（OQ-004 决议） |
| Stop 时清空 | PASS — stop() 已扩展等待 `_ondemand_queue` 清空 |
| DB 连接 | PASS — `_ondemand_worker_loop` 复用与 `_worker_loop` 相同的连接维护模式 |

### FreeArkWeb/backend/freearkweb/api/views.py（修改）

| 维度 | 评审结论 |
|------|---------|
| 认证 | PASS — `@permission_classes([permissions.IsAuthenticated])` |
| 参数校验 | PASS — specific_part 为空返回 400 |
| 防重入 | PASS — `_ondemand_inflight` 进程内缓存，TTL=25s |
| MQTT 发布 | PASS — `paho.mqtt.publish.single()` 一次性连接，不依赖长连接 |
| 失败处理 | PASS — MQTT 异常返回 503，日志记录 |
| 数据库影响 | PASS — 不访问数据库，不触发 device_param_history |

### FreeArkWeb/backend/freearkweb/api/urls.py（修改）

| 维度 | 评审结论 |
|------|---------|
| 路由注册 | PASS — `devices/ondemand-refresh/` 已正确注册，name 唯一 |

### FreeArkWeb/frontend/src/views/DeviceCardsView.vue（重构）

| 维度 | 评审结论 |
|------|---------|
| 刷新按钮移除 | PASS — `nav-refresh-btn` 已从模板移除，Refresh icon 已从 import/components 中移除 |
| 按需采集触发 | PASS — mounted + 30s timer 均调用 `triggerOndemandRefresh()` |
| 防重入 | PASS — `ondemandInFlight` 标志，重复 timer 触发时跳过 |
| 超时降级 | PASS — 20s setTimeout 后重置 inFlight 并调用 fetchData() |
| MQTT done 订阅 | PASS — `connectMqttDone()` 在 mounted 中调用，`beforeUnmount` 中断开 |
| 页面切换清理 | PASS — watch specificPart 时断开 MQTT，清除 timeout，重置 inFlight |
| 统一时间戳 | PASS — `lastUpdatedAt` 计算属性，取所有 params collected_at 最大值 |
| 各列时间移除 | PASS — `col-time` span 已从 col-header 中移除 |
| 降级兜底 | PASS — `_mqttDisconnect` 为 null 时 startAutoRefresh 走 fetchData() 路径 |
| 加载指示 | PASS — `ondemandInFlight` 控制 Loading 图标显示 |

---

## CRITICAL findings

**无**

## MAJOR findings

**无**

## MINOR findings

1. **ondemand_collect_subscriber.py `_read_plc_params`**：逐参数串行读取适合初版，参数量大时耗时需监控。可后续优化为分块批量读取（不阻塞本次部署）。
2. **views.py `_ondemand_inflight`**：进程级 dict，不支持多进程部署（waitress 单进程无影响）。若未来切换多进程，需改为 Redis/数据库。

## 评审结论

PASS — 无 CRITICAL，无 MAJOR，2 个 MINOR findings 均不阻塞部署，可进入测试阶段。
