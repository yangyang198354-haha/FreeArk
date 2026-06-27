# BUG-STREAM-001 — 方舟智能体聊天"不够流式"根因调查（blockStreamingDefault 误判 + reasoning 死分支）

| 字段 | 值 |
|---|---|
| Bug ID | BUG-STREAM-001 |
| 调查日期 | 2026-05-27 |
| 涉及版本 | OpenClaw 2026.5.20；FreeArk adapter `openclaw_adapter.py` v1.3 |
| 严重程度 | Low — 体验问题，不影响功能正确性；附带发现一处 adapter 隐藏 bug |
| 影响面 | 「和方舟智能体聊天」页面流式渲染粒度；adapter 的 reasoning 处理分支 |
| 状态 | ✅ 已诊断；生产配置已回滚至默认；后续修复见 §7 |

---

## 1. 现象

用户反馈：

> "前端 web 的感受不是流式的。从 deepseek 网上看到要实现流式 需要在 openclaw 端设置 `openclaw config set agents.defaults.blockStreamingDefault on`，另外前端 web 也要在 param 设置 `stream:true` 类似的东西。"

需要验证：
1. 三段链路（Web ↔ FreeArk ↔ OpenClaw ↔ DeepSeek）哪段卡了
2. 上述两个二手建议是否正确

---

## 2. 三段链路实测（probe_stream_timing.py）

写一次性 Python WS 探针 `scripts/analysis/probe_stream_timing.py`，在 Pi 上 loopback 模拟 FreeArk adapter 的握手，捕获每个 `event:chat state:delta` 帧的到达时刻，计算帧间隔分布。

### 2.1 长 prompt 基准（默认配置）

`agents.defaults.blockStreamingDefault` 未显式设置（schema 默认）：

```
total deltas: 149
content: 149 frames, 3189 chars
streaming span: 28083ms
inter-frame gap: min=68 p50=176 p90=245 p99=421 max=473
frames arriving <50ms after previous: 0/148 (0%)
```

含义：

- 28 秒内分 149 帧到达 → **三段都在流，不是"等完再吐"**
- 平均 **21 字符/帧、p50=176ms 帧间隔** → 远不是 token-by-token；典型块流（block streaming）特征
- **0% 帧在 50ms 内** → 每帧之间都有明显间隙，不是 DeepSeek 原生 token 速率（~20-30ms/token）

### 2.2 把 `blockStreamingDefault` 设成 `off` 再测

```
total deltas: 97
content: 97 frames, 2080 chars
streaming span: 17068ms
inter-frame gap: min=111 p50=171 p90=209 p99=309 max=309
frames arriving <50ms after previous: 0/96 (0%)
```

**改前 / 改后 对比**：

| 指标 | 默认 | `off` | 变化 |
|---|---|---|---|
| 字符/帧 | ~21 | ~21 | **0** |
| p50 帧间隔 | 176ms | 171ms | **5ms（噪声级）** |
| <50ms 帧占比 | 0% | 0% | 0 |

**改 `agents.defaults.blockStreamingDefault` 对 Gateway WS RPC `chat.send` 路径无效。**

### 2.3 回滚验证

```bash
openclaw config patch --stdin <<< '{"agents":{"defaults":{"blockStreamingDefault":null}}}'
systemctl --user restart openclaw-gateway.service
```

再跑探针：p50=165ms，结构无变化。生产配置已回到改前状态（`openclaw config get agents.defaults.blockStreamingDefault` 重新报 `Config path not found`）。

---

## 3. 为什么 `blockStreamingDefault` 不影响我们这条路径

`openclaw config schema` 全树搜 `coalesce|buffer|debounce|throttle|chunk|streaming` 得到的可调项分布：

