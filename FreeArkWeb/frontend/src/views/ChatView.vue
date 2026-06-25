<template>
  <div class="chat-view">
    <!-- 左侧会话面板 -->
    <SessionSidebar
      :currentSessionKey="currentSessionKey"
      @session-selected="handleSessionSelected"
    />

    <!-- 右侧主内容区 -->
    <div class="chat-main">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-title-group">
        <div class="ph-accent-inline"></div>
        <div>
          <h2>和方舟智能体聊天</h2>
          <p class="page-subtitle">方舟智能体 · 流式回复体验</p>
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

      <!-- v1.4: 历史消息加载中提示（isHistoryLoading，REQ-NFR-001） -->
      <div v-if="isHistoryLoading" class="chat-history-loading">
        <span class="history-loading-text">正在加载历史消息...</span>
      </div>

      <!-- v1.4: 历史消息加载失败横幅（historyLoadError，可继续聊天） -->
      <div v-if="historyLoadError" class="chat-history-error">
        <el-icon><Warning /></el-icon>
        <span>{{ historyLoadError }}</span>
        <el-button type="text" size="small" @click="historyLoadError = ''">关闭</el-button>
      </div>

      <!-- v1.4: 历史消息为空提示（historyEmpty，US-007 AC-007-01） -->
      <div v-if="historyEmpty && !isHistoryLoading && messages.length === 0" class="chat-history-empty">
        <p>该会话暂无历史记录，可直接发送新消息</p>
      </div>

      <!-- 空状态（新会话欢迎语，仅非历史加载场景显示） -->
      <div v-if="messages.length === 0 && !isHistoryLoading && !historyEmpty && !historyLoadError" class="chat-empty">
        <div class="chat-empty-icon"><Bot :size="48" /></div>
        <p class="chat-empty-text">你好！我是方舟智能体，有什么可以帮助你的？</p>
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
            <span class="avatar-icon"><Bot :size="18" /></span>
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
            <!-- MOD-FE-01 IFC-002: stream_end 后助手消息 → Markdown 渲染（ADR-001 方向A，ADR-003 两阶段）-->
            <!-- confirm 卡片激活时不渲染，保持纯文本（IFC-002 条件4）-->
            <div
              v-else-if="isRenderable(msg)"
              class="bubble-content bubble-content--rendered"
              v-html="renderMarkdown(msg.content)"
            ></div>
            <!-- 降级：用户消息 / 流式中 / confirm 激活中的助手消息 → 纯文本插值（REQ-NFUNC-006）-->
            <span v-else class="bubble-content">
              <!-- v1.9.0 history 含图前缀检测：覆盖 v1.5.0 单图格式和 v1.9.0 多图格式 -->
              <!-- 单图格式：[图片描述：...] | 多图格式：[图片1描述：...] [图片2描述：...] -->
              <!-- 若有前缀则显示"含图"徽标，不显示 VLM 描述原文（保持简洁）-->
              <template v-if="msg.content && /^\[图片(\d+)?描述：/.test(msg.content)">
                <span class="msg-image-badge">
                  <el-icon :size="10"><Picture /></el-icon> 含图
                </span>
                <!-- 提取原始文字部分（跳过所有 [图片N描述：...] 前缀）-->
                {{ msg.content.replace(/\[图片(\d+)?描述：[^\]]*\]\s*/g, '').trim() || '（图片消息）' }}
              </template>
              <!-- v1.5.0/v1.9.0 新消息含图标注：hasImage=true 说明本次发送含图（尚未入库，无前缀）-->
              <template v-else-if="msg.hasImage">
                <span class="msg-image-badge">
                  <el-icon :size="10"><Picture /></el-icon> 含图
                </span>
                {{ msg.content }}
              </template>
              <template v-else>{{ msg.content }}</template>
            </span>
            <!-- 「正在思考...」/ 静默期进度：无 reasoning 活动且 content 为空时显示；
                 收到 status_update 则显示动态进度文案（如"正在调取数据并生成回复…"）-->
            <span
              v-if="msg.streaming && !msg.content && !msg.reasoning && !msg.reasoningStreaming"
              class="thinking-indicator"
            >{{ msg.statusText || '正在思考...' }}</span>
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

            <!-- v1.4.1 新增（IFC-141-1001/1002/1003，MOD-141-10）：图片引用区域 -->
            <!-- 仅在 stream_end 后（streaming=false）且有 related_images 时渲染 -->
            <div
              v-if="!msg.streaming && msg.relatedImages && msg.relatedImages.length > 0"
              class="rag-images-section"
            >
              <div class="rag-images-label">相关图片参考</div>
              <div class="rag-images-grid">
                <div
                  v-for="img in msg.relatedImages"
                  :key="img.image_id"
                  class="rag-image-item"
                >
                  <!-- blob: URL 就绪后渲染 el-image；未就绪时显示占位 loading -->
                  <el-image
                    v-if="msg.imageUrls[img.image_id]"
                    :src="msg.imageUrls[img.image_id]"
                    fit="contain"
                    :preview-src-list="[msg.imageUrls[img.image_id]]"
                    class="rag-image-thumb"
                  />
                  <div v-else class="rag-image-loading">
                    <span>加载中...</span>
                  </div>
                  <div v-if="img.source" class="rag-image-source" :title="img.source">
                    {{ img.source }}
                  </div>
                </div>
              </div>
            </div>
            <!-- ─────────────────────────────────────────────── -->
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
      <!-- v1.9.0：多图预览区（选中1~5张图片后显示，REQ-MI-001）-->
      <div v-if="selectedImages.length > 0" class="image-preview-area image-preview-area--multi">
        <div
          v-for="(img, idx) in selectedImages"
          :key="idx"
          class="image-preview-item"
        >
          <img :src="img.previewDataURL" class="image-preview-thumb" :alt="`待发送图片${idx+1}`" />
          <button class="image-preview-clear" @click="removeImage(idx)" :title="`移除第${idx+1}张图片`">×</button>
        </div>
        <!-- 已达上限提示（REQ-MI-002 方案A：已达5张则显示提示）-->
        <span v-if="selectedImages.length >= 5" class="image-limit-hint">已达上限（5/5）</span>
        <!-- VLM 分析进度提示（多图进度，由服务端传来）-->
        <span v-if="isAnalyzingImage" class="image-analyzing-hint">{{ visionProgressMsg || '正在分析图片内容…' }}</span>
      </div>

      <div class="chat-input-wrapper">
        <!-- v1.9.0：图片上传按钮（多选，已达5张时禁用，REQ-MI-002）-->
        <input
          ref="imageFileInput"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          multiple
          style="display:none"
          @change="onImageSelect"
        />
        <el-button
          class="chat-image-btn"
          :disabled="!wsConnected || isWaiting || selectedImages.length >= 5"
          :title="selectedImages.length >= 5 ? '已达上限（最多5张图片）' : '上传图片（支持 JPEG/PNG/WebP，最大 10MB，最多5张）'"
          @click="imageFileInput && imageFileInput.click()"
        >
          <el-icon><Picture /></el-icon>
          <span v-if="selectedImages.length > 0" class="image-count-badge">{{ selectedImages.length }}</span>
        </el-button>

        <el-input
          v-model="inputText"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          :disabled="!wsConnected || isWaiting"
          :placeholder="selectedImages.length > 0 ? '添加文字说明（可选，直接发送将分析图片内容）' : inputPlaceholder"
          resize="none"
          class="chat-input"
          @keydown.enter.exact.prevent="handleSend"
          @keydown.enter.shift.exact="handleShiftEnter"
        />
        <el-button
          type="primary"
          :disabled="!wsConnected || isWaiting || (!inputText.trim() && selectedImages.length === 0)"
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
  </div>
