<!--
  @module MOD-BD-001 (was MOD-PAGE-HOME)
  @implements IFC-BD-001-01 through IFC-BD-001-10
  @depends MOD-BD-002 (useBridgeDashboard), MOD-BD-003 (useAnimationControl),
    MOD-BD-004~010 (ShipHull, SubsystemCompartment, RoomCompartment, FaultDrawer,
    HealthIndicator, PlcIndicator, CabinSwitcher), ArkTabBar, MetricCard, authStore
  @author sub_agent_software_developer
  @description Bridge dashboard page — role-based routing:
    - role=user (owner): Cyberpunk ship cross-section dashboard (v1.11.0 rewrite)
      showing fault/warning status only. No running parameters.
    - admin/operator: Material Design dashboard (PRESERVED AS-IS from original).
-->
<template>
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- OWNER PATH — v1.11.2 Bridge Dashboard (HOLO-HUD card layout)    -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <view v-if="isOwner" class="owner-page" :class="{ 'animations-paused': animationsPaused }">
    <!-- Background layers (consistent with 指挥/param-settings) -->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="hud-scan" />

    <!-- Status bar spacer (push content below system status bar + capsule) -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- Header: centered title (matching 指挥 page style) -->
    <view class="owner-header">
      <view class="header-spacer" />
      <text class="owner-title">舰桥</text>
      <view class="header-spacer" />
    </view>

    <!-- Top status bar: fault count | condensation | health LED | PLC -->
    <view class="top-status-bar">
      <view class="ts-item" :class="faultPillClass" @tap="onFaultPillTap">
        <text class="ts-num">{{ faultTotal }}</text>
        <text class="ts-label">故障</text>
      </view>
      <view class="ts-item" :class="condensationPillClass" @tap="onCondensationTap">
        <text class="ts-num">{{ dash.state.condensationCount }}</text>
        <text class="ts-label">结露</text>
      </view>
      <view class="ts-item ts-health" :class="healthPillClass">
        <view class="ts-led" />
        <text class="ts-label">{{ dash.state.overallStatus.text }}</text>
      </view>
      <view class="ts-item ts-plc" :class="plcPillClass">
        <text class="ts-num">{{ dash.state.plcOnline }}/{{ dash.state.plcTotal }}</text>
        <text class="ts-label">在线</text>
      </view>
    </view>

    <!-- Main content area -->
    <scroll-view scroll-y class="owner-content" :scroll-with-animation="true">
      <!-- Loading state -->
      <view v-if="dash.state.loading && !hasInitialData" class="owner-tip">
        <view class="sync-pulse" />
        <text>正在同步座舱状态…</text>
      </view>

      <!-- Empty state: no bindings -->
      <view v-else-if="dash.hasNoBindings.value" class="owner-empty">
        <view class="empty-frame">
          <view class="empty-glow" />
          <text class="empty-title">未链接座舱</text>
          <text class="empty-sub">链接座舱后可查看设备状态</text>
          <view class="empty-btn" @tap="goBind"><text>激活座舱</text></view>
        </view>
      </view>

      <!-- Main dashboard -->
      <view v-else class="dashboard">
        <!-- ── Section: 子系统状态 ── -->
        <view class="dash-section">
          <view class="section-head">
            <view class="section-bar" />
            <text class="section-label">SYS STATUS</text>
          </view>
          <view class="subsystem-grid">
            <SubsystemCompartment
              v-for="sub in dash.state.subsystems"
              :key="sub.id"
              :subsystem="sub"
              :animationsPaused="animationsPaused"
              @open="onCompartmentOpen"
            />
          </view>
        </view>

        <!-- ── Section: 房间状态 ── -->
        <view class="dash-section">
          <view class="section-head">
            <view class="section-bar" />
            <text class="section-label">ROOM STATUS</text>
          </view>
          <view class="room-grid">
            <RoomCompartment
              v-for="(room, index) in dash.state.rooms"
              :key="room.id"
              :room="room"
              :shapeIndex="index"
              :singleRoom="dash.state.rooms.length === 1"
              :animationsPaused="animationsPaused"
              @open="onCompartmentOpen"
            />
          </view>
        </view>

        <!-- Error banner -->
        <view v-if="dash.state.error" class="owner-error">
          <text>{{ dash.state.error }}</text>
        </view>

        <!-- Bottom spacer for tab bar -->
        <view style="height: 120rpx;" />
      </view>
    </scroll-view>

    <!-- Fault drawer (shows all device params read-only, replicating web system panel) -->
    <FaultDrawer
      :compartment="dash.state.activeCompartment"
      :visible="!!dash.state.activeCompartment"
      :faultEvents="dash.state.compartmentFaults"
      :deviceParams="dash.state.compartmentParams"
      @close="dash.closeCompartment()"
    />

    <!-- Tab bar -->
    <ArkTabBar active="home" />
  </view>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- ADMIN/OPERATOR PATH — PRESERVED EXACTLY AS-IS (lines 167-260)  -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <view v-else class="admin-page">
    <view :style="{ height: statusBarHeight + 'px' }" class="admin-status-spacer" />
    <scroll-view scroll-y class="admin-scroll">
      <view class="home-page">
        <view class="header">
          <text class="header-title">方舟舰桥</text>
          <text class="header-subtitle">{{ currentDate }}</text>
        </view>

        <view class="section">
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

        <view class="section">
          <text class="section-title">快捷入口</text>
          <view class="shortcuts-grid">
            <view class="shortcut-tile" @tap="goTo('/subpackages/ops/pages/faults')">
              <text class="shortcut-icon">!</text>
              <text class="shortcut-label">故障管理</text>
              <view
                v-if="typeof dashData.faultCount === 'number' && dashData.faultCount > 0"
                class="shortcut-badge"
              >{{ dashData.faultCount }}</view>
            </view>
            <view class="shortcut-tile" @tap="goTo('/subpackages/ops/pages/condensation')">
              <text class="shortcut-icon">~</text>
              <text class="shortcut-label">结露预警</text>
            </view>
            <view class="shortcut-tile" @tap="goTo('/pages/chat/index')">
              <text class="shortcut-icon">AI</text>
              <text class="shortcut-label">方舟智能体</text>
            </view>
            <view class="shortcut-tile" @tap="goTo('/subpackages/game/pages/ark-poc')">
              <text class="shortcut-icon">⬢</text>
              <text class="shortcut-label">方舟座舱</text>
            </view>
            <view class="shortcut-tile" @tap="goTo('/subpackages/game/pages/agent-scene')">
              <text class="shortcut-icon">⊙</text>
              <text class="shortcut-label">智能体座舱</text>
            </view>
            <view class="shortcut-tile" @tap="goTo('/subpackages/monitor/pages/index')">
              <text class="shortcut-icon">M</text>
              <text class="shortcut-label">设备监控</text>
            </view>
            <view class="shortcut-tile" @tap="goTo('/subpackages/energy/pages/index')">
              <text class="shortcut-icon">E</text>
              <text class="shortcut-label">能耗报表</text>
            </view>
            <view class="shortcut-tile" @tap="goTo('/subpackages/ops/pages/workorders')">
              <text class="shortcut-icon">W</text>
              <text class="shortcut-label">巡检工单</text>
            </view>
            <view class="shortcut-tile" @tap="goTo('/pages/profile/index')">
              <text class="shortcut-icon">U</text>
              <text class="shortcut-label">个人中心</text>
            </view>
          </view>
        </view>

        <view v-if="errorMsg" class="error-banner">
          <text>{{ errorMsg }}</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
