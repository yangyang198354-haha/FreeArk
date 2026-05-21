# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.5.4
  title: MQTT 采集链路性能优化 P1 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.4
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (PLCLatestDataHandler._write_history, 751-786)
    - FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py (MQTTConsumer, 46-113)
    - docs/requirements/v0.5.2_dph_cleanup_service_mgmt/requirements_spec.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，基于性能调查报告，含开放问题 OQ-1~OQ-4 |
| 0.2.0-CONFIRMED | 2026-05-21 | 用户确认 OQ-1~OQ-4：P1-1 选方案 A，P1-2 选策略 A（先观察，本期不开发）。本期开发范围锁定为仅 P1-1 |

---

## 1. 背景与动因

### 1.1 业务背景

FreeArk 楼宇 PLC 数据采集平台通过「数据采集 → MQTT → Django 消费 → MySQL 入库」链路，将 568 个设备的 PLC 参数持续写入生产数据库（MySQL 192.168.31.98:3306，库名 `freeark`）。

2026-05-21 完成的性能调查报告（`data_collection_pipeline_perf_analysis_2026-05-21.md`）确认，**energy 参数（`total_hot_quantity`、`total_cold_quantity`）的入库延迟实测均值达 20.5 分钟，峰值 45 分钟**，4 个采集周期的数据积压在队列中未入库；energy 队列满载率估算约 97%，随时有丢消息风险。

### 1.2 P0 已完成事项（本特性的前提假设）

以下两项 P0 优化已由用户完成，本版本（v0.5.4）的所有需求以"P0 已生效"为前提：

| 序号 | 措施 | 完成状态 |
|------|------|---------|
| P0-1 | `freeark-dph-cleanup` systemd 服务已部署，今晚 22:00 执行第一次清理，预计将 `device_param_history` 从 3600 万行收缩至约 1060 万行 | 已部署，待首次执行 |
| P0-2 | 生产 MySQL `innodb_buffer_pool_size` 已由 128 MB 手工调整至 2 GB | 已完成 |

**本文档 REQ-FUNC-* 均不覆盖 P0 措施（已完成），不重复描述。**

### 1.3 本次范围：P1 两条优化

本次需求聚焦于性能调查报告建议的 P1 优先级两项：

- **P1-1**：对 energy 参数的历史写入引入去重 / 降低写入频率（`mqtt_handlers.py`）
- **P1-2**：重新评估 MQTT consumer worker 分配与队列 maxsize（`mqtt_consumer.py`）

P2（`ConnectionStatusHandler` 行锁优化）不在本期范围内。

---

## 2. 现状勘察结论（需求分析前置）

### 2.1 P1-1 相关现状（`mqtt_handlers.py`）

| 项目 | 现状 |
|------|------|
| 模块级常量 | `_ENERGY_PARAM_NAMES = frozenset(['total_hot_quantity', 'total_cold_quantity'])` |
| 模块级缓存 | `_general_hist_last_hour: dict = {}` — 仅用于 general 参数去重 |
| energy 分支 | `_write_history()` 中 `if param_name not in _ENERGY_PARAM_NAMES` 为 False 时直接追加，无任何去重/限流 |
| energy 写入频次 | 实测每 ≈ 6 分钟一批，568 设备 × 2 参数 ≈ **1136 行/批** |
| general 写入频次 | 每小时第一条写入（去重后），每批 ≈ 47,600 行 |
| energy 参数另存位置 | 同时写入 `plc_data`（按天聚合，计费用）和 `plc_latest_data`（最新快照）—— 这两张表不受本特性影响 |
| GIL 注释 | 现有注释称 `_general_hist_last_hour` 的 dict get/set 依赖 GIL 原子性，极端情况同一小时多写一条可接受 |

**关键问题**：`device_param_history` 中的 energy 历史在 `plc_data`（日聚合）和 `plc_latest_data`（快照）之外，对业务是否有独立查询价值？需要多细的时间粒度？这是 P1-1 选型的决策前提（见 OQ-1、OQ-2）。

### 2.2 P1-2 相关现状（`mqtt_consumer.py`）

