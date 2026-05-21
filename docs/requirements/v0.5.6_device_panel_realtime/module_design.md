# 模块设计文档

```
file_header:
  document_id: MOD-v0.5.6
  title: 设备面板实时数据刷新 — 模块设计文档
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.6
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/requirements/v0.5.6_device_panel_realtime/architecture_design.md
    - docs/requirements/v0.5.6_device_panel_realtime/requirements_spec.md
```

---

## 模块清单

| 模块 ID | 模块名 | 所在位置 | 变更类型 | 覆盖需求 |
|---------|--------|---------|---------|---------|
| MOD-DC-01 | OndemandCollectSubscriber | `datacollection/ondemand_collect_subscriber.py` | 新增 | REQ-FUNC-001, US-006 |
| MOD-BE-01 | ondemand_refresh 视图 | `FreeArkWeb/backend/freearkweb/api/views.py` | 新增函数 | REQ-FUNC-001, US-005 |
| MOD-BE-02 | URL 路由注册 | `FreeArkWeb/backend/freearkweb/api/urls.py` | 修改 | US-005 |
| MOD-BE-03 | OndemandPLCLatestDataHandler | `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 新增类 | REQ-FUNC-001, US-007, ADR-004 |
| MOD-BE-04 | MQTTConsumer 扩展（ondemand 队列） | `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | 修改 | REQ-FUNC-001, US-007 |
| MOD-FE-01 | DeviceCardsView 改造 | `FreeArkWeb/frontend/src/views/DeviceCardsView.vue` | 修改 | REQ-FUNC-001~004, US-001~004 |
| MOD-DC-02 | ImprovedDataCollectionManager 启动扩展 | `datacollection/improved_data_collection_manager.py` | 修改（start()） | US-006 |

---

## MOD-DC-01：OndemandCollectSubscriber

**文件**：`datacollection/ondemand_collect_subscriber.py`（新建）

**职责**：
1. 通过 paho-mqtt 客户端订阅 `/datacollection/plc/ondemand/request/#`
2. 收到指令后，解析 `specific_part`，在独立线程执行单设备 PLC 数据读取
3. 将采集结果发布至 `/datacollection/plc/ondemand/result/<specific_part>`，格式与周期采集结果完全一致
4. 维护有界待处理队列（maxsize=20），防止并发过载

**类定义**：

```python
class OndemandCollectSubscriber:
    ONDEMAND_REQUEST_TOPIC = '/datacollection/plc/ondemand/request/#'
    ONDEMAND_RESULT_TOPIC_PREFIX = '/datacollection/plc/ondemand/result/'

    def __init__(self,
                 mqtt_broker: str = '192.168.31.98',
                 mqtt_port: int = 32788,
                 max_pending: int = 20):
        # paho client（独立实例，不与 PLCWriteSubscriber 共用）
        # 有界 pending 集合（set，防止同一 specific_part 重复积压）
        # 单线程执行池（concurrent.futures.ThreadPoolExecutor(max_workers=1)）
        ...

    def start(self) -> None:
        """启动 MQTT 客户端循环（loop_start，后台线程）"""

    def stop(self) -> None:
        """停止 MQTT 客户端，等待执行线程退出"""

    def _on_connect(self, client, userdata, flags, rc) -> None:
        """连接成功后订阅 request topic"""

    def _on_message(self, client, userdata, msg) -> None:
        """收到指令消息，解析 specific_part，提交采集任务"""
        # 1. 解析 payload JSON，提取 specific_part
        # 2. 若 specific_part 在 pending 集合中（已有进行中任务），丢弃（防重入）
        # 3. 若 pending 集合已满（maxsize=20），丢弃
        # 4. 将 specific_part 加入 pending 集合，提交 _execute_ondemand(specific_part) 至执行池

    def _execute_ondemand(self, specific_part: str) -> None:
        """在线程池中执行：读取单设备 PLC 数据，发布结果"""
        # 1. 根据 specific_part 定位 PLC IP（从 all_owner.json 或内存映射）
        # 2. 使用 manager._read_single_plc_with_multiple_params() 执行读取
        # 3. 构建与周期采集相同格式的结果 dict
        # 4. 通过 MQTTClient 发布至结果 topic
        # 5. 从 pending 集合中移除 specific_part
        # 6. 若读取失败（PLC 不可达），发布包含 success=false 的结果（让 consumer 感知）

    def _load_owner_ip_map(self) -> dict:
        """加载 specific_part -> plc_ip 映射（复用 all_owner.json / resource/*.json）"""
```

