<!--
  @module MOD-BD-006
  @implements IFC-BD-006-01 through IFC-BD-006-04
  @depends none
  @description Renders a single room compartment with holographic name label and fault/warning counts.
    v1.13.0: 1:1 还原 cyberpunk-smart-home 参考设计。
    使用四角 bracket + diamond 指示器 + SVG data-URI 房间图标 + per-room 霓虹配色。
    Min touch area >= 44x44 logical pixels (REQ-NFUNC-004).
-->
<template>
  <view
    class="room-compartment"
    :class="[statusClass, colorClass, { 'room-single': singleRoom }]"
    :style="{ animationDelay: animDelay }"
    @tap="onTap"
  >
    <!-- 四角 bracket 装饰（参考 cyber-bracket-full） -->
    <view class="br-tl" />
    <view class="br-tr" />
    <view class="br-bl" />
    <view class="br-br" />

    <!-- 右上角 diamond 指示器（参考设计） -->
    <text class="room-diamond">&#9670;</text>

    <!-- SVG data-URI 房间图标 -->
    <view class="room-icon" :class="iconClass" />

    <!-- 房间名 -->
    <text class="room-name">{{ room.name }}</text>

    <!-- 故障/预警/结露标签 -->
    <view v-if="hasTags" class="room-counts">
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

    <!-- 故障伤害标记 -->
    <view v-if="statusClass === 'state-fault'" class="room-damage">
      <view class="damage-mark dm1" />
      <view class="damage-mark dm2" />
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  room: { type: Object, required: true },
  animationsPaused: { type: Boolean, default: false },
  shapeIndex: { type: Number, default: 0 },
  singleRoom: { type: Boolean, default: false },
})

const emit = defineEmits(['open'])

const statusClass = computed(() => `state-${props.room.status || 'idle'}`)

/** Per-room index → neon color (0=cyan, 1=purple, 2=green, 3=orange). */
const colorClass = computed(() => {
  const idx = props.shapeIndex % 4
  const colors = ['color-cyan', 'color-purple', 'color-green', 'color-orange']
  return colors[idx]
})

/** Staggered animation delay. */
const animDelay = computed(() => `${0.6 + props.shapeIndex * 0.1}s`)

/** Room icon class (maps to data-URI). */
const iconClass = computed(() => {
  const idx = props.shapeIndex % 4
  const icons = ['ico-master', 'ico-study', 'ico-kids', 'ico-guest']
  return icons[idx]
})

const hasTags = computed(() =>
  props.room.faultCount > 0 || props.room.warningCount > 0 || props.room.hasCondensation
)

function onTap() {
  emit('open', props.room)
}
</script>

