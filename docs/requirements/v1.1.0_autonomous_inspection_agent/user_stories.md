---
file_header:
  document_id: US-v1.1.0-AIA
  title: 自治巡检 Agent（方案 B）— 用户故事清单
  author_agent: sub_agent_system_architect
  project: FreeArk v1.1.0
  version: 0.1.0-DRAFT
  created_at: 2026-06-15
  status: DRAFT
  references:
    - docs/requirements/v1.1.0_autonomous_inspection_agent/requirements_spec.md (status=DRAFT)
---

> **注意**：本文件依赖的需求规格说明书（requirements_spec.md）当前状态为 DRAFT（非 APPROVED）。
> 用户故事基于已定稿的需求内容产出，正式实施前须等待需求规格状态升级为 APPROVED。

---

## P0 / P1 用户故事（Must Have / Should Have）

---

### US-001（对应 REQ-FUNC-001）

作为 运维人员
我希望 系统提供独立的 `freeark-inspection-agent` systemd 服务，能以常驻后台进程的方式自动运行
以便 巡检 Agent 能无人值守地响应设备预警，不依赖人工触发、不依赖 chat HTTP 请求

#### 验收标准

- **AC-US-001-01**（对应 AC-001-01：服务独立运行）
  - Given: 代码已通过 `git pull` 部署到生产服务器（192.168.31.51），并已执行 `sudo systemctl start freeark-inspection-agent`
  - When: 运行 `sudo systemctl status freeark-inspection-agent`
  - Then: 输出显示服务状态为 `active (running)`，进程 PID 与 `freeark-backend`（Django WSGI）和 `freeark-fault-consumer` 各自独立，互不共享

- **AC-US-001-02**（对应 AC-001-02：自动重启）
  - Given: `freeark-inspection-agent.service` unit 文件中已配置 `Restart=on-failure` 和 `RestartSec=30`
  - When: 服务进程因未捕获异常以非零退出码退出
  - Then: systemd 在 30s 后自动重启该服务，无需人工干预，journalctl 中可见重启事件

- **AC-US-001-03**（对应 AC-001-03：开机自启）
  - Given: 已执行 `sudo systemctl enable freeark-inspection-agent`
  - When: 树莓派重启完成
  - Then: `freeark-inspection-agent` 服务在系统启动后自动进入 `active (running)` 状态

---

### US-002（对应 REQ-FUNC-002）

作为 运维人员
我希望 系统自动从 `fault_event` 表和 `condensation_warning_event` 表中识别活跃且尚未处置的预警记录
以便 每一条新出现的故障或结露预警都能被自动纳入处置流程，无需人工筛选

#### 验收标准

- **AC-US-002-01**（对应 AC-002-01：识别未处置的活跃故障事件）
  - Given: `fault_event` 表中存在 `is_active=True` 且 `inspection_status='PENDING'` 的记录
  - When: `freeark-inspection-agent` 服务的轮询周期触发（每 30s 一次）
  - Then: 服务识别到该记录，为其触发一次自治决策循环；该记录的 `inspection_status` 被原子更新为 `IN_PROGRESS`

- **AC-US-002-02**（对应 AC-002-02：识别未处置的活跃结露预警）
  - Given: `condensation_warning_event` 表中存在 `is_active=True` 且 `inspection_status='PENDING'` 的记录
  - When: 轮询周期触发
  - Then: 服务识别到该记录，为其触发一次自治决策循环；`inspection_status` 原子更新为 `IN_PROGRESS`

- **AC-US-002-03**（对应 AC-002-03：不重复处置）
  - Given: 某条预警事件已完成处置，`inspection_status='DONE'`（或已创建工单）
  - When: 服务继续运行，或服务重启后
  - Then: 轮询查询条件 `inspection_status='PENDING'` 过滤掉该记录，不再触发决策循环，不产生重复工单

