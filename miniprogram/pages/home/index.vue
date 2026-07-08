<!--
  @module MOD-BD-001 (was MOD-PAGE-HOME)
  @implements IFC-BD-001-01 through IFC-BD-001-10
  @depends MOD-BD-002 (useBridgeDashboard), MOD-BD-003 (useAnimationControl),
    MOD-BD-005~007 (SubsystemCompartment, RoomCompartment, FaultDrawer),
    ArkTabBar, MetricCard, authStore
  @author sub_agent_software_developer
  @description Bridge dashboard page — role-based routing:
    - role=user (owner): Cyberpunk HOLO-HUD dashboard (v1.11.3)
      showing fault/warning status + connectivity indicators. No running parameters.
    - admin/operator: Material Design dashboard (PRESERVED AS-IS from original).
-->
<template>
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- OWNER PATH — v1.11.3 Bridge Dashboard (HOLO-HUD card layout)    -->
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

    <!-- Top connectivity bar: PLC neural link + Cockpit screen link -->
    <view class="top-conn-bar">
      <!-- PLC: 接驳方舟神经网络 -->
      <view class="conn-item" :class="connPlcClass">
        <view class="conn-led" :class="connPlcLedClass" />
        <view class="conn-body">
          <text class="conn-label">接驳方舟神经网络</text>
          <text class="conn-status">{{ connPlcLabel }}</text>
        </view>
      </view>
      <!-- Screen: 链接座舱 -->
      <view class="conn-item" :class="connScreenClass">
        <view class="conn-led" :class="connScreenLedClass" />
        <view class="conn-body">
          <text class="conn-label">链接座舱</text>
          <text class="conn-status">{{ connScreenLabel }}</text>
        </view>
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
          <view class="section-head" :class="sysSectionGlowClass">
            <view class="section-bar" :class="sysBarClass" />
            <text class="section-label" :class="sysLabelClass">SYS STATUS</text>
            <view class="section-scan-line" />
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

        <!-- ── Section: 威胁仪表 (fault + condensation gauges) ── -->
        <view class="dash-section gauge-section">
          <view class="section-head">
            <view class="section-bar gauge-bar" />
            <text class="section-label gauge-label">THREAT BOARD</text>
            <view class="section-scan-line" />
          </view>
          <view class="gauge-row">
            <!-- Fault gauge -->
            <view class="gauge-card" :class="faultGaugeClass" @tap="onFaultGaugeTap">
              <view class="gauge-ring">
                <view class="gauge-ring-inner">
                  <text class="gauge-num">{{ faultTotal }}</text>
                </view>
                <view class="gauge-ring-arc" :class="faultGaugeArcClass" />
              </view>
              <text class="gauge-label-text">系统故障</text>
              <view v-if="faultTotal > 0" class="gauge-sparks">
                <view class="gauge-spark gs1" />
                <view class="gauge-spark gs2" />
              </view>
            </view>
            <!-- Condensation gauge -->
            <view class="gauge-card" :class="condGaugeClass" @tap="onCondGaugeTap">
              <view class="gauge-ring">
                <view class="gauge-ring-inner">
                  <text class="gauge-num">{{ dash.state.condensationCount }}</text>
                </view>
                <view class="gauge-ring-arc" :class="condGaugeArcClass" />
              </view>
              <text class="gauge-label-text">结露预警</text>
              <view v-if="dash.state.condensationCount > 0" class="gauge-sparks">
                <view class="gauge-spark gs1" />
                <view class="gauge-spark gs2" />
              </view>
            </view>
          </view>
        </view>

        <!-- ── Section: 房间状态 ── -->
        <view class="dash-section">
          <view class="section-head" :class="roomSectionGlowClass">
            <view class="section-bar" :class="roomBarClass" />
            <text class="section-label" :class="roomLabelClass">ROOM STATUS</text>
            <view class="section-scan-line" />
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
  <!-- ADMIN/OPERATOR PATH — PRESERVED EXACTLY AS-IS                    -->
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
// OWNER COMPOSABLES (v1.11.3 bridge dashboard)
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

// ── Connectivity indicators (v1.11.3) ──────────────────────

/** PLC connectivity status → CSS class. */
const connPlcClass = computed(() => {
  const s = dash.state.plcCockpitStatus
  if (s === 'online') return 'conn-online'
  if (s === 'offline') return 'conn-offline'
  return 'conn-unknown'
})

const connPlcLedClass = computed(() => {
  const s = dash.state.plcCockpitStatus
  if (s === 'online') return 'led-online'
  if (s === 'offline') return 'led-offline'
  return 'led-unknown'
})

