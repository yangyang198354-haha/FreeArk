<!--
  @module MOD-PAGE-CHANGE-PASSWORD
  @description 修改密码。对齐 Web ChangePasswordView：
    POST /api/change-password/ {current_password,new_password} → {success}
    校验：新密码==确认；长度≥8；须含字母+数字+特殊字符。成功后返回。
-->
<template>
  <view class="cp-page">
    <view class="form-card">
      <view class="field">
        <text class="label">当前密码</text>
        <input class="input" type="password" v-model="currentPassword" placeholder="请输入当前密码" placeholder-class="ph" />
      </view>
      <view class="field">
        <text class="label">新密码</text>
        <input class="input" type="password" v-model="newPassword" placeholder="至少8位，含字母/数字/特殊字符" placeholder-class="ph" />
      </view>
      <view class="field">
        <text class="label">确认新密码</text>
        <input class="input" type="password" v-model="confirmPassword" placeholder="再次输入新密码" placeholder-class="ph" />
      </view>

      <text v-if="errorMsg" class="err">{{ errorMsg }}</text>

      <button class="submit-btn" :loading="loading" :disabled="loading" @tap="submit">
        {{ loading ? '提交中…' : '确认修改' }}
      </button>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMsg = ref('')

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

if (!authStore.isLoggedIn) uni.reLaunch({ url: '/pages/login/index' })
</script>

<style scoped>
.cp-page { min-height: 100vh; background: #f5f5f5; padding: 24rpx; }
.form-card { background: #fff; border-radius: 16rpx; padding: 32rpx; }
.field { margin-bottom: 28rpx; }
.label { display: block; font-size: 26rpx; color: #555; margin-bottom: 10rpx; }
.input { width: 100%; height: 84rpx; border: 2rpx solid #e0e0e0; border-radius: 12rpx; padding: 0 24rpx; font-size: 28rpx; background: #fafafa; }
.ph { color: #bbb; }
.err { display: block; color: #f44336; font-size: 24rpx; margin-bottom: 16rpx; }
.submit-btn { background: #1a73e8; color: #fff; font-size: 30rpx; font-weight: bold; border-radius: 48rpx; height: 92rpx; line-height: 92rpx; border: none; margin-top: 8rpx; }
.submit-btn[disabled] { opacity: 0.6; }
</style>
