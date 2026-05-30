# 架构设计文档（增量）— 方舟龙虾语音输入

```
file_header:
  document_id: ARCH-VOICE-001
  project: FreeArk — freeark_lobster_voice_input
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  depends_on:
    - REQ-SPEC-VOICE-001
    - US-SPEC-VOICE-001
    - ARCH-REASONING-001 (ADR-006~008)
    - ARCH-MEMORY-001 (ADR-009~013)
  id_continuation: ADR-013 已被 freeark_lobster_memory_isolation 占用；本期 ADR-014 起
  context_snapshot: >
    FreeArk 生产 HEAD 95c3c78，ChatConsumer v1.3，chat_memory 模块，
    ChatView.vue v1.1，routing.py（/ws/chat/ → ChatConsumer），
    asgi.py（ProtocolTypeRouter + AllowedHostsOriginValidator + URLRouter），
    Django 5.2.8 + Channels 4.3.2 + Uvicorn 0.47 + aiohttp 3.13.5
```

---

## 0. 强制架构约束（本期全局）

以下约束优先级高于所有 ADR 决策，任何实现不得违反：

| 编号 | 约束 | 来源 |
|------|------|------|
| ARCH-C-011 | ChatConsumer v1.3 的公开接口（connect/disconnect/_handle_chat 签名）、chat_memory 接口、/ws/chat/ WS 消息协议**冻结不可修改** | REQ-NFR-018 |
| ARCH-C-012 | 火山 ASR secret key **只在服务端 .env**，绝不下发到前端（任何 HTTP/WS 响应均不含 key） | REQ-NFR-017 |
| ARCH-C-013 | 音频数据**不落地磁盘**，后端全程在内存/管道中处理，处理完即释放 | REQ-FUNC-025 |
| ARCH-C-014 | 语音输入降级不影响核心聊天：/ws/chat/ 连接、ChatConsumer v1.3、chat_memory 的行为在语音功能完全故障时必须维持正常 | REQ-FUNC-024 AC-024-06 |
| ARCH-C-015 | 后端 WS 中继连接（Django ↔ 火山 ASR）须有 timeout 和资源回收机制，防止 tab 关闭后 WS 泄漏 | REQ-FUNC-025 AC-025-04, REQ-NFR-016 |
| ARCH-C-016 | 前端语音 UI 元素不遮挡现有 reasoning details 折叠区和 stream 消息气泡 | REQ-FUNC-026 AC-026-02 |
| ARCH-C-017 | 不确定的火山 ASR 能力（协议字段、限流、并发数）标注 VERIFY-VOICE-001~005，GROUP_C 启动前须生产探查验证 | 强制纪律第 6 条 |

---

## 1. 架构变更总览

### 1.1 新增组件一览

| 组件 | 类型 | 位置 | 说明 |
|------|------|------|------|
| STTConsumer | Django Channels Consumer | api/consumers.py（追加类） | 新建 WS endpoint /ws/stt/，处理语音流上传与 ASR 中继 |
| VolcASRClient | 异步客户端 | api/volc_asr_client.py（新文件） | 封装与火山 ASR WSS 的连接、发帧、接收识别结果 |
| STTView (Vue) | 前端组件 | frontend/src/components/STTButton.vue（新文件） | 麦克风按钮、录音状态、流式识别文字展示 |
| routing.py | 路由 | api/routing.py（追加路由） | 追加 /ws/stt/ → STTConsumer 路由 |

### 1.2 变更后端到端数据流（选定方案，含降级路径）

```
浏览器 ChatView（麦克风按钮）
    │ [1] getUserMedia() → MediaRecorder
    │ [2] 音频 chunk（Binary WS frame）
    ↓
Django Channels /ws/stt/（STTConsumer）
    │ [3] 接收音频 chunk（bytes_data）
    │ [4] aiohttp WS client 转发给火山 ASR WSS
    ↓
火山引擎 ASR WSS endpoint ──── ARCH-C-017（能力待探查）
    │ [5] 流式 transcript（JSON frame）
    ↓
STTConsumer（接收识别结果）
    │ [6] 发送 {"type": "stt_partial", "text": "..."} 到浏览器
    │     或 {"type": "stt_final", "text": "..."}
    ↓
浏览器（接收文字片段，实时更新识别展示区）
    │ [7] 识别完成，文字注入 el-input textarea
    │ [8] 用户校对后手动发送
    ↓
现有 /ws/chat/（ChatConsumer v1.3）→ chat_memory → OpenClaw
```

**降级路径（ARCH-C-014）**：
```
/ws/stt/ 故障（任何原因）
    ↓
STTConsumer 发送 {"type": "stt_error", "code": "...", "message": "..."}
    ↓
前端展示错误提示，语音输入按钮恢复可用
    ↓
/ws/chat/ 连接完全不受影响，用户继续使用文字输入
```

