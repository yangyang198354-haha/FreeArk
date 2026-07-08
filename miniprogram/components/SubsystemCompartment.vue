<!--
  @module MOD-BD-005
  @implements IFC-BD-005-01 through IFC-BD-005-06
  @depends none
  @description Renders a single subsystem compartment (fresh-air/energy/hydraulic/air-quality).
    Displays CSS-drawn icon, subsystem name, and fault/warning counts.
    Color-coded by status: normal=cyan, warning=yellow, fault=red+blink, idle=dim purple.
    Min touch area >= 44x44 logical pixels (REQ-NFUNC-004).
-->
<template>
  <view
    class="subsystem-compartment"
    :class="statusClass"
    @tap="onTap"
  >
    <!-- CSS-drawn icon -->
    <view class="compartment-icon">
      <!-- Fresh-air: circular fan -->
      <view v-if="iconKind === 'fan'" class="icon-fan">
        <view class="fan-ring">
          <view class="fan-blade fb1" />
          <view class="fan-blade fb2" />
          <view class="fan-blade fb3" />
        </view>
      </view>

      <!-- Energy: battery / energy core -->
      <view v-else-if="iconKind === 'energy'" class="icon-energy">
        <view class="energy-core" />
        <view class="energy-ring" />
      </view>

      <!-- Hydraulic: pump / module block -->
      <view v-else-if="iconKind === 'hydraulic'" class="icon-hydraulic">
        <view class="hydraulic-block" />
        <view class="hydraulic-pipe hp1" />
        <view class="hydraulic-pipe hp2" />
      </view>

      <!-- Air-quality: sensor / wave -->
      <view v-else class="icon-air">
        <view class="air-sensor" />
        <view class="air-wave aw1" />
        <view class="air-wave aw2" />
      </view>

      <!-- Damage spark overlay for warning/fault -->
      <view v-if="statusClass === 'state-fault'" class="damage-overlay">
        <view class="damage-spark ds1" />
        <view class="damage-spark ds2" />
      </view>
    </view>

    <!-- Name + count -->
    <view class="compartment-info">
      <text class="compartment-name">{{ displayName }}</text>
      <text v-if="statusText" class="compartment-count">{{ statusText }}</text>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

/**
 * IFC-BD-005-01: Subsystem state data { id, name, status, faultCount, warningCount, productCode }.
 * IFC-BD-005-02: Whether animations are paused.
 */
const props = defineProps({
  subsystem: {
    type: Object,
    required: true,
  },
  animationsPaused: { type: Boolean, default: false },
})

const emit = defineEmits(['open'])

/** IFC-BD-005-04: CSS status class. */
const statusClass = computed(() => `state-${props.subsystem.status || 'idle'}`)

/** IFC-BD-005-05: Display name for this subsystem type. */
const displayName = computed(() => {
  const id = props.subsystem.id
  if (id === 'fresh-air') return '新风模块'
  if (id === 'energy') return '能耗中枢'
  if (id === 'hydraulic') return '水力模块'
  if (id === 'air-quality') return '空气品质'
  return props.subsystem.name || id || '子系统'
})

/** IFC-BD-005-06: Icon type for this subsystem. */
const iconKind = computed(() => {
  const id = props.subsystem.id
  if (id === 'fresh-air') return 'fan'
  if (id === 'energy') return 'energy'
  if (id === 'hydraulic') return 'hydraulic'
  if (id === 'air-quality') return 'air'
  return 'fan'
})

/** Display text for fault/warning count. */
const statusText = computed(() => {
  const s = props.subsystem
  if (!s) return ''
  if (s.status === 'normal') return ''
  if (s.faultCount > 0) return `${s.faultCount} 故障`
  if (s.warningCount > 0) return `${s.warningCount} 预警`
  return ''
})

/** IFC-BD-005-03: Emit open event on tap. */
function onTap() {
  emit('open', props.subsystem)
}
</script>

