<!--
  @module MOD-PAGE-PROFILE-SETUP
  @description 微信登录后首次设置头像和昵称（v1.12.0）。
    赛博朋克 HUD 视觉风格，与登录页/个人中心一致。
    通过 chooseAvatar + type="nickname" 获取头像和昵称。
    mode=initial: 微信登录后跳转，保存后 reLaunch 首页。
    mode=edit: 个人中心编辑入口跳转，保存后 navigateBack。
  视觉规格:
    深空底 #05070f + 青色主题 #2ff4e0 + 霓虹边框 + HUD 角标。
    字体：Noto Sans SC 为主，无远程加载（补偿字间距维持科技感）。
-->
<template>
  <view class="setup-page">
    <!-- 背景装饰 -->
    <view class="bg-base"></view>
    <view class="bg-grid"></view>
    <view class="bg-blob"></view>

    <!-- 状态栏占位（custom 导航） -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer"></view>

    <!-- header -->
    <view class="header">
      <text v-if="pageMode === 'edit'" class="back-btn" @tap="goBack">‹ 返回</text>
      <view class="header-spacer" v-else></view>
      <text class="header-title">完善资料</text>
      <text v-if="pageMode === 'initial'" class="skip-btn" @tap="goSkip">跳过 ›</text>
      <view class="header-spacer" v-else></view>
    </view>

    <scroll-view scroll-y class="body" :style="{ paddingBottom: safeBottom + 'px' }">
      <!-- 说明文字 -->
      <view class="desc">
        <text class="desc-title">设置你的个人资料</text>
        <text class="desc-sub">头像和昵称将在个人中心展示</text>
      </view>

      <!-- 头像选择区 -->
      <view class="card avatar-card">
        <view class="corner tl"></view><view class="corner tr"></view>
        <view class="corner bl"></view><view class="corner br"></view>
        <button
          class="avatar-btn"
          open-type="chooseAvatar"
          @chooseavatar="onChooseAvatar"
        >
          <view v-if="localAvatarUrl" class="avatar-preview">
            <image :src="localAvatarUrl" class="avatar-img" mode="aspectFill" />
          </view>
          <view v-else class="avatar-placeholder">
            <text class="avatar-plus">＋</text>
            <text class="avatar-label">选择头像</text>
          </view>
        </button>
      </view>

      <!-- 昵称输入区 -->
      <view class="card nickname-card">
        <view class="field-label"><text class="gt">&gt;</text>昵称</view>
        <view class="field">
          <input
            class="field-input"
            type="nickname"
            v-model="nicknameValue"
            placeholder="请输入昵称"
            placeholder-class="field-ph"
            :disabled="saving"
          />
        </view>
      </view>

      <!-- 保存按钮 -->
      <button class="save-btn" :disabled="saving" @tap="onSave">
        <view v-if="saving" class="btn-loading">
          <view class="spinner"></view>
          <text class="btn-loading-txt">保存中</text>
        </view>
        <text v-else class="btn-txt">保 存</text>
      </button>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20
const safeBottom = sysInfo.safeAreaInsets
  ? (sysInfo.safeAreaInsets.bottom || 0)
  : 0

const pageMode = ref('initial')    // 'initial' | 'edit'
const localAvatarUrl = ref(null)   // 临时文件路径
const nicknameValue = ref('')      // 昵称
const saving = ref(false)

onLoad((options) => {
  if (options && options.mode === 'edit') {
    pageMode.value = 'edit'
  }
  // 编辑模式下预填当前值
  if (pageMode.value === 'edit') {
    if (authStore.nickname) {
      nicknameValue.value = authStore.nickname
    }
  }
})

function onChooseAvatar(e) {
  const url = e.detail && e.detail.avatarUrl
  if (url) {
    localAvatarUrl.value = url
  }
}

async function onSave() {
  if (saving.value) return
  saving.value = true

  try {
    const filePath = localAvatarUrl.value || null
    const nickname = nicknameValue.value.trim() || null

    if (!filePath && !nickname) {
      uni.showToast({ title: '请设置头像或昵称', icon: 'none' })
      saving.value = false
      return
    }

    const result = await api.uploadProfile(nickname, filePath)

    // 更新 auth store
    const updatedInfo = {
      ...authStore.userInfo,
      avatar_url: result.avatar_url || authStore.userInfo?.avatar_url,
      nickname: result.nickname || nickname,
    }
    authStore.login(authStore.token, updatedInfo)

    uni.showToast({ title: '资料已保存', icon: 'success', duration: 1500 })

    setTimeout(() => {
      if (pageMode.value === 'initial') {
        uni.reLaunch({ url: '/pages/home/index' })
      } else {
        uni.navigateBack()
      }
    }, 600)
  } catch (err) {
    const msg = err.message || '保存失败，请重试'
    uni.showToast({ title: msg, icon: 'none', duration: 2000 })
  } finally {
    saving.value = false
  }
}

function goBack() {
  uni.navigateBack()
}

function goSkip() {
  uni.reLaunch({ url: '/pages/home/index' })
}
</script>

<style scoped>
.setup-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070f;
  overflow: hidden;
  font-family: 'Noto Sans SC', -apple-system, sans-serif;
}

