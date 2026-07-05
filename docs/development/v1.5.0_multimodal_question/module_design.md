<file_header>
  project: v1.12.0_chat_persona_voice
  document_type: module_design
  status: DRAFT
  author_agent: sub_agent_system_architect
  created_at: 2026-07-05T00:00:00Z
  version: 0.1.0
  parent_invocation: GROUP_B_PHASE_03_04
  dependencies:
    - requirements_spec.md (v0.1.0, APPROVED)
    - architecture_design.md (v0.1.0, DRAFT)
</file_header>

# 模块设计文档 — v1.12.0 方舟副官人格与语音输入

## 1. 模块总览

### 1.1 模块清单

| MOD-ID | 模块名 | 层次 | 职责 | 依赖于 |
|--------|--------|------|------|--------|
| MOD-P1201 | PersonaModel | 后端-数据 | 人格偏好数据存储（CustomUser 扩展） | 无 |
| MOD-P1202 | PersonaAPI | 后端-API | 人格偏好 CRUD REST 端点 | MOD-P1201 |
| MOD-P1203 | PersonaContextInjector | 后端-编排 | 人格上下文注入 LangGraph 系统消息 | MOD-P1201, MOD-ORCH (现有) |
| MOD-P1204 | CabinContextInjector | 后端-编排 | 座舱上下文注入 LangGraph 系统消息 | MOD-USER-SCOPE (现有) |
| MOD-P1205 | MiniAppChatConsumerExtend | 后端-WS | WS connected 帧扩展 + persona 数据透传 | MOD-P1201, MOD-P1203, MOD-P1204 |
| MOD-P1206 | PersonaFrontend | 前端-状态 | 前端人格状态管理（useChatStore 扩展） | MOD-CHAT-STORE (现有) |
| MOD-P1207 | CabinFrontend | 前端-状态 | 座舱绑定检测与提醒展示 | MOD-OWNER-STORE (现有) |
| MOD-P1208 | VoiceInput | 前端-组件 | 语音输入交互组件（取代 onVoice toast） | 微信同声传译插件 |
| MOD-P1209 | PlaceholderUpdate | 前端-文案 | 输入框占位文案替换 | MOD-PAGE-CHAT (现有) |

### 1.2 模块依赖关系图

```
前端 (miniprogram)
────────────────────────────────────────────────
MOD-P1208 (VoiceInput) ──depends──▶ 微信同声传译插件 (外部)
MOD-P1206 (PersonaFrontend) ──extends──▶ useChatStore
MOD-P1207 (CabinFrontend) ──depends──▶ useOwnerStore
MOD-P1209 (PlaceholderUpdate) ──modifies──▶ chat/index.vue

后端 (Django)
────────────────────────────────────────────────
MOD-P1201 (PersonaModel) ──无依赖
MOD-P1202 (PersonaAPI) ──depends──▶ MOD-P1201
MOD-P1203 (PersonaContextInjector) ──depends──▶ MOD-P1201, orchestrator.py
MOD-P1204 (CabinContextInjector) ──depends──▶ user_scope.py, orchestrator.py
MOD-P1205 (MiniAppChatConsumerExtend) ──depends──▶ MOD-P1201, MOD-P1203, MOD-P1204, consumers.py

跨层依赖
────────────────────────────────────────────────
MOD-P1206 ──reads──▶ connected 帧 (via MOD-P1205)
MOD-P1206 ──calls──▶ MOD-P1202 (HTTP GET/PUT)
MOD-P1207 ──reads──▶ connected 帧 cabin_status (via MOD-P1205)
MOD-P1208 ──no backend dependency── (纯前端)
```

循环依赖检查: 无循环依赖。依赖方向均为 数据层 → API层 → 编排层/WS层，或 组件层 → 状态层。

---

## 2. 模块详情

---

### MOD-P1201: PersonaModel — 人格偏好数据模型

