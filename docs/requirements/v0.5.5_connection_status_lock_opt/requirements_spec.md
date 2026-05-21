# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.5.5
  title: MQTT 采集链路性能优化 P2 — ConnectionStatusHandler 行锁路径优化 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.5
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md
    - docs/requirements/v0.5.4_mqtt_pipeline_perf_p1/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (ConnectionStatusHandler, 452-594)
    - FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py (energy_handlers 配置, 92-97)
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，含开放问题 OQ-1~OQ-3，等待用户确认 |
| 1.0.0-CONFIRMED | 2026-05-21 | 用户确认实施 P2：OQ-1=A（确认实施）、OQ-2=方案 A（进程内缓存 + 快/慢路径分离）、OQ-3=可接受（重启后首批走慢路径）。需求锁定，进入开发。 |

---

## 1. 背景与动因

### 1.1 业务背景

FreeArk 楼宇 PLC 数据采集平台通过「数据采集 → MQTT → Django 消费 → MySQL 入库」链路，持续处理约 568 个设备的 energy 参数（`total_hot_quantity`、`total_cold_quantity`）及约 596 个设备的 general 参数。

### 1.2 前序优化已完成事项

以下优化均已落地，本版本（v0.5.5）的需求以"P0/P1-1 均已生效"为前提：

| 序号 | 措施 | 完成状态 | 备注 |
|------|------|---------|------|
| P0-1 | `freeark-dph-cleanup` systemd 服务，清理 device_param_history 至合理规模 | 已完成 | v0.5.2 |
| P0-2 | 生产 MySQL `innodb_buffer_pool_size` 128MB → 2GB | 已完成 | 用户手工调整 |
| P1-1 | energy 参数历史写入按小时去重（`_energy_hist_last_hour` 缓存） | 已完成并部署 | v0.5.4，commit cafa7b6 |
| P1-2 | MQTT consumer worker 分配调整 | 暂缓 | 用户选策略 A（先观察），需求/设计已归档 |

### 1.3 本次范围：P2 — ConnectionStatusHandler 行锁路径优化

**性能调查报告「瓶颈 4」**（`data_collection_pipeline_perf_analysis_2026-05-21.md` §4）指出：3 个 energy worker 并发执行 `ConnectionStatusHandler._update_connection_status()` 时，`select_for_update()` 对 `PLCConnectionStatus` 表的同一批行存在行锁竞争，估算约 150ms/条。

**当前现状（代码精读，v0.5.4 后）**：

| 方面 | 现状 |
|------|------|
| 调用范围 | `ConnectionStatusHandler` 仅在 `energy_handlers` 链中（`mqtt_consumer.py:93-97`）；general handler 链明确跳过（注释"节省约 150ms/条"） |
| 单次调用路径 | `transaction.atomic()` → `select_for_update().get_or_create(specific_part=...)` → （若状态变化）`PLCStatusChangeHistory.objects.create()` → `plc_status.save()` |
| 行锁来源 | `select_for_update()` 在 `transaction.atomic()` 内对 `PLCConnectionStatus` 的对应行加 InnoDB 行锁，整个事务期间持有 |
| 并发模式 | 3 个 energy worker 线程，各持独立 Django DB 连接；每条 energy 消息触发一次 `_update_connection_status`（每设备一次） |
| 状态变化频率 | 设备上下线事件属于**低频异常事件**；正常运行期间，绝大多数调用的状态为"无变化"（设备持续在线） |
| 对延迟的当前贡献 | P0+P1-1 生效后，energy worker 的 3 个耗时操作估算：PLCDataHandler ≤50ms + **ConnectionStatusHandler ≈150ms（行锁）** + PLCLatestDataHandler ≤50ms；行锁占比约 60%，是现在的主要耗时源 |
| SQLite 行为差异 | SQLite 不支持行级锁；`select_for_update()` 在 SQLite 上退化为全表锁或空操作，测试环境无法复现行锁竞争 |

**P0+P1-1 联合效果下的重新评估**：

