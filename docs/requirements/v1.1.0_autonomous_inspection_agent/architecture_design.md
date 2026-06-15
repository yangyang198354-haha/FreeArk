---
file_header:
  document_id: ARCH-v1.1.0-AIA
  title: 自治巡检 Agent（方案 B）— 架构设计文档
  author_agent: sub_agent_system_architect
  project: FreeArk v1.1.0
  version: 0.1.0-DRAFT
  created_at: 2026-06-15
  status: DRAFT
  references:
    - docs/requirements/v1.1.0_autonomous_inspection_agent/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py (L63-402)
    - FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py (L197-255)
    - FreeArkWeb/backend/freearkweb/api/models.py (L680-816)
    - agents/langgraph-poc/PHASE_G_DELEGATION_DESIGN.md §2/§4
---

> **注意**：本架构文档依赖的需求规格说明书（requirements_spec.md）当前状态为 DRAFT（非 APPROVED）。
> 架构设计基于已定稿的需求内容产出，开发实施前须等待需求规格状态升级为 APPROVED。

---

## 1. 架构概览

### 1.1 设计原则

本版本（方案 B）是方案 A 的**独立扩展子系统**，严格遵循以下三条设计原则：

1. **不修改现有 chat 链路**：`api/langgraph_chat/` 下的所有文件（`orchestrator.py`、`fa_tools.py`、`adapter.py` 等）均为只读，方案 B 通过进程内 import 复用，不 fork、不修改。（约束来源：OOS-01、REQ-CON-004）
2. **最小化新依赖**：不引入 Redis、外部消息队列、PostgreSQL、Docker 等新中间件；完全复用现有 Django ORM + MySQL + systemd 生态。（约束来源：OOS-06、REQ-CON-001）
3. **写操作强隔离**：无论 LLM 决策结果如何，写操作必须且只能经过 `WriteAuthPolicy.check()` 单一入口，不存在旁路。（约束来源：REQ-FUNC-005、REQ-NFUNC-003）

### 1.2 架构风格

**模块化单体（Modular Monolith）扩展**：在现有 Django 单体应用内新增 `inspection_agent/` 包，作为独立的 Django Management Command 运行，以独立进程（systemd service）形式与现有服务共存。

选型依据：REQ-CON-001（禁 Docker，物理机 systemd）、REQ-NFUNC-001（树莓派单核）、OOS-06（禁新中间件）。

### 1.3 系统边界图（ASCII）

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     树莓派 Pi 5  (192.168.31.51)                             │
│                                                                              │
│  ┌─────────────────────────────────┐    ┌────────────────────────────────┐  │
│  │   freeark-backend               │    │  freeark-inspection-agent      │  │
│  │   (Django WSGI / Gunicorn)      │    │  [方案 B — 本版本新增]         │  │
│  │                                 │    │                                │  │
│  │  ┌─────────────────────────┐    │    │  ┌──────────────────────────┐ │  │
│  │  │ api/langgraph_chat/     │    │    │  │ inspection_agent/        │ │  │
│  │  │  orchestrator.py        │◄───┼────┼──┤  agent.py (import)      │ │  │
│  │  │  fa_tools.py            │    │    │  │  auth.py                 │ │  │
│  │  │  adapter.py             │    │    │  │  event_poller.py         │ │  │
│  │  │  [方案 A，只读，不修改]  │    │    │  │  work_order.py           │ │  │
│  │  └─────────────────────────┘    │    │  │  audit.py                │ │  │
│  │                                 │    │  └──────────────────────────┘ │  │
│  │  HTTP/WS ◄── 用户 chat 请求     │    │                                │  │
│  └─────────────────────────────────┘    │  Django Management Command     │  │
│                                         │  run_inspection_agent.py       │  │
│  ┌──────────────────────┐               └───────────────┬────────────────┘  │
│  │ freeark-fault-       │                               │                   │
│  │ consumer             │                               │ DB 轮询            │
│  │ (写入 fault_event)   │──────────┐                    │ (每 30s)          │
│  └──────────────────────┘         │                    │                   │
│                                   ▼                    ▼                   │
│  ┌──────────────────────┐   ┌─────────────────────────────────────────┐    │
│  │ freeark-condensation │   │         MySQL  192.168.31.98:3306        │    │
│  │ -consumer            │──►│  fault_event (含 inspection_status)      │    │
│  │ (写入 condensation_  │   │  condensation_warning_event (同上)       │    │
│  │  warning_event)      │   │  inspection_work_order  [新增]           │    │
│  └──────────────────────┘   └─────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ WS Gateway RPC (loopback :18789)
                                       ▼
                          ┌────────────────────────────┐
                          │  OpenClaw / DeepSeek LLM   │
                          │  127.0.0.1:18789            │
                          │  (Bearer token, WS RPC)     │
                          └────────────────────────────┘
