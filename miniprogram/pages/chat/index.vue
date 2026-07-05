<!--
  @module MOD-PAGE-CHAT-INDEX
  @description AI 问答（方案1 · 对话气泡，赛博朋克 HUD）——「对话优先」。
    Claude Design handoff「AI问答 方案1」1:1 还原。custom 导航 + 自绘 4-Tab 底栏。
    进入即对话界面（复用既有 WS 链路 utils/chat-ws.js → 进程内 LangGraph → DeepSeek，零后端改动）：
      顶部子栏『＋新建会话 / 历史会话▾』；空会话显示问候 + 快捷提问 chips。
    WS 协议严格复刻：token 走 query、connected 帧才算连上、stream_token 流式、
      confirm_required 写确认门、onHide 必须 close()。历史会话下拉复用 api.getSessionList/getSessionHistory。
    本页是原生 tabBar 页：onShow 调 uni.hideTabBar() 隐藏原生底栏，避免与自绘 4-Tab 重叠（首页 onShow 复原）。
    图标为 SVG data-URI 背景（微信小程序不渲染 inline SVG）；字体不远程加载（规避 OTS 崩溃）。
-->
<template>
  <view class="ai-page">
    <!-- 背景装饰 -->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="bg-blob" />

    <!-- 状态栏占位 -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- header -->
    <view class="header">
      <view v-if="canGoBack" class="back-btn ico-back" @tap="goBack" />
      <text class="header-title">副官</text>
    </view>

    <!-- subbar -->
    <view class="subbar">
      <view class="new-pill" @tap="newSession"><text>＋ 新建会话</text></view>
      <view class="history-entry" @tap="toggleHistory">
        <text>历史会话</text><text class="caret-dn">▾</text>
      </view>
    </view>

    <!-- 断连横幅 -->
    <view v-if="!wsConnected && !connecting" class="disc-banner">
      <text>连接已断开，</text><text class="relink" @tap="reconnect">点击重连</text>
    </view>

    <!-- v1.12.0: 座舱未绑定提醒 -->
    <view v-if="wsConnected && !chatStore.cabinStatus.is_bound" class="cabin-banner" @tap="goToBind">
      <text>⚠️ 您尚未绑定座舱（房间），副官无法获取您的房间信息。</text>
      <text class="cabin-link">点击绑定 →</text>
    </view>

    <!-- chat feed: scroll-into-view anchor ensures reliable auto-scroll on new messages -->
    <scroll-view class="feed" scroll-y :scroll-top="scrollTopDyn" :scroll-into-view="bottomAnchor" :scroll-with-animation="true">
      <!-- 问候 + 快捷提问（空会话）-->
      <block v-if="messages.length === 0">
        <view class="row row-ai">
          <view class="avatar-ark"><text>ARK</text></view>
          <view class="bubble bubble-ai">
            <text class="btext">{{ personaGreeting }}</text>
          </view>
        </view>
        <view class="chips">
          <view v-for="(c, i) in quickChips" :key="i" class="chip" @tap="sendText(c)"><text>{{ c }}</text></view>
        </view>
      </block>

      <!-- 消息 -->
      <view
        v-for="(m, i) in messages"
        :key="i"
        class="row"
        :class="m.role === 'user' ? 'row-user' : 'row-ai'"
      >
        <view v-if="m.role !== 'user'" class="avatar-ark"><text>ARK</text></view>
        <ChatBubble
          :role="m.role"
          :content="m.content"
          :streaming="m.streaming"
          :reasoning="m.reasoning || ''"
          :statusText="m.statusText || ''"
          :confirmActions="m.confirmActions || null"
          theme="cyberpunk"
          @confirm="handleConfirm"
        />
      </view>
      <view :id="bottomAnchor" style="height:2rpx" />
    </scroll-view>

    <!-- input bar (v1.13.0: ChatInputBar 豆包风格四按钮) -->
    <ChatInputBar
      :wsConnected="wsConnected"
      :isStreaming="isStreaming"
      theme="dark"
      @send="onSend"
      @error="onInputError"
    />

    <!-- 底栏 -->
    <ArkTabBar active="chat" />

    <!-- 历史会话下拉 -->
    <view v-if="showHistory" class="hist-mask" @tap="toggleHistory" />
    <view v-if="showHistory" class="hist-panel">
      <view class="hist-title"><text>历史会话</text></view>
      <scroll-view scroll-y class="hist-list">
        <view v-if="histLoading" class="hist-empty"><text>加载中…</text></view>
        <view v-else-if="histSessions.length === 0" class="hist-empty"><text>暂无历史会话</text></view>
        <view
          v-for="(s, i) in histSessions"
          :key="i"
          class="hist-item"
          @tap="openHistory(s)"
        >
          <text class="hist-summary">{{ s.title || s.summary || (s.session_key_full || s.session_key || '会话') }}</text>
          <text class="hist-time">{{ formatTime(s.last_message_time || s.updated_at || s.ended_at || s.started_at) }}</text>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useChatStore } from '@/store/chat'
