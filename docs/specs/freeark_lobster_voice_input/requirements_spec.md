# 需求规格说明书 — 方舟龙虾语音输入

```
file_header:
  document_id: REQ-SPEC-VOICE-001
  project: FreeArk — freeark_lobster_voice_input
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_requirement_analyst (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  context_snapshot: >
    FreeArk 生产 HEAD 95c3c78，ChatConsumer v1.3（memory_isolation 已部署），
    ChatView.vue v1.1（reasoning_token UI + details 折叠区），
    OpenClawAdapter v1.3，chat_memory 模块，
    生产树莓派 Pi 5，Django 5.2.8 + Channels 4.3.2 + Uvicorn 0.47
  depends_on:
    - REQ-SPEC-LOBSTER-001（lobster-agent-api-channel，REQ-FUNC-001~007）
    - REQ-SPEC-REASONING-001（freeark_lobster_reasoning_stream，REQ-FUNC-008~012，REQ-NFR-005~009）
    - REQ-SPEC-MEMORY-001（freeark_lobster_memory_isolation，REQ-FUNC-013~017，REQ-NFR-010~014）
  id_continuation: >
    REQ-FUNC-018 起（接续 freeark_lobster_memory_isolation 的 REQ-FUNC-017）；
    REQ-NFR-015 起（接续 REQ-NFR-014）；
    US-VOICE-001 起（新前缀）
```

---

## 0. 文档说明

本文档是**增量需求规格**，描述 FreeArk 方舟龙虾 Web 聊天界面新增语音输入功能的需求。

**增量边界**：本文档仅描述语音输入功能（REQ-FUNC-018 起）带来的新需求，不重复已有功能（文字聊天、reasoning 流、memory 隔离）的需求。

**来源约定**：
- `[USER-VOICE-01]` = 用户原话："web ui 前端和龙虾聊天能增加语音输入吗，有无方案?"
- `[USER-VOICE-02]` = 用户原话："我有豆包的语音模型服务，也有 secret key，可以集成吗"
- `[USER-VOICE-03]` = 用户原话："选流式方案"
- `[FACT-VOICE-01]` = ChatView.vue v1.1 实测：输入区为 el-input textarea，有发送按钮，无麦克风元素
- `[FACT-VOICE-02]` = 生产环境已部署：ChatConsumer v1.3 (consumers.py)，/ws/chat/ endpoint 存在
- `[FACT-VOICE-03]` = 用户已持有字节火山引擎（豆包）语音服务 secret key
- `[FACT-VOICE-04]` = 流式方案用户明确选定 [USER-VOICE-03]
- `[FACT-VOICE-05]` = ChatView.vue v1.1 中 isWaiting 状态控制输入区禁用（已实现）
- `[FACT-VOICE-06]` = MediaRecorder API 是浏览器原生 API，主流浏览器支持，但格式有差异
- `[FACT-VOICE-07]` = iOS Safari 对 MediaRecorder 支持有限（Safari 14.1+，部分功能受限）
- `[FACT-VOICE-08]` = 微信内嵌浏览器（WKWebView）对 getUserMedia 有限制
- `[FACT-VOICE-09]` = 火山引擎 ASR 能力细节（协议字段、并发数、限流规则）为**待 GROUP_C 启动前生产探查验证**

**禁止项**：本文档不包含架构决策（如"用哪种 WebSocket 方案"、"用哪种音频编码"、"火山 API 的具体调用方式"），这些属于 GROUP_B 职责。

---

## 1. 功能需求

### REQ-FUNC-018 — 麦克风权限授权

**来源**：[USER-VOICE-01] + [FACT-VOICE-06]
**描述**：系统须在用户首次点击语音输入时，请求麦克风访问权限，并根据用户的权限响应做出明确的 UI 反馈。

**验收标准**：
- AC-018-01：Given 用户首次点击语音输入按钮，When 浏览器弹出麦克风权限请求对话框，Then 该对话框来自浏览器原生，系统不自行模拟或替换，用户可选择允许或拒绝。
- AC-018-02：Given 用户允许麦克风权限，When 权限授予成功，Then 系统立即开始录音并显示录音中状态（不需再次点击）。
- AC-018-03：Given 用户拒绝麦克风权限，When 权限被拒绝，Then 系统在聊天界面显示明确的错误提示（如"麦克风权限被拒绝，请在浏览器设置中允许"），语音输入按钮变为不可用状态或给出引导文字，不抛出未处理的异常。
- AC-018-04：Given 用户曾拒绝权限，当前会话中再次点击语音输入按钮，Then 系统再次尝试请求权限（getUserMedia），若仍被拒绝，显示同 AC-018-03 相同的错误提示。
- AC-018-05：Given 用户在系统设置中已永久屏蔽麦克风（浏览器无法弹出请求对话框），When 点击语音输入按钮，Then 系统捕获 NotAllowedError / NotFoundError 并显示人性化错误提示，告知用户前往浏览器设置手动开启。