```

**关键边界说明：**
- `freeark-inspection-agent` 对 `api/langgraph_chat/` 的使用是**只读 import**（读取类和工具定义），不调用 `freeark-backend` 的 HTTP 接口，不共享进程或线程池。
- 两个 consumer 服务（`freeark-fault-consumer`、`freeark-condensation-consumer`）保持完全不变；方案 B 仅消费它们写入 DB 的记录，不干预其运行逻辑（OOS-03 约束）。
- 方案 B 与方案 A 的 chat 链路在进程层面完全隔离，chat HTTP 接口的性能不受巡检 Agent 阻塞（REQ-NFUNC-001 支撑）。

---

## 2. 开放决策裁定

### 2.1 OD-01：自治写授权策略（AUTO_WRITE_POLICY）

**决策问题**：在无人值守的自治场景下，系统对 `set_device_params` / `trigger_refresh` 等设备写操作采用哪种授权模式？

**背景**（来源：REQ-FUNC-005、REQ-NFUNC-003）：
- 方案 B 的 inspection-expert 具备 `delegate_write` 工具，其 LLM 推理结果可能生成写操作提案。
- 与方案 A 的 chat 链路不同，方案 B 是无人值守的，不存在用户实时确认（chat 链路的 `_gate` interrupt 确认门不在此场景）。
- 树莓派无冗余：若写操作错误调整了设备参数（如将制冷切为制热），无法自动回滚，物理影响是真实的。

**候选方案分析：**

| 维度 | 策略 A（白名单自动执行） | 策略 B（全转工单，无自动写） |
|------|------------------------|--------------------------|
| 自动化程度 | 高：白名单内无需人工 | 低：全部需人工跟进 |
| 安全风险 | 中：LLM 在白名单内仍可能误判 | 极低：零自动写，无误操作风险 |
| 白名单设计难度 | 高：需精确定义各参数的安全区间 | 无：无白名单 |
| 初期验证价值 | 低：无法纯粹验证 LLM 决策质量 | 高：所有提案落库，可审查 LLM 决策是否准确 |
| 适用阶段 | 系统稳定、LLM 决策经过充分验证后 | 系统初期、信心建立阶段 |
| 审计日志 | 必须：`WRITE_EXECUTED` 事件 | 必须：`WRITE_BLOCKED_POLICY_B` 事件 |

**架构师推荐：策略 B（PolicyB）作为初期部署策略**

理由：
1. **LLM 决策不确定性**：DeepSeek 模型在三恒系统参数调整上尚无足够验证基线，无人值守场景下的误判无法被及时发现和回滚。
2. **单点无冗余**：树莓派 Pi 5 是生产唯一节点，设备参数错误写入无自动回滚机制，物理影响（温湿度失控）是真实的。
3. **建立信任基线**：策略 B 积累的工单和审计日志可作为评估 LLM 决策准确率的数据基础，待准确率满足阈值后再升级至策略 A，有依据可循。
4. **代码接缝已就绪**：`WriteAuthPolicy` 类设计支持环境变量切换（`AUTO_WRITE_POLICY=A/B`），从 B 升级到 A 只需修改 `.env`，无需改代码。

**给用户的拍板建议**：
> **建议初期选择策略 B（`AUTO_WRITE_POLICY=B`）**。
>
> 系统上线后，通过审计日志（`WRITE_BLOCKED_POLICY_B` + `WORKORDER_CREATED` 条目）观察 LLM 推荐的写操作提案是否合理，运维人员跟进工单后人工确认处置是否与 LLM 建议一致。
> 当积累足够数据（建议：连续 30 天，LLM 提案与人工决策吻合率 >= 90%）后，可通过更新 `.env` 中的 `AUTO_WRITE_POLICY=A` 和 `INSPECTION_WRITE_WHITELIST` 升级至策略 A，无需部署新代码。

**代码接缝设计**（`inspection_agent/auth.py`）：

```
WriteAuthPolicy
  ├── check(tool_name, args, event) → AuthResult
  │     读取 os.environ["AUTO_WRITE_POLICY"]（默认 "B"）
  │     if "A" → PolicyA(whitelist).check(...)
  │     else   → PolicyB().check(...)
  │
  ├── PolicyA（白名单，备选）
  │     从 INSPECTION_WRITE_WHITELIST 环境变量（JSON）读取白名单
  │     校验参数变化量 → 通过：AuthResult(allowed=True)
  │                    → 越界：AuthResult(allowed=False, reason="OUT_OF_WHITELIST")
  │
  └── PolicyB（推荐，初期）
        始终返回 AuthResult(allowed=False, reason="POLICY_B_NO_AUTO_WRITE")
```

安全保证：`execute_write()` 在 `inspection_agent/` 包内**只能**被 `WriteAuthPolicy.check()` 返回 `allowed=True` 后调用，不存在其他调用路径。这是系统架构层面的唯一写入口。

---

### 2.2 OD-02：事件接入方式

**决策问题**：`freeark-inspection-agent` 如何感知 `fault_event` / `condensation_warning_event` 中新出现的待处置事件？

**背景**（来源：REQ-FUNC-002、S-10、OOS-03、OOS-06）：
- consumer 服务（`freeark-fault-consumer`、`freeark-condensation-consumer`）不可修改（OOS-03）。
- 禁止引入 Redis 等新中间件（OOS-06）。
- 方案 B 是独立进程，与 consumer 不共享内存。

**候选方案分析：**

| 维度 | 方式 1：DB 轮询 | 方式 2：Django post_save 信号 |
|------|--------------|---------------------------|
| 实现复杂度 | 低：标准 ORM 查询 | 高：跨进程信号无法直接传递 |
| 是否需改动 consumer | 否 | 是（违反 OOS-03） |
| 实时性 | 30s 延迟 | 准实时 |
| 跨进程兼容 | 是：DB 是天然跨进程共享存储 | 否：Django signal 是进程内机制，跨进程需 IPC（违反 OOS-06） |
| 轮询对 DB 压力 | 极低：每 30s 一次简单 SELECT | N/A |
| 预警响应时效需求 | 可接受：预警发出 30s 内响应对楼宇三恒系统足够 | 不适用 |
| 依赖新中间件 | 否 | 是（IPC 机制或 Redis pub/sub，违反 OOS-06） |

**架构师决策：DB 轮询（方式 1）**

理由：
1. consumer 禁止修改（OOS-03）直接排除了信号驱动的 consumer 侧改造路径。
2. 跨进程信号传递需要 Redis pub/sub 或 Unix socket，均属新中间件，违反 OOS-06。
3. 楼宇三恒预警的响应时效不是毫秒级的，30s 内响应完全满足业务需求（REQ-NFUNC-001 不要求实时，仅要求"不阻塞其他服务"）。
4. DB 轮询实现最简单，失败模式可预测（DB 连接失败可重试），无额外运维负担。

**落地设计**：
- 新增 `inspection_status` 字段（`PENDING / IN_PROGRESS / DONE / SKIPPED`）到 `FaultEvent` 和 `CondensationWarningEvent`（通过 migration 0033）。
- 轮询查询：`SELECT WHERE is_active=True AND inspection_status='PENDING' ORDER BY first_seen_at ASC LIMIT N`
- 取到事件后原子 UPDATE `inspection_status='IN_PROGRESS'`，防止未来并发场景的重复取用。
- 轮询间隔：30s（通过 `INSPECTION_POLL_INTERVAL` 环境变量配置，默认 30）。
- 批量大小：每轮最多取 `INSPECTION_BATCH_SIZE` 条（默认 5），防止积压时爆炸式并发（REQ-NFUNC-001）。

---

### 2.3 OD-03：处置状态持久化方案

**决策问题**：如何持久化每条预警事件的决策处置进度，确保重启后零漏单零重单？

**背景**（来源：REQ-FUNC-007、REQ-NFUNC-002、S-08）：
- 现有生产 chat 链路使用 `MemorySaver()`（进程内），重启即丢失——这对 chat 场景可接受，但对自治巡检场景不可接受（AC-007-03 明确要求）。
- `MemorySaver` 不满足 REQ-FUNC-007 的持久化要求。

**候选方案分析：**

| 维度 | 方案 X：LangGraph DB Checkpointer | 方案 Y：自建状态字段（推荐） |
|------|----------------------------------|--------------------------|
| 实现复杂度 | 高：需适配 LangGraph checkpointer 接口 | 低：标准 Django ORM CharField |
| 新依赖 | 是：需 PostgreSQL 或 SQLite checkpointer 包，与现有 MySQL 兼容性未经验证 | 否：完全复用现有 Django ORM + MySQL |
| 与 LangGraph 图集成 | 深度集成，支持断点续传图状态 | 解耦，仅记录"此事件是否处理完" |
| 方案 B 场景适配性 | 偏重：方案 B 的有界 ReAct 循环无需断点续传（8 步上限内完成或兜底） | 恰当：只需记录事件级粗粒度状态（PENDING/IN_PROGRESS/DONE/SKIPPED） |
| 重启重建逻辑 | 自动（由 checkpointer 恢复图状态） | 手动：启动时扫描 IN_PROGRESS → 重置为 PENDING |
| 测试友好性 | 低：需安装额外包 | 高：SQLite 测试环境完全兼容 |

**架构师决策：方案 Y（自建状态字段）**

理由：
1. 方案 B 的有界 ReAct 循环（MAX_EXPERT_STEPS=8）设计为幂等的：同一事件重新处理的结果应与上次一致（LLM 基于相同事件上下文推理）。不需要断点续传中间图状态，只需知道"该事件是否已处理完"。
2. LangGraph DB Checkpointer 与 MySQL 9.4 的兼容性未经验证（官方文档以 PostgreSQL/SQLite 为主），引入未验证的依赖是不必要的风险（R-05）。
3. 方案 Y 的重启重建逻辑简单且可预测：启动时原子 UPDATE IN_PROGRESS → PENDING，下一轮轮询重新取用，无状态泄漏。
4. 方案 Y 完全在现有 Django ORM + MySQL 生态内，SQLite 测试环境直接支持，无新依赖。

**落地设计**：

在 `FaultEvent` 和 `CondensationWarningEvent` 两张表各新增两个字段（migration 0033）：

```
inspection_status     CharField  max_length=16
                      choices: PENDING / IN_PROGRESS / DONE / SKIPPED
                      default='PENDING'
                      db_index=True