import { useOwnerStore } from '@/store/owner'
import { ChatWebSocket } from '@/utils/chat-ws'
import { api } from '@/utils/api'
import ArkTabBar from '@/components/ArkTabBar.vue'
import ChatBubble from '@/components/ChatBubble.vue'
import ChatInputBar from '@/components/ChatInputBar.vue'

const authStore = useAuthStore()
const chatStore = useChatStore()
const ownerStore = useOwnerStore()

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

const scrollTopDyn = ref(0)
const bottomAnchor = ref('anchor-a')
const connecting = ref(false)
const sessionKeyParam = ref(null)
const shouldLoadHistoryOnConnect = ref(false)
const canGoBack = ref(false)

// 历史会话下拉
const showHistory = ref(false)
const histSessions = ref([])
const histLoading = ref(false)

const quickChips = ['客厅主机不制冷？', '如何开启离家节能', '新风滤网多久换']

const messages = computed(() => chatStore.messages)
const wsConnected = computed(() => chatStore.wsConnected)
const isStreaming = computed(() => {
  const last = messages.value[messages.value.length - 1]
  return !!(last?.streaming)
})

// v1.12.0: 人格感知问候语
const personaGreeting = computed(() => {
  const p = chatStore.persona
  const greeting = p?.greeting_style || '智能方舟的副官'
  const tone = p?.tone_style || '尊敬的舰长大人'
  return `${tone}，我是${greeting}。可以帮您控制设备、排查故障，也能解答空调与新风知识。`
})

let chatWs = null

function initWs() {
  chatWs = new ChatWebSocket({
    onConnected(sessionKey, sessionId, persona, cabinStatus) {
      chatStore.setConnected(true, sessionKey, sessionId, persona, cabinStatus)
      sessionKeyParam.value = sessionKey || sessionKeyParam.value
      connecting.value = false
      // 仅在「恢复既有会话」时取历史；新会话 connect 阶段尚无 DB 行，取历史必 404。
      if (shouldLoadHistoryOnConnect.value) loadHistory(sessionKey)
      shouldLoadHistoryOnConnect.value = false
    },
    onStatusUpdate(msg) { chatStore.setStatusText(msg) },
    onReasoningToken(token) { chatStore.appendReasoningToken(token) },
    onReasoningEnd() {},
    onToken(token) { chatStore.appendToken(token); scrollToBottom() },
    onStreamEnd() { chatStore.setStreamEnd(); scrollToBottom() },
    onConfirmRequired(actions) {
      const last = messages.value[messages.value.length - 1]
      if (last) last.confirmActions = actions
    },
    onError(err) {
      connecting.value = false
      uni.showToast({ title: err.message || '发生错误', icon: 'none' })
    },
    onClose(code) {
      connecting.value = false
      chatStore.setConnected(false, null, null)
      if (code === 4001) {
        uni.showToast({ title: '鉴权失败，请重新登录', icon: 'none' })
        authStore.logout()
        uni.reLaunch({ url: '/pages/login/index' })
      }
    },
  })
}