根据 ADR-003（v0.5.4 架构文档）的推算，P1-1 生效后，3 个 energy worker 的吞吐约为 7.5–15 条/秒，远超到达速率 1.58 条/秒，积压已有望自然消解。**因此，P2 在当前形势下的必要性需要用户确认**（详见 §6 OQ-1）。

---

## 2. 现状勘察结论（需求分析前置）

### 2.1 `_update_connection_status()` 代码精读

**来源**：`mqtt_handlers.py` 528-593 行。

当前实现逻辑：

```
transaction.atomic() 开始
  ① select_for_update().get_or_create(specific_part=<设备ID>, defaults={...})
     → 若不存在：INSERT 新行（created=True），加行锁
     → 若已存在：SELECT + 加行锁（created=False）
  ② 若 created=True 或 connection_status 字段值变化：
       PLCStatusChangeHistory.objects.create(...)  — 插入变更历史
  ③ 若 created=False：
       plc_status.connection_status = status
       plc_status.building = building
       plc_status.unit = unit
       plc_status.room_number = room_number
  ④ 若 status == 'online'：
       plc_status.last_online_time = timezone.now()
  ⑤ plc_status.save()
transaction.atomic() 结束（释放行锁）
```

**关键观察**：

- **步骤 ①** 无论状态是否变化，每次调用都执行 `select_for_update()`，每次都在 `transaction.atomic()` 的生命周期内持有行锁。
- **步骤 ③ + ⑤** 无论 `connection_status` 是否真正变化，对于 `created=False` 的情形，`building`、`unit`、`room_number` 字段总是被重写（即使值相同）；`save()` 总是执行（只要 `created=False`）。
- **正常运行时**（设备持续在线），每次调用均经历：行锁等待 → 获取锁 → 读现有行 → 判断 status 未变化 → 仍然执行 `save()`（更新相同字段） → 释放行锁。这是当前 150ms 耗时的来源。
- **`PLCStatusChangeHistory` 记录能力**（硬约束）：状态变化历史对运维至关重要，任何优化方案不得丢失状态从 A 变为 B 的记录能力。

### 2.2 `PLCConnectionStatus` 表特征

- 主键 / 唯一键：`specific_part`（设备标识符）
- 体量：每台设备一行，共约 568 行（energy 设备数），行数极少
- `connection_status` 字段：字符串 `'online'` 或 `'offline'`
- 变化特性：正常运行期间该值**极少变化**（设备上线后长期保持 `online`）；仅在设备上下线事件时变化

### 2.3 P2 的必要性评估维度

以下数据供用户判断 P2 是否值得实施（见 §6 OQ-1）：

| 指标 | 当前估算（P0+P1-1 后） |
|------|---------------------|
| energy 到达速率 | 1.58 条/秒（568 设备 × 2 参数 / 6 分钟 ÷ 60 ≈ 1.58/s；但每 MQTT 消息含 1 台设备，故 ≈1.58 消息/秒） |
| 3 worker 理论吞吐（当前，行锁 150ms 主导） | ≈ 3 / 0.25s ≈ 12 条/秒 |
| 3 worker 理论吞吐（P2 后，行锁消除，剩余 ~100ms） | ≈ 3 / 0.10s ≈ 30 条/秒 |
| 对延迟的边际收益 | 从 ~250ms/条 降至 ~100ms/条；队列积压在当前形势下已可能为零 |

**结论**：P0+P1-1 已使吞吐远超到达速率，队列积压根因已消除。P2 是锦上添花的优化，对当前积压问题无决定性意义，**但对 energy worker 延迟指标仍有 60% 的提升空间**。

---

## 3. 功能性需求

> **重要**：§3 的具体方案依赖 §6 开放问题的用户决策。以下需求以"P2 确认实施"为前提呈现；若用户在 OQ-1 决策"暂缓"，则本节全部需求不进入本期开发（归档保留，与 P1-2 处理方式一致）。

### FR1 — 消除或减少 `ConnectionStatusHandler` 的 `select_for_update()` 行锁

**来源**：性能调查报告 P2 建议"优化 `ConnectionStatusHandler` 的 `select_for_update` 行锁路径"。

