# 架构设计文档（增量）— 方舟龙虾 Reasoning 流式展示

```
file_header:
  document_id: ARCH-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-25
  depends_on:
    - REQ-SPEC-REASONING-001
    - US-REASONING-001
    - ARCH-LOBSTER-001 (lobster-agent-api-channel，ADR-001~005 继承)
    - PROBES-LOBSTER-001 (OpenClaw 实测探针报告)
  context_snapshot: >
    OpenClaw 2026.5.20，Node.js 22.22.2，DeepSeek v4-flash（reasoning=true，
    reasoning_effort: low/medium/high），FreeArk WS Gateway RPC v4，
    openclaw_adapter.py v1.2（行 261-291），ChatConsumer v1.1（行 132-154），
    ChatView.vue 现有实现
  id_continuation: ADR-005 已被 lobster-agent-api-channel 占用；本期 ADR-006 起
```

---

## 0. 增量说明

本文档是 **增量架构设计**，仅记录本期新增 ADR（ADR-006~ADR-008）。  
ADR-001~005 定义继承自 `docs/sdlc/lobster-agent-api-channel/architecture_design.md`，不重复。  
所有新增 ADR 与现有 ADR 无冲突，属于正交扩展。

---

## 1. 架构变更总览

### 1.1 变更范围

本期改动仅涉及现有三个文件，**不新增文件、不引入新依赖、不修改部署配置**：

| 文件 | 当前版本 | 升级后版本 | 改动性质 |
|------|---------|----------|---------|
| `openclaw_adapter.py` (MOD-BE-02) | v1.2 | v1.3 | 扩展 yield 协议 + reasoning 字段解析 + reasoning_effort 参数 + 统计日志 |
| `consumers.py` (MOD-BE-01) | v1.1 | v1.2 | 扩展消息类型转发（reasoning_token, reasoning_end） |
| `ChatView.vue` (MOD-FE-01，新建模块记录) | 无版本 | v1.1 | 新增 `<details>` 折叠区 + 消息结构扩展 + 消息类型处理 |

### 1.2 变更后数据流（双流并行）

```
用户发送消息
    │
    ▼ WebSocket: {"type":"chat_message","message":"..."}
ChatConsumer._handle_chat (v1.2)
    │ augmented_message = "[__freeark_user__:<user>] <message>"  [已有，ADR-004]
    │
    ▼ async for (kind, text) in OpenClawAdapter.stream_chat(...)
OpenClawAdapter.stream_chat (v1.3)
    │
    ├─ event:chat state:delta  → reasoning字段 非空  → yield ('reasoning', text)
    ├─ event:chat state:delta  → deltaText 非空      → yield ('content', text)
    └─ event:chat state:final                        → return
    │
    ▼ kind 路由
ChatConsumer._handle_chat (v1.2)
    │
    ├─ kind='reasoning'  → send {"type":"reasoning_token","token":text}
    ├─ kind='content' (首次，若前有reasoning) → send {"type":"reasoning_end"}
    │                                           → send {"type":"stream_token","token":text}
    ├─ kind='content' (后续)                 → send {"type":"stream_token","token":text}
    └─ 流结束                                → send {"type":"stream_end"}
    │
    ▼ WebSocket → Nginx :8080 → 浏览器
ChatView.vue (v1.1) handleMessage
    ├─ 'reasoning_token' → msg.reasoning += token; <details open> 显示
    ├─ 'reasoning_end'   → <details> 折叠（open 移除）
    ├─ 'stream_token'    → msg.content += token [不变]
    └─ 'stream_end'      → msg.streaming = false [不变]
```

---

## 2. 架构决策记录（ADR）— 本期新增

---

### ADR-006：OpenClaw reasoning 字段名与 yield 协议设计

**问题**：OpenClaw 2026.5.20 的 `event:chat` `state:delta` payload 中，reasoning 增量使用什么字段名？adapter 如何安全地解析并向上层 yield？

**背景约束**：
- 当前 v1.2 adapter 只读 `payload.get('deltaText')`（行 268-270），未处理任何 reasoning 字段
- DeepSeek v4-flash 是 reasoning 模型，`reasoning: true`，`compat.supportsReasoningEffort: true`
- PROBES-LOBSTER-001 §8 指出字段名为**未确定项**，候选：`reasoningDelta`、`thinkingDelta`、`kind=='reasoning'`+复用`deltaText`