| 配置位置 | 用途 | 与 FreeArk 路径关系 |
|---|---|---|
| `acp.stream.*` | ACP（Agent Connection Protocol）客户端流投影 | ❌ 我们不走 ACP |
| `channels.{discord,slack,telegram,feishu,...}.streaming` 与 `blockStreamingCoalesce` | OpenClaw 出站到 IM 平台的块编排 | ❌ 我们不是这些 channel |
| `channels.*.blockStreamingCoalesce` | 同上 | ❌ |
| `agents.defaults.blockStreamingDefault` | 作为上述 channel 默认值的总闸 | ❌ **只服务 channels** |
| `models.providers.<p>.models[*].streaming` | 上游 LLM API 是否用 SSE | ✅ 间接相关，默认开 |
| `messages.queue.debounceMs` | 全局 followup 队列 debounce | ❌ 入站方向，不是出站 |

**结论**：Gateway WS RPC `chat.send` → `event:chat state:delta` 这条出站路径**没有对外暴露 coalescer 配置**。21 字符/帧、170ms 间隔的合并发生在 OpenClaw 内部硬编码或 DeepSeek 上游 SSE 事件粒度，**当前 config 层面无 knob 可调**。

---

## 4. 附带发现：`reasoning_effort` 代码路径 + reasoning 字段是死代码

调查过程中顺便验证 `openclaw_adapter.py` v1.3 的 reasoning 处理分支：

### 4.1 chat.send 拒绝 `reasoningEffort` 参数

```
chat.send rejected: invalid chat.send params: at root: unexpected property 'reasoningEffort'
```

`openclaw_adapter.py:186-189` 当 `OPENCLAW_REASONING_EFFORT` 设为 `low/medium/high` 时会注入 `params['reasoningEffort']` —— **会被 OpenClaw 直接拒**。生产 `.env` 当前为空字符串，bug 处于潜伏状态。

### 4.2 正确的参数名是 `thinking`

逐个测试候选参数（`probe_chat_send_params.py`）：

| 参数名 | chat.send 响应 |
|---|---|
| `thinking` | ✅ ACCEPTED |
| `reasoning` | ❌ unexpected property |
| `thinkingEffort` | ❌ unexpected property |
| `reasoningMode` | ❌ unexpected property |
| `reasoningEffort` | ❌ unexpected property |
| `model.reasoningEffort` | ❌ unexpected property 'model' |
| `options.reasoning_effort` | ❌ unexpected property 'options' |
| `options.thinking` | ❌ unexpected property 'options' |

### 4.3 即便用 `thinking=high`，DeepSeek v4-flash 也不分离 reasoning 流

两次跑（`thinking=high` vs `thinking=off`，同一 prompt）对比 delta payload：

| 项 | `thinking=high` | `thinking=off` |
|---|---|---|
| delta 帧数 | 16 | 9 |
| state 值集合 | `{delta, final}` | `{delta, final}` |
| 字段 keys 集合 | `{deltaText, message, runId, seq, sessionKey, state}` | 同 |
| 出现 reasoning/think 字段 | False | False |

无论开关 thinking，payload 结构**完全一致**，只有 `deltaText` 一条文本通道。

→ `openclaw_adapter.py:90` `_REASONING_FIELD='reasoningDelta'` 以及 `kind == 'reasoning'` 兜底分支在 DeepSeek v4-flash 这条路径上**永不命中**，是死代码。前端 `reasoning_token` / `reasoning_end` 消息也永远不会发送。

---

## 5. 三段链路最终判定表

| 段 | 是否真流式 | 注释 |
|---|---|---|
| Web ↔ FreeArk (`ChatView.vue` ↔ `ChatConsumer`) | ✅ 真流式 | 每个 `stream_token` 帧立刻 `last.content += token`，Vue 响应式渲染 |
| FreeArk ↔ OpenClaw Gateway (`openclaw_adapter` aiohttp WS RPC) | ⚠️ 流式但**粗粒度** | 149 帧/28s，~21 字/帧，p50 170ms 帧间隔 |
| OpenClaw → DeepSeek | ✅ 应该是真流式 | 否则上一段不会拿到 149 个增量；但合并位置不可观测 |

