<!--
  @module MOD-PAGE-ENERGY-REPORT
  @description 能耗报表（US-09/US-10）。一页参数化 type：
    daily   → GET /api/usage/quantity/            {…,start_time,end_time}（能耗日报）
    period  → GET /api/usage/quantity/specifictimeperiod 同参（用量查询）
    monthly → GET /api/usage/quantity/monthly/    {…,start_month,end_month}（能耗月报）
  公共响应：{success, data:[{specific_part,building,unit,room_number,energy_mode,
                            initial_energy,final_energy,usage_quantity,time_period}], total}
  对齐 Web：筛选(楼栋-单元 / 供能模式 / 时间段) + 用量趋势图 + 明细表。
  移动端简化：specific_part 仅做 楼栋[-单元]（Web 还支持到户号，floor 推导后补）；
    趋势图为"各时段总用量"单线（制冷/制热拆分见明细；Web 图按模式分系列）。
-->
<template>
  <view class="er-page">
    <!-- 筛选 -->
    <view class="filter-card">
      <view class="filter-row">
        <picker class="f-item" mode="selector" :range="buildingOptions" :value="buildingIdx" @change="e => buildingIdx = Number(e.detail.value)">
          <text class="f-text">楼栋: {{ buildingOptions[buildingIdx] }}</text>
        </picker>
        <picker class="f-item" mode="selector" :range="unitOptions" :value="unitIdx" @change="e => unitIdx = Number(e.detail.value)">
          <text class="f-text">单元: {{ unitOptions[unitIdx] }}</text>
        </picker>
        <picker class="f-item" mode="selector" :range="modeOptions" :value="modeIdx" @change="e => modeIdx = Number(e.detail.value)">
          <text class="f-text">模式: {{ modeOptions[modeIdx] }}</text>
        </picker>
      </view>
      <view class="filter-row">
        <picker class="f-date" :mode="'date'" :fields="useMonth ? 'month' : 'day'" :value="startVal" @change="e => startVal = e.detail.value">
          <text class="f-text">起: {{ startVal }}</text>
        </picker>
        <text class="f-sep">至</text>
        <picker class="f-date" :mode="'date'" :fields="useMonth ? 'month' : 'day'" :value="endVal" @change="e => endVal = e.detail.value">
          <text class="f-text">止: {{ endVal }}</text>
        </picker>
        <view class="f-btn" @tap="query"><text>查询</text></view>
      </view>
    </view>

    <scroll-view scroll-y class="er-body" @scrolltolower="loadMore">
      <!-- 汇总 -->
      <view v-if="list.length > 0" class="summary">
        <text class="sum-num">{{ totalUsage }}</text>
        <text class="sum-label">kWh · 共 {{ total }} 条</text>
      </view>

      <!-- 趋势图 -->
      <view v-if="list.length > 0" class="chart-card">
        <view class="chart-head"><text class="chart-title">用量趋势</text></view>
        <LineChart
          canvas-id="energyChart"
          :categories="chartCategories"
          :data="chartValues"
          name="用电量"
          unit="kWh"
          :height="220"
        />
      </view>

      <view v-if="loading && list.length === 0" class="tip"><text>加载中…</text></view>
      <view v-else-if="list.length === 0" class="tip"><text>暂无数据</text></view>

      <!-- 明细 -->
      <view v-for="(row, i) in list" :key="i" class="row-card">
        <view class="row-top">
          <text class="row-period">{{ row.time_period }}</text>
          <text class="row-usage">{{ fmtNum(row.usage_quantity) }} kWh</text>
        </view>
        <view class="row-meta">
          <text class="row-loc">{{ locText(row) }}</text>
          <text class="row-mode" :class="row.energy_mode === '制冷' ? 'mode-cool' : 'mode-heat'">{{ row.energy_mode || '-' }}</text>
        </view>
        <view class="row-energy">
          <text>初 {{ fmtNum(row.initial_energy) }} → 末 {{ fmtNum(row.final_energy) }} kWh</text>
        </view>
      </view>

      <view v-if="loading && list.length > 0" class="list-tip"><text>加载中…</text></view>
      <view v-if="noMore && list.length > 0" class="list-tip"><text>没有更多了</text></view>
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

const type = ref('daily')
const useMonth = computed(() => type.value === 'monthly')

const TITLES = { daily: '能耗日报', monthly: '能耗月报', period: '用量查询' }

