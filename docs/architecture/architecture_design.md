# 架构设计文档

**文档编号**: ARCH-DESIGN-DEVICE-SETTINGS-001  
**项目名称**: FreeArk 设备参数设置功能  
**版本**: 0.3.0-APPROVED  
**状态**: APPROVED（v0.3.0：2026-05-19 broker WebSocket 端口确认为 32797；移除本期回滚接口设计）  
**创建日期**: 2026-05-19  
**最后更新**: 2026-05-19  
**作者**: system-architect (via pm-orchestrator)  
**审核**: pm-orchestrator（v0.3.0 端口与回滚范围调整审核通过）  
**输入文档**: REQ-SPEC-DEVICE-SETTINGS-001 v0.3.0-APPROVED, REQ-US-DEVICE-SETTINGS-001 v0.3.0-APPROVED

---

## 1. 架构概述

本功能在现有 FreeArk 平台（Django 5.2 + Waitress + Vue 3 + Element Plus）之上叠加一条**双向 MQTT 写入链路**，并通过 **MQTT-over-WebSocket** 将回执实时推送到前端。整体遵循"物理机部署，禁止 Docker，生产服务器树莓派（192.168.31.51），生产 DB MySQL@192.168.31.98:3306"的约束。

---

## 2. 现有基础设施调研结论

### 2.1 MQTT Broker

经代码分析（`FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py`、`FreeArkWeb/backend/mqtt_config.json`、`resource/mqtt_config.json`）：

| 用途 | Broker 地址 | 端口 | 协议 |
|------|------------|------|------|
| Django 后端订阅采集数据 | 192.168.31.98 | 32788 | MQTT TCP |
| datacollection 进程发布采集数据 | 192.168.31.98 | 32788 | MQTT TCP |
| Django MQTTConsumer 默认 fallback | 192.168.31.97 | 32795 | MQTT TCP |
| 屏侧云端通信（独立 Broker） | 47.117.41.184 | 11883 | MQTT TCP |

**结论**：
- MQTT broker 已存在于局域网（192.168.31.98:32788 为主，32795 为 fallback），**无需新增 broker**。
- **WebSocket 端口已确认**（2026-05-19 用户确认）：broker WebSocket 端口为 **32797**，前端连接地址为 `ws://192.168.31.98:32797/mqtt`。无需运维确认，此项前置条件已解除。

### 2.2 PLC 写入能力

`datacollection/plc_write_manager.py` 中 `PLCWriteManager` 已实现完整的 snap7 写入能力（`write_db_data(db_num, offset, value, data_type)`）。`plc_config.json` 已定义各 `param_name` 的地址映射。**新功能只需为其增加 MQTT 订阅触发入口**，不需要重写写入逻辑。

### 2.3 现有技术栈

- **后端**：Django 5.2 + DRF + Token Auth + paho-mqtt + Waitress（WSGI，非 ASGI）
- **前端**：Vue 3 + Element Plus + Vite + Axios（无 WebSocket 库）
- **部署**：物理机（树莓派 192.168.31.51），`git pull` 部署，无 Docker

---

## 3. 架构决策记录（ADR）

### ADR-01: MQTT-over-WebSocket 实现方式

**问题**：前端需要通过 WebSocket 接收 MQTT 回执推送；Django 后端使用 Waitress（WSGI），不支持原生 WebSocket。

**方案对比**：

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A（选定）** 前端直连 Broker WebSocket | 前端 JS 使用 `mqtt.js` 库直接连接 broker 的 WebSocket 端口（**32797**，已确认），订阅 `/datacollection/plc/write/ack/{specific_part}` | 零后端改动；实时性最好；架构简单 | broker 地址暴露给前端（局域网内可接受） |
| B 后端 Django Channels + Redis | 引入 Django Channels 替换 Waitress，增加 Redis channel layer | 后端控制强 | 需要 ASGI 服务器（Daphne/Uvicorn）替换 Waitress，引入 Redis，改动量大 |
| C 轮询降级方案 | 前端每 3 秒 GET `/api/plc-write-record/{request_id}/` 查询状态 | 实现最简单 | 违反 Q5 实时推送决策；延迟最差 |

