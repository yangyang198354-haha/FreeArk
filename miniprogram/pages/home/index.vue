<!--
  @module MOD-BD-001 (was MOD-PAGE-HOME)
  @implements IFC-BD-001-01 through IFC-BD-001-10
  @depends MOD-BD-002 (useBridgeDashboard), MOD-BD-003 (useAnimationControl),
    MOD-BD-005~007 (SubsystemCompartment, RoomCompartment, FaultDrawer),
    ArkTabBar, MetricCard, authStore
  @author sub_agent_software_developer
  @description Bridge dashboard page — role-based routing:
    - role=user (owner): Cyberpunk HOLO-HUD dashboard (v1.13.0)
      1:1 还原 cyberpunk-smart-home 参考设计。
    - admin/operator: Material Design dashboard (PRESERVED AS-IS from original).
-->
<template>
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- OWNER PATH — v1.13.0 Bridge Dashboard (1:1 参考设计还原)        -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <view v-if="isOwner" class="owner-page" :class="{ 'animations-paused': animationsPaused }">
    <!-- 背景层（参考设计：grid + hex + scan-beam + scanlines） -->
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="bg-hex" />
    <view class="scan-beam" />
    <view class="cyber-scanlines" />

    <!-- 状态栏占位 -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- Header（参考设计：毛玻璃三栏，中 shimmer 标题） -->
    <view class="owner-header">
      <view class="header-spacer" />
      <text class="owner-title">舰桥</text>
      <view class="header-spacer" />
    </view>

    <!-- 连接状态栏（参考设计：圆角胶囊 pills） -->
    <view class="top-conn-bar">
      <!-- PLC：接驳方舟神经网络 -->
      <view class="status-pill" :class="connPlcClass">
        <view class="status-dot" :class="connPlcLedClass" />
        <text class="status-pill-text">接驳方舟神经网络 / {{ connPlcLabel }}</text>
      </view>
      <!-- Screen：链接座舱 -->
      <view class="status-pill status-pill-screen" :class="connScreenClass">
        <view class="status-dot" :class="connScreenLedClass" />
        <text class="status-pill-text">链接座舱 / {{ connScreenLabel }}</text>
      </view>
    </view>

    <!-- 主内容区 -->
    <scroll-view scroll-y class="owner-content" :scroll-with-animation="true">
      <!-- 加载状态 -->
      <view v-if="dash.state.loading && !hasInitialData" class="owner-tip">
        <view class="sync-pulse" />
        <text>正在同步座舱状态…</text>
      </view>

      <!-- 空状态：无绑定 -->
      <view v-else-if="dash.hasNoBindings.value" class="owner-empty">
        <view class="empty-frame">
          <view class="empty-glow" />
          <text class="empty-title">未链接座舱</text>
          <text class="empty-sub">链接座舱后可查看设备状态</text>
          <view class="empty-btn" @tap="goBind"><text>激活座舱</text></view>
        </view>
      </view>

      <!-- 主仪表盘 -->
      <view v-else class="dashboard">
        <!-- ── Section: THREAT BOARD ── -->
        <view class="dash-section gauge-section">
          <view class="section-head">
            <view class="section-bar gauge-bar" />
            <text class="section-label gauge-label">THREAT BOARD</text>
            <view class="section-divider gauge-divider" />
            <text class="section-badge gauge-badge-flicker">CLEAR</text>
          </view>
          <view class="gauge-row">
            <!-- 系统故障 Gauge -->
            <view class="gauge-card" :class="faultGaugeClass" @tap="onFaultGaugeTap">
              <view class="br-tl" /><view class="br-tr" /><view class="br-bl" /><view class="br-br" />
              <view v-if="faultTotal > 0" class="gauge-flash" />
              <view class="gauge-ring">
                <view class="gauge-ring-outer" :class="faultGaugeArcClass" />
                <view class="gauge-ring-inner">
                  <text class="gauge-num" :class="{ 'gauge-num-fault': faultTotal > 0 }">{{ faultTotal }}</text>
                </view>
              </view>
              <text class="gauge-label-text">系统故障</text>
              <view v-if="faultTotal > 0" class="gauge-sparks">
                <view class="gauge-spark gs1" />
                <view class="gauge-spark gs2" />
              </view>
            </view>
            <!-- 结露预警 Gauge -->
            <view class="gauge-card" :class="condGaugeClass" @tap="onCondGaugeTap">
              <view class="br-tl" /><view class="br-tr" /><view class="br-bl" /><view class="br-br" />
              <view v-if="dash.state.condensationCount > 0" class="gauge-flash gauge-flash-warn" />
              <view class="gauge-ring">
                <view class="gauge-ring-outer" :class="condGaugeArcClass" />
                <view class="gauge-ring-inner">
                  <text class="gauge-num" :class="{ 'gauge-num-warn': dash.state.condensationCount > 0 }">{{ dash.state.condensationCount }}</text>
                </view>
              </view>
              <text class="gauge-label-text">结露预警</text>
              <view v-if="dash.state.condensationCount > 0" class="gauge-sparks">
                <view class="gauge-spark gs1 warn-spark" />
                <view class="gauge-spark gs2 warn-spark" />
              </view>
            </view>
          </view>
        </view>

        <!-- ── Section: SYS STATUS ── -->
        <view class="dash-section">
          <view class="section-head">
            <view class="section-bar" :class="sysBarClass" />
            <text class="section-label" :class="sysLabelClass">SYS STATUS</text>
            <view class="section-divider" />
            <text class="section-badge">{{ dash.state.subsystems.length }} MODULES</text>
          </view>
          <view class="subsystem-grid">
            <SubsystemCompartment
              v-for="(sub, idx) in dash.state.subsystems"
              :key="sub.id"
              :subsystem="sub"
              :index="idx"
              :animationsPaused="animationsPaused"
              @open="onCompartmentOpen"
            />
          </view>
        </view>

        <!-- ── Section: ROOM STATUS ── -->
        <view class="dash-section">
          <view class="section-head">
            <view class="section-bar" :class="roomBarClass" />
            <text class="section-label" :class="roomLabelClass">ROOM STATUS</text>
            <view class="section-divider" />
            <text class="section-badge">{{ dash.state.rooms.length }} ROOMS</text>
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

        <!-- ── Data Stream 装饰 ── -->
        <view class="data-stream">
          <view class="data-stream-line" />
          <text class="data-stream-text">SYS.CYCLE.24.7</text>
          <view class="data-stream-line" />
        </view>

        <!-- 错误横幅 -->
        <view v-if="dash.state.error" class="owner-error">
          <text>{{ dash.state.error }}</text>
        </view>

        <!-- 底部间距（让出 Tab 栏） -->
        <view style="height: 120rpx;" />
      </view>
    </scroll-view>

    <!-- Fault 抽屉 -->
    <FaultDrawer
      :compartment="dash.state.activeCompartment"
      :visible="!!dash.state.activeCompartment"
      :faultEvents="dash.state.compartmentFaults"
      :deviceParams="dash.state.compartmentParams"
      @close="dash.closeCompartment()"
    />

    <!-- Tab 栏 -->
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
  if (s === 'online') return 'pill-online'
  if (s === 'offline') return 'pill-offline'
  return 'pill-unknown'
})

