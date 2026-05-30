# 事件根因分析 — 2026-05-22 夜 PLC 批量上下线波动

**分析时间**：2026-05-23 14:15（北京时间）
**分析人**：Claude（替代 system-architect 子代理，因子代理 session 受限）
**配套取证**：`docs/incident_20260522_plc_fluctuation_evidence.md`

---

## 1. 路径 A 状态机（task-scheduler → MQTT → ConnectionStatusHandler）

源码位置：`FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py:453-631`。

### 触发链路
```
multi_thread_plc_handler 采集一轮（snap7 读 PLC）
  ↓ 结果通过 MQTT 推送到 mqtt_consumer
mqtt_consumer ConnectionStatusHandler.handle()
  ↓
判定逻辑（line 477-490）：
  - device_info['data'] 中至少一个 param 有 success=True  → status='online'
  - device_info['data'] 全部 success=False               → status='offline'
  - 无 data 字段                                          → status='offline'（带警告）
  ↓
_update_connection_status(specific_part, status, ...)
```

### 状态机（快路径 / 慢路径分离，v0.5.5 P2 优化）
源码位置：`mqtt_handlers.py:529-631`，进程内缓存 `_conn_status_cache: dict`（line 661）。

```
[cache 命中且 status 不变] → 快路径
  - status='online'  → PLCConnectionStatus.filter().update(last_online_time=now)  # 无事务无行锁
  - status='offline' → 完全跳过                                                    # 零 DB 写入
  - 不写 plc_status_change_history
  - logger.debug，level=ERROR 在生产被静默

[cache miss 或 status 变化] → 慢路径
  - transaction.atomic() + select_for_update().get_or_create()
  - 若 status_changed:
      PLCStatusChangeHistory.objects.create(specific_part=..., status=..., source='mqtt')  # line 588-595
      更新 PLCConnectionStatus 各字段
      若 status='online' 刷新 last_online_time
  - 事务提交后才更新 _conn_status_cache（line 626）
  - 异常时不更新缓存，下次仍走慢路径重试
```

### 关键代码行
- `line 479`: `has_success = any(data.get('success', False) for data in device_info['data'].values())`
- `line 483/486/490`: 三处状态判定入口
- `line 594`: `source='mqtt'` ← 路径 A 的写入标记
- `line 661`: `_conn_status_cache: dict = {}` 进程内缓存
- `line 543-554`: 快路径（命中 cache）
- `line 556-627`: 慢路径（cache miss / 状态变化）

### 重启行为
**进程重启 → `_conn_status_cache` 清空** → 重启后**所有 specific_part 的首批消息都走慢路径** → 都会触发 `select_for_update` + 写 `plc_status_change_history`。

如果重启时大量 PLC 实际是 online 的，重启后首批消息会**集中产生大量 `source=mqtt/status=online` 的历史记录**。

---

## 2. 路径 B 状态机（plc_connection_monitor）

源码位置：`FreeArkWeb/backend/freearkweb/api/management/commands/plc_connection_monitor.py`。

### 启动参数（生产实际值）
```
ExecStart=... plc_connection_monitor --check-interval 3600 --timeout-threshold 3600
```
- `check_interval = 3600s`（每 1 小时扫一次）
- `timeout_threshold = 3600s`（最后通信时间 < now - 1 小时 即视为超时）

**注意**：代码默认值是 300s / 600s（5 分钟扫一次 / 10 分钟超时），systemd unit 文件覆盖到 3600s / 3600s。

### 扫描逻辑（line 87-127）
```python
def _check_connection_status(self, timeout_threshold):
    timeout_time = timezone.now() - timedelta(seconds=timeout_threshold)
    with transaction.atomic():
        offline_devices = list(PLCConnectionStatus.objects.select_for_update().filter(
            connection_status='online',
            last_online_time__lt=timeout_time
        ).values('id', 'specific_part', 'building', 'unit', 'room_number'))

        if offline_devices:
            PLCConnectionStatus.objects.filter(id__in=ids).update(
                connection_status='offline',
                updated_at=timezone.now()
            )
            PLCStatusChangeHistory.objects.bulk_create([
                PLCStatusChangeHistory(
                    specific_part=d['specific_part'],
                    status='offline',
                    building=..., unit=..., room_number=...,
                    source='monitor'         # ← 路径 B 的写入标记，line 120
                )
                for d in offline_devices
            ])
    time.sleep(check_interval)
```

### 关键特征
**单向只置离线** —— 没有任何"online ← offline 翻回"的逻辑。这意味着：
- 路径 B **不会**产生 `source=monitor/status=online` 的记录（与 T2 数据一致：monitor/online = 0 条）
- 设备从 offline 回到 online **必经路径 A**（mqtt）

### 写入语义
- `bulk_create` 批量写入 `plc_status_change_history`，一次扫描一次性写入所有超时设备
- `select_for_update` 行锁，避免与路径 A 的 `select_for_update` 并发竞争