**背景**：当前实现在每条 energy 消息处理时，无论设备连接状态是否变化，均执行一次 `select_for_update()` 行锁。在设备正常运行（持续在线）的情形下，行锁竞争产生约 150ms 的不必要等待。

**约束**（来自用户硬约束，不可削弱）：
- 设备状态变化（online → offline，或 offline → online）必须记录到 `PLCStatusChangeHistory` 表，不得丢失。
- 新建设备（`PLCConnectionStatus` 表中无对应行）时，必须正确 INSERT 初始状态行。

| 编号 | 需求描述 | 备注 |
|------|----------|------|
| REQ-FUNC-001 | `_update_connection_status()` 的实现**必须**在状态真正变化（`online` ↔ `offline`，或首次创建）时，向 `PLCStatusChangeHistory` 写入一条变更历史记录。这是不可削弱的硬约束，任何优化方案均须满足。 | 硬约束，来自用户 |
| REQ-FUNC-002 | 优化实施后，在正常运行期间（设备持续 `online`），对 `PLCConnectionStatus` 表的写操作应当减少或消除（目标：无状态变化时不执行 `UPDATE`）。 | 方案选型依赖 OQ-2 |
| REQ-FUNC-003 | 优化实施后，若设备状态发生变化，`PLCConnectionStatus` 表的对应行必须在事务内更新（`connection_status`、`building`、`unit`、`room_number`、`last_online_time` 等字段保持完整更新语义）。 | — |
| REQ-FUNC-004 | 优化实施后，若 `PLCConnectionStatus` 表中不存在对应 `specific_part` 的行（新设备），必须正确创建该行（包含初始的 `connection_status`、`building`、`unit`、`room_number` 字段）。 | — |
| REQ-FUNC-005 | 优化方案不得引入新的数据库表、Django model、migration 或外部存储（Redis、文件缓存等）。纯内存缓存（进程级 dict）可用，但需在 §4 NFR 约束范围内。 | 方案选型依赖 OQ-2 |

### FR2 — 优化 `PLCConnectionStatus` 的 `save()` 路径

**背景**：当前 `created=False` 时，`save()` 总是执行，即使 `connection_status`、`building`、`unit`、`room_number` 字段均未变化（仅 `last_online_time` 在 `status=='online'` 时更新）。

| 编号 | 需求描述 | 备注 |
|------|----------|------|
| REQ-FUNC-006 | 若状态无变化（`created=False` 且 `connection_status == status`），且 `last_online_time` 的更新是必要的，`save()` 应仅更新必要字段（通过 `update_fields` 限制），避免全字段 UPDATE。 | 方案选型依赖 OQ-2 |
| REQ-FUNC-007 | 若状态无变化且无需更新 `last_online_time`（如 `status == 'offline'` 且状态已是 `offline`），`save()` 应当**跳过**，不执行任何 DB 写操作。 | 方案选型依赖 OQ-2 |

---

## 4. 非功能性需求

### NFR1 — 数据一致性（最高优先级）

| 编号 | 需求描述 |
|------|----------|
| NFR1-1 | 状态变化历史（`PLCStatusChangeHistory`）不得出现漏记：设备状态每次从 A 变到 B（A ≠ B），或首次创建，必须有且仅有一条对应历史记录。 |
| NFR1-2 | 在多 worker 并发场景下，不得出现"两个 worker 同时判断状态未变化，实则其中一个先变化后被覆盖"导致状态历史缺失的竞态条件。优化方案须分析并保证此一致性。 |
| NFR1-3 | `PLCConnectionStatus` 表每个 `specific_part` 有且仅有一行（当前通过 `get_or_create` 保证），优化后该约束须维持。 |

### NFR2 — 线程安全

| 编号 | 需求描述 |
|------|----------|
| NFR2-1 | 若方案使用进程级内存缓存（dict）作为"本地状态副本"或"去重缓存"，需在设计文档中明确其线程安全边界，并评估最坏情况（多 worker 并发写同一设备）对 `PLCStatusChangeHistory` 的影响。 |
| NFR2-2 | 不得在热路径（每条 energy 消息处理中）引入 Python 层面的显式锁（`threading.Lock` 等），以避免锁竞争转移问题（将数据库行锁竞争转变为 Python 锁竞争）。 |

