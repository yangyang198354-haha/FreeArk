<!--
  @module MOD-PAGE-PROFILE
  @description 个人中心。展示账号/角色，入口：修改密码、退出登录。
    （补齐切片缺口：登出入口。）
-->
<template>
  <view class="profile-page">
    <view class="user-card">
      <view class="avatar"><text>{{ avatarText }}</text></view>
      <view class="user-info">
        <text class="username">{{ username || '未登录' }}</text>
        <text class="role">{{ isAdmin ? '管理员' : '普通用户' }}</text>
      </view>
    </view>

    <view class="menu">
      <view class="menu-item" @tap="goChangePassword">
        <text class="mi-label">修改密码</text>
        <text class="mi-arrow">›</text>
      </view>
    </view>

    <button class="logout-btn" @tap="onLogout">退出登录</button>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()
const username = computed(() => authStore.username)
const isAdmin = computed(() => authStore.isAdmin)
const avatarText = computed(() => (authStore.username || '?').slice(0, 1).toUpperCase())

onShow(() => {
  if (!authStore.isLoggedIn) uni.reLaunch({ url: '/pages/login/index' })
})

function goChangePassword() {
  uni.navigateTo({ url: '/pages/change-password/index' })
}

function onLogout() {
  uni.showModal({
    title: '退出登录',
    content: '确定要退出登录吗？',
    success: (r) => {
      if (r.confirm) {
        authStore.logout()
        uni.reLaunch({ url: '/pages/login/index' })
      }
    },
  })
}
</script>

<style scoped>
.profile-page { min-height: 100vh; background: #f5f5f5; padding: 24rpx; }
.user-card { display: flex; align-items: center; background: #fff; border-radius: 16rpx; padding: 32rpx; margin-bottom: 24rpx; }
.avatar { width: 96rpx; height: 96rpx; border-radius: 50%; background: #1a73e8; color: #fff; font-size: 44rpx; font-weight: bold; text-align: center; line-height: 96rpx; margin-right: 24rpx; }
.user-info { display: flex; flex-direction: column; }
.username { font-size: 32rpx; font-weight: bold; color: #333; }
.role { font-size: 24rpx; color: #999; margin-top: 6rpx; }
.menu { background: #fff; border-radius: 16rpx; overflow: hidden; margin-bottom: 48rpx; }
.menu-item { display: flex; align-items: center; justify-content: space-between; padding: 32rpx 24rpx; }
.mi-label { font-size: 30rpx; color: #333; }
.mi-arrow { font-size: 32rpx; color: #bbb; }
.logout-btn { background: #fff; color: #f44336; font-size: 30rpx; border-radius: 16rpx; height: 96rpx; line-height: 96rpx; border: none; }
</style>
