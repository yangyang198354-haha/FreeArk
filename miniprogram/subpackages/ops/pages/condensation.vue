<!--
  @module MOD-PAGE-CONDENSATION
  @description 结露预警（只读，US-08）。对齐 Web CondensationWarningView：
    GET /api/devices/condensation-warning-events/ {page,page_size,is_active,first_seen_after} → DRF {results,count}
    字段：specific_part,room_name,warning_type,warning_message,dew_point_temp,ntc_temp,humidity,
         first_seen_at,recovered_at,is_active。默认近 7 天。只读（不含触发巡检）。
-->
<template>
  <view class="cw-page">
    <view class="filter-bar">
      <view v-for="(opt, i) in statusOptions" :key="i" class="seg" :class="{ active: statusIdx === i }" @tap="setStatus(i)">
        <text>{{ opt }}</text>
      </view>
    </view>

    <scroll-view scroll-y class="cw-list" @scrolltolower="loadMore" refresher-enabled :refresher-triggered="refreshing" @refresherrefresh="onRefresh">
      <view v-if="list.length === 0 && !loading" class="empty"><text>暂无结露预警</text></view>

      <view v-for="(row, i) in list" :key="i" class="card">
        <view class="card-top">
          <text class="loc">{{ row.specific_part }}</text>
          <text class="tag" :class="row.is_active ? 'tag-active' : 'tag-recovered'">{{ row.is_active ? '预警中' : '已恢复' }}</text>
        </view>
        <text class="msg">{{ row.warning_message || row.warning_type || '—' }}</text>
        <view class="metrics">
          <text class="m">露点 {{ num(row.dew_point_temp) }}°C</text>
          <text class="m">NTC {{ num(row.ntc_temp) }}°C</text>
          <text class="m">湿度 {{ num(row.humidity) }}%</text>
        </view>
        <view class="times">
          <text>{{ row.room_name || '' }} · 首次 {{ fmt(row.first_seen_at) }}</text>
          <text v-if="!row.is_active && row.recovered_at">· 恢复 {{ fmt(row.recovered_at) }}</text>
        </view>
      </view>

      <view v-if="loading" class="list-tip"><text>加载中…</text></view>
      <view v-if="noMore && list.length > 0" class="list-tip"><text>没有更多了</text></view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()

const statusOptions = ['全部', '预警中', '已恢复']
const statusValues = ['', 'true', 'false']
const statusIdx = ref(1)

const list = ref([])
const loading = ref(false)
const refreshing = ref(false)
const noMore = ref(false)
const page = ref(1)
const PAGE_SIZE = 20

function fmt(s) { return s ? String(s).replace('T', ' ').slice(5, 16) : '—' }
function num(v) { return (v === null || v === undefined || v === '') ? '-' : v }

async function load(reset = false) {
  if (loading.value) return
  if (reset) { page.value = 1; noMore.value = false }
  loading.value = true
  try {
    const sevenAgo = new Date()
    sevenAgo.setDate(sevenAgo.getDate() - 7)
    const params = {
      page: page.value,
      page_size: PAGE_SIZE,
      first_seen_after: sevenAgo.toISOString().slice(0, 10) + 'T00:00:00',
    }
    if (statusValues[statusIdx.value]) params.is_active = statusValues[statusIdx.value]
    const res = await api.getCondensationEvents(params)
    const items = res && res.results !== undefined ? res.results : (res && res.data) || []
    list.value = reset ? items : [...list.value, ...items]
    if (items.length < PAGE_SIZE) noMore.value = true
    page.value++
  } catch (e) {
    uni.showToast({ title: '获取结露预警失败', icon: 'none' })
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function setStatus(i) { if (statusIdx.value === i) return; statusIdx.value = i; load(true) }
function loadMore() { if (!noMore.value) load(false) }
async function onRefresh() { refreshing.value = true; await load(true) }

onShow(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  load(true)
})
</script>

<style scoped>
.cw-page { display: flex; flex-direction: column; height: 100vh; background: #f5f5f5; }
.filter-bar { display: flex; background: #fff; border-bottom: 1rpx solid #f0f0f0; flex-shrink: 0; }
.seg { flex: 1; text-align: center; padding: 20rpx 0; }
.seg text { font-size: 26rpx; color: #666; }
.seg.active { border-bottom: 4rpx solid #1a73e8; }
.seg.active text { color: #1a73e8; font-weight: bold; }
.cw-list { flex: 1; }
.empty { text-align: center; padding: 80rpx 24rpx; color: #999; font-size: 28rpx; }
.card { background: #fff; margin: 12rpx 24rpx; border-radius: 12rpx; padding: 20rpx 24rpx; box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8rpx; }
.loc { font-size: 28rpx; font-weight: bold; color: #333; }
.tag { font-size: 22rpx; padding: 2rpx 16rpx; border-radius: 20rpx; }
.tag-active { background: #fff4e5; color: #f59e0b; }
.tag-recovered { background: #e6f4ea; color: #34a853; }
.msg { font-size: 26rpx; color: #333; display: block; margin-bottom: 10rpx; }
.metrics { display: flex; margin-bottom: 8rpx; }
.m { font-size: 24rpx; color: #1a73e8; margin-right: 20rpx; }
.times { font-size: 22rpx; color: #aaa; }
.list-tip { text-align: center; padding: 24rpx; font-size: 24rpx; color: #999; }
</style>
