# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v1.1.0-AIA
  title: 自治巡检 Agent（方案 B）— 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇三恒系统物联网管理平台
  version: v1.1.0-autonomous-inspection-agent
  created_at: 2026-06-15
  status: DRAFT
  references:
    - agents/langgraph-poc/PHASE_G_DELEGATION_DESIGN.md §4
    - FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py
    - FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py
    - FreeArkWeb/backend/freearkweb/api/models.py (FaultEvent, CondensationWarningEvent)
    - docs/requirements/v0.6.0_fault_management/requirements_spec.md
    - docs/requirements/v0.7.0_condensation_warning/requirements_spec.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-06-15 | 初始草稿，基于 PHASE_G_DELEGATION_DESIGN.md §4 及业主原始需求#3；含头号开放决策 OD-01~OD-03 |
| 0.2.0-DRAFT | 2026-06-15 | 架构门通过，三条开放决策落定：OD-01=策略B（用户拍板，AUTO_WRITE_POLICY=B 零自动写）、OD-02=DB轮询（架构师裁定）、OD-03=自建状态字段（架构师裁定）；P2：工单仅落库+Django Admin、本期不做通知 |

---

## 1. 背景与动因

### 1.1 项目背景

FreeArk 是楼栋三恒系统（温湿度控制/新风/能耗）的物联网管理平台，生产部署在树莓派
（内网 192.168.31.51），禁止 Docker，所有服务以 systemd 管理。

**原始需求 #3**（节选自设计稿 §0）：

> 巡检 agent 收到预警→分析(三恒)→取数(能耗)→处置(能耗写)→否则开工单

**方案 A（已上线，PR #19，2026-06-15）**：在生产 chat 编排器
（`api/langgraph_chat/`）中为 `inspection-expert` 绑定了三个跨专家委托工具
（`delegate_knowledge` / `delegate_read` / `delegate_write`）。这是**用户触发的同步
chat 链路**，已满足"联动三恒/能耗"目标，但不满足"自治/有状态/无人值守/工单"要求。

**本版本（v1.1.0，方案 B）** 是方案 A 的上层扩展：把同一套委托决策循环搬到**事件驱动、
有状态、无人值守**的独立子系统，完整实现原始需求 #3 的"自治+工单"部分。

**来源**：设计稿 `PHASE_G_DELEGATION_DESIGN.md §4`（以下简称"设计稿 §4"）。

### 1.2 版本定位

| 版本 | 主要变更 |
|------|---------|
| v1.0.0 | 仪表盘重设计 + 设备/结露面板 |
| v1.1.0-方案A | inspection-expert 绑定委托工具（chat 同步链路，PR #19 已上线） |
| **v1.1.0-方案B** | **自治巡检 Agent 独立子系统（本版本需求）** |

---

## 2. 范围

### 2.1 本版本范围内（In Scope）

| 编号 | 范围项 | 来源 |
|------|--------|------|
| S-01 | 新增独立 systemd 服务 `freeark-inspection-agent`，事件驱动、无人值守运行 | 设计稿 §4.2 |
| S-02 | 从 `fault_event` 表和 `condensation_warning_event` 表接收活跃预警事件作为触发源 | 设计稿 §4.2 |
| S-03 | 进程内复用 `api/langgraph_chat/` 的 experts（energy / sanheng / inspection）及委托工具（`delegate_knowledge` / `delegate_read` / `delegate_write`） | 设计稿 §4.2 |
| S-04 | 自主决策闭环：预警 → 三恒成因分析 → 取数 → 处置提案/工单创建 → 记录状态 | 设计稿 §4.2 |
| S-05 | 自治写授权模型（**核心安全要害，见 OD-01**）：定义在无人值守下写操作的授权策略 | 设计稿 §4.2 |
| S-06 | 新增 `WorkOrder` 数据模型及 Django migration | 设计稿 §4.2 |
| S-07 | 工单持久化到 DB（先落库，通知与 UI 视用户决策列为 P2） | 设计稿 §4.2 |
| S-08 | 处置状态持久化：防止重启后重复处置或漏处置 | 设计稿 §4.2 |
| S-09 | 审计日志：每次自治写操作（执行或拒绝）均须有可查的结构化日志记录 | 设计稿 §4.2 |
| S-10 | 事件接入方式（**架构阶段定夺，见 OD-02**）：DB 轮询或信号驱动 | 设计稿 §4.2 |

### 2.2 本版本范围外（Out of Scope）

