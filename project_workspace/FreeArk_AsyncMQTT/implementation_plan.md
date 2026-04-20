# Implementation Plan — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_software_developer, status=APPROVED, version=1.0 -->

## 变更摘要

修改文件：`FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py`
未修改文件：`mqtt_handlers.py`（handler 接口不变）

## 关键变更点

### 1. 新增 import
```python
import queue  # 新增，用于 queue.Queue 和 queue.Full
```

### 2. __init__ 新增参数和属性
```python
def __init__(self, num_workers=4, queue_maxsize=2000):
    ...
    self._msg_queue = queue.Queue(maxsize=queue_maxsize)
    self._num_workers = num_workers
    self._worker_threads = []
    self.stop_event = threading.Event()
```

### 3. on_message 完全重写（核心修改）
原来：close_old_connections() + 解码 + JSON 解析 + process_message（阻塞 200-400ms）
现在：put_nowait((topic, payload, qos))，< 1ms 返回

### 4. 新增 _dispatch 方法
承接原 on_message 的全部解码/解析/分发逻辑，在 worker 线程中调用。

### 5. 新增 _worker_loop 方法
Worker 线程主循环，处理 stop_event + queue.get + _dispatch + task_done。

### 6. start() 修改
在 paho loop_start() 之前启动 N 个 mqtt-worker-{i} 线程。

### 7. stop() 重写
实现优雅关闭：stop_event.set → loop_stop/disconnect → 等待队列清空(30s) → worker join → db_maintenance join。

## 向后兼容性

- `start_mqtt_consumer()` / `stop_mqtt_consumer()` 函数签名不变
- `process_message()` 逻辑不变（完整保留重试机制）
- `_db_maintenance_thread()` 逻辑不变
- 全局 `mqtt_consumer = MQTTConsumer()` 不变