inspection_started_at  DateTimeField
                       null=True, blank=True
```

重启重建：服务启动时执行原子 UPDATE，将所有 `inspection_status='IN_PROGRESS'` 的记录重置为 `'PENDING'`，确保中途中断的事件被重新取用（不丢单），同时 `inspection_status='DONE'` 的记录不受影响（不重单）。

---

## 3. 新服务 freeark-inspection-agent 设计

### 3.1 目录结构

方案 B 的新代码全部落在生产侧 Django 项目内（`FreeArkWeb/backend/freearkweb/`），不碰 `agents/langgraph-poc/`（REQ-CON-004）：

```
FreeArkWeb/backend/freearkweb/
├── api/
│   ├── management/
│   │   └── commands/
│   │       └── run_inspection_agent.py   # Django Management Command 入口
│   └── models.py                         # 新增 WorkOrder 模型（末尾追加）
│                                         # 新增 FaultEvent / CW inspection_status 字段
│                                         # (同一 migration 链维护)
│
├── inspection_agent/                      # 新包，与 api/ 同级
│   ├── __init__.py
│   ├── agent.py                           # InspectionAgent 类：决策循环主逻辑
│   ├── auth.py                            # WriteAuthPolicy / PolicyA / PolicyB
│   ├── event_poller.py                    # EventPoller：DB 轮询器
│   ├── work_order.py                      # 工单创建 / 防重复逻辑
│   └── audit.py                           # 结构化审计日志工具函数
│
└── api/
    └── migrations/
        └── 0033_add_inspection_status_and_workorder.py  # 新增 migration
```

**说明：**
- `inspection_agent/` 包只可 **import** `api.langgraph_chat.*`，不可修改其文件。
- `WorkOrder` 模型放在 `api/models.py` 末尾，以复用同一个 migration 链（不新建独立 app），避免跨 app migration 依赖复杂性。

### 3.2 systemd Unit 文件

文件路径：`/etc/systemd/system/freeark-inspection-agent.service`

部署路径（git 管理）：`FreeArkWeb/deploy/freeark-inspection-agent.service`

```ini
[Unit]
Description=FreeArk Autonomous Inspection Agent
After=network.target freeark-backend.service freeark-fault-consumer.service freeark-condensation-consumer.service
Wants=freeark-fault-consumer.service freeark-condensation-consumer.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/FreeArkWeb/backend/freearkweb
EnvironmentFile=/home/pi/FreeArkWeb/backend/freearkweb/.env
ExecStart=/home/pi/.venv/bin/python manage.py run_inspection_agent
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-inspection-agent

[Install]
WantedBy=multi-user.target
```

关键设计点：
- `After` 和 `Wants` 确保两个 consumer 服务先于巡检 Agent 启动，保证事件源 DB 表可用（REQ-FUNC-002 依赖）。
- `Restart=on-failure` + `RestartSec=30` 满足 AC-001-02（自动重启，REQ-FUNC-001）。
- `StandardOutput=journal` 确保 Python logging 输出可被 `journalctl -u freeark-inspection-agent` 查询（REQ-NFUNC-004）。
- `EnvironmentFile` 注入 `.env`，不硬编码凭证（REQ-CON-005）。

### 3.3 Management Command 结构设计

文件：`api/management/commands/run_inspection_agent.py`

结构（伪代码级，非实现）：

```
class Command(BaseCommand):
    help = "运行自治巡检 Agent（freeark-inspection-agent）"

    handle(options):
        1. 配置 logging（SysLogHandler 或 StreamHandler → journald）
        2. 写 INFO 日志："freeark-inspection-agent 启动"
        3. 启动重建：原子重置 FaultEvent + CW 中 inspection_status='IN_PROGRESS' → 'PENDING'
        4. 初始化 InspectionAgent（进程内单例）
        5. 调用 agent.run_forever()

InspectionAgent.run_forever():
    无限循环:
        try:
            events = event_poller.poll()     # 取 PENDING 事件列表（最多 BATCH_SIZE 条）
            for event in events:
                process_event(event)         # 串行处理，一条完成后再处理下一条
            sleep(INSPECTION_POLL_INTERVAL)  # 默认 30s
        except KeyboardInterrupt:
            break                            # 收到 SIGTERM/SIGINT 优雅退出
        except Exception as e:
            log ERROR("未预期异常：{e}，继续下一轮")
            sleep(INSPECTION_POLL_INTERVAL)  # 不崩溃，继续轮询
```

---

## 4. 事件接入设计（OD-02 落地）

### 4.1 新增字段规格

需通过 migration 0033 向两张表各添加以下字段（不修改现有字段）：

**FaultEvent 新增字段：**

```
inspection_status
  type: CharField, max_length=16
  choices: [('PENDING','待处置'), ('IN_PROGRESS','处理中'), ('DONE','已处置'), ('SKIPPED','已跳过')]
  default: 'PENDING'
  db_index: True
  verbose_name: '巡检处置状态'

inspection_started_at
  type: DateTimeField
  null: True, blank: True
  verbose_name: '巡检开始时间'
