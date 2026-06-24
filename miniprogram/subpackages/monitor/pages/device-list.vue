<!--
  @module MOD-PAGE-DEVICE-LIST
  @description 设备列表（US-04，房间筛选）。对齐 Web DeviceManagementDeviceListView：
    GET /api/device-management/device-list/ {page,page_size,room_no} → DRF {results,count}
    room_no 由 楼栋[-单元[-户号]] 拼成（与 Web CascadingSelector 一致）。
    点设备 → 设备面板（实时参数）。移动端：房间筛选 + 加载更多 + 下拉刷新。
    注：Web 还有 屏/PLC/开关/模式/故障 等多个状态筛选与列，移动端首期先做房间筛选+设备身份，其余从简。
-->
<template>
  <view class="dl-page">
    <!-- 房间筛选 -->
    <view class="filter-bar">
      <picker class="filter-item" mode="selector" :range="buildingOptions" :value="buildingIdx" @change="onBuildingChange">
        <text class="filter-text">楼栋: {{ buildingOptions[buildingIdx] }}</text>
      </picker>
      <picker class="filter-item" mode="selector" :range="unitOptions" :value="unitIdx" @change="onUnitChange">
        <text class="filter-text">单元: {{ unitOptions[unitIdx] }}</text>
      </picker>
      <input
        class="filter-input"
        v-model="roomInput"
        placeholder="户号"
        confirm-type="search"
        @confirm="applyFilter"
      />
      <view class="filter-btn" @tap="applyFilter"><text>查询</text></view>
    </view>

    <scroll-view
      scroll-y
      class="dl-list"
      @scrolltolower="loadMore"
      refresher-enabled
      :refresher-triggered="refreshing"
      @refresherrefresh="onRefresh"
    >
      <view v-if="list.length === 0 && !loading" class="empty-state">
        <text class="empty-text">暂无设备</text>
      </view>

      <view
        v-for="row in list"
        :key="row.specific_part"
        class="dl-item"
        @tap="openPanel(row)"
      >
        <view class="dl-room">{{ row.building }}栋{{ row.unit }}单元{{ row.room_number }}</view>
        <view class="dl-sub">
          <text class="dl-sp">{{ row.specific_part }}</text>
          <text class="dl-arrow">›</text>
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

const list = ref([])
const loading = ref(false)
const refreshing = ref(false)
const noMore = ref(false)
const page = ref(1)
const PAGE_SIZE = 20

const buildingOptions = ['全部', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
const buildingIdx = ref(0)
const unitOptions = ['全部', '1', '2', '3']
const unitIdx = ref(0)
const roomInput = ref('')

function buildRoomNo() {
  if (buildingIdx.value === 0) return ''
  let r = buildingOptions[buildingIdx.value]
  if (unitIdx.value !== 0) r += `-${unitOptions[unitIdx.value]}`
  if (unitIdx.value !== 0 && roomInput.value.trim()) r += `-${roomInput.value.trim()}`
  return r
}

async function loadData(reset = false) {
  if (loading.value) return
  if (reset) {
    page.value = 1
    noMore.value = false
  }
  loading.value = true
  try {
    const params = { page: page.value, page_size: PAGE_SIZE }
    const roomNo = buildRoomNo()
    if (roomNo) params.room_no = roomNo
    const res = await api.getDeviceList(params)
    const items = (res && res.results !== undefined) ? res.results : []
    list.value = reset ? items : [...list.value, ...items]
    if (items.length < PAGE_SIZE) noMore.value = true
    page.value++
  } catch (err) {
    uni.showToast({ title: '获取设备列表失败', icon: 'none' })
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
function onBuildingChange(e) { buildingIdx.value = Number(e.detail.value) }
function onUnitChange(e) { unitIdx.value = Number(e.detail.value) }

function openPanel(row) {
  uni.navigateTo({
    url: `/subpackages/monitor/pages/device-panel?specific_part=${encodeURIComponent(row.specific_part)}`,
  })
}

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  if (list.value.length === 0) loadData(true)
})
</script>

<style scoped>
.dl-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.filter-bar {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1rpx solid #f0f0f0;
  padding: 12rpx 16rpx;
  flex-shrink: 0;
}
.filter-item {
  flex: 1;
  text-align: center;
}
.filter-text {
  font-size: 24rpx;
  color: #555;
}
.filter-input {
  width: 120rpx;
  font-size: 24rpx;
  background: #f5f5f5;
  border-radius: 8rpx;
  padding: 8rpx 12rpx;
  margin: 0 12rpx;
}
.filter-btn {
  background: #1a73e8;
  border-radius: 8rpx;
  padding: 10rpx 24rpx;
}
.filter-btn text {
  color: #fff;
  font-size: 24rpx;
}
.dl-list {
  flex: 1;
}
.dl-item {
  background: #fff;
  margin: 12rpx 24rpx;
  border-radius: 12rpx;
  padding: 24rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06);
}
.dl-room {
  font-size: 30rpx;
  color: #333;
  font-weight: bold;
  margin-bottom: 8rpx;
}
.dl-sub {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.dl-sp {
  font-size: 24rpx;
  color: #999;
}
.dl-arrow {
  font-size: 32rpx;
  color: #bbb;
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
