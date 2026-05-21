# 用户故事清单

```
file_header:
  document_id: US-v0.5.4
  title: MQTT 采集链路性能优化 P1 — 用户故事清单
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.4
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/requirements/v0.5.4_mqtt_pipeline_perf_p1/requirements_spec.md
    - docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，含 US-P1-01 ~ US-P1-06 |
| 0.2.0-CONFIRMED | 2026-05-21 | 用户确认 OQ-1~OQ-4。`[依赖 OQ-X]` 标记按方案 A / 整点小时对齐落实；特性二（US-P1-05/06）随策略 A 归档延后 |

---

## 说明

本清单覆盖 v0.5.4 范围内的 P1-1（energy 历史写入降频）和 P1-2（worker 分配调整）两个特性。

部分用户故事的验收标准（AC）标注了 `[依赖 OQ-X]`，表示该 AC 的具体阈值或方案细节须在对应开放问题得到用户答复后补全；已知的结构性验收标准已全部列出。

> **决策落实（2026-05-21 用户确认）：**
> - `[依赖 OQ-1/OQ-2]` 的 AC（如 AC-P1-01-5、AC-P1-04-3）一律按**方案 A —— 每小时整点对齐**取值：时间窗口 = 整点小时，相邻历史记录间隔 ≥ 1 小时。
> - **特性二（US-P1-05、US-P1-06，即 P1-2）随 OQ-3 决策"策略 A 先观察"归档延后，不进入本期（v0.5.4）开发。** 待 P1-1 上线观察后另行启动。
> - 本期开发与测试范围 = 特性一（US-P1-01 ~ US-P1-04）。

Given/When/Then 缩写：**G** = Given，**W** = When，**T** = Then。

---

## 特性一：energy 历史写入降频（P1-1）

### US-P1-01：energy 历史写入受去重控制，避免每周期全量追加

**作为** 系统运维工程师，  
**我希望** energy 参数（`total_hot_quantity`、`total_cold_quantity`）在 `device_param_history` 中的写入频率受时间窗口控制，每个时间窗口内只写入第一条，  
**以便** 减少 `device_param_history` 的 INSERT 压力，缓解 MQTT 消费队列积压。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P1-01-1 | G | `PLCLatestDataHandler._write_history()` 已修改，energy 参数处理路径包含去重缓存逻辑 |
| AC-P1-01-2 | W | 同一设备（`specific_part`）的同一 energy 参数（`param_name`）在同一时间窗口内被第二次及以后写入 |
| AC-P1-01-3 | T | 该条记录被跳过，不追加到 `hist_objs`，不触发 `bulk_create()` 写入 `device_param_history` |
| AC-P1-01-4 | T | Django 日志中出现包含"energy"或"跳过"语义的 DEBUG 级别日志（或类似于 general 的"历史写入跳过"日志） |
| AC-P1-01-5 | G | 时间窗口边界跨越（如整点小时切换）[依赖 OQ-1/OQ-2] |
| AC-P1-01-6 | W | 新时间窗口内首次到达该设备的该 energy 参数数据 |
| AC-P1-01-7 | T | 该条记录正常写入 `device_param_history`，去重缓存 key 更新为新窗口标识 |

---

### US-P1-02：energy 去重缓存线程安全，与 general 去重缓存模式一致

**作为** 后端开发工程师，  
**我希望** energy 去重缓存的实现方式与 `_general_hist_last_hour` 完全对称，依赖 CPython GIL 而非显式锁，  
**以便** 保持代码风格一致，并避免在高频写入热路径中引入锁竞争。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P1-02-1 | G | energy 去重缓存以模块级 `dict` 形式定义（如 `_energy_hist_last_hour: dict = {}`） |
| AC-P1-02-2 | G | 代码注释说明依赖 GIL 原子性，极端情况多写一条可接受，无显式锁 |
| AC-P1-02-3 | W | 多个 energy worker 并发处理同一设备同一参数的消息 |
| AC-P1-02-4 | T | 不抛出异常；最坏情况该时间窗口多写一条，但不会出现数据丢失或死锁 |
| AC-P1-02-5 | T | 代码中无 `threading.Lock()`、`threading.RLock()` 或 `asyncio.Lock()` 等显式同步原语 |

---

### US-P1-03：energy 写入降频不影响 plc_data 和 plc_latest_data

**作为** 系统管理员，  
**我希望** energy 历史降频改动只影响 `device_param_history` 的写入，不影响计费和实时快照，  
**以便** 确保日常运营和计费数据不受性能优化干扰。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P1-03-1 | G | P1-1 代码变更已部署，`freeark-mqtt-consumer` 已重启 |
| AC-P1-03-2 | W | energy 采集周期到达（约每 6 分钟），MQTT 消息正常入队并被消费 |
| AC-P1-03-3 | T | `plc_latest_data` 表中对应设备的 `total_hot_quantity`、`total_cold_quantity` 字段正常更新（`updated_at` 推进） |
| AC-P1-03-4 | T | `plc_data` 表中当天对应行的能耗数据正常追加（与变更前行为一致） |
| AC-P1-03-5 | T | 仅 `device_param_history` 中 energy 参数的写入频率降低，每个时间窗口内只有第一条写入 |

---

### US-P1-04：energy 历史降频后，写入频率可通过查询验证

**作为** 运维工程师，  
**我希望** 在生产 MySQL 中用简单 SQL 验证 energy 参数的实际写入频率，  
**以便** 确认 P1-1 优化效果符合预期。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P1-04-1 | G | P1-1 已部署并运行至少一个完整时间窗口（如 1 小时）以上 |
| AC-P1-04-2 | W | 执行 `SELECT collected_at FROM device_param_history WHERE param_name = 'total_hot_quantity' AND specific_part = '<任一设备>' ORDER BY collected_at DESC LIMIT 20` |
| AC-P1-04-3 | T | 相邻两条记录的 `collected_at` 间隔不小于目标时间窗口（如 1 小时或 N 分钟），不再出现每 6 分钟一条的密集写入 [具体间隔依赖 OQ-1] |

---

## 特性二：worker 分配与 maxsize 调整（P1-2）

> **⚠ 本特性（P1-2）本期不开发** —— OQ-3 用户决策为策略 A（先观察）。US-P1-05、US-P1-06 归档保留，待 P1-1 上线、生产观察 1-2 天后，依据实测数据另行启动。下列用户故事不纳入 v0.5.4 的开发与测试范围。

### US-P1-05：worker 数量与 maxsize 调整后服务正常启动，队列积压缓解

**作为** 系统运维工程师，  
**我希望** `NUM_ENERGY_WORKERS`、`NUM_GENERAL_WORKERS`、`queue_maxsize` 三个常量按评估结果调整，且调整后 `freeark-mqtt-consumer` 服务正常重启，  
**以便** 在 P0 生效后，energy 队列的积压风险进一步降低，不再逼近 maxsize 上限。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P1-05-1 | G | `mqtt_consumer.py` 中的三个常量已按选定策略修改（策略见 OQ-3）[依赖 OQ-3] |
| AC-P1-05-2 | W | `sudo systemctl restart freeark-mqtt-consumer` 执行后 |
| AC-P1-05-3 | T | `systemctl status freeark-mqtt-consumer` 显示 `active (running)` |
| AC-P1-05-4 | T | Django 日志中出现 N 条（N = `NUM_ENERGY_WORKERS` + `NUM_GENERAL_WORKERS`，调整后）"Worker 线程启动"日志，能量和 general 各自对应 |
| AC-P1-05-5 | G | P0 已生效，P1-1 已部署，P1-2 调整后运行 24 小时以上 |
| AC-P1-05-6 | W | 查询生产 MySQL energy 参数的入库延迟（`created_at - collected_at`） |
| AC-P1-05-7 | T | energy 参数入库延迟均值显著低于调整前基线（20.5 分钟），目标值待 P0 生效后实测确定 [依赖 OQ-3 + 实测] |

---

### US-P1-06：worker 常量保持模块级定义，不引入配置化复杂度

**作为** 后端开发工程师，  
**我希望** worker 数量和 maxsize 的调整通过修改 `mqtt_consumer.py` 顶部的模块级常量完成，不引入配置文件驱动或数据库驱动的动态调整，  
**以便** 保持代码简洁，与现有实现风格一致，降低引入 bug 的风险。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P1-06-1 | G | P1-2 代码变更已完成 |
| AC-P1-06-2 | T | `NUM_ENERGY_WORKERS`、`NUM_GENERAL_WORKERS`、`queue_maxsize` 均为 `mqtt_consumer.py` 顶部的模块级整数常量，无额外的 JSON/YAML/DB 读取 |
| AC-P1-06-3 | T | `MQTTConsumer.__init__` 中对这三个常量的引用方式与变更前一致（通过默认参数传入） |
| AC-P1-06-4 | T | 代码中无新增的配置文件加载逻辑、数据库查询或环境变量读取用于这三个参数 |

---

## 附：用户故事与需求编号对照

| 用户故事 | 覆盖需求编号 |
|---------|------------|
| US-P1-01 | REQ-FUNC-001、REQ-FUNC-005、NFR2-1、NFR2-2、NFR3-1 |
| US-P1-02 | REQ-FUNC-002、NFR1-1、NFR1-2 |
| US-P1-03 | REQ-FUNC-003 |
| US-P1-04 | NFR3-2 |
| US-P1-05 | REQ-FUNC-006、REQ-FUNC-007、REQ-FUNC-008、NFR2-3 |
| US-P1-06 | REQ-FUNC-009 |

**未独立成故事的需求**（已在上述 AC 中隐含覆盖）：
- REQ-FUNC-004（保留 bulk_create 机制）：已在 US-P1-01 AC-P1-01-3 中体现
- REQ-FUNC-010（路由规则不变）：范围排除项，无需用户故事
- NFR4-1 ~ NFR4-5（部署约束）：已在 AC-P1-05-2/3 中体现
