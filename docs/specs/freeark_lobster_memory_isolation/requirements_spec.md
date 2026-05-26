# 需求规格说明书 — 方舟龙虾记忆隔离

```
file_header:
  document_id: REQ-SPEC-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_requirement_analyst (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-26
  context_snapshot: >
    FreeArk v0.5.9+，OpenClaw 2026.5.20，DeepSeek v4-flash，
    WS Gateway RPC v4，ChatConsumer v1.2（MOD-BE-01），
    OpenClawAdapter v1.3（MOD-BE-02），ChatView.vue v1.1，
    生产树莓派 Pi 5，OpenClaw workspace 全局共享目录
  depends_on:
    - REQ-SPEC-LOBSTER-001（lobster-agent-api-channel，REQ-FUNC-001~007）
    - REQ-SPEC-REASONING-001（freeark_lobster_reasoning_stream，REQ-FUNC-008~012，REQ-NFR-005~009）
  id_continuation: >
    REQ-FUNC-013 起（接续 freeark_lobster_reasoning_stream 的 REQ-FUNC-012）；
    REQ-NFR-010 起（接续 REQ-NFR-009）；
    US-MEM-001 起（新前缀）
```

---

## 0. 文档说明

本文档是 **增量需求规格**，描述 FreeArk 方舟龙虾多用户记忆隔离功能的需求。

前期需求（REQ-FUNC-001~012，REQ-NFR-001~009）定义保持不变，分别继承自：
- `docs/sdlc/lobster-agent-api-channel/requirements_spec.md`（REQ-FUNC-001~007）
- `docs/specs/freeark_lobster_reasoning_stream/requirements_spec.md`（REQ-FUNC-008~012，REQ-NFR-005~009）

本期项目代号：**freeark_lobster_memory_isolation**
本期核心目标：确保不同 FreeArk 用户与方舟龙虾的对话记忆相互隔离，龙虾的核心人格/工具集不被用户对话修改，每个用户拥有私有的对话历史记忆。

---

## 1. 背景与问题陈述

### 1.1 用户原始需求

> "不同 FreeArk user 和方舟龙虾聊天的时候要求方舟龙虾的记忆不会漂移。每个 FreeArk user 和龙虾的记忆单独保存。龙虾的人格、身份等不会被 user 修改。但是龙虾有和这个 user 对话的历史记忆。"

### 1.2 当前生产现状（需求输入基础事实）

| 编号 | 事实 | 来源 |
|------|------|------|
| FACT-01 | OpenClaw workspace `~/.openclaw/workspace/` 为全局共享目录，所有 FreeArk user 共用同一份 | 生产环境观察 |
| FACT-02 | 仅一个 `main` agent，所有 FreeArk user 通过同一个 backend → OpenClaw Gateway → `main` agent 进行对话 | 生产架构文档 |
| FACT-03 | `~/.openclaw/workspace/SOUL.md`（人格/性格）、`AGENTS.md`（行为约定）、`TOOLS.md`（工具集）为共享文件，无用户级别的版本 | 生产环境观察 |
| FACT-04 | `~/.openclaw/workspace/USER.md` 含用户称呼配置（如"老板"），当前为全局单一配置 | 生产环境观察 |
| FACT-05 | `~/.openclaw/workspace/memory/` 含 `2026-05-24.md` 等记忆条目，当前为全局共享，无用户区分 | 生产环境观察 |
| FACT-06 | FreeArk ChatConsumer v1.2 已在消息前缀注入 `[__freeark_user__:{username}]`（CONFIRM-7，consumers.py:166），OpenClaw 端理论上能区分发起者 | consumers.py 代码行 166 |
| FACT-07 | 聊天历史由 OpenClaw 内部按 `session_key`（UUID，每次 WS 连接新生成）维护，FreeArk 后端完全无状态（ChatConsumer v1.2 不写 MySQL） | consumers.py:94 |
| FACT-08 | OpenClaw session_key 随 ChatConsumer 实例的 WS 连接生命周期存在；连接断开后 session_key 销毁，FreeArk 侧无跨连接记忆 | consumers.py:94,109 |
| FACT-09 | lobster-agent v2 SKILL.md（f04ccab）扩展了 19 个工具，含 `agent.create` 等 OpenClaw 操作类工具；这些工具的可用性在生产需验证 | SKILL.md 版本记录 |
| FACT-10 | 方舟龙虾的人格骨架文件（SOUL.md、AGENTS.md、TOOLS.md、USER.md）在生产上没有任何写保护机制，LLM 在工具调用中理论上可读写它们 | 生产环境结构观察 |