---

### REQ-FUNC-019 — 录音控制与状态反馈

**来源**：[USER-VOICE-01] + [FACT-VOICE-01]
**描述**：系统须提供明确的录音控制 UI（开始/结束），并向用户实时显示录音状态，避免用户不清楚系统是否在录音（隐私保护要求）。

**验收标准**：
- AC-019-01：Given 用户未在录音，When 录音按钮处于默认状态，Then 按钮视觉上明确标识为"可点击开始录音"的状态（如麦克风图标）。
- AC-019-02：Given 系统正在录音，When 录音进行中，Then UI 必须持续显示明确的"正在录音"指示（如按钮状态变化、动态图标、录音时长计时器之一），不允许录音在无任何 UI 指示的情况下静默进行。
- AC-019-03：Given 系统正在录音，When 用户点击停止按钮，Then 录音立即停止，系统进入识别状态（或直接展示识别结果），按钮恢复为可再次开始录音状态。
- AC-019-04：Given 系统正在录音，When 到达单次最大录音时长（具体时长见 REQ-FUNC-021），Then 系统自动停止录音，显示超时提示，进入识别流程，不抛出异常。
- AC-019-05：Given 系统正在识别（录音已停止，等待识别结果），Then UI 须显示"识别中"状态，不允许用户在此期间重复触发录音（防止多重录音状态叠加）。

---

### REQ-FUNC-020 — 流式语音识别文本展示

**来源**：[USER-VOICE-01] [USER-VOICE-02] [USER-VOICE-03] + [FACT-VOICE-04]
**描述**：系统须将语音识别结果以流式方式实时展示给用户，边说边出字，提供接近豆包 App 的流式识别体验。

**注意**：本需求仅描述"展示"行为，不描述展示的技术实现方式（属于 GROUP_B 职责）。展示位置（是填入输入框还是独立区域）为开放问题 OQ-001（见 §5）。

**验收标准**：
- AC-020-01：Given 用户正在说话，When 流式识别产生中间结果，Then 系统将中间结果以文字形式实时展示在界面上，延迟不超过 3 秒（用户感知到识别开始）。
- AC-020-02：Given 流式识别过程中，When 每次收到新的文字片段，Then 界面上已展示的文字应追加更新，不是每次清空重写（保持连贯体验）。
- AC-020-03：Given 识别完成（流结束），When 最终识别结果确定，Then 界面展示的文字应更新为最终版本（最终 transcript 可能与中间版本略有差异）。
- AC-020-04：Given 识别完成后文字已展示，When 用户检视识别内容，Then 识别文字须清晰可读，不与消息列表或其他 UI 元素重叠干扰。
- AC-020-05：Given 识别文字展示区域有内容，When 用户点击发送 / 确认，Then 该文字注入聊天输入框（或直接发送，见 OQ-001），识别展示区清空重置为初始状态。

---

### REQ-FUNC-021 — 录音时长限制

**来源**：[USER-VOICE-01] + [FACT-VOICE-09]（火山 ASR 单次时长限制待探查）
**描述**：系统须设置单次语音输入的最大时长，防止无限录音占用资源或超过 STT 服务限制。

**注意**：具体最大时长值为开放问题 OQ-002（见 §5），GROUP_C 启动前须完成火山 ASR 限制探查。

**验收标准**：
- AC-021-01：Given 单次录音持续超过最大时长，Then 系统自动触发停止录音，行为等同 AC-019-04。
- AC-021-02：Given 录音正在进行，When 已录时长达到最大时长的 80%，Then 系统须给用户可见警示（如倒计时、颜色变化），提醒用户时间即将用完。
- AC-021-03：Given 服务端 STT 服务对单次流式会话有时长限制，When 达到服务端限制，Then 系统须优雅处理（关闭本次流，展示已识别内容，不崩溃）。

---

### REQ-FUNC-022 — VAD 静音检测