**关键约束**：
- `max_workers=1`：单线程串行处理，避免多个按需采集并发争用同一 PLC 连接
- `pending` 集合为 `set`，同一 `specific_part` 同时只有 1 个采集任务，防重入
- 不与 `TaskScheduler` 的 `PLCManager` 线程池共用（独立的 `PLCReadWriter` 实例）

---

## MOD-DC-02：ImprovedDataCollectionManager.start() 扩展

**文件**：`datacollection/improved_data_collection_manager.py`（修改）

**变更**：在 `start()` 方法中追加 `OndemandCollectSubscriber` 启动：

```python
def start(self):
    self.plc_manager.start()
    logger.info(f"改进版数据收集管理器已启动，线程池大小：{self.max_workers}")
    self._start_plc_write_subscriber()
    self._start_ondemand_collect_subscriber()  # 新增

def _start_ondemand_collect_subscriber(self):
    try:
        from datacollection.ondemand_collect_subscriber import OndemandCollectSubscriber
        self._ondemand_subscriber = OndemandCollectSubscriber(
            mqtt_broker='192.168.31.98',
            mqtt_port=32788,
        )
        self._ondemand_subscriber.start()
        logger.info('OndemandCollectSubscriber 已启动')
    except Exception as e:
        logger.error('OndemandCollectSubscriber 启动失败: %s', e, exc_info=True)
```

**注意**：`_start_ondemand_collect_subscriber` 的失败不能传播到 `start()`，确保主采集链路不受影响。

---

## MOD-BE-01：ondemand_refresh 视图

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`（追加函数）

**函数签名**：

```python
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def device_ondemand_refresh(request):
    """
    POST /api/devices/ondemand-refresh/
    触发指定专有部分的按需 PLC 数据采集。
    向 MQTT broker 发布 /datacollection/plc/ondemand/request/<specific_part>。
    返回 202 Accepted 表示指令已提交（不等待采集完成）。
    """
```

**实现要点**：
1. 从 `request.data` 提取 `specific_part`，校验非空
2. 构建 `paho.mqtt.publish.single()` 调用（或使用共享连接池），发布至 `request topic`
3. 使用 `hostname=settings.MQTT_BROKER`、`port=settings.MQTT_PORT`（从 `mqtt_config.json` 加载，与 MQTTConsumer 保持一致）
4. 返回 `202 Accepted`
5. MQTT 发布异常捕获并返回 `503 Service Unavailable`

**防重入设计（后端请求锁）**：
- 使用进程内 dict `_ondemand_inflight: dict[str, float]`，记录 `specific_part -> 请求时间戳`
- 若同一 `specific_part` 的上次请求距现在 < 25 秒，返回 `202 Accepted` 但不重复发布 MQTT（幂等）
- 避免多用户同时打开同一设备面板导致短时间内多次重复采集

---

## MOD-BE-02：URL 路由注册

**文件**：`FreeArkWeb/backend/freearkweb/api/urls.py`（追加 1 行）

```python
path('devices/ondemand-refresh/', views.device_ondemand_refresh, name='device-ondemand-refresh'),
```

---

## MOD-BE-03：OndemandPLCLatestDataHandler

**文件**：`FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py`（追加类）

**类定义**：

```python
class OndemandPLCLatestDataHandler(PLCLatestDataHandler):
    """按需采集专用 handler：仅写 plc_latest_data，不写 device_param_history。
    
    覆盖 handle()，在调用 _bulk_upsert() 后直接返回，
    不调用 _write_history()，防止 device_param_history 膨胀（ADR-004）。
    """

    def handle(self, topic, payload, building_file=None):
        logger.debug(f"OndemandPLCLatestDataHandler: 处理按需采集消息 - 主题={topic}")
        # 复用父类的 payload 解析逻辑，但仅调用 _bulk_upsert，不调 _write_history
        # 实现方式：复制父类 handle() 中的 record 构建逻辑，在 records 收集完成后
        # 直接调用 self._bulk_upsert(records)，然后 return
        ...
