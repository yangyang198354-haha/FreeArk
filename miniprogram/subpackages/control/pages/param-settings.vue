<!--
  @module MOD-PAGE-PARAM-SETTINGS
  @description 业主端·设备参数设置（v1.10.0）。直连厂端 MQTT broker：
    - GET /api/miniapp/device-settings/config/ 取 broker/绑定房间(含 screenMac)/可写白名单+标签
    - 订阅 /screen/upload/screen/to/cloud/{screenMac} 的 DeviceStatusUpdate 渲染设备与当前值（屏端自描述）
    - 编辑后发 DeviceWrite 到 /screen/service/cloud/to/screen/{screenMac}
    - 写确认靠下一条值推送反映目标值（无独立 ack，ADR-04）；成功后尽力上报审计
  仅业主(role=user)可用；越权由后端 config/audit 兜（只下发自己房间）。
-->
<template>
  <view class="ps-page">
    <!-- 房间选择（多房间时） -->
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
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'
import { ScreenMqtt, buildWriteItems } from '@/utils/screenMqtt'

const authStore = useAuthStore()

const loading = ref(true)
const rooms = ref([])
const roomIndex = ref(0)
const broker = ref(null)
const topics = ref(null)
const config = ref({ writable_attrs: {}, product_code_role: {}, mode_energy_link: {}, link_product_codes: [] })

const devices = reactive({})        // deviceSn -> {productCode, attrs:{tag:val}}
const edits = reactive({})          // deviceSn -> {tag: newVal}
const mqttConnected = ref(false)
const applyingSn = ref('')

let mqtt = null

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
  // 保留一位小数（温度），整数则不带小数
  next = Number.isInteger(w.step) ? String(next) : next.toFixed(1)
  setEdit(dev.deviceSn, w.tag, String(next))
}

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
  // 清空旧连接与设备
  if (mqtt) { mqtt.disconnect(); mqtt = null }
  Object.keys(devices).forEach(k => delete devices[k])
  Object.keys(edits).forEach(k => delete edits[k])
  mqttConnected.value = false

  mqtt = new ScreenMqtt(broker.value, topics.value)
  mqtt.onDeviceUpdate((p) => {
    const prev = devices[p.deviceSn] || { productCode: p.productCode, attrs: {} }
    devices[p.deviceSn] = {
      productCode: p.productCode != null ? p.productCode : prev.productCode,
      attrs: { ...prev.attrs, ...p.attrs },
    }
  })
  try {
    await mqtt.connect()
    mqttConnected.value = true
    mqtt.subscribeRoom(room.screen_mac)
  } catch (e) {
    uni.showToast({ title: '设备通道连接失败', icon: 'none' })
  }
}

async function applyDevice(dev) {
  const sn = dev.deviceSn
  const room = currentRoom.value
  if (!mqtt || !mqttConnected.value || !room) {
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
      mqtt.writeAttrs(room.screen_mac, sn, items)
      await mqtt.waitConfirm(sn, tag, target, 8000)
      okCount++
      items.forEach(it => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: it.attrTag === tag ? String(oldVal ?? '') : '' }))
      if (edits[sn]) delete edits[sn][tag]
    } catch (e) {
      failCount++
      items.forEach(it => auditItems.push({ attr_tag: it.attrTag, attr_value: it.attrValue, old_value: '' }))
    }
  }

  // 尽力上报审计（失败静默，不阻断）
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
function goBind() {
  uni.navigateTo({ url: '/pages/bind/index' })
}

onLoad(() => {
  uni.setNavigationBarTitle({ title: '参数设置' })
})
onShow(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  if (rooms.value.length === 0 && loading.value) loadConfig()
})
onUnload(() => {
  if (mqtt) { mqtt.disconnect(); mqtt = null }
})
</script>

<style scoped>
.ps-page { display: flex; flex-direction: column; height: 100vh; background: #f5f5f5; }
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
