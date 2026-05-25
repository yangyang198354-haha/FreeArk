# 模块设计文档（增量）— 方舟龙虾 Reasoning 流式展示

```
file_header:
  document_id: MOD-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-25
  depends_on: ARCH-REASONING-001, REQ-SPEC-REASONING-001
  prior_module_docs:
    - docs/sdlc/lobster-agent-api-channel/module_design.md (MOD-BE-01 v1.0, MOD-BE-02 v1.2 定义)
```

---

## 0. 增量说明

本文档是 **增量模块设计**，仅描述本期变更模块。
- MOD-SK-01（FreeArk Skill）、MOD-AG-01（Agent 配置）、MOD-BE-03（服务账号）继承自 `lobster-agent-api-channel/module_design.md`，不重复，不修改。
- MOD-BE-02 从 v1.2 升级到 **v1.3**（核心改动）。
- MOD-BE-01 从 v1.1 升级到 **v1.2**（扩展消息类型）。
- MOD-FE-01 为**首次建立**的前端模块记录（`ChatView.vue` 本期首次纳入模块管理）。

---

## MOD-BE-02：OpenClawAdapter（v1.2 → **v1.3**）

**文件**：`FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py`

**版本**：v1.3（本期升级）

**需求引用**：REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-012, REQ-NFR-007, REQ-NFR-008

**架构引用**：ADR-006, ADR-008

### 变更概述

v1.2 → v1.3 的三项核心变更：

1. **yield 协议升级**：`yield str` → `yield tuple[str, str]`，二元组 `(kind, text)`
2. **reasoning 字段解析**：新增 `_REASONING_FIELD` 常量，防御性解析 reasoning 增量
3. **reasoning_effort 透传**：从 Django settings 读取 `OPENCLAW_REASONING_EFFORT`，注入 `chat.send params`
4. **分段统计日志**：对话结束时 INFO 日志输出 reasoning/content token 计数和耗时

### 接口变更

#### `stream_chat()` 签名变更

```python
# v1.2（旧）
async def stream_chat(
    cls,
    message: str,
    session_key: str,
) -> AsyncGenerator[str, None]:
    """...Yields: str — 非空增量 token 文本..."""

# v1.3（新）
async def stream_chat(
    cls,
    message: str,
    session_key: str,
) -> AsyncGenerator[tuple[str, str], None]:
    """
    ...
    Yields:
        tuple[str, str] — (kind, text) 二元组
            kind: 'reasoning' | 'content'
            text: 非空增量文本（空 text 不 yield）
    
    Reasoning 序列先于 content 序列。
    单帧可产出两个 yield（先 reasoning 后 content）。
    ...
    """
```

**注意**：`stream_chat` 的参数签名（`message`, `session_key`）不变，调用方仍传相同参数。唯一变化是 yield 类型从 `str` 变为 `tuple[str, str]`。

#### `_build_chat_send_frame()` 变更

```python
# v1.3 新增 reasoning_effort 参数支持
@staticmethod
def _build_chat_send_frame(
    req_id: str,
    session_key: str,
    message: str,
    idempotency_key: str,
    reasoning_effort: str = '',          # 新增参数
) -> dict:
    params = {
        'sessionKey': session_key,
        'message': message,
        'idempotencyKey': idempotency_key,
    }
    if reasoning_effort in ('low', 'medium', 'high'):
        params['reasoningEffort'] = reasoning_effort   # camelCase 待实测确认（ARCH-C-003）
    return {
        'type': 'req',
        'id': req_id,
        'method': 'chat.send',
        'params': params,
    }
```

#### `_get_config()` 变更

```python
# v1.3 新增 reasoning_effort 读取
return {
    'base_url': ...,
    'token': ...,
    'timeout': ...,
    'connect_timeout': ...,
    'reasoning_effort': getattr(settings, 'OPENCLAW_REASONING_EFFORT', '') or '',  # 新增
}
```

### 新增常量

```python
# 探查前占位值，US-RSN-001 完成后替换为实测字段名
# 候选: 'reasoningDelta', 'thinkingDelta', 'reasoning'
_REASONING_FIELD = 'reasoningDelta'   # TODO: AC-008-01 实测后确认
```

