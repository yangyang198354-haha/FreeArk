# 用户故事 — 方舟智能体 Reasoning 流式展示

```
file_header:
  document_id: US-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_requirement_analyst (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-25
  depends_on: REQ-SPEC-REASONING-001
  id_continuation: US-RSN-001 起（新序列，避免与 lobster-agent-api-channel US-LAC-* 冲突）
```

---

## 故事地图概览

```
Epic: 让方舟智能体"思考"过程可见，消除用户等待空白期

  前置基础设施
    US-RSN-001  reasoning 字段名实测探查
  
  后端改造
    US-RSN-002  adapter yield 协议升级（str → (kind, text)）
    US-RSN-003  consumer 分类转发 + reasoning_end 信号
    US-RSN-004  reasoning/content 分段统计日志
  
  前端改造
    US-RSN-005  助手气泡展示可折叠思考过程
    US-RSN-006  reasoning 结束自动折叠，content 接续展示
    US-RSN-007  无 reasoning 时降级到原版行为
  
  性能调优
    US-RSN-008  reasoning_effort 环境变量配置
    US-RSN-009  reasoning_effort 效果基线测量
  
  兼容性保障
    US-RSN-010  旧前端兼容性回归验证
```

---

## US-RSN-001：OpenClaw reasoning 字段名实测探查

**角色**：后端开发者  
**目标**：在生产 adapter 加临时日志，捕获 OpenClaw `event:chat` `state:delta` 的完整 payload，确定 reasoning 增量的字段名  
**价值**：没有字段名，后续所有 reasoning 读取代码均无法正确实现

**需求引用**：REQ-FUNC-008

**故事描述**：
作为后端开发者，我需要在生产环境（Pi）对 `openclaw_adapter.py` 加入一个临时 `logger.info` 调用，触发一次真实对话，从日志中读取 `payload` 的完整 JSON 结构，确认 reasoning 字段名，然后立即移除临时日志，开始正式实现。

**Given / When / Then**：

- **场景 A：字段名探查成功**
  - Given：在 `openclaw_adapter.py` 行 267（`state == 'delta'` 分支内）临时加入 `logger.info('PROBE delta payload: %s', json.dumps(payload))`
  - When：在 Pi 上以 `APP_LOG_LEVEL=INFO uvicorn...` 启动后端，从前端发送一条提问（如"介绍三恒系统"）
  - Then：`journalctl` 或进程 stdout 中出现至少 1 条形如 `PROBE delta payload: {"deltaText":"...","reasoningDelta":"...","state":"delta",...}` 的日志行，其中可清晰识别 reasoning 字段名

- **场景 B：字段名不在 payload 顶层（嵌套结构）**
  - Given：日志中 payload 无 `reasoningDelta` / `thinkingDelta` 字段，而是 `{"kind":"reasoning","deltaText":"..."}` 结构
  - When：开发者记录结构
  - Then：探查报告记录"kind 字段区分 reasoning/content，均复用 deltaText"，架构师据此设计 adapter 解析逻辑

- **场景 C：无任何 reasoning 字段（模型未启用 reasoning）**
  - Given：对话触发后，所有 delta 帧的 payload 只有 `deltaText`
  - When：开发者换用更复杂问题（如"分析当前三恒系统的优化方向"）重试
  - Then：若仍无 reasoning 字段，上报给 PM，由 PM 确认是否需要在 OpenClaw 侧显式启用 `reasoning: true` 参数

**验收标准引用**：AC-008-01、AC-008-02

**优先级**：P0（阻塞 US-RSN-002）  
**估算**：1h（含 Pi SSH 操作、日志捕获、记录结果、移除临时代码）

---

## US-RSN-002：Adapter yield 协议升级

**角色**：后端开发者  
**目标**：将 `OpenClawAdapter.stream_chat` 的 yield 类型从 `str` 改为 `(kind, text)` 二元组，支持区分 reasoning 和 content  
**价值**：是所有 reasoning 展示功能的技术基础

**需求引用**：REQ-FUNC-009

**故事描述**：
作为后端开发者，我需要在确认字段名后（US-RSN-001 完成后），修改 `openclaw_adapter.py` 的 `stream_chat` 方法：当解析到 reasoning 字段时 yield `('reasoning', text)`，当解析到 `deltaText` 时 yield `('content', text)`，并更新版本标注为 v1.3，更新 docstring。

