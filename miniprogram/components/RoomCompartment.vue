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
.room-compartment {
  position: relative;
  box-sizing: border-box;
  width: calc(50% - 7rpx);
  min-height: 180rpx;
  padding: 18rpx 16rpx;
  overflow: hidden;
  border: 1rpx solid rgba(47, 244, 224, 0.28);
  background:
    linear-gradient(135deg, rgba(14, 33, 54, 0.90), rgba(9, 17, 37, 0.86)),
    linear-gradient(180deg, rgba(47, 244, 224, 0.05), transparent);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

/* Single-room layout */
.room-single {
  width: 100%;
  min-height: 260rpx;
}

/* ── Clip-path shapes ── */
.room-shape-0 { clip-path: polygon(0 0, 92% 0, 100% 20%, 100% 100%, 0 100%); }
.room-shape-1 { clip-path: polygon(8% 0, 100% 0, 100% 100%, 0 100%, 0 20%); }
.room-shape-2 { clip-path: polygon(0 0, 100% 0, 100% 82%, 90% 100%, 0 100%); }
.room-shape-3 { clip-path: polygon(0 0, 100% 0, 100% 100%, 10% 100%, 0 82%); }

/* ── Status border colors ── */
.state-warning {
  border-color: rgba(255, 212, 0, 0.54);
}
.state-fault {
  border-color: rgba(255, 49, 93, 0.6);
}
.state-idle {
  border-color: rgba(47, 244, 224, 0.10);
  opacity: 0.55;
}

/* ── Decorative lines ── */
.room-lines {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.42;
}
.room-line-a {
  position: absolute;
  left: 14rpx;
  right: 14rpx;
  top: 60rpx;
  height: 1rpx;
  background: rgba(143, 217, 255, 0.18);
}
.room-line-b {
  position: absolute;
  top: 14rpx;
  bottom: 14rpx;
  left: 58%;
  width: 1rpx;
  background: rgba(143, 217, 255, 0.18);
}

/* ── Damage marks ── */
.room-damage {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-mark {
  position: absolute;
  width: 28rpx;
  height: 6rpx;
  background: #ffd400;
  box-shadow: 0 0 12rpx rgba(255, 212, 0, 0.8);
  animation: damageBlink 1.2s ease-in-out infinite;
}
.state-fault .damage-mark {
  background: #ff315d;
  box-shadow: 0 0 14rpx rgba(255, 49, 93, 0.85);
}
.dm1 { right: 18rpx; top: 22rpx; transform: rotate(24deg); }
.dm2 { left: 22rpx; bottom: 36rpx; transform: rotate(-30deg); animation-delay: 0.2s; }
.dm3 { right: 36rpx; bottom: 58rpx; width: 16rpx; transform: rotate(65deg); animation-delay: 0.5s; }

/* ── Header ── */
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
  font-size: 28rpx;
  color: #f3fbff;
  font-weight: 700;
  text-shadow: 0 0 8rpx rgba(47, 244, 224, 0.4);
}

.room-dot {
  width: 12rpx;
  height: 12rpx;
  margin-left: 10rpx;
  background: #5f7da6;
  transform: rotate(45deg);
  flex-shrink: 0;
}

.state-normal .room-dot { background: #27f5b5; box-shadow: 0 0 10rpx #27f5b5; }
.state-warning .room-dot { background: #ffd400; box-shadow: 0 0 10rpx #ffd400; }
.state-fault .room-dot { background: #ff315d; box-shadow: 0 0 10rpx #ff315d; }

/* ── Counts (NO running parameters) ── */
.room-counts {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin-top: 10rpx;
}

.count-tag {
  display: inline-flex;
  align-items: center;
  padding: 6rpx 12rpx;
  border: 1rpx solid;
  background: rgba(5, 12, 24, 0.62);
}

.count-tag text {
  font-size: 20rpx;
  font-weight: 700;
}

.count-fault {
  border-color: rgba(255, 49, 93, 0.5);
}
.count-fault text { color: #ff315d; }

.count-warning {
  border-color: rgba(255, 212, 0, 0.5);
}
.count-warning text { color: #ffd400; }

.count-condensation {
  border-color: rgba(255, 212, 0, 0.35);
}
.count-condensation text { color: #ffd400; font-weight: 400; }

/* Keyframe */
@keyframes damageBlink {
  0%, 100% { opacity: 0.48; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.12); }
}
</style>