| 常量 | 当前值 | 位置 |
|------|--------|------|
| `NUM_ENERGY_WORKERS` | 3 | `mqtt_consumer.py:48` |
| `NUM_GENERAL_WORKERS` | 6 | `mqtt_consumer.py:49` |
| `queue_maxsize` | 2000（energy / general 各一个） | `MQTTConsumer.__init__:57` |
| 路由规则 | payload < 2000 字节 → energy 队列；否则 → general 队列 | `on_message:255` |

**实测数据（调查报告）**：
- energy 队列积压估算 ~1939 条（maxsize=2000，~97% 满载）
- energy 平均延迟 20.5 分钟，general 平均延迟 5.6 分钟
- P0 生效后，单条 energy INSERT 将显著加速（索引驻留内存，消除随机 I/O），worker 分配需重新评估

---

## 3. 功能性需求

### FR1 — energy 历史写入降频（P1-1）

**来源**：性能调查报告 P1 建议"对 energy 参数的历史写入引入去重 / 批量 INSERT / 降低历史粒度"。

**背景**：当前 energy 参数每 6 分钟向 `device_param_history` 全量写入一批（1136 行），一天约 240 批（若无积压）。P0 完成后表体量将收缩、INSERT 变快，但 energy 数据本身是否需要每 6 分钟一条历史记录仍是开放问题（见 OQ-1、OQ-2）。**本 FR 的具体方案选型依赖 OQ-1 和 OQ-2 的用户答复，在用户确认前以"占位需求"方式呈现，实现细节由架构/设计阶段确定。**

| 编号 | 需求描述 | 依赖 |
|------|----------|------|
| REQ-FUNC-001 | `PLCLatestDataHandler._write_history()` 对 energy 参数（`_ENERGY_PARAM_NAMES` 所有成员）引入写入控制，降低其向 `device_param_history` 的写入频率。具体策略（每小时留一条 / 每 N 分钟留一条 / 其他）由 OQ-1 用户答复决定。 | OQ-1 |
| REQ-FUNC-002 | energy 写入控制逻辑必须与 general 的现有去重逻辑（`_general_hist_last_hour`）**风格一致**：使用模块级内存缓存，依赖 GIL 原子性（极端情况多写一条可接受，无需显式锁），不引入新的数据库表或外部存储。 | — |
| REQ-FUNC-003 | 写入控制仅影响 `device_param_history` 的写入频率；`plc_data`（能耗日报）和 `plc_latest_data`（最新快照）的写入逻辑**不受影响**，维持现有行为。 | — |
| REQ-FUNC-004 | `_write_history()` 已使用 `bulk_create()` 批量写入，该机制保留；本特性的优化方向是通过去重减少送入 `bulk_create()` 的记录数，而非改写批量写入机制本身。 | — |
| REQ-FUNC-005 | 控制策略的时间粒度参数（如"每小时"或"每 30 分钟"）应以模块级常量形式定义，便于后续调整，不硬编码在逻辑中。 | OQ-1 |

**REQ-FUNC-001 备注 — 已选定方案（2026-05-21 用户确认 OQ-1）：**

> **方案 A（每小时留一条，与 general 对齐）** —— 新建 `_energy_hist_last_hour: dict = {}` 缓存，逻辑与 general 分支完全对称，以 `collected_at` 的整点小时（`'%Y-%m-%d-%H'`）为 key，写入频率由每 6 分钟 → 每小时（降约 10 倍）。
>
> 方案 B（每 N 分钟粒度）、方案 C（完全不写入 device_param_history）均未选用 —— 用户确认 energy 历史"小时粒度趋势够用"。

---

### FR2 — MQTT consumer worker 分配调整（P1-2）

> **⚠ 本期（v0.5.4）不开发** —— OQ-3 用户决策为策略 A（先观察）。FR2 的需求与设计在本文档及设计文档中予以归档保留，但**不进入本期开发**。待 P1-1 上线、生产观察 1-2 天后，依据实测的 energy 入库延迟另行决定是否启动 P1-2 及具体策略。本期开发范围仅含 FR1（P1-1）。

**来源**：性能调查报告 P1 建议"重新评估 worker 分配（energy 适当增加），并复核 energy 队列 maxsize 余量"。

**背景**：**P0 完成后**，energy INSERT 性能预计有显著提升，worker 数量需求可能与 P0 前完全不同。本 FR 基于"P0 已生效"的前提，在架构/设计阶段通过推算给出推荐值，具体数值依赖 OQ-3 的用户决策。