**来源**：[USER-VOICE-01]
**描述**：系统须支持检测用户停止说话并据此决定是否自动结束录音（VAD — Voice Activity Detection）。VAD 实现位置为架构决策（见 GROUP_B OQ 中的 ADR-019）。

**验收标准**：
- AC-022-01：Given VAD 功能启用，When 用户说话结束后静音持续超过一定阈值（如 1.5 秒），Then 系统可自动结束录音，进入识别流程（无需用户手动点击停止）。
- AC-022-02：Given VAD 功能启用且系统准备自动停止，When 用户在静音触发自动停止前重新开口说话，Then 系统不应停止录音，应继续录音。
- AC-022-03：Given VAD 功能存在不确定性（技术限制），Then 系统始终提供手动停止录音按钮作为兜底操作，用户可在任何时候手动停止，不依赖 VAD 自动检测。
- AC-022-04：Given 用户偏好手动控制录音（不希望自动停止），Then 系统应提供手动模式（按住说话 / 点击开始-点击停止），VAD 自动停止为可选行为。

---

### REQ-FUNC-023 — 语音识别文本注入策略

**来源**：[USER-VOICE-01]
**描述**：识别完成后，文字需注入到聊天流程中。具体注入策略（自动发送 vs 填入输入框待用户校对）为开放问题 OQ-001（见 §5），本需求描述两种策略的需求边界。

**验收标准**：
- AC-023-01（填入输入框策略）：Given 识别完成，When 文字注入输入框，Then 用户可在发送前手动编辑、追加或清空文字，与正常文字输入体验一致。
- AC-023-02（填入输入框策略）：Given 识别文字已注入输入框，Then 用户须主动点击发送或按 Enter 才触发聊天，不应自动发送。
- AC-023-03（自动发送策略，如选用）：Given 识别完成且触发自动发送，Then 系统须给用户 2 秒以上的可取消窗口（倒计时显示，用户可点击取消），不得无预警直接发送。
- AC-023-04：Given 识别完成后文字已注入（无论策略），When 聊天功能处于 isWaiting=true 状态（龙虾正在回复），Then 不允许触发新发送，须等待当前回复完成，与现有文字输入行为一致（参考 FACT-VOICE-05）。

---

### REQ-FUNC-024 — 错误处理与降级

**来源**：[USER-VOICE-01] [USER-VOICE-02]
**描述**：语音输入涉及多个可能失败的环节（麦克风、网络、STT 服务），系统须对每种错误场景做明确处理，且语音输入不可用时不影响文字聊天功能。

**验收标准**：
- AC-024-01（麦克风不可用）：Given 设备无麦克风或麦克风被其他应用占用，When 用户点击语音输入按钮，Then 系统显示明确错误提示（"设备无麦克风"或"麦克风被占用"），文字聊天功能不受影响。
- AC-024-02（网络断开）：Given 语音 WS 连接中断（录音进行中或识别进行中），When 网络断开，Then 系统停止录音，显示网络错误提示，不挂起前端，已录音频数据不用于重试（防数据重复），文字聊天 WS 不受语音 WS 断开影响。
- AC-024-03（STT 服务不可达）：Given 火山 ASR 服务返回错误或连接超时，When 语音识别请求失败，Then 系统显示"语音识别暂时不可用"提示，文字聊天功能继续正常工作（语音输入降级不破坏核心聊天功能）。
- AC-024-04（STT 服务 5xx / 限额耗尽）：Given 火山 ASR 返回服务端错误或 quota 超限错误，Then 系统区分展示（"识别服务繁忙，请稍后再试" / "语音识别配额已用尽，请联系管理员"），不展示技术堆栈信息给用户。
- AC-024-05（识别结果为空）：Given 识别服务成功响应但返回空文本（用户可能未发出有效语音），Then 系统提示"未识别到语音内容"，不向聊天输入框注入空字符串，不触发聊天发送。
- AC-024-06（降级基线）：Given 语音输入功能完全不可用（任何原因），Then ChatView 的文字输入和发送功能须保持完全正常，已建立的 /ws/chat/ 连接不受影响。

---

### REQ-FUNC-025 — 隐私与音频数据处理

**来源**：[USER-VOICE-01] + [FACT-VOICE-09]
**描述**：语音输入涉及用户音频数据，系统须满足明确的隐私处理规范。

