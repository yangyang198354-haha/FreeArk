<!--
  @module MOD-1110-FE-02
  @implements IFC-1110-FE-02-1 (initOwnerHome), IFC-1110-FE-02-2 (toggleExpand),
              IFC-1110-FE-02-3 (loadRealtimeParams), IFC-1110-FE-02-4 (onRefresh),
              IFC-1110-FE-02-5 (runRefreshPathA), IFC-1110-FE-02-6 (runRefreshPathB),
              IFC-1110-FE-02-7 (writeCache), IFC-1110-FE-02-8 (readCache),
              IFC-1110-FE-02-9 (goToSettings)
  @depends MOD-1110-FE-01 (useMqttClient.js), MOD-1110-FE-03 (api.js 新增项)
  @author sub_agent_software_developer
  @description 业主端·我的房产（房间结构） + 参数设置（v1.11.0）一体页。
    上区：我的房产 — 套卡片 → 展开 → 房间分组 → 参数 + 可写标注 + 刷新
    下区：参数设置（原有写链路，零语义变更，通过 useMqttClient 单例迁移）

    关键设计：
    - ADR-1110-04: MQTT 单例由 useMqttClient 管理（acquire/release 引用计数）
    - ADR-1110-06: 缓存读写同步（getStorageSync/setStorageSync）
    - ADR-1110-07: 实时参数懒加载（展开时才请求）
    - ADR-1110-05: 垂直二区布局，"去设置"用 pageScrollTo 到锚点 #param-settings-anchor
    - DEV-01: 路径A超时仅提示，不自动降级路径B（用户已拍板）
