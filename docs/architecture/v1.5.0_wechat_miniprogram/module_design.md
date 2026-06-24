# 模块与页面设计 — v1.5.0 微信小程序移动端

**文档编号**: ARCH-MP-v150-002
**项目名称**: FreeArk 微信小程序移动端（v1.5.0_wechat_miniprogram）
**版本**: 1.0.0
**状态**: DRAFT — 待用户确认
**创建日期**: 2026-06-23
**作者**: system-architect (via pm-orchestrator)
**输入文档**: ARCH-MP-v150-001, REQ-SPEC-MP-v150-001

---

## 目录

1. 页面清单与路由
2. 分包方案（已定稿）
3. 公共组件清单
4. API 客户端封装
5. 状态管理（Pinia）
6. 实时数据策略（轮询 + WebSocket）
7. 鉴权流程与路由守卫
8. 功能与后端接口映射表（FR-MP-01~14 逐一）
9. 图表组件封装（uCharts）
10. Markdown 渲染组件
11. 角色可见性控制

---

## 1. 页面清单与路由

### 主包页面（pages/）

| 页面路径 | 对应需求 | 角色 | 说明 |
|---------|---------|------|------|
| `pages/login/index` | FR-MP-01 | 全部 | 账号密码登录页，未登录强制跳转至此 |
| `pages/home/index` | FR-MP-02 | 全部 | 首页综合看板，4 个指标卡 + 快捷入口 |
| `pages/profile/index` | — | 全部 | 个人中心（显示用户名、角色、登出入口、改密入口） |
| `pages/profile/change-password` | FR-MP-14 | 全部 | 修改密码 |

### 分包 A — 监控（subpackages/monitor/pages/）

| 页面路径 | 对应需求 | 角色 | 说明 |
|---------|---------|------|------|
| `plc-status` | FR-MP-03 | 全部 | PLC 在线状态列表，支持下拉刷新 |
| `device-cards` | FR-MP-04 | 全部 | 设备卡片列表，按房间筛选 |
| `device-history` | FR-MP-05 | 全部 | 设备参数历史折线图，时间范围 Tab |
| `room-history` | FR-MP-06 | 全部 | 房间历史趋势图（温湿氧三线） |

### 分包 B — AI 问答（subpackages/chat/pages/）

| 页面路径 | 对应需求 | 角色 | 说明 |
|---------|---------|------|------|
| `index` | FR-MP-11 | 全部 | 会话历史列表 + 新建会话入口 + 专家选择 |
| `session` | FR-MP-11 | 全部 | 聊天页（WebSocket 流式，towxml 渲染） |

### 分包 C — 能耗（subpackages/energy/pages/）

| 页面路径 | 对应需求 | 角色 | 说明 |
|---------|---------|------|------|
| `query` | FR-MP-09 | 全部 | 能耗用量查询（时间范围选择 + 数据表格） |
| `daily` | FR-MP-10 | 全部 | 能耗日报（选日期 + 明细表格） |
| `monthly` | FR-MP-10 | 全部 | 能耗月报（选年月 + 柱状图 + 汇总表格） |

### 分包 D — 运维（subpackages/ops/pages/）

| 页面路径 | 对应需求 | 角色 | 说明 |
|---------|---------|------|------|
| `faults` | FR-MP-07 | 全部 | 故障列表（状态/房间筛选，下拉加载更多） |
| `condensation` | FR-MP-08 | 全部 | 结露预警列表（下拉刷新） |
| `work-orders` | FR-MP-12/13 | 全部/管理员 | 工单列表，管理员可见审批按钮 |
| `worklog` | FR-MP-（扩展） | 全部 | 巡检工作日志列表 + 详情（已纳入首期，OQ-06 已确认） |

### TabBar（底部导航）

| Tab | 图标含义 | 跳转页面 |
|-----|---------|---------|
| 首页 | home | `pages/home/index` |
| 监控 | monitor | `subpackages/monitor/pages/plc-status` |
| 运维 | tool | `subpackages/ops/pages/faults` |
| 问答 | chat | `subpackages/chat/pages/index` |
| 我的 | person | `pages/profile/index` |