### 核心处理逻辑（v1.3 diff，仅 `state == 'delta'` 分支）

```python
# v1.2（当前）
if state == 'delta':
    delta_text = payload.get('deltaText') or ''
    if delta_text:
        yield delta_text

# v1.3（升级后）
if state == 'delta':
    # reasoning 解析（防御性，同时支持独立字段和 kind 区分两种结构）
    reasoning_text = payload.get(_REASONING_FIELD) or ''
    if not reasoning_text and payload.get('kind') == 'reasoning':
        # kind 区分模式：kind='reasoning' 时 deltaText 携带 reasoning 内容
        reasoning_text = payload.get('deltaText') or ''
        delta_text = ''
    else:
        delta_text = payload.get('deltaText') or ''
    
    if reasoning_text:
        reasoning_tokens += 1
        yield ('reasoning', reasoning_text)
    if delta_text:
        content_tokens += 1
        yield ('content', delta_text)
```

### 统计日志（对话结束时）

```python
# state:final 前（正常结束）
total_ms = int((time.monotonic() - start_time) * 1000)
logger.info(
    'stream_complete session=%s... reasoning_tokens=%d content_tokens=%d '
    'reasoning_ms=%d content_ms=%d total_ms=%d',
    session_key[:8], reasoning_tokens, content_tokens,
    reasoning_ms, content_ms, total_ms,
)

# 异常退出前
logger.info(
    'stream_incomplete session=%s... reasoning_tokens=%d content_tokens=%d reason=%s',
    session_key[:8], reasoning_tokens, content_tokens, reason,
)
```

### 不变的部分

- WS 连接/握手逻辑（`connect.challenge` → `connect` req → `connect` res）
- `state:aborted` / `state:error` / `state:final` 处理
- `OpenClawUnavailableError` 的语义
- 超时处理
- 安全约束（token 不 yield，不打印 token 文本）

---

## MOD-BE-01：ChatConsumer（v1.1 → **v1.2**）

**文件**：`FreeArkWeb/backend/freearkweb/api/consumers.py`

**版本**：v1.2（本期升级）

**需求引用**：REQ-FUNC-010, REQ-NFR-005, REQ-NFR-009

**架构引用**：ADR-007

### 变更概述

v1.1 → v1.2 的唯一改动：**`_handle_chat` 方法**。

`connect`、`disconnect`、`receive`、`_get_user_by_token` 方法**不变**。

### `_handle_chat` 变更（v1.1 → v1.2）

```python
# v1.1（当前，行 132-183）
async def _handle_chat(self, user_message: str):
    try:
        chat_user = getattr(self.user, 'username', 'unknown')
        augmented_message = f"[__freeark_user__:{chat_user}] {user_message}"
        async for token in OpenClawAdapter.stream_chat(
            message=augmented_message,
            session_key=self.session_key,
        ):
            await self.send(json.dumps({
                'type': 'stream_token',
                'token': token,
            }))
        await self.send(json.dumps({'type': 'stream_end'}))
    except OpenClawUnavailableError as exc:
        ...  # 不变

# v1.2（本期，差异部分）
async def _handle_chat(self, user_message: str):
    try:
        chat_user = getattr(self.user, 'username', 'unknown')
        augmented_message = f"[__freeark_user__:{chat_user}] {user_message}"
        
        # 内部状态（局部变量，无持久化）
        _in_reasoning = False
        _reasoning_ended = False
        
        async for kind, text in OpenClawAdapter.stream_chat(       # 解包二元组
            message=augmented_message,
            session_key=self.session_key,
        ):
            if kind == 'reasoning':
                _in_reasoning = True
                await self.send(json.dumps({
                    'type': 'reasoning_token',
                    'token': text,
                }))
            elif kind == 'content':
                # 首次 content：先发 reasoning_end（若有过 reasoning）
                if _in_reasoning and not _reasoning_ended:
                    await self.send(json.dumps({'type': 'reasoning_end'}))
                    _reasoning_ended = True
                    _in_reasoning = False
                await self.send(json.dumps({
                    'type': 'stream_token',
                    'token': text,
                }))
        
        await self.send(json.dumps({'type': 'stream_end'}))
    
    except OpenClawUnavailableError as exc:
        ...  # 不变（行 159-165）
    except asyncio.TimeoutError:
        ...  # 不变（行 167-173）
    except Exception as exc:
        ...  # 不变（行 175-183）
```