### NFR3 — 测试可行性（SQLite 兼容）

| 编号 | 需求描述 |
|------|----------|
| NFR3-1 | 测试环境使用 SQLite，SQLite 不支持 `select_for_update()` 的行级锁语义（会退化为全表锁或空操作）。优化后的实现必须在 SQLite 环境下可正常运行（不因 SQLite 行为差异抛出未捕获异常）。 |
| NFR3-2 | 若优化方案去除了 `select_for_update()`，SQLite 测试的一致性验证应通过模拟并发调用或序列化调用的方式覆盖关键业务逻辑（状态变化检测、历史记录写入）。 |
| NFR3-3 | 若优化方案保留 `select_for_update()` 但缩短持锁范围，测试用例须能验证状态变化检测和历史写入的正确性（对 SQLite 行为差异免疫）。 |

### NFR4 — 性能

| 编号 | 需求描述 |
|------|----------|
| NFR4-1 | 优化后，在设备持续在线（无状态变化）的正常运行场景下，`_update_connection_status()` 单次调用的平均耗时应低于优化前的 150ms 基线。具体目标值由架构决策阶段的方案选型决定，须在设计文档中给出估算。 |
| NFR4-2 | 在设备状态发生变化的场景下，`_update_connection_status()` 的正确性优先于性能——允许此路径耗时高于正常路径，但须保证 `PLCStatusChangeHistory` 写入的原子性。 |

### NFR5 — 可观测性

| 编号 | 需求描述 |
|------|----------|
| NFR5-1 | 优化实施后，应保留或新增 DEBUG 级别日志，说明每次调用是走了"无变化快路径"还是"状态变化慢路径"，便于运维排查设备上下线事件。 |
| NFR5-2 | `PLCStatusChangeHistory` 记录是状态变化的持久化审计日志，运维可通过查询该表确认优化后状态变化记录未丢失。 |

### NFR6 — 部署与运维

| 编号 | 需求描述 |
|------|----------|
| NFR6-1 | 生产环境：树莓派 192.168.31.51，项目路径 `/home/yangyang/Freeark/FreeArk`，物理机部署，**禁止 Docker/容器化**。 |
| NFR6-2 | 部署方式：plink SSH + `git pull`，**禁止 pscp 逐文件上传**。代码变更后需重启 `freeark-mqtt-consumer` systemd 服务（`sudo systemctl restart freeark-mqtt-consumer`）。 |
| NFR6-3 | 本次变更仅涉及 `mqtt_handlers.py`（`ConnectionStatusHandler` 类内部实现），不修改 `mqtt_consumer.py`、`models.py`，不引入新 migration，不影响前端。 |
| NFR6-4 | 测试环境统一用 SQLite，**严禁测试连生产库**。 |
| NFR6-5 | 生产数据库：MySQL 192.168.31.98:3306，库 `freeark`，`innodb_buffer_pool_size` 现为 2GB。优化方案须在此配置下有效。 |
| NFR6-6 | 回滚方案：`git revert` 对应 commit + `sudo systemctl restart freeark-mqtt-consumer`。回滚后 `ConnectionStatusHandler` 恢复原始行锁实现，无数据损失。 |

---

## 5. 范围边界与排除项

| 项目 | 是否在本期范围 | 说明 |
|------|--------------|------|
| P0-1: dph 清理服务 | 否 | 已完成，见 v0.5.2 |
| P0-2: innodb_buffer_pool_size 调整 | 否 | 已完成 |
| P1-1: energy 历史写入按小时去重 | 否 | 已完成，见 v0.5.4 |
| P1-2: MQTT consumer worker 分配调整 | 否 | 暂缓，见 v0.5.4 归档 |
| `PLCConnectionStatus` 表结构变更 | 否 | 不引入新字段或索引，不做 migration |
| `PLCStatusChangeHistory` 表结构变更 | 否 | 不变更，仅保留写入逻辑正确性 |
| general handler 链的 ConnectionStatusHandler | 否 | general 消息本来就跳过此 handler，本期不变 |
| energy 采集频次调整 | 否 | 采集端不在范围 |
| `PLCDataHandler` / `PLCLatestDataHandler` | 否 | 本次只优化 `ConnectionStatusHandler` |
| 前端 / API / migration | 否 | 无任何前端变更，无新 API，无 migration |