| 编号 | 需求描述 | 依赖 |
|------|----------|------|
| REQ-FUNC-006 | 评估并调整 `NUM_ENERGY_WORKERS` 常量。评估前提：P0 完成后 energy INSERT 延迟预计从"秒级"降至"毫秒级"（索引驻留内存），需重新计算 3 个 worker 是否仍是瓶颈。具体目标值由 OQ-3 用户答复决定；若用户选择保守策略，可保持 3 不变。 | OQ-3 |
| REQ-FUNC-007 | 评估并调整 `NUM_GENERAL_WORKERS` 常量。general 链路当前表现健康（5.6 分钟延迟），P0 后改善幅度有限；general worker 如有富余可考虑适当减少，或维持 6 不变。具体数值由 OQ-3 用户答复决定。 | OQ-3 |
| REQ-FUNC-008 | 复核 `queue_maxsize`（当前 2000）是否需要调整。P0 后若 energy 消费速度提升，97% 满载状态应自然缓解；若用户要求增加安全裕量，可适当上调 maxsize。具体数值由 OQ-3 用户答复决定；若用户选择观察，可保持 2000 不变。 | OQ-3 |
| REQ-FUNC-009 | `NUM_ENERGY_WORKERS`、`NUM_GENERAL_WORKERS`、`queue_maxsize` 三个常量均保持在 `mqtt_consumer.py` 顶部的模块级常量位置，不引入配置文件或数据库配置化。变更后需重启 `freeark-mqtt-consumer` systemd 服务生效。 | — |
| REQ-FUNC-010 | 路由规则（`_ENERGY_PAYLOAD_MAX_SIZE = 2000` 字节分界线）不在本特性调整范围内，维持现有逻辑。 | — |

---

## 4. 非功能性需求

### NFR1 — 线程安全

| 编号 | 需求描述 |
|------|----------|
| NFR1-1 | energy 历史去重缓存（若新建）的线程安全模型必须与 `_general_hist_last_hour` 保持一致：依赖 CPython GIL 保证 dict 单次 get/set 的原子性，极端情况（多 worker 并发写同一 key）最多多写一条历史记录，业务可接受，不引入显式锁或线程同步原语。 |
| NFR1-2 | 不得引入 `threading.Lock` 或其他同步原语到历史写入的热路径中，避免在高频 INSERT 场景下引入锁竞争反而降低吞吐。 |

### NFR2 — 性能

| 编号 | 需求描述 |
|------|----------|
| NFR2-1 | P1-1 实施后，energy 参数对 `device_param_history` 的写入频率降低幅度应不低于 5 倍（相对现有每 6 分钟一条）。具体降幅由 OQ-1 答复后确定，方案 A（每小时一条）降幅为 10 倍。 |
| NFR2-2 | P1-1 实施后，`_write_history()` 在正常去重生效的情况下，energy 批次的 `hist_objs` 为空（或显著减少），`bulk_create()` 调用次数随之减少；已有 `"历史写入跳过（均已在本小时记录）"` 日志可作为验证手段。 |
| NFR2-3 | P1-2 的 worker 数量调整不得导致 general 链路延迟超过当前基线（5.6 分钟均值），一般通过维持 general worker 数量或仅小幅调整保证。 |
| NFR2-4 | 本次代码变更不引入额外的数据库表、索引或 migration。`device_param_history` 表结构本身不变更。 |

### NFR3 — 可观测性

| 编号 | 需求描述 |
|------|----------|
| NFR3-1 | energy 历史写入增加去重跳过日志（与 general 的 `"历史写入跳过（均已在本小时记录）"` 等级和格式对齐），便于运维确认去重策略实际生效。 |
| NFR3-2 | 变更后，通过查询 `device_param_history` 中 energy 参数的 `collected_at` 时间分布，可验证写入频率是否符合目标粒度。 |

### NFR4 — 部署与运维

