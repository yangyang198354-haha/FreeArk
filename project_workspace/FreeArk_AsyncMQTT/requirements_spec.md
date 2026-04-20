# Requirements Specification — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_requirement_analyst, status=APPROVED, version=1.0 -->

## 1. 背景与问题陈述

FreeArk 能耗采集平台的 `mqtt_consumer.py` 使用 paho-mqtt `loop_start()` 模式。
该模式下网络 I/O 与 `on_message` 回调共享同一网络线程。当 general 组 634 台设备
消息同时涌入时，`on_message` 内的同步 DB 操作（200-400ms/条）将网络线程阻塞
2-4 分钟，paho 无法发送 PINGREQ，EMQX 以 rc=16（MQTT_ERR_KEEPALIVE）断开连接，
QoS 0 下断连期间消息永久丢失，`plc_latest_data` 停止更新。

## 2. 利益相关方

| 角色 | 关注点 |
|------|--------|
| 运维/开发（杨洋） | 服务稳定性、SIGTERM 优雅退出、无外部依赖 |
| 平台用户 | 前端设备面板数据实时性（600s 内更新） |
| 生产服务器 | 树莓派物理机，Python 3.13，Django 5.2，无 Docker |

## 3. 功能需求

### REQ-FUNC-001: 网络线程零阻塞
**来源**: Bug 根因分析（on_message 阻塞导致 PINGREQ 无法发送）
**描述**: `on_message` 回调必须在收到消息后立即完成（目标 < 1ms），仅执行
payload 解码和入队，不执行任何 I/O 操作。
**AC（Given/When/Then）**:
- Given: EMQX broker 连接正常，消息队列未满
- When: `on_message` 被 paho 网络线程调用
- Then: 方法在 1ms 内返回，payload 已放入内部队列

### REQ-FUNC-002: 独立 Worker 线程池消费消息
**来源**: 技术约束（标准库 `queue`、`threading`、`concurrent.futures`）
**描述**: 独立的 worker 线程（通过 `ThreadPoolExecutor` 或 `threading.Thread`）从
内部队列取消息，调用原有 `process_message` 逻辑执行 DB 操作。
**AC**:
- Given: 消息已入队
- When: worker 线程从队列取出消息
- Then: 调用 `_dispatch(topic, payload_bytes)` 完成解码和 handler 分发

### REQ-FUNC-003: 内部消息队列有界且可配置
**来源**: 防止内存无限增长
**描述**: 使用 `queue.Queue(maxsize=2000)` 作为内部缓冲，队列满时丢弃新消息并记录
WARNING 日志，不阻塞网络线程。
**AC**:
- Given: 队列已达 maxsize=2000
- When: 新消息到达
- Then: 调用 `put_nowait` 抛出 `queue.Full`，记录 WARNING，返回，不阻塞

### REQ-FUNC-004: Worker 线程中正确管理 Django DB 连接
**来源**: Django ORM thread-local connection 约束
**描述**: 每个 worker 线程在处理每条消息前调用 `close_old_connections()`，确保
跨线程的 DB 连接独立且有效。
**AC**:
- Given: worker 线程已启动
- When: 从队列取出消息准备处理
- Then: 在调用 handler 前执行 `close_old_connections()`

### REQ-FUNC-005: 保留现有 db_maintenance_thread
**来源**: 现有代码保活机制
**描述**: `db_maintenance_thread` 及其 300s 保活逻辑保持不变，继续在其自身线程中
维护 DB 连接。
**AC**:
- Given: MQTTConsumer 启动
- When: `start()` 被调用
- Then: db_maintenance_thread 正常启动，独立于 worker 线程运行

### REQ-FUNC-006: 优雅关闭（SIGTERM 安全）
**来源**: systemd 运行约束
**描述**: 收到停止信号（`stop()` 调用）后，等待队列中剩余消息全部消费完毕再退出，
最长等待时间不超过 30s。
**AC**:
- Given: 服务正在运行，队列中有未处理消息
- When: `stop()` 被调用（SIGTERM 触发）
- Then: worker 线程继续消费直到队列为空，然后 executor shutdown，最长等待 30s

### REQ-FUNC-007: Worker 线程数可配置
**来源**: 树莓派资源约束
**描述**: Worker 线程数默认 4，通过 `__init__` 参数或配置可调整，thread_name_prefix
为 "mqtt-worker" 以便日志识别。
**AC**:
- Given: MQTTConsumer 初始化
- When: 无额外配置
- Then: ThreadPoolExecutor 以 max_workers=4 启动，线程名前缀为 "mqtt-worker"

## 4. 非功能需求

### REQ-NFN-001: 不引入外部依赖
依赖仅限 Python 标准库（`queue`、`threading`、`concurrent.futures`）；
禁止引入 Celery、Redis、aio-pika 等。

### REQ-NFN-002: 向后兼容 Handler 接口
`PLCDataHandler`、`ConnectionStatusHandler`、`PLCLatestDataHandler` 的
`handle(topic, payload, building_file)` 签名不变，无需修改 `mqtt_handlers.py`。

### REQ-NFN-003: 日志可观测性
- 消息入队成功：DEBUG 级别（高频，避免日志爆炸）
- 队列满丢弃：WARNING 级别（含 topic）
- Worker 处理完成：INFO 级别（含 topic、耗时）
- Worker 异常：ERROR 级别（含 topic、异常）

### REQ-NFN-004: 生产验证标准
- 生产日志 24h 内不出现 `DISCONNECT rc=16`
- `plc_latest_data` 中 `specific_part='3-1-7-702'` 的 `collected_at` 在 600s 内更新
- 服务正确响应 SIGTERM（`systemctl stop freeark-mqtt-consumer` 在 30s 内完成）

## 5. 约束

| 约束 | 值 |
|------|----|
| Python 版本 | 3.13 |
| Django 版本 | 5.2 |
| MQTT 库 | paho-mqtt |
| DB 驱动 | MySQLdb |
| 部署方式 | systemd 物理机（树莓派） |
| Worker 线程数 | 4（默认） |
| 队列容量 | 2000 条 |
| 优雅关闭超时 | 30s |
| 禁止使用 | Docker、Celery、Redis |

## 6. 不在范围内

- `mqtt_handlers.py` 的逻辑修改
- MQTT broker 侧配置变更
- 数据库 schema 修改
- 前端代码变更