---

## 2. ADR — 架构决策记录

---

### ADR-014：流式 ASR 中继架构选型

**问题**：语音识别流程中，客户端（前端）与 STT 服务（火山 ASR）之间需要如何连接？

**约束**：ARCH-C-012（secret key 不能到前端）、ARCH-C-011（不破坏现有消费者）

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：前端直连火山 ASR | 浏览器 JS 直接建立 WSS 连接到火山 ASR，secret key 传给前端 | 延迟最低，无服务端中继开销 | **违反 ARCH-C-012**（secret key 暴露前端），安全上绝对不可接受 |
| B：Django WS 中继（流式） | 前端 → /ws/stt/（Django）→ 火山 ASR WSS，Django 双向转发 | secret key 安全，流式低延迟，用户已有 aiohttp 3.13.5 | 增加服务端并发压力，多一跳延迟（局域网/云内约 5-20ms） |
| C：整段录完 HTTP POST | 前端录完整段音频 → HTTP POST → Django → 火山 ASR HTTP API（非流式） | 实现最简单 | **违反 USER-VOICE-03 流式方案选定**；延迟高，与流式识别体验不符 |
| D：前端 WebRTC + Django TURN | 使用 WebRTC + TURN 服务器中转音频 | 复杂度极高，引入 TURN 服务器新依赖 | 显著增加运维复杂度，远超当前项目规模 |

**决策**：`OPEN_FOR_USER_REVIEW`

**PM 推荐**：方案 B（Django WS 中继，流式）是唯一满足"secret key 安全 + 流式体验"双约束的方案。方案 A 违反安全硬约束，方案 C 违反用户选定的流式要求，方案 D 过度复杂。此 ADR 提交用户 CONFIRM，但 PM 认为方案 B 无争议。

**影响**：模块 STTConsumer（MOD-BE-05）、VolcASRClient（MOD-BE-06）

---

### ADR-015：前端音频编码格式

**问题**：浏览器 MediaRecorder 默认产出 webm/opus 容器格式，火山 ASR 接受哪些格式？前端应如何处理？

**约束**：ARCH-C-017（火山 ASR 能力待探查 VERIFY-VOICE-003）、ARCH-C-013（后端不落地）

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：原始 webm/opus 直传 | 前端不做任何编码转换，直接将 MediaRecorder 产出的 webm/opus chunk 透传到后端和火山 ASR | 前端实现最简，无额外依赖 | 火山 ASR 是否接受 webm/opus **待 VERIFY-VOICE-003 确认**；某些浏览器 MediaRecorder 格式可能不同（Firefox 可能产出 ogg） |
| B：后端转码为 PCM/WAV | 后端接收 webm/opus 后用 ffmpeg/pydub 转为 PCM 再发给火山 ASR | 对火山 ASR 格式适配性最好 | 引入 ffmpeg 或 pydub 新运维依赖；转码引入延迟（对流式不友好）；ARCH-C-013 落地风险 |
| C：前端用 AudioContext 转为 PCM | 前端用 Web Audio API 获取 PCM 原始数据，不使用 MediaRecorder | 直接输出 PCM，兼容性好 | 前端实现复杂度高；PCM 数据量大（带宽约为 opus 的 6x） |
| D：前端优先尝试 webm/opus，失败降级 PCM | 检测 MediaRecorder 支持的格式，优先 opus，iOS Safari 降级 | 平衡 | 实现复杂，需维护格式检测逻辑 |

**决策**：`OPEN_FOR_USER_REVIEW`

**建议顺序**：VERIFY-VOICE-003 完成后再决定。若火山 ASR 支持 webm/opus → 选方案 A（最简）；若仅支持 PCM → 选方案 C（避免 ffmpeg 依赖）；若支持 raw PCM 且方案 C 带宽可接受 → 选方案 C。

**影响**：MOD-BE-06（VolcASRClient）的编码参数、MOD-FE-01（STTButton.vue）的 MediaRecorder 配置

---

### ADR-016：STT 文本注入策略

**问题**：识别完成后，识别文字如何注入到聊天流程？

**候选方案**：

| 方案 | 描述 | 用户体验 | 风险 |
|------|------|---------|------|
| A：填入输入框，用户手动校对后发送 | stt_final 触发后，文字填入 el-input，光标置末，用户手动按 Enter 或点发送 | 保留用户控制权，避免识别错误直接发送 | 多一步操作，流程稍长 |
| B：自动发送（含取消窗口） | stt_final 触发后倒计时 3 秒，用户可取消；倒计时结束后自动调用 handleSend() | 更流畅，接近豆包 App 体验 | 识别错误会被发送；isWaiting=true 时需处理冲突 |
| C：双模式可切换（A + B 均支持，用户在设置中选择） | 在 ChatView 或设置页提供"自动发送/手动校对"开关 | 最灵活 | 实现工作量约为 A/B 的 2x，前端状态管理复杂度增加 |

