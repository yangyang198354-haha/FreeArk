# 测试计划

```
file_header:
  document_id: TP-v0.5.6
  title: 设备面板实时数据刷新 — 测试计划
  author_agent: sub_agent_test_engineer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/requirements/v0.5.6_device_panel_realtime/requirements_spec.md
    - docs/requirements/v0.5.6_device_panel_realtime/user_stories.md
    - docs/development/v0.5.6_device_panel_realtime/implementation_plan.md
```

---

## 测试策略

由于 FreeArk 采用物理机部署（无 Docker），本测试计划区分：
- **静态验证**：代码逻辑、接口签名、模块依赖可通过代码审查验证
- **集成测试**：需在生产或类生产环境（树莓派 + MQTT broker + PLC 设备）执行

---

## 单元测试用例

### UT-001：OndemandPLCLatestDataHandler 不写历史

**测试对象**：`mqtt_handlers.OndemandPLCLatestDataHandler._write_history()`

**验证方式（静态）**：
- 代码中 `_write_history` 被覆盖为 no-op，方法体只有 `logger.debug(...)`
- 父类 `PLCLatestDataHandler.handle()` 调用 `self._write_history(records)`，多态确保调用子类实现
- `DeviceParamHistory.objects.bulk_create` 不会被执行

**预期结果**：PASS（代码审查已确认）

**覆盖需求**：OQ-003, ADR-004, AC-001-5

---

### UT-002：MQTTConsumer on_message 路由 — ondemand 消息进 ondemand 队列

**测试对象**：`mqtt_consumer.MQTTConsumer.on_message()`

**验证方式（静态）**：
- topic 以 `/datacollection/plc/ondemand/result/` 开头时，`target_queue = self._ondemand_queue`
- 该判断在所有其他 topic 判断（screen_connectivity, write_ack, energy/general）之前
- ondemand 消息不会进入 `_energy_queue` 或 `_general_queue`

**预期结果**：PASS（代码审查已确认）

**覆盖需求**：REQ-FUNC-001, US-007, AC-007-1

---

### UT-003：MQTTConsumer _extract_specific_part_from_topic

**测试对象**：`mqtt_consumer.MQTTConsumer._extract_specific_part_from_topic()`

**测试数据**：
| topic | prefix | 预期结果 |
|-------|--------|---------|
| `/datacollection/plc/ondemand/result/9-1-31-3104` | `/datacollection/plc/ondemand/result/` | `9-1-31-3104` |
| `/datacollection/plc/ondemand/result/` | `/datacollection/plc/ondemand/result/` | `` (空字符串) |
| `/other/topic` | `/datacollection/plc/ondemand/result/` | `` (空字符串) |

**验证方式（静态）**：
- `topic[len(prefix):]` 逻辑简单，无副作用

**预期结果**：PASS

---

### UT-004：MQTTConsumer _extract_max_collected_at

**测试对象**：`mqtt_consumer.MQTTConsumer._extract_max_collected_at()`

**测试数据**（JSON payload 结构）：
```python
payload = {
    "9-1-31-3104": {
        "PLC IP地址": "192.168.1.100",
        "data": {
            "living_room_temperature": {"value": 225, "success": True, "timestamp": "2026-05-21 10:00:05"},
            "system_switch": {"value": 1, "success": True, "timestamp": "2026-05-21 10:00:03"},
        }
    }
}
# 预期结果：'2026-05-21 10:00:05'
```

**预期结果**：PASS

---

### UT-005：OndemandCollectSubscriber 防重入

**测试对象**：`ondemand_collect_subscriber.OndemandCollectSubscriber._on_request()`

**验证方式（静态）**：
- `specific_part in self._pending` 时直接返回，不提交新任务
- `len(self._pending) >= self._max_pending` 时拒绝新请求

**预期结果**：PASS（代码审查已确认）

**覆盖需求**：AC-002-2（防重入）

---

### UT-006：device_ondemand_refresh 参数校验

**测试对象**：`views.device_ondemand_refresh()`

**测试用例**：
| 场景 | 输入 | 预期 HTTP 状态 |
|------|------|--------------|
| specific_part 为空字符串 | `{"specific_part": ""}` | 400 |
| specific_part 缺失 | `{}` | 400 |
| specific_part 有效 + MQTT 正常 | `{"specific_part": "9-1-31-3104"}` | 202 |
| specific_part 有效 + MQTT 故障 | `{"specific_part": "9-1-31-3104"}` + broker 不可达 | 503 |