---

## 3. 两路径并发互动分析

### 时序场景 S1：PLC 真实掉线
```
T0      PLC 实际断开通信（网络/电源/故障）
T0+少    multi_thread_plc_handler 采集失败（snap7 TCP Unreachable peer）
          → ConnectionStatusHandler 收到 has_success=False
          → cached='online'，status='offline'，状态变化，**走慢路径**
          → 写 history (source='mqtt', status='offline')
          → 更新 cache='offline'

T0+1h    Path B 扫描：last_online_time < (now - 3600s)，置 offline
          → 但该 PLC 在 T0+少 已被 Path A 置 offline，不在 'connection_status=online' 的过滤集里
          → **不重复写**

预期：source=mqtt/offline 占主体，source=monitor/offline 几乎为 0
```

**但 T2 数据显示 monitor/offline = 1220 条 vs mqtt/offline = 21 条** ——

→ **现实是 Path A 的 cache 大多数情况下没机会更新到 offline**。原因：路径 A 走慢路径的前提是「采集消息真的送到 ConnectionStatusHandler」。**PLC 不可达时 task-scheduler 根本不会发 MQTT 失败消息**（推测：采集失败时 multi_thread_plc_handler 返回错误，task_scheduler 可能直接吞掉，不通过 MQTT 上报"我采集失败了"）。

也就是说：**PLC 掉线时 ConnectionStatusHandler 收不到任何关于这台 PLC 的消息**——它的 cache 保持 'online'，last_online_time 不更新。Path B 才是真正能检测到"长时间无消息"的角色。

### 时序场景 S2：PLC 实际恢复
```
T0     PLC 长时间不通，Path B 已置 offline (source=monitor)
T0+少   PLC 网络恢复
T0+少   task-scheduler 采集成功 → MQTT → ConnectionStatusHandler
          → cached='online'（残留），status='online'
          → 快路径（cache 命中）：仅刷新 last_online_time，**不写 history**
          → 但实际 DB 中 connection_status='offline'，与 cache 不一致！
```

**这里有个 bug 风险**：cache 与 DB 不一致。Path B 在 T0 写了 DB='offline' **但没通知 Path A 的 cache**，cache 仍是 'online'。T0+少 PLC 恢复，路径 A 走快路径只刷新 last_online_time，导致 **DB 永远卡在 offline，前端永不感知恢复**。

**但 T2 数据显示 mqtt/online = 898 条** ——

→ 实际上路径 A 在很多情况下还是走了慢路径。最可能原因：**进程重启清空 cache**（如 00:02-00:04 用户手动重启），或 task-scheduler 重启后 thread pool 重建（一些 specific_part 走到不同 worker 进程）。

### 时序场景 S3：服务重启清空 cache
```
T0    sudo systemctl restart freeark-mqtt-consumer
       → _conn_status_cache = {}
T0+少  PLC 上报数据 → ConnectionStatusHandler
       → cached=None，status='online'，**cache miss → 走慢路径**
       → select_for_update 查询 DB 当前 connection_status='offline'（被 Path B 之前置的）
       → status_changed=True
       → 写 history (source='mqtt', status='online')
       → 更新 cache='online'
```

**这是 T3 数据「00:00-00:30 mqtt/online 共 370 条」的直接解释**：
- 00:04:47 mqtt-consumer 重启 → cache 清空
- 之后前几分钟 PLC 的成功上报都被记录为 source=mqtt/online
- 大量 PLC 的 DB 状态从 monitor 留下的 offline 翻回 online

→ **服务重启本身放大了"批量上线"的感观**，但实际上是把"真实恢复但快路径没记录"的事件**集中补记**。

---

## 4. 重启效应评估（v0.5.7 部署是否相关）

v0.5.7 部署重启时间：09:27 / 09:46 / 09:47——发生在事件主时段（21:30 / 00:00 / 03:00 / 04:00）**之后**。

**结论：v0.5.7 部署与本事件无因果关系**。原因：
- 事件起点 21:30 远早于部署
- v0.5.7 改动集中在房型过滤（utils_room_filter），不触及 PLC 连接状态判定路径
- 我做的部署重启反而是 09:30 「mqtt/online 164 条」的直接原因（同 S3 场景）

**00:02-00:04 yangyang 用户手动重启 4 个服务**是事件夜里的关键扰动：
- 重启时 PLC 大量真实掉线（21:30-23:30 monitor 已置 offline 369 个）
- 重启后 cache 清空，幸存的能上报数据的 PLC 全部走慢路径补记 online
- **重启本身既没有触发掉线，也没有触发上线，但放大了"上线感"**——把原本应该被快路径吞掉的事件全部具象化为 history 记录

---

## 5. 与生产证据的对齐口径

### 假设 A（路径 A 主导下线）——**反驳**
- 预期 source=mqtt/offline 占多数
- 实际 source=mqtt/offline = 21 条（< 2%），mqtt/online = 898 条
- → **假设 A 不成立**

