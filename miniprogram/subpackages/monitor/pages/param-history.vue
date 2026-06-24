<!--
  @module MOD-PAGE-PARAM-HISTORY
  @description 设备参数历史趋势图（US-05）。对齐 Web DeviceParamHistoryView：
    GET /api/devices/param-history/ {specific_part,param_names,start_time,end_time,chart:'true'}
      → {success, results:[{param_name, collected_at, value}]}
  param_names / labels 由 device-panel 透传（避开前端 SUB_TYPE_PARAMS 配置常量）。
  简化：数值原样绘制（Web 的 scale/开关/枚举 映射未透传，故温湿度等会按原始整数显示，趋势形状正确、量级未换算）；
    时间范围 1天/7天 切换，每个参数一张折线图。
-->
<template>
  <view class="ph-page">
    <view class="range-bar">
      <view
        v-for="r in ranges"
        :key="r.days"
        class="range-item"
        :class="{ active: rangeDays === r.days }"
        @tap="setRange(r.days)"
      ><text>{{ r.label }}</text></view>
    </view>

    <scroll-view scroll-y class="ph-body">
      <view v-if="loading" class="tip"><text>加载中…</text></view>
      <view v-else-if="params.length === 0" class="tip"><text>无可用参数</text></view>
      <view v-else-if="!hasAnyData" class="tip"><text>该时间段暂无历史数据</text></view>

      <view v-else v-for="p in params" :key="p.name" class="chart-card">
        <view class="chart-head">
          <text class="chart-title">{{ p.label }}</text>
        </view>
        <LineChart
          :canvas-id="'ph_' + p.name"
          :categories="series[p.name] ? series[p.name].categories : []"
          :data="series[p.name] ? series[p.name].values : []"
          :name="p.label"
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

const specificPart = ref('')
const params = ref([])       // [{name, label}]
const series = ref({})       // { param_name: {categories:[], values:[]} }
const loading = ref(false)
const rangeDays = ref(7)
const ranges = [
  { days: 1, label: '近1天' },
  { days: 7, label: '近7天' },
]

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
  if (!specificPart.value || params.value.length === 0) return
  loading.value = true
  try {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - (rangeDays.value - 1))
    const res = await api.getParamHistory({
      specific_part: specificPart.value,
      param_names: params.value.map(p => p.name).join(','),
      start_time: `${dateStr(start)} 00:00:00`,
      end_time: `${dateStr(end)} 23:59:59`,
      chart: 'true',
    })
    const grouped = {}
    for (const p of params.value) grouped[p.name] = { categories: [], values: [] }
    if (res && res.success && Array.isArray(res.results)) {
      for (const row of res.results) {
        const g = grouped[row.param_name]
        if (!g) continue
        g.categories.push(shortTime(row.collected_at))
        const num = Number(row.value)
        g.values.push(isNaN(num) ? 0 : num)
      }
    }
    series.value = grouped
  } catch (e) {
    uni.showToast({ title: '获取历史数据失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function setRange(days) {
  if (rangeDays.value === days) return
  rangeDays.value = days
  load()
}

onLoad((options) => {
  specificPart.value = options.specific_part || ''
  const names = (options.param_names || '').split(',').map(s => decodeURIComponent(s)).filter(Boolean)
  const labels = (options.labels || '').split(',').map(s => decodeURIComponent(s))
  params.value = names.map((n, i) => ({ name: n, label: labels[i] || n }))
  uni.setNavigationBarTitle({ title: decodeURIComponent(options.title || '') || '参数历史' })
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
.ph-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.range-bar {
  display: flex;
  background: #fff;
  border-bottom: 1rpx solid #f0f0f0;
  flex-shrink: 0;
}
.range-item {
  padding: 20rpx 32rpx;
}
.range-item text {
  font-size: 26rpx;
  color: #666;
}
.range-item.active {
  border-bottom: 4rpx solid #1a73e8;
}
.range-item.active text {
  color: #1a73e8;
  font-weight: bold;
}
.ph-body {
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
  padding: 4rpx 8rpx 12rpx;
}
.chart-title {
  font-size: 28rpx;
  font-weight: bold;
  color: #333;
}
</style>