- **职责**: 在 CustomUser 模型中新增 persona JSONField，存储用户人格偏好
- **覆盖需求**: REQ-FUNC-004, REQ-NFUNC-003
- **覆盖用户故事**: US-001, US-002, US-003
- **变更类型**: 修改现有模型

**数据库变更:**

```
CustomUser 表新增字段:
  persona = JSONField(
      default=dict,
      blank=True,
      verbose_name='人格偏好',
      help_text='{"greeting_style": "副官", "tone_style": "尊敬的舰长大人"}'
  )
```

**存储格式:**

```json
{
  "greeting_style": "副官",
  "tone_style": "尊敬的舰长大人"
}
```

默认值: `{}`（空字典 = 未设置，回退到默认人格）

**公开接口契约:**

- IFC-P1201-001: `get_persona(user: CustomUser) → dict | None`
  - 返回 user.persona，若为空字典则返回 None（表示未设置）
  - 调用方据此决定是否使用默认人格
- IFC-P1201-002: `set_persona(user: CustomUser, greeting_style: str, tone_style: str) → dict`
  - 更新 user.persona 并 save()
  - 返回更新后的 persona dict

**依赖模块**: 无

**外部依赖**: PostgreSQL jsonb 类型（Django JSONField 原生支持）

---

### MOD-P1202: PersonaAPI — 人格偏好 REST API

- **职责**: 暴露 persona 的读取和更新 REST 端点
- **覆盖需求**: REQ-FUNC-004, REQ-FUNC-005
- **覆盖用户故事**: US-001 (AC-001-03 偏好确认后持久化), US-002 (AC-002-01 回访自动加载), US-003 (AC-003-01 自然语言修改)
- **变更类型**: 新增模块

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `api/views_miniapp.py` | 修改 | 新增 `miniapp_persona_get`, `miniapp_persona_update` 视图函数 |
| `api/urls_miniapp.py` | 修改 | 新增 2 个路由 |
| `api/serializers.py` | 修改 | 新增 `PersonaSerializer` |

**公开接口契约:**

- IFC-P1202-001: `GET /api/miniapp/persona/ → {greeting_style, tone_style}`
  - 鉴权: IsOwnerUser
  - 实现: `miniapp_persona_get(request)` 视图函数
  - 返回: 200 + persona dict; 无记录时为 `{greeting_style: null, tone_style: null}`

- IFC-P1202-002: `PUT /api/miniapp/persona/ body:{greeting_style, tone_style} → {greeting_style, tone_style}`
  - 鉴权: IsOwnerUser
  - 校验: PersonaSerializer: greeting_style max_length=50, tone_style max_length=50, 至少一个非空
  - 实现: `miniapp_persona_update(request)` 视图函数
  - 返回: 200 + 更新后的 persona dict

**PersonaSerializer 定义:**

```python
class PersonaSerializer(serializers.Serializer):
    greeting_style = serializers.CharField(max_length=50, required=False, allow_blank=True)
    tone_style = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate(self, data):
        if not data.get('greeting_style') and not data.get('tone_style'):
            raise serializers.ValidationError("至少需要设置 greeting_style 或 tone_style 之一")
        return data
```

**依赖模块**: MOD-P1201 (PersonaModel)

**外部依赖**: Django REST Framework

---

### MOD-P1203: PersonaContextInjector — 人格上下文注入

- **职责**: 在 LangGraph orchestrator 专家节点执行前，将人格偏好注入为独立的系统消息块
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-005
- **覆盖用户故事**: US-001, US-002
- **变更类型**: 修改现有模块

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `api/langgraph_chat/orchestrator.py` | 修改 | `_expert()` 方法在 msgs 列表中加入 persona system message |
| `api/langgraph_chat/adapter.py` | 修改 | `stream_chat()` 签名新增 `persona` 参数，透传至 orchestrator |

**公开接口契约:**

