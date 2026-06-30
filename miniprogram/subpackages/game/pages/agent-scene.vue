<!--
  @module MOD-PAGE-AGENT-SCENE
  @depends MOD-CHAT-WS (chat-ws.js), MOD-GAME-ARKROBOT (arkRobot.js), MOD-STORE-AUTH
  @description 方舟智能体·机器人对话场景（游戏化 POC）。
    上半屏 Canvas 渲染一只悬浮机器人，由聊天 WS 生命周期驱动状态机：
      连接中→booting / 空闲→idle / 录音→listening / 状态·推理→thinking / 流式输出→speaking。
    下半屏对话记录 + 输入条（文字发送 / 按住说话）。

    聊天链路：严格复用既有 ChatWebSocket（utils/chat-ws.js）——
      token 走 query、connected 帧才算连上、stream_token 流式、confirm_required 写确认门、
      onHide 必须 close()。后端经进程内 LangGraph 直连 DeepSeek，零后端改动。

    语音：uni.getRecorderManager() 真实录音 + 驱动 listening 动画；
      语音转文字（ASR）需微信「同声传译」插件，默认关闭（VOICE_ASR_ENABLED=false），
      开启步骤见 recognizeVoice() 注释。关闭时录音可用、识别给出明确提示，不伪造文本。

    渲染纯 Canvas 2D（无 Pixi/Spine）；运行时须真机/开发者工具验证。
-->
<template>
  <view class="agent-page">
    <!-- 机器人舞台 -->
    <view class="robot-stage">
      <canvas type="2d" id="robotCanvas" canvas-id="robotCanvas" class="robot-canvas" />
      <view class="state-chip" :class="'chip-' + robotState"><text>{{ stateLabel }}</text></view>
      <view v-if="caption" class="caption"><text>{{ caption }}</text></view>
    </view>

    <!-- 对话记录 -->
    <scroll-view class="transcript" scroll-y :scroll-top="scrollTop" :scroll-with-animation="true">
      <view v-if="messages.length === 0" class="empty">
        <text>向方舟智能体打个招呼吧 👋</text>
        <text class="empty-sub">它能查看方舟状态、解读故障、协助操控</text>
      </view>

      <view
        v-for="(m, i) in messages"
        :key="i"
        class="row"
        :class="m.role === 'user' ? 'row-user' : 'row-ai'"
      >
        <view class="bubble" :class="m.role === 'user' ? 'bubble-user' : 'bubble-ai'">
          <text v-if="m.statusText && m.streaming && !m.content" class="status-text">{{ m.statusText }}</text>
          <text class="bubble-text">{{ m.content }}<text v-if="m.streaming" class="caret">▋</text></text>

          <!-- 写确认门 -->
          <view v-if="m.confirmActions && m.confirmActions.length" class="confirm-box">
            <text class="confirm-tip">智能体请求执行操作，是否同意？</text>
            <view class="confirm-btns">
              <view class="cf-btn cf-yes" @tap="handleConfirm(true)"><text>同意</text></view>
              <view class="cf-btn cf-no" @tap="handleConfirm(false)"><text>拒绝</text></view>
            </view>
          </view>
        </view>
      </view>
      <view :style="{ height: '1px' }" />
    </scroll-view>

    <!-- 断连横幅 -->
    <view v-if="!wsConnected && !connecting" class="disc-banner">
      <text>连接已断开，</text><text class="relink" @tap="connectWs">点击重连</text>
    </view>

    <!-- 输入条 -->
    <view class="input-bar">
      <textarea
        class="msg-input"
        v-model="inputText"
        placeholder="和方舟智能体说点什么…"
        :disabled="!wsConnected || isStreaming || recording"
        auto-height
        :maxlength="-1"
        @confirm="sendMessage"
      />
      <view
        class="mic-btn"
        :class="{ rec: recording }"
        @touchstart="startVoice"
        @touchend="stopVoice"
        @touchcancel="stopVoice"
      ><text>{{ recording ? '松开' : '🎤' }}</text></view>
      <button
        class="send-btn"
        :disabled="!wsConnected || isStreaming || !inputText.trim()"
        @tap="sendMessage"
      >发送</button>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, nextTick, getCurrentInstance } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { ChatWebSocket } from '@/utils/chat-ws'
import { ArkRobotRenderer } from '../arkRobot'

