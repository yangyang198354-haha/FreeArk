<!--
  @module MOD-BD-006
  @implements IFC-BD-006-01 through IFC-BD-006-04
  @depends none
  @description Renders a single room compartment with holographic name label and fault/warning counts.
    Color-coded by the room's aggregate fault status. Does NOT display running parameters
    (temperature, humidity, kWh, CO2, etc.) per REQ-FUNC-010.
    Min touch area >= 44x44 logical pixels (REQ-NFUNC-004).
    Uses 4 clip-path variants (shapeIndex 0-3) for visual variety.
-->
<template>
  <view
    class="room-compartment"
    :class="[statusClass, shapeClass, { 'room-single': singleRoom }]"
    @tap="onTap"
  >
    <!-- Decorative panel lines -->
    <view class="room-lines">
      <view class="room-line-a" />
      <view class="room-line-b" />
    </view>

    <!-- Damage marks for warning/fault -->
    <view v-if="statusClass !== 'state-normal' && statusClass !== 'state-idle'" class="room-damage">
      <view class="damage-mark dm1" />
      <view class="damage-mark dm2" />
      <view class="damage-mark dm3" />
    </view>

    <!-- Room header: name + status dot -->
    <view class="room-header">
      <text class="room-name">{{ room.name }}</text>
      <view class="room-dot" />
    </view>

    <!-- Fault/warning counts (NO running params) -->
    <view class="room-counts">
      <view v-if="room.faultCount > 0" class="count-tag count-fault">
        <text>{{ room.faultCount }} 故障</text>
      </view>
      <view v-if="room.warningCount > 0" class="count-tag count-warning">
        <text>{{ room.warningCount }} 预警</text>
      </view>
      <view v-if="room.hasCondensation" class="count-tag count-condensation">
        <text>结露</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

/**
 * IFC-BD-006-01: Room state { id, name, status, faultCount, warningCount, hasCondensation }.
 * IFC-BD-006-02: Whether animations are paused.
 * IFC-BD-006-03: Clip-path shape index (0-3).
 */
const props = defineProps({
  room: { type: Object, required: true },
  animationsPaused: { type: Boolean, default: false },
  shapeIndex: { type: Number, default: 0 },
  /** When true, render at 100% width (only room in the grid). */
  singleRoom: { type: Boolean, default: false },
})

const emit = defineEmits(['open'])

const statusClass = computed(() => `state-${props.room.status || 'idle'}`)
const shapeClass = computed(() => `room-shape-${props.shapeIndex % 4}`)

function onTap() {
  emit('open', props.room)
}
</script>

<style scoped>
/* ── Card base (HOLO-HUD room card) ──────────────────────── */
.room-compartment {
  position: relative;
  box-sizing: border-box;
  min-height: 180rpx;
  padding: 18rpx 16rpx;
  overflow: hidden;
  border: 1rpx solid rgba(47, 244, 224, 0.20);
  background: linear-gradient(180deg, rgba(9, 22, 42, 0.88), rgba(6, 14, 30, 0.78));
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.room-single {
  min-height: 240rpx;
}

/* HUD corner brackets */
.room-compartment::before,
.room-compartment::after {
  content: '';
  position: absolute;
  width: 14rpx;
  height: 14rpx;
  pointer-events: none;
  opacity: 0.30;
}
.room-compartment::before {
  top: 4rpx;
  left: 4rpx;
  border-top: 1rpx solid rgba(47, 244, 224, 0.45);
  border-left: 1rpx solid rgba(47, 244, 224, 0.45);
}
.room-compartment::after {
  bottom: 4rpx;
  right: 4rpx;
  border-bottom: 1rpx solid rgba(47, 244, 224, 0.45);
  border-right: 1rpx solid rgba(47, 244, 224, 0.45);
}

/* Status variations */
.state-warning {
  border-color: rgba(255, 212, 0, 0.44);
  box-shadow: 0 0 16rpx rgba(255, 212, 0, 0.08);
}
.state-fault {
  border-color: rgba(255, 49, 93, 0.48);
  box-shadow: 0 0 20rpx rgba(255, 49, 93, 0.10);
  animation: roomFaultGlow 1.5s ease-in-out infinite;
}
.state-idle {
  border-color: rgba(47, 244, 224, 0.07);
  opacity: 0.48;
}

@keyframes roomFaultGlow {
  0%, 100% { box-shadow: 0 0 20rpx rgba(255, 49, 93, 0.10); }
  50% { box-shadow: 0 0 34rpx rgba(255, 49, 93, 0.20); }
}

/* Decorative lines */
.room-lines {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.30;
}
.room-line-a {
  position: absolute;
  left: 10rpx;
  right: 10rpx;
  top: 54rpx;
  height: 1rpx;
  background: rgba(143, 217, 255, 0.14);
}
.room-line-b {
  position: absolute;
  top: 10rpx;
  bottom: 10rpx;
  left: 55%;
  width: 1rpx;
  background: rgba(143, 217, 255, 0.14);
}

/* Damage marks */
.room-damage {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-mark {
  position: absolute;
  width: 22rpx;
  height: 4rpx;
  background: #ffd400;
  box-shadow: 0 0 10rpx rgba(255, 212, 0, 0.75);
  animation: damageBlink 1.0s ease-in-out infinite;
}
.state-fault .damage-mark {
  background: #ff315d;
  box-shadow: 0 0 12rpx rgba(255, 49, 93, 0.80);
}
.dm1 { right: 14rpx; top: 18rpx; transform: rotate(24deg); }
.dm2 { left: 18rpx; bottom: 30rpx; transform: rotate(-30deg); animation-delay: 0.2s; }
.dm3 { right: 30rpx; bottom: 50rpx; width: 12rpx; transform: rotate(65deg); animation-delay: 0.5s; }

/* Header */
.room-header {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.room-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 26rpx;
  color: #f3fbff;
  font-weight: 700;
  text-shadow: 0 0 8rpx rgba(47, 244, 224, 0.35);
}

.room-dot {
  width: 10rpx;
  height: 10rpx;
  margin-left: 8rpx;
  background: #5f7da6;
  transform: rotate(45deg);
  flex-shrink: 0;
}

.state-normal .room-dot { background: #27f5b5; box-shadow: 0 0 8rpx #27f5b5; }
.state-warning .room-dot { background: #ffd400; box-shadow: 0 0 8rpx #ffd400; }
.state-fault .room-dot { background: #ff315d; box-shadow: 0 0 8rpx #ff315d; }

/* Counts */
.room-counts {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 6rpx;
  margin-top: 8rpx;
}

.count-tag {
  display: inline-flex;
  align-items: center;
  padding: 4rpx 10rpx;
  border: 1rpx solid;
  background: rgba(5, 12, 24, 0.58);
}

.count-tag text {
  font-size: 18rpx;
  font-weight: 700;
}

.count-fault {
  border-color: rgba(255, 49, 93, 0.45);
}
.count-fault text { color: #ff315d; }

.count-warning {
  border-color: rgba(255, 212, 0, 0.45);
}
.count-warning text { color: #ffd400; }

.count-condensation {
  border-color: rgba(255, 212, 0, 0.30);
}
.count-condensation text { color: #ffd400; font-weight: 400; }

/* Keyframes */
@keyframes damageBlink {
  0%, 100% { opacity: 0.40; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.15); }
}
</style>
