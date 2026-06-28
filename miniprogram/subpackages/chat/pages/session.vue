<!--
  @module MOD-PAGE-CHAT-SESSION
  @author sub_agent_software_developer
  @description Chat session page (US-11, slice 2). Most critical page.

  WS protocol (strictly replicated — no invention):
    URL: ws://{host}/ws/chat/?token={userToken}[&session_key={uuid}]
    Auth: token as query param (NOT header)
    Connected gate: wsConnected=true set ONLY on receiving {type:"connected"} frame, NOT onOpen.
    onHide → chatWs.close() (prevents backend hang-up from 5s keep-alive limit)
    onShow → reconnect if not connected
    Auth fail: server closes with code 4001 → logout + reLaunch login

  WS frame handling:
    connected       → setConnected(true), load history if session_key provided
    status_update   → setStatusText (shown in streaming placeholder bubble)
    reasoning_token → appendReasoningToken
    reasoning_end   → (reasoning phase done, keep visible)
    stream_token    → appendToken + scrollToBottom
    stream_end      → setStreamEnd + scrollToBottom
    confirm_required → attach actions to last message bubble
    error           → showToast
-->
<template>
  <view class="session-page">
    <!-- Disconnected banner with manual reconnect -->
    <view v-if="!wsConnected && !connecting" class="disconnected-banner">
      <text>连接已断开，</text>
      <text class="reconnect-link" @tap="reconnect">点击重连</text>
    </view>

    <!-- Message list -->
    <scroll-view
      class="message-list"
      scroll-y
      :scroll-top="scrollTop"
      :scroll-with-animation="true"
      scroll-into-view="msg-bottom"
    >
      <view id="msg-top" />
      <ChatBubble
        v-for="(msg, i) in messages"
        :key="i"
        :role="msg.role"
        :content="msg.content"
        :streaming="msg.streaming"
        :reasoning="msg.reasoning"
        :status-text="msg.statusText"
        :confirm-actions="msg.confirmActions"
        @confirm="handleConfirm"
      />
      <view id="msg-bottom" />
    </scroll-view>

    <!-- Input area -->
    <view class="input-area">
      <textarea
        class="msg-input"
        v-model="inputText"
        placeholder="输入消息…"
        :disabled="!wsConnected || isStreaming"
        auto-height
        :max-height="200"
        @confirm="sendMessage"
      />
      <button
        class="send-btn"
        :disabled="!wsConnected || isStreaming || !inputText.trim()"
        @tap="sendMessage"
      >
        发送
      </button>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useChatStore } from '@/store/chat'
import { ChatWebSocket } from '@/utils/chat-ws'
import { api } from '@/utils/api'
import ChatBubble from '@/components/ChatBubble.vue'

const authStore = useAuthStore()
const chatStore = useChatStore()

const inputText = ref('')
const scrollTop = ref(0)
const connecting = ref(false)
const sessionKeyParam = ref(null)

// Derived from store (reactive)
const messages = computed(() => chatStore.messages)
const wsConnected = computed(() => chatStore.wsConnected)
const isStreaming = computed(() => {
  const last = messages.value[messages.value.length - 1]
  return !!(last?.streaming)
})

let chatWs = null

function initWs() {
  chatWs = new ChatWebSocket({
    onConnected(sessionKey, sessionId) {
      // Only here — NOT in onOpen — do we mark the connection live
      chatStore.setConnected(true, sessionKey, sessionId)
      connecting.value = false
      // Load history only when resuming an existing session (opened with a session_key param).
      // A brand-new session gets a freshly-generated session_key from the backend that has no
      // DB row yet (ADR-001: connect 不落库，首条消息才建 session)，对它取历史必然 404。
      if (sessionKeyParam.value) {
        loadHistory(sessionKey)
      }
    },
    onStatusUpdate(msg) {
      chatStore.setStatusText(msg)
    },
    onReasoningToken(token) {
      chatStore.appendReasoningToken(token)
    },
    onReasoningEnd() {
      // Reasoning phase complete — reasoning text stays visible, no additional action needed
    },
    onToken(token) {
      chatStore.appendToken(token)
      scrollToBottom()
    },
    onStreamEnd() {
      chatStore.setStreamEnd()
      scrollToBottom()
    },
    onConfirmRequired(actions) {
      const last = messages.value[messages.value.length - 1]
      if (last) last.confirmActions = actions
    },
    onError(err) {
      // 连接异常也要复位 connecting，否则断连横幅(v-if=!wsConnected && !connecting)永不显示
      connecting.value = false
      uni.showToast({ title: err.message || '发生错误', icon: 'none' })
    },
    onClose(code) {
      // 复位 connecting，让"连接已断开，点击重连"横幅能正常出现
      connecting.value = false
      chatStore.setConnected(false, null, null)
      if (code === 4001) {
        // Auth failure — force re-login
        uni.showToast({ title: '鉴权失败，请重新登录', icon: 'none' })
        authStore.logout()
        uni.reLaunch({ url: '/pages/login/index' })
      }
      // Do NOT auto-reconnect — show banner, let user decide
    },
  })
}