```

**或者**，更简洁的方式——覆盖 `_write_history`，使其成为 no-op：

```python
class OndemandPLCLatestDataHandler(PLCLatestDataHandler):
    def _write_history(self, records):
        """按需采集不写历史（ADR-004）"""
        pass
```

推荐后者，改动量最小，逻辑清晰。

---

## MOD-BE-04：MQTTConsumer 扩展

**文件**：`FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py`（修改）

**变更点一：`__init__` 中新增 ondemand 队列和 handler**

```python
# 新增常量
NUM_ONDEMAND_WORKERS = 1
ONDEMAND_RESULT_TOPIC_PREFIX = '/datacollection/plc/ondemand/result/'
ONDEMAND_DONE_TOPIC_PREFIX = '/datacollection/plc/ondemand/done/'

# __init__ 中追加
self.ondemand_handlers = [
    OndemandPLCLatestDataHandler(),
]
self._ondemand_queue = queue.Queue(maxsize=100)
self._num_ondemand_workers = NUM_ONDEMAND_WORKERS
```

**变更点二：`on_connect` 中订阅 ondemand result topic**

```python
client.subscribe('/datacollection/plc/ondemand/result/#', qos=self.qos)
logger.info("已订阅主题: /datacollection/plc/ondemand/result/# (ondemand 按需采集结果)")
```

**变更点三：`on_message` 路由逻辑**

在消息大小判断前，增加 ondemand topic 路由：

```python
if msg.topic.startswith(self.ONDEMAND_RESULT_TOPIC_PREFIX):
    target_queue = self._ondemand_queue
    queue_name = 'ondemand'
elif msg.topic == self.SCREEN_CONNECTIVITY_TOPIC:
    ...（原有逻辑）
```

**变更点四：`start()` 中启动 ondemand worker**

```python
for i in range(self._num_ondemand_workers):
    t = threading.Thread(
        target=self._ondemand_worker_loop,
        name=f"mqtt-ondemand-worker-{i}",
        daemon=True,
    )
    t.start()
    self._worker_threads.append(t)
logger.info(f"已启动 {self._num_ondemand_workers} 个 ondemand worker")
```

**变量点五：新增 `_ondemand_worker_loop`**

```python
def _ondemand_worker_loop(self):
    """Ondemand worker 主循环：
    - 从 _ondemand_queue 取消息
    - 调用 OndemandPLCLatestDataHandler.handle()（只写 plc_latest_data）
    - 完成后发布 done 通知至 /datacollection/plc/ondemand/done/<specific_part>
    """
    close_old_connections()
    django_connection.ensure_connection()
    thread_name = threading.current_thread().name
    logger.info(f"[{thread_name}] Ondemand worker 启动")

    msg_counter = 0
    while not self.stop_event.is_set() or not self._ondemand_queue.empty():
        try:
            topic, payload_bytes, qos = self._ondemand_queue.get(timeout=1)
        except queue.Empty:
            continue

        t_start = time.monotonic()
        try:
            msg_counter += 1
            if msg_counter % _CLOSE_CONN_EVERY_N == 0:
                close_old_connections()
            django_connection.ensure_connection()

            self._dispatch_ondemand(topic, payload_bytes)
        except Exception as e:
            logger.error(f"[{thread_name}] ondemand 消息处理异常: {e}", exc_info=True)
        finally:
            self._ondemand_queue.task_done()
            elapsed_ms = (time.monotonic() - t_start) * 1000
            logger.info(f"[{thread_name}] ondemand 消息处理完成: topic={topic}, 耗时={elapsed_ms:.1f}ms")

    logger.info(f"[{thread_name}] Ondemand worker 退出")

def _dispatch_ondemand(self, topic: str, payload_bytes: bytes):
    """解码 payload，调用 ondemand handler，完成后发布 done 通知"""
    try:
        payload_str = payload_bytes.decode('utf-8')
        payload = self._safe_json_parse(payload_str)
    except Exception as e:
        logger.error(f"[ondemand] 消息解码/解析失败: {e}")
        return

    # 调用 OndemandPLCLatestDataHandler
    for handler in self.ondemand_handlers:
        try:
            handler.handle(topic, payload)
        except Exception as e:
            logger.error(f"[ondemand] handler 处理失败: {e}", exc_info=True)

    # 提取 specific_part 并发布 done 通知
    specific_part = self._extract_specific_part_from_topic(topic, self.ONDEMAND_RESULT_TOPIC_PREFIX)
    if specific_part:
        self._publish_ondemand_done(specific_part, payload)

