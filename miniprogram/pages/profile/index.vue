<!--
  @module MOD-PAGE-PROFILE
  @description 个人中心（方案1 · 卡片流，赛博朋克 HUD）。
    Claude Design handoff「个人中心 方案1」1:1 还原。custom 导航 + 自绘 4-Tab 底栏。
    核心：业主绑定的是「房号 / 专有部分」（非设备）。房号列表接真实数据 api.getBindStatus()。
    保留既有功能接线：绑定(bind)、修改密码(change-password 由编辑铅笔进入)、退出登录、参数设置入口。
    图标为 SVG data-URI 背景（微信小程序不渲染 inline SVG）；字体不远程加载（规避 OTS 崩溃），靠字间距近似。
-->
<template>
  <view class="me-page">
    <!-- 背景装饰（不拦截点击）-->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="bg-blob" />

    <!-- 状态栏占位（custom 导航）-->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- header -->
    <view class="header">
      <text class="header-title">舰长休息室</text>
    </view>

    <!-- body -->
    <scroll-view scroll-y class="body">
      <!-- profile card -->
      <view class="card profile-card">
        <view class="corner tl" /><view class="corner tr" />
        <view class="corner bl" /><view class="corner br" />
        <view class="pc-row">
          <view class="avatar-wrap" @tap="onEditAvatar">
            <view class="avatar-ring" />
            <!-- v1.12.0: 有头像显示图片，无头像或加载失败显示文字降级 -->
            <image v-if="authStore.avatarUrl && !imgError"
                   :src="authStore.avatarUrl"
                   class="avatar-img"
                   mode="aspectFill"
                   @error="imgError = true" />
            <view v-else class="avatar"><text>{{ avatarText }}</text></view>
          </view>
          <view class="pc-info">
            <view class="pc-name-row">
              <text class="pc-name" @tap="onEditNickname">{{ nickname }}</text>
              <text class="badge-ok">{{ roleBadge }}</text>
            </view>
            <text class="pc-id">ID · {{ userId }}</text>
            <text v-if="subLine" class="pc-sub">{{ subLine }}</text>
          </view>
          <view class="edit-btn ico-pencil" @tap="goEdit" />
        </view>
      </view>

      <!-- section label -->
      <view class="section-label">
        <text class="sl-left">PROPERTY · 我的房号</text>
        <text class="sl-right" @tap="goViewAll">查看全部 ›</text>
      </view>

      <!-- property list -->
      <view class="card list-card">
        <block v-if="bindings.length">
          <view v-for="(b, i) in bindings" :key="b.specific_part || i">
            <view class="prop-row" @tap="switchProp(b)">
              <view class="house-ico" :class="i === 0 ? 'ico-house-cyan' : 'ico-house-purple'" />
              <view class="prop-mid">
                <view class="prop-name-row">
                  <text class="prop-name">{{ b.location_name || '未命名小区' }}</text>
                  <text v-if="i === 0" class="badge-default">默认</text>
                </view>
                <text class="prop-sub">{{ b.specific_part }} · 专有部分</text>
              </view>
              <text class="prop-switch">切换 ›</text>
            </view>
            <view v-if="i < bindings.length - 1" class="hairline" />
          </view>
        </block>
        <view v-else class="prop-empty">
          <text>{{ loadingBindings ? '加载中…' : '尚未绑定房号' }}</text>
        </view>
      </view>

      <!-- bind new -->
      <view class="bind-new" @tap="goBind">
        <text class="bind-plus">＋</text>
        <text>绑定新房号</text>
      </view>

      <!-- settings row -->
      <view class="settings-row" @tap="goParamSettings">
        <view class="settings-ico ico-gear" />
        <text class="settings-label">参数设置</text>
        <text class="settings-arrow">›</text>
      </view>
    </scroll-view>

    <!-- logout（固定在底栏之上）-->
    <view class="logout-bar">
      <view class="logout-btn" @tap="onLogout">
        <view class="ico-power" />
        <text>退出登录</text>
      </view>
    </view>

    <!-- 底栏 -->
    <ArkTabBar active="profile" />
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useOwnerStore } from '@/store/owner'
import ArkTabBar from '@/components/ArkTabBar.vue'

const authStore = useAuthStore()
const ownerStore = useOwnerStore()

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