| 编号 | 需求描述 |
|------|----------|
| NFR4-1 | 生产环境：树莓派 192.168.31.51，项目路径 `/home/yangyang/Freeark/FreeArk`，物理机部署，禁止 Docker。 |
| NFR4-2 | 部署方式：plink SSH + `git pull`，禁止 pscp 逐文件上传。 |
| NFR4-3 | 两个源文件（`mqtt_handlers.py`、`mqtt_consumer.py`）均属于 Django backend 进程，代码变更后需重启 `freeark-mqtt-consumer` systemd 服务（`sudo systemctl restart freeark-mqtt-consumer`）。 |
| NFR4-4 | 测试环境统一用 SQLite，严禁测试连生产库。 |
| NFR4-5 | `_general_hist_last_hour`（及新建的 energy 去重缓存）为进程内模块级内存缓存，服务重启后缓存清空，下一个采集周期重新积累。此行为已知且可接受（最坏情况多写一批 1136 行）。 |

---

## 5. 范围边界与排除项

| 项目 | 是否在本期范围 | 说明 |
|------|--------------|------|
| P0-1: dph 清理 systemd 服务 | 否 | 已完成，见 v0.5.2 |
| P0-2: innodb_buffer_pool_size 调整 | 否 | 已由用户手工完成 |
| P2: ConnectionStatusHandler 行锁优化 | 否 | 性能调查报告中标注为 P2，本期不做 |
| energy 采集频次调整（task_scheduler） | 否 | 采集端不在本次范围，消费端降频已足够 |
| device_param_history 表结构变更/分区 | 否 | 超出本期范围 |
| MQTT 路由规则（payload 2000B 分界线）调整 | 否 | REQ-FUNC-010 明确排除 |
| plc_data / plc_latest_data 写入逻辑 | 否 | REQ-FUNC-003 明确排除 |
| energy 历史查询 API 新增 | 否 | 不在本期 |
| 配置文件/数据库驱动的 worker 数量动态调整 | 否 | REQ-FUNC-009 明确模块级常量形式即可 |

---

## 6. 开放问题（Open Questions）与用户决策

> **状态：OQ-1~OQ-4 已于 2026-05-21 经用户全部答复确认。** 下方各 OQ 详述保留原始问题描述以备追溯；正文中凡标注"推荐 / 待确认 / 依赖 OQ-X"之处，一律以下表决策结论为准。

### 决策结论（2026-05-21 用户确认）

| 开放问题 | 用户决策 | 对需求的影响 |
|---------|---------|------------|
| OQ-1 | **方案 A** —— energy 历史每小时保留一条（小时粒度趋势够用） | REQ-FUNC-001 锁定为方案 A |
| OQ-2 | **整点小时对齐**（与 general 一致，OQ-1=A 时的默认方式） | `_write_history` energy 分支用 `'%Y-%m-%d-%H'` 作 key |
| OQ-3 | **策略 A —— 先观察** | FR2 / REQ-FUNC-006~009（P1-2）本期**不开发**，待 P1-1 上线观察 1-2 天后再评估 |
| OQ-4 | 随 OQ-3 决定 —— **分批**：本期仅开发并部署 P1-1 | P1-1 与 P1-2 不合并部署；P1-2 留待后续 |

**本期（v0.5.4）开发范围据此锁定为：仅 P1-1（FR1 / REQ-FUNC-001~005 及相关 NFR）。** FR2（P1-2）的需求与设计予以归档保留，不进入本期开发。

---

以下为各开放问题的原始详述（保留备查）：

---

### OQ-1：energy 历史在 device_param_history 中的业务价值与所需粒度

**背景**：energy 参数（`total_hot_quantity`、`total_cold_quantity`）同时存在于三张表：

| 表 | 用途 | 粒度 |
|----|------|------|
| `plc_latest_data` | 最新快照，实时展示当前值 | 每次采集覆盖 |
| `plc_data` | 按天聚合计费，写入每日用量 | 每采集周期追加当天行 |
| `device_param_history` | 时序历史，当前每 6 分钟一条 | 每 6 分钟一批（待优化） |

**问题**：`device_param_history` 中的 energy 历史记录，是否有实际的业务查询场景？

具体子问题：
1. 是否有看板图表或报表需要查询 energy 的**分钟级**历史（即比"每天"更细但比"每小时"更细）？
2. 还是"每小时一条"已经足够支撑所有现有和规划中的查询？
3. 或者 energy 的历史趋势完全可以从 `plc_data`（日报）推导，根本不依赖 `device_param_history` 中的 energy 行？

