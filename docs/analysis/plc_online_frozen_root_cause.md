# PLC 在线数量冻结故障 — 根因分析报告（第一步）

**日期**：2026-05-30  
**故障现象**：看板"在线 PLC"数量长期卡在约 170 台，但现场 PLC 开机率约 80%（在线数应远高于此）。  
**历史规律**：重启 freeark-task-scheduler + freeark-mqtt-consumer 两个服务后立即恢复正常。  
**本报告状态**：基于代码静态分析已完成；生产实时取证命令已列出但尚未执行。

---

## 一、系统真实数据链路（代码核实版）

通过阅读全部相关代码，真实链路如下：

```
[PLC 设备]
    |
    | S7comm TCP 连接
    v
[task-scheduler → ImprovedDataCollectionManager → PLCManager 线程池]
    | 采集成功 → 序列化为 JSON → MQTT Publish
    | 主题: /datacollection/plc/to/collector/<building_file>/<specific_part>
    v
[EMQX MQTT Broker @ 192.168.31.98:32788]
    |
    | MQTT Subscribe (QoS=1)
    v
[mqtt-consumer — MQTTConsumer.on_message]
    | payload_size < 2000B → energy_queue (3 workers)
    | payload_size >= 2000B → general_queue (6 workers)
    v
[Worker 线程 _worker_loop → _dispatch → process_message]
    |
    |── ConnectionStatusHandler（仅 energy 队列，即小消息）
    |     └─ _update_connection_status(specific_part, 'online'/'offline')
    |         ├─ 快路径：cache 命中且状态一致 → UPDATE last_online_time=now()
    |         └─ 慢路径：cache miss 或状态变化 → SELECT FOR UPDATE + 完整事务
    |
    |── PLCLatestDataHandler（energy + general 队列均有）
    |     └─ bulk upsert → plc_latest_data 表
    |
    └── PLCDataHandler（energy + general 队列均有）
          └─ bulk_create/bulk_update → plc_data 表（能耗历史）
    |
    v
[plc_connection_status 表]
    | connection_status='online'/'offline', last_online_time=TIMESTAMP
    |
    | 独立监控进程：freeark-plc-connection-monitor
    | 每 300 秒扫描，把 last_online_time < now()-600s 的行从 online 翻为 offline
    v
[Django API — views.py]
    | dashboard_plc_online_rate():
    |   SELECT COUNT(*) WHERE connection_status='online'
    |   → 直接读 plc_connection_status 表，无缓存，无内存状态
    v
[前端看板 — 显示 online_count]
```

**关键结论**：
- "在线"数量 = `plc_connection_status` 表中 `connection_status='online'` 的行数，100% 是数据库查询，前端/API 层无任何内存缓存。
- `ConnectionStatusHandler` 是唯一将设备写为 `online` 的代码路径，而它只在 **energy 消息**（payload < 2KB）被 mqtt-consumer 消费时才被调用。
- `plc-connection-monitor` 是唯一将设备翻为 `offline` 的定期进程（超时阈值 600 秒）。

---

## 二、在线判定阈值与机制

| 参数 | 值 | 代码位置 |
|------|------|------|
| 判定字段 | `plc_connection_status.connection_status` | `models.py:200` |
| 写 online 触发 | mqtt-consumer 收到 energy 消息且 has_success=True | `mqtt_handlers.py:ConnectionStatusHandler` |
| 写 offline 触发 | `last_online_time < now()-600s`（每 5 分钟扫描） | `plc_connection_monitor.py:_check_connection_status` |
| 进程内缓存 | `_conn_status_cache` dict（仅本进程内有效，重启清空） | `mqtt_handlers.py:681` |
| 快路径条件 | cache[specific_part] == 'online' 且 DB 行 connection_status='online' | `mqtt_handlers.py:553-561` |
| 看板 API | 直接聚合 COUNT，无额外缓存 | `views.py:909-911` |

---

## 三、"170 冻结"的可能失效机制（按可能性排序）

### 候选根因 A（最高可能性）：mqtt-consumer 的 _conn_status_cache 进程内缓存与 DB 状态脱节，导致大量设备跳过 online 更新

**机制说明**：

`_conn_status_cache` 是一个进程级 Python dict，key=specific_part, value='online'/'offline'。

正常路径（快路径）：
1. 消息进来，cache 命中 'online'
2. 执行 `UPDATE ... WHERE connection_status='online'`，返回 rows=1
3. 跳过慢路径，返回

