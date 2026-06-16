# 用户故事清单 — v1.3.0 智能体按需巡检与工作日志

**文档编号**: REQ-US-AIA-v130-001  
**关联规格**: REQ-SPEC-AIA-v130-001  
**版本**: 1.0.0  
**状态**: DRAFT — 待用户门控确认  
**创建日期**: 2026-06-16  
**作者**: requirement-analyst (via pm-orchestrator)

---

## 故事分组

- **Block A**：按需巡检触发（US-IA-01 ~ US-IA-06）
- **Block B**：巡检工作日志（US-WL-01 ~ US-WL-04）
- **Block C**：导航栏改造（US-NAV-01 ~ US-NAV-02）

---

## Block A：按需巡检触发

---

### US-IA-01：在故障管理页触发单条故障事件的智能体巡检

**As a** 物业管理员  
**I want to** 在故障管理列表中，对某一条感兴趣的故障事件点击「智能体巡检」按钮  
**So that** inspection-agent 能对该条事件执行一次完整的决策分析（委托分析、写提案、转工单），而无需等待 systemd 自动轮询

**优先级**: P0（核心功能）  
**关联需求**: REQ-FUNC-IA-001、REQ-FUNC-IA-003

**验收标准（Given/When/Then）**:

**场景 1：成功触发一条 PENDING 状态的故障事件**
```
Given  故障管理页已加载，表格中存在一条 inspection_status=PENDING 的故障事件（id=42）
  And  操作列显示「智能体巡检」按钮（蓝色/可点击）
When   用户点击该行的「智能体巡检」按钮
Then   前端立即调用 POST /api/inspection/trigger/fault_event/42/
  And  后端在 500ms 内返回 202 Accepted，body 含 status=IN_PROGRESS
  And  该事件的 inspection_status 在 DB 中变为 IN_PROGRESS
  And  该行操作列按钮变为「巡检中...」并处于禁用态（loading）
  And  前端每 5 秒轮询一次 GET /api/inspection/status/fault_event/42/
  And  50~300 秒后，轮询到 status=DONE，按钮变为「已巡检」（灰色）
```

**场景 2：事件已恢复（is_active=False），跳过建单**
```
Given  一条 is_active=False 且 inspection_status=PENDING 的故障事件
When   用户点击「智能体巡检」
Then   后端触发 process_event，检测到 is_active=False，标记 inspection_status=SKIPPED
  And  前端轮询到 status=SKIPPED，按钮变为「已跳过」（灰色）
  And  不建工单
```

**场景 3：触发 API 响应时间**
```
Given  用户点击「智能体巡检」按钮
When   POST /api/inspection/trigger/fault_event/{id}/ 请求发出
Then   后端在 ≤500ms 内返回 202（不等待 LLM 执行完成）
```

---

### US-IA-02：在结露预警页触发单条结露预警事件的智能体巡检

**As a** 物业管理员  
**I want to** 在结露预警列表中，对某一条预警事件点击「智能体巡检」按钮  
**So that** inspection-agent 能对该条结露预警执行一次完整的决策分析

**优先级**: P0（核心功能）  
**关联需求**: REQ-FUNC-IA-002、REQ-FUNC-IA-003

**验收标准（Given/When/Then）**:

**场景 1：成功触发一条 PENDING 状态的结露预警事件**
```
Given  结露预警页已加载，表格中存在一条 inspection_status=PENDING 的预警事件（id=88）
  And  操作列（列 13）显示「智能体巡检」按钮（可点击）
When   用户点击该行的「智能体巡检」按钮
Then   前端调用 POST /api/inspection/trigger/condensation_warning_event/88/
  And  后端在 ≤500ms 内返回 202 Accepted
  And  该事件 inspection_status 变为 IN_PROGRESS
  And  前端按钮变为「巡检中...」loading 态
  And  决策完成后（50~300 秒）轮询到 DONE，按钮变为「已巡检」
```

**场景 2：操作列布局不破坏**
```
Given  结露预警页当前操作列只有「设备面板」一个按钮
When   新增「智能体巡检」按钮后
Then   「设备面板」按钮仍正常显示，两个按钮并排，操作列宽度调整为合适值（min-width 需评估）
  And  新按钮不遮挡、不重叠已有按钮
```