- **AC-US-002-04**（对应 AC-002-04：忽略已恢复事件）
  - Given: 某条 `fault_event` 记录在被服务取用前已恢复为 `is_active=False`
  - When: 服务准备处理该记录（如在 IN_PROGRESS 期间事件恢复）
  - Then: 服务检测到 `is_active=False`，跳过该记录，将 `inspection_status` 更新为 `SKIPPED`，写入 INFO 级别日志

---

### US-003（对应 REQ-FUNC-003）

作为 运维人员
我希望 系统在接收到预警后自动执行"知识分析 → 取数 → 处置判断"四步决策链，并在结论明确后创建工单或发起处置提案
以便 每条预警均获得专业诊断意见，而不是简单地丢弃或忽略

#### 验收标准

- **AC-US-003-01**（对应 AC-003-01：知识分析委托被调用）
  - Given: 服务接收到一条活跃的结露预警事件（`condensation_warning_event`），`specific_part="3-1-7-702"`
  - When: 决策循环启动
  - Then: 决策链中有且仅有一次 `delegate_knowledge` 调用，入参包含该预警描述信息，返回三恒成因分析结果后流程继续；审计日志记录 `event_type=DELEGATION_CALLED`

- **AC-US-003-02**（对应 AC-003-02：只读取数委托被调用）
  - Given: `delegate_knowledge` 已返回分析结果
  - When: 决策链继续执行
  - Then: 决策链中有且仅有一次 `delegate_read` 调用，入参包含 `specific_part` 及取数需求，返回实时参数和/或历史数据；审计日志记录 `event_type=DELEGATION_CALLED`

- **AC-US-003-03**（对应 AC-003-03：可处置路径生成处置提案）
  - Given: `delegate_read` 返回数据后，LLM 判断该预警可通过参数调整处置
  - When: 决策链继续执行
  - Then: 服务生成处置提案，强制进入 `WriteAuthPolicy.check()` 授权检查，不存在跳过授权直接写设备的路径

- **AC-US-003-04**（对应 AC-003-04：不可处置路径创建工单）
  - Given: `delegate_read` 返回数据后，LLM 判断该预警超出可自动处置范围
  - When: 决策链继续执行
  - Then: 服务调用工单创建逻辑，生成一条 `WorkOrder` 记录（`status=OPEN`），不尝试写设备参数；`inspection_status` 更新为 `DONE`

- **AC-US-003-05**（对应 AC-003-05：委托步数上限保护）
  - Given: 决策链正在处理单条预警
  - When: 委托工具调用次数达到步数上限（`MAX_EXPERT_STEPS=8`）
  - Then: 流程安全退出，写入 WARNING 级别日志，创建工单（兜底），不丢失预警；`inspection_status` 更新为 `DONE`

- **AC-US-003-06**（对应 AC-003-06：委托专家报错降级）
  - Given: `delegate_knowledge` 或 `delegate_read` 调用中目标专家抛出异常或超时
  - When: 委托调用失败
  - Then: 错误信息回灌给 inspection-expert（不杜撰结果），审计日志记录 `event_type=DELEGATION_ERROR`；决策链根据错误信息选择创建工单（兜底），不崩溃

---

### US-004（对应 REQ-FUNC-004）

作为 开发人员
我希望 `freeark-inspection-agent` 直接进程内复用 `api/langgraph_chat/` 中已有的 experts 和委托工具
以便 不重复维护专家逻辑，方案 A 的专家能力升级时方案 B 自动受益

#### 验收标准

- **AC-US-004-01**（对应 AC-004-01：复用生产专家模块）
  - Given: `freeark-inspection-agent` 服务启动
  - When: 服务初始化 `InspectionAgent`
  - Then: 代码使用 `from api.langgraph_chat.fa_tools import TOOLS_BY_EXPERT` 等同一套配置，不存在独立维护的专家副本；`grep -r "def inspection_expert" inspection_agent/` 返回空