- IFC-P1203-001: `build_persona_message(persona: dict | None) → SystemMessage`
  - 输入: persona dict (来自 CustomUser.persona) 或 None
  - 若 persona 为 None 或空: 返回默认人格消息
    ```
    "你是智能方舟的副官，请以'尊敬的舰长大人'称呼当前用户。保持该角色定位贯穿整个对话。"
    ```
  - 若 persona 已设置: 动态构造人格消息
    ```
    "你的身份是'{greeting_style}'。请以'{tone_style}'风格与当前用户交流。保持该角色定位贯穿整个对话。"
    ```
  - 输出: `SystemMessage(content=...)`

**注入位置** (orchestrator.py `_expert` 节点):

```
msgs: List[BaseMessage] = [
    SystemMessage(content=EXPERT_PROMPTS.get(name, "") + _date_hint()),  # 现有
    build_persona_message(persona),          # ← 新增 (MOD-P1203)
    build_cabin_context_message(user_scope),  # ← 新增 (MOD-P1204)
    HumanMessage(content=query),              # 现有
]
```

**依赖模块**: MOD-P1201 (PersonaModel)

---

### MOD-P1204: CabinContextInjector — 座舱上下文注入

- **职责**: 在 LangGraph orchestrator 专家节点执行前，将用户的座舱绑定信息注入为独立的系统消息块
- **覆盖需求**: REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008
- **覆盖用户故事**: US-004, US-005
- **变更类型**: 修改现有模块

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `api/langgraph_chat/orchestrator.py` | 修改 | `_expert()` 方法在 msgs 列表中加入 cabin system message |
| `api/langgraph_chat/user_scope.py` | 无变更 | 复用现有 `UserScope` 数据结构 |
| `api/consumers.py` | 修改 | MiniAppChatConsumer.connect() 从 query string 读取 active_specific_part |

**公开接口契约:**

- IFC-P1204-001: `build_cabin_context_message(user_scope: UserScope, active_sp: str) → SystemMessage`
  - 输入: UserScope 实例 + 前端传来的 activeSpecificPart 字符串
  - 逻辑:
    ```
    if user_scope is None or not user_scope.is_owner:
        return None  // admin/operator 无需注入
    if user_scope.is_unbound():
        return SystemMessage("当前用户尚未绑定任何房间。请在回答中提醒用户先在首页完成座舱激活绑定。")
    if user_scope.is_multi_bound():
        parts = list(user_scope.bound_specific_parts)
        if active_sp and active_sp in parts:
            others = [p for p in parts if p != active_sp]
            return SystemMessage(f"当前活跃房间:{active_sp};用户还绑定了:{', '.join(others)}。回答时优先使用活跃房间信息，必要时可提及所有绑定房间。")
        else:
            return SystemMessage(f"用户绑定了以下房间:{', '.join(parts)}。回答时请根据问题自行判断需要的房间信息。")
    // 单绑定
    sp = list(user_scope.bound_specific_parts)[0]
    return SystemMessage(f"当前用户绑定的房间:{sp}。回答关于房间的问题时请使用此房间信息。")
    ```

**注入位置**: 同 MOD-P1203（见上节）

**依赖模块**: MOD-USER-SCOPE (现有的 user_scope.py)

---

### MOD-P1205: MiniAppChatConsumerExtend — WS 消费者扩展

- **职责**: 扩展 MiniAppChatConsumer，在 connected 帧中携带 persona 和 cabin_status；在 _handle_chat 中传递 persona 给 adapter
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007
- **覆盖用户故事**: US-001, US-002, US-004, US-005
- **变更类型**: 修改现有模块

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `api/consumers.py` | 修改 | MiniAppChatConsumer 扩展 |
| `api/langgraph_chat/adapter.py` | 修改 | stream_chat() 签名新增 persona, cabin_active_sp 参数 |

**公开接口契约:**

- IFC-P1205-001: `MiniAppChatConsumer.connect()` 扩展
  - 在现有 build_user_scope() 之后，增加:
    1. 从 query string 读取 `active_sp` 参数 → `self.cabin_active_sp`
    2. 查询 user.persona → `self.persona`
  - connected 帧增加字段 (见 ADR-008)