**前置条件（US-RSN-001 必须先完成）**：
US-RSN-001（reasoning 字段名实测探查）是本 ADR 的前置任务。开发人员必须在生产 Pi 上捕获完整 payload 后，才能确定字段名。

**架构决策（基于候选分析，字段名用占位符 `REASONING_FIELD`）**：

**方案对比**：

| 方案 | 结构 | 优点 | 缺点 |
|------|------|------|------|
| A：独立字段（`reasoningDelta` / `thinkingDelta`） | `{deltaText:"", reasoningDelta:"..."}` | 明确区分，无二义性 | 依赖字段名实测确认 |
| B：kind 区分 + 复用 deltaText | `{kind:"reasoning", deltaText:"..."}` | 字段复用，最小 schema 变化 | 解析时需先检查 kind 字段 |
| C：嵌套结构 | `{reasoning:{delta:"..."}, content:{delta:"..."}}` | 结构清晰 | 解析代码变复杂 |

**决策**：采用**防御性解析策略**，支持方案 A 和方案 B，由 `REASONING_FIELD` 常量统一控制：

```python
# adapter.py — 探查完成后填入实际字段名
_REASONING_FIELD = 'reasoningDelta'  # TODO: US-RSN-001 探查后确认，候选: 'thinkingDelta', 'reasoning'

# 解析逻辑
if state == 'delta':
    # 方案 A/C：独立字段
    reasoning_text = payload.get(_REASONING_FIELD) or ''
    # 方案 B：kind 区分
    if not reasoning_text and payload.get('kind') == 'reasoning':
        reasoning_text = payload.get('deltaText') or ''
        delta_text = ''  # kind==reasoning 时 deltaText 是 reasoning 内容
    else:
        delta_text = payload.get('deltaText') or ''
    
    if reasoning_text:
        yield ('reasoning', reasoning_text)
    if delta_text:
        yield ('content', delta_text)
```

**yield 协议规范**：

```
stream_chat() -> AsyncGenerator[tuple[str, str], None]
  where tuple = (kind: Literal['reasoning', 'content'], text: str)
  invariants:
    - text 非空（空 text 不 yield）
    - kind 只有 'reasoning' 或 'content' 两种值
    - reasoning 序列先于 content 序列（符合 DeepSeek 模型行为）
    - 单帧可同时产出两个 yield（先 reasoning 后 content）
```

**理由**：
1. 防御性策略覆盖所有候选字段名，不因字段名不同而逻辑分裂
2. `_REASONING_FIELD` 常量集中管理，探查后只需改一处
3. 二元组协议比单 str 增加最小结构，调用方解包简单
4. 不引入第三方库，纯标准库解析

**开放风险**：
- RISK-001：若 OpenClaw 不在 payload 中携带 reasoning 增量（而是通过独立事件流），探查结果将推翻本 ADR，需重新设计。US-RSN-001 场景 C 已覆盖此风险的上报路径。
- RISK-002：若同一 delta 帧的 reasoningDelta 和 deltaText 同时非空（混合帧），本设计先 yield reasoning 再 yield content，逻辑正确。

**需求覆盖**：REQ-FUNC-008, REQ-FUNC-009, REQ-NFR-007

---

### ADR-007：ChatConsumer 消息协议扩展与向后兼容策略

**问题**：如何在现有 `stream_token` / `stream_end` 协议基础上扩展 `reasoning_token` / `reasoning_end`，同时保证旧前端不受影响？

**背景约束**：
- 向后兼容是硬约束（REQ-NFR-005）
- ChatConsumer 当前（v1.1）只处理 `str` 类型 yield，改为二元组后必须同步修改
- `stream_token` 必须继续发送，且语义不变（content 增量）

**决策：状态机式 kind 追踪 + 最小扩展消息集**

消息类型定义（完整协议 v1.1）：

