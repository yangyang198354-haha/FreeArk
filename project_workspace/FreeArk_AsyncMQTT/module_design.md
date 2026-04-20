# Module Design — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_system_architect, status=APPROVED, version=1.0 -->

## 模块: mqtt_consumer.py (修改)

### 变更清单

| 方法/属性 | 变更类型 | 说明 |
|----------|---------|------|
| `__init__` | 修改 | 新增 `_msg_queue`、`_worker_threads`、`stop_event`、`_num_workers` |
| `on_message` | 重写 | 移除所有 DB 逻辑，仅 `put_nowait((topic, payload_bytes, qos))` |
| `_dispatch` | 新增 | 原 on_message 的解码 + `_safe_json_parse` + `process_message` 逻辑 |
| `_worker_loop` | 新增 | Worker 线程入口，loop `queue.get` → `_dispatch` → `task_done` |
| `start` | 修改 | 额外启动 N 个 worker 线程 |
| `stop` | 修改 | 先 `stop_event.set()` + `queue.join(timeout=30)` 再 paho 停止 |
| `process_message` | 不变 | 保留原有重试 + handler 分发逻辑 |
| `_safe_json_parse` | 移至 `_dispatch` 调用 | 不修改方法本身 |
| `_check_and_reconnect_db` | 不变 | 保留 |
| `_db_maintenance_thread` | 不变 | 保留 |

### 属性定义

```python
# 新增属性（在 __init__ 中初始化）
self._msg_queue = queue.Queue(maxsize=2000)
self._num_workers = 4
self._worker_threads = []
self.stop_event = threading.Event()
```

### _worker_loop 伪代码

```python
def _worker_loop(self):
    close_old_connections()  # 每个线程独立初始化 DB 连接
    thread_name = threading.current_thread().name
    logger.info(f"{thread_name} 启动")
    while not self.stop_event.is_set() or not self._msg_queue.empty():
        try:
            topic, payload_bytes, qos = self._msg_queue.get(timeout=1)
        except queue.Empty:
            continue
        try:
            self._dispatch(topic, payload_bytes)
        except Exception as e:
            logger.error(f"{thread_name} 处理消息异常: topic={topic}, {e}", exc_info=True)
        finally:
            self._msg_queue.task_done()
    logger.info(f"{thread_name} 退出")
```

### _dispatch 伪代码

```python
def _dispatch(self, topic: str, payload_bytes: bytes):
    close_old_connections()
    # UTF-8 解码（原 on_message 逻辑）
    try:
        payload_str = payload_bytes.decode('utf-8')
    except UnicodeDecodeError:
        payload_str = payload_bytes.decode('latin-1')
    # JSON 解析（调用现有 _safe_json_parse）
    payload = self._safe_json_parse(payload_str)
    # 记录 debug 日志（原 on_message 中的摘要日志）
    # 调用 process_message
    self.process_message(topic, payload)
```

### on_message 重写

```python
def on_message(self, client, userdata, msg):
    try:
        self._msg_queue.put_nowait((msg.topic, msg.payload, msg.qos))
        logger.debug("消息入队: topic=%s, size=%d", msg.topic, len(msg.payload))
    except queue.Full:
        logger.warning("消息队列已满，丢弃消息: topic=%s", msg.topic)
```

### stop 修改

```python
def stop(self):
    logger.info("停止 MQTT 消费者，等待队列清空...")
    self.stop_event.set()
    # 等待队列中所有消息处理完成（最长 30s）
    try:
        self._msg_queue.join()
    except Exception:
        logger.warning("queue.join 无 timeout 参数，改用轮询等待")
        # 备选：轮询
        deadline = time.time() + 30
        while not self._msg_queue.empty() and time.time() < deadline:
            time.sleep(0.5)
    # 等待 worker 线程退出
    for t in self._worker_threads:
        t.join(timeout=5)
    # 停止 paho
    self.client.loop_stop()
    self.client.disconnect()
    # 停止 db_maintenance
    self.db_maintenance_running = False
    if self.db_maintenance_thread:
        self.db_maintenance_thread.join(timeout=5)
```

## 模块: mqtt_handlers.py (不修改)

handler 接口 `handle(topic, payload, building_file)` 保持不变，
由 worker 线程中的 `_dispatch → process_message` 调用，无需感知线程模型变化。