```

**CondensationWarningEvent 新增字段：** 同上，字段名和规格完全相同。

**对现有约束的影响分析：**
- `FaultEvent` 现有唯一约束 `(specific_part, device_sn, fault_code, first_seen_at)` 不受影响（新增字段独立）。
- 现有索引 `idx_fault_sp_active(specific_part, is_active)` 和 `idx_fault_time_active(first_seen_at, is_active)` 不受影响。
- `CondensationWarningEvent` 现有约束同理，无冲突。

### 4.2 EventPoller 轮询查询设计

模块：`inspection_agent/event_poller.py`，核心方法 `poll() → List[Union[FaultEvent, CondensationWarningEvent]]`

轮询逻辑（伪代码级，非实现）：

```
EventPoller.poll():
    batch_size = int(env.get("INSPECTION_BATCH_SIZE", 5))

    # 查询 FaultEvent
    fault_events = FaultEvent.objects.filter(
        is_active=True,
        inspection_status='PENDING'
    ).order_by('first_seen_at')[:batch_size]

    # 查询 CondensationWarningEvent
    cw_events = CondensationWarningEvent.objects.filter(
        is_active=True,
        inspection_status='PENDING'
    ).order_by('first_seen_at')[:batch_size]

    # 合并、按 first_seen_at 排序，取前 batch_size 条
    all_events = sorted(
        list(fault_events) + list(cw_events),
        key=lambda e: e.first_seen_at
    )[:batch_size]

    # 原子标记：避免重复取用（当前串行设计，预留并发安全）
    for event in all_events:
        event.__class__.objects.filter(
            pk=event.pk,
            inspection_status='PENDING'  # 乐观锁条件
        ).update(
            inspection_status='IN_PROGRESS',
            inspection_started_at=datetime.utcnow()
        )

    return all_events
```

### 4.3 去重与状态一致性

| 场景 | 处理方式 |
|------|---------|
| 事件已恢复（`is_active=False`）但尚在 IN_PROGRESS | `process_event` 开头检查 `is_active`，若为 False 则标记 SKIPPED |
| 事件已处置（`inspection_status='DONE'`） | 轮询条件 `inspection_status='PENDING'` 自动过滤 |
| 服务重启，事件处于 IN_PROGRESS | 启动重建：原子 UPDATE IN_PROGRESS → PENDING，下轮轮询重取 |
| 工单已存在（同事件，OPEN 状态） | `work_order.py` 先查后建；DB 层 `uniq_active_workorder_per_event` 约束兜底 |

---

## 5. 决策循环设计

### 5.1 InspectionAgent.process_event(event) 流程

```
输入：FaultEvent 或 CondensationWarningEvent 实例

步骤 1 — 前置检查
  检查 event.is_active；若 False → 标记 SKIPPED → 写 INFO 日志 → 返回

步骤 2 — 构建事件上下文
  对 FaultEvent：提取 specific_part / fault_message / severity / fault_type / device_sn
  对 CondensationWarningEvent：提取 specific_part / warning_message / warning_type /
    condensation_alarm_value / dew_point_temp

步骤 3 — 构建 inspection-expert 初始 HumanMessage
  内容包含：事件描述（上下文）+ 巡检指令（"请分析成因，取数，判断是否可处置，若可处置则提案写操作，否则说明不可处置原因"）

步骤 4 — 实例化单专家有界 ReAct 循环
  复用：
    - api.langgraph_chat.orchestrator.Orchestrator 的 llm 和 EXPERT_PROMPTS
    - api.langgraph_chat.fa_tools.TOOLS_BY_EXPERT["inspection-expert"]（含 delegate_* 工具）
    - api.langgraph_chat.orchestrator.Orchestrator._handle_read_delegation()
    - api.langgraph_chat.orchestrator.Orchestrator._run_subexpert()
  不使用：MemorySaver 图、_gate interrupt、路由/fan-out 图（自治场景不需要）

步骤 5 — 执行有界 ReAct（最多 MAX_EXPERT_STEPS=8 步）
  5a. LLM 调用 delegate_knowledge → _handle_read_delegation("sanheng-knowledge") → 结果回灌
  5b. LLM 调用 delegate_read → _handle_read_delegation("energy-expert") → 结果回灌
  5c. LLM 输出最终结论：
      - 若生成 delegate_write 调用 → 进入步骤 6（写授权）
      - 若声明不可处置 → 进入步骤 7（直接创建工单）
      - 若步骤数达到上限 → 进入步骤 7（兜底工单）

步骤 6 — 写授权检查（仅当 LLM 生成 delegate_write 调用时）
  auth_result = WriteAuthPolicy.check(tool_name, args, event)
  if auth_result.allowed:               # 策略 A，白名单内
      result = execute_write(tool_name, args, operator_override="inspection-agent")
      write audit log(WRITE_EXECUTED)
      → 步骤 8
  else:                                  # 策略 B 或策略 A 越界
      write audit log(WRITE_BLOCKED_POLICY_B 或 WRITE_BLOCKED_WHITELIST)
      → 步骤 7（创建工单，recorded_action 含被拦截提案）

步骤 7 — 创建工单
  work_order.create(
      source_event=event,
      symptom=event.fault_message 或 warning_message,
      diagnosis=从 delegate_knowledge 返回摘要,
      recommended_action=从 LLM 结论或被拦截写提案,
      severity=event.severity 或 warning_type
  )
  write audit log(WORKORDER_CREATED)

步骤 8 — 更新处置状态
  event.inspection_status = 'DONE'（或 'SKIPPED'）
  event.save(update_fields=['inspection_status', 'updated_at'])

步骤 9 — 写综合审计日志（事件处理完成标记）
  写 INFO 日志：事件 ID、specific_part、最终处置结果（工单 or 写操作）
```

### 5.2 超时与异常兜底

| 异常类型 | 处理 |
|---------|------|
| `asyncio.TimeoutError` / `httpx.ReadTimeout`（LLM 超时） | 捕获 → 创建工单（兜底）→ 标记 DONE → 写 ERROR 审计日志 |
| 网络中断（`ConnectionError` / `OSError`，WiFi 省电劣化） | 捕获 → 创建工单（兜底）→ 写 ERROR 日志 → 继续下一条事件 |
| 委托专家异常（`_run_subexpert` 抛出） | 捕获 → 错误信息回灌 LLM（不杜撰）→ LLM 决定创建工单或重试 |
| 步数上限（`MAX_EXPERT_STEPS` 耗尽） | LangGraph 循环自然退出 → 捕获退出原因 → 创建工单 → 写 WARNING 日志 |
| DB 写入失败（工单/状态更新） | 捕获 → 写 ERROR 日志 → 不标记 DONE（等待下轮重试） |
| 未预期异常 | `run_forever` 最外层 except 捕获 → 写 ERROR 日志 → sleep 后继续轮询 |

### 5.3 复用边界约束

**可以 import 的模块（只读使用）：**
- `api.langgraph_chat.orchestrator.Orchestrator`（实例化 + 调用 `_handle_read_delegation`、`_run_subexpert`）
- `api.langgraph_chat.fa_tools.TOOLS_BY_EXPERT`（取 inspection-expert 工具列表）
- `api.langgraph_chat.fa_tools.execute_write`（仅在 `WriteAuthPolicy.check()` 返回 `allowed=True` 后调用）
- `api.langgraph_chat.prompts.EXPERT_PROMPTS`（取 inspection-expert 系统提示词）

**绝对不得修改的文件（OOS-01、REQ-CON-004）：**
- `api/langgraph_chat/orchestrator.py`
- `api/langgraph_chat/fa_tools.py`
- `api/langgraph_chat/adapter.py`
- `api/langgraph_chat/` 目录下任何其他现有文件

---

## 6. 自治写授权层设计（OD-01 落地）

### 6.1 WriteAuthPolicy 类设计

模块：`inspection_agent/auth.py`

```
AuthResult（数据类）
  allowed: bool
  reason: str    # "POLICY_B_NO_AUTO_WRITE" / "OUT_OF_WHITELIST" / "APPROVED_BY_WHITELIST"

