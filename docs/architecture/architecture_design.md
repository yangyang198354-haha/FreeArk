# 架构设计文档

**文档编号**: ARCH-DESIGN-DEVICE-SETTINGS-001  
**项目名称**: FreeArk 设备参数设置功能  
**版本**: 0.4.0-APPROVED  
**状态**: APPROVED（v0.4.0：2026-05-19 P1~P5 诊断方向 + Q10~Q12 落地方案；PM 门控通过）  
**创建日期**: 2026-05-19  
**最后更新**: 2026-05-19  
**作者**: system-architect (via pm-orchestrator)  
**审核**: pm-orchestrator（v0.4.0 增量 ADR 门控通过）  
**输入文档**: REQ-SPEC-DEVICE-SETTINGS-001 v0.4.0-APPROVED, REQ-US-DEVICE-SETTINGS-001 v0.4.0-APPROVED

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

---

## v0.4.0 增量调整（基于用户决策 Q10~Q12 + 生产实测问题 P1~P5）

**本节为增量 ADR，不修改 v0.3.0 已有架构。仅描述 P1~P5 的诊断方向与落地方案。**

---

### P1 — 枚举下拉菜单空值：诊断方向

**现象**：生产环境"系统开关"等枚举类下拉菜单无选项。

**代码调研**（已 Read `views_device_settings.py` + `models.py`）：

后端 `device_settings_params` 视图（第 47~49 行）匹配逻辑：
```python
attr_tags = [c.param_name for c in configs]
attr_defs = {
    d.attr_tag: d
    for d in DeviceAttrDef.objects.filter(attr_tag__in=attr_tags)
}
```

前端 `parseSelectOptions`（`DeviceSettingsPanelView.vue` 第 213~226 行）解析逻辑：
```javascript
const parsed = JSON.parse(json)
if (Array.isArray(parsed)) {
    return parsed.map(item =>
        typeof item === 'object' ? item : { label: String(item), value: item }
    )
}
return []  // 非数组格式返回空
```

**3 个最可能的根因假设（按可能性排序）**：

1. **假设 H1（最可能）：`DeviceAttrDef.select_values_json` 数据为空或格式不匹配**
   - 生产数据库中，`*_switch` 类参数对应的 `DeviceAttrDef` 行的 `select_values_json` 字段为空字符串或 `null`，或格式为非数组 JSON（如 `{"0":"关","1":"开"}` 而非 `[{"label":"关","value":0}]`）
   - 前端 `parseSelectOptions` 仅处理数组格式，若 DB 中存的是对象格式则返回 `[]`
   - **建议自查路径**：`SELECT attr_tag, select_values_json FROM device_attr_def WHERE attr_tag LIKE '%_switch%';`

2. **假设 H2（次可能）：`attr_tag` ≠ `DeviceConfig.param_name`，导致 JOIN 失败**
   - `views_device_settings.py` 用 `DeviceConfig.param_name` 当作 `attr_tag` 查 `DeviceAttrDef`，但生产 DB 中两表命名体系存在不一致（如 `living_room_switch` vs `hvac_switch`）
   - 结果 `attr_defs.get(cfg.param_name)` 返回 `None`，前端收到 `select_values_json: ''`，下拉为空
   - **建议自查路径**：对比 `SELECT DISTINCT param_name FROM device_config WHERE param_name LIKE '%_switch%'` 与 `SELECT DISTINCT attr_tag FROM device_attr_def WHERE attr_tag LIKE '%_switch%'`，检查是否有命名差异

3. **假设 H3（较低）：`DeviceAttrBinding` 限制了 `product_code` 过滤，导致漏查**
   - 当前视图未使用 `DeviceAttrBinding` 过滤 `product_code`，直接按 `attr_tag` 全局匹配。若未来引入 `product_code` 过滤，可能遗漏匹配。当前代码不存在此问题，但若 `DeviceAttrDef` 中同一 `attr_tag` 有多个 `product_code` 行，查询可能返回错误行（`dict` 后者覆盖前者）
   - **建议自查路径**：`SELECT attr_tag, count(*) FROM device_attr_def GROUP BY attr_tag HAVING count(*) > 1;`

**开发自查优先顺序**：H1 → H2 → H3。P1 不需要架构重设计，只需数据修复或命名规范对齐。

---

### P2 — 下发通道异常：诊断方向（端到端链路检查）