| 编号 | 排除项 | 说明 |
|------|--------|------|
| OOS-01 | 改动现有 chat 链路（`api/langgraph_chat/`） | 方案 B 是独立子系统，不修改方案 A 已上线代码 |
| OOS-02 | 将 PoC 委托工具逻辑（`agents/langgraph-poc/`）重新移植到生产 | 生产侧已由方案 A 落地，方案 B 直接复用；不再另行移植 PoC 版本 |
| OOS-03 | 改造 `freeark-fault-consumer` 或 `freeark-condensation-consumer` | 两个已有 consumer 服务保持不变，方案 B 仅消费其写入的 DB 记录 |
| OOS-04 | 修改 MQTT Consumer 协议或 MQTT broker 配置 | 同 OOS-03 |
| OOS-05 | 前端工单处置 UI（P2，视用户决策实施，本期仅落库+通知） | 设计稿 §4.2 备注 |
| OOS-06 | Redis/外部消息队列引入 | 本期禁止引入新中间件；状态持久化由架构师在 DB 方案内确定 |
| OOS-07 | 告警通知渠道（钉钉/短信/邮件）集成 | 超出本版本范围，记入演进路线 |
| OOS-08 | chat 链路的 `_gate` interrupt 确认 UX 变更 | 写确认门已有，方案 B 不修改现有确认逻辑 |
| OOS-09 | PoC 代码（`agents/langgraph-poc/`）修改或删除 | PoC 独立维护，不受本版本影响 |

---

## 3. 功能需求

### REQ-FUNC-001：独立 systemd 服务

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-001 |
| 描述 | 系统应当新增独立 Django Management Command，由 systemd 服务 `freeark-inspection-agent` 管理，以独立进程无人值守运行，不依赖 chat HTTP 请求触发。 |
| 来源引用 | "独立 systemd 服务（`freeark-inspection-agent`），与 freeark-fault-consumer 共存" — 设计稿 §4.2 |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-001-01（服务独立运行）**
  - Given：代码已部署，`sudo systemctl start freeark-inspection-agent` 执行完毕
  - When：查询 `sudo systemctl status freeark-inspection-agent`
  - Then：服务状态为 `active (running)`，进程独立于 `freeark-backend`（Django WSGI）和 `freeark-fault-consumer`

- **AC-001-02（自动重启）**
  - Given：`freeark-inspection-agent.service` 已注册 `Restart=on-failure`
  - When：进程因异常退出（非零退出码）
  - Then：systemd 在配置的 `RestartSec` 后自动重启服务，无需人工干预

- **AC-001-03（开机自启）**
  - Given：服务已通过 `systemctl enable` 启用
  - When：树莓派重启
  - Then：服务在系统启动后自动运行

---

### REQ-FUNC-002：事件源接入（从 DB 读取活跃预警）

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-002 |
| 描述 | 系统应当从 `fault_event` 表和 `condensation_warning_event` 表中识别新出现的活跃且尚未处置的记录，作为触发自治决策循环的事件源。 |
| 来源引用 | "自治巡检 Agent 的事件源即来自这两张表中新出现的活跃记录" — 原始需求（设计稿 §4.2） |
| 优先级 | Must Have |
| 备注 | 接入方式（DB 轮询 vs 信号驱动）为架构开放决策 OD-02，留给架构师定夺 |

**验收标准：**

- **AC-002-01（识别未处置的活跃故障事件）**
  - Given：`fault_event` 表中存在 `is_active=True` 且尚未被本服务处置的记录
  - When：服务在运行中（无论轮询还是信号驱动，由架构决定）
  - Then：服务识别到该记录，并为其触发一次且仅一次自治决策循环

- **AC-002-02（识别未处置的活跃结露预警）**
  - Given：`condensation_warning_event` 表中存在 `is_active=True` 且尚未被本服务处置的记录
  - When：服务在运行中
  - Then：服务识别到该记录，并为其触发一次且仅一次自治决策循环

- **AC-002-03（不重复处置）**
  - Given：某条预警事件已完成处置（已创建工单或已记录处置状态）
  - When：服务继续运行或服务重启后
  - Then：该条预警事件不再被重新触发处置流程

- **AC-002-04（忽略已恢复事件）**
  - Given：某条 `fault_event` 记录在被取用前已变为 `is_active=False`
  - When：服务准备处理该记录
  - Then：服务跳过该记录，不触发决策循环，记录 INFO 日志

---

### REQ-FUNC-003：自主决策闭环（分析→取数→处置/工单）

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-003 |
| 描述 | 系统应当对每条触发事件执行完整的四步决策链：（1）调 `delegate_knowledge` 向三恒知识专家请求成因分析；（2）调 `delegate_read` 向能耗专家读取该房间实时参数和历史数据；（3）判断是否可处置；（4）可处置则提案写操作（经授权策略），不可处置则创建工单。 |
| 来源引用 | "收到预警事件 → 调 delegate_knowledge → 调 delegate_read → 判断：可处置 → 提案 delegate_write；不可处置 → 创建工单" — 设计稿 §4.2 |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-003-01（知识分析委托被调用）**
  - Given：服务接收到一条活跃的结露预警事件（`condensation_warning_event`），`specific_part="3-1-7-702"`
  - When：决策循环启动
  - Then：在决策链中有且仅有一次 `delegate_knowledge` 调用，入参包含该预警的描述信息，返回三恒成因分析结果后流程继续

- **AC-003-02（只读取数委托被调用）**
  - Given：`delegate_knowledge` 返回分析结果后
  - When：决策链继续执行
  - Then：在决策链中有且仅有一次 `delegate_read` 调用，入参包含 `specific_part` 以及取数需求，返回该房间的实时参数和/或历史数据

