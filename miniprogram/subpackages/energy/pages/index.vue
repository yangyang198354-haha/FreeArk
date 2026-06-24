<!--
  @module MOD-PAGE-ENERGY-INDEX
  @description 能耗分包入口菜单（批次②）。三类报表共用 report 页（type 区分）。
-->
<template>
  <view class="energy-index">
    <view class="menu-list">
      <view
        v-for="item in menu"
        :key="item.type"
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
        <text class="menu-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()

onShow(() => {
  if (!authStore.isLoggedIn) uni.reLaunch({ url: '/pages/login/index' })
})

const menu = [
  { type: 'daily', label: '能耗日报', desc: '按日统计用电量', icon: '日' },
  { type: 'monthly', label: '能耗月报', desc: '按月统计用电量', icon: '月' },
  { type: 'period', label: '用量查询', desc: '指定时间段用量明细', icon: '查' },
]

function go(item) {
  uni.navigateTo({ url: `/subpackages/energy/pages/report?type=${item.type}` })
}
</script>

<style scoped>
.energy-index {
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
  font-size: 30rpx;
  font-weight: bold;
  text-align: center;
  line-height: 64rpx;
  margin-right: 20rpx;
}
.menu-text { display: flex; flex-direction: column; }
.menu-label { font-size: 30rpx; color: #333; }
.menu-desc { font-size: 22rpx; color: #999; margin-top: 4rpx; }
.menu-arrow { font-size: 32rpx; color: #bbb; }
</style>