**现象**：v0.3.0 生产环境下发命令后无回执，链路不通。

**代码调研结论**：
- `mqtt_consumer.py` 已正确订阅 `/datacollection/plc/write/ack/#`（第 129~130 行），`process_message` 正确路由至 `_handle_write_ack`（第 422~423 行）
- `datacollection/plc_write_subscriber.py` 已存在且正确订阅 `COMMAND_TOPIC`（第 59 行），`_on_command` 已实现（第 63 行）
- `views_device_settings.py` publish 逻辑存在：通过 `mqtt_consumer.client.publish()` 发布（第 128~130 行），但使用的是 `mqtt_consumer` 模块的单例客户端

**端到端链路节点 + 建议诊断日志位置**：

| 节点 | 文件 | 建议在此处加 DEBUG 日志的位置 | 诊断问题 |
|------|------|-------------------------------|---------|
| 1. API 接收请求 | `views_device_settings.py` L82 | `logger.info('收到下发请求: sp=%s param=%s val=%s', specific_part, param_name, new_value)` | 请求是否到达后端 |
| 2. MQTT publish 调用 | `views_device_settings.py` L127~131 | `logger.info('mqtt publish 结果: rc=%s mid=%s', result.rc, result.mid)` | publish 是否成功（rc=0 才算成功） |
| 3. 验证 `mqtt_consumer.client` 是否已连接 | `views_device_settings.py` `_get_mqtt_client()` | `logger.info('mqtt client state: %s', client._state)` | 共享 client 是否处于 connected 状态 |
| 4. Broker 路由至 PLCWriteSubscriber | `datacollection/plc_write_subscriber.py` L63 | `logger.info('_on_command 触发: topic=%s', topic)` 已有 L106 error 日志，需补充 L63 入口日志 | 命令是否到达 subscriber |
| 5. PLCWriteSubscriber PLC 写入 | `datacollection/plc_write_subscriber.py` L108 | `logger.info('_write_plc: ip=%s db=%s offset=%s val=%s type=%s', plc_ip, db_num, offset, value, data_type)` | snap7 参数是否正确 |
| 6. 回执发布 | `datacollection/plc_write_subscriber.py` L121 | `logger.info('_publish_ack: topic=%s success=%s', topic, success)` 已有（第 136 行） | 回执是否发出 |
| 7. 后端收到回执 | `mqtt_consumer.py` `_handle_write_ack` L369 | `logger.info('_handle_write_ack: request_id=%s success=%s', request_id, success)` 已有（第 392 行） | 回执是否到达后端 |

**最可能的 P2 根因**（不修改架构，先加日志定位）：

- **高优先级怀疑**：`_get_mqtt_client()` 返回的 `mqtt_consumer.client` 在生产环境中可能尚未连接（Django 进程启动后 MQTT 连接是异步建立的），导致 `publish` 调用时 client 处于未连接状态，`result.rc != 0`，但当前错误日志（`'下发通道异常'`）不区分 rc 值。建议：在 `device_settings_write` 的 except 块中打印 `result.rc` 具体值（而非仅判断 `!= 0`），并在 `_get_mqtt_client()` 中检查 `client.is_connected()`。

- **次要怀疑**：PLCWriteSubscriber 进程（`freeark-task-scheduler` systemd 服务）订阅的 MQTT broker 地址/端口与后端不一致。`mqtt_consumer.py` 默认 broker 为 `192.168.31.97:32795`（fallback），而 `plc_write_subscriber.py` 从 `freeark-task-scheduler` 启动参数传入。若两者连接不同 broker instance，命令到不了 subscriber。

---

### P3 — 人类可读映射：后端常量文件落地方案（ADR-06）

**决策**（Q11 已确认）：后端 Python 常量文件，无 DB migration。

**新建文件**：`FreeArkWeb/backend/freearkweb/api/param_value_label.py`

**建议结构**（基于 Read `plc_config.json` + `DeviceConfig.param_name` 命名约定）：

