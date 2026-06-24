<!--
  @module MOD-PAGE-PLC-STATUS
  @description PLC 连接状态列表（US-03）。对齐 Web PlcStatusView.vue：
    GET /api/plc/connection-status/ {page,page_size,building,unit,connection_status}
    → {success, data:[{specific_part,connection_status,last_online_time,building,unit,room_number}], total, statistics}
    筛选：连接状态 / 楼栋 / 单元。移动端用卡片列表 + 加载更多 + 下拉刷新。
    行点击原 Web 跳 SpecificPartDetail（部件详情，属二期）→ 暂以 toast 提示。
-->
<template>
  <view class="plc-page">
    <!-- 统计头 -->
    <view class="stats-bar">
      <view class="stat-cell">
        <text class="stat-num stat-online">{{ statistics.online_count }}</text>
        <text class="stat-label">在线</text>
      </view>
      <view class="stat-cell">
        <text class="stat-num stat-offline">{{ statistics.offline_count }}</text>
        <text class="stat-label">离线</text>
      </view>
      <view class="stat-cell">
        <text class="stat-num">{{ statistics.total_devices }}</text>
        <text class="stat-label">总数</text>
      </view>
      <view class="stat-cell">
        <text class="stat-num">{{ onlineRateText }}</text>
        <text class="stat-label">在线率</text>
      </view>
    </view>

    <!-- 筛选条 -->
    <view class="filter-bar">
      <picker class="filter-item" mode="selector" :range="statusOptions" :value="statusIdx" @change="onStatusChange">
        <text class="filter-text">状态: {{ statusOptions[statusIdx] }}</text>
      </picker>
      <picker class="filter-item" mode="selector" :range="buildingOptions" :value="buildingIdx" @change="onBuildingChange">
        <text class="filter-text">楼栋: {{ buildingOptions[buildingIdx] }}</text>
      </picker>
      <picker class="filter-item" mode="selector" :range="unitOptions" :value="unitIdx" @change="onUnitChange">
        <text class="filter-text">单元: {{ unitOptions[unitIdx] }}</text>
      </picker>
    </view>

    <!-- 列表 -->
    <scroll-view
      scroll-y
      class="plc-list"
      @scrolltolower="loadMore"
      refresher-enabled
      :refresher-triggered="refreshing"
      @refresherrefresh="onRefresh"
    >
      <view v-if="list.length === 0 && !loading" class="empty-state">
        <text class="empty-text">暂无数据</text>
      </view>

      <view
        v-for="row in list"
        :key="row.specific_part"
        class="plc-item"
        @tap="openDetail(row)"
      >
        <view class="plc-top">
          <text class="plc-id">{{ row.specific_part }}</text>
          <text class="plc-tag" :class="row.connection_status === 'online' ? 'tag-online' : 'tag-offline'">
            {{ row.connection_status === 'online' ? '在线' : '离线' }}
          </text>
        </view>
        <view class="plc-meta">
          <text class="meta-item">{{ row.building }}栋{{ row.unit }}单元{{ row.room_number }}</text>
          <text v-if="row.connection_status === 'offline'" class="meta-offline">
            最后在线 {{ formatDateTime(row.last_online_time) }}
          </text>
        </view>
      </view>

      <view v-if="loading" class="list-tip"><text>加载中…</text></view>
      <view v-if="noMore && list.length > 0" class="list-tip"><text>没有更多了</text></view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()

const list = ref([])
const loading = ref(false)
const refreshing = ref(false)
const noMore = ref(false)
const page = ref(1)
const total = ref(0)
const PAGE_SIZE = 20
const statistics = ref({ online_count: 0, offline_count: 0, total_devices: 0, online_rate: 0 })

