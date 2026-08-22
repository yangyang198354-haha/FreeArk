<!--
  @module MOD-PAGE-PERSONA
  @description 副官人格设置（v1.13.0，舰长休息室 → 副官人格）。

    对话里也能改（"以后叫我胖子熊大人"），本页是确定性入口，补两个短板：
      1. 可发现性——没人会主动猜到副官可以改口，设置项摆出来就是功能说明；
      2. 抽取器边界——模糊表达（"能不能别这么客气"）多半被判 none，这里零歧义。
    另外对话里的"恢复默认"是三个字段一起清，本页支持只清语气、保留称呼。

    接口：GET /api/miniapp/persona/ → {identity, address, tone}
          PUT /api/miniapp/persona/update/
            键非空=设置 / 键为空串=清空该字段 / 键缺席=保留 / reset=true=整体恢复默认
    键语义：identity=副官自称 / address=如何称呼用户 / tone=语气
            （v1.12.0 的 greeting_style/tone_style 语义混淆已废，详见后端 api/persona.py）

    保存后同步 chatStore.persona 并标记聊天需重连——当前 WS 连接持有的是
    connect 时读的 persona 快照，不重连的话副官页开场问候语还是旧称呼。
-->
<template>
  <view class="pa-page">
    <!-- 背景装饰 -->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="bg-blob" />

    <!-- 状态栏占位 -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- header -->
    <view class="header">
      <view class="back-btn ico-back" @tap="goBack" />
      <text class="header-title">副官人格</text>
    </view>

    <!-- body -->
    <scroll-view scroll-y class="body">
      <view class="card form-card">
        <view class="corner tl" /><view class="corner tr" />
        <view class="corner bl" /><view class="corner br" />

        <view class="field">
          <text class="label">副官的自称</text>
          <view class="input-wrap">
            <input
              class="input"
              v-model="identity"
              :placeholder="DEFAULT_IDENTITY"
              placeholder-class="ph"
              maxlength="50"
            />
          </view>
          <text class="hint">它怎么称呼自己</text>
        </view>

        <view class="field">
          <text class="label">对我的称呼</text>
          <view class="input-wrap">
            <input
              class="input"
              v-model="address"
              :placeholder="DEFAULT_ADDRESS"
              placeholder-class="ph"
              maxlength="50"
            />
          </view>
          <text class="hint">它怎么称呼你</text>
        </view>

        <view class="field">
          <text class="label">说话语气</text>
          <view class="input-wrap">
            <input
              class="input"
              v-model="tone"
              placeholder="留空即可，例：简洁 / 轻松 / 正式"
              placeholder-class="ph"
              maxlength="50"
            />
          </view>
          <text class="hint">可留空</text>
        </view>

        <!-- 实时预览：与聊天页 personaGreeting 同一拼法 -->
        <view class="preview">
          <text class="preview-label">PREVIEW · 开场问候</text>
          <text class="preview-text">{{ previewText }}</text>
        </view>

        <view v-if="errorMsg" class="err-banner">
          <view class="err-dot" />
          <text>{{ errorMsg }}</text>
        </view>

        <view
          class="submit-btn"
          :class="{ 'btn-disabled': loading }"
          @tap="submit"
        >
          <text>{{ loading ? '保存中…' : '保存' }}</text>
        </view>

        <view
          class="reset-btn"
          :class="{ 'btn-disabled': loading }"
          @tap="onReset"
        >
          <text>恢复默认人格</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useChatStore } from '@/store/chat'
import { api } from '@/utils/api'

const DEFAULT_IDENTITY = '智能方舟的副官'
const DEFAULT_ADDRESS = '尊敬的舰长大人'

const authStore = useAuthStore()
const chatStore = useChatStore()

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

const identity = ref('')
const address = ref('')
const tone = ref('')
const loading = ref(false)
const errorMsg = ref('')

