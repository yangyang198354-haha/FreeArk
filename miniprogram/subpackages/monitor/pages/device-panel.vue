<!--
  @module MOD-PAGE-DEVICE-PANEL
  @description 设备面板（实时参数，US-04）。对齐 Web DeviceCardsView：
    GET /api/devices/realtime-params/?specific_part=X
      → {success, data:{group:{sub_types:{sub:{display, params:[{param_name,display_name,value}]}}}}}
    POST /api/devices/ondemand-refresh/ {specific_part} 触发按需采集。
  移动端简化：①按 sub_type 平铺成卡片（不分"温控/系统"两行）；②按需刷新触发后延时重取，
    不订阅 MQTT done（Web 超时降级亦是直接重取 DB 快照）；③参数值暂原样展示（formatValue 映射后续补）。
  历史趋势按钮：本轮先占位，uCharts 图表页落地后接通。
-->
<template>
  <view class="panel-page">
    <view class="panel-header">
      <text class="panel-sp">{{ specificPart }}</text>
      <view class="panel-actions">
        <view class="hist-btn" @tap="goRoomHistory"><text>房间历史</text></view>
        <view class="refresh-btn" :class="{ disabled: refreshing }" @tap="onDemand">
          <text>{{ refreshing ? '采集中…' : '刷新' }}</text>
        </view>
      </view>
    </view>

    <scroll-view scroll-y class="panel-body">
      <view v-if="loading && !hasData" class="tip"><text>加载中…</text></view>
      <view v-else-if="!hasData" class="tip"><text>暂无设备参数数据</text></view>

      <template v-else>
        <template v-for="(group, gk) in deviceData" :key="gk">
          <view
            v-for="(sub, sk) in group.sub_types"
            :key="sk"
            class="sub-card"
          >
            <view class="sub-head">
              <text class="sub-title">{{ sub.display }}</text>
              <view
                v-if="HISTORY_SUBS.includes(sk)"
                class="sub-hist"
                @tap="goParamHistory(sub)"
              ><text>历史 ›</text></view>
            </view>
            <view class="param-list">
              <view v-for="p in (sub.params || [])" :key="p.param_name" class="param-row">
                <text class="param-label">{{ p.display_name || p.param_name }}</text>
                <text class="param-value">{{ fmt(p.value) }}</text>
              </view>
            </view>
          </view>
        </template>
      </template>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()

// 与 Web 一致：仅这些子类型提供历史趋势入口
const HISTORY_SUBS = ['main_thermostat', 'fresh_air', 'energy_meter', 'hydraulic_module']

const specificPart = ref('')
const deviceData = ref({})
const loading = ref(false)
const refreshing = ref(false)
let ondemandTimer = null

const hasData = computed(() => deviceData.value && Object.keys(deviceData.value).length > 0)

function fmt(v) {
  if (v === null || v === undefined || v === '') return '-'
  return String(v)
}

async function fetchData() {
  if (!specificPart.value) return
  loading.value = true
  try {
    const res = await api.getDeviceRealtimeParams(specificPart.value)
    deviceData.value = (res && res.success) ? (res.data || {}) : {}
    if (!(res && res.success)) uni.showToast({ title: '获取设备数据失败', icon: 'none' })
  } catch (err) {
    uni.showToast({ title: '获取设备数据失败，请重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function onDemand() {
  if (refreshing.value || !specificPart.value) return
  refreshing.value = true
  try {
    await api.ondemandRefresh(specificPart.value)
    // 简化：触发后等待约 5s 再读取快照（不订阅 MQTT done 通知）
    ondemandTimer = setTimeout(async () => {
      await fetchData()
      refreshing.value = false
      ondemandTimer = null
    }, 5000)
  } catch (e) {
    // 降级：直接重取 DB 快照
    await fetchData()
    refreshing.value = false
  }
}

function goParamHistory(sub) {
  // 把该子类型的参数名/显示名透传给历史页（避开前端 SUB_TYPE_PARAMS 配置）
  const ps = (sub && sub.params) || []
  const names = ps.map(p => encodeURIComponent(p.param_name)).join(',')
  const labels = ps.map(p => encodeURIComponent(p.display_name || p.param_name)).join(',')
  uni.navigateTo({
    url: `/subpackages/monitor/pages/param-history?specific_part=${encodeURIComponent(specificPart.value)}&title=${encodeURIComponent(sub.display || '参数历史')}&param_names=${names}&labels=${labels}`,
  })
}
function goRoomHistory() {
  uni.navigateTo({
    url: `/subpackages/monitor/pages/room-history?specific_part=${encodeURIComponent(specificPart.value)}`,
  })
}

onLoad((options) => {
  specificPart.value = options.specific_part || ''
  if (specificPart.value) {
    uni.setNavigationBarTitle({ title: '设备面板' })
  }
})

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  if (!hasData.value) fetchData()
})
</script>

<style scoped>
.panel-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  padding: 20rpx 24rpx;
  border-bottom: 1rpx solid #f0f0f0;
  flex-shrink: 0;
}
.panel-sp {
  font-size: 26rpx;
  color: #333;
  font-weight: bold;
  flex: 1;
  margin-right: 16rpx;
}
.panel-actions {
  display: flex;
  align-items: center;
}
.hist-btn {
  padding: 10rpx 20rpx;
  border-radius: 8rpx;
  background: #f0f4ff;
  margin-right: 12rpx;
}
.hist-btn text {
  font-size: 24rpx;
  color: #1a73e8;
}
.refresh-btn {
  padding: 10rpx 24rpx;
  border-radius: 8rpx;
  background: #1a73e8;
}
.refresh-btn.disabled {
  opacity: 0.6;
}
.refresh-btn text {
  font-size: 24rpx;
  color: #fff;
}
.panel-body {
  flex: 1;
}
.tip {
  text-align: center;
  padding: 80rpx 24rpx;
  color: #999;
  font-size: 28rpx;
}
.sub-card {
  background: #fff;
  margin: 16rpx 24rpx;
  border-radius: 12rpx;
  padding: 20rpx 24rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06);
}
.sub-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12rpx;
  padding-bottom: 12rpx;
  border-bottom: 1rpx solid #f0f0f0;
}
.sub-title {
  font-size: 28rpx;
  font-weight: bold;
  color: #333;
}
.sub-hist text {
  font-size: 22rpx;
  color: #1a73e8;
}
.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10rpx 0;
}
.param-label {
  font-size: 26rpx;
  color: #666;
}
.param-value {
  font-size: 26rpx;
  color: #333;
  font-weight: bold;
}
</style>