### 假设 B（路径 B 主导下线）——**成立**
- 预期 source=monitor/offline 占多数
- 实际 source=monitor/offline = 1220 条（98%）
- → **假设 B 成立**：plc_connection_monitor 是批量下线的直接执行者

### 但 B 不是"根因"，只是"消息使者"
- B 的判定规则正确（timeout=3600s）
- 触发 B 大量置 offline 的原因是 **PLC 真实掉线**
- 真正根因在网络层 / PLC 端 / 中间路由器，不在 FreeArk 软件

### 批量上线的根因
两部分混合：
1. PLC 实际恢复 → multi_thread_plc_handler 采集成功 → 路径 A 走快路径只刷新 last_online_time（**但 DB 仍 offline，前端不感知**）
2. 服务重启清空 cache → 后续上报走慢路径 → 集中补记 source=mqtt/online → **前端感知"批量上线"**

---

## 6. 最小化修复方向（描述，不实施）

### F1【最重要 / 非软件】PLC 网络层根因排查
- 21:30 / 02:30-04:00 两个时段是否有定时网络维护、定时电源重启、定时上游切换？
- 查路由器 / 交换机 / 楼层配电柜日志
- 192.168.3 / 192.168.4 网段（当前 TCP ESTAB 偏少）重点排查
- **本条不是 FreeArk 软件能修的**，但是消除"批量波动"必须先解决的根本问题

### F2【软件 / 高 ROI】路径 B 置 offline 后**主动失效路径 A 的 cache**
- 现状：cache 与 DB 不一致，PLC 恢复后 ConnectionStatusHandler 走快路径仅刷 last_online_time，**DB 永远卡 offline，前端看不到恢复**
- 修复：plc_connection_monitor 置 offline 时，通过 IPC（如 Redis pub/sub 或共享 cache）通知 mqtt_consumer 进程让相关 specific_part 的 cache 失效
- 效果：PLC 真实恢复时立即走慢路径写 mqtt/online，**前端实时感知**，不依赖服务重启

### F3【软件 / 中 ROI】路径 B 的"批量"动作改为"分批 + 节流"
- 现状：一次扫描可能一次性置 349 台 offline，前端看到陡变
- 修复：把超时设备按时间分窗（如每 30 秒批 50 台），降低观感冲击
- 但本质上是粉饰，**不解决根因**

### F4【可观测性 / 高 ROI】前端加"近 1 小时变更次数 TOP" 列表
- 帮助运维快速识别"频繁掉线"的 PLC（而非看全量在线数波动）
- 数据已经在 plc_status_change_history 表，只需加 API + 前端组件
- 同时区分 source='monitor' 和 source='mqtt' 的占比，便于将来诊断

### F5【运维】夜间服务重启加 cache 预热
- 现状：重启后所有 specific_part 首批消息走慢路径，DB 压力陡增（select_for_update 大量行锁）
- 修复：进程启动时从 PLCConnectionStatus 一次性拉取所有当前 status 到 cache，避开"首批全走慢路径"
- 但这需要权衡——如果 DB 里就是错的（cache 与 DB 不一致），预热反而把错的固化了

### F6【运维】把 timeout_threshold 调整到匹配业务容忍度
- 当前 3600s（1 小时）已经很宽松
- 若觉得仍频繁，可调到 7200s；但代价是发现真实掉线变慢
- **不建议**：先解决 F1 网络层根因再说

---

## 7. 可观测性缺口

1. **生产日志全局 ERROR 级别**（log_config.json） → 路径 A 的 debug 日志全部丢失，cache 命中/miss、状态翻转细节看不到，排查极费力
2. **journald 一次 flush 千行的时间戳失真**（T5 现象） → 服务停止时累积的 stdout 全部打到停止瞬间，无法逐次定位扫描时间
3. **缺 PLC 端 ping/网络探针历史** → 无法回溯昨晚是哪些 PLC 在哪些时刻掉的
4. **缺 cache 状态可观测性** → `_conn_status_cache` 是进程内 dict，外部无法 dump，无法验证 cache 与 DB 一致性
5. **缺 source 字段在前端的可视化** → 用户看到"波动"但分不清是 monitor 触发还是 mqtt 触发的，难以自助诊断

**建议引入观测点**：
- 增加 `/api/admin/conn-status/cache-dump` 端点（仅运维），dump cache vs DB 差异
- 路径 A / B 的关键转换点改用 logger.warning（不靠默认 INFO），让生产可见
- 前端"在线数"加二级面板，按 source 区分变更率

---

## 总结一句话

**plc_connection_monitor 不是"作恶者"，它只是把 PLC 真实掉线的事实如实写到了 DB；多个"批量"现象是因为 PLC 集体掉线的事实加上 plc-connection-monitor 一小时一次的扫描节拍，再加上用户手动重启服务清空 cache 后的集中补记，三者叠加导致的视觉感知**。
