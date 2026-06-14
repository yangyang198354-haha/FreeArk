# 阶段 G 设计 —— 跨 Agent 子委托 与 自治巡检 Agent

> 状态：**设计稿（不含生产代码改动）**。供 review 后拍板走 A 还是 B。
> 前置：阶段 A–F 已把 OpenClaw 编排替换为生产 `api/langgraph_chat/`（见 `PHASE3_ROLLOUT.md`）。
> PoC 已实现并离线验证子委托机制（`agents/langgraph-poc/orchestrator.py` + `test_delegation.py` 4/4 绿）。
> 配套记忆：`project_langgraph_two_codebases`、`project_freeark_systemd_services`。

---

## 0. 一句话

原始需求#3 的"巡检 agent 收到预警→分析(三恒)→取数(能耗)→处置(能耗写)→否则开工单"
是一条**专家自主子委托链**。生产 chat 编排器目前只能做**用户复合提问的并行 fan-out**，
不能做专家自主子委托。本文给出把子委托落地的两条路径（A 在 chat 内、B 独立自治子系统），
并明确：**被委托的写必须复用现有 `_gate` interrupt 门，不另起确认路径**。

---

## 1. 背景：两种"委托"，别混

| | 用户复合提问 | 专家自主子委托 |
|---|---|---|
| 例 | "看能耗+看故障+讲原理" | 巡检收到预警，自己决定调三恒解释、调能耗取数、提案写处置 |
| 触发 | 用户一句话 | 专家在推理中途自行决定 |
| 生产现状 | ✅ router 并行 fan-out + aggregate 已覆盖 | ❌ 无 |
| 对应 | 现有 chat | **原始需求#3 自治巡检 agent** |

结论：**不需要**为"用户复合提问"做子委托——fan-out 已够。子委托只为"专家自主决策"存在。

---

## 2. 生产现状（可复用的接缝，已核实 2026-06-15）