**Given / When / Then**：

- **场景 A：reasoning 增量处理**
  - Given：`event:chat` `state:delta` payload 中包含 reasoning 字段（字段名由 US-RSN-001 确定，记为 `REASONING_FIELD`）
  - When：adapter 解析该帧
  - Then：`yield ('reasoning', payload[REASONING_FIELD])`，若 `REASONING_FIELD` 值为空字符串则跳过（不 yield）

- **场景 B：content 增量处理（向后兼容保持不变的内部逻辑）**
  - Given：payload 中 `deltaText` 不为空
  - When：adapter 解析该帧
  - Then：`yield ('content', deltaText)`，与 v1.2 的 `yield deltaText` 语义等价（但格式为二元组）

- **场景 C：同帧同时有 reasoning 和 content（边界情况）**
  - Given：同一个 delta 帧同时含 `REASONING_FIELD` 和 `deltaText`（实测可能性低，但需定义行为）
  - When：adapter 解析该帧
  - Then：先 yield `('reasoning', ...)` 再 yield `('content', ...)`，保持顺序一致性

- **场景 D：现有异常路径不变**
  - Given：`state:aborted` / `state:error` / `state:final`
  - When：adapter 处理终态帧
  - Then：行为与 v1.2 完全一致（raise / return），二元组协议不影响终态处理

**验收标准引用**：AC-009-01、AC-009-02、AC-009-03、AC-009-04

**优先级**：P0  
**估算**：2h（代码改写 + 单元测试更新）  
**阻塞于**：US-RSN-001

---

## US-RSN-003：Consumer 分类转发与 reasoning_end 信号

**角色**：后端开发者  
**目标**：`ChatConsumer._handle_chat` 按 kind 分类转发，在 kind 从 reasoning 切换为 content 时发送 `reasoning_end`  
**价值**：前端需要 `reasoning_end` 信号来折叠思考区域并切换到正式回答渲染

**需求引用**：REQ-FUNC-010, REQ-NFR-005

**Given / When / Then**：

- **场景 A：reasoning 阶段转发**
  - Given：adapter yield `('reasoning', text)`，text 非空
  - When：`_handle_chat` 处理该 yield
  - Then：通过 WS 发送 `{"type": "reasoning_token", "token": text}`；内部标记 `_seen_reasoning = True`，`_in_reasoning = True`

- **场景 B：从 reasoning 切换到 content（reasoning_end 触发）**
  - Given：`_in_reasoning == True`，adapter 下一个 yield 为 `('content', text)`
  - When：`_handle_chat` 检测到 kind 从 reasoning 变为 content
  - Then：先发送 `{"type": "reasoning_end"}`（仅一次），然后发送 `{"type": "stream_token", "token": text}`；`_in_reasoning` 置 False

- **场景 C：全程无 reasoning，仅有 content**
  - Given：adapter 只 yield `('content', ...)` 序列
  - When：`_handle_chat` 处理整个流
  - Then：不发送 `reasoning_token` 或 `reasoning_end`；仅发送 `stream_token` + `stream_end`（与 v1.1 行为完全一致）

- **场景 D：reasoning 结束后再出现 reasoning（理论上不应发生，防御性处理）**
  - Given：`_in_reasoning == False`（已发过 reasoning_end），adapter 再次 yield `('reasoning', ...)`
  - When：`_handle_chat` 处理该 yield
  - Then：仍然发送 `reasoning_token`，但不再重复发送 `reasoning_end`（取决于后续是否切换 content，若有切换则再发一次 `reasoning_end`）；记录 WARNING 日志

- **场景 E：旧前端接收到 reasoning_token/reasoning_end**
  - Given：旧版 `ChatView.vue`（switch 无对应分支）
  - When：前端收到 `{"type": "reasoning_token", ...}` 或 `{"type": "reasoning_end"}`
  - Then：`default` 分支静默忽略；`stream_token` 和 `stream_end` 的处理不受影响

**验收标准引用**：AC-010-01、AC-010-02、AC-010-03、AC-010-04、AC-010-05、AC-NFR-005-01

**优先级**：P0  
**估算**：1.5h（代码改写 + 单元测试）  
**阻塞于**：US-RSN-002

---