**决策**：选择**方案 A**。前端直连 Broker WebSocket，使用 `mqtt.js`（NPM 包，前端侧，无需后端改动），避免引入 Django Channels 和 Redis 等重型依赖。  
**broker WebSocket 端口已确认为 32797**（2026-05-19 用户确认），前端连接 URL：`ws://192.168.31.98:32797/mqtt`。此项前置条件已解除，不再是部署阻塞项。

---

### ADR-02: PLC 写入订阅进程的集成方式

**问题**：datacollection 进程是否已有 MQTT 订阅能力可以复用？是否需要新增独立进程？

**代码调研结果**：`datacollection/improved_data_collection_manager.py` 通过 `MQTTClient` 发布采集数据；`datacollection/plc_write_manager.py` 的 `PLCWriteManager` 已有 snap7 写入能力，但当前没有 MQTT 订阅触发机制（只有发布能力）。commit `6dfa56f` (`fix(device-tree-sync)`) 涉及 `DeviceAttrDef` 行锁修复，与写入应用无直接关联。

**方案对比**：

| 方案 | 说明 |
|------|------|
| **A（选定）** 在 datacollection 进程内新增订阅线程 | 在 `improved_data_collection_manager.py` 中新增一个 `PLCWriteSubscriber` 线程，与现有采集线程共存 |
| B 独立新进程 | 新建 `datacollection/plc_write_subscriber.py` 作为独立进程，通过 systemd 管理 |

**决策**：选择**方案 A**（优先），可在现有 datacollection 进程中新增订阅线程，共享 MQTTClient 连接。若运维希望独立管理，可切换为方案 B（独立进程），两者接口完全相同，代码可复用。

---

### ADR-03: 独立操作记录表 vs 扩展 DeviceParamHistory

**决策**（来自 Q4 用户决策）：新建独立表 `plc_write_record`。

**理由**：
- `device_param_history` 是采集侧时序数据，语义上是"读到的值"，不是"主动写入的命令记录"；混合写入会模糊语义。
- 独立表可以增加 `status`（状态机字段）、`old_value`（写前快照）、`acked_at`（回执时间）等 `device_param_history` 没有的字段。
- 独立表查询时不需要过滤 `source` 字段，索引更简洁。

---

### ADR-04: 后端写命令 API 的事务边界

**问题**：后端接收到前端 POST 请求后，需要同步写 DB（`plc_write_record` 插入 `status=pending`）和异步发布 MQTT。事务边界如何保证？

**决策**：
1. 接收 POST → 生成 `request_id` → 在 DB 事务中插入 `plc_write_record(status=pending)` → 事务提交。
2. 事务提交成功后，在同一请求的 finally 块中发布 MQTT（paho-mqtt publish，QoS=1）。
3. 若 MQTT 发布失败（broker 不可达）：将 DB 记录更新为 `status=failed`，错误信息写入 `error_message`，返回 503。
4. 若 MQTT 发布成功：返回 202 Accepted（附带 `request_id`）。

**理由**：先写 DB 后发 MQTT，保证操作留痕不丢失；MQTT 发布失败时可从 DB 记录中重试。

---

### ADR-05: 回执超时状态机

**状态机设计**：

```
pending ──(MQTT ack 到达, success=true)──→ success
pending ──(MQTT ack 到达, success=false)─→ failed
pending ──(30s 客户端计时器超时)──────────→ [UI 显示 timeout，DB 不变]
pending ──(后端后台任务 T+60s 扫描)────── → timeout（DB 更新）
```

- **客户端超时（30s）**：由前端 JS 计时器管理，超时时 UI 展示"等待超时"，并对该 `request_id` 标记为超时状态（仅 UI 状态，不写 DB）。
- **服务端超时（60s）**：后端可选地运行一个定时任务（Django management command 或 cron），将 `status=pending` 且 `created_at < NOW()-60s` 的记录批量更新为 `status=timeout`。此任务保证 DB 状态最终一致，不依赖 UI。

---

## 4. 端到端时序图

```
操作员(浏览器) → Django 后端 → MQTT Broker → datacollection(PLCWriteSubscriber) → PLC
                                    ↑
                               WebSocket
                                    ↓
                              mqtt.js(浏览器)
```

**详细时序（正常路径）**：