---

### US-IA-03：按钮状态随 inspection_status 动态显示

**As a** 物业管理员  
**I want to** 操作列的「智能体巡检」按钮能直观反映当前巡检状态  
**So that** 我无需离开列表页就能了解每条事件的处置进度

**优先级**: P0  
**关联需求**: REQ-FUNC-IA-001、REQ-FUNC-IA-002

**验收标准（Given/When/Then）**:

**场景 1：四种状态的按钮显示**
```
Given  故障管理/结露预警列表已加载
When   各行的 inspection_status 分别为 PENDING / IN_PROGRESS / DONE / SKIPPED
Then   PENDING   → 显示「智能体巡检」，蓝色链接按钮，可点击
       IN_PROGRESS → 显示「巡检中...」，禁用态（loading spinner 或灰色）
       DONE      → 显示「已巡检」，灰色，（可点击或禁用，依 OQ-4 拍板结果）
       SKIPPED   → 显示「已跳过」，灰色，鼠标悬停提示「事件已恢复，无需巡检」
```

**场景 2：页面刷新后状态持久**
```
Given  用户已触发某事件巡检并等待完成（inspection_status=DONE）
When   用户刷新页面或重新进入故障管理页
Then   该事件操作列仍显示「已巡检」（状态持久化在 DB，不依赖前端内存）
```

---

### US-IA-04：并发保护——同时只允许一条事件处于巡检中

**As a** 系统（运行在树莓派单核上）  
**I want to** 在已有一条事件巡检进行中时，拒绝新的巡检触发请求  
**So that** 避免多条 50 秒 LLM 任务并发压垮树莓派

**优先级**: P0  
**关联需求**: REQ-FUNC-IA-006

**验收标准（Given/When/Then）**:

**场景 1：并发触发被拒绝**
```
Given  当前系统中已有 1 条事件的 inspection_status=IN_PROGRESS
When   用户对另一条 PENDING 事件点击「智能体巡检」
Then   前端调用 POST /api/inspection/trigger/{event_type}/{id}/
  And  后端返回 429 Too Many Requests
  And  body 含 {"message": "当前有巡检任务正在执行，请稍后再试"}
  And  前端以 el-message warning 提示「当前有巡检任务正在执行，请稍后再试」
  And  被点击按钮的状态保持不变（仍显示「智能体巡检」）
```

**场景 2：同一事件重复触发被拒绝**
```
Given  事件 id=42 当前 inspection_status=IN_PROGRESS
When   用户再次点击该事件的「智能体巡检」按钮（UI 应已禁用，此场景测 API 层防护）
Then   POST /api/inspection/trigger/fault_event/42/ 返回 409 Conflict
  And  body 含 {"status": "IN_PROGRESS", "message": "该事件正在巡检中"}
```

---

### US-IA-05：巡检决策完成后建立工单

**As a** 物业管理员  
**I want to** 智能体巡检完成后，能在 Django Admin 或工作日志页面看到生成的工单  
**So that** 人工能据工单内容进行实际处置

**优先级**: P0  
**关联需求**: REQ-FUNC-IA-003（副作用：`process_event` 触发 `create_from_event`）

**验收标准（Given/When/Then）**:

**场景 1：正常决策路径——LLM 给出写提案，被策略 B 拦截，建工单**
```
Given  触发对故障事件 id=42 的按需巡检（inspection_status=IN_PROGRESS）
When   inspection-agent 执行 process_event：LLM 生成写提案 → WriteAuthPolicy 策略 B 拦截
Then   DB 中 inspection_work_order 表新增一条 WorkOrder
  And  ticket_id 格式为 WO-YYYYMMDD-NNNNNN
  And  source_event_type='fault_event'，source_event_id=42
  And  recommended_action 包含被拦截的写提案描述（如"设备 9-1-31-3104 参数 xxx→yyy"）
  And  status='OPEN'
  And  事件 inspection_status 变为 DONE
```

**场景 2：决策超时，兜底建工单**
```
Given  触发对某事件的按需巡检
When   LLM 决策超时（超过 INSPECTION_DECISION_TIMEOUT 秒）
Then   兜底建工单，recommended_action 包含「自治决策未完成，已兜底建单待人工巡检」
  And  事件 inspection_status 变为 DONE
  And  不丢单
```

