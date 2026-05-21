# 架构设计文档 — v0.5.5 ConnectionStatusHandler 行锁路径优化

```
file_header:
  document_id: ARCH-v0.5.5
  title: MQTT 采集链路性能优化 P2 — ConnectionStatusHandler 行锁路径优化 — 架构设计文档
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.5
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/requirements/v0.5.5_connection_status_lock_opt/requirements_spec.md
    - docs/requirements/v0.5.5_connection_status_lock_opt/user_stories.md
    - docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md
    - docs/architecture/architecture_design_v0.5.4_mqtt_pipeline_perf_p1.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (ConnectionStatusHandler, 452-594)
    - FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，含 ADR-001~ADR-003；ADR-001 方案选型待 OQ-1/OQ-2 用户确认 |
| 1.0.0-CONFIRMED | 2026-05-21 | 用户确认 OQ-1=A、OQ-2=方案 A。ADR-001 由「推荐方案 A」转为「确认方案 A」，方案 B 降级为备用记录；ADR-002/ADR-003 生效。架构锁定，进入开发。 |

---

## 1. 架构总览

### 1.1 本次变更的架构定性

本次 v0.5.5 是**对既有系统的增量内部优化**，变更范围严格限定于一个已有文件的一个方法的内部实现。不引入任何新的架构层次、外部服务、数据存储、新 Django 模型或 migration。

| 变更文件 | 变更性质 | 变更规模 |
|---------|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 优化 `ConnectionStatusHandler._update_connection_status()` 内部逻辑，新增模块级进程内缓存（若选方案 A）或仅优化 save() 路径（若选方案 B） | 预计 20-40 行 |

**不引入**：新文件、新 Django 模型、新数据库表/列/索引、migration、新 API endpoint、新 systemd 服务、新依赖包、Redis 或其他外部缓存。

### 1.2 优化目标链路定位

```
energy worker (×3)
  → PLCDataHandler.handle()            — 写 plc_data（不变）
  → ConnectionStatusHandler.handle()   — ← 本次优化目标
      └─ _update_connection_status()
           [当前] transaction.atomic()
                  + select_for_update().get_or_create()  ← 行锁，约 150ms
                  + PLCStatusChangeHistory.create()（仅状态变化时）
                  + plc_status.save()（全字段，即使无变化）
           [优化后，方案选型见 ADR-001]
  → PLCLatestDataHandler.handle()      — 写 plc_latest_data（不变）

general worker (×6)
  → PLCDataHandler → PLCLatestDataHandler  — 跳过 ConnectionStatusHandler（不变）
```

### 1.3 P0+P1-1 后的当前性能基线

基于 v0.5.4 架构文档 ADR-003 的推算，**P1-1 已于 v0.5.4 部署**，当前单条 energy 消息处理时间估算：

| 步骤 | 耗时估算 | 说明 |
|------|---------|------|
| PLCDataHandler | ≤50ms | INSERT plc_data，P0 后磁盘 I/O 已降至内存级别 |
| ConnectionStatusHandler（当前） | **≈150ms** | select_for_update() 行锁，是当前主要耗时源 |
| PLCLatestDataHandler | ≤50ms | bulk_upsert，P1-1 后多数 energy 消息跳过 device_param_history INSERT |
| **合计** | **≈250ms** | 3 worker 吞吐 ≈12 条/秒，到达速率 ≈1.58 条/秒，积压已可能消解 |

P2 优化目标：将 ConnectionStatusHandler 耗时从 150ms 降至 10-50ms（依方案），使合计降至 ≈110-150ms，吞吐提升至 20-30 条/秒。

---

## 2. 架构决策记录（ADR）

### ADR-001：`_update_connection_status()` 优化方案选型

**背景**：当前实现在每次调用时，无论设备连接状态是否变化，均执行 `select_for_update().get_or_create()` 获取行锁，随后执行全字段 `save()`。在正常运行期间（设备持续在线），这是一次"持锁 → 读 → 无变化判断 → 全字段写 → 释放锁"的完整事务，约耗时 150ms，且 3 个 energy worker 并发时存在行锁等待。

**约束边界**（来自 REQ-FUNC-001、NFR1-1/1-2）：
- 状态变化时必须原子性地写入 `PLCStatusChangeHistory`（不可漏记）
- 不可引入 Python 层显式锁（`threading.Lock` 等）
- 不可引入新 Django 模型或 migration
- SQLite 测试环境须可运行（NFR3-1）

---

#### 方案 A — 进程内状态缓存 + 分路径执行（推荐）

**核心思路**：在模块级维护 `_conn_status_cache: dict`（`specific_part` → `'online'/'offline'`），将 `_update_connection_status()` 拆分为两条路径：

- **快路径**（缓存命中且状态一致）：不进入 `transaction.atomic()`，仅执行一条 `UPDATE ... SET last_online_time=NOW() WHERE specific_part=...`（仅 `status='online'` 时），或完全跳过（`status='offline'` 且无变化时）。完全消除行锁。
- **慢路径**（缓存 miss，或缓存状态 ≠ 当前状态）：走完整的 `transaction.atomic() + select_for_update()` 路径，保证 `PLCStatusChangeHistory` 写入的原子性，并更新缓存。

**伪代码结构**：

```python
# 模块级（新增）
# (specific_part: str) -> connection_status: str ('online'/'offline')
# 线程安全：依赖 CPython GIL 保证单次 dict get/set 的原子性
# 缓存 miss 时走 select_for_update 慢路径，保证一致性
_conn_status_cache: dict = {}

