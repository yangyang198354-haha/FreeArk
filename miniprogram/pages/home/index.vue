<!--
  @module MOD-PAGE-HOME
  @description 首页角色分流：
    - role=user：方舟战舰风格的专有部分户型俯视图，展示房间结构、主机/风机俯视设备、
      温度数字面板，以及局部黄色预警/红色告警损伤效果。
    - admin/operator：保留原有系统概览与快捷入口 dashboard 行为。
-->
<template>
  <view v-if="isOwner" class="owner-page">
    <view class="bg-base" />
    <view class="bg-grid" />
    <view class="hud-scan" />

    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <view class="owner-header">
      <view class="owner-title-box">
        <text class="owner-title">方舟户型舱图</text>
        <text class="owner-subtitle">{{ ownerHeaderSub }}</text>
      </view>
      <view class="owner-state" :class="'state-' + overallStatus.level">
        <view class="state-led" />
        <text>{{ overallStatus.text }}</text>
      </view>
    </view>

    <scroll-view scroll-y class="owner-content">
      <view v-if="bindings.length > 1" class="unit-bar">
        <picker
          mode="selector"
          :range="bindingLabels"
          :value="selectedBindingIndex"
          @change="onBindingChange"
        >
          <view class="unit-picker">
            <text class="unit-label">当前专有部分</text>
            <text class="unit-value">{{ currentBindingLabel }} ›</text>
          </view>
        </picker>
      </view>

      <view v-if="ownerLoading && !ownerHasContent" class="owner-tip">
        <text>正在同步方舟舱图…</text>
      </view>

      <view v-else-if="!bindings.length" class="owner-empty">
        <view class="empty-frame">
          <text class="empty-title">未绑定专有部分</text>
          <text class="empty-sub">绑定房号后可查看方舟户型舱图</text>
          <view class="empty-btn" @tap="goBind"><text>去绑定</text></view>
        </view>
      </view>

      <view v-else class="ark-deck">
        <view class="deck-ribbon">
          <text>{{ currentSpecificPart || '—' }}</text>
          <text>{{ realtimeText }}</text>
        </view>

        <view class="ship-shell" :class="'state-' + overallStatus.level">
          <view class="ship-nose">
            <view class="nose-plate" />
            <text>FREEARK</text>
          </view>

          <view class="system-dock">
            <view
              v-for="module in systemModules"
              :key="module.id"
              class="module-node"
              :class="['state-' + module.status, 'module-' + module.kind]"
              @tap="openModule(module)"
            >
              <view class="module-visual">
                <view v-if="module.kind === 'fan'" class="fan-top">
                  <view class="fan-ring">
                    <view class="fan-blade fan-b1" />
                    <view class="fan-blade fan-b2" />
                    <view class="fan-blade fan-b3" />
                  </view>
                </view>
                <view v-else-if="module.kind === 'host'" class="host-top">
                  <view class="host-core" />
                  <view class="host-fin host-f1" />
                  <view class="host-fin host-f2" />
                  <view class="host-fin host-f3" />
                </view>
                <view v-else class="panel-top">
                  <view class="panel-screen" />
                  <view class="panel-line" />
                </view>
                <view v-if="module.status === 'warning' || module.status === 'fault'" class="module-damage">
                  <view class="damage-spark ds1" />
                  <view class="damage-spark ds2" />
                </view>
              </view>
              <view class="module-copy">
                <text class="module-name">{{ module.name }}</text>
                <text class="module-temp">{{ module.tempText }}</text>
              </view>
            </view>
          </view>

          <view class="ship-spine">
            <view class="spine-line">
              <view class="spine-flow" />
            </view>
            <view class="spine-dot sd1" />
            <view class="spine-dot sd2" />
            <view class="spine-dot sd3" />
          </view>

          <view class="room-grid" :class="'room-count-' + roomCards.length">
            <view
              v-for="(room, index) in roomCards"
              :key="room.id"
              class="room-cell"
              :class="['state-' + room.status, 'room-shape-' + (index % 4)]"
              @tap="openRoom(room)"
            >
              <view class="room-panel-lines">
                <view class="panel-line-a" />
                <view class="panel-line-b" />
              </view>
              <view v-if="room.status === 'warning' || room.status === 'fault'" class="room-damage">
                <view class="damage-mark dm1" />
                <view class="damage-mark dm2" />
                <view class="damage-mark dm3" />
              </view>
              <view class="room-head">
                <text class="room-name">{{ room.name }}</text>
                <view class="room-status-dot" />
              </view>
              <view class="temp-board">
                <text class="temp-value">{{ room.tempText }}</text>
                <text class="temp-label">TEMP</text>
              </view>
              <view class="room-devices">
                <view
                  v-for="device in room.devices"
                  :key="device.id"
                  class="mini-device"
                  :class="'mini-' + device.kind"
                >
                  <view class="mini-icon" />
                  <text>{{ device.name }}</text>
                </view>
              </view>
            </view>
          </view>

          <view class="ship-tail">
            <view class="tail-engine te1" />
            <view class="tail-engine te2" />
          </view>
        </view>

        <view v-if="ownerError" class="owner-error">
          <text>{{ ownerError }}</text>
        </view>
      </view>
    </scroll-view>

    <ArkTabBar active="home" />
  </view>

  <view v-else class="admin-page">
    <view :style="{ height: statusBarHeight + 'px' }" class="admin-status-spacer" />
    <scroll-view scroll-y class="admin-scroll">
      <view class="home-page">
        <view class="header">
          <text class="header-title">FreeArk 控制中心</text>
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
import { ref, computed } from 'vue'
import { onShow, onHide, onPullDownRefresh } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useOwnerStore } from '@/store/owner'
import { api } from '@/utils/api'
import { PagePoller } from '@/utils/poller'
import MetricCard from '@/components/MetricCard.vue'
import ArkTabBar from '@/components/ArkTabBar.vue'
import { attrSeverity, worseStatus } from '@/subpackages/game/arkZoneMap'

