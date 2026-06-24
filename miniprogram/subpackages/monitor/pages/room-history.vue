<!--
  @module MOD-PAGE-ROOM-HISTORY
  @description 房间历史趋势图（US-06）。对齐 Web RoomHistoryView：
    GET /api/devices/param-history/ {specific_part,param_names,start_time,end_time,chart:'true'}
      → {success, results:[{param_name, collected_at, value}]}
  房间 tab 与参数名取自 Web ROOM_TABS（温度/湿度，scale 0.1 还原真实量级）。默认近 7 天。
  简化：每房间聚焦温度+湿度两条趋势（Web 另含开关/凝露提醒等，移动端首期从简）。
-->
<template>
  <view class="rh-page">
    <!-- 房间 tab -->
    <scroll-view scroll-x class="tab-bar">
      <view
        v-for="room in rooms"
        :key="room.key"
        class="tab-item"
        :class="{ active: activeKey === room.key }"
        @tap="switchRoom(room.key)"
      ><text>{{ room.label }}</text></view>
    </scroll-view>

    <scroll-view scroll-y class="rh-body">
      <view v-if="loading" class="tip"><text>加载中…</text></view>
      <view v-else-if="!hasAnyData" class="tip"><text>该时间段暂无历史数据</text></view>

      <view v-else v-for="p in currentParams" :key="p.param" class="chart-card">
        <view class="chart-head">
          <text class="chart-title">{{ p.label }}</text>
          <text class="chart-unit">{{ p.unit }}</text>
        </view>
        <LineChart
          :canvas-id="'rh_' + p.param"
          :categories="series[p.param] ? series[p.param].categories : []"
          :data="series[p.param] ? series[p.param].values : []"
          :name="p.label"
          :unit="p.unit"
          :height="220"
        />
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'
import LineChart from '@/components/LineChart.vue'

const authStore = useAuthStore()

// 取自 Web RoomHistoryView 的 ROOM_TABS（聚焦温度/湿度，scale 0.1）
const rooms = [
  { key: 'study_room', label: '书房', params: [
    { label: '温度', param: 'study_room_temperature', unit: '°C', scale: 0.1 },
    { label: '湿度', param: 'study_room_humidity', unit: '%', scale: 0.1 },
  ]},
  { key: 'bedroom', label: '次卧', params: [
    { label: '温度', param: 'bedroom_temperature', unit: '°C', scale: 0.1 },
    { label: '湿度', param: 'bedroom_humidity', unit: '%', scale: 0.1 },
  ]},
  { key: 'children_room', label: '主卧', params: [
    { label: '温度', param: 'children_room_temperature', unit: '°C', scale: 0.1 },
    { label: '湿度', param: 'children_room_humidity', unit: '%', scale: 0.1 },
  ]},
  { key: 'fourth_children_room', label: '儿童房', params: [
    { label: '温度', param: 'fourth_children_room_temperature', unit: '°C', scale: 0.1 },
    { label: '湿度', param: 'fourth_children_room_humidity', unit: '%', scale: 0.1 },
  ]},
]

const specificPart = ref('')
const activeKey = ref(rooms[0].key)
const series = ref({})
const loading = ref(false)
const RANGE_DAYS = 7

const currentRoom = computed(() => rooms.find(r => r.key === activeKey.value) || rooms[0])
const currentParams = computed(() => currentRoom.value.params)
const hasAnyData = computed(() =>
  Object.values(series.value).some(s => s.values && s.values.length > 0)
)

function dateStr(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
function shortTime(s) {
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function load() {
  if (!specificPart.value) return
  loading.value = true
  try {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - (RANGE_DAYS - 1))
    const ps = currentParams.value
    const res = await api.getParamHistory({
      specific_part: specificPart.value,
      param_names: ps.map(p => p.param).join(','),
      start_time: `${dateStr(start)} 00:00:00`,
      end_time: `${dateStr(end)} 23:59:59`,
      chart: 'true',
    })
    const scaleMap = {}
    const grouped = {}
    for (const p of ps) { grouped[p.param] = { categories: [], values: [] }; scaleMap[p.param] = p.scale || 1 }
    if (res && res.success && Array.isArray(res.results)) {
      for (const row of res.results) {
        const g = grouped[row.param_name]
        if (!g) continue
        g.categories.push(shortTime(row.collected_at))
        const num = Number(row.value)
        g.values.push(isNaN(num) ? 0 : +(num * scaleMap[row.param_name]).toFixed(1))
      }
    }
    series.value = grouped
  } catch (e) {
    uni.showToast({ title: '获取历史数据失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function switchRoom(key) {
  if (activeKey.value === key) return
  activeKey.value = key
  series.value = {}
  load()
}

onLoad((options) => {
  specificPart.value = options.specific_part || ''
  uni.setNavigationBarTitle({ title: '房间历史' })
})

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  load()
})
</script>

<style scoped>
.rh-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.tab-bar {
  white-space: nowrap;
  background: #fff;
  border-bottom: 1rpx solid #f0f0f0;
  flex-shrink: 0;
}
.tab-item {
  display: inline-block;
  padding: 20rpx 36rpx;
}
.tab-item text {
  font-size: 26rpx;
  color: #666;
}
.tab-item.active {
  border-bottom: 4rpx solid #1a73e8;
}
.tab-item.active text {
  color: #1a73e8;
  font-weight: bold;
}
.rh-body {
  flex: 1;
}
.tip {
  text-align: center;
  padding: 80rpx 24rpx;
  color: #999;
  font-size: 28rpx;
}
.chart-card {
  background: #fff;
  margin: 16rpx 24rpx;
  border-radius: 12rpx;
  padding: 16rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06);
}
.chart-head {
  display: flex;
  align-items: baseline;
  padding: 4rpx 8rpx 12rpx;
}
.chart-title {
  font-size: 28rpx;
  font-weight: bold;
  color: #333;
  margin-right: 12rpx;
}
.chart-unit {
  font-size: 22rpx;
  color: #999;
}
</style>
