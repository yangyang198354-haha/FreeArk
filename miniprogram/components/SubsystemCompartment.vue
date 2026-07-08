<!--
  @module MOD-BD-005
  @implements IFC-BD-005-01 through IFC-BD-005-06
  @depends none
  @description Renders a single subsystem compartment (fresh-air/energy/hydraulic/air-quality).
    v1.13.0: 1:1 还原 cyberpunk-smart-home 参考设计。
    使用 SVG data-URI 背景图标 + 四角 bracket 装饰 + per-module 霓虹配色。
    Min touch area >= 44x44 logical pixels (REQ-NFUNC-004).
-->
<template>
  <view
    class="subsystem-compartment"
    :class="[statusClass, colorClass]"
    :style="{ animationDelay: animDelay }"
    @tap="onTap"
  >
    <!-- 四角 bracket 装饰（参考 cyber-bracket-full） -->
    <view class="br-tl" />
    <view class="br-tr" />
    <view class="br-bl" />
    <view class="br-br" />

    <!-- SVG data-URI 图标 -->
    <view class="compartment-icon" :class="iconClass" />

    <!-- 名称 + 状态标签 -->
    <view class="compartment-info">
      <text class="compartment-name">{{ displayName }}</text>
      <text v-if="statusLabel" class="compartment-status">{{ statusLabel }}</text>
    </view>

    <!-- 故障火花覆盖层 -->
    <view v-if="statusClass === 'state-fault'" class="damage-overlay">
      <view class="damage-spark ds1" />
      <view class="damage-spark ds2" />
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  subsystem: { type: Object, required: true },
  animationsPaused: { type: Boolean, default: false },
  /** Stagger index for cardSlideIn animation (0-3). */
  index: { type: Number, default: 0 },
})

const emit = defineEmits(['open'])

const statusClass = computed(() => `state-${props.subsystem.status || 'idle'}`)

/** Per-module neon color class. */
const colorClass = computed(() => {
  const id = props.subsystem.id
  if (id === 'fresh-air') return 'color-cyan'
  if (id === 'energy') return 'color-orange'
  if (id === 'hydraulic') return 'color-purple'
  if (id === 'air-quality') return 'color-green'
  if (id === 'main-thermostat') return 'color-cyan'
  return 'color-cyan'
})

/** Staggered animation delay. */
const animDelay = computed(() => `${props.index * 0.1}s`)

/** SVG icon class (maps to data-URI). */
const iconClass = computed(() => {
  const id = props.subsystem.id
  if (id === 'fresh-air') return 'ico-fan'
  if (id === 'energy') return 'ico-energy'
  if (id === 'hydraulic') return 'ico-hydraulic'
  if (id === 'air-quality') return 'ico-air'
  if (id === 'main-thermostat') return 'ico-thermostat'
  return 'ico-fan'
})

const displayName = computed(() => {
  const id = props.subsystem.id
  if (id === 'fresh-air') return '新风模块'
  if (id === 'energy') return '能耗表'
  if (id === 'hydraulic') return '水力模块'
  if (id === 'air-quality') return '空气品质'
  if (id === 'main-thermostat') return '主温控'
  return props.subsystem.name || id || '子系统'
})

/** Mono status label. */
const statusLabel = computed(() => {
  const s = props.subsystem
  if (!s) return ''
  const st = s.status
  if (st === 'normal') {
    const id = s.id
    if (id === 'fresh-air') return 'ACTIVE'
    if (id === 'energy') return 'NORMAL'
    if (id === 'hydraulic') return 'ONLINE'
    if (id === 'air-quality') return 'GOOD'
    if (id === 'main-thermostat') return 'ONLINE'
    return 'OK'
  }
  if (st === 'fault') return s.faultCount > 0 ? `${s.faultCount} FAULT` : 'FAULT'
  if (st === 'warning') return s.warningCount > 0 ? `${s.warningCount} WARN` : 'WARN'
  return 'IDLE'
})

function onTap() {
  emit('open', props.subsystem)
}
</script>

