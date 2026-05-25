# 代码评审报告 — 方舟龙虾 Reasoning 流式展示

```
file_header:
  document_id: CR-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_software_developer (PM-orchestrated, PARTIAL_FLOW GROUP_C)
  created_at: 2026-05-26
  depends_on: IMPL-REASONING-001, ARCH-REASONING-001, MOD-REASONING-001
```

---

## 评审结论摘要

| 文件 | CRITICAL | MAJOR | MINOR | INFO | 评审结论 |
|------|---------|-------|-------|------|---------|
| `openclaw_adapter.py` v1.3 | 0 | 0 | 1 | 2 | PASS |
| `consumers.py` v1.2 | 0 | 0 | 0 | 1 | PASS |
| `ChatView.vue` v1.1 | 0 | 0 | 1 | 2 | PASS |
| `settings.py`（追加）| 0 | 0 | 0 | 0 | PASS |
| `tests.py`（追加）| 0 | 0 | 1 | 1 | PASS |

**总体评审结论：PASS**（无 CRITICAL finding，无 MAJOR finding，所有 MINOR 均已标注处置建议）

---

## 1. `openclaw_adapter.py` v1.3

### 1.1 yield 协议破坏性变更同步性检查

**检查项**：adapter 从 `yield str` 改为 `yield tuple[str, str]` 后，是否所有调用方均已同步更新解包逻辑？

**结论**：PASS。
- `consumers.py` v1.2 中 `_handle_chat` 已同步改为 `async for kind, text in OpenClawAdapter.stream_chat(...)`。
- 两文件在同一批次实现，module_design.md ARCH-C-002 要求同批次部署。
- 不存在其他调用 `stream_chat()` 的代码（搜索全仓库 `stream_chat` 只有 adapter 定义和 consumer 调用）。

### 1.2 日志安全检查（REQ-NFR-007）

**检查项**：INFO 日志是否泄露 reasoning 或 content 的 token 文本本身？

**结论**：PASS。
- `stream_complete` 日志格式：`'stream_complete session=%s reasoning_tokens=%d content_tokens=%d reasoning_ms=%d content_ms=%d total_ms=%d'`，参数为 `session_key[:8]`（截断）、整数计数、整数毫秒，无任何 token 文本。
- `stream_incomplete` 日志格式：`'stream_incomplete session=%s reasoning_tokens=%d content_tokens=%d reason=%s'`，同样无 token 文本。
- `logger.error('OpenClaw chat error: kind=%s msg=%s', err_kind, err_msg)` 打印的是 OpenClaw 错误元数据，非 token 文本。
- reasoning_text / delta_text 变量从未传入任何 logger 调用。

### 1.3 reasoning_effort 非法值警告路径

**检查项**：`OPENCLAW_REASONING_EFFORT` 非法值（如 `ultra`）是否有 WARNING 日志并被正确忽略？

**结论**：PASS。
- `stream_chat()` 开头验证：
  ```python
  if reasoning_effort and reasoning_effort not in ('low', 'medium', 'high'):
      logger.warning('OPENCLAW_REASONING_EFFORT=%s 非法（low/medium/high），忽略', reasoning_effort)
      reasoning_effort = ''
  ```
- 验证后，`_build_chat_send_frame()` 内的 `if reasoning_effort in ('low', 'medium', 'high'):` 双重保险确保空字符串不注入参数。
- 满足 US-RSN-008 场景 C（AC-012-03）。

### 1.4 计时器逻辑检查

**MINOR** — 当对话全程无 reasoning（`reasoning_phase_start` 为 None）且发生 `state:aborted`/`state:error` 时，`reasoning_ms` 保持 0，`content_ms` 同理。这是正确行为（0 表示该阶段未发生），但 `stream_incomplete` 日志格式中未输出 reasoning_ms/content_ms，使得中断日志比正常结束日志信息略少。

**处置建议**（非阻塞）：未来可在 `stream_incomplete` 日志中同样输出两个 ms 字段，便于 US-RSN-009 基线测量时排查中断原因。当前实现不影响功能，推迟到 P2 迭代处理。

### 1.5 `_in_reasoning_phase` 变量命名

**INFO** — 局部变量 `_in_reasoning_phase` 与 consumer 中的 `_in_reasoning` 含义相同但命名稍有差异（adapter 用于计时，consumer 用于协议状态）。不影响功能，命名合理，各自语义清晰。