const connPlcLabel = computed(() => {
  const s = dash.state.plcCockpitStatus
  if (s === 'online') return '已接驳'
  if (s === 'offline') return '断开'
  return '扫描中'
})

/** Screen connectivity status → CSS class. */
const connScreenClass = computed(() => {
  const s = dash.state.screenCockpitStatus
  if (s === 'online') return 'conn-online'
  if (s === 'offline') return 'conn-offline'
  return 'conn-unknown'
})

const connScreenLedClass = computed(() => {
  const s = dash.state.screenCockpitStatus
  if (s === 'online') return 'led-online'
  if (s === 'offline') return 'led-offline'
  return 'led-unknown'
})

const connScreenLabel = computed(() => {
  const s = dash.state.screenCockpitStatus
  if (s === 'online') return '已链接'
  if (s === 'offline') return '断链'
  return '搜索中'
})

// ── Section title color classes (neon, status-driven) ──────

function worstSectionStatus(items) {
  let worst = 'normal'
  let hasItems = false
  for (const item of items) {
    hasItems = true
    if (item.status === 'fault') return 'fault'
    if (item.status === 'warning') worst = 'warning'
    else if (item.status === 'idle' && worst === 'normal') worst = 'idle'
  }
  if (!hasItems) return 'idle'
  return worst
}

const sysSectionStatus = computed(() => worstSectionStatus(dash.state.subsystems))
const roomSectionStatus = computed(() => worstSectionStatus(dash.state.rooms))

const sysSectionGlowClass = computed(() => `head-${sysSectionStatus.value}`)
const sysBarClass = computed(() => `bar-${sysSectionStatus.value}`)
const sysLabelClass = computed(() => `label-${sysSectionStatus.value}`)

const roomSectionGlowClass = computed(() => `head-${roomSectionStatus.value}`)
const roomBarClass = computed(() => `bar-${roomSectionStatus.value}`)
const roomLabelClass = computed(() => `label-${roomSectionStatus.value}`)

// ── Gauge classes ──────────────────────────────────────────

const faultGaugeClass = computed(() => faultTotal.value > 0 ? 'gauge-fault' : 'gauge-ok')
const faultGaugeArcClass = computed(() => faultTotal.value > 0 ? 'arc-fault' : 'arc-ok')

const condGaugeClass = computed(() => dash.state.condensationCount > 0 ? 'gauge-warn' : 'gauge-ok')
const condGaugeArcClass = computed(() => dash.state.condensationCount > 0 ? 'arc-warn' : 'arc-ok')

/** Compartment open event. */
function onCompartmentOpen(compartment) {
  dash.openCompartment(compartment)
}

/** Fault gauge tap → open first fault room. */
function onFaultGaugeTap() {
  const room = dash.state.rooms.find(r => r.faultCount > 0)
  if (room) {
    dash.openCompartment(room)
  }
}

/** Condensation gauge tap → open first room with condensation. */
function onCondGaugeTap() {
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
<!-- STYLES: Owner (v1.11.3 HOLO-HUD card dashboard)                 -->
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
  width: 180rpx;
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

/* ── Top connectivity bar (v1.11.3) ──────────────────────── */
.top-conn-bar {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  display: flex;
  gap: 16rpx;
  padding: 4rpx 22rpx 12rpx;
}

.conn-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10rpx;
  padding: 10rpx 14rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.12);
  background: rgba(5, 10, 22, 0.70);
  position: relative;
  overflow: hidden;
}

/* LED diamond */
.conn-led {
  width: 16rpx;
  height: 16rpx;
  transform: rotate(45deg);
  flex-shrink: 0;
}

.led-online {
  background: #27f5b5;
  box-shadow: 0 0 12rpx rgba(39, 245, 181, 0.8), 0 0 28rpx rgba(39, 245, 181, 0.3);
  animation: ledPulse 2s ease-in-out infinite;
}

.led-offline {
  background: #ff315d;
  box-shadow: 0 0 12rpx rgba(255, 49, 93, 0.7), 0 0 28rpx rgba(255, 49, 93, 0.2);
}

.led-unknown {
  background: #5f7da6;
  box-shadow: 0 0 6rpx rgba(95, 125, 166, 0.3);
  animation: ledScan 1.5s ease-in-out infinite;
}

@keyframes ledPulse {
  0%, 100% { box-shadow: 0 0 12rpx rgba(39, 245, 181, 0.8); }
  50% { box-shadow: 0 0 24rpx rgba(39, 245, 181, 1.0), 0 0 40rpx rgba(39, 245, 181, 0.4); }
}

@keyframes ledScan {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

.conn-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2rpx;
}

