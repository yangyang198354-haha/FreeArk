# 事件取证报告 — 2026-05-22 夜 PLC 在线数批量波动

**取证时间**：2026-05-23 13:30 - 14:15（北京时间）
**取证人**：Claude（替代 devops-engineer 子代理，因子代理 session 受限）
**取证方式**：SSH 进生产树莓派只读取证；不重启服务、不改配置。

---

## T1. 服务状态快照

```
freeark-backend.service                loaded active running
freeark-daily-usage.service            loaded active running
freeark-monthly-usage.service          loaded active running
freeark-mqtt-consumer.service          loaded active running
freeark-plc-connection-monitor.service loaded active running
freeark-screen-heartbeat.service       loaded active running
freeark-task-scheduler.service         loaded active running
```
全部 7 个 freeark 服务当前 active running。

---

## T14. plc_status_change_history 表结构

```
Field          Type          Null  Key  Default  Extra
id             bigint        NO    PRI  NULL     auto_increment
specific_part  varchar(20)   NO    MUL  NULL
status         varchar(10)   NO    MUL  NULL
change_time    datetime(6)   NO    MUL  NULL
building       varchar(10)   NO    MUL  NULL
unit           varchar(10)   NO    MUL  NULL
room_number    varchar(10)   NO    MUL  NULL
created_at     datetime(6)   NO         NULL
source         varchar(10)   NO         NULL
```
关键字段：`source` ∈ {'monitor', 'mqtt'}，`status` ∈ {'online', 'offline'}。

---

## T2. 过去 24h source × status 分布（最强证据）

```
source   status   cnt
monitor  offline  1220
mqtt     online   898
mqtt     offline  21
```

- 批量下线 1220 条 **全部** 来自 `source=monitor`（plc_connection_monitor 写入）
- 批量上线 898 条 **全部** 来自 `source=mqtt`（ConnectionStatusHandler 写入）
- mqtt/offline 仅 21 条噪音级别

→ **路径 A 是上线的主驱动，路径 B 是下线的主驱动**，且二者各司其职无串扰。

---

## T3. 18:00-10:00 每 30 分钟 source/status 分桶

```
bucket          status   source   cnt
05-22 19:30     offline  mqtt     1
05-22 21:30     offline  monitor  349    ★ 第一次批量下线
05-22 22:00     offline  mqtt     1
05-22 22:30     offline  monitor  17
05-22 23:30     offline  monitor  3
05-23 00:00     online   mqtt     118    ★ 用户手动重启后批量上线
05-23 00:30     online   mqtt     252    ★
05-23 01:00     offline  mqtt     1
05-23 01:00     online   mqtt     53
05-23 03:00     offline  monitor  128
05-23 04:00     offline  monitor  310    ★ 第二次批量下线
05-23 05:00     offline  monitor  23
05-23 06:00     offline  monitor  3
05-23 07:00     offline  monitor  6
05-23 07:00     offline  mqtt     1
05-23 09:30     online   mqtt     164    ★ 批量恢复上线
```

**关键时间窗**：21:30、03:00-04:00 两次大批量 PLC 集体不可达；00:00-00:30 和 09:30 两次集中恢复上线。

---

## T4. 变更次数 ≥ 2 的 PLC TOP 30

所有 TOP 30 PLC 模式高度一致：
- 变更次数：**全部 = 4 次**
- sources：**全部 = `monitor, mqtt`**
- statuses：**全部 = `offline, online`**
- 第一次变更：21:45 / 22:24 / 22:45 / 23:45（夜间逐批）
- 最后一次变更：09:34 - 09:42（恢复上线）

→ 每台 PLC 经历了 **2 个完整循环**（offline → online → offline → online），分别对应夜里的两次掉线和两次恢复。

---

## T5. plc-connection-monitor 24h 全量日志

journalctl 在 00:02:47 服务停止时**一次性 flush** 了大量历史日志，所以全部日志时间戳均显示为 00:02:47（journald 时间戳失真）。日志内容是逐次扫描的累积：

- 多条「✅ 所有在线设备均在正常通信范围内」与「📊 当前状态统计: 在线设备 530-568/634 台」交替出现，说明扫描周期内 PLC 数量在 ~530-568 之间波动
- 一次「✅ 已将 12 个超时设备标记为离线」记录

