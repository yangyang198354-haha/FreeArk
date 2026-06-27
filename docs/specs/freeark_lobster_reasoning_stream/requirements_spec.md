# 需求规格说明书 — 方舟智能体 Reasoning 流式展示

```
file_header:
  document_id: REQ-SPEC-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_requirement_analyst (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-25
  context_snapshot: >
    FreeArk v0.5.9+，OpenClaw 2026.5.20，DeepSeek v4-flash（reasoning 模型），
    WS Gateway RPC v4，ChatConsumer v1.1（MOD-BE-01），
    OpenClawAdapter v1.2（MOD-BE-02），ChatView.vue 现有实现
  depends_on:
    - REQ-SPEC-LOBSTER-001（前期 API 通道需求，REQ-FUNC-001~007 已定义）
    - PROBES-LOBSTER-001（OpenClaw 实测探针报告）
  id_continuation: >
    REQ-FUNC-008 起（接续 lobster-agent-api-channel 的 REQ-FUNC-007）；
    REQ-NFR-005 起（接续 REQ-NFR-004）；
    ADR-004 起（接续 ADR-003）
```

---

## 0. 文档说明

本文档是 **增量需求规格**，仅描述本期新增内容。所有 REQ-FUNC-001~007、REQ-NFR-001~004、ADR-001~003 定义保持不变，继承自 `docs/sdlc/lobster-agent-api-channel/requirements_spec.md`。

本期项目代号：**freeark_lobster_reasoning_stream**  
本期核心目标：消除用户在 reasoning 阶段面对空气泡的等待体验，实时展示 AI 思考过程，并通过降低 reasoning_effort 加速首 token 到达。

---

## 1. 背景与用户痛点

### 1.1 用户原始反馈

> "前端 UI 和智能体聊天其实不是真正的流式，发出消息后很久才能收到消息，也看不到像 deepseek 一样的思考过程，体验很不好。"

### 1.2 诊断结论（已验证，可直接作为需求输入）

| 编号 | 诊断发现 | 来源 |
|------|---------|------|
| DIAG-01 | 链路本身是真流式（adapter→consumer→nginx WS→Vue 每段 token-by-token 即转发），不是架构缺陷 | 代码审查 |
| DIAG-02 | `deepseek-v4-flash` 是 reasoning 模型，先长时间思考再输出 content delta；思考阶段 content 为空 | 模型文档 |
| DIAG-03 | `openclaw_adapter.py` v1.2（行 267-270）只读 `event:chat` 帧的 `payload.deltaText`，未读 reasoning 字段 | 代码行 261-291 |
| DIAG-04 | `ChatConsumer._handle_chat` 只发 `stream_token` 一种类型，无 reasoning 类型 | consumers.py 行 151-154 |
| DIAG-05 | `ChatView.vue` 在空 content 时显示「正在思考...」静态文字，reasoning 阶段用户面对静态气泡 | ChatView.vue 行 46 |
| DIAG-06 | OpenClaw 2026.5.20 在 `event:chat` `state:delta` 的 payload 里携带 reasoning 增量的字段名**尚未实测**，需前置探查 | 待验证 |

---

## 2. 本期功能需求

### REQ-FUNC-008：OpenClaw reasoning 字段名实测探查（前置任务）

**描述**：在生产 `openclaw_adapter.py` 中加入临时 `logger.info` 打印，捕获至少 1 次 `event:chat` `state:delta` 的完整 payload JSON，确定 reasoning 增量的字段名。

**来源**：DIAG-06；用户方案 A 描述（"字段名探查作为前置任务"）

**候选字段名**：`reasoningDelta`、`thinkingDelta`、`payload.kind == 'reasoning'` + 复用 `deltaText`、或其他。

**验收标准**：

