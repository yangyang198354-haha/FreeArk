<!--
  @module MOD-PAGE-FAULTS
  @description 故障管理（只读，US-07）。对齐 Web FaultManagementView：
    GET /api/devices/fault-events/ {page,page_size,is_active,first_seen_after,...} → DRF {results,count}
    字段：specific_part,room_name,fault_code,fault_message,fault_type,severity,
         first_seen_at,last_seen_at,recovered_at,is_active。默认近 7 天。
  移动端：状态三态筛选(全部/活跃/已恢复) + 卡片列表 + 加载更多；只读（不含触发巡检等管理动作）。
-->
<template>
  <view class="fl-page">
    <view class="filter-bar">
      <view
        v-for="(opt, i) in statusOptions"
        :key="i"
        class="seg"
        :class="{ active: statusIdx === i }"
        @tap="setStatus(i)"
      ><text>{{ opt }}</text></view>
    </view>

    <scroll-view
      scroll-y class="fl-list"
      @scrolltolower="loadMore"
      refresher-enabled :refresher-triggered="refreshing" @refresherrefresh="onRefresh"
    >
      <view v-if="list.length === 0 && !loading" class="empty"><text>暂无故障记录</text></view>

      <view v-for="(row, i) in list" :key="i" class="card">
        <view class="card-top">
          <text class="loc">{{ row.specific_part }}</text>
          <text class="tag" :class="row.is_active ? 'tag-active' : 'tag-recovered'">
            {{ row.is_active ? '活跃' : '已恢复' }}
          </text>
        </view>
        <text class="msg">{{ row.fault_message || row.fault_code || '—' }}</text>
        <view class="meta">
          <text class="meta-item">{{ row.room_name || '' }}</text>
          <text class="meta-item">{{ row.fault_type || '' }}</text>
          <text v-if="row.severity" class="meta-item">{{ row.severity }}</text>
        </view>
        <view class="times">
          <text>首次 {{ fmt(row.first_seen_at) }}</text>
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

const statusOptions = ['全部', '活跃', '已恢复']
const statusValues = ['', 'true', 'false']
const statusIdx = ref(1) // 默认显示活跃

const list = ref([])
const loading = ref(false)
const refreshing = ref(false)
const noMore = ref(false)
const page = ref(1)
const PAGE_SIZE = 20

function fmt(s) {
  if (!s) return '—'
  return String(s).replace('T', ' ').slice(5, 16)
}

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
    const res = await api.getFaultEvents(params)
    const items = res && res.results !== undefined ? res.results : (res && res.data) || []
    list.value = reset ? items : [...list.value, ...items]
    if (items.length < PAGE_SIZE) noMore.value = true
    page.value++
  } catch (e) {
    uni.showToast({ title: '获取故障列表失败', icon: 'none' })
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
.fl-page { display: flex; flex-direction: column; height: 100vh; background: #f5f5f5; }
.filter-bar { display: flex; background: #fff; border-bottom: 1rpx solid #f0f0f0; flex-shrink: 0; }
.seg { flex: 1; text-align: center; padding: 20rpx 0; }
.seg text { font-size: 26rpx; color: #666; }
.seg.active { border-bottom: 4rpx solid #1a73e8; }
.seg.active text { color: #1a73e8; font-weight: bold; }
.fl-list { flex: 1; }
.empty { text-align: center; padding: 80rpx 24rpx; color: #999; font-size: 28rpx; }
.card { background: #fff; margin: 12rpx 24rpx; border-radius: 12rpx; padding: 20rpx 24rpx; box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8rpx; }
.loc { font-size: 28rpx; font-weight: bold; color: #333; }
.tag { font-size: 22rpx; padding: 2rpx 16rpx; border-radius: 20rpx; }
.tag-active { background: #fce8e6; color: #f44336; }
.tag-recovered { background: #e6f4ea; color: #34a853; }
.msg { font-size: 26rpx; color: #333; display: block; margin-bottom: 8rpx; }
.meta { display: flex; flex-wrap: wrap; margin-bottom: 6rpx; }
.meta-item { font-size: 22rpx; color: #888; margin-right: 16rpx; }
.times { font-size: 22rpx; color: #aaa; }
.list-tip { text-align: center; padding: 24rpx; font-size: 24rpx; color: #999; }
</style>