// 语音转文字开关：需在 manifest.json 注册微信「同声传译」插件后置 true（见 recognizeVoice 注释）
const VOICE_ASR_ENABLED = false

const instance = getCurrentInstance()
const authStore = useAuthStore()

// ── 对话状态（本页自持，不复用全局 chat store，避免与 AI 问答页互相干扰）──────
const messages = ref([])           // {role, content, streaming, statusText, confirmActions}
const inputText = ref('')
const wsConnected = ref(false)
const connecting = ref(false)
const recording = ref(false)
const scrollTop = ref(0)

const robotState = ref('booting')  // booting|idle|listening|thinking|speaking

const isStreaming = computed(() => {
  const last = messages.value[messages.value.length - 1]
  return !!(last && last.streaming)
})

const STATE_LABEL = {
  booting: '启动中…', idle: '在线', listening: '聆听中', thinking: '思考中', speaking: '回应中',
}
const stateLabel = computed(() => STATE_LABEL[robotState.value] || '')

const caption = computed(() => {
  if (recording.value) return '🎙 正在聆听，松开结束'
  const last = messages.value[messages.value.length - 1]
  if (last && last.streaming && last.statusText && !last.content) return last.statusText
  if (robotState.value === 'thinking') return '正在调用方舟智能体…'
  return ''
})

// ── 机器人渲染 ───────────────────────────────────────────────────────────────
let canvasNode = null
let robot = null
let rafId = null
let running = false

function setRobot(s) {
  robotState.value = s
  if (robot) robot.setState(s)
}

function setupCanvas() {
  const dpr = uni.getSystemInfoSync().pixelRatio || 2
  uni.createSelectorQuery()
    .in(instance.proxy)
    .select('#robotCanvas')
    .fields({ node: true, size: true })
    .exec((res) => {
      const info = res && res[0]
      if (!info || !info.node) return
      canvasNode = info.node
      const ctx = canvasNode.getContext('2d')
      const w = info.width
      const h = info.height
      canvasNode.width = w * dpr
      canvasNode.height = h * dpr
      ctx.scale(dpr, dpr)
      robot = new ArkRobotRenderer(canvasNode, ctx, w, h)
      robot.setState(robotState.value)
      running = true
      loop()
    })
}

function loop() {
  if (!running || !robot) return
  robot.render(Date.now())
  if (canvasNode && canvasNode.requestAnimationFrame) {
    rafId = canvasNode.requestAnimationFrame(loop)
  } else {
    rafId = setTimeout(loop, 33)
  }
}

function stopLoop() {
  running = false
  if (rafId != null) {
    if (canvasNode && canvasNode.cancelAnimationFrame) canvasNode.cancelAnimationFrame(rafId)
    else clearTimeout(rafId)
    rafId = null
  }
}

// ── 聊天 WS（复用 ChatWebSocket）─────────────────────────────────────────────
let chatWs = null

function initWs() {
  chatWs = new ChatWebSocket({
    onConnected() {
      wsConnected.value = true
      connecting.value = false
      setRobot('idle')
    },
    onStatusUpdate(msg) { setStatusText(msg); setRobot('thinking') },
    onReasoningToken() { setRobot('thinking') },
    onReasoningEnd() {},
    onToken(token) {
      appendToken(token)
      setRobot('speaking')
      if (robot) robot.pulseSpeak()
      scrollToBottom()
    },
    onStreamEnd() {
      setStreamEnd()
      setRobot('idle')
      scrollToBottom()
    },
    onConfirmRequired(actions) {
      const last = messages.value[messages.value.length - 1]
      if (last) last.confirmActions = actions
      setRobot('idle')
    },
    onError(err) {
      // 复位 connecting，否则断连横幅(v-if=!wsConnected && !connecting)永不显示
      connecting.value = false
      uni.showToast({ title: err.message || '发生错误', icon: 'none' })
      setStreamEnd()
      setRobot('idle')
    },
    onClose(code) {
      // 复位 connecting，让断连横幅能正常出现
      connecting.value = false
      wsConnected.value = false
      if (code === 4001) {
        uni.showToast({ title: '鉴权失败，请重新登录', icon: 'none' })
        authStore.logout()
        uni.reLaunch({ url: '/pages/login/index' })
      } else if (robotState.value !== 'booting') {
        setRobot('booting')
      }
    },
  })
}