WriteAuthPolicy
  属性：whitelist（从 INSPECTION_WRITE_WHITELIST 环境变量解析的 dict，PolicyA 使用）

  check(tool_name: str, args: dict, event) → AuthResult:
      policy = os.environ.get("AUTO_WRITE_POLICY", "B").upper()
      if policy == "A":
          return PolicyA(self.whitelist).check(tool_name, args, event)
      return PolicyB().check(tool_name, args, event)

PolicyB（初期推荐）
  check(...) → AuthResult(allowed=False, reason="POLICY_B_NO_AUTO_WRITE")
  无任何例外路径：始终拦截

PolicyA（白名单，备选）
  初始化：从 INSPECTION_WRITE_WHITELIST 解析 JSON 白名单
  check(tool_name, args, event):
      if tool_name not in whitelist: → AuthResult(allowed=False, reason="OUT_OF_WHITELIST")
      param_rules = whitelist[tool_name]
      for param_name, new_value in args.items():
          if param_name in param_rules:
              rule = param_rules[param_name]
              验证 new_value 在 [min_delta, max_delta] 或 [abs_min, abs_max] 范围内
              若越界 → AuthResult(allowed=False, reason="OUT_OF_WHITELIST")
      return AuthResult(allowed=True, reason="APPROVED_BY_WHITELIST")
```

### 6.2 INSPECTION_WRITE_WHITELIST 格式示例

`.env` 中配置（不入 git）：

```
INSPECTION_WRITE_WHITELIST={"set_device_params": {"temperature_set": {"abs_min": 20, "abs_max": 28, "max_delta": 2}}}
```

含义：`set_device_params` 调用中，`temperature_set` 参数的绝对值须在 20–28°C 内，且单次变化量不超过 ±2°C。

### 6.3 调用路径完整性保证

下图展示了从 `delegate_write` 工具调用到实际写操作的**唯一合法路径**：

```
LLM 输出 delegate_write(tool_name, args)
         │
         ▼
InspectionAgent.process_event()
  拦截 delegate_write 调用（不直接传给 orchestrator 执行）
         │
         ▼
WriteAuthPolicy.check(tool_name, args, event)
         │
  ┌──────┴──────┐
  │             │
  allowed=True   allowed=False
  (策略 A 白名单) (策略 B 或越界)
  │             │
  ▼             ▼
execute_write() work_order.create()
  + 审计日志      + 审计日志
```

**没有任何代码路径可以绕过 `WriteAuthPolicy.check()` 直接调用 `execute_write()`**。这是通过代码设计（而非运行时检查）在架构层面强制保证的。

---

## 7. WorkOrder 数据模型

### 7.1 Django 模型定义（追加至 `api/models.py`）

```
WorkOrder 模型（db_table='inspection_work_order'）

字段：
  id              BigAutoField（主键，自动生成）
  ticket_id       CharField max_length=32, unique=True        # 人可读工单编号 WO-YYYYMMDD-NNNNNN
  severity        CharField max_length=16                     # error / warning / 来自预警事件
  source_event_type CharField max_length=32                   # 'fault_event' / 'condensation_warning_event'
  source_event_id BigIntegerField, db_index=True              # 触发事件的 DB 主键
  affected_device CharField max_length=100                    # "{device_sn} / {specific_part}"
  symptom         TextField                                    # 来自 fault_message / warning_message
  diagnosis       TextField blank=True                        # 来自 delegate_knowledge 返回摘要
  recommended_action TextField blank=True                     # 来自 LLM 结论或被拦截写提案
  status          CharField max_length=16, db_index=True      # OPEN / IN_PROGRESS / RESOLVED / CANCELLED
  created_at      DateTimeField auto_now_add=True
  updated_at      DateTimeField auto_now=True
  resolved_at     DateTimeField null=True blank=True
  resolved_by     CharField max_length=100 blank=True

约束：
  uniq_active_workorder_per_event：
    UniqueConstraint(
      fields=['source_event_type', 'source_event_id'],
      condition=Q(status__in=['OPEN', 'IN_PROGRESS']),
      name='uniq_active_workorder_per_event'
    )
    说明：同一事件（source_event_type + source_event_id）在 OPEN/IN_PROGRESS 状态下
         只能有一条活跃工单，防止重复建单

索引：
  wo_status_time_idx:   Index(fields=['status', 'created_at'])
  wo_source_idx:        Index(fields=['source_event_type', 'source_event_id'])
```

**MySQL 兼容性说明**：条件唯一约束（`condition=Q(...)` 即 Partial Index）在 MySQL 8.0+ 和生产 MySQL 9.4 中均受支持。SQLite 测试环境需 Django 4.1+ 支持（已有 Django 版本须在实施前核实）。

### 7.2 ticket_id 生成规则

格式：`WO-{YYYYMMDD}-{6位序号}`，示例：`WO-20260615-000001`

生成逻辑（`inspection_agent/work_order.py`）：
- 每次创建前，查询当天已有工单数量（`COUNT WHERE ticket_id LIKE 'WO-YYYYMMDD-%'`）。
- 序号 = 当天已有数量 + 1，左补零至 6 位。
- 若 DB INSERT 因 `unique=True` 冲突（极低概率并发），递增序号重试一次。

### 7.3 防重复建单逻辑

`work_order.create(source_event_type, source_event_id, ...)` 内部逻辑：
1. 先查询：`WorkOrder.objects.filter(source_event_type=..., source_event_id=..., status__in=['OPEN','IN_PROGRESS']).exists()`
2. 若存在 → 不创建新工单，写 INFO 日志"工单已存在，跳过"，返回已有工单对象。
3. 若不存在 → 创建新工单。
4. DB 层 `uniq_active_workorder_per_event` 约束作为最终兜底（防并发竞争）。

---

## 8. Migration 设计

### 8.1 Migration 0033（`0033_add_inspection_status_and_workorder`）

**文件路径**：`FreeArkWeb/backend/freearkweb/api/migrations/0033_add_inspection_status_and_workorder.py`

**依赖**：`("api", "0032_token_activity_extended_session")`

**操作列表：**

1. `AddField` → `FaultEvent.inspection_status`（CharField, default='PENDING', choices, db_index=True）
2. `AddField` → `FaultEvent.inspection_started_at`（DateTimeField, null=True, blank=True）
3. `AddField` → `CondensationWarningEvent.inspection_status`（同上规格）
4. `AddField` → `CondensationWarningEvent.inspection_started_at`（同上规格）
5. `CreateModel` → `WorkOrder`（含所有字段）
6. `AddConstraint` → `WorkOrder.uniq_active_workorder_per_event`（条件唯一约束）
7. `AddIndex` → `WorkOrder.wo_status_time_idx`
8. `AddIndex` → `WorkOrder.wo_source_idx`

**向后兼容性保证：**
- 所有 `AddField` 操作对现有表均为非破坏性（新增字段带默认值或可为 null）。
- 现有业务功能在 migration 执行前后行为不变（现有代码不引用新字段）。
- `WorkOrder` 表全新创建，表名 `inspection_work_order` 与现有表无冲突。

**执行命令（生产部署）：**
```bash
/home/pi/.venv/bin/python manage.py migrate api 0033_add_inspection_status_and_workorder
```

### 8.2 回滚设计

若需回滚：`python manage.py migrate api 0032_token_activity_extended_session`

回滚操作：
- 删除 `WorkOrder` 表（`inspection_work_order`）
- 从 `FaultEvent` 和 `CondensationWarningEvent` 中删除 `inspection_status` 和 `inspection_started_at` 字段

**注意**：回滚会永久删除已创建的工单数据和处置状态记录。生产回滚前须备份 `inspection_work_order` 表。

---

## 9. 审计日志设计

### 9.1 日志模块结构

模块：`inspection_agent/audit.py`

```
audit_logger = logging.getLogger("freeark.inspection_agent.audit")