// ── Core imports ────────────────────────────────────────────
import { ref, computed } from 'vue'
import { onShow, onHide, onPullDownRefresh } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'

// ── Owner (role=user) imports ──────────────────────────────
import { useBridgeDashboard } from '@/composables/useBridgeDashboard'
import { useAnimationControl } from '@/composables/useAnimationControl'

// ── Admin/operator imports ─────────────────────────────────
import { api } from '@/utils/api'
import { PagePoller } from '@/utils/poller'
import MetricCard from '@/components/MetricCard.vue'

// ── Shared imports ──────────────────────────────────────────
import ArkTabBar from '@/components/ArkTabBar.vue'

// ── Owner component imports ────────────────────────────────
import SubsystemCompartment from '@/components/SubsystemCompartment.vue'
import RoomCompartment from '@/components/RoomCompartment.vue'
import FaultDrawer from '@/components/FaultDrawer.vue'

// ═══════════════════════════════════════════════════════════════
// SETUP — shared
// ═══════════════════════════════════════════════════════════════

const authStore = useAuthStore()
const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

if (!authStore.isLoggedIn) {
  uni.reLaunch({ url: '/pages/login/index' })
}

const isOwner = computed(() => authStore.role === 'user')

// ═══════════════════════════════════════════════════════════════
// OWNER COMPOSABLES (v1.11.0 bridge dashboard)
// ═══════════════════════════════════════════════════════════════