const connPlcLedClass = computed(() => {
  const s = dash.state.plcCockpitStatus
  if (s === 'online') return 'dot-cyan'
  if (s === 'offline') return 'dot-magenta'
  return 'dot-dim'
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
  if (s === 'online') return 'pill-online'
  if (s === 'offline') return 'pill-offline'
  return 'pill-unknown'
})

const connScreenLedClass = computed(() => {
  const s = dash.state.screenCockpitStatus
  if (s === 'online') return 'dot-green'
  if (s === 'offline') return 'dot-magenta'
  return 'dot-dim'
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

const sysBarClass = computed(() => `bar-${sysSectionStatus.value}`)
const sysLabelClass = computed(() => `label-${sysSectionStatus.value}`)

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
<!-- STYLES: Owner (v1.13.0 — 1:1 还原 cyberpunk-smart-home 参考)    -->
<!-- ═══════════════════════════════════════════════════════════════ -->
<style scoped>
/* ── Page base ──────────────────────────────────────────── */
.owner-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0a0a0f;
  overflow: hidden;
}

/* ── 字体栈（系统字体近似参考设计）─────────────────────── */
/* Display: Orbitron → monospace 粗体 + 大写 + 宽字距 */
/* Body: Rajdhani → PingFang SC / 系统无衬线 */
/* Mono: Share Tech Mono → Courier New 等宽 */

/* ── 背景层 ────────────────────────────────────────────── */
.bg-base,
.bg-grid,
.bg-hex,
.scan-beam,
.cyber-scanlines {
  position: absolute;
  pointer-events: none;
}

.bg-base {
  inset: 0;
  background:
    radial-gradient(ellipse 70% 60% at 50% 30%, rgba(0, 240, 255, 0.04), transparent),
    radial-gradient(ellipse 50% 40% at 80% 70%, rgba(176, 38, 255, 0.04), transparent),
    linear-gradient(180deg, #0a0a0f, #0d0d18 60%, #0a0a0f);
}

.bg-grid {
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 240, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 240, 255, 0.04) 1px, transparent 1px);
  background-size: 48rpx 48rpx;
  -webkit-mask-image: linear-gradient(180deg, #000 20%, transparent 80%);
  mask-image: linear-gradient(180deg, #000 20%, transparent 80%);
}

.bg-hex {
  inset: 0;
  opacity: 0.02;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='49' viewBox='0 0 28 49'%3E%3Cg fill-rule='evenodd'%3E%3Cg fill='%2300f0ff'%3E%3Cpath d='M13.99 9.25l13 7.5v15l-13 7.5L1 31.75v-15l12.99-7.5zM3 17.9v12.7l10.99 6.34 11-6.35V17.9l-11-6.34L3 17.9zM0 15l12.98-7.5V0h-2v6.35L0 12.69v2.3zm0 18.5L12.98 41v8h-2v-6.85L0 35.81v-2.3zM15 0v7.5L27.99 15H28v-2.31h-.01L17 6.35V0h-2zm0 49v-8l12.99-7.5H28v2.31h-.01L17 42.15V49h-2z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  animation: hexPulse 8s ease-in-out infinite;
}

/* 扫描光束（水平线扫过屏幕） */
.scan-beam {
  left: 0;
  right: 0;
  height: 2px;
  z-index: 2;
  background: linear-gradient(90deg, transparent, rgba(0, 240, 255, 0.08), rgba(176, 38, 255, 0.08), transparent);
  animation: scanLineMove 6s linear infinite;
}

/* 扫描线覆盖层 */
.cyber-scanlines {
  inset: 0;
  z-index: 9999;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 4rpx,
    rgba(0, 0, 0, 0.03) 4rpx,
    rgba(0, 0, 0, 0.03) 8rpx
  );
}

.status-spacer {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
}

/* ── Header（参考设计：毛玻璃效果 + shimmer 标题）─────── */
.owner-header {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  height: 88rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 10, 15, 0.88);
  border-bottom: 1px solid rgba(0, 240, 255, 0.15);
}