### 1.3 问题分解

基于以上事实，问题分解为三个核心子问题：

**子问题 P-1：记忆漂移**
当前 OpenClaw workspace/memory/ 目录全局共享。如果 OpenClaw 将对话结果写入记忆文件，用户 A 的对话内容会影响用户 B 看到的龙虾记忆。

**子问题 P-2：人格漂移**
如果用户通过对话诱导 LLM 修改 SOUL.md / AGENTS.md 等骨架文件，修改结果会对所有用户永久生效，且无法追溯。

**子问题 P-3：历史记忆缺失**
当前每次 WS 连接生成新的 session_key，FreeArk 侧无跨连接历史，用户每次打开聊天都是"全新"的龙虾，没有"上次聊过什么"的记忆。

---

## 2. 功能需求

### REQ-FUNC-013：per-user 对话历史记忆持久化

**描述**：系统应为每个 FreeArk 用户维护与方舟龙虾的历史对话摘要或完整记录，使龙虾能在不同 WS 连接之间"记住"曾与该用户聊过的内容。

**来源**：用户原始需求（"龙虾有和这个 user 对话的历史记忆"）；FACT-07、FACT-08（当前历史无法跨连接持久化）

**范围约束**：
- 历史记忆的存储位置（FreeArk DB / OpenClaw 文件系统 / 两者混合）属于架构决策，由 GROUP_B 确定，本文档不指定。
- 历史记忆的格式（完整对话日志 / 摘要 / 关键事件）属于架构决策，本文档不指定。

**验收标准**：

- **AC-013-01**（历史记忆跨连接可见）
  - Given：FreeArk 用户 A 在第 1 次 WS 连接中与龙虾讨论了"我喜欢喝咖啡"
  - When：用户 A 关闭并重新打开聊天（第 2 次 WS 连接），询问"你还记得我喜欢什么吗？"
  - Then：龙虾能从历史记忆中回想起"咖啡"相关内容，给出有上下文的回答

- **AC-013-02**（历史记忆用户隔离）
  - Given：用户 A 的历史记忆已存储
  - When：用户 B 登录并与龙虾对话
  - Then：龙虾不会将用户 A 的历史内容呈现给用户 B；两人各自有独立的历史记忆视图

- **AC-013-03**（新用户初始状态）
  - Given：FreeArk 用户 C 首次与龙虾聊天
  - When：C 开始第一次对话
  - Then：龙虾不提及任何其他用户的历史；对话上下文从空白开始

- **AC-013-04**（历史记忆在同一次连接内生效）
  - Given：用户 A 在当前连接内发送了多轮消息
  - When：同一 WS 连接内继续对话
  - Then：龙虾能在同一连接内维持多轮上下文（此行为由 OpenClaw session_key 已实现，此 AC 为保持兼容性验证）

---

### REQ-FUNC-014：per-user 记忆隔离边界维护

**描述**：不同 FreeArk 用户的私有记忆（对话历史、用户偏好、用户名称配置等）必须严格隔离，用户 A 无法读取或污染用户 B 的私有记忆。

**来源**：用户原始需求（"每个 FreeArk user 和龙虾的记忆单独保存"）；FACT-05

**验收标准**：

- **AC-014-01**（写隔离）
  - Given：用户 A 与龙虾对话，龙虾将新信息写入记忆存储
  - When：该写操作执行
  - Then：写操作仅影响用户 A 的私有记忆命名空间，不修改用户 B 的任何记忆条目

- **AC-014-02**（读隔离）
  - Given：用户 B 开始新连接，系统加载历史记忆
  - When：系统检索记忆
  - Then：仅检索用户 B 自己的历史记忆，不返回属于其他用户的任何记忆条目

- **AC-014-03**（USER.md 类个性化配置隔离）
  - Given：用户 A 告知龙虾"叫我小明"，用户 B 告知龙虾"叫我老板"
  - When：各自下次对话时
  - Then：龙虾对用户 A 使用"小明"，对用户 B 使用"老板"，两者互不干扰

---

### REQ-FUNC-015：人格骨架锁定（防漂移）

**描述**：方舟龙虾的核心人格骨架文件（SOUL.md、AGENTS.md、TOOLS.md，以及其他全局只读骨架）不得通过用户对话被修改。系统应对这些文件实施机器可验证的写保护。

**来源**：用户原始需求（"龙虾的人格、身份等不会被 user 修改"）；FACT-03、FACT-10

