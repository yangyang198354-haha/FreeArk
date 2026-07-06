<!--
  @module MOD-001  ChatInputBar
  @description  Simplified chat input bar — text input + send button + voice toggle.
    - Text mode:  [textarea flex:1] [↑ send] [🎤 mic]
    - Voice mode: [hold-to-speak flex:1] [⌨ keyboard]
    - Camera/album buttons removed for phased stabilization.
-->
<template>
  <view class="cib-root">
    <view class="cib-row">
      <!-- TEXT MODE -->
      <template v-if="!isVoiceMode">
        <textarea
          class="cib-text"
          v-model="inputText"
          placeholder="输入消息…"
          :disabled="isTextDisabled"
          auto-height
          :max-height="200"
          @confirm="handleSend"
        />
        <view
          class="cib-btn cib-send"
          :class="sendBtnClass"
          @tap="handleSend"
        >
          <view class="cib-ico cib-ico-send" />
        </view>
      </template>

      <!-- VOICE MODE -->
      <template v-else>
        <view
          class="cib-hold"
          :class="{
            'cib-hold--recording': isRecording,
            'cib-hold--cancelling': isCancelling,
            'cib-hold--disabled': isVoiceDisabled
          }"
          @touchstart="handleVoiceStart"
          @touchend="handleVoiceEnd"
          @touchmove="handleVoiceMove"
        >
          <text>{{ holdToSpeakLabel }}</text>
        </view>
      </template>

      <!-- Voice/Keyboard toggle (always enabled) -->
      <view class="cib-btn" @tap="toggleVoiceMode">
        <view :class="['cib-ico', isVoiceMode ? 'cib-ico-keyboard' : 'cib-ico-mic']" />
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { requestPermission } from '@/utils/permission'
import { startRecording, stopAndRecognize } from '@/utils/voice-input'

// ==========================================================================
// Props
// ==========================================================================
const props = defineProps({
  wsConnected: { type: Boolean, required: true },
  isStreaming: { type: Boolean, required: true },
  theme: { type: String, default: 'light' },
})

// ==========================================================================
// Emits
// ==========================================================================
const emit = defineEmits(['send', 'error'])

// ==========================================================================
// State
// ==========================================================================
const inputText = ref('')
const isVoiceMode = ref(false)
const isRecording = ref(false)
const isCancelling = ref(false)

let _touchStartY = 0

// ==========================================================================
// Computed
// ==========================================================================
const isTextDisabled = computed(() => !props.wsConnected || props.isStreaming)
const isVoiceDisabled = computed(() => !props.wsConnected || props.isStreaming)
const hasText = computed(() => inputText.value.trim().length > 0)
const canSend = computed(() => props.wsConnected && !props.isStreaming && hasText.value)

const sendBtnClass = computed(() => ({
  'cib-send--active': canSend.value,
  'cib-send--disabled': !canSend.value,
}))

const holdToSpeakLabel = computed(() => {
  if (isCancelling.value) return '松手取消'
  if (isRecording.value) return '松手发送'
  return '按住说话'
})

// ==========================================================================
// Mode toggle
// ==========================================================================
function toggleVoiceMode() {
  isVoiceMode.value = !isVoiceMode.value
  if (isVoiceMode.value) inputText.value = ''
}

// ==========================================================================
// Send
// ==========================================================================
function handleSend() {
  if (!canSend.value) return
  const text = inputText.value.trim()
  if (!text) return
  emit('send', { text, media: [] })
  inputText.value = ''
}

// ==========================================================================
// Voice start
// ==========================================================================
async function handleVoiceStart(e) {
  if (isVoiceDisabled.value) return
  if (isRecording.value) return

  // ⚠️  Set isRecording BEFORE await to close the race window.  If the user
  //     releases during the permission dialog, handleVoiceEnd must see that
  //     recording is in progress so it calls stopAndRecognize().
  isRecording.value = true
  isCancelling.value = false

  const permResult = await requestPermission('scope.record', { name: '录音' })
  if (permResult !== 'authorized') {
    isRecording.value = false
    if (permResult === 'denied') {
      emit('error', { code: 'PERMISSION_DENIED', message: '录音权限未开启，请在设置中允许' })
    }
    return
  }

  const touch = e.touches && e.touches[0]
  _touchStartY = touch ? touch.pageY : 0

  try {
    await startRecording()
  } catch (err) {
    isRecording.value = false
    emit('error', { code: 'RECORD_START_FAILED', message: '录音启动失败，请重试' })
  }
}

// ==========================================================================
// Voice end
// ==========================================================================
async function handleVoiceEnd() {
  if (!isRecording.value) return
  isRecording.value = false

  if (isCancelling.value) {
    isCancelling.value = false
    try { stopAndRecognize() } catch (_) { /* discard */ }
    return
  }

  try {
    const result = await stopAndRecognize()
    if (result && result.text) {
      emit('send', { text: result.text, media: [] })
    }
  } catch (err) {
    emit('error', { code: 'RECORD_STOP_FAILED', message: '语音识别失败，请使用文字输入' })
  }
}

// ==========================================================================
// Voice move — cancel detection
// ==========================================================================
function handleVoiceMove(e) {
  if (!isRecording.value) return
  const touch = e.touches && e.touches[0]
  if (!touch) return
  isCancelling.value = (_touchStartY - touch.pageY) > 60
}
</script>

<style>
/* ========================================================================
   ChatInputBar — Simplified layout (NO scoped — avoids WeChat compound-
   selector mangling on Android where .a.b → .a .b breaks everything)
   All classes use cib- (chat-input-bar) namespace prefix.
   ======================================================================== */

.cib-root {
  background: #fff;
  border-top: 1rpx solid #eee;
  flex-shrink: 0;
}

.cib-row {
  display: flex;
  align-items: flex-end;
  padding: 16rpx 24rpx;
  gap: 12rpx;
}

/* ---- icon button (send / voice-toggle) ---- */
.cib-btn {
  width: 56rpx;
  height: 56rpx;
  border-radius: 50%;
  background-color: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cib-ico {
  width: 36rpx;
  height: 36rpx;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
}

/* SVG icons (data-URI) */
.cib-ico-send     { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23666'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E"); }
.cib-ico-mic      { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E"); }
.cib-ico-keyboard  { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='2' y='4' width='20' height='16' rx='2'/%3E%3Cpath d='M6 8h.01M10 8h8M10 12h8M6 12h.01M14 16h4M6 16h2'/%3E%3C/svg%3E"); }

/* ---- textarea ---- */
.cib-text {
  flex: 1;
  min-height: 56rpx;
  max-height: 200rpx;
  background: #f5f5f5;
  border-radius: 12rpx;
  padding: 12rpx 20rpx;
  font-size: 28rpx;
  line-height: 1.5;
  box-sizing: border-box;
}

/* ---- send button states ---- */
.cib-send--active {
  background-color: #1a73e8;
}
.cib-send--active .cib-ico-send {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23fff'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
.cib-send--disabled {
  opacity: 0.35;
  pointer-events: none;
}

/* ---- hold-to-speak ---- */
.cib-hold {
  flex: 1;
  height: 56rpx;
  border-radius: 12rpx;
  background-color: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28rpx;
  color: #333;
  user-select: none;
}
.cib-hold--recording {
  background-color: #c8daf7;
  color: #1a73e8;
}
.cib-hold--cancelling {
  background-color: #fce4e4;
  color: #d93025;
}
.cib-hold--disabled {
  opacity: 0.35;
  pointer-events: none;
}
</style>