```
T=0s   操作员点击"确认" → POST /api/device-settings/write/ 
         payload: { specific_part, param_name, new_value, token }

T=0~0.1s   Django 后端:
         1. 验证 Token (IsAuthenticated)
         2. 查询 PLCLatestData 获取 old_value（快照）
         3. 生成 request_id (UUID)
         4. INSERT plc_write_record(status=pending, ...)
         5. mqtt_publish('/datacollection/plc/write/command/{specific_part}', 
              { request_id, specific_part, plc_ip, param_name, new_value, operator }, QoS=1)
         6. 返回 202 Accepted { request_id }

T=0.1s   前端收到 202，button→loading，启动 30s 超时计时器

T=0~0.5s   Broker 将命令消息路由至 PLCWriteSubscriber（datacollection）

T=0.5~3s   PLCWriteSubscriber:
         1. 解析消息，查找 plc_config.json 中 param_name 的 db_num/offset/data_type
         2. snap7.write_db_data(db_num, offset, new_value, data_type)
         3. 写入成功 → mqtt_publish('/datacollection/plc/write/ack/{specific_part}',
              { request_id, success=true, written_at })
            同时调用 Django API（或直接写 DB）更新 plc_write_record(status=success, acked_at)

T=3~4s   Broker 将回执消息路由至:
         a) 前端 mqtt.js WebSocket 订阅者 → UI 更新（写入成功，绿色对勾）
         b) Django 后端（可选订阅回执 topic）→ 更新 DB

T=3~4s   【端到端延迟约 3~4 秒，满足 ≤10s 要求】

失败路径:
T=0.5~3s   snap7 连接 PLC 超时（如 PLC 掉线）
         → PLCWriteSubscriber: mqtt_publish('.../ack/{specific_part}', { request_id, success=false, error_message="连接超时" })
         → 前端: 参数状态显示"写入失败：连接超时"，重试按钮出现

超时路径:
T=30s   前端计时器触发 → UI 显示"等待超时"，确认按钮恢复
T=60s   后端定时任务扫描 → pending 记录更新为 timeout
```

**延迟可行性论证**（满足 ≤10s 要求）：
- MQTT 发布（后端→Broker）：局域网内，< 50ms
- MQTT 路由（Broker→datacollection）：局域网内，< 50ms
- snap7 PLC 写入：通常 100~500ms（S7 协议，局域网）
- MQTT 回执发布（datacollection→Broker）：< 50ms
- WebSocket 推送（Broker→前端）：< 100ms
- 合计正常路径：约 **0.3~1s**；即使 PLC 响应慢至 3s，总延迟仍在 **≤5s** 以内，远优于 10s 要求。

---

## 5. 对现有代码的影响范围

### 5.1 新增文件

| 文件路径 | 说明 |
|---------|------|
| `FreeArkWeb/backend/freearkweb/api/migrations/0018_plcwriterecord.py` | plc_write_record 表 migration |
| `FreeArkWeb/backend/freearkweb/api/views_device_settings.py` | 设置命令 API views（避免污染现有 views.py） |
| `FreeArkWeb/backend/freearkweb/api/serializers_device_settings.py` | 设置相关 serializers |
| `datacollection/plc_write_subscriber.py` | PLCWriteSubscriber 类（MQTT 订阅 + snap7 写入 + 回执发布） |
| `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue` | 设置面板组件（弹窗/抽屉） |
| `FreeArkWeb/frontend/src/views/PlcWriteRecordView.vue` | 审计日志查询页面（US-9，FR6） |
| `FreeArkWeb/frontend/src/composables/useMqttWebSocket.js` | MQTT-over-WebSocket composable（封装 mqtt.js） |

### 5.2 修改文件

| 文件路径 | 改动内容 |
|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/models.py` | 新增 `PLCWriteRecord` 模型 |
| `FreeArkWeb/backend/freearkweb/api/urls.py` | 注册设置命令接口和审计日志接口路由 |
| `FreeArkWeb/backend/freearkweb/api/views.py` | 可选：导入 views_device_settings（或保持独立）|
| `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 新增"设置"按钮（操作列扩展，约 10 行） |
| `FreeArkWeb/frontend/src/router/index.js`（若存在） | 注册审计日志页面路由 |
| `datacollection/improved_data_collection_manager.py` | 启动时初始化 `PLCWriteSubscriber` 线程 |
| `FreeArkWeb/frontend/package.json` | 新增依赖：`mqtt`（mqtt.js，~200KB gzip，轻量）|

### 5.3 无需改动文件