const buildingOptions = ['全部', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
const buildingIdx = ref(0)
const unitOptions = ['全部', '1', '2', '3']
const unitIdx = ref(0)
const modeOptions = ['全部', '制冷', '制热']
const modeValues = ['', '制冷', '制热']
const modeIdx = ref(0)

const startVal = ref('')
const endVal = ref('')

const list = ref([])
const total = ref(0)
const loading = ref(false)
const noMore = ref(false)
const page = ref(1)
const PAGE_SIZE = 50

const chartCategories = ref([])
const chartValues = ref([])

const totalUsage = computed(() => {
  const s = list.value.reduce((acc, r) => acc + (r.usage_quantity != null ? (parseFloat(r.usage_quantity) || 0) : 0), 0)
  return +s.toFixed(1)
})

function pad(n) { return String(n).padStart(2, '0') }
function fmtNum(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  return isNaN(n) ? String(v) : (+n.toFixed(1)).toString()
}
function locText(row) {
  if (row.building || row.unit || row.room_number) return `${row.building || ''}栋${row.unit || ''}单元${row.room_number || ''}`
  return row.specific_part || '-'
}

function initDefaultRange() {
  const end = new Date()
  const start = new Date()
  if (useMonth.value) {
    start.setMonth(start.getMonth() - 5)
    startVal.value = `${start.getFullYear()}-${pad(start.getMonth() + 1)}`
    endVal.value = `${end.getFullYear()}-${pad(end.getMonth() + 1)}`
  } else {
    start.setDate(start.getDate() - 6)
    startVal.value = `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`
    endVal.value = `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}`
  }
}

function buildSpecificPart() {
  if (buildingIdx.value === 0) return ''
  let sp = buildingOptions[buildingIdx.value]
  if (unitIdx.value !== 0) sp += `-${unitOptions[unitIdx.value]}`
  return sp
}

function buildChart() {
  const byPeriod = {}
  for (const r of list.value) {
    const t = r.time_period
    if (!t) continue
    const u = r.usage_quantity != null ? (parseFloat(r.usage_quantity) || 0) : 0
    byPeriod[t] = (byPeriod[t] || 0) + u
  }
  const cats = Object.keys(byPeriod).sort()
  chartCategories.value = cats
  chartValues.value = cats.map(c => +byPeriod[c].toFixed(1))
}

async function load(reset = false) {
  if (loading.value) return
  if (!startVal.value || !endVal.value) {
    uni.showToast({ title: '请选择时间段', icon: 'none' })
    return
  }
  if (reset) { page.value = 1; noMore.value = false }
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: PAGE_SIZE,
      specific_part: buildSpecificPart(),
      energy_mode: modeValues[modeIdx.value],
    }
    if (useMonth.value) {
      params.start_month = startVal.value
      params.end_month = endVal.value
    } else {
      params.start_time = startVal.value
      params.end_time = endVal.value
    }
    let res
    if (type.value === 'monthly') res = await api.getUsageMonthly(params)
    else if (type.value === 'period') res = await api.getUsagePeriod(params)
    else res = await api.getUsageDaily(params)

    if (res && res.success && Array.isArray(res.data)) {
      list.value = reset ? res.data : [...list.value, ...res.data]
      total.value = res.total || list.value.length
      if (res.data.length < PAGE_SIZE) noMore.value = true
      page.value++
    } else {
      if (reset) list.value = []
      total.value = 0
      noMore.value = true
    }
    buildChart()
  } catch (e) {
    uni.showToast({ title: '查询失败，请重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function query() { load(true) }
function loadMore() { if (!noMore.value) load(false) }

onLoad((options) => {
  type.value = options.type || 'daily'
  uni.setNavigationBarTitle({ title: TITLES[type.value] || '能耗报表' })
  initDefaultRange()
})

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  if (list.value.length === 0) load(true)
})
</script>

<style scoped>
.er-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.filter-card {
  background: #fff;
  border-bottom: 1rpx solid #f0f0f0;
  padding: 12rpx 16rpx;
  flex-shrink: 0;
}
.filter-row {
  display: flex;
  align-items: center;
  padding: 8rpx 0;
}
.f-item {
  flex: 1;
  text-align: center;
}
.f-text {
  font-size: 24rpx;
  color: #555;
}
.f-date {
  flex: 1;
  text-align: center;
  background: #f5f5f5;
  border-radius: 8rpx;
  padding: 10rpx 0;
}
.f-sep {
  font-size: 22rpx;
  color: #999;
  margin: 0 12rpx;
}
.f-btn {
  background: #1a73e8;
  border-radius: 8rpx;
  padding: 10rpx 28rpx;
  margin-left: 12rpx;
}
.f-btn text {
  color: #fff;
  font-size: 24rpx;
}
.er-body {
  flex: 1;
}
.summary {
  background: #fff;
  margin: 16rpx 24rpx 0;
  border-radius: 12rpx;
  padding: 24rpx;
  display: flex;
  align-items: baseline;
  justify-content: center;
}
.sum-num {
  font-size: 48rpx;
  font-weight: bold;
  color: #1a73e8;
  margin-right: 12rpx;
}
.sum-label {
  font-size: 24rpx;
  color: #999;
}
.chart-card {
  background: #fff;
  margin: 16rpx 24rpx;
  border-radius: 12rpx;
  padding: 16rpx;
}
.chart-head { padding: 4rpx 8rpx 12rpx; }
.chart-title { font-size: 28rpx; font-weight: bold; color: #333; }
.tip {
  text-align: center;
  padding: 80rpx 24rpx;
  color: #999;
  font-size: 28rpx;
}
.row-card {
  background: #fff;
  margin: 12rpx 24rpx;
  border-radius: 12rpx;
  padding: 20rpx 24rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06);
}
.row-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8rpx;
}
.row-period { font-size: 26rpx; color: #333; font-weight: bold; }
.row-usage { font-size: 28rpx; color: #1a73e8; font-weight: bold; }
.row-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6rpx;
}
.row-loc { font-size: 24rpx; color: #666; }
.row-mode {
  font-size: 22rpx;
  padding: 2rpx 14rpx;
  border-radius: 20rpx;
}
.mode-cool { background: #e8f0fe; color: #1a73e8; }
.mode-heat { background: #fce8e6; color: #f44336; }
.row-energy { font-size: 22rpx; color: #999; }
.list-tip {
  text-align: center;
  padding: 24rpx;
  font-size: 24rpx;
  color: #999;
}
</style>