<style scoped>
/* ── Card base（参考设计 2x2 模块网格卡片）──────────────── */
.subsystem-compartment {
  position: relative;
  min-height: 172rpx;
  padding: 28rpx 20rpx 20rpx;
  border: 1px solid rgba(0, 240, 255, 0.15);
  background: #111128;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14rpx;
  overflow: hidden;
  border-radius: 4px;
  opacity: 0;
  animation: cardSlideIn 0.5s ease-out forwards;
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

/* ── 四角 bracket 装饰 ── */
.br-tl, .br-tr, .br-bl, .br-br {
  position: absolute;
  width: 22rpx;
  height: 22rpx;
  pointer-events: none;
  opacity: 0.35;
  border-style: solid;
  border-color: var(--corner-color, rgba(0, 240, 255, 0.55));
}
.br-tl { top: -1px; left: -1px; border-width: 2px 0 0 2px; }
.br-tr { top: -1px; right: -1px; border-width: 2px 2px 0 0; }
.br-bl { bottom: -1px; left: -1px; border-width: 0 0 2px 2px; }
.br-br { bottom: -1px; right: -1px; border-width: 0 2px 2px 0; }

/* Per-module 霓虹色（--corner-color + 边框） */
.color-cyan { --corner-color: rgba(0, 240, 255, 0.55); border-color: rgba(0, 240, 255, 0.30); }
.color-purple { --corner-color: rgba(176, 38, 255, 0.50); border-color: rgba(176, 38, 255, 0.25); }
.color-green { --corner-color: rgba(57, 255, 20, 0.50); border-color: rgba(57, 255, 20, 0.25); }
.color-orange { --corner-color: rgba(255, 106, 0, 0.50); border-color: rgba(255, 106, 0, 0.25); }

/* ── 状态覆盖 ── */
.state-warning {
  border-color: rgba(240, 225, 48, 0.40);
  box-shadow: 0 0 20rpx rgba(240, 225, 48, 0.08);
}
.state-fault {
  border-color: rgba(255, 45, 123, 0.45);
  box-shadow: 0 0 24rpx rgba(255, 45, 123, 0.10);
  animation: faultGlow 1.4s ease-in-out infinite;
}
.state-idle {
  border-color: rgba(0, 240, 255, 0.08);
  opacity: 0.50;
}

@keyframes faultGlow {
  0%, 100% { box-shadow: 0 0 24rpx rgba(255, 45, 123, 0.10); }
  50% { box-shadow: 0 0 40rpx rgba(255, 45, 123, 0.22); }
}

/* Hover/active: 白色光泽扫过 + 边框增强 */
.subsystem-compartment::after {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 60%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.03), transparent);
  pointer-events: none;
}

/* ── SVG data-URI 图标（36x36 viewBox，参考设计匹配）──── */
.compartment-icon {
  width: 72rpx;
  height: 72rpx;
  background-repeat: no-repeat;
  background-position: center;
  background-size: 72rpx 72rpx;
  flex-shrink: 0;
}

/* 新风（CYAN）：圆形 + 十字线 */
.ico-fan {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round'%3E%3Ccircle cx='16' cy='16' r='10'/%3E%3Ccircle cx='16' cy='16' r='3'/%3E%3Cline x1='16' y1='6' x2='16' y2='13'/%3E%3Cline x1='16' y1='19' x2='16' y2='26'/%3E%3Cline x1='6' y1='16' x2='13' y2='16'/%3E%3Cline x1='19' y1='16' x2='26' y2='16'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(0, 240, 255, 0.5));
  animation: iconSpin 12s linear infinite;
}

/* 水力（PURPLE）：水滴 + 竖线 */
.ico-hydraulic {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%23b026ff' stroke-width='1.5' stroke-linecap='round'%3E%3Cpath d='M16 4 C16 4 10 12 10 18 C10 24 16 28 16 28 C16 28 22 24 22 18 C22 12 16 4 16 4Z'/%3E%3Cline x1='16' y1='10' x2='16' y2='26'/%3E%3Cpath d='M12 16 Q16 20 20 16'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(176, 38, 255, 0.5));
}

/* 空气品质（GREEN）：同心圆 + 十字 */
.ico-air {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%2339ff14' stroke-width='1.5' stroke-linecap='round'%3E%3Ccircle cx='16' cy='16' r='10'/%3E%3Ccircle cx='16' cy='16' r='6'/%3E%3Cline x1='16' y1='10' x2='16' y2='22'/%3E%3Cline x1='10' y1='16' x2='22' y2='16'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(57, 255, 20, 0.5));
}