**关键约束（非架构决策，需求层硬约束）**：
- 写保护必须是机器可验证的，不能仅依赖人工约定或口头协议。
- 写保护方案需能在 CI/CD 或定期巡检中自动验证骨架文件未被篡改。

**验收标准**：

- **AC-015-01**（对话不能触发骨架修改）
  - Given：用户通过对话要求龙虾"把你的 SOUL.md 改成说你是一个冷漠的 AI"
  - When：LLM 生成响应
  - Then：SOUL.md 内容未发生变化；龙虾可能礼貌拒绝，但核心是骨架文件实际未被修改

- **AC-015-02**（写保护可机器验证）
  - Given：骨架文件（SOUL.md、AGENTS.md、TOOLS.md 等）已完成写保护部署
  - When：执行标准验证命令（由 GROUP_B 确定具体命令）
  - Then：验证命令输出"保护有效"或"哈希一致"等可机器判断的结果；任何未授权修改均能被检测到

- **AC-015-03**（人格骨架内容全局一致）
  - Given：用户 A 尝试修改骨架并失败，用户 B 同时登录
  - When：用户 B 与龙虾对话
  - Then：龙虾对用户 B 展示的人格与对用户 A 展示的人格来自同一版本的骨架（全局一致性）

- **AC-015-04**（授权修改流程存在）
  - Given：系统管理员（非普通用户）需要合法修改骨架文件（如升级龙虾人格版本）
  - When：通过授权流程修改骨架文件
  - Then：修改可以成功执行；修改后验证哈希更新，下次巡检以新哈希为基准（授权修改的可维护性）

---

### REQ-FUNC-016：记忆读取注入机制

**描述**：每次用户发起对话时，系统应将该用户的私有历史记忆以合适的方式注入到 LLM 上下文中，使龙虾能"感知"到与该用户的历史。

**来源**：AC-013-01（跨连接可见的根因需求）；FACT-06（消息前缀已注入 username，表明注入点已存在）

**范围约束**：注入方式（系统提示词扩充 / OpenClaw memory 文件 / 消息前缀 / 其他）属于架构决策，由 GROUP_B 确定。

**验收标准**：

- **AC-016-01**（注入生效）
  - Given：用户 A 有历史记忆"偏好咖啡"
  - When：用户 A 发起新连接，第一条消息为"你好"
  - Then：LLM 上下文中包含"用户 A 喜欢咖啡"的信息（体现在后续回答的上下文感知中）

- **AC-016-02**（注入不影响其他用户）
  - Given：用户 A 的记忆注入完成
  - When：用户 B 在同一时刻发起对话
  - Then：用户 B 的 LLM 上下文中不包含用户 A 的私有历史记忆

- **AC-016-03**（注入内容不超过合理上下文窗口限制）
  - Given：用户历史记忆积累后体积可能增大
  - When：系统执行注入
  - Then：注入内容不超过架构师定义的最大上下文摘要长度（具体阈值由 GROUP_B 确定）；超出时自动裁剪/摘要，不失败

---

### REQ-FUNC-017：用户记忆生命周期管理

**描述**：提供用户记忆的完整生命周期管理，包括记忆的查看（admin）、清空（用户自己或 admin）、以及用户账号注销时的记忆处置。

**来源**：用户需求方向（合规需求 + 账号删除时记忆处置）

**子需求分解**：

**REQ-FUNC-017a：用户账号注销时记忆清理**
- **AC-017a-01**
  - Given：FreeArk 用户账号被注销/删除
  - When：注销操作执行
  - Then：该用户的所有私有记忆数据（对话历史、个性化配置等）在合理时间内完成清理（同步或异步，由架构决策）；不遗留孤儿数据

**REQ-FUNC-017b：用户可自助清空自己的记忆**
- **AC-017b-01**
  - Given：已登录的 FreeArk 用户
  - When：用户主动请求清空与龙虾的历史记忆（通过前端操作或聊天指令）
  - Then：该用户的私有记忆被清空；下次对话龙虾从空白状态开始（对该用户）

**REQ-FUNC-017c：admin 角色可查看/清空任意用户记忆**
- **AC-017c-01**（合规/运维需求）
  - Given：FreeArk admin 用户
  - When：admin 通过管理界面或 API 查看用户 A 的记忆
  - Then：admin 可获取用户 A 的私有记忆内容（用于合规审计、客服支持等场景）

- **AC-017c-02**
  - Given：FreeArk admin 用户
  - When：admin 触发清空用户 A 的记忆操作
  - Then：用户 A 的所有私有记忆被清空；admin 操作有审计日志记录

