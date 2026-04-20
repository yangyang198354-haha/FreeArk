# Architecture Design — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_system_architect, status=APPROVED, version=1.0 -->

## 1. 架构决策

### ADR-001: 线程模型选择 — ThreadPoolExecutor vs 手动 Thread

**问题**: 如何实现 worker 线程池？

**方案 A: `concurrent.futures.ThreadPoolExecutor`**
- 优点: 标准库，自动线程复用，shutdown(wait=True) 语义清晰
- 缺点: 不直接控制每个线程的生命周期初始化

**方案 B: 手动 `threading.Thread` + `queue.Queue`**
- 优点: 完全控制线程初始化（可在线程启动时调用 close_old_connections）
- 缺点: 需要手动管理线程生命周期

**决策**: 采用方案 B（手动 Thread）。
原因：Django ORM 的 thread-local connection 要求每个 worker 线程在启动时执行
`close_old_connections()`，手动 Thread 可以在 `_worker_loop` 入口直接调用，
逻辑更清晰；ThreadPoolExecutor 的线程复用特性反而需要在每次任务开始时重复调用，
不如一次性在线程入口初始化直观。实际上两种方案均可行，选 B 是风格优先而非技术必要。

### ADR-002: 队列满时策略 — 丢弃 vs 阻塞

**问题**: 队列满时如何处理新消息？

**方案 A: `put_nowait` + 丢弃 + WARNING**
- 优点: 网络线程绝对不阻塞，MQTT 连接不受影响
- 缺点: 可能丢弃少量消息（但 general 组 634 条消息在正常 worker 处理速度下不会触发）

**方案 B: `put(block=True, timeout=0.1)` + 短超时放弃**
- 优点: 给队列轻微缓冲机会
- 缺点: 仍可能阻塞网络线程 100ms，不满足 REQ-FUNC-001

**决策**: 采用方案 A（put_nowait + 丢弃）。队列容量 2000 条，在 4 个 worker 线程
并发处理下（每条约 200-400ms），吞吐量约 10-20 条/s，而 634 条消息发布间隔 20ms，
整批到达约 12.7s，不触发满状态。

### ADR-003: 优雅关闭实现

**问题**: 如何确保 SIGTERM 时队列已消费完毕？

**方案 A: `queue.join()` + `task_done()`**
- 语义精确，`join()` 阻塞直到所有 `task_done()` 调用匹配
- 需要每条消息处理完成后调用 `task_done()`

**方案 B: stop_event + 队列空检查轮询**
- 实现简单，worker 检测 `stop_event.is_set() and queue.empty()`

**决策**: 采用方案 A（queue.join），语义最精确，避免 race condition。

## 2. 组件架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    MQTTConsumer (主类)                           │
│                                                                  │
│  ┌──────────────┐    put_nowait    ┌────────────────────────┐  │
│  │ paho 网络线程 │ ──────────────→ │  queue.Queue(2000)     │  │
│  │  on_message  │  (< 1ms 返回)   │  (msg_topic, payload,  │  │
│  └──────────────┘                  │   qos)                 │  │
│                                    └──────────┬─────────────┘  │
│                                               │ get(timeout=1)  │
│                                    ┌──────────▼─────────────┐  │
│                                    │   Worker 线程 x4       │  │
│                                    │  _worker_loop()         │  │
│                                    │  - close_old_conns()   │  │
│                                    │  - _dispatch(topic,    │  │
│                                    │    payload_bytes)      │  │
│                                    │  - task_done()         │  │
│                                    └──────────┬─────────────┘  │
│                                               │                  │
│                                    ┌──────────▼─────────────┐  │
│                                    │     Handlers           │  │
│                                    │  PLCDataHandler        │  │
│                                    │  ConnectionStatusHdlr  │  │
│                                    │  PLCLatestDataHandler  │  │
│                                    └────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ db_maintenance_thread (300s 保活，独立线程，保持原逻辑)     │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 线程模型

| 线程名称 | 数量 | 职责 | DB 连接管理 |
|---------|------|------|------------|
| paho 网络线程 | 1 | on_message 入队 | 无 DB 操作 |
| mqtt-worker-0..3 | 4 | 消息解码 + handler 分发 + DB 写入 | 每条消息前 close_old_connections() |
| db-maintenance | 1 | 300s 保活检查（原逻辑） | 原有逻辑不变 |

## 4. 数据流

```
EMQX → paho on_message(topic, payload_bytes)
    → try put_nowait((topic, payload_bytes, qos))
        成功: 返回 (< 1ms)
        失败(Full): logger.warning + 返回 (< 1ms)

队列 → worker._worker_loop()
    → close_old_connections()
    → topic, payload_bytes, qos = queue.get(timeout=1)
    → _dispatch(topic, payload_bytes)
        → payload_str = payload_bytes.decode('utf-8')
        → payload = _safe_json_parse(payload_str)
        → process_message(topic, payload)
            → handler.handle(topic, payload, building_file) x3
    → queue.task_done()

stop() → stop_event.set()
    → queue.join()  # 等待所有 task_done()
    → [workers 自然退出]
    → client.loop_stop()
    → client.disconnect()
    → db_maintenance_running = False
```

## 5. 关键接口

```python
class MQTTConsumer:
    # 新增属性
    _msg_queue: queue.Queue          # maxsize=2000, 存储 (topic_str, payload_bytes, qos_int)
    _worker_threads: list[threading.Thread]  # 4个 worker 线程
    _num_workers: int                # 默认 4
    stop_event: threading.Event     # 停止信号

    # 变更方法
    def on_message(self, client, userdata, msg) -> None:
        """仅入队，< 1ms 返回"""

    def _worker_loop(self) -> None:
        """Worker 线程入口，消费队列"""

    def _dispatch(self, topic: str, payload_bytes: bytes) -> None:
        """原 on_message 中的解码+process_message 逻辑"""

    def start(self) -> bool:
        """启动 worker 线程 + db_maintenance_thread + paho loop"""

    def stop(self) -> bool:
        """优雅关闭：queue.join() + stop_event.set() + executor shutdown"""
```

## 6. 错误处理策略

| 错误场景 | 处理方式 |
|---------|---------|
| 队列满 | put_nowait 捕获 queue.Full，记录 WARNING，继续 |
| payload 解码失败 | _dispatch 内捕获，记录 ERROR，task_done()，继续下一条 |
| handler DB 错误 | 原有 process_message 重试逻辑保留，由 worker 线程执行 |
| worker 未预期异常 | except Exception + ERROR 日志，task_done()，线程不退出 |
| stop 超时 | queue.join(timeout=30s)，超时记录 WARNING 强制退出 |
