<file_header>
  project: v1.12.0_chat_persona_voice
  document_type: architecture_design
  status: DRAFT
  author_agent: sub_agent_system_architect
  created_at: 2026-07-05T00:00:00Z
  version: 0.1.0
  parent_invocation: GROUP_B_PHASE_03_04
  dependencies:
    - requirements_spec.md (v0.1.0, APPROVED)
</file_header>

# 架构设计文档 — v1.12.0 方舟副官人格与语音输入

## 1. 架构概览

### 1.1 架构风格

本次迭代采用**分层模块化单体**架构，遵循既有 Django + uni-app 技术栈，在现有架构基础上进行增量演进。变更分布在三个层次：

| 层次 | 变更类型 | 影响范围 |
|------|---------|---------|
| **表示层** (miniprogram) | 增量修改 | chat/index.vue 语音重新实现、useOwnerStore 集成、新增 usePersonaStore |
| **应用层** (Django REST/WS) | 增量修改 | orchestrator.py 上下文注入、新增 persona API |
| **数据层** (PostgreSQL) | 增量修改 | CustomUser 新增 persona JSONField、migration |

### 1.2 系统层次结构

```
┌─────────────────────────────────────────────────────────────────┐
│                     微信小程序（uni-app/Vue 3）                    │
│                                                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ chat/index.vue│ │ useOwnerStore│ │ useChatStore              │ │
│  │  + VoiceInput │ │ (bindings,   │ │ + persona (新增字段)       │ │
│  │   (新组件)     │ │  activeSP)   │ │ + cabinStatus (新增)       │ │
│  └──────┬───────┘ └──────┬───────┘ └────────────┬─────────────┘ │
│         │                │                       │                │
│         │   ChatWebSocket │  /ws/miniapp/chat/   │  HTTP api.js  │
└─────────┼────────────────┼───────────────────────┼────────────────┘
          │                │                       │
    ══════╪════════════════╪═══════════════════════╪════════════════
          │                │                       │
┌─────────┼────────────────┼───────────────────────┼────────────────┐
│         ▼                ▼                       ▼                │
│  Django Channels (ASGI)                    Django REST (WSGI)     │
│  ┌───────────────┐                        ┌──────────────────┐   │
│  │MiniAppChat    │                        │ /api/miniapp/     │   │
│  │Consumer       │                        │   persona/       │   │
│  │ user_scope ───┼──── LangGraph ────┐     │   GET/PUT (新增)  │   │
│  └───────────────┘                   │     └──────────────────┘   │
│                                      ▼                            │
│  ┌──────────────────────────────────────────────┐                │
│  │         LangGraph Orchestrator                │                │
│  │  ┌────────┐  ┌────────┐  ┌────────────────┐  │                │
│  │  │ route  │→ │ expert │→ │   aggregate    │  │                │
│  │  └────────┘  │(fanout)│  └────────────────┘  │                │
│  │              └────────┘                       │                │
│  │         cabin_context_inject (新增)           │                │
│  │         persona_prompt_load (新增)            │                │
│  └──────────────────────────────────────────────┘                │
│                                                                   │
│  ┌──────────────────┐                                            │
│  │ PostgreSQL        │                                            │
│  │  CustomUser       │  + persona JSONField (新增)                 │
│  │    avatar_url     │                                            │
│  │    nickname       │                                            │
│  │    + persona      │  {"greeting_style":"...","tone_style":"..."}│
│  └──────────────────┘                                            │
└───────────────────────────────────────────────────────────────────┘
```

### 1.3 选型依据

| 关键需求 | 架构选择 | 依据 |
|---------|---------|------|
| REQ-NFUNC-004 (向下兼容) | 增量修改现有模块，不替换 | 6 项 WS 协议帧保持兼容，仅追加新字段 |
| REQ-NFUNC-003 (事务持久化) | PostgreSQL JSONField on CustomUser | 同一事务写入，无需额外表 join |
| CON-01 (微信原生/官方插件) | 微信同声传译插件 (OQ-04) | 零后端新增、零 pip install、微信官方 |
| CON-03 (Django ORM 兼容) | JSONField + Django ORM | 原生支持 PostgreSQL jsonb 类型 |

---

## 2. 架构决策记录 (ADR)

---

### ADR-001: 人格偏好数据模型