- **AC-US-004-02**（对应 AC-004-02：inspection-expert 委托工具可用）
  - Given: 服务运行中，决策链启动
  - When: inspection-expert 执行推理
  - Then: inspection-expert 的工具列表包含 `delegate_knowledge`、`delegate_read`、`delegate_write` 三个委托工具（与方案 A chat 链路一致）

- **AC-US-004-03**（对应 AC-004-03：非委托专家不暴露委托工具）
  - Given: 决策链中 energy-expert 或 sanheng-knowledge 被 `_run_subexpert` 调用
  - When: 被委托专家执行（深度限 1）
  - Then: 被委托专家的工具列表中不包含任何委托工具（`delegate_*`），不可发起二次委托，杜绝递归

---

### US-005（对应 REQ-FUNC-005）

作为 系统安全负责人
我希望 所有无人值守场景下的设备写操作（`set_device_params` / `trigger_refresh`）必须经过明确的授权策略检查，且策略可通过环境变量切换
以便 在系统初期以零自动写风险（策略 B）验证决策链质量，待信心充足后可升级为白名单自动执行（策略 A），全程有据可查

#### 验收标准（策略 B，初期推荐）

- **AC-US-005-B-01**（对应 AC-005-B-01：所有写提案转工单）
  - Given: `AUTO_WRITE_POLICY=B`（环境变量设置），决策链生成任意写操作提案
  - When: 授权检查 `WriteAuthPolicy.check()` 执行
  - Then: 写操作不执行；调用方转入工单创建逻辑；审计日志记录 `event_type=WRITE_BLOCKED_POLICY_B`，`result=BLOCKED`

- **AC-US-005-B-02**（对应 AC-005-B-02：无自动执行路径）
  - Given: `AUTO_WRITE_POLICY=B`，任意预警事件经过决策链
  - When: 决策链完成
  - Then: 生产 DB 中不存在由 `freeark-inspection-agent` 直接发起的设备参数变更记录；设备参数仅可通过方案 A chat 链路（`_gate` 确认门）由人工确认后写入

#### 验收标准（策略 A，备选）

- **AC-US-005-A-01**（对应 AC-005-A-01：白名单内自动执行）
  - Given: `AUTO_WRITE_POLICY=A`，决策链提案将某房间温度设定值从 26°C 调整为 25°C（变化量 1°C，在白名单安全区间内）
  - When: `WriteAuthPolicy.check()` 执行
  - Then: 写操作通过授权，`execute_write()` 被调用，审计日志记录 `event_type=WRITE_EXECUTED`，`result=SUCCESS`

- **AC-US-005-A-02**（对应 AC-005-A-02：越界转工单）
  - Given: `AUTO_WRITE_POLICY=A`，决策链提案参数调整量超出白名单范围
  - When: `WriteAuthPolicy.check()` 执行
  - Then: 写操作不执行，转工单；审计日志记录 `event_type=WRITE_BLOCKED_WHITELIST`，`result=BLOCKED`；工单 `recommended_action` 记录被拦截提案

---

### US-006（对应 REQ-FUNC-006）

作为 运维人员
我希望 系统在决策链判断"不可处置"或"写操作超出授权范围"时自动创建持久化工单（WorkOrder）
以便 每条未被自动处置的预警都有明确的处置任务等待人工跟进，不丢失

#### 验收标准

- **AC-US-006-01**（对应 AC-006-01：不可处置时创建工单）
  - Given: 决策链执行完毕，LLM 判断预警超出自动处置范围
  - When: 工单创建逻辑执行
  - Then: `inspection_work_order` 表新增一条记录，`status=OPEN`，`source_event_id` 指向触发事件的 DB 主键，`symptom`/`diagnosis`/`recommended_action` 均已填充（不为空字符串）