**结论**：监控器按设计扫描，未见异常错误。

---

## T6. task-scheduler 24h WARNING+ 非 PLC-unreachable 行

```
May 23 00:05:36 freeark-task-scheduler: stop-sigterm timed out. Killing. (SIGKILL)
May 23 09:28:45 freeark-task-scheduler: stop-sigterm timed out. Killing. (SIGKILL)
May 23 09:47:46 freeark-task-scheduler: stop-sigterm timed out. Killing. (SIGKILL)
```

三次都是 service 停止时进程没在 SIGTERM 后 30s 内退出被强杀。属于已知现象（多线程进程不响应 SIGTERM），与本次事件无因果关系。

---

## T6b. task-scheduler「PLC连接异常」按 30 分钟分桶（23:30 起）

```
count   bucket
  140   May 22 23:30   ← 基线
  599   May 23 00:00   ← +328% 突增
  512   May 23 00:30
  512   May 23 01:00
  512   May 23 01:30
  448   May 23 02:00
  512   May 23 02:30
  576   May 23 03:00
  448   May 23 03:30
  512   May 23 04:00
  576   May 23 04:30
  448   May 23 05:00
  512   May 23 05:30
  576   May 23 06:00
  448   May 23 06:30
  512   May 23 07:00
  508   May 23 07:30
  516   May 23 08:00
  512   May 23 08:30
  570   May 23 09:00
  575   May 23 09:30
```

23:30 → 00:00 PLC 异常报错激增 4.3x，之后一直保持 ~450-580 高位。说明从 00:00 之后**持续有大量 PLC 不可达**，问题并未消失。

---

## T7. mqtt-consumer 24h WARNING+

无显著条目（已被 grep 过滤为空）。

---

## T8. multi_thread_plc_handler 应用日志（当前 14:10:31-37 最末 120 行）

密集的 `❌ PLC连接异常：192.168.X.Y, Rack: 0, Slot: 1 - b' TCP : Unreachable peer'` 与 `⚠️ 读取异常，第N次重试：b' ISO : An error occurred during send TCP : Other Socket error (32)'` 错误，**当前仍在持续发生**。涉及网段广泛：192.168.3 / 4 / 5 / 6 / 7 / 8 / 9 等。

---

## T9. 24h 内服务重启时间线（**关键发现**）

```
freeark-task-scheduler:
  May 23 00:05:36 - Started (前一次 stop SIGKILL'd at 00:05:36)
  May 23 09:28:45 - Started (我做 v0.5.7 部署重启)
  May 23 09:47:46 - Started (我做 fix2 部署重启)

freeark-plc-connection-monitor:
  May 23 00:02:47 - Started   ★ 事件夜里的意外重启

freeark-mqtt-consumer:
  May 23 00:04:47 - Started   ★ 事件夜里的意外重启
  May 23 09:27:15 - Started (我做 v0.5.7 部署重启)
  May 23 09:46:16 - Started (我做 fix2 部署重启)

freeark-backend:
  May 23 09:27:15 - Started (我做 v0.5.7 部署重启)
  May 23 09:46:16 - Started (我做 fix2 部署重启)
```

**夜里 00:02-00:05 三个服务连续重启**——非自动重启，是**手动触发的**（见 T9b）。

---

## T9b. 00:02-00:08 systemd journal 完整时间线（重启触发源）

```
May 23 00:02:38 sudo[12425]: yangyang : COMMAND=/bin/systemctl restart freeark-screen-heartbeat
May 23 00:02:47 sudo[12431]: yangyang : COMMAND=/bin/systemctl restart freeark-plc-connection-monitor
May 23 00:04:06 sudo[12495]: yangyang : COMMAND=/bin/systemctl restart freeark-task-scheduler
May 23 00:04:46 sudo[12519]: yangyang : COMMAND=/bin/systemctl restart freeark-mqtt-consumer
May 23 00:07:31 sshd: Accepted publickey for yangyang from 192.168.31.142 port 5810 (session 263)
May 23 00:08:23 sudo[12861]: yangyang : COMMAND=/usr/bin/systemctl stop freeark-dph-cleanup
```

