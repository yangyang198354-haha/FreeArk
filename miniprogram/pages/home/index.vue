<!--
  @module MOD-PAGE-HOME
  @author sub_agent_software_developer
  @description Home dashboard (US-02).
    4 metric cards: PLC online rate, active faults, condensation warnings, today energy.
    4 shortcut tiles: fault mgmt, condensation, AI chat, device monitor.
    Pull-down refresh + 30s auto-poll via PagePoller.
    Polls stop on onHide, resume on onShow (battery/network friendly).

  API calls (NQ-01 confirmed — 4 separate endpoints):
    1. GET /api/dashboard/plc-online-rate/          → online_count, total_count
    2. GET /api/dashboard/fault-summary/            → active_fault_count
    3. GET /api/dashboard/summary/                  → today_kwh
    4. GET /api/devices/condensation-warning-events/?page=1&page_size=1 → count (DRF root)
-->
<template>
  <view class="home-page">
    <!-- Header -->
    <view class="header">
      <text class="header-title">FreeArk 控制中心</text>
      <text class="header-subtitle">{{ currentDate }}</text>
    </view>

    <!-- 系统概览：仅 admin/operator 可见。
         user（业主）角色被 UserRoleApiGuardMiddleware 拦截所有管理端接口（RBAC OQ-06），
         fetchDashboard() 对 user 角色提前返回，因此本节对 user 隐藏以避免永久显示"--"。 -->
    <view v-if="authStore.role !== 'user'" class="section">
      <text class="section-title">系统概览</text>
      <view class="metrics-grid">
        <MetricCard
          class="metric-cell"
          title="在线 PLC"
          :value="plcText"
          :alert="plcAlert"
        />
        <MetricCard
          class="metric-cell"
          title="活跃故障"
          :value="dashData.faultCount"
          subtitle="条"
          :alert="typeof dashData.faultCount === 'number' && dashData.faultCount > 0"
        />
        <MetricCard
          class="metric-cell"
          title="结露预警"
          :value="dashData.condensationCount"
          subtitle="条"
          :alert="typeof dashData.condensationCount === 'number' && dashData.condensationCount > 0"
          @tap="goTo('/subpackages/ops/pages/condensation')"
        />
        <MetricCard
          class="metric-cell"
          title="今日能耗"
          :value="dashData.todayKwh"
          subtitle="kWh"
        />
      </view>
    </view>

    <!-- 业主端欢迎区（role=user）：替代系统概览指标卡 -->
    <view v-else class="section">
      <text class="section-title">我的设备</text>
      <view class="owner-welcome">
        <text class="owner-welcome-text">欢迎使用 FreeArk 业主端</text>
        <text class="owner-welcome-sub">请通过下方「参数设置」管理您的房间设备</text>
      </view>
    </view>

    <!-- 快捷入口
         admin/operator：故障管理、结露预警、AI 问答、设备监控、能耗报表、巡检工单、个人中心
         user（业主）：方舟智能体问答、参数设置、个人中心
           — 管理端快捷入口对 user 隐藏，避免点进去因 UserRoleApiGuardMiddleware (RBAC OQ-06) 403。
           — 个人中心(/api/auth/me/ 在白名单)保留，业主需要它登出和改密。 -->
    <view class="section">
      <text class="section-title">快捷入口</text>
      <view class="shortcuts-grid">
        <!-- 管理端入口：仅 admin/operator 可见 -->
        <view
          v-if="authStore.role !== 'user'"
          class="shortcut-tile"
          @tap="goTo('/subpackages/ops/pages/faults')"
        >
          <text class="shortcut-icon">!</text>
          <text class="shortcut-label">故障管理</text>
          <view
            v-if="typeof dashData.faultCount === 'number' && dashData.faultCount > 0"
            class="shortcut-badge"
          >{{ dashData.faultCount }}</view>
        </view>
        <view
          v-if="authStore.role !== 'user'"
          class="shortcut-tile"
          @tap="goTo('/subpackages/ops/pages/condensation')"
        >
          <text class="shortcut-icon">~</text>
          <text class="shortcut-label">结露预警</text>
        </view>

        <!-- 方舟智能体问答：全角色可见 -->
        <view class="shortcut-tile" @tap="goTo('/pages/chat/index')">
          <text class="shortcut-icon">AI</text>
          <text class="shortcut-label">方舟智能体</text>
        </view>

        <!-- 方舟座舱（游戏化 POC）：全角色可见 -->
        <view class="shortcut-tile" @tap="goTo('/subpackages/game/pages/ark-poc')">
          <text class="shortcut-icon">⬢</text>
          <text class="shortcut-label">方舟座舱</text>
        </view>

        <!-- 方舟智能体·机器人场景（游戏化 POC）：全角色可见 -->
        <view class="shortcut-tile" @tap="goTo('/subpackages/game/pages/agent-scene')">
          <text class="shortcut-icon">⊙</text>
          <text class="shortcut-label">智能体座舱</text>
        </view>

        <!-- 管理端入口：仅 admin/operator 可见 -->
        <view
          v-if="authStore.role !== 'user'"
          class="shortcut-tile"
          @tap="goTo('/subpackages/monitor/pages/index')"
        >
          <text class="shortcut-icon">M</text>
          <text class="shortcut-label">设备监控</text>
        </view>
        <view
          v-if="authStore.role !== 'user'"
          class="shortcut-tile"
          @tap="goTo('/subpackages/energy/pages/index')"
        >
          <text class="shortcut-icon">E</text>
          <text class="shortcut-label">能耗报表</text>
        </view>
        <view
          v-if="authStore.role !== 'user'"
          class="shortcut-tile"
          @tap="goTo('/subpackages/ops/pages/workorders')"
        >
          <text class="shortcut-icon">W</text>
          <text class="shortcut-label">巡检工单</text>
        </view>

        <!-- 参数设置：仅 user（业主）可见，调用 /api/miniapp/ 白名单接口 -->
        <view
          v-if="authStore.role === 'user'"
          class="shortcut-tile"
          @tap="goTo('/subpackages/control/pages/param-settings')"
        >
          <text class="shortcut-icon">⚙</text>
          <text class="shortcut-label">参数设置</text>
        </view>

        <!-- 个人中心：全角色可见（/api/auth/me/ 在 RBAC 白名单，不会 403） -->
        <view class="shortcut-tile" @tap="goTo('/pages/profile/index')">
          <text class="shortcut-icon">U</text>
          <text class="shortcut-label">个人中心</text>
        </view>
      </view>
    </view>

    <!-- Error state -->
    <view v-if="errorMsg" class="error-banner">
      <text>{{ errorMsg }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow, onHide, onPullDownRefresh } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'
