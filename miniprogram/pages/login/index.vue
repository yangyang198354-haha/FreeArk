<!--
  @module MOD-PAGE-LOGIN
  @author sub_agent_software_developer
  @description Login page (US-01).
    - Calls POST /api/auth/login/ via api.login()
    - Reads res.token and res.user (NOT res.user_info)
    - Saves userInfo including role via authStore.login()
    - Redirects to home on success; shows toast on 401/network error
    - If already logged in, redirects immediately to home
-->
<template>
  <view class="login-page">
    <view class="logo-area">
      <text class="logo-title">FreeArk</text>
      <text class="logo-subtitle">三恒系统移动端</text>
    </view>

    <view class="form-area">
      <view class="input-group">
        <text class="input-label">账号</text>
        <input
          class="input-field"
          type="text"
          v-model="username"
          placeholder="请输入账号"
          placeholder-class="input-placeholder"
          :disabled="loading"
        />
      </view>

      <view class="input-group">
        <text class="input-label">密码</text>
        <input
          class="input-field"
          type="password"
          v-model="password"
          placeholder="请输入密码"
          placeholder-class="input-placeholder"
          :disabled="loading"
        />
      </view>

      <button
        class="login-btn"
        :loading="loading"
        :disabled="loading"
        @tap="handleLogin"
      >
        {{ loading ? '登录中…' : '登录' }}
      </button>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)

// Auth guard: if already logged in skip login page
if (authStore.isLoggedIn) {
  uni.reLaunch({ url: '/pages/home/index' })
}

async function handleLogin() {
  if (!username.value.trim() || !password.value) {
    uni.showToast({ title: '请输入账号和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const res = await api.login({
      username: username.value.trim(),
      password: password.value,
      remember_me: true,
    })
    if (res.success && res.token) {
      // Backend returns res.user (NOT res.user_info) — contains id, username, email, role, first_name, last_name
      authStore.login(res.token, res.user)
      uni.reLaunch({ url: '/pages/home/index' })
    } else {
      throw new Error('登录失败')
    }
  } catch (err) {
    password.value = ''
    const msg =
      err.message.includes('SESSION_EXPIRED') ? '账号或密码错误' :
      err.message.includes('401') ? '账号或密码错误' :
      err.message.includes('HTTP 400') ? '账号或密码错误' :
      '登录失败，请检查网络'
    uni.showToast({ title: msg, icon: 'none', duration: 2000 })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60rpx 48rpx;
}
.logo-area {
  text-align: center;
  margin-bottom: 80rpx;
}
.logo-title {
  display: block;
  font-size: 72rpx;
  font-weight: bold;
  color: #fff;
  letter-spacing: 4rpx;
}
.logo-subtitle {
  display: block;
  font-size: 28rpx;
  color: rgba(255,255,255,0.8);
  margin-top: 12rpx;
}
.form-area {
  width: 100%;
  background: #fff;
  border-radius: 24rpx;
  padding: 48rpx;
  box-shadow: 0 8rpx 32rpx rgba(0,0,0,0.15);
}
.input-group {
  margin-bottom: 32rpx;
}
.input-label {
  display: block;
  font-size: 26rpx;
  color: #555;
  margin-bottom: 10rpx;
}
.input-field {
  width: 100%;
  height: 88rpx;
  border: 2rpx solid #e0e0e0;
  border-radius: 12rpx;
  padding: 0 24rpx;
  font-size: 28rpx;
  background: #fafafa;
}
.input-placeholder {
  color: #bbb;
}
.login-btn {
  width: 100%;
  height: 96rpx;
  background: #1a73e8;
  color: #fff;
  font-size: 32rpx;
  font-weight: bold;
  border-radius: 48rpx;
  border: none;
  margin-top: 16rpx;
  line-height: 96rpx;
}
.login-btn[disabled] {
  opacity: 0.6;
}
</style>