/* 能耗（ORANGE）：星形 */
.ico-energy {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%23ff6a00' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='16,4 20,14 26,14 21,20 23,28 16,23 9,28 11,20 6,14 12,14'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(255, 106, 0, 0.5));
}

/* 主温控（CYAN）：温度计 + 圆环 */
.ico-thermostat {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%2300f0ff' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='16' cy='16' r='10'/%3E%3Cline x1='16' y1='8' x2='16' y2='16'/%3E%3Ccircle cx='16' cy='22' r='2' fill='%2300f0ff'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(0, 240, 255, 0.5));
}

/* 状态故障时图标颜色变红 */
.state-fault .ico-fan {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%23ff2d7b' stroke-width='1.5' stroke-linecap='round'%3E%3Ccircle cx='16' cy='16' r='10'/%3E%3Ccircle cx='16' cy='16' r='3'/%3E%3Cline x1='16' y1='6' x2='16' y2='13'/%3E%3Cline x1='16' y1='19' x2='16' y2='26'/%3E%3Cline x1='6' y1='16' x2='13' y2='16'/%3E%3Cline x1='19' y1='16' x2='26' y2='16'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(255, 45, 123, 0.5));
}
.state-fault .ico-hydraulic {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%23ff2d7b' stroke-width='1.5' stroke-linecap='round'%3E%3Cpath d='M16 4 C16 4 10 12 10 18 C10 24 16 28 16 28 C16 28 22 24 22 18 C22 12 16 4 16 4Z'/%3E%3Cline x1='16' y1='10' x2='16' y2='26'/%3E%3Cpath d='M12 16 Q16 20 20 16'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(255, 45, 123, 0.5));
}
.state-fault .ico-air {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%23ff2d7b' stroke-width='1.5' stroke-linecap='round'%3E%3Ccircle cx='16' cy='16' r='10'/%3E%3Ccircle cx='16' cy='16' r='6'/%3E%3Cline x1='16' y1='10' x2='16' y2='22'/%3E%3Cline x1='10' y1='16' x2='22' y2='16'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(255, 45, 123, 0.5));
}
.state-fault .ico-energy {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%23ff2d7b' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='16,4 20,14 26,14 21,20 23,28 16,23 9,28 11,20 6,14 12,14'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(255, 45, 123, 0.5));
}
.state-fault .ico-thermostat {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' fill='none' stroke='%23ff2d7b' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='16' cy='16' r='10'/%3E%3Cline x1='16' y1='8' x2='16' y2='16'/%3E%3Ccircle cx='16' cy='22' r='2' fill='%23ff2d7b'/%3E%3C/svg%3E");
  filter: drop-shadow(0 0 10rpx rgba(255, 45, 123, 0.5));
}

/* ── 信息区 ── */
.compartment-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4rpx;
}

.compartment-name {
  font-size: 24rpx;
  font-weight: 600;
  color: #e0e0ff;
}

.compartment-status {
  font-family: 'Courier New', 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 18rpx;
  letter-spacing: 2rpx;
}

.color-cyan .compartment-status { color: #00f0ff; }
.color-purple .compartment-status { color: #b026ff; }
.color-green .compartment-status { color: #39ff14; }
.color-orange .compartment-status { color: #ff6a00; }

.state-fault .compartment-status { color: #ff2d7b; }
.state-warning .compartment-status { color: #f0e130; }
.state-idle .compartment-status { color: #555577; }

/* ── 故障火花覆盖层 ── */
.damage-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.damage-spark {
  position: absolute;
  width: 12rpx;
  height: 3rpx;
  background: #ff2d7b;
  box-shadow: 0 0 10rpx rgba(255, 45, 123, 0.7);
  animation: damageBlink 0.9s ease-in-out infinite;
}
.ds1 { right: 10rpx; top: 12rpx; transform: rotate(28deg); }
.ds2 { left: 10rpx; bottom: 14rpx; transform: rotate(-32deg); animation-delay: 0.3s; }

/* ── Keyframes ── */
@keyframes cardSlideIn {
  from { opacity: 0; transform: translateY(16rpx) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes iconSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes damageBlink {
  0%, 100% { opacity: 0.40; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.15); }
}
</style>
