<!--
  @module MOD-1120-FE-02
  @author Claude (v1.13.0 参数设置页·米家风设备卡片流改版)
  @depends MOD-1110-FE-01 (useMqttClient.js), MOD-1120-FE-01 (paramPanels.js),
           MOD-API (api.js: getDeviceSettingsConfig / getOwnerStructure / reportDeviceSettingsAudit)
  @description 业主端·参数设置（v1.13.0 卡片流）。

    每个设备/房间 = 一张「米家风」设备卡，状态 + 控制同屏（取消 v1.12 的设置/详细双 tab）：
      头部   图标 + 名称 + 主开关
      指标   大字关键指标（温度）+ 小字指标 + 网格指标（空气品质）—— 屏端只读读数
      控件   点选即生效的可写控件（模式圆点 / 风速分段 / 加湿开关 / 设定温度步进）
      展开   「查看全部 N 项」内联展开该设备其余只读读数（不跳页）

    数据来源（单一来源 = 屏端 MQTT，后端不连 broker）：
      骨架  = GET /api/miniapp/owner/structure/（device_sn/product_code/params 定义）
              端侧缓存 owner_structure_{sp}，TTL 30 天（OQ-03）；每次进入后台静默重拉一次。
      值    = MQTT DeviceStatusUpdate，按 device_sn + attrTag 对齐（屏端自描述）。
              卡片版面 = paramPanels.buildCard()，命中「可写∪只读」白名单才展示
              （error_*/comm_fault/plc_* 等被过滤）。

    写链路（DeviceWrite/写确认/审计/点选即生效去抖）继承 v1.10.0，零语义变更。
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
      <view v-else-if="cards.length === 0" class="tip"><text>当前房产暂无设备信息</text></view>

      <!-- 设备卡片流（米家风，纵向排列）-->
      <template v-else>
        <view v-for="card in cards" :key="card.id" class="dev-card">

          <!-- 头部：图标 + 名称 + 主开关 -->
          <view class="card-head">
            <text class="card-icon">{{ card.icon }}</text>
            <text class="card-title">{{ card.title }}</text>
            <switch
              v-if="card.switchCtl"
              class="card-switch"
              :checked="curVal(card.switchCtl.sn, card.switchCtl.w.tag) === 'on'"
              @change="onToggle(ctlDev(card.switchCtl), card.switchCtl.w.tag, $event)"
            />
          </view>

          <!-- 大字关键指标（温度等）-->
          <view v-if="card.big.length" class="big-row">
            <view v-for="m in card.big" :key="m.tag" class="big-item">
              <text class="big-val">{{ m.value }}</text>
              <text class="big-lbl">{{ m.label }}</text>
            </view>
          </view>

          <!-- 小字指标（行内）-->
          <view v-if="card.small.length" class="small-row">
            <text v-for="m in card.small" :key="m.tag" class="small-item">{{ m.label }} {{ m.value }}</text>
          </view>

          <!-- 网格指标（空气品质）-->
          <view v-if="card.grid.length" class="grid-row">
            <view v-for="m in card.grid" :key="m.tag" class="grid-cell">
              <text class="cell-val">{{ m.value }}</text>
              <text class="cell-lbl">{{ m.label }}</text>
            </view>
          </view>

          <!-- 可写控件（点选即生效）-->
          <view v-if="card.controls.length" class="ctl-area">
            <view v-for="c in card.controls" :key="c.sn + '-' + c.w.tag">

              <!-- 圆点（运行模式）-->
              <view v-if="c.w.control === 'dots'" class="ctl-dots">
                <text class="ctl-label">{{ c.w.label }}</text>
                <view class="dots-ctl">
                  <view v-for="opt in c.w.options" :key="opt.value" class="dot-item" @tap="onPickDot(ctlDev(c), c.w, opt.value)">
                    <view class="dot" :class="{ on: curVal(c.sn, c.w.tag) === opt.value }"></view>
                    <text class="dot-label" :class="{ on: curVal(c.sn, c.w.tag) === opt.value }">{{ opt.label }}</text>
                  </view>
                </view>
              </view>

              <!-- 分段 chips（如风速 select）-->
              <view v-else-if="c.w.control === 'select'" class="ctl-row">
                <text class="ctl-label">{{ c.w.label }}</text>
                <view class="seg">
                  <view
                    v-for="opt in c.w.options"
                    :key="opt.value"
                    class="seg-item"
                    :class="{ on: curVal(c.sn, c.w.tag) === opt.value }"
                    @tap="onPickDot(ctlDev(c), c.w, opt.value)"
                  ><text>{{ opt.label }}</text></view>
                </view>
              </view>

              <!-- 开关 -->
              <view v-else-if="c.w.control === 'toggle'" class="ctl-row">
                <text class="ctl-label">{{ c.w.label }}</text>
                <switch :checked="curVal(c.sn, c.w.tag) === 'on'" @change="onToggle(ctlDev(c), c.w.tag, $event)" />
              </view>

              <!-- 数值步进 -->
              <view v-else-if="c.w.control === 'number'" class="ctl-row">
                <text class="ctl-label">{{ c.w.label }}</text>
                <view class="num-ctl">
                  <view class="num-btn" @tap="onStep(ctlDev(c), c.w, -1)">−</view>
                  <text class="num-val">{{ curVal(c.sn, c.w.tag) ?? '—' }}{{ c.w.unit || '' }}</text>
                  <view class="num-btn" @tap="onStep(ctlDev(c), c.w, 1)">＋</view>
                </view>
              </view>

            </view>
          </view>

          <!-- 查看全部（其余只读读数，展开/收起，不跳页）-->
          <view v-if="card.rest.length" class="more-row" @tap="toggleExpand(card.id)">
            <text class="more-txt">{{ expanded[card.id] ? '收起' : '查看全部 ' + card.rest.length + ' 项' }}</text>
            <text class="more-arrow">{{ expanded[card.id] ? '▲' : '›' }}</text>
          </view>
          <view v-if="expanded[card.id]" class="rest-list">
            <view v-for="r in card.rest" :key="r.tag" class="rest-row">
              <text class="rest-name">{{ r.label }}</text>
              <text class="rest-val">{{ r.value }}</text>
            </view>
          </view>

          <!-- 空卡占位（无开关/控件/指标/读数，连接中先撑住）-->
          <view
            v-if="!card.switchCtl && !card.controls.length && !card.big.length && !card.small.length && !card.grid.length && !card.rest.length"
            class="empty-tip"
          >
            <text>{{ mqttConnected ? '采集中…' : '设备未上报' }}</text>
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
import { buildPanels, buildCard } from '@/utils/paramPanels'

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