- **AC-US-006-02**（对应 AC-006-02：写提案越界时创建工单，策略 A）
  - Given: `AUTO_WRITE_POLICY=A`，授权检查拦截了超出白名单的写提案
  - When: 拦截后转工单逻辑执行
  - Then: `inspection_work_order` 表新增记录，`recommended_action` 字段包含被拦截的写提案内容（含参数名和建议值），`status=OPEN`

- **AC-US-006-03**（对应 AC-006-03：同一事件不重复建单）
  - Given: 某 `fault_event` 记录已有关联的 `WorkOrder`（`status` 为 `OPEN` 或 `IN_PROGRESS`）
  - When: 服务因重启再次识别到该事件（`inspection_status` 已重置为 PENDING）
  - Then: 代码层先查询现有活跃工单，DB 层 `uniq_active_workorder_per_event` 约束兜底；不创建重复工单，已有工单保持不变

- **AC-US-006-04**（对应 AC-006-04：工单持久化到生产 DB）
  - Given: 工单创建成功，记录已写入 `inspection_work_order` 表
  - When: `freeark-inspection-agent` 服务重启
  - Then: `inspection_work_order` 表中该工单记录仍存在，`status`/`ticket_id`/`diagnosis` 等字段值不丢失

---

### US-007（对应 REQ-FUNC-007）

作为 运维人员
我希望 系统能持久化每条预警事件的决策处置进度，在服务重启后自动恢复未完成的处置任务
以便 树莓派宕机或网络中断导致服务重启时，不发生漏单（漏处置）或重单（重复处置）

#### 验收标准

- **AC-US-007-01**（对应 AC-007-01：正常完成后状态持久化）
  - Given: 服务对某条 `fault_event`（`id=N`）完成完整决策循环，`inspection_status` 已更新为 `DONE`
  - When: 服务重启
  - Then: 重启后轮询查询（`WHERE inspection_status='PENDING'`）不返回该记录，决策循环不被重新触发

- **AC-US-007-02**（对应 AC-007-02：中途崩溃后重启可识别未完成状态）
  - Given: 服务在处理某条预警的决策循环中途崩溃，该记录 `inspection_status='IN_PROGRESS'`
  - When: 服务重启，执行启动重建逻辑
  - Then: 启动时原子 UPDATE 将所有 `inspection_status='IN_PROGRESS'` 的记录重置为 `PENDING`，下一轮轮询重新取用，不丢单

- **AC-US-007-03**（对应 AC-007-03：MemorySaver 不满足持久化要求）
  - Given: 方案 B 不使用 `MemorySaver`（进程内内存，重启即丢）作为处置状态存储
  - When: 验证设计
  - Then: `inspection_agent/` 包内无 `MemorySaver` 实例化代码；处置状态完全依赖 `fault_event.inspection_status` 和 `condensation_warning_event.inspection_status` 字段（DB 持久化）

---

### US-008（对应 REQ-FUNC-008）

作为 运维人员 / 安全审计员
我希望 系统对每次写操作授权判断、工单创建及委托调用关键节点写入结构化审计日志，可通过 journalctl 查询
以便 事后追溯任意预警事件的完整处置链路，验证 LLM 决策质量，排查异常

#### 验收标准

- **AC-US-008-01**（对应 AC-008-01：写操作执行审计，策略 A）
  - Given: `AUTO_WRITE_POLICY=A`，白名单内写操作成功执行
  - When: 操作完成
  - Then: `journalctl -u freeark-inspection-agent` 可检索到 `event_type=WRITE_EXECUTED` 的 JSON 日志条目，含 `specific_part`、`action_detail`（含参数名和新值）、`result=SUCCESS`，时间戳精确到秒

- **AC-US-008-02**（对应 AC-008-02：写操作拦截审计）
  - Given: 写操作被拦截（策略 A 越界或策略 B 全拦截）
  - When: 拦截发生
  - Then: 日志中出现 `event_type=WRITE_BLOCKED_WHITELIST` 或 `WRITE_BLOCKED_POLICY_B`，含 `specific_part`、`action_detail`、`result=BLOCKED`