-->
<template>
  <view class="ps-page">

    <!-- ══ 区域一：我的房产（v1.11.0 新增）══════════════════════════════════ -->
    <view class="owner-home-section">
      <view class="section-header">
        <text class="section-title">我的房产</text>
      </view>

      <!-- 离线横幅（REQ-FUNC-005）-->
      <view v-if="isOffline" class="offline-banner">
        <text>当前离线，显示缓存数据</text>
      </view>

      <!-- config 获取失败提示（REQ-FUNC-002 降级）-->
      <view v-if="configFailed" class="config-warn-banner">
        <text>参数配置获取失败，可设置参数标注不可用</text>
      </view>

      <!-- 无绑定（US-OWNER-001 AC-4）-->
      <view v-if="!ownerLoading && bindStatus.length === 0" class="tip">
        <text>您还没有绑定专有部分</text>
        <view class="link-btn" @tap="goBind"><text>去绑定</text></view>
      </view>

      <!-- 套卡片列表 -->
      <view
        v-for="part in bindStatus"
        :key="part.specific_part"
        class="part-card"
      >
        <!-- 卡片头：location_name + 展开/折叠 + 刷新按钮 -->
        <view class="part-card-header" @tap="toggleExpand(part.specific_part)">
          <text class="part-name">{{ part.location_name || part.specific_part }}</text>
          <view class="part-header-right">
            <view
              v-if="partState[part.specific_part] && partState[part.specific_part].expanded"
              class="refresh-btn"
              :class="{ 'refresh-btn-busy': partState[part.specific_part].refreshing }"
              @tap.stop="onRefresh(part.specific_part)"
            >
              <text>{{ partState[part.specific_part].refreshing ? '刷新中…' : '刷新' }}</text>
            </view>
            <text class="expand-arrow">{{ partState[part.specific_part] && partState[part.specific_part].expanded ? '▲' : '▼' }}</text>
          </view>
        </view>

        <!-- 展开内容 -->
        <view v-if="partState[part.specific_part] && partState[part.specific_part].expanded" class="part-expand">

          <!-- 时间戳标签（REQ-FUNC-004）-->
          <text v-if="partState[part.specific_part].tsLabel" class="ts-label">
            {{ partState[part.specific_part].tsLabel }}
          </text>

          <!-- 错误提示（路径A超时/刷新失败，DEV-01）-->
          <view v-if="partState[part.specific_part].refreshError" class="refresh-error-msg">
            <text>{{ partState[part.specific_part].refreshError }}</text>
          </view>

          <!-- loading 状态（US-OWNER-004 AC-3）-->
          <view v-if="partState[part.specific_part].loading" class="tip-loading">
            <text>加载中…</text>
          </view>

          <!-- 参数分组（group → sub_type → params）-->
          <view v-else-if="partState[part.specific_part].data">
            <view
              v-for="(group, gKey) in partState[part.specific_part].data"
              :key="gKey"
              class="group-block"
            >
              <view
                v-for="(sub, sKey) in group.sub_types"
                :key="sKey"
                class="room-block"
              >
                <!-- 房间标题（panel_* = sub_type_display；系统级 = "全屋系统"）-->
                <text class="room-title">{{ sub.display }}</text>
                <view
                  v-for="param in sub.params"
                  :key="param.param_name"
                  class="param-row"
                >
                  <text class="param-name">{{ param.display_name || param.param_name }}</text>
                  <view class="param-right">
                    <text class="param-value">{{ param.value != null ? param.value : '—' }}</text>
                    <view v-if="isWritable(param.param_name)" class="param-badges">
                      <text class="badge-writable">可设置</text>
                      <view
                        class="btn-go-settings"
                        @tap.stop="goToSettings(part.specific_part)"
                      >
                        <text>去设置</text>
                      </view>
                    </view>
                    <text v-else class="badge-readonly">只读</text>
                  </view>
                </view>
              </view>
            </view>
          </view>

          <!-- 无数据降级（REQ-FUNC-005）-->
          <view v-else class="tip-error">
            <text>{{ partState[part.specific_part].errorMsg || '获取设备数据失败，请点击重试' }}</text>
            <view class="retry-btn" @tap.stop="onRefresh(part.specific_part)">
              <text>重试</text>
            </view>
          </view>

        </view>
      </view>

      <!-- 加载状态（ownerLoading 期间）-->
      <view v-if="ownerLoading" class="tip">
        <text>加载中…</text>
      </view>
    </view>

    <!-- ══ 区域二：参数设置（原有内容，零语义变更）════════════════════════ -->
    <view class="param-settings-section" id="param-settings-anchor">

      <!-- 房间选择（多房间时）-->
      <view v-if="rooms.length > 1" class="room-bar">
        <text class="room-label">房间</text>
        <picker :range="roomLabels" :value="roomIndex" @change="onRoomChange">
          <view class="room-pick">{{ currentRoom ? (currentRoom.location_name || currentRoom.specific_part) : '请选择' }} ›</view>
        </picker>
      </view>
      <view v-else-if="currentRoom" class="room-bar">
        <text class="room-single">{{ currentRoom.location_name || currentRoom.specific_part }}</text>
        <text class="conn-dot" :class="{ on: mqttConnected }">{{ mqttConnected ? '已连接' : '连接中…' }}</text>
      </view>

      <scroll-view scroll-y class="ps-body">
        <view v-if="loading" class="tip"><text>加载中…</text></view>
        <view v-else-if="rooms.length === 0" class="tip">
          <text>您还没有绑定专有部分</text>
          <view class="link-btn" @tap="goBind"><text>去绑定</text></view>
        </view>
        <view v-else-if="!hasDevices" class="tip"><text>正在获取设备数据…（请确保设备在线）</text></view>

        <template v-else>
          <view v-for="dev in deviceList" :key="dev.deviceSn" class="dev-card">
            <view class="dev-head">
              <text class="dev-role">{{ dev.role }}</text>
              <text class="dev-sn">#{{ dev.deviceSn }}</text>
            </view>

            <view v-for="w in dev.writable" :key="w.tag" class="attr-row">
              <text class="attr-label">{{ w.label }}</text>

              <!-- toggle -->
              <switch
                v-if="w.control === 'toggle'"
                :checked="curVal(dev.deviceSn, w.tag) === 'on'"
                @change="onToggle(dev, w.tag, $event)"
              />

              <!-- select -->
              <picker
                v-else-if="w.control === 'select'"
                :range="w.optionLabels"
                :value="selIndex(dev.deviceSn, w)"
                @change="onSelect(dev, w, $event)"
              >
                <view class="sel-val">{{ curLabel(dev.deviceSn, w) }} ›</view>
              </picker>

              <!-- number -->
              <view v-else-if="w.control === 'number'" class="num-ctl">
                <view class="num-btn" @tap="onStep(dev, w, -1)">−</view>
                <text class="num-val">{{ curVal(dev.deviceSn, w.tag) }}{{ w.unit || '' }}</text>
                <view class="num-btn" @tap="onStep(dev, w, 1)">＋</view>
              </view>
            </view>

            <view
              v-if="hasPending(dev.deviceSn)"
              class="apply-btn"
              :class="{ busy: applyingSn === dev.deviceSn }"
              @tap="applyDevice(dev)"
            >
              <text>{{ applyingSn === dev.deviceSn ? '下发中…' : '下发更改' }}</text>
            </view>
          </view>
        </template>
      </scroll-view>
    </view>

  </view>
</template>