| 文件路径 | 理由 |
|---------|------|
| `datacollection/plc_write_manager.py` | `PLCWriteManager.write_db_data()` 直接复用，PLCWriteSubscriber 调用它 |
| `plc_config.json` | 地址映射无需改动，直接读取 |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | 无需新配置项（MQTT 地址已有） |
| `FreeArkWeb/backend/freearkweb/freearkweb/wsgi.py` / `asgi.py` | 继续使用 Waitress + WSGI，不引入 ASGI |

---

## 6. 风险与缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Broker 未开启 WebSocket 端口 | 中 | 高（前端无法直连） | 部署前执行检查脚本（见第 8 节）；若不支持，降级为后端轮询方案（3s 轮询） |
| snap7 写入时 PLC 连接不稳定 | 低 | 中（单次写入失败） | 已有重试机制（UI 提供重试按钮）；超时 30s 后提示操作员 |
| mqtt.js 包与现有 Vite 构建冲突 | 低 | 低 | mqtt.js v5.x 原生支持 ESM，与 Vite 兼容；已在同类 Vue 3 项目中验证 |
| PLCWriteSubscriber 线程崩溃导致订阅丢失 | 低 | 中（写命令无人处理） | 线程内加 try/except 自动重连；datacollection 进程本身有监控重启机制 |
| plc_write_record 表写入并发（多用户同时下发） | 低 | 低（Q7：实际不存在） | 每行独立 request_id（UUID），不存在行级冲突 |

---

## 7. 部署说明（生产环境，树莓派 192.168.31.51）

部署流程遵循"plink + git pull"约束：

```bash
# 1. 推送代码到 git
git push origin main

# 2. 通过 plink 在生产服务器执行 git pull
plink -ssh yangyang@192.168.31.51 -pw 123456 \
  "cd /home/yangyang/Freeark/FreeArk && git pull origin main"

# 3. 执行 Django migration（新增 plc_write_record 表）
plink -ssh yangyang@192.168.31.51 -pw 123456 \
  "/home/yangyang/Freeark/FreeArk/venv/bin/python \
   /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py \
   migrate --settings=freearkweb.settings"

# 4. 安装前端新依赖并重新构建
plink -ssh yangyang@192.168.31.51 -pw 123456 \
  "cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend && npm install && npm run build"

# 5. 重启 Waitress 服务（Django 后端）
plink -ssh yangyang@192.168.31.51 -pw 123456 \
  "pkill -f start_waitress_server.py && nohup python ... &"

# 6. 重启 datacollection 进程（新增 PLCWriteSubscriber）
# （按现有 datacollection 进程管理方式重启）
```

---

## 8. 部署前置检查项

### CHECK-01: Broker WebSocket 端口 — 已确认，无需检查

**状态**：已确认（2026-05-19 用户确认），端口为 **32797**。

前端 `mqtt.js` 连接 URL：
```
ws://192.168.31.98:32797/mqtt
```

此项前置检查项已关闭，不再是部署阻塞项。

### CHECK-02: plc_config.json 可写参数白名单验证

确认所有 `*_temp_setting`、`*_switch` 类型的 `param_name` 均在 `plc_config.json` 中有对应条目，避免下发时报"param_name 未定义"错误。

---

## 9. 需求覆盖矩阵

| 需求编号 | 架构组件覆盖 |
|---------|------------|
| FR1 | DeviceManagementDeviceListView.vue（新增"设置"按钮）|
| FR2 | GET /api/device-settings/params/{specific_part}/ + DeviceSettingsPanelView.vue |
| FR3 | POST /api/device-settings/write/ + paho-mqtt publish（Django 后端）|
| FR4 | PLCWriteSubscriber（datacollection）+ PLCWriteManager.write_db_data() |
| FR5 | mqtt.js + useMqttWebSocket.js composable（前端）|
| FR6 | GET /api/device-settings/records/ + PlcWriteRecordView.vue（本期只读，无回滚接口）|
| NFR-1 | 局域网 MQTT 端到端延迟论证（≤5s，远优于 10s 要求）|
| NFR-2 | PLCWriteSubscriber 失败回执 + 前端超时计时器 |
| NFR-3 | request_id UUID 幂等性保证（plc_write_record UNIQUE 约束）|
| NFR-4 | IsAuthenticated（Token Auth，DRF） |
