# 架构决策记录 — v1.5.0 微信小程序移动端

**文档编号**: ARCH-MP-v150-001
**项目名称**: FreeArk 微信小程序移动端（v1.5.0_wechat_miniprogram）
**版本**: 1.0.0
**状态**: DRAFT — 待用户确认
**创建日期**: 2026-06-23
**作者**: system-architect (via pm-orchestrator)
**输入文档**: REQ-SPEC-MP-v150-001, REQ-US-MP-v150-001

---

## 目录

1. 整体架构概述
2. ADR-001 框架选型（uni-app vs Taro）
3. ADR-002 AI 问答实时协议（真实协议分析 + uni-app 复刻方案）
4. ADR-003 实时数据策略（30 秒轮询 vs WebSocket）
5. ADR-004 鉴权与存储适配（Token 持久化、401 重登流程）
6. ADR-005 Markdown 渲染（towxml vs mp-html）
7. ADR-006 分包加载策略
8. ADR-007 小程序代码仓库位置与构建并存
9. 整体架构图（文字描述）
10. 安全合规要求
11. 风险汇总

---

## 1. 整体架构概述

```
微信小程序客户端（uni-app）
    │
    │  HTTPS（REST API）   WSS（AI 问答专用）
    │
Django 后端（树莓派 Pi4 aarch64）
    ├── Nginx（SSL 终止，反向代理）
    ├── Waitress / Daphne（ASGI，HTTP + WebSocket）
    ├── Django REST Framework（Token 认证）
    ├── Django Channels（WebSocket，/ws/chat/）
    ├── LangGraph 编排器（进程内单例）
    └── MySQL（192.168.31.98:3306）
```

小程序客户端与后端的通信分两条通道：
- **REST API**（HTTPS）：所有数据查询、登录、工单审批等操作，由 `uni.request` 统一封装。
- **WebSocket（WSS）**：仅 AI 问答使用，由 `uni.connectSocket` 连接 `/ws/chat/`，占用 1 个并发连接配额（微信限 2 个）。

后端**不新增任何微信专属服务**，完全复用现有 Django 后端。

---

## 2. ADR-001 框架选型

### 决策

**uni-app（Vue 3 + Composition API）**，首发微信小程序。

### 背景与选项对比

| 维度 | uni-app（Vue 3） | Taro（React） |
|------|----------------|--------------|
| 学习曲线 | 现有 FreeArk Web 已是 Vue 3，零切换成本 | React 系，需重新学习 |
| 生态与文档 | uCharts、uni-ui 等生态成熟，中文文档丰富 | NutUI、Taro UI，React 生态 |
| 多端能力 | 编译 H5/App/小程序均成熟 | 同样支持多端 |
| 社区活跃度 | DCloud 官方维护，更新积极 | 京东维护，同样活跃 |
| 单人维护成本 | 与桌面 Web 同语法，维护面最小 | 增加技术栈切换开销 |

### 理由

单人维护场景下，**技术栈一致性是最重要的约束**。现有桌面 Web 为 Vue 3，团队（单人）对 Vue Composition API 已有积累，uni-app 方案零学习开销，且 uCharts/uni-ui 生态直接满足图表与 UI 需求。

### 影响

- 不引入 React/JSX 依赖。
- 状态管理使用 **Pinia**（Vue 3 官方，uni-app 已集成）。
- UI 库使用 **wot-design-uni**（轻量，小程序兼容好；备选 uni-ui）。

---

## 3. ADR-002 AI 问答实时协议

> **架构师注**：本节基于对 `FreeArkWeb/frontend/src/views/ChatView.vue`、`src/utils/api.js`、`api/routing.py`、`api/consumers.py`、`api/langgraph_chat/adapter.py` 的实际阅读，记录真实协议，不含臆测。

### 3.1 真实协议分析

#### WebSocket 端点

```
ws://{host}/ws/chat/?token={userToken}[&session_key={uuid}]
```

鉴权方式：Token 直接作为 **query parameter** 传入（`?token=xxx`），由 `ChatConsumer.connect()` 从 `scope['query_string']` 解析，调用 `_get_user_by_token()` 验证 DRF Token 有效性。**无须 HTTP 头鉴权**，这一点对小程序 WebSocket 非常友好（`wx.connectSocket` 不能在握手阶段携带自定义 Header）。

