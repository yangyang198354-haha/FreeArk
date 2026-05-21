# 用户故事清单

```
file_header:
  document_id: US-v0.5.5
  title: MQTT 采集链路性能优化 P2 — ConnectionStatusHandler 行锁路径优化 — 用户故事清单
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.5
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/requirements/v0.5.5_connection_status_lock_opt/requirements_spec.md
    - docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (ConnectionStatusHandler, 452-594)
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，US-P2-01 ~ US-P2-05；含 `[依赖 OQ-X]` 标记，等待用户确认 |
| 1.0.0-CONFIRMED | 2026-05-21 | 用户确认 OQ-1=A、OQ-2=方案 A、OQ-3=可接受。全部用户故事激活；`[依赖 OQ-2 方案]` 标记按方案 A 解读（去除热路径行锁、保留慢路径 `select_for_update()`）。 |

---

## 说明

本清单覆盖 v0.5.5 范围内的 P2 特性（`ConnectionStatusHandler` 行锁路径优化）。

> **【已确认 — 2026-05-21】** OQ-1=A（确认实施 P2），全部用户故事激活并进入本期开发。OQ-2=方案 A（进程内缓存 + 快/慢路径分离），OQ-3=可接受。下列 `[依赖 OQ-2 方案]` / `[依赖 OQ-2 方案，方向 A]` 标注均按方案 A 解读，标注 `[依赖 OQ-2 方案，方向 B]` 的 AC 不适用本期。

部分验收标准（AC）标注了 `[依赖 OQ-2 方案]`，其具体实现细节由架构设计阶段 ADR-001（方案 A）确定。

Given/When/Then 缩写：**G** = Given，**W** = When，**T** = Then。

---

## 特性：ConnectionStatusHandler 行锁路径优化（P2）

### US-P2-01：正常运行期间（设备持续在线），`_update_connection_status()` 不执行不必要的全字段 UPDATE

**作为** 系统运维工程师，  
**我希望** 当设备的连接状态（`online`/`offline`）未发生变化时，`PLCConnectionStatus` 的 UPDATE 操作减少或消除，  
**以便** 降低 energy worker 线程在 `ConnectionStatusHandler` 上的平均耗时，释放 DB 连接资源。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P2-01-1 | G | `_update_connection_status()` 已按选定方案（`[依赖 OQ-2 方案]`）优化；`freeark-mqtt-consumer` 已重启 |
| AC-P2-01-2 | W | 设备状态为 `online`，本次 MQTT 消息同样为 `online`（无状态变化） |
| AC-P2-01-3 | T | 若状态无变化：不执行包含 `connection_status`、`building`、`unit`、`room_number` 全字段的 UPDATE；仅在必要时更新 `last_online_time` |
| AC-P2-01-4 | W | 设备状态为 `offline`，本次 MQTT 消息同样为 `offline`（无状态变化） |
| AC-P2-01-5 | T | 若状态无变化且 `status == 'offline'`：跳过 `save()`，不执行任何 DB 写操作 |
| AC-P2-01-6 | T | Django DEBUG 日志中出现"无状态变化，快路径"或语义等价的日志，可区分快路径与慢路径 |

---

### US-P2-02：设备状态变化时，`PLCStatusChangeHistory` 写入不遗漏

**作为** 运维工程师，  
**我希望** 在 PLC 设备上线或离线时（`online` ↔ `offline` 状态切换），`PLCStatusChangeHistory` 表中必须有对应的变更记录，  
**以便** 追溯设备历史上下线事件，支持运维分析和告警。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P2-02-1 | G | `_update_connection_status()` 已按选定方案优化 |
| AC-P2-02-2 | W | 设备当前状态为 `online`，本次 MQTT 消息携带 `offline` 标识（模拟设备离线） |
| AC-P2-02-3 | T | `PLCStatusChangeHistory` 表中新增一条记录，`specific_part` 正确，`status = 'offline'`，`source = 'mqtt'` |
| AC-P2-02-4 | W | 设备当前状态为 `offline`，本次 MQTT 消息携带 `online` 标识（模拟设备上线） |
| AC-P2-02-5 | T | `PLCStatusChangeHistory` 表中新增一条记录，`specific_part` 正确，`status = 'online'`，`source = 'mqtt'` |
| AC-P2-02-6 | G | 多个 energy worker 并发处理同一设备的消息（状态变化场景） |
| AC-P2-02-7 | T | `PLCStatusChangeHistory` 中对应设备的变更记录数与实际状态变化次数一致（不多不少），不出现漏记 |

---

### US-P2-03：新设备首次出现时，正确创建 `PLCConnectionStatus` 初始行

**作为** 系统开发工程师，  
**我希望** 当一个新 `specific_part`（此前从未出现过的设备）的 energy 消息到达时，`PLCConnectionStatus` 表自动创建该设备的初始状态行，  
**以便** 不因优化改动而破坏新设备自动注册的现有行为。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P2-03-1 | G | `PLCConnectionStatus` 表中不存在 `specific_part = '<新设备ID>'` 的行 |
| AC-P2-03-2 | W | 该新设备的 energy MQTT 消息被某个 energy worker 处理，调用 `_update_connection_status('<新设备ID>', 'online', ...)` |
| AC-P2-03-3 | T | `PLCConnectionStatus` 表中新增一行，`specific_part`、`connection_status`、`building`、`unit`、`room_number` 字段均正确 |
| AC-P2-03-4 | T | `PLCStatusChangeHistory` 表中新增一条对应的创建历史记录（`created=True` 路径） |
| AC-P2-03-5 | G | `[依赖 OQ-2 方案]` 若方案使用内存缓存：新设备在缓存 miss 时能正确走数据库创建路径（不因缓存为空而异常） |

---

### US-P2-04：服务重启后，`ConnectionStatusHandler` 正常恢复工作

**作为** 运维工程师，  
**我希望** `freeark-mqtt-consumer` 重启后，`ConnectionStatusHandler` 的优化实现能自动初始化，不需要手工干预，  
**以便** 日常部署操作（`git pull` + `systemctl restart`）与优化前完全一致。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P2-04-1 | G | `[依赖 OQ-2 方案]` 若方案使用进程内状态缓存，重启后缓存为空 |
| AC-P2-04-2 | W | `sudo systemctl restart freeark-mqtt-consumer` 执行后，energy MQTT 消息到来 |
| AC-P2-04-3 | T | `systemctl status freeark-mqtt-consumer` 显示 `active (running)` |
| AC-P2-04-4 | T | 重启后首批消息（约 568 条，每设备一条）被正确处理，`PLCConnectionStatus` 状态正确，日志无 CRITICAL/ERROR 异常 |
| AC-P2-04-5 | T | `[依赖 OQ-2 方案，方向 A]` 若使用内存缓存：重启后首批消息可能走慢路径（行锁），但不抛异常，系统自动恢复至快路径状态 |

---

### US-P2-05：SQLite 测试环境下，优化后的 `ConnectionStatusHandler` 逻辑可正常测试

**作为** 后端开发工程师，  
**我希望** 优化后的 `_update_connection_status()` 在 SQLite 测试环境下能正常运行并通过单元测试，  
**以便** 在不连生产库的前提下验证业务逻辑的正确性。

**验收标准：**

| # | G / W / T | 描述 |
|---|-----------|------|
| AC-P2-05-1 | G | Django 测试配置使用 SQLite（`DATABASES['default']['ENGINE'] = 'django.db.backends.sqlite3'`） |
| AC-P2-05-2 | W | 运行 `ConnectionStatusHandler` 相关单元测试（包括状态无变化、状态变化、新设备创建三个场景） |
| AC-P2-05-3 | T | 所有测试通过，无因 SQLite 不支持行级锁而导致的异常 |
| AC-P2-05-4 | T | `PLCStatusChangeHistory` 的写入行为（状态变化时有记录，状态无变化时无记录）可通过 SQLite 测试验证 |
| AC-P2-05-5 | G | `[依赖 OQ-2 方案，方向 A]` 若方案去除了 `select_for_update()`：SQLite 测试无需特殊 mock，直接可用 |
| AC-P2-05-6 | G | `[依赖 OQ-2 方案，方向 B]` 若方案保留 `select_for_update()`：需确认 SQLite 环境下 `select_for_update()` 不抛出 `DatabaseError`（Django 的 SQLite 后端在非事务内会报错，需在 `transaction.atomic()` 内使用） |

---

## 附：用户故事与需求编号对照

| 用户故事 | 覆盖需求编号 |
|---------|------------|
| US-P2-01 | REQ-FUNC-002、REQ-FUNC-006、REQ-FUNC-007、NFR4-1、NFR5-1 |
| US-P2-02 | REQ-FUNC-001、REQ-FUNC-003、NFR1-1、NFR1-2 |
| US-P2-03 | REQ-FUNC-004、NFR1-3 |
| US-P2-04 | NFR6-2、NFR6-3 |
| US-P2-05 | NFR3-1、NFR3-2、NFR3-3 |

**未独立成故事的需求**（已在上述 AC 中隐含覆盖）：
- REQ-FUNC-005（不引入新表/migration）：范围排除项，无需独立用户故事
- NFR2-1/NFR2-2（线程安全）：已在 US-P2-02 AC-P2-02-6/7 中覆盖
- NFR4-2（状态变化路径正确性优先于性能）：已在 US-P2-02 中覆盖
- NFR5-2（`PLCStatusChangeHistory` 可审计）：已在 US-P2-02 中覆盖
- NFR6-1/NFR6-4/NFR6-5/NFR6-6（部署约束）：部署规范性需求，无独立用户故事