// 筛选项（与 Web 一致：状态 / 楼栋 1-10 / 单元 1-3）
const statusOptions = ['全部', '在线', '离线']
const statusValues = ['', 'online', 'offline']
const statusIdx = ref(0)
const buildingOptions = ['全部', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
const buildingIdx = ref(0)
const unitOptions = ['全部', '1', '2', '3']
const unitIdx = ref(0)

const onlineRateText = computed(() => {
  const r = statistics.value.online_rate
  if (r === undefined || r === null || r === '') return '--'
  // 后端可能返回 0-1 或 0-100，做一次归一展示
  const num = Number(r)
  if (isNaN(num)) return '--'
  const pct = num <= 1 ? num * 100 : num
  return `${pct.toFixed(0)}%`
})

async function loadData(reset = false) {
  if (loading.value) return
  if (reset) {
    page.value = 1
    noMore.value = false
  }
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: PAGE_SIZE,
      building: buildingIdx.value === 0 ? '' : buildingOptions[buildingIdx.value],
      unit: unitIdx.value === 0 ? '' : unitOptions[unitIdx.value],
      connection_status: statusValues[statusIdx.value],
    }
    const res = await api.getPlcConnectionStatus(params)
    if (res && res.success && Array.isArray(res.data)) {
      list.value = reset ? res.data : [...list.value, ...res.data]
      total.value = res.total || 0
      if (res.statistics) statistics.value = res.statistics
      if (res.data.length < PAGE_SIZE) noMore.value = true
      page.value++
    } else {
      if (reset) list.value = []
      noMore.value = true
    }
  } catch (err) {
    uni.showToast({ title: '获取数据失败，请重试', icon: 'none' })
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function loadMore() {
  if (!noMore.value) loadData(false)
}

async function onRefresh() {
  refreshing.value = true
  await loadData(true)
}

function applyFilter() {
  loadData(true)
}
function onStatusChange(e) { statusIdx.value = Number(e.detail.value); applyFilter() }
function onBuildingChange(e) { buildingIdx.value = Number(e.detail.value); applyFilter() }
function onUnitChange(e) { unitIdx.value = Number(e.detail.value); applyFilter() }

function formatDateTime(s) {
  if (!s) return '-'
  const d = new Date(s)
  if (isNaN(d.getTime())) return '-'
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function openDetail() {
  // 部件详情页（SpecificPartDetail）属二期范围
  uni.showToast({ title: '设备详情功能二期开放', icon: 'none' })
}

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  loadData(true)
})
</script>

<style scoped>
.plc-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.stats-bar {
  display: flex;
  background: #fff;
  padding: 24rpx 0;
  flex-shrink: 0;
}
.stat-cell {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.stat-num {
  font-size: 36rpx;
  font-weight: bold;
  color: #333;
}
.stat-online { color: #34a853; }
.stat-offline { color: #f44336; }
.stat-label {
  font-size: 22rpx;
  color: #999;
  margin-top: 4rpx;
}
.filter-bar {
  display: flex;
  background: #fff;
  border-top: 1rpx solid #f0f0f0;
  border-bottom: 1rpx solid #f0f0f0;
  flex-shrink: 0;
}
.filter-item {
  flex: 1;
  padding: 20rpx 0;
  text-align: center;
}
.filter-text {
  font-size: 24rpx;
  color: #555;
}
.plc-list {
  flex: 1;
}
.plc-item {
  background: #fff;
  margin: 12rpx 24rpx;
  border-radius: 12rpx;
  padding: 24rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06);
}
.plc-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10rpx;
}
.plc-id {
  font-size: 28rpx;
  color: #333;
  font-weight: bold;
  flex: 1;
  margin-right: 16rpx;
}
.plc-tag {
  font-size: 22rpx;
  padding: 2rpx 16rpx;
  border-radius: 20rpx;
  flex-shrink: 0;
}
.tag-online {
  background: #e6f4ea;
  color: #34a853;
}
.tag-offline {
  background: #fce8e6;
  color: #f44336;
}
.plc-meta {
  display: flex;
  flex-direction: column;
}
.meta-item {
  font-size: 24rpx;
  color: #666;
}
.meta-offline {
  font-size: 22rpx;
  color: #999;
  margin-top: 4rpx;
}
.empty-state {
  padding: 80rpx 48rpx;
  text-align: center;
}
.empty-text {
  color: #999;
  font-size: 28rpx;
}
.list-tip {
  text-align: center;
  padding: 24rpx;
  font-size: 24rpx;
  color: #999;
}
</style>