- **AC-008-01**
  - Given：生产环境与 DeepSeek v4-flash 完成一次完整对话（包含 reasoning 阶段）
  - When：`APP_LOG_LEVEL=INFO` 或临时 logger 激活，查看 openclaw_adapter 日志
  - Then：日志中出现至少 1 条包含完整 `event:chat` `state:delta` payload 的 INFO 行，其内容可确定 reasoning 字段名

- **AC-008-02**
  - Given：探查结果已确认字段名
  - When：架构师据此编写架构设计文档
  - Then：architecture_design.md 中 ADR-006（adapter 字段名常量）明确引用该字段名，并标注"来源：AC-008-01 实测"

**约束**：临时 logger 仅记录字段名/结构，**不打印 token 文本本身**（隐私约束，见 REQ-NFR-007）；探查完成后立即移除临时日志行，替换为正式 v1.3 实现。

---

### REQ-FUNC-009：Adapter 扩展 reasoning/content 双流 yield 协议

**描述**：`OpenClawAdapter.stream_chat` 从 `yield str` 改为 `yield (kind, text)`，`kind ∈ {'reasoning', 'content'}`，使调用方能区分思考过程增量与正式回答增量。

**来源**：用户方案 A — 后端部分

**验收标准**：

- **AC-009-01**
  - Given：adapter 连接 OpenClaw，DeepSeek v4-flash 进入 reasoning 阶段
  - When：`event:chat` `state:delta` 帧中包含 reasoning 字段（字段名由 AC-008-01 确定）
  - Then：adapter yield `('reasoning', <text>)`，不 yield `('content', ...)`

- **AC-009-02**
  - Given：DeepSeek 结束 reasoning，开始输出正式回答
  - When：`event:chat` `state:delta` 帧中包含 `deltaText`（正式回答增量）
  - Then：adapter yield `('content', <text>)`

- **AC-009-03**
  - Given：adapter 的 `stream_chat` 改为 yield 二元组
  - When：`ChatConsumer._handle_chat` 调用 `async for (kind, text) in stream_chat(...)`
  - Then：代码正确解包二元组，不产生 `TypeError`

- **AC-009-04**（可观测性）
  - Given：一次完整对话结束
  - When：检查 INFO 级日志
  - Then：日志包含 `reasoning_tokens=<N>` 和 `content_tokens=<M>` 以及各自耗时段（精确到秒），**不含 token 文本本身**

---

### REQ-FUNC-010：ChatConsumer 转发 reasoning/content 分类消息

**描述**：`ChatConsumer._handle_chat` 按 yield 二元组的 `kind` 分发两种 WebSocket 消息类型，并在 reasoning 结束时发送一次 `reasoning_end` 信号。

**来源**：用户方案 A — 后端部分

**向后兼容硬约束**：`stream_token` 消息类型必须保留且语义不变（仅转发 content 增量），旧版前端收到 `reasoning_token` 会走 `default` 分支被忽略，不影响功能。

**验收标准**：

- **AC-010-01**（reasoning_token 转发）
  - Given：adapter yield `('reasoning', text)`
  - When：ChatConsumer 处理该 yield
  - Then：前端收到 `{"type": "reasoning_token", "token": "<text>"}`

- **AC-010-02**（content token 转发，向后兼容）
  - Given：adapter yield `('content', text)`
  - When：ChatConsumer 处理该 yield
  - Then：前端收到 `{"type": "stream_token", "token": "<text>"}` — 与现有协议一致

- **AC-010-03**（reasoning_end 信号）
  - Given：在所有 `('reasoning', ...)` yield 之后，第一个 `('content', ...)` yield 到达之前（或 reasoning 阶段结束时）
  - When：ChatConsumer 检测到 kind 从 reasoning 切换为 content
  - Then：先发送 `{"type": "reasoning_end"}` 一次，再发送 `{"type": "stream_token", "token": "..."}`

- **AC-010-04**（stream_end 保留）
  - Given：adapter 生成器耗尽（`state:final`）
  - When：ChatConsumer 正常结束
  - Then：发送 `{"type": "stream_end"}` — 与现有协议一致

