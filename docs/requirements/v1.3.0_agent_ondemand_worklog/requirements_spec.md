# 需求规格说明书 — v1.3.0 智能体按需巡检与工作日志

**文档编号**: REQ-SPEC-AIA-v130-001  
**项目名称**: FreeArk Inspection Agent On-Demand Trigger & Work Log (v1.3.0)  
**版本**: 1.0.0  
**状态**: ✅ 需求已确认（2026-06-16，OQ-1~OQ-7 全部拍板，见 §4）；待开发  
**创建日期**: 2026-06-16  
**作者**: requirement-analyst (via pm-orchestrator)  
**审核**: 待用户拍板（开放决策 OQ-1 ~ OQ-7 见 §4）

---

## 版本历史

| 版本  | 日期       | 变更摘要                             |
|-------|------------|--------------------------------------|
| 1.0.0 | 2026-06-16 | 初始草稿，含开放决策 OQ-1~OQ-7 待用户拍板 |

---

## 0. 问题陈述

### 0.1 背景现状

FreeArk inspection-agent（v1.1.0，方案 B）已具备完整的单事件决策能力：  
`InspectionAgent.process_event(event)` 执行九步 ReAct 决策（委托分析→写提案被策略 B 拦截→建工单），单次耗时约 50 秒（真实 DeepSeek 调用）。

现状痛点：
- **积压 454 条存量事件**：启用 systemd 自动轮询会触发批量处理，消耗大量 token 且难以逐条追踪调试。
- **审计日志仅进 journald**：`inspection_agent/audit.py` 的 JSON 行只写 journald，前端无法查看每次巡检的决策过程，可追溯性为零。
- **缺少按需触发入口**：当前只能由 systemd 服务轮询触发，无法对单条感兴趣的事件按需处理。
- **导航结构模糊**：聊天功能入口名为"和方舟智能体聊天"，与规划中的智能体能力群不在同一分组，不利于后续扩展。

### 0.2 本版本目标

1. 将 inspection-agent 改为**按需、单事件触发**模式（systemd 服务保持 disabled）。
2. 在故障管理和结露预警页面操作列新增「**智能体巡检**」按钮，触发对该条事件的单次决策处置。
3. 新增「**巡检智能体工作日志**」页面，展示每次巡检的完整决策过程（可追溯）。
4. 重组导航栏，新建「**方舟智能体**」菜单分组，统一聚合智能体相关功能。

### 0.3 范围说明（OOS）

- **不修改** `api/langgraph_chat/` 和 `agents/` 任何文件（写授权策略、聊天链路保持原样）。
- **不修改** `inspection_agent/agent.py` 的 `process_event` 核心决策逻辑。
- **不实现**批量处置 454 条存量事件的自动化功能（本期）。
- **不改变**工单系统的现有逻辑（`work_order.py`、`WorkOrder` 模型）。
- **不改变**聊天功能本身（`ChatView.vue`、`ChatConsumer`、OpenClaw 链路）。

---

## 1. 利益相关方

| 角色            | 关切                                                     |
|-----------------|----------------------------------------------------------|
| 物业管理员       | 能对单条故障/预警快速触发智能分析，查看决策结论，无需等待轮询 |
| 系统管理员 (admin) | 能管控谁可触发巡检、查看完整决策过程、了解工单来源       |
| 开发/调试人员    | 前期调试阶段每次单独触发、精准观察每步决策日志            |

---

## 2. 功能需求

### 2.1 按需巡检触发（REQ-FUNC-IA-001 ~ 007）

#### REQ-FUNC-IA-001：故障管理页操作列新增「智能体巡检」按钮

**来源**: 用户原话「在故障管理页面的操作栏加一个"智能体巡检"」  
**现状**: `FaultManagementView.vue` 操作列（`min-width="100"`，`fixed="right"`）当前仅有「设备面板」按钮。  
**需求**: 在「设备面板」按钮旁新增「智能体巡检」`el-button`（`link`、`type="warning"` 或醒目区分色）。