用户感觉"不流式"的根因：**OpenClaw 出站路径以 ~21 字符/包、170ms/包的粒度合并 DeepSeek 的逐 token 流**。三段都在"流"，但中段切了块。

---

## 6. 用户提到的两个二手建议，结论

| 建议 | 实测结论 |
|---|---|
| `openclaw config set agents.defaults.blockStreamingDefault on` | ❌ **方向错且无效**。该配置只服务 `channels.*`（IM 平台），不通到 Gateway WS RPC；改 on 或 off p50 都是 170ms |
| 前端 param 设 `stream: true` | ❌ **协议不存在**。前端走 WebSocket（`ws/chat/`），不是 REST。`stream:true` 是 DeepSeek REST API 的 body 字段，跟我们没关系 |

---

## 7. 待办（不在本次调查范围）

### 7.1 修 adapter 的 `reasoning_effort` 死代码（潜伏 bug）

`FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py:90, 164-195, 240-244, 342-376`

候选方案：
- **A**（推荐）：去掉整段 reasoning 处理逻辑，简化 adapter。`yield ('reasoning', ...)` 永不发生，前端 `reasoning_token` 分支可删
- **B**：保留 reasoning 通道、把参数名改正为 `thinking`，但当前模型不会回任何 reasoning 数据，仍是死路径；推迟到换模型再做
- **C**：什么都不动，但在 `.env` 加注释说明 `OPENCLAW_REASONING_EFFORT` 设了会导致 chat 全挂

方案 A 改动面最小、收益明确。但需要确认未来是否会切换到真正支持 reasoning 流的模型（如 Claude extended thinking）。

### 7.2 改善流式体感（不依赖 OpenClaw 改造）

- 前端给 `stream_token` 加打字机渐显动画（CSS transition），把"21 字一跳"视觉拉平
- 或在 `ChatView.vue` 收到一帧后按字符 setTimeout 慢吐到 DOM，~30ms/字符

### 7.3 等 OpenClaw 版本更新

后续 OpenClaw 版本可能暴露 Gateway 路径的 coalescer 配置；定期 `openclaw config schema | grep -iE 'gateway.*coalesce|chat.*coalesce'` 复查。

---

## 8. 走过的弯路

调查初期我假设 `blockStreamingDefault` 与名字一致 → 直接进入"该不该改 on/off"模式。但用户当面提出疑问后改为先实测，避免按错误方向直接改生产。教训：

- **OpenClaw 配置项命名容易误导**（`blockStreamingDefault` 看起来是总闸，实际只管 channels）
- **schema 才是权威**：`openclaw config schema` 全树搜定位某 key 的完整路径，能识破"听起来很顶层但实际作用域很窄"的配置
- **二手 AI 抓的资料经常张冠李戴**：用户读到的建议把 DeepSeek REST 的 `stream:true` 和 OpenClaw 配置混为一谈
- **写 30 行的 WS 探针比读 1000 行源码更省时**：直接观察 wire 上的真实帧分布，结论一目了然

---

## 9. 探针脚本归档

复用与重测用：

- `scripts/analysis/probe_stream_timing.py` — 测帧数 / 字符数 / 帧间隔分布
- `scripts/analysis/probe_reasoning_fields.py` — 列出 delta payload 所有 keys + 样本值
- `scripts/analysis/probe_chat_send_params.py` — 枚举 chat.send 接受/拒绝的参数名
- `scripts/analysis/probe_thinking_payload.py` — 验证 `thinking` 参数对 delta 结构的影响

运行方式：上传到 Pi `/tmp/`，`venv/bin/python /tmp/<script>.py --token-file ~/.openclaw_gateway_token [...]`。

---

## 10. 提交记录

本次调查不改源码（adapter 修复留到后续）。仅本文档与探针脚本入仓。生产改动：

1. `openclaw config set agents.defaults.blockStreamingDefault off` → restart gateway → 测试
2. `openclaw config patch ... blockStreamingDefault:null` → restart gateway → 恢复默认（已确认）

生产当前状态：与 2026-05-27 调查开始前完全一致。
