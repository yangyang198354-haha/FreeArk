<!--
  @module MOD-COMPONENT-RINGGAUGE
  @description HOLO-HUD 环形温度/滤网仪表盘（@qiun/ucharts arcbar，mp-weixin canvas 2d）。
    270° 缺口在底部的渐变描边圆弧（青 #7df9ff → 紫 #7c3aed，圆头），弧长编码 progress(0~100)。
    圆心叠加文字（topLabel / 大字读数+单位 / 可选 setpoint），由本组件以原生 view 渲染（arcbar 不画圆心文字）。
    青/紫主题随 alt 切换，对齐父卡 ci % 2 交替。运行时渲染须在微信开发者工具/真机验证；构建仅保证可编译。
-->
<template>
  <view class="ring-wrap">
    <view class="ring-canvas-box">
      <canvas
        type="2d"
        :id="canvasId"
        :canvas-id="canvasId"
        class="ring-canvas"
      />
      <!-- 圆心文字叠层（arcbar 不渲染圆心标题，故用原生 view 还原设计稿三行）-->
      <view class="ring-center">
        <text class="ring-top">{{ topLabel }}</text>
        <view class="ring-num-row">
          <text class="ring-num" :class="{ alt }">{{ numText }}</text>
          <text class="ring-unit">{{ unitText }}</text>
        </view>
        <text v-if="sub" class="ring-sub">{{ sub }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { getCurrentInstance, nextTick, onMounted, watch } from 'vue'
import uCharts from '@qiun/ucharts'

const props = defineProps({
  canvasId: { type: String, required: true },
  // 进度 0~100（由 paramPanels.metricOf 预计算的 progressPct 传入，弧长 = progress% × 270°）
  progress: { type: Number, default: 0 },
  numText: { type: String, default: '—' },
  unitText: { type: String, default: '' },
  topLabel: { type: String, default: '' },
  sub: { type: String, default: '' },          // 可选第三行（如「设定 26.0°C」），空则不渲染
  alt: { type: Boolean, default: false },       // 紫色主题（父卡交替）
})

const instance = getCurrentInstance()
let chart = null

function render() {
  const dpr = (uni.getSystemInfoSync().pixelRatio) || 2
  uni.createSelectorQuery()
    .in(instance.proxy)
    .select('#' + props.canvasId)
    .fields({ node: true, size: true })
    .exec((res) => {
      const info = res && res[0]
      if (!info || !info.node) return
      const canvas = info.node
      const ctx = canvas.getContext('2d')
      const w = info.width
      const h = info.height
      canvas.width = w * dpr
      canvas.height = h * dpr
      const frac = Math.min(Math.max(Number(props.progress) || 0, 0), 100) / 100
      chart = new uCharts({
        type: 'arcbar',
        context: ctx,
        canvas2d: true,
        pixelRatio: dpr,
        width: w * dpr,
        height: h * dpr,
        background: 'rgba(0,0,0,0)',
        animation: true,
        timing: 'easeOut',
        duration: 600,
        series: [{
          name: props.topLabel || 'value',
          data: frac,
          color: props.alt ? '#a855f7' : '#00e5ff',
        }],
        title: { name: '' },     // 圆心文字由模板叠层渲染，关闭内置标题
        subtitle: { name: '' },
        extra: {
          arcbar: {
            type: 'default',
            width: 8,                                   // 描边宽（×pix）→ 设计稿 stroke-width 8
            backgroundColor: props.alt ? 'rgba(124,58,237,0.15)' : 'rgba(0,229,255,0.12)',
            startAngle: 0.75,                           // 缺口在底部（270° 弧，cw）
            endAngle: 0.25,
            gap: 2,
            lineCap: 'round',
            linearType: 'custom',
            customColor: props.alt ? ['#c4a6ff', '#7c3aed'] : ['#7df9ff', '#7c3aed'],
          },
        },
      })
    })
}

onMounted(() => nextTick(() => setTimeout(render, 60)))
// 仅在进度/主题变化时重绘（避免每次 MQTT tick 无谓重建）
watch(() => [props.progress, props.alt], () => nextTick(() => setTimeout(render, 60)))
</script>

<style scoped>
.ring-wrap { display: flex; flex-direction: column; align-items: center; }
.ring-canvas-box { position: relative; width: 176rpx; height: 176rpx; }
.ring-canvas { width: 176rpx; height: 176rpx; }
.ring-center {
  position: absolute; left: 0; top: 0; right: 0; bottom: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  pointer-events: none;
}
.ring-top { font-size: 18rpx; color: #5f7da6; letter-spacing: 1rpx; }
.ring-num-row { display: flex; align-items: flex-end; }
.ring-num {
  font-family: 'Orbitron', 'Menlo', monospace; font-size: 44rpx; font-weight: 800;
  color: #eaf6ff; line-height: 1; text-shadow: 0 0 14rpx rgba(0, 229, 255, 0.5);
}
.ring-num.alt { text-shadow: 0 0 14rpx rgba(124, 58, 237, 0.5); }
.ring-unit { font-size: 18rpx; color: #5f7da6; margin-left: 2rpx; margin-bottom: 4rpx; }
.ring-sub { font-size: 18rpx; color: #27f5b5; margin-top: 4rpx; letter-spacing: 0.5rpx; white-space: nowrap; }
</style>