<script setup>
/**
 * @module MOD-1110-FE-02
 * @implements IFC-1110-FE-02-1 ~ IFC-1110-FE-02-9
 * @depends MOD-1110-FE-01 (useMqttClient), MOD-1110-FE-03 (api.js 新增项)
 */
import { ref, computed, reactive } from 'vue'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'
import { buildWriteItems } from '@/utils/screenMqtt'
import { useMqttClient } from '@/utils/useMqttClient'

const authStore = useAuthStore()

// ── MQTT 单例 composable（MOD-1110-FE-01，ADR-1110-04）──────────────────────
const mqttClient = useMqttClient()

// ── 区域二：参数设置 原有 state（零语义变更）───────────────────────────────

const loading = ref(true)
const rooms = ref([])
const roomIndex = ref(0)
const broker = ref(null)
const topics = ref(null)
const config = ref({ writable_attrs: {}, product_code_role: {}, mode_energy_link: {}, link_product_codes: [] })

const devices = reactive({})        // deviceSn -> {productCode, attrs:{tag:val}}
const edits = reactive({})          // deviceSn -> {tag: newVal}
const mqttConnected = computed(() => mqttClient.connected.value)
const applyingSn = ref('')

let knownSns = new Set()   // 本次连接已发现的 deviceSn（含缓存载入）
let firstProbeDone = false // 是否已做过首次邻近探测

// onDeviceUpdate 注销函数（onUnload 时调用）
let _offDeviceUpdate = null

const currentRoom = computed(() => rooms.value[roomIndex.value] || null)
const roomLabels = computed(() => rooms.value.map(r => r.location_name || r.specific_part))
const hasDevices = computed(() => Object.keys(devices).length > 0)

// 设备列表（含可写属性定义），按 deviceSn 排序
const deviceList = computed(() => {
  const wa = config.value.writable_attrs || {}
  const roleMap = config.value.product_code_role || {}
  return Object.keys(devices).sort().map((sn) => {
    const d = devices[sn]
    const writable = Object.keys(d.attrs)
      .filter((tag) => wa[tag])
      .map((tag) => {
        const c = wa[tag]
        return {
          tag,
          label: c.label || tag,
          control: c.control,
          unit: c.unit,
          step: c.step || 1,
          min: c.min, max: c.max,
          options: c.options || [],
          optionLabels: (c.options || []).map(o => o.label),
        }
      })
    return {
      deviceSn: sn,
      productCode: d.productCode,
      role: roleMap[d.productCode] || `设备 ${d.productCode || ''}`,
      writable,
    }
  }).filter(d => d.writable.length > 0)
})

function curVal(sn, tag) {
  if (edits[sn] && edits[sn][tag] !== undefined) return edits[sn][tag]
  return devices[sn] ? devices[sn].attrs[tag] : undefined
}
function curLabel(sn, w) {
  const v = curVal(sn, w.tag)
  const opt = w.options.find(o => o.value === v)
  return opt ? opt.label : (v ?? '—')
}
function selIndex(sn, w) {
  const v = curVal(sn, w.tag)
  const i = w.options.findIndex(o => o.value === v)
  return i >= 0 ? i : 0
}
function hasPending(sn) {
  return edits[sn] && Object.keys(edits[sn]).length > 0
}
function setEdit(sn, tag, val) {
  if (!edits[sn]) edits[sn] = {}
  edits[sn][tag] = val
}

function onToggle(dev, tag, e) {
  setEdit(dev.deviceSn, tag, e.detail.value ? 'on' : 'off')
}
function onSelect(dev, w, e) {
  const opt = w.options[e.detail.value]
  if (opt) setEdit(dev.deviceSn, w.tag, opt.value)
}
function onStep(dev, w, dir) {
  const cur = parseFloat(curVal(dev.deviceSn, w.tag))
  let base = isNaN(cur) ? (w.min ?? 0) : cur
  let next = base + dir * (w.step || 1)
  if (w.min !== undefined) next = Math.max(w.min, next)
  if (w.max !== undefined) next = Math.min(w.max, next)
  next = Number.isInteger(w.step) ? String(next) : next.toFixed(1)
  setEdit(dev.deviceSn, w.tag, String(next))
}

// ── 区域二 连接管理（已迁移到 useMqttClient，ADR-1110-04）──────────────────

