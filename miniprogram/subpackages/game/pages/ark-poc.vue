<!--
  @module MOD-PAGE-ARK-POC
  @depends MOD-1110-FE-01 (useMqttClient.js), MOD-GAME-ARKZONEMAP (arkZoneMap.js),
           MOD-GAME-ARKRENDER (arkRenderer.js), MOD-API (api.js)
  @description 游戏化「方舟座舱」概念验证页（POC）——实时数据 + 美术升级渲染。
    三条主链路：
      1. 分区渲染：方舟画成 3 个子系统分区（新风 / 温控 / 除湿·能源）的"准插画"飞船透视图
         （金属船体 + 驾驶舱辉光 + 双引擎尾焰 + 星空背景 + HUD），由 ArkRenderer 负责；
      2. 状态着色：每区按「实时设备状态」着色（绿/黄/红/暗）+ 脉冲辉光 + 故障火花；
      3. 点击钻取：多边形精确命中 → 弹窗模拟进入子系统控制页。

    实时数据通道（复用业主端既有链路，零后端改动）：
      api.getDeviceSettingsConfig() → broker/topics/rooms（含 screen_mac, specific_part）
      api.getOwnerRealtimeParams(sp) → device_sns（用于 publishRead 主动拉取首屏值）
      useMqttClient: acquire → subscribe(screen_mac) → publishRead → onDeviceUpdate(cb)
      cb 收到 {deviceSn, productCode, attrs} → 合并入 deviceStore → 经 arkZoneMap 推导分区状态。

    渲染仍用微信原生 Canvas 2D（零 Pixi/Spine 依赖）；真插画可由 renderer.loadShipImage(src) 一键替换。
    运行时须真机/开发者工具验证。演示按钮进入「演示模式」冻结实时覆盖，便于无在线设备时看效果。
-->
<template>
  <view class="ark-page">
    <!-- 顶部 HUD：整体状态 + 数据源 -->
    <view class="hud" :class="'hud-' + overall.level">
      <view class="hud-left">
        <text class="hud-title">ARK · 方舟座舱</text>
        <text class="hud-status">{{ overall.text }}</text>
      </view>
      <view class="hud-chip" :class="'chip-' + connState">
        <text>{{ connText }}</text>
      </view>
    </view>

    <!-- 数据源提示横幅 -->
    <view v-if="banner" class="banner"><text>{{ banner }}</text></view>

    <!-- 飞船画布 -->
    <view class="stage">
      <canvas
        type="2d"
        id="arkCanvas"
        canvas-id="arkCanvas"
        class="ark-canvas"
        @tap="onTap"
      />
    </view>

    <!-- 命中反馈 -->
    <view class="readout">
      <text class="readout-line">最近点击：{{ lastTapText }}</text>
      <text class="readout-hint">{{ demoMode ? '演示模式（实时覆盖已冻结）' : '点击飞船任一分区 → 进入该子系统' }}</text>
    </view>

    <!-- 控制条 -->
    <view class="toolbar">
      <button class="tool-btn" size="mini" @tap="randomize">随机状态</button>
      <button class="tool-btn" size="mini" @tap="allGreen">全部正常</button>
      <button class="tool-btn" size="mini" @tap="injectFault">注入故障</button>
      <button
        class="tool-btn"
        :class="{ 'tool-btn-live': demoMode }"
        size="mini"
        @tap="resumeLive"
      >实时</button>
    </view>
  </view>
</template>

<script setup>
import { ref, reactive, computed, getCurrentInstance } from 'vue'
import { onReady, onHide, onUnload } from '@dcloudio/uni-app'
import { api } from '@/utils/api'
import { useMqttClient } from '@/utils/useMqttClient'
import { computeZoneStatuses } from '../arkZoneMap'
import { ArkRenderer } from '../arkRenderer'

const instance = getCurrentInstance()
const mqttClient = useMqttClient()

// ── 分区定义（静态：id/name/poly）。状态由实时数据驱动，存 zoneStatus。──────────
// poly: 归一化坐标 [0..1]，渲染时按画布实际宽高缩放；既用于绘制也用于命中检测。
// 换真插画时：把这些 poly 对齐插画里各子系统的区域即可（renderer 用它做热区+辉光蒙版）。
const zones = [
  {
    id: 'fresh_air',
    name: '新风系统',
    poly: [[0.50, 0.06], [0.61, 0.19], [0.61, 0.29], [0.39, 0.29], [0.39, 0.19]],
  },
  {
    id: 'temp_control',
    name: '温控系统',
    poly: [
      [0.39, 0.29], [0.61, 0.29], [0.68, 0.42], [0.68, 0.58],
      [0.61, 0.66], [0.39, 0.66], [0.32, 0.58], [0.32, 0.42],
    ],
  },
  {
    id: 'dehumid',
    name: '除湿·能源',
    poly: [
      [0.39, 0.66], [0.61, 0.66], [0.63, 0.82], [0.55, 0.91],
      [0.45, 0.91], [0.37, 0.82],
    ],
  },
]
const ZONE_IDS = zones.map((z) => z.id)