const dash = useBridgeDashboard()
const anim = useAnimationControl()
const { animationsPaused } = anim

/** True when there is initial data already rendered (prevents loading flicker during refresh). */
const hasInitialData = computed(() =>
  dash.state.subsystems.length > 0 || dash.state.rooms.length > 0
)

/** Total fault count across subsystems + rooms. */
const faultTotal = computed(() => {
  let total = 0
  for (const s of dash.state.subsystems) total += (s.faultCount || 0)
  for (const r of dash.state.rooms) total += (r.faultCount || 0)
  return total
})

/** Top status pill classes. */
const faultPillClass = computed(() => faultTotal.value > 0 ? 'ts-fault' : 'ts-ok')
const condensationPillClass = computed(() => dash.state.condensationCount > 0 ? 'ts-warn' : 'ts-ok')
const healthPillClass = computed(() => `ts-${dash.state.overallStatus.level}`)
const plcPillClass = computed(() => {
  if (dash.state.loading) return 'ts-idle'
  if (dash.state.plcTotal === 0) return 'ts-idle'
  if (dash.state.plcOnline === dash.state.plcTotal) return 'ts-ok'
  if (dash.state.plcOnline > 0) return 'ts-warn'
  return 'ts-fault'
})

/** Compartment open event. */
function onCompartmentOpen(compartment) {
  dash.openCompartment(compartment)
}

/** Fault pill tap → open first fault room. */
function onFaultPillTap() {
  const room = dash.state.rooms.find(r => r.faultCount > 0)
  if (room) {
    dash.openCompartment(room)
  }
}

/** Condensation tap → open first room with condensation. */
function onCondensationTap() {
  const room = dash.state.rooms.find(r => r.hasCondensation)
  if (room) {
    dash.openCompartment(room)
  }
}

function goBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}

// ═══════════════════════════════════════════════════════════════
// ADMIN/OPERATOR DASHBOARD (PRESERVED AS-IS)
// ═══════════════════════════════════════════════════════════════

const errorMsg = ref('')
const dashData = ref({
  plcOnline: '--',
  plcTotal: '--',
  faultCount: '--',
  condensationCount: '--',
  todayKwh: '--',
})

// admin dashboard 内存缓存（5 分钟有效），避免每次 onShow 重复请求
let _dashCache = null
let _dashCacheTs = 0
const DASH_CACHE_TTL = 5 * 60 * 1000

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

async function fetchDashboard(force = false) {
  if (authStore.role === 'user') return
  const now = Date.now()
  if (!force && _dashCache && (now - _dashCacheTs) < DASH_CACHE_TTL) {
    dashData.value = { ..._dashCache }
    return
  }
  errorMsg.value = ''
  try {
    const [plcRes, faultRes, summaryRes, condensationRes] = await Promise.allSettled([
      api.getDashboardPlcOnlineRate(),
      api.getDashboardFaultSummary(),
      api.getDashboardSummary(),
      api.getCondensationWarningCount(),
    ])

    const next = { ...dashData.value }

    if (plcRes.status === 'fulfilled' && plcRes.value?.data) {
      next.plcOnline = plcRes.value.data.online_count
      next.plcTotal = plcRes.value.data.total_count
    }

    if (faultRes.status === 'fulfilled' && faultRes.value?.data) {
      next.faultCount = faultRes.value.data.active_fault_count
    }

    if (summaryRes.status === 'fulfilled' && summaryRes.value?.data) {
      const kwh = summaryRes.value.data.today_kwh
      next.todayKwh = typeof kwh === 'number' ? kwh.toFixed(1) : kwh
    }

    if (condensationRes.status === 'fulfilled') {
      const d = condensationRes.value
      if (typeof d?.count === 'number') {
        next.condensationCount = d.count
      } else if (typeof d?.data?.count === 'number') {
        next.condensationCount = d.data.count
      } else {
        next.condensationCount = 0
      }
    }

    dashData.value = next
    _dashCache = { ...next }
    _dashCacheTs = now
  } catch (err) {
    errorMsg.value = '数据加载失败，请下拉刷新重试'
  }
}