**答复将决定**：
- 方案 A：每小时留一条（与 general 对齐），降幅 10 倍
- 方案 B：每 N 分钟留一条（N 由用户指定，如 30 分钟），降幅 2-5 倍
- 方案 C：完全不写入 device_param_history（若确认无查询价值），降幅 100%

---

### OQ-2：energy 历史去重的时间对齐方式

**背景**：general 的去重以 `collected_at` 的小时（`'%Y-%m-%d-%H'`）为 key，即**整点对齐**——同一小时内第一条写入，之后跳过，跨小时后写一条。

**问题**（仅在 OQ-1 答复为"需要保留，但可降粒度"时相关）：
1. energy 去重是否沿用相同的整点小时对齐方式（简单，与 general 完全一致）？
2. 还是希望用 collected_at 的 N 分钟窗口取整（如每 30 分钟的第一条），即按"时间桶"对齐而非整点？

**注意**：`total_hot_quantity` / `total_cold_quantity` 是累计量（非增量），相邻两个整点时刻的值差即为该小时的实际用量，因此"整点小时对齐"在计费粒度上与 `plc_data` 是一致的。

**默认推荐**（若用户无特殊要求）：与 general 一致，使用整点小时对齐，方案最简单，风险最低。

---

### OQ-3：P0 生效后 worker 数量调整策略

**背景**：
- P0-2（buffer pool 2GB）生效后，energy INSERT 从"随机磁盘 I/O"变为"内存操作"，单条处理时间预计从 ≥2s 大幅降至数十毫秒量级
- P0-1（dph 清理）完成后，表体量约 1060 万行，索引大小进一步降低，INSERT 进一步加速
- 届时 energy 队列积压的根因（INSERT 太慢）将大幅改善，3 个 worker 的吞吐可能已足够

**问题**：用户希望在 P0 生效后采用哪种 worker 调整策略？

| 策略 | energy workers | general workers | maxsize | 适用场景 |
|------|----------------|-----------------|---------|---------|
| A: 保守观察 | 3（不变） | 6（不变） | 2000（不变） | P0 后观察一段时间，若积压消除则无需调整 |
| B: 小幅增加 energy | 5 或 6 | 6（不变） | 2000（不变） | 担心 P0 效果不足，提前加固 energy 吞吐 |
| C: 重新平衡 | 6 | 4 | 2000（不变） | worker 总数不变（维持系统负载），但从 general 调配至 energy |
| D: 扩大 maxsize | 3（不变） | 6（不变） | 3000 或 4000 | 主要目的是增加缓冲余量，防止丢消息，不增加 DB 压力 |
| 自定义 | 用户指定 | 用户指定 | 用户指定 | — |

**建议**（PM 视角）：优先建议"先执行 P1-1（降低 energy 写入频率），在 P0 生效后观察 1-2 天，再决定是否需要 P1-2 调整"。P1-1 本身已能大幅降低 energy worker 的单条处理时间（去重后大多数消息不触发 INSERT），可能使 worker 分配问题自然消解。

---

### OQ-4：P1-1 和 P1-2 的实施顺序

**背景**：P1-1（降低 energy 写入频率）和 P1-2（调整 worker 数量）可以独立部署，也可以一次性打包部署。

**问题**：
1. 是否希望先部署 P1-1，观察效果（预计 1-2 天），再决定是否部署 P1-2？
2. 还是希望 P1-1 和 P1-2 在同一个 commit 中一次性部署？

**注意**：P1-1 与 P1-2 修改的是不同文件（`mqtt_handlers.py` vs `mqtt_consumer.py`），代码上无依赖，两者均触发同一个 `freeark-mqtt-consumer` 服务重启。建议拆分，但最终由用户决定。

---

## 7. 与已有文档的关系

| 文档 | 关系 |
|------|------|
| `docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md` | 本特性的需求来源，P1 建议是本文档的直接实现 |
| `docs/requirements/v0.5.2_dph_cleanup_service_mgmt/requirements_spec.md` | 覆盖了 P0-1（dph 清理服务），本特性与之平行，不修改其内容 |
| `docs/requirements/v0.5.2_waitress_db_tuning/` | 覆盖了看板 API 性能调优，与本特性无直接依赖 |
| `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 本特性 P1-1 的修改目标（`_write_history` 方法 + 模块级常量） |
| `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | 本特性 P1-2 的修改目标（`NUM_ENERGY_WORKERS` 等常量） |