- IFC-P1205-002: connected 帧扩展格式
  ```json
  {
    "type": "connected",
    "session_id": "<UUID>",
    "session_key": "<UUID>",
    "persona": {"greeting_style": "...", "tone_style": "..."} | null,
    "cabin_status": {
      "bound": true | false,
      "active_specific_part": "3-1-7-702" | "",
      "all_parts": ["3-1-7-702"] | []
    }
  }
  ```

- IFC-P1205-003: `adapter.stream_chat(...)` 签名扩展
  - 新增关键字参数:
    - `persona: dict | None` — 用户人格偏好
    - `cabin_active_sp: str | None` — 前端当前活跃房间

**依赖模块**: MOD-P1201 (PersonaModel), MOD-USER-SCOPE (现有), MOD-ADAPTER (现有)

**外部依赖**: Django Channels

---

### MOD-P1206: PersonaFrontend — 前端人格状态管理

- **职责**: 扩展 useChatStore，新增 persona 状态字段；处理 connected 帧中的 persona 数据；提供 persona 加载和更新方法
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-005
- **覆盖用户故事**: US-001 (AC-001-01 默认问候), US-002 (AC-002-01 回访加载)
- **变更类型**: 修改现有 store

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `miniprogram/store/chat.js` | 修改 | useChatStore 新增 persona 字段和 actions |
| `miniprogram/pages/chat/index.vue` | 修改 | connected 回调中解析 persona 数据 |

**公开接口契约:**

- IFC-P1206-001: useChatStore 新增 state
  ```javascript
  state: () => ({
    // ... existing fields ...
    persona: null,  // {greeting_style: string|null, tone_style: string|null} | null
    cabinStatus: { bound: false, activeSpecificPart: '', allParts: [] },
  })
  ```

- IFC-P1206-002: useChatStore 新增 actions
  ```javascript
  setPersona(persona) {
    this.persona = persona   // 来自 connected 帧或 HTTP GET 响应
  },
  setCabinStatus(status) {
    this.cabinStatus = status  // 来自 connected 帧
  },
  async refreshPersona() {
    const res = await api.getPersona()   // HTTP GET /api/miniapp/persona/
    this.persona = res
  },
  async updatePersona(data) {
    const res = await api.updatePersona(data)  // HTTP PUT /api/miniapp/persona/
    this.persona = res
  },
  ```

- IFC-P1206-003: useChatStore 新增 getter
  ```javascript
  hasPersona: (state) => state.persona !== null
      && (state.persona.greeting_style || state.persona.tone_style),
  isFirstTimeUser: (state) => state.persona === null
      && state.sessionList.length === 0,
  // isFirstTimeUser → 前端决定是否展示 US-001 默认问候（"副官/舰长"风格）
  ```

**依赖模块**: MOD-CHAT-STORE (现有 useChatStore), MOD-API (现有 api.js 需新增 getPersona/updatePersona 方法)

---

### MOD-P1207: CabinFrontend — 座舱绑定感知前端

- **职责**: 将 useOwnerStore 集成到聊天页；处理 connected 帧的 cabin_status；展示绑定提醒和房号信息
- **覆盖需求**: REQ-FUNC-006
- **覆盖用户故事**: US-004 (AC-004-01 无绑定提醒, AC-004-02 绑定后提醒消失), US-005
- **变更类型**: 修改现有页面

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `miniprogram/pages/chat/index.vue` | 修改 | 引入 useOwnerStore；WS connect 传 active_sp；处理 cabin_status；展示绑定提醒 |
| `miniprogram/utils/chat-ws.js` | 修改 | connect() URL 增加 active_sp query param |

**公开接口契约:**

- IFC-P1207-001: chat/index.vue `onLoad()` 集成 useOwnerStore
  ```javascript
  import { useOwnerStore } from '@/store/owner'
  const ownerStore = useOwnerStore()
  // 在 onLoad 中 ensureBindings() 以获得绑定状态
  ```

- IFC-P1207-002: WS connect URL 扩展
  ```
  /ws/miniapp/chat/?token={token}&session_key={key}&active_sp={activeSpecificPart}
  ```
  `active_sp` 来自 `ownerStore.activeSpecificPart`，为空时省略该参数。