必须记录的事件（函数签名）：

log_write_executed(event_id, event_type, specific_part, tool_name, args, result_status)
  → event_type=WRITE_EXECUTED, result=SUCCESS 或 ERROR

log_write_blocked(event_id, event_type, specific_part, tool_name, args, policy_reason)
  → event_type=WRITE_BLOCKED_POLICY_B 或 WRITE_BLOCKED_WHITELIST, result=BLOCKED

log_workorder_created(event_id, event_type, specific_part, ticket_id)
  → event_type=WORKORDER_CREATED, result=SUCCESS

log_delegation_called(event_id, event_type, target_expert, query_summary)
  → event_type=DELEGATION_CALLED, result=SUCCESS 或 ERROR

log_delegation_error(event_id, event_type, target_expert, error_type, error_msg)
  → event_type=DELEGATION_ERROR, result=ERROR
```

### 9.2 日志 JSON 结构（每条审计日志）

```json
{
  "timestamp": "2026-06-15T10:30:00.123456",
  "event_type": "WORKORDER_CREATED",
  "source_event_id": 42,
  "source_event_type": "fault_event",
  "specific_part": "3-1-7-702",
  "action_detail": {
    "ticket_id": "WO-20260615-000001",
    "severity": "warning"
  },
  "result": "SUCCESS"
}
```

### 9.3 安全约束

- 日志 JSON 中**严禁**包含：`DEEPSEEK_API_KEY`、`DB_PASSWORD`、任何包含 `key`/`password`/`token`/`secret` 键名的字段值。
- `audit.py` 的所有函数接口**不接受**凭证类参数，从设计层面防止误传。
- `action_detail` 中记录工具参数时，参数值为业务值（如温度设定值），不含任何网络凭证。

### 9.4 可观测性

通过 `journalctl -u freeark-inspection-agent` 查询，示例：

```bash
journalctl -u freeark-inspection-agent --since "2026-06-15" --output json-pretty | grep WORKORDER_CREATED
```

---

## 10. 性能与可靠性

### 10.1 树莓派单核约束（REQ-NFUNC-001）

| 约束项 | 设计决策 |
|-------|---------|
| 每轮最多处理事件数 | `INSPECTION_BATCH_SIZE`（默认 5），防止积压时爆发式 LLM 并发 |
| 处理模式 | 串行：一条事件处理完成后才处理下一条，不并发 |
| 进程隔离 | 独立进程，不与 `freeark-backend`（Django WSGI/Gunicorn 工作进程）共享线程池 |
| LLM 调用时间 | 单次 8–35s，轮询间隔 30s；处理 5 条事件约 1–3 分钟，期间 chat 接口不受影响（独立进程） |
| DB 负担 | 每 30s 两次 SELECT（FaultEvent + CW）和若干 UPDATE/INSERT，对 MySQL 影响极低 |

### 10.2 LLM 超时兜底（R-02）

- 复用现有 `LANGGRAPH_LLM_TIMEOUT`（默认 60s）。
- 超时捕获：`asyncio.TimeoutError`、`httpx.ReadTimeout`、`httpx.ConnectTimeout`。
- 超时处理：创建工单（兜底，不丢单）→ 将事件标记为 `DONE`（防止无限重试超时事件）→ 写 ERROR 审计日志。

### 10.3 WiFi 省电/网络中断（R-03，已知生产风险）

- 参考 `project_prod_internet_loss_wifi_rca`：`wlan0` 开启 power_save 时可能间歇性劣化。
- 网络异常类型：`ConnectionError`、`OSError`、`ssl.SSLError`。
- 处理：捕获后创建工单（兜底）→ 写 ERROR 日志（含错误类型和事件 ID）→ 继续处理下一条事件，不崩溃。
- `run_forever` 最外层异常捕获确保任何未预期异常不导致服务进程退出（systemd `Restart=on-failure` 作为最终兜底）。

### 10.4 重启零漏单零重单（REQ-NFUNC-002）

```
重启重建流程（服务启动时执行，步骤 3 in Management Command）：

FaultEvent.objects.filter(inspection_status='IN_PROGRESS').update(
    inspection_status='PENDING',
    inspection_started_at=None
)
# CondensationWarningEvent 同上

说明：
- IN_PROGRESS → PENDING：重新处理中途中断的事件（零漏单）
- DONE → 不变：已完成事件不再取用（零重单）
- SKIPPED → 不变：已跳过事件不再取用
```

WorkOrder 防重单：`uniq_active_workorder_per_event` DB 约束 + 代码层先查再建（see §7.3）。

---

## 11. 安全约束汇总

| 约束 | 实施方式 | 来源需求 |
|------|---------|---------|
| 凭证不入 git | `.env` 存放所有凭证，`.gitignore` 已含 `.env` | REQ-CON-005 |
| 凭证不写日志 | `audit.py` 接口不接受凭证类参数 | REQ-NFUNC-003、REQ-NFUNC-004-AC-03 |
| 写操作唯一入口 | `WriteAuthPolicy.check()` 是 `execute_write()` 的唯一前置，无旁路 | REQ-FUNC-005、REQ-NFUNC-003 |
| 禁止修改现有 chat 代码 | OOS-01 约束，代码审查时验证 import 路径，无 `edit`/`write` 操作 | REQ-CON-004、OOS-01 |
| 策略切换不需要改代码 | `AUTO_WRITE_POLICY` 环境变量，修改 `.env` 后重启服务即可切换 | OD-01 设计 |
| 白名单不硬编码 | `INSPECTION_WRITE_WHITELIST` 环境变量（JSON），不入 git | REQ-FUNC-005 |

---

## 12. 部署设计（遵循 REQ-CON-003）

### 12.1 初次部署流程

```bash
# 在本地开发机执行（通过 plink SSH 连接树莓派）
# 步骤 1：拉取最新代码
cd /home/pi/FreeArkWeb
git pull origin main