const authStore = useAuthStore()
const ownerStore = useOwnerStore()
const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

if (!authStore.isLoggedIn) {
  uni.reLaunch({ url: '/pages/login/index' })
}

const isOwner = computed(() => authStore.role === 'user')

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

const bindings = computed(() => ownerStore.bindings)
const selectedBindingIndex = ref(0)
const ownerLoading = ref(false)
const ownerError = ref('')

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

const currentBinding = computed(() => bindings.value[selectedBindingIndex.value] || null)
const currentSpecificPart = computed(() => currentBinding.value?.specific_part || '')
const ownerStructure = computed(() => ownerStore.structureFor(currentSpecificPart.value))
const ownerRealtime = computed(() => ownerStore.realtimeFor(currentSpecificPart.value))
const currentBindingLabel = computed(() => {
  const b = currentBinding.value
  if (!b) return '未选择'
  return b.location_name || b.specific_part || '未命名专有部分'
})
const bindingLabels = computed(() =>
  bindings.value.map((b) => b.location_name || b.specific_part || '未命名专有部分')
)
const ownerHeaderSub = computed(() =>
  currentSpecificPart.value ? `${currentBindingLabel.value} · ${currentSpecificPart.value}` : '等待绑定'
)
const ownerHasContent = computed(() => bindings.value.length > 0 && (roomCards.value.length > 0 || systemModules.value.length > 0))