</template>

<script>
/**
 * @module MOD-FE-01 (MarkdownRenderer)
 * @implements IFC-001 (renderMarkdown), IFC-002 (isRenderable)
 * @depends marked (npm), dompurify (npm)
 * @author sub_agent_software_developer
 * @see project_workspace/FreeArk_ChatFormat/architecture/module_design.md
 */
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { User, Warning, Position, Picture } from '@element-plus/icons-vue'
import { Bot } from 'lucide-vue-next'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import SessionSidebar from '../components/SessionSidebar.vue'
import api, { fetchRagImage, uploadChatImage, uploadChatImages } from '../utils/api.js'
import {
  chatHistoryCache,
  chatHistoryCacheTime,
  chatHistoryCacheKey,
} from '../router/index.js'

const CHAT_HISTORY_CACHE_TTL_MS = 30000  // 与会话列表缓存 TTL 保持一致

// MOD-FE-01: 配置 marked — 启用 GFM 表格（REQ-FUNC-002）和 breaks（REQ-FUNC-003）
// ADR-002 决策：marked + DOMPurify 组合
marked.use({ gfm: true, breaks: true })

// MOD-FE-01 IFC-001: renderMarkdown(rawText: string) → string（安全 HTML，已 XSS 消毒）
// 定义在模块级别以支持独立单元测试（REQ-NFUNC-004 可维护性）
// ADR-003 两阶段渲染：仅在 stream_end 后（isRenderable 为 true 时）才被模板调用
// ADR-004 DOMPurify 客户端消毒：LLM 输出视为不可信输入（REQ-NFUNC-003）
const DOMPURIFY_CONFIG = {
  ALLOWED_TAGS: [
    'p', 'br', 'hr', 'strong', 'em', 'del',
    'ul', 'ol', 'li',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'code', 'pre', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'a', 'span', 'div',
  ],
  ALLOWED_ATTR: ['href', 'title', 'class', 'target', 'rel'],
  FORCE_BODY: false,
}