**按钮显示逻辑**：
- 当 `row.inspection_status === 'PENDING'`：显示「智能体巡检」，可点击，蓝色/默认。
- 当 `row.inspection_status === 'IN_PROGRESS'`：显示「巡检中...」，禁用（loading 态）。
- 当 `row.inspection_status === 'DONE'`：显示「已巡检」，灰色，可再次点击（重新触发，见 OQ-4）。
- 当 `row.inspection_status === 'SKIPPED'`：显示「已跳过」，灰色，提示事件已恢复无需巡检。

**触发行为**（依赖 OQ-1 确认方案）：  
用户点击 → 前端调用后端 API（POST `/api/inspection/trigger/fault_event/{id}/`）→ 后端异步发起 `process_event(event)` → 立即返回 202 Accepted + `inspection_status=IN_PROGRESS` → 前端按钮变为 loading 态并轮询状态（见 REQ-FUNC-IA-003）。

---

#### REQ-FUNC-IA-002：结露预警页操作列新增「智能体巡检」按钮

**来源**: 用户原话「在结露预警页面的操作栏加一个"智能体巡检"」  
**现状**: `CondensationWarningView.vue` 操作列（列 13，`min-width="120"`，`fixed="right"`）当前仅有「设备面板」按钮。  
**需求**: 与 REQ-FUNC-IA-001 相同的按钮和交互逻辑，但触发 API 为 `POST /api/inspection/trigger/condensation_warning_event/{id}/`。

---

#### REQ-FUNC-IA-003：按需触发 API 端点

**来源**: REQ-FUNC-IA-001、REQ-FUNC-IA-002 的后端实现需求  
**需求**:

| 属性       | 规格                                                              |
|------------|-------------------------------------------------------------------|
| 路径       | `POST /api/inspection/trigger/{event_type}/{event_id}/`           |
| event_type | `fault_event` 或 `condensation_warning_event`                    |
| 认证       | `IsAuthenticated`（见 OQ-5）                                      |
| 成功响应   | `202 Accepted`，body: `{"status": "IN_PROGRESS", "message": "巡检已启动，预计 50~300 秒完成"}` |
| 重复触发   | 若 `inspection_status == 'IN_PROGRESS'`，返回 `409 Conflict`，body: `{"status": "IN_PROGRESS", "message": "该事件正在巡检中"}` |
| 事件不存在 | `404 Not Found`                                                  |
| 副作用     | 将 `inspection_status` 置为 `IN_PROGRESS`，`inspection_started_at` 置为当前时间，异步提交 `process_event` 到后台线程/任务 |

**异步执行方案**（依赖 OQ-1）：  
推荐方案：Django 视图中使用 `threading.Thread` 启动后台线程执行 `InspectionAgent.process_event(event)`，无需引入 Celery（避免增加树莓派资源消耗）。串行保证：同一时刻只允许一个巡检任务执行（通过检查全局 `IN_PROGRESS` 数量，见 OQ-1）。

---

#### REQ-FUNC-IA-004：状态轮询 API 端点

**来源**: 前端需要得知异步任务完成状态  
**需求**:

| 属性       | 规格                                                              |
|------------|-------------------------------------------------------------------|
| 路径       | `GET /api/inspection/status/{event_type}/{event_id}/`            |
| 认证       | `IsAuthenticated`                                                 |
| 响应       | `{"inspection_status": "PENDING|IN_PROGRESS|DONE|SKIPPED", "inspection_started_at": "ISO8601|null", "work_order_id": "WO-YYYYMMDD-NNNNNN|null"}` |
| 前端行为   | 收到 `IN_PROGRESS` 时每 5 秒轮询一次；收到 `DONE` 或 `SKIPPED` 时停止轮询，刷新该行数据 |

---

#### REQ-FUNC-IA-005：巡检状态在列表中可见

