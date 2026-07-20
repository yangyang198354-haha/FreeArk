<!--
  @module MOD-001  ChatInputBar
  @description  豆包 / DeepSeek 风格输入栏：显式 inputMode 状态机（text | voice）。

  v1.13.2 重设计（本轮）：
    引入显式状态 inputMode: 'text' | 'voice'，与 hasText / isRecording / isCancelling / isDisabled 组合，
    状态 → 视图的映射（与需求四条规格一一对应）：

    | inputMode | hasText | isRecording | 输入区                       | 按钮槽 (testid)            |
    |-----------|---------|-------------|------------------------------|----------------------------|
    | text      | false   | -           | textarea + 灰色 placeholder  | mode-toggle-btn 麦克风图标 |
    | text      | true    | -           | textarea 有文字              | send-btn 发送图标          |
    | voice     | -       | false       | 「按住 说话」横条            | mode-toggle-btn 键盘图标   |
    | voice     | -       | true        | 横条高亮「松开 发送 · 上滑取消」| mode-toggle-btn 键盘图标  |

  ============================ CSS 层叠陷阱：本文件的硬性纪律 ============================
  v1.13.1 线上事故复盘：当时用 `.cib-hidden { display:none }`（第 160 行）配合按钮基类
  `.cib-send--active { display:flex }`（第 191+ 行）做互斥显隐。两者都是单类选择器、特异性相同，
  后定义者胜出 → `.cib-hidden` 完全失效 → 麦克风永远不可见、有文字时发送反而不可见。
  微信小程序 WXSS 不支持 :deep，标签选择器对自定义组件不生效，我们也无法保证编译后的规则顺序。

  因此本文件强制执行三条纪律（有静态回归守卫：tests/chat-input-modes.spec.js）：
    D1. 显隐一律由 v-if / v-else 承担，**任何 CSS 规则都不得声明 display: none**。
    D2. 任何带 `--` 的修饰类**一律不得声明 display**；display 只允许出现在布局基类
        （.cib-root / .cib-row / .cib-rec-tip / .cib-btn / .cib-hold / .cib-ico）上。
    D3. 同一个 CSS 属性在同一元素上只允许有一个来源：基类只写布局，修饰类只写配色，
        且每个元素的每一类修饰**由 JS 计算出唯一一个类名**（不叠加 theme + state 两个都改背景的类）。
  =====================================================================================

  图标对比度（v1.13.0 事故：青图标压青渐变底）：每个图标修饰类的描边/填充色都与其所在按钮
  的背景色成对选取，见各规则上方注释。
-->
<template>
  <view :class="['cib-root', isDark ? 'cib-root--dark' : 'cib-root--light']">
    <!-- 录音浮层提示：仅录音中出现 -->
    <view
      v-if="isRecording"
      :class="['cib-rec-tip', isCancelling ? 'cib-rec-tip--cancel' : 'cib-rec-tip--normal']"
      data-testid="rec-tip"
    >
      <text :class="['cib-rec-txt', isCancelling ? 'cib-rec-txt--cancel' : 'cib-rec-txt--normal']">
        {{ isCancelling ? '松开手指，取消发送' : '正在聆听… 上滑取消' }}
      </text>
    </view>

    <view class="cib-row">
      <!-- ===== 输入区：text 模式 = textarea；voice 模式 = 按住说话横条 ===== -->
      <textarea
        v-if="isTextMode"
        :class="['cib-text', isDark ? 'cib-text--dark' : 'cib-text--light']"
        v-model="inputText"
        :placeholder="textPlaceholder"
        :placeholder-class="isDark ? 'cib-ph--dark' : 'cib-ph--light'"
        :focus="textFocus"
        auto-height
        :max-height="200"
        @confirm="handleSend"
      />

      <!-- voice 模式的录音控件，承载既有契约 data-testid="voice-btn" -->
      <view
        v-else
        :class="['cib-hold', holdStateClass]"
        data-testid="voice-btn"
        @touchstart="handleVoiceStart"
        @touchend="handleVoiceEnd"
        @touchmove="handleVoiceMove"
      >
        <text :class="['cib-hold-txt', holdTxtClass]">{{ holdLabel }}</text>
      </view>

      <!-- ===== 按钮槽：send 与 mode-toggle 结构互斥（v-if/v-else），不依赖任何 CSS ===== -->
      <view
        v-if="showSend"
        :class="['cib-btn', sendBtnClass]"
        data-testid="send-btn"
        @tap="handleSend"
      >
        <view :class="['cib-ico', sendIcoClass]" />
      </view>
      <view
        v-else
        :class="['cib-btn', toggleBtnClass]"
        data-testid="mode-toggle-btn"
        @tap="handleToggleMode"
      >
        <view :class="['cib-ico', toggleIcoClass]" />
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { requestPermission } from '@/utils/permission'
import { startRecording, stopAndRecognize } from '@/utils/voice-input'