- **AC-US-008-03**（对应 AC-008-03：工单创建审计）
  - Given: 工单创建成功
  - When: 创建完成
  - Then: 日志中出现 `event_type=WORKORDER_CREATED`，含 `source_event_id`、`ticket_id`（工单编号）、`result=SUCCESS`

- **AC-US-008-04**（对应 AC-008-04：审计日志通过 journalctl 可查）
  - Given: `freeark-inspection-agent.service` unit 文件中已配置 `StandardOutput=journal`
  - When: 任意时刻
  - Then: `journalctl -u freeark-inspection-agent --output json-pretty` 可检索到完整结构化审计条目，不需要额外日志文件

---

## P2 用户故事（Could Have，待用户决策后实施）

> 以下用户故事对应 REQ-FUNC-009 和 REQ-FUNC-010，优先级为 P2（Could Have）。
> **当前状态**：待用户确认通知渠道（REQ-FUNC-009）和 UI 交互细节（REQ-FUNC-010）后实施。
> 本期最低可接受交付为"工单落库"，通知与 UI 均为增强项，不阻塞 P0/P1 交付。

---

### US-009（对应 REQ-FUNC-009）— 待用户决策后实施

作为 运维人员
我希望 系统在工单创建后通过已配置的通知渠道（钉钉/短信/邮件，具体待定）向我发送通知
以便 我能及时获知新的待处置预警，不需要主动查看系统

**当前决策缺口**：通知渠道（钉钉 webhook / 短信 / 邮件）及触发时机需用户确认。`[INFERRED — requires PM confirmation]`

#### 验收标准

- **AC-US-009-01**（对应 AC-009-01：工单通知发送）
  - Given: 新工单创建成功，通知渠道已通过 `.env` 配置
  - When: 工单落库完成
  - Then: 系统通过已配置渠道向至少一个运维人员发送通知，通知内容包含工单编号、严重级别（`severity`）、受影响房间（`specific_part`）

---

### US-010（对应 REQ-FUNC-010）— 待用户决策后实施

作为 运维人员
我希望 在 Web 管理界面中有一个工单列表页面，可以查看所有待处置工单并标记为已解决
以便 在不借助数据库工具的情况下管理和跟踪所有预警处置任务

**当前决策缺口**：UI 详细交互（筛选、分页、处置操作流程）待用户确认。`[INFERRED — requires PM confirmation]`

#### 验收标准

- **AC-US-010-01**（对应 AC-010-01：工单列表可访问）
  - Given: 用户已登录 FreeArk Web 管理界面
  - When: 用户访问工单列表页面（URL 待定）
  - Then: 页面展示 `inspection_work_order` 表中的工单，包含工单编号（`ticket_id`）、严重级别、受影响设备（`affected_device`）、状态（`status`）、创建时间，支持分页浏览

---

## 用户故事覆盖矩阵

| 用户故事 | 对应需求 | 优先级 | 覆盖验收标准数量 |
|---------|---------|--------|----------------|
| US-001 | REQ-FUNC-001 | P0 Must Have | 3 |
| US-002 | REQ-FUNC-002 | P0 Must Have | 4 |
| US-003 | REQ-FUNC-003 | P0 Must Have | 6 |
| US-004 | REQ-FUNC-004 | P0 Must Have | 3 |
| US-005 | REQ-FUNC-005 | P0 Must Have | 4 |
| US-006 | REQ-FUNC-006 | P1 Should Have | 4 |
| US-007 | REQ-FUNC-007 | P0 Must Have | 3 |
| US-008 | REQ-FUNC-008 | P1 Should Have | 4 |
| US-009 | REQ-FUNC-009 | P2 Could Have | 1 |
| US-010 | REQ-FUNC-010 | P2 Could Have | 1 |