async function loadConfig() {
  loading.value = true
  try {
    const res = await api.getDeviceSettingsConfig()
    broker.value = res.broker
    topics.value = res.topics
    config.value = res.config || config.value
    rooms.value = res.rooms || []
    if (rooms.value.length > 0) await connectRoom()
  } catch (err) {
    uni.showToast({ title: '加载配置失败，请重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function connectRoom() {
  const room = currentRoom.value
  if (!room || !room.screen_mac) return

  // 清空旧设备状态（连接切换）
  Object.keys(devices).forEach(k => delete devices[k])
  Object.keys(edits).forEach(k => delete edits[k])
  knownSns = new Set()
  firstProbeDone = false

  // 注销旧的 onDeviceUpdate 监听
  if (_offDeviceUpdate) { _offDeviceUpdate(); _offDeviceUpdate = null }

  const mac = room.screen_mac

  // 注册 DeviceStatusUpdate 回调（通过单例 composable，ADR-1110-04）
  _offDeviceUpdate = mqttClient.onDeviceUpdate((p) => {
    const prev = devices[p.deviceSn] || { productCode: p.productCode, attrs: {} }
    devices[p.deviceSn] = {
      productCode: p.productCode != null ? p.productCode : prev.productCode,
      attrs: { ...prev.attrs, ...p.attrs },
    }
    const sn = String(p.deviceSn)
    if (!knownSns.has(sn)) {
      knownSns.add(sn)
      persistSns(mac)
      if (!firstProbeDone) { firstProbeDone = true; probeNeighbors(mac, p.deviceSn) }
    }
  })

  try {
    console.log('[param-settings] connectRoom screen_mac=', mac)
    await mqttClient.acquire(broker.value, topics.value)   // IFC-1110-FE-01-1
    mqttClient.subscribe(mac)                               // IFC-1110-FE-01-3
    console.log('[param-settings] subscribed uplink for', mac)

    // 主动拉取：缓存过的 deviceSn 立即读
    const cached = loadSns(mac)
    if (cached.length) {
      cached.forEach(s => knownSns.add(s))
      firstProbeDone = true
      mqttClient.publishRead(mac, cached)                   // IFC-1110-FE-01-4
      console.log('[param-settings] active read cached sns:', cached.join(','))
    }
  } catch (e) {
    console.error('[param-settings] connectRoom FAILED:', e && e.message)
    uni.showToast({ title: '设备通道连接失败：' + (e && e.message || ''), icon: 'none' })
  }
}

// deviceSn 缓存（按 screenMac）+ 邻近探测
const snCacheKey = (mac) => `ds_sns_${mac}`
function loadSns(mac) {
  try { const a = uni.getStorageSync(snCacheKey(mac)); return Array.isArray(a) ? a.map(String) : [] } catch (e) { return [] }
}
function persistSns(mac) {
  try { uni.setStorageSync(snCacheKey(mac), Array.from(knownSns)) } catch (e) { /* ignore */ }
}
function probeNeighbors(mac, sn) {
  const base = parseInt(sn, 10)
  if (isNaN(base) || !mqttClient.connected.value) return
  const range = []
  for (let d = -8; d <= 8; d++) { const v = base + d; if (v > 0 && v !== base) range.push(String(v)) }
  mqttClient.publishRead(mac, range)                        // IFC-1110-FE-01-4
  console.log('[param-settings] probe neighbors around', sn)
}

async function applyDevice(dev) {
  const sn = dev.deviceSn
  const room = currentRoom.value
  if (!mqttClient.connected.value || !room) {
    uni.showToast({ title: '通道未连接', icon: 'none' }); return
  }
  if (applyingSn.value) return
  applyingSn.value = sn
  const pending = { ...edits[sn] }
  const auditItems = []
  let okCount = 0, failCount = 0

  for (const tag of Object.keys(pending)) {
    const target = pending[tag]
    const oldVal = devices[sn] ? devices[sn].attrs[tag] : ''
    const items = buildWriteItems(dev.productCode, tag, target, config.value)
    try {
      mqttClient.publishWrite(room.screen_mac, sn, items)   // IFC-1110-FE-01-5
      await mqttClient.waitConfirm(sn, tag, target, 8000)   // IFC-1110-FE-01-6
      okCount++
      items.forEach(it => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: it.attrTag === tag ? String(oldVal ?? '') : '' }))
      if (edits[sn]) delete edits[sn][tag]
    } catch (e) {
      failCount++
      items.forEach(it => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: '' }))
    }
  }

  if (auditItems.length > 0) {
    try {
      await api.reportDeviceSettingsAudit({
        request_id: 'mp-' + Date.now(),
        specific_part: room.specific_part,
        screen_mac: room.screen_mac,
        device_sn: sn,
        result: failCount === 0 ? 'success' : (okCount === 0 ? 'timeout' : 'success'),
        items: auditItems,
      })
    } catch (e) { /* 静默 */ }
  }

  applyingSn.value = ''
  if (failCount === 0) uni.showToast({ title: '下发成功', icon: 'success' })
  else if (okCount === 0) uni.showToast({ title: '未确认，请重试或刷新', icon: 'none' })
  else uni.showToast({ title: `部分成功（${okCount}/${okCount + failCount}）`, icon: 'none' })
}