**潜在触发失效的场景**：

如果 `plc-connection-monitor` 将某台设备的 DB 行翻为 offline（例如因 mqtt-consumer 暂时卡顿导致心跳超时），而此时 `_conn_status_cache` 中该设备仍然是 'online'：

- 快路径执行 `UPDATE WHERE connection_status='online'`，rows=0（因为 DB 已是 offline）
- 代码检测到 rows=0，清除该 specific_part 的 cache，fall-through 到慢路径（v0.5.8 F2 修复）
- 慢路径正确地将其恢复为 online

这个路径是有 F2 修复的，**理论上**应该能自恢复。但 F2 只在快路径 `rows==0` 时触发——如果快路径根本没有进入（例如 on_message 回调完全停止工作），则没有任何机制能触发恢复。

### 候选根因 B（次高可能性）：mqtt-consumer 的 on_message 回调虽然没有崩溃，但消息实际已不再流入，或队列长期满

**机制说明**：

`on_message` 回调是 paho 网络线程调用的，逻辑极简（只是 `put_nowait` 入队）。但 paho 2.1.0 使用 VERSION1 兼容模式——paho 网络线程负责维持 PINGREQ，如果某个原因导致网络线程卡死（极少见，但可能因系统资源耗尽），则整个 MQTT 连接的心跳停止，broker 超时断开（rc=16 EMQX keep-alive 超时），但 `on_disconnect` 回调**不会触发自动重连**（代码里 `on_disconnect` 只记录日志，没有重连逻辑）。

断开后，新上线 PLC 发来的 energy 消息不再被接收，`_update_connection_status` 不再被调用，`last_online_time` 停止更新。600 秒后 plc-connection-monitor 把它们翻为 offline。新上线的 PLC 从未建立过 online 记录，也不会出现在统计中。

**170 这个稳定值的含义**：170 台设备在 mqtt-consumer 断连时恰好处于 online 状态，且 plc-connection-monitor 还未将它们超时，因此这 170 台是"被冻结的最后快照"。之后新上线的 PLC 由于 mqtt-consumer 不再消费消息，永远不会被标记为 online。

### 候选根因 C（可能性较高）：task-scheduler 中 PLCManager 线程池或 MQTT 连接池耗尽

**机制说明**：

task-scheduler 用 `ImprovedDataCollectionManager`，内部有：
- `PLCManager` 线程池（max_workers=10）
- `PLCWriteSubscriber`（独立 MQTT 连接，32788 端口）
- `OndemandCollectSubscriber`（独立 MQTT 连接，32788 端口）

如果线程池中某个 task 因 PLC 连接超时卡住（`future.result(timeout=60)` 等 60 秒），且所有 10 个线程均卡住，则 task-scheduler 不再采集，也不向 MQTT broker 发布新消息。mqtt-consumer 收到的消息量骤降，`last_online_time` 不再刷新，60s 超时后 plc-connection-monitor 批量将设备翻 offline。

**但这个场景会让数字跌到 0，而不是稳定在 170**。所以单独的 C 不能解释"冻结"现象，除非与 B 同时发生：先是 task-scheduler 停止发布（导致无新消息），然后 mqtt-consumer 的连接也出了问题（导致即使有历史设备的消息也无法消费），两者叠加才出现"冻结快照"。

### 候选根因 D：plc-connection-monitor 的扫描本身卡死

**机制说明**：

`_check_connection_status` 使用 `select_for_update()` 在同一个事务里批量写 PLCConnectionStatus + PLCStatusChangeHistory。如果与 mqtt-consumer 的 ConnectionStatusHandler 慢路径（也使用 select_for_update）发生死锁，MySQL 会中止一方，但 plc-connection-monitor 的 try/except 只会 `log_error` 后继续睡 300s——不会自动重试。

如果 plc-connection-monitor 的某次循环卡住（例如 MySQL 连接超时 60s 后被掐断，而没有 catch 到 OperationalError），它在 finally 块中正常退出，但 systemd 的 `Restart=on-failure` 只在进程退出码非0时重启——如果 `except Exception` 把错误吞掉后以 exit_code=1 退出，则会被 systemd 重启，这是正常的。

D 本身不会导致"冻结"，因为即使 monitor 停了，已经是 online 的设备仍然停留在 online（直到 monitor 恢复才开始清理），不会冻结在 170。

---