const bindings = computed(() => ownerStore.bindings)
const loadingBindings = ref(false)
const imgError = ref(false)  // v1.12.0: 头像加载失败降级

const nickname = computed(() => authStore.nickname || authStore.username || '未登录')
const avatarText = computed(() => (authStore.username || '?').slice(0, 1).toUpperCase())
const userId = computed(() => {
  const id = authStore.userInfo?.id
  return id != null ? `ARK-${id}` : (authStore.username || '—')
})
const roleBadge = computed(() => {
  const r = authStore.role
  if (r === 'admin') return '管理员'
  if (r === 'operator') return '运维'
  return '已认证'
})
const subLine = computed(() => authStore.userInfo?.email || '')

async function loadBindings() {
  if (!authStore.isLoggedIn) return
  loadingBindings.value = !ownerStore.bindingsLoaded
  try {
    // getBindStatus → { bound, bindings:[{specific_part, location_name, bound_at}] }
    await ownerStore.ensureBindings({ allowStale: true })
  } catch (e) {
    // 非致命：无绑定/接口异常时列表留空，展示「尚未绑定房号」
    // Keep cached bindings when the silent refresh fails.
  } finally {
    loadingBindings.value = false
  }
}

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  loadBindings()
})

function switchProp(b) {
  // 本地记录当前活跃房号（供其余页面读取 specific_part）；后端无「默认房号」概念，纯前端偏好
  if (b.specific_part) {
    ownerStore.setActiveSpecificPart(b.specific_part)
  }
  uni.showToast({ title: `已切换到 ${b.location_name || b.specific_part}`, icon: 'none' })
}

// v1.12.0: 编辑头像 — 跳转到 profile-setup 编辑页
async function onEditAvatar() {
  if (!authStore.isLoggedIn) return
  // 在个人中心直接使用 chooseAvatar 弹窗选择头像并上传
  // 复用 profile-setup 的 chooseAvatar 上传逻辑
  uni.navigateTo({ url: '/pages/profile-setup/index?mode=edit' })
}

// v1.12.0: 编辑昵称 — 跳转到 profile-setup 编辑页
function onEditNickname() {
  if (!authStore.isLoggedIn) return
  uni.navigateTo({ url: '/pages/profile-setup/index?mode=edit' })
}

function goViewAll() {
  uni.navigateTo({ url: '/pages/bind/index' })
}
function goBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}
function goParamSettings() {
  uni.switchTab({ url: '/pages/device/param-settings' })
}
function goEdit() {
  // 设计中的「编辑」= 编辑资料；当前可用的账号操作为修改密码，保留其入口
  uni.navigateTo({ url: '/pages/change-password/index' })
}

function onLogout() {
  uni.showModal({
    title: '退出登录',
    content: '确定要退出登录吗？',
    success: (r) => {
      if (r.confirm) {
        authStore.logout()
        // 延迟一帧再 reLaunch：确保 showModal 的全屏蒙层先播完消失动画再跳转。
        // 否则在 reLaunch 销毁页面栈时蒙层可能被遗留在新登录页之上、吞掉所有点击
        //（原生 input 在更高的原生层，唯独它仍可用——与"登出后登录页点不动、重启工具才好"现象一致）。
        setTimeout(() => uni.reLaunch({ url: '/pages/login/index' }), 80)
      }
    },
  })
}
</script>

<style scoped>
.me-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070f;
  overflow: hidden;
}

