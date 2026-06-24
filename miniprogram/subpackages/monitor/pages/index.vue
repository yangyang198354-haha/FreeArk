<!--
  @module MOD-PAGE-MONITOR-INDEX
  @description 监控分包入口菜单（分包A）。列出监控相关子页面，逐批落地。
    已实现的 navigateTo 跳转，未实现的给"敬请期待"提示。
-->
<template>
  <view class="monitor-index">
    <view class="menu-list">
      <view
        v-for="item in menu"
        :key="item.path || item.label"
        class="menu-item"
        @tap="go(item)"
      >
        <view class="menu-main">
          <text class="menu-icon">{{ item.icon }}</text>
          <view class="menu-text">
            <text class="menu-label">{{ item.label }}</text>
            <text class="menu-desc">{{ item.desc }}</text>
          </view>
        </view>
        <text class="menu-arrow">{{ item.ready ? '›' : '开发中' }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
  }
})

const menu = [
  { label: 'PLC 连接状态', desc: '各设备在线/离线状态', icon: 'P', ready: true, path: '/subpackages/monitor/pages/plc-status' },
  { label: '设备列表', desc: '按房间查找设备 · 查看实时参数', icon: 'D', ready: true, path: '/subpackages/monitor/pages/device-list' },
]

function go(item) {
  if (item.ready && item.path) {
    uni.navigateTo({ url: item.path })
  } else {
    uni.showToast({ title: '功能开发中，敬请期待', icon: 'none' })
  }
}
</script>

<style scoped>
.monitor-index {
  min-height: 100vh;
  background: #f5f5f5;
  padding: 24rpx;
}
.menu-list {
  background: #fff;
  border-radius: 16rpx;
  overflow: hidden;
}
.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx 24rpx;
  border-bottom: 1rpx solid #f0f0f0;
}
.menu-main {
  display: flex;
  align-items: center;
}
.menu-icon {
  width: 64rpx;
  height: 64rpx;
  border-radius: 12rpx;
  background: #e8f0fe;
  color: #1a73e8;
  font-size: 32rpx;
  font-weight: bold;
  text-align: center;
  line-height: 64rpx;
  margin-right: 20rpx;
}
.menu-text {
  display: flex;
  flex-direction: column;
}
.menu-label {
  font-size: 30rpx;
  color: #333;
}
.menu-desc {
  font-size: 22rpx;
  color: #999;
  margin-top: 4rpx;
}
.menu-arrow {
  font-size: 28rpx;
  color: #bbb;
}
</style>