**关键设计点**：
- `_in_reasoning` / `_reasoning_ended` 是方法内局部变量，**不是实例变量**，不跨请求持久化
- 即使同一连接发多条消息，每次 `_handle_chat` 调用都有独立的状态（满足 REQ-NFR-009 多用户隔离）
- 若全程无 reasoning（kind 全为 'content'），`reasoning_end` 永不发送，行为与 v1.1 完全兼容

---

## MOD-FE-01：ChatView.vue（首次建立版本记录，**v1.1**）

**文件**：`FreeArkWeb/frontend/src/views/ChatView.vue`

**版本**：v1.1（本期首次受 SDLC 管理）

**需求引用**：REQ-FUNC-011, REQ-NFR-005, REQ-NFR-006

**架构引用**：ADR-007

### 模块职责

- WebSocket 连接与重连管理（不变）
- 消息发送与接收（扩展新消息类型）
- 消息列表渲染（扩展 reasoning 区域）
- 输入区交互（不变）

### 消息数据结构扩展

```javascript
// v1.0（当前）
{ role: 'user' | 'assistant', content: string, streaming?: boolean }

// v1.1（本期）
{
  role: 'user' | 'assistant',
  content: string,              // 正式回答文本（不变）
  reasoning: string,            // 新增：reasoning 文本（默认 ''）
  streaming: boolean,           // 不变：content 是否正在流式
  reasoningStreaming: boolean,  // 新增：reasoning 是否正在流式（默认 false）
}
```

用户消息创建（不变）：
```javascript
messages.value.push({ role: 'user', content: text })
```

助手消息创建（扩展）：
```javascript
messages.value.push({
  role: 'assistant',
  content: '',
  reasoning: '',
  streaming: true,
  reasoningStreaming: false,    // 收到首个 reasoning_token 后置 true
})
```

### handleMessage 扩展

```javascript
// 新增两个 case（现有 switch 中添加）

case 'reasoning_token': {
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant' && last.streaming) {
    last.reasoning += data.token || ''
    if (!last.reasoningStreaming) {
      last.reasoningStreaming = true   // 触发 <details> 显示
    }
  }
  scrollToBottom()
  break
}

case 'reasoning_end': {
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.reasoningStreaming = false    // 触发 <details> 折叠
  }
  break
}

// 已有 case 'stream_token'（不变，content 继续追加）
// 已有 case 'stream_end'（不变，streaming 置 false）
// 已有 case 'error'（不变）
// 已有 default（不变，静默忽略——兼容性关键）
```

### 模板变更（助手气泡 `.chat-bubble--assistant` 内部）

```html
<!-- v1.0（当前） -->
<div class="chat-bubble chat-bubble--assistant">
  <span class="bubble-content">{{ msg.content }}</span>
  <span v-if="msg.streaming && !msg.content" class="thinking-indicator">正在思考...</span>
  <span v-if="msg.streaming && msg.content" class="stream-cursor">|</span>
</div>

<!-- v1.1（本期） -->
<div class="chat-bubble chat-bubble--assistant">
  <!-- 思考过程折叠区（仅在有 reasoning 内容时渲染） -->
  <details
    v-if="msg.reasoning || msg.reasoningStreaming"
    :open="msg.reasoningStreaming"
    class="reasoning-details"
  >
    <summary class="reasoning-summary">🧠 思考过程</summary>
    <span class="reasoning-text">{{ msg.reasoning }}</span>
  </details>
  
  <!-- 正式回答区（不变） -->
  <span class="bubble-content">{{ msg.content }}</span>
  <!-- 「正在思考...」：仅在 无reasoning 且 content 为空 时显示（降级） -->
  <span
    v-if="msg.streaming && !msg.content && !msg.reasoning && !msg.reasoningStreaming"
    class="thinking-indicator"
  >正在思考...</span>
  <span v-if="msg.streaming && msg.content" class="stream-cursor">|</span>
</div>
```

