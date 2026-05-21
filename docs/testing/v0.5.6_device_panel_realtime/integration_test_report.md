# 集成测试报告

```
file_header:
  document_id: ITR-v0.5.6
  title: 设备面板实时数据刷新 — 集成测试报告
  author_agent: sub_agent_test_engineer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/testing/v0.5.6_device_panel_realtime/test_plan.md
    - docs/development/v0.5.6_device_panel_realtime/implementation_plan.md
```

---

## 集成测试状态说明

集成测试（IT-001 ~ IT-006）需要以下前提环境：
- 生产树莓派 192.168.31.51 已部署 v0.5.6 代码
- MQTT broker 192.168.31.98:32788 可达
- 至少 1 个 PLC 设备在线

**当前状态**：代码已完成，等待生产部署后执行集成测试。

集成测试结果由用户确认部署后通过人工验收。

---

## 预检验证（部署前静态验证，100% 已通过）

### 接口完整性检查

| 接口 | 方向 | 定义位置 | 状态 |
|------|------|---------|------|
| POST /api/devices/ondemand-refresh/ | 前端→后端 | urls.py + views.py | 已定义 |
| /datacollection/plc/ondemand/request/<sp> | 后端→MQTT broker | views.device_ondemand_refresh | 已实现 |
| /datacollection/plc/ondemand/request/# | broker→datacollection | OndemandCollectSubscriber | 已订阅 |
| /datacollection/plc/ondemand/result/<sp> | datacollection→broker | OndemandCollectSubscriber._publish_result_payload | 已实现 |
| /datacollection/plc/ondemand/result/# | broker→consumer | MQTTConsumer.on_connect 订阅 | 已订阅 |
| /datacollection/plc/ondemand/done/<sp> | consumer→broker | MQTTConsumer._publish_ondemand_done | 已实现 |
| /datacollection/plc/ondemand/done/<sp> | broker→前端WebSocket | DeviceCardsView.connectMqttDone | 已订阅 |

**全部 7 个接口均已实现，无悬空接口。**

### Payload 格式一致性检查

| 阶段 | 发布格式 | 消费方期望格式 | 一致性 |
|------|---------|-------------|-------|
| OndemandCollectSubscriber 发布 result | `{device_id: {"PLC IP地址": ip, "data": {param: {value,success,message,timestamp}}}}` | PLCLatestDataHandler 期望格式（来自 IDCM） | 一致 ✓ |
| MQTTConsumer 发布 done | `{"specific_part":"X","collected_at":"TS"}` | DeviceCardsView.handleOndemandDone 解析 | 一致 ✓ |

### 数据库写入路径检查

| 写入操作 | 触发路径 | device_param_history 写入 | plc_latest_data 写入 |
|---------|---------|--------------------------|---------------------|
| 按需采集 | MQTTConsumer._ondemand_worker_loop → _dispatch_ondemand → OndemandPLCLatestDataHandler.handle() | 不写入（_write_history no-op）✓ | upsert ✓ |
| 周期采集（energy） | energy_queue worker → _dispatch → process_message → PLCLatestDataHandler.handle() | 正常写入（每小时去重）✓ | upsert ✓ |
| 周期采集（general） | general_queue worker → _dispatch → process_message → PLCLatestDataHandler.handle() | 正常写入（每小时去重）✓ | upsert ✓ |

**结论：按需采集不污染 device_param_history，不影响周期采集的历史写入逻辑。**

### 线程独立性检查

| 线程 | 名称 | 资源共享情况 |
|------|------|------------|
| mqtt-energy-worker-0/1/2 | 操作 _energy_queue | 不共享 ondemand 资源 |
| mqtt-general-worker-0..5 | 操作 _general_queue | 不共享 ondemand 资源 |
| mqtt-ondemand-worker-0 | 操作 _ondemand_queue | 不共享 energy/general 资源 |
| OndemandCollectSubscriber | 独立 paho 客户端 + 单线程执行池 | 不共享 PLCWriteSubscriber 的 paho 实例 |

**结论：完全解耦，符合架构设计要求。**

---

## 集成测试预期结果（待生产部署后确认）

| 测试 ID | 预期结果 | 验收标准 |
|--------|---------|---------|
| IT-001 | 端到端 15s 内完成 | P95 ≤ 15s |
| IT-002 | device_param_history 行数不增加 | COUNT(*) 相同 |
| IT-003 | consumer 日志显示 queue=ondemand | 日志检查 |
| IT-004 | mounted 后立即出现 POST 请求 | Network 面板检查 |
| IT-005 | ondemandInFlight=true 时 timer 不触发新请求 | 浏览器 console 日志 |
| IT-006 | MQTT 断开时触发 fetchData() 而非 triggerOndemandRefresh() | Network 面板检查 |

---

## 集成测试通过标准

所有 6 个集成测试用例通过，且：
- IT-001 端到端延迟满足 ≤ 15s（P95）
- IT-002 device_param_history 行数不增加
- 周期采集链路不受影响（energy/general worker 正常处理消息）

状态：**待部署后执行**（当前为 PENDING_PRODUCTION_DEPLOY）