鉴权失败时，后端关闭连接，`closeCode=4001`。

#### 握手完成后，后端主动推送 `connected` 帧

```json
{
  "type": "connected",
  "session_id": "uuid-string",
  "session_key": "uuid-string"
}
```

前端收到此帧后才将 `wsConnected = true`（非 `onopen` 时刻）。`session_key` 用于后续历史消息查询。

#### 客户端发送消息（`chat_message`）

```json
{
  "type": "chat_message",
  "message": "用户输入文本"
}
```

#### 服务端推送帧类型（完整枚举）

| `type` 字段 | 触发时机 | 关键字段 | 前端处理 |
|------------|---------|---------|---------|
| `connected` | 握手完成后 | `session_key` | 标记 wsConnected=true |
| `status_update` | 分类/查询/生成静默期 | `message`（进度文案） | 显示"正在思考…"状态文案 |
| `reasoning_token` | DeepSeek 等思考型 LLM 的 reasoning 增量 | `token` | 追加到折叠区 |
| `reasoning_end` | reasoning 阶段结束 | — | 折叠 reasoning 区 |
| `stream_token` | AI 正文 token 增量 | `token` | 追加到消息气泡 |
| `stream_end` | 本轮 AI 回答完毕 | — | 关闭流式光标，触发 Markdown 渲染 |
| `confirm_required` | Tier-2 写操作确认门（巡检审批场景） | `actions` 数组 | 展示确认卡片 |
| `error` | 后端异常 | `code`, `message` | 展示错误提示 |

**客户端额外发送帧**（仅 Tier-2 写确认场景）：

```json
{ "type": "confirm_response", "approved": true }
```

#### 流式策略（基于 adapter.py _drive 函数）

- **单专家路由**：透传 `expert` 节点的 `AIMessageChunk`（逐 token 流）。
- **多专家路由**：跳过各 expert 的 token，流 `aggregate` 节点的融合结果（避免内容交错）。
- `route` 节点的分类 token 不透传。
- 非流式 LLM 兜底：循环结束后从图最终状态取整段答复，一次性推送。
- `INTERNAL_NOSTREAM_TAG` 标记的委托子专家 token 被抑制（防止双重输出）。

#### 后端 WebSocket 路由

```python
# api/routing.py
re_path(r'^ws/chat/$', ChatConsumer.as_asgi())
```

ASGI 路由由 `asgi.py` 的 `ProtocolTypeRouter` 分发，HTTP 走 Django，WebSocket 走 Channels。

#### 历史消息接口（REST）

```
GET /api/memory/me/?page=1&page_size=20       # 会话列表
GET /api/memory/session/{session_key}/history/ # 会话历史消息，返回 {messages:[{role,content,created_at}]}
```

### 3.2 协议对小程序 WebSocket 的友好度分析

**优点（对小程序非常友好）**：
1. Token 鉴权走 query param，不需要在握手 Header 中携带自定义字段，完全符合 `uni.connectSocket` 的能力范围。
2. 消息体为纯 JSON，无二进制帧，`uni.onSocketMessage` 直接 `JSON.parse` 即可处理。
3. 消息类型有明确的 `type` 字段，易于 switch-case 分发。

**需适配点**：
1. **WSS 强制要求**：微信小程序 `wx.connectSocket` 只接受 `wss://` 协议，后端需通过 Nginx 反代提供 WSS 端点（BA-04）。
2. **小程序后台 5 秒挂起**：进入后台后 WebSocket 可能被系统挂起，需在 `onHide` 主动断开（`uni.closeSocket`），`onShow` 重连。
3. **并发连接限制**：微信平台同时最多 2 个 WebSocket，实时数据降级为轮询（ADR-003），保留 1 个给 AI 问答。

### 3.3 uni-app 复刻方案