function connectWs() {
  if (!authStore.token) return
  connecting.value = true
  setRobot('booting')
  chatWs.connect(authStore.token, null)
}

// 本地消息操作
function appendToken(token) {
  const last = messages.value[messages.value.length - 1]
  if (last && last.streaming) last.content += token
}
function setStatusText(text) {
  const last = messages.value[messages.value.length - 1]
  if (last && last.streaming) last.statusText = text
}
function setStreamEnd() {
  const last = messages.value[messages.value.length - 1]
  if (last) last.streaming = false
}

function pushUser(text) {
  messages.value.push({ role: 'user', content: text, streaming: false, statusText: '', confirmActions: null })
}
function pushAssistantPlaceholder() {
  messages.value.push({ role: 'assistant', content: '', streaming: true, statusText: '', confirmActions: null })
}

function sendMessage() {
  const text = inputText.value.trim()
  if (!text || !wsConnected.value || isStreaming.value) return
  inputText.value = ''
  pushUser(text)
  pushAssistantPlaceholder()
  setRobot('thinking')
  chatWs.send(text)
  scrollToBottom()
}

function handleConfirm(approved) {
  chatWs.sendConfirm(approved)
  const last = messages.value[messages.value.length - 1]
  if (last) last.confirmActions = null
}

function scrollToBottom() {
  nextTick(() => { scrollTop.value = 1e7 })
}

// ── 语音输入 ─────────────────────────────────────────────────────────────────
let recorder = null
function ensureRecorder() {
  if (recorder) return recorder
  recorder = uni.getRecorderManager()
  recorder.onStop((res) => {
    recording.value = false
    setRobot(wsConnected.value ? 'idle' : 'booting')
    recognizeVoice(res && res.tempFilePath)
  })
  recorder.onError(() => {
    recording.value = false
    setRobot('idle')
    uni.showToast({ title: '录音失败', icon: 'none' })
  })
  return recorder
}

function startVoice() {
  if (!wsConnected.value || isStreaming.value || recording.value) return
  ensureRecorder()
  recording.value = true
  setRobot('listening')
  try {
    recorder.start({ format: 'mp3', duration: 60000, sampleRate: 16000, numberOfChannels: 1 })
  } catch (e) {
    recording.value = false
    setRobot('idle')
  }
}

function stopVoice() {
  if (!recording.value) return
  try { recorder && recorder.stop() } catch (e) { recording.value = false; setRobot('idle') }
}

/**
 * 语音转文字。POC 默认未开启（VOICE_ASR_ENABLED=false）：录音真实可用、动画真实，
 * 但不伪造识别文本，仅提示。开启微信「同声传译」插件后即可真识别：
 *   1) manifest.json → mp-weixin.plugins 注册：
 *        "WechatSI": { "version": "0.3.5", "provider": "wx069ba97219f66d99" }
 *   2) 用 plugin 的 getRecordRecognitionManager() 做实时识别（边录边转），
 *      或对 tempFilePath 走后端 ASR；得到 text 后调 submitVoiceText(text)。
 *   3) 把本文件顶部 VOICE_ASR_ENABLED 置 true 并接上识别回调。
 */
function recognizeVoice(tempFilePath) {
  if (!VOICE_ASR_ENABLED) {
    uni.showToast({ title: '语音识别未开通（需同声传译插件），可改用文字', icon: 'none' })
    return
  }
  // 已开通时：在此把识别结果交给 submitVoiceText(text)
  // submitVoiceText(recognizedText)
}

/** 识别得到文本后，等同于用户发了一条消息。 */
function submitVoiceText(text) {
  if (!text || !text.trim() || !wsConnected.value || isStreaming.value) return
  pushUser(text.trim())
  pushAssistantPlaceholder()
  setRobot('thinking')
  chatWs.send(text.trim())
  scrollToBottom()
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
onLoad(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  uni.setNavigationBarTitle({ title: '方舟智能体' })
  initWs()
  connectWs()
})

onShow(() => {
  setTimeout(setupCanvas, 60)
  if (chatWs && !wsConnected.value && !connecting.value) connectWs()
})

onHide(() => {
  stopLoop()
  if (chatWs) chatWs.close()
  wsConnected.value = false
})

onUnload(() => {
  stopLoop()
  if (chatWs) chatWs.close()
})
</script>