**决策**：`OPEN_FOR_USER_REVIEW`

**建议**：首期选方案 A（填入输入框+手动发送），保守安全，避免识别错误自动发送令用户沮丧。方案 B 可作为 v2 迭代（需要用户从 ChatView 使用中确认误识别率可接受）。方案 C 作为后期功能迭代。

**影响**：MOD-FE-01（STTButton.vue）的事件逻辑

---

### ADR-017：火山 ASR 鉴权方式

**问题**：后端如何使用 secret key 向火山 ASR WSS 进行鉴权？

**约束**：ARCH-C-012（secret key 仅在 .env）、ARCH-C-017（具体协议字段待 VERIFY-VOICE-005 确认）

**候选方案**：

| 方案 | 描述 | 适用场景 |
|------|------|---------|
| A：Query String 鉴权 | WS 连接 URL 携带 app_key + token 参数（如 `wss://...?app_key=xxx&token=yyy`） | 火山 ASR 支持 URL 鉴权时 |
| B：HTTP Upgrade Header 鉴权 | WS 握手时在 HTTP headers 中携带 Authorization 或自定义 Header（aiohttp 支持 headers 参数） | 火山 ASR 支持 Header 鉴权时 |
| C：首帧 JSON 鉴权 | WS 建立后，发送第一帧 JSON 携带 app_key + token 进行鉴权（常见于字节系 ASR 协议） | 火山 ASR 要求首帧鉴权时 |
| D：签名计算（HMAC-SHA256）| 用 secret key 计算签名，每次连接生成时效性 token（类似 AWS V4 签名） | 火山 ASR 要求签名鉴权时 |

**决策**：`OPEN_FOR_USER_REVIEW`

**注**：具体方式须待 VERIFY-VOICE-005 确认火山 ASR 的实际鉴权协议。VolcASRClient 的接口设计须预留鉴权方式的可配置性（通过工厂参数，不硬编码）。secret key 通过 `os.environ.get('VOLC_ASR_APP_KEY')` 读取，不出现在代码或日志中。

**影响**：MOD-BE-06（VolcASRClient.connect() 方法签名）

---

### ADR-018：STT 服务错误恢复与降级策略

**问题**：当火山 ASR 不可达或返回错误时，系统如何响应？

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：直接报错（无降级） | STTConsumer 发送 stt_error 给前端，语音输入当次失败 | 实现简单，行为透明 | 用户体验：语音完全不可用时只能切文字 |
| B：降级到浏览器原生 Web Speech API | 前端检测到 stt_error 后，回退到 window.SpeechRecognition | 改善用户体验 | SpeechRecognition 兼容性差（Chrome-only），识别质量差异大；前端需维护双 STT 路径 |
| C：降级到整段 HTTP 一次性识别 | stt_error 后触发 HTTP POST（整段音频），调用火山 ASR HTTP API | 用户无需切文字 | 引入第二个 API 路径，维护成本增加；已录音频可能丢失（内存中） |
| D：重试一次后报错 | STTConsumer 自动重试连接火山 ASR 一次（500ms 后），仍失败则发 stt_error | 处理瞬时故障 | 增加延迟；非瞬时故障时用户等待 2x timeout |

**决策**：`OPEN_FOR_USER_REVIEW`

**建议**：方案 A（直接报错）+ 方案 D（单次重试）组合：STTConsumer 在首次连接失败后，等待 500ms 重试一次，两次都失败则发 stt_error，前端展示友好提示。不引入 Web Speech API（兼容性问题）或整段 HTTP（额外路径）。此组合实现简洁且满足 ARCH-C-014 降级基线。

**影响**：MOD-BE-05（STTConsumer）的错误处理逻辑、MOD-BE-06（VolcASRClient）的重试机制

---

### ADR-019：VAD（静音检测）实现位置

**问题**：在哪一层实现 Voice Activity Detection？

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：浏览器端 JS（AudioContext + AnalyserNode） | 前端用 Web Audio API 分析音量，低于阈值 N 毫秒后发送"停止"信号 | 延迟最低（本地检测），不消耗服务端计算 | 前端需 AudioContext，Safari 旧版兼容问题；音量阈值需调参 |
| B：Django 后端（Python 分析音频数据） | STTConsumer 接收音频 chunk 后分析 RMS/能量，低于阈值则关闭流 | 不依赖前端 Audio API 兼容性 | 服务端 CPU 增加；音频格式依赖（需先解码才能分析 RMS） |
| C：火山 ASR 自带 VAD | 依赖火山 ASR 服务端 VAD，服务端决定何时结束识别 | 实现最简，质量最好（专业 VAD 模型） | **待 VERIFY-VOICE-003 确认火山 ASR 是否提供 VAD 结果下发** |
| D：无 VAD，仅手动停止 | 用户始终手动点击停止按钮（AC-022-03 要求手动兜底始终存在） | 实现最简，无需 VAD | REQ-FUNC-022 要求 VAD 作为 P1 特性存在；P0 时可先不实现 |