<style scoped>
/* ── Card base（参考设计 2x2 房间状态卡片）──────────────── */
.room-compartment {
  position: relative;
  box-sizing: border-box;
  min-height: 144rpx;
  padding: 28rpx 20rpx 20rpx;
  overflow: hidden;
  border: 1px solid rgba(0, 240, 255, 0.15);
  background: #111128;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
  border-radius: 4px;
  opacity: 0;
  animation: cardSlideIn 0.5s ease-out forwards;
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

.room-single {
  min-height: 200rpx;
  grid-column: 1 / -1;
}

/* ── 四角 bracket 装饰 ── */
.br-tl, .br-tr, .br-bl, .br-br {
  position: absolute;
  width: 22rpx;
  height: 22rpx;
  pointer-events: none;
  opacity: 0.35;
  border-style: solid;
  border-color: var(--room-color, rgba(0, 240, 255, 0.55));
}
.br-tl { top: -1px; left: -1px; border-width: 2px 0 0 2px; }
.br-tr { top: -1px; right: -1px; border-width: 2px 2px 0 0; }
.br-bl { bottom: -1px; left: -1px; border-width: 0 0 2px 2px; }
.br-br { bottom: -1px; right: -1px; border-width: 0 2px 2px 0; }

/* Per-room 霓虹色 */
.color-cyan  { --room-color: #00f0ff; --room-glow: rgba(0, 240, 255, 0.15); border-color: rgba(0, 240, 255, 0.20); }
.color-purple { --room-color: #b026ff; --room-glow: rgba(176, 38, 255, 0.15); border-color: rgba(176, 38, 255, 0.20); }
.color-green  { --room-color: #39ff14; --room-glow: rgba(57, 255, 20, 0.15); border-color: rgba(57, 255, 20, 0.20); }
.color-orange { --room-color: #ff6a00; --room-glow: rgba(255, 106, 0, 0.15); border-color: rgba(255, 106, 0, 0.20); }

/* ── Diamond 指示器（右上角，呼吸动画）── */
.room-diamond {
  position: absolute;
  top: 10rpx;
  right: 10rpx;
  font-size: 16rpx;
  line-height: 1;
  color: var(--room-color, #00f0ff);
  animation: glowBreathe 2s ease-in-out infinite;
}

/* ── SVG data-URI 房间图标（16x16 viewBox）──── */
.room-icon {
  width: 32rpx;
  height: 32rpx;
  background-repeat: no-repeat;
  background-position: center;
  background-size: 32rpx 32rpx;
  flex-shrink: 0;
}

/* 主卧 / 次卧：房子图标 */
.ico-master, .ico-guest {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'/%3E%3Cpolyline points='9 22 9 12 15 12 15 22'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 4rpx rgba(0, 240, 255, 0.4));
}
.color-cyan .ico-master,
.color-cyan .ico-guest {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'/%3E%3Cpolyline points='9 22 9 12 15 12 15 22'/%3E%3C/svg%3E");
}
.color-orange .ico-master,
.color-orange .ico-guest {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ff6a00' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'/%3E%3Cpolyline points='9 22 9 12 15 12 15 22'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 4rpx rgba(255, 106, 0, 0.4));
}

/* 书房：书本图标 */
.ico-study {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23b026ff' stroke-width='1.5' stroke-linecap='round'%3E%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 4rpx rgba(176, 38, 255, 0.4));
}

/* 儿童房：笑脸图标 */
.ico-kids {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2339ff14' stroke-width='1.5' stroke-linecap='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cpath d='M8 14s1.5 2 4 2 4-2 4-2'/%3E%3Cline x1='9' y1='9' x2='9.01' y2='9'/%3E%3Cline x1='15' y1='9' x2='15.01' y2='9'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 4rpx rgba(57, 255, 20, 0.4));
}

/* ── 房间名 ── */
.room-name {
  font-size: 26rpx;
  font-weight: 600;
  color: #e0e0ff;
}

/* ── 状态覆盖 ── */
.state-warning {
  border-color: rgba(240, 225, 48, 0.44);
  box-shadow: 0 0 20rpx rgba(240, 225, 48, 0.08);
}
.state-fault {
  border-color: rgba(255, 45, 123, 0.48);
  box-shadow: 0 0 24rpx rgba(255, 45, 123, 0.10);
  animation: roomFaultGlow 1.5s ease-in-out infinite;
}
.state-idle {
  border-color: rgba(0, 240, 255, 0.07);
  opacity: 0.48;
}

@keyframes roomFaultGlow {
  0%, 100% { box-shadow: 0 0 24rpx rgba(255, 45, 123, 0.10); }
  50% { box-shadow: 0 0 40rpx rgba(255, 45, 123, 0.20); }
}

/* ── 故障伤害标记 ── */
.room-damage {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-mark {
  position: absolute;
  width: 22rpx;
  height: 4rpx;
  background: #ff2d7b;
  box-shadow: 0 0 12rpx rgba(255, 45, 123, 0.80);
  animation: damageBlink 1.0s ease-in-out infinite;
}
.dm1 { right: 14rpx; top: 40rpx; transform: rotate(24deg); }
.dm2 { left: 18rpx; bottom: 22rpx; transform: rotate(-30deg); animation-delay: 0.2s; }

/* ── 标签 ── */
.room-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 6rpx;
  justify-content: center;
}

.count-tag {
  display: inline-flex;
  align-items: center;
  padding: 4rpx 10rpx;
  border: 1px solid;
  background: rgba(5, 12, 24, 0.58);
  border-radius: 2px;
}

.count-tag text {
  font-size: 18rpx;
  font-weight: 700;
}

.count-fault { border-color: rgba(255, 45, 123, 0.45); }
.count-fault text { color: #ff2d7b; }

.count-warning { border-color: rgba(240, 225, 48, 0.45); }
.count-warning text { color: #f0e130; }

.count-condensation { border-color: rgba(240, 225, 48, 0.30); }
.count-condensation text { color: #f0e130; font-weight: 400; }

/* ── Keyframes ── */
@keyframes cardSlideIn {
  from { opacity: 0; transform: translateY(16rpx) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes glowBreathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@keyframes damageBlink {
  0%, 100% { opacity: 0.40; }
  50% { opacity: 1; }
}
</style>
