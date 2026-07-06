<!--
  @module MOD-001  ChatInputBar
  @description  Ultra-simple chat input: text input + send + voice.
    Layout:  [textarea flex:1] [↑ send] [🎤 voice]
    No mode switching.  Voice button = long-press to record, release to send.
-->
<template>
  <view class="cib-root">
    <view class="cib-row">
      <!-- Text input -- always visible -->
      <textarea
        class="cib-text"
        v-model="inputText"
        placeholder="输入消息…"
        :disabled="isTextDisabled"
        auto-height
        :max-height="200"
        @confirm="handleSend"
      />

      <!-- Send button -- always visible -->
      <view
        class="cib-btn cib-send"
        :class="sendBtnClass"
        @tap="handleSend"
      >
        <view class="cib-ico cib-ico-send" />
      </view>

      <!-- Voice button -- long-press to record -->
      <view
        class="cib-btn cib-voice"
        :class="voiceBtnClass"
        @touchstart="handleVoiceStart"
        @touchend="handleVoiceEnd"
        @touchmove="handleVoiceMove"
      >
        <view class="cib-ico cib-ico-mic" />
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { requestPermission } from '@/utils/permission'
import { startRecording, stopAndRecognize } from '@/utils/voice-input'

const props = defineProps({
  wsConnected: { type: Boolean, required: true },
  isStreaming: { type: Boolean, required: true },
  theme: { type: String, default: 'light' },
})

const emit = defineEmits(['send', 'error'])

// ==========================================================================
// State
// ==========================================================================
const inputText = ref('')
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

const voiceBtnClass = computed(() => ({
  'cib-voice--recording': isRecording.value && !isCancelling.value,
  'cib-voice--cancelling': isCancelling.value,
  'cib-voice--disabled': isVoiceDisabled.value,
}))

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
// Voice start (long-press)
// ==========================================================================
async function handleVoiceStart(e) {
  if (isVoiceDisabled.value) return
  if (isRecording.value) return

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
// Voice end (release)
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
   ChatInputBar — Ultra-simple: textarea + send + voice
   NO scoped — avoids WeChat compound-selector mangling on Android.
   All classes use cib- namespace prefix.
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

/* ---- circle button (send / voice) ---- */
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
.cib-ico-send { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23666'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E"); }
.cib-ico-mic  { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E"); }

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

/* ---- voice button states ---- */
.cib-voice--recording {
  background-color: #c8daf7;
}
.cib-voice--recording .cib-ico-mic {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%231a73e8' stroke='%231a73e8' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
.cib-voice--cancelling {
  background-color: #fce4e4;
}
.cib-voice--disabled {
  opacity: 0.35;
  pointer-events: none;
}
</style>