def _extract_specific_part_from_topic(self, topic: str, prefix: str) -> str:
    """从 topic 中提取 specific_part（prefix 之后的部分）"""
    if topic.startswith(prefix):
        return topic[len(prefix):]
    return ''

def _publish_ondemand_done(self, specific_part: str, payload: dict):
    """发布 done 通知至 /datacollection/plc/ondemand/done/<specific_part>"""
    # 取 payload 中最大 collected_at 作为通知的时间戳
    collected_at = self._extract_max_collected_at(payload)
    done_topic = f"{self.ONDEMAND_DONE_TOPIC_PREFIX}{specific_part}"
    done_payload = json.dumps({
        "specific_part": specific_part,
        "collected_at": collected_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })
    try:
        self.client.publish(done_topic, done_payload, qos=0)
        logger.info(f"[ondemand] done 通知已发布: topic={done_topic}")
    except Exception as e:
        logger.error(f"[ondemand] done 通知发布失败: {e}")

def _extract_max_collected_at(self, payload: dict) -> str | None:
    """从 payload 中提取所有 timestamp 的最大值"""
    # payload 结构：{device_id: {data: {param: {timestamp: "..."},...},...},...}
    max_ts = None
    if isinstance(payload, dict):
        for device_info in payload.values():
            if isinstance(device_info, dict) and 'data' in device_info:
                for param_data in device_info['data'].values():
                    ts = param_data.get('timestamp') if isinstance(param_data, dict) else None
                    if ts and (max_ts is None or ts > max_ts):
                        max_ts = ts
    return max_ts
```

**变量点六：`stop()` 中等待 ondemand_queue 清空**

在 `stop()` 中将 `_ondemand_queue` 纳入清空等待逻辑（参照 `_energy_queue` 和 `_general_queue` 的处理方式）。

---

## MOD-FE-01：DeviceCardsView.vue 改造

**文件**：`FreeArkWeb/frontend/src/views/DeviceCardsView.vue`

### 变更 1：移除刷新按钮

删除模板中的：
```html
<el-button ... @click="fetchData" class="nav-refresh-btn">
  <el-icon><Refresh /></el-icon>
  刷新
</el-button>
```
并删除相关 `import { Refresh }` 及 `components: { Refresh }`。

### 变更 2：合并 30 秒定时器 + 按需采集

**原有逻辑**：
```javascript
startAutoRefresh() {
  this.refreshTimer = setInterval(() => { this.fetchData() }, 30000)
}
```

**新逻辑**：将 `startAutoRefresh` 改为每 30 秒触发 `triggerOndemandRefresh()`：
```javascript
startAutoRefresh() {
  this.refreshTimer = setInterval(() => { this.triggerOndemandRefresh() }, 30000)
}
```

新增方法：
```javascript
async triggerOndemandRefresh() {
  if (this.ondemandInFlight) return  // 防重入
  this.ondemandInFlight = true
  try {
    await api.post('/api/devices/ondemand-refresh/', {
      specific_part: this.specificPart,
    })
    // 等待 MQTT done 通知触发 fetchData()，不在此处直接 fetchData()
  } catch (e) {
    // 降级：直接读 DB 快照
    console.warn('[DeviceCards] ondemand 请求失败，降级读取 DB:', e)
    await this.fetchData()
  } finally {
    // ondemandInFlight 在收到 done 通知后才重置（见下方 handleOndemandDone）
    // 若超过 20 秒仍未收到 done，超时重置
    this.ondemandTimeoutTimer = setTimeout(() => {
      this.ondemandInFlight = false
    }, 20000)
  }
}
```

### 变更 3：MQTT WebSocket 订阅 done 通知

在 `data()` 中新增：
```javascript
ondemandInFlight: false,
ondemandTimeoutTimer: null,
mqttClient: null,
```

新增方法：
```javascript
connectMqttDone() {
  const topic = `/datacollection/plc/ondemand/done/${this.specificPart}`
  const { connect, disconnect } = useMqttWebSocket(topic, this.handleOndemandDone)
  this._mqttDisconnect = disconnect
  connect()
},

disconnectMqttDone() {
  if (this._mqttDisconnect) {
    this._mqttDisconnect()
    this._mqttDisconnect = null
  }
},

