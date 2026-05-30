# 模块设计文档（增量）— 方舟龙虾语音输入

```
file_header:
  document_id: MOD-VOICE-001
  project: FreeArk — freeark_lobster_voice_input
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  depends_on:
    - ARCH-VOICE-001 (ADR-014~020)
    - TECH-VOICE-001
    - REQ-SPEC-VOICE-001
  notes: >
    本文档基于 ADR-014 方案 B（Django WS 中继，流式）、
    ADR-016 方案 A（填入输入框+手动发送）、
    ADR-020 方案 A（独立 /ws/stt/ endpoint）作为设计前提。
    若用户 ADR CONFIRM 选择其他方案，对应模块接口须更新。
    ADR-015/017/018/019 中的 OPEN 项在接口中预留可配置点。
```

---

## 0. 模块全景图

```
┌──────────────────────────────────────────────────────────────────────┐
│  前端层                                                               │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐  │
│  │ MOD-FE-02: STTButton.vue    │   │ MOD-FE-01: ChatView.vue v1.1│  │
│  │ (新建 Vue 组件)              │←→│ (现有，仅追加麦克风按钮引用) │  │
│  │ - 麦克风按钮 UI              │   │ - inputText ref 注入点      │  │
│  │ - 录音状态管理               │   │ - isWaiting 状态传入 STTBtn │  │
│  │ - 流式文字展示               │   └─────────────────────────────┘  │
│  │ - WS /ws/stt/ 客户端        │                                     │
│  └──────────────┬──────────────┘                                     │
│                 │ WS /ws/stt/ (Binary + JSON frames)                 │
└─────────────────│────────────────────────────────────────────────────┘
                  │
┌─────────────────│────────────────────────────────────────────────────┐
│  后端层          │                                                     │
│  ┌──────────────▼──────────────┐                                     │
│  │ MOD-BE-05: STTConsumer      │   ← 新建 (api/consumers.py 追加类)  │
│  │ (AsyncWebsocketConsumer)    │                                     │
│  │ - 鉴权（复用 _get_user）     │                                     │
│  │ - 接收音频 Binary frame      │                                     │
│  │ - 调用 VolcASRClient        │                                     │
│  │ - 转发 stt_partial/final    │                                     │
│  │ - 错误处理 + 资源回收        │                                     │
│  └──────────────┬──────────────┘                                     │
│                 │ aiohttp WS client (WSS)                            │
│  ┌──────────────▼──────────────┐                                     │
│  │ MOD-BE-06: VolcASRClient    │   ← 新建 (api/volc_asr_client.py)  │
│  │ - 连接火山 ASR WSS          │                                     │
│  │ - 发送音频帧                 │                                     │
│  │ - 接收识别结果               │                                     │
│  │ - 超时 + 重试               │                                     │
│  └──────────────┬──────────────┘                                     │
│                 │                                                     │
│  ┌──────────────▼──────────────┐                                     │
│  │ MOD-BE-04: routing.py       │   ← 现有，追加 /ws/stt/ 路由       │
│  │ (追加 STTConsumer 路由)     │                                     │
│  └─────────────────────────────┘                                     │
│                                                                      │
│  ┌─────────────────────────────┐                                     │
│  │ MOD-BE-01: ChatConsumer v1.3│   ← 冻结不变（ARCH-C-011）         │
│  │ MOD-BE-02: OpenClawAdapter  │   ← 冻结不变                       │
│  │ MOD-BE-03: asgi.py          │   ← 冻结不变                       │
│  └─────────────────────────────┘                                     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. 模块详细设计

---

### MOD-BE-05：STTConsumer

**文件**：`FreeArkWeb/backend/freearkweb/api/consumers.py`（在现有文件中追加类，不修改 ChatConsumer）
**类型**：AsyncWebsocketConsumer（Channels）
**版本**：v1.0（新建）
**职责**：接收前端音频 Binary WS frame，通过 VolcASRClient 中继到火山 ASR，将识别文字片段转发回前端。

#### 1.1 接口定义

```python
class STTConsumer(AsyncWebsocketConsumer):
    """
    STTConsumer — WebSocket 语音转文字代理（MOD-BE-05 v1.0）

    鉴权：与 ChatConsumer 相同，通过 query_string token 参数鉴权
    Endpoint：/ws/stt/?token=<drf_token>
    音频帧：bytes_data（Binary WS frame，格式由 ADR-015 决定）
    控制帧：text_data JSON（{"type": "stt_start"} / {"type": "stt_stop"}）

    WS 消息协议（下行，服务端 → 客户端）：
      {"type": "stt_connected", "session_id": str}       连接建立成功
      {"type": "stt_partial", "text": str}               流式中间识别结果
      {"type": "stt_final", "text": str}                 最终识别结果
      {"type": "stt_error", "code": str, "message": str} 错误（见错误码表）
      {"type": "stt_closed"}                              识别会话已关闭
    """

    async def connect(self) -> None:
        """
        握手鉴权：验证 DRF token（复用 ChatConsumer._get_user_by_token 逻辑）
        成功：accept() + 发送 stt_connected 帧
        失败：close(code=4001)

        返回：None
        副作用：self.user, self.stt_session_id 初始化；self._asr_client = None
        """
        ...

    async def disconnect(self, close_code: int) -> None:
        """
        连接断开时的资源回收。
        若 self._asr_client 不为 None，则调用 self._asr_client.close()
        满足 ARCH-C-015（timeout + 资源回收）、REQ-FUNC-025 AC-025-04

        返回：None
        """
        ...

    async def receive(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None
    ) -> None:
        """
        接收前端消息：
        - text_data: 控制帧（stt_start / stt_stop）
        - bytes_data: 音频 chunk（Binary WS frame）
        ARCH-C-013：不写磁盘，直接转发给 VolcASRClient

        返回：None
        """
        ...

    async def _handle_stt_start(self) -> None:
        """
        初始化 VolcASRClient，建立到火山 ASR 的连接，
        启动 _recv_loop 协程（异步监听识别结果）

        返回：None
        异常：VolcASRConnectionError → 发送 stt_error(code="ASR_CONNECT_FAIL")
        """
        ...

    async def _handle_stt_stop(self) -> None:
        """
        通知火山 ASR 音频流结束（发送 EOS 帧），等待最终 stt_final
        关闭 VolcASRClient 连接

        返回：None
        """
        ...

    async def _recv_loop(self) -> None:
        """
        异步循环：从 VolcASRClient 接收识别结果帧，
        转发 stt_partial / stt_final 到前端 WS

        返回：None（循环直到 ASR WS 关闭）
        """
        ...

    @staticmethod
    async def _get_user_by_token(token_key: str):
        """
        复用 ChatConsumer 中的 token 鉴权逻辑
        （GROUP_C 实现时可提取为 api/auth_utils.py 共享函数，避免重复）

        返回：User | None
        """
        ...