## US-RSN-004：Adapter reasoning/content 分段统计日志

**角色**：后端开发者（可观测性需求）  
**目标**：对话结束时 adapter 输出一行 INFO 日志，包含 reasoning_tokens 数、content_tokens 数、各阶段耗时  
**价值**：便于 reasoning_effort 效果验证（US-RSN-009）和生产运维监控

**需求引用**：REQ-NFR-008

**Given / When / Then**：

- **场景 A：正常对话完成**
  - Given：`stream_chat` 迭代至 `state:final`，`APP_LOG_LEVEL=INFO`
  - When：generator 正常 return 前
  - Then：输出 INFO 日志：`stream_complete session=<key[:8]>... reasoning_tokens=<N> content_tokens=<M> reasoning_ms=<T1> content_ms=<T2> total_ms=<T3>`，N/M 为 yield 次数（非字符数），T1/T2/T3 为毫秒整数

- **场景 B：对话被中断（aborted/error/timeout）**
  - Given：`stream_chat` 因异常退出
  - When：异常抛出前
  - Then：输出 INFO 日志：`stream_incomplete session=<key[:8]>... reasoning_tokens=<N> content_tokens=<M> reason=<aborted|error|timeout>`

- **场景 C：日志不含 token 文本**
  - Given：任何情况下
  - When：检查 INFO 日志内容
  - Then：日志中无 reasoning 或 content 的文本内容，仅有计数和时间

**验收标准引用**：AC-009-04、AC-NFR-007-01、AC-NFR-008-01

**优先级**：P1（不阻塞 UI 功能，但阻塞 US-RSN-009 的基线测量）  
**估算**：1h（在 US-RSN-002 基础上增加计时和计数逻辑）

---

## US-RSN-005：助手气泡展示可折叠思考过程

**角色**：前端用户 / 前端开发者  
**目标**：收到第一个 `reasoning_token` 时，助手气泡顶部立即显示展开的「🧠 思考过程」折叠区，reasoning 文字实时追加，样式为浅灰斜体  
**价值**：消除用户在 reasoning 阶段面对静态「正在思考...」的等待感

**需求引用**：REQ-FUNC-011, REQ-NFR-006

**Given / When / Then**：

- **场景 A：首个 reasoning_token 到达**
  - Given：用户发送消息，助手消息对象已创建（`{ role:'assistant', content:'', reasoning:'', streaming:true, reasoningStreaming:true }`），前端显示「正在思考...」
  - When：`handleMessage` 收到 `{"type":"reasoning_token","token":"<text>"}`
  - Then：「正在思考...」占位消失；助手气泡顶部渲染 `<details open>` 元素，标题 `<summary>🧠 思考过程</summary>`，内容追加 `<text>`；`msg.reasoning += token`；`msg.reasoningStreaming = true`

- **场景 B：后续 reasoning_token 继续追加**
  - Given：`reasoningStreaming == true`，`<details open>` 已显示
  - When：收到更多 `reasoning_token`
  - Then：`msg.reasoning += token`，`<details>` 内容实时更新，自动滚动到底部

- **场景 C：首个 reasoning_token 端到端延迟**
  - Given：FreeArk 链路（Uvicorn ASGI + Django Channels + nginx WS）
  - When：用户在前端发送消息，后端调用 OpenClaw，OpenClaw 触发 DeepSeek reasoning
  - Then：从前端 `ws.send` 到 `handleMessage` 收到首个 `reasoning_token`，FreeArk 链路透传延迟 ≤ 2s

**验收标准引用**：AC-011-01、AC-NFR-006-01

**优先级**：P0  
**估算**：2h（模板 + script + style）

---

## US-RSN-006：reasoning 结束自动折叠，content 接续展示

**角色**：前端用户  
**目标**：收到 `reasoning_end` 后，「🧠 思考过程」自动折叠，正式回答在折叠区下方正常流式展示  
**价值**：清晰区分思考阶段和回答阶段，减少界面噪声

**需求引用**：REQ-FUNC-011

**Given / When / Then**：

- **场景 A：reasoning_end 触发折叠**
  - Given：`<details open>` 中 reasoning 文字正在追加
  - When：`handleMessage` 收到 `{"type":"reasoning_end"}`
  - Then：`msg.reasoningStreaming = false`；`<details>` 的 `open` 属性被移除（折叠）；用户可点击 `<summary>` 重新展开