const props = defineProps({
  wsConnected: { type: Boolean, required: true },
  isStreaming: { type: Boolean, required: true },
  theme: { type: String, default: 'light' },
})
const emit = defineEmits(['send', 'error'])

const inputText = ref('')
// 显式输入模式：本轮核心。不再用「hasText 隐式互斥」推导显隐。
const inputMode = ref('text')
const isRecording = ref(false)
const isCancelling = ref(false)
const textFocus = ref(false)
let _touchStartY = 0

const isDark = computed(() => props.theme === 'dark')
const isTextMode = computed(() => inputMode.value === 'text')
// 断连 / 流式回复中**不禁用 textarea**：用户仍可自由组织语言（豆包 / DeepSeek 行为），
// 仅由 canSend 拦截真正的发送动作，并以 placeholder + 发送钮禁用态给出反馈。
// 若在此处禁用输入框，用户在断连时永远无法产生文字，"有文字 + 断连"状态不可达。
const isVoiceDisabled = computed(() => !props.wsConnected || props.isStreaming)
const hasText = computed(() => inputText.value.trim().length > 0)
const canSend = computed(() => props.wsConnected && !props.isStreaming && hasText.value)

// 规格 2/3：text 模式下有文字 → 发送按钮；否则 → 模式切换按钮。voice 模式恒为切换按钮。
const showSend = computed(() => isTextMode.value && hasText.value)

// ---- 文案 ----
const textPlaceholder = computed(() => {
  if (!props.wsConnected) return '连接已断开，正在重连…'
  if (props.isStreaming) return '副官正在回复…'
  return '向智能方舟副官提问'
})

const holdLabel = computed(() => {
  if (isCancelling.value) return '松开手指，取消发送'
  if (isRecording.value) return '松开 发送 · 上滑取消'
  if (!props.wsConnected) return '连接已断开，暂不可语音'
  if (props.isStreaming) return '副官正在回复…'
  return '按住 说话'
})

// ---- 单一修饰类计算（纪律 D3：每个元素每类属性只有一个修饰类来源）----
const holdStateClass = computed(() => {
  if (isCancelling.value) return 'cib-hold--cancel'
  if (isRecording.value) return 'cib-hold--recording'
  if (isVoiceDisabled.value) return isDark.value ? 'cib-hold--off-dark' : 'cib-hold--off-light'
  return isDark.value ? 'cib-hold--idle-dark' : 'cib-hold--idle-light'
})

const holdTxtClass = computed(() => {
  if (isCancelling.value) return 'cib-hold-txt--cancel'
  if (isRecording.value) return 'cib-hold-txt--recording'
  if (isVoiceDisabled.value) return isDark.value ? 'cib-hold-txt--off-dark' : 'cib-hold-txt--off-light'
  return isDark.value ? 'cib-hold-txt--idle-dark' : 'cib-hold-txt--idle-light'
})

// 类名沿用 v1.12/v1.13 既有命名，便于既有断言与线上样式排查对齐；
// 差异在于这些类**不再声明 display**（display 归 .cib-btn 独有）。
const sendBtnClass = computed(() => {
  if (isDark.value) return canSend.value ? 'cib-send--dark-active' : 'cib-send--dark-disabled'
  return canSend.value ? 'cib-send--active' : 'cib-send--disabled'
})

// v1.13.0 事故修复保留：图标颜色必须随 canSend 变化，否则激活态青图标压在青渐变底上不可见。
const sendIcoClass = computed(() => {
  if (isDark.value) return canSend.value ? 'cib-ico-send--dark-active' : 'cib-ico-send--dark-disabled'
  return canSend.value ? 'cib-ico-send--active' : 'cib-ico-send--disabled'
})

const toggleBtnClass = computed(() => (isDark.value ? 'cib-toggle--dark' : 'cib-toggle--light'))

// 规格 3/4：text 模式显示麦克风（切到语音），voice 模式显示键盘（切回文字）。
const toggleIcoClass = computed(() => {
  if (isTextMode.value) return isDark.value ? 'cib-ico-mic--dark' : 'cib-ico-mic--light'
  return isDark.value ? 'cib-ico-kbd--dark' : 'cib-ico-kbd--light'
})