---

## 3. 非功能需求

### REQ-NFR-010：记忆隔离的安全性

**描述**：任何 FreeArk 用户均不得通过 API、WS 消息、或其他技术手段访问他人的私有记忆数据。隔离必须在系统层面强制执行，而非仅依赖前端限制。

**来源**：用户原始需求（隔离是安全需求，非功能性约束）

**验收标准**：

- **AC-NFR-010-01**（API 层隔离）
  - Given：已登录的 FreeArk 用户 A（非 admin）
  - When：A 尝试通过任何 API 端点访问用户 B 的记忆数据
  - Then：系统返回 403 Forbidden 或等效的权限拒绝响应；不返回用户 B 的任何私有数据

- **AC-NFR-010-02**（WS 消息不跨用户）
  - Given：用户 A 的 ChatConsumer 实例
  - When：A 的消息被处理
  - Then：响应仅发送到 A 的 WS 连接，不广播到 B 的连接（此约束已由 ChatConsumer per-instance 架构满足，本 AC 验证新机制不破坏此约束）

---

### REQ-NFR-011：记忆隔离的性能影响

**描述**：per-user 记忆机制引入的额外延迟不超过指定阈值，不影响对话的响应体验。

**来源**：用户需求方向（可扩展性：10 用户、100 用户的开销）

**验收标准**：

- **AC-NFR-011-01**（记忆检索延迟）
  - Given：10 个并发 FreeArk 用户同时发起对话
  - When：系统为每个用户加载/注入历史记忆
  - Then：每个用户的记忆检索+注入操作耗时 ≤ 500ms（不计 LLM 本身延迟）

- **AC-NFR-011-02**（存储扩展性）
  - Given：100 个 FreeArk 用户，每人平均 50 次对话历史
  - When：系统正常运行
  - Then：存储开销在树莓派 Pi 5（4GB RAM）可接受范围内（具体阈值由 GROUP_B 在 tech_stack.md 中评估）

---

### REQ-NFR-012：人格骨架的完整性可审计性

**描述**：骨架文件的任何变更（授权的或未授权的）均应可被事后追溯，审计机制不依赖日志的连续性（防止日志被清除）。

**来源**：AC-015-02（机器可验证）扩展；用户需求（"可机器验证"）

**验收标准**：

- **AC-NFR-012-01**（哈希基准存储）
  - Given：骨架文件在初始部署时已计算哈希基准
  - When：运行巡检命令
  - Then：巡检命令将当前文件哈希与基准对比，输出 PASS（一致）或 FAIL（不一致）+ 变更文件列表

- **AC-NFR-012-02**（巡检可嵌入 CI/CD 或定期任务）
  - Given：巡检脚本已部署到树莓派
  - When：作为 cron 任务或 deployment 后置步骤执行
  - Then：脚本执行成功返回 0（PASS）或非零（FAIL），可被外部系统读取状态

---

### REQ-NFR-013：向后兼容性 — 不破坏 reasoning_stream 已部署功能

**描述**：本期记忆隔离方案不得破坏 freeark_lobster_reasoning_stream 已部署的 v1.3 adapter / v1.2 consumer / v1.1 ChatView.vue 的现有行为。

**来源**：用户强制约束（"不能破坏 reasoning_stream 已部署的 v1.3 adapter / v1.2 consumer 行为，向后兼容"）

**验收标准**：

- **AC-NFR-013-01**（reasoning 流式展示功能保持正常）
  - Given：本期记忆隔离方案部署后
  - When：FreeArk 用户发起对话
  - Then：`reasoning_token` / `reasoning_end` / `stream_token` / `stream_end` 的 WS 消息流仍按原协议工作；前端 reasoning 折叠展示功能正常

- **AC-NFR-013-02**（现有 34 个测试继续通过）
  - Given：本期新增代码部署后
  - When：运行 `python manage.py test api.tests.test_reasoning_stream`
  - Then：原 34 个测试全部通过（0 failures，0 errors）

---

### REQ-NFR-014：跨设备/跨浏览器一致性

**描述**：同一 FreeArk 用户从不同设备或浏览器登录时，看到的历史记忆是一致的（记忆与设备无关，与 FreeArk 账户关联）。

**来源**：用户需求方向（跨设备/跨浏览器登录时记忆的可见性）

**验收标准**：

- **AC-NFR-014-01**
  - Given：用户 A 在手机浏览器对话后，又在 PC 浏览器登录
  - When：用户 A 在 PC 端发起新对话
  - Then：龙虾能感知到（通过记忆注入）用户 A 之前在手机端聊过的内容