function onRoomChange(e) {
  roomIndex.value = e.detail.value
  connectRoom()
}

// ── 区域一：我的房产 state（v1.11.0 新增）────────────────────────────────────

/** GET /api/miniapp/bind/status/ 的 bindings 数组 */
const bindStatus = ref([])
const ownerLoading = ref(false)
const isOffline = ref(false)
const configFailed = ref(false)

/**
 * 每个 specific_part 的展开/加载/数据状态字典。
 * key = specific_part string
 * value = {
 *   expanded: boolean,
 *   loading: boolean,
 *   refreshing: boolean,
 *   refreshLockUntil: number,  // Date.now() + 3000，最短锁定到期时刻
 *   data: object | null,       // realtime-params 的 data 字段
 *   screen_mac: string,
 *   device_sns: number[],
 *   tsLabel: string,
 *   errorMsg: string | null,
 *   refreshError: string | null,
 * }
 */
const partState = reactive({})

/** 缓存 TTL（5 分钟，ADR-1110-06 / D-03）*/
const CACHE_TTL_MS = 5 * 60 * 1000

// ── IFC-1110-FE-02-7: writeCache ────────────────────────────────────────────

function writeCache(specificPart, data) {
  try {
    uni.setStorageSync(`owner_realtime_${specificPart}`, JSON.stringify(data))
    uni.setStorageSync(`owner_realtime_${specificPart}_ts`, new Date().toISOString())
  } catch (e) {
    console.warn('[param-settings] writeCache 失败:', e)
  }
}

// ── IFC-1110-FE-02-8: readCache ─────────────────────────────────────────────

function readCache(specificPart) {
  try {
    const raw = uni.getStorageSync(`owner_realtime_${specificPart}`)
    const tsRaw = uni.getStorageSync(`owner_realtime_${specificPart}_ts`)
    const data = raw ? JSON.parse(raw) : null
    const ts = tsRaw ? new Date(tsRaw) : null
    return { data, ts }
  } catch (e) {
    return { data: null, ts: null }
  }
}

// ── 时间戳标签工具 ───────────────────────────────────────────────────────────

function buildTsLabel(ts, suffix = '') {
  if (!ts) return ''
  const diffMs = Date.now() - ts.getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return `刚刚更新${suffix}`
  const stale = diffMs > CACHE_TTL_MS
  const timeStr = mins < 60 ? `${mins} 分钟前` : `${Math.floor(mins / 60)} 小时前`
  const prefix = stale ? '数据可能已过时（更新于 ' : '更新于 '
  const postfix = stale ? '）' : ''
  return `${prefix}${timeStr}${postfix}${suffix}`
}

// ── 初始化 partState ─────────────────────────────────────────────────────────

function _initPartState(specificPart) {
  if (!partState[specificPart]) {
    partState[specificPart] = {
      expanded: false,
      loading: false,
      refreshing: false,
      refreshLockUntil: 0,
      data: null,
      screen_mac: '',
      device_sns: [],
      tsLabel: '',
      errorMsg: null,
      refreshError: null,
    }
  }
}

// ── IFC-1110-FE-02-1: initOwnerHome ─────────────────────────────────────────

async function initOwnerHome() {
  if (ownerLoading.value) return
  ownerLoading.value = true

  // bind/status（config 已由 loadConfig() 取）。FND-009：原 Promise.allSettled 仅含 1 个
  // promise 属冗余，直接 try/catch await 等价且更清晰。
  try {
    const data = await api.getBindStatus()
    bindStatus.value = (data.bindings || data || []).filter(b => b.specific_part)
  } catch (e) {
    // 网络不通，标记离线
    isOffline.value = true
    bindStatus.value = []
  } finally {
    ownerLoading.value = false
  }

  // 初始化每个 specific_part 的 partState
  for (const part of bindStatus.value) {
    _initPartState(part.specific_part)
  }
}

// ── IFC-1110-FE-02-3: loadRealtimeParams ────────────────────────────────────