**`<details>` 交互行为说明**：
- `:open="msg.reasoningStreaming"` — reasoning 进行中时展开（`open` 属性为 true），reasoning_end 后 `reasoningStreaming` 变 false 则 `open` 移除，自动折叠
- 用户点击 `<summary>` 可随时展开/折叠，不受响应式数据影响（原生 HTML 行为）
- `{{ msg.reasoning }}` 使用 Vue 插值（HTML 转义），不使用 `v-html`（安全约束）

**`v-if="msg.reasoning || msg.reasoningStreaming"` 逻辑**：
- `msg.reasoning` 非空：有 reasoning 内容（包括 reasoning 结束后的完整文本）
- `msg.reasoningStreaming`：正在 reasoning（即使 reasoning 文本尚为空，也显示空 details）
- 两者都 false：无 reasoning，不渲染 `<details>`（满足 AC-011-05 无 reasoning 降级）

### 新增样式

```css
/* 思考过程折叠区 */
.reasoning-details {
  margin-bottom: var(--space-2, 8px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: var(--space-2, 8px);
}

.reasoning-summary {
  cursor: pointer;
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, #94A3B8);
  user-select: none;
  list-style: none;         /* 移除默认三角 */
}

.reasoning-summary::before {
  content: '▶ ';
  font-size: 9px;
  transition: transform 0.2s ease;
}

details[open] .reasoning-summary::before {
  content: '▼ ';
}

.reasoning-text {
  display: block;
  margin-top: var(--space-1, 4px);
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, #94A3B8);
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  max-height: 300px;        /* 防止超长 reasoning 撑破布局 */
  overflow-y: auto;
}
```

**样式约束**（满足 AC-011-06）：
- reasoning 文字颜色 `#94A3B8`（CSS 变量 `--color-text-secondary`）
- 字体斜体（`font-style: italic`）
- 与正式回答主文字（`--color-text-primary: #E2E8F0`）视觉区分

### 不变部分

- WebSocket 连接/重连逻辑（`connectWS`、`handleManualReconnect`）
- 发送逻辑（`handleSend`、`handleShiftEnter`）
- 滚动逻辑（`scrollToBottom`）
- 用户气泡渲染
- 连接状态指示
- 错误提示
- 输入区布局

---

## 模块间接口依赖（本期）

```
MOD-BE-02 v1.3
  └─ 对外接口：stream_chat() → AsyncGenerator[tuple[str, str], None]
  └─ 调用方：MOD-BE-01 v1.2（consumers.py _handle_chat）

MOD-BE-01 v1.2
  └─ 对外接口：WebSocket 消息序列
     reasoning_token(×N) → reasoning_end(×1) → stream_token(×M) → stream_end(×1)
  └─ 调用方：MOD-FE-01 v1.1（ChatView.vue handleMessage）

MOD-FE-01 v1.1
  └─ 消费：上述 WebSocket 消息序列
  └─ 产出：reasoning 折叠区 + content 流式气泡
```

---

## 变更影响分析

### 同文件其他方法影响

| 方法 | 影响 | 说明 |
|------|------|------|
| `connect` | 无 | 不变 |
| `disconnect` | 无 | 不变 |
| `receive` | 无 | 入口方法，仅调用 `_handle_chat`，签名不变 |
| `_get_user_by_token` | 无 | 纯 ORM 查询，不变 |
| `_build_connect_frame` | 无 | 握手帧，不变 |
| `_to_ws_url` | 无 | URL 转换，不变 |

### 相关测试文件影响

| 测试文件 | 影响类型 | 需要更新 |
|---------|---------|---------|
| 现有 adapter 单元测试（若有） | 破坏性：yield 类型从 str 变为 tuple | 必须更新解包逻辑 |
| 现有 consumer 集成测试（若有） | 扩展：需新增 reasoning_token 消息断言 | 必须新增 case |
| 新增：US-RSN-010 兼容性测试 | 新增 | 新建 `TransactionTestCase` |