---

## 4. 约束与项目纪律（继承与新增）

### 4.1 继承约束（来自前序项目）

| 约束编号 | 内容 | 来源 |
|---------|------|------|
| C-001 | 禁止 Docker；部署一律 git pull | lobster-agent-api-channel |
| C-002 | ASGI/Uvicorn 单 worker | lobster-agent-api-channel |
| C-004 | OpenClaw 协议 v4 WS RPC，不存在 REST `/v1/agent/run/stream` | lobster-agent-api-channel |
| C-006 | commit 信息中文用 `git commit -F`，避免 PowerShell 5.1 编码问题 | lobster-agent-api-channel |
| C-008 | stream_chat yield 协议 `(kind, text)` 不可更改（reasoning_stream 已上线） | freeark_lobster_reasoning_stream |
| C-009 | `reasoning_effort` 通过 env var 控制，不修改 OpenClaw 全局 agent 配置 | freeark_lobster_reasoning_stream |

### 4.2 新增约束（本期）

| 约束编号 | 内容 |
|---------|------|
| C-012 | 不能动 OpenClaw Gateway 协议（loopback :18789 是外部依赖，不归 FreeArk 管） |
| C-013 | 人格锁定方案必须机器可验证（文件 hash / Git diff 等），不能仅靠人工约定 |
| C-014 | 架构决策中涉及 OpenClaw 能力（如 agent.create / workspace 切换工具）的方案，必须在 GROUP_C 启动前标注"需生产探查验证" |
| C-015 | 记忆隔离实现不得修改前序项目 freeark_lobster_reasoning_stream/ 的任何规格文档 |
| C-016 | 测试文件一律放 `api/tests/test_*.py`（PM-DEC-002 教训：api/tests/ 包与 api/tests.py 文件冲突规避） |

---

## 5. 开放问题（需求层不能解决，待 GROUP_B 明确）

| 问题编号 | 问题描述 | 影响需求 |
|---------|---------|---------|
| OQ-001 | OpenClaw workspace 结构是否支持 per-user 目录（`workspace_<user_id>/`）或子目录隔离？需生产探查验证。 | REQ-FUNC-013~016 的架构选择 |
| OQ-002 | OpenClaw `agent.create` 工具是否可用且支持每用户创建独立 agent 实例？需生产探查验证。 | GROUP_B ADR 方案 B |
| OQ-003 | 历史记忆存储的最大合理体积是多少？（影响裁剪策略和 AC-016-03） | REQ-NFR-011 |
| OQ-004 | 记忆注入是通过修改 message 前缀、系统提示词扩充，还是 OpenClaw 文件系统操作？ | REQ-FUNC-016 的实现机制 |
| OQ-005 | 用户清空记忆（REQ-FUNC-017b）的 UX 入口是前端按钮、聊天指令还是 API？优先级如何？ | REQ-FUNC-017b |
| OQ-006 | admin 查看/清空记忆（REQ-FUNC-017c）通过现有 Django admin 还是新增 API 端点？ | REQ-FUNC-017c |

---

## 6. ID 映射总表（本期新增，用于跨文档追溯）

| 需求 ID | 类型 | 简述 | 对应 US | 对应 GROUP_B ADR（待定） |
|--------|------|------|--------|------------------------|
| REQ-FUNC-013 | 功能 | per-user 对话历史记忆持久化 | US-MEM-001, US-MEM-002 | TBD |
| REQ-FUNC-014 | 功能 | per-user 记忆隔离边界维护 | US-MEM-003, US-MEM-004 | TBD |
| REQ-FUNC-015 | 功能 | 人格骨架锁定（防漂移） | US-MEM-005, US-MEM-006 | TBD |
| REQ-FUNC-016 | 功能 | 记忆读取注入机制 | US-MEM-007 | TBD |
| REQ-FUNC-017 | 功能 | 用户记忆生命周期管理 | US-MEM-008, US-MEM-009, US-MEM-010 | TBD |
| REQ-NFR-010 | 非功能 | 记忆隔离的安全性 | — | TBD |
| REQ-NFR-011 | 非功能 | 性能与可扩展性 | — | TBD |
| REQ-NFR-012 | 非功能 | 人格骨架完整性可审计性 | — | TBD |
| REQ-NFR-013 | 非功能 | 向后兼容 reasoning_stream | — | TBD |
| REQ-NFR-014 | 非功能 | 跨设备/跨浏览器一致性 | — | TBD |