import { PagePoller } from '@/utils/poller'
import MetricCard from '@/components/MetricCard.vue'

const authStore = useAuthStore()

// Auth guard
if (!authStore.isLoggedIn) {
  uni.reLaunch({ url: '/pages/login/index' })
}

const errorMsg = ref('')
const dashData = ref({
  plcOnline: '--',
  plcTotal: '--',
  faultCount: '--',
  condensationCount: '--',
  todayKwh: '--',
})

const plcText = computed(() => {
  if (dashData.value.plcOnline === '--') return '--'
  return `${dashData.value.plcOnline}/${dashData.value.plcTotal}`
})

const plcAlert = computed(() => {
  const online = dashData.value.plcOnline
  const total = dashData.value.plcTotal
  if (online === '--' || total === '--') return false
  return online < total
})

const currentDate = computed(() => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

async function fetchDashboard() {
  // user（业主）角色被后端 UserRoleApiGuardMiddleware 拦截所有 /api/dashboard/ 及管理端接口
  // （RBAC OQ-06，middleware.py）。勿发管理端请求，否则每次进首页触发 4 个 403。
  if (authStore.role === 'user') return
  errorMsg.value = ''
  try {
    const [plcRes, faultRes, summaryRes, condensationRes] = await Promise.allSettled([
      api.getDashboardPlcOnlineRate(),
      api.getDashboardFaultSummary(),
      api.getDashboardSummary(),
      api.getCondensationWarningCount(),
    ])

    if (plcRes.status === 'fulfilled' && plcRes.value?.data) {
      dashData.value.plcOnline = plcRes.value.data.online_count
      dashData.value.plcTotal = plcRes.value.data.total_count
    }

    if (faultRes.status === 'fulfilled' && faultRes.value?.data) {
      dashData.value.faultCount = faultRes.value.data.active_fault_count
    }

    if (summaryRes.status === 'fulfilled' && summaryRes.value?.data) {
      const kwh = summaryRes.value.data.today_kwh
      dashData.value.todayKwh = typeof kwh === 'number' ? kwh.toFixed(1) : kwh
    }

    // Condensation: DRF paginated response has top-level `count` field.
    // No dedicated dashboard endpoint — using list endpoint with page_size=1.
    if (condensationRes.status === 'fulfilled') {
      const d = condensationRes.value
      if (typeof d?.count === 'number') {
        dashData.value.condensationCount = d.count
      } else if (typeof d?.data?.count === 'number') {
        dashData.value.condensationCount = d.data.count
      } else {
        dashData.value.condensationCount = 0
      }
    }
  } catch (err) {
    errorMsg.value = '数据加载失败，请下拉刷新重试'
  }
}

const poller = new PagePoller(fetchDashboard, 30000)

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  poller.start()
})