```

#### 1.2 错误码表

| code | 含义 | 前端展示文案 |
|------|------|------------|
| `ASR_CONNECT_FAIL` | 无法连接火山 ASR（重试后仍失败） | "语音识别服务暂时不可用，请稍后再试" |
| `ASR_TIMEOUT` | 火山 ASR 响应超时（N 秒，N 由配置决定） | "识别超时，请重试" |
| `ASR_QUOTA_EXCEEDED` | 配额超限（如火山 ASR 返回 429 类错误） | "语音识别配额已用尽，请联系管理员" |
| `ASR_SERVICE_ERROR` | 火山 ASR 返回 5xx 错误 | "识别服务繁忙，请稍后再试" |
| `AUDIO_EMPTY` | 识别结果为空（用户未发出有效语音） | "未识别到语音内容，请重试" |
| `AUTH_FAIL` | DRF Token 无效（close code 4001） | "鉴权失败，请重新登录" |

#### 1.3 超时配置

| 参数 | Django settings 变量名 | 默认值 | 说明 |
|------|----------------------|--------|------|
| ASR 连接超时 | `STT_ASR_CONNECT_TIMEOUT` | 5（秒）| VolcASRClient 建立连接超时 |
| ASR 无响应超时 | `STT_ASR_RECV_TIMEOUT` | 30（秒）| _recv_loop 收不到任何帧后关闭 |
| 最大录音时长 | `STT_MAX_RECORD_SECONDS` | 60（秒）| 满足 REQ-FUNC-021，具体值待 VERIFY-VOICE-002 |

所有配置从 `os.environ.get(...)` 读取，不硬编码，满足 REQ-NFR-017 模式。

---

### MOD-BE-06：VolcASRClient

**文件**：`FreeArkWeb/backend/freearkweb/api/volc_asr_client.py`（新建文件）
**类型**：异步上下文管理器（async context manager）
**版本**：v1.0（新建）
**职责**：封装与火山 ASR WSS 的连接、音频帧发送、识别结果接收、鉴权、超时和重试。

#### 2.1 接口定义

```python
class VolcASRConnectionError(Exception):
    """火山 ASR 连接失败"""
    pass