---

## 2. 分包方案

详见 architecture_design.md ADR-006。要点：

- **uCharts** 放入主包（压缩后约 200KB），分包 A 和分包 C 均可直接使用，避免重复打包。
- **towxml** 放入分包 B（仅 AI 问答页使用），避免污染主包体积。
- **Pinia** 放主包（`store/` 目录），所有分包均可按需引用 store。
- `preloadRule`：首页加载完成后，在 WiFi 条件下预加载分包 A 和分包 D。

---

## 3. 公共组件清单

| 组件名 | 路径 | 说明 |
|-------|------|------|
| `LoadingBar` | `components/LoadingBar.vue` | 全局顶部加载进度条 |
| `EmptyState` | `components/EmptyState.vue` | 空状态占位（图标 + 文案） |
| `ErrorBanner` | `components/ErrorBanner.vue` | 错误提示横幅（可关闭） |
| `StatusTag` | `components/StatusTag.vue` | 在线/离线/异常状态彩色标签 |
| `MetricCard` | `components/MetricCard.vue` | 指标卡片（数字 + 标题 + 可选告警色） |
| `ChartLine` | `components/ChartLine.vue` | uCharts 折线图封装（接受 data/labels/title） |
| `ChartBar` | `components/ChartBar.vue` | uCharts 柱状图封装 |
| `ChatBubble` | `components/ChatBubble.vue` | 聊天气泡（含 towxml Markdown 渲染） |
| `PagePoller` | `utils/poller.js` | 轮询工具类（非组件，JS 模块） |
| `ConfirmModal` | 调用 `uni.showModal` 封装 | 二次确认弹窗（工单审批） |

---

## 4. API 客户端封装

统一封装于 `miniprogram/utils/http.js`，所有页面/store 通过此模块发请求，禁止裸调 `uni.request`。

### 4.1 设计目标

- 统一 baseURL（从 `manifest.json` 或环境配置读取，区分开发/生产）。
- 统一注入 `Authorization: Token {token}` 请求头。
- 统一 401 拦截 → 清除本地 Token → `uni.reLaunch` 到登录页。
- 统一错误处理（网络错误、超时、服务端错误）。
- 不依赖 Cookie（小程序环境不适合 CSRF cookie 模式）。

### 4.2 封装结构