.conn-label {
  font-size: 20rpx;
  font-weight: 600;
  color: #8fd9ff;
  letter-spacing: 2rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conn-status {
  font-size: 18rpx;
  color: #6f8cad;
}

/* Conn status variations */
.conn-online { border-color: rgba(39, 245, 181, 0.25); }
.conn-online .conn-status { color: #27f5b5; }

.conn-offline { border-color: rgba(255, 49, 93, 0.35); animation: connFaultGlow 2s ease-in-out infinite; }
.conn-offline .conn-status { color: #ff315d; }

.conn-unknown { opacity: 0.55; }

@keyframes connFaultGlow {
  0%, 100% { border-color: rgba(255, 49, 93, 0.35); }
  50% { border-color: rgba(255, 49, 93, 0.65); }
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
  margin-bottom: 22rpx;
}

/* ── Section heads (v1.11.3: larger, neon color-coded, animated) ── */
.section-head {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 6rpx 4rpx 16rpx;
  position: relative;
}

.section-bar {
  width: 6rpx;
  height: 32rpx;
  border-radius: 3rpx;
  flex-shrink: 0;
  transition: background 0.6s ease;
}

/* Bar colors by status */
.bar-normal { background: linear-gradient(180deg, #27f5b5, #0f9b7a); box-shadow: 0 0 12rpx rgba(39, 245, 181, 0.5); }
.bar-warning { background: linear-gradient(180deg, #ffd400, #b89400); box-shadow: 0 0 12rpx rgba(255, 212, 0, 0.5); }
.bar-fault { background: linear-gradient(180deg, #ff315d, #b8002d); box-shadow: 0 0 14rpx rgba(255, 49, 93, 0.6); animation: barFaultBlink 0.8s ease-in-out infinite; }
.bar-idle { background: linear-gradient(180deg, #5f7da6, #3a506b); box-shadow: none; opacity: 0.5; }

@keyframes barFaultBlink {
  0%, 100% { box-shadow: 0 0 14rpx rgba(255, 49, 93, 0.6); }
  50% { box-shadow: 0 0 28rpx rgba(255, 49, 93, 1.0); }
}

.section-label {
  font-size: 28rpx;
  font-weight: 800;
  letter-spacing: 6rpx;
  transition: color 0.6s ease, text-shadow 0.6s ease;
}

/* Label colors by status */
.label-normal { color: #27f5b5; text-shadow: 0 0 16rpx rgba(39, 245, 181, 0.6); }
.label-warning { color: #ffd400; text-shadow: 0 0 16rpx rgba(255, 212, 0, 0.6); }
.label-fault { color: #ff315d; text-shadow: 0 0 18rpx rgba(255, 49, 93, 0.7); animation: labelFaultBlink 1s ease-in-out infinite; }
.label-idle { color: #5f7da6; text-shadow: none; }

@keyframes labelFaultBlink {
  0%, 100% { text-shadow: 0 0 18rpx rgba(255, 49, 93, 0.7); }
  50% { text-shadow: 0 0 32rpx rgba(255, 49, 93, 1.0); }
}

/* Scan line animation behind section title */
.section-scan-line {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 13rpx;
  height: 1rpx;
  background: linear-gradient(90deg, transparent, rgba(47, 244, 224, 0.2), transparent);
  pointer-events: none;
  opacity: 0;
}

.head-fault .section-scan-line {
  opacity: 1;
  background: linear-gradient(90deg, transparent, rgba(255, 49, 93, 0.4), transparent);
  animation: scanLineSweep 2s linear infinite;
}

.head-warning .section-scan-line {
  opacity: 1;
  background: linear-gradient(90deg, transparent, rgba(255, 212, 0, 0.3), transparent);
}

@keyframes scanLineSweep {
  0% { transform: translateX(-100%); opacity: 0; }
  50% { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
}

/* ── Gauge section (v1.11.3: THREAT BOARD) ──────────────── */
.gauge-section {
  margin: 6rpx 0 22rpx;
}

.gauge-bar {
  background: linear-gradient(180deg, #ffd400, #ff315d) !important;
  box-shadow: 0 0 10rpx rgba(255, 212, 0, 0.4) !important;
}

.gauge-label {
  color: #ffd400 !important;
  text-shadow: 0 0 12rpx rgba(255, 212, 0, 0.45) !important;
}

.gauge-row {
  display: flex;
  gap: 16rpx;
}

.gauge-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12rpx;
  padding: 24rpx 16rpx 20rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.20);
  background: linear-gradient(180deg, rgba(9, 22, 42, 0.85), rgba(5, 12, 28, 0.80));
  position: relative;
  overflow: hidden;
}

/* Gauge HUD corner brackets */
.gauge-card::before,
.gauge-card::after {
  content: '';
  position: absolute;
  width: 16rpx;
  height: 16rpx;
  pointer-events: none;
  opacity: 0.30;
}
.gauge-card::before {
  top: 4rpx; left: 4rpx;
  border-top: 1rpx solid rgba(47, 244, 224, 0.5);
  border-left: 1rpx solid rgba(47, 244, 224, 0.5);
}
.gauge-card::after {
  bottom: 4rpx; right: 4rpx;
  border-bottom: 1rpx solid rgba(47, 244, 224, 0.5);
  border-right: 1rpx solid rgba(47, 244, 224, 0.5);
}

/* Gauge ring */
.gauge-ring {
  position: relative;
  width: 100rpx;
  height: 100rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gauge-ring-inner {
  width: 76rpx;
  height: 76rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.35);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gauge-num {
  font-size: 34rpx;
  font-weight: 900;
  color: #eaf6ff;
  letter-spacing: 2rpx;
}

.gauge-ring-arc {
  position: absolute;
  inset: -4rpx;
  border-radius: 50%;
  border: 3rpx solid transparent;
}

.arc-ok { border-top-color: rgba(39, 245, 181, 0.5); border-right-color: rgba(39, 245, 181, 0.3); }
.arc-fault { border-top-color: rgba(255, 49, 93, 0.7); border-right-color: rgba(255, 49, 93, 0.5); animation: arcFaultSpin 2s linear infinite; }
.arc-warn { border-top-color: rgba(255, 212, 0, 0.6); border-right-color: rgba(255, 212, 0, 0.3); animation: arcFaultSpin 2.5s linear infinite; }

@keyframes arcFaultSpin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.gauge-label-text {
  font-size: 22rpx;
  font-weight: 700;
  color: #8fd9ff;
  letter-spacing: 3rpx;
}

/* Gauge status colors */
.gauge-ok { border-color: rgba(39, 245, 181, 0.22); }
.gauge-ok .gauge-num { color: #27f5b5; text-shadow: 0 0 10rpx rgba(39, 245, 181, 0.4); }
.gauge-ok .gauge-ring-inner { border-color: rgba(39, 245, 181, 0.35); }

.gauge-fault { border-color: rgba(255, 49, 93, 0.40); box-shadow: 0 0 24rpx rgba(255, 49, 93, 0.08); animation: gaugeFaultGlow 1.6s ease-in-out infinite; }
.gauge-fault .gauge-num { color: #ff315d; text-shadow: 0 0 14rpx rgba(255, 49, 93, 0.6); }
.gauge-fault .gauge-ring-inner { border-color: rgba(255, 49, 93, 0.45); }

.gauge-warn { border-color: rgba(255, 212, 0, 0.38); box-shadow: 0 0 24rpx rgba(255, 212, 0, 0.06); animation: gaugeWarnGlow 2s ease-in-out infinite; }
.gauge-warn .gauge-num { color: #ffd400; text-shadow: 0 0 12rpx rgba(255, 212, 0, 0.5); }
.gauge-warn .gauge-ring-inner { border-color: rgba(255, 212, 0, 0.40); }

@keyframes gaugeFaultGlow {
  0%, 100% { border-color: rgba(255, 49, 93, 0.40); }
  50% { border-color: rgba(255, 49, 93, 0.70); }
}

@keyframes gaugeWarnGlow {
  0%, 100% { border-color: rgba(255, 212, 0, 0.38); }
  50% { border-color: rgba(255, 212, 0, 0.60); }
}

/* Gauge sparks (when active) */
.gauge-sparks {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.gauge-spark {
  position: absolute;
  width: 10rpx;
  height: 3rpx;
  background: #ff315d;
  box-shadow: 0 0 8rpx rgba(255, 49, 93, 0.8);
  animation: sparkBlink 0.7s ease-in-out infinite;
}

.gs1 { top: 16rpx; right: 24rpx; transform: rotate(30deg); }
.gs2 { bottom: 22rpx; left: 20rpx; transform: rotate(-40deg); animation-delay: 0.35s; }

.gauge-warn .gauge-spark { background: #ffd400; box-shadow: 0 0 8rpx rgba(255, 212, 0, 0.8); }

@keyframes sparkBlink {
  0%, 100% { opacity: 0.30; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
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
.animations-paused .bar-fault,
.animations-paused .gauge-fault,
.animations-paused .gauge-warn,
.animations-paused .conn-fault,
.animations-paused .led-online,
.animations-paused .led-unknown,
.animations-paused .section-scan-line,
.animations-paused .gauge-ring-arc,
.animations-paused .gauge-spark,
.animations-paused .label-fault {
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