.header-spacer {
  width: 180rpx;
  flex: 0 0 auto;
}

.owner-title {
  flex: 1;
  text-align: center;
  font-family: 'Courier New', 'SF Mono', 'Menlo', monospace;
  font-size: 36rpx;
  font-weight: 700;
  letter-spacing: 12rpx;
  text-transform: uppercase;
  background: linear-gradient(90deg, #e0e0ff 0%, #00f0ff 40%, #e0e0ff 60%, #00f0ff 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: shimmer 4s linear infinite;
}

/* ── 连接状态胶囊 Pills ───────────────────────────────── */
.top-conn-bar {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  display: flex;
  gap: 12rpx;
  padding: 12rpx 22rpx 8rpx;
}

.status-pill {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8rpx;
  padding: 10rpx 16rpx;
  border-radius: 9999px;
  background: rgba(0, 240, 255, 0.06);
  border: 1px solid rgba(0, 240, 255, 0.25);
  animation: glowBreathe 3s ease-in-out infinite;
}

.status-pill-screen {
  background: rgba(57, 255, 20, 0.04);
  border-color: rgba(57, 255, 20, 0.20);
  animation: glowBreathe 3s ease-in-out 1.5s infinite;
}

.pill-offline {
  background: rgba(255, 45, 123, 0.06);
  border-color: rgba(255, 45, 123, 0.35);
  animation: glowBreathe 2s ease-in-out infinite;
}

.pill-unknown {
  opacity: 0.55;
}

.status-dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  flex-shrink: 0;
  animation: glowBreathe 2s ease-in-out infinite;
}