| 消息类型 | 方向 | 触发条件 | 是否新增 |
|---------|------|---------|---------|
| `connected` | 服务器→客户端 | WS 连接建立 | 不变 |
| `reasoning_token` | 服务器→客户端 | adapter yield `('reasoning', ...)` | **新增** |
| `reasoning_end` | 服务器→客户端 | kind 从 reasoning 切换为 content（一次性） | **新增** |
| `stream_token` | 服务器→客户端 | adapter yield `('content', ...)` | 不变（语义不变） |
| `stream_end` | 服务器→客户端 | adapter 生成器耗尽 | 不变 |
| `error` | 服务器→客户端 | 各种异常 | 不变 |
| `chat_message` | 客户端→服务器 | 用户发送消息 | 不变 |

Consumer 内部状态追踪（`_handle_chat` 局部变量）：

```python
_in_reasoning = False       # 当前是否在 reasoning 阶段
_reasoning_ended = False    # 是否已发过 reasoning_end（防重复）
_seen_reasoning = False     # 是否出现过 reasoning（用于统计日志）
```

`reasoning_end` 发送规则：
- 条件：`_in_reasoning == True` AND `kind == 'content'` AND `_reasoning_ended == False`
- 发送后：`_reasoning_ended = True`，`_in_reasoning = False`
- 目的：允许极端情况（reasoning 后再次出现 reasoning）不重复发送 reasoning_end

**向后兼容验证**：
- 旧版前端 `switch(data.type)` 的 `default` 分支静默忽略未知 type
- `stream_token` 类型和结构完全不变（`{"type":"stream_token","token":"..."}` 格式）
- `stream_end` 类型和结构完全不变
- 旧前端在 reasoning 阶段看到空 content，继续显示「正在思考...」，reasoning 结束后 content 正常流入——不报错，体验次于新前端但功能正常

**消息时序保证**：
```
reasoning_token × N → reasoning_end × 1 → stream_token × M → stream_end × 1
```
无 reasoning 时：
```
stream_token × M → stream_end × 1  （完全兼容旧协议）
```

**需求覆盖**：REQ-FUNC-010, REQ-NFR-005

---

### ADR-008：reasoning_effort 配置位置与透传策略

**问题**：如何配置 `reasoning_effort` 参数，在不污染全局 OpenClaw agent 配置的前提下，允许 FreeArk 侧灵活控制？

**背景约束**：
- DeepSeek v4-flash 支持 `reasoning_effort: "low" | "medium" | "high"`
- PROBES-LOBSTER-001 §5.1 指出 `models.json` 在 `~/.openclaw/agents/main/agent/` 下，修改将影响所有使用该 agent 的客户端
- OpenClaw WS RPC v4 的 `chat.send` 请求 `params` 字段是否支持透传 `reasoning_effort` 需实测（当前 `_build_chat_send_frame` 只传 `sessionKey/message/idempotencyKey`）

**方案对比**：

| 方案 | 位置 | 影响范围 | 可动态变更 | 与探查一致性 |
|------|------|---------|----------|-----------|
| **A（选定）** FreeArk adapter 侧，通过 `chat.send params` 透传 | `.env` → adapter → `chat.send` `params.reasoningEffort` | 仅此 FreeArk 实例，不影响其他 OpenClaw 客户端 | 重启生效 | 需实测 OpenClaw 是否透传至模型调用 |
| B 全局 `models.json` | `~/.openclaw/agents/main/agent/models.json` | 影响全局 | 需手动改配置 + 重启 openclaw | 有风险：影响其他调用方 |
| C OpenClaw Control UI | 通过 UI 设置 agent params | 影响全局 | 可热更新 | 不在 FreeArk git 管理范围内 |

**决策：选方案 A（adapter 侧透传）**

实现细节：

```python
# _get_config() 中新增：
'reasoning_effort': getattr(settings, 'OPENCLAW_REASONING_EFFORT', '') or '',

# _build_chat_send_frame 中新增：
params = {
    'sessionKey': session_key,
    'message': message,
    'idempotencyKey': idempotency_key,
}
reasoning_effort = cfg.get('reasoning_effort', '')
if reasoning_effort in ('low', 'medium', 'high'):
    params['reasoningEffort'] = reasoning_effort
elif reasoning_effort:
    logger.warning('OPENCLAW_REASONING_EFFORT=%s 非法（low/medium/high），忽略', reasoning_effort)
```

`.env` 中新增（可选）：
```
OPENCLAW_REASONING_EFFORT=low
```