**场景 3：同一事件已有 OPEN 工单，防重复建单**
```
Given  事件 id=42 已有 status=OPEN 的工单 WO-20260616-000001
When   因任何原因再次触发 process_event（如 OQ-4 允许重新触发）
Then   不新建工单，返回已有工单 WO-20260616-000001
  And  事件 inspection_status 仍变为 DONE
```

---

### US-IA-06：systemd 服务保持 disabled，不影响按需触发

**As a** 开发/调试人员  
**I want to** `freeark-inspection-agent` systemd 服务保持 disabled 状态  
**So that** 不会因 systemd 轮询意外消耗 token 或触发批量处理

**优先级**: P0  
**关联需求**: REQ-FUNC-IA-007

**验收标准（Given/When/Then）**:

**场景 1：systemd 服务状态验证**
```
Given  v1.3.0 部署到生产环境（树莓派 192.168.31.51）后
When   运行 systemctl is-enabled freeark-inspection-agent
Then   输出为 disabled
When   运行 systemctl is-active freeark-inspection-agent
Then   输出为 inactive (dead)
```

**场景 2：按需触发不依赖 systemd**
```
Given  freeark-inspection-agent systemd 服务处于 disabled+stopped
When   用户在前端点击「智能体巡检」按钮触发 API
Then   后台线程（或等效机制）正常执行 process_event
  And  50~300 秒后 inspection_status 变为 DONE
  And  工单正常建立
  And  systemd 服务状态未发生变化（仍 disabled）
```

---

## Block B：巡检工作日志

---

### US-WL-01：查看巡检智能体工作日志列表

**As a** 物业管理员  
**I want to** 通过「巡检智能体工作日志」页面，查看 inspection-agent 处理每条事件的决策步骤  
**So that** 我能追溯每次按需巡检的完整过程（委托调用了什么、写提案被拦截了还是建了工单）

**优先级**: P0  
**关联需求**: REQ-FUNC-WL-002、REQ-FUNC-WL-003

**验收标准（Given/When/Then）**:

**场景 1：页面加载显示最新日志**
```
Given  用户已登录，访问 /agent/inspection-worklog
When   页面加载完成
Then   显示最近 7 天（默认）的巡检日志，按时间倒序排列
  And  每行显示：时间、房号、事件类型、来源事件 ID、决策步骤、结果、工单编号
  And  分页默认每页 20 条
  And  loading 状态在数据返回前可见
```

**场景 2：一次完整按需巡检产生多条日志记录**
```
Given  用户对故障事件 id=42（房号 9-1-31-3104）触发按需巡检
When   巡检完成（耗时约 60 秒）
Then   工作日志页面中出现多条 source_event_id=42 的记录，包含：
       - PROCESS_STARTED（结果: SUCCESS）
       - DELEGATION_CALLED（target_expert: knowledge-expert，结果: SUCCESS）
       - WRITE_PROPOSAL（工具名，结果: SUCCESS）
       - WRITE_BLOCKED（策略 B 拦截，结果: BLOCKED）
       - WORKORDER_CREATED（ticket_id: WO-20260616-000001，结果: SUCCESS）
       - PROCESS_COMPLETED（结果: SUCCESS）
```

---

### US-WL-02：通过过滤条件精确查找决策日志

**As a** 物业管理员  
**I want to** 在工作日志页面按房号、事件类型、时间段过滤记录  
**So that** 快速定位某个房间或某段时间内的巡检决策过程

**优先级**: P0  
**关联需求**: REQ-FUNC-WL-002、REQ-FUNC-WL-003

**验收标准（Given/When/Then）**:

**场景 1：按房号过滤**
```
Given  工作日志页面已加载（含多条不同房号的日志）
When   用户在房号输入框输入「9-1-31」并点击查询
Then   列表仅显示 specific_part 包含「9-1-31」的日志记录
  And  其他房号的记录不显示
```

**场景 2：按事件类型过滤**
```
Given  工作日志页面已加载
When   用户在事件类型下拉选择「结露预警事件」
Then   列表仅显示 source_event_type='condensation_warning_event' 的日志
```