def _update_connection_status(self, specific_part, status, building, unit, room_number):
    cached = _conn_status_cache.get(specific_part)

    if cached == status:
        # 快路径：状态无变化，避免行锁
        if status == 'online':
            # 仅更新 last_online_time，用 QuerySet.update() 避免行锁
            PLCConnectionStatus.objects.filter(
                specific_part=specific_part
            ).update(last_online_time=timezone.now())
        # else: status=='offline' 且无变化，完全跳过，无任何 DB 写入
        logger.debug(f"ConnectionStatusHandler: 快路径（无状态变化）- {specific_part}: {status}")
        return

    # 慢路径：缓存 miss 或状态变化，走行锁事务
    try:
        with transaction.atomic():
            plc_status, created = PLCConnectionStatus.objects.select_for_update().get_or_create(
                specific_part=specific_part,
                defaults={
                    'connection_status': status,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number,
                }
            )
            status_changed = created or (plc_status.connection_status != status)

            if status_changed:
                PLCStatusChangeHistory.objects.create(
                    specific_part=specific_part,
                    status=status,
                    building=building,
                    unit=unit,
                    room_number=room_number,
                    source='mqtt',
                )

            if not created:
                plc_status.connection_status = status
                plc_status.building = building
                plc_status.unit = unit
                plc_status.room_number = room_number
            if status == 'online':
                plc_status.last_online_time = timezone.now()
            plc_status.save()

        # 事务成功后更新缓存（放在事务外，确保只在提交成功后更新）
        _conn_status_cache[specific_part] = status
        logger.debug(f"ConnectionStatusHandler: 慢路径（状态变化/初次建立）- {specific_part}: {cached!r} -> {status!r}")

    except Exception as e:
        logger.error(f"ConnectionStatusHandler: 更新连接状态失败 - {specific_part}: {e}", exc_info=True)