handleOndemandDone({ payload }) {
  try {
    const data = JSON.parse(payload)
    if (data.specific_part !== this.specificPart) return
    // 清除超时计时器，重置 inFlight 标志
    if (this.ondemandTimeoutTimer) {
      clearTimeout(this.ondemandTimeoutTimer)
      this.ondemandTimeoutTimer = null
    }
    this.ondemandInFlight = false
    // 拉取最新数据
    this.fetchData()
  } catch {
    // JSON 解析失败，忽略
  }
},
```

在 `mounted()` 中：
```javascript
mounted() {
  if (this.specificPart) {
    this.fetchData()
    this.triggerOndemandRefresh()  // 打开即触发一次
    this.startAutoRefresh()
    this.connectMqttDone()
  }
},
```

在 `beforeUnmount()` 中：
```javascript
beforeUnmount() {
  this.stopAutoRefresh()
  this.disconnectMqttDone()
  if (this.ondemandTimeoutTimer) clearTimeout(this.ondemandTimeoutTimer)
},
```

### 变更 4：统一时间戳显示

**计算属性**（新增）：
```javascript
computed: {
  ...
  lastUpdatedAt() {
    let maxTs = null
    for (const groupData of Object.values(this.deviceData)) {
      for (const subTypeData of Object.values(groupData.sub_types || {})) {
        for (const param of (subTypeData.params || [])) {
          if (param.collected_at && (!maxTs || param.collected_at > maxTs)) {
            maxTs = param.collected_at
          }
        }
      }
    }
    return maxTs || null
  },
}
```

**模板变更**：

在模板 `<div class="panel-footer">` 处更新：
```html
<div class="panel-footer" v-if="hasData">
  <el-text type="info" size="small">
    上次数据更新于：{{ lastUpdatedAt || '—' }}
  </el-text>
</div>
```

同时，移除各 `col-header` 内的 `<span class="col-time">{{ getCollectedAt(subTypeData.params) }}</span>`（或置为不渲染）。

### 变更 5：loading 状态

在 `triggerOndemandRefresh()` 进行中时，不使用全局 `loading`（避免骨架屏遮挡已有数据），改为顶部导航栏右侧显示一个小圆形进度指示器（`el-icon loading`）。

---

## 模块间接口矩阵

| 调用方 | 被调用方 | 接口类型 | 数据 |
|--------|---------|---------|------|
| DeviceCardsView | `POST /api/devices/ondemand-refresh/` | HTTP POST | `{specific_part}` |
| views.device_ondemand_refresh | MQTT Broker | MQTT publish | `/datacollection/plc/ondemand/request/<sp>` |
| OndemandCollectSubscriber | MQTT Broker | MQTT subscribe | `/datacollection/plc/ondemand/request/#` |
| OndemandCollectSubscriber | ImprovedDataCollectionManager (PLCManager) | 方法调用 | 单设备读取 |
| OndemandCollectSubscriber | MQTT Broker | MQTT publish | `/datacollection/plc/ondemand/result/<sp>` |
| MQTTConsumer._ondemand_worker_loop | OndemandPLCLatestDataHandler.handle() | 方法调用 | MQTT payload dict |
| OndemandPLCLatestDataHandler | PLCLatestData ORM | Django ORM | bulk_create (upsert) |
| MQTTConsumer._dispatch_ondemand | MQTT Broker | MQTT publish | `/datacollection/plc/ondemand/done/<sp>` |
| DeviceCardsView.handleOndemandDone | fetchData() | 方法调用 | 内部 |
| fetchData() | `GET /api/devices/realtime-params/` | HTTP GET | `{specific_part}` |

---

## 不变模块（受保护）

以下模块**不做任何修改**：

| 模块 | 理由 |
|------|------|
| `PLCDataHandler` | 只处理 energy 参数的 `plc_data` 表写入，与按需采集无关 |
| `ConnectionStatusHandler` | 已在 v0.5.5 P2 优化，按需采集不触发连接状态更新 |
| `PLCLatestDataHandler._write_history()` | 继承后覆盖，原类不变 |
| `TaskScheduler` | 周期采集链路完全独立，不修改 |
| `energy_queue` / `general_queue` | 完全不变 |
| `PLCWriteSubscriber` | 不变 |
| 其他视图和 URL | 不修改 |