**来源**: 便于用户直观了解每条事件的处置进度  
**需求**: 故障管理和结露预警列表中，按需触发后，`inspection_status` 的状态变化（IN_PROGRESS → DONE）须在前端可见（按钮状态反映，轮询机制实现），无需额外新增独立列（减少表格宽度）。若用户希望查看详细决策过程，通过「巡检工作日志」页面查询（REQ-FUNC-WL-001）。

---

#### REQ-FUNC-IA-006：并发保护

**来源**: 树莓派单核资源限制，用户交代「串行，需考虑并发触发的排队/拒绝」  
**需求**: 后端触发 API 检查当前系统中处于 `IN_PROGRESS` 状态的巡检事件总数：
- 若已有 1 条 `IN_PROGRESS` → 返回 `429 Too Many Requests`，body: `{"message": "当前有巡检任务正在执行，请稍后再试"}`  
- 防止多用户同时触发多条 50s 长时任务压垮树莓派

---

#### REQ-FUNC-IA-007：系统 systemd 服务状态约束

**来源**: 用户原话「没有打开 systemd」「省 token、便于前期调试」  
**需求**: `freeark-inspection-agent` systemd 服务保持 **disabled + stopped** 状态，本版本不通过 systemd 启动轮询模式。`run_inspection_agent` 管理命令保留（供未来可选），但不作为本版本的任何触发路径。

---

### 2.2 巡检智能体工作日志（REQ-FUNC-WL-001 ~ 006）

#### REQ-FUNC-WL-001：新增巡检决策日志持久化（后端）

**来源**: 用户原话「能看到 inspection-agent 处理故障和预警的决策处理过程」；现状 `audit.py` 只写 journald，网页不可查。  
**需求**: 新增数据库模型 `InspectionLog`（表名 `inspection_log`），记录每次 `process_event` 执行过程中的关键步骤，供前端工作日志页面查询。

**InspectionLog 模型字段**:

| 字段名               | 类型                  | 说明                                              |
|----------------------|-----------------------|---------------------------------------------------|
| `id`                 | BigAutoField (PK)    | 主键                                              |
| `source_event_type`  | CharField(32)        | `fault_event` 或 `condensation_warning_event`    |
| `source_event_id`    | BigIntegerField      | 来源事件 ID                                       |
| `specific_part`      | CharField(64)        | 房号，冗余存储加速过滤                             |
| `event_type_display` | CharField(32)        | 人可读事件类型（"故障事件"/"结露预警事件"）         |
| `step`               | CharField(32)        | 决策步骤类型，见下表                              |
| `step_detail`        | JSONField            | 步骤详情（结构化，见下说明）                       |
| `result`             | CharField(16)        | `SUCCESS`、`BLOCKED`、`ERROR`、`SKIPPED`         |
| `work_order_ticket`  | CharField(32)        | 关联工单编号（仅 WORKORDER_CREATED 步骤填写）      |
| `created_at`         | DateTimeField        | 记录时间（`auto_now_add=True`）                   |

**step 枚举值**（对应现有 `audit.py` 常量扩展）:

| step 值                  | 含义                                        |
|--------------------------|---------------------------------------------|
| `PROCESS_STARTED`        | 开始处理一条事件                             |
| `EVENT_SKIPPED`          | 事件已恢复，跳过                            |
| `DELEGATION_CALLED`      | 调用子专家委托（delegate_knowledge/delegate_read） |
| `DELEGATION_ERROR`       | 子专家委托异常                              |
| `WRITE_PROPOSAL`         | LLM 生成写提案                              |
| `WRITE_BLOCKED`          | 写提案被策略 B 拦截                         |
| `WRITE_EXECUTED`         | 写提案被策略 A 执行（当前策略 B 下不可达）  |
| `WORKORDER_CREATED`      | 工单创建成功                                |
| `WORKORDER_EXISTED`      | 工单已存在，未重复建单                      |
| `DECISION_TIMEOUT`       | 决策超时，兜底建单                          |
| `DECISION_ERROR`         | 决策异常，兜底建单                          |
| `PROCESS_COMPLETED`      | 整体处置完成                                |