- **AC-003-03（可处置路径：生成处置提案）**
  - Given：`delegate_read` 返回数据后，LLM 判断该预警可通过参数调整处置
  - When：决策链继续执行
  - Then：服务生成处置提案，进入 REQ-FUNC-005 定义的写授权流程，不直接跳过授权

- **AC-003-04（不可处置路径：创建工单）**
  - Given：`delegate_read` 返回数据后，LLM 判断该预警超出可自动处置范围
  - When：决策链继续执行
  - Then：服务调用工单创建逻辑（REQ-FUNC-006），生成一条新的 `WorkOrder` 记录，不尝试写设备参数

- **AC-003-05（委托步数上限保护）**
  - Given：决策链在单条预警的处理中正在执行
  - When：委托工具调用次数达到系统配置的步数上限（参考现有 `MAX_EXPERT_STEPS=8`）
  - Then：流程安全退出，记录 WARNING 日志，创建工单（兜底路径，不丢失预警）

- **AC-003-06（被委托专家报错降级）**
  - Given：`delegate_knowledge` 或 `delegate_read` 调用中目标专家抛出异常或超时
  - When：委托调用失败
  - Then：错误信息回灌给发起方（inspection-expert），不杜撰结果，不崩溃；决策链据错误信息选择创建工单或重试（具体由 LLM 依提示词约束决定）

---

### REQ-FUNC-004：进程内复用生产 langgraph_chat 专家与委托机制

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-004 |
| 描述 | 系统应当在 `freeark-inspection-agent` 进程内直接导入并复用 `FreeArkWeb/backend/freearkweb/api/langgraph_chat/` 中已有的 experts（energy-expert / sanheng-knowledge / inspection-expert）及委托工具（delegate_knowledge / delegate_read / delegate_write），不重复实现专家逻辑。 |
| 来源引用 | "进程内复用现有 `api/langgraph_chat/` 的 experts 和委托机制" — 设计稿 §4.2 |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-004-01（复用生产专家模块）**
  - Given：`freeark-inspection-agent` 服务启动
  - When：服务初始化
  - Then：服务使用 `api.langgraph_chat` 包内的 `TOOLS_BY_EXPERT`、`EXPERT_PROMPTS` 等同一套配置，不存在独立维护的专家副本

- **AC-004-02（inspection-expert 委托工具可用）**
  - Given：服务运行中
  - When：决策链中 inspection-expert 执行推理
  - Then：inspection-expert 具备 `delegate_knowledge` / `delegate_read` / `delegate_write` 三个委托工具（与方案 A chat 链路一致）

- **AC-004-03（非委托专家不暴露委托工具）**
  - Given：决策链中 energy-expert 或 sanheng-knowledge 被委托执行
  - When：被委托专家执行（深度限 1）
  - Then：被委托专家不拥有委托工具，不可发起二次委托（杜绝递归）

---

### REQ-FUNC-005：自治写授权模型

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-005 |
| 描述 | 系统应当在无人值守场景下实施明确的写操作授权策略，确保设备参数写入（`set_device_params` / `trigger_refresh`）不在未授权条件下自动执行。授权策略须在架构阶段由用户拍板（见 OD-01），需求层定义两种候选策略的边界。 |
| 来源引用 | "写确认在无人值守下的难题（B 的核心开放问题）…候选策略 A/B" — 设计稿 §4.2 |
| 优先级 | Must Have |
| 备注 | **AUTO_WRITE_POLICY = TBD，见开放决策 OD-01，须在架构阶段由用户拍板，不得在未拍板前进入编码** |

**候选策略定义（供架构师与用户决策，二选一）：**

**策略 A — 安全区间白名单自动执行：**
- 写操作参数在预定义的安全区间内（例如：温度设定值在当前值 ±N°C 以内、或在绝对值范围 M₁–M₂°C 以内），系统自动执行写操作，**无需人工确认**。
- 具体安全区间参数（±N 值、绝对边界值）由用户在架构阶段定义，并以配置方式管理，不硬编码。
- 越界或高风险操作（参数超出白名单范围、非温度类写操作等）：**不自动执行**，转为创建工单，等待人工处置。
- 每次自动执行的写操作须写入审计日志（REQ-FUNC-009）。

**策略 B — 全部转工单，无自动写：**
- 所有写操作提案均**不自动执行**，一律创建工单（REQ-FUNC-006），等待运维人员通过 chat 链路（方案 A）手动确认后执行。
- 无白名单配置，无自动写入，零自动执行风险。
- 所有提案须写入审计日志（REQ-FUNC-009）。

**验收标准（策略 A）：**

- **AC-005-A-01（白名单内自动执行）**
  - Given：`AUTO_WRITE_POLICY=A`，决策链提案将某房间温度设定值从 26°C 调整为 25°C（变化量 1°C，在安全区间内）
  - When：授权检查执行
  - Then：写操作自动执行，结果写入审计日志，不打断人工处理

- **AC-005-A-02（越界转工单）**
  - Given：`AUTO_WRITE_POLICY=A`，决策链提案将某参数调整量超出白名单范围
  - When：授权检查执行
  - Then：写操作不执行，自动转为创建工单，工单 `recommended_action` 字段记录提案内容，写入审计日志

**验收标准（策略 B）：**

