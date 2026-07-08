<!--
  @module MOD-BD-009
  @implements IFC-BD-009-01, IFC-BD-009-02, IFC-BD-009-03, IFC-BD-009-04, IFC-BD-009-05
  @depends none
  @description Standalone PLC online status indicator.
    All online → normal cyan; some offline → warning yellow with pulse; all offline → fault red.
-->
<template>
  <view class="plc-indicator" :class="statusClass">
    <view class="plc-label">
      <text>通讯链路</text>
    </view>
    <view class="plc-led-area">
      <view class="plc-led" />
      <text class="plc-count">{{ displayLabel }}</text>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

/**
 * IFC-BD-009-01: Number of currently online PLCs.
 * IFC-BD-009-02: Total number of PLCs.
 * IFC-BD-009-03: Whether data is still loading.
 */
const props = defineProps({
  onlineCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})

/** IFC-BD-009-04: Derive status from online/total ratio. */
const statusClass = computed(() => {
  if (props.loading) return 'state-idle'
  if (props.totalCount === 0) return 'state-idle'
  if (props.onlineCount === props.totalCount) return 'state-normal'
  if (props.onlineCount > 0) return 'state-warning'
  return 'state-fault'
})

/** IFC-BD-009-05: Display text. */
const displayLabel = computed(() => {
  if (props.loading) return '同步中'
  if (props.totalCount === 0) return '—'
  return `${props.onlineCount}/${props.totalCount} 在线`
})
</script>

<style scoped>
.plc-indicator {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16rpx 22rpx;
  margin: 10rpx 22rpx 16rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.26);
  background: rgba(7, 15, 32, 0.68);
}

.plc-label text {
  font-size: 22rpx;
  color: #6f8cad;
}

.plc-led-area {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.plc-led {
  width: 14rpx;
  height: 14rpx;
  background: #27f5b5;
  box-shadow: 0 0 10rpx rgba(39, 245, 181, 0.7);
  transform: rotate(45deg);
}

.plc-count {
  font-size: 24rpx;
  color: #eaf6ff;
}

/* State variations */
.state-idle .plc-led { background: #5f7da6; box-shadow: none; }
.state-idle .plc-count { color: #6f8cad; }

.state-normal .plc-led {
  background: #27f5b5;
  box-shadow: 0 0 10rpx rgba(39, 245, 181, 0.7);
}

.state-warning {
  border-color: rgba(255, 212, 0, 0.42);
}
.state-warning .plc-led {
  background: #ffd400;
  box-shadow: 0 0 12rpx rgba(255, 212, 0, 0.8);
  animation: pulseSoft 1.8s ease-in-out infinite;
}
.state-warning .plc-count { color: #ffd400; }

.state-fault {
  border-color: rgba(255, 49, 93, 0.48);
}
.state-fault .plc-led {
  background: #ff315d;
  box-shadow: 0 0 14rpx rgba(255, 49, 93, 0.9);
  animation: damageBlink 1.1s ease-in-out infinite;
}
.state-fault .plc-count { color: #ff315d; }

/* Reuse existing keyframes (must be defined in parent or global) */
@keyframes pulseSoft {
  0%, 100% { opacity: 0.65; }
  50% { opacity: 1; }
}
@keyframes damageBlink {
  0%, 100% { opacity: 0.48; transform: rotate(45deg) scale(1); }
  50% { opacity: 1; transform: rotate(45deg) scale(1.12); }
}
</style>