`settings.py` 中新增（在现有 OPENCLAW_* 变量附近）：
```python
OPENCLAW_REASONING_EFFORT = env('OPENCLAW_REASONING_EFFORT', default='')
```

**开放风险**：
- RISK-003：OpenClaw 2026.5.20 的 `chat.send` 是否将 `params.reasoningEffort` 透传至 DeepSeek API 调用，当前未实测。实测方法：设置后查看日志是否有 reasoning 耗时变化（US-RSN-009）。若不透传，方案 B 作为备选需告知用户。
- RISK-004：`reasoningEffort` 的字段名可能是 `reasoning_effort`（snake_case）而非 camelCase，需随 US-RSN-001 探查一并确认 OpenClaw RPC params 约定。

**理由**：
1. FreeArk 完全控制，不依赖 OpenClaw 配置文件权限
2. 通过环境变量可零代码变更地动态调整
3. 不影响其他可能存在的 OpenClaw 客户端（如手机 App、命令行工具）
4. 代码集中在 adapter，改动局部，可单元测试

**需求覆盖**：REQ-FUNC-012

---

## 3. 兼容性架构保证

### 3.1 向后兼容矩阵

| 场景 | 后端状态 | 前端状态 | 结果 |
|------|---------|---------|------|
| 完全升级 | v1.3 adapter + v1.2 consumer | v1.1 ChatView | 前端展示 reasoning 折叠区 + content |
| 后端升级、前端旧版 | v1.3 adapter + v1.2 consumer | 旧版 ChatView（无 reasoning 分支） | reasoning_token / reasoning_end 被忽略，content 正常展示，功能完整 |
| 双旧版（无改动） | v1.2 adapter + v1.1 consumer | 旧版 ChatView | 原有行为，「正在思考...」静态显示 |
| 仅 adapter 升级（不升级 consumer） | v1.3 adapter | 旧 consumer | consumer 解包 `(kind, text)` 会失败（TypeError）——此中间状态**不允许部署** |

**关键约束**：v1.3 adapter 和 v1.2 consumer 必须同批次部署，不允许单独部署 adapter。

### 3.2 无状态约束不变

- ChatConsumer 不写 MySQL（沿用 ADR-001）
- reasoning 文本不持久化，随 WS 连接销毁（沿用 REQ-NFR-009）
- session_key 随实例销毁（不变）

---

## 4. 安全架构

### 4.1 reasoning 内容安全边界

- adapter 仅透传 OpenClaw/DeepSeek 产出的 reasoning 文本，不构造、不过滤
- reasoning 文本来自 DeepSeek 模型，system prompt 由 OpenClaw 注入，不经过 FreeArk
- OpenClaw gateway token（`OPENCLAW_GATEWAY_TOKEN`）不出现在任何 yield 的 `text` 中（adapter 只读 payload 字段，不 yield 请求头或配置项）
- INFO 日志只记录 token 计数和耗时，**不记录 token 文本**（满足 REQ-NFR-007）

### 4.2 前端渲染安全

- reasoning 文本以 `{{ msg.reasoning }}` 插值渲染（Vue 自动转义 HTML），不使用 `v-html`
- `<details>` 是原生 HTML 元素，无 XSS 风险
- reasoning 文本长度无约束（由 DeepSeek 模型决定），但 `<details>` 折叠后不占用视觉空间

---

## 5. 架构约束汇总（本期新增）

| 约束 | 来源 | 约束内容 |
|------|------|---------|
| ARCH-C-001 | ADR-006 | `_REASONING_FIELD` 常量必须在 US-RSN-001 探查后用真实字段名填写，不可用推测值上线 |
| ARCH-C-002 | ADR-007 | adapter v1.3 和 consumer v1.2 必须同批次部署，禁止单独部署 |
| ARCH-C-003 | ADR-008 | `reasoningEffort` 的 camelCase/snake_case 字段名需随 US-RSN-001 一并确认 |
| ARCH-C-004 | ADR-007 | `reasoning_end` 最多发送一次（per chat，由 `_reasoning_ended` 状态位保证） |
| ARCH-C-005 | REQ-NFR-009 | reasoning 不写入任何持久化存储，不跨 WS 连接传递 |