- **AC-005-B-01（所有写提案转工单）**
  - Given：`AUTO_WRITE_POLICY=B`，决策链生成任意写操作提案
  - When：授权检查执行
  - Then：写操作不执行，创建工单，工单记录提案内容，写入审计日志

- **AC-005-B-02（无自动执行路径）**
  - Given：`AUTO_WRITE_POLICY=B`，任意预警事件
  - When：决策链完成
  - Then：`fault_event` / `condensation_warning_event` 对应记录的 DB 中无任何由本服务直接发起的设备参数变更，设备参数仅可通过 chat 链路（方案 A 的 `_gate` 确认门）由人工确认后写入

---

### REQ-FUNC-006：工单创建（WorkOrder 模型）

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-006 |
| 描述 | 系统应当新增 `WorkOrder` Django 模型，在决策链判断"不可处置"或"写操作超出授权范围"时创建工单记录，持久化到生产 DB。 |
| 来源引用 | "工单 sink（当前不存在，需新建）：建模 WorkOrder（ticket_id/severity/affected_device/symptom/diagnosis/recommended_action/status）" — 设计稿 §4.2 |
| 优先级 | Should Have（P1） |
| 备注 | |

**WorkOrder 模型最小字段集（需求层，具体字段类型由架构师确认）：**

| 字段 | 语义 |
|------|------|
| `id` | 主键（BigAutoField） |
| `ticket_id` | 人可读工单编号，格式待定（如 WO-20260615-001） |
| `severity` | 严重级别（引自触发事件的 `severity` 或 `warning_type`） |
| `source_event_type` | 触发来源类型：`fault_event` / `condensation_warning_event` |
| `source_event_id` | 触发事件的 DB 主键（关联 FaultEvent 或 CondensationWarningEvent） |
| `affected_device` | 受影响设备标识（`device_sn` + `specific_part`） |
| `symptom` | 症状描述（来自触发事件的 `fault_message` / `warning_message`） |
| `diagnosis` | LLM 分析结论（来自 `delegate_knowledge` 返回摘要） |
| `recommended_action` | 建议处置措施（来自决策链，策略 A/B 下的未执行写提案） |
| `status` | 工单状态：`OPEN` / `IN_PROGRESS` / `RESOLVED` / `CANCELLED` |
| `created_at` | 创建时间（auto_now_add） |
| `updated_at` | 最后更新时间（auto_now） |
| `resolved_at` | 解决时间（可为 NULL） |
| `resolved_by` | 解决人（可为 NULL，人工处置时填写） |

**验收标准：**

- **AC-006-01（不可处置时创建工单）**
  - Given：决策链执行完毕，LLM 判断预警超出自动处置范围
  - When：创建工单逻辑执行
  - Then：`work_order` 表新增一条记录，`status=OPEN`，`source_event_id` 指向触发事件，`symptom`/`diagnosis`/`recommended_action` 均已填充（不为空）

- **AC-006-02（写提案越界时创建工单，策略 A）**
  - Given：`AUTO_WRITE_POLICY=A`，写提案超出安全区间
  - When：授权检查拦截后转工单
  - Then：`work_order` 表新增记录，`recommended_action` 包含被拦截的写提案内容，`status=OPEN`

- **AC-006-03（同一事件不重复建单）**
  - Given：某 `fault_event` 记录已有关联 `WorkOrder`（`status` 非 `CANCELLED`）
  - When：服务因重启再次识别到该事件
  - Then：不创建重复工单；已有工单保持不变

- **AC-006-04（工单持久化到生产 DB）**
  - Given：`AUTO_WRITE_POLICY=A` 或 `B`，工单创建成功
  - When：服务重启后
  - Then：工单记录仍在 `work_order` 表中，`status` 不丢失

---

### REQ-FUNC-007：处置状态持久化

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-007 |
| 描述 | 系统应当持久化每条预警事件的决策处置进度（待处置 / 处理中 / 已完成 / 已跳过），确保服务重启后不重复处置或漏处置。 |
| 来源引用 | "记录本条预警的处置状态" / "自治需要持久化每条预警的处置进度，防重启重复处置或漏处置" — 设计稿 §4.2 |
| 优先级 | Must Have |
| 备注 | 持久化方案（DB checkpointer / 自建状态字段）为架构开放决策 OD-03，留给架构师定夺 |

**验收标准：**

- **AC-007-01（正常完成后状态持久化）**
  - Given：服务对某条 `fault_event`（`id=N`）完成了完整决策循环（无论最终是写操作还是创建工单）
  - When：服务重启
  - Then：重启后服务不再将该 `fault_event(id=N)` 识别为"待处置"，不重新触发决策循环

- **AC-007-02（中途崩溃后重启可识别未完成状态）**
  - Given：服务在处理某条预警事件决策循环中途崩溃（如 LLM 调用超时导致进程崩溃）
  - When：服务重启后
  - Then：服务能识别该预警事件处于"处理中"或"待处置"状态，可重新触发决策循环（不丢单）