**step_detail 结构示例**:
```json
// DELEGATION_CALLED
{"target_expert": "knowledge-expert", "query_summary": "分析 9-1-31-3104 结露成因"}

// WRITE_BLOCKED
{"tool_name": "set_device_params", "args": {"specific_part": "...", "items": [...]}, "policy_reason": "POLICY_B_NO_AUTO_WRITE"}

// WORKORDER_CREATED
{"ticket_id": "WO-20260616-000001", "severity": "error", "diagnosis": "...", "recommended_action": "..."}
```

**写入时机**: 在 `inspection_agent/agent.py` 的 `process_event` 及 `audit.py` 各 `log_*` 函数调用处，**同步写入 DB**（不替换现有 journald 日志，双写）。若 DB 写入失败，不影响主流程（catch + 仅 logger.warning）。

---

#### REQ-FUNC-WL-002：工作日志查询 API

**来源**: 前端工作日志页面数据源  
**需求**:

| 属性       | 规格                                                              |
|------------|-------------------------------------------------------------------|
| 路径       | `GET /api/inspection/logs/`                                      |
| 认证       | `IsAuthenticated`（见 OQ-5）                                     |
| 过滤参数   | `event_type`（fault_event/condensation_warning_event）、`specific_part`（模糊）、`date_from`、`date_to`、`result`（SUCCESS/BLOCKED/ERROR 等）、`step` |
| 排序       | 默认 `-created_at`（最新在前）                                    |
| 分页       | `page` + `page_size`（默认 20，最大 100）                        |
| 响应字段   | id、source_event_type、source_event_id、specific_part、event_type_display、step、step_detail、result、work_order_ticket、created_at |

---

#### REQ-FUNC-WL-003：工作日志页面（前端）

**来源**: 用户原话「新页面，是巡检智能体工作日志，能看到 inspection-agent 处理故障和预警的决策处理过程」  
**需求**: 新建 `InspectionWorkLogView.vue`，路由 `/agent/inspection-worklog`。

**页面布局**:
1. **页头**：标题「巡检智能体工作日志」+ 说明文案「记录 inspection-agent 对每条故障/预警事件的决策全过程，含委托调用、写提案拦截和工单创建结论」。
2. **过滤栏**:
   - 事件类型选择（全部 / 故障事件 / 结露预警事件）
   - 房号输入（模糊过滤 specific_part）
   - 时间段选择器（默认最近 7 天）
   - 步骤类型选择（可选，默认全部）
   - 查询 / 重置按钮
3. **日志列表表格**（每条日志一行）:

| 列名         | 字段              | 宽度     | 说明                                          |
|--------------|-------------------|----------|-----------------------------------------------|
| 时间         | created_at        | 160px    | 格式 `YYYY-MM-DD HH:mm:ss`                   |
| 房号         | specific_part     | 120px    | 可点击筛选同房号                              |
| 事件类型     | event_type_display | 100px   | "故障事件"/"结露预警事件"                     |
| 来源事件 ID  | source_event_id   | 80px     | 纯数字                                        |
| 决策步骤     | step              | 150px    | 用 `el-tag` 按步骤类型着色（见下）           |
| 结果         | result            | 80px     | `el-tag`：SUCCESS=绿、BLOCKED=橙、ERROR=红、SKIPPED=灰 |
| 工单编号     | work_order_ticket | 140px    | 非空时显示为文本；WORKORDER_CREATED 步骤才有值 |
| 详情         | step_detail       | -        | 「查看」按钮弹 el-dialog 展示 JSON 格式化内容  |