- **Status**: Accepted
- **Context**: REQ-FUNC-004 要求人格偏好跨会话持久化；REQ-NFUNC-003 要求事务性保障；OQ-02 PM 已确认扩展 UserProfile 加 JSON 字段。当前 CustomUser 已包含 avatar_url、nickname 等用户级字段，无独立 UserProfile 表。
- **Options**:
  - **Option A: 扩展 CustomUser 增加 persona JSONField** — 在 CustomUser 模型新增 `persona = JSONField(default=dict, blank=True)`，存储 `{"greeting_style": "...", "tone_style": "..."}`。与现有 avatar_url/nickname 并列。优点：用户级数据同一行、无 join、单次查询即可获取；migration 简单（仅新增字段）。缺点：JSONField 跨字段校验需应用层实现。
  - **Option B: 新建 UserPersona 模型做 OneToOneField 关联** — 创建独立表 `api_userpersona` 关联 CustomUser。优点：结构更规范化，便于扩展更多人格维度。缺点：额外 join 查询、增加 migration 复杂度、现有 serde 层需要适配新关系（CurrentUserSerializer 已有嵌套序列化逻辑）。
- **Decision**: 选择 Option A — 扩展 CustomUser 增加 `persona JSONField`。OQ-02 确认"非新建表"，v1 人格维度仅 greeting_style + tone_style 两个键，JSONField 足够；CustomUser 已有 avatar_url/nickname 等用户资料字段，persona 与它们语义平级，放同一模型符合现有数据组织模式。QPS 极低（每会话仅 WS connect 时一次读取），join 开销可忽略，但 Option A 的 migration 简单性在灰度部署中风险更低。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-004/REQ-NFUNC-003，数据与用户同生命周期的 ACID 保证；migration 仅一个 ALTER TABLE ADD COLUMN。
  - 负向: JSONField schema 在 DB 层无强制约束，应用层需校验 greeting_style/tone_style 键的有效性；未来若人格维度增长到数十个字段需迁移到独立表。

---

### ADR-002: 房号上下文注入 LLM 的方式

- **Status**: Accepted
- **Context**: REQ-FUNC-007 要求已绑定座舱的房号自动注入对话上下文；REQ-FUNC-008 要求多座舱场景注入全部房号。OQ-03 PM 已确认"独立系统消息块注入"。当前 orchestrator._expert 节点在调用 LLM 前构造消息列表 msgs（第 464-467 行），系统提示来自 EXPERT_PROMPTS + _date_hint()。
- **Options**:
  - **Option A: 独立 SystemMessage 块追加到消息列表** — 在 msgs 列表的首个 SystemMessage 之后追加一个独立的 SystemMessage("当前用户绑定的房间：3-1-7-702, 5-2-1-101")。优点：与主系统提示解耦、不影响现有提示语义、注入/移除简单；缺点：增加一条消息的 token 开销。
  - **Option B: 系统消息前缀注入（类似 [__freeark_user__:xxx] 格式）** — 在首个 SystemMessage 的 content 顶部追加 "[__freeark_cabin__:3-1-7-702]" 伪标签。优点：不增加消息数量、token 更少；缺点：修改系统提示正文，对 ExpertSpec.fallback_prompt 和 agents/ 文件内系统提示有侵入性；伪标签格式可能被 LLM 误解析。
- **Decision**: 选择 Option A — 独立 SystemMessage 块注入。OQ-03 明确采用"作为独立系统消息块追加"方案。独立消息块与主系统提示解耦，注入/移除不修改 agents/ 目录下的提示文件，也不修改 ExpertSpec 注册表。后文称之为 `cabin_context_message`，格式为 `"当前用户绑定的房间：[房号列表]；若未绑定则为'无'。回答用户关于房间的问题时请根据此信息定位具体房间。"`。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-007/REQ-FUNC-008；与主提示完全解耦；单一注入点（orchestrator._expert 节点）易于维护。
  - 负向: 每个 expert 调用额外消耗 ~20-100 tokens（取决于绑定数量）；多 expert fan-out 时每个分支都会收到该消息（冗余但不影响正确性）。

---

### ADR-003: 语音转文字方案选型

