<!--
  @module MOD-001  ChatInputBar
  @description  textarea + send + mic（豆包/微信风格：发送与麦克风互斥显示）。
    v1.13.1 修复：
      1) 发送图标按 canSend 分色（激活态深色图标压在亮渐变底上），修复「输入文字后按钮看不见」。
      2) 麦克风有真正的常态/录音中/上滑取消/禁用四态，不再常驻 opacity:0.45。
      3) 无文字→显示麦克风，有文字→显示发送；二者始终留在 DOM 中（display 切换），
         以保证既有测试对 [data-testid] 元素存在性的断言不被破坏。
    禁用逻辑仍走 JS 拦截（isVoiceDisabled），视觉上另有 --disabled 修饰类。
-->
<template>
  <view :class="isDark ? 'cib-root--dark' : 'cib-root'">
    <!-- 录音浮层提示：仅录音中出现 -->
    <view v-if="isRecording" :class="isCancelling ? 'cib-rec-tip cib-rec-tip--cancel' : 'cib-rec-tip'">
      <text class="cib-rec-txt">{{ isCancelling ? '松开手指，取消发送' : '正在聆听… 上滑取消' }}</text>
    </view>

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
        <view :class="['cib-ico-send', sendIcoClass]" />
      </view>

      <view :class="micBtnClass" data-testid="voice-btn"
        @touchstart="handleVoiceStart"
        @touchend="handleVoiceEnd"
        @touchmove="handleVoiceMove"
      >
        <view :class="['cib-ico-mic', micIcoClass]" />
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

// 有文字 → 显示发送；无文字 → 显示麦克风。录音中强制显示麦克风。
const showSend = computed(() => hasText.value && !isRecording.value)
const showMic = computed(() => !showSend.value)

const sendBtnClass = computed(() => {
  const base = isDark.value
    ? (canSend.value ? 'cib-send--dark-active' : 'cib-send--dark-disabled')
    : (canSend.value ? 'cib-send--active' : 'cib-send--disabled')
  return showSend.value ? [base] : [base, 'cib-hidden']
})

// 关键修复：图标颜色必须同时依赖 canSend，否则激活态青图标压在青渐变底上不可见。
const sendIcoClass = computed(() => {
  if (isDark.value) return canSend.value ? 'cib-ico-send--dark-active' : 'cib-ico-send--dark-disabled'
  return canSend.value ? 'cib-ico-send--active' : 'cib-ico-send--disabled'
})

const micBtnClass = computed(() => {
  const cls = ['cib-mic']
  if (isDark.value) cls.push('cib-mic--dark')
  if (isCancelling.value) cls.push('cib-mic--cancelling')
  else if (isRecording.value) cls.push('cib-mic--recording')
  else if (isVoiceDisabled.value) cls.push('cib-mic--disabled')
  if (!showMic.value) cls.push('cib-hidden')
  return cls
})

const micIcoClass = computed(() => {
  if (isCancelling.value) return 'cib-ico-mic--cancel'
  if (isRecording.value) return 'cib-ico-mic--recording'
  return isDark.value ? 'cib-ico-mic--dark' : 'cib-ico-mic--light'
})

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

  // 必须在 await 之前同步读取 touch 坐标：微信小程序事件对象在异步边界后可能已被回收，
  // 原实现在权限弹窗 await 之后再读 e.touches，真机上拿到空值 → _touchStartY=0 →
  // 上滑取消阈值永远算不出来（回归修复，阈值 60 保持不变）。
  const touch = e && e.touches && e.touches[0]
  _touchStartY = touch ? touch.pageY : 0

  isRecording.value = true
  isCancelling.value = false

  const permResult = await requestPermission('scope.record', { name: '录音' })
  if (permResult !== 'authorized') {
    isRecording.value = false
    if (permResult === 'denied') emit('error', { code: 'PERMISSION_DENIED', message: '录音权限未开启' })
    return
  }

  // 快速点击（touchend 早于权限返回）时 handleVoiceEnd 已把 isRecording 置回 false，
  // 此时不能再启动录音，否则录音开始后没有对应的 stop → 录音卡死、提示 toast 常驻。
  if (!isRecording.value) return

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

/* 互斥显示用：元素保留在 DOM 中，仅视觉隐藏 */
.cib-hidden { display: none; }

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

/* ---- 录音浮层提示 ---- */
.cib-rec-tip {
  display: flex; align-items: center; justify-content: center;
  padding: 14rpx 24rpx; margin: 12rpx 24rpx 0;
  border-radius: 16rpx;
  background: rgba(47,244,224,0.12);
  border: 1px solid rgba(56,230,224,0.4);
}
.cib-rec-tip--cancel {
  background: rgba(255,77,79,0.16);
  border-color: rgba(255,77,79,0.55);
}
.cib-rec-txt { font-size: 24rpx; color: #9fe9e0; letter-spacing: 1rpx; }
.cib-rec-tip--cancel .cib-rec-txt { color: #ff9a9c; }

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

/* 图标：.cib-ico-send 只负责尺寸，颜色由 --active / --disabled 修饰类决定 */
.cib-ico-send {
  width: 40rpx; height: 40rpx; background-repeat: no-repeat;
  background-position: center; background-size: contain;
}
/* 亮色激活：白色图标压在 #1a73e8 蓝底上 */
.cib-ico-send--active {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23ffffff'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
.cib-ico-send--disabled {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23666'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
/* 暗色激活：深色图标压在青→蓝渐变底上（修复青压青不可见） */
.cib-ico-send--dark-active {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23041018'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
.cib-ico-send--dark-disabled {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%232ff4e0'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}

/* ---- mic：常态 / 录音中 / 上滑取消 / 禁用 四态 ---- */
.cib-mic {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 64rpx; height: 64rpx; border-radius: 50%;
  background-color: #f1f3f5; border: 1px solid #dcdfe3;
  transition: background-color 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.cib-mic--dark {
  background-color: rgba(56,230,224,0.14);
  border: 1px solid rgba(56,230,224,0.45);
}
/* 录音中：与发送激活态同级的视觉分量 + 呼吸光晕 */
.cib-mic--recording {
  background: linear-gradient(135deg, #22e6da, #3a8bff);
  border-color: rgba(47,244,224,0.9);
  box-shadow: 0 0 20px rgba(47,244,224,0.55);
  animation: cib-pulse 1.2s ease-in-out infinite;
}
/* 上滑取消：红色警示 */
.cib-mic--cancelling {
  background: #ff4d4f;
  border-color: rgba(255,77,79,0.9);
  box-shadow: 0 0 20px rgba(255,77,79,0.5);
}
/* 禁用：仅视觉降级，拦截仍由 JS(isVoiceDisabled) 负责 */
.cib-mic--disabled { opacity: 0.4; }

@keyframes cib-pulse {
  0%, 100% { box-shadow: 0 0 16px rgba(47,244,224,0.45); }
  50%      { box-shadow: 0 0 30px rgba(47,244,224,0.85); }
}

/* 图标：.cib-ico-mic 只负责尺寸，颜色由修饰类决定 */
.cib-ico-mic {
  width: 40rpx; height: 40rpx; background-repeat: no-repeat;
  background-position: center; background-size: contain;
}
.cib-ico-mic--light {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
.cib-ico-mic--dark {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
/* 录音中/取消：深色或白色描边，压在高饱和底色上保证对比度 */
.cib-ico-mic--recording {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23041018' stroke-width='2' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
.cib-ico-mic--cancel {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
</style>
