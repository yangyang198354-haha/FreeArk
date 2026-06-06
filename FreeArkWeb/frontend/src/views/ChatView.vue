<template>
  <div class="chat-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-title-group">
        <div class="ph-accent-inline"></div>
        <div>
          <h2>和方舟龙虾聊天</h2>
          <p class="page-subtitle">由 OpenClaw 驱动的 AI 助手，流式回复体验</p>
        </div>
      </div>
      <!-- 连接状态指示 -->
      <div class="conn-status">
        <span class="conn-dot" :class="wsConnected ? 'conn-dot--online' : 'conn-dot--offline'"></span>
        <span class="conn-label">{{ wsConnected ? '已连接' : '未连接' }}</span>
        <el-button
          v-if="!wsConnected && reconnectCount >= MAX_RECONNECT"
          size="small"
          @click="handleManualReconnect"
        >重新连接</el-button>
      </div>
    </div>

    <!-- 消息列表区域 -->
    <div class="chat-messages" ref="messagesContainer">
      <!-- 空状态 -->
      <div v-if="messages.length === 0" class="chat-empty">
        <div class="chat-empty-icon">🦞</div>
        <p class="chat-empty-text">你好！我是方舟龙虾，有什么可以帮助你的？</p>
      </div>

      <!-- 消息列表 -->
      <template v-else>
        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="chat-message"
          :class="msg.role === 'user' ? 'chat-message--user' : 'chat-message--assistant'"
        >
          <!-- 助手消息头像/标识 -->
          <div v-if="msg.role === 'assistant'" class="chat-avatar chat-avatar--assistant">
            <span class="avatar-icon">🦞</span>
          </div>

          <!-- 消息气泡 -->
          <div class="chat-bubble" :class="msg.role === 'user' ? 'chat-bubble--user' : 'chat-bubble--assistant'">
            <!-- 思考过程折叠区（仅在有 reasoning 内容或正在 reasoning 时渲染）-->
            <!-- v-if 条件覆盖 AC-011-05 降级场景：reasoning 和 reasoningStreaming 均为空/false 时不渲染 -->
            <details
              v-if="msg.reasoning || msg.reasoningStreaming"
              :open="msg.reasoningStreaming"
              class="reasoning-details"
            >
              <summary class="reasoning-summary">🧠 思考过程</summary>
              <span class="reasoning-text">{{ msg.reasoning }}</span>
            </details>

            <!-- 正式回答区：流式期间按 chunk 渲染（每段独立 fade-in，缓解 OpenClaw
                 ~21 字/帧的块状到达观感）；流结束后切换到整段渲染避免长消息保留过多 DOM -->
            <template v-if="msg.streaming && msg.chunks && msg.chunks.length">
              <span
                v-for="(chunk, ci) in msg.chunks"
                :key="ci"
                class="bubble-chunk"
              >{{ chunk }}</span>
            </template>
            <span v-else class="bubble-content">{{ msg.content }}</span>
            <!-- 「正在思考...」：仅在无 reasoning 活动且 content 为空时显示（降级兼容） -->
            <span
              v-if="msg.streaming && !msg.content && !msg.reasoning && !msg.reasoningStreaming"
              class="thinking-indicator"
            >正在思考...</span>
            <span v-if="msg.streaming && msg.content" class="stream-cursor">|</span>

            <!-- 阶段 E：Tier-2 写操作确认卡片（需用户授权后才执行）-->
            <div v-if="msg.confirm" class="confirm-card">
              <div class="confirm-title">⚠️ 待确认的操作（授权后才会执行）</div>
              <ul class="confirm-list">
                <li v-for="(a, ai) in msg.confirm.actions" :key="ai">{{ a.preview }}</li>
              </ul>
              <div class="confirm-actions">
                <el-button type="primary" size="small" @click="handleConfirm(true)">确认执行</el-button>
                <el-button size="small" @click="handleConfirm(false)">取消</el-button>
              </div>
            </div>
          </div>

          <!-- 用户消息头像 -->
          <div v-if="msg.role === 'user'" class="chat-avatar chat-avatar--user">
            <el-icon :size="18"><User /></el-icon>
          </div>
        </div>
      </template>

      <!-- 错误提示 -->
      <div v-if="errorMessage" class="chat-error">
        <el-icon><Warning /></el-icon>
        <span>{{ errorMessage }}</span>
        <el-button type="text" size="small" @click="errorMessage = ''">关闭</el-button>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input-area">
      <div class="chat-input-wrapper">
        <el-input
          v-model="inputText"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          :disabled="!wsConnected || isWaiting"
          :placeholder="inputPlaceholder"
          resize="none"
          class="chat-input"
          @keydown.enter.exact.prevent="handleSend"
          @keydown.enter.shift.exact="handleShiftEnter"
        />
        <el-button
          type="primary"
          :disabled="!wsConnected || isWaiting || !inputText.trim()"
          :loading="isWaiting"
          class="chat-send-btn"
          @click="handleSend"
        >
          <el-icon v-if="!isWaiting"><Position /></el-icon>
          <span>{{ isWaiting ? '发送中' : '发送' }}</span>
        </el-button>
      </div>
      <p class="chat-hint">Enter 发送 · Shift+Enter 换行</p>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { User, Warning, Position } from '@element-plus/icons-vue'