- **AC-007-03（MemorySaver 不满足持久化要求）**
  - Given：服务正在运行，处置状态存储于进程内存（MemorySaver）
  - When：服务进程被终止
  - Then：内存状态丢失，此时必须从持久化存储（DB）重建状态；验收条件：重建后所有"处理中"或"待处置"状态可被正确识别

---

### REQ-FUNC-008：审计日志

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-008 |
| 描述 | 系统应当对每次自治写操作提案的授权判断结果（执行或拒绝）、每次工单创建动作，以及每次委托调用的关键结果，以结构化格式写入可查的审计日志，支持事后追溯。 |
| 来源引用 | "参数在安全区间白名单…自动执行 + 审计日志" / "全部不自动写，所有写操作转工单" — 设计稿 §4.2 |
| 优先级 | Should Have（P1） |
| 备注 | |

**审计日志最小必须字段：**

| 字段 | 内容 |
|------|------|
| `timestamp` | ISO8601 时间戳 |
| `event_type` | 事件类型：`WRITE_EXECUTED` / `WRITE_BLOCKED_WHITELIST` / `WRITE_BLOCKED_POLICY_B` / `WORKORDER_CREATED` / `DELEGATION_CALLED` / `DELEGATION_ERROR` |
| `source_event_id` | 触发预警事件的 DB ID |
| `source_event_type` | `fault_event` / `condensation_warning_event` |
| `specific_part` | 涉及房间 |
| `action_detail` | 操作详情（写参数名+新值，或工单 ID，或委托目标专家） |
| `result` | `SUCCESS` / `BLOCKED` / `ERROR` |

**验收标准：**

- **AC-008-01（写操作执行审计，策略 A）**
  - Given：`AUTO_WRITE_POLICY=A`，白名单内写操作成功执行
  - When：操作完成
  - Then：审计日志中出现 `event_type=WRITE_EXECUTED`，含 `specific_part`、`action_detail`（含具体参数名和新值）、`result=SUCCESS`，时间戳精确到秒

- **AC-008-02（写操作拦截审计）**
  - Given：写操作被拦截（策略 A 越界，或策略 B 全拦截）
  - When：拦截发生
  - Then：审计日志中出现对应 `event_type`（`WRITE_BLOCKED_*`），含 `specific_part`、`action_detail`、`result=BLOCKED`

- **AC-008-03（工单创建审计）**
  - Given：工单创建成功
  - When：创建完成
  - Then：审计日志中出现 `event_type=WORKORDER_CREATED`，含 `source_event_id`、`result=SUCCESS`

- **AC-008-04（审计日志通过 journalctl 可查）**
  - Given：审计日志通过 Python logging 写入 journald
  - When：任意时刻
  - Then：`journalctl -u freeark-inspection-agent` 可检索到对应审计条目

---

### REQ-FUNC-009：工单通知（P2，取决于用户决策）

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-009 |
| 描述 | 系统应当在工单创建后向运维人员发送通知（通知渠道待定），以便人工及时介入处置。 |
| 来源引用 | "先落库+通知（范围待定）" — 设计稿 §4.2 |
| 优先级 | Could Have（P2） |
| 备注 | ✅ 已拍板（2026-06-15，用户）：**本期不做通知**，仅落库；通知渠道（钉钉/短信/邮件）移入演进路线 EV-01。本需求降级为本版本范围外。 |

**验收标准：**

- **AC-009-01（工单通知发送）**
  - Given：新工单创建成功，通知渠道已配置
  - When：工单落库完成
  - Then：系统通过已配置渠道向至少一个运维人员发送通知，通知内含工单 ID、严重级别、受影响房间

---

### REQ-FUNC-010：工单列表 UI（P2）

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-010 |
| 描述 | 系统应当在 Web 管理界面新增工单列表页面，支持查看和处置工单。 |
| 来源引用 | "列表/处置 UI，或先落库+通知" — 设计稿 §4.2 |
| 优先级 | Could Have（P2） |
| 备注 | ✅ 已拍板（2026-06-15，用户）：**本期不做自建前端 UI**，工单仅落库 + 通过 Django Admin（或 chat）查看；自建工单列表/处置页移入演进路线 EV-02。 |

**验收标准：**

- **AC-010-01（工单列表可访问）**
  - Given：用户已登录 Web 管理界面
  - When：用户访问工单列表页面
  - Then：页面展示 `work_order` 表中的工单，包含工单 ID、严重级别、受影响设备、状态、创建时间，支持分页

---

## 4. 非功能需求

### REQ-NFUNC-001：性能（树莓派单核环境）

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-001 |
| 描述 | 系统在树莓派 Pi（单核/低 RAM 环境）下运行时，单条预警事件的完整决策循环（含 LLM 调用）不应导致其他 systemd 服务（`freeark-backend`、`freeark-fault-consumer` 等）出现可感知的性能退化。 |
| 来源引用 | 基础设施约束：树莓派 Pi 部署，禁 Docker |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-NFR-001-01（不阻塞其他服务）**
  - Given：`freeark-inspection-agent` 正在处理一条预警事件的决策循环（含 LLM 调用，约 8–35s）
  - When：同时有用户通过 chat 发起请求
  - Then：`freeark-backend` 的 chat 接口响应时间不因 `freeark-inspection-agent` 运行而显著增加（差值 < 10%）

