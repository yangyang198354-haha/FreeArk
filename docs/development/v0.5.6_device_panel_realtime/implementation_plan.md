# 实现计划

```
file_header:
  document_id: IMPL-v0.5.6
  title: 设备面板实时数据刷新 — 实现计划与实施报告
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/requirements/v0.5.6_device_panel_realtime/requirements_spec.md
    - docs/requirements/v0.5.6_device_panel_realtime/architecture_design.md
    - docs/requirements/v0.5.6_device_panel_realtime/module_design.md
```

---

## 已实现模块清单

| 模块 ID | 文件路径 | 变更类型 | 状态 | 覆盖需求/用户故事 |
|---------|---------|---------|------|-----------------|
| MOD-DC-01 | `datacollection/ondemand_collect_subscriber.py` | 新增 | 已完成 | REQ-FUNC-001, US-006 |
| MOD-DC-02 | `datacollection/improved_data_collection_manager.py` | 修改（start()） | 已完成 | US-006 |
| MOD-BE-01 | `FreeArkWeb/backend/freearkweb/api/views.py` | 新增函数 device_ondemand_refresh | 已完成 | REQ-FUNC-001, US-005 |
| MOD-BE-02 | `FreeArkWeb/backend/freearkweb/api/urls.py` | 追加 1 条路由 | 已完成 | US-005 |
| MOD-BE-03 | `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 新增 OndemandPLCLatestDataHandler 类 | 已完成 | REQ-FUNC-001, US-007, ADR-004 |
| MOD-BE-04 | `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | 修改（队列/worker/路由/订阅） | 已完成 | REQ-FUNC-001, US-007 |
| MOD-FE-01 | `FreeArkWeb/frontend/src/views/DeviceCardsView.vue` | 重构 | 已完成 | REQ-FUNC-001~004, US-001~004 |

---

## 关键实现决策说明

### MOD-DC-01 OndemandCollectSubscriber
- 独立 paho-mqtt 客户端（`MQTTClient`，不与 PLCWriteSubscriber 共用）
- `concurrent.futures.ThreadPoolExecutor(max_workers=1)`：单线程串行处理（OQ-002）
- 有界 pending set（maxsize=20）+ per-specific_part 防重入
- 失败时（PLC 不可达、IP 未找到）发布含空 data 的 result 消息，consumer 可感知
- `_load_owner_ip_map()`：扫描 `resource/*.json` 建立 specific_part -> PLC IP 映射
- 超时保护通过 PLCReadWriter 本身 snap7 超时控制（由 PLCReadWriter 的连接参数保障）

### MOD-BE-03 OndemandPLCLatestDataHandler
- 继承 PLCLatestDataHandler，仅覆盖 `_write_history()` 为 no-op（OQ-003）
- 父类 `handle()` 逻辑完整复用，包含 payload 格式检验、records 构建、`_bulk_upsert()`

### MOD-BE-04 MQTTConsumer 扩展
- `on_message` 路由优先级：ondemand result > screen connectivity > write ack > energy/general
- `_ondemand_worker_loop`：完整复用 `_worker_loop` 的连接维护模式（close_old_connections, ensure_connection）
- done 通知发布：QoS=0，`self.client.publish()`（OQ-004）
- `stop()` 已扩展等待 `_ondemand_queue` 清空

### MOD-BE-01 device_ondemand_refresh 视图
- 使用 `paho.mqtt.publish.single()` 一次性发布，不依赖 MQTTConsumer 的长连接
- `_ondemand_inflight` 进程内字典 + TTL=25s 防重入
- 异常捕获返回 503，不 500

### MOD-FE-01 DeviceCardsView.vue
- 移除 `Refresh` 按钮和 import，改为 `Loading` 图标（采集进行中显示）
- `triggerOndemandRefresh()`：防重入（ondemandInFlight），超时 20s 后降级 fetchData()
- `connectMqttDone()`：调用 `useMqttWebSocket()` 订阅 done topic
- `startAutoRefresh()`：MQTT 可用时触发 ondemand，不可用时降级 fetchData()（AC-003-3）
- `lastUpdatedAt` 计算属性：遍历所有 params 取最大 collected_at（REQ-FUNC-004）
- `col-time` span 已从 col-header 模板中移除（AC-004-2）

---

## 不变模块确认

| 模块 | 确认状态 |
|------|---------|
| PLCDataHandler | 未修改 |
| ConnectionStatusHandler | 未修改 |
| PLCLatestDataHandler（原类） | 未修改 |
| TaskScheduler | 未修改 |
| energy_queue / general_queue | 未修改 |
| PLCWriteSubscriber | 未修改 |
| 其他视图和 URL | 未修改 |
| device_param_history 写入路径 | 未触及 |

---

## 部署约束确认

- 物理机部署，禁 Docker：代码无容器化依赖
- 生产部署：plink + git pull（无 pscp）
- 数据库路径：按需采集只写 plc_latest_data，不写 device_param_history（OQ-003）
- 新增依赖：无（paho-mqtt 已在生产环境安装）