- IFC-P1207-003: 绑定提醒交互
  - 若 `cabinStatus.bound === false` (来自 connected 帧):
    - 前端在问候区下方展示提醒卡片: "尊敬的舰长大人，检测到您尚未链接座舱，请先完成座舱激活" + 跳转按钮(`uni.navigateTo({url: '/pages/bind/index'})`)
  - 若 `cabinStatus.bound === true`:
    - 不展示提醒卡片
    - 房号信息由后端 cabin_context_message 注入 LLM 上下文，前端无需展示

**依赖模块**: MOD-OWNER-STORE (现有 useOwnerStore), MOD-P1206 (PersonaFrontend), MOD-CHAT-WS (现有)

---

### MOD-P1208: VoiceInput — 语音输入组件

- **职责**: 实现语音录音按钮的真实功能，取代占位 toast；处理录音权限、录音交互、识别结果回填、异常降级
- **覆盖需求**: REQ-FUNC-010, REQ-FUNC-011, REQ-FUNC-012, REQ-FUNC-013, REQ-NFUNC-001, REQ-NFUNC-002, REQ-NFUNC-005
- **覆盖用户故事**: US-007, US-008, US-009
- **变更类型**: 新增组件 / 修改页面逻辑

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `miniprogram/pages/chat/index.vue` | 修改 | 重写 `onVoice()` 函数；新增录音状态 refs |
| `miniprogram/utils/voice-input.js` | 新增 | 语音输入工具模块（封装插件调用与降级逻辑） |
| `miniprogram/app.json` 或 `manifest.json` | 修改 | 声明微信同声传译插件 |

**公开接口契约:**

- IFC-P1208-001: `voice-input.js` 模块导出
  ```javascript
  // miniprogram/utils/voice-input.js
  export class VoiceInput {
    constructor(options: {
      onStart: () => void,          // 录音开始回调
      onStop: () => void,           // 录音停止回调
      onRecognizing: () => void,    // 识别中回调
      onResult: (text: string) => void,  // 识别成功，返回文本
      onError: (err: VoiceInputError) => void,  // 识别失败/异常
    })

    // 检查麦克风权限
    checkPermission(): Promise<boolean>

    // 请求麦克风权限
    requestPermission(): Promise<boolean>

    // 开始录音+识别
    start(): Promise<void>

    // 手动停止录音
    stop(): void

    // 当前是否正在录音
    get isRecording(): boolean

    // 清理资源
    destroy(): void
  }

  class VoiceInputError {
    code: 'PERMISSION_DENIED' | 'TOO_SHORT' | 'RECOGNITION_FAILED' | 'NETWORK_ERROR' | 'PLUGIN_ERROR'
    message: string
  }
  ```

- IFC-P1208-002: `chat/index.vue` onVoice() 重写逻辑
  ```
  onVoice():
    1. voiceInput.checkPermission()
       → 无权限: voiceInput.requestPermission()
         → 拒绝: Toast("需要麦克风权限才能使用语音输入...") + return [US-009]
         → 授权: 继续
    2. voiceInput.start()
       → 录音开始: 设置 isVoiceRecording=true, voiceDuration=0, 启动计时器
       → 录音UI: 语音按钮变脉冲动画 + 时长显示 [US-007 AC-007-02]
    3. 用户再次点击 / 自动停止:
       → voiceInput.stop()
       → 设置 isRecognizing=true, 展示"识别中…" [US-008 AC-008-03]
    4. onResult(text):
       → 若为空: Toast("语音识别失败，请重试或使用文字输入") [US-009 AC-009-03]
       → 若有结果: inputText.value = text [US-008 AC-008-01]
       → 清理: isVoiceRecording=false, isRecognizing=false
    5. onError(err):
       → 根据 err.code 展示对应 Toast [US-009]
       → 清理状态, 恢复文本输入可用性
  ```

