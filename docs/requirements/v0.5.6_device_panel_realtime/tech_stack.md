# 技术选型文档

```
file_header:
  document_id: TECH-v0.5.6
  title: 设备面板实时数据刷新 — 技术选型
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: DRAFT
  references:
    - docs/requirements/v0.5.6_device_panel_realtime/architecture_design.md
    - docs/architecture/tech_stack_v0.5.0_device_settings.md
```

---

## 结论：本版本不引入新技术栈，全部在现有技术选型范围内实现

v0.5.6 的所有新增模块均沿用已有技术栈，无需引入新的依赖或框架。

---

## 技术选型确认清单

| 组件 | 现有技术选型 | v0.5.6 使用方式 | 变更 |
|------|------------|---------------|------|
| 后端框架 | Django + Django REST Framework | 新增视图函数 `device_ondemand_refresh`，复用现有 `@api_view`、`Response` | 无变更 |
| MQTT 客户端（后端 consumer） | paho-mqtt | 扩展 `MQTTConsumer`：新增 topic 订阅、独立队列、独立 worker | 无新依赖 |
| MQTT 客户端（后端 views publish） | paho-mqtt `publish.single()` | 单次发布 ondemand request 指令 | 无新依赖 |
| MQTT 客户端（datacollection） | paho-mqtt | `OndemandCollectSubscriber` 使用同一库 | 无新依赖 |
| 数据库 ORM | Django ORM + MySQL (生产) / SQLite (测试) | `PLCLatestData.objects.bulk_create(update_conflicts=True)` 复用现有 upsert | 无变更 |
| 前端框架 | Vue 3 + Composition API | `DeviceCardsView.vue` 改造使用现有 `ref`、`computed`、生命周期钩子 | 无新依赖 |
| 前端 MQTT WebSocket | mqtt.js (via `useMqttWebSocket.js`) | 订阅 `/datacollection/plc/ondemand/done/<sp>` topic，与 write_ack 模式相同 | 无变更 |
| 前端 HTTP 客户端 | 自封装 `api.js` (fetch) | 新增 `api.post('/api/devices/ondemand-refresh/', ...)` 调用 | 无变更 |
| nginx MQTT WebSocket 反代 | nginx `/mqtt-ws/` 反代 | 已就绪，无需修改 | 无变更 |
| Python 并发 | `threading.Thread` + `concurrent.futures.ThreadPoolExecutor` | `OndemandCollectSubscriber` 使用 `ThreadPoolExecutor(max_workers=1)` | 无新依赖 |
| systemd 服务管理 | systemd | 所有变更均在已有 service 内（`freeark-task-scheduler.service`、`freeark-mqtt-consumer.service`、`freeark-web.service`）；无新增 service | 无变更 |

---

## 依赖版本（不变）

| 依赖 | 现有版本约束 | 状态 |
|------|------------|------|
| paho-mqtt | 已安装 | 沿用 |
| Django | 已安装（≥4.x） | 沿用 |
| djangorestframework | 已安装 | 沿用 |
| mqtt (npm) | 已安装（前端） | 沿用 |
| Vue 3 | 已安装 | 沿用 |
| Element Plus | 已安装 | 沿用 |

---

## 备注

若后续需要在后端 `views.py` 中使用 paho-mqtt 的**长连接复用**（而非每次 `publish.single()` 新建连接），可考虑封装一个共享的 `MQTTPublisher` 单例（模块级实例），但这属于性能优化项，不在 v0.5.6 必须范围内。v0.5.6 优先采用 `paho.mqtt.publish.single()` 简单实现，正确性优先。