```

**一致性分析**（多 worker 并发场景）：

| 场景 | 并发行为 | 一致性保证 |
|------|---------|----------|
| 两个 worker 同时读到 `cached == status`（快路径） | 各自执行一次 `QuerySet.update(last_online_time=...)`，无事务，可能有轻微时间差，结果收敛（后者覆盖前者，值相同） | 安全，无数据错误 |
| 一个 worker 在慢路径，另一个同时读缓存 | 慢路径 worker 持有行锁；另一个 worker 若同时也因缓存 miss 进入慢路径，则在 `select_for_update()` 处等待行锁（与当前行为相同），排队执行 | 安全，历史记录不丢失 |
| 设备状态快速在两种状态间抖动（极端边缘） | 两个 worker 各持一个状态值；最终 `_conn_status_cache[specific_part]` 以最后一次事务提交为准；两次慢路径均会写入 `PLCStatusChangeHistory`，历史不丢失 | 最坏情况多一条历史记录，与当前 select_for_update 串行执行结果一致 |
| 服务重启后缓存清空 | 第一批 568 条消息全部走慢路径；慢路径行为与当前实现完全一致；缓存建立后恢复快路径 | 安全，重启后无数据异常 |

**SQLite 兼容性**：慢路径中的 `select_for_update()` 在 SQLite 上退化（SQLite 无行级锁，但在 `transaction.atomic()` 内不会报错）；快路径的 `QuerySet.update()` 在 SQLite 上正常工作。整体行为在 SQLite 测试环境中可正常运行，无需 mock。

**优点**：
1. 正常运行期间（设备持续在线）完全消除行锁，快路径仅一次 `QuerySet.update()` 或零写操作
2. 状态变化和新设备场景完全保留现有行锁事务语义，历史记录安全
3. 进程重启后自动恢复，无需人工干预
4. 内存占用极小：约 568 设备 × (str key + str value) ≈ 50KB

**缺点**：
1. 引入进程内状态缓存，需分析并文档化一致性边界（已在上方完成）
2. 重启后首批消息走慢路径（行为与优化前完全相同，可接受）
3. 代码比方案 B 稍复杂，需要测试覆盖快路径和慢路径两个分支

**性能估算（优化后）**：

| 场景 | 快路径耗时 | 慢路径耗时 |
|------|----------|----------|
| 状态无变化，online | `QuerySet.update()` ≈ 5-15ms（无事务，无行锁） | — |
| 状态无变化，offline | 零 DB 写入，≈ 0ms | — |
| 状态变化（低频） | — | ≈ 150ms（与现有相同，但发生频率极低） |
| **正常运行加权平均** | **≈ 10ms** | — |

---

#### 方案 B — 保留行锁，仅优化 `save()` 路径（不引入缓存）

**核心思路**：保留 `transaction.atomic() + select_for_update()`，但优化事务内的写路径：
- 若状态无变化：仅在 `status == 'online'` 时用 `save(update_fields=['last_online_time', 'updated_at'])` 最小化 UPDATE；`status == 'offline'` 且无变化时跳过 `save()`
- 若状态有变化：写入 `PLCStatusChangeHistory` 并全字段 `save()`（现有逻辑不变）

**伪代码结构**：

```python
def _update_connection_status(self, specific_part, status, building, unit, room_number):
    try:
        with transaction.atomic():
            plc_status, created = PLCConnectionStatus.objects.select_for_update().get_or_create(
                specific_part=specific_part,
                defaults={
                    'connection_status': status,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number,
                }
            )

            if created:
                # 新设备：写历史，全字段 save 已在 get_or_create 的 INSERT 中完成
                PLCStatusChangeHistory.objects.create(
                    specific_part=specific_part, status=status,
                    building=building, unit=unit, room_number=room_number, source='mqtt',
                )
                if status == 'online':
                    plc_status.last_online_time = timezone.now()
                    plc_status.save(update_fields=['last_online_time'])
                logger.debug(f"ConnectionStatusHandler: 新建状态记录 - {specific_part}: {status}")
            else:
                old_status = plc_status.connection_status
                if old_status != status:
                    # 状态变化：写历史，全字段 save
                    PLCStatusChangeHistory.objects.create(
                        specific_part=specific_part, status=status,
                        building=building, unit=unit, room_number=room_number, source='mqtt',
                    )
                    plc_status.connection_status = status
                    plc_status.building = building
                    plc_status.unit = unit
                    plc_status.room_number = room_number
                    if status == 'online':
                        plc_status.last_online_time = timezone.now()
                    plc_status.save()
                    logger.debug(f"ConnectionStatusHandler: 状态变化 - {specific_part}: {old_status} -> {status}")
                else:
                    # 状态无变化：最小化 save
                    if status == 'online':
                        plc_status.last_online_time = timezone.now()
                        plc_status.save(update_fields=['last_online_time'])
                    # else: offline 且无变化，跳过 save()
                    logger.debug(f"ConnectionStatusHandler: 无变化，最小化写入 - {specific_part}: {status}")
    except Exception as e:
        logger.error(f"ConnectionStatusHandler: 更新连接状态失败 - {specific_part}: {e}", exc_info=True)