function connectWs() {
  if (!authStore.token) return
  connecting.value = true
  const activeSp = ownerStore.activeSpecificPart || ''
  chatWs.connect(authStore.token, sessionKeyParam.value, activeSp)
}

function reconnect() { connectWs() }

async function loadHistory(sessionKey) {
  if (!sessionKey || messages.value.length > 0) return
  try {
    const res = await api.getSessionHistory(sessionKey)
    const msgs = res?.messages || []
    msgs.forEach((m) => {
      chatStore.addMessage({
        role: m.role, content: m.content,
        streaming: false,
        reasoning: m.reasoning || m.thinking || m.reasoning_content || '',
        statusText: '', confirmActions: null,
      })
    })
    scrollToBottom()
  } catch { /* 历史加载失败非致命 */ }
}

// 发送
function onSend({ text, media }) {
  const hasText = text && text.trim().length > 0
  const hasMedia = media && media.length > 0
  if (!hasText && !hasMedia) return
  if (!wsConnected.value || isStreaming.value) return

  const parts = []
  if (hasMedia) {
    const imageCount = media.filter(m => m.type === 'image').length
    parts.push(imageCount > 0 ? ('[图片' + (imageCount > 1 ? ' x' + imageCount : '') + ']') : '[媒体消息]')
  }
  if (hasText) parts.push(text.trim())
  const userLabel = parts.join(' ')

  chatStore.addMessage({ role: 'user', content: userLabel, streaming: false, reasoning: '', statusText: '', confirmActions: null })
  chatStore.addMessage({ role: 'assistant', content: '', streaming: true, reasoning: '', statusText: '', confirmActions: null })

  if (hasMedia) {
    const uploadIds = media.map(m => m.url)
    chatWs.sendWithImages(text ? text.trim() : '', uploadIds)
  } else {
    chatWs.send(text.trim())
  }
  scrollToBottom()
}

function onInputError(error) {
  uni.showToast({ title: error.message || '操作失败', icon: 'none', duration: 2000 })
}

function handleConfirm(approved) {
  chatWs.sendConfirm(approved)
  const last = messages.value[messages.value.length - 1]
  if (last) last.confirmActions = null
}

// 新建会话：清空并以新 key 重连
function newSession() {
  showHistory.value = false
  connecting.value = true
  shouldLoadHistoryOnConnect.value = false
  sessionKeyParam.value = null
  chatStore.resetSession()
  if (chatWs) chatWs.close()
  connectWs()
}

// 历史会话下拉
function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) loadHistList()
}
async function loadHistList() {
  histLoading.value = true
  try {
    const res = await api.getSessionList({ page: 1, page_size: 20 })
    histSessions.value = normalizeSessionList(res)
  } catch {
    histSessions.value = []
  } finally {
    histLoading.value = false
  }
}
function openHistory(s) {
  const key = s.session_key_full || s.session_key || s.key
  showHistory.value = false
  if (!key) return
  sessionKeyParam.value = key
  shouldLoadHistoryOnConnect.value = true
  connecting.value = true
  chatStore.resetSession()
  chatStore.sessionKey = key
  if (chatWs) chatWs.close()
  connectWs()
}

function normalizeSessionList(res) {
  const list = res?.sessions || res?.results || res?.data || []
  return Array.isArray(list) ? list : []
}

function scrollToBottom() {
  nextTick(() => {
    // Toggle between two anchors so scroll-into-view always triggers, even
    // if the previous target was the same value (fixes auto-scroll stalling).
    bottomAnchor.value = bottomAnchor.value === 'anchor-a' ? 'anchor-b' : 'anchor-a'
    scrollTopDyn.value = Date.now()
  })
}

function goBack() { uni.navigateBack() }

function goToBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