# 步骤 2：执行数据库 migration
cd backend/freearkweb
/home/pi/.venv/bin/python manage.py migrate

# 步骤 3：安装 systemd service 文件
sudo cp deploy/freeark-inspection-agent.service /etc/systemd/system/
sudo systemctl daemon-reload

# 步骤 4：启用并启动服务
sudo systemctl enable freeark-inspection-agent
sudo systemctl start freeark-inspection-agent

# 步骤 5：验证
sudo systemctl status freeark-inspection-agent
journalctl -u freeark-inspection-agent -n 50 --no-pager
```

### 12.2 日常更新部署流程

```bash
cd /home/pi/FreeArkWeb
git pull origin main
cd backend/freearkweb
/home/pi/.venv/bin/python manage.py migrate    # 若有新 migration
sudo systemctl restart freeark-inspection-agent
sudo systemctl status freeark-inspection-agent
```

### 12.3 .env 新增配置项

```bash
# 自治巡检 Agent 配置（追加至 .env，不入 git）
AUTO_WRITE_POLICY=B
INSPECTION_POLL_INTERVAL=30
INSPECTION_BATCH_SIZE=5
INSPECTION_WRITE_WHITELIST={}   # 策略 A 时填写 JSON 白名单，策略 B 时留空
```

---

## 13. 与现有 Migration 链/模型冲突验证

| 验证项 | 结论 |
|--------|------|
| migration 链末端 | 当前末端：`0032_token_activity_extended_session`；方案 B 新增 `0033`，依赖 `0032`，链路连续 |
| FaultEvent 新增字段冲突 | 无冲突：新增字段独立于现有唯一约束 `(specific_part, device_sn, fault_code, first_seen_at)`；现有索引 `idx_fault_sp_active`、`idx_fault_time_active` 不受影响 |
| CondensationWarningEvent 新增字段冲突 | 无冲突：不触及现有唯一约束和索引 |
| WorkOrder 表名冲突 | 无冲突：`inspection_work_order` 与现有表名（`fault_event`、`condensation_warning_event`、`api_chat_session` 等）均不重名 |
| WorkOrder 条件唯一约束兼容性 | MySQL 9.4 生产环境：支持；SQLite（测试）：Django 4.1+ 支持（实施前需核实 Django 版本）|
| 现有代码对新字段感知 | 现有代码未引用 `inspection_status` 字段，migration 前后现有业务功能不受影响（所有 ORM 查询不含新字段） |

---

## 14. 架构决策记录（ADRs）

### ADR-B-001：事件接入方式选择 DB 轮询

**Status**: Accepted

**Context**（来源：REQ-FUNC-002、S-10、OOS-03、OOS-06）：
`freeark-inspection-agent` 需感知 `fault_event` 和 `condensation_warning_event` 表中新出现的待处置事件。
consumer 服务不可修改（OOS-03），禁止引入新中间件如 Redis（OOS-06）。

**Options**：

- **Option A：Django post_save 信号驱动**
  - 描述：consumer 落库后发出 Django signal，巡检 Agent 监听后触发处理
  - 优点：准实时响应，无轮询延迟
  - 缺点：Django signal 是进程内机制，consumer 与巡检 Agent 是不同进程，跨进程传递需 IPC（Unix socket、Redis pub/sub 等），均属新中间件，违反 OOS-06；且需改动 consumer 侧（违反 OOS-03）
  - 结论：**不可行**，被 OOS-03 + OOS-06 硬性排除

- **Option B：DB 轮询（推荐）**
  - 描述：巡检 Agent 每 30s 查询 DB 中 `is_active=True AND inspection_status='PENDING'` 的记录
  - 优点：实现简单；无额外依赖；DB 是跨进程天然共享存储；不触及 consumer；故障模式可预测
  - 缺点：30s 轮询延迟；额外 DB SELECT 查询（影响极低）
  - 结论：**可行，采用**

**Decision**: 采用 Option B（DB 轮询），轮询间隔 30s，通过 `inspection_status` 字段（migration 0033 新增）作为处置状态机。

**Consequences**：
- 正向：无新中间件依赖，实现简单，故障恢复路径清晰，与 OOS-03/OOS-06 完全兼容。
- 负向：预警触发有最长 30s 延迟（楼宇三恒场景可接受）；需在两张事件表各新增两个字段（migration 0033）。

---

### ADR-B-002：状态持久化选择自建状态字段

**Status**: Accepted

**Context**（来源：REQ-FUNC-007、REQ-NFUNC-002、S-08）：
服务重启后需能识别未完成的处置任务（零漏单），已完成的不再重复处理（零重单）。进程内 `MemorySaver` 不满足持久化要求（AC-007-03 明确排除）。

**Options**：

- **Option X：LangGraph DB Checkpointer**
  - 描述：使用 LangGraph 官方 DB checkpointer（如 `langgraph-checkpoint-sqlite` 或 `langgraph-checkpoint-postgres`）
  - 优点：与 LangGraph 图状态深度集成，理论上支持断点续传中间步骤
  - 缺点：需引入新包；官方版本以 PostgreSQL/SQLite 为主，与生产 MySQL 9.4 兼容性未验证；方案 B 的有界 ReAct（8 步内完成）不需要步骤级断点续传，该方案引入了超出实际需求的复杂度；测试环境适配难度增加

- **Option Y：自建状态字段（推荐）**
  - 描述：在 `FaultEvent` 和 `CondensationWarningEvent` 表新增 `inspection_status`（PENDING/IN_PROGRESS/DONE/SKIPPED）和 `inspection_started_at` 字段
  - 优点：实现简单；完全复用现有 Django ORM + MySQL；SQLite 测试环境直接兼容；无新依赖；重建逻辑清晰（启动时 IN_PROGRESS → PENDING）
  - 缺点：与 LangGraph 图内部状态解耦，若步骤级状态重要需手动维护（方案 B 的幂等 ReAct 设计使此缺点实际影响极小）

**Decision**: 采用 Option Y（自建状态字段），通过 migration 0033 实现。

**Consequences**：
- 正向：零新依赖，实现简单可靠，完全契合方案 B 的幂等设计哲学。
- 负向：不支持 LangGraph 步骤级断点续传（方案 B 的有界 ReAct 允许重新处理，幂等设计消除此影响）。

---

### ADR-B-003：写授权策略推荐策略 B（全转工单）

**Status**: Proposed（待用户拍板）

**Context**（来源：REQ-FUNC-005、REQ-NFUNC-003、OD-01）：
在无人值守的自治场景下，inspection-expert 的 `delegate_write` 工具调用提案是否应自动执行？

**Options**：

- **Option A：安全区间白名单自动执行（PolicyA）**
  - 描述：参数变化量在 `INSPECTION_WRITE_WHITELIST` 定义的安全区间内自动执行写操作，越界转工单
  - 优点：实现"自治处置"价值，减少人工介入；白名单可精细控制风险
  - 缺点：LLM 在白名单内仍可能误判（如将错误的房间参数调整了"合理"范围内的值）；白名单参数设计需精确；树莓派无回滚机制，物理影响不可逆；初期无 LLM 决策质量基线

- **Option B：全转工单，无自动写（PolicyB）（推荐初期）**
  - 描述：所有写操作提案均不自动执行，一律创建工单待人工处置
  - 优点：零自动写风险；所有 LLM 决策通过工单显式记录，可审查决策质量；适合系统初期建立信任基线
  - 缺点：需人工跟进每条工单，不实现完全自治；响应速度依赖人工跟进频率

**Decision**: 推荐策略 B（PolicyB）作为初期策略，通过 `WriteAuthPolicy` 类设计保留策略 A 的代码接缝，待 LLM 决策质量经审计日志验证（建议 30 天 >= 90% 吻合率）后通过 `.env` 切换至策略 A，无需代码变更。

**Consequences**：
- 正向：零自动写风险；与 AC-005-B-01/02 完全匹配；建立 LLM 决策质量审计基线；策略切换无需代码部署。
- 负向：初期"自治处置"价值受限（需人工处置工单）；若工单积压，运维负担增加（缓解：工单通知 REQ-FUNC-009 为 P2 项，可配合解决）。

---

### ADR-B-004：服务复用方式（进程内 import vs. 微服务 HTTP 调用）

**Status**: Accepted

**Context**（来源：REQ-FUNC-004、S-03、REQ-CON-001、OOS-01）：
方案 B 需复用 `api/langgraph_chat/` 中的 experts 和委托工具。有两种复用方式：进程内 import 或通过 HTTP 调用 `freeark-backend`。

**Options**：

- **Option A：微服务 HTTP 调用**
  - 描述：`freeark-inspection-agent` 通过 HTTP 调用 `freeark-backend` 的 chat API，复用 chat 链路
  - 优点：物理隔离，互不影响
  - 缺点：绑定了 chat 链路（需触发用户 session、路由、fan-out 全图）；chat 链路有 `_gate` interrupt 机制（需人工确认），不适合自治场景；http 调用增加延迟和故障点；方案 A 的 chat 路由逻辑不为方案 B 设计

- **Option B：进程内 import 单专家调用（推荐）**
  - 描述：在 `inspection_agent/agent.py` 中直接 `import` 生产 `api.langgraph_chat.*` 模块，构建单专家有界 ReAct 循环，绕过路由/fan-out/gate 图
  - 优点：完整复用专家逻辑和工具定义；不走不适合自治场景的 `_gate` interrupt；实现简单；不依赖 freeark-backend 进程是否运行（独立进程内 import）；Django Management Command 天然可访问同一个 Django ORM 和应用包
  - 缺点：与 `api/langgraph_chat/` 存在模块依赖（API 变更需跟进）；需确保不修改被 import 的文件（OOS-01）

**Decision**: 采用 Option B（进程内 import），明确复用边界：只 import，不修改；只调用 `_handle_read_delegation` 和 `_run_subexpert`，不走完整的路由-fan_out-aggregate 图。

**Consequences**：
- 正向：完整复用专家逻辑；不依赖 freeark-backend HTTP 接口；实现简单；符合 S-03 明确要求（"进程内复用"）。
- 负向：与 `api/langgraph_chat/` 存在模块级耦合（方案 A API 重大变更时方案 B 需跟进，风险 R-06 缓解：代码审查约束 + import 路径检查）。

---

## 15. 开放问题（[ASSUMPTION] 标注）

| 编号 | 开放问题 | 影响 | 建议行动 |
|------|---------|------|---------|
| OQ-01 | 生产 Django 版本是否 >= 4.1（SQLite 条件唯一约束兼容性需要） | WorkOrder 的 `uniq_active_workorder_per_event` 在 SQLite 测试环境可用性 | 实施前执行 `python -c "import django; print(django.VERSION)"` 核实 |
| OQ-02 | `inspection-expert` 的 SYSTEM_PROMPT 是否包含"无人值守场景下不直接执行写操作，使用 delegate_write 提案"的约束 [ASSUMPTION：已包含] | 若未包含，LLM 可能绕过 delegate_write 直接输出参数，需补充提示词 | 实施前审查 `EXPERT_PROMPTS["inspection-expert"]` 内容 |
| OQ-03 | `Orchestrator._handle_read_delegation` 和 `_run_subexpert` 是否为公开方法（非 `__` 前缀私有方法） | 若为私有，进程内 import 调用需调整 | 实施前核实 `orchestrator.py` 方法签名（当前描述为单下划线 `_handle_read_delegation`，可访问） |
| OQ-04 | 工单通知渠道（REQ-FUNC-009，P2）用户尚未决策 [INFERRED — requires PM confirmation] | P2 功能实施计划 | 用户确认通知渠道后补充实施 |
| OQ-05 | 策略 A 白名单具体参数范围（温度安全区间边界值）未定义 [ASSUMPTION — requires PM confirmation] | PolicyA 的 `INSPECTION_WRITE_WHITELIST` 内容 | 若用户决定启用策略 A，需与运维人员共同定义安全区间参数 |

---

## 16. 演进路线（超出本版本）

| 编号 | 演进项 | 当前限制 | 演进条件 |
|------|--------|---------|---------|
| EV-01 | 升级至策略 A（白名单自动执行） | 策略 B 初期，无 LLM 决策质量基线 | 审计日志显示 30 天 LLM 提案准确率 >= 90% |
| EV-02 | 工单通知（REQ-FUNC-009，钉钉/短信/邮件） | P2，渠道未定 | 用户确认通知渠道后实施 |
| EV-03 | 工单列表 Web UI（REQ-FUNC-010） | P2，交互未定 | 用户确认 UI 交互细节后实施 |
| EV-04 | 多事件并发处理 | 当前串行，树莓派单核约束 | 若积压严重且性能允许，引入有限并发（线程池，上限 2） |
| EV-05 | 定时主动巡检（非事件驱动） | 当前仅响应 fault_event/CW 触发 | 产品需求确认后，EventPoller 扩展 schedule 维度 |
| EV-06 | 策略 A 白名单可视化配置 UI | 当前通过 .env 配置 | 白名单参数需频繁调整时引入 |