- **AC-010-05**（旧前端兼容性）
  - Given：旧版前端（`handleMessage` 的 `switch` 中无 `reasoning_token` / `reasoning_end` 分支）
  - When：后端发送 `reasoning_token` 或 `reasoning_end`
  - Then：旧前端 `default` 分支静默忽略，`stream_token` 和 `stream_end` 处理逻辑不受影响，页面功能正常

---

### REQ-FUNC-011：前端 ChatView.vue 实时展示思考过程

**描述**：助手气泡内顶部增加可折叠的「思考过程」区域，实时显示 reasoning_token 流，reasoning_end 后自动折叠，正式回答在折叠区下方正常展示。

**来源**：用户方案 A — 前端部分

**验收标准**：

- **AC-011-01**（首个 reasoning_token 触发显示）
  - Given：用户发送消息，助手气泡已创建（content 为空）
  - When：前端收到第一个 `reasoning_token`
  - Then：「正在思考...」静态占位**立即消失**；助手气泡顶部出现展开的 `<details>` 区域，标题为「🧠 思考过程」；reasoning 文字以浅灰斜体追加

- **AC-011-02**（reasoning 区域自动折叠）
  - Given：reasoning 文字正在追加
  - When：前端收到 `reasoning_end`
  - Then：`<details>` 区域自动折叠（`open` 属性移除）；折叠后用户仍可点击展开查看

- **AC-011-03**（正式回答区域）
  - Given：`reasoning_end` 已收到
  - When：前端收到 `stream_token`（content 增量）
  - Then：content 追加到 `<details>` 下方，样式与现有 `stream_token` 渲染一致；流式光标在 content 区域显示

- **AC-011-04**（消息数据结构扩展）
  - Given：助手消息对象创建
  - When：代码初始化消息
  - Then：消息结构为 `{ role: 'assistant', content: '', reasoning: '', streaming: true, reasoningStreaming: true }`

- **AC-011-05**（无 reasoning 时降级）
  - Given：对话模型不产生 reasoning（如配置变更后）
  - When：从未收到 `reasoning_token`，直接收到 `stream_token`
  - Then：「🧠 思考过程」区域不显示（reasoning 为空，`<details>` 不渲染）；行为与原版完全一致

- **AC-011-06**（样式约束）
  - Given：reasoning 文字渲染
  - When：用户查看气泡
  - Then：reasoning 文字颜色为浅灰（`#94A3B8` 或接近色），字体为斜体，区别于正式回答的主文字颜色

---

### REQ-FUNC-012：reasoning_effort 降级配置（方案 B）

**描述**：为 OpenClaw 调用 DeepSeek v4-flash 时增加 `reasoning_effort: "low"` 参数，缩短 reasoning 阶段耗时。配置位置由架构师确认（优先 adapter 侧 params，避免污染全局 agent 配置）。

**来源**：用户方案 B

**验收标准**：

- **AC-012-01**（参数生效）
  - Given：`OPENCLAW_REASONING_EFFORT=low`（或架构师确定的等效配置）已设置
  - When：发起一次对话
  - Then：`event:chat` `state:delta` 中 reasoning 阶段耗时（基线 T0 秒，取 3 次测量均值）下降 ≥ 50%

- **AC-012-02**（基线测量）
  - Given：未设置 reasoning_effort（默认 medium/high）
  - When：连续 3 次对话（问题为"介绍一下三恒系统"）
  - Then：记录每次从 `chat.send` 到首个 content token 到达的耗时（T1、T2、T3），计算均值 T0 作为基线，写入 tech_stack.md NFR 基线表

- **AC-012-03**（环境变量控制）
  - Given：`OPENCLAW_REASONING_EFFORT` 未设置或为空
  - When：adapter 初始化
  - Then：不传递 `reasoning_effort` 参数给 OpenClaw（回退 DeepSeek 默认行为，不硬编码）