- **Status**: Accepted
- **Context**: REQ-FUNC-010/011/012/013 要求实现语音输入，含录音交互、语音转文字、异常降级；REQ-NFUNC-001 要求采样率 >= 16000 Hz；REQ-NFUNC-005 要求音频不落盘；CON-01 约束仅使用微信原生 API 或官方插件。OQ-04 PM 已确认微信同声传译插件方案。
- **Options**:
  - **Option A: 微信同声传译插件 (wx-plugin://wxeb9a1a3c3cc0a0f3)** — 前端直接调用插件的 speechToText API，录音 + 识别均在微信客户端完成。优点：零后端新增、零 pip install、免费、微信官方维护、隐私合规（音频不出微信端）；缺点：仅支持普通话、无法定制 ASR 模型、识别结果不可审计。
  - **Option B: 后端 ASR 服务（百度/讯飞/腾讯云）** — 前端使用 RecorderManager 录音，通过 HTTP 上传音频到后端，后端调用第三方 ASR API。优点：支持多语种、可选模型、可记录审计日志；缺点：需要后端新增 ASR 集成模块（违反"零后端新增"目标）、音频传输有隐私风险、需要 api key 管理和费用预算。
- **Decision**: 选择 Option A — 微信同声传译插件 (speechToText)。OQ-04 确认"微信同声传译插件（客户端方案）"。这使语音输入成为纯前端功能，满足 REQ-NFUNC-005（音频不落盘——录音和识别均在微信沙箱内完成），满足 CON-01（微信官方插件），满足"零后端新增"的约束。插件 appId: wxeb9a1a3c3cc0a0f3，版本跟随微信客户端自动更新。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-010~013、REQ-NFUNC-001/005；零后端变更、零 API 费用；隐私合规开箱即用。
  - 负向: 仅支持普通话（不支持方言/英语），若未来有多语种需求需切换方案；插件可用性依赖微信平台，若插件下线需迁移；微信插件需在 app.json 中声明，小程序提审需通过插件使用说明。

---

### ADR-004: 多座舱绑定的上下文注入策略

- **Status**: Accepted
- **Context**: REQ-FUNC-008 要求多座舱绑定注入全部房号；OQ-05 PM 已确认"多座舱默认用首页 activeSpecificPart"优先策略。UserScope 已实现 is_multi_bound()（user_scope.py 第 51-53 行），bound_specific_parts 为 frozenset。
- **Options**:
  - **Option A: 优先 activeSpecificPart，备选列出全部** — cabin_context_message 首先标注"当前房间：{activeSpecificPart}"（若存在）；若多绑定额外附"其他绑定房间：{others}"。优点：与 OQ-05 决策一致、AI 优先聚焦活跃房间、减少困惑；缺点：非活跃房间信息可能被 LLM 忽略。
  - **Option B: 列出全部绑定，不区分优先级** — cabin_context_message 为"用户绑定的房间：A, B, C"。优点：AI 看到完整信息可自行判断；缺点：当用户问"房间温度多少"时 AI 需反问用户具体哪个房间（增加一轮交互），与 OQ-05-c 决策冲突。
  - **Option C: 仅注入 activeSpecificPart，忽略其他** — 只注入单个房间，多绑定的其余房间不注入上下文。优点：最简单；缺点：用户切换 activeSpecificPart 后需断开重连才能刷新上下文，与 REQ-FUNC-008 冲突。
- **Decision**: 选择 Option A — activeSpecificPart 优先策略。OQ-05 明确"默认使用首页 activeSpecificPart"。实现上：MiniAppChatConsumer 的 connect() 从 OwnerStore 的 activeSpecificPart 前端字段读取当前选中房间，构建 UserScope 时同时保留 bound_specific_parts 全量；cabin_context_message 格式为"当前活跃房间：3-1-7-702；您还绑定了以下房间：5-2-1-101"。若 activeSpecificPart 为空（用户未在首页选择），降级为列出全部绑定。
- **Consequences**:
  - 正向: 满足 REQ-FUNC-008 + OQ-05；减少"哪个房间"反问；上下文聚焦用户当前关注点。
  - 负向: activeSpecificPart 来源是前端 uni.storage（非后端权威），若用户清除缓存或换设备，首次连接可能为空，退化为列出全部绑定；需前端在 WS connect 时额外传递 active_specific_part 参数。

---

### ADR-005: 人格偏好 API 设计

- **Status**: Accepted
- **Context**: REQ-FUNC-003 要求首次对话可设置人格偏好；REQ-FUNC-004 要求持久化；OQ-06 确认"支持后续修改"，US-003 升级为 Should Have。需要后端提供 persona 的读写 API。
- **Options**:
  - **Option A: 扩展现有 /api/miniapp/profile/update/ 端点** — 在 profile update 端点中增加 persona 字段处理（与 avatar/nickname 并列）。优点：复用现有认证/序列化逻辑、减少新路由；缺点：profile/update/ 的语义是"个人资料"，persona 作为"对话偏好"放入略显语义混杂。
  - **Option B: 新建独立 /api/miniapp/persona/ GET + PUT 端点** — 独立端点只服务于 persona 的读写。优点：关注点分离、未来可扩展更多人格维度；缺点：新增 2 个路由 + 视图 + 序列化器。
- **Decision**: 选择 Option B — 新建独立 /api/miniapp/persona/ 端点。persona 语义上与 avatar/nickname 不同（前者是 LLM 对话风格配置，后者是个人资料展示），分离便于独立版本演进。端点设计: `GET /api/miniapp/persona/` → 200 `{greeting_style, tone_style}`；`PUT /api/miniapp/persona/` body: `{greeting_style, tone_style}` → 200。权限: IsOwnerUser（复用 urls_miniapp.py 既有权限模式）。无 persona 记录时 GET 返回 `{greeting_style: null, tone_style: null}`。
- **Consequences**:
  - 正向: 满足 OQ-06（后续修改）和 REQ-FUNC-004（持久化）；独立端点支持未来的 frontend 设置页集成。
  - 负向: 新增 2 个路由增加 urls_miniapp.py 行数 ~15 行。

---

### ADR-006: 前端人格状态管理

- **Status**: Accepted
- **Context**: REQ-FUNC-001/005 要求默认人格展示和回访自动加载；CON-04 要求新增状态遵循 Pinia store 模式。当前前端 store 有 useAuthStore（token/userInfo）、useChatStore（messages/sessionKey）、useOwnerStore（bindings/device data）。persona 数据有独立的生命周期（WS connect 时加载一次，用户修改时更新），不宜放入 chat 或 owner store。
- **Options**:
  - **Option A: 扩展 useChatStore 增加 persona 字段** — 在 useChatStore state 中新增 `persona: {greeting_style: null, tone_style: null}`。优点：persona 直接影响聊天行为，与 chat store 关联自然。缺点：useChatStore 职责开始膨胀（已管理 messages/wsConnected/sessionKey/sessionList）。
  - **Option B: 新建独立的 usePersonaStore** — 新建 `miniprogram/store/persona.js`，包含 persona 数据、loadPersona() action、缓存。优点：单一职责、清晰边界、persona 数据独立缓存。缺点：新增一个 store 文件（~50 行），增加代码量。
- **Decision**: 选择 Option A — 扩展 useChatStore。persona 与聊天行为的耦合度高：persona 数据影响问候语展示（REQ-FUNC-001）、影响前端首次对话判断逻辑（US-001 的 AC-001-01 需感知是否有历史会话 + persona 是否已设置）。chat store 已经是聊天页的核心状态容器，persona 字段天然属于此上下文。新增独立 store 带来的 cross-store 同步复杂度（chat 页需要同时 watch personaStore 和 chatStore）高于在 chat store 中新增两个字段的成本。persist 层使用 uni.storage 缓存 + WS connected 帧携带 persona 数据。
- **Consequences**:
  - 正向: 满足 CON-04（Pinia 模式）；persona 与聊天状态在同一 store 中原子访问。
  - 负向: useChatStore 增加 2 个字段 + 1 个 action（loadPersona），轻微膨胀但尚在可接受范围。

---

### ADR-007: 人格偏好向 LangGraph 系统提示注入

- **Status**: Accepted
- **Context**: REQ-FUNC-001 要求副官以"智能方舟的副官"身份自居；REQ-FUNC-002 要求以"尊敬的舰长大人"称呼用户；REQ-FUNC-005 要求回访用户自动加载已持久化的人格偏好。人格偏好需注入 LLM 系统提示以使 AI 回复风格一致。当前系统提示加载链: prompts.py → load_expert_prompts() → 读 agents/<expert>/SYSTEM_PROMPT.langgraph.md → EXPERT_PROMPTS → orchestrator._expert 使用。
- **Options**:
  - **Option A: 动态修改 EXPERT_PROMPTS 内容** — 在 WS connect 时根据 persona 动态重写提示内容。优点：提示内容统一包含人格。缺点：EXPERT_PROMPTS 是模块级变量（进程共享），一用户的 persona 修改会影响同 worker 进程的其他用户；线程安全风险极高。
  - **Option B: 在 orchestrator._expert 中追加独立的 persona 系统消息** — 类似 ADR-002 的 cabin_context，在 msgs 列表 SystemMessage 之后追加一个包含人格指令的 SystemMessage。优点：请求级隔离、无进程共享问题、与 cabin_context 注入模式一致；缺点：增加一条消息。
  - **Option C: 在 EXPERT_PROMPTS 内容中使用占位符 + 运行时替换** — 提示文件中使用 `{persona_greeting}` 占位符，运行时 str.format。优点：提示与管理层统一；缺点：修改 agents/ 目录下的静态提示文件，增加运维复杂度。
- **Decision**: 选择 Option B — 独立 persona 系统消息追加。与 ADR-002 (cabin context) 保持相同的注入模式，即"独立 SystemMessage 块追加到 msgs 列表"。注入点在 MiniAppChatConsumer._handle_chat → adapter.stream_chat 调用链中，adapter 层从 user_scope 或独立参数中提取 persona 偏好，构造 persona_context_message。默认 persona（greeting_style="副官", tone_style="尊敬的舰长大人"）的注入内容为: `"你是智能方舟的副官，请以'尊敬的舰长大人'称呼当前用户。保持该角色定位贯穿整个对话。"` 若用户自定义了 persona，据此调整措辞。
- **Consequences**:
  - 正向: 请求级隔离、无进程共享竞争；与 cabin 注入模式一致，降低学习成本。
  - 负向: 每个 expert 调用增加一条系统消息（~30-80 tokens）；adapter 层需要新增 persona 参数传递。

---

### ADR-008: WebSocket 协议扩展

- **Status**: Accepted
- **Context**: REQ-NFUNC-004 要求 WS 协议帧格式保持向下兼容，新增字段仅追加。当前 WS 帧类型: connected, status_update, reasoning_token, reasoning_end, stream_token, stream_end, confirm_required, error。前端 ChatWebSocket 仅处理这 8 种帧类型。需要将 persona 数据传递给前端以支持问候语判断和设置页展示。
- **Options**:
  - **Option A: connected 帧扩展 persona 字段** — 在 `{type: "connected", session_key: "...", session_id: "..."}` 中追加 `"persona": {...}`。优点：persona 在连接建立时就传递完毕，前端只需一次接收。缺点：connected 帧仅发送一次，若用户在会话中通过自然语言修改 persona（US-003），前端 persona 状态不会同步更新。
  - **Option B: 新增 persona_update 帧类型** — 新增 `{type: "persona_update", persona: {...}}` 帧。优点：可随时推送 persona 变更（兼容 US-003 自然语言修改）。缺点：新增 WS 帧类型增加协议复杂度。
  - **Option C: 前端从 connected 帧获取 + 主动 HTTP 拉取** — connected 帧携带 persona（减少一次 HTTP 请求），前端在用户设置修改后通过 HTTP PUT 更新并通过 HTTP GET 重新拉取。优点：不新增 WS 帧类型；缺点：persona 变更后的前端状态更新依赖主动拉取逻辑。
- **Decision**: 选择方案组合: connected 帧扩展 persona 字段 (Option A) + 前端 HTTP 按需拉取 (Option C)。connected 帧增加可选的 `"persona": {"greeting_style": "副官", "tone_style": "尊敬的舰长大人"} | null`。persona 数据在 WS connect 时一次性传递，满足 US-001 的首次问候判断和 US-002 的回访加载；用户在会话中自然语言修改 persona（US-003）后，后端在回复中确认修改，前端通过调用 GET /api/miniapp/persona/ 更新本地状态。不新增 WS 帧类型以保持协议最简。
- **Consequences**:
  - 正向: 满足 REQ-NFUNC-004（向下兼容——新增字段为 optional，旧版前端忽略它无副作用）；persona 在连接建立时即就绪。
  - 负向: persona 修改后前端需 HTTP 主动拉取（而非 WS 推送），存在短暂不一致窗口（修改完成到前端拉取之间，约 0-5s）；若 US-003 的修改发生在前端 connected 后，需要额外的状态同步逻辑。

---

### ADR-009: 语音录音临时文件处理

- **Status**: Accepted
- **Context**: REQ-NFUNC-005 要求音频不落盘持久化，处理完成后立即清除。微信同声传译插件的 speechToText API 的录音和识别均在微信客户端沙箱内完成（ADRD-003），音频数据不离开微信进程，天然满足不落盘要求。但 RecorderManager 的 tempFilePath 仍需显式清理。
- **Options**:
  - **Option A: 完全依赖微信同声传译插件（零录音文件）** — 使用插件 speechToText API 直接录音 + 识别，不经过 RecorderManager。优点：音频从头到尾不产生文件、完全满足 REQ-NFUNC-005；缺点：插件 API 无法获取录音时长、波形数据（限制 REQ-FUNC-011 的录音反馈能力）。
  - **Option B: RecorderManager 录音 + 停止后立即清理** — 使用 RecorderManager 获取音频帧做波形动画，停止后传入插件做识别，识别完成后立即 `fs.unlinkSync(tempFilePath)`。优点：可满足 REQ-FUNC-011 波形/时长展示；缺点：短暂存在临时文件（秒级），需确保清理逻辑覆盖所有退出路径。
- **Decision**: 选择 Option A — 完全依赖微信同声传译插件的 speechToText API。该 API 的 `start` 方法自动拉起微信录音界面并实时识别，不产生可访问的音频文件路径。识别结果通过回调返回。REQ-FUNC-011 的视觉反馈通过插件自带的录音界面 + 前端自定义的状态指示器实现（插件录音时前端展示脉冲动画+计时器，不依赖 RecorderManager 帧数据）。此方案在合规性上最优（音频绝对不落盘/不传输），且实现最简单。
- **Consequences**:
  - 正向: 绝对满足 REQ-NFUNC-005（零音频文件）；实现简单（插件单 API 调用覆盖录音+识别+清理）。
  - 负向: 无法自定义录音 UI（使用插件默认录音界面，仅能叠加前端状态指示）；无法获取音频原始数据做自定义波形；用户体验依赖插件 UI 质量。

---

## 3. 数据流图

### 3.1 人格偏好设置流

```
用户首次对话                                   人格持久化与复用
───────────                                   ────────────────
US-001: 首次建立人格身份                       US-002: 回访自动加载

[前端 chat/index.vue]                        [前端 chat/index.vue]
  │                                             │
  │ WS connect ──token──▶                       │ WS connect ──token──▶
  │                    [MiniAppChatConsumer]      │                    [MiniAppChatConsumer]
  │                         │                    │                         │
  │                    connected 帧               │                    connected 帧
  │                    {persona: null}             │                    {persona: {...}}
  │  ◀──────────────────┘                        │  ◀──────────────────┘
  │                                             │
  │  persona=null → 展示默认"副官"问候             │  persona={...} → 展示定制问候
  │                                             │
  │  用户发送人格偏好                               │
  │  "我喜欢简洁的风格" ─────────▶                   │
  │                    [LangGraph Orchestrator]    │
  │                         │                    │
  │                    LLM 识别为人格修改意图         │
  │                    → 更新 DB persona 字段        │
  │                    → 回复中确认修改               │
  │  ◀── AI 确认回复 ───┘                         │
  │                                             │
  │  HTTP GET /api/miniapp/persona/               │
  │  ◀── {greeting_style, tone_style} ──────┘    │
  │                                             │
  │  useChatStore.persona = fetched               │
```

### 3.2 座舱感知流

```
US-004: 未绑定座舱提醒                            US-005: 座舱信息注入

[前端 chat/index.vue]                          [前端 chat/index.vue]
  │  useOwnerStore.bindings = []                 │  useOwnerStore.bindings = [...]
  │  useOwnerStore.activeSpecificPart = ''       │  useOwnerStore.activeSpecificPart = '3-1-7-702'
  │                                             │
  │ WS connect ──active_specific_part──▶         │ WS connect ──active_specific_part──▶
  │                    [MiniAppChatConsumer]      │                    [MiniAppChatConsumer]
  │                         │                    │                         │
  │                    build_user_scope():         │                    build_user_scope():
  │                    bound_specific_parts=[]     │                    bound_specific_parts={"3-1-7-702","5-2-1-101"}
  │                    is_unbound() → true         │                    is_multi_bound() → true
  │                         │                    │                         │
  │                    cabin_context_message:       │                    cabin_context_message:
  │                    "未绑定任何房间"               │                    "活跃房间:3-1-7-702;其他:5-2-1-101"
  │                         │                    │                         │
  │                    _expert 节点:               │                    _expert 节点:
  │                    msgs += [cabin_ctx]         │                    msgs += [cabin_ctx]
  │                         │                    │                         │
  │                    LLM 生成消息:                │                    LLM 生成消息:
  │                    "请先绑定座舱" + 跳转链接       │                    "3-1-7-702 房间温度 24.5°C"
  │  ◀── stream_token ───┘                       │  ◀── stream_token ───┘
```

### 3.3 语音输入流

```
US-007: 语音录音                                US-008: 语音转文字发送
US-009: 异常降级

[前端 chat/index.vue VoiceInput 组件]
  │
  │ 点击语音按钮 (.voice-btn)
  │
  ├── 检查权限 scope.record
  │   ├── 未授权 → wx.authorize()
  │   │   ├── 授权成功 → 继续
  │   │   └── 拒绝 → Toast "需要麦克风权限" [US-009 AC-009-01]
  │   └── 已授权 → 继续
  │
  │ 调用插件 speechToText API
  │   wechatPlugin.start({
  │     lang: 'zh_CN',
  │     success: (res) => {
  │       inputText.value = res.result  // [US-008 AC-008-01]
  │       // 用户可编辑后手动发送 [US-008 AC-008-02]
  │     },
  │     fail: (err) => {
  │       // [US-009 AC-009-03] 识别失败降级
  │       Toast "语音识别失败，请重试或使用文字输入"
  │       // textarea 始终可用
  │     }
  │   })
  │
  │ 录音中 [US-007 AC-007-02]:
  │   语音按钮 pulse 动画 + 计时器展示
  │   (插件自带录音界面 + 前端状态覆盖层)
  │
  │ 录音结束:
  │   清除动画 → 展示"识别中…"加载状态 [US-008 AC-008-03]
  │   → 识别完成 → 填入 inputText
  │   → 用户确认 → 走既有 sendText() 路径
  │
  │ 异常处理 [US-009]:
  │   网络断开 → Toast + 降级文本输入
  │   识别超时 → Toast + 降级文本输入
  │   录音过短 → Toast + 不触发识别
```

### 3.4 普通聊天流（人格注入后）

```
[前端 chat/index.vue]                   [后端 Django Channels + LangGraph]
  │
  │ WS: {type: "chat_message", message: "..."}
  │ ─────────────────────────────────▶
  │                                    MiniAppChatConsumer.receive()
  │                                         │
  │                                    _handle_chat(user_message)
  │                                         │
  │                                    加载 persona (from CustomUser)
  │                                    加载 cabin context (from UserScope)
  │                                         │
  │                                    adapter.stream_chat(
  │                                      message=augmented_message,
  │                                      user_scope=user_scope,
  │                                      persona=persona,        ← 新增
  │                                      cabin_active_sp=active_sp, ← 新增
  │                                    )
  │                                         │
  │                                    LangGraph Orchestrator
  │                                      │
  │                                      route: 路由分类
  │                                      │
  │                                      expert (fan-out):
  │                                      msgs = [
  │                                        SystemMessage(EXPERT_PROMPT),
  │                                        SystemMessage(persona_ctx),    ← 新增
  │                                        SystemMessage(cabin_ctx),      ← 新增
  │                                        SystemMessage(date_hint),
  │                                        HumanMessage(query),
  │                                      ]
  │                                      │
  │                                      gate: 写确认门
  │                                      │
  │                                      aggregate: 融合回复
  │                                        │
  │  ◀── stream_token ─────────────────┘
  │  ◀── stream_end
  │  ◀── confirm_required (如有)
```

---

## 4. 接口定义

### 4.1 REST API

#### 4.1.1 GET /api/miniapp/persona/

获取当前用户的人格偏好设置。

- **权限**: IsOwnerUser (role=user)
- **认证**: Bearer Token (header)
- **请求**: 无 body
- **响应 200**:
  ```json
  {
    "greeting_style": "副官",
    "tone_style": "尊敬的舰长大人"
  }
  ```
- **响应 200 (未设置)**:
  ```json
  {
    "greeting_style": null,
    "tone_style": null
  }
  ```
- **错误**: 401 (未认证), 403 (非 owner 用户)

#### 4.1.2 PUT /api/miniapp/persona/

更新当前用户的人格偏好设置。

- **权限**: IsOwnerUser (role=user)
- **认证**: Bearer Token (header)
- **请求 body**:
  ```json
  {
    "greeting_style": "副官",
    "tone_style": "亲切的助手"
  }
  ```
- **响应 200**:
  ```json
  {
    "greeting_style": "副官",
    "tone_style": "亲切的助手"
  }
  ```
- **校验规则**:
  - `greeting_style`: string, max 50 chars, optional
  - `tone_style`: string, max 50 chars, optional
  - 至少一个字段非 null
- **错误**: 400 (校验失败), 401, 403

### 4.2 WebSocket 协议扩展

#### 4.2.1 connected 帧（扩展）

```json
{
  "type": "connected",
  "session_id": "<UUID>",
  "session_key": "<UUID>",
  "persona": {
    "greeting_style": "副官",
    "tone_style": "尊敬的舰长大人"
  },
  "cabin_status": {
    "bound": true,
    "active_specific_part": "3-1-7-702",
    "all_parts": ["3-1-7-702", "5-2-1-101"]
  }
}
```

- `persona`: null 或对象。null 表示用户尚未设置人格偏好（首次用户）。
- `cabin_status`: 对象，`bound` 为 false 时 `active_specific_part` 和 `all_parts` 均为空。
- **向后兼容**: 两个新增字段均为 optional，旧版前端忽略它们不报错。

#### 4.2.2 其他帧类型

保持不变（不新增、不修改），保持向下兼容:
- `status_update`: `{type: "status_update", message: "..."}`
- `reasoning_token`: `{type: "reasoning_token", token: "..."}`
- `reasoning_end`: `{type: "reasoning_end"}`
- `stream_token`: `{type: "stream_token", token: "..."}`
- `stream_end`: `{type: "stream_end"}`
- `confirm_required`: `{type: "confirm_required", actions: [...]}`
- `error`: `{type: "error", ...}`

---

## 5. 安全边界分析

### 5.1 Persona 数据安全

| 维度 | 分析 | 缓解措施 |
|------|------|---------|
| **数据归属** | persona 是用户级私有数据，与用户一一对应 | GET/PUT 端点使用 IsOwnerUser 权限，确保用户只能操作自己的 persona |
| **SQL 注入** | persona JSONField 写入需经 Django ORM | Serializer 层做类型校验；字段值仅限 string（非嵌套 JSON） |
| **XSS** | persona 数据通过 connected 帧传至前端，前端用于问候语条件判断 | 前端仅做 null/non-null 比较，不将 persona 值插入 innerHTML；问候语为后端 LLM 生成 |
| **信息泄露** | persona 值不应出现在日志/错误消息中 | 日志仅记录 "persona updated" 事件，不记录具体值 |
| **越权修改** | admin/operator 无权修改业主的 persona | 端点绑定 IsOwnerUser 权限类，admin/operator 返回 403 |

### 5.2 语音输入安全

| 维度 | 分析 | 缓解措施 |
|------|------|---------|
| **音频隐私** | REQ-NFUNC-005 要求音频不落盘 | 微信同声传译插件在微信沙箱内完成录音+识别，音频数据不暴露给前端代码 |
| **麦克风权限** | 用户需显式授权 scope.record | wx.authorize() 弹窗由微信系统控制，前端无法绕过；拒绝后降至文本输入 |
| **识别结果安全** | 识别文本填入输入框，与手动输入走相同的 sendText() 路径 | 无需特殊处理——识别结果等同于用户手动输入文本 |
| **网络传输** | 插件内部网络请求，不经过小程序代码层 | 插件由微信官方签名，网络请求不由小程序控制 |

### 5.3 座舱上下文安全

| 维度 | 分析 | 缓解措施 |
|------|------|---------|
| **数据归属** | cabin_context 仅包含 current user 的绑定信息 | UserScope 在 WS connect 时通过 build_user_scope() 查询 OwnerUserBinding 构造，按 user 过滤 |
| **跨用户泄露** | UserScope 是 per-connection 实例，不会跨 session 共享 | frozen dataclass + 局部变量作用域确保隔离 |
| **房号在 LLM 提示中** | 房号以明文出现在系统消息中，发送至 DeepSeek API | DeepSeek API 传输层 TLS 加密；房号是业务标识（非 PII） |

---

## 6. 开放问题与假设

| ID | 类型 | 内容 | 关联 |
|----|------|------|------|
| OQ-07 | 待确认 | 语音录音最大时长限制？当前方案使用微信同声传译插件，其默认最长录音时间为 60 秒。若 PM 要求更长时间，需评估插件是否支持配置 | REQ-FUNC-010 |
| OQ-08 | 待确认 | AI 问候语是否与人格联动？当前架构假设问候语由后端 LLM 根据 persona 动态生成（非前端硬编码）。若 PM 要求固定文案，需调整前端问候模板逻辑 | REQ-FUNC-001 |
| [ASSUMPTION] | 假设 | activeSpecificPart 由前端在 WS connect 时通过 query string 参数传递（如 `?token=...&session_key=...&active_sp=3-1-7-702`），后端以此构造 cabin_context | REQ-FUNC-007 |
| [ASSUMPTION] | 假设 | 自然语言修改 persona (US-003) 由现有 LangGraph orchestrator 的 LLM 判断意图实现，不需要新增独立的 NLU 模块 | REQ-FUNC-005 |
</file_header>