export function renderMarkdown(rawText) {
  if (!rawText) return ''
  const htmlRaw = marked.parse(rawText)
  return DOMPurify.sanitize(htmlRaw, DOMPURIFY_CONFIG)
}

// MOD-FE-01 IFC-002: isRenderable(msg: MessageObject) → boolean
// 严格4条件 AND：仅对流结束后的助手消息（无 confirm 卡片）启用 Markdown 渲染
// 保证流式期间（msg.streaming===true）始终走纯文本路径（REQ-NFUNC-002 满足）
export function isRenderable(msg) {
  return (
    msg.role === 'assistant' &&
    msg.streaming === false &&
    msg.content.length > 0 &&
    msg.confirm === null
  )
}

// WebSocket 连接地址构建
// 根据当前页面协议自动选择 ws:// 或 wss://
// sessionKey 可选：传入时追加 &session_key=... 以加载已有会话
function buildWsUrl(token, sessionKey) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  let url = `${protocol}//${host}/ws/chat/?token=${encodeURIComponent(token)}`
  if (sessionKey) {
    url += `&session_key=${encodeURIComponent(sessionKey)}`
  }
  return url
}

const MAX_RECONNECT = 3
const RECONNECT_DELAY_MS = 2000

export default {
  name: 'ChatView',
  components: {
    User,
    Warning,
    Position,
    Picture,
    Bot,
    SessionSidebar,
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
    const imageFileInput = ref(null)   // v1.5.0：隐藏 file input 的模板引用（MOD-MQ-01）
    const currentSessionKey = ref(null)

    // v1.4 历史消息加载状态（MOD-FE-CHAT，IFC-FE-CHAT-001，REQ-NFR-001）
    const isHistoryLoading = ref(false)    // 历史消息加载 loading 状态
    const historyLoadError = ref('')       // 历史消息加载错误提示
    const historyEmpty = ref(false)        // 历史消息为空标记（US-007 空状态提示）

    // v1.5.0 多模态提问（MOD-MQ-01，REQ-FUNC-001）
    // v1.9.0 扩展为多图（MOD-MI-01，REQ-MI-001）
    const selectedImageBlob = ref(null)    // v1.5.0 保留（向后兼容，不直接使用）
    const previewDataURL = ref(null)       // v1.5.0 保留（向后兼容，不直接使用）
    const isAnalyzingImage = ref(false)    // VLM 分析进行中（显示进度提示）
    // v1.9.0 新增：多图列表（最多5张，REQ-MI-001）
    // 每个元素：{ blob: Blob, previewDataURL: string }
    const selectedImages = ref([])
    const visionProgressMsg = ref('')     // 当前进度提示文字（多图分析时显示）

    // WebSocket 实例（非响应式，避免 Vue 代理 WS 对象）
    let ws = null
    const reconnectCount = ref(0)
    let reconnectTimer = null

    // --- 计算属性 ---
    const inputPlaceholder = computed(() => {
      if (!wsConnected.value) return '连接中，请稍候...'
      if (isWaiting.value) return '方舟智能体正在回复中...'
      return '输入消息，Enter 发送'
    })

    // --- WebSocket 连接 ---
    function connectWS(sessionKey) {
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

      const url = buildWsUrl(token, sessionKey || null)
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
            connectWS(currentSessionKey.value)
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
      connectWS(currentSessionKey.value)
    }

    /**
     * 将历史消息接口返回的 HistoryMessage 映射为 ChatView 内部消息对象格式。
     * IFC-FE-CHAT-001 历史消息格式转换（模块设计文档 MOD-FE-CHAT）。
     */
    function mapHistoryToMessage(hm) {
      return {
        role: hm.role,           // "user" | "assistant"
        content: hm.content,
        chunks: [],
        reasoning: '',
        streaming: false,
        reasoningStreaming: false,
        confirm: null,
        statusText: '',
        // v1.4.1 新增（IFC-141-1001）：图片引用（历史消息不含，初始化为空）
        relatedImages: [],   // [{ image_id, source }]
        imageUrls: {},       // image_id → blob: URL（懒加载）
      }
    }

    /**
     * 处理会话切换（v1.4 改造，IFC-FE-CHAT-001）。
     *
     * sessionKey = null：新建会话，不加载历史，直接 connectWS(null)。
     * sessionKey 非 null：切换已有会话，并行 connectWS + api.getSessionHistory 加载历史。
     *   - 历史加载成功：messages.value = history（升序）
     *   - 历史加载失败：historyLoadError 提示（WS 聊天仍可使用）
     *   - 历史为空：historyEmpty = true（US-007 空状态提示）
     *
     * cachedHistory（可选）：路由预取缓存数据（{ messages }），命中时跳过 HTTP 请求，
     *   直接渲染缓存内容；后台静默刷新由 onMounted 的 silent 逻辑负责。
     *   此参数仅供内部 onMounted 缓存优先路径使用，侧边栏点击切换时不传。
     */
    async function handleSessionSelected(sessionKey, cachedHistory) {
      // 1. 重置所有状态
      messages.value = []
      historyLoadError.value = ''
      historyEmpty.value = false
      if (ws) {
        ws.onclose = null
        ws.onerror = null
        ws.onmessage = null
        try { ws.close() } catch (_) { /* 忽略 */ }
        ws = null
      }
      wsConnected.value = false
      reconnectCount.value = 0
      errorMessage.value = ''

      if (!sessionKey) {
        // 新建会话：不加载历史，直接建立 WS 连接
        isHistoryLoading.value = false
        connectWS(null)
        return
      }

      // 切换已有会话：WS 连接先启动（不等 history 加载，REQ-NFR-001 不阻塞界面）
      connectWS(sessionKey)

      // 缓存优先路径：路由 beforeEnter 已预取历史，直接渲染，跳过 HTTP 请求
      if (cachedHistory) {
        isHistoryLoading.value = false
        const historyMessages = (cachedHistory.messages || []).map(mapHistoryToMessage)
        if (historyMessages.length === 0) {
          historyEmpty.value = true
        } else {
          messages.value = historyMessages
          await nextTick()
          scrollToBottom()
        }
        return
      }

      // 正常路径：网络加载历史消息（通过 api.js，团队规范：禁止裸 axios）
      isHistoryLoading.value = true
      try {
        const data = await api.getSessionHistory(sessionKey)
        const historyMessages = (data.messages || []).map(mapHistoryToMessage)
        if (historyMessages.length === 0) {
          historyEmpty.value = true
        } else {
          messages.value = historyMessages
        }
      } catch (err) {
        // SESSION_EXPIRED 已由 api.js authenticatedFetch 统一处理（跳转登录页）
        if (err && err.message !== 'SESSION_EXPIRED') {
          historyLoadError.value = '历史消息加载失败，可直接发送新消息'
        }
      } finally {
        isHistoryLoading.value = false
      }
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
          if (data.session_key) {
            currentSessionKey.value = data.session_key
          }
          break

        // 静默期进度提示（分类/查询/生成阶段）：更新占位文案，content 到来即被替换
        case 'status_update': {
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant' && last.streaming) {
            last.statusText = data.message || ''
          }
          break
        }

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
          // v1.5.0/v1.9.0：收到第一个 token，VLM 分析已完成，清除进度状态
          isAnalyzingImage.value = false
          visionProgressMsg.value = ''
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

        // v1.5.0 新增（MOD-MQ-01，REQ-FUNC-003）：VLM 图片分析进度提示
        // adapter 在 VLM 调用开始前 yield 此消息，前端显示进度动画
        case 'vision_progress': {
          isAnalyzingImage.value = true
          // v1.9.0：直接显示服务端传来的 message 文字（含"正在分析第N/T张"进度信息）
          const progressMsg = data.message || '正在分析图片，请稍候…'
          visionProgressMsg.value = progressMsg
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant' && last.streaming) {
            last.statusText = progressMsg
          }
          break
        }

        case 'stream_end': {
          // v1.5.0/v1.9.0：VLM 分析结束（流内容开始），清除图片分析进度状态
          isAnalyzingImage.value = false
          visionProgressMsg.value = ''
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant') {
            last.streaming = false
            // v1.4.1 新增（IFC-141-1002）：存储图片引用元数据，触发懒加载
            if (data.related_images && data.related_images.length > 0) {
              last.relatedImages = data.related_images   // [{ image_id, source }]
              last.imageUrls = {}
              // 懒加载：立即触发每张图片的 blob URL 获取
              data.related_images.forEach(img => {
                loadImageBlobUrl(last, img.image_id)
              })
            }
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
          // v1.9.0：IMAGE_ANALYSIS_PARTIAL 是非阻塞通知帧，不中断流（ADR-MI-004）
          // 其余错误码保持原有阻塞逻辑
          if (data.code === 'IMAGE_ANALYSIS_PARTIAL') {
            // 非阻塞通知：显示提示但不停止流、不重置 isWaiting
            errorMessage.value = data.message || '部分图片分析失败，已用占位文字替代'
            break
          }
          // 如果有正在流式渲染的助手消息，标记流结束
          {
            const last = messages.value[messages.value.length - 1]
            if (last && last.role === 'assistant' && last.streaming) {
              last.streaming = false
              last.content = last.content || ''  // 保留已接收到的内容
            }
          }
          // v1.5.0/v1.9.0：清除 VLM 图片分析进度状态
          isAnalyzingImage.value = false
          visionProgressMsg.value = ''
          isWaiting.value = false
          errorMessage.value = data.message || '发生未知错误'
          break

        default:
          // 静默忽略未知消息类型（向后兼容：旧前端不会有 reasoning_* 分支，
          // 新增的消息类型在旧前端中走此 default 分支，不影响功能）
          break
      }
    }

    // --- v1.5.0 图片选择、压缩、预览（MOD-MQ-01，REQ-FUNC-001）---

    /**
     * 前端支持的图片 MIME 类型白名单（客户端辅助过滤，服务端有二次校验）
     */
    const ALLOWED_IMAGE_TYPES = new Set([
      'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif',
    ])

    /**
     * onImageSelect：处理 <input type="file"> 的 change 事件（v1.9.0 多图版本）。
     * 支持多选，每张独立校验和压缩后追加到 selectedImages 列表。
     * 超过5张时拦截并提示（REQ-MI-001，REQ-MI-002）。
     */
    async function onImageSelect(event) {
      const files = event.target.files
      if (!files || files.length === 0) return

      const MAX_IMAGES = 5

      // 逐文件处理
      for (let fi = 0; fi < files.length; fi++) {
        const file = files[fi]

        // 超5张限制检查（前端主动拦截，REQ-MI-002 方案A）
        if (selectedImages.value.length >= MAX_IMAGES) {
          alert(`最多5张图片，已忽略第${fi + 1}张及之后的图片`)
          break
        }

        // 大小校验：> 10MB 拒绝
        if (file.size > 10 * 1024 * 1024) {
          alert(`图片文件过大（>10MB），请压缩后上传（第${fi + 1}张已忽略）`)
          continue
        }

        // MIME 类型客户端校验（辅助 UX，服务端有魔数检测）
        if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
          alert(`不支持的图片格式，请上传 JPEG/PNG/WebP 格式图片（第${fi + 1}张已忽略）`)
          continue
        }

        try {
          // 压缩（超过 1920×1920 时等比缩放，JPEG quality=0.85）
          const blob = await compressImage(file, 1920, 0.85)
          // 生成预览 data:URL
          const dataURL = await new Promise((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = (e) => resolve(e.target.result)
            reader.onerror = () => reject(new Error('FileReader 失败'))
            reader.readAsDataURL(blob)
          })
          selectedImages.value.push({ blob, previewDataURL: dataURL })
        } catch (err) {
          // 压缩失败降级：直接使用原文件（iOS Safari 兼容性降级，RISK-MQ-006）
          console.warn('onImageSelect: 压缩失败，使用原文件:', err.message)
          try {
            const dataURL = await new Promise((resolve, reject) => {
              const reader = new FileReader()
              reader.onload = (e) => resolve(e.target.result)
              reader.onerror = () => reject(new Error('FileReader 失败'))
              reader.readAsDataURL(file)
            })
            selectedImages.value.push({ blob: file, previewDataURL: dataURL })
          } catch (readErr) {
            console.warn('onImageSelect: 读取原文件也失败，跳过:', readErr.message)
          }
        }
      }

      // 重置 file input value（允许重复选同一文件触发 change）
      event.target.value = ''
    }

    /**
     * removeImage：从 selectedImages 中移除指定索引的图片（REQ-MI-001）。
     */
    function removeImage(index) {
      selectedImages.value.splice(index, 1)
    }

    /**
     * clearSelectedImages：清空所有已选图片（v1.9.0，替代 clearSelectedImage）。
     */
    function clearSelectedImages() {
      selectedImages.value = []
      if (imageFileInput.value) imageFileInput.value.value = ''
    }

    /**
     * clearSelectedImage：v1.5.0 兼容方法（保留，内部调用 clearSelectedImages）。
     */
    function clearSelectedImage() {
      selectedImageBlob.value = null
      previewDataURL.value = null
      clearSelectedImages()
    }

    /**
     * compressImage：使用 Canvas API 压缩图片到指定最大尺寸。
     * 若原始尺寸 ≤ maxDimension，直接返回原 Blob，不压缩。
     */
    function compressImage(blob, maxDimension = 1920, quality = 0.85) {
      return new Promise((resolve, reject) => {
        const img = new Image()
        const blobUrl = URL.createObjectURL(blob)

        img.onload = () => {
          URL.revokeObjectURL(blobUrl)

          let { width, height } = img

          // 不需要压缩：尺寸在限制内
          if (width <= maxDimension && height <= maxDimension) {
            resolve(blob)
            return
          }

          // 等比缩放
          if (width > height) {
            height = Math.round(height * (maxDimension / width))
            width = maxDimension
          } else {
            width = Math.round(width * (maxDimension / height))
            height = maxDimension
          }

          const canvas = document.createElement('canvas')
          canvas.width = width
          canvas.height = height
          const ctx = canvas.getContext('2d')
          ctx.drawImage(img, 0, 0, width, height)

          canvas.toBlob(
            (compressedBlob) => {
              if (compressedBlob) resolve(compressedBlob)
              else reject(new Error('Canvas.toBlob 返回 null'))
            },
            'image/jpeg',
            quality,
          )
        }

        img.onerror = () => {
          URL.revokeObjectURL(blobUrl)
          reject(new Error('图片加载失败'))
        }

        img.src = blobUrl
      })
    }

    // --- 发送消息（v1.9.0：支持多图混合消息）---
    async function handleSend() {
      const text = inputText.value.trim()
      const hasImages = selectedImages.value.length > 0
      // 允许纯图片消息（text 为空但有图）
      if (!text && !hasImages) return
      if (!wsConnected.value || isWaiting.value) return
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        errorMessage.value = '连接尚未就绪，请稍候'
        return
      }

      // 清除旧错误
      errorMessage.value = ''
      visionProgressMsg.value = ''

      // 决定发送的文字（多图/单图默认文案，OQ-MI-004）
      let sendText = text
      if (!sendText && hasImages) {
        sendText = selectedImages.value.length > 1 ? '请帮我分析这些图片' : '请帮我分析这张图片'
      }

      // 添加用户消息到列表（含图标注由 hasImage 驱动渲染）
      messages.value.push({
        role: 'user',
        content: sendText,
        hasImage: hasImages,   // 含图标注（用于消息气泡渲染）
      })

      // v1.9.0：若有选中图片，并发预上传获取所有 upload_id（ADR-MI-002）
      let upload_ids = []
      if (hasImages) {
        const blobs = selectedImages.value.map(img => img.blob)
        // 清空图片选择（在发出请求前清空，REQ-MI-001 发送后预览清空）
        clearSelectedImages()

        upload_ids = await uploadChatImages(blobs)

        if (upload_ids.length === 0) {
          errorMessage.value = '所有图片上传失败，可以改为纯文字描述后重试'
          messages.value.pop()
          return
        }
        if (upload_ids.length < blobs.length) {
          // 部分上传失败：继续发送（容错优先，OQ-MI-001 方案A 精神一致）
          errorMessage.value = `${blobs.length - upload_ids.length} 张图片上传失败，已继续发送剩余 ${upload_ids.length} 张`
        }
      } else {
        // 无图：清空图片选择（保持状态一致）
        clearSelectedImages()
      }

      // 发送 WebSocket 消息（ADR-MI-003：新字段 image_upload_ids 复数列表）
      const wsPayload = { type: 'chat_message', message: sendText }
      if (upload_ids.length > 0) wsPayload.image_upload_ids = upload_ids
      ws.send(JSON.stringify(wsPayload))

      // 清空输入
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
        statusText: '',            // 静默期进度提示（status_update），content 到来前显示
        // v1.4.1 新增（IFC-141-1001）：图片引用（stream_end 时写入）
        relatedImages: [],         // [{ image_id, source }]
        imageUrls: {},             // image_id → blob: URL（懒加载，loadImageBlobUrl 填入）
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

    // --- v1.4.1 图片 Blob URL 懒加载（IFC-141-1003，MOD-141-10）---
    // blob: URL 生命周期与消息列表等同；组件卸载时统一撤销（onUnmounted）。
    // 懒加载：stream_end 收到 related_images 后立即触发，不阻塞其他渲染。
    // authenticatedFetch 已在 api.js 中统一携带 Bearer Token（前端认证陷阱规避）。
    async function loadImageBlobUrl(msg, imageId) {
      try {
        const blob = await fetchRagImage(imageId)
        const blobUrl = URL.createObjectURL(blob)
        // 响应式写入：Vue 需要 [] 操作触发响应（直接赋属性已在 Vue3 中正常响应）
        msg.imageUrls[imageId] = blobUrl
      } catch (err) {
        // 取图失败不影响文字回复，仅记录 console.warn（不打扰用户）
        console.warn(`loadImageBlobUrl: 图片 ${imageId} 加载失败:`, err.message)
      }
    }

    // --- 生命周期 ---
    onMounted(() => {
      // v1.5 首屏优化：路由 beforeEnter 已预取最新会话历史，缓存命中时直接渲染，
      // 并同时发起带 sessionKey 的 WS 连接，省去用户手动点击选择会话的步骤。
      //
      // 判断缓存有效条件：
      //   1. chatHistoryCacheKey 非 null（有最新会话）
      //   2. 距写入时间 < 30s（缓存未过期）
      //   3. 与会话列表第一条 key 一致（chatHistoryCacheKey 本身已保证）
      const now = Date.now()
      const historyCacheHit = chatHistoryCacheKey !== null
        && chatHistoryCache !== null
        && (now - chatHistoryCacheTime) < CHAT_HISTORY_CACHE_TTL_MS

      if (historyCacheHit) {
        // 缓存命中：直接用最新会话 key 触发渲染（不发 HTTP 历史请求）
        currentSessionKey.value = chatHistoryCacheKey
        handleSessionSelected(chatHistoryCacheKey, chatHistoryCache)
        // 后台静默刷新：确保历史内容最新（不影响已渲染内容）
        api.getSessionHistory(chatHistoryCacheKey)
          .then(freshData => {
            // 仅在当前 session 未切换时才更新（防止用户已切换到其他会话）
            if (currentSessionKey.value === chatHistoryCacheKey) {
              const freshMsgs = (freshData.messages || []).map(mapHistoryToMessage)
              if (freshMsgs.length > 0) {
                messages.value = freshMsgs
              }
            }
          })
          .catch(() => {
            // 静默失败：已渲染的缓存内容保持不变
          })
      } else {
        // 缓存未命中（预取尚未完成或已过期）：降级为默认行为（新建会话模式）
        connectWS()
      }
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
      // v1.4.1 新增（IFC-141-1004）：撤销所有 blob: URL，防止内存泄漏
      // 每条消息的 imageUrls 是 image_id → blob: URL 映射
      messages.value.forEach(msg => {
        if (msg.imageUrls) {
          Object.values(msg.imageUrls).forEach(blobUrl => {
            try { URL.revokeObjectURL(blobUrl) } catch (_) { /* 忽略 */ }
          })
        }
      })
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
      imageFileInput,
      inputPlaceholder,
      currentSessionKey,
      // v1.4: 历史消息加载状态（MOD-FE-CHAT）
      isHistoryLoading,
      historyLoadError,
      historyEmpty,
      handleSend,
      handleShiftEnter,
      handleManualReconnect,
      handleConfirm,
      handleSessionSelected,
      renderMarkdown,
      isRenderable,
      // v1.4.1 新增（IFC-141-1003）：图片 Blob URL 懒加载（模板中 el-image 使用）
      loadImageBlobUrl,
      // v1.5.0 多模态提问（MOD-MQ-01，REQ-FUNC-001）
      selectedImageBlob,
      previewDataURL,
      isAnalyzingImage,
      onImageSelect,
      clearSelectedImage,
      // v1.9.0 多图扩展（MOD-MI-01，REQ-MI-001）
      selectedImages,
      visionProgressMsg,
      removeImage,
      clearSelectedImages,
    }
  }
}
</script>