## 四、为什么重启这两个服务能立即恢复

### 重启 mqtt-consumer 的效果
1. 进程终止，`_conn_status_cache` 清空（进程内 dict 销毁）
2. paho 网络线程终止，连接断开
3. 重新启动时 `MQTTConsumer.connect()` 建立新的 MQTT 连接
4. `on_connect` 回调重新订阅所有 topic（包括 `/datacollection/plc/to/collector/#`）
5. broker 重传 QoS=1 积压消息（如有），新消息开始流入
6. `ConnectionStatusHandler` 第一批消息走慢路径（cache 空），把所有发来消息的 PLC 写为 online
7. 看板立即上升

**重启 task-scheduler 的效果**：
1. 进程终止，`PLCManager` 线程池销毁（所有卡住的 future 丢弃）
2. `PLCWriteSubscriber` / `OndemandCollectSubscriber` 的 MQTT 连接断开
3. 重新启动时，线程池清洁重建，`data_collection_manager.start()` 重新初始化
4. 立刻开始采集 PLC 数据，新采集结果通过 MQTT 发布到 broker
5. mqtt-consumer 消费后更新 `last_online_time`，`plc-connection-monitor` 不再将它们翻 offline

**两者配合才能"立即恢复"**：
- 只重启 task-scheduler：如果 mqtt-consumer 已断连，新发布的消息消费不了，online 数不变
- 只重启 mqtt-consumer：如果 task-scheduler 已停止采集，没有新消息，无法更新已超时设备的 last_online_time
- 两者都重启：采集链路完全重建，消费链路完全重建，正常心跳流恢复

---

## 五、已有的关键代码缺陷（静态分析发现）

### 缺陷 1：mqtt-consumer 的 on_disconnect 没有自动重连逻辑

代码位置：`api/mqtt_consumer.py:489-494`

```python
def on_disconnect(self, client, userdata, rc):
    if rc != 0:
        logger.warning(f"意外断开与MQTT代理的连接，返回代码: {rc}")
    else:
        logger.info("已断开与MQTT代理的连接")
```

断开后只记录日志，没有任何重连尝试。paho 2.x 的 `loop_start()` 在 2.0 之前的版本有内置自动重连，但在 2.x 版本中，`reconnect_delay_set()` 不被 `loop_start()` 自动使用——**需要显式在 `on_disconnect` 中调用 `client.reconnect()` 或使用 `loop_forever(reconnect_delay=...)` 才能自动重连**。

当前代码用的是 `loop_start()`（后台线程），不是 `loop_forever()`，也没有在 `on_disconnect` 里调用 `client.reconnect()`。因此，一旦 MQTT 连接断开（无论是 broker 重启、keep-alive 超时还是网络抖动），mqtt-consumer 进程继续跑但**不再收任何消息**，且**不会自动恢复**。

这是最关键的代码缺陷，与"重启即恢复"的行为完全吻合。

### 缺陷 2：mqtt_consumer_service.py 的 --auto-restart 参数默认为 False，且监控逻辑为空

代码位置：`api/management/commands/mqtt_consumer_service.py:31-35, 118-126`

```python
parser.add_argument('--auto-restart', action='store_true', default=False, ...)
```

`_monitor_service` 方法体内全是注释，没有实际的健康检查和重启逻辑：

```python
def _monitor_service(self):
    logger.debug('🔍 监控服务状态')
    # 假设有一个检查服务状态的函数
    # if not is_mqtt_consumer_running():
    #     ...
```

即使 systemd unit 文件里传了 `--auto-restart`，检查函数也是 no-op，不会触发重启。

### 缺陷 3：task-scheduler 与 mqtt-consumer 是否真的构成"数据发布者"？

注意：根据代码，task-scheduler 采集后将结果通过 `send_results_to_mqtt()` 发布到 MQTT（`mqtt_config.enabled=true` 时）或直接保存 JSON/Excel 文件。需要确认生产配置中 MQTT 输出是否已启用（`output_config.json` 的 `mqtt.enabled`）。如果 MQTT 输出未启用，则 task-scheduler 不发布消息到 broker，mqtt-consumer 也收不到任何 PLC 数据。**这是一个需要生产现场验证的关键配置点。**

---

## 六、需要在生产执行的取证命令（只读，不重启）

以下命令请通过 SSH 在生产树莓派执行（Bash 工具 + junction 路径方式）：