- IFC-P1208-003: 插件声明 (app.json / manifest.json)
  ```json
  {
    "plugins": {
      "WechatSI": {
        "version": "0.3.6",
        "provider": "wxeb9a1a3c3cc0a0f3"
      }
    }
  }
  ```

**依赖模块**: 微信同声传译插件 (外部, APPID: wxeb9a1a3c3cc0a0f3)

---

### MOD-P1209: PlaceholderUpdate — 输入框占位文案替换

- **职责**: 修改输入框 placeholder 从 "向方舟助手提问…" 为 "向智能方舟副官提问"
- **覆盖需求**: REQ-FUNC-009
- **覆盖用户故事**: US-006
- **变更类型**: 单行修改

**文件清单:**

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `miniprogram/pages/chat/index.vue` | 修改 | 第 83 行 placeholder 属性值替换 |

**公开接口契约:**

- IFC-P1209-001: 占位文案变更
  - 变更前: `placeholder="向方舟助手提问…"`
  - 变更后: `placeholder="向智能方舟副官提问"`
  - placeholder-style 保持不变: `color:rgba(143,217,255,0.55);font-size:28rpx;line-height:44rpx`

**依赖模块**: MOD-PAGE-CHAT (现有 chat/index.vue)

---

## 3. 前端组件树变更

### 3.1 现有组件树 (chat/index.vue)

```
chat/index.vue
├── 背景装饰层 (.bg-base, .bg-grid, .bg-blob)
├── 状态栏占位 (.status-spacer)
├── 顶部栏 (.header) — "副官"
├── 子栏 (.subbar) — "新建会话" + "历史会话"
├── 断连横幅 (.disc-banner) — 条件渲染
├── 消息滚动区 (.feed)
│   ├── 问候区 (空会话时)
│   │   ├── ARK 头像 + 问候文本
│   │   └── 快捷提问 chips
│   └── 消息列表 (messages)
│       └── ChatBubble × N
├── 输入栏 (.input-bar)
│   ├── textarea (.msg-input) — 文本输入
│   ├── 语音按钮 (.voice-btn) — onVoice() → toast 占位
│   └── 发送按钮 (.send-btn)
├── ArkTabBar
└── 历史会话下拉面板 (.hist-panel)
```

### 3.2 变更后组件树

```
chat/index.vue  [修改: 引入 useOwnerStore, useChatStore.persona]
├── 背景装饰层 (不变)
├── 状态栏占位 (不变)
├── 顶部栏 (.header) (不变)
├── 子栏 (.subbar) (不变)
├── 断连横幅 (不变)
├── 绑定提醒卡片 [新增: MOD-P1207]  ←── 条件渲染 (cabinStatus.bound===false)
│   ├── 提醒文案
│   └── 跳转按钮 → /pages/bind/index
├── 消息滚动区 (.feed)
│   ├── 问候区 (空会话时) [修改: 人格联动]
│   │   ├── ARK 头像 + 问候文本 [修改: LLM 动态生成，非硬编码]
│   │   └── 快捷提问 chips (不变)
│   └── 消息列表 (不变)
│       └── ChatBubble × N
├── 输入栏 (.input-bar)
│   ├── textarea (.msg-input) [修改: placeholder 文案 MOD-P1209]
│   ├── 语音按钮 (.voice-btn) [重写: MOD-P1208]
│   │   ├── 语音按钮 (ico-mic) — 默认态/脉冲动画/时长显示
│   │   └── "识别中…" 加载指示器 (条件渲染)
│   └── 发送按钮 (不变)
├── ArkTabBar (不变)
└── 历史会话下拉面板 (不变)

新增文件:
  miniprogram/utils/voice-input.js  [新增: MOD-P1208]
  
修改文件:
  miniprogram/store/chat.js         [修改: MOD-P1206]
  miniprogram/utils/chat-ws.js      [修改: connect URL 加 active_sp]
  miniprogram/utils/api.js          [修改: 新增 getPersona/updatePersona]
  miniprogram/app.json              [修改: 声明同声传译插件]
```