// ── 当前套户视图（结构状态 + 卡片）────────────────────────────────────────────
const curPart = computed(() => {
  const sp = currentRoom.value?.specific_part
  return sp ? partState[sp] : null
})
const curStructure = computed(() => curPart.value?.structure || null)
const curStructureLoading = computed(() => !!curPart.value?.structureLoading)
const curSyncPending = computed(() => curStructure.value?.sync_status === 'pending')
const curError = computed(() => curPart.value?.errorMsg || '')

const panels = computed(() => buildPanels(curStructure.value, config.value))

// 屏端实时值（sn → attrs）快照，供 buildCard 读取突出指标 / 查看全部；devices 变更即重算。
const attrsBySn = computed(() => {
  const m = {}
  for (const sn of Object.keys(devices)) m[sn] = devices[sn].attrs
  return m
})
// 面板 → 米家风卡片视图模型（结构 + 实时值合成）。
const cards = computed(() => panels.value.map((p) => buildCard(p, attrsBySn.value, config.value)))

// ── 「查看全部」展开态（cardId → bool）─────────────────────────────────────────
const expanded = reactive({})
function toggleExpand(id) { expanded[id] = !expanded[id] }

// 控件 slot（{sn,productCode,w}）→ 写链路所需的轻量 dev 对象（deviceSn/productCode）。
function ctlDev(c) { return { deviceSn: c.sn, productCode: c.productCode } }

