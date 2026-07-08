<!--
  @module MOD-BD-007
  @implements IFC-BD-007-01 through IFC-BD-007-06
  @depends none
  @description Half-screen drawer for fault/warning event details.
    Dark semi-transparent background with cyan glowing border.
    List items with status-color left border (red=fault / yellow=warning).
    Shows device name, fault type, severity, fault message, first seen time.
    Supports swipe-down close, overlay-tap close, and handle-tap close.
    Safe-area bottom padding for iPhone notch devices.
-->
<template>
  <view v-if="visible && compartment" class="drawer-root" @touchmove.stop.prevent>
    <!-- Overlay backdrop -->
    <view class="drawer-overlay" @tap="onClose" />

    <!-- Drawer panel -->
    <view
      class="drawer-panel"
      :class="{ 'drawer-open': visible }"
      @touchstart="onTouchStart"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
    >
      <!-- Close handle -->
      <view class="drawer-handle" @tap="onClose">
        <view class="handle-bar" />
      </view>

      <!-- Title -->
      <view class="drawer-title">
        <text class="drawer-title-text">{{ title }}</text>
        <text class="drawer-title-status" :class="statusClass">{{ compartment.status === 'fault' ? '告警' : compartment.status === 'warning' ? '预警' : '正常' }}</text>
      </view>

      <!-- Event list -->
      <scroll-view scroll-y class="drawer-list">
        <view v-if="!hasEvents" class="drawer-empty">
          <text>该隔舱运行正常，无活跃故障或预警</text>
        </view>

        <view
          v-for="(event, idx) in eventsBySeverity"
          :key="event.id || idx"
          class="drawer-item"
          :class="event.severity === 'fault' || event.severity === 'error' ? 'item-fault' : 'item-warning'"
        >
          <!-- Status color left bar -->
          <view class="item-bar" />

          <view class="item-content">
            <view class="item-header">
              <text class="item-device">{{ event.deviceName || '未知设备' }}</text>
              <text class="item-severity" :class="event.severity === 'fault' || event.severity === 'error' ? 'sev-fault' : 'sev-warning'">
                {{ event.severity === 'fault' || event.severity === 'error' ? '故障' : event.severity === 'condensation' ? '结露' : '预警' }}
              </text>
            </view>

            <text class="item-type">{{ event.faultType || event.deviceTypeLabel || '' }}</text>

            <text v-if="event.faultMessage" class="item-message">{{ event.faultMessage }}</text>

            <view class="item-footer">
              <text v-if="event.roomName" class="item-room">{{ event.roomName }}</text>
              <text class="item-time">{{ formatTime(event.firstSeenAt) }}</text>
            </view>
          </view>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'

/**
 * IFC-BD-007-01: Compartment detail { type, id, name, status, faultEvents[] } | null.
 * IFC-BD-007-02: Drawer visibility.
 */