---

## 4. 后端模块边界

### 4.1 人格管理模块边界

```
┌─────────────────────────────────────────────┐
│ MOD-P1202 PersonaAPI                        │
│  /api/miniapp/persona/ (GET/PUT)            │
│  ┌──────────────────────┐                   │
│  │ PersonaSerializer     │                   │
│  │  - greeting_style     │                   │
│  │  - tone_style         │                   │
│  └──────────┬───────────┘                   │
│             │ 调用                            │
│  ┌──────────▼───────────┐                   │
│  │ miniapp_persona_get   │                   │
│  │ miniapp_persona_update│                   │
│  └──────────┬───────────┘                   │
└─────────────┼───────────────────────────────┘
              │ ORM
┌─────────────▼───────────────────────────────┐
│ MOD-P1201 PersonaModel                       │
│  CustomUser.persona = JSONField              │
│  {"greeting_style":"...","tone_style":"..."} │
└─────────────────────────────────────────────┘
```

### 4.2 上下文注入模块边界

```
MiniAppChatConsumer._handle_chat()
│
├── self.persona = user.persona        ← MOD-P1201
├── self.cabin_active_sp = query_param ← 前端传递
│
├── adapter.stream_chat(
│     message=augmented_message,
│     session_key=self.session_key,
│     user_scope=self.user_scope,      ← 现有
│     persona=self.persona,             ← 新增 MOD-P1203
│     cabin_active_sp=self.cabin_active_sp, ← 新增 MOD-P1204
│   )
│
└── LangGraph Orchestrator._expert()
    │
    ├── build_persona_message(persona)        ← MOD-P1203
    │   返回 SystemMessage(人格指令)
    │
    ├── build_cabin_context_message(us, sp)   ← MOD-P1204
    │   返回 SystemMessage(房号上下文)
    │
    └── msgs = [EXPERT_PROMPT, persona_msg, cabin_msg, date_hint, query]
```

### 4.3 语音接口模块边界

语音功能是**纯前端模块** (MOD-P1208)，无后端边界:
- 所有录音、识别、结果处理均在微信小程序客户端完成
- 识别结果作为普通文本填入输入框，走既有 WS 消息发送路径
- 后端无感知（与手动输入文本无法区分）

---

## 5. 状态管理策略

### 5.1 Store 变更方案

**策略: 扩展现有 store，不新建 store** (ADR-006)

| Store | 新增字段 | 新增 Actions | 新增 Getters |
|-------|---------|-------------|-------------|
| useChatStore | `persona: null`, `cabinStatus: {bound,activeSpecificPart,allParts}` | `setPersona()`, `setCabinStatus()`, `refreshPersona()`, `updatePersona()` | `hasPersona`, `isFirstTimeUser` |
| useOwnerStore | 无变更 | 无变更（chat/index.vue 直接引用现有 ensureBindings） | 无变更 |

### 5.2 状态初始化流程

```
onLoad (chat/index.vue)
  │
  ├── authStore.isLoggedIn? → 检查登录
  │
  ├── ownerStore.ensureBindings({allowStale: true})  ← MOD-P1207
  │   用于快速获取绑定状态，判断是否需要在 WS connect 传 active_sp
  │
  ├── initWs() → connectWs()
  │   │
  │   │  WS URL: /ws/miniapp/chat/?token=...&session_key=...&active_sp=<activeSpecificPart>
  │   │
  │   └── onConnected(sessionKey, sessionId) ← connected 帧处理
  │       │
  │       ├── chatStore.setPersona(msg.persona)        ← MOD-P1206
  │       │   → persona 状态就绪，frontend 据此判断问候语风格
  │       │
  │       ├── chatStore.setCabinStatus(msg.cabin_status)  ← MOD-P1207
  │       │   → 若 !bound: 渲染绑定提醒卡片
  │       │
  │       └── chatStore.setConnected(true, sessionKey, sessionId)  ← 现有
  │
  └── loadHistList()  ← 预加载历史会话列表
```