文件：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/`

- **图**：`orchestrator.py` `route → fan_out(Send 并行) → expert → gate → aggregate`，
  `compile(checkpointer=MemorySaver())`。
- **专家节点** `_expert`（orchestrator.py:182）：单轮 ReAct——**读工具内联执行**；
  **写工具不执行**，拆成 `{"pending_write":{tool,args}}` 返回，交 `_gate`。
- **写确认门** `_gate`（orchestrator.py:212）：有 pending_write 则 `interrupt({kind:"confirm_required",actions})`
  暂停；resume 带 `{approved}`；批准走 `execute_write(tool,args,operator)`（注入 `openclaw-agent::<user>` 追溯）。
  → **pm 评审的 P0-2（Tier-2 interrupt 门）已完成**，不用再做。
- **前端确认链路**：`adapter.py` `_drive`（adapter.py:97）捕获 `__interrupt__` → yield `('confirm', json)` →
  前端弹确认 → `resume_chat(session_key,{approved})` 同线程恢复。
- **路由**：`router.classify_experts`（LLM 分类→关键词→DEFAULT + 误路由护栏）。
- **提示装载**：`prompts.py` 读 `SYSTEM_PROMPT.langgraph.md`(优先)→`SYSTEM_PROMPT.md`(兜底)。
  → 我们对 inspection-expert 两版提示词加的**委托契约已被生产装载**（只是没机制执行）。
- **写工具集**：`fa_tools.WRITE_TOOL_NAMES = {set_device_params, trigger_refresh}`（高危 service/sync 按设计排除）；
  `TOOLS_BY_EXPERT`：energy=读+写、inspection=只读、sanheng=无工具。

---

## 3. 方案 A —— 子委托落进生产 chat 编排器

### 3.1 目标
inspection-expert 在**一个 chat 轮次内**可自主：调 sanheng 分析、调 energy 取数、提案 energy 写
（写经现有 `_gate` 确认）。仍是"用户问→答"的同步链，不引入事件驱动。

### 3.2 机制（沿用 PoC 已验证设计，按生产 _gate 适配）
给 inspection 绑定 3 个**委托工具**（schema 同 PoC）：`delegate_knowledge` / `delegate_read` / `delegate_write`。
`_expert` 改造为有界 ReAct 循环（PoC 已做，移植即可），按工具名分流：

- **delegate_knowledge / delegate_read（只读、无副作用）→ 内联同步**：
  orchestrator 直接跑目标专家（深度限 1：被委托方**不带**委托工具，杜绝递归；read-only），
  结果作为 ToolMessage 回灌 inspection，继续推理。等价 PoC `_handle_delegation`。

- **delegate_write（有副作用）→ 延迟到 `_gate`，不内联**：
  inspection 节点**不等写结果**（不能内联——写要用户确认=图暂停），而是产出一条
  `{"pending_write":{tool,args}}`（与 energy 写路径**同形**）随节点返回 → 流到 `_gate` →
  复用现有 interrupt 确认 → 批准后 `execute_write` 注入 operator 执行。
  **关键收益**：一套确认 UX、一套审计、一条 resume 链路，零重复。

> 设计要点：**读委托同步内联，写委托异步走门**。这不是妥协，是更安全——自主发现绝不
> 自动升格为已授权写（呼应提示词里"禁止链式自动触发写""requires_user_confirmation"）。

### 3.3 触发：inspection 何时该委托？
- 进程内 LLM 路径不输出 JSON 路由标记（`.langgraph.md` 契约），由模型**直接发起委托工具调用**
  （function call），与普通工具调用同构——这正是 PoC fake_llm 验证的链路。
- `.langgraph.md` 已写明三条委托方向 + 写需确认；模型据此在需要时 call 对应 delegate_* 工具。

### 3.4 改动面（仅生产编排层，逐项可回滚）
1. `langgraph_chat/orchestrator.py`：移植 PoC 的委托工具定义 + `_expert` 有界循环 +
   `_handle_delegation`（读内联）；delegate_write 改为产出 `pending_write` 而非走 confirm 回调。
2. `delegating_experts = {"inspection-expert"}`（只给巡检，energy/sanheng 不暴露委托工具）。
3. `adapter._drive`：委托过程中的进度（"正在请求三恒分析…/正在取数…"）下发 `('status',…)`，
   避免子委托静默期；写委托仍走既有 `('confirm',…)`。
4. 测试：把 `test_delegation.py` 等价用例搬成 Django 单测（`LANGGRAPH_USE_FAKE_LLM=True`），
   覆盖：读委托回灌、写委托→interrupt→approve/deny、深度限 1、非委托专家不暴露工具。

### 3.5 边界
- 仍是 chat 同步轮次，**无状态持久化、无事件触发、无工单**——不满足原始需求#3 的"自治/有状态/工单"。
- 是 B 的**前置积木**：B 的决策循环复用同一套委托机制。

---

## 4. 方案 B —— 自治巡检 Agent（独立事件驱动子系统）

### 4.1 目标（= 原始需求#3 全貌）
非 chat。事件触发、有状态、自主跑完"分析→取数→处置/升级"闭环，处理不了开工单。

### 4.2 组成
- **事件源**：`freeark-fault-consumer` 写入新故障/预警即触发（该服务是故障事件入口，见
  `project_freeark_systemd_services`）。接法二选一：DB 轮询新故障行 / consumer 落库后发信号。
- **运行体**：独立 systemd 服务（如 `freeark-inspection-agent`），进程内复用
  `langgraph_chat` 的 experts + 委托机制（方案 A 的子委托）跑决策图。
- **决策循环**（复用 inspection-expert 提示词的 delegations 契约）：
  预警 → delegate_knowledge(三恒成因) → delegate_read(该户参数/历史) →
  {可处置 → delegate_write；不可处置 → 开工单} → 记状态。
- **写确认在无人值守下的难题**（B 的核心开放问题，A 不涉及）：
  chat 的 interrupt 门要真人点确认；自治模式没有交互用户。需定策略，候选：
  - 策略白名单：参数在安全区间内（如温度设定 ±范围）自动执行 + 审计；
  - 越界/高风险：**不自动写**，转工单等人工。
- **工单 sink**（当前不存在，需新建）：建模 `WorkOrder`（ticket_id/severity/affected_device/
  symptom/diagnosis/recommended_action/status）+ 列表/处置 UI，或先落库 + 通知。
  呼应 pm 报告 P2-6（提示词侧 work_order 模板尚未补，可一并做）。
- **状态持久化**：MemorySaver 仅进程内（重启即丢）；自治需 DB checkpointer 或自建状态表，
  记每条预警的处置进度，避免重启重复处置/漏处置。

### 4.3 改动面（大）
新 systemd 服务 + 事件接入 + 自动写策略 + WorkOrder 模型/迁移/UI + 持久状态 + 一套新测试。
是一个完整 feature，建议单独走 SDLC（需求→架构→实现→测试→部署）。

---

## 5. PoC 映射（已验证的部分）
`agents/langgraph-poc/`（离线 venv，`FREEARK_POC_MOCK=1 PYTHONIOENCODING=utf-8`）：
- `orchestrator.py`：委托工具 + `_expert` 有界循环 + `_handle_delegation` + `_ask_confirm`（confirm 回调，默认拒绝）。
- `test_delegation.py`：4/4 绿——approve→EXECUTED、deny/异常→USER_CANCELLED、深度限1、非委托专家不暴露工具。
- `bench.py`：无回归（路由/fan-out 不变）。
> PoC 用 confirm **回调**模拟确认门；**生产方案 A 用 `pending_write`+`_gate` interrupt 替换之**（更强）。

---

## 6. 风险 / 开放问题
1. **A**：delegate_write 与现有 energy 写在同一 `_gate` 汇聚时，多条 pending_write 的确认 UX
   是否合并展示（`_gate` 已支持 actions 数组，基本就绪）。
2. **A**：子委托加深单轮链路 → 延迟变长（多次 LLM 调用串行）。需设步数/深度上限（PoC `MAX_EXPERT_STEPS=8`）。
3. **B**：自治写的授权模型（白名单 vs 全部转工单）——**安全要害，必须先定策略再写代码**。
4. **B**：工单 sink 是新建子系统，工作量与 UI 取决于人工处置流程。
5. 通用：被委托方报错/超时的降级（回灌错误而非杜撰），提示词已约束，编排层需落实。

---

## 7. 建议
- **A 是 B 的前置**：子委托机制 A、B 共用。先做 A（中等、复用 `_gate`、风险小、立即让 chat 巡检更强），
  把机制在生产跑稳；再据需要做 B（大、需定自治写策略 + 工单子系统，单独走 SDLC）。
- 若只想尽快满足"巡检能联动三恒/能耗"，A 即可交付价值；原始需求#3 的"自治+工单"需 B。

---

## 8. 已完成的验证
- 远端 `397fc54` 已 pull（#15/16/17，全在 FreeArkWeb/，与本设计无冲突）。
- PoC 子委托 `test_delegation.py` 4/4、`bench.py` 无回归（本机 venv 实跑）。
- 生产接缝（_gate/router/prompts/fa_tools）已逐文件核实，见 §2。