### 1.6 _REASONING_FIELD 占位值风险标注

**INFO** — `_REASONING_FIELD = 'reasoningDelta'` 含详细的 TODO 注释，清晰说明待 US-RSN-001 实测确认，以及上线后 `reasoning_tokens=0` 时的处置路径（见 implementation_plan.md §3）。ARCH-C-001 约束在走法 B 下通过防御性双路解析满足（代码同时兼容多种候选字段名，任一命中即可工作，而非用推测值上线后崩溃）。

---

## 2. `consumers.py` v1.2

### 2.1 _reasoning_ended 防重复发送逻辑

**检查项**：`reasoning_end` 是否最多发送一次（ARCH-C-004）？

**结论**：PASS。
```python
if _in_reasoning and not _reasoning_ended:
    await self.send(json.dumps({'type': 'reasoning_end'}))
    _reasoning_ended = True
    _in_reasoning = False
```
- `_reasoning_ended` 一旦置 True，后续无论多少 `content` yield 都不再发送 `reasoning_end`。
- 局部变量不跨 `_handle_chat` 调用持久化（每次新消息均从 False 开始），满足 REQ-NFR-009。

### 2.2 全程无 reasoning 时的行为

**检查项**：adapter 只 yield `('content', ...)` 时，是否永不发送 `reasoning_end`？

**结论**：PASS。
- `_in_reasoning` 初始为 False，`kind == 'content'` 分支的判断条件 `if _in_reasoning and not _reasoning_ended` 永为 False。
- 消息序列退化为纯 `stream_token` + `stream_end`，与 v1.1 完全兼容（AC-010-05）。

### 2.3 未知 kind 的前向兼容

**INFO** — `else: pass`（静默忽略未知 kind）的设计注释为"前向兼容"。若 adapter 未来新增第三种 kind（如 `'tool_call'`），consumer 不会崩溃，仅静默忽略。这是正确的防御性设计。

---

## 3. `ChatView.vue` v1.1

### 3.1 `<details>` v-if 条件覆盖 AC-011-05 降级场景

**检查项**：`v-if="msg.reasoning || msg.reasoningStreaming"` 是否正确覆盖"无 reasoning 时不渲染 details"？

**结论**：PASS。
- 助手消息创建时 `reasoning: ''`，`reasoningStreaming: false`，两者均为 falsy，`<details>` 不渲染。
- 首次 `reasoning_token` 到达时，`last.reasoningStreaming = true`，`<details>` 开始渲染（`msg.reasoningStreaming` 为 truthy）。
- `reasoning_end` 后，`reasoningStreaming = false`，但 `msg.reasoning` 非空（累积了文本），`<details>` 保持渲染（折叠态，可点击展开）。
- 全程无 `reasoning_token`：`msg.reasoning === ''` 且 `msg.reasoningStreaming === false`，`<details>` 从不渲染，满足 AC-011-05。

### 3.2 `thinking-indicator` v-if 条件扩展

**检查项**：`v-if="msg.streaming && !msg.content && !msg.reasoning && !msg.reasoningStreaming"` 是否正确在 reasoning 活跃时隐藏？

**结论**：PASS。
- 原 v1.0 条件：`msg.streaming && !msg.content`，在 reasoning 阶段（content 为空）显示「正在思考...」
- v1.1 新增 `&& !msg.reasoning && !msg.reasoningStreaming`：
  - 有 reasoning 文本时：`!msg.reasoning` 为 false → indicator 不显示（由 `<details>` 展示 reasoning 内容）
  - reasoning 正在流式时：`!msg.reasoningStreaming` 为 false → indicator 不显示
  - 全程无 reasoning 且 content 为空时：三个条件全满足 → indicator 显示（降级行为正确）

### 3.3 `reasoning-summary::before` 的三角图标

**MINOR** — 当前实现用 `::before { content: '▶ ' }` / `details[open] ::before { content: '▼ ' }` 实现展开/折叠指示。
在某些浏览器下（Chrome 89+），`details[open] .reasoning-summary::before` 需要确认选择器优先级高于基础 `::before`。
另外，`transition: transform 0.2s ease` 在模块设计文档中有提及，但实现中将两种状态的 `content` 属性直接切换而非旋转，无过渡动画效果。