**步骤 el-tag 着色方案（建议）**:
- `DELEGATION_CALLED`：蓝色（info）
- `WRITE_BLOCKED`：橙色（warning）
- `WORKORDER_CREATED`：成功（success）
- `DECISION_TIMEOUT` / `DECISION_ERROR`：红色（danger）
- 其余：默认灰

4. **分页器**：与 FaultManagementView 一致。

---

#### REQ-FUNC-WL-004：工作日志与事件关联（可选增强）

**来源**: 可追溯需求，便于从事件页面直接查看决策过程  
**需求（可选，依赖 OQ-2 和用户拍板）**: 在故障管理/结露预警操作列，当 `inspection_status == 'DONE'` 时，「已巡检」按钮右侧可增加「查看日志」小链接，跳转到工作日志页面并自动按 `source_event_id` 过滤。

**优先级**: NICE_TO_HAVE（不阻塞核心功能交付）。

---

#### REQ-FUNC-WL-005：工作日志数据保留策略

**来源**: 防止 `inspection_log` 表无限增长（参考 `device_param_history` 的历史教训）  
**需求**: `inspection_log` 记录按需产生（不轮询），数据量可控，本期不设自动清理策略。若后续开启轮询模式，再行评估保留期限（建议 90 天）。

---

#### REQ-FUNC-WL-006：现有 journald 审计日志保持不变

**来源**: 不破坏现有可观测性  
**需求**: `inspection_agent/audit.py` 的 journald 输出路径保留，`InspectionLog` DB 写入为**新增双写路径**，不替换。

---

### 2.3 导航栏改造（REQ-FUNC-NAV-001 ~ 003）

#### REQ-FUNC-NAV-001：新增「方舟智能体」菜单分组

**来源**: 用户原话「在导航栏增加一个功能叫"方舟智能体"，下面有两个菜单」  
**现状**: `Layout.vue` 中「和方舟智能体聊天」为独立 `el-menu-item`（`index="/chat"`），无分组。  
**需求**: 将当前独立「和方舟智能体聊天」`el-menu-item` 替换为 `el-sub-menu`（`index="agent"`），子菜单含：
1. 「和方舟智能体聊天」（原「和方舟智能体聊天」）
2. 「巡检智能体工作日志」（新建页面）

**菜单结构变更对比**:

```
// 变更前
<el-menu-item index="/chat">
  <el-icon><ChatDotRound /></el-icon>
  <template #title><span>和方舟智能体聊天</span></template>
</el-menu-item>

// 变更后
<el-sub-menu index="agent">
  <template #title>
    <el-icon><[选定图标]></el-icon>
    <span>方舟智能体</span>
  </template>
  <el-menu-item index="/chat">和方舟智能体聊天</el-menu-item>
  <el-menu-item index="/agent/inspection-worklog">巡检智能体工作日志</el-menu-item>
</el-sub-menu>
```

---

#### REQ-FUNC-NAV-002：「和方舟智能体聊天」功能不变

**来源**: 用户原话「就是现在的"和方舟智能体聊天"」  
**需求**: 仅做以下两项变更，聊天功能本身（`ChatView.vue`、ChatConsumer、OpenClaw WS 链路）**一律不动**：
1. 菜单文案：`和方舟智能体聊天` → `和方舟智能体聊天`
2. 菜单归属：从独立 item 移入「方舟智能体」子菜单
3. 路由路径 `/chat` 保持不变（见 OQ-6）
4. 路由名称 `Chat` 保持不变

---

#### REQ-FUNC-NAV-003：新增「巡检智能体工作日志」路由

**来源**: REQ-FUNC-WL-003  
**需求**: 在 `src/router/index.js` 新增路由：
```js
{
  path: '/agent/inspection-worklog',
  name: 'InspectionWorkLog',
  component: () => import('../views/InspectionWorkLogView.vue'),
  meta: { requiresAuth: true }
}
```

---

## 3. 非功能需求

### 3.1 性能