**验收标准**：
- AC-025-01：Given 音频数据从前端传输到后端，Then 音频数据在服务端**不得**持久化存储到磁盘（不落地文件系统），处理完毕即释放内存。
- AC-025-02：Given 用户查看聊天历史（已存储的 ChatMessage 记录），Then 历史记录中只存储识别后的**文字**，不存储音频文件路径或音频数据。
- AC-025-03：Given 系统正在录音，When 录音 UI 处于活跃状态，Then 必须有持续可见的录音指示（满足 AC-019-02），不得在无用户感知的情况下静默录音。
- AC-025-04：Given 用户关闭浏览器 tab 或导航离开 ChatView，Then 后端语音 WS 连接须在合理时间内（≤30 秒）自动关闭，不得持续占用后端 WS 连接资源。

---

### REQ-FUNC-026 — 与 reasoning 流的共存

**来源**：[USER-VOICE-01] + [FACT-VOICE-05] + [REQ-SPEC-REASONING-001]
**描述**：语音输入需与现有 reasoning_stream 功能共存，不破坏 reasoning_token / stream_token 流式展示。

**验收标准**：
- AC-026-01：Given 龙虾正在回复（isWaiting=true，包含 reasoning 流进行中），When 用户点击语音输入按钮，Then 系统须禁止开始录音（或提示"请等待当前回复完成"），不在回复进行中同时开始录音。
- AC-026-02：Given 语音输入功能新增的 UI 元素（麦克风按钮等），When 渲染在 ChatView.vue 中，Then 不遮挡、不覆盖现有的 reasoning <details> 折叠区和 stream 消息气泡。
- AC-026-03：Given 语音识别文字已注入输入框，When 用户发送此文字消息，Then 后续 ChatConsumer v1.3 的 chat_memory 注入逻辑（load_history + append_message）须正常运行，与文字输入行为完全一致。
- AC-026-04：Given 语音输入 WS 连接（如单独 endpoint）存在，When 该连接出现错误，Then 不影响 /ws/chat/ 连接的 reasoning_stream 和 memory 功能（两个 WS 连接互相隔离）。

---

### REQ-FUNC-027 — 一次会话内多次语音输入

**来源**：[USER-VOICE-01]
**描述**：用户在一次 ChatView 会话中，须能多次使用语音输入，每次录音/识别是独立的操作。

**验收标准**：
- AC-027-01：Given 用户已完成一次语音识别并发送了消息，When 用户再次点击语音输入按钮，Then 系统可正常开始新一轮录音，不需刷新页面。
- AC-027-02：Given 用户在一次会话中进行了多次语音输入，Then 每次识别文字独立产生，不与上次识别结果混合，不累积拼接。
- AC-027-03：Given 上一次语音识别成功或失败，Then 系统状态须完全重置为初始状态（可再次录音），无残留状态影响下次使用。

---

### REQ-FUNC-028 — 浏览器兼容性

**来源**：[USER-VOICE-01] + [FACT-VOICE-06] [FACT-VOICE-07] [FACT-VOICE-08]
**描述**：系统须对 MediaRecorder API 的浏览器兼容情况做明确定义，不支持的浏览器须有降级处理。

**验收标准**：
- AC-028-01（支持）：Given 用户使用 Chrome 90+ / Edge 90+ / Firefox 90+，Then 语音输入功能须完整可用（录音、流式识别、文字注入全流程）。
- AC-028-02（部分支持）：Given 用户使用 Safari 14.1+（桌面端），Then 语音输入功能的基础录音须可用（MediaRecorder 有限支持），如有格式限制须由系统自动适配或提示用户。
- AC-028-03（不支持降级）：Given 用户使用不支持 MediaRecorder API 的浏览器（如旧版 Safari、iOS Safari <14.1），When 检测到不支持，Then 系统须隐藏或禁用语音输入按钮，并展示提示（"您的浏览器不支持语音输入，请使用 Chrome 或 Edge"），文字聊天不受影响。
- AC-028-04（微信内嵌浏览器）：Given 用户在微信内嵌浏览器（WKWebView）中使用，When 该环境对 getUserMedia 有限制，Then 系统须检测并降级处理，行为同 AC-028-03，不因 getUserMedia 报错导致聊天功能崩溃。
- AC-028-05（移动端）：Given 用户在 iOS Safari 14.1+ 或 Android Chrome 上使用，Then 须验证基础录音功能可用（确切支持矩阵为待 GROUP_C 探查验证项 VERIFY-VOICE-001）。

---

## 2. 非功能需求

### REQ-NFR-015 — 语音识别延迟

**来源**：[USER-VOICE-03]（流式方案 = 用户期待低延迟体验）
**描述**：流式识别的用户感知延迟须满足基础体验要求。