```

**优点**：
1. 不引入内存缓存，无缓存一致性问题
2. 代码结构比方案 A 更保守，改动范围更小
3. 消除了不必要的全字段 `save()`，减少了 UPDATE 的字段数

**缺点**：
1. 行锁竞争根因**未消除**：3 个 energy worker 仍然并发执行 `select_for_update()`，行锁等待时间未降低
2. 性能提升有限：持锁时间略有缩短（省去全字段 UPDATE 中的多余字段），但行锁等待（约 100-130ms）仍是主要耗时
3. `online` 场景下仍有一次 `save(update_fields=['last_online_time'])`，虽小于全字段 UPDATE，但行锁期间的事务开销仍在

**性能估算（优化后）**：

| 场景 | 耗时估算 | 说明 |
|------|---------|------|
| 状态无变化，online | ≈ 120-140ms | 行锁等待 + 最小化 UPDATE（比当前全字段 UPDATE 略快，但行锁未消除） |
| 状态无变化，offline | ≈ 100-120ms | 行锁等待 + 零写入（略快于当前） |
| 状态变化 | ≈ 150ms | 与当前相同 |
| **正常运行加权平均** | **≈ 120ms** | 相比当前 150ms，提升约 20% |

---

#### 方案对比汇总

| 维度 | 方案 A（进程内缓存 + 分路径） | 方案 B（保留行锁 + 优化 save） |
|------|--------------------------|---------------------------|
| 正常运行耗时 | **≈10ms**（行锁完全消除） | ≈120ms（行锁仍在） |
| 性能提升幅度 | **约 93%** | 约 20% |
| 状态变化场景正确性 | 等同现有（慢路径保留行锁事务） | 等同现有 |
| 新设备创建正确性 | 等同现有（缓存 miss 走慢路径） | 等同现有 |
| 历史记录安全性 | 等同现有（分析见 ADR-001 一致性分析） | 等同现有 |
| 代码复杂度 | 中（分两路径，需缓存初始化逻辑） | 低（保守修改，仅优化 if/else 分支） |
| 引入内存缓存 | 是（约 50KB，进程级） | 否 |
| SQLite 兼容性 | 完全兼容（快路径无 select_for_update） | 完全兼容（行为与现有相同） |
| 重启后首批行为 | 首批走慢路径（与优化前相同），后续恢复快路径 | 与优化前完全相同 |
| 风险评估 | 低（缓存一致性已分析，边界清晰） | 极低（最保守修改） |

**ADR-001 决策：方案 A（已确认 — 2026-05-21 用户拍板）**

> 用户在 OQ-1 选择「确认实施 P2」、OQ-2 选择「方向 A — 进程内缓存 + 快/慢路径分离」。架构师推荐与用户决策一致，方案 A 为本期最终实施方案；方案 B 作为备用设计记录保留（见模块设计 §1.4），不实施。

**理由**：
1. 方案 A 的性能提升幅度（93%）远优于方案 B（20%）；当前 ConnectionStatusHandler 是 energy worker 的主要耗时源（约 60%），方案 A 将其从主要瓶颈降至可忽略量级
2. 方案 A 的缓存一致性边界已经明确分析，主要风险（并发场景）通过"慢路径仍保留行锁"和"缓存在事务提交后更新"两个设计要素规避
3. 方案 B 虽然保守，但对当前最主要的性能问题（行锁竞争）未能实质解决，实施代价（测试、代码审查、生产部署风险）与方案 A 相近，但收益远低
4. 内存缓存约 50KB，对树莓派内存完全可忽略
5. 进程重启后的"首批慢路径"行为与 P1-1 的 `_energy_hist_last_hour` 缓存重建完全类似，在该项目中已有先例，属于已知可接受行为

**最终方案选型已由用户确认（2026-05-21）：OQ-1=A、OQ-2=方案 A。** 方案 A 进入开发，方案 B 归档为备用。

---

### ADR-002：进程内状态缓存的键结构与命名（方案 A 专属）

**背景**（仅在 ADR-001 选定方案 A 时相关）：确定 `_conn_status_cache` 的命名、键结构和线程安全模型。

**决策**：

```python
# [P2 新增] ConnectionStatus 进程内状态缓存（方案 A）
# key: specific_part (str) → last_known_status: str ('online'/'offline')
# 线程安全：依赖 CPython GIL 保证单次 dict get/set 的原子性；
#           极端并发边界见 ADR-001 一致性分析。
# 内存：约 568 设备 × ~60 bytes = ~34KB，忽略不计。
# 服务重启后清空，自动重建（首批消息走慢路径）。
_conn_status_cache: dict = {}
```

**命名说明**：
- 区别于 `_energy_hist_last_hour` / `_general_hist_last_hour`（时序历史去重缓存），本缓存是"设备当前已知状态"（非时间窗口去重），故命名为 `_conn_status_cache` 而非 `_conn_status_last_hour`
- 键仅为 `specific_part`（字符串），不含 `param_name`（`ConnectionStatusHandler` 处理的是设备级状态，非参数级）

**与既有缓存的对比**：

| 缓存 | 键结构 | 值 | 用途 | 引入版本 |
|------|--------|---|------|---------|
| `_general_hist_last_hour` | `(specific_part, param_name)` → `'YYYY-MM-DD-HH'` | 小时时间戳字符串 | 历史写入去重 | 原有 |
| `_energy_hist_last_hour` | `(specific_part, param_name)` → `'YYYY-MM-DD-HH'` | 小时时间戳字符串 | 历史写入去重（v0.5.4） | v0.5.4 P1-1 |
| `_conn_status_cache` | `specific_part` → `'online'/'offline'` | 状态字符串 | 行锁绕路（v0.5.5） | v0.5.5 P2（本次） |

---

### ADR-003：`last_online_time` 的更新策略

**背景**：`PLCConnectionStatus.last_online_time` 字段每次 `status == 'online'` 的消息都应更新（记录最后在线时间）。方案 A 的快路径不走事务，需明确如何处理此字段。

**可选做法**：

| 做法 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A1（推荐）| 快路径走 `QuerySet.filter(...).update(last_online_time=timezone.now())`，无事务，无行锁 | 轻量，无锁，MySQL 原子 UPDATE | 需一次 DB 往返（约 5-15ms） |
| A2 | 快路径完全跳过 `last_online_time` 更新（只在慢路径时更新） | 零 DB 写入 | `last_online_time` 只在状态变化时更新，正常在线期间不推进，可能影响"最后在线时间"语义 |
| A3 | 快路径按时间阈值控制 `last_online_time` 更新（如最多每 10 分钟更新一次） | 大幅减少 DB 写入次数 | 增加额外缓存状态（上次更新时间），复杂度增加 |

**ADR-003 决策：做法 A1（推荐）**

**理由**：
- `last_online_time` 是运维关注的"设备最后在线时间"指标，若不在正常在线期间更新，该字段的时效性将丧失（仅在状态切换时推进）
- 做法 A1 的 `QuerySet.update()` 不持行锁，单次约 5-15ms，远低于当前 150ms
- 做法 A2 的语义损失（`last_online_time` 不跟踪正常在线时刻）对于运维场景不可接受
- 做法 A3 复杂度过高，当前规模不值得引入

> **注意**：`status == 'offline'` 的快路径（状态无变化）完全跳过任何 DB 写入（`offline` 时不更新 `last_online_time`），这是现有逻辑的保留。

---

## 3. 受影响的组件交互（方案 A 生效后）

### 3.1 `ConnectionStatusHandler._update_connection_status()` 执行流程（方案 A）

```
调用 _update_connection_status(specific_part, status, ...)
  │
  ├─ 读 _conn_status_cache.get(specific_part) → cached
  │
  ├─[cached == status]→ 快路径
  │     ├─[status == 'online']→ QuerySet.filter(...).update(last_online_time=now())
  │     │    约 5-15ms，无行锁
  │     └─[status == 'offline']→ 完全跳过（零 DB 写入）
  │          ≈ 0ms
  │     → return（不进入 transaction.atomic()）
  │
  └─[cached != status 或 cache miss]→ 慢路径
        transaction.atomic() 开始
          select_for_update().get_or_create(specific_part=...)
          ├─[created=True 或 connection_status 变化]
          │    PLCStatusChangeHistory.create(...)
          │    plc_status 字段更新 + plc_status.save()
          └─[else] → 理论上不应到此（快路径已处理无变化情形）
                     仅在并发竞争（两 worker 同时 cache miss）时出现：
                     select_for_update 后发现对方已先写入，状态实则未变
                     → 走最小化 save(update_fields=['last_online_time']) 或跳过
        transaction.atomic() 结束
        _conn_status_cache[specific_part] = status  ← 事务提交后更新缓存
