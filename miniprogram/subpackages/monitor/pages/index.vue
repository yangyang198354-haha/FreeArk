<!--
  @module MOD-PAGE-MONITOR-INDEX
  @description 监控分包入口菜单（分包A）。列出监控相关子页面，逐批落地。
    已实现的 navigateTo 跳转，未实现的给"敬请期待"提示。
    暗色赛博朋克主题，与整体小程序风格一致。
-->
<template>
  <view class="mi-page">
    <!-- 背景装饰 -->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="bg-blob" />

    <!-- 状态栏占位 -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- header -->
    <view class="header">
      <view class="back-btn ico-back" @tap="goBack" />
      <text class="header-title">设备监控</text>
    </view>

    <scroll-view scroll-y class="body">
      <view class="card menu-card">
        <view class="corner tl" /><view class="corner tr" />
        <view class="corner bl" /><view class="corner br" />

        <view
          v-for="item in menu"
          :key="item.path || item.label"
          class="menu-item"
          @tap="go(item)"
        >
          <view class="menu-main">
            <view class="menu-icon" :style="{ background: item.iconBg || 'rgba(47,244,224,0.12)' }">
              <text :style="{ color: item.iconColor || '#2ff4e0' }">{{ item.icon }}</text>
            </view>
            <view class="menu-text">
              <text class="menu-label">{{ item.label }}</text>
              <text class="menu-desc">{{ item.desc }}</text>
            </view>
          </view>
          <text class="menu-arrow" :class="{ 'menu-tag': !item.ready }">
            {{ item.ready ? '›' : '开发中' }}
          </text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
  }
})

const menu = [
  { label: 'PLC 连接状态', desc: '各设备在线/离线状态', icon: 'P', iconBg: 'rgba(47,244,224,0.12)', iconColor: '#2ff4e0', ready: true, path: '/subpackages/monitor/pages/plc-status' },
  { label: '设备列表', desc: '按房间查找设备 · 查看实时参数', icon: 'D', iconBg: 'rgba(139,92,246,0.15)', iconColor: '#a78bfa', ready: true, path: '/subpackages/monitor/pages/device-list' },
]

function go(item) {
  if (item.ready && item.path) {
    uni.navigateTo({ url: item.path })
  } else {
    uni.showToast({ title: '功能开发中，敬请期待', icon: 'none' })
  }
}

function goBack() {
  uni.navigateBack()
}
</script>

<style scoped>
.mi-page {
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
.ico-back {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23eaf6ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 5l-7 7 7 7'/%3E%3C/svg%3E");
}

/* ── body ───────────────────────────────── */
.body { position: relative; z-index: 4; flex: 1 1 auto; padding: 20rpx 36rpx; }

/* ── card ───────────────────────────────── */
.card {
  position: relative; border-radius: 32rpx;
  border: 1px solid rgba(56,230,224,0.18);
}
.menu-card {
  padding: 16rpx 0;
  background: linear-gradient(180deg, rgba(14,22,42,0.75), rgba(8,14,28,0.8));
  box-shadow: inset 0 0 26px rgba(20,40,80,0.35);
}
.corner { position: absolute; width: 44rpx; height: 44rpx; }
.corner.tl { left: -1px; top: -1px; border-left: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.corner.tr { right: -1px; top: -1px; border-right: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.corner.bl { left: -1px; bottom: -1px; border-left: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.corner.br { right: -1px; bottom: -1px; border-right: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 8rpx 0; }

/* ── menu item ──────────────────────────── */
.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx 36rpx;
  border-bottom: 1rpx solid rgba(56,230,224,0.08);
  transition: background 0.15s;
}
.menu-item:active {
  background: rgba(47,244,224,0.06);
}
.menu-item:last-child {
  border-bottom: none;
}
.menu-main {
  display: flex;
  align-items: center;
}
.menu-icon {
  width: 72rpx;
  height: 72rpx;
  border-radius: 16rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 24rpx;
}
.menu-icon text {
  font-size: 32rpx;
  font-weight: 700;
}
.menu-text {
  display: flex;
  flex-direction: column;
}
.menu-label {
  font-size: 30rpx;
  color: #eaf6ff;
  font-weight: 600;
}
.menu-desc {
  font-size: 22rpx;
  color: rgba(143,217,255,0.5);
  margin-top: 6rpx;
}
.menu-arrow {
  font-size: 36rpx;
  color: rgba(47,244,224,0.4);
  font-weight: 300;
}
.menu-tag {
  font-size: 22rpx;
  color: rgba(255,255,255,0.25);
  background: rgba(255,255,255,0.06);
  padding: 4rpx 16rpx;
  border-radius: 8rpx;
}
</style>