<style scoped>
.subsystem-compartment {
  position: relative;
  flex: 1;
  min-width: 140rpx;
  min-height: 136rpx; /* >=44x44 logical px */
  padding: 14rpx 10rpx 10rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.22);
  background: linear-gradient(180deg, rgba(8, 20, 38, 0.82), rgba(6, 12, 28, 0.72));
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

/* Status border colors */
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

/* ── Icons ─────────── */
.compartment-icon {
  position: relative;
  width: 100%;
  height: 74rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Fan icon (fresh-air) */
.icon-fan {
  width: 64rpx;
  height: 64rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.55);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fan-ring {
  position: relative;
  width: 46rpx;
  height: 46rpx;
  border-radius: 50%;
  animation: fanSpin 3.8s linear infinite;
}
.fan-blade {
  position: absolute;
  left: 20rpx;
  top: 4rpx;
  width: 7rpx;
  height: 20rpx;
  border-radius: 10rpx;
  background: rgba(47, 244, 224, 0.72);
  transform-origin: 3rpx 19rpx;
}
.fb2 { transform: rotate(120deg); }
.fb3 { transform: rotate(240deg); }

/* Energy core icon */
.icon-energy {
  position: relative;
  width: 56rpx;
  height: 72rpx;
}
.energy-core {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 24rpx;
  height: 38rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.72);
  background: rgba(47, 244, 224, 0.15);
}
.energy-ring {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 50rpx;
  height: 50rpx;
  border: 1rpx dashed rgba(124, 58, 237, 0.45);
  border-radius: 50%;
}

/* Hydraulic module icon */
.icon-hydraulic {
  position: relative;
  width: 72rpx;
  height: 54rpx;
}
.hydraulic-block {
  position: absolute;
  left: 10rpx;
  top: 8rpx;
  width: 52rpx;
  height: 38rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.65);
  background: rgba(47, 244, 224, 0.08);
}
.hydraulic-pipe {
  position: absolute;
  background: rgba(47, 244, 224, 0.55);
}
.hp1 {
  left: 4rpx;
  top: 20rpx;
  width: 10rpx;
  height: 3rpx;
}
.hp2 {
  right: 4rpx;
  top: 30rpx;
  width: 10rpx;
  height: 3rpx;
}

/* Air quality sensor icon */
.icon-air {
  position: relative;
  width: 60rpx;
  height: 60rpx;
}
.air-sensor {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 16rpx;
  height: 16rpx;
  background: rgba(47, 244, 224, 0.7);
  border-radius: 50%;
}
.air-wave {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  border: 1rpx solid rgba(47, 244, 224, 0.35);
  border-radius: 50%;
}
.aw1 {
  width: 36rpx;
  height: 36rpx;
}
.aw2 {
  width: 54rpx;
  height: 54rpx;
}

/* Damage overlay */
.damage-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-spark {
  position: absolute;
  width: 14rpx;
  height: 4rpx;
  background: #ff315d;
  animation: damageBlink 1.1s ease-in-out infinite;
}
.ds1 { right: 12rpx; top: 14rpx; transform: rotate(28deg); }
.ds2 { left: 14rpx; bottom: 16rpx; transform: rotate(-32deg); animation-delay: 0.3s; }

/* ── Info ─────────── */
.compartment-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-top: 4rpx;
  padding: 0 4rpx;
  box-sizing: border-box;
}

.compartment-name {
  min-width: 0;
  font-size: 20rpx;
  color: #cde7f7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compartment-count {
  font-size: 20rpx;
  font-weight: 700;
  flex-shrink: 0;
  margin-left: 6rpx;
}

.state-warning .compartment-count { color: #ffd400; }
.state-fault .compartment-count { color: #ff315d; }

/* Color overrides for fault state */
.state-fault .fan-blade { background: rgba(255, 49, 93, 0.72); }
.state-fault .icon-fan { border-color: rgba(255, 49, 93, 0.55); }

/* Keyframes (reused from existing, defined here for component isolation) */
@keyframes fanSpin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
@keyframes damageBlink {
  0%, 100% { opacity: 0.48; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.12); }
}
</style>