// 每区当前状态：'idle'|'normal'|'warning'|'fault'
const zoneStatus = reactive({ fresh_air: 'idle', temp_control: 'idle', dehumid: 'idle' })

// 实时设备字典：deviceSn -> { productCode, attrs:{tag:val} }
const deviceStore = reactive({})

const lastTapText = ref('—')
const demoMode = ref(false)
const connState = ref('connecting') // connecting | live | offline | unbound | error
const banner = ref('')

const connText = computed(() => ({
  connecting: '连接中…',
  live: demoMode.value ? '演示模式' : '实时已连接',
  offline: '离线',
  unbound: '未绑定设备',
  error: '通道异常',
}[connState.value] || '—'))

// 整体状态：取最严重分区
const overall = computed(() => {
  const vals = Object.values(zoneStatus)
  if (vals.some((v) => v === 'fault')) return { level: 'fault', text: '● 检测到故障' }
  if (vals.some((v) => v === 'warning')) return { level: 'warning', text: '● 存在警告' }
  if (vals.every((v) => v === 'idle')) return { level: 'idle', text: '○ 等待数据…' }
  return { level: 'normal', text: '● 全系统正常' }
})

// ── 实时数据接入 ─────────────────────────────────────────────────────────────
let _offDeviceUpdate = null
let _mqttAcquired = false

function handleDeviceUpdate(p) {
  const prev = deviceStore[p.deviceSn] || { productCode: p.productCode, attrs: {} }
  deviceStore[p.deviceSn] = {
    productCode: p.productCode != null ? p.productCode : prev.productCode,
    attrs: { ...prev.attrs, ...p.attrs },
  }
  if (!demoMode.value) recomputeZoneStatus()
}

function recomputeZoneStatus() {
  Object.assign(zoneStatus, computeZoneStatuses(deviceStore, ZONE_IDS))
}

async function bootstrapRealtime() {
  try {
    const res = await api.getDeviceSettingsConfig()
    const broker = res && res.broker
    const topics = res && res.topics
    const rooms = (res && res.rooms) || []
    if (!broker || !topics || rooms.length === 0) {
      connState.value = 'unbound'
      banner.value = '未检测到绑定设备，当前为演示数据。点底部按钮预览着色效果。'
      demoMode.value = true
      seedDemo()
      return
    }

    // POC：取第一个房间。生产可加房间切换。
    const room = rooms[0]
    const mac = room.screen_mac
    const sp = room.specific_part

    _offDeviceUpdate = mqttClient.onDeviceUpdate(handleDeviceUpdate)

    let deviceSns = []
    try {
      const rp = await api.getOwnerRealtimeParams(sp)
      if (rp && rp.success && Array.isArray(rp.device_sns)) deviceSns = rp.device_sns.map(String)
    } catch (e) { /* 无 device_sns 也可，等待屏端自发推送 */ }

    await mqttClient.acquire(broker, topics)
    _mqttAcquired = true
    mqttClient.subscribe(mac)
    if (deviceSns.length > 0) mqttClient.publishRead(mac, deviceSns)

    connState.value = 'live'
    banner.value = ''
  } catch (e) {
    console.error('[ark-poc] bootstrapRealtime failed:', e && e.message)
    connState.value = 'error'
    banner.value = '实时通道不可用，已切换演示数据。'
    demoMode.value = true
    seedDemo()
  }
}

function teardownRealtime() {
  if (_offDeviceUpdate) { _offDeviceUpdate(); _offDeviceUpdate = null }
  if (_mqttAcquired) { mqttClient.release(); _mqttAcquired = false }
}

// ── Canvas 运行时（绘制委托给 ArkRenderer）──────────────────────────────────
let canvasNode = null
let renderer = null
let rafId = null
let running = false

function setupCanvas() {
  const dpr = uni.getSystemInfoSync().pixelRatio || 2
  uni.createSelectorQuery()
    .in(instance.proxy)
    .select('#arkCanvas')
    .fields({ node: true, size: true })
    .exec((res) => {
      const info = res && res[0]
      if (!info || !info.node) return
      canvasNode = info.node
      const ctx = canvasNode.getContext('2d')
      const cssW = info.width
      const cssH = info.height
      canvasNode.width = cssW * dpr
      canvasNode.height = cssH * dpr
      ctx.scale(dpr, dpr)
      renderer = new ArkRenderer(canvasNode, ctx, cssW, cssH, zones)
      renderer.setStatuses(zoneStatus)
      // 真插画接入示例（有资产时取消注释，并把上面 poly 对齐插画区域）：
      // renderer.loadShipImage('/static/ark/ship.png')
      running = true
      loop()
    })
}

function loop() {
  if (!running || !renderer) return
  renderer.render(Date.now())
  if (canvasNode && canvasNode.requestAnimationFrame) {
    rafId = canvasNode.requestAnimationFrame(loop)
  } else {
    rafId = setTimeout(loop, 33)
  }
}

function stopLoop() {
  running = false
  if (rafId != null) {
    if (canvasNode && canvasNode.cancelAnimationFrame) canvasNode.cancelAnimationFrame(rafId)
    else clearTimeout(rafId)
    rafId = null
  }
}

