<!--
  @module MOD-COMP-ARK-TABBAR
  @description 赛博朋克风格 4-Tab 底栏（页内自绘，非原生 tabBar）。
    设计交付「方舟座舱」共享底栏：舰桥 / 指挥 / 副官 / 舰长休息室。
    v1.13.0: 1:1 还原 cyberpunk-smart-home 参考设计。
    - 首页、指挥、副官、舰长休息室 现在是 tabBar 页 → switchTab。
    图标用 SVG data-URI 背景实现（微信小程序 WXML 不渲染 inline SVG）。
    用法：作为页面 flex 列布局的最后一个 flex-shrink:0 子节点。
    在 AI问答/首页(原生 tab 页) 使用时，宿主页需 hideTabBar/showTabBar 避免与原生底栏重叠。
-->
<template>
  <view class="ark-tabbar">
    <!-- 顶部分隔渐变动画线（参考设计 header 底部线） -->
    <view class="tabbar-top-line" />
    <view
      v-for="t in tabs"
      :key="t.key"
      class="tab"
      :class="{ active: active === t.key }"
      @tap="go(t.key)"
    >
      <view class="ico" :class="'ico-' + t.key + (active === t.key ? '-on' : '')" />
      <text class="label">{{ t.label }}</text>
    </view>
    <!-- 安全区底部 -->
    <view class="tabbar-safe" />
  </view>
</template>

<script setup>
defineProps({
  active: { type: String, default: '' }, // home | device | chat | profile
})

const tabs = [
  { key: 'home', label: '舰桥' },
  { key: 'device', label: '指挥室' },
  { key: 'chat', label: '副官' },
  { key: 'profile', label: '舰长休息室' },
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
  position: relative;
  flex: 0 0 auto;
  display: flex;
  align-items: stretch;
  background: rgba(10, 10, 15, 0.92);
  border-top: 1px solid rgba(0, 240, 255, 0.15);
}

/* 顶部分隔渐变动画线（cyberpunk-smart-home 参考） */
.tabbar-top-line {
  position: absolute;
  top: -1px;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, #00f0ff, #b026ff, #ff2d7b, transparent);
  background-size: 200% 100%;
  animation: borderTrail 4s linear infinite;
  z-index: 1;
}

.tab {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4rpx;
  padding-top: 14rpx;
  padding-bottom: 8rpx;
}

/* 活跃 Tab 发光下划线（参考 tab-glow-underline） */
.tab.active::before {
  content: '';
  position: absolute;
  bottom: 2rpx;
  left: 50%;
  transform: translateX(-50%);
  width: 48rpx;
  height: 4rpx;
  border-radius: 2rpx;
  background: #00f0ff;
  box-shadow: 0 0 12rpx rgba(0, 240, 255, 0.6), 0 0 28rpx rgba(0, 240, 255, 0.3);
  animation: glowBreathe 2s ease-in-out infinite;
}

.ico {
  position: relative;
  z-index: 1;
  width: 44rpx;
  height: 44rpx;
  background-repeat: no-repeat;
  background-position: center;
  background-size: 40rpx 40rpx;
}

.tab.active .ico {
  filter: drop-shadow(0 0 8rpx rgba(0, 240, 255, 0.6));
}

.label {
  font-size: 18rpx;
  letter-spacing: 2rpx;
  color: #555577;
}

.tab.active .label {
  color: #00f0ff;
  text-shadow: 0 0 8rpx rgba(0, 240, 255, 0.4);
}

/* ── 安全区底部 ── */
.tabbar-safe {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: constant(safe-area-inset-bottom);
  height: env(safe-area-inset-bottom);
  background: rgba(10, 10, 15, 0.92);
  pointer-events: none;
}

/* ── 图标（SVG data-URI，对照 cyberpunk-smart-home 参考设计）───────────── */
/* 未选中：#555577；选中：#00f0ff */

/* ── 舰桥（Bridge）：雷达十字准星 + 圆弧（参考设计匹配）── */
.ico-home {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23555577' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='8'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cline x1='12' y1='2' x2='12' y2='5'/%3E%3Cline x1='12' y1='19' x2='12' y2='22'/%3E%3Cline x1='2' y1='12' x2='5' y2='12'/%3E%3Cline x1='19' y1='12' x2='22' y2='12'/%3E%3C/svg%3E");
}
.ico-home-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='8'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cline x1='12' y1='2' x2='12' y2='5'/%3E%3Cline x1='12' y1='19' x2='12' y2='22'/%3E%3Cline x1='2' y1='12' x2='5' y2='12'/%3E%3Cline x1='19' y1='12' x2='22' y2='12'/%3E%3C/svg%3E");
}

/* ── 指挥（Command）：六边形盾徽 + 对角线（参考设计匹配）── */
.ico-device {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23555577' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12,2 22,8 22,16 12,22 2,16 2,8'/%3E%3Cline x1='12' y1='8' x2='12' y2='16'/%3E%3Cline x1='8' y1='12' x2='16' y2='12'/%3E%3C/svg%3E");
}
.ico-device-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12,2 22,8 22,16 12,22 2,16 2,8'/%3E%3Cline x1='12' y1='8' x2='12' y2='16'/%3E%3Cline x1='8' y1='12' x2='16' y2='12'/%3E%3C/svg%3E");
}

/* ── 副官（Adjutant）：AI 神经网络节点拓扑（参考设计人物剪影→保持节点拓扑）── */
.ico-chat {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23555577' stroke-width='1.5' stroke-linecap='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M5 20 C5 16 8 14 12 14 C16 14 19 16 19 20'/%3E%3C/svg%3E");
}
.ico-chat-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M5 20 C5 16 8 14 12 14 C16 14 19 16 19 20'/%3E%3C/svg%3E");
}

/* ── 舰长休息室（Captain's Quarters）：星徽（参考设计匹配）── */
.ico-profile {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23555577' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12,2 15,9 22,9 16,14 18,21 12,17 6,21 8,14 2,9 9,9'/%3E%3C/svg%3E");
}
.ico-profile-on {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12,2 15,9 22,9 16,14 18,21 12,17 6,21 8,14 2,9 9,9'/%3E%3C/svg%3E");
}

/* ── Keyframes ── */
@keyframes borderTrail {
  0% { background-position: 0% 0%; }
  100% { background-position: 200% 0%; }
}

@keyframes glowBreathe {
  0%, 100% { box-shadow: 0 0 8rpx rgba(0, 240, 255, 0.3); }
  50% { box-shadow: 0 0 20rpx rgba(0, 240, 255, 0.6), 0 0 40rpx rgba(0, 240, 255, 0.25); }
}
</style>
