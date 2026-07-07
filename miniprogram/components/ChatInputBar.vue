<!--
  @module MOD-001  ChatInputBar
  @description  Ultra-simple: textarea + send + mic.
    Mic: ONE fixed class, always looks the same.
    JS handles disable logic (blocks action when WS down or streaming).
-->
<template>
  <view :class="isDark ? 'cib-root--dark' : 'cib-root'">
    <view class="cib-row">
      <textarea
        :class="isDark ? 'cib-text--dark' : 'cib-text'"
        v-model="inputText"
        placeholder="向智能方舟副官提问"
        :disabled="isTextDisabled"
        auto-height :max-height="200"
        @confirm="handleSend"
      />

      <view :class="sendBtnClass" data-testid="send-btn" @tap="handleSend">
        <view :class="sendIcoClass" />
      </view>

      <view class="cib-mic" data-testid="voice-btn"
        @touchstart="handleVoiceStart"
        @touchend="handleVoiceEnd"
        @touchmove="handleVoiceMove"
      >
        <view :class="isDark ? 'cib-ico-mic--dark' : 'cib-ico-mic'" />
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

const inputText = ref('')
const isRecording = ref(false)
const isCancelling = ref(false)
let _touchStartY = 0

const isDark = computed(() => props.theme === 'dark')
const isTextDisabled = computed(() => !props.wsConnected || props.isStreaming)
const isVoiceDisabled = computed(() => !props.wsConnected || props.isStreaming)
const hasText = computed(() => inputText.value.trim().length > 0)
const canSend = computed(() => props.wsConnected && !props.isStreaming && hasText.value)

const sendBtnClass = computed(() => {
  if (isDark.value) return canSend.value ? 'cib-send--dark-active' : 'cib-send--dark-disabled'
  return canSend.value ? 'cib-send--active' : 'cib-send--disabled'
})
const sendIcoClass = computed(() => isDark.value ? 'cib-ico-send--dark' : 'cib-ico-send')

function handleSend() {
  if (!canSend.value) return
  const text = inputText.value.trim()
  if (!text) return
  emit('send', { text, media: [] })
  inputText.value = ''
}

async function handleVoiceStart(e) {
  if (isVoiceDisabled.value) return
  if (isRecording.value) return
  isRecording.value = true
  isCancelling.value = false

  const permResult = await requestPermission('scope.record', { name: '录音' })
  if (permResult !== 'authorized') {
    isRecording.value = false
    if (permResult === 'denied') emit('error', { code: 'PERMISSION_DENIED', message: '录音权限未开启' })
    return
  }
  const touch = e.touches && e.touches[0]
  _touchStartY = touch ? touch.pageY : 0
  try { await startRecording() }
  catch (err) { isRecording.value = false; emit('error', { code: 'RECORD_START_FAILED', message: '录音启动失败' }) }
}

async function handleVoiceEnd() {
  if (!isRecording.value) return
  isRecording.value = false
  if (isCancelling.value) { isCancelling.value = false; try { stopAndRecognize() } catch (_) {}; return }
  try {
    const result = await stopAndRecognize()
    if (result && typeof result === 'string') emit('send', { text: result, media: [] })
    else if (result && result.text) emit('send', { text: result.text, media: [] })
  } catch (err) { emit('error', { code: 'RECORD_STOP_FAILED', message: '语音识别失败' }) }
}

function handleVoiceMove(e) {
  if (!isRecording.value) return
  const touch = e.touches && e.touches[0]
  if (!touch) return
  isCancelling.value = (_touchStartY - touch.pageY) > 60
}
</script>

<style>
.cib-root { background: #fff; border-top: 1rpx solid #eee; flex-shrink: 0; }
.cib-root--dark { background: rgba(8,14,28,0.7); border-top: 1px solid rgba(56,230,224,0.12); flex-shrink: 0; }
.cib-row { display: flex; align-items: flex-end; padding: 16rpx 24rpx; gap: 12rpx; }

.cib-text {
  flex: 1; min-height: 44rpx; max-height: 180rpx; background: #f5f5f5;
  border-radius: 12rpx; padding: 10rpx 16rpx; font-size: 28rpx;
  line-height: 1.5; box-sizing: border-box; color: #333;
}
.cib-text--dark {
  flex: 1; min-height: 44rpx; max-height: 180rpx;
  background: rgba(4,10,22,0.7); border: 1px solid rgba(56,230,224,0.25);
  border-radius: 12rpx; padding: 10rpx 16rpx; font-size: 28rpx;
  line-height: 1.5; box-sizing: border-box; color: #eaf6ff;
}

/* ---- send ---- */
.cib-send--active {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 64rpx; height: 64rpx; border-radius: 50%; background: #1a73e8;
}
.cib-send--disabled {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 64rpx; height: 64rpx; border-radius: 50%;
  background-color: #f5f5f5; opacity: 0.35; pointer-events: none;
}
.cib-send--dark-active {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 64rpx; height: 64rpx; border-radius: 50%;
  background: linear-gradient(135deg, #22e6da, #3a8bff);
  box-shadow: 0 0 20px rgba(47,244,224,0.55);
}
.cib-send--dark-disabled {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 64rpx; height: 64rpx; border-radius: 50%;
  background-color: rgba(56,230,224,0.18);
  border: 1px solid rgba(56,230,224,0.35);
  opacity: 0.45; pointer-events: none;
}
.cib-ico-send {
  width: 40rpx; height: 40rpx; background-repeat: no-repeat;
  background-position: center; background-size: contain;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23666'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
.cib-ico-send--dark {
  width: 40rpx; height: 40rpx; background-repeat: no-repeat;
  background-position: center; background-size: contain;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%232ff4e0'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}

/* ---- mic: ONE fixed class (same as send dark disabled, always visible) ---- */
.cib-mic {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 64rpx; height: 64rpx; border-radius: 50%;
  background-color: rgba(56,230,224,0.18);
  border: 1px solid rgba(56,230,224,0.35);
  opacity: 0.45;
}
.cib-ico-mic {
  width: 40rpx; height: 40rpx; background-repeat: no-repeat;
  background-position: center; background-size: contain;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
.cib-ico-mic--dark {
  width: 40rpx; height: 40rpx; background-repeat: no-repeat;
  background-position: center; background-size: contain;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
</style>