```python
# param_value_label.py
# 维护 param_name 枚举型字段的 PLC 原始值 ↔ 人类可读标签映射
# 格式：{ param_name_suffix_pattern: { raw_value_str: human_label } }
# 匹配规则：param_name 以 key 结尾时应用对应映射

SWITCH_LABELS = {"0": "关", "1": "开"}

PARAM_VALUE_LABELS = {
    "_switch": SWITCH_LABELS,                    # 所有 *_switch 参数
    "_mode": {"0": "制冷", "1": "制热", "2": "通风", "3": "除湿"},  # 如有模式字段
}

PARAM_UNITS = {
    "_temp_setting": "℃",
    "_temperature": "℃",
    "_humidity": "%RH",
}

def get_value_options(param_name: str) -> list[dict]:
    """返回 [{raw: '0', label: '关'}, {raw: '1', label: '开'}] 或 []"""
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return [{"raw": k, "label": v} for k, v in mapping.items()]
    return []

def get_display_value(param_name: str, raw_value) -> str:
    """将 PLC 原始值转换为人类可读字符串"""
    if raw_value is None:
        return "—"
    raw_str = str(raw_value)
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return mapping.get(raw_str, raw_str)
    unit = ""
    for suffix, u in PARAM_UNITS.items():
        if param_name.endswith(suffix):
            unit = f" {u}"
            break
    return f"{raw_str}{unit}"
```

**API 响应变更**（`GET /api/device-settings/params/{specific_part}/`）：

每个参数增加两个字段（P5 过滤后仅返回 `is_writable=true` 的参数，但 `display_value` 和 `value_options` 对所有返回字段均有效）：

```json
{
  "param_name": "living_room_switch",
  "display_name": "客厅系统开关",
  "current_value": "1",
  "display_value": "开",
  "is_writable": true,
  "attr_value_type": 1,
  "value_options": [{"raw": "0", "label": "关"}, {"raw": "1", "label": "开"}],
  "select_values_json": "[{\"value\":0,\"label\":\"关\"},{\"value\":1,\"label\":\"开\"}]"
}
```

**影响范围**：仅 `views_device_settings.py`（追加两字段组装逻辑），无 DB migration，无 model 变化。

---

### P4 — 批量下发协议：ADR-07

**决策**（Q10 已确认）：一条 MQTT 命令多 item，单个 `request_id`。

#### MQTT Command Payload Schema（v0.4.0）

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "specific_part": "3-1-7-702",
  "plc_ip": "192.168.31.50",
  "operator": "admin",
  "submitted_at": "2026-05-19T10:30:00Z",
  "items": [
    { "param_name": "living_room_switch", "new_value": "1", "data_type": "int16" },
    { "param_name": "living_room_temp_setting", "new_value": "24", "data_type": "int16" }
  ]
}
```

#### MQTT Ack Payload Schema — 推荐方案：按 request_id 整体回执，含 items[].success

架构师评估两方案：

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A（推荐）** 整体回执含 items | `{ request_id, success: bool, items: [{param_name, success, error_message}] }` | 一条回执即可知道每个 item 结果，前端处理简单 | item 数量多时 payload 略大（可接受） |
| B 每个 item 单独回执 | 每个 `param_name` 单独发一条 ack，`request_id` 相同 | 与 v0.3.0 兼容，PLCWriteSubscriber 改动最小 | 前端需等待 N 条消息聚合，增加状态管理复杂度 |

**选定方案 A**（整体回执）：

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "specific_part": "3-1-7-702",
  "success": false,
  "written_at": "2026-05-19T10:30:02Z",
  "items": [
    { "param_name": "living_room_switch", "success": true },
    { "param_name": "living_room_temp_setting", "success": false, "error_message": "PLC_WRITE_FAILED: snap7 timeout" }
  ]
}
```

#### plc_write_record DB 方案：1 request_id 对应 N 行

**决策**：保持每个 `param_name` 独立一行 `plc_write_record`，共用同一 `request_id`，不新增 `batch_id` 字段。

**理由**：
- 现有 `plc_write_record` 表已有 `request_id` 字段（`UNIQUE` 约束），需放宽为 `UNIQUE` 仅对单 `(request_id, param_name)` 组合生效，或改为非唯一索引（批量时同一 request_id 对应多行）
- `request_id` 本身即可作为"批次 ID"使用，无需新增 `batch_id`，零额外 migration 字段
- 审计页按 `request_id` 分组即可查看一次批量操作的所有记录
- **Migration 需求**：需将 `plc_write_record.request_id` 的 `UNIQUE` 约束改为普通索引（允许同一 `request_id` 对应多行）；或新增 `batch_request_id` 非唯一字段并保留 `request_id` 不变（后者零 schema 风险，推荐）

