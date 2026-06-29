<!--
  @module MOD-1120-FE-02
  @author Claude (v1.12.0 参数设置页重设计)
  @depends MOD-1110-FE-01 (useMqttClient.js), MOD-1120-FE-01 (paramPanels.js),
           MOD-API (api.js: getDeviceSettingsConfig / getOwnerStructure / reportDeviceSettingsAudit)
  @description 业主端·参数设置（v1.12.0）。

    单一页面：按预设类型纵向排列设备/房间面板
      主机（集中供暖）→ 新风 → 主温控 → 各房间 → 其余系统设备
    每个面板两个 tab：
      tab1「设置」 —— OQ-01 精选可写属性的编辑控件，点选即生效（去抖 600ms 自动下发；运行模式用四圆点控件）；
                      写链路（DeviceWrite/写确认/审计）继承 v1.10.0，零语义变更
      tab2「详细」 —— 该设备全部属性（含只读）的当前值，仅展示不可编辑（C-07）

    数据来源：
      骨架  = GET /api/miniapp/owner/structure/（device_sn/product_code/sub_type/params 定义）
              端侧缓存 owner_structure_{sp}，TTL 30 天（OQ-03）；每次进入页面后台静默重拉一次
              （兑现「硬件若变化、重新进入小程序即可更新」），不提供手动刷新按钮。
      值    = MQTT DeviceStatusUpdate，按 device_sn + param_name(=attrTag) 对齐（单一实时来源）。

    相对 v1.11.x 的移除：折叠卡片「我的房产」区域、REST realtime-params 值管线、
      手动刷新/按需采集（onRefresh/runRefreshPathA/B）。写链路与 MQTT composable 保持不变。