onLoad((options) => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  canGoBack.value = getCurrentPages().length > 1
  sessionKeyParam.value = options?.session_key || null
  shouldLoadHistoryOnConnect.value = !!sessionKeyParam.value
  chatStore.resetSession()
  if (sessionKeyParam.value) chatStore.sessionKey = sessionKeyParam.value
  initWs()
  connectWs()
  // Preload history list in background so it's ready when the user opens the panel
  loadHistList()
})

onShow(() => {
  // 隐藏原生 tabBar，避免与自绘 4-Tab 底栏重叠
  uni.hideTabBar({ animation: false, fail: () => {} })
  if (chatWs && !wsConnected.value && !connecting.value) connectWs()
})

onHide(() => {
  if (chatWs) chatWs.close()
  chatStore.setConnected(false, null, null)
})

onUnload(() => {
  if (chatWs) chatWs.close()
})
</script>

<style scoped>
.ai-page { position: relative; height: 100vh; display: flex; flex-direction: column; background: #05070f; overflow: hidden; }

/* 背景 */
.bg-base, .bg-grid, .bg-blob { position: absolute; pointer-events: none; }
.bg-base {
  inset: 0;
  background:
    radial-gradient(90% 50% at 15% 0%, rgba(101,55,180,0.30), transparent 55%),
    radial-gradient(80% 45% at 100% 5%, rgba(20,180,170,0.22), transparent 55%),
    linear-gradient(180deg, #0b0a1a, #07101c 60%, #050811);
}
.bg-grid {
  inset: 0;
  background-image:
    linear-gradient(rgba(56,230,224,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,230,224,0.06) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 60%);
  mask-image: linear-gradient(180deg, #000, transparent 60%);
}
.bg-blob {
  width: 360rpx; height: 360rpx; right: -100rpx; top: 400rpx; border-radius: 50%;
  background: radial-gradient(circle, rgba(47,244,224,0.18), transparent 70%);
  filter: blur(6px); animation: ark-float 16s ease-in-out infinite;
}
@keyframes ark-float { 0%,100% { transform: translate(0,0); } 50% { transform: translate(20rpx,-24rpx); } }

.status-spacer { position: relative; z-index: 5; flex: 0 0 auto; }

/* header */
.header { position: relative; z-index: 5; flex: 0 0 auto; height: 92rpx; display: flex; align-items: center; justify-content: center; }
.back-btn { position: absolute; left: 24rpx; width: 44rpx; height: 44rpx; background-repeat: no-repeat; background-position: center; background-size: 44rpx 44rpx; }
.header-title { font-size: 34rpx; font-weight: 700; letter-spacing: 4rpx; color: #eaf6ff; text-shadow: 0 0 12px rgba(56,230,224,0.5); }

/* subbar */
.subbar { position: relative; z-index: 5; flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; padding: 4rpx 32rpx 16rpx; }
/* subbar pills: unified height / border / bg / text */
.subbar pill,
.new-pill,
.history-entry {
  display: flex; align-items: center; gap: 8rpx;
  height: 56rpx; line-height: 56rpx;
  border: 1px solid rgba(56,230,224,0.4);
  border-radius: 28rpx; padding: 0 22rpx;
  background: rgba(47,244,224,0.06);
  transition: background 0.15s;
}
.new-pill text,
.history-entry text { font-size: 24rpx; color: #2ff4e0; }
.new-pill:active,
.history-entry:active { background: rgba(47,244,224,0.14); }
.caret-dn { font-size: 22rpx; color: #2ff4e0; margin-left: -2rpx; }

/* 断连横幅 */
.disc-banner { position: relative; z-index: 5; flex: 0 0 auto; text-align: center; padding: 12rpx; background: rgba(255,212,0,0.1); }
.disc-banner text { font-size: 24rpx; color: #ffe066; }
.relink { color: #7df9ff; text-decoration: underline; }

/* v1.12.0: 座舱未绑定提醒横幅 */
.cabin-banner { position: relative; z-index: 5; flex: 0 0 auto; text-align: center; padding: 12rpx 24rpx; background: rgba(0,180,255,0.12); display: flex; justify-content: center; align-items: center; gap: 12rpx; }
.cabin-banner text { font-size: 24rpx; color: rgba(143,217,255,0.8); }
.cabin-link { color: #7df9ff !important; text-decoration: underline; }

/* feed：mp-weixin scroll-view 在 flex 列内必须 flex-basis:0 + min-height:0 才能真正滚动；
   之前 `flex: 1 1 auto` 会让 scroll-view 高度被内容撑破，超出屏幕外的消息就看不到（用户 bug#4）。 */
.feed { position: relative; z-index: 4; flex: 1 1 0; min-height: 0; padding: 12rpx 28rpx 16rpx; }
.row { display: flex; margin-bottom: 26rpx; }
.row-user { justify-content: flex-end; }
.row-ai { justify-content: flex-start; align-items: flex-start; }

.avatar-ark {
  flex: 0 0 auto; width: 68rpx; height: 68rpx; border-radius: 18rpx; margin-right: 20rpx;
  background: linear-gradient(150deg, rgba(47,244,224,0.18), rgba(139,92,246,0.18));
  border: 1px solid rgba(56,230,224,0.45);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 12px rgba(47,244,224,0.25);
}
.avatar-ark text { font-size: 22rpx; font-weight: 900; letter-spacing: 1rpx; color: #aef9f2; }

.bubble { max-width: 78%; padding: 22rpx 26rpx; }
.bubble-ai { background: rgba(14,22,42,0.85); border: 1px solid rgba(56,230,224,0.2); border-radius: 10rpx 28rpx 28rpx 28rpx; }
.btext { font-size: 27rpx; line-height: 1.65; color: #dbeeff; word-break: break-all; }

/* quick chips */
.chips { display: flex; flex-wrap: wrap; gap: 16rpx; padding-left: 88rpx; margin-bottom: 26rpx; }
.chip { border: 1px solid rgba(56,230,224,0.35); border-radius: 28rpx; padding: 12rpx 22rpx; background: rgba(47,244,224,0.05); }
.chip text { font-size: 24rpx; color: #9fe9e0; }

/* v1.13.0: input bar replaced by ChatInputBar component (theme="dark") */

/* 历史下拉 */
.hist-mask { position: fixed; inset: 0; z-index: 20; background: rgba(0,0,0,0.4); }
.hist-panel {
  position: fixed; z-index: 21; left: 32rpx; right: 32rpx;
  top: 220rpx; max-height: 60vh; border-radius: 24rpx; overflow: hidden;
  background: rgba(10,18,36,0.98); border: 1px solid rgba(56,230,224,0.3);
  box-shadow: 0 12px 40px rgba(0,0,0,0.6);
}
.hist-title { padding: 24rpx 28rpx; border-bottom: 1px solid rgba(56,230,224,0.14); }
.hist-title text { font-size: 26rpx; font-weight: 700; color: #7df9ff; letter-spacing: 2rpx; }
.hist-list { max-height: calc(60vh - 80rpx); }
.hist-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 24rpx 28rpx; border-bottom: 1px solid rgba(56,230,224,0.08);
  transition: background 0.12s;
}
.hist-item:active { background: rgba(47,244,224,0.08); }
.hist-summary {
  flex: 1; min-width: 0; font-size: 26rpx; color: #dbeeff;
  margin-right: 16rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.hist-time {
  flex: 0 0 auto; font-size: 22rpx; color: rgba(143,217,255,0.45);
  font-variant-numeric: tabular-nums;
}
.hist-empty { padding: 48rpx; text-align: center; }
.hist-empty text { font-size: 24rpx; color: rgba(143,217,255,0.5); }

/* 图标（SVG data-URI）*/
.ico-back { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23eaf6ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 5l-7 7 7 7'/%3E%3C/svg%3E"); }
</style>
