<!--
  @module MOD-BD-004
  @implements IFC-BD-004-01, IFC-BD-004-02, IFC-BD-004-03
  @depends none
  @description Ship hull container for the bridge dashboard.
    Renders the clip-path polygon ship silhouette with deep-space background,
    80rpx grid overlay, and HUD scan line. Border color changes with overall status.
    Contains all inner compartments via default slot.
-->
<template>
  <view class="ship-shell" :class="statusClass">
    <!-- Background layers -->
    <view class="hull-bg-base" />
    <view class="hull-bg-grid" />

    <!-- HUD scan line -->
    <view v-if="!animationsPaused" class="hull-scan" />

    <!-- Ship nose (FREEARK nameplate) -->
    <view class="ship-nose">
      <view class="nose-plate" />
      <text>FREEARK</text>
    </view>

    <!-- Inner compartments (slot) -->
    <slot />

    <!-- Ship tail (engine glow) -->
    <view class="ship-tail">
      <view class="tail-engine te1" />
      <view class="tail-engine te2" />
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

/**
 * IFC-BD-004-01: Overall ship status controlling border color.
 * IFC-BD-004-02: Whether animations are paused.
 */
const props = defineProps({
  status: { type: String, default: 'syncing' },
  animationsPaused: { type: Boolean, default: false },
})

const statusClass = computed(() => `state-${props.status}`)
</script>

<style scoped>
.ship-shell {
  position: relative;
  overflow: hidden;
  padding: 24rpx 22rpx 0;
  border: 1rpx solid rgba(47, 244, 224, 0.26);
  background:
    linear-gradient(135deg, rgba(13, 31, 50, 0.92), rgba(18, 16, 45, 0.88)),
    linear-gradient(180deg, rgba(47, 244, 224, 0.08), transparent 34%);
  clip-path: polygon(50% 0, 94% 7%, 100% 49%, 91% 95%, 50% 100%, 9% 95%, 0 49%, 6% 7%);
  box-shadow: inset 0 0 44rpx rgba(47, 244, 224, 0.12), 0 0 28rpx rgba(0, 0, 0, 0.35);
}

/* Status-based border colors */
.ship-shell.state-warning {
  border-color: rgba(255, 212, 0, 0.42);
  box-shadow: inset 0 0 44rpx rgba(255, 212, 0, 0.10), 0 0 28rpx rgba(0, 0, 0, 0.35);
}
.ship-shell.state-fault {
  border-color: rgba(255, 49, 93, 0.48);
  box-shadow: inset 0 0 50rpx rgba(255, 49, 93, 0.12), 0 0 32rpx rgba(0, 0, 0, 0.4);
}

/* Background layers (absolute, behind content) */
.hull-bg-base,
.hull-bg-grid,
.hull-scan {
  position: absolute;
  pointer-events: none;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
}

.hull-bg-base {
  background:
    radial-gradient(ellipse at 50% 30%, rgba(47, 244, 224, 0.04), transparent 60%),
    radial-gradient(ellipse at 80% 80%, rgba(124, 58, 237, 0.06), transparent 50%);
}

.hull-bg-grid {
  background-image:
    linear-gradient(rgba(56, 230, 224, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 230, 224, 0.04) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 85%);
  mask-image: linear-gradient(180deg, #000, transparent 85%);
}

/* HUD scan line */
.hull-scan {
  left: 0;
  right: 0;
  top: 0;
  bottom: auto;
  height: 180rpx;
  z-index: 1;
  background: linear-gradient(180deg, transparent, rgba(47, 244, 224, 0.07), transparent);
  animation: ownerScan 5s linear infinite;
}

@keyframes ownerScan {
  0% { transform: translateY(-180rpx); }
  100% { transform: translateY(1200rpx); }
}

/* Ship nose */
.ship-nose,
.ship-tail {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 2;
}

.ship-nose {
  height: 58rpx;
}

.ship-nose text {
  position: relative;
  z-index: 2;
  font-size: 22rpx;
  color: rgba(244, 251, 255, 0.82);
  font-weight: 700;
}

.nose-plate {
  position: absolute;
  width: 220rpx;
  height: 42rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.35);
  background: rgba(47, 244, 224, 0.06);
  clip-path: polygon(18% 0, 82% 0, 100% 100%, 0 100%);
}

/* Ship tail engines */
.ship-tail {
  height: 58rpx;
  gap: 46rpx;
}

.tail-engine {
  width: 84rpx;
  height: 18rpx;
  background: linear-gradient(90deg, transparent, rgba(47, 244, 224, 0.78), transparent);
  animation: enginePulse 1.8s ease-in-out infinite;
}

.te2 { animation-delay: 0.45s; }

@keyframes enginePulse {
  0%, 100% { box-shadow: 0 0 14rpx rgba(47, 244, 224, 0.45); }
  50% { box-shadow: 0 0 30rpx rgba(47, 244, 224, 0.85); }
}
</style>