-->
<template>
  <view class="ps-page">

    <view v-if="loading" class="tip"><text>加载中…</text></view>

    <view v-else-if="rooms.length === 0" class="tip">
      <text>您还没有绑定专有部分</text>
      <view class="link-btn" @tap="goBind"><text>去绑定</text></view>
    </view>

    <template v-else>
      <!-- 套户选择条（多套户时为选择器，单套户时显示名称 + 连接状态）-->
      <view v-if="rooms.length > 1" class="unit-bar">
        <text class="unit-label">房产</text>
        <picker :range="roomLabels" :value="roomIndex" @change="onRoomChange">
          <view class="unit-pick">{{ currentRoom ? (currentRoom.location_name || currentRoom.specific_part) : '请选择' }} ›</view>
        </picker>
        <text class="conn-dot" :class="{ on: mqttConnected }">{{ mqttConnected ? '已连接' : '连接中…' }}</text>
      </view>
      <view v-else-if="currentRoom" class="unit-bar">
        <text class="unit-single">{{ currentRoom.location_name || currentRoom.specific_part }}</text>
        <text class="conn-dot" :class="{ on: mqttConnected }">{{ mqttConnected ? '已连接' : '连接中…' }}</text>
      </view>

      <!-- 结构骨架加载中（无任何缓存可渲染）-->
      <view v-if="curStructureLoading && !curStructure" class="tip"><text>正在获取设备结构…</text></view>

      <!-- 设备树未同步（sync_status=pending）-->
      <view v-else-if="curSyncPending" class="tip">
        <text>您的房间结构尚未就绪，请等待设备初始化后再试</text>
        <view class="link-btn" @tap="reloadStructure"><text>重试</text></view>
      </view>

      <!-- 结构加载失败且无缓存可降级 -->
      <view v-else-if="curError && !curStructure" class="tip">
        <text>{{ curError }}</text>
        <view class="link-btn" @tap="reloadStructure"><text>重试</text></view>
      </view>

      <!-- 结构就绪但无设备 -->
      <view v-else-if="panels.length === 0" class="tip"><text>当前房产暂无设备信息</text></view>

      <!-- 面板列表（纵向排列）-->
      <template v-else>
        <view v-for="panel in panels" :key="panel.id" class="panel-card">
          <view class="panel-head">
            <text class="panel-title">{{ panel.title }}</text>
            <view class="tab-bar">
              <view
                class="tab"
                :class="{ active: tabOf(panel.id) === 'set' }"
                @tap="setTab(panel.id, 'set')"
              ><text>设置</text></view>
              <view
                class="tab"
                :class="{ active: tabOf(panel.id) === 'detail' }"
                @tap="setTab(panel.id, 'detail')"
              ><text>详细</text></view>
            </view>
          </view>

          <!-- tab1「设置」：可写控件 + 下发 -->
          <view v-if="tabOf(panel.id) === 'set'" class="panel-body">
            <template v-for="dev in panel.devices" :key="dev.deviceSn">
              <view v-if="dev.controls.length > 0" class="dev-block">
                <text v-if="panel.devices.length > 1 && dev.deviceName" class="dev-sub-name">{{ dev.deviceName }}</text>

                <!-- 圆点型（运行模式）：整行独占，四个圆点点选即生效（#5/#6）-->
                <view v-for="w in dev.controls.filter((c) => c.control === 'dots')" :key="w.tag" class="dots-row">
                  <text class="attr-label">{{ w.label }}</text>
                  <view class="dots-ctl">
                    <view
                      v-for="opt in w.options"
                      :key="opt.value"
                      class="dot-item"
                      @tap="onPickDot(dev, w, opt.value)"
                    >
                      <view class="dot" :class="{ on: curVal(dev.deviceSn, w.tag) === opt.value }"></view>
                      <text class="dot-label" :class="{ on: curVal(dev.deviceSn, w.tag) === opt.value }">{{ opt.label }}</text>
                    </view>
                  </view>
                </view>

                <!-- 其余控件（开关/选择/数值）：点选/调整即生效（#5）-->
                <view v-for="w in dev.controls.filter((c) => c.control !== 'dots')" :key="w.tag" class="attr-row">
                  <text class="attr-label">{{ w.label }}</text>

                  <switch
                    v-if="w.control === 'toggle'"
                    :checked="curVal(dev.deviceSn, w.tag) === 'on'"
                    @change="onToggle(dev, w.tag, $event)"
                  />

                  <picker
                    v-else-if="w.control === 'select'"
                    :range="w.optionLabels"
                    :value="selIndex(dev.deviceSn, w)"
                    @change="onSelect(dev, w, $event)"
                  >
                    <view class="sel-val">{{ curLabel(dev.deviceSn, w) }} ›</view>
                  </picker>

                  <view v-else-if="w.control === 'number'" class="num-ctl">
                    <view class="num-btn" @tap="onStep(dev, w, -1)">−</view>
                    <text class="num-val">{{ curVal(dev.deviceSn, w.tag) ?? '—' }}{{ w.unit || '' }}</text>
                    <view class="num-btn" @tap="onStep(dev, w, 1)">＋</view>
                  </view>
                </view>
              </view>
            </template>

            <view v-if="!panelHasControls(panel)" class="no-set-tip">
              <text>此设备无可设置项</text>
            </view>
          </view>

          <!-- tab2「详细」：屏端实推的当前值（屏端自描述，命中白名单才显示），仅展示（C-07）-->
          <view v-else class="panel-body">
            <template v-for="dev in panel.devices" :key="dev.deviceSn">
              <text v-if="panel.devices.length > 1 && dev.deviceName" class="dev-sub-name">{{ dev.deviceName }}</text>

              <view v-if="detailRows(dev.deviceSn).length > 0">
                <view v-for="r in detailRows(dev.deviceSn)" :key="r.tag" class="param-row">
                  <text class="param-name">{{ r.label }}</text>
                  <view class="param-right">
                    <text class="param-value">{{ r.value }}</text>
                    <text :class="r.writable ? 'badge-writable' : 'badge-readonly'">
                      {{ r.writable ? '可设置' : '只读' }}
                    </text>
                  </view>
                </view>
              </view>
              <view v-else class="no-params-placeholder">
                <text>{{ mqttConnected ? '采集中…' : '设备未上报' }}</text>
              </view>
            </template>
          </view>
        </view>
      </template>
    </template>

  </view>