- **AC-NFR-001-02（串行处理，不并发爆炸）**
  - Given：`fault_event` 表中同时存在 5 条新增活跃未处置记录
  - When：服务识别到这 5 条记录
  - Then：服务按顺序或有限并发（并发上限由架构师定）处理，不同时发起 5 次独立 LLM 调用，防止 OOM 或网络请求爆炸

---

### REQ-NFUNC-002：可靠性（重启后状态重建）

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-002 |
| 描述 | 系统在进程重启后，能从持久化存储中重建所有未完成的预警处置状态，做到零漏单（不漏处置）和零重单（不重复处置）。 |
| 来源引用 | "防重启重复处置或漏处置" — 设计稿 §4.2 |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-NFR-002-01（重启零漏单）**
  - Given：服务在处理 3 条预警事件中途被 `systemctl restart` 重启
  - When：服务重启完成
  - Then：3 条事件中"待处置"状态的均被重新识别并触发决策循环；"已完成"状态的不再触发

- **AC-NFR-002-02（重启零重单）**
  - Given：服务已对某条预警事件完成处置（工单或写操作），进程后续重启
  - When：服务重启完成
  - Then：该条预警事件不再被视为"待处置"，不产生重复工单

---

### REQ-NFUNC-003：安全（写授权与最小权限）

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-003 |
| 描述 | 自治写操作须经 REQ-FUNC-005 定义的授权策略批准，未经批准的写操作不得执行；服务使用的 LLM API Key 及 DB 凭证存储在 `.env` 文件中，不得硬编码入代码或 git 仓库。 |
| 来源引用 | "写确认在无人值守下的难题" / "密钥在 .env，绝不入 git" — 设计稿 §4.2 + 基础设施约束 |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-NFR-003-01（凭证不入 git）**
  - Given：`git log` 或 `git diff` 中查看所有与本版本相关的 commit
  - When：任意时刻
  - Then：代码库中不含 DEEPSEEK_API_KEY、DB 密码等敏感值的明文，`.env` 文件已列入 `.gitignore`

- **AC-NFR-003-02（无绕过授权的写路径）**
  - Given：任意预警事件触发决策循环
  - When：决策链判断需要写操作
  - Then：写操作必须经过 REQ-FUNC-005 的授权检查，不存在跳过检查直接调用 `set_device_params` 或 `trigger_refresh` 的代码路径

---

### REQ-NFUNC-004：可观测性（日志）

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-004 |
| 描述 | 服务须通过 Python logging 写入 journald，支持通过 `journalctl -u freeark-inspection-agent` 查询；日志须覆盖：服务启动/停止、事件识别、委托调用进出、授权判断、工单创建、错误。 |
| 来源引用 | 基础设施约束：所有服务以 systemd 管理；参考同类服务日志规范（v0.6.0-FM §4.5） |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-NFR-004-01（关键动作可查）**
  - Given：服务运行中，处理一条预警事件
  - When：决策链完成（含委托调用、授权判断、工单创建）
  - Then：`journalctl -u freeark-inspection-agent` 中可检索到该条预警事件的：识别（INFO）、每步委托调用（INFO）、授权判断结果（INFO 或 WARNING）、最终处置结果（INFO）

- **AC-NFR-004-02（错误不静默）**
  - Given：委托调用失败（LLM 超时或异常）
  - When：异常发生
  - Then：日志中出现 ERROR 级别条目，包含错误类型、预警事件 ID、失败的委托目标，不静默忽略

- **AC-NFR-004-03（日志中不含敏感凭证）**
  - Given：服务正常运行，日志通过 journald 可查
  - When：任意时刻
  - Then：日志中不含 API Key、DB 密码等敏感字符串

---

## 5. 约束（基础设施）

### REQ-CON-001：禁止 Docker，物理机 systemd 部署

| 字段 | 内容 |
|------|------|
| ID | REQ-CON-001 |
| 描述 | 系统必须以 systemd service 方式部署，禁止使用 Docker 或容器化方案。 |
| 来源引用 | 基础设施约束：物理机部署，禁 Docker，树莓派 Pi |
| 优先级 | Must Have |
| 备注 | |

---

### REQ-CON-002：生产 DB MySQL，测试用 SQLite

| 字段 | 内容 |
|------|------|
| ID | REQ-CON-002 |
| 描述 | 生产环境使用 MySQL（192.168.31.98:3306）；本地开发和 CI 测试使用 SQLite（`--settings=freearkweb.test_settings`），不依赖生产 DB。 |
| 来源引用 | 基础设施约束 |
| 优先级 | Must Have |
| 备注 | |

---

### REQ-CON-003：部署一律通过 git pull，禁止 pscp

| 字段 | 内容 |
|------|------|
| ID | REQ-CON-003 |
| 描述 | 生产部署步骤必须为：① plink SSH 连接；② git pull；③ migrate；④ systemctl reload/restart，禁止 pscp 逐文件上传。 |
| 来源引用 | 基础设施约束：部署一律 git pull，禁止 pscp 逐文件上传 |
| 优先级 | Must Have |
| 备注 | |