**处置建议**（非阻塞）：功能正确，视觉细节可接受。若需要平滑过渡，可改用单个 `content: '▶ '` + `transform: rotate(90deg)` 动画方案，推迟到 UI 优化迭代。

### 3.4 `{{ msg.reasoning }}` 渲染安全性

**INFO** — `{{ msg.reasoning }}` 使用 Vue 插值（自动 HTML 转义），不使用 `v-html`，满足 architecture_design.md §4.2 前端渲染安全约束。XSS 风险已排除。

### 3.5 `reasoning-text` 的 `white-space: pre-wrap`

**INFO** — `.reasoning-text { white-space: pre-wrap }` 与 `.chat-bubble { white-space: pre-wrap }` 一致（C-011 约束：reasoning 不做 Markdown 渲染，与 content 保持一致）。`max-height: 300px; overflow-y: auto` 防止超长 reasoning 撑破布局，设计合理。

---

## 4. `settings.py` 追加

**评审结论：PASS，无 finding。**

```python
OPENCLAW_REASONING_EFFORT = os.environ.get('OPENCLAW_REASONING_EFFORT', '')
```

- 默认值为空字符串，adapter 遇到空字符串不传 reasoning_effort 参数，满足 AC-012-03（环境变量未设置时使用模型默认值）。
- 追加位置在现有 OPENCLAW_* 变量组末尾，注释与已有风格一致。
- 未触碰 .env 文件，满足强制纪律要求。

---

## 5. `tests.py` 追加（US-RSN-010）

### 5.1 TransactionTestCase 使用

**检查项**：WS 集成测试是否使用 TransactionTestCase（C-005 约束）？

**结论**：PASS。两个测试类均继承 `TransactionTestCase`。

### 5.2 channels.testing 可用性保护

**检查项**：若 `channels.testing` 不可用，测试是否安全退出？

**结论**：PASS。
```python
try:
    from channels.testing import WebsocketCommunicator
    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False
```
每个测试类的 `setUp()` 中调用 `self.skipTest('...')` 确保导入失败时优雅跳过，不报错。

### 5.3 async_gen mock 可靠性

**MINOR** — `_make_async_gen(*tuples)` 每次调用只能迭代一次（async generator 不可重用）。
当前测试中，每个 `_patch(... return_value=_make_async_gen(...))` 只会被 `stream_chat()` 调用一次，不存在重用问题。
但若未来测试需要多次调用 stream_chat（如重试场景），需改用 `side_effect` 传入工厂函数。

**处置建议**（非阻塞）：当前测试场景下无问题，记录为技术债，在 GROUP_D 完善测试时注意。

### 5.4 事件循环使用方式

**INFO** — 测试中使用 `asyncio.get_event_loop().run_until_complete(coro)`。在 Python 3.10+ 环境中，若无当前事件循环，`get_event_loop()` 会 DeprecationWarning。
可改用 `asyncio.run(coro)` 或 `self.loop = asyncio.new_event_loop()` 模式提高可移植性。
Pi 上 Python 版本需确认（若为 3.10+，建议在 GROUP_D 时改进），当前实现功能正确。

---

## 6. 评审总结

**所有关键验证项均通过**：
- yield 协议破坏性变更已同步（adapter tuple ↔ consumer 解包）
- `_reasoning_ended` 防重复发送逻辑正确（ARCH-C-004）
- 日志不泄露 token 文本（REQ-NFR-007）
- `<details>` v-if 条件正确覆盖降级场景（AC-011-05）
- reasoning_effort 非法值 WARNING 路径存在并正确忽略（AC-012-03）
- adapter v1.3 和 consumer v1.2 同批次实现（ARCH-C-002 满足，部署时需遵守）

**MINOR finding 汇总（不阻塞进入 GROUP_D）**：
| ID | 文件 | 描述 | 处置时机 |
|----|------|------|---------|
| CR-M-001 | adapter.py | stream_incomplete 日志缺 reasoning_ms/content_ms 字段 | P2 迭代 |
| CR-M-002 | ChatView.vue | `<details>` 折叠三角无过渡动画（设计文档提及 transition，实现未做） | UI 优化迭代 |
| CR-M-003 | tests.py | async_gen mock 不可重用，多次调用场景需改用 side_effect | GROUP_D 完善时 |
