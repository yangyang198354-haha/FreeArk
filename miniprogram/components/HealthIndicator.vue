<!--
  @module MOD-BD-008
  @implements IFC-BD-008-01, IFC-BD-008-02, IFC-BD-008-03
  @depends none
  @description Overall health status diamond LED indicator for the bridge dashboard.
    Displays a rotating-diamond LED with glow effect, color-coded by status level.
    Also shows a condensation warning count badge.
-->
<template>
  <view class="health-indicator" :class="ledClass">
    <view class="health-led" />
    <view class="health-text">
      <text class="health-label">{{ status.text }}</text>
      <view v-if="condensationCount > 0" class="condensation-badge">
        <text>{{ condensationCount }}</text>
        <text class="badge-label">结露</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

/**
 * IFC-BD-008-01: status — { level: 'syncing'|'normal'|'warning'|'fault', text: String }
 *   - level=fault   → red glow
 *   - level=warning → yellow glow
 *   - level=normal  → green glow
 *   - level=syncing → grey (sync pulse)
 */
const props = defineProps({
  status: {
    type: Object,
    default: () => ({ level: 'syncing', text: '同步中' }),
  },
  /** IFC-BD-008-02: Active condensation warning count. */
  condensationCount: {
    type: Number,
    default: 0,
  },
})

/** IFC-BD-008-03: CSS class for LED color state. */
const ledClass = computed(() => {
  const level = props.status?.level || 'syncing'
  return `state-${level}`
})
</script>

<style scoped>
.health-indicator {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  padding: 10rpx 18rpx;
  border: 1rpx solid rgba(120, 160, 255, 0.22);
  background: rgba(7, 14, 31, 0.72);
}

.health-led {
  width: 16rpx;
  height: 16rpx;
  margin-right: 16rpx;
  background: #5f7da6;
  transform: rotate(45deg);
  flex-shrink: 0;
}

/* Diamond LED color + glow by state */
.state-normal .health-led {
  background: #27f5b5;
  box-shadow: 0 0 14rpx #27f5b5;
}
.state-warning .health-led {
  background: #ffd400;
  box-shadow: 0 0 14rpx #ffd400;
}
.state-fault .health-led {
  background: #ff315d;
  box-shadow: 0 0 14rpx #ff315d;
}

/* syncing: grey pulsing */
.state-syncing .health-led {
  background: #5f7da6;
}

.health-text {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.health-label {
  font-size: 22rpx;
  color: #9fb8d8;
}

.state-normal .health-label { color: #27f5b5; }
.state-warning .health-label { color: #ffd400; }
.state-fault .health-label { color: #ff6b8b; }

.condensation-badge {
  display: flex;
  align-items: center;
  gap: 4rpx;
  padding: 4rpx 10rpx;
  border: 1rpx solid rgba(255, 212, 0, 0.5);
  background: rgba(255, 212, 0, 0.12);
}

.condensation-badge text {
  font-size: 20rpx;
  color: #ffd400;
  font-weight: 700;
}

.badge-label {
  font-weight: 400 !important;
  font-size: 18rpx !important;
}
</style>