**推荐做法（零风险）**：新增 `batch_request_id VARCHAR(64) NULL` 字段，单字段下发时 `batch_request_id=NULL`，批量下发时所有 item 共用同一 `batch_request_id`，每行 `request_id` 仍保持 UUID 唯一。这样无需修改 `UNIQUE` 约束，migration 仅追加新字段。

#### 后端 API 接口变更

`POST /api/device-settings/write/` 请求体改为：

```json
{
  "specific_part": "3-1-7-702",
  "items": [
    { "param_name": "living_room_switch", "new_value": "1" },
    { "param_name": "living_room_temp_setting", "new_value": "24" }
  ]
}
```

响应 202：

```json
{
  "batch_request_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_count": 2,
  "status": "pending"
}
```

#### PLCWriteSubscriber 改造

`_on_command` 需迭代 `cmd['items']`，对每个 item 调用 `_write_plc`，汇总结果后发布整体 ack。

---

### P5 — 只显示可写参数：过滤位置建议（ADR-08）

**决策**：**后端过滤**（不返回 `is_writable=false` 的参数），前端不渲染只读参数。

**理由**：
- 防止前端通过绕过 UI 直接调用 `POST /write/` 接口写只读字段（纵深防御）
- 后端 `device_settings_params` 视图已有 `_is_writable()` 函数，只需在组装 `params` 列表时过滤 `is_writable=False` 的行，约 1 行改动
- 前端组件 `DeviceSettingsPanelView.vue` 中现有 `v-if="row.is_writable"` 判断可简化（后端已过滤，但前端 guard 保留以防万一）

**实现位置**：`views_device_settings.py` `device_settings_params` 函数内，在 `groups[key]['params'].append(...)` 之前加条件判断：
```python
if not _is_writable(cfg.param_name):
    continue  # P5：设置面板不返回只读参数
```

---

### v0.4.0 增量变更对生产已运行模块的影响范围

| 文件 / 模块 | 影响类型 | 变更描述 | 风险 |
|------------|---------|---------|------|
| `api/param_value_label.py` | **新增** | P3 映射常量文件，零副作用 | 低 |
| `api/views_device_settings.py` | **修改** | 1) P5：添加 `is_writable` 过滤（1行）；2) P3：追加 `display_value` + `value_options` 字段；3) P4：接口改接收 `items` 数组；4) P2：`_get_mqtt_client()` 加连接状态检查 | 中（接口协议变化，前端需同步更新） |
| `api/serializers_device_settings.py` | **修改** | `DeviceSettingWriteSerializer` 改为接受 `items` 数组而非单 `param_name/new_value` | 中 |
| `datacollection/plc_write_subscriber.py` | **修改** | P4：`_on_command` 改为迭代 `items`，`_publish_ack` 改为发整体 ack；P2：入口增加 DEBUG 日志 | 中（已在线，需重启 `freeark-task-scheduler`） |
| `api/mqtt_consumer.py` | **不变** | `_handle_write_ack` 已存在且正确；P2 诊断日志在上层视图加，此处无需改 | 无 |
| `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue` | **修改** | P3：`parseSelectOptions` 改用 `value_options`；P4：合并提交逻辑；P5：移除前端侧 `is_writable` filter（后端已过滤）；P2：错误分类展示 | 中 |
| `api/migrations/` | **新增（可选）** | 若采用 `batch_request_id` 方案需新增 migration 追加字段（Q12 无 migration，Q11 无 migration） | 低 |
| `api/models.py` | **可选修改** | 若新增 `batch_request_id` 字段则需修改 `PLCWriteRecord` model | 低 |
| v0.3.0 已部署文件（`views_device_settings.py`, `plc_write_subscriber.py`, `useMqttWebSocket.js`, `DeviceSettingsPanelView.vue`）| 均需升级 | v0.4.0 为增量修改，不推翻 v0.3.0 实现，仅在现有基础上扩展 | 中（需全量测试回归） |

---

---

## 用户最终决策（2026-05-19，PM 补录）

D1：本期上线 batch_request_id migration 0024（可空字段，migration 追加）。
D2：不做 API 兼容，同步部署前后端（破坏性变更，旧单字段接口废弃）。
D3：SUBSCRIBER_NOT_CONSUMING 仅前端 30s 超时推断，后端不实现服务端定时扫描；前端 timeout 文案改为"PLC 写入模块未响应（30s 超时），请检查 freeark-task-scheduler 服务"。

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