```javascript
// miniprogram/utils/chat-ws.js

const CHAT_WS_URL = (token, sessionKey) => {
  const base = getApp().globalData.wsBaseUrl  // e.g. 'wss://freeark.example.com'
  let url = `${base}/ws/chat/?token=${encodeURIComponent(token)}`
  if (sessionKey) url += `&session_key=${encodeURIComponent(sessionKey)}`
  return url
}

class ChatWebSocket {
  constructor(callbacks) {
    this.socketTask = null   // uni.connectSocket 返回值
    this.connected = false
    this.callbacks = callbacks  // { onConnected, onToken, onReasoningToken, onStreamEnd,
                                //   onStatusUpdate, onConfirmRequired, onError }
  }

  connect(token, sessionKey) {
    // 先清理旧连接
    this.close()
    this.socketTask = uni.connectSocket({
      url: CHAT_WS_URL(token, sessionKey),
      complete: () => {}
    })
    this.socketTask.onOpen(() => {
      // 等 connected 帧，不在 onOpen 时标记 connected
    })
    this.socketTask.onMessage(({ data }) => {
      const msg = JSON.parse(data)
      switch (msg.type) {
        case 'connected':
          this.connected = true
          this.callbacks.onConnected?.(msg.session_key)
          break
        case 'status_update':
          this.callbacks.onStatusUpdate?.(msg.message)
          break
        case 'reasoning_token':
          this.callbacks.onReasoningToken?.(msg.token)
          break
        case 'reasoning_end':
          this.callbacks.onReasoningEnd?.()
          break
        case 'stream_token':
          this.callbacks.onToken?.(msg.token)
          break
        case 'stream_end':
          this.callbacks.onStreamEnd?.()
          break
        case 'confirm_required':
          this.callbacks.onConfirmRequired?.(msg.actions)
          break
        case 'error':
          this.callbacks.onError?.(msg)
          break
      }
    })
    this.socketTask.onClose(({ code }) => {
      this.connected = false
      this.callbacks.onClose?.(code)
    })
    this.socketTask.onError(() => {
      this.callbacks.onError?.({ code: 'WS_ERROR', message: '连接异常' })
    })
  }

  send(message) {
    if (!this.socketTask || !this.connected) return
    this.socketTask.send({
      data: JSON.stringify({ type: 'chat_message', message })
    })
  }

  sendConfirm(approved) {
    if (!this.socketTask) return
    this.socketTask.send({
      data: JSON.stringify({ type: 'confirm_response', approved })
    })
  }

  close() {
    if (this.socketTask) {
      this.socketTask.close({})
      this.socketTask = null
      this.connected = false
    }
  }
}
```

**页面生命周期管理**：

```javascript
// pages/chat/chat.vue (setup)
onShow(() => {
  if (!chatWs.connected) chatWs.connect(token, sessionKey)
})
onHide(() => {
  chatWs.close()   // 防止后台 5 秒被挂起
})
onUnload(() => {
  chatWs.close()
})
```

**Markdown 渲染时机**：流式期间使用纯文本追加（`content += token`），`stream_end` 后将 `content` 传入 towxml 渲染组件（参见 ADR-005）。

---

## 4. ADR-003 实时数据策略

### 决策

**设备/故障/结露/PLC 状态等数据使用 30 秒轮询**；AI 问答独占 WebSocket。

### 理由

1. 微信小程序最多 2 个并发 WebSocket 连接；AI 问答占 1 个，预留另 1 个给极端场景（不浪费）。
2. 30 秒间隔与树莓派资源限制匹配，MQTT pipeline 已有后台压力（见 memory 中 device_param_history 及 fault-consumer 历史问题）。
3. 实时性要求：三恒系统状态变化频率通常在分钟级，30 秒可接受。

### 轮询实现规范

```javascript
// utils/poller.js
class PagePoller {
  constructor(fn, intervalMs = 30000) {
    this._fn = fn
    this._interval = intervalMs
    this._timer = null
  }
  start() {
    this._fn()  // 立即执行一次
    this._timer = setInterval(this._fn, this._interval)
  }
  stop() {
    if (this._timer) clearInterval(this._timer)
    this._timer = null
  }
}
```

**各页面轮询开停时机**：

| 页面 | start | stop |
|------|-------|------|
| 首页看板 | onShow | onHide |
| PLC 状态 | onShow | onHide |
| 设备卡片 | onShow | onHide |
| 故障列表 | onShow | onHide |
| 结露预警 | onShow | onHide |
| 参数历史图 | 不轮询（用户主动刷新/切 Tab） | — |
| AI 问答 | 不轮询（WebSocket） | — |
| 能耗报表 | 不轮询（静态历史数据） | — |
| 工单列表 | onShow | onHide |