**场景 3：按时间段过滤**
```
Given  工作日志页面已加载（默认最近 7 天）
When   用户选择时间段 2026-06-10 至 2026-06-12
Then   列表仅显示 created_at 在该范围内的日志
  And  超出范围的记录不显示
```

**场景 4：重置过滤条件**
```
Given  用户已设置多个过滤条件
When   点击「重置」按钮
Then   所有过滤条件恢复默认值（时间段=最近7天，其他=全部）
  And  列表重新加载显示全量数据
```

---

### US-WL-03：查看决策步骤的详细信息

**As a** 开发/调试人员  
**I want to** 点击工作日志某条记录的「查看」按钮，弹出该步骤的完整 step_detail 内容  
**So that** 我能看到 LLM 写提案的具体参数、委托调用的完整摘要等调试信息

**优先级**: P1  
**关联需求**: REQ-FUNC-WL-003

**验收标准（Given/When/Then）**:

**场景 1：查看 WRITE_BLOCKED 步骤详情**
```
Given  工作日志列表中有一条 step=WRITE_BLOCKED 的记录
When   用户点击该行「详情」列的「查看」按钮
Then   弹出 el-dialog，标题「步骤详情」
  And  对话框中格式化展示 step_detail 的 JSON 内容，包含：
       tool_name: "set_device_params"
       args: { specific_part: "...", items: [...] }
       policy_reason: "POLICY_B_NO_AUTO_WRITE"
  And  不显示已被 _scrub() 脱敏的敏感字段（如有）
```

**场景 2：查看 DELEGATION_CALLED 步骤详情**
```
Given  工作日志列表中有一条 step=DELEGATION_CALLED 的记录
When   用户点击「查看」按钮
Then   对话框展示：
       target_expert: "knowledge-expert"
       query_summary: "分析 9-1-31-3104 结露成因..."
```

---

### US-WL-04：工作日志记录写入不影响巡检主流程

**As a** 系统  
**I want to** 即使 InspectionLog DB 写入失败，process_event 主流程也不中断  
**So that** 工单创建和事件状态更新的可靠性不受日志记录的影响

**优先级**: P0  
**关联需求**: REQ-FUNC-WL-001（REQ-NFR-006）

**验收标准（Given/When/Then）**:

**场景 1：DB 写入失败时主流程继续**
```
Given  InspectionLog 的 DB 写入路径抛出异常（模拟：DB 连接超时）
When   process_event 执行过程中尝试写入 DELEGATION_CALLED 日志
Then   异常被 catch，记录 logger.warning 到 journald
  And  process_event 继续执行后续步骤（不抛出、不中断）
  And  工单正常建立，inspection_status 正常置为 DONE
  And  journald 中仍有原有的 audit.py JSON 日志
```

---

## Block C：导航栏改造

---

### US-NAV-01：导航栏新增「方舟智能体」分组

**As a** 所有已登录用户  
**I want to** 在侧边导航栏看到「方舟智能体」子菜单组  
**So that** 智能体相关功能（聊天 + 工作日志）集中在一个分组，便于发现和使用

**优先级**: P0  
**关联需求**: REQ-FUNC-NAV-001、REQ-FUNC-NAV-002、REQ-FUNC-NAV-003

**验收标准（Given/When/Then）**:

**场景 1：「方舟智能体」菜单分组可见**
```
Given  用户已登录，进入任意页面
When   查看左侧导航栏
Then   存在「方舟智能体」可展开/收起的子菜单组（el-sub-menu）
  And  展开后显示两个子项：「和方舟智能体聊天」、「巡检智能体工作日志」
  And  原独立「和方舟龙虾聊天」菜单项不再单独出现（已归入分组）
```

**场景 2：「和方舟智能体聊天」功能不变**
```
Given  用户点击「方舟智能体」→「和方舟智能体聊天」
When   页面跳转
Then   路由路径为 /chat（不变）
  And  加载 ChatView.vue（不变）
  And  聊天功能（OpenClaw WS 链路）正常工作，界面与 v1.2.0 一致
  And  页面标题或功能本身无其他变化
```