const adminPoller = new PagePoller(fetchDashboard, 30000)

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }

  if (authStore.role === 'user') {
    uni.hideTabBar({ animation: false, fail: () => {} })
    dash.start()
    anim.onShow()
  } else {
    uni.showTabBar({ animation: false, fail: () => {} })
    try { uni.setNavigationBarColor({ frontColor: '#ffffff', backgroundColor: '#1a73e8' }) } catch (e) {}
    adminPoller.stop()
    adminPoller.start()
  }
})

onHide(() => {
  dash.stop()
  adminPoller.stop()
  anim.onHide()
})

onPullDownRefresh(async () => {
  if (authStore.role === 'user') {
    await dash.refresh(true)
  } else {
    await fetchDashboard(true)
  }
  uni.stopPullDownRefresh()
})

// ── Admin navigation ──────────────────────────────────────

const TAB_ROUTES = ['/pages/chat/index']
const NAV_ROUTES = [
  '/subpackages/monitor/pages/index',
  '/subpackages/energy/pages/index',
  '/subpackages/ops/pages/faults',
  '/subpackages/ops/pages/condensation',
  '/subpackages/ops/pages/workorders',
  '/pages/device/param-settings',
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
  uni.showToast({ title: '功能开发中，敬请期待', icon: 'none' })
}
</script>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- STYLES: Owner (v1.11.2 HOLO-HUD card dashboard)                 -->
<!-- ═══════════════════════════════════════════════════════════════ -->
<style scoped>
/* ── Page base ──────────────────────────────────────────── */
.owner-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070f;
  overflow: hidden;
}

/* ── Background layers ──────────────────────────────────── */
.bg-base,
.bg-grid,
.hud-scan {
  position: absolute;
  pointer-events: none;
}