**验收标准**：
- AC-NFR-015-01：Given 用户开口说话，When 流式识别产生第一个可显示的文字片段，Then 从用户开口到首字出现的延迟不超过 3 秒（P90）。
- AC-NFR-015-02：Given 用户说完停止说话，When 识别最终完成，Then 从用户停话到最终文字确定的时间不超过 5 秒（P90）。
- AC-NFR-015-03：Given 以上延迟要求无法满足（网络或服务端性能原因），Then 系统须展示"识别中..."占位符让用户知晓系统正在工作，不允许界面静默无反馈超过 3 秒。

---

### REQ-NFR-016 — 资源回收与连接管理

**来源**：[USER-VOICE-01] [FACT-VOICE-09]
**描述**：语音输入涉及持续的 WS 连接和音频流，系统须确保资源及时释放，防止泄漏。

**验收标准**：
- AC-NFR-016-01：Given 语音输入 WS 连接已建立，When 录音停止且识别完成，Then 后端须在识别结束后 ≤5 秒内关闭与 STT 服务的连接，不持续保持空闲连接。
- AC-NFR-016-02：Given 用户关闭 tab / 浏览器 / 导航离开，When 语音 WS 连接收到 onclose 事件，Then 后端须在 ≤30 秒内完成清理（关闭 STT 上游连接、释放音频缓冲区）。
- AC-NFR-016-03：Given 单次语音识别的后端处理超时（如 STT 服务无响应超过 N 秒，N 为架构决策），Then 后端须主动关闭连接并向前端返回超时错误，不无限等待。
- AC-NFR-016-04：Given 多个用户同时使用语音输入功能，Then 每个用户的语音连接须完全隔离，不允许一个用户的音频数据流入另一个用户的识别 session。

---

### REQ-NFR-017 — 安全：secret key 隔离

**来源**：[USER-VOICE-02] [USER-VOICE-03]
**描述**：用户持有的火山 ASR secret key 属于敏感凭证，须严格隔离在服务端，任何情况下不暴露给浏览器前端。

**验收标准**：
- AC-NFR-017-01：Given 任何前端 HTTP/WS 响应，Then 火山 ASR secret key / app_key / token 等凭证信息**不得**出现在任何响应内容（包括 headers、body、WS frame）中。
- AC-NFR-017-02：Given secret key 配置，Then 仅通过服务端环境变量（如 VOLC_ASR_APP_KEY）注入，不入代码仓库，不出现在任何 Django settings.py 硬编码中。
- AC-NFR-017-03：Given Django 日志，Then 日志不输出 secret key 明文（日志脱敏），满足 [REQ-NFR-007] 的延续约束。

---

### REQ-NFR-018 — 可维护性：不破坏已有功能

**来源**：[FACT-VOICE-02]（生产已部署 ChatConsumer v1.3 + memory 模块）
**描述**：语音输入功能的实现不得破坏已部署的 reasoning_stream 和 memory_isolation 功能。

**验收标准**：
- AC-NFR-018-01：Given 语音输入功能完成实现，Then freeark_lobster_reasoning_stream 的 34 个测试（api/tests/test_reasoning_stream.py）须全部通过（回归）。
- AC-NFR-018-02：Given 语音输入功能完成实现，Then freeark_lobster_memory_isolation 的 96 个 memory 测试（api/tests/test_memory_*.py）须全部通过（回归）。
- AC-NFR-018-03：Given ChatConsumer v1.3 的接口和行为，Then 语音输入不得修改 ChatConsumer 的公开接口（connect/disconnect/_handle_chat 签名不变）、chat_memory 模块接口，以及 /ws/chat/ 的 WS 消息协议。

---

### REQ-NFR-019 — 用户感知隐私透明度

**来源**：[USER-VOICE-01]
**描述**：鉴于语音录音的敏感性，系统须确保用户始终清晰知道录音状态，不允许"静默录音"。

**验收标准**：
- AC-NFR-019-01：Given 任何时刻，Then 用户须能通过 UI 清晰判断当前是否在录音（录音状态指示始终可见且明确）。
- AC-NFR-019-02：Given 录音状态指示，Then 该指示不能仅依赖颜色区分（须同时有图标/文字/动效变化），满足基础无障碍可访问性。

---

## 3. 开放问题（Open Questions，推给 GROUP_B）

以下问题属于架构或技术选型决策，不在本文档范围内，由 GROUP_B 在 ADR 中解答：

