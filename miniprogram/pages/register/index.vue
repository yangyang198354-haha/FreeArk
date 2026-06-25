<!--
  @module MOD-PAGE-REGISTER
  @description 业主注册页（v1.8.0，REQ-AUTH-001）。
    - 账号密码注册，复用 web 注册逻辑（后端 UserRegistrationSerializer，role 强制 user）
    - 调用 api.miniappRegister({username,password,password2,email}) → POST /api/miniapp/auth/register/
    - 成功(201)直接保存 token+user 并进入首页（注册即登录）
    - 字段校验：用户名/密码非空，两次密码一致；后端 400 错误体回显
-->
<template>
  <view class="register-page">
    <view class="logo-area">
      <text class="logo-title">注册账号</text>
      <text class="logo-subtitle">FreeArk 业主端</text>
    </view>

    <view class="form-area">
      <view class="input-group">
        <text class="input-label">账号</text>
        <input class="input-field" type="text" v-model="username" placeholder="请设置账号" placeholder-class="input-placeholder" :disabled="loading" />
      </view>
      <view class="input-group">
        <text class="input-label">邮箱（选填）</text>
        <input class="input-field" type="text" v-model="email" placeholder="请输入邮箱" placeholder-class="input-placeholder" :disabled="loading" />
      </view>
      <view class="input-group">
        <text class="input-label">密码</text>
        <input class="input-field" type="password" v-model="password" placeholder="请设置密码" placeholder-class="input-placeholder" :disabled="loading" />
      </view>
      <view class="input-group">
        <text class="input-label">确认密码</text>
        <input class="input-field" type="password" v-model="password2" placeholder="请再次输入密码" placeholder-class="input-placeholder" :disabled="loading" />
      </view>

      <button class="primary-btn" :loading="loading" :disabled="loading" @tap="handleRegister">
        {{ loading ? '注册中…' : '注册并登录' }}
      </button>
      <view class="back-link" @tap="goBack"><text>已有账号？返回登录</text></view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const username = ref('')
const email = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)

async function handleRegister() {
  if (!username.value.trim()) {
    uni.showToast({ title: '请输入账号', icon: 'none' })
    return
  }
  if (!password.value || !password2.value) {
    uni.showToast({ title: '请输入密码', icon: 'none' })
    return
  }
  if (password.value !== password2.value) {
    uni.showToast({ title: '两次密码不一致', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const payload = {
      username: username.value.trim(),
      password: password.value,
      password2: password2.value,
    }
    if (email.value.trim()) payload.email = email.value.trim()
    const res = await api.miniappRegister(payload)
    if (res && res.token) {
      // 注册即登录：保存 token + user（role 后端强制 user）
      authStore.login(res.token, res.user)
      uni.reLaunch({ url: '/pages/home/index' })
    } else {
      throw new Error('注册失败')
    }
  } catch (err) {
    // 后端 400 返回字段级错误（如 {username:["已存在"]}），http.js 只透传 HTTP 状态，
    // 这里给出通用提示（用户名占用是最常见原因）。
    const msg = err.message && err.message.includes('HTTP 400')
      ? '注册失败：账号可能已被占用或密码过弱'
      : '注册失败，请检查网络'
    uni.showToast({ title: msg, icon: 'none', duration: 2500 })
  } finally {
    loading.value = false
  }
}

function goBack() {
  uni.navigateBack({ fail: () => uni.reLaunch({ url: '/pages/login/index' }) })
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60rpx 48rpx;
}
.logo-area { text-align: center; margin-bottom: 60rpx; }
.logo-title { display: block; font-size: 60rpx; font-weight: bold; color: #fff; letter-spacing: 4rpx; }
.logo-subtitle { display: block; font-size: 28rpx; color: rgba(255,255,255,0.8); margin-top: 12rpx; }
.form-area { width: 100%; background: #fff; border-radius: 24rpx; padding: 48rpx; box-shadow: 0 8rpx 32rpx rgba(0,0,0,0.15); }
.input-group { margin-bottom: 28rpx; }
.input-label { display: block; font-size: 26rpx; color: #555; margin-bottom: 10rpx; }
.input-field { width: 100%; height: 88rpx; border: 2rpx solid #e0e0e0; border-radius: 12rpx; padding: 0 24rpx; font-size: 28rpx; background: #fafafa; }
.input-placeholder { color: #bbb; }
.primary-btn { width: 100%; height: 96rpx; background: #1a73e8; color: #fff; font-size: 32rpx; font-weight: bold; border-radius: 48rpx; border: none; margin-top: 16rpx; line-height: 96rpx; }
.primary-btn[disabled] { opacity: 0.6; }
.back-link { text-align: center; margin-top: 28rpx; font-size: 26rpx; color: #1a73e8; }
</style>