---

## 6. 开放问题（Open Questions）

以下问题须用户确认后，才能锁定需求范围和方案。

> **【已解决 — 2026-05-21 用户确认】**
>
> | 开放问题 | 用户决策 | 影响 |
> |---------|---------|------|
> | OQ-1 | **选项 A — 确认实施 P2** | 全部功能性需求 FR1/FR2 进入本期开发 |
> | OQ-2 | **方向 A — 进程内状态缓存 + 快/慢路径分离** | 由 ADR-001 锁定方案 A 为最终方案 |
> | OQ-3 | **可接受** | 服务重启后首批消息走一次慢路径（与 P1-1 缓存重建行为一致），用户确认可接受 |
>
> 以下 OQ 原文保留备查。

---

### OQ-1：P0+P1-1 已生效后，P2 是否仍有必要？

**背景**：

性能调查报告调查时（2026-05-21），energy 链路有约 20 分钟积压，queue 满载率约 97%，原因是：
1. `device_param_history` 膨胀导致 INSERT 极慢（根因，瓶颈 1）
2. energy worker 仅 3 个（瓶颈 3）
3. `select_for_update()` 行锁约 150ms（瓶颈 4，即 P2 的优化目标）

P0-1、P0-2、P1-1 完成后：
- 瓶颈 1 已大幅缓解（P0 已生效，INSERT 从磁盘 I/O 级别降至内存级别）
- P1-1 生效后，绝大多数 energy 消息不再触发 `device_param_history` INSERT（去重后约 1/10 的消息才写入）
- 经 v0.5.4 ADR-003 推算：P1-1 后 energy worker 吞吐约 12-15 条/秒，到达速率约 1.58 条/秒，吞吐充裕，**队列积压问题可能已经消解**

在此背景下，P2 的行锁优化：
- **收益**：energy worker 平均处理时间从 ~250ms 降至 ~100ms，延迟指标改善；worker 线程利用率降低，对树莓派 CPU/DB 连接有轻微正向效果
- **成本**：代码复杂度增加（从简单的 `select_for_update().get_or_create()` 改为更复杂的逻辑）；引入进程级缓存的话，重启后首批消息处理行为需要分析；测试覆盖需要增加并发场景

**请用户确认以下选项之一：**

| 选项 | 描述 |
|------|------|
| A — 确认实施 P2 | 认为行锁优化的性能收益值得投入，希望本期完成需求与设计（并在确认后进入开发） |
| B — 暂缓 P2 | P0+P1-1 后积压已消解，P2 优先级已降低，暂不实施（需求/设计文档归档保留，后续视生产观察结果再评估） |
| C — 观察后决定 | 用户希望先查询生产实测数据（energy 入库延迟 `created_at - collected_at`），根据实测结果决定 |

**若选 A，请同时回答 OQ-2 和 OQ-3。若选 B 或 C，本期 P2 文档归档，不进入开发。**

**建议**：如当前用户尚未收集 P1-1 部署后的生产实测延迟数据，建议先选 C（观察 1-2 天），取一次 `SELECT AVG(TIMESTAMPDIFF(SECOND, collected_at, created_at)) FROM device_param_history WHERE param_name='total_hot_quantity' AND collected_at > NOW() - INTERVAL 2 HOUR` 的基线，再做决策。

---

### OQ-2：P2 优化方案选型

**背景**（仅在 OQ-1 = A 时相关）：

设计阶段架构师将在 ADR 中给出 ≥2 方案的对比，供用户最终拍板。以下为需求阶段的初步方向分析：

**方向 A — 去除 `select_for_update()`，改用进程内状态缓存 + 乐观写入**

