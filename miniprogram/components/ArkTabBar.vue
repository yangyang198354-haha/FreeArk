<!--
  @module MOD-COMP-ARK-TABBAR
  @description 赛博朋克风格 4-Tab 底栏（页内自绘，非原生 tabBar）。
    设计交付「方舟座舱」共享底栏：首页 / 设备 / AI问答 / 我的。
    - 首页、AI问答 是原生 tabBar 页 → switchTab（会清理非 tab 页栈）。
    - 设备、我的 是分包/主包非 tab 页 → navigateTo；设备按角色分流（业主→参数设置）。
    图标用 SVG data-URI 背景实现（微信小程序 WXML 不渲染 inline SVG）。
    用法：作为页面 flex 列布局的最后一个 flex-shrink:0 子节点。
    在 AI问答/首页(原生 tab 页) 使用时，宿主页需 hideTabBar/showTabBar 避免与原生底栏重叠。
-->
<template>
  <view class="ark-tabbar">
    <view
      v-for="t in tabs"
      :key="t.key"
      class="tab"
      :class="{ active: active === t.key }"
      @tap="go(t.key)"
    >
      <view v-if="active === t.key" class="glow-pill" />
      <view class="ico" :class="'ico-' + t.key + (active === t.key ? '-on' : '')" />
      <text class="label">{{ t.label }}</text>
    </view>
  </view>
</template>

<script setup>
import { useAuthStore } from '@/store/auth'

defineProps({
  active: { type: String, default: '' }, // home | device | chat | profile
})

const authStore = useAuthStore()

const tabs = [
  { key: 'home', label: '首页' },
  { key: 'device', label: '设备' },
  { key: 'chat', label: 'AI问答' },
  { key: 'profile', label: '我的' },
]

function go(key) {
  switch (key) {
    case 'home':
      uni.switchTab({ url: '/pages/home/index' })
      break
    case 'chat':
      uni.switchTab({ url: '/pages/chat/index' })
      break
    case 'device':
      // 设备参数设置页已移入主包，现在作为 tab 页常驻
      uni.switchTab({ url: '/pages/device/param-settings' })
      break
    case 'profile':
      uni.switchTab({ url: '/pages/profile/index' })
      break
  }
}
</script>

<style scoped>
.ark-tabbar {
  flex: 0 0 auto;
  display: flex;
  align-items: stretch;
  height: 128rpx;
  padding-bottom: constant(safe-area-inset-bottom);
  padding-bottom: env(safe-area-inset-bottom);
  background: rgba(6, 10, 20, 0.9);
  border-top: 1px solid rgba(56, 230, 224, 0.14);
}
.tab {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
}
.glow-pill {
  position: absolute;
  top: 0;
  width: 52rpx;
  height: 4rpx;
  border-radius: 4rpx;
  background: #2ff4e0;
  box-shadow: 0 0 8px #2ff4e0;
}
.ico {
  width: 44rpx;
  height: 44rpx;
  background-repeat: no-repeat;
  background-position: center;
  background-size: 44rpx 44rpx;
}
.tab.active .ico {
  filter: drop-shadow(0 0 6px rgba(47, 244, 224, 0.7));
}
.label {
  font-size: 20rpx;
  color: rgba(170, 195, 230, 0.5);
}
.tab.active .label {
  color: #2ff4e0;
  text-shadow: 0 0 8px rgba(47, 244, 224, 0.6);
}

/* ── 图标（SVG data-URI，stroke 颜色内联）───────────────────────────── */
/* 未选中：rgba(170,195,230,.5)；选中：#2ff4e0 */
.ico-home {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='rgba(170,195,230,0.5)' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 11l9-7 9 7'/%3E%3Cpath d='M5 10v9h14v-9'/%3E%3C/svg%3E");
}
.ico-home-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 11l9-7 9 7'/%3E%3Cpath d='M5 10v9h14v-9'/%3E%3C/svg%3E");
}
.ico-device {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='rgba(170,195,230,0.5)' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='4' y='4' width='16' height='16' rx='2.5'/%3E%3Crect x='9' y='9' width='6' height='6' rx='1'/%3E%3C/svg%3E");
}
.ico-device-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='4' y='4' width='16' height='16' rx='2.5'/%3E%3Crect x='9' y='9' width='6' height='6' rx='1'/%3E%3C/svg%3E");
}
.ico-chat {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='rgba(170,195,230,0.5)' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 5h16v11H9l-4 4v-4H4z'/%3E%3C/svg%3E");
}
.ico-chat-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 5h16v11H9l-4 4v-4H4z'/%3E%3C/svg%3E");
}
.ico-profile {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='rgba(170,195,230,0.5)' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M4 20c0-4 4-6 8-6s8 2 8 6'/%3E%3C/svg%3E");
}
.ico-profile-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M4 20c0-4 4-6 8-6s8 2 8 6'/%3E%3C/svg%3E");
}
</style>