**场景 3：「巡检智能体工作日志」菜单可点击跳转**
```
Given  用户点击「方舟智能体」→「巡检智能体工作日志」
When   页面跳转
Then   路由路径为 /agent/inspection-worklog
  And  加载 InspectionWorkLogView.vue
  And  页面显示工作日志列表
```

**场景 4：导航栏折叠状态下菜单可用**
```
Given  用户已折叠侧边栏（isCollapsed=true）
When   点击「方舟智能体」图标
Then   弹出 el-menu--popup，包含「和方舟智能体聊天」和「巡检智能体工作日志」两个子项
  And  点击任一子项正常跳转
```

---

### US-NAV-02：菜单文案更新（「龙虾」→「智能体」）

**As a** 所有已登录用户  
**I want to** 看到「和方舟智能体聊天」（而非「和方舟龙虾聊天」）  
**So that** 产品定位更清晰，与整体「方舟智能体」品牌一致

**优先级**: P0  
**关联需求**: REQ-FUNC-NAV-002

**验收标准（Given/When/Then）**:

**场景 1：文案变更后功能不变**
```
Given  用户进入导航栏「方舟智能体」子菜单
When   查看子菜单第一项文案
Then   显示「和方舟智能体聊天」（不再显示「和方舟龙虾聊天」）
  And  点击后路由仍跳转到 /chat
  And  ChatView 功能完全不变（仅菜单文案变化，代码无其他改动）
```

**场景 2：浏览器历史记录 /chat 仍可用**
```
Given  用户曾访问过 /chat 并保存书签或浏览器历史
When   用户通过书签或地址栏直接访问 /chat
Then   页面正常加载 ChatView（路由路径未改变，不返回 404）
```

---

## 验收标准汇总矩阵

| 故事编号   | 标题                             | 优先级 | 关联需求                         | OQ 依赖       |
|------------|----------------------------------|--------|----------------------------------|---------------|
| US-IA-01   | 故障管理页触发智能体巡检         | P0     | REQ-FUNC-IA-001、003             | OQ-1、OQ-4   |
| US-IA-02   | 结露预警页触发智能体巡检         | P0     | REQ-FUNC-IA-002、003             | OQ-1、OQ-4   |
| US-IA-03   | 按钮状态随 inspection_status 变化 | P0     | REQ-FUNC-IA-001、002             | OQ-4          |
| US-IA-04   | 并发保护（同时仅1条 IN_PROGRESS） | P0     | REQ-FUNC-IA-006                  | OQ-1          |
| US-IA-05   | 巡检完成后建立工单               | P0     | REQ-FUNC-IA-003（process_event） | —             |
| US-IA-06   | systemd 保持 disabled            | P0     | REQ-FUNC-IA-007                  | OQ-3          |
| US-WL-01   | 查看工作日志列表                 | P0     | REQ-FUNC-WL-002、003             | OQ-2          |
| US-WL-02   | 过滤条件精确查找日志             | P0     | REQ-FUNC-WL-002、003             | OQ-2          |
| US-WL-03   | 查看步骤详情（el-dialog）        | P1     | REQ-FUNC-WL-003                  | OQ-2          |
| US-WL-04   | 日志写入失败不影响主流程         | P0     | REQ-NFR-006                      | OQ-2          |
| US-NAV-01  | 新增「方舟智能体」导航分组       | P0     | REQ-FUNC-NAV-001、002、003       | OQ-6          |
| US-NAV-02  | 菜单文案「龙虾」→「智能体」      | P0     | REQ-FUNC-NAV-002                 | OQ-6          |

---

## 不在本版本范围内的故事（OOS）

| 故事（未编号）                          | 原因                               |
|-----------------------------------------|------------------------------------|
| 批量处置 454 条存量事件                 | 依赖 OQ-7 拍板，本期不实现         |
| 工单前端管理页面（工单列表/状态更新）   | 现有需求规格明确「本期仅 Django Admin」|
| 巡检结果通知推送（邮件/微信）           | 超出本版本范围                     |
| 策略 A 白名单放行（自动执行写操作）     | 不改变 WriteAuthPolicy，策略 B 保持 |
| ChatView 聊天功能任何改动               | 明确 OOS                           |
| `api/langgraph_chat/` 任何改动          | 明确 OOS（CON-003）               |