**决策**：`OPEN_FOR_USER_REVIEW`

**建议**：
- P0 阶段（GROUP_C 首期实现）：先实现方案 D（仅手动停止），满足 AC-022-03 兜底要求
- P1 阶段（迭代）：优先方案 C（若 VERIFY-VOICE-003 确认火山 ASR 有 VAD 下发），否则方案 A（浏览器端 AudioContext）
- 方案 B 不推荐（服务端解码音频增加复杂度）

**影响**：MOD-FE-01（STTButton.vue）的 AudioContext 集成（P1 时）

---

### ADR-020：是否独立新 WS endpoint

**问题**：语音输入是走新建的 /ws/stt/ endpoint（新增 STTConsumer），还是复用现有 /ws/chat/ 的多消息类型协议？

**约束**：ARCH-C-011（/ws/chat/ 消息协议冻结），ARCH-C-014（语音故障不影响聊天）

**候选方案**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：独立 /ws/stt/ endpoint（新 STTConsumer） | 新建 STTConsumer，在 routing.py 追加 /ws/stt/ 路由，前端建立两个独立 WS 连接 | 完全隔离，故障互不影响（满足 ARCH-C-014）；不修改 ChatConsumer（满足 ARCH-C-011）；清晰的职责分离 | 前端需维护两个 WS 连接；略增加前端连接状态管理 |
| B：复用 /ws/chat/，新增消息类型（stt_audio_chunk / stt_result） | ChatConsumer 增加 bytes_data 处理（音频帧）和新的 stt_* 消息类型 | 一个连接，前端简洁 | **违反 ARCH-C-011**（ChatConsumer 接口冻结）；WS 混合文本+二进制帧处理复杂；语音故障可能影响聊天 WS |

**决策**：`OPEN_FOR_USER_REVIEW`

**PM 注**：方案 B 违反 ARCH-C-011 硬约束，实际无法选择。方案 A 是唯一合规方案。此 ADR 提交用户形式确认，但 PM 认为方案 A 无争议。

**影响**：api/routing.py（追加路由）、api/consumers.py（追加 STTConsumer 类）

---

## 3. 生产探查验证清单（GROUP_C 启动前必须完成）

| 编号 | 探查项 | 影响 ADR | 探查方式 |
|------|--------|---------|---------|
| VERIFY-VOICE-001 | iOS Safari 14.1+ / Android Chrome MediaRecorder 实际可用性 | ADR-015 | 用户设备实测，或 BrowserStack 测试矩阵 |
| VERIFY-VOICE-002 | 火山 ASR 单次流式会话最大时长（秒） | REQ-FUNC-021 OQ-002 | 查阅火山引擎 ASR 官方文档；用测试 key 实测 |
| VERIFY-VOICE-003 | 火山 ASR 接受的音频格式（webm/opus/PCM/WAV/ogg 支持矩阵）及 VAD 能力 | ADR-015, ADR-019 | 查阅火山引擎 ASR SDK 文档；实测音频格式 |
| VERIFY-VOICE-004 | 用户账号级别的并发 ASR 连接数限制 | REQ-NFR-016 AC-NFR-016-04 | 查阅火山引擎控制台配额页面 |
| VERIFY-VOICE-005 | 火山 ASR WSS 鉴权方式（URL param / Header / 首帧 JSON / 签名） | ADR-017 | 查阅火山引擎 ASR 大模型语音识别 SDK 文档；运行官方 Python demo |

**说明**：VERIFY-VOICE-001~005 须在 GROUP_C 开始实现前完成。用户持有 secret key，可以在不部署的情况下运行 Python demo 脚本完成探查（不需要 SSH 到生产）。

---

## 4. 架构约束汇总

| 编号 | 约束描述 | 违反后果 |
|------|---------|---------|
| ARCH-C-011 | ChatConsumer v1.3 接口冻结 | 回归测试 34+96 个用例失败 |
| ARCH-C-012 | secret key 不出现在任何前端响应 | 安全漏洞，key 失效需用户重申请 |
| ARCH-C-013 | 音频不落地磁盘 | 违反隐私需求，存储占用不可控 |
| ARCH-C-014 | 语音故障不影响文字聊天 | 核心功能可用性下降 |
| ARCH-C-015 | WS 连接 timeout 和资源回收 | 后端 WS leak，可用性下降 |
| ARCH-C-016 | 语音 UI 不遮挡 reasoning UI | 现有功能 UI 破坏 |
| ARCH-C-017 | 火山 ASR 能力不确定项标注待探查 | GROUP_C 实现偏差 |