.bg-base {
  inset: 0;
  background:
    radial-gradient(ellipse 70% 60% at 50% 30%, rgba(47, 100, 244, 0.08), transparent),
    radial-gradient(ellipse 50% 40% at 80% 70%, rgba(124, 58, 237, 0.06), transparent),
    linear-gradient(180deg, #05070f, #07101c 60%, #050811);
}

.bg-grid {
  inset: 0;
  background-image:
    linear-gradient(rgba(56, 230, 224, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 230, 224, 0.05) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000 20%, transparent 80%);
  mask-image: linear-gradient(180deg, #000 20%, transparent 80%);
}

.hud-scan {
  left: 0;
  right: 0;
  top: 0;
  height: 260rpx;
  z-index: 1;
  background: linear-gradient(180deg, transparent, rgba(47, 244, 224, 0.07), transparent);
  animation: ownerScan 5s linear infinite;
}

.status-spacer {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
}

/* ── Header (centered, matching 指挥/副官 page) ─────────── */
.owner-header {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  height: 88rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-spacer {
  width: 180rpx; /* offset to center the title accounting for capsule buttons on right */
  flex: 0 0 auto;
}

.owner-title {
  flex: 1;
  text-align: center;
  font-size: 34rpx;
  font-weight: 700;
  letter-spacing: 8rpx;
  color: #f4fbff;
  text-shadow: 0 0 12rpx rgba(56, 230, 224, 0.50);
}

/* ── Top status bar ─────────────────────────────────────── */
.top-status-bar {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  display: flex;
  gap: 12rpx;
  padding: 2rpx 22rpx 14rpx;
}

.ts-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4rpx;
  padding: 12rpx 6rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.14);
  background: rgba(7, 15, 32, 0.60);
}

.ts-num {
  font-size: 26rpx;
  font-weight: 800;
  color: #eaf6ff;
  letter-spacing: 2rpx;
}

.ts-label {
  font-size: 18rpx;
  color: #6f8cad;
}

.ts-led {
  width: 14rpx;
  height: 14rpx;
  background: #5f7da6;
  transform: rotate(45deg);
  margin-bottom: 2rpx;
}

/* Status pill colors */
.ts-ok { border-color: rgba(39, 245, 181, 0.22); }
.ts-ok .ts-num { color: #27f5b5; }
.ts-ok .ts-led { background: #27f5b5; box-shadow: 0 0 8rpx rgba(39, 245, 181, 0.6); }

.ts-warn { border-color: rgba(255, 212, 0, 0.36); }
.ts-warn .ts-num { color: #ffd400; }
.ts-warn .ts-led { background: #ffd400; box-shadow: 0 0 8rpx rgba(255, 212, 0, 0.6); }

.ts-fault { border-color: rgba(255, 49, 93, 0.44); animation: pillFaultGlow 1.4s ease-in-out infinite; }
.ts-fault .ts-num { color: #ff315d; }
.ts-fault .ts-led { background: #ff315d; box-shadow: 0 0 10rpx rgba(255, 49, 93, 0.7); }

.ts-idle { opacity: 0.45; }
.ts-idle .ts-num { color: #5f7da6; }

@keyframes pillFaultGlow {
  0%, 100% { border-color: rgba(255, 49, 93, 0.44); }
  50% { border-color: rgba(255, 49, 93, 0.72); }
}

/* ── Content scroll ─────────────────────────────────────── */
.owner-content {
  position: relative;
  z-index: 4;
  flex: 1 1 0;
  min-height: 0;
}

/* ── Loading ────────────────────────────────────────────── */
.owner-tip {
  padding: 200rpx 36rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24rpx;
}

.owner-tip text {
  font-size: 26rpx;
  color: rgba(180, 212, 238, 0.65);
}

.sync-pulse {
  width: 48rpx;
  height: 48rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.4);
  border-top-color: #2ff4e0;
  border-radius: 50%;
  animation: spinSync 0.9s linear infinite;
}

@keyframes spinSync {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* ── Empty state ────────────────────────────────────────── */
.owner-empty {
  padding: 180rpx 36rpx;
  text-align: center;
}

.empty-frame {
  position: relative;
  padding: 50rpx 34rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.18);
  background: rgba(6, 12, 28, 0.72);
  overflow: hidden;
}

.empty-glow {
  position: absolute;
  top: -60rpx;
  left: 50%;
  transform: translateX(-50%);
  width: 200rpx;
  height: 80rpx;
  background: radial-gradient(ellipse, rgba(47, 244, 224, 0.12), transparent);
  pointer-events: none;
}

.empty-title {
  display: block;
  font-size: 32rpx;
  color: #f4fbff;
  font-weight: 700;
}

.empty-sub {
  display: block;
  margin-top: 14rpx;
  font-size: 24rpx;
  color: #6f8cad;
}

.empty-btn {
  margin: 34rpx auto 0;
  width: 210rpx;
  padding: 18rpx 0;
  background: linear-gradient(90deg, #2ff4e0, #7c3aed);
}

.empty-btn text {
  font-size: 26rpx;
  color: #04121f;
  font-weight: 700;
}

/* ── Dashboard ──────────────────────────────────────────── */
.dashboard {
  padding: 0 22rpx;
}

.dash-section {
  margin-bottom: 18rpx;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 8rpx 4rpx 14rpx;
}

.section-bar {
  width: 5rpx;
  height: 22rpx;
  background: linear-gradient(180deg, #2ff4e0, #7c3aed);
  border-radius: 2rpx;
}

.section-label {
  font-size: 22rpx;
  font-weight: 700;
  color: rgba(143, 217, 255, 0.58);
  letter-spacing: 4rpx;
}

/* ── Subsystem grid (2x2) ───────────────────────────────── */
.subsystem-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14rpx;
}

/* ── Room grid (2 columns) ──────────────────────────────── */
.room-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14rpx;
}

/* ── Error banner ───────────────────────────────────────── */
.owner-error {
  margin: 18rpx 0 0;
  padding: 16rpx 20rpx;
  background: rgba(255, 212, 0, 0.08);
  border-left: 4rpx solid #ffd400;
}

.owner-error text {
  font-size: 24rpx;
  color: #ffe28a;
}

/* ── Animations paused ──────────────────────────────────── */
.animations-paused .hud-scan,
.animations-paused .ts-fault {
  animation-play-state: paused;
}

/* ── Keyframes ──────────────────────────────────────────── */
@keyframes ownerScan {
  0% { transform: translateY(-260rpx); }
  100% { transform: translateY(1700rpx); }
}
</style>

/* ═══════════════════════════════════════════════════════════════ */
<!-- STYLES: Admin/Operator (PRESERVED AS-IS) -->
<style scoped>
/* ═══════════════════════════════════════════════════════════════ */

.admin-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}
.admin-status-spacer {
  flex: 0 0 auto;
  background: #1a73e8;
}
.admin-scroll {
  flex: 1 1 0;
  min-height: 0;
}
.home-page {
  padding: 24rpx;
  min-height: 100%;
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
</style>
