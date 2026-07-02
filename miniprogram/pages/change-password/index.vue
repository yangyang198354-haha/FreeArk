<!--
  @module MOD-PAGE-CHANGE-PASSWORD
  @description 修改密码。对齐 Web ChangePasswordView：
    POST /api/change-password/ {current_password,new_password} → {success}
    校验：新密码==确认；长度≥8；须含字母+数字+特殊字符。成功后返回。
    暗色赛博朋克主题，与整体小程序风格一致。
-->
<template>
  <view class="cp-page">
    <!-- 背景装饰 -->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="bg-blob" />

    <!-- 状态栏占位 -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- header -->
    <view class="header">
      <view class="back-btn ico-back" @tap="goBack" />
      <text class="header-title">修改密码</text>
    </view>

    <!-- body -->
    <scroll-view scroll-y class="body">
      <view class="card form-card">
        <view class="corner tl" /><view class="corner tr" />
        <view class="corner bl" /><view class="corner br" />

        <view class="field">
          <text class="label">当前密码</text>
          <view class="input-wrap">
            <input
              class="input"
              type="password"
              v-model="currentPassword"
              placeholder="请输入当前密码"
              placeholder-class="ph"
              :password="!showCurrent"
            />
            <view class="eye-btn" :class="{ on: showCurrent }" @tap="showCurrent = !showCurrent">
              <view class="ico-eye" />
            </view>
          </view>
        </view>

        <view class="field">
          <text class="label">新密码</text>
          <view class="input-wrap">
            <input
              class="input"
              type="password"
              v-model="newPassword"
              placeholder="至少8位，含字母/数字/特殊字符"
              placeholder-class="ph"
              :password="!showNew"
            />
            <view class="eye-btn" :class="{ on: showNew }" @tap="showNew = !showNew">
              <view class="ico-eye" />
            </view>
          </view>
        </view>

        <view class="field">
          <text class="label">确认新密码</text>
          <view class="input-wrap">
            <input
              class="input"
              type="password"
              v-model="confirmPassword"
              placeholder="再次输入新密码"
              placeholder-class="ph"
              :password="!showConfirm"
            />
            <view class="eye-btn" :class="{ on: showConfirm }" @tap="showConfirm = !showConfirm">
              <view class="ico-eye" />
            </view>
          </view>
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
          <text>{{ loading ? '提交中…' : '确认修改' }}</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMsg = ref('')
const showCurrent = ref(false)
const showNew = ref(false)
const showConfirm = ref(false)

// 与 Web 一致：≥8 位且含字母+数字+特殊字符
const PWD_RE = /^(?=.*[a-zA-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/

async function submit() {
  errorMsg.value = ''
  if (!currentPassword.value || !newPassword.value) { errorMsg.value = '请填写完整'; return }
  if (newPassword.value !== confirmPassword.value) { errorMsg.value = '新密码和确认新密码不一致'; return }
  if (newPassword.value.length < 8) { errorMsg.value = '新密码必须至少 8 位'; return }
  if (!PWD_RE.test(newPassword.value)) { errorMsg.value = '新密码必须包含字母、数字和特殊字符'; return }

  loading.value = true
  try {
    const res = await api.changePassword({ current_password: currentPassword.value, new_password: newPassword.value })
    if (res && res.success) {
      uni.showToast({ title: '密码修改成功', icon: 'success' })
      setTimeout(() => uni.navigateBack(), 1200)
    } else {
      errorMsg.value = '密码修改失败'
    }
  } catch (e) {
    errorMsg.value = '修改失败，请检查当前密码是否正确'
  } finally {
    loading.value = false
  }
}

function goBack() {
  uni.navigateBack()
}

if (!authStore.isLoggedIn) uni.reLaunch({ url: '/pages/login/index' })
</script>

<style scoped>
.cp-page {
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
.body { position: relative; z-index: 4; flex: 1 1 auto; padding: 20rpx 36rpx; }

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
.eye-btn {
  flex: 0 0 auto; width: 72rpx; height: 100%;
  display: flex; align-items: center; justify-content: center;
  opacity: 0.4; transition: opacity 0.2s;
}
.eye-btn.on { opacity: 0.85; }
.ico-eye {
  width: 36rpx; height: 36rpx;
  background-repeat: no-repeat; background-position: center; background-size: 36rpx 36rpx;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3C/svg%3E");
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
.err-banner text {
  font-size: 24rpx; color: #ff6b8b;
}

/* ── submit btn ─────────────────────────── */
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
.submit-btn.btn-disabled {
  opacity: 0.45; box-shadow: none;
}

/* ── 图标 ───────────────────────────────── */
.ico-back {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23eaf6ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 5l-7 7 7 7'/%3E%3C/svg%3E");
}
</style>