</template>

<script setup>
/**
 * @module MOD-1120-FE-02
 * @depends MOD-1110-FE-01 (useMqttClient), MOD-1120-FE-01 (paramPanels)
 */
import { ref, computed, reactive } from 'vue'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'
import { buildWriteItems } from '@/utils/screenMqtt'
import { useMqttClient } from '@/utils/useMqttClient'
import { buildPanels, panelHasControls, buildDetailRows } from '@/utils/paramPanels'

const authStore = useAuthStore()
const mqttClient = useMqttClient()

// ── 配置 / 套户 / MQTT 实时值 state ──────────────────────────────────────────
const loading = ref(true)
const rooms = ref([])               // config.rooms：[{specific_part, location_name, screen_mac}]
const roomIndex = ref(0)
const broker = ref(null)
const topics = ref(null)
const config = ref({ writable_attrs: {}, readonly_attrs: {}, product_code_role: {}, mode_energy_link: {}, link_product_codes: [] })

const devices = reactive({})        // deviceSn → {productCode, attrs:{tag:val}}（MQTT 实时值）
const edits = reactive({})          // deviceSn → {tag: newVal}（待下发）
const applyingSn = ref('')
const mqttConnected = computed(() => mqttClient.connected.value)

let knownSns = new Set()
let _offDeviceUpdate = null

const currentRoom = computed(() => rooms.value[roomIndex.value] || null)
const roomLabels = computed(() => rooms.value.map((r) => r.location_name || r.specific_part))

// ── 结构骨架 state（按 specific_part）───────────────────────────────────────
const partState = reactive({})      // sp → {structure, structureLoading, errorMsg}

/** 结构缓存 TTL：30 天（OQ-03，硬件结构基本不变）；sync_status=pending 时 5 分钟。 */
const STRUCT_TTL_MS = 30 * 24 * 60 * 60 * 1000
const STRUCT_TTL_PENDING_MS = 5 * 60 * 1000

function _initPartState(sp) {
  if (!partState[sp]) {
    partState[sp] = { structure: null, structureLoading: false, errorMsg: null }
  }
}

// ── 当前套户视图（结构状态 + 面板）────────────────────────────────────────────
const curPart = computed(() => {
  const sp = currentRoom.value?.specific_part
  return sp ? partState[sp] : null
})
const curStructure = computed(() => curPart.value?.structure || null)
const curStructureLoading = computed(() => !!curPart.value?.structureLoading)
const curSyncPending = computed(() => curStructure.value?.sync_status === 'pending')
const curError = computed(() => curPart.value?.errorMsg || '')

const panels = computed(() => buildPanels(curStructure.value, config.value))

// ── tab 状态（panelId → 'set' | 'detail'，默认 'set'）─────────────────────────
const tabState = reactive({})
function tabOf(id) { return tabState[id] || 'set' }
function setTab(id, t) { tabState[id] = t }

// ── tab2「详细」值展示（屏端自描述：直接渲染屏端实推 attrs，过滤非白名单）──────
/** 某设备「详细」tab 行：来自屏端 MQTT 实时 attrs，命中 可写∪只读 白名单才显示。 */
function detailRows(sn) {
  const d = devices[String(sn)]
  if (!d) return []
  return buildDetailRows(d.attrs, config.value.writable_attrs, config.value.readonly_attrs)
}