- **场景 B：首个 content stream_token 渲染**
  - Given：`reasoning_end` 已收到，`<details>` 已折叠
  - When：`handleMessage` 收到 `{"type":"stream_token","token":"<text>"}`
  - Then：`msg.content += token`；content 渲染在 `<details>` 下方的正式回答区，样式与现有 `stream_token` 处理一致；流式光标在 content 区域闪烁

- **场景 C：stream_end 终结**
  - Given：`msg.streaming = true`
  - When：收到 `{"type":"stream_end"}`
  - Then：`msg.streaming = false`；光标消失；`isWaiting = false`；行为与现有实现一致

- **场景 D：用户在折叠后点击展开**
  - Given：`<details>` 已自动折叠，reasoning 内容在 DOM 中存在（只是 hidden）
  - When：用户点击 `<summary>🧠 思考过程</summary>`
  - Then：`<details>` 重新展开，reasoning 文字完整显示（浅灰斜体），可滚动

**验收标准引用**：AC-011-02、AC-011-03

**优先级**：P0  
**估算**：1h（与 US-RSN-005 合并实现，逻辑上分开描述）

---

## US-RSN-007：无 reasoning 时降级到原版行为

**角色**：前端用户  
**目标**：若对话没有产生 reasoning（如模型切换或 reasoning_effort=low 后推理阶段极短被省略），界面行为与升级前完全一致  
**价值**：确保新功能不破坏现有聊天体验

**需求引用**：REQ-FUNC-011 AC-011-05, REQ-NFR-005

**Given / When / Then**：

- **场景 A：从未收到 reasoning_token**
  - Given：用户发送消息，助手消息对象已创建（`reasoning: ''`）
  - When：前端直接收到 `stream_token`（未经历 `reasoning_token` / `reasoning_end`）
  - Then：`<details>` 区域不渲染（`v-if="msg.reasoning || msg.reasoningStreaming"` 为 false）；「正在思考...」在 content 为空时显示，content 追加后消失；与升级前行为完全一致

- **场景 B：reasoning 极短（仅 1-2 个 token）**
  - Given：`msg.reasoning` 非空但只有极少内容
  - When：`reasoning_end` 到达
  - Then：`<details>` 仍然显示（折叠后可展开），内容完整保留，不因内容短而隐藏

**验收标准引用**：AC-011-05

**优先级**：P0（必须与 US-RSN-005/006 同批次验证）  
**估算**：包含在 US-RSN-005 估算中

---

## US-RSN-008：reasoning_effort 环境变量配置

**角色**：运维 / 后端开发者  
**目标**：通过 `.env` 中的 `OPENCLAW_REASONING_EFFORT` 控制 chat.send 的 reasoning_effort 参数，无需修改代码  
**价值**：灵活调整 reasoning 深度，在速度和回答质量间取得平衡

**需求引用**：REQ-FUNC-012

**Given / When / Then**：

- **场景 A：env 设置 reasoning_effort=low**
  - Given：`FreeArkWeb/backend/.env` 中包含 `OPENCLAW_REASONING_EFFORT=low`
  - When：adapter 的 `_build_chat_send_frame` 构建请求
  - Then：`params` 中包含 `{"reasoningEffort": "low"}`（或 OpenClaw 实际接受的字段名，由架构师确认）

- **场景 B：env 未设置 reasoning_effort（默认行为）**
  - Given：`.env` 中无 `OPENCLAW_REASONING_EFFORT` 或值为空
  - When：adapter 构建 chat.send 请求
  - Then：`params` 中不包含 `reasoningEffort` 字段，DeepSeek 使用默认 reasoning effort（不硬编码 medium/high）

- **场景 C：env 设置无效值**
  - Given：`OPENCLAW_REASONING_EFFORT=ultra`（非 low/medium/high）
  - When：adapter 初始化时
  - Then：adapter 输出 WARNING 日志"OPENCLAW_REASONING_EFFORT=ultra 不是合法值（low/medium/high），忽略"，不传递该参数

**验收标准引用**：AC-012-01、AC-012-03、AC-012-04

**优先级**：P1  
**估算**：1h（adapter 改动 + .env 更新 + 单元测试）

---

