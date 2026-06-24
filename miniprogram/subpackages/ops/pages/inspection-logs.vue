<!--
  @module MOD-PAGE-INSPECTION-LOGS
  @description 巡检工作日志（只读，US-14）。对齐 Web InspectionWorkLogView：
    GET /api/inspection/logs/ {page,page_size,...} → {success,data,total}
    字段：created_at,specific_part,event_type_display,source_event_id,step,result,work_order_ticket。
    result：SUCCESS/BLOCKED/ERROR/SKIPPED/INFO。
-->
<template>
  <view class="il-page">
    <scroll-view scroll-y class="il-list" @scrolltolower="loadMore" refresher-enabled :refresher-triggered="refreshing" @refresherrefresh="onRefresh">
      <view v-if="logs.length === 0 && !loading" class="empty"><text>暂无工作日志</text></view>

      <view v-for="(row, i) in logs" :key="i" class="card">
        <view class="card-top">
          <text class="ev">{{ row.event_type_display || '事件' }} #{{ row.source_event_id }}</text>
          <text class="res" :class="resClass(row.result)">{{ resLabel(row.result) }}</text>
        </view>
        <view class="line"><text class="k">房号</text><text class="v">{{ row.specific_part || '—' }}</text></view>
        <view class="line"><text class="k">步骤</text><text class="v">{{ row.step || '—' }}</text></view>
        <view v-if="row.work_order_ticket" class="line"><text class="k">工单</text><text class="v tk">{{ row.work_order_ticket }}</text></view>
        <text class="time">{{ fmt(row.created_at) }}</text>
      </view>

      <view v-if="loading" class="list-tip"><text>加载中…</text></view>
      <view v-if="noMore && logs.length > 0" class="list-tip"><text>没有更多了</text></view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()

const RESULT_LABELS = { SUCCESS: '成功', BLOCKED: '已拦截', ERROR: '错误', SKIPPED: '已跳过', INFO: '信息' }

const logs = ref([])
const total = ref(0)
const loading = ref(false)
const refreshing = ref(false)
const noMore = ref(false)
const page = ref(1)
const PAGE_SIZE = 20

function fmt(s) { return s ? String(s).replace('T', ' ').slice(0, 16) : '—' }
function resLabel(r) { return RESULT_LABELS[r] || r || '—' }
function resClass(r) {
  if (r === 'SUCCESS') return 'r-success'
  if (r === 'BLOCKED' || r === 'SKIPPED') return 'r-warn'
  if (r === 'ERROR') return 'r-error'
  return 'r-info'
}

async function load(reset = false) {
  if (loading.value) return
  if (reset) { page.value = 1; noMore.value = false }
  loading.value = true
  try {
    const res = await api.getInspectionLogs({ page: page.value, page_size: PAGE_SIZE })
    if (res && res.success && Array.isArray(res.data)) {
      logs.value = reset ? res.data : [...logs.value, ...res.data]
      total.value = res.total || logs.value.length
      if (res.data.length < PAGE_SIZE) noMore.value = true
      page.value++
    } else {
      if (reset) logs.value = []
      noMore.value = true
    }
  } catch (e) {
    uni.showToast({ title: '获取工作日志失败', icon: 'none' })
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function loadMore() { if (!noMore.value) load(false) }
async function onRefresh() { refreshing.value = true; await load(true) }

onShow(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  load(true)
})
</script>

<style scoped>
.il-page { display: flex; flex-direction: column; height: 100vh; background: #f5f5f5; }
.il-list { flex: 1; }
.empty { text-align: center; padding: 80rpx 24rpx; color: #999; font-size: 28rpx; }
.card { background: #fff; margin: 12rpx 24rpx; border-radius: 12rpx; padding: 20rpx 24rpx; box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8rpx; }
.ev { font-size: 26rpx; font-weight: bold; color: #333; }
.res { font-size: 22rpx; padding: 2rpx 16rpx; border-radius: 20rpx; }
.r-success { background: #e6f4ea; color: #34a853; }
.r-warn { background: #fff4e5; color: #f59e0b; }
.r-error { background: #fce8e6; color: #f44336; }
.r-info { background: #eef1f5; color: #888; }
.line { display: flex; padding: 4rpx 0; }
.k { font-size: 24rpx; color: #999; width: 90rpx; }
.v { font-size: 24rpx; color: #555; flex: 1; }
.v.tk { color: #1a73e8; }
.time { font-size: 22rpx; color: #aaa; margin-top: 6rpx; display: block; }
.list-tip { text-align: center; padding: 24rpx; font-size: 24rpx; color: #999; }
</style>
