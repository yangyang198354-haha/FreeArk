# User Stories — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_requirement_analyst, status=APPROVED, version=1.0 -->

## US-001: 网络线程不被 DB 操作阻塞

**As a** 平台运维工程师,
**I want** MQTT 网络线程在收到消息后立即返回，不执行 DB 操作,
**So that** paho-mqtt 能持续发送 PINGREQ，EMQX 不会因 keepalive 超时断开连接。

**Acceptance Criteria**:
- AC-001-1: Given 634 条消息同时涌入，When on_message 被调用，Then 每次调用在 1ms 内完成
- AC-001-2: Given MQTT 连接已建立，When general 组消息批量到达，Then 生产日志不出现 DISCONNECT rc=16
- AC-001-3: Given on_message 处理中，When 调用 put_nowait，Then 不调用任何 Django ORM 方法

**关联需求**: REQ-FUNC-001, REQ-FUNC-003

---

## US-002: DB 写入由独立 Worker 线程处理

**As a** 平台运维工程师,
**I want** 消息的 DB 持久化在独立线程中完成,
**So that** DB 延迟不影响 MQTT 连接稳定性，且数据仍然可靠写入。

**Acceptance Criteria**:
- AC-002-1: Given 消息已入队，When worker 线程取出消息，Then PLCLatestData/PLCData/ConnectionStatus 正确写入
- AC-002-2: Given worker 线程处理消息，When DB 操作前，Then 已调用 close_old_connections()
- AC-002-3: Given 4 个 worker 线程并发，When 多条消息同时处理，Then 无 DB 连接冲突（thread-local 隔离）

**关联需求**: REQ-FUNC-002, REQ-FUNC-004, REQ-FUNC-007

---

## US-003: 队列满时不丢失网络连接

**As a** 平台用户,
**I want** 即使消息处理积压时也不影响 MQTT 连接,
**So that** 设备面板在高负载期间仍能显示数据，不出现全量数据超时。

**Acceptance Criteria**:
- AC-003-1: Given 队列已满（2000条），When 新消息到达，Then 记录 WARNING 日志，网络线程立即返回
- AC-003-2: Given 队列已满时丢弃消息，When 队列恢复空闲，Then 后续消息正常入队处理
- AC-003-3: Given 正常负载下，When 634 条 general 组消息到达，Then 队列不触发满状态

**关联需求**: REQ-FUNC-003

---

## US-004: 服务优雅关闭不丢失已入队消息

**As a** 平台运维工程师,
**I want** 执行 systemctl stop freeark-mqtt-consumer 时，已入队消息能处理完再退出,
**So that** 停服不导致数据丢失。

**Acceptance Criteria**:
- AC-004-1: Given 队列中有 N 条消息，When stop() 被调用，Then worker 继续消费直至队列为空
- AC-004-2: Given 优雅关闭中，When 等待时间超过 30s，Then 强制退出并记录 WARNING
- AC-004-3: Given stop() 调用后，When executor 已 shutdown，Then db_maintenance_thread 也已停止

**关联需求**: REQ-FUNC-006, REQ-FUNC-005

---

## US-005: 数据采集结果可验证

**As a** 平台用户,
**I want** 在 general 组采集周期（600s）内看到 specific_part='3-1-7-702' 的数据更新,
**So that** 确认异步化改造后数据链路端到端正常。

**Acceptance Criteria**:
- AC-005-1: Given 服务部署后运行 600s，When 查询 plc_latest_data WHERE specific_part='3-1-7-702'，Then collected_at 在近 600s 内
- AC-005-2: Given 服务运行 24h，When 检查日志，Then 无 DISCONNECT rc=16 事件
- AC-005-3: Given 执行 systemctl stop，When 等待，Then 30s 内进程退出，systemd 状态为 inactive

**关联需求**: REQ-NFN-004