async function loadRealtimeParams(specificPart, forceRefresh = false) {
  const ps = partState[specificPart]
  if (!ps) return

  // 步骤1：同步读取缓存（ADR-1110-06）
  const { data: cachedData, ts: cachedTs } = readCache(specificPart)

  if (!forceRefresh && cachedData) {
    // 有缓存，立即渲染
    ps.data = cachedData
    ps.tsLabel = buildTsLabel(cachedTs)
    ps.loading = false
    ps.errorMsg = null
  } else if (!cachedData) {
    // 无缓存，显示 loading
    ps.loading = true
    ps.data = null
  }

  // 步骤2：后台异步刷新
  try {
    const res = await api.getOwnerRealtimeParams(specificPart)
    if (res && res.success) {
      ps.data = res.data || null
      ps.screen_mac = res.screen_mac || ''
      ps.device_sns = res.device_sns || []
      ps.tsLabel = buildTsLabel(new Date())
      ps.errorMsg = null
      ps.loading = false
      // 写缓存（ADR-1110-06）
      writeCache(specificPart, res.data || {})
    } else {
      // API 返回非 success（403/400 等）
      if (!cachedData) {
        ps.errorMsg = res && res.error ? res.error : '获取设备数据失败，请点击重试'
        ps.loading = false
      } else {
        ps.tsLabel = buildTsLabel(cachedTs, '（刷新失败）')
      }
    }
  } catch (e) {
    // 网络失败
    if (!cachedData) {
      if (isOffline.value) {
        ps.errorMsg = '暂无数据，请检查网络连接后点击刷新'
      } else {
        ps.errorMsg = '获取设备数据失败，请点击重试'
      }
      ps.loading = false
    } else {
      ps.tsLabel = buildTsLabel(cachedTs, '（刷新失败）')
    }
  }
}

// ── IFC-1110-FE-02-2: toggleExpand ──────────────────────────────────────────

async function toggleExpand(specificPart) {
  _initPartState(specificPart)
  const ps = partState[specificPart]
  ps.expanded = !ps.expanded

  if (ps.expanded) {
    // 展开时执行缓存先行 + 后台刷新（ADR-1110-07）
    await loadRealtimeParams(specificPart)
  }
  // 折叠时保留数据（不清空，下次展开立即渲染缓存）
}

// ── IFC-1110-FE-02-5: runRefreshPathA ───────────────────────────────────────

async function runRefreshPathA(specificPart, screenMac, deviceSns) {
  const ps = partState[specificPart]
  const TIMEOUT_MS = 10000  // 10s（INF-01，OQ-D 已采用默认）

  // 注册一次性 DeviceStatusUpdate 监听，等待**本套设备**的更新（FND-008：按 device_sn
  // 过滤，避免并发刷新时收到他套响应而提前 resolve）。deviceSns 为空时不过滤（兜底）。
  const snSet = new Set((deviceSns || []).map(String))
  let resolved = false
  let timer = null
  let off = null

  // outcome：收到的 parsed 对象 = 成功；null = 超时（FND-008 修复原 `timer===null` 永假的死分支）
  const outcome = await new Promise((resolve) => {
    off = mqttClient.onDeviceUpdate((parsed) => {  // IFC-1110-FE-01-7
      if (resolved) return
      if (snSet.size > 0 && !snSet.has(String(parsed && parsed.deviceSn))) return
      resolved = true
      resolve(parsed)
    })

    timer = setTimeout(() => {
      if (!resolved) {
        resolved = true
        resolve(null)  // null = 超时
      }
    }, TIMEOUT_MS)

    // 订阅并发布 DeviceStatusRead
    mqttClient.subscribe(screenMac)  // IFC-1110-FE-01-3（幂等）
    mqttClient.publishRead(screenMac, deviceSns.map(String))  // IFC-1110-FE-01-4
  })

  clearTimeout(timer)
  if (off) off()

  if (outcome === null) {
    // 超时（DEV-01：仅提示，不降级路径B，用户已拍板）
    ps.refreshError = '设备未响应，请确认设备在线'
    return
  }

  // 收到响应，重取快照（确保完整数据）
  await loadRealtimeParams(specificPart, true)
  ps.refreshError = null
}

// ── IFC-1110-FE-02-6: runRefreshPathB ───────────────────────────────────────

async function runRefreshPathB(specificPart) {
  const ps = partState[specificPart]

  try {
    await api.ownerOndemandRefresh(specificPart)
  } catch (e) {
    // ondemand-refresh 失败
    const hasCache = ps.data != null
    if (!hasCache) {
      ps.errorMsg = '暂无数据，请检查网络'
    }
    ps.refreshError = '刷新失败，请检查网络'
    return
  }

  // 等待 5s 后重取快照（US-OWNER-003 AC-1）
  await new Promise(resolve => setTimeout(resolve, 5000))
  await loadRealtimeParams(specificPart, true)
  ps.refreshError = null
}