// WebSocket 连接地址构建
// 根据当前页面协议自动选择 ws:// 或 wss://
function buildWsUrl(token) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}/ws/chat/?token=${encodeURIComponent(token)}`
}

const MAX_RECONNECT = 3
const RECONNECT_DELAY_MS = 2000

export default {
  name: 'ChatView',
  components: {
    User,
    Warning,
    Position,
  },
  setup() {
    // --- 状态 ---
    // v1.1 消息结构：{ role, content, reasoning, streaming, reasoningStreaming }
    const messages = ref([])
    const inputText = ref('')
    const isWaiting = ref(false)      // 等待 OpenClaw 响应期间
    const wsConnected = ref(false)
    const errorMessage = ref('')
    const messagesContainer = ref(null)

    // WebSocket 实例（非响应式，避免 Vue 代理 WS 对象）
    let ws = null
    const reconnectCount = ref(0)
    let reconnectTimer = null

    // --- 计算属性 ---
    const inputPlaceholder = computed(() => {
      if (!wsConnected.value) return '连接中，请稍候...'
      if (isWaiting.value) return '方舟龙虾正在回复中...'
      return '输入消息，Enter 发送'
    })

    // --- WebSocket 连接 ---
    function connectWS() {
      const token = localStorage.getItem('userToken')
      if (!token) {
        errorMessage.value = '未检测到登录凭证，请重新登录'
        return
      }

      // 清理旧连接
      if (ws) {
        ws.onclose = null
        ws.onerror = null
        ws.onmessage = null
        try { ws.close() } catch (_) { /* 忽略 */ }
        ws = null
      }

      const url = buildWsUrl(token)
      try {
        ws = new WebSocket(url)
      } catch (err) {
        errorMessage.value = '无法建立连接，请检查网络'
        return
      }

      ws.onopen = () => {
        // 等待后端发送 connected 消息后再标记 wsConnected
      }

      ws.onmessage = (event) => {
        handleMessage(event)
      }

      ws.onclose = (event) => {
        wsConnected.value = false
        ws = null

        // 4001 = 鉴权失败，不重连
        if (event.code === 4001) {
          errorMessage.value = '鉴权失败，请重新登录后刷新页面'
          return
        }

        // 自动重连
        if (reconnectCount.value < MAX_RECONNECT) {
          reconnectCount.value++
          errorMessage.value = `连接断开，${RECONNECT_DELAY_MS / 1000}s 后自动重连（第 ${reconnectCount.value}/${MAX_RECONNECT} 次）...`
          reconnectTimer = setTimeout(() => {
            errorMessage.value = ''
            connectWS()
          }, RECONNECT_DELAY_MS)
        } else {
          errorMessage.value = '连接多次失败，请点击"重新连接"按钮手动重试'
        }
      }

      ws.onerror = () => {
        // onerror 之后必然触发 onclose，错误提示在 onclose 中处理
      }
    }

    function handleManualReconnect() {
      reconnectCount.value = 0
      errorMessage.value = ''
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      connectWS()
    }

    // --- 消息处理（v1.1）---
    function handleMessage(event) {
      let data
      try {
        data = JSON.parse(event.data)
      } catch (_) {
        return
      }

      switch (data.type) {
        case 'connected':
          wsConnected.value = true
          reconnectCount.value = 0
          errorMessage.value = ''
          break

        // v1.1 新增：reasoning_token — 追加到 msg.reasoning，触发 <details> 展示
        case 'reasoning_token': {
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant' && last.streaming) {
            last.reasoning += data.token || ''
            if (!last.reasoningStreaming) {
              last.reasoningStreaming = true  // 触发 <details open> 渲染
            }
          }
          scrollToBottom()
          break
        }

        // v1.1 新增：reasoning_end — 折叠 <details>，content 即将开始
        case 'reasoning_end': {
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant') {
            last.reasoningStreaming = false  // 移除 :open 绑定，<details> 自动折叠
          }
          break
        }

        case 'stream_token': {
          // 找到最后一条 streaming 的 assistant 消息，追加 token
          // content：保留聚合字符串供 stream_end 后整段渲染 / 持久化
          // chunks：保留每帧增量供流式期间逐 chunk 淡入动画（A2）
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant' && last.streaming) {
            const tok = data.token || ''
            last.content += tok
            if (tok) {
              if (!last.chunks) last.chunks = []
              last.chunks.push(tok)
            }
          }
          scrollToBottom()
          break
        }

        case 'stream_end': {
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant') {
            last.streaming = false
          }
          isWaiting.value = false
          scrollToBottom()
          break
        }

        // 阶段 E：Tier-2 写操作确认门 —— 后端 interrupt，等用户授权
        case 'confirm_required': {
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant') {
            last.confirm = { actions: data.actions || [] }
            last.streaming = false  // 暂停光标，渲染确认卡片
          }
          // isWaiting 维持 true：输入保持禁用，直到用户确认/取消并完成 resume
          scrollToBottom()
          break
        }

        case 'error':
          // 如果有正在流式渲染的助手消息，用错误内容替换
          {
            const last = messages.value[messages.value.length - 1]
            if (last && last.role === 'assistant' && last.streaming) {
              last.streaming = false
              last.content = last.content || ''  // 保留已接收到的内容
            }
          }
          isWaiting.value = false
          errorMessage.value = data.message || '发生未知错误'
          break

        default:
          // 静默忽略未知消息类型（向后兼容：旧前端不会有 reasoning_* 分支，
          // 新增的消息类型在旧前端中走此 default 分支，不影响功能）
          break
      }
    }

    // --- 发送消息（v1.1：助手消息结构扩展）---
    function handleSend() {
      const text = inputText.value.trim()
      if (!text || !wsConnected.value || isWaiting.value) return
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        errorMessage.value = '连接尚未就绪，请稍候'
        return
      }

      // 清除旧错误
      errorMessage.value = ''

      // 添加用户消息到列表
      messages.value.push({ role: 'user', content: text })

      // 发送 WebSocket 消息
      ws.send(JSON.stringify({ type: 'chat_message', message: text }))

      // 清空输入，添加助手占位消息（v1.1 扩展结构）
      inputText.value = ''
      isWaiting.value = true
      messages.value.push({
        role: 'assistant',
        content: '',
        chunks: [],               // A2: 流式期间每帧增量数组，用于逐 chunk 淡入动画
        reasoning: '',            // v1.1 新增：reasoning 文本（默认空）
        streaming: true,
        reasoningStreaming: false, // v1.1 新增：收到首个 reasoning_token 后置 true
        confirm: null,             // 阶段 E：Tier-2 写确认门 { actions:[...] }，无则 null
      })

      scrollToBottom()
    }

    // --- 阶段 E：用户对 Tier-2 写操作的确认/取消 ---
    function handleConfirm(approved) {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        errorMessage.value = '连接已断开，无法提交确认'
        return
      }
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant') {
        last.confirm = null        // 移除确认卡片
        last.streaming = true       // 恢复流式光标，等待 resume 的回复
      }
      // isWaiting 维持 true：等待后端执行/取消后的 stream_end
      ws.send(JSON.stringify({ type: 'confirm_response', approved: !!approved }))
      scrollToBottom()
    }

    function handleShiftEnter() {
      // Shift+Enter 换行：由 el-input textarea 默认行为处理，此函数为占位
    }

    // --- 滚动到底部 ---
    async function scrollToBottom() {
      await nextTick()
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    }

    // --- 生命周期 ---
    onMounted(() => {
      connectWS()
    })

    onUnmounted(() => {
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) {
        ws.onclose = null
        ws.onerror = null
        ws.onmessage = null
        try { ws.close() } catch (_) { /* 忽略 */ }
        ws = null
      }
    })

    return {
      messages,
      inputText,
      isWaiting,
      wsConnected,
      errorMessage,
      reconnectCount,
      MAX_RECONNECT,
      messagesContainer,
      inputPlaceholder,
      handleSend,
      handleShiftEnter,
      handleManualReconnect,
      handleConfirm,
    }
  }
}
</script>

<style scoped>
/* ---- 整体布局 ---- */
.chat-view {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-height) - var(--space-5) * 2 - 32px);
  min-height: 480px;
  gap: var(--space-3);
}

/* ---- 页面标题行 ---- */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-shrink: 0;
}

.page-title-group {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.ph-accent-inline {
  width: 4px;
  height: 44px;
  border-radius: 2px;
  background: linear-gradient(180deg, var(--acc), var(--acc-2));
  flex-shrink: 0;
  margin-top: 2px;
}

.page-title-group h2 {
  margin: 0 0 4px 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--ink-0);
}

.page-subtitle {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--ink-2);
}

/* 连接状态 */
.conn-status {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  flex-shrink: 0;
}

.conn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.conn-dot--online {
  background-color: #22C55E;
  box-shadow: 0 0 6px #22C55E80;
}

.conn-dot--offline {
  background-color: #94A3B8;
}

.conn-label {
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, #94A3B8);
}

/* ---- 消息列表区域 ---- */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3, 12px) 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
  /* 自定义滚动条 */
  scrollbar-width: thin;
  scrollbar-color: var(--color-bg-sidebar-hover, rgba(255,255,255,0.1)) transparent;
}

.chat-messages::-webkit-scrollbar {
  width: 4px;
}

.chat-messages::-webkit-scrollbar-track {
  background: transparent;
}

.chat-messages::-webkit-scrollbar-thumb {
  background-color: var(--color-bg-sidebar-hover, rgba(255,255,255,0.1));
  border-radius: 2px;
}

/* 空状态 */
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: var(--space-3, 12px);
  color: var(--color-text-secondary, #94A3B8);
  padding: var(--space-8, 40px) 0;
}

.chat-empty-icon {
  font-size: 48px;
  line-height: 1;
}

.chat-empty-text {
  margin: 0;
  font-size: var(--font-size-base, 14px);
  text-align: center;
}

/* ---- 单条消息 ---- */
.chat-message {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2, 8px);
  max-width: 100%;
}

/* 用户消息：右对齐 */
.chat-message--user {
  flex-direction: row-reverse;
}

/* 助手消息：左对齐 */
.chat-message--assistant {
  flex-direction: row;
}

/* 头像 */
.chat-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 18px;
  line-height: 1;
}

.chat-avatar--assistant {
  background-color: var(--color-bg-sidebar-active, #1E4A8A);
  color: #fff;
}

.chat-avatar--user {
  background-color: var(--color-bg-sidebar-hover, rgba(255,255,255,0.1));
  color: var(--color-text-primary, #E2E8F0);
}

.avatar-icon {
  font-size: 18px;
  line-height: 1;
}

/* 气泡 */
.chat-bubble {
  max-width: 70%;
  padding: var(--space-2, 8px) var(--space-3, 12px);
  border-radius: 12px;
  font-size: var(--font-size-base, 14px);
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}

.chat-bubble--user {
  background-color: var(--color-bg-sidebar-active, #1E4A8A);
  color: #FFFFFF;
  border-bottom-right-radius: 4px;
}

.chat-bubble--assistant {
  background-color: var(--color-bg-card, #1E293B);
  color: var(--color-text-primary, #E2E8F0);
  border-bottom-left-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

/* 流式光标 */
.stream-cursor {
  display: inline-block;
  animation: cursor-blink 0.8s step-end infinite;
  color: var(--color-primary, #3B82F6);
  font-weight: bold;
  margin-left: 1px;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 阶段 E：Tier-2 写操作确认卡片 */
.confirm-card {
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid var(--color-warning, #F59E0B);
  border-radius: 8px;
  background: rgba(245, 158, 11, 0.08);
}
.confirm-title {
  font-weight: 600;
  color: var(--color-warning, #F59E0B);
  margin-bottom: 6px;
}
.confirm-list {
  margin: 0 0 10px;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.6;
}
.confirm-actions {
  display: flex;
  gap: 8px;
}

/* A2: 流式 chunk 渐入。OpenClaw Gateway 当前以 ~21 字/帧、170ms 间隔吐 delta，
   每帧一个 .bubble-chunk 在挂载瞬间触发一次 fade-in，把块状到达的视觉跳跃感拉平。
   动画 250ms < 帧间隔 170ms ≈ 不重叠，体感像连续生成。 */
.bubble-chunk {
  display: inline;
  animation: chunk-fade-in 250ms ease-out;
}

@keyframes chunk-fade-in {
  from { opacity: 0.25; }
  to   { opacity: 1; }
}

/* 思考中提示（降级：无 reasoning 时显示） */
.thinking-indicator {
  color: var(--color-text-secondary, #94A3B8);
  font-style: italic;
  font-size: var(--font-size-sm, 12px);
  animation: fade-pulse 1.2s ease-in-out infinite;
}

@keyframes fade-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

/* ---- 思考过程折叠区（v1.1 新增）---- */
.reasoning-details {
  margin-bottom: var(--space-2, 8px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: var(--space-2, 8px);
}

.reasoning-summary {
  cursor: pointer;
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, #94A3B8);
  user-select: none;
  list-style: none;         /* 移除默认三角 */
}

/* Firefox 需要单独设置 */
.reasoning-summary::-webkit-details-marker {
  display: none;
}

.reasoning-summary::before {
  content: '▶ ';
  font-size: 9px;
}

details[open] .reasoning-summary::before {
  content: '▼ ';
}

.reasoning-text {
  display: block;
  margin-top: var(--space-1, 4px);
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, #94A3B8);
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  max-height: 300px;        /* 防止超长 reasoning 撑破布局 */
  overflow-y: auto;
}

/* ---- 错误提示 ---- */
.chat-error {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: var(--space-2, 8px) var(--space-3, 12px);
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-base, 6px);
  color: #FCA5A5;
  font-size: var(--font-size-sm, 12px);
  flex-shrink: 0;
}

/* ---- 输入区域 ---- */
.chat-input-area {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 4px);
}

.chat-input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2, 8px);
}

.chat-input {
  flex: 1;
}

/* 覆盖 Element Plus el-textarea 样式以适配深蓝主题 */
.chat-input :deep(.el-textarea__inner) {
  background-color: var(--color-bg-card, #1E293B);
  border-color: rgba(255, 255, 255, 0.12);
  color: var(--color-text-primary, #E2E8F0);
  border-radius: var(--radius-base, 6px);
  resize: none;
  font-size: var(--font-size-base, 14px);
  line-height: 1.6;
  padding: 8px 12px;
}

.chat-input :deep(.el-textarea__inner):focus {
  border-color: var(--el-color-primary, #409EFF);
}

.chat-input :deep(.el-textarea__inner)::placeholder {
  color: var(--color-text-secondary, #64748B);
}

.chat-send-btn {
  height: 38px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.chat-hint {
  margin: 0;
  font-size: var(--font-size-xs, 11px);
  color: var(--color-text-secondary, #64748B);
  text-align: right;
  padding-right: var(--space-1, 4px);
}
</style>