/* ── 背景 ─────────────────────────────────────────── */
.bg-base, .bg-grid, .bg-blob { position: absolute; pointer-events: none; }
.bg-base {
  inset: 0;
  background:
    radial-gradient(90% 45% at 18% 0%, rgba(101,55,180,0.32), transparent 55%),
    radial-gradient(80% 40% at 100% 4%, rgba(20,180,170,0.22), transparent 55%),
    linear-gradient(180deg, #0b0a1a, #07101c 60%, #050811);
}
.bg-grid {
  inset: 0;
  background-image:
    linear-gradient(rgba(56,230,224,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,230,224,0.06) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 55%);
  mask-image: linear-gradient(180deg, #000, transparent 55%);
}
.bg-blob {
  width: 400rpx; height: 400rpx; left: -120rpx; top: 180rpx; border-radius: 50%;
  background: radial-gradient(circle, rgba(139,92,246,0.22), transparent 70%);
  filter: blur(8px);
  animation: ark-float 16s ease-in-out infinite;
}
@keyframes ark-float { 0%,100% { transform: translate(0,0); } 50% { transform: translate(20rpx,-24rpx); } }

.status-spacer { position: relative; z-index: 5; flex: 0 0 auto; }

/* ── header ───────────────────────────────────────── */
.header {
  position: relative; z-index: 5; flex: 0 0 auto;
  height: 92rpx; display: flex; align-items: center; justify-content: center;
}
.header-title {
  font-size: 34rpx; font-weight: 700; letter-spacing: 8rpx; color: #f4fbff;
  text-shadow: 0 0 12px rgba(56,230,224,0.5);
}

/* ── body ─────────────────────────────────────────── */
.body { position: relative; z-index: 4; flex: 1 1 auto; padding: 20rpx 36rpx; }

/* profile card */
.card {
  position: relative; border-radius: 32rpx;
  border: 1px solid rgba(56,230,224,0.18);
}
.profile-card {
  padding: 36rpx;
  background: linear-gradient(180deg, rgba(14,22,42,0.75), rgba(8,14,28,0.8));
  box-shadow: inset 0 0 26px rgba(20,40,80,0.35);
  margin-bottom: 32rpx;
}
.corner { position: absolute; width: 44rpx; height: 44rpx; }
.corner.tl { left: -1px; top: -1px; border-left: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.corner.tr { right: -1px; top: -1px; border-right: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.corner.bl { left: -1px; bottom: -1px; border-left: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.corner.br { right: -1px; bottom: -1px; border-right: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 8rpx 0; }

.pc-row { display: flex; align-items: center; gap: 30rpx; }
.avatar-wrap { position: relative; width: 128rpx; height: 128rpx; flex: 0 0 auto; display: flex; align-items: center; justify-content: center; }
.avatar-ring { position: absolute; inset: 0; border-radius: 50%; border: 1px dashed rgba(56,230,224,0.5); }
.avatar {
  width: 108rpx; height: 108rpx; border-radius: 50%;
  background: linear-gradient(150deg, rgba(47,244,224,0.25), rgba(139,92,246,0.25));
  border: 1px solid rgba(56,230,224,0.6);
  display: flex; align-items: center; justify-content: center;
}
.avatar text { font-size: 48rpx; font-weight: 900; color: #aef9f2; text-shadow: 0 0 12px rgba(47,244,224,0.7); }
/* v1.12.0: 图片头像 */
.avatar-img { width: 108rpx; height: 108rpx; border-radius: 50%; border: 1px solid rgba(56,230,224,0.6); }

.pc-info { flex: 1; min-width: 0; }
.pc-name-row { display: flex; align-items: center; gap: 16rpx; }
.pc-name { font-size: 38rpx; font-weight: 700; color: #f4fbff; }
.badge-ok {
  font-size: 18rpx; letter-spacing: 2rpx; color: #5ff0b6;
  border: 1px solid rgba(95,240,182,0.5); border-radius: 8rpx; padding: 2rpx 10rpx; white-space: nowrap;
}
.pc-id { display: block; font-size: 22rpx; letter-spacing: 2rpx; color: rgba(143,217,255,0.65); margin-top: 12rpx; }
.pc-sub { display: block; font-size: 24rpx; color: rgba(143,217,255,0.55); margin-top: 6rpx; }

.edit-btn {
  flex: 0 0 auto; width: 68rpx; height: 68rpx; border-radius: 18rpx;
  border: 1px solid rgba(56,230,224,0.3);
  background-repeat: no-repeat; background-position: center; background-size: 34rpx 34rpx;
}

/* section label */
.section-label { display: flex; align-items: center; justify-content: space-between; padding: 0 4rpx; margin-bottom: 24rpx; }
.sl-left { font-size: 22rpx; letter-spacing: 4rpx; color: rgba(56,230,224,0.7); }
.sl-right { font-size: 24rpx; color: rgba(143,217,255,0.6); }

/* property list */
.list-card {
  background: linear-gradient(180deg, rgba(14,22,42,0.7), rgba(8,14,28,0.78));
  border-color: rgba(56,230,224,0.15);
  margin-bottom: 32rpx;
}
.prop-row { display: flex; align-items: center; gap: 26rpx; padding: 28rpx 32rpx; }
.house-ico { flex: 0 0 auto; width: 84rpx; height: 84rpx; border-radius: 22rpx; background-repeat: no-repeat; background-position: center; background-size: 40rpx 40rpx; }
.ico-house-cyan { background-color: rgba(47,244,224,0.1); border: 1px solid rgba(56,230,224,0.5); }
.ico-house-purple { background-color: rgba(139,92,246,0.12); border: 1px solid rgba(139,92,246,0.55); }
.prop-mid { flex: 1; min-width: 0; }
.prop-name-row { display: flex; align-items: center; gap: 14rpx; }
.prop-name { font-size: 30rpx; font-weight: 700; color: #eaf6ff; }
.badge-default { font-size: 18rpx; color: #5ff0b6; border: 1px solid rgba(95,240,182,0.5); border-radius: 8rpx; padding: 2rpx 10rpx; white-space: nowrap; }
.prop-sub { display: block; font-size: 20rpx; letter-spacing: 2rpx; color: rgba(143,217,255,0.5); margin-top: 6rpx; }
.prop-switch { font-size: 26rpx; color: rgba(143,217,255,0.55); }
.hairline { height: 1px; background: linear-gradient(90deg, transparent, rgba(56,230,224,0.18), transparent); margin: 0 32rpx; }
.prop-empty { padding: 40rpx; text-align: center; }
.prop-empty text { font-size: 26rpx; color: rgba(143,217,255,0.5); }

/* bind new */
.bind-new {
  display: flex; align-items: center; justify-content: center; gap: 16rpx;
  height: 96rpx; border-radius: 28rpx; border: 1px dashed rgba(56,230,224,0.4);
  background: rgba(47,244,224,0.04); color: #2ff4e0; font-size: 28rpx; margin-bottom: 32rpx;
}
.bind-plus { font-size: 36rpx; font-weight: 300; }

/* settings row */
.settings-row {
  display: flex; align-items: center; gap: 26rpx; padding: 26rpx 32rpx;
  border-radius: 28rpx; background: rgba(14,22,42,0.55); border: 1px solid rgba(56,230,224,0.12);
}
.settings-ico { flex: 0 0 auto; width: 60rpx; height: 60rpx; border-radius: 16rpx; background-color: rgba(47,244,224,0.08); background-repeat: no-repeat; background-position: center; background-size: 32rpx 32rpx; }
.settings-label { flex: 1; font-size: 28rpx; color: #dbeeff; }
.settings-arrow { font-size: 30rpx; color: rgba(143,217,255,0.5); }

/* logout */
.logout-bar { position: relative; z-index: 5; flex: 0 0 auto; padding: 20rpx 36rpx 28rpx; }
.logout-btn {
  display: flex; align-items: center; justify-content: center; gap: 16rpx; height: 100rpx;
  border-radius: 50rpx; border: 1px solid rgba(255,61,166,0.5); background: rgba(255,61,166,0.06);
  color: #ff7ab5; font-weight: 700; font-size: 30rpx; letter-spacing: 4rpx;
  box-shadow: 0 0 16px rgba(255,61,166,0.18);
}

/* ── 图标（SVG data-URI）─────────────────────────── */
.ico-pencil { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 20h4l10-10-4-4L4 16z'/%3E%3C/svg%3E"); }
.ico-house-cyan { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 21V9l8-5 8 5v12'/%3E%3Cpath d='M9 21v-6h6v6'/%3E%3C/svg%3E"); }
.ico-house-purple { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23c4a6ff' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 21V9l8-5 8 5v12'/%3E%3Cpath d='M9 21v-6h6v6'/%3E%3C/svg%3E"); }
.ico-gear { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ff4e0' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cpath d='M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2'/%3E%3C/svg%3E"); }
.ico-power { width: 34rpx; height: 34rpx; background-repeat: no-repeat; background-position: center; background-size: 34rpx 34rpx; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ff7ab5' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3v9'/%3E%3Cpath d='M6.5 6a8 8 0 1 0 11 0'/%3E%3C/svg%3E"); }
</style>
