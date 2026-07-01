# 数据采集 → MQTT → 入库链路 性能调查报告

- 调查日期：2026-05-21
- 范围：general / energy 两组数据的采集频次、mqtt_consumer 消费线程、链路性能瓶颈、数据库实际更新频次
- 方法：静态代码分析（采集端 + 消费端）+ 生产数据库实测（MySQL 192.168.31.98 / 库 freeark）

---

## 1. 采集频次（静态配置 + 实测验证）

**配置来源**：`datacollection/resource/task_scheduler_config.json`

| 分组 | 参数 | 配置间隔 | 实测间隔 | 说明 |
|------|------|---------|---------|------|
| energy | total_hot_quantity、total_cold_quantity（2 个） | 300s（5 分钟） | **≈ 6 分钟** | 实测稳定段 22:57→00:33 每桶精确 6 分钟 |
| general | 其余约 85 个参数（通配符 `*`） | 600s（10 分钟） | ≈ 10–15 分钟 | 采集耗时叠加在间隔上 |

实测间隔大于配置间隔的原因：`task_scheduler.py` 每个 IntervalGroup 用 `stop_event.wait(interval_seconds)`，**先跑完整轮采集再等待**，实际间隔 = 配置间隔 + 采集耗时。

---

## 2. mqtt_consumer 消费线程数（静态确认）

**来源**：`FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py:47-49`

| 队列 | worker 线程数 | 队列 maxsize | 路由规则 | 处理 handler 链 |
|------|--------------|-------------|---------|----------------|
| energy | **3** (`NUM_ENERGY_WORKERS`) | 2000 | payload < 2000 字节 | 3 个：PLCDataHandler → ConnectionStatusHandler → PLCLatestDataHandler |
| general | **6** (`NUM_GENERAL_WORKERS`) | 2000 | payload ≥ 2000 字节 | 2 个：跳过 ConnectionStatusHandler |

paho 网络线程仅负责入队（零 I/O）；每个 worker 持有独立的 Django thread-local DB 连接。

---

## 3. 数据库实测数据

### 3.1 表体量

| 表 | 行数 | 体量 |
|----|------|------|
| device_param_history | **≈ 3599 万行** | 数据 4.6 GB + 索引 6.98 GB = **11.6 GB** |
| plc_data（能耗日报） | 214,422 行 | 制冷/制热各 107,211 |
| plc_latest_data（最新值） | 51,753 行 | 596 设备 × 87 参数类型 |

### 3.2 各表实际更新频次

| 表 / 数据 | 实测更新频次 | 每批行数 |
|-----------|------------|---------|
| device_param_history — **energy** | 每 ≈ 6 分钟一批 | ≈ 1136 行（568 设备 × 2 参数） |
| device_param_history — **general** | **每 ≈ 1 小时一批**（去重） | ≈ 47,600 行（596 设备 × ~80 参数） |
| plc_latest_data — energy | 每 ≈ 6 分钟刷新 | upsert |
| plc_latest_data — general | 每 ≈ 10–12 分钟刷新 | upsert |
| plc_data | 每能耗周期 ≈ 6 分钟突发更新当天行 | ≈ 1100+ 行/批 |

**关键差异**：general 参数虽然每 10 分钟采集一次，但 `PLCLatestDataHandler._write_history` 对 general 做了**每小时去重**（`_general_hist_last_hour` 缓存），因此 device_param_history 里 general 只有每小时一次约 4.7 万行的突发；energy 参数**不去重**，每个周期全量写入。

### 3.3 采集 → 入库延迟（lag = created_at − collected_at）

| 分组 | 样本行数 | 平均延迟 | 最小 | 最大 |
|------|---------|---------|------|------|
| general | 476,255 | **334.9 秒（5.6 分钟）** | 0 s | 1836 s（30 分钟） |
| energy | 71,234 | **1227.6 秒（20.5 分钟）** | 5 s | 2698 s（45 分钟） |

**实时旁证**：调查执行时（生产时间 ≈ 00:56），device_param_history 中 energy 最新 collected_at 仅到 **00:33:58**，而 plc_latest_data 同批数据的 updated_at 为 **00:55:28** —— 即 00:33 采集的能耗数据直到 00:55 才落库，**22 分钟延迟正在实时发生**；00:39 / 00:45 / 00:51 三个周期的能耗数据当时仍积压在队列中未入库。

---

## 4. 性能瓶颈分析

### 瓶颈 1（根因）：device_param_history 表膨胀，每次 INSERT 都慢

3599 万行 / 11.6 GB，其中索引 6.98 GB，而 InnoDB buffer pool 仅 128 MB（见 [项目已知问题]）。索引无法驻留内存，**每次 INSERT 的索引维护都退化为随机磁盘 I/O**，单条写入耗时被放大。这是整条链路最慢的一环。