**下拉刷新**（`onPullDownRefresh`）在所有列表页额外提供，立即调用一次数据接口，调用完毕后调用 `uni.stopPullDownRefresh()`。

---

## 5. ADR-004 鉴权与存储适配

### 5.1 Token 持久化

小程序无 `localStorage`/DOM，使用 **`uni.setStorageSync`** 替代。

```javascript
// utils/auth.js

const TOKEN_KEY = 'userToken'
const USER_INFO_KEY = 'userInfo'

export function saveAuth(token, userInfo) {
  uni.setStorageSync(TOKEN_KEY, token)
  uni.setStorageSync(USER_INFO_KEY, JSON.stringify(userInfo))
}

export function getToken() {
  return uni.getStorageSync(TOKEN_KEY) || null
}

export function getUserInfo() {
  const raw = uni.getStorageSync(USER_INFO_KEY)
  try { return raw ? JSON.parse(raw) : null } catch { return null }
}

export function isAdmin() {
  const info = getUserInfo()
  return info?.role === 'admin'
}

export function clearAuth() {
  uni.removeStorageSync(TOKEN_KEY)
  uni.removeStorageSync(USER_INFO_KEY)
}
```

**管理员判断**：严格使用 `userInfo.role === 'admin'`，绝不使用 `is_staff`（`/api/auth/me/` 不返回该字段）。

### 5.2 API 请求鉴权头

所有请求携带：

```
Authorization: Token {token}
Content-Type: application/json
```

**无 CSRF Token**：小程序无 Cookie，Token 认证请求已由 `SlidingWindowTokenAuthentication`（现有配置移除了 `SessionAuthentication`）处理，DRF TokenAuthentication 不强制 CSRF，无需 `X-CSRFToken` 头。

### 5.3 登录态校验流程

```
小程序启动
  │
  ├─ uni.getStorageSync('userToken') 非空？
  │     是 → 直接进入首页（乐观加载；首个 API 请求 401 时触发重登）
  │     否 → 跳转登录页
  │
登录页
  │ POST /api/auth/login/ { username, password }
  │
  ├─ 200 OK → saveAuth(token, user_info) → 跳转首页
  └─ 401 → 弹出错误提示
```

### 5.4 401 重登流程

API 客户端统一拦截，参见 module_design.md 中的 `http.js` 封装。

```
API 返回 401
  │
  ├─ clearAuth()
  ├─ 若当前不在登录页 → uni.reLaunch({ url: '/pages/login/index' })
  └─ 给用户提示："会话已过期，请重新登录"
```

### 5.5 Token 生命周期

现有后端使用 `SlidingWindowTokenAuthentication`，默认 30 分钟不活跃超时（`SESSION_INACTIVITY_TIMEOUT=1800`），7 天延长模式（`SESSION_EXTENDED_TIMEOUT=604800`）。小程序首期不修改 Token 策略，登录时传 `remember_me=true` 使用 7 天滑动窗口（与 Web 端行为一致，降低频繁重登）。

---

## 6. ADR-005 Markdown 渲染

### 决策

**选用 `towxml`**（版本 3.x），理由优先于 `mp-html`。

### 对比

| 维度 | towxml 3.x | mp-html |
|------|-----------|---------|
| 专为小程序设计 | 是（WXS + template） | 是 |
| Markdown 原生支持 | 是（内置 md 解析） | 需插件，默认处理 HTML |
| 流式追加适配 | 支持（重新传入完整 md 字符串重渲染） | 同样支持 |
| 小程序 eval 限制 | 无 eval，纯静态解析 | 同样无 eval |
| 包体积 | ~80KB（含 highlight.js 按需） | ~60KB |
| 中文 README/社区 | 活跃，issue 中文优先 | 活跃 |

### 使用策略

- **流式期间**：不渲染 Markdown，直接文本追加显示在 `<text>` 组件，避免高频 setData 引发性能问题。
- **`stream_end` 后**：将完整 `content` 字符串传入 `towxml` 组件渲染最终 Markdown。