// ---- 行为 ----
function handleSend() {
  if (!canSend.value) return
  const text = inputText.value.trim()
  if (!text) return
  emit('send', { text, media: [] })
  inputText.value = ''
}

// 规格 4：模式切换。草稿 inputText 在切换过程中**不做任何清理**，往返后仍在。
function handleToggleMode() {
  if (isRecording.value) return // 录音进行中禁止切换，避免录音无对应 stop
  if (isTextMode.value) {
    inputMode.value = 'voice'
    textFocus.value = false
    try { uni && uni.hideKeyboard && uni.hideKeyboard() } catch (_) {}
  } else {
    inputMode.value = 'text'
    isCancelling.value = false
    nextTick(() => { textFocus.value = true })
  }
}

async function handleVoiceStart(e) {
  if (isVoiceDisabled.value) return
  if (isRecording.value) return

  // 必须在 await 之前同步读取 touch 坐标：微信小程序事件对象在异步边界后可能已被回收，
  // 原实现在权限弹窗 await 之后再读 e.touches，真机上拿到空值 → _touchStartY=0 →
  // 上滑取消阈值永远算不出来（v1.13.1 回归修复，阈值 60 保持不变）。
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
  // （v1.13.1 回归修复，不得删除）
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
/* =========================================================================
   纪律 D2：以下是**唯一**允许声明 display 的规则集合（均为不带 `--` 的布局基类）。
   任何修饰类都不得声明 display，全文件不得出现 display:none。
   ========================================================================= */
.cib-root { flex-shrink: 0; }
.cib-row { display: flex; align-items: flex-end; padding: 16rpx 24rpx; gap: 12rpx; }
.cib-rec-tip {
  display: flex; align-items: center; justify-content: center;
  padding: 14rpx 24rpx; margin: 12rpx 24rpx 0; border-radius: 16rpx;
}
.cib-btn {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 64rpx; height: 64rpx; border-radius: 50%;
  transition: background-color 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.cib-hold {
  display: flex; align-items: center; justify-content: center;
  flex: 1; min-height: 64rpx; border-radius: 12rpx; box-sizing: border-box;
  padding: 10rpx 16rpx;
  transition: background-color 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.cib-ico {
  display: block; width: 40rpx; height: 40rpx;
  background-repeat: no-repeat; background-position: center; background-size: contain;
}
/* ===================== 以上为 display 的全部来源 ===================== */

/* ---- 根容器配色（修饰类只写配色）---- */
.cib-root--light { background: #fff; border-top: 1rpx solid #eee; }
.cib-root--dark { background: rgba(8,14,28,0.7); border-top: 1px solid rgba(56,230,224,0.12); }

/* ---- textarea：基类只写布局，修饰类只写配色 ---- */
.cib-text {
  flex: 1; min-height: 44rpx; max-height: 180rpx;
  border-radius: 12rpx; padding: 10rpx 16rpx; font-size: 28rpx;
  line-height: 1.5; box-sizing: border-box;
}
.cib-text--light { background: #f5f5f5; border: 1px solid #e3e5e8; color: #333; }
.cib-text--dark { background: rgba(4,10,22,0.7); border: 1px solid rgba(56,230,224,0.25); color: #eaf6ff; }
/* 规格 1：空输入时的灰色占位提示 */
.cib-ph--light { color: #9aa0a6; font-size: 28rpx; }
.cib-ph--dark { color: #5f7f8c; font-size: 28rpx; }

/* ---- 录音浮层 ---- */
.cib-rec-tip--normal { background: rgba(47,244,224,0.12); border: 1px solid rgba(56,230,224,0.4); }
.cib-rec-tip--cancel { background: rgba(255,77,79,0.16); border: 1px solid rgba(255,77,79,0.55); }
.cib-rec-txt { font-size: 24rpx; letter-spacing: 1rpx; }
.cib-rec-txt--normal { color: #9fe9e0; }
.cib-rec-txt--cancel { color: #ff9a9c; }

/* ---- 「按住 说话」横条：idle / recording / cancel / disabled 四态 × 主题 ----
   每个状态由 JS 计算出**唯一一个**修饰类，互不叠加，故无层叠竞争。 */
.cib-hold--idle-light { background: #f1f3f5; border: 1px solid #dcdfe3; }
.cib-hold--idle-dark { background: rgba(56,230,224,0.10); border: 1px solid rgba(56,230,224,0.45); }
.cib-hold--recording {
  background: linear-gradient(135deg, #22e6da, #3a8bff);
  border: 1px solid rgba(47,244,224,0.9);
  box-shadow: 0 0 20px rgba(47,244,224,0.55);
  animation: cib-pulse 1.2s ease-in-out infinite;
}
.cib-hold--cancel {
  background: #ff4d4f; border: 1px solid rgba(255,77,79,0.9);
  box-shadow: 0 0 20px rgba(255,77,79,0.5);
}
/* 禁用态：不用 opacity（会被误读成「消失」），改用实心灰底 + 虚线边 + 可读灰字 */
.cib-hold--off-light { background: #eceef0; border: 1px dashed #c2c7cd; }
.cib-hold--off-dark { background: rgba(120,140,160,0.14); border: 1px dashed rgba(150,175,190,0.5); }

.cib-hold-txt { font-size: 28rpx; letter-spacing: 2rpx; }
.cib-hold-txt--idle-light { color: #4a5560; }
.cib-hold-txt--idle-dark { color: #9fe9e0; }
.cib-hold-txt--recording { color: #041018; }   /* 深墨字压青蓝渐变亮底 */
.cib-hold-txt--cancel { color: #ffffff; }      /* 白字压 #ff4d4f 红底 */
.cib-hold-txt--off-light { color: #8b939c; }
.cib-hold-txt--off-dark { color: #93a7b4; }

/* ---- 发送按钮配色（不含 display）---- */
.cib-send--active { background: #1a73e8; border: 1px solid #1a73e8; }
/* 禁用但仍渲染：灰底 + 实边 + 深灰图标，明确「不可用」而不是「消失」 */
.cib-send--disabled { background-color: #e6e8eb; border: 1px solid #d3d7dc; }
.cib-send--dark-active {
  background: linear-gradient(135deg, #22e6da, #3a8bff);
  border: 1px solid rgba(47,244,224,0.9);
  box-shadow: 0 0 20px rgba(47,244,224,0.55);
}
.cib-send--dark-disabled {
  background-color: rgba(120,140,160,0.16); border: 1px solid rgba(150,175,190,0.45);
}

/* ---- 模式切换按钮配色 ---- */
.cib-toggle--light { background-color: #f1f3f5; border: 1px solid #dcdfe3; }
.cib-toggle--dark { background-color: rgba(56,230,224,0.14); border: 1px solid rgba(56,230,224,0.45); }

@keyframes cib-pulse {
  0%, 100% { box-shadow: 0 0 16px rgba(47,244,224,0.45); }
  50%      { box-shadow: 0 0 30px rgba(47,244,224,0.85); }
}

/* =========================================================================
   图标：修饰类只写 background-image。每个图标色都与其按钮底色配对做对比度检查。
   ========================================================================= */
/* 白箭头 压 #1a73e8 蓝底 */
.cib-ico-send--active {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23ffffff'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
/* 深灰箭头 压 #e6e8eb 浅灰底 */
.cib-ico-send--disabled {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%236b7280'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
/* 深墨箭头 压 青→蓝渐变亮底（v1.13.0 事故修复：严禁在此用青色 %232ff4e0）*/
.cib-ico-send--dark-active {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23041018'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
/* 浅灰蓝箭头 压 rgba(120,140,160,.16) 暗底 */
.cib-ico-send--dark-disabled {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23aebccb'%3E%3Cpath d='M3 11l18-8-8 18-2-7-8-3z'/%3E%3C/svg%3E");
}
/* 麦克风：深灰描边 压 #f1f3f5 浅底 */
.cib-ico-mic--light {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%234a5560' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
/* 麦克风：青描边 压 rgba(56,230,224,.14) 深底（暗色主题底为 #05070f 系）*/
.cib-ico-mic--dark {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='9' y='3' width='6' height='11' rx='3'/%3E%3Cpath d='M5 11a7 7 0 0 0 14 0'/%3E%3Cpath d='M12 18v3'/%3E%3C/svg%3E");
}
/* 键盘：深灰描边 压 #f1f3f5 浅底 */
.cib-ico-kbd--light {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%234a5560' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='2' y='6' width='20' height='12' rx='2'/%3E%3Cpath d='M6 10h0M10 10h0M14 10h0M18 10h0M8 14h8'/%3E%3C/svg%3E");
}
/* 键盘：青描边 压 rgba(56,230,224,.14) 深底 */
.cib-ico-kbd--dark {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.8' stroke-linecap='round'%3E%3Crect x='2' y='6' width='20' height='12' rx='2'/%3E%3Cpath d='M6 10h0M10 10h0M14 10h0M18 10h0M8 14h8'/%3E%3C/svg%3E");
}
</style>
