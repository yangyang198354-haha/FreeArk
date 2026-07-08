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
  if (id === 'energy') return '能耗表'
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
/* ── Card base (HOLO-HUD style, matching 指挥 page) ─────── */
.subsystem-compartment {
  position: relative;
  min-height: 172rpx;
  padding: 20rpx 16rpx 16rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.18);
  background: linear-gradient(180deg, rgba(9, 22, 42, 0.88), rgba(6, 14, 30, 0.78));
  display: flex;
  align-items: center;
  gap: 16rpx;
  overflow: hidden;
}

/* HUD corner brackets */
.subsystem-compartment::before,
.subsystem-compartment::after {
  content: '';
  position: absolute;
  width: 18rpx;
  height: 18rpx;
  pointer-events: none;
  opacity: 0.35;
}
.subsystem-compartment::before {
  top: 6rpx;
  left: 6rpx;
  border-top: 1rpx solid rgba(47, 244, 224, 0.55);
  border-left: 1rpx solid rgba(47, 244, 224, 0.55);
}
.subsystem-compartment::after {
  bottom: 6rpx;
  right: 6rpx;
  border-bottom: 1rpx solid rgba(47, 244, 224, 0.55);
  border-right: 1rpx solid rgba(47, 244, 224, 0.55);
}

/* Status border glow */
.state-warning {
  border-color: rgba(255, 212, 0, 0.48);
  box-shadow: 0 0 18rpx rgba(255, 212, 0, 0.10);
}
.state-fault {
  border-color: rgba(255, 49, 93, 0.52);
  box-shadow: 0 0 22rpx rgba(255, 49, 93, 0.12);
  animation: faultGlow 1.4s ease-in-out infinite;
}
.state-idle {
  border-color: rgba(47, 244, 224, 0.08);
  opacity: 0.50;
}

@keyframes faultGlow {
  0%, 100% { box-shadow: 0 0 22rpx rgba(255, 49, 93, 0.12); }
  50% { box-shadow: 0 0 36rpx rgba(255, 49, 93, 0.22); }
}

/* ── Icons ─────────── */
.compartment-icon {
  position: relative;
  flex: 0 0 auto;
  width: 74rpx;
  height: 74rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Fan icon */
.icon-fan {
  width: 62rpx;
  height: 62rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.50);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fan-ring {
  position: relative;
  width: 42rpx;
  height: 42rpx;
  border-radius: 50%;
  animation: fanSpin 3.8s linear infinite;
}
.fan-blade {
  position: absolute;
  left: 18rpx;
  top: 3rpx;
  width: 6rpx;
  height: 18rpx;
  border-radius: 10rpx;
  background: rgba(47, 244, 224, 0.68);
  transform-origin: 3rpx 18rpx;
}
.fb2 { transform: rotate(120deg); }
.fb3 { transform: rotate(240deg); }

.state-fault .fan-blade { background: rgba(255, 49, 93, 0.68); }
.state-fault .icon-fan { border-color: rgba(255, 49, 93, 0.50); }

/* Energy icon */
.icon-energy {
  position: relative;
  width: 50rpx;
  height: 64rpx;
}
.energy-core {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 20rpx;
  height: 34rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.65);
  background: rgba(47, 244, 224, 0.12);
}
.energy-ring {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 46rpx;
  height: 46rpx;
  border: 1rpx dashed rgba(124, 58, 237, 0.40);
  border-radius: 50%;
}

/* Hydraulic icon */
.icon-hydraulic {
  position: relative;
  width: 64rpx;
  height: 48rpx;
}
.hydraulic-block {
  position: absolute;
  left: 8rpx;
  top: 6rpx;
  width: 48rpx;
  height: 36rpx;
  border: 2rpx solid rgba(47, 244, 224, 0.58);
  background: rgba(47, 244, 224, 0.06);
}
.hydraulic-pipe {
  position: absolute;
  background: rgba(47, 244, 224, 0.50);
}
.hp1 { left: 2rpx; top: 18rpx; width: 8rpx; height: 2rpx; }
.hp2 { right: 2rpx; top: 28rpx; width: 8rpx; height: 2rpx; }

/* Air icon */
.icon-air {
  position: relative;
  width: 56rpx;
  height: 56rpx;
}
.air-sensor {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 14rpx;
  height: 14rpx;
  background: rgba(47, 244, 224, 0.65);
  border-radius: 50%;
}
.air-wave {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  border: 1rpx solid rgba(47, 244, 224, 0.30);
  border-radius: 50%;
}
.aw1 { width: 32rpx; height: 32rpx; }
.aw2 { width: 50rpx; height: 50rpx; }

/* Damage sparks */
.damage-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-spark {
  position: absolute;
  width: 12rpx;
  height: 3rpx;
  background: #ff315d;
  animation: damageBlink 0.9s ease-in-out infinite;
}
.ds1 { right: 10rpx; top: 12rpx; transform: rotate(28deg); }
.ds2 { left: 10rpx; bottom: 14rpx; transform: rotate(-32deg); animation-delay: 0.3s; }

/* ── Info ─────────── */
.compartment-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.compartment-name {
  font-size: 24rpx;
  font-weight: 700;
  color: #cde7f7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compartment-count {
  font-size: 22rpx;
  font-weight: 700;
}

.state-warning .compartment-count { color: #ffd400; }
.state-fault .compartment-count { color: #ff315d; }

/* Keyframes */
@keyframes fanSpin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
@keyframes damageBlink {
  0%, 100% { opacity: 0.40; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.15); }
}
</style>