**验证方式（静态）**：
- `specific_part = (request.data.get('specific_part') or '').strip()` — 空/缺失均被拦截
- MQTT 异常捕获 → 503

**预期结果**：PASS

**覆盖需求**：US-005, AC-005-1~3

---

### UT-007：device_ondemand_refresh 防重入（25s TTL）

**测试对象**：`views.device_ondemand_refresh()` + `_ondemand_inflight`

**验证方式（静态）**：
- 同一 `specific_part` 25 秒内第二次请求：`_ondemand_inflight.get(specific_part)` 返回近期时间戳，`(now - last_ts) < 25` 为 True → 直接返回 202，不发布 MQTT

**预期结果**：PASS

---

## 集成测试用例

### IT-001：按需采集端到端流程（需生产环境）

**前提**：生产树莓派 192.168.31.51 已部署 v0.5.6 代码，MQTT broker 192.168.31.98:32788 可达，至少 1 个 PLC 设备在线

**步骤**：
1. POST `/api/devices/ondemand-refresh/` `{"specific_part": "X"}`
2. 观察 MQTT broker 是否收到 `/datacollection/plc/ondemand/request/X`
3. 观察 datacollection 日志：是否有 `[ondemand] 开始采集`
4. 观察 MQTT broker 是否收到 `/datacollection/plc/ondemand/result/X`
5. 观察 consumer 日志：是否处理 ondemand 消息、写入 plc_latest_data、发布 done 通知
6. 观察前端是否收到 done 通知、自动更新参数值

**验收标准**：端到端时间 ≤ 15s（P95）

**覆盖需求**：REQ-FUNC-001, US-001, AC-001-1~3

---

### IT-002：按需采集不写 device_param_history（需生产环境）

**步骤**：
1. 记录 `device_param_history` 表当前行数 N
2. 触发 1 次按需采集
3. 等待 done 通知到达（consumer 完成写入）
4. 查询 `device_param_history` 行数

**验收标准**：行数仍为 N（不增加）

**覆盖需求**：OQ-003, ADR-004, AC-001-5

---

### IT-003：ondemand 消息不进入 energy/general 队列（需 consumer 日志）

**步骤**：
1. 触发按需采集
2. 检查 consumer 日志中的 `消息入队: queue=` 记录

**验收标准**：日志显示 `queue=ondemand`，不出现 `queue=energy` 或 `queue=general`

**覆盖需求**：AC-007-1

---

### IT-004：页面打开时自动触发按需采集（前端）

**步骤**：
1. 打开设备面板页面
2. 观察浏览器 Network 面板

**验收标准**：`mounted` 后立即出现 POST `/api/devices/ondemand-refresh/` 请求

**覆盖需求**：US-001, AC-001-1

---

### IT-005：30s 定时器防重入

**步骤**：
1. 手动触发一次 `triggerOndemandRefresh()`，不等待 done 通知
2. 等待 30s 定时器到期

**验收标准**：定时器到期后，因 `ondemandInFlight=true`，不发出新的 POST 请求

**覆盖需求**：AC-002-2

---

### IT-006：MQTT 不可用时降级为 DB 轮询

**步骤**：
1. 断开 MQTT WebSocket 连接（或模拟浏览器断网）
2. 等待 30s 定时器

**验收标准**：触发 `fetchData()`（GET realtime-params），不触发 `triggerOndemandRefresh()`

**覆盖需求**：AC-003-3

---

## 回归测试确认

以下现有功能在 v0.5.6 代码变更后应保持不变：

| 功能 | 涉及文件 | 测试要点 |
|------|---------|---------|
| 周期采集（energy/general 队列） | mqtt_consumer.py on_message | ondemand 路由不影响 energy/general 路由判断 |
| PLCDataHandler（energy 参数写入） | mqtt_handlers.py | 未修改 |
| ConnectionStatusHandler | mqtt_handlers.py | 未修改 |
| PLCLatestDataHandler（正常路径） | mqtt_handlers.py | 父类不受子类覆盖影响 |
| PLCWriteSubscriber（写入指令） | plc_write_subscriber.py | 未修改 |
| TaskScheduler（周期调度） | task_scheduler.py | 不修改，OndemandCollectSubscriber 失败不影响主循环 |