class VolcASRClient:
    """
    异步火山 ASR WSS 客户端（MOD-BE-06 v1.0）

    使用 aiohttp 3.13.5（现有依赖）建立 WS 连接。
    鉴权方式由 ADR-017 决定（OPEN_FOR_USER_REVIEW），接口预留 auth_config 参数。
    音频格式由 ADR-015 决定（OPEN_FOR_USER_REVIEW），接口预留 audio_format 参数。
    ARCH-C-012: app_key 从 os.environ 读取，不接受外部传入（防止意外暴露）

    典型用法：
        async with VolcASRClient(audio_format="webm/opus") as client:
            await client.send_audio_chunk(chunk_bytes)
            async for result in client.iter_results():
                yield result
    """

    def __init__(
        self,
        audio_format: str = "webm/opus",          # ADR-015 决定的格式
        connect_timeout: float = 5.0,             # STT_ASR_CONNECT_TIMEOUT
        recv_timeout: float = 30.0,               # STT_ASR_RECV_TIMEOUT
        max_retries: int = 1,                     # ADR-018：单次重试
    ) -> None:
        """
        初始化客户端参数（不建立连接）。
        app_key 从 os.environ.get('VOLC_ASR_APP_KEY') 读取。
        app_id（若需要）从 os.environ.get('VOLC_ASR_APP_ID') 读取。
        两个环境变量值不记录到日志（ARCH-C-012 / REQ-NFR-017 AC-NFR-017-03）
        """
        ...

    async def __aenter__(self) -> "VolcASRClient":
        """
        建立 WS 连接到火山 ASR（含鉴权，按 ADR-017 决定的方式）。
        若连接失败：重试 max_retries 次，仍失败则 raise VolcASRConnectionError。

        返回：self
        异常：VolcASRConnectionError
        """
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        关闭 WS 连接，释放 aiohttp.ClientSession。
        满足 ARCH-C-015、REQ-NFR-016 AC-NFR-016-01
        """
        ...

    async def send_audio_chunk(self, chunk: bytes) -> None:
        """
        向火山 ASR 发送一个音频 chunk（Binary frame）。
        ARCH-C-013: chunk 不写磁盘，直接转发。

        参数：chunk: bytes — 来自前端 MediaRecorder 的原始音频帧
        返回：None
        异常：RuntimeError（若连接未建立）
        """
        ...

    async def send_eos(self) -> None:
        """
        发送音频流结束标志（EOS，End of Stream）到火山 ASR。
        具体格式（JSON 帧 / 空 Binary 帧 / 特殊标志帧）待 VERIFY-VOICE-003/005 确认。
        接口固定，实现细节在 GROUP_C 完成 VERIFY 后填充。

        返回：None
        """
        ...

    async def iter_results(self):
        """
        异步生成器：逐个 yield 来自火山 ASR 的识别结果帧。

        yield 类型（TypedDict）：
            {
                "type": Literal["partial", "final"],
                "text": str,
                "is_end": bool    # is_end=True 时表示本次识别流结束
            }

        异常：
            asyncio.TimeoutError → 调用方转换为 stt_error(code="ASR_TIMEOUT")
            aiohttp.ClientError  → 调用方转换为 stt_error(code="ASR_SERVICE_ERROR")
        """
        ...
```

#### 2.2 SECRET KEY 读取约定

```python
# 正确方式（ARCH-C-012）
app_key = os.environ.get('VOLC_ASR_APP_KEY', '')
if not app_key:
    raise VolcASRConnectionError("VOLC_ASR_APP_KEY 未配置")

# 禁止：
# logger.info("app_key=%s", app_key)   ← 日志泄露（REQ-NFR-017 AC-NFR-017-03）
# return {"app_key": app_key}          ← 响应泄露（AC-NFR-017-01）
```

#### 2.3 鉴权接口预留（ADR-017 OPEN）

VolcASRClient 的 `__aenter__` 中鉴权逻辑封装为内部方法 `_build_auth_headers() -> dict` 或 `_build_auth_url() -> str`，GROUP_C 实现时根据 VERIFY-VOICE-005 结论填充具体逻辑，对 STTConsumer 的调用接口透明。

---

### MOD-FE-02：STTButton.vue

**文件**：`FreeArkWeb/frontend/src/components/STTButton.vue`（新建 Vue 组件）
**版本**：v1.0（新建）
**职责**：麦克风按钮 UI、录音状态管理、WS /ws/stt/ 客户端、流式文字展示、与 ChatView.vue 的 props/emit 接口。

#### 3.1 Props 接口

```typescript
// Props（TypeScript 类型化，满足接口类型化要求）
interface STTButtonProps {
  isWaiting: boolean    // 来自 ChatView.vue：龙虾是否正在回复中
                        // isWaiting=true 时禁用语音输入（REQ-FUNC-026 AC-026-01）
  wsToken: string       // DRF Token，用于 /ws/stt/?token=<wsToken> 鉴权
                        // 从 ChatView.vue 传入（已在 localStorage 中，安全）
                        // ARCH-C-012: 此处传的是 DRF Token，不是 VOLC secret key
  disabled?: boolean    // 外部禁用覆盖（如浏览器不支持 MediaRecorder 时，ChatView 传入）
}
```

#### 3.2 Emits 接口

```typescript
// Emits（TypeScript 类型化）
interface STTButtonEmits {
  // 识别最终完成，向父组件传递识别文字（注入 inputText）
  'stt-final': [text: string]

  // 识别流式中间结果（可选监听，用于在 ChatView 展示实时文字）
  'stt-partial': [text: string]

  // 语音输入发生错误
  'stt-error': [error: { code: string; message: string }]

  // 录音状态变更（供父组件同步 UI，如禁用发送按钮）
  'recording-state-change': [state: 'idle' | 'recording' | 'recognizing' | 'error']
}
```

#### 3.3 内部状态机

```
IDLE
  │ [点击麦克风按钮 + isWaiting=false + MediaRecorder 支持]
  │ getUserMedia() → 权限授予
  ↓
RECORDING
  │ MediaRecorder.start() → 音频 chunk 通过 /ws/stt/ WS 发送
  │ 显示：录音图标（动画）+ 计时器 + 停止按钮
  │ [点击停止 / VAD 触发 / 超时（STT_MAX_RECORD_SECONDS）]
  ↓
RECOGNIZING
  │ 发送 stt_stop 控制帧（或超时）→ 等待 stt_final
  │ 显示：识别中... + 流式文字（stt_partial 更新）
  │ [收到 stt_final]
  ↓
IDLE（重置）
  │ emit('stt-final', text)
  │ [收到 stt_error（任何阶段）]
  ↓
ERROR（瞬态）
  │ 显示错误提示（el-message 或内联文字）
  │ emit('stt-error', {...})
  ↓
IDLE（自动重置，3 秒后或用户关闭提示）
```

#### 3.4 浏览器兼容性检测

```javascript
// 组件 onMounted 时执行（REQ-FUNC-028）
const isMediaRecorderSupported = computed(() => {
  return !!(
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    typeof window.MediaRecorder !== 'undefined'
  )
})
// isMediaRecorderSupported=false → 按钮显示为禁用 + tooltip
// 同时通过 emit 通知父组件（供 ChatView 隐藏或调整布局）
```

#### 3.5 WS 连接策略（/ws/stt/）

- STTButton.vue 的 WS 连接**按需建立**（每次点击开始录音时建立），识别完成或出错后关闭。
- 不在 onMounted 时建立常驻连接（避免资源浪费，满足 REQ-NFR-016 AC-NFR-016-01）。
- WS URL 构建方式与 ChatView.vue 相同（自动 ws:// / wss://，取 window.location.host）。

---

### MOD-FE-01 修改：ChatView.vue（最小侵入）

**修改性质**：最小侵入，仅追加必要引用，不修改现有逻辑。
**修改内容**：

1. 在输入区追加 `<STTButton>` 组件（麦克风按钮），位于 el-input 和发送按钮旁。
2. 传入 props：`:isWaiting="isWaiting"` 和 `:wsToken="token"`。
3. 监听 emit：`@stt-final="inputText = $event"`（将识别文字注入输入框）。
4. 监听 `@stt-error`（展示错误提示，复用现有 errorMessage ref）。
5. import STTButton from '@/components/STTButton.vue'。

**不修改**：
- ChatView.vue 的 WS 连接逻辑（/ws/chat/）
- handleSend、handleMessage、connectWS 等函数
- messages ref 结构
- reasoning 相关逻辑
- isWaiting 状态的计算和控制

---

### MOD-BE-04 修改：routing.py（追加路由）

**修改性质**：单行追加，不修改现有路由。

```python
# api/routing.py — 追加 STTConsumer 路由
from django.urls import re_path
from api.consumers import ChatConsumer, STTConsumer  # 追加 STTConsumer

websocket_urlpatterns = [
    re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    re_path(r'^ws/stt/$', STTConsumer.as_asgi()),   # 新增
]
```

---

## 2. 依赖关系图

```
MOD-FE-02 (STTButton.vue)
    ↓ props/emit
MOD-FE-01 (ChatView.vue) ← 仅追加 STTButton 引用（现有逻辑冻结）

MOD-FE-02 (STTButton.vue)
    ↓ WS /ws/stt/
MOD-BE-05 (STTConsumer)
    ↓ async context manager
MOD-BE-06 (VolcASRClient)
    ↓ aiohttp WS client
火山 ASR WSS

MOD-BE-04 (routing.py) ← 追加 STTConsumer 路由
    ↓ 引用
MOD-BE-05 (STTConsumer)

MOD-BE-03 (asgi.py) ← 不变
    ↓ 引用（现有）
MOD-BE-04 (routing.py)

冻结模块（不参与依赖变更）：
MOD-BE-01 (ChatConsumer v1.3)
MOD-BE-02 (OpenClawAdapter v1.3)
chat_memory 模块
```

**无循环依赖验证**：
- MOD-FE-02 → MOD-BE-05 → MOD-BE-06（单向）
- MOD-BE-04 → MOD-BE-05（单向）
- MOD-BE-03 → MOD-BE-04（单向，不变）
- MOD-FE-02 → MOD-FE-01（通过 emit 反向，但这是 Vue 父子通信，非模块依赖循环）

---

## 3. 接口类型化汇总

| 接口 | 输入类型 | 输出类型 | 异常 |
|------|---------|---------|------|
| `STTConsumer.connect()` | WS query_string token | None（副作用：accept + 发送 stt_connected） | close(4001) |
| `STTConsumer.disconnect(close_code)` | int | None（副作用：close VolcASRClient） | 降级（不抛出） |
| `STTConsumer.receive(text_data, bytes_data)` | str \| None, bytes \| None | None（副作用：转发 audio / 控制帧） | stt_error WS frame |
| `VolcASRClient.__aenter__()` | — | VolcASRClient | VolcASRConnectionError |
| `VolcASRClient.__aexit__(...)` | exc 三元组 | None | — |
| `VolcASRClient.send_audio_chunk(chunk)` | bytes | None | RuntimeError（未连接） |
| `VolcASRClient.send_eos()` | — | None | aiohttp.ClientError |
| `VolcASRClient.iter_results()` | — | AsyncGenerator[dict[str, Any], None] | asyncio.TimeoutError, aiohttp.ClientError |
| `STTButton` props | {isWaiting: bool, wsToken: str, disabled?: bool} | — | — |
| `STTButton` emits | — | stt-final(str), stt-partial(str), stt-error({code,message}), recording-state-change(state) | — |

---

## 4. 需求覆盖矩阵

| 需求编号 | 需求名称 | 覆盖模块 |
|---------|---------|---------|
| REQ-FUNC-018 | 麦克风权限授权 | MOD-FE-02（getUserMedia + NotAllowedError 处理）|
| REQ-FUNC-019 | 录音控制与状态反馈 | MOD-FE-02（状态机 RECORDING 状态 + 计时器 + 按钮状态）|
| REQ-FUNC-020 | 流式语音识别文本展示 | MOD-FE-02（stt_partial 接收 + 文字更新）+ MOD-BE-05（转发 stt_partial）|
| REQ-FUNC-021 | 录音时长限制 | MOD-FE-02（计时器 + 80% 预警）+ MOD-BE-05（STT_MAX_RECORD_SECONDS 超时）|
| REQ-FUNC-022 | VAD 静音检测 | MOD-FE-02（P1，ADR-019）|
| REQ-FUNC-023 | 语音识别文本注入策略 | MOD-FE-02（emit stt-final）+ MOD-FE-01（inputText = $event）|
| REQ-FUNC-024 | 错误处理与降级 | MOD-FE-02（stt_error 处理）+ MOD-BE-05（错误码）+ MOD-BE-06（重试）|
| REQ-FUNC-025 | 隐私与音频数据处理 | MOD-BE-05（ARCH-C-013 不落地）+ MOD-FE-02（录音指示 ARCH-C-016）|
| REQ-FUNC-026 | 与 reasoning 流的共存 | MOD-FE-02（isWaiting prop 禁用）+ MOD-FE-01（最小侵入修改）|
| REQ-FUNC-027 | 一次会话内多次语音输入 | MOD-FE-02（状态机重置 → IDLE）|
| REQ-FUNC-028 | 浏览器兼容性 | MOD-FE-02（isMediaRecorderSupported 检测）|
| REQ-NFR-015 | 语音识别延迟 | MOD-BE-06（流式 iter_results）+ MOD-FE-02（stt-partial 即时渲染）|
| REQ-NFR-016 | 资源回收与连接管理 | MOD-BE-05（disconnect 回收）+ MOD-BE-06（__aexit__ 关闭）|
| REQ-NFR-017 | 安全：secret key 隔离 | MOD-BE-06（只读 os.environ，不传出）|
| REQ-NFR-018 | 可维护性：不破坏已有功能 | MOD-BE-04（追加路由）+ MOD-FE-01（最小侵入）+ 冻结 MOD-BE-01/02 |
| REQ-NFR-019 | 用户感知隐私透明度 | MOD-FE-02（状态机 RECORDING 状态 + 持续可见指示）|

---

## 5. 新增文件清单

| 文件路径 | 模块 | 性质 |
|---------|------|------|
| `FreeArkWeb/backend/freearkweb/api/volc_asr_client.py` | MOD-BE-06 | 新建 |
| `FreeArkWeb/frontend/src/components/STTButton.vue` | MOD-FE-02 | 新建 |

## 6. 修改文件清单（最小侵入）

| 文件路径 | 模块 | 修改内容 | 不修改内容 |
|---------|------|---------|----------|
| `FreeArkWeb/backend/freearkweb/api/consumers.py` | MOD-BE-05 | 追加 STTConsumer 类 | ChatConsumer 全部代码冻结 |
| `FreeArkWeb/backend/freearkweb/api/routing.py` | MOD-BE-04 | 追加 /ws/stt/ 路由 | /ws/chat/ 路由不变 |
| `FreeArkWeb/frontend/src/views/ChatView.vue` | MOD-FE-01 | 引入 STTButton 组件 + inputText emit 处理 | WS 连接、handleSend、reasoning 逻辑全部冻结 |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | — | 追加 STT_* 配置项（读取 .env） | 现有 settings 不变 |

---

## 7. GROUP_D 测试位置预告（PM-DEC-002 延续）

依照 PM-DEC-002 纪律，GROUP_D 所有新测试文件须放在：
```
api/tests/test_voice_*.py
```
禁止：
- `api/tests.py`（PM-DEC-002 已确认禁用）
- `api/tests/test_reasoning_stream.py` 中追加语音测试（保持文件职责单一）