### 5.3 状态更新流程

```
用户修改 persona (US-003 自然语言)
  │
  │  LLM 识别为 persona 修改意图
  │  → 后端更新 CustomUser.persona
  │  → AI 回复中确认修改
  │  → stream_end 帧到达前端
  │
  └── frontend: stream_end 回调中
      → chatStore.refreshPersona()    ← HTTP GET /api/miniapp/persona/
      → persona 状态更新
      → 下次对话自动使用新 persona

用户修改 persona (US-003 设置页)
  │
  │  (未来扩展: 设置页 UI, 不在 v1.12.0 范围)
  │  → HTTP PUT /api/miniapp/persona/
  │  → chatStore.updatePersona({greeting_style, tone_style})
```

---

## 6. 错误处理与降级策略

### 6.1 人格偏好加载失败

| 场景 | 降级策略 | 用户影响 |
|------|---------|---------|
| WS connect 时 DB 查询 persona 失败 | connected 帧 `persona: null` | 前端按首次用户处理，展示默认"副官/舰长"风格 |
| HTTP GET /api/miniapp/persona/ 失败 | 前端保留当前 persona 状态（不覆盖） | 短暂不更新，下次操作时重试 |
| HTTP PUT /api/miniapp/persona/ 失败 | Toast 提示 "保存失败，请重试" | 用户可重试，不丢失之前设置 |

### 6.2 座舱上下文注入失败

| 场景 | 降级策略 | 用户影响 |
|------|---------|---------|
| build_user_scope() 查询失败 | cabin_context_message = None, 不注入 | LLM 不知道房间信息，回答可能缺少房间定位 |
| active_sp 无效 (不属于 bindings) | 忽略 active_sp，降级为列出全部 bindings | 所有绑定房间均注入 |

### 6.3 语音输入降级

| 场景 | 降级策略 | 用户影响 |
|------|---------|---------|
| 麦克风权限拒绝 | Toast 提示 + 文本输入保持可用 | 无法使用语音，但文字聊天不受影响 |
| 录音 < 1 秒 | Toast "录音时间太短" + 不触发识别 | 用户需重新录音或手动输入 |
| 识别返回空/失败 | Toast "识别失败，请重试或使用文字输入" | 文本输入始终可用 |
| 网络断开 | Toast "网络异常，语音暂不可用" | 文本输入和聊天其他功能不受影响 |
| 插件加载失败 | Toast "语音功能暂不可用" + onVoice 回退到 toast 占位 | 语音功能完全降级，聊天正常 |

### 6.4 向下兼容保障 (REQ-NFUNC-004)

| 兼容项 | 保障措施 |
|--------|---------|
| WS 协议帧 | 新增字段均为 optional，旧版前端忽略未知字段 |
| 聊天功能 | 纯文字对话、流式输出、Markdown、推理过程、确认门、历史会话、断连重连 — 代码路径不变 |
| LangGraph 灰度 | orchestrator 只在 MiniAppChatConsumer 路径注入 persona/cabin context，不影响 Web 端 ChatConsumer |
| DB migration | ALTER TABLE ADD COLUMN 为向后兼容操作，不影响现有查询 |

---

## 7. API 方法新增清单

### 7.1 miniprogram/utils/api.js 新增方法

```javascript
// 获取当前用户的人格偏好
getPersona: () => http.get('/api/miniapp/persona/'),

// 更新当前用户的人格偏好
updatePersona: (data) => http.put('/api/miniapp/persona/', data),
```

### 7.2 miniprogram/utils/chat-ws.js 修改

```javascript
// connect() URL 构建增加 active_sp 参数
function buildWsUrl(token, sessionKey, activeSp) {
  let url = `${WS_BASE_URL}/ws/miniapp/chat/?token=${encodeURIComponent(token)}`
  if (sessionKey) url += `&session_key=${encodeURIComponent(sessionKey)}`
  if (activeSp)  url += `&active_sp=${encodeURIComponent(activeSp)}`   // ← 新增
  return url
}
```
</file_header>