// ── IFC-1110-FE-02-4: onRefresh ─────────────────────────────────────────────

async function onRefresh(specificPart) {
  const ps = partState[specificPart]
  if (!ps) return

  // 防抖检查（REQ-NFUNC-001）
  if (ps.refreshing || Date.now() < ps.refreshLockUntil) return

  // 网络离线检查
  if (isOffline.value) {
    uni.showToast({ title: '网络不可用，无法刷新', icon: 'none' }); return
  }

  ps.refreshing = true
  ps.refreshLockUntil = Date.now() + 3000  // 最短锁定 3s
  ps.refreshError = null

  try {
    const screenMac = ps.screen_mac
    const deviceSns = ps.device_sns || []

    if (screenMac && deviceSns.length > 0) {
      // 路径 A：MQTT DeviceStatusRead（ADR-1110-02，D-02）
      try {
        // 确保已连接（若参数设置区已连接则直接复用）
        if (!mqttClient.connected.value && broker.value && topics.value) {
          await mqttClient.acquire(broker.value, topics.value)
        }
        await runRefreshPathA(specificPart, screenMac, deviceSns)
      } catch (e) {
        console.error('[param-settings] runRefreshPathA 异常:', e)
        ps.refreshError = '设备未响应，请确认设备在线'
      }
    } else {
      // 路径 B：PLC ondemand-refresh
      await runRefreshPathB(specificPart)
    }
  } finally {
    // 最短锁定保护：等到 refreshLockUntil 才恢复按钮
    const remaining = ps.refreshLockUntil - Date.now()
    if (remaining > 0) await new Promise(r => setTimeout(r, remaining))
    ps.refreshing = false
  }
}

// ── IFC-1110-FE-02-9: goToSettings ──────────────────────────────────────────

function goToSettings(specificPart) {
  // 在参数设置区的 rooms 中找到匹配的 specific_part，切换 roomIndex
  const idx = rooms.value.findIndex(r => r.specific_part === specificPart)
  if (idx >= 0) {
    roomIndex.value = idx
  }
  // 滚动到参数设置区锚点（ADR-1110-05）
  uni.pageScrollTo({ selector: '#param-settings-anchor', duration: 300 })
}

// ── 通用工具 ─────────────────────────────────────────────────────────────────

function goBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}

// 判断参数是否可写（REQ-FUNC-002）
function isWritable(paramName) {
  const wa = config.value.writable_attrs
  return !!(wa && wa[paramName])
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────

onLoad(() => {
  uni.setNavigationBarTitle({ title: '我的房产' })
})

onShow(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }

  // 初始化参数设置区（区域二，复用原有逻辑）
  if (rooms.value.length === 0 && loading.value) loadConfig()

  // 初始化我的房产区（区域一），仅首次或 bindStatus 为空时执行
  if (bindStatus.value.length === 0 && !ownerLoading.value) initOwnerHome()
})

onUnload(() => {
  // 注销 DeviceStatusUpdate 监听，释放 MQTT 引用（ADR-1110-04 引用计数管理）
  if (_offDeviceUpdate) { _offDeviceUpdate(); _offDeviceUpdate = null }
  mqttClient.release()   // IFC-1110-FE-01-2
})
</script>