**验收标准：**

- **AC-CON-003-01（git pull 部署验证）**
  - Given：代码已合并到 main 分支
  - When：需要在生产服务器（192.168.31.51）部署
  - Then：部署人员通过 plink 执行 `git pull` + `python manage.py migrate` + `sudo systemctl daemon-reload && sudo systemctl restart freeark-inspection-agent`，不使用 pscp 或 scp 传输文件

---

### REQ-CON-004：两套 LangGraph 代码库不混淆

| 字段 | 内容 |
|------|------|
| ID | REQ-CON-004 |
| 描述 | PoC 代码在 `agents/langgraph-poc/`，生产代码在 `FreeArkWeb/backend/freearkweb/api/langgraph_chat/`。方案 B 落在生产侧，不修改 PoC 代码，不将 PoC 代码路径用于生产运行。 |
| 来源引用 | 基础设施约束：两套 langgraph 代码 |
| 优先级 | Must Have |
| 备注 | |

---

### REQ-CON-005：密钥管理

| 字段 | 内容 |
|------|------|
| ID | REQ-CON-005 |
| 描述 | LLM API Key（DEEPSEEK_API_KEY 等）及 DB 凭证必须通过 `.env` 注入，不得硬编码在代码或配置文件中，`.env` 须列入 `.gitignore`。 |
| 来源引用 | 基础设施约束：密钥在 .env，绝不入 git |
| 优先级 | Must Have |
| 备注 | |

---

## 6. 依赖与假设

### 6.1 依赖

| 依赖项 | 类型 | 说明 |
|--------|------|------|
| 方案 A（PR #19，已上线） | 功能依赖 | `api/langgraph_chat/` 中的 `delegate_knowledge` / `delegate_read` / `delegate_write` 委托工具及 experts 必须已在生产部署，方案 B 复用这套机制 |
| `fault_event` 表（v0.6.0-FM） | DB 依赖 | 事件源之一，由 `freeark-fault-consumer` 维护，已在生产 |
| `condensation_warning_event` 表（v0.7.0-CW） | DB 依赖 | 事件源之一，由 `freeark-condensation-consumer` 维护，已在生产 |
| `freeark-fault-consumer` systemd 服务 | 运行依赖 | 提供 `fault_event` 数据，需先于 `freeark-inspection-agent` 运行 |
| `freeark-condensation-consumer` systemd 服务 | 运行依赖 | 提供 `condensation_warning_event` 数据，需先于 `freeark-inspection-agent` 运行 |
| DeepSeek LLM API（OpenClaw via WS gateway） | 外部服务依赖 | 决策循环依赖 LLM；网络中断时需降级处理（见风险 R-03） |
| MySQL 9.4 @ 192.168.31.98 | 生产 DB | `WorkOrder` 表及处置状态存储 |

### 6.2 假设

| 编号 | 假设内容 |
|------|---------|
| A-01 | 方案 A 委托工具（`delegate_knowledge` / `delegate_read` / `delegate_write`）在生产已稳定运行，方案 B 可直接复用，不需要重新测试委托机制本身 |
| A-02 | `inspection-expert` 的 SYSTEM_PROMPT（`.langgraph.md`）已包含足够的委托契约约束，无需为自治场景单独修改提示词（若需修改，则需重新评估范围） |
| A-03 | 树莓派生产环境可承载再增加一个 `freeark-inspection-agent` 常驻进程（参考 A-06 于 v0.6.0-FM，已有两个 consumer 服务共存） |
| A-04 | `fault_event` 和 `condensation_warning_event` 两张表中现有字段（`is_active`、`specific_part`、`device_sn` 等）足以支撑事件识别和决策链上下文构建，无需修改已有模型 |

---

## 7. 风险

| 风险编号 | 描述 | 概率 | 影响 | 缓解措施 |
|----------|------|------|------|---------|
| R-01 | 自治写策略（OD-01）未拍板导致开发阻塞：在 AUTO_WRITE_POLICY 确定之前，REQ-FUNC-005 无法编码 | 高 | 高 | 明确 OD-01 为 P0 开放决策，架构启动前必须先拍板；拍板前可先实现策略 B（全转工单，零风险）作为临时实现 |
| R-02 | LLM 调用超时（单次 LLM 调用约 8–35s）导致决策循环阻塞或积压 | 中 | 中 | 设置 LLM 调用超时（复用现有 `LANGGRAPH_LLM_TIMEOUT`）；超时时走工单兜底路径；串行处理防积压 |
| R-03 | 网络中断（WiFi 省电/wlan0 劣化）导致 LLM API 调用失败（已有 RCA：`project_prod_internet_loss_wifi_rca`） | 中 | 中 | LLM 调用失败时创建工单（兜底）；记录 ERROR 日志；服务不因网络中断崩溃（重试后继续） |
| R-04 | 错误决策导致设备参数被错误调整（仅策略 A 风险） | 低 | 高 | 策略 A 安全区间白名单 + 审计日志；越界即转工单；架构阶段必须精确定义白名单参数范围和边界值 |
| R-05 | 处置状态持久化方案（OD-03）复杂度超预期（DB checkpointer 需与 LangGraph 深度集成） | 中 | 中 | 允许降级方案：自建状态字段（在 `WorkOrder` 或独立状态表中记录处置状态），不强制使用 LangGraph DB checkpointer |
| R-06 | 两套代码库（PoC vs 生产）在方案 B 实现中混淆，误用 PoC 路径 | 低 | 中 | REQ-CON-004 明确约束；代码审查时检查 import 路径是否指向生产侧 |
| R-07 | `freeark-fault-consumer` 与 `freeark-inspection-agent` 同时读写 DB 时出现竞争（如 consumer 刚写入 T1，inspector 立即读取） | 低 | 低 | 事件接入方式由架构师定夺（OD-02）；DB 层面有 `is_active` / `unique constraint` 兜底 |