onHide(() => {
  poller.stop()
})

onPullDownRefresh(async () => {
  await fetchDashboard()
  uni.stopPullDownRefresh()
})

// 已实现的 TabBar 页（须用 switchTab，不能 navigateTo）
const TAB_ROUTES = ['/pages/chat/index']
// 已实现的分包页/主包非 tab 页（用 navigateTo）
const NAV_ROUTES = [
  '/subpackages/monitor/pages/index',
  '/subpackages/energy/pages/index',
  '/subpackages/ops/pages/faults',
  '/subpackages/ops/pages/condensation',
  '/subpackages/ops/pages/workorders',
  '/subpackages/control/pages/param-settings',
  '/subpackages/game/pages/ark-poc',
  '/subpackages/game/pages/agent-scene',
  '/pages/profile/index',
]

function goTo(url) {
  if (TAB_ROUTES.includes(url)) {
    uni.switchTab({ url })
    return
  }
  if (NAV_ROUTES.includes(url)) {
    uni.navigateTo({ url })
    return
  }
  // 运维等分包尚未实现，给优雅提示而非导航失败
  uni.showToast({ title: '功能开发中，敬请期待', icon: 'none' })
}
</script>

<style scoped>
.home-page {
  padding: 24rpx;
  min-height: 100vh;
  background: #f5f5f5;
}
.header {
  background: #1a73e8;
  border-radius: 16rpx;
  padding: 32rpx;
  margin-bottom: 24rpx;
}
.header-title {
  display: block;
  font-size: 36rpx;
  font-weight: bold;
  color: #fff;
}
.header-subtitle {
  display: block;
  font-size: 24rpx;
  color: rgba(255,255,255,0.8);
  margin-top: 8rpx;
}
.section {
  margin-bottom: 24rpx;
}
.section-title {
  display: block;
  font-size: 28rpx;
  font-weight: bold;
  color: #333;
  margin-bottom: 16rpx;
}
.metrics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}
/* WXSS 不支持 > * 通配；用外层类 .metric-cell 控制每个卡片宽度（2 列） */
.metric-cell {
  flex: 1 1 calc(50% - 8rpx);
  min-width: 0;
}
.shortcuts-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}
.shortcut-tile {
  flex: 1 1 calc(50% - 8rpx);
  min-width: 0;
  background: #fff;
  border-radius: 16rpx;
  padding: 32rpx 24rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.08);
  position: relative;
}
.shortcut-icon {
  font-size: 48rpx;
  color: #1a73e8;
  font-weight: bold;
  margin-bottom: 12rpx;
}
.shortcut-label {
  font-size: 26rpx;
  color: #555;
}
.shortcut-badge {
  position: absolute;
  top: 16rpx;
  right: 16rpx;
  background: #f44336;
  color: #fff;
  font-size: 20rpx;
  border-radius: 20rpx;
  padding: 2rpx 10rpx;
  min-width: 32rpx;
  text-align: center;
}
.error-banner {
  background: #fff3cd;
  border-radius: 12rpx;
  padding: 16rpx 24rpx;
  text-align: center;
  color: #856404;
  font-size: 26rpx;
}
/* 业主端欢迎区（role=user，替代系统概览指标卡） */
.owner-welcome {
  background: #fff;
  border-radius: 16rpx;
  padding: 32rpx;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.08);
}
.owner-welcome-text {
  display: block;
  font-size: 30rpx;
  font-weight: bold;
  color: #333;
  margin-bottom: 12rpx;
}
.owner-welcome-sub {
  display: block;
  font-size: 26rpx;
  color: #888;
  line-height: 1.6;
}
</style>