```

### 3.2 并发竞争最坏情形分析

**情形**：2 个 energy worker 同时处理同一设备的消息，且均 cache miss（新设备或重启后）。

```
Worker-1: cache.get(X) → None（miss）→ 进入慢路径
Worker-2: cache.get(X) → None（miss）→ 进入慢路径

Worker-1: select_for_update() → 获得行锁
Worker-2: select_for_update() → 等待行锁

Worker-1: 判断 created=True（新设备）或 old_status != status（状态变化）
         → PLCStatusChangeHistory.create()
         → plc_status.save()
         → 事务提交 → _conn_status_cache[X] = status
         → 释放行锁

Worker-2: 获得行锁（此时 created=False，old_status == status）
         → 判断 old_status == status（无变化）
         → 不写 PLCStatusChangeHistory
         → save(update_fields=['last_online_time']) 或跳过
         → 事务提交 → _conn_status_cache[X] = status（重复写，无害）
```

**结论**：最坏情况下，`PLCStatusChangeHistory` 不会多写（Worker-2 发现状态已同步，不再写历史），也不会漏写（Worker-1 已写入）。一致性保证完整。

---

## 4. 非功能性约束（架构层面）

| 约束 | 实现方案 |
|------|---------|
| 物理机，禁止 Docker | 无新增服务，无容器化 |
| 部署方式 | `plink + git pull`，变更后重启 `freeark-mqtt-consumer`；无 migration，无前端发版 |
| 线程安全 | 快路径：GIL 保证 dict get 原子性；`QuerySet.update()` 是线程安全的 DB 操作；慢路径：与现有 select_for_update 行为完全一致 |
| 内存占用 | `_conn_status_cache`：568 key × ~60 bytes ≈ 34KB，可忽略 |
| SQLite 测试兼容 | 快路径无 select_for_update，在 SQLite 下完全正常；慢路径 select_for_update 在 SQLite 的 transaction.atomic() 内不报错 |
| 回滚方案 | `git revert` + `sudo systemctl restart freeark-mqtt-consumer`；回滚后恢复原始 select_for_update 实现，`_conn_status_cache` 随进程消亡，无数据影响 |
| 状态变化历史不丢失 | 慢路径（行锁事务）保留完整的 PLCStatusChangeHistory.create() 逻辑，与现有实现语义等同 |

---

## 5. 数据流对比

### 5.1 `_update_connection_status()` 耗时对比（方案 A）

| 场景 | 频率估算 | 优化前 | 优化后（方案 A） | 降幅 |
|------|---------|--------|----------------|------|
| 设备持续在线（无变化），online | 约 95% 以上的调用 | ≈150ms（行锁） | ≈10ms（QuerySet.update） | **-93%** |
| 设备持续在线（无变化），offline | 极少（断网场景） | ≈150ms（行锁） | ≈0ms（跳过） | **-100%** |
| 状态变化（online↔offline） | 极低频（上下线事件） | ≈150ms（行锁） | ≈150ms（慢路径，不变） | 0%（正确性优先） |
| 重启后首批消息 | 仅重启时 | ≈150ms | ≈150ms（慢路径，缓存建立后恢复） | 0%（可接受） |
| **加权平均（正常运行）** | — | **≈150ms** | **≈10ms** | **≈-93%** |

### 5.2 energy worker 端到端处理时间对比

| 阶段 | P1-1 后（当前基线） | P2 后（方案 A） |
|------|-------------------|----------------|
| PLCDataHandler | ≤50ms | ≤50ms（不变） |
| ConnectionStatusHandler | ≈150ms | **≈10ms**（快路径） |
| PLCLatestDataHandler | ≤50ms | ≤50ms（不变） |
| **单条合计** | **≈250ms** | **≈110ms** |
| **3 worker 理论吞吐** | ≈12 条/秒 | **≈27 条/秒** |
| 到达速率 | 1.58 条/秒 | 1.58 条/秒 |
| 吞吐/到达率比 | 7.6× | **17×** |

---

## 6. 与既有架构的关系

本次变更完全在 `mqtt_handlers.py` 的 `ConnectionStatusHandler._update_connection_status()` 方法内部，不改变任何：

- API endpoint（无新增、无变更）
- 数据库 Schema（无新增表/列/索引，无 migration）
- systemd 服务配置（无新增服务，仅需重启已有 `freeark-mqtt-consumer`）
- 前端代码（无任何变更）
- MQTT 消息格式（无变更）
- 其他 handler（`PLCDataHandler`、`PLCLatestDataHandler`）
- `PLCConnectionStatus`、`PLCStatusChangeHistory` 模型定义

本次是在现有"进程内模块级缓存"模式（`_energy_hist_last_hour`、`_general_hist_last_hour`）的基础上，将相同的设计模式应用于连接状态快路径判断，架构上无引入新模式。