| 编号        | 需求                                                             |
|-------------|------------------------------------------------------------------|
| REQ-NFR-001 | 触发 API（POST）响应时间 ≤ 500ms（不含 LLM 执行时间，仅状态更新+返回 202） |
| REQ-NFR-002 | 状态轮询 API（GET）响应时间 ≤ 200ms                             |
| REQ-NFR-003 | 工作日志列表 API，单页 20 条，响应时间 ≤ 1s（`inspection_log` 表量级可控）|
| REQ-NFR-004 | 同时最多 1 条事件处于 `IN_PROGRESS` 状态（REQ-FUNC-IA-006 并发保护） |

### 3.2 可靠性

| 编号        | 需求                                                             |
|-------------|------------------------------------------------------------------|
| REQ-NFR-005 | `process_event` 异常时（超时/网络/LLM 异常），兜底建工单，不丢单（现有逻辑已支持） |
| REQ-NFR-006 | `InspectionLog` DB 写入失败时，不阻断主流程（catch + warning）  |
| REQ-NFR-007 | 后台线程异常退出时，将事件 `inspection_status` 重置为 `PENDING`（同 `run_once` 现有逻辑） |

### 3.3 安全

| 编号        | 需求                                                             |
|-------------|------------------------------------------------------------------|
| REQ-NFR-008 | 触发 API 需 `IsAuthenticated`（所有已登录用户），admin 拍板后可收紧为 admin-only |
| REQ-NFR-009 | `InspectionLog.step_detail`（JSONField）经 `audit.py` 现有 `_scrub()` 脱敏，不存储 API 密钥/token |

### 3.4 可维护性

| 编号        | 需求                                                             |
|-------------|------------------------------------------------------------------|
| REQ-NFR-010 | `InspectionLog` 写入逻辑不耦合 `audit.py` 现有 journald 路径，可独立开关 |
| REQ-NFR-011 | 按需触发 API 须有独立 Django 单元测试（POST 触发、409 重复、429 并发保护） |

---

## 4. 开放决策（✅ 已全部拍板 2026-06-16）

> **决议汇总**（用户拍板，开发按此执行）：
> - **OQ-1 异步执行** = 后台线程（threading.Thread）+ 前端轮询状态（点击立即返回，按钮 loading→完成）；全局同时最多 1 条 IN_PROGRESS，超出拒绝（树莓派单核串行）。
> - **OQ-2 工作日志数据源** = **新建 `InspectionLog` 表**（关键步骤粒度：PROCESS_STARTED/DELEGATION_CALLED/WRITE_BLOCKED/WORKORDER_CREATED/… + step_detail JSON）；audit 双写 DB+journald，DB 失败不阻断主流程。**含一次生产 migration。**
> - **OQ-3 systemd** = 保留 service 与 run_inspection_agent 代码，仅维持 disabled（不删，留后路）。
> - **OQ-4 重新触发** = **允许**对已 DONE 事件重新触发巡检（前期调试需反复观察决策）。
> - **OQ-5 权限** = 触发与查看工作日志均 IsAuthenticated（所有登录用户），与现有服务管理一致。
> - **OQ-6 聊天路由** = 保持 `/chat` 不变（仅菜单归类 + 文案「和方舟智能体聊天」→「和方舟智能体聊天」）。
> - **OQ-7 存量 454** = 自然消化（保持 PENDING、页面显示「待巡检」，仅按需逐条处理；不批量、不标 SKIPPED）。

以下为各项原始分析（保留备查）。

---

### OQ-1：按需触发的并发与超时处理方案

**问题**: 单事件决策约 50 秒（真实 DeepSeek），HTTP 请求不能等待。树莓派单核，需考虑并发。

**推荐方案（供选择）**:

