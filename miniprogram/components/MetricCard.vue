<!--
  @module MOD-COMPONENT-METRICCARD
  @author sub_agent_software_developer
  @description Dashboard metric card. Shows title, value, optional subtitle.
    alert=true turns value text red (for fault/condensation counts > 0).
-->
<template>
  <view class="metric-card" @tap="$emit('tap')">
    <view class="metric-title">{{ title }}</view>
    <view class="metric-value" :class="{ 'metric-value--alert': alert }">{{ value }}</view>
    <view v-if="subtitle" class="metric-subtitle">{{ subtitle }}</view>
  </view>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  value: { type: [String, Number], default: '--' },
  subtitle: { type: String, default: '' },
  alert: { type: Boolean, default: false },
})
defineEmits(['tap'])
</script>

<style scoped>
.metric-card {
  background: #fff;
  border-radius: 12rpx;
  padding: 24rpx;
  flex: 1;
  min-width: 0;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.08);
}
.metric-title {
  font-size: 24rpx;
  color: #666;
  margin-bottom: 8rpx;
}
.metric-value {
  font-size: 44rpx;
  font-weight: bold;
  color: #333;
}
.metric-value--alert {
  color: #f44336;
}
.metric-subtitle {
  font-size: 22rpx;
  color: #999;
  margin-top: 4rpx;
}
</style>