function connectWs() {
  if (!authStore.token) return
  connecting.value = true
  chatWs.connect(authStore.token, sessionKeyParam.value)
}

function reconnect() {
  connectWs()
}

async function loadHistory(sessionKey) {
  // Only load if we have a key and no messages already loaded
  if (!sessionKey || messages.value.length > 0) return
  try {
    const res = await api.getSessionHistory(sessionKey)
    const msgs = res?.messages || []
    msgs.forEach(m => {
      chatStore.addMessage({
        role: m.role,
        content: m.content,
        streaming: false,
        reasoning: '',
        statusText: '',
        confirmActions: null,
      })
    })
    scrollToBottom()
  } catch {
    // History load failure is non-fatal — session continues without history
  }
}

function sendMessage() {
  const text = inputText.value.trim()
  if (!text || !wsConnected.value || isStreaming.value) return

  inputText.value = ''

  // Push user message immediately for instant feedback
  chatStore.addMessage({
    role: 'user',
    content: text,
    streaming: false,
    reasoning: '',
    statusText: '',
    confirmActions: null,
  })

  // Push streaming placeholder for AI response
  chatStore.addMessage({
    role: 'assistant',
    content: '',
    streaming: true,
    reasoning: '',
    statusText: '',
    confirmActions: null,
  })

  chatWs.send(text)
  scrollToBottom()
}

function handleConfirm(approved) {
  chatWs.sendConfirm(approved)
  // Dismiss confirm card after user responds
  const last = messages.value[messages.value.length - 1]
  if (last) last.confirmActions = null
}

function scrollToBottom() {
  nextTick(() => {
    scrollTop.value = 999999
  })
}

onLoad((options) => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }

  sessionKeyParam.value = options.session_key || null

  // 后端 LLM 自动路由专家，不向用户暴露；标题统一用助手品牌名
  uni.setNavigationBarTitle({ title: '方舟智能体' })

  // Reset store for this session
  chatStore.resetSession()
  if (sessionKeyParam.value) {
    chatStore.sessionKey = sessionKeyParam.value
  }

  initWs()
  connectWs()
})

onShow(() => {
  // Reconnect if coming back from background and WS is down
  if (chatWs && !wsConnected.value && !connecting.value) {
    connectWs()
  }
})

onHide(() => {
  // MUST close on hide to prevent backend 5s hang-up / dead connection accumulation
  if (chatWs) chatWs.close()
  chatStore.setConnected(false, null, null)
})

onUnload(() => {
  if (chatWs) chatWs.close()
})
</script>

<style scoped>
.session-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.disconnected-banner {
  background: #fff3cd;
  padding: 16rpx 24rpx;
  text-align: center;
  font-size: 26rpx;
  color: #856404;
  flex-shrink: 0;
}
.reconnect-link {
  color: #1a73e8;
  text-decoration: underline;
}
.message-list {
  flex: 1;
  padding: 16rpx 0;
}
.input-area {
  display: flex;
  align-items: flex-end;
  padding: 16rpx 24rpx;
  background: #fff;
  border-top: 1rpx solid #eee;
  gap: 16rpx;
  flex-shrink: 0;
}
.msg-input {
  flex: 1;
  min-height: 72rpx;
  max-height: 200rpx;
  background: #f5f5f5;
  border-radius: 8rpx;
  padding: 16rpx;
  font-size: 28rpx;
  line-height: 1.5;
}
.send-btn {
  background: #1a73e8;
  color: #fff;
  font-size: 28rpx;
  border-radius: 8rpx;
  padding: 0 32rpx;
  height: 72rpx;
  line-height: 72rpx;
  flex-shrink: 0;
  border: none;
}
.send-btn[disabled] {
  opacity: 0.5;
}
</style>