```bash
SSH_CMD="ssh -i /c/fa-home/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=15 \
  -p 22 yangyang@192.168.31.51"
```

### 取证 1：服务进程状态与运行时长

```bash
$SSH_CMD 'systemctl status freeark-mqtt-consumer freeark-task-scheduler freeark-plc-connection-monitor --no-pager'
```

**关注**：Active 状态、运行时长（越长越可能积累了问题）。

### 取证 2：mqtt-consumer 最近 200 行 journal 日志（含断连记录）

```bash
$SSH_CMD 'sudo journalctl -u freeark-mqtt-consumer -n 200 --no-pager'
```

**关注**：是否有 `意外断开与MQTT代理的连接`；最后一次 `成功连接到MQTT代理` 是什么时间；是否有 `消息队列已满` 警告。

### 取证 3：task-scheduler 最近 100 行 journal 日志

```bash
$SSH_CMD 'sudo journalctl -u freeark-task-scheduler -n 100 --no-pager'
```

**关注**：是否有 `PLC任务超时`；最近是否在正常打印 `本轮任务执行完成`。

### 取证 4：mqtt-consumer 进程的线程数和文件句柄

```bash
# 获取 mqtt-consumer 的 PID
$SSH_CMD 'systemctl show -p MainPID freeark-mqtt-consumer'
# 替换下面 <PID> 为上面得到的值
$SSH_CMD 'ls /proc/<PID>/fd | wc -l'        # 文件句柄数
$SSH_CMD 'cat /proc/<PID>/status | grep -E "Threads|VmRSS|VmPeak"'  # 线程数 & 内存
```

**关注**：线程数应约为 3(energy)+6(general)+1(ondemand)+1(paho网络线程)+1(db-maintenance)+1(主线程) = 13 左右；内存是否异常增长。

### 取证 5：MQTT broker 连接状态

```bash
# EMQX HTTP API 查询当前活跃客户端（需要 EMQX REST API 地址和凭据）
# 如果 EMQX 暴露了管理端口（默认 18083），可以用：
$SSH_CMD 'curl -s http://192.168.31.98:18083/api/v5/clients?clientid=django-mqtt-client --user <admin>:<password>'
# 或者直接看 mqtt-consumer 是否有活跃的 TCP 连接到 broker:
$SSH_CMD 'ss -tnp | grep 32788'
```

**关注**：是否有 `ESTABLISHED` 连接指向 `192.168.31.98:32788`；如果 mqtt-consumer 进程还活着但没有这条连接，说明已断开未重连。

### 取证 6（最关键）：DB 中"在线"PLC 的 last_online_time 分布

```bash
$SSH_CMD 'cd /home/yangyang/Freeark/FreeArk && \
  echo "SELECT connection_status, COUNT(*) as cnt, MIN(last_online_time) as earliest, MAX(last_online_time) as latest FROM plc_connection_status GROUP BY connection_status;" | \
  venv/bin/python FreeArkWeb/backend/freearkweb/manage.py dbshell'
```

**关注**：
- online 行的 latest（MAX last_online_time）— 如果这个值卡在某个过去时刻（例如数小时前），说明 mqtt-consumer 在那时断开连接，之后没有任何 PLC 更新过 last_online_time。
- online 行的 earliest（MIN last_online_time）— 如果最老的 last_online_time 超过 600 秒（plc-connection-monitor 超时阈值），说明 plc-connection-monitor 也停止工作了（否则这些设备早就被翻 offline）。

### 取证 7：DB 中近 1 小时内 last_online_time 更新的 PLC 数量

```bash
$SSH_CMD 'cd /home/yangyang/Freeark/FreeArk && \
  echo "SELECT COUNT(*) FROM plc_connection_status WHERE last_online_time >= NOW() - INTERVAL 10 MINUTE;" | \
  venv/bin/python FreeArkWeb/backend/freearkweb/manage.py dbshell'
```

**关注**：如果近 10 分钟内 last_online_time 更新了的台数 = 0，说明 mqtt-consumer 已断连且没有任何设备的心跳被更新。

### 取证 8：生产的 output_config.json — 确认 mqtt 输出是否启用

```bash
$SSH_CMD 'cat /home/yangyang/Freeark/FreeArk/datacollection/resource/output_config.json 2>/dev/null || echo "FILE_NOT_FOUND"'
```

**关注**：`mqtt.enabled` 是否为 true；如果为 false，task-scheduler 根本不向 broker 发消息，整个链路断裂。