// 与 chat/index.vue 的 personaGreeting 保持同一拼法，所见即所得
const previewText = computed(() => {
  const i = identity.value.trim() || DEFAULT_IDENTITY
  const a = address.value.trim() || DEFAULT_ADDRESS
  return `${a}，我是${i}。可以帮您控制设备、排查故障，也能解答空调与新风知识。`
})

function applyToLocal(p) {
  identity.value = p?.identity || ''
  address.value = p?.address || ''
  tone.value = p?.tone || ''
  // 同步全局：新会话的开场问候语依赖它
  chatStore.setPersona(p && (p.identity || p.address || p.tone) ? p : null)
  // 当前 WS 连接持的是 connect 时的 persona 快照，需重连才会生效
  chatStore.markPersonaStale()
}

onLoad(async () => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  try {
    const p = await api.getPersona()
    identity.value = p?.identity || ''
    address.value = p?.address || ''
    tone.value = p?.tone || ''
  } catch (e) {
    errorMsg.value = '读取人格设置失败，请稍后重试'
  }
})

async function submit() {
  if (loading.value) return
  errorMsg.value = ''
  loading.value = true
  try {
    // 三个字段全量提交：空串表示清空该字段（后端语义见接口文档）
    const p = await api.updatePersona({
      identity: identity.value.trim(),
      address: address.value.trim(),
      tone: tone.value.trim(),
    })
    applyToLocal(p)
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 900)
  } catch (e) {
    errorMsg.value = e?.message || '保存失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function onReset() {
  if (loading.value) return
  uni.showModal({
    title: '恢复默认人格',
    content: `将恢复为「${DEFAULT_IDENTITY}」，并称呼你为「${DEFAULT_ADDRESS}」。`,
    success: async (res) => {
      if (!res.confirm) return
      loading.value = true
      errorMsg.value = ''
      try {
        const p = await api.updatePersona({ reset: true })
        applyToLocal(p)
        uni.showToast({ title: '已恢复默认', icon: 'success' })
      } catch (e) {
        errorMsg.value = e?.message || '恢复失败，请稍后重试'
      } finally {
        loading.value = false
      }
    },
  })
}

function goBack() {
  uni.navigateBack()
}
</script>

<style scoped>
.pa-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070f;
  overflow: hidden;
}

/* ── 背景装饰 ──────────────────────────── */
.bg-base, .bg-grid, .bg-blob { position: absolute; pointer-events: none; }
.bg-base {
  inset: 0;
  background:
    radial-gradient(90% 45% at 18% 0%, rgba(101,55,180,0.28), transparent 55%),
    radial-gradient(80% 40% at 100% 4%, rgba(20,180,170,0.20), transparent 55%),
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
  width: 400rpx; height: 400rpx; right: -120rpx; top: 600rpx; border-radius: 50%;
  background: radial-gradient(circle, rgba(139,92,246,0.20), transparent 70%);
  filter: blur(8px);
  animation: ark-float 16s ease-in-out infinite;
}
@keyframes ark-float { 0%,100% { transform: translate(0,0); } 50% { transform: translate(20rpx,-24rpx); } }

.status-spacer { position: relative; z-index: 5; flex: 0 0 auto; }

/* ── header ─────────────────────────────── */
.header {
  position: relative; z-index: 5; flex: 0 0 auto;
  height: 92rpx; display: flex; align-items: center; justify-content: center;
}
.back-btn {
  position: absolute; left: 24rpx;
  width: 44rpx; height: 44rpx;
  background-repeat: no-repeat; background-position: center; background-size: 44rpx 44rpx;
}
.header-title {
  font-size: 34rpx; font-weight: 700; letter-spacing: 8rpx; color: #f4fbff;
  text-shadow: 0 0 12px rgba(56,230,224,0.5);
}

/* ── body ───────────────────────────────── */
.body { position: relative; z-index: 4; flex: 1 1 auto; padding: 20rpx 36rpx 40rpx; }