// ── tab1「设置」控件读写（写链路继承 v1.10.0，零语义变更）────────────────────
function curVal(sn, tag) {
  if (edits[sn] && edits[sn][tag] !== undefined) return edits[sn][tag]
  return devices[sn] ? devices[sn].attrs[tag] : undefined
}
function curLabel(sn, w) {
  const v = curVal(sn, w.tag)
  const opt = w.options.find((o) => o.value === v)
  return opt ? opt.label : (v ?? '—')
}
function selIndex(sn, w) {
  const v = curVal(sn, w.tag)
  const i = w.options.findIndex((o) => o.value === v)
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
  scheduleFlush(dev)
}
function onSelect(dev, w, e) {
  const opt = w.options[e.detail.value]
  if (opt) { setEdit(dev.deviceSn, w.tag, opt.value); scheduleFlush(dev) }
}
function onPickDot(dev, w, value) {
  if (curVal(dev.deviceSn, w.tag) === value) return  // 点当前态不重复下发
  setEdit(dev.deviceSn, w.tag, value)
  scheduleFlush(dev)
}
function onStep(dev, w, dir) {
  const cur = parseFloat(curVal(dev.deviceSn, w.tag))
  let base = isNaN(cur) ? (w.min ?? 0) : cur
  let next = base + dir * (w.step || 1)
  if (w.min !== undefined) next = Math.max(w.min, next)
  if (w.max !== undefined) next = Math.min(w.max, next)
  next = Number.isInteger(w.step) ? String(next) : next.toFixed(1)
  setEdit(dev.deviceSn, w.tag, String(next))
  scheduleFlush(dev)   // 数值连点会被去抖合并（见 scheduleFlush）
}

// 点选即生效（#5）：控件变更后去抖 600ms 自动下发该设备的待发改动（替代「下发更改」按钮）。
// 去抖让数值步进连点合并为一次写，避免刷屏式下发。
const _flushTimers = {}
function scheduleFlush(dev) {
  const sn = dev.deviceSn
  if (_flushTimers[sn]) clearTimeout(_flushTimers[sn])
  _flushTimers[sn] = setTimeout(() => {
    delete _flushTimers[sn]
    applyDevice(dev)
  }, 600)
}

async function applyDevice(dev) {
  const sn = dev.deviceSn
  const room = currentRoom.value
  if (!mqttClient.connected.value || !room) {
    uni.showToast({ title: '通道未连接', icon: 'none' }); return
  }
  if (!hasPending(sn)) return
  if (applyingSn.value) { scheduleFlush(dev); return }  // 有写在途，稍后重排，勿丢改动
  applyingSn.value = sn
  const pending = { ...edits[sn] }
  const auditItems = []
  let okCount = 0, failCount = 0

  for (const tag of Object.keys(pending)) {
    const target = pending[tag]
    const oldVal = devices[sn] ? devices[sn].attrs[tag] : ''
    const items = buildWriteItems(dev.productCode, tag, target, config.value)
    try {
      mqttClient.publishWrite(room.screen_mac, sn, items)
      await mqttClient.waitConfirm(sn, tag, target, 8000)
      okCount++
      items.forEach((it) => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: it.attrTag === tag ? String(oldVal ?? '') : '' }))
      if (edits[sn]) delete edits[sn][tag]
    } catch (e) {
      failCount++
      items.forEach((it) => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: '' }))
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
  if (failCount === 0) uni.showToast({ title: '已生效', icon: 'success' })
  else if (okCount === 0) uni.showToast({ title: '未确认，请重试', icon: 'none' })
  else uni.showToast({ title: `部分成功（${okCount}/${okCount + failCount}）`, icon: 'none' })

  // 在途写期间若又产生新改动，排一次后续 flush 以排空（点选即生效语义）
  if (hasPending(sn)) scheduleFlush(dev)
}

// ── 套户切换 ─────────────────────────────────────────────────────────────────
function onRoomChange(e) {
  selectUnit(Number(e.detail.value))
}

async function selectUnit(idx) {
  roomIndex.value = idx
  const sp = currentRoom.value?.specific_part
  if (!sp) return
  _initPartState(sp)
  await loadStructure(sp)   // 缓存优先即时渲染；缓存未命中时 await 网络
  await connectRoom()       // 用结构 device_sns 主动拉取 MQTT 实时值
}