```javascript
// miniprogram/utils/http.js

import { getToken, clearAuth } from './auth'

const BASE_URL = '__FREEARK_API_BASE__'  // 通过 manifest.json 的 networkTimeout 或
                                          // 全局 app.js globalData 注入

let _sessionExpiredShown = false

async function request(method, path, data, extraHeaders = {}) {
  const token = getToken()
  if (!token) {
    redirectToLogin()
    return Promise.reject(new Error('NOT_LOGGED_IN'))
  }

  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}${path}`,
      method,
      data,
      header: {
        'Authorization': `Token ${token}`,
        'Content-Type': 'application/json',
        ...extraHeaders,
      },
      timeout: 15000,
      success(res) {
        if (res.statusCode === 200 || res.statusCode === 201) {
          resolve(res.data)
        } else if (res.statusCode === 401) {
          handleUnauthorized()
          reject(new Error('SESSION_EXPIRED'))
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(res.data)}`))
        }
      },
      fail(err) {
        reject(new Error(`网络错误: ${err.errMsg}`))
      }
    })
  })
}

function handleUnauthorized() {
  clearAuth()
  if (!_sessionExpiredShown) {
    _sessionExpiredShown = true
    uni.showToast({ title: '会话已过期，请重新登录', icon: 'none', duration: 2000 })
    setTimeout(() => {
      _sessionExpiredShown = false
      uni.reLaunch({ url: '/pages/login/index' })
    }, 2000)
  }
}

function redirectToLogin() {
  uni.reLaunch({ url: '/pages/login/index' })
}

const http = {
  get: (path, params) => request('GET', path + buildQuery(params)),
  post: (path, data) => request('POST', path, data),
  put: (path, data) => request('PUT', path, data),
  patch: (path, data) => request('PATCH', path, data),
  del: (path) => request('DELETE', path),
}

function buildQuery(params) {
  if (!params || Object.keys(params).length === 0) return ''
  return '?' + Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
}

export default http
```

### 4.3 API 方法封装（api.js）

```javascript
// miniprogram/utils/api.js
import http from './http'

export default {
  // 鉴权
  login: (data) => http.post('/api/auth/login/', data),
  logout: () => http.post('/api/auth/logout/', {}),
  getCurrentUser: () => http.get('/api/auth/me/'),
  changePassword: (data) => http.post('/api/change-password/', data),

  // 首页看板
  getDashboardSummary: () => http.get('/api/dashboard/summary/'),
  getDashboardTotalEnergy: () => http.get('/api/dashboard/total-energy/'),
  getDashboardFaultSummary: () => http.get('/api/dashboard/fault-summary/'),
  getDashboardPlcOnlineRate: () => http.get('/api/dashboard/plc-online-rate/'),

  // PLC 状态
  getPlcConnectionStatus: () => http.get('/api/plc/connection-status/'),

  // 设备卡片
  getDeviceRealtimeParams: (params) => http.get('/api/devices/realtime-params/', params),

  // 设备参数历史
  getDeviceParamHistory: (params) => http.get('/api/devices/param-history/', params),

  // 故障管理
  getFaultEvents: (params) => http.get('/api/devices/fault-events/', params),
  getFaultEventCategories: () => http.get('/api/devices/fault-event-categories/'),

  // 结露预警
  getCondensationWarnings: (params) => http.get('/api/devices/condensation-warning-events/', params),

  // 能耗
  getUsageQuantity: (params) => http.get('/api/usage/quantity/', params),
  getUsageQuantitySpecificPeriod: (params) => http.get('/api/usage/quantity/specifictimeperiod/', params),
  getUsageQuantityMonthly: (params) => http.get('/api/usage/quantity/monthly/', params),

  // AI 问答（REST 部分）
  getSessionList: (params) => http.get('/api/memory/me/', params),
  getSessionHistory: (sessionKey) => http.get(`/api/memory/session/${sessionKey}/history/`),
  deleteSession: (sessionKey) => http.del(`/api/memory/session/${sessionKey}/`),

  // 巡检工单
  getWorkOrders: (params) => http.get('/api/workorders/', params),
  getWorkOrderDetail: (id) => http.get(`/api/workorders/${id}/`),
  approveWorkOrder: (id, data) => http.post(`/api/workorders/${id}/approve-write/`, data),
  resolveWorkOrder: (id, data) => http.post(`/api/workorders/${id}/resolve/`, data),

  // 巡检日志
  getInspectionLogs: (params) => http.get('/api/inspection/logs/', params),
}
```

---

## 5. 状态管理（Pinia）

### 5.1 authStore

```javascript
// store/auth.js
import { defineStore } from 'pinia'
import { saveAuth, getToken, getUserInfo, clearAuth, isAdmin } from '@/utils/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken(),
    userInfo: getUserInfo(),
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    isAdmin: (state) => state.userInfo?.role === 'admin',
    username: (state) => state.userInfo?.username || '',
  },
  actions: {
    login(token, userInfo) {
      this.token = token
      this.userInfo = userInfo
      saveAuth(token, userInfo)
    },
    logout() {
      this.token = null
      this.userInfo = null
      clearAuth()
    },
  },
})
```

### 5.2 chatStore

```javascript
// store/chat.js
import { defineStore } from 'pinia'

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessionKey: null,        // 当前会话 key（UUID）
    messages: [],            // 消息数组 {role, content, streaming, reasoning, confirm}
    wsConnected: false,
    expertType: 'freeark',   // 'freeark' | 'sanheng'
    sessionList: [],         // 会话历史列表
  }),
  actions: {
    addMessage(msg) { this.messages.push(msg) },
    appendToken(token) {
      const last = this.messages[this.messages.length - 1]
      if (last?.streaming) last.content += token
    },
    setStreamEnd() {
      const last = this.messages[this.messages.length - 1]
      if (last) last.streaming = false
    },
    setConnected(val, sessionKey) {
      this.wsConnected = val
      if (sessionKey) this.sessionKey = sessionKey
    },
    resetSession() {
      this.messages = []
      this.wsConnected = false
    },
  },
})
```

### 5.3 其他 Store

- `uiStore`：全局 loading flag，toast 队列。
- `deviceStore`（可选）：缓存 PLC 状态列表 + 上次更新时间，避免页面切换时闪烁。

---

## 6. 实时数据策略

详见 architecture_design.md ADR-003。

### 6.1 轮询页面（30 秒）

各页面 `onShow` 启动轮询，`onHide` 停止；页面额外提供下拉刷新（`onPullDownRefresh`）。

示例：

```javascript
// subpackages/ops/pages/faults.vue
import { PagePoller } from '@/utils/poller'
const poller = new PagePoller(fetchFaults, 30000)

onShow(() => poller.start())
onHide(() => poller.stop())
onPullDownRefresh(() => {
  fetchFaults().finally(() => uni.stopPullDownRefresh())
})
```

### 6.2 AI 问答 WebSocket 生命周期

```
页面 onLoad → chatWs.connect(token, sessionKey)
收到 connected → wsConnected = true → 允许发送
页面 onHide → chatWs.close()   // 防后台挂起
页面 onShow → if (!connected) chatWs.connect(...)
页面 onUnload → chatWs.close()
```

**断线提示与重连**：`socketTask.onClose` 时，若 `code !== 4001`（鉴权失败），展示「连接已断开，点击重连」提示条，不自动重连（避免后台反复消耗连接配额）。

---

## 7. 鉴权流程与路由守卫

uni-app 无 Vue Router 的 `beforeEach`，在每个需鉴权页面的 `onLoad` 开头执行检查：

```javascript
// utils/auth-guard.js
import { useAuthStore } from '@/store/auth'

export function requireAuth() {
  const auth = useAuthStore()
  if (!auth.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return false
  }
  return true
}

export function requireAdmin() {
  const auth = useAuthStore()
  if (!auth.isAdmin) {
    uni.showToast({ title: '无权限', icon: 'none' })
    uni.navigateBack()
    return false
  }
  return true
}
```

使用示例：

```javascript
// 任意需鉴权页面的 onLoad
onLoad(() => {
  if (!requireAuth()) return
  // 正常初始化...
})
```

工单审批按钮的管理员判断：

```vue
<button v-if="authStore.isAdmin" @tap="handleApprove">批准</button>
```

---

## 8. 功能与后端接口映射表

| 需求编号 | 功能 | HTTP 方法 | 后端端点 | 请求参数 | 备注 |
|---------|------|---------|---------|---------|------|
| FR-MP-01 | 登录 | POST | `/api/auth/login/` | `{username, password, remember_me}` | 返回 `{token, user_info:{role,...}}` |
| FR-MP-01 | 登出 | POST | `/api/auth/logout/` | — | Token 认证，后端销毁 Token |
| FR-MP-01 | 获取当前用户 | GET | `/api/auth/me/` | — | 返回 `{username, role, ...}`，不含 `is_staff` |
| FR-MP-02 | 首页综合看板 — PLC 在线率 | GET | `/api/dashboard/plc-online-rate/` | — | 含在线数/总数 |
| FR-MP-02 | 首页综合看板 — 故障数 | GET | `/api/dashboard/fault-summary/` | — | 返回活跃故障数 |
| FR-MP-02 | 首页综合看板 — 结露预警数 | GET | `/api/dashboard/summary/` 或 `/api/dashboard/fault-summary/` | — | 需确认哪个端点含结露预警数；见注1 |
| FR-MP-02 | 首页综合看板 — 今日能耗 | GET | `/api/dashboard/total-energy/` | — | 返回今日 kWh |
| FR-MP-03 | PLC 状态列表 | GET | `/api/plc/connection-status/` | — | 返回所有 PLC 状态列表 |
| FR-MP-04 | 设备卡片列表 | GET | `/api/devices/realtime-params/` | `?specific_part=...`（可选） | 实时参数卡片，支持筛选 |
| FR-MP-05 | 设备参数历史 | GET | `/api/devices/param-history/` | `specific_part, sub_type, start_time, end_time` | 返回历史数据点列表 |
| FR-MP-06 | 房间历史趋势 | GET | `/api/devices/param-history/` | 同上，按房间相关 specific_part 查询 | 复用同一端点 |
| FR-MP-07 | 故障列表 | GET | `/api/devices/fault-events/` | `page, page_size, status, room`（按 BA-07 确认分页支持） | 返回分页故障列表 |
| FR-MP-07 | 故障筛选（房间分类） | GET | `/api/devices/fault-event-categories/` | — | 获取房间/分类列表用于筛选 |
| FR-MP-08 | 结露预警列表 | GET | `/api/devices/condensation-warning-events/` | `page, page_size`（按 BA-07） | 结露预警列表 |
| FR-MP-09 | 能耗用量查询 | GET | `/api/usage/quantity/specifictimeperiod/` | `start_date, end_date, ...` | 特定时间段用量 |
| FR-MP-10 | 能耗日报 | GET | `/api/usage/quantity/` | `date`（按具体参数名确认） | 日度用量 |
| FR-MP-10 | 能耗月报 | GET | `/api/usage/quantity/monthly/` | `year, month` | 月度汇总 |
| FR-MP-11 | AI 问答 — 会话列表 | GET | `/api/memory/me/` | `page, page_size` | 返回该用户会话列表（最近 20 条） |
| FR-MP-11 | AI 问答 — 会话历史 | GET | `/api/memory/session/{session_key}/history/` | — | 返回 `{messages:[{role,content,created_at}]}` |
| FR-MP-11 | AI 问答 — 聊天（流式） | WebSocket | `wss://domain/ws/chat/?token=xxx[&session_key=yyy]` | — | 见 ADR-002 真实协议 |
| FR-MP-12 | 工单列表 | GET | `/api/workorders/` | `page, page_size, status`（按 BA-07） | 所有用户可见 |
| FR-MP-13 | 工单审批（批准） | POST | `/api/workorders/{id}/approve-write/` | `{action: "approve"}` 或后端规定格式 | 管理员专属 |
| FR-MP-13 | 工单审批（拒绝） | POST | `/api/workorders/{id}/approve-write/` | `{action: "reject", reason: "..."}` | 管理员专属 |
| FR-MP-14 | 修改密码 | POST | `/api/change-password/` | `{old_password, new_password}` | 所有用户 |
| US-14（扩展） | 巡检工作日志 | GET | `/api/inspection/logs/` | `page, page_size` | 只读浏览 |

> **注1**：首页结露预警数的来源端点需在开发前确认。候选：`/api/dashboard/summary/` 或 `devices/fault-summary/`。建议在后端确认后，若无专用字段，由后端在 `dashboard/summary/` 中新增 `condensation_warning_count` 字段（工作量：后端改动约 0.5h，属 BA-05 范畴）。

---

## 9. 图表组件封装（uCharts）

uCharts 放在主包，所有分包均可直接 import。

### 9.1 折线图组件（ChartLine）

```vue
<!-- components/ChartLine.vue -->
<template>
  <view class="chart-container">
    <canvas
      :canvas-id="canvasId"
      :id="canvasId"
      type="2d"
      class="chart-canvas"
      @touchstart="touchStart"
      @touchmove="touchMove"
      @touchend="touchEnd"
    />
  </view>
</template>

<script setup>
import { onMounted, watch } from 'vue'
import uCharts from '@/utils/u-charts/u-charts.js'

const props = defineProps({
  canvasId: { type: String, required: true },
  data: { type: Object, default: () => ({}) },  // {categories: [], series: [{name, data}]}
  title: { type: String, default: '' },
})

let chartInstance = null

function renderChart(data) {
  if (!data?.categories?.length) return
  chartInstance = new uCharts({
    type: 'line',
    canvasId: props.canvasId,
    categories: data.categories,
    series: data.series,
    width: uni.upx2px(750),
    height: uni.upx2px(400),
    legend: { show: true },
    extra: { line: { type: 'curve' } },
    // ... 其他配置
  })
}

onMounted(() => renderChart(props.data))
watch(() => props.data, renderChart, { deep: true })

// 触摸事件转发（uCharts tooltip 交互需要）
function touchStart(e) { chartInstance?.touchLegend(e); chartInstance?.showToolTip(e) }
function touchMove(e) { chartInstance?.showToolTip(e) }
function touchEnd(e) {}
</script>
```

### 9.2 柱状图组件（ChartBar）

与 ChartLine 结构相同，`type: 'column'`。

### 9.3 使用示例

```javascript
// subpackages/monitor/pages/device-history.vue
const chartData = computed(() => ({
  categories: historyData.value.map(d => d.time_label),
  series: [{ name: '温度', data: historyData.value.map(d => d.value) }],
}))
```

---

## 10. Markdown 渲染组件

详见 architecture_design.md ADR-005。

### 集成步骤

```bash
cd miniprogram
npm install towxml
```

### ChatBubble 组件

```vue
<!-- components/ChatBubble.vue -->
<template>
  <view class="bubble" :class="role === 'user' ? 'bubble--user' : 'bubble--assistant'">
    <!-- reasoning 折叠区（可选展示） -->
    <view v-if="reasoning" class="reasoning-box">
      <text class="reasoning-label">思考过程</text>
      <text class="reasoning-text">{{ reasoning }}</text>
    </view>

    <!-- 流式期间：纯文本追加 -->
    <text v-if="streaming" class="bubble-text">{{ content }}</text>
    <!-- 结束后：towxml Markdown 渲染 -->
    <towxml v-else-if="content" :nodes="markdownNodes" />

    <!-- 确认卡片（工单写操作审批，Tier-2 写门） -->
    <view v-if="confirm" class="confirm-card">
      <text class="confirm-title">待确认操作</text>
      <text v-for="(a, i) in confirm.actions" :key="i">{{ a.preview }}</text>
      <button @tap="$emit('confirm', true)">确认</button>
      <button @tap="$emit('confirm', false)">取消</button>
    </view>

    <!-- 流式光标 -->
    <text v-if="streaming && content" class="stream-cursor">|</text>
    <!-- 思考中占位 -->
    <text v-if="streaming && !content && !reasoning" class="thinking">
      {{ statusText || '正在思考...' }}
    </text>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import towxml from '@/utils/towxml/index'

const props = defineProps({
  role: String,
  content: { type: String, default: '' },
  streaming: { type: Boolean, default: false },
  reasoning: { type: String, default: '' },
  confirm: { type: Object, default: null },
  statusText: { type: String, default: '' },
})

const markdownNodes = computed(() =>
  props.streaming ? null : towxml(props.content || '', 'markdown')
)
</script>
```

---

## 11. 角色可见性控制

所有角色控制统一依据 `useAuthStore().isAdmin`（即 `userInfo.role === 'admin'`），不使用 `is_staff`。

### 11.1 工单审批按钮

```vue
<!-- subpackages/ops/pages/work-orders.vue -->
<template v-if="authStore.isAdmin">
  <button @tap="handleApprove(item)" class="btn-approve">批准</button>
  <button @tap="handleReject(item)" class="btn-reject">拒绝</button>
</template>
```

### 11.2 管理员专属入口（首页或个人中心）

首期管理员无额外独占页面（工单审批内嵌在工单列表中），后期若需独立管理入口，在 profile 页通过 `v-if="authStore.isAdmin"` 控制。

### 11.3 后端鉴权双重保障

即便前端隐藏了 UI，后端 `views_workorder.workorder_approve_write` 视图中的 `IsAdminUser` 权限类会再次验证角色，防止绕过。

```python
# views_workorder.py（现有代码，无需修改）
class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'admin'  # 使用 role 字段，不用 is_staff
```