<style scoped>
/* ── 页面基础 ─────────────────────────────────────────────────────────────── */
.ps-page { display: flex; flex-direction: column; background: #f5f5f5; min-height: 100vh; }

/* ── 区域一：我的房产 ────────────────────────────────────────────────────── */
.owner-home-section { padding: 0 0 16rpx; }
.section-header { background: #fff; padding: 24rpx 24rpx 16rpx; border-bottom: 1rpx solid #f0f0f0; }
.section-title { font-size: 32rpx; font-weight: bold; color: #333; }

.offline-banner {
  background: #fff7e6; padding: 12rpx 24rpx;
  border-left: 4rpx solid #f59e0b;
  margin: 0 0 8rpx;
}
.offline-banner text { font-size: 24rpx; color: #92400e; }

.config-warn-banner {
  background: #fef2f2; padding: 12rpx 24rpx;
  border-left: 4rpx solid #ef4444;
  margin: 0 0 8rpx;
}
.config-warn-banner text { font-size: 24rpx; color: #b91c1c; }

.part-card {
  background: #fff; margin: 16rpx 24rpx; border-radius: 12rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06); overflow: hidden;
}
.part-card-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20rpx 24rpx;
}
.part-name { font-size: 28rpx; font-weight: bold; color: #333; flex: 1; }
.part-header-right { display: flex; align-items: center; gap: 16rpx; }
.expand-arrow { font-size: 20rpx; color: #aaa; }

.refresh-btn {
  padding: 8rpx 20rpx; background: #1a73e8; border-radius: 8rpx;
}
.refresh-btn text { color: #fff; font-size: 24rpx; }
.refresh-btn-busy { opacity: 0.6; }

.part-expand { padding: 0 24rpx 16rpx; border-top: 1rpx solid #f5f5f5; }

.ts-label { font-size: 22rpx; color: #999; display: block; padding: 8rpx 0; }

.refresh-error-msg {
  background: #fef2f2; border-radius: 8rpx; padding: 10rpx 16rpx; margin: 8rpx 0;
}
.refresh-error-msg text { font-size: 24rpx; color: #ef4444; }

.group-block { margin-top: 12rpx; }
.room-block { margin-bottom: 16rpx; }
.room-title { font-size: 26rpx; font-weight: bold; color: #555; display: block; padding: 8rpx 0 4rpx; border-bottom: 1rpx solid #f0f0f0; margin-bottom: 8rpx; }

.param-row { display: flex; align-items: center; justify-content: space-between; padding: 10rpx 0; border-bottom: 1rpx solid #fafafa; }
.param-name { font-size: 26rpx; color: #666; flex: 1; }
.param-right { display: flex; align-items: center; gap: 12rpx; }
.param-value { font-size: 26rpx; color: #333; }
.param-badges { display: flex; align-items: center; gap: 8rpx; }
.badge-writable { font-size: 20rpx; color: #16a34a; background: #f0fdf4; padding: 2rpx 8rpx; border-radius: 4rpx; }
.badge-readonly { font-size: 20rpx; color: #aaa; }
.btn-go-settings { padding: 6rpx 16rpx; background: #1a73e8; border-radius: 6rpx; }
.btn-go-settings text { color: #fff; font-size: 22rpx; }

.tip-loading { text-align: center; padding: 32rpx; color: #aaa; font-size: 26rpx; }
.tip-error { text-align: center; padding: 24rpx; }
.tip-error text { font-size: 26rpx; color: #666; }
.retry-btn { margin-top: 16rpx; display: inline-block; padding: 10rpx 28rpx; background: #1a73e8; border-radius: 8rpx; }
.retry-btn text { color: #fff; font-size: 24rpx; }

/* ── 区域二：参数设置（原有样式，零改动）────────────────────────────────── */
.param-settings-section { display: flex; flex-direction: column; min-height: 60vh; }
.room-bar {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; padding: 20rpx 24rpx; border-bottom: 1rpx solid #f0f0f0;
}
.room-label { font-size: 26rpx; color: #999; margin-right: 16rpx; }
.room-pick, .room-single { font-size: 28rpx; color: #1a73e8; font-weight: bold; }
.conn-dot { font-size: 22rpx; color: #f59e0b; }
.conn-dot.on { color: #16a34a; }
.ps-body { flex: 1; }
.tip { text-align: center; padding: 80rpx 24rpx; color: #999; font-size: 28rpx; }
.link-btn { margin-top: 24rpx; display: inline-block; padding: 12rpx 32rpx; background: #1a73e8; border-radius: 8rpx; }
.link-btn text { color: #fff; font-size: 26rpx; }
.dev-card { background: #fff; margin: 16rpx 24rpx; border-radius: 12rpx; padding: 20rpx 24rpx; box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06); }
.dev-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 12rpx; padding-bottom: 12rpx; border-bottom: 1rpx solid #f0f0f0; }
.dev-role { font-size: 28rpx; font-weight: bold; color: #333; }
.dev-sn { font-size: 22rpx; color: #bbb; }
.attr-row { display: flex; align-items: center; justify-content: space-between; padding: 14rpx 0; }
.attr-label { font-size: 26rpx; color: #666; }
.sel-val { font-size: 26rpx; color: #1a73e8; }
.num-ctl { display: flex; align-items: center; }
.num-btn { width: 56rpx; height: 56rpx; line-height: 52rpx; text-align: center; border: 1rpx solid #ddd; border-radius: 8rpx; font-size: 32rpx; color: #1a73e8; }
.num-val { min-width: 120rpx; text-align: center; font-size: 26rpx; color: #333; font-weight: bold; }
.apply-btn { margin-top: 16rpx; background: #1a73e8; border-radius: 8rpx; padding: 16rpx; text-align: center; }
.apply-btn.busy { opacity: 0.6; }
.apply-btn text { color: #fff; font-size: 26rpx; }
</style>