- **AC-012-04**（不影响其他模型）
  - Given：`reasoning_effort` 配置只针对 `chat.send` 请求
  - When：DeepSeek v4-flash 调用时
  - Then：只有 `deepseek-v4-flash` 模型的调用携带该参数（由 adapter 控制，不修改 OpenClaw 全局 agent 配置中的 `models.json`）

---

## 3. 非功能需求

### REQ-NFR-005：兼容性 — 向后兼容旧前端

**描述**：后端新增 `reasoning_token` / `reasoning_end` 消息类型，不破坏旧版前端（仅处理 `stream_token` / `stream_end`）的正常工作。

**来源**：项目纪律 — 向后兼容是硬约束

**验收标准**：

- **AC-NFR-005-01**
  - Given：旧版前端（无 `reasoning_token` 分支）已连接到已升级的后端
  - When：后端发送完整的 reasoning + content 对话流
  - Then：旧前端仅渲染 content 部分，reasoning 帧被 `default` 分支忽略，页面无异常，对话正常结束

---

### REQ-NFR-006：性能 — 首个 reasoning_token 延迟

**描述**：用户发送消息后，前端收到第一个 `reasoning_token` 的端到端延迟目标 ≤ 2 秒（生产网络 loopback+WS 延迟之和）。

**来源**：用户指定的非功能要求

**验收标准**：

- **AC-NFR-006-01**
  - Given：FreeArk 后端和 OpenClaw 均运行在 Pi（loopback 通信）
  - When：用户发送一条消息，OpenClaw 调用 DeepSeek v4-flash
  - Then：从前端 `ws.send` 到前端 `onmessage` 收到第一个 `reasoning_token`，端到端延迟 ≤ 2s（不含 DeepSeek 自身启动 reasoning 的时间，仅度量 FreeArk 链路透传延迟）

**注**：此 NFR 度量 FreeArk 链路本身的透传性能（不引入额外缓冲），不约束 DeepSeek 模型本身的 reasoning 启动延迟。

---

### REQ-NFR-007：安全 — reasoning 内容不含敏感信息

**描述**：adapter 透传 reasoning 文本时不做内容审计，但严格保证：
1. system prompt 不出现在 reasoning 流中（OpenClaw/DeepSeek 行为约束）。
2. OpenClaw gateway token 不出现在任何 yield 的 tuple 中。
3. 日志不打印 token 文本本身（无论 reasoning 还是 content）。

**来源**：用户指定的安全非功能要求；沿用 ADR-001（无状态约束）

**验收标准**：

- **AC-NFR-007-01**
  - Given：INFO 级日志激活
  - When：对话完成，查看 `api.openclaw_adapter` 日志
  - Then：日志中不出现 token 文本，仅出现计数类摘要（`reasoning_tokens=N, content_tokens=M`）

- **AC-NFR-007-02**
  - Given：ChatConsumer 收到 `reasoning_token` 并转发
  - When：前端显示 reasoning 内容
  - Then：reasoning 内容中不包含 `Authorization:` / `Bearer ` 等 token 模式（由 OpenClaw 模型层保证，FreeArk 不做正文过滤）

---

### REQ-NFR-008：可观测性 — reasoning/content 分段统计

**描述**：每次对话结束，adapter INFO 日志包含 reasoning 阶段 token 数、content 阶段 token 数、各阶段耗时（精确到毫秒），不含文本内容。

**来源**：用户指定的可观测要求

**验收标准**：

- **AC-NFR-008-01**
  - Given：`APP_LOG_LEVEL=INFO`
  - When：一次完整对话结束（`state:final`）
  - Then：`api.openclaw_adapter` 输出一行 INFO 日志，格式如：
    `stream_complete session=<key[:8]> reasoning_tokens=<N> content_tokens=<M> reasoning_ms=<T1> content_ms=<T2> total_ms=<T3>`

---

### REQ-NFR-009：多用户隔离 — reasoning 不持久化