| 选项 | 方案                                                            | 优点                          | 缺点                          |
|------|-----------------------------------------------------------------|-------------------------------|-------------------------------|
| A    | `threading.Thread` + 系统级 `IN_PROGRESS` 计数锁（无额外依赖） | 零新依赖，树莓派友好           | 进程重启丢失运行中任务状态     |
| B    | Django management command 异步（subprocess 子进程）            | 进程隔离更健壮                 | 管理更复杂，引入 IPC           |
| C    | Celery（已有？）                                               | 成熟队列管理                   | 树莓派增加资源消耗，需 broker  |

**建议**: 选项 A（`threading.Thread`），`IN_PROGRESS` 数量通过 DB 查询保证多进程/重启后一致性。

**用户需拍板**: A / B / C？

---

### OQ-2：工作日志数据粒度与数据源

**问题**: 要展示「委托调用/写提案被拦截/建单结论」，粒度如何？

**已建议方案**: 新建 `InspectionLog` 模型（见 REQ-FUNC-WL-001），记录每个关键步骤（不记录完整 LLM 推理链，仅记录结构化事件点）。

**替代方案**: 仅依赖 `WorkOrder` 的 `diagnosis`/`recommended_action` 字段（粒度低，看不到委托过程）。

**用户需拍板**:
- 是否接受新增 `InspectionLog` 表（需 DB migration）？
- 如接受，是否需要记录 LLM 的完整推理步骤（每一步 ReAct thought/action），还是仅记录结构化关键事件点（本文档已建议）？

---

### OQ-3：systemd 服务取舍

**问题**: 本期彻底关闭 systemd 轮询，`run_inspection_agent` 命令和 `run_forever` 逻辑怎么处理？

**选项**:
- A：保留代码，仅确保服务保持 disabled（纯按需模式，不删功能代码）
- B：在代码层面将 `run_forever` 和 `event_poller` 标记为废弃（deprecation 注释），但不删除
- C：删除轮询相关代码，彻底改为按需模式

**建议**: 选项 A（成本最低，日后需要可再开启）。

**用户需拍板**: A / B / C？

---

### OQ-4：已处置事件的重新触发

**问题**: 一条 `inspection_status=DONE` 的事件，用户能否再次点「智能体巡检」重新触发？

**影响**:
- 若允许：需将 `inspection_status` 从 `DONE` 重置为 `IN_PROGRESS`，并支持对同一 `source_event_id` 建多条日志（`InspectionLog` 无问题）；工单有防重复建单保护（`uniq_active_workorder_per_event`），只要原工单在 `OPEN/IN_PROGRESS`，不会重复建单。
- 若不允许：「已巡检」按钮纯展示，不可点。

**用户需拍板**: 允许重新触发 / 不允许？

---

### OQ-5：权限控制粒度

**问题**: 谁能点「智能体巡检」？谁能看「巡检智能体工作日志」？

**选项**:
- A：所有已登录用户均可（`IsAuthenticated`）
- B：仅 admin 角色可触发巡检，普通用户只能查看日志
- C：仅 admin 可触发和查看

**建议**: 前期调试阶段选 A（与其他页面一致），后续可收紧。

**用户需拍板**: A / B / C？

---

### OQ-6：聊天页面路由路径是否调整

**问题**: 「和方舟智能体聊天」导航归入「方舟智能体」子菜单后，路由路径 `/chat` 是否需同步改为 `/agent/chat`？

**影响**:
- 若改路径：需同步更新 `router/index.js`、`Layout.vue` 菜单 `index`，以及任何使用 `router.push('/chat')` 的代码。
- 若不改：路径 `/chat` 保持，菜单 `index` 仍为 `/chat`，仅导航分组变化，最小侵入。

**建议**: 不改路径，保持 `/chat`（最小侵入）。

**用户需拍板**: 保持 `/chat` / 改为 `/agent/chat`？

---

### OQ-7：存量 454 条事件的处理方式

**问题**: 现有 454 条 `inspection_status=PENDING` 的存量事件，本期按需触发上线后如何处理？