---

## 8. 头号开放决策（交接架构师输入）

以下三条开放决策**必须在架构阶段由用户拍板，不得在未拍板前进入编码**：

---

### OD-01（P0，必拍板）：AUTO_WRITE_POLICY — 自治写授权策略

**决策问题**：在无人值守的自治场景下，系统对 `set_device_params` / `trigger_refresh` 等写操作采用哪种授权模式？

| 策略 | 行为 | 优点 | 风险 |
|------|------|------|------|
| 策略 A：安全区间白名单自动执行 | 参数变化量在白名单范围内自动执行，越界转工单 | 响应更快，减少人工介入 | 需精确定义白名单参数和边界值；LLM 误判仍可能在白名单内触发错误调整 |
| 策略 B：全部转工单（推荐初期） | 所有写提案均不自动执行，一律转工单 | 零自动执行风险，适合初期验证 | 响应慢（需人工跟进），不实现"自治处置"价值 |

**当前状态**：✅ 已拍板（2026-06-15，用户）= **策略 B（全部转工单，`AUTO_WRITE_POLICY=B`，零自动写）**。代码须留 `WriteAuthPolicy` 接缝；后续凭审计日志判断 LLM 提案准确率，仅改 `.env` 即可升级至策略 A，无需改代码。
**建议**：初期采用策略 B 验证决策链正确性，待积累足够信心后升级至策略 A

---

### OD-02（P0，架构定夺）：事件接入方式

**决策问题**：`freeark-inspection-agent` 如何感知 `fault_event` / `condensation_warning_event` 中的新事件？

| 方式 | 机制 | 优点 | 缺点 |
|------|------|------|------|
| 方式 1：DB 轮询 | 定时查询 `WHERE is_active=True AND processed=False` | 实现简单，无额外依赖 | 轮询间隔内有延迟；树莓派 MySQL 额外定期查询压力 |
| 方式 2：信号驱动 | consumer 落库后发信号（如数据库信号 / Django post_save / 内部 IPC） | 实时响应，无轮询延迟 | 需改动 consumer 侧发出信号（与 OOS-03 冲突，需权衡）；跨进程通信增加复杂度 |

**当前状态**：✅ 已裁定（2026-06-15，架构师）= **方式 1 DB 轮询**（新增 `inspection_status` 字段 + 30s 轮询）。因 consumer 禁改（OOS-03）+ 禁新中间件（OOS-06）排除信号驱动；30s 延迟对楼宇场景可接受。
**约束**：禁止引入 Redis 等新中间件（REQ-CON-006 隐含，基础设施约束）

---

### OD-03（P1，架构定夺）：处置状态持久化方案

**决策问题**：如何持久化每条预警事件的决策处置进度？

| 方案 | 机制 | 优点 | 缺点 |
|------|------|------|------|
| 方案 X：LangGraph DB Checkpointer | 使用 LangGraph 官方 DB checkpointer（如 PostgreSQL 或 SQLite 版本） | 与 LangGraph 图状态原生集成，重启可断点续传 | 需引入新依赖；与 Django MySQL 的兼容性需验证 |
| 方案 Y：自建处置状态字段 | 在 `WorkOrder` 表或新建状态表中记录 `(source_event_id, status, started_at)` | 实现简单，完全复用现有 ORM | 与 LangGraph 图状态解耦，需手动维护状态一致性 |

**当前状态**：✅ 已裁定（2026-06-15，架构师）= **方案 Y 自建状态字段**（`inspection_status`，不引入 LangGraph DB Checkpointer）。理由：MySQL 9.4 兼容性未验证；有界幂等 ReAct（8 步）无需步骤级断点续传；零新依赖。

---

## 9. 演进路线（超出本版本范围的候选项）

| 编号 | 标题 | 说明 |
|------|------|------|
| EV-01 | 告警通知集成（钉钉/短信/邮件） | 工单创建后实时推送；本期超出范围 |
| EV-02 | 工单处置 Web UI | 运维人员通过前端页面查看并处置工单；本期 P2 |
| EV-03 | 自动化巡检排班（定时主动巡检） | 非预警触发，按时间维度主动扫描设备状态 |
| EV-04 | 策略 A 白名单参数的可视化配置 UI | 运维人员通过界面调整安全区间，无需重启服务 |
| EV-05 | 多事件并发处理（事件队列） | 当前要求串行/有限并发；未来可引入事件队列提升吞吐 |