## US-RSN-009：reasoning_effort 效果基线测量

**角色**：后端开发者 / QA  
**目标**：在生产环境测量 reasoning_effort=default 时的 reasoning 耗时基线（T0），验证 low 设置后耗时下降 ≥ 50%  
**价值**：量化方案 B 的实际效果，为 NFR 验收提供数据

**需求引用**：REQ-FUNC-012 AC-012-01、AC-012-02

**Given / When / Then**：

- **场景 A：基线测量**
  - Given：`OPENCLAW_REASONING_EFFORT` 未设置，`APP_LOG_LEVEL=INFO`，adapter v1.3 已部署
  - When：连续发送 3 次相同问题（"介绍三恒系统的主要设备组成"），记录每次 INFO 日志中的 `reasoning_ms`
  - Then：记录 T1、T2、T3，计算 T0 = (T1+T2+T3)/3，写入技术文档作为基线

- **场景 B：low 配置效果验证**
  - Given：`OPENCLAW_REASONING_EFFORT=low`，重新部署后端
  - When：相同 3 次问题
  - Then：记录 T1'、T2'、T3'，计算 T0' = 均值，验证 (T0 - T0') / T0 ≥ 50%

- **场景 C：效果不达标**
  - Given：T0' / T0 < 50%
  - When：报告结果
  - Then：上报 PM，PM 调整 NFR 阈值或调研是否 `medium` 更合适

**验收标准引用**：AC-012-01、AC-012-02

**优先级**：P1（在 P0 功能完成后进行）  
**估算**：1h（生产操作 + 数据记录）

---

## US-RSN-010：旧前端兼容性回归验证

**角色**：QA / 前端开发者  
**目标**：在升级后端（发送 `reasoning_token` / `reasoning_end`）但不升级前端的情况下，验证聊天功能正常  
**价值**：确保 AC-NFR-005-01 得到验证，降低部署风险

**需求引用**：REQ-NFR-005

**Given / When / Then**：

- **场景 A：旧版前端接收 reasoning_token**
  - Given：`ChatView.vue` 的 `switch(data.type)` 中无 `reasoning_token` 分支（即注释掉新 case）
  - When：后端发送完整的 reasoning + content 流
  - Then：前端 `default` 分支不做任何操作；`stream_token` 处理正常；content 正常渲染；`stream_end` 后 `isWaiting = false`

- **场景 B：旧版前端接收 reasoning_end**
  - Given：同上
  - When：后端发送 `{"type": "reasoning_end"}`
  - Then：`default` 分支忽略，无 JS 错误，UI 无异常

- **场景 C：集成测试覆盖（TransactionTestCase）**
  - Given：WS 集成测试（`TransactionTestCase`）
  - When：模拟 adapter yield `('reasoning', 'text')`, `('content', 'text')`，ChatConsumer 处理后发送消息序列
  - Then：测试断言消息序列为 `reasoning_token`、`reasoning_end`、`stream_token`、`stream_end`；单独断言无 `reasoning_token` 场景下序列为 `stream_token`、`stream_end`

**验收标准引用**：AC-NFR-005-01、AC-010-05

**优先级**：P0（必须在部署前通过）  
**估算**：1.5h（集成测试编写 + 执行）

---

## 故事依赖关系（实施顺序参考）

```
US-RSN-001 (探查)
  └─→ US-RSN-002 (adapter yield 协议)
        └─→ US-RSN-003 (consumer 分类转发) ─→ US-RSN-010 (兼容性回归)
        └─→ US-RSN-004 (统计日志)
              └─→ US-RSN-009 (基线测量)

US-RSN-005 (前端气泡 reasoning 展示) [并行]
  └─→ US-RSN-006 (折叠 + content 接续)
  └─→ US-RSN-007 (无 reasoning 降级)

US-RSN-008 (reasoning_effort env) [并行于 US-RSN-002]
  └─→ US-RSN-009 (基线测量)
```

**建议实施批次**：
- 批次 1（P0，后端）：US-RSN-001 → US-RSN-002 → US-RSN-003
- 批次 2（P0，前端）：US-RSN-005 + US-RSN-006 + US-RSN-007
- 批次 3（P0，验证）：US-RSN-010
- 批次 4（P1）：US-RSN-004 + US-RSN-008 + US-RSN-009