const props = defineProps({
  compartment: { type: Object, default: null },
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

/** IFC-BD-007-04: Drawer title. */
const title = computed(() => {
  const c = props.compartment
  if (!c) return ''
  const typeLabel = c.type === 'subsystem' ? '子系统' : '房间'
  return `${c.name} — ${typeLabel}状态`
})

/** IFC-BD-007-05: Whether there are any events. */
const hasEvents = computed(() => {
  return props.compartment?.faultEvents?.length > 0
})

/** IFC-BD-007-06: Events sorted by severity (errors first). */
const eventsBySeverity = computed(() => {
  const events = props.compartment?.faultEvents || []
  return [...events].sort((a, b) => {
    const sevA = a.severity === 'error' ? 2 : a.severity === 'fault' ? 2 : 1
    const sevB = b.severity === 'error' ? 2 : b.severity === 'fault' ? 2 : 1
    return sevB - sevA
  })
})

const statusClass = computed(() => {
  const st = props.compartment?.status || 'normal'
  return `status-${st}`
})

/** Format ISO timestamp to readable short form. */
function formatTime(isoString) {
  if (!isoString) return ''
  try {
    const d = new Date(isoString)
    if (isNaN(d.getTime())) return isoString
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const hours = String(d.getHours()).padStart(2, '0')
    const minutes = String(d.getMinutes()).padStart(2, '0')
    return `${month}-${day} ${hours}:${minutes}`
  } catch (e) {
    return isoString
  }
}

function onClose() {
  emit('close')
}

/* ── Swipe-down-to-close gesture ── */
const touchStartY = ref(0)
const touchDeltaY = ref(0)

function onTouchStart(e) {
  touchStartY.value = e.touches[0].clientY
}

function onTouchMove(e) {
  touchDeltaY.value = e.touches[0].clientY - touchStartY.value
}

function onTouchEnd() {
  if (touchDeltaY.value > 60) {
    emit('close')
  }
  touchDeltaY.value = 0
}
</script>

<style scoped>
.drawer-root {
  position: fixed;
  inset: 0;
  z-index: 999;
}

.drawer-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
}

.drawer-panel {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  max-height: 65vh;
  min-height: 55vh;
  background: linear-gradient(180deg, rgba(6, 12, 28, 0.97), rgba(8, 16, 36, 0.95));
  border-top: 2rpx solid rgba(47, 244, 224, 0.35);
  box-shadow: 0 -8rpx 40rpx rgba(0, 0, 0, 0.5), 0 -2rpx 20rpx rgba(47, 244, 224, 0.15);
  display: flex;
  flex-direction: column;
  transform: translateY(100%);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  padding-bottom: env(safe-area-inset-bottom, 20rpx);
}

.drawer-open {
  transform: translateY(0);
}

/* ── Handle ── */
.drawer-handle {
  display: flex;
  justify-content: center;
  padding: 16rpx 0 10rpx;
}

.handle-bar {
  width: 60rpx;
  height: 8rpx;
  border-radius: 4rpx;
  background: rgba(47, 244, 224, 0.35);
}

/* ── Title ── */
.drawer-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10rpx 28rpx 16rpx;
  border-bottom: 1rpx solid rgba(47, 244, 224, 0.15);
}

.drawer-title-text {
  font-size: 30rpx;
  font-weight: 700;
  color: #f4fbff;
}

.drawer-title-status {
  font-size: 22rpx;
  padding: 4rpx 14rpx;
  border: 1rpx solid;
}

.status-normal { color: #27f5b5; border-color: rgba(39, 245, 181, 0.4); }
.status-warning { color: #ffd400; border-color: rgba(255, 212, 0, 0.4); }
.status-fault { color: #ff315d; border-color: rgba(255, 49, 93, 0.4); }
.status-idle { color: #6f8cad; border-color: rgba(111, 140, 173, 0.3); }

/* ── List ── */
.drawer-list {
  flex: 1;
  min-height: 0;
  padding: 0 22rpx;
}

.drawer-empty {
  padding: 60rpx 20rpx;
  text-align: center;
}

.drawer-empty text {
  font-size: 26rpx;
  color: #6f8cad;
}

/* ── List item ── */
.drawer-item {
  display: flex;
  margin-top: 16rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.10);
  background: rgba(7, 14, 31, 0.55);
  overflow: hidden;
}

.item-bar {
  width: 6rpx;
  flex-shrink: 0;
}

.item-fault .item-bar { background: #ff315d; }
.item-warning .item-bar { background: #ffd400; }

.item-content {
  flex: 1;
  padding: 16rpx 16rpx 14rpx;
  min-width: 0;
}

.item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.item-device {
  font-size: 26rpx;
  color: #eaf6ff;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
  margin-right: 12rpx;
}

.item-severity {
  font-size: 20rpx;
  padding: 3rpx 10rpx;
  border-radius: 4rpx;
  flex-shrink: 0;
}

.sev-fault {
  color: #fff;
  background: rgba(255, 49, 93, 0.6);
}

.sev-warning {
  color: #04121f;
  background: rgba(255, 212, 0, 0.7);
}

.item-type {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #6f8cad;
}

.item-message {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #9fb8d8;
  line-height: 1.4;
}

.item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10rpx;
}

.item-room {
  font-size: 20rpx;
  color: rgba(143, 217, 255, 0.5);
}

.item-time {
  font-size: 20rpx;
  color: rgba(143, 217, 255, 0.45);
}
</style>