**描述**：reasoning 流与 content 流一样，仅在当前 WebSocket 连接内存中存在，不写入数据库、不写入文件、不跨用户共享。

**来源**：沿用 ADR-001 无状态约束；用户明确指定

**验收标准**：

- **AC-NFR-009-01**
  - Given：两个用户同时进行 reasoning 对话
  - When：用户 A 的 reasoning 流在 ChatConsumer A 的实例中
  - Then：ChatConsumer B 的实例中不存在用户 A 的 reasoning 数据（各 Consumer 实例完全隔离）

---

## 4. 约束与项目纪律（继承与新增）

### 4.1 继承约束（来自 lobster-agent-api-channel）

| 约束编号 | 内容 |
|---------|------|
| C-001 | 禁止 Docker；部署一律 git pull |
| C-002 | ASGI/Uvicorn 单 worker（不增加 worker 数） |
| C-003 | `ALLOWED_HOSTS` 含 `192.168.31.51` |
| C-004 | OpenClaw 协议 v4 WS RPC，不存在 REST `/v1/agent/run/stream` |
| C-005 | WS 集成测试需用 `TransactionTestCase`（Django Channels 约束） |
| C-006 | commit 信息中文用 `git commit -F` 或 Bash 工具，避免 PowerShell 5.1 编码问题 |
| C-007 | OpenClaw gateway token 不出现在日志 WARNING 级及以上，不出现在任何 yield 内容中 |

### 4.2 新增约束（本期）

| 约束编号 | 内容 |
|---------|------|
| C-008 | `stream_chat` yield 协议从 `str` 改为 `(kind, text)` 后，`ChatConsumer` 必须同步更新解包逻辑，不得保留向前兼容的"兼容两种格式"分支（降低复杂度） |
| C-009 | `reasoning_effort` 通过环境变量 `OPENCLAW_REASONING_EFFORT` 控制，adapter 读取后透传；不修改 OpenClaw 全局 agent 配置文件 `models.json` |
| C-010 | 前端 `<details>` 折叠组件使用原生 HTML，不引入新的 JS 库或 Element Plus 新组件（保持零新依赖） |
| C-011 | reasoning 文本不做 Markdown 渲染（与 content 保持一致，目前均以 `white-space: pre-wrap` 展示） |

---

## 5. ID 映射总表（本期新增，用于跨文档追溯）

| 需求 ID | 类型 | 简述 | 对应 ADR | 对应 MOD |
|--------|------|------|---------|---------|
| REQ-FUNC-008 | 功能 | reasoning 字段名实测探查 | ADR-006 | MOD-BE-02 v1.3 |
| REQ-FUNC-009 | 功能 | adapter yield (kind, text) 协议 | ADR-006 | MOD-BE-02 v1.3 |
| REQ-FUNC-010 | 功能 | consumer 转发分类消息 + reasoning_end | ADR-005, ADR-007 | MOD-BE-01 v1.2 |
| REQ-FUNC-011 | 功能 | 前端实时展示思考过程 | ADR-007 | MOD-FE-01 |
| REQ-FUNC-012 | 功能 | reasoning_effort 配置 | ADR-008 | MOD-BE-02 v1.3 |
| REQ-NFR-005 | 非功能 | 向后兼容旧前端 | ADR-007 | MOD-BE-01, MOD-FE-01 |
| REQ-NFR-006 | 非功能 | 首 reasoning_token 延迟 ≤ 2s | — | MOD-BE-02, MOD-BE-01 |
| REQ-NFR-007 | 非功能 | reasoning 不含敏感信息 | ADR-005 | MOD-BE-02 v1.3 |
| REQ-NFR-008 | 非功能 | reasoning/content 分段统计日志 | — | MOD-BE-02 v1.3 |
| REQ-NFR-009 | 非功能 | reasoning 不持久化，多用户隔离 | ADR-001（继承） | MOD-BE-01 |