.dot-cyan { background: #00f0ff; box-shadow: 0 0 8rpx rgba(0, 240, 255, 0.6); }
.dot-green { background: #39ff14; box-shadow: 0 0 8rpx rgba(57, 255, 20, 0.6); }
.dot-magenta { background: #ff2d7b; box-shadow: 0 0 8rpx rgba(255, 45, 123, 0.6); }
.dot-dim { background: #555577; box-shadow: 0 0 4rpx rgba(85, 85, 119, 0.3); }

.status-pill-text {
  font-size: 20rpx;
  color: #8888aa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pill-online .status-pill-text { color: #8888aa; }
.pill-offline .status-pill-text { color: #ff2d7b; }

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
  border: 2rpx solid rgba(0, 240, 255, 0.4);
  border-top-color: #00f0ff;
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
  border: 1px solid rgba(0, 240, 255, 0.18);
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
  background: radial-gradient(ellipse, rgba(0, 240, 255, 0.12), transparent);
  pointer-events: none;
}

.empty-title {
  display: block;
  font-size: 32rpx;
  color: #e0e0ff;
  font-weight: 700;
}

.empty-sub {
  display: block;
  margin-top: 14rpx;
  font-size: 24rpx;
  color: #8888aa;
}

.empty-btn {
  margin: 34rpx auto 0;
  width: 210rpx;
  padding: 18rpx 0;
  background: linear-gradient(90deg, #00f0ff, #b026ff);
}

.empty-btn text {
  font-size: 26rpx;
  color: #0a0a0f;
  font-weight: 700;
}

/* ── Dashboard ──────────────────────────────────────────── */
.dashboard {
  padding: 0 22rpx;
}

.dash-section {
  margin-bottom: 20rpx;
}

/* ── 章节头（参考设计：竖条渐变 + shimmer 标签 + 分割线 + mono 徽章）── */
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

/* 参考设计：竖条渐变色 + glow */
.bar-normal { background: linear-gradient(180deg, #00f0ff, #b026ff); box-shadow: 0 0 12rpx rgba(0, 240, 255, 0.4); }
.bar-warning { background: linear-gradient(180deg, #f0e130, #ff6a00); box-shadow: 0 0 12rpx rgba(240, 225, 48, 0.5); }
.bar-fault { background: linear-gradient(180deg, #ff2d7b, #b026ff); box-shadow: 0 0 14rpx rgba(255, 45, 123, 0.6); animation: barFaultBlink 0.8s ease-in-out infinite; }
.bar-idle { background: linear-gradient(180deg, #555577, #333355); box-shadow: none; opacity: 0.5; }

@keyframes barFaultBlink {
  0%, 100% { box-shadow: 0 0 14rpx rgba(255, 45, 123, 0.6); }
  50% { box-shadow: 0 0 28rpx rgba(255, 45, 123, 1.0); }
}

.section-label {
  font-family: 'Courier New', 'SF Mono', 'Menlo', monospace;
  font-size: 28rpx;
  font-weight: 800;
  letter-spacing: 8rpx;
  transition: color 0.6s ease, text-shadow 0.6s ease;
}

/* shimmer 效果覆盖 */
.label-normal {
  color: #00f0ff;
  text-shadow: 0 0 16rpx rgba(0, 240, 255, 0.6);
  background: linear-gradient(90deg, #00f0ff 0%, #00f0ff 40%, #e0e0ff 60%, #00f0ff 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: shimmer 4s linear infinite;
}
.label-warning { color: #f0e130; text-shadow: 0 0 16rpx rgba(240, 225, 48, 0.6); }
.label-fault { color: #ff2d7b; text-shadow: 0 0 18rpx rgba(255, 45, 123, 0.7); animation: labelFaultBlink 1s ease-in-out infinite; }
.label-idle { color: #555577; text-shadow: none; }

@keyframes labelFaultBlink {
  0%, 100% { text-shadow: 0 0 18rpx rgba(255, 45, 123, 0.7); }
  50% { text-shadow: 0 0 32rpx rgba(255, 45, 123, 1.0); }
}

/* 渐变分割线 */
.section-divider {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(0, 240, 255, 0.35), transparent);
}

/* mono 徽章 */
.section-badge {
  font-family: 'Courier New', 'SF Mono', 'Menlo', monospace;
  font-size: 18rpx;
  letter-spacing: 2rpx;
  color: #555577;
}

/* ── THREAT BOARD 章节头特殊样式 ── */
.gauge-section {
  margin: 6rpx 0 20rpx;
}

.gauge-bar {
  background: linear-gradient(180deg, #ff2d7b, #ff6a00) !important;
  box-shadow: 0 0 10rpx rgba(255, 45, 123, 0.4) !important;
}

.gauge-label {
  color: #ff2d7b !important;
  text-shadow: 0 0 12rpx rgba(255, 45, 123, 0.4) !important;
  -webkit-text-fill-color: #ff2d7b !important;
  background: none !important;
  animation: none !important;
}

.gauge-divider {
  background: linear-gradient(90deg, rgba(255, 45, 123, 0.3), transparent) !important;
}

.gauge-badge-flicker {
  color: #ff2d7b;
  animation: cyber-flicker 4s linear infinite;
}

/* ── Gauge 卡片 ────────────────────────────────────────── */
.gauge-row {
  display: flex;
  gap: 16rpx;
}

.gauge-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10rpx;
  padding: 24rpx 16rpx 20rpx;
  border: 1px solid rgba(0, 240, 255, 0.20);
  background: #111128;
  border-radius: 4px;
  position: relative;
  overflow: hidden;
}

/* 四角 bracket */
.gauge-card .br-tl, .gauge-card .br-tr, .gauge-card .br-bl, .gauge-card .br-br {
  position: absolute;
  width: 22rpx;
  height: 22rpx;
  pointer-events: none;
  opacity: 0.35;
  border-style: solid;
  border-color: rgba(0, 240, 255, 0.55);
}
.gauge-card .br-tl { top: -1px; left: -1px; border-width: 2px 0 0 2px; }
.gauge-card .br-tr { top: -1px; right: -1px; border-width: 2px 2px 0 0; }
.gauge-card .br-bl { bottom: -1px; left: -1px; border-width: 0 0 2px 2px; }
.gauge-card .br-br { bottom: -1px; right: -1px; border-width: 0 2px 2px 0; }

/* 警告闪光覆盖层 */
.gauge-flash {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle, rgba(255, 45, 123, 0.08), transparent);
  animation: warningFlash 4s ease-in-out infinite;
  pointer-events: none;
}
.gauge-flash-warn {
  background: radial-gradient(circle, rgba(255, 106, 0, 0.06), transparent);
  animation: warningFlash 4s ease-in-out 2s infinite;
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

.gauge-ring-outer {
  position: absolute;
  inset: -4rpx;
  border-radius: 50%;
  border: 3rpx solid transparent;
}

.gauge-ring-inner {
  width: 76rpx;
  height: 76rpx;
  border: 2rpx solid rgba(0, 240, 255, 0.35);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gauge-num {
  font-family: 'Courier New', 'SF Mono', 'Menlo', monospace;
  font-size: 34rpx;
  font-weight: 900;
  color: #e0e0ff;
  letter-spacing: 2rpx;
}

.gauge-num-fault { color: #ff2d7b; text-shadow: 0 0 14rpx rgba(255, 45, 123, 0.6); }
.gauge-num-warn { color: #ff6a00; text-shadow: 0 0 12rpx rgba(255, 106, 0, 0.5); }

.arc-ok { border-top-color: rgba(57, 255, 20, 0.5); border-right-color: rgba(57, 255, 20, 0.3); }
.arc-fault { border-top-color: rgba(255, 45, 123, 0.7); border-right-color: rgba(255, 45, 123, 0.5); animation: arcFaultSpin 2s linear infinite; }
.arc-warn { border-top-color: rgba(255, 106, 0, 0.6); border-right-color: rgba(240, 225, 48, 0.3); animation: arcFaultSpin 2.5s linear infinite; }

@keyframes arcFaultSpin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.gauge-label-text {
  font-size: 22rpx;
  font-weight: 600;
  color: #8888aa;
  letter-spacing: 2rpx;
}

/* Gauge 状态色 */
.gauge-ok { border-color: rgba(57, 255, 20, 0.22); }
.gauge-ok .gauge-num { color: #39ff14; text-shadow: 0 0 10rpx rgba(57, 255, 20, 0.4); }
.gauge-ok .gauge-ring-inner { border-color: rgba(57, 255, 20, 0.35); }
.gauge-ok .br-tl, .gauge-ok .br-tr, .gauge-ok .br-bl, .gauge-ok .br-br { border-color: rgba(57, 255, 20, 0.55); }

.gauge-fault { border-color: rgba(255, 45, 123, 0.40); box-shadow: 0 0 24rpx rgba(255, 45, 123, 0.08); animation: gaugeFaultGlow 1.6s ease-in-out infinite; }
.gauge-fault .gauge-ring-inner { border-color: rgba(255, 45, 123, 0.45); }
.gauge-fault .br-tl, .gauge-fault .br-tr, .gauge-fault .br-bl, .gauge-fault .br-br { border-color: rgba(255, 45, 123, 0.55); }

.gauge-warn { border-color: rgba(255, 106, 0, 0.38); box-shadow: 0 0 24rpx rgba(255, 106, 0, 0.06); animation: gaugeWarnGlow 2s ease-in-out infinite; }
.gauge-warn .gauge-ring-inner { border-color: rgba(255, 106, 0, 0.40); }
.gauge-warn .br-tl, .gauge-warn .br-tr, .gauge-warn .br-bl, .gauge-warn .br-br { border-color: rgba(255, 106, 0, 0.55); }

@keyframes gaugeFaultGlow {
  0%, 100% { border-color: rgba(255, 45, 123, 0.40); }
  50% { border-color: rgba(255, 45, 123, 0.70); }
}

@keyframes gaugeWarnGlow {
  0%, 100% { border-color: rgba(255, 106, 0, 0.38); }
  50% { border-color: rgba(255, 106, 0, 0.60); }
}

/* Gauge sparks */
.gauge-sparks {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.gauge-spark {
  position: absolute;
  width: 10rpx;
  height: 3rpx;
  background: #ff2d7b;
  box-shadow: 0 0 8rpx rgba(255, 45, 123, 0.8);
  animation: sparkBlink 0.7s ease-in-out infinite;
}

.warn-spark { background: #ff6a00; box-shadow: 0 0 8rpx rgba(255, 106, 0, 0.8); }

.gs1 { top: 16rpx; right: 24rpx; transform: rotate(30deg); }
.gs2 { bottom: 22rpx; left: 20rpx; transform: rotate(-40deg); animation-delay: 0.35s; }

@keyframes sparkBlink {
  0%, 100% { opacity: 0.30; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ── 子系统网格 (2x2) ──────────────────────────────────── */
.subsystem-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14rpx;
}

/* ── 房间网格 (2 列) ───────────────────────────────────── */
.room-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14rpx;
}

/* ── Data Stream 装饰 ──────────────────────────────────── */
.data-stream {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 0 4rpx;
  margin-bottom: 16rpx;
  opacity: 0.4;
}

.data-stream-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #00f0ff, transparent);
}

.data-stream-line:last-child {
  background: linear-gradient(90deg, transparent, #b026ff, transparent);
}

.data-stream-text {
  font-family: 'Courier New', 'SF Mono', 'Menlo', monospace;
  font-size: 16rpx;
  letter-spacing: 3rpx;
  color: #00f0ff;
}

/* ── Error banner ───────────────────────────────────────── */
.owner-error {
  margin: 18rpx 0 0;
  padding: 16rpx 20rpx;
  background: rgba(240, 225, 48, 0.08);
  border-left: 4rpx solid #f0e130;
}

.owner-error text {
  font-size: 24rpx;
  color: #f0e130;
}

/* ── Animations paused ──────────────────────────────────── */
.animations-paused .scan-beam,
.animations-paused .bar-fault,
.animations-paused .gauge-fault,
.animations-paused .gauge-warn,
.animations-paused .pill-offline,
.animations-paused .status-dot,
.animations-paused .status-pill,
.animations-paused .gauge-ring-outer,
.animations-paused .gauge-spark,
.animations-paused .label-fault,
.animations-paused .gauge-flash,
.animations-paused .gauge-badge-flicker,
.animations-paused .owner-title {
  animation-play-state: paused;
}

/* ── Keyframes ──────────────────────────────────────────── */
@keyframes shimmer {
  0% { background-position: -200% center; }
  100% { background-position: 200% center; }
}

@keyframes scanLineMove {
  0% { top: -2px; }
  100% { top: 100%; }
}

@keyframes hexPulse {
  0%, 100% { opacity: 0.02; }
  50% { opacity: 0.06; }
}

@keyframes glowBreathe {
  0%, 100% { box-shadow: 0 0 4px var(--glow-color, rgba(0, 240, 255, 0.3)); }
  50% { box-shadow: 0 0 16px var(--glow-color, rgba(0, 240, 255, 0.5)), 0 0 32px rgba(0, 240, 255, 0.2); }
}

@keyframes cyber-flicker {
  0%, 19.999%, 22%, 62.999%, 64%, 64.999%, 70%, 100% { opacity: 1; }
  20%, 21.999%, 63%, 63.999%, 65%, 69.999% { opacity: 0.4; }
}

@keyframes warningFlash {
  0%, 100% { opacity: 0; }
  50% { opacity: 0.6; }
}

@keyframes cursorBlink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
</style>

<!-- ═══════════════════════════════════════════════════════════════ -->
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