/* ── 背景（与登录页一致）───────────────────── */
.bg-base, .bg-grid, .bg-blob { position: absolute; pointer-events: none; }
.bg-base {
  inset: 0; z-index: 0;
  background:
    radial-gradient(90% 45% at 18% 0%, rgba(101,55,180,0.32), transparent 55%),
    radial-gradient(80% 40% at 100% 4%, rgba(20,180,170,0.22), transparent 55%),
    linear-gradient(180deg, #0b0a1a, #07101c 60%, #050811);
}
.bg-grid {
  inset: 0; z-index: 0;
  background-image:
    linear-gradient(rgba(56,230,224,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,230,224,0.06) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 55%);
  mask-image: linear-gradient(180deg, #000, transparent 55%);
}
.bg-blob {
  width: 400rpx; height: 400rpx; left: -120rpx; top: 180rpx; border-radius: 50%; z-index: 0;
  background: radial-gradient(circle, rgba(139,92,246,0.22), transparent 70%);
  filter: blur(8px);
}

/* ── header ────────────────────────────────── */
.status-spacer { position: relative; z-index: 5; flex: 0 0 auto; }
.header {
  position: relative; z-index: 5; flex: 0 0 auto;
  height: 92rpx; display: flex; align-items: center; justify-content: space-between;
  padding: 0 36rpx;
}
.header-title {
  font-size: 34rpx; font-weight: 700; letter-spacing: 8rpx; color: #f4fbff;
  text-shadow: 0 0 12px rgba(56,230,224,0.5);
}
.back-btn, .skip-btn {
  font-size: 28rpx; color: #2ff4e0; letter-spacing: 2rpx;
}
.skip-btn { color: rgba(143,217,255,0.6); }
.header-spacer { width: 120rpx; }

/* ── body ──────────────────────────────────── */
.body { position: relative; z-index: 4; flex: 1 1 auto; padding: 20rpx 36rpx; }

/* ── 说明 ──────────────────────────────────── */
.desc { display: flex; flex-direction: column; align-items: center; margin: 40rpx 0 32rpx; }
.desc-title {
  font-size: 30rpx; font-weight: 700; letter-spacing: 4rpx; color: #f4fbff;
  text-shadow: 0 0 16px rgba(56,230,224,0.4);
}
.desc-sub { font-size: 24rpx; color: rgba(143,217,255,0.55); margin-top: 12rpx; }

/* ── 卡片 ──────────────────────────────────── */
.card {
  position: relative; border-radius: 28rpx;
  background: linear-gradient(180deg, rgba(14,22,42,0.72), rgba(8,14,28,0.78));
  border: 1rpx solid rgba(56,230,224,0.18);
  box-shadow: inset 0 0 60rpx rgba(20,40,80,0.4);
}
.corner { position: absolute; width: 44rpx; height: 44rpx; }
.corner.tl { left: -1rpx; top: -1rpx; border-left: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.corner.tr { right: -1rpx; top: -1rpx; border-right: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.corner.bl { left: -1rpx; bottom: -1rpx; border-left: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.corner.br { right: -1rpx; bottom: -1rpx; border-right: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 8rpx 0; }

.avatar-card { padding: 44rpx; display: flex; justify-content: center; margin-bottom: 32rpx; }
.nickname-card { padding: 36rpx 40rpx 40rpx; margin-bottom: 40rpx; }

/* ── 头像选择 ──────────────────────────────── */
.avatar-btn {
  padding: 0; margin: 0; border: none; background: transparent;
  width: 192rpx; height: 192rpx; line-height: normal;
  display: flex; align-items: center; justify-content: center;
}
.avatar-btn::after { border: none; }
.avatar-placeholder {
  width: 192rpx; height: 192rpx; border-radius: 50%;
  border: 2rpx dashed rgba(56,230,224,0.5);
  background: rgba(47,244,224,0.06);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.avatar-plus { font-size: 56rpx; color: #2ff4e0; font-weight: 300; }
.avatar-label { font-size: 22rpx; color: rgba(143,217,255,0.6); margin-top: 8rpx; }
.avatar-preview { width: 192rpx; height: 192rpx; border-radius: 50%; overflow: hidden; border: 2rpx solid rgba(56,230,224,0.6); }
.avatar-img { width: 100%; height: 100%; }

/* ── 昵称输入 ──────────────────────────────── */
.field-label { display: flex; align-items: center; font-weight: 700; font-size: 26rpx; letter-spacing: 4rpx; color: #8fd9ff; margin-bottom: 16rpx; }
.gt { color: #2ff4e0; margin-right: 12rpx; }
.field {
  position: relative; border-radius: 20rpx;
  background: rgba(4,10,22,0.7);
  border: 1rpx solid rgba(56,230,224,0.28);
}
.field-input {
  width: 100%; height: 100rpx; padding: 0 32rpx; box-sizing: border-box;
  color: #eaf6ff; font-size: 30rpx; background: transparent;
}
.field-ph { color: rgba(143,217,255,0.4); }

/* ── 保存按钮 ──────────────────────────────── */
.save-btn {
  position: relative; overflow: hidden;
  width: 100%; height: 112rpx; margin-top: 0; padding: 0;
  border: none; border-radius: 60rpx;
  background: linear-gradient(95deg, #22e6da 0%, #3a8bff 48%, #8b5cf6 100%);
  box-shadow: 0 0 52rpx rgba(47,244,224,0.45), 0 0 88rpx rgba(139,92,246,0.3);
  display: flex; align-items: center; justify-content: center;
}
.save-btn::after { border: none; }
.btn-txt {
  font-weight: 700; font-size: 36rpx; letter-spacing: 16rpx; color: #04121f;
}
.btn-loading { display: flex; align-items: center; }
.btn-loading-txt { font-weight: 700; font-size: 32rpx; letter-spacing: 4rpx; color: #04121f; margin-left: 16rpx; }
.spinner {
  width: 32rpx; height: 32rpx; border-radius: 50%;
  border: 4rpx solid rgba(4,18,31,0.3); border-top-color: #04121f;
  animation: ark-spin 0.7s linear infinite;
}
@keyframes ark-spin { to { transform: rotate(360deg); } }
</style>