```vue
<!-- pages/chat/components/ChatBubble.vue -->
<template>
  <view class="bubble">
    <!-- 流式期间：纯文本 -->
    <text v-if="streaming">{{ content }}</text>
    <!-- 结束后：towxml 渲染 -->
    <towxml v-else :nodes="parsedNodes" />
  </view>
</template>

<script setup>
import towxml from '@/utils/towxml/index'
const props = defineProps(['content', 'streaming'])
const parsedNodes = computed(() =>
  props.streaming ? null : towxml(props.content, 'markdown')
)
</script>
```

---

## 7. ADR-006 分包加载策略

### 决策

采用**分包加载（subpackages）**，主包 ≤ 1.5MB，单分包 ≤ 4MB，总包 ≤ 8MB。

### 分包划分

| 包 | 路径 | 包含页面 | 预估大小 | 触发时机 |
|----|------|---------|---------|---------|
| **主包** | `pages/` | 登录、首页、个人中心 | ~600KB（含 Pinia、uni-ui 基础、api client） | 启动即加载 |
| **分包 A：监控** | `subpackages/monitor/` | PLC 状态、设备卡片、参数历史图、房间历史图 | ~1.5MB（含 uCharts） | 点击监控入口 |
| **分包 B：AI 问答** | `subpackages/chat/` | 会话列表、聊天页 | ~1.2MB（含 towxml） | 点击 AI 问答入口 |
| **分包 C：能耗** | `subpackages/energy/` | 用量查询、日报、月报 | ~1MB（含 uCharts，复用分包 A 的 uCharts？见注） | 点击能耗入口 |
| **分包 D：运维** | `subpackages/ops/` | 故障管理、结露预警、工单（含审批）、巡检日志 | ~600KB | 点击运维入口 |

> **注**：uni-app 分包不能互相引用。uCharts 在分包 A 和分包 C 均需引入，可将 uCharts 放入**独立分包（预加载）**或**主包**。推荐放主包（uCharts 压缩后约 200KB，主包可容纳）。

### pages.json 结构（示意）

```json
{
  "pages": [
    { "path": "pages/login/index" },
    { "path": "pages/home/index" },
    { "path": "pages/profile/index" },
    { "path": "pages/profile/change-password" }
  ],
  "subPackages": [
    {
      "root": "subpackages/monitor",
      "pages": [
        { "path": "pages/plc-status" },
        { "path": "pages/device-cards" },
        { "path": "pages/device-history" },
        { "path": "pages/room-history" }
      ]
    },
    {
      "root": "subpackages/chat",
      "pages": [
        { "path": "pages/index" },
        { "path": "pages/session" }
      ]
    },
    {
      "root": "subpackages/energy",
      "pages": [
        { "path": "pages/query" },
        { "path": "pages/daily" },
        { "path": "pages/monthly" }
      ]
    },
    {
      "root": "subpackages/ops",
      "pages": [
        { "path": "pages/faults" },
        { "path": "pages/condensation" },
        { "path": "pages/work-orders" },
        { "path": "pages/worklog" }
      ]
    }
  ],
  "preloadRule": {
    "pages/home/index": {
      "network": "wifi",
      "packages": ["subpackages/monitor", "subpackages/ops"]
    }
  }
}
```

---

## 8. ADR-007 代码仓库位置与构建并存

### 决策

小程序代码放置于**项目根目录下的 `miniprogram/` 子目录**，与现有 `FreeArkWeb/` 并存，互不干扰。

### 目录结构

```
FreeArk/
├── FreeArkWeb/                    # 现有桌面 Web（保持不变）
│   ├── frontend/                  # Vue 3 桌面端
│   └── backend/                   # Django 后端
├── miniprogram/                   # 新增：uni-app 微信小程序
│   ├── pages/                     # 主包页面
│   ├── subpackages/               # 各分包
│   ├── utils/                     # 工具（api.js, auth.js, poller.js, chat-ws.js）
│   ├── components/                # 公共组件
│   ├── store/                     # Pinia stores
│   ├── static/                    # 静态资源
│   ├── App.vue
│   ├── main.js
│   ├── pages.json
│   ├── manifest.json
│   └── package.json               # 独立 npm 依赖，不与 FreeArkWeb/frontend 混用
└── docs/                          # 文档（本文档所在位置）
```