// ── 交互 ─────────────────────────────────────────────────────────────────────
function onTap(e) {
  const d = e.detail || {}
  const x = d.x != null ? d.x : e.touches?.[0]?.x ?? e.changedTouches?.[0]?.x
  const y = d.y != null ? d.y : e.touches?.[0]?.y ?? e.changedTouches?.[0]?.y
  if (x == null || y == null || !renderer) return

  const id = renderer.hitTest(x, y)
  if (!id) {
    lastTapText.value = `(${Math.round(x)}, ${Math.round(y)}) → 空白区`
    return
  }
  const name = renderer.zoneName(id)
  lastTapText.value = `(${Math.round(x)}, ${Math.round(y)}) → ${name}`

  uni.showModal({
    title: name,
    content: `当前状态：${renderer.statusText(id)}\n（示例）进入该子系统的状态查看与操控页？`,
    confirmText: '进入',
    cancelText: '返回',
    success: (r) => {
      if (r.confirm) {
        uni.showToast({ title: `（示例）进入「${name}」`, icon: 'none' })
        // 生产：uni.navigateTo({ url: `/subpackages/control/pages/...?zone=${id}` })
      }
    },
  })
}

// ── 演示控制（冻结实时覆盖）──────────────────────────────────────────────────
const STATES = ['normal', 'warning', 'fault']
function randomize() {
  demoMode.value = true
  ZONE_IDS.forEach((id) => { zoneStatus[id] = STATES[Math.floor(Math.random() * STATES.length)] })
}
function allGreen() {
  demoMode.value = true
  ZONE_IDS.forEach((id) => { zoneStatus[id] = 'normal' })
}
function injectFault() {
  demoMode.value = true
  zoneStatus[ZONE_IDS[Math.floor(Math.random() * ZONE_IDS.length)]] = 'fault'
}
function resumeLive() {
  demoMode.value = false
  recomputeZoneStatus()
}
function seedDemo() {
  zoneStatus.fresh_air = 'normal'
  zoneStatus.temp_control = 'warning'
  zoneStatus.dehumid = 'fault'
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
onReady(() => {
  setTimeout(setupCanvas, 60)
  bootstrapRealtime()
})
onHide(stopLoop)
onUnload(() => {
  stopLoop()
  teardownRealtime()
})
</script>

<style scoped>
.ark-page { min-height: 100vh; background: #05080f; display: flex; flex-direction: column; }
.hud {
  margin: 20rpx 24rpx 0; padding: 20rpx 28rpx; border-radius: 14rpx;
  display: flex; align-items: center; justify-content: space-between;
  border: 1px solid rgba(0, 229, 255, 0.35); background: rgba(10, 18, 36, 0.9);
}
.hud-left { display: flex; flex-direction: column; }
.hud-title { font-size: 30rpx; font-weight: bold; color: #7df9ff; letter-spacing: 2rpx; }
.hud-status { font-size: 26rpx; font-weight: bold; margin-top: 4rpx; }
.hud-normal .hud-status { color: #00ffa3; }
.hud-warning .hud-status { color: #ffd400; }
.hud-fault .hud-status { color: #ff2e63; }
.hud-idle .hud-status { color: #4d7099; }
.hud-fault { border-color: rgba(255, 46, 99, 0.6); }
.hud-warning { border-color: rgba(255, 212, 0, 0.5); }

.hud-chip { padding: 6rpx 18rpx; border-radius: 20rpx; font-size: 22rpx; border: 1px solid rgba(0,229,255,0.4); }
.hud-chip text { color: #7df9ff; }
.chip-live { border-color: rgba(0,255,163,0.6); }
.chip-live text { color: #00ffa3; }
.chip-offline text, .chip-error text { color: #ff5c85; }
.chip-unbound text { color: #ffd400; }

.banner {
  margin: 12rpx 24rpx 0; padding: 12rpx 20rpx; border-radius: 10rpx;
  background: rgba(255, 212, 0, 0.1); border-left: 4rpx solid #ffd400;
}
.banner text { font-size: 22rpx; color: #ffe066; }

.stage {
  flex: 1; margin: 16rpx 24rpx; border-radius: 16rpx; overflow: hidden;
  border: 1px solid rgba(0, 229, 255, 0.18);
}
.ark-canvas { width: 100%; height: 100%; min-height: 820rpx; }

.readout { margin: 0 24rpx; display: flex; flex-direction: column; }
.readout-line { font-size: 24rpx; color: #7df9ff; }
.readout-hint { font-size: 22rpx; color: rgba(125, 249, 255, 0.5); margin-top: 4rpx; }

.toolbar { display: flex; gap: 12rpx; padding: 20rpx 24rpx 32rpx; }
.tool-btn {
  flex: 1; margin: 0; font-size: 24rpx; color: #cfefff;
  background: rgba(0, 229, 255, 0.12); border: 1px solid rgba(0, 229, 255, 0.4);
}
.tool-btn-live { background: rgba(0,255,163,0.18); border-color: rgba(0,255,163,0.6); color: #00ffa3; }
</style>