| 编号 | 问题 | 备注 |
|------|------|------|
| OQ-001 | 流式识别文字的展示位置与注入策略：填入输入框（用户校对后手动发送）/ 流式直接送 chat（+取消窗口）/ 双模式可切换 | 影响 REQ-FUNC-020/023 的实现 |
| OQ-002 | 单次录音最大时长值（秒）：需结合火山 ASR 单次流式会话限制、用户体验权衡 | AC-021-01/02 的具体参数 |
| OQ-003 | VAD 的实现位置：浏览器端 JS 实现 / 后端 Django 实现 / 火山 ASR 自带 VAD / 混合 | REQ-FUNC-022 的实现约束 |
| OQ-004 | VAD 是否默认启用、静音阈值参数是否可配置（运维参数 vs 用户设置） | REQ-FUNC-022 的行为参数 |
| OQ-005 | iOS Safari / 微信内嵌浏览器的支持级别：彻底不支持 / 降级 / 条件支持 | REQ-FUNC-028 的最终支持矩阵 |

---

## 4. 验证清单（GROUP_C 启动前须完成的生产探查）

| 编号 | 探查项 | 影响需求 |
|------|--------|---------|
| VERIFY-VOICE-001 | 移动端（iOS Safari 14.1+ / Android Chrome）MediaRecorder 实际可用性验证 | REQ-FUNC-028 AC-028-05 |
| VERIFY-VOICE-002 | 火山引擎 ASR 单次流式会话最大时长限制 | REQ-FUNC-021，OQ-002 |
| VERIFY-VOICE-003 | 火山引擎 ASR 接受的音频格式列表（webm/opus 是否接受，还是需要 PCM/WAV） | GROUP_B ADR-015 |
| VERIFY-VOICE-004 | 火山引擎 ASR 并发连接数限制（用户账号级别）| REQ-NFR-016 |
| VERIFY-VOICE-005 | 火山引擎 ASR WS 鉴权方式：Header / Query param / 连接帧携带 | GROUP_B ADR-017 |

---

## 5. 需求依赖关系

```
REQ-FUNC-018（权限）
    ↓ 前置
REQ-FUNC-019（录音控制）
    ↓ 并行
REQ-FUNC-022（VAD）
    ↓ 前置
REQ-FUNC-020（流式展示）
    ↓ 前置
REQ-FUNC-023（注入策略）
    ↓ 并行
REQ-FUNC-027（多次录音）

横切需求（无先后依赖）：
    REQ-FUNC-024（错误处理）
    REQ-FUNC-025（隐私）
    REQ-FUNC-026（共存）
    REQ-FUNC-028（兼容性）
    REQ-NFR-015~019（非功能）
```

---

## 6. 需求汇总

| 编号 | 名称 | 优先级 | 来源 |
|------|------|--------|------|
| REQ-FUNC-018 | 麦克风权限授权 | P0 | [USER-VOICE-01] |
| REQ-FUNC-019 | 录音控制与状态反馈 | P0 | [USER-VOICE-01] |
| REQ-FUNC-020 | 流式语音识别文本展示 | P0 | [USER-VOICE-01~03] |
| REQ-FUNC-021 | 录音时长限制 | P0 | [USER-VOICE-01] |
| REQ-FUNC-022 | VAD 静音检测 | P1 | [USER-VOICE-01] |
| REQ-FUNC-023 | 语音识别文本注入策略 | P0 | [USER-VOICE-01] |
| REQ-FUNC-024 | 错误处理与降级 | P0 | [USER-VOICE-01~02] |
| REQ-FUNC-025 | 隐私与音频数据处理 | P0 | [USER-VOICE-01] |
| REQ-FUNC-026 | 与 reasoning 流的共存 | P0 | [FACT-VOICE-02] |
| REQ-FUNC-027 | 一次会话内多次语音输入 | P1 | [USER-VOICE-01] |
| REQ-FUNC-028 | 浏览器兼容性 | P1 | [FACT-VOICE-06~08] |
| REQ-NFR-015 | 语音识别延迟 | P0 | [USER-VOICE-03] |
| REQ-NFR-016 | 资源回收与连接管理 | P0 | [USER-VOICE-01] |
| REQ-NFR-017 | 安全：secret key 隔离 | P0 | [USER-VOICE-02] |
| REQ-NFR-018 | 可维护性：不破坏已有功能 | P0 | [FACT-VOICE-02] |
| REQ-NFR-019 | 用户感知隐私透明度 | P0 | [USER-VOICE-01] |