### 构建流程

```
开发调试：
  cd miniprogram && npx @dcloudio/uvm vite
  → 微信开发者工具导入 miniprogram/ 目录
  → 选择「不校验合法域名」（开发阶段）

正式发布：
  微信开发者工具 → 上传代码 → 微信公众平台审核
  → 审核通过后发布

与现有 Web 构建的隔离：
  FreeArkWeb/frontend 的 npm scripts 和 build 流程完全不变。
  miniprogram/ 有独立的 package.json 和 node_modules。
  git 仓库统一管理，.gitignore 在 miniprogram/ 目录下可单独追加。
```

---

## 9. 整体架构图（文字描述）

```
用户（微信小程序）
    │
    ├─ [HTTPS] REST API 请求
    │       Authorization: Token xxx
    │       → Nginx:443（SSL 终止）
    │       → Waitress:8000（HTTP）
    │       → Django DRF（SlidingWindowTokenAuthentication）
    │       → views/*.py（故障/能耗/设备/工单等）
    │       ← JSON 响应
    │
    └─ [WSS] WebSocket
            wss://domain/ws/chat/?token=xxx&session_key=yyy
            → Nginx:443（WSS 反代）
            → Daphne ASGI（WebSocket）
            → Channels ProtocolTypeRouter
            → ChatConsumer（connect/receive/disconnect）
            → LangGraphAdapter.stream_chat()
            → LangGraph 编排图（进程内，expert + aggregate）
            ← JSON frames（stream_token / stream_end 等）

Pinia Store（小程序内存）
    ├─ authStore（userToken, userInfo, role）
    ├─ deviceStore（PLC 状态，设备卡片缓存）
    ├─ chatStore（当前会话 key, messages, wsConnected）
    └─ uiStore（全局 loading 状态）
```

---

## 10. 安全合规要求

### 10.1 合法域名白名单（外部前置，开发无关）

小程序上线前必须在微信公众平台配置：
- `request` 合法域名：`https://freeark.example.com`（或用户实际备案域名）
- `socket` 合法域名：`wss://freeark.example.com`

开发阶段使用微信开发者工具「不校验合法域名」模式，直连内网 `http://192.168.31.51`。

### 10.2 HTTPS/WSS 强制

所有生产通信必须经 Nginx SSL 终止（443 端口），后端 HTTP/WebSocket 不直接对外暴露。

### 10.3 敏感操作二次确认

工单审批（批准/拒绝）在调用 API 前，使用 `uni.showModal` 弹出确认对话框，防止误触。

### 10.4 Token 安全存储

`uni.setStorageSync` 在微信小程序环境中数据存储于设备本地，不以明文传输，符合 NFR-MP-04 要求。密码字段仅在登录时一次性传输，不存储。

### 10.5 角色可见性

`userInfo.role === 'admin'` 仅控制 UI 元素可见性（审批按钮），实际鉴权由后端 `IsAdminUser` 视图权限类执行，前端可见性控制不替代后端鉴权。

---

## 11. 风险汇总

| 编号 | 风险 | 影响 | 缓解 |
|------|------|------|------|
| RISK-ARCH-01 | 合法域名/备案周期长（3+ 月），阻塞上线 | 高 | 开发阶段内网调试；备案同步推进 |
| RISK-ARCH-02 | towxml 在新版微信/iOS 的渲染 bug | 中 | 双端真机验证；备选 mp-html |
| RISK-ARCH-03 | 小程序后台 5 秒挂起断 WebSocket | 中 | onHide 主动 close，onShow 重连 |
| RISK-ARCH-04 | 分包总体积超限（>20MB） | 中 | uCharts 放主包；按需引入 towxml highlight |
| RISK-ARCH-05 | 树莓派并发增加，MySQL 负荷上升 | 中 | 30 秒轮询间隔；DB 监控 |
| RISK-ARCH-06 | 单人维护两个前端代码库 | 中 | API 客户端尽量复用逻辑；小程序只读操作少 |
| RISK-ARCH-07 | 微信审核拒绝（首次必经） | 中 | 提前准备隐私协议、用途说明 |