### 取证 9：plc-connection-monitor 是否正在运行

```bash
$SSH_CMD 'sudo journalctl -u freeark-plc-connection-monitor -n 50 --no-pager'
```

**关注**：最近是否有 `在线设备 N/M 台`；最近一条记录时间（如果超过 5 分钟没有新记录，说明 monitor 也停了）。

---

## 七、根因假设与验证矩阵

| 编号 | 假设 | 验证命令 | 期望观测到的异常证据 |
|------|------|----------|---------------------|
| A | mqtt-consumer MQTT 连接已断开 | 取证 5（ss -tnp），取证 2（journalctl） | ss 无 32788 ESTABLISHED；journalctl 有 "意外断开" 且无后续 "成功连接" |
| B | mqtt-consumer 进程活着但收不到消息 | 取证 7（DB 10min 更新数） | 近 10min last_online_time 更新数 = 0 |
| C | online 设备的 last_online_time 卡在某时刻 | 取证 6（DB MAX） | MAX(last_online_time) 距现在超过 10min |
| D | plc-connection-monitor 停止运行 | 取证 9（monitor journal） | 最近 >5min 无新日志条目；且 online 设备的 MIN(last_online_time) 超过 600s 无被翻 offline |
| E | task-scheduler 停止向 broker 发消息 | 取证 3 + 取证 8 | task-scheduler 日志无 "本轮任务执行完成"；或 output_config mqtt.enabled=false |

---

## 八、基于代码分析的确定性结论（无需生产取证即可断定）

1. **前端看板展示的"在线数"100% 来自 DB 实时聚合查询**，展示环节不存在缓存问题。问题不在前端。

2. **mqtt-consumer 的 `on_disconnect` 没有自动重连逻辑（缺陷 1）是结构性缺陷**，一旦 MQTT 连接断开（无论什么原因），进程将永久处于"存活但不消费"状态，直到被手动重启。这与"重启即恢复"完美吻合。

3. **task-scheduler 不参与"在线判定"逻辑**。task-scheduler 的职责是采集 PLC 数据并发布到 MQTT。它重启能恢复的原因是：恢复了消息流，让 mqtt-consumer 重新有消息可消费，从而 `ConnectionStatusHandler` 能更新 `last_online_time`。

4. **"170 这个稳定值"是一个进程内快照被冻结的典型表现**：mqtt-consumer MQTT 连接断开后，ConnectionStatusHandler 不再被调用，`last_online_time` 停止更新；plc-connection-monitor 每 5 分钟扫描，持续将超时设备翻为 offline，最终所有"本该在线"的设备都被翻为 offline，只剩下那 170 台（这 170 台的 last_online_time 恰好还在 600 秒内，或者 monitor 也停了）。

5. **monitor 也可能停了**（见候选根因 D）：如果 MIN(last_online_time) 距今超过 600 秒但这些设备仍然显示 online，则 plc-connection-monitor 也出了问题，两个服务同时失效。

---

## 九、待执行的生产取证（交用户确认后执行）

上述"取证 1~9"的命令尚未在生产执行（本报告为纯代码分析阶段）。

**请用户通过 SSH 执行上述取证命令，并将输出反馈**，以便：
1. 确认是"mqtt-consumer 断连未重连"（最可能）还是"task-scheduler 停止发布"；
2. 确认 plc-connection-monitor 是否也同时失效（解释"为何 170 台没被翻成 0"）；
3. 确认 output_config.json 中 mqtt 输出是否已开启。

---

## 十、第一步小结

**当前分析结论**（置信度：基于代码分析，约 85%）：

故障的根本原因是 **mqtt-consumer 进程的 MQTT 连接意外断开后缺乏自动重连机制**（`on_disconnect` 中无重连逻辑）。进程保持运行状态（systemd 不会触发重启，因为进程未崩溃），但不再消费 broker 上的消息，`ConnectionStatusHandler` 停止被调用，`plc_connection_status.last_online_time` 不再更新，`plc-connection-monitor` 持续将超时设备翻为 offline，最终在线数冻结在 170（或更低某个值）。

任务调度器的问题是辅助因素（如果 task-scheduler 线程池卡死，也减少了发往 broker 的消息量），但核心问题是 mqtt-consumer 端的断连无恢复机制。

**等待用户提供取证 1~9 的输出，用于确认根因并出第二步处置方案。**