const realtimeSubTypes = computed(() => flattenRealtimeSubTypes(ownerRealtime.value?.data || ownerRealtime.value || {}))
const roomCards = computed(() => buildRoomCards(ownerStructure.value, realtimeSubTypes.value))
const systemModules = computed(() => buildSystemModules(ownerStructure.value, realtimeSubTypes.value))
const realtimeText = computed(() => {
  if (ownerLoading.value) return 'SYNC'
  if (ownerRealtime.value?.success === false) return 'OFFLINE'
  if (ownerRealtime.value) return 'LIVE SNAPSHOT'
  return 'NO DATA'
})
const overallStatus = computed(() => {
  const statuses = [
    ...roomCards.value.map((r) => r.status),
    ...systemModules.value.map((m) => m.status),
  ]
  if (statuses.includes('fault')) return { level: 'fault', text: '告警' }
  if (statuses.includes('warning')) return { level: 'warning', text: '预警' }
  if (statuses.some((s) => s === 'normal')) return { level: 'normal', text: '正常' }
  return { level: 'idle', text: '等待数据' }
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

async function loadOwnerHome(force = false) {
  if (ownerLoading.value && !force) return
  ownerError.value = ''
  try {
    await ownerStore.ensureBindings({ force, allowStale: !force })

    if (!bindings.value.length) {
      ownerLoading.value = false
      return
    }

    const activeSp = readActiveSpecificPart()
    const matchedIndex = bindings.value.findIndex((b) => b.specific_part === activeSp)
    selectedBindingIndex.value = matchedIndex >= 0 ? matchedIndex : Math.min(selectedBindingIndex.value, bindings.value.length - 1)

    const sp = currentSpecificPart.value
    if (sp) {
      ownerStore.setActiveSpecificPart(sp)
      ownerStore.hydrateStructure(sp)
      ownerStore.hydrateRealtime(sp)
    }

    // 先 hydrate 缓存再判断 loading，避免缓存命中时仍显示 loading
    ownerLoading.value = force || !ownerHasContent.value

    await loadOwnerPart(sp, force)
  } catch (err) {
    ownerError.value = '户型舱图加载失败，请下拉刷新'
  } finally {
    ownerLoading.value = false
  }
}

async function loadOwnerPart(specificPart, force = false) {
  if (!specificPart) return

  const [structureRes, realtimeRes] = await Promise.allSettled([
    ownerStore.ensureStructure(specificPart, { force, allowStale: !force }),
    ownerStore.ensureRealtime(specificPart, { force, allowStale: !force }),
  ])

  if ((structureRes.status !== 'fulfilled' || structureRes.value?.success === false) && !ownerStructure.value) {
    ownerError.value = '房间结构暂不可用'
  }

  if ((realtimeRes.status !== 'fulfilled' || realtimeRes.value?.success === false) && !ownerRealtime.value) {
    if (!ownerError.value) ownerError.value = '实时参数暂不可用'
  }
}

function readActiveSpecificPart() {
  if (ownerStore.activeSpecificPart) return ownerStore.activeSpecificPart
  try { return uni.getStorageSync('active_specific_part') || '' } catch (e) { return '' }
}

function onBindingChange(e) {
  const idx = Number(e.detail.value)
  selectedBindingIndex.value = idx
  const sp = currentSpecificPart.value
  if (sp) {
    ownerLoading.value = !ownerStore.structureFor(sp) && !ownerStore.realtimeFor(sp)
    loadOwnerPart(sp, false).finally(() => { ownerLoading.value = false })
  }
}

function flattenRealtimeSubTypes(data) {
  const out = {}
  const groups = data || {}
  for (const groupKey of Object.keys(groups)) {
    const group = groups[groupKey] || {}
    const subTypes = group.sub_types || {}
    for (const subKey of Object.keys(subTypes)) {
      out[subKey] = subTypes[subKey] || {}
    }
  }
  return out
}

function buildRoomCards(structure, subTypeMap) {
  const rooms = structure?.rooms || []
  if (!rooms.length) return fallbackRoomsFromRealtime(subTypeMap)
  return rooms.map((room, index) => {
    const devices = room.devices || []
    const params = collectParamsForDevices(devices, subTypeMap)
    const status = statusFromParams(params, devices.length > 0)
    return {
      id: `room-${room.room_id || index}`,
      name: room.room_name || room.ori_room_name || `房间 ${index + 1}`,
      status,
      tempText: tempTextFromParams(params),
      devices: compactRoomDevices(devices),
    }
  })
}

function fallbackRoomsFromRealtime(subTypeMap) {
  const panelKeys = Object.keys(subTypeMap).filter((key) => key.indexOf('panel_') === 0 || key.indexOf('thermostat') >= 0)
  return panelKeys.map((key, index) => {
    const sub = subTypeMap[key] || {}
    const params = sub.params || []
    return {
      id: `rt-${key}`,
      name: sub.display || panelNameFromSubType(key) || `房间 ${index + 1}`,
      status: statusFromParams(params, params.length > 0),
      tempText: tempTextFromParams(params),
      devices: [{ id: key, name: '温控', kind: 'panel' }],
    }
  })
}

function buildSystemModules(structure, subTypeMap) {
  const modules = []
  const allDevices = [
    ...((structure?.system_devices || [])),
  ]
  for (const room of (structure?.rooms || [])) {
    for (const device of (room.devices || [])) allDevices.push(device)
  }
  const claimed = new Set()

  for (const device of allDevices) {
    const kind = moduleKind(device)
    if (!kind) continue
    const claimKey = kind === 'fan' ? 'fan' : (kind === 'host' ? 'host' : String(device.device_sn || device.sub_type || kind))
    if (claimed.has(claimKey)) continue
    claimed.add(claimKey)

    const params = paramsForSubType(device.sub_type, subTypeMap)
    modules.push({
      id: `module-${claimKey}`,
      name: moduleName(device, kind),
      kind,
      status: statusFromParams(params, true),
      tempText: tempTextFromParams(params),
      raw: device,
    })
  }

  if (!modules.some((m) => m.kind === 'host')) {
    modules.unshift(buildSyntheticModule('host', subTypeMap))
  }
  if (!modules.some((m) => m.kind === 'fan')) {
    modules.push(buildSyntheticModule('fan', subTypeMap))
  }
  return modules.slice(0, 4)
}

function buildSyntheticModule(kind, subTypeMap) {
  const subKeys = Object.keys(subTypeMap)
  const matched = subKeys.find((key) => {
    if (kind === 'fan') return key.indexOf('fresh') >= 0 || key.indexOf('air') >= 0
    return key.indexOf('hydraulic') >= 0 || key.indexOf('host') >= 0 || key.indexOf('main') >= 0
  })
  const params = matched ? paramsForSubType(matched, subTypeMap) : []
  return {
    id: `module-${kind}-synthetic`,
    name: kind === 'fan' ? '风机' : '主机',
    kind,
    status: statusFromParams(params, params.length > 0),
    tempText: tempTextFromParams(params),
  }
}

function collectParamsForDevices(devices, subTypeMap) {
  const params = []
  for (const device of devices || []) {
    params.push(...paramsForSubType(device.sub_type, subTypeMap))
  }
  return params
}

function paramsForSubType(subType, subTypeMap) {
  if (!subType || !subTypeMap[subType]) return []
  return subTypeMap[subType].params || []
}

function compactRoomDevices(devices) {
  const result = []
  for (const device of devices || []) {
    const kind = deviceKind(device)
    result.push({
      id: String(device.device_sn || `${device.sub_type}-${result.length}`),
      name: kind === 'panel' ? '温控' : (kind === 'fan' ? '风机' : (kind === 'host' ? '主机' : '设备')),
      kind,
    })
    if (result.length >= 3) break
  }
  if (!result.length) result.push({ id: 'empty-panel', name: '面板', kind: 'panel' })
  return result
}

function statusFromParams(params, hasDevice) {
  if (!params || params.length === 0) return hasDevice ? 'idle' : 'idle'
  let status = 'normal'
  for (const p of params) {
    const sev = severityFromParam(p)
    if (sev) status = worseStatus(status, sev)
  }
  return status
}

function severityFromParam(param) {
  const tag = String(param?.param_name || '')
  const value = param?.value
  const direct = attrSeverity(tag, value)
  if (direct) return direct
  const lower = tag.toLowerCase()
  if (param?.is_stale) return 'warning'
  if ((lower.indexOf('alarm') >= 0 || lower.indexOf('warning') >= 0) && isNonZero(value)) return 'warning'
  if ((lower.indexOf('fault') >= 0 || lower.indexOf('error') >= 0) && isNonZero(value)) return 'fault'
  return null
}

function isNonZero(value) {
  if (value === null || value === undefined || value === '') return false
  const n = Number(value)
  if (!Number.isNaN(n)) return n !== 0
  const s = String(value).toLowerCase()
  return !(s === '0' || s === 'normal' || s === 'false' || s === 'off')
}

function tempTextFromParams(params) {
  const temp = pickTemperature(params)
  return temp == null ? '--°C' : `${temp}°C`
}

function pickTemperature(params) {
  const candidates = (params || []).filter((p) => {
    const key = `${p.param_name || ''} ${p.display_name || ''}`.toLowerCase()
    const isTemp = key.indexOf('temp') >= 0 || key.indexOf('temperature') >= 0 || key.indexOf('温度') >= 0
    const excluded = key.indexOf('set') >= 0 || key.indexOf('设定') >= 0 || key.indexOf('dew') >= 0 ||
      key.indexOf('露点') >= 0 || key.indexOf('water') >= 0 || key.indexOf('水') >= 0
    return isTemp && !excluded && p.value !== null && p.value !== undefined && p.value !== ''
  })
  const picked = candidates[0] || (params || []).find((p) => {
    const key = `${p.param_name || ''} ${p.display_name || ''}`.toLowerCase()
    return (key.indexOf('temp') >= 0 || key.indexOf('温度') >= 0) && p.value !== null && p.value !== undefined && p.value !== ''
  })
  if (!picked) return null
  const n = Number(picked.value)
  if (Number.isNaN(n)) return null
  const normalized = Math.abs(n) > 80 && Math.abs(n) < 1000 ? n / 10 : n
  return normalized.toFixed(1)
}

function panelNameFromSubType(subType) {
  const map = {
    panel_study_room: '书房',
    panel_bedroom: '次卧',
    panel_children_room: '主卧',
    panel_fourth_children: '儿童房',
    main_thermostat: '客厅',
  }
  return map[subType] || ''
}

function moduleKind(device) {
  const code = String(device?.product_code || '')
  const sub = String(device?.sub_type || '')
  if (code === '270001' || sub.indexOf('hydraulic') >= 0 || sub.indexOf('host') >= 0) return 'host'
  if (code === '130004' || code === '10016' || sub.indexOf('fresh_air') >= 0) return 'fan'
  if (code === '260001' || code === '120003' || sub.indexOf('thermostat') >= 0 || sub.indexOf('panel_') === 0) return 'panel'
  return ''
}

function deviceKind(device) {
  return moduleKind(device) || 'panel'
}

function moduleName(device, kind) {
  if (kind === 'host') return '主机'
  if (kind === 'fan') return '风机'
  if (device?.sub_type === 'main_thermostat') return '主温控'
  return '面板'
}

function openRoom(room) {
  uni.showToast({ title: `${room.name} ${room.tempText}`, icon: 'none' })
}

function openModule(module) {
  uni.showToast({ title: `${module.name} ${statusText(module.status)}`, icon: 'none' })
}

function statusText(status) {
  if (status === 'fault') return '告警'
  if (status === 'warning') return '预警'
  if (status === 'normal') return '正常'
  return '等待数据'
}

function goBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}

const poller = new PagePoller(fetchDashboard, 30000)

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }

  poller.stop()
  if (authStore.role === 'user') {
    uni.hideTabBar({ animation: false, fail: () => {} })
    try { uni.setNavigationBarColor({ frontColor: '#ffffff', backgroundColor: '#05070f' }) } catch (e) {}
    loadOwnerHome()
  } else {
    uni.showTabBar({ animation: false, fail: () => {} })
    try { uni.setNavigationBarColor({ frontColor: '#ffffff', backgroundColor: '#1a73e8' }) } catch (e) {}
    poller.start()
  }
})