// ── 控件读写（写链路继承 v1.10.0，零语义变更）────────────────────────────────
function curVal(sn, tag) {
  if (edits[sn] && edits[sn][tag] !== undefined) return edits[sn][tag]
  return devices[sn] ? devices[sn].attrs[tag] : undefined
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
function onPickDot(dev, w, value) {
  if (curVal(dev.deviceSn, w.tag) === value) return  // 点当前态不重复下发（圆点 / 分段 chips 共用）
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

// 点选即生效：控件变更后去抖 600ms 自动下发该设备的待发改动（替代「下发更改」按钮）。
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
.ps-page { display: flex; flex-direction: column; background: #f2f3f5; min-height: 100vh; padding-bottom: 32rpx; }

/* 套户选择条 */
.unit-bar { display: flex; align-items: center; justify-content: space-between; padding: 22rpx 30rpx 8rpx; }
.unit-label { font-size: 24rpx; color: #9aa0a6; margin-right: 12rpx; }
.unit-pick, .unit-single { font-size: 30rpx; color: #1f2937; font-weight: 600; flex: 1; }
.conn-dot { font-size: 22rpx; color: #f59e0b; }
.conn-dot.on { color: #16a34a; }

/* 提示 / 空态 */
.tip { text-align: center; padding: 80rpx 24rpx; color: #9aa0a6; font-size: 28rpx; }
.link-btn { margin-top: 24rpx; display: inline-block; padding: 14rpx 36rpx; background: #3b82f6; border-radius: 999rpx; }
.link-btn text { color: #fff; font-size: 26rpx; }

/* 设备卡 */
.dev-card {
  background: #fff; margin: 18rpx 24rpx; border-radius: 24rpx;
  padding: 26rpx 28rpx 14rpx; box-shadow: 0 6rpx 20rpx rgba(17, 24, 39, 0.05);
}
.card-head { display: flex; align-items: center; }
.card-icon {
  width: 64rpx; height: 64rpx; line-height: 64rpx; text-align: center;
  font-size: 34rpx; background: #eef2ff; border-radius: 18rpx; margin-right: 18rpx;
}
.card-title { font-size: 32rpx; font-weight: 700; color: #1f2937; flex: 1; }
.card-switch { transform: scale(0.9); }

/* 大字关键指标 */
.big-row { display: flex; gap: 48rpx; margin: 20rpx 0 6rpx; }
.big-item { display: flex; flex-direction: column; }
.big-val { font-size: 64rpx; font-weight: 700; color: #ea6a3a; line-height: 1.1; }
.big-lbl { font-size: 22rpx; color: #9aa0a6; margin-top: 4rpx; }

/* 小字指标 */
.small-row { display: flex; flex-wrap: wrap; gap: 24rpx; margin: 8rpx 0 4rpx; }
.small-item { font-size: 24rpx; color: #6b7280; }

/* 网格指标（空气品质）*/
.grid-row { display: flex; flex-wrap: wrap; margin: 14rpx 0 4rpx; }
.grid-cell { width: 25%; display: flex; flex-direction: column; align-items: center; padding: 12rpx 0; }
.cell-val { font-size: 34rpx; font-weight: 700; color: #1f2937; }
.cell-lbl { font-size: 20rpx; color: #9aa0a6; margin-top: 4rpx; }

/* 控件区 */
.ctl-area { margin-top: 8rpx; }
.ctl-row { display: flex; align-items: center; justify-content: space-between; padding: 16rpx 0; border-top: 1rpx solid #f3f4f6; }
.ctl-label { font-size: 26rpx; color: #374151; }

/* 分段 chips（风速等少选项 select）*/
.seg { display: flex; background: #f3f4f6; border-radius: 999rpx; padding: 4rpx; }
.seg-item { padding: 8rpx 28rpx; border-radius: 999rpx; }
.seg-item text { font-size: 24rpx; color: #6b7280; }
.seg-item.on { background: #3b82f6; }
.seg-item.on text { color: #fff; font-weight: 600; }

/* 数值步进 */
.num-ctl { display: flex; align-items: center; }
.num-btn { width: 60rpx; height: 60rpx; line-height: 56rpx; text-align: center; border: 1rpx solid #e5e7eb; border-radius: 14rpx; font-size: 34rpx; color: #3b82f6; }
.num-val { min-width: 130rpx; text-align: center; font-size: 30rpx; color: #1f2937; font-weight: 700; }

/* 圆点（运行模式）*/
.ctl-dots { padding: 16rpx 0; border-top: 1rpx solid #f3f4f6; }
.dots-ctl { display: flex; justify-content: space-between; margin-top: 18rpx; }
.dot-item { display: flex; flex-direction: column; align-items: center; flex: 1; }
.dot { width: 44rpx; height: 44rpx; border-radius: 50%; background: #e5e7eb; }
.dot.on { background: #3b82f6; box-shadow: 0 0 0 8rpx rgba(59, 130, 246, 0.15); }
.dot-label { font-size: 22rpx; color: #9aa0a6; margin-top: 10rpx; }
.dot-label.on { color: #3b82f6; font-weight: 600; }

/* 查看全部 + 展开列表 */
.more-row { display: flex; align-items: center; justify-content: center; gap: 8rpx; padding: 18rpx 0 8rpx; }
.more-txt, .more-arrow { font-size: 24rpx; color: #9aa0a6; }
.rest-list { padding: 2rpx 0 8rpx; }
.rest-row { display: flex; align-items: center; justify-content: space-between; padding: 12rpx 0; border-top: 1rpx solid #f7f8fa; }
.rest-name { font-size: 24rpx; color: #6b7280; }
.rest-val { font-size: 24rpx; color: #374151; }

/* 空卡占位 */
.empty-tip { text-align: center; padding: 28rpx 0; }
.empty-tip text { font-size: 24rpx; color: #c0c4cc; }
</style>