**选项**:
- A：不主动处理，用户可在故障管理/结露预警页面逐条点击触发（自然消化）
- B：提供临时管理命令（仅供 admin 手动分批执行），不在前端暴露
- C：本期彻底不动，存量积压留到未来批量处理功能再定

**建议**: 选项 A（自然消化，与按需触发功能复用同一路径，无额外实现成本）。

**用户需拍板**: A / B / C？

---

## 5. 数据模型变更摘要

| 变更类型 | 对象                  | 说明                                                    |
|----------|-----------------------|---------------------------------------------------------|
| 新增表   | `inspection_log`      | 新建 `InspectionLog` 模型，需新 migration（0036 或顺序号）|
| 无变更   | `fault_event`         | `inspection_status`/`inspection_started_at` 字段已存在  |
| 无变更   | `condensation_warning_event` | 同上                                           |
| 无变更   | `inspection_work_order` | `WorkOrder` 模型不变，防重复建单逻辑不变              |

---

## 6. API 端点汇总

| 方法 | 路径                                              | 功能                   | 认证           |
|------|---------------------------------------------------|------------------------|----------------|
| POST | `/api/inspection/trigger/{event_type}/{event_id}/` | 触发单条事件巡检       | IsAuthenticated |
| GET  | `/api/inspection/status/{event_type}/{event_id}/`  | 查询巡检状态           | IsAuthenticated |
| GET  | `/api/inspection/logs/`                           | 查询工作日志列表（分页）| IsAuthenticated |

---

## 7. 前端文件变更摘要

| 文件                                          | 变更类型 | 变更摘要                                              |
|-----------------------------------------------|----------|-------------------------------------------------------|
| `src/components/Layout.vue`                   | 修改     | 导航菜单：独立 chat item → 「方舟智能体」子菜单，含2个子项 |
| `src/router/index.js`                         | 修改     | 新增 `/agent/inspection-worklog` 路由                 |
| `src/views/FaultManagementView.vue`           | 修改     | 操作列新增「智能体巡检」按钮 + 状态显示逻辑           |
| `src/views/CondensationWarningView.vue`       | 修改     | 同上                                                  |
| `src/views/InspectionWorkLogView.vue`         | 新建     | 巡检智能体工作日志页面                                |

---

## 8. 后端文件变更摘要

| 文件                                              | 变更类型 | 变更摘要                                                    |
|---------------------------------------------------|----------|-------------------------------------------------------------|
| `api/models.py`                                   | 修改     | 新增 `InspectionLog` 模型                                   |
| `api/migrations/0036_inspection_log.py`           | 新建     | `InspectionLog` 的 DB migration（编号待确认）              |
| `api/views_inspection.py`（新建）或 `api/views.py` | 新建/修改 | 触发 API、状态查询 API、日志列表 API                       |
| `api/serializers_inspection.py`（新建）           | 新建     | `InspectionLogSerializer`                                   |
| `api/urls.py`                                     | 修改     | 注册 `/api/inspection/` 路由组                             |
| `inspection_agent/audit.py`                       | 修改     | 各 `log_*` 函数新增 DB 写入路径（双写，不替换 journald）   |
| `inspection_agent/agent.py`                       | 修改     | `process_event` 开始/完成时写 `PROCESS_STARTED`/`PROCESS_COMPLETED` 日志 |

---

## 9. 约束与依赖

| 编号        | 约束                                                              |
|-------------|-------------------------------------------------------------------|
| CON-001     | 物理机部署，无 Docker；所有依赖须已在树莓派生产环境可用          |
| CON-002     | 生产 DB：`192.168.31.98:3306` MySQL；测试用 SQLite                |
| CON-003     | 不修改 `api/langgraph_chat/` 和 `agents/` 任何文件               |
| CON-004     | `freeark-inspection-agent` systemd 服务保持 disabled              |
| CON-005     | 前端框架：Vue 3 + Element Plus（复用现有组件风格）               |
| CON-006     | 后端框架：Django REST Framework，认证：DRF Token                  |