// ── 配置加载 + MQTT 连接 ─────────────────────────────────────────────────────
async function loadConfig() {
  loading.value = true
  try {
    const res = await api.getDeviceSettingsConfig()
    broker.value = res.broker
    topics.value = res.topics
    config.value = res.config || config.value
    rooms.value = res.rooms || []
    if (rooms.value.length > 0) await selectUnit(0)
  } catch (err) {
    uni.showToast({ title: '加载配置失败，请重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function connectRoom() {
  const room = currentRoom.value
  if (!room || !room.screen_mac) return

  // 切换套户：清空旧设备/编辑状态
  Object.keys(devices).forEach((k) => delete devices[k])
  Object.keys(edits).forEach((k) => delete edits[k])
  knownSns = new Set()
  if (_offDeviceUpdate) { _offDeviceUpdate(); _offDeviceUpdate = null }

  const mac = room.screen_mac
  const sp = room.specific_part

  _offDeviceUpdate = mqttClient.onDeviceUpdate((p) => {
    const prev = devices[p.deviceSn] || { productCode: p.productCode, attrs: {} }
    devices[p.deviceSn] = {
      productCode: p.productCode != null ? p.productCode : prev.productCode,
      attrs: { ...prev.attrs, ...p.attrs },
    }
    const sn = String(p.deviceSn)
    if (!knownSns.has(sn)) { knownSns.add(sn); persistSns(mac) }
  })

  try {
    await mqttClient.acquire(broker.value, topics.value)
    mqttClient.subscribe(mac)
    const allSns = _discoverSns(sp, mac)
    if (allSns.length > 0) {
      allSns.forEach((s) => knownSns.add(s))
      mqttClient.publishRead(mac, allSns)
    }
  } catch (e) {
    uni.showToast({ title: '设备通道连接失败：' + (e && e.message || ''), icon: 'none' })
  }
}

/** 设备 SN 发现：结构骨架 device_sns 优先，回退结构缓存，再回退遗留 SN 缓存。 */
function _discoverSns(sp, mac) {
  const struct = partState[sp]?.structure
  if (struct && Array.isArray(struct.device_sns) && struct.device_sns.length > 0) {
    return struct.device_sns.map(String)
  }
  const { data: cached } = readStructureCache(sp)
  if (cached && Array.isArray(cached.device_sns) && cached.device_sns.length > 0) {
    return cached.device_sns.map(String)
  }
  return loadSns(mac)
}

// 遗留 SN 缓存（按 screenMac，v1.11.0 兼容降级）
const snCacheKey = (mac) => `ds_sns_${mac}`
function loadSns(mac) {
  try { const a = uni.getStorageSync(snCacheKey(mac)); return Array.isArray(a) ? a.map(String) : [] } catch (e) { return [] }
}
function persistSns(mac) {
  try { uni.setStorageSync(snCacheKey(mac), Array.from(knownSns)) } catch (e) { /* ignore */ }
}

// ── 结构骨架缓存（owner_structure_{sp}，TTL 30 天）────────────────────────────
function writeStructureCache(sp, data) {
  try {
    const ttlMs = data && data.sync_status === 'pending' ? STRUCT_TTL_PENDING_MS : STRUCT_TTL_MS
    uni.setStorageSync(`owner_structure_${sp}`, JSON.stringify(data))
    uni.setStorageSync(`owner_structure_${sp}_ts`, new Date().toISOString())
    uni.setStorageSync(`owner_structure_${sp}_ttl`, ttlMs)
  } catch (e) {
    console.warn('[param-settings] writeStructureCache 失败:', e)
  }
}

function readStructureCache(sp) {
  try {
    const raw = uni.getStorageSync(`owner_structure_${sp}`)
    const tsRaw = uni.getStorageSync(`owner_structure_${sp}_ts`)
    const ttlMs = uni.getStorageSync(`owner_structure_${sp}_ttl`) || STRUCT_TTL_MS
    const data = raw ? JSON.parse(raw) : null
    const ts = tsRaw ? new Date(tsRaw) : null
    const expired = ts ? (Date.now() - ts.getTime() > ttlMs) : true
    return { data: expired ? null : data, rawData: data }
  } catch (e) {
    return { data: null, rawData: null }
  }
}

/**
 * 加载结构骨架：
 *   - 缓存有效 → 立即渲染（秒开），并后台静默重拉一次（兑现「重新进入即更新」，OQ-02/OQ-03）。
 *   - 缓存过期但有旧数据 → 先用旧数据渲染，再 await 网络。
 *   - 无任何缓存 → 显示加载态，await 网络（首次进入预取，OQ-02）。
 */
async function loadStructure(sp, forceRefresh = false) {
  const ps = partState[sp]
  if (!ps) return
  const { data: cached, rawData } = readStructureCache(sp)

  if (!forceRefresh && cached) {
    ps.structure = cached
    ps.structureLoading = false
    ps.errorMsg = null
    _refreshStructureNetwork(sp)   // 后台静默刷新，不阻塞渲染
    return
  }
  if (rawData) {
    ps.structure = rawData          // 过期旧数据先撑住骨架
    ps.structureLoading = false
  } else {
    ps.structure = null
    ps.structureLoading = true
  }
  await _refreshStructureNetwork(sp)
}

/** 网络重拉结构（指数退避重试 3 次）；成功后更新缓存，并补拉新发现设备的 MQTT 值。 */
async function _refreshStructureNetwork(sp) {
  const ps = partState[sp]
  if (!ps) return
  const BACKOFF_MS = [0, 500, 1500]
  for (let attempt = 0; attempt < BACKOFF_MS.length; attempt++) {
    if (BACKOFF_MS[attempt] > 0) await new Promise((r) => setTimeout(r, BACKOFF_MS[attempt]))
    try {
      const res = await api.getOwnerStructure(sp)
      if (res && res.success !== false) {
        ps.structure = res
        ps.errorMsg = null
        writeStructureCache(sp, res)
        _readNewlyDiscovered(sp, res)
      } else {
        ps.errorMsg = (res && res.error) || '获取设备结构失败，请点击重试'
        // 保留已有 structure（若有），不清空
      }
      ps.structureLoading = false
      return
    } catch (e) {
      if (attempt < BACKOFF_MS.length - 1) continue
      // 重试耗尽：降级用过期缓存
      const { rawData } = readStructureCache(sp)
      if (rawData && !ps.structure) ps.structure = rawData
      if (!ps.structure) ps.errorMsg = '获取设备结构失败，请点击重试'
      ps.structureLoading = false
    }
  }
}

/** 后台刷新发现新 device_sn 且 MQTT 已连接当前套户时，补发 DeviceStatusRead。 */
function _readNewlyDiscovered(sp, structure) {
  const room = currentRoom.value
  if (!room || room.specific_part !== sp) return
  if (!mqttClient.connected.value || !Array.isArray(structure.device_sns)) return
  const fresh = structure.device_sns.map(String).filter((s) => !knownSns.has(s))
  if (fresh.length > 0) {
    fresh.forEach((s) => knownSns.add(s))
    mqttClient.publishRead(room.screen_mac, fresh)
  }
}

/** 错误/pending 态的重试入口（强制网络重拉，非「手动刷新有效数据」入口）。 */
function reloadStructure() {
  const sp = currentRoom.value?.specific_part
  if (sp) loadStructure(sp, true)
}

// ── 通用 ─────────────────────────────────────────────────────────────────────
function goBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
onLoad(() => {
  uni.setNavigationBarTitle({ title: '参数设置' })
})

onShow(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  if (rooms.value.length === 0 && loading.value) loadConfig()
})

onUnload(() => {
  Object.values(_flushTimers).forEach((t) => clearTimeout(t))
  if (_offDeviceUpdate) { _offDeviceUpdate(); _offDeviceUpdate = null }
  mqttClient.release()
})
</script>

<style scoped>
.ps-page { display: flex; flex-direction: column; background: #f5f5f5; min-height: 100vh; padding-bottom: 24rpx; }

/* 套户选择条 */
.unit-bar {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; padding: 20rpx 24rpx; border-bottom: 1rpx solid #f0f0f0;
}
.unit-label { font-size: 26rpx; color: #999; margin-right: 16rpx; }
.unit-pick, .unit-single { font-size: 28rpx; color: #1a73e8; font-weight: bold; flex: 1; }
.conn-dot { font-size: 22rpx; color: #f59e0b; }
.conn-dot.on { color: #16a34a; }

/* 提示 / 空态 */
.tip { text-align: center; padding: 80rpx 24rpx; color: #999; font-size: 28rpx; }
.link-btn { margin-top: 24rpx; display: inline-block; padding: 12rpx 32rpx; background: #1a73e8; border-radius: 8rpx; }
.link-btn text { color: #fff; font-size: 26rpx; }

/* 面板卡片 */
.panel-card {
  background: #fff; margin: 16rpx 24rpx; border-radius: 12rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06); overflow: hidden;
}
.panel-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20rpx 24rpx; border-bottom: 1rpx solid #f0f0f0;
}
.panel-title { font-size: 30rpx; font-weight: bold; color: #333; }

/* tab 切换 */
.tab-bar { display: flex; border: 1rpx solid #e5e7eb; border-radius: 8rpx; overflow: hidden; }
.tab { padding: 8rpx 28rpx; background: #f7f8fa; }
.tab text { font-size: 24rpx; color: #666; }
.tab.active { background: #1a73e8; }
.tab.active text { color: #fff; }

.panel-body { padding: 8rpx 24rpx 16rpx; }
.dev-block { padding: 8rpx 0; }
.dev-sub-name { font-size: 24rpx; color: #888; display: block; padding: 8rpx 0 4rpx; font-style: italic; }

/* tab1 控件行 */
.attr-row { display: flex; align-items: center; justify-content: space-between; padding: 14rpx 0; border-bottom: 1rpx solid #fafafa; }
.attr-label { font-size: 26rpx; color: #666; }
.sel-val { font-size: 26rpx; color: #1a73e8; }
.num-ctl { display: flex; align-items: center; }
.num-btn { width: 56rpx; height: 56rpx; line-height: 52rpx; text-align: center; border: 1rpx solid #ddd; border-radius: 8rpx; font-size: 32rpx; color: #1a73e8; }
.num-val { min-width: 120rpx; text-align: center; font-size: 26rpx; color: #333; font-weight: bold; }

/* 圆点型运行模式控件（#6）：整行，label 一行 + 四个圆点一行，点选即生效 */
.dots-row { padding: 14rpx 0; border-bottom: 1rpx solid #fafafa; }
.dots-ctl { display: flex; justify-content: space-between; margin-top: 16rpx; }
.dot-item { display: flex; flex-direction: column; align-items: center; flex: 1; }
.dot { width: 40rpx; height: 40rpx; border-radius: 50%; background: #dfe3e8; border: 2rpx solid #cbd2d9; }
.dot.on { background: #1a73e8; border-color: #1a73e8; box-shadow: 0 0 0 6rpx rgba(26,115,232,0.15); }
.dot-label { font-size: 22rpx; color: #999; margin-top: 8rpx; }
.dot-label.on { color: #1a73e8; font-weight: bold; }

.no-set-tip { text-align: center; padding: 32rpx 0; }
.no-set-tip text { font-size: 24rpx; color: #bbb; }

/* tab2 详细行 */
.param-row { display: flex; align-items: center; justify-content: space-between; padding: 12rpx 0; border-bottom: 1rpx solid #fafafa; }
.param-name { font-size: 26rpx; color: #666; flex: 1; }
.param-right { display: flex; align-items: center; gap: 12rpx; }
.param-value { font-size: 26rpx; color: #333; }
.badge-writable { font-size: 20rpx; color: #16a34a; background: #f0fdf4; padding: 2rpx 8rpx; border-radius: 4rpx; }
.badge-readonly { font-size: 20rpx; color: #aaa; }
.no-params-placeholder { padding: 16rpx 0; }
.no-params-placeholder text { font-size: 24rpx; color: #bbb; }
</style>