<style scoped>
.agent-page { display: flex; flex-direction: column; height: 100vh; background: #05080f; }

.robot-stage { position: relative; height: 42vh; flex-shrink: 0; }
.robot-canvas { width: 100%; height: 100%; }
.state-chip {
  position: absolute; top: 20rpx; right: 24rpx;
  padding: 6rpx 18rpx; border-radius: 20rpx; font-size: 22rpx;
  border: 1px solid rgba(0,229,255,0.4); background: rgba(8,16,30,0.7);
}
.state-chip text { color: #7df9ff; }
.chip-listening { border-color: rgba(0,255,163,0.7); }
.chip-listening text { color: #00ffa3; }
.chip-thinking { border-color: rgba(255,200,60,0.7); }
.chip-thinking text { color: #ffc83c; }
.chip-speaking text { color: #5ae6ff; }
.caption {
  position: absolute; bottom: 16rpx; left: 0; right: 0; text-align: center;
}
.caption text { font-size: 24rpx; color: rgba(125,249,255,0.75); }

.transcript { flex: 1; padding: 16rpx 24rpx; }
.empty { text-align: center; padding-top: 60rpx; display: flex; flex-direction: column; }
.empty text { font-size: 28rpx; color: #5d7a99; }
.empty-sub { font-size: 22rpx; color: #3a5874; margin-top: 10rpx; }

.row { display: flex; margin-bottom: 18rpx; }
.row-user { justify-content: flex-end; }
.row-ai { justify-content: flex-start; }
.bubble { max-width: 78%; padding: 16rpx 20rpx; border-radius: 14rpx; }
.bubble-user { background: rgba(0,229,255,0.16); border: 1px solid rgba(0,229,255,0.4); }
.bubble-ai { background: rgba(20,34,52,0.9); border: 1px solid rgba(90,120,150,0.35); }
.bubble-text { font-size: 28rpx; color: #e6f6ff; line-height: 1.5; word-break: break-all; }
.status-text { display: block; font-size: 22rpx; color: #ffc83c; margin-bottom: 6rpx; }
.caret { color: #5ae6ff; }

.confirm-box { margin-top: 14rpx; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 12rpx; }
.confirm-tip { font-size: 22rpx; color: #ffd400; display: block; margin-bottom: 10rpx; }
.confirm-btns { display: flex; gap: 16rpx; }
.cf-btn { flex: 1; text-align: center; padding: 12rpx 0; border-radius: 8rpx; }
.cf-yes { background: rgba(0,255,163,0.18); border: 1px solid rgba(0,255,163,0.6); }
.cf-yes text { color: #00ffa3; font-size: 24rpx; }
.cf-no { background: rgba(255,46,99,0.15); border: 1px solid rgba(255,46,99,0.5); }
.cf-no text { color: #ff5c85; font-size: 24rpx; }

.disc-banner { text-align: center; padding: 12rpx; background: rgba(255,212,0,0.1); }
.disc-banner text { font-size: 24rpx; color: #ffe066; }
.relink { color: #7df9ff; text-decoration: underline; }

.input-bar {
  display: flex; align-items: flex-end; gap: 12rpx;
  padding: 16rpx 24rpx; background: rgba(8,16,30,0.95);
  border-top: 1px solid rgba(0,229,255,0.18); flex-shrink: 0;
}
.msg-input {
  flex: 1; min-height: 72rpx; max-height: 200rpx;
  background: rgba(20,34,52,0.9); border: 1px solid rgba(0,229,255,0.25);
  border-radius: 10rpx; padding: 16rpx; font-size: 28rpx; color: #e6f6ff;
}
.mic-btn {
  width: 88rpx; height: 72rpx; border-radius: 10rpx; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,229,255,0.12); border: 1px solid rgba(0,229,255,0.4);
}
.mic-btn text { color: #cfefff; font-size: 26rpx; }
.mic-btn.rec { background: rgba(0,255,163,0.22); border-color: rgba(0,255,163,0.7); }
.mic-btn.rec text { color: #00ffa3; }
.send-btn {
  flex-shrink: 0; height: 72rpx; line-height: 72rpx; padding: 0 28rpx;
  font-size: 28rpx; color: #05080f; background: #00d2ff; border-radius: 10rpx; border: none;
}
.send-btn[disabled] { opacity: 0.4; }
</style>