/* ── card ───────────────────────────────── */
.card {
  position: relative; border-radius: 32rpx;
  border: 1px solid rgba(56,230,224,0.18);
}
.form-card {
  padding: 48rpx 36rpx;
  background: linear-gradient(180deg, rgba(14,22,42,0.75), rgba(8,14,28,0.8));
  box-shadow: inset 0 0 26px rgba(20,40,80,0.35);
}
.corner { position: absolute; width: 44rpx; height: 44rpx; }
.corner.tl { left: -1px; top: -1px; border-left: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.corner.tr { right: -1px; top: -1px; border-right: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.corner.bl { left: -1px; bottom: -1px; border-left: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.corner.br { right: -1px; bottom: -1px; border-right: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 8rpx 0; }

/* ── field ──────────────────────────────── */
.field { margin-bottom: 32rpx; }
.label {
  display: block; font-size: 24rpx; letter-spacing: 2rpx;
  color: rgba(143,217,255,0.7); margin-bottom: 14rpx;
}
.input-wrap {
  display: flex; align-items: center;
  height: 92rpx; border-radius: 16rpx;
  border: 1px solid rgba(56,230,224,0.25);
  background: rgba(5,10,22,0.7);
  transition: border-color 0.2s;
}
.input-wrap:focus-within {
  border-color: rgba(47,244,224,0.6);
  box-shadow: 0 0 16rpx rgba(47,244,224,0.12);
}
.input {
  flex: 1; height: 100%; padding: 0 28rpx;
  font-size: 28rpx; color: #eaf6ff;
}
.ph { color: rgba(143,217,255,0.35); }
.hint {
  display: block; margin-top: 10rpx; padding-left: 4rpx;
  font-size: 22rpx; color: rgba(143,217,255,0.4);
}

/* ── preview ────────────────────────────── */
.preview {
  margin: 8rpx 0 32rpx;
  padding: 24rpx 26rpx;
  border-radius: 16rpx;
  background: rgba(47,244,224,0.05);
  border: 1px solid rgba(56,230,224,0.16);
}
.preview-label {
  display: block; font-size: 20rpx; letter-spacing: 3rpx;
  color: rgba(47,244,224,0.6); margin-bottom: 12rpx;
}
.preview-text {
  display: block; font-size: 26rpx; line-height: 1.6; color: #dbeeff;
}

/* ── error ──────────────────────────────── */
.err-banner {
  display: flex; align-items: center; gap: 14rpx;
  padding: 18rpx 22rpx; margin-bottom: 24rpx;
  border-radius: 12rpx;
  background: rgba(255,49,93,0.08);
  border: 1px solid rgba(255,49,93,0.3);
}
.err-dot {
  flex: 0 0 auto; width: 12rpx; height: 12rpx;
  background: #ff315d; border-radius: 50%;
  box-shadow: 0 0 10rpx rgba(255,49,93,0.6);
}
.err-banner text { font-size: 24rpx; color: #ff6b8b; }

/* ── buttons ────────────────────────────── */
.submit-btn {
  display: flex; align-items: center; justify-content: center;
  height: 100rpx; border-radius: 50rpx;
  background: linear-gradient(90deg, #2ff4e0, #7c3aed);
  box-shadow: 0 0 24rpx rgba(47,244,224,0.3);
  margin-top: 8rpx;
}
.submit-btn text {
  font-size: 30rpx; font-weight: 700; color: #04121f; letter-spacing: 4rpx;
}
.reset-btn {
  display: flex; align-items: center; justify-content: center;
  height: 88rpx; border-radius: 50rpx;
  margin-top: 20rpx;
  border: 1px solid rgba(143,217,255,0.25);
  background: rgba(14,22,42,0.5);
}
.reset-btn text {
  font-size: 27rpx; color: rgba(143,217,255,0.75); letter-spacing: 2rpx;
}
.btn-disabled { opacity: 0.45; box-shadow: none; }

/* ── 图标 ───────────────────────────────── */
.ico-back {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23eaf6ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 5l-7 7 7 7'/%3E%3C/svg%3E");
}
</style>