<style scoped>
/* ---- 整体布局 ---- */
.chat-view {
  display: flex;
  flex-direction: row;
  height: calc(100vh - var(--header-height) - var(--space-5) * 2 - 32px);
  min-height: 480px;
  gap: var(--space-3);
}

.chat-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  gap: var(--space-3);
  overflow: hidden;
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

/* ---- v1.4: 历史消息加载状态区域 ---- */

/* 历史消息加载中提示（REQ-NFR-001） */
.chat-history-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-3, 12px);
  flex-shrink: 0;
}

.history-loading-text {
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, #94A3B8);
  font-style: italic;
  animation: fade-pulse 1.2s ease-in-out infinite;
}

/* 历史消息加载失败横幅 */
.chat-history-error {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: var(--space-2, 8px) var(--space-3, 12px);
  background-color: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: var(--radius-base, 6px);
  color: #FCD34D;
  font-size: var(--font-size-sm, 12px);
  flex-shrink: 0;
}

/* 历史消息为空提示（US-007 AC-007-01） */
.chat-history-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5, 24px) var(--space-3, 12px);
  flex-shrink: 0;
}

.chat-history-empty p {
  margin: 0;
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-secondary, #94A3B8);
  font-style: italic;
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

/* ---- v1.5.0 图片上传 & 预览（MOD-MQ-01，REQ-FUNC-001）---- */
.chat-image-btn {
  height: 38px;
  flex-shrink: 0;
  padding: 0 10px;
}

/* 图片预览区（选中图片后在输入框上方显示）*/
.image-preview-area {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: 6px 8px;
  background-color: var(--color-bg-card, #1E293B);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-base, 6px);
  margin-bottom: 2px;
}

.image-preview-thumb {
  max-height: 80px;
  max-width: 120px;
  object-fit: contain;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.image-preview-clear {
  background: rgba(255, 255, 255, 0.1);
  border: none;
  color: var(--color-text-secondary, #64748B);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background-color 0.15s, color 0.15s;
}

.image-preview-clear:hover {
  background: rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

/* VLM 分析中进度提示文字 */
.image-analyzing-hint {
  font-size: var(--font-size-xs, 12px);
  color: var(--el-color-primary, #409EFF);
  animation: analyzing-pulse 1.2s ease-in-out infinite;
  flex-grow: 1;
}

@keyframes analyzing-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ---- v1.5.0 消息气泡含图标注 ---- */
/* 用户消息气泡内的含图徽标（独立于 [图片描述：] 前缀逻辑，用于显示时标注）*/
.msg-image-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--font-size-xs, 11px);
  color: var(--color-text-secondary, #64748B);
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
  padding: 1px 6px;
  margin-left: 6px;
  vertical-align: middle;
}

/* ---- MOD-FE-01：Markdown 渲染区域样式（ADR-005：:deep() 穿透 v-html 注入的 DOM）---- */
/* 容器：覆盖父级 .chat-bubble 的 white-space: pre-wrap，避免 HTML 标签换行符显示为空白 */
.bubble-content--rendered {
  white-space: normal;
}
/* 段落（REQ-FUNC-003 标点段落规整）*/
.bubble-content--rendered :deep(p) {
  margin: 4px 0;
  line-height: 1.6;
}
.bubble-content--rendered :deep(p:first-child) {
  margin-top: 0;
}
.bubble-content--rendered :deep(p:last-child) {
  margin-bottom: 0;
}
/* 粗体强调（REQ-FUNC-001）*/
.bubble-content--rendered :deep(strong) {
  font-weight: 700;
}
/* 斜体 */
.bubble-content--rendered :deep(em) {
  font-style: italic;
}
/* 删除线 */
.bubble-content--rendered :deep(del) {
  text-decoration: line-through;
  opacity: 0.7;
}
/* 表格对齐（REQ-FUNC-002）*/
.bubble-content--rendered :deep(table) {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
  margin: 8px 0;
  display: block;
  overflow-x: auto;
}
.bubble-content--rendered :deep(th),
.bubble-content--rendered :deep(td) {
  border: 1px solid rgba(255, 255, 255, 0.15);
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;
}
.bubble-content--rendered :deep(th) {
  background: rgba(255, 255, 255, 0.06);
  font-weight: 600;
}
/* 列表（REQ-FUNC-004 缩进层级）*/
.bubble-content--rendered :deep(ul),
.bubble-content--rendered :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}
.bubble-content--rendered :deep(li) {
  margin: 2px 0;
  line-height: 1.5;
}
/* 行内代码 */
.bubble-content--rendered :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  padding: 2px 5px;
  font-family: monospace;
  font-size: 12px;
}
/* 代码块 */
.bubble-content--rendered :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 6px;
  padding: 10px 12px;
  overflow-x: auto;
  margin: 6px 0;
}
.bubble-content--rendered :deep(pre code) {
  background: none;
  padding: 0;
  font-size: 12px;
}
/* 链接 */
.bubble-content--rendered :deep(a) {
  color: var(--el-color-primary, #409EFF);
  text-decoration: underline;
}
/* 引用块 */
.bubble-content--rendered :deep(blockquote) {
  border-left: 3px solid rgba(255, 255, 255, 0.2);
  padding-left: 10px;
  margin: 4px 0;
  color: var(--color-text-secondary, #94A3B8);
  font-style: italic;
}
/* 标题（h1~h3，LLM 输出通常最多用到 h3）*/
.bubble-content--rendered :deep(h1),
.bubble-content--rendered :deep(h2),
.bubble-content--rendered :deep(h3) {
  margin: 6px 0 4px;
  font-weight: 600;
  line-height: 1.4;
}
.bubble-content--rendered :deep(h1) { font-size: 1.1em; }
.bubble-content--rendered :deep(h2) { font-size: 1.05em; }
.bubble-content--rendered :deep(h3) { font-size: 1.0em; }
/* 分隔线（LLM 常用 --- 分段；marked 转 <hr>，渲染为干净分隔线而非被删）*/
.bubble-content--rendered :deep(hr) {
  border: none;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  margin: 8px 0;
}

/* ---- v1.4.1 RAG 图片引用区域（IFC-141-1001/1002/1003，MOD-141-10）---- */
.rag-images-section {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.rag-images-label {
  font-size: 11px;
  color: var(--color-text-secondary, #94A3B8);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.rag-images-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.rag-image-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  max-width: 180px;
}

.rag-image-thumb {
  width: 160px;
  height: 120px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 0, 0, 0.2);
  object-fit: contain;
  cursor: zoom-in;
}

.rag-image-loading {
  width: 160px;
  height: 120px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
}

.rag-image-loading span {
  font-size: 11px;
  color: var(--color-text-secondary, #94A3B8);
}

.rag-image-source {
  font-size: 11px;
  color: var(--color-text-secondary, #94A3B8);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