### 瓶颈 2：energy 队列积压 ~20 分钟，且逼近队列上限

- energy 每周期约 568 条 MQTT 消息 / 6 分钟 ≈ **1.58 条/秒**。
- 仅 **3 个 energy worker**，且每条 energy 消息都要：① `ConnectionStatusHandler` 的 `select_for_update()` 行锁（约 150ms，general 不走此 handler）② 不去重地写入膨胀的 device_param_history（瓶颈 1）。
- 单条 energy 消息处理耗时被瓶颈 1 拖到约 ≥2 秒，3 worker 的吞吐 ≈ 1.5 条/秒 < 进入速率 1.58 条/秒 → **队列只进不出，持续积压**。
- 按 `积压量 = 到达率 × 延迟` 估算：1.58 × 1227 ≈ **1939 条**，而 energy 队列 maxsize = **2000** —— **队列已处于 ~97% 满载**，一旦抖动即溢出丢消息。

### 瓶颈 3：worker 分配与实际负载相反

energy 是真正积压的一组，却只有 **3** 个 worker；general 相对轻松（去重后多数消息跳过昂贵的历史写入），却有 **6** 个 worker。worker 分配与瓶颈方向相反。

### 瓶颈 4：energy 专属的行锁竞争

3 个 energy worker 并发执行 `ConnectionStatusHandler._update_connection_status` 的 `select_for_update()`，对同一批 PLC 连接状态行存在行锁竞争（`mqtt_handlers.py` 一带）。

### 为什么 general 反而健康

general 链路延迟仅 5.6 分钟：6 个 worker + 每小时去重使绝大多数 general 消息**跳过**最昂贵的 device_param_history 写入，队列得以快速排空。energy 则是「worker 更少 + 每条都做未去重的慢写入 + 多一道行锁」三重叠加。

---

## 5. 结论与建议

### 结论

1. **采集频次**：energy 配置 5 分钟 / 实测 ≈ 6 分钟；general 配置 10 分钟 / 实测 ≈ 10–15 分钟。
2. **消费线程**：energy 队列 3 worker，general 队列 6 worker（按 payload 2000 字节分流）。
3. **数据库更新频次**：energy 历史每 ≈ 6 分钟、general 历史每 ≈ 1 小时（去重）；最新值表 energy ≈ 6 分钟、general ≈ 10–12 分钟。
4. **瓶颈确认存在**：energy 链路有 ~20 分钟入库积压，energy 队列 ~97% 满载；根因是 device_param_history 表膨胀导致 INSERT 慢。

### 建议（按优先级）

| 优先级 | 措施 | 预期效果 |
|--------|------|---------|
| P0 | 确认 `freeark-dph-cleanup` 服务确在运行并核对其保留天数；将 device_param_history 收缩到合理规模 | 索引变小 → INSERT 变快 → 直接缓解瓶颈 1/2 |
| P0 | 调大生产 MySQL（192.168.31.98）的 `innodb_buffer_pool_size`（128MB → 视内存调到 1–2GB+） | 索引可驻留内存，写入不再随机 I/O |
| P1 | 对 energy 参数的历史写入也引入去重 / 改批量 INSERT / 降低历史粒度 | 减少对 device_param_history 的写入次数 |
| P1 | 重新评估 worker 分配（energy 适当增加），并复核 energy 队列 maxsize 余量 | 缓解队列满载风险（须在瓶颈 1 解决后才有效） |
| P2 | 优化 `ConnectionStatusHandler` 的 `select_for_update` 行锁路径 | 降低 energy worker 间锁竞争 |

> 注意：在 device_param_history 膨胀问题（瓶颈 1）解决前，单纯增加 energy worker 收效有限 —— 瓶颈是磁盘 I/O 而非 CPU，更多并发只是争抢同一磁盘。

---

## 附：调查方法备注

- 调查脚本：`_investigate_collection_perf.py`（plink SSH 到树莓派 → 在 Pi 上 `mysql` 连生产库，全部为只读 SELECT）。
- 生产安全：device_param_history 的 `param_name` 列**无索引**，裸 `WHERE param_name` 过滤会全表扫描 3600 万行（实测 90s 超时）；所有时间窗口查询均改用**有索引的 `collected_at`** 做范围过滤。
- 时区提示：生产 MySQL 会话 `NOW()` 为 UTC，而表中时间戳按本地时间（UTC+8）存储，故脚本中 `INTERVAL 1 HOUR` 实际覆盖了约 9–10 小时数据；因 lag 为同表两列之差，时区影响自动抵消，延迟数值有效。