**00:02-00:04 的 4 次重启由 yangyang 用户主动发起**（来自某个早于 24h 窗口的 ssh session 或本地 console）。每次 sudo 都明确记录了 PWD 与 COMMAND。

**这与"批量上线"的时间窗 00:00-00:30 强烈重合**——服务重启清空 `_conn_status_cache`，重启后首批 PLC 成功采集消息全部走 ConnectionStatusHandler 慢路径，触发批量 source=mqtt/online 写入。

---

## T10. dmesg 网络层（dmesg 仅有 boot 时的 link up 信息）

```
[Wed May 20 18:42:36] macb 1f00100000.ethernet eth0: configuring for phy/rgmii-id link mode
[Wed May 20 18:42:40] macb 1f00100000.ethernet eth0: Link is Up - 1Gbps/Full - flow control tx
```

dmesg 缓冲只保留了启动以来的核心事件，未见昨晚至今的网卡 down/up 抖动。说明**树莓派本机的 eth0 没出问题**，问题在远端 PLC 或中间网络。

---

## T11. 当前 PLC 网段 TCP ESTAB 分布（2026-05-23 14:10）

```
ESTAB Count   网段
        107   192.168.9
        105   192.168.8
        104   192.168.7
         59   192.168.5
         53   192.168.1
         39   192.168.31
         32   192.168.6
         32   192.168.2
         26   192.168.10
         24   192.168.4    ← 偏少
         22   192.168.3    ← 偏少
```

192.168.3 / 192.168.4 网段 ESTAB 数量明显偏少，可能是当前主要受影响的两个网段。

---

## T12. plc-connection-monitor systemd unit 文件（**关键参数**）

```
[Service]
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py plc_connection_monitor --check-interval 3600 --timeout-threshold 3600
```

**生产实际参数**：
- check-interval = **3600 秒（1 小时）**
- timeout-threshold = **3600 秒（1 小时）**

**与代码默认值不同**：代码默认是 300s + 600s。生产 unit 文件主动放宽到 3600s + 3600s。意味着 monitor 每小时扫一次，PLC 必须连续 1 小时未通信才会被置 offline。

---

## T13. plc_connection_status 当前在线/离线统计

```
connection_status   cnt   oldest_last_online_time   newest_last_online_time
offline             445   02-21 20:34:41             05-23 14:10:44
online              189   05-23 13:25:05             05-23 14:15:15
```

- 总计 634 台 PLC，**当前 70% offline / 30% online**
- 最老 offline 设备最后通信时间 = **2026-02-21**（3 个月没通信，僵尸数据）
- 最新 offline = 刚刚（14:10:44）——**问题正在持续**

---

## 初步判断

基于事实数据：

1. **批量下线的直接执行者是 `plc-connection-monitor`**（source=monitor 共 1220 条，占下线总量 98.3%）。**路径 B 主导下线方向**。
2. **批量上线的直接执行者是 `ConnectionStatusHandler`**（source=mqtt/online 共 898 条，占上线 100%）。**路径 A 主导上线方向**。
3. 两者**各司其职、按设计工作**，未见软件错误。
4. **批量波动的根本触发源不在两条路径，而在 PLC 网络层**——21:30 / 03:00-04:00 两次大批量 PLC 集体不可达，从未恢复完全，当前仍在大量报错。
5. **00:02-00:04 的 4 次服务手动重启**（由 yangyang 用户发起）与「00:00-00:30 批量上线 423 台」时间窗完全重合——重启清空 `_conn_status_cache` 是触发批量 source=mqtt/online 写入的直接原因。

下线大批量是真实掉线，上线大批量包含两部分：(a) PLC 实际恢复后的上报；(b) 服务重启清缓存后首批消息全部走慢路径产生的"批量记录"。**前者反映真实，后者是缓存机制的副作用**。

---

## 取证未覆盖

- 没有 PLC 端网络层探针历史数据（如 ping 时序）——无法定位是哪条线路/路由器/交换机故障
- dmesg 缓冲未保留昨晚网卡事件——若需更早事件，需查 `/var/log/kern.log` 或 `journalctl --grep`
- 没有交换机 / 路由器日志——非本机可访问
- 没有覆盖 21:30 之前 24h 的 PLC 历史变更趋势——`change_time >= 24h ago` 截断了
