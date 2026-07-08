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
  <!-- OWNER PATH — v1.11.0 Bridge Dashboard (cyberpunk ship)          -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <view v-if="isOwner" class="owner-page" :class="{ 'animations-paused': animationsPaused }">
    <!-- Background layers -->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="hud-scan" />

    <!-- Status bar spacer -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- Header: title + health indicator -->
    <view class="owner-header">
      <view class="owner-title-box">
        <text class="owner-title">方舟舰桥</text>
        <text class="owner-subtitle">{{ dash.state.selectedLabel || '等待数据' }}</text>
      </view>
      <HealthIndicator
        :status="dash.state.overallStatus"
        :condensationCount="dash.state.condensationCount"
      />
    </view>

    <!-- Main content area -->
    <scroll-view scroll-y class="owner-content">
      <!-- Cockpit switcher (shown when multiple bindings) -->
      <CabinSwitcher
        :bindings="dash.state.bindings"
        :selectedIndex="dash.selectedBindingIndex.value"
        :visible="dash.showCabinSwitcher.value"
        @change="onCabinChange"
      />

      <!-- Loading state -->
      <view v-if="dash.state.loading && !hasInitialData" class="owner-tip">
        <text>正在同步方舟舱图…</text>
      </view>

      <!-- Empty state: no bindings -->
      <view v-else-if="dash.hasNoBindings.value" class="owner-empty">
        <view class="empty-frame">
          <text class="empty-title">未链接座舱</text>
          <text class="empty-sub">链接座舱后可查看方舟户型舱图</text>
          <view class="empty-btn" @tap="goBind"><text>激活座舱</text></view>
        </view>
      </view>

      <!-- Main dashboard: ship + compartments -->
      <view v-else class="ark-deck">
        <!-- Deck ribbon -->
        <view class="deck-ribbon">
          <text>{{ dash.state.selectedSp || '—' }}</text>
          <text>{{ dash.state.refreshing ? 'SYNC' : 'LIVE' }}</text>
        </view>

        <!-- Ship hull container -->
        <ShipHull :status="dash.state.overallStatus.level" :animationsPaused="animationsPaused">
          <!-- Subsystem dock -->
          <view class="system-dock">
            <SubsystemCompartment
              v-for="sub in dash.state.subsystems"
              :key="sub.id"
              :subsystem="sub"
              :animationsPaused="animationsPaused"
              @open="onCompartmentOpen"
            />
          </view>

          <!-- Ship spine (power flow) -->
          <view class="ship-spine">
            <view class="spine-line">
              <view class="spine-flow" />
            </view>
            <view class="spine-dot sd1" />
            <view class="spine-dot sd2" />
            <view class="spine-dot sd3" />
          </view>

          <!-- Room grid -->
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
        </ShipHull>

        <!-- PLC indicator (standalone, outside ship hull) -->
        <PlcIndicator
          :onlineCount="dash.state.plcOnline"
          :totalCount="dash.state.plcTotal"
          :loading="dash.state.loading"
        />

        <!-- Error banner -->
        <view v-if="dash.state.error" class="owner-error">
          <text>{{ dash.state.error }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- Fault drawer (page-level, outside scroll-view for fixed positioning) -->
    <FaultDrawer
      :compartment="dash.state.activeCompartment"
      :visible="!!dash.state.activeCompartment"
      @close="dash.closeCompartment()"
    />

    <!-- Tab bar (existing, unchanged) -->
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
import HealthIndicator from '@/components/HealthIndicator.vue'
import PlcIndicator from '@/components/PlcIndicator.vue'
import CabinSwitcher from '@/components/CabinSwitcher.vue'
import ShipHull from '@/components/ShipHull.vue'
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

/** IFC-BD-001-07/08: Compartment open event from subsystem or room. */
function onCompartmentOpen(compartment) {
  dash.openCompartment(compartment)
}

/** IFC-BD-001-10: Cockpit switch. */
function onCabinChange(index) {
  const sp = dash.state.bindings[index]?.specific_part
  if (sp) {
    dash.switchCockpit(sp)
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
<!-- STYLES: Owner (v1.11.0 bridge dashboard)                        -->
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
    linear-gradient(135deg, rgba(43, 21, 77, 0.8), rgba(5, 12, 24, 0.92) 44%, rgba(4, 18, 28, 0.96)),
    linear-gradient(180deg, #05070f, #07101c 60%, #050811);
}

.bg-grid {
  inset: 0;
  background-image:
    linear-gradient(rgba(56, 230, 224, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 230, 224, 0.06) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 70%);
  mask-image: linear-gradient(180deg, #000, transparent 70%);
}

.hud-scan {
  left: 0;
  right: 0;
  top: 0;
  height: 260rpx;
  z-index: 1;
  background: linear-gradient(180deg, transparent, rgba(47, 244, 224, 0.10), transparent);
  animation: ownerScan 5s linear infinite;
}

/* ── Status spacer ──────────────────────────────────────── */
.status-spacer {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
}

/* ── Header ─────────────────────────────────────────────── */
.owner-header {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  min-height: 122rpx;
  padding: 18rpx 28rpx 10rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.owner-title-box {
  min-width: 0;
  flex: 1;
  margin-right: 16rpx;
}

.owner-title {
  display: block;
  font-size: 36rpx;
  font-weight: 800;
  color: #f4fbff;
  text-shadow: 0 0 16rpx rgba(47, 244, 224, 0.55);
}

.owner-subtitle {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  color: rgba(180, 212, 238, 0.72);
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Content scroll ─────────────────────────────────────── */
.owner-content {
  position: relative;
  z-index: 4;
  flex: 1 1 0;
  min-height: 0;
}

/* ── Loading / Empty / Error states ─────────────────────── */
.owner-tip,
.owner-empty {
  padding: 140rpx 36rpx;
  text-align: center;
}

.owner-tip text {
  font-size: 28rpx;
  color: rgba(180, 212, 238, 0.70);
}

.empty-frame {
  padding: 50rpx 34rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.25);
  background: rgba(6, 12, 28, 0.78);
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
  font-size: 26rpx;
  color: #8aa2c0;
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

/* ── Ark deck (main dashboard area) ─────────────────────── */
.ark-deck {
  padding: 18rpx 22rpx 26rpx;
}

.deck-ribbon {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12rpx 8rpx 14rpx;
}

.deck-ribbon text {
  font-size: 20rpx;
  color: rgba(143, 217, 255, 0.64);
}

/* ── System dock ────────────────────────────────────────── */
.system-dock {
  display: flex;
  gap: 10rpx;
  align-items: stretch;
  justify-content: center;
  margin: 12rpx 16rpx 20rpx;
}

/* ── Ship spine ─────────────────────────────────────────── */
.ship-spine {
  position: relative;
  height: 28rpx;
  margin: 0 54rpx;
  overflow: hidden;
}

.spine-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 13rpx;
  height: 2rpx;
  background: rgba(47, 244, 224, 0.28);
}

.spine-flow {
  position: absolute;
  top: -2rpx;
  width: 120rpx;
  height: 6rpx;
  background: linear-gradient(90deg, transparent, rgba(47, 244, 224, 0.9), transparent);
  animation: powerFlow 2.8s linear infinite;
}

.spine-dot {
  position: absolute;
  top: 8rpx;
  width: 12rpx;
  height: 12rpx;
  background: #2ff4e0;
  transform: rotate(45deg);
  animation: pulseSoft 1.8s ease-in-out infinite;
}

.sd1 { left: 18%; }
.sd2 { left: 50%; animation-delay: 0.4s; }
.sd3 { left: 82%; animation-delay: 0.8s; }

/* ── Room grid ──────────────────────────────────────────── */
.room-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 14rpx;
  margin: 12rpx 10rpx 14rpx;
}

/* ── Error banner ───────────────────────────────────────── */
.owner-error {
  margin: 18rpx 10rpx 0;
  padding: 16rpx 20rpx;
  background: rgba(255, 212, 0, 0.08);
  border-left: 4rpx solid #ffd400;
}

.owner-error text {
  font-size: 24rpx;
  color: #ffe28a;
}

/* ── CSS Keyframes (reused from existing, preserved) ────── */
@keyframes ownerScan {
  0% { transform: translateY(-260rpx); }
  100% { transform: translateY(1700rpx); }
}

@keyframes pulseSoft {
  0%, 100% { opacity: 0.65; }
  50% { opacity: 1; }
}

@keyframes powerFlow {
  0% { transform: translateX(-120rpx); opacity: 0; }
  20%, 80% { opacity: 1; }
  100% { transform: translateX(520rpx); opacity: 0; }
}

@keyframes fanSpin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes damageBlink {
  0%, 100% { opacity: 0.48; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.12); }
}

@keyframes enginePulse {
  0%, 100% { box-shadow: 0 0 14rpx rgba(47, 244, 224, 0.45); }
  50% { box-shadow: 0 0 30rpx rgba(47, 244, 224, 0.85); }
}

/* ═══════════════════════════════════════════════════════════════ */
/* STYLES: Admin/Operator (PRESERVED AS-IS from lines 1348-1451)  */
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