onHide(() => {
  poller.stop()
})

onPullDownRefresh(async () => {
  if (authStore.role === 'user') {
    await loadOwnerHome(true)
  } else {
    await fetchDashboard(true)
  }
  uni.stopPullDownRefresh()
})

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

<style scoped>
.owner-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070f;
  overflow: hidden;
}
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
    linear-gradient(rgba(56,230,224,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,230,224,0.06) 1px, transparent 1px);
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
.status-spacer {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
}
.owner-header {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  min-height: 104rpx;
  padding: 0 28rpx 10rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.owner-title-box {
  min-width: 0;
  flex: 1;
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
}
.owner-state {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  padding: 12rpx 18rpx;
  border: 1rpx solid rgba(120, 160, 255, 0.22);
  background: rgba(7, 14, 31, 0.72);
}
.owner-state text {
  font-size: 22rpx;
  color: #9fb8d8;
}
.state-led {
  width: 14rpx;
  height: 14rpx;
  margin-right: 10rpx;
  background: #5f7da6;
  transform: rotate(45deg);
}
.state-normal .state-led { background: #27f5b5; box-shadow: 0 0 14rpx #27f5b5; }
.state-warning .state-led { background: #ffd400; box-shadow: 0 0 14rpx #ffd400; }
.state-fault .state-led { background: #ff315d; box-shadow: 0 0 14rpx #ff315d; }
.state-normal text { color: #27f5b5; }
.state-warning text { color: #ffd400; }
.state-fault text { color: #ff6b8b; }
.owner-content {
  position: relative;
  z-index: 4;
  flex: 1 1 0;
  min-height: 0;
}
.unit-bar {
  padding: 10rpx 28rpx 0;
}
.unit-picker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 22rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.22);
  background: rgba(7, 15, 32, 0.68);
}
.unit-label {
  font-size: 22rpx;
  color: #6f8cad;
}
.unit-value {
  max-width: 470rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 26rpx;
  color: #eaf6ff;
}
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
.ship-shell {
  position: relative;
  overflow: hidden;
  padding: 24rpx 22rpx 30rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.26);
  background:
    linear-gradient(135deg, rgba(13, 31, 50, 0.92), rgba(18, 16, 45, 0.88)),
    linear-gradient(180deg, rgba(47, 244, 224, 0.08), transparent 34%);
  clip-path: polygon(50% 0, 94% 7%, 100% 49%, 91% 95%, 50% 100%, 9% 95%, 0 49%, 6% 7%);
  box-shadow: inset 0 0 44rpx rgba(47, 244, 224, 0.12), 0 0 28rpx rgba(0, 0, 0, 0.35);
}
.ship-shell.state-warning { border-color: rgba(255, 212, 0, 0.42); }
.ship-shell.state-fault { border-color: rgba(255, 49, 93, 0.48); }
.ship-nose,
.ship-tail {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
}
.ship-nose {
  height: 58rpx;
}
.ship-nose text {
  position: relative;
  z-index: 2;
  font-size: 22rpx;
  color: rgba(244, 251, 255, 0.82);
  font-weight: 700;
}
.nose-plate {
  position: absolute;
  width: 220rpx;
  height: 42rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.35);
  background: rgba(47, 244, 224, 0.06);
  clip-path: polygon(18% 0, 82% 0, 100% 100%, 0 100%);
}
.system-dock {
  display: flex;
  gap: 14rpx;
  align-items: stretch;
  justify-content: center;
  margin: 12rpx 16rpx 20rpx;
}
.module-node {
  position: relative;
  flex: 1;
  min-width: 0;
  padding: 16rpx 12rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.22);
  background: linear-gradient(180deg, rgba(8, 20, 38, 0.82), rgba(6, 12, 28, 0.72));
}
.module-node.state-warning,
.room-cell.state-warning {
  border-color: rgba(255, 212, 0, 0.54);
}
.module-node.state-fault,
.room-cell.state-fault {
  border-color: rgba(255, 49, 93, 0.6);
}
.module-visual {
  position: relative;
  height: 84rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.host-top {
  position: relative;
  width: 104rpx;
  height: 58rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.65);
  background: linear-gradient(90deg, rgba(47, 244, 224, 0.10), rgba(124, 58, 237, 0.18));
}
.host-core {
  position: absolute;
  left: 32rpx;
  top: 14rpx;
  width: 40rpx;
  height: 30rpx;
  border: 1rpx solid rgba(244, 251, 255, 0.48);
}
.host-fin {
  position: absolute;
  top: 8rpx;
  width: 4rpx;
  height: 42rpx;
  background: rgba(47, 244, 224, 0.45);
}
.host-f1 { left: 12rpx; }
.host-f2 { right: 12rpx; }
.host-f3 { left: 50rpx; }
.fan-top {
  width: 78rpx;
  height: 78rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.55);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fan-ring {
  position: relative;
  width: 58rpx;
  height: 58rpx;
  border-radius: 50%;
  animation: fanSpin 3.8s linear infinite;
}
.fan-blade {
  position: absolute;
  left: 26rpx;
  top: 5rpx;
  width: 9rpx;
  height: 24rpx;
  border-radius: 10rpx;
  background: rgba(47, 244, 224, 0.72);
  transform-origin: 4rpx 24rpx;
}
.fan-b2 { transform: rotate(120deg); }
.fan-b3 { transform: rotate(240deg); }
.panel-top {
  width: 78rpx;
  height: 58rpx;
  border: 2rpx solid rgba(143, 217, 255, 0.50);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 8rpx;
}
.panel-screen {
  height: 18rpx;
  background: rgba(47, 244, 224, 0.38);
}
.panel-line {
  margin-top: 8rpx;
  height: 4rpx;
  background: rgba(143, 217, 255, 0.35);
}
.module-damage {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-spark {
  position: absolute;
  width: 18rpx;
  height: 5rpx;
  background: #ffd400;
  animation: damageBlink 1.1s ease-in-out infinite;
}
.state-fault .damage-spark {
  background: #ff315d;
}
.ds1 { right: 16rpx; top: 16rpx; transform: rotate(28deg); }
.ds2 { left: 18rpx; bottom: 20rpx; transform: rotate(-32deg); }
.module-copy {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6rpx;
}
.module-name {
  min-width: 0;
  font-size: 22rpx;
  color: #cde7f7;
}
.module-temp {
  font-size: 22rpx;
  color: #2ff4e0;
  font-weight: 700;
}
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
.room-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 14rpx;
  margin: 12rpx 10rpx 14rpx;
}
.room-cell {
  position: relative;
  box-sizing: border-box;
  width: calc(50% - 7rpx);
  min-height: 220rpx;
  padding: 20rpx;
  overflow: hidden;
  border: 1rpx solid rgba(47, 244, 224, 0.28);
  background:
    linear-gradient(135deg, rgba(14, 33, 54, 0.90), rgba(9, 17, 37, 0.86)),
    linear-gradient(180deg, rgba(47, 244, 224, 0.05), transparent);
}
.room-count-1 .room-cell {
  width: 100%;
  min-height: 300rpx;
}
.room-shape-0 { clip-path: polygon(0 0, 92% 0, 100% 20%, 100% 100%, 0 100%); }
.room-shape-1 { clip-path: polygon(8% 0, 100% 0, 100% 100%, 0 100%, 0 20%); }
.room-shape-2 { clip-path: polygon(0 0, 100% 0, 100% 82%, 90% 100%, 0 100%); }
.room-shape-3 { clip-path: polygon(0 0, 100% 0, 100% 100%, 10% 100%, 0 82%); }
.room-panel-lines {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.42;
}
.panel-line-a,
.panel-line-b {
  position: absolute;
  background: rgba(143, 217, 255, 0.18);
}
.panel-line-a {
  left: 18rpx;
  right: 18rpx;
  top: 74rpx;
  height: 1rpx;
}
.panel-line-b {
  top: 18rpx;
  bottom: 18rpx;
  left: 58%;
  width: 1rpx;
}
.room-damage {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-mark {
  position: absolute;
  width: 34rpx;
  height: 7rpx;
  background: #ffd400;
  box-shadow: 0 0 14rpx rgba(255, 212, 0, 0.85);
  animation: damageBlink 1.2s ease-in-out infinite;
}
.state-fault .damage-mark {
  background: #ff315d;
  box-shadow: 0 0 16rpx rgba(255, 49, 93, 0.9);
}
.dm1 { right: 22rpx; top: 26rpx; transform: rotate(24deg); }
.dm2 { left: 26rpx; bottom: 42rpx; transform: rotate(-30deg); animation-delay: 0.2s; }
.dm3 { right: 42rpx; bottom: 70rpx; width: 20rpx; transform: rotate(65deg); animation-delay: 0.5s; }
.room-head {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.room-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 30rpx;
  color: #f3fbff;
  font-weight: 700;
}
.room-status-dot {
  width: 14rpx;
  height: 14rpx;
  margin-left: 12rpx;
  background: #5f7da6;
  transform: rotate(45deg);
}
.room-cell.state-normal .room-status-dot { background: #27f5b5; box-shadow: 0 0 12rpx #27f5b5; }
.room-cell.state-warning .room-status-dot { background: #ffd400; box-shadow: 0 0 12rpx #ffd400; }
.room-cell.state-fault .room-status-dot { background: #ff315d; box-shadow: 0 0 12rpx #ff315d; }
.temp-board {
  position: relative;
  z-index: 2;
  display: inline-flex;
  align-items: flex-end;
  margin-top: 24rpx;
  padding: 12rpx 16rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.30);
  background: rgba(5, 12, 24, 0.62);
}
.temp-value {
  font-size: 42rpx;
  line-height: 1;
  color: #2ff4e0;
  font-weight: 800;
}
.temp-label {
  margin-left: 10rpx;
  padding-bottom: 4rpx;
  font-size: 18rpx;
  color: rgba(143, 217, 255, 0.58);
}
.room-devices {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin-top: 22rpx;
}
.mini-device {
  display: flex;
  align-items: center;
  max-width: 48%;
  padding: 7rpx 9rpx;
  background: rgba(143, 217, 255, 0.08);
  border: 1rpx solid rgba(143, 217, 255, 0.13);
}
.mini-device text {
  font-size: 18rpx;
  color: rgba(218, 238, 255, 0.82);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini-icon {
  flex: 0 0 auto;
  width: 16rpx;
  height: 16rpx;
  margin-right: 8rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.72);
}
.mini-fan .mini-icon {
  border-radius: 50%;
}
.mini-host .mini-icon {
  width: 20rpx;
}
.ship-tail {
  height: 58rpx;
  gap: 46rpx;
}
.tail-engine {
  width: 84rpx;
  height: 18rpx;
  background: linear-gradient(90deg, transparent, rgba(47, 244, 224, 0.78), transparent);
  animation: enginePulse 1.8s ease-in-out infinite;
}
.te2 { animation-delay: 0.45s; }
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