思路：在进程内维护一个 `_connection_status_cache: dict` （`specific_part` → `'online'/'offline'`），每次 `_update_connection_status()` 调用时：
1. 先查缓存，若缓存显示状态未变化 → 仅执行轻量 `UPDATE ... SET last_online_time=... WHERE specific_part=...`（用 `update_fields` 限制），不加行锁
2. 若缓存 miss（新设备）或缓存状态与当前不同 → 走 `select_for_update()` 行锁路径（保证并发安全），写入 `PLCStatusChangeHistory`，更新缓存
3. 进程重启后缓存清空，首批消息触发一次带行锁的"慢路径"重新建立缓存

**优点**：正常运行时（无状态变化）完全消除行锁等待  
**缺点**：引入内存缓存，需分析缓存一致性和竞态边界；重启后首批消息仍走行锁路径

**方向 B — 保留 `select_for_update()`，但缩短持锁范围 + 减少不必要 `save()`**

思路：保留 `transaction.atomic()` + `select_for_update()`，但优化事务内的 `save()` 逻辑：
1. 若状态未变化：仅在 `status == 'online'` 时用 `update_fields=['last_online_time']` 执行最小化 UPDATE，其余字段不写；若 `status == 'offline'` 且状态无变化，跳过 `save()`
2. 不引入内存缓存，实现逻辑最简单

**优点**：逻辑最简单，不引入缓存；改善了不必要的全字段 UPDATE；行锁本身仍存在，但持锁时间缩短  
**缺点**：行锁竞争根因未消除，性能提升有限（缩短持锁时间，但等待时间取决于并发度）

**方向 C — 改用 `update_or_create()`（去掉显式 `select_for_update()`）**

思路：`update_or_create()` 内部使用 `SELECT` + `INSERT/UPDATE`，不显式加 `SELECT ... FOR UPDATE` 行锁，依赖数据库的 `INSERT` 唯一约束冲突检测保证原子性。  
**缺点**：`update_or_create()` 在 Django 中仍在 `atomic()` 块内，并不能完全消除并发竞争；MySQL InnoDB 在 `INSERT ON DUPLICATE KEY UPDATE` 时仍可能有间隙锁；更重要的是，**状态变化检测逻辑（判断 old_status vs new_status）无法直接通过 `update_or_create()` 原子实现**，仍需先读后写，从而引入 TOCTOU 竞态。

**请用户在 OQ-1=A 后，由架构师在设计阶段给出 ≥2 方案的完整 ADR（含方案 A/B 的一致性分析、性能估算），再由用户拍板。此 OQ 在需求阶段不需要用户立即选择——仅需用户知悉方向，设计阶段补全。**

---

### OQ-3：若使用进程内状态缓存（方向 A），服务重启后的首批行为是否可接受？

**背景**（仅在 OQ-1=A 且设计阶段选用方向 A 时相关）：

若采用进程内缓存方案：
- 服务重启后，`_connection_status_cache` 为空
- 第一批 energy 消息（约 568 条，每设备一条）的 `_update_connection_status()` 调用均为"缓存 miss"，均走带行锁的"慢路径"
- 重建缓存期间，行锁竞争与优化前相同（约 150ms/条），但此后（同一进程生命周期内）转入快路径
- 服务正常运行期间重启频率极低（仅代码部署时），此影响可接受

**请用户确认**：服务重启后首批消息走一次慢路径，是否可接受？（预期答复：可接受，与 P1-1 缓存重建的行为一致。）

---

## 7. 与已有文档的关系

| 文档 | 关系 |
|------|------|
| `docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md` | 本特性需求来源，P2 建议是本文档的直接实现 |
| `docs/requirements/v0.5.4_mqtt_pipeline_perf_p1/requirements_spec.md` | P1 需求，本特性与之平行，体例保持一致 |
| `docs/architecture/architecture_design_v0.5.4_mqtt_pipeline_perf_p1.md` | P1 架构，ADR-003 中的行锁 150ms 估算是本特性的输入基线 |
| `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 本特性的修改目标（`ConnectionStatusHandler._update_connection_status()`，约 528-593 行） |
| `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | 确认 `ConnectionStatusHandler` 仅在 `energy_handlers` 链中（92-97 行），不影响 general 链 |
