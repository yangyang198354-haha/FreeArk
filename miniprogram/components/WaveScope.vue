<!--
  @module MOD-COMPONENT-WAVESCOPE
  @description HOLO-HUD 运行波形示波器（@qiun/ucharts line，mp-weixin canvas 2d）。
    主机卡顶部的横向滚动青色波形：细线、无点、半透明，深色底（rgba(4,10,24,.6)）。
    维护定长滚动缓冲（随机游走，营造「运行中」氛围），定时 updateData 追加新点 → 视觉左移滚动。
    非数据图表，纯运行态装饰；不参与任何写链路。运行时渲染须在微信开发者工具/真机验证。
-->
<template>
  <view class="wave-box" :style="{ height: heightRpx }">
    <canvas
      type="2d"
      :id="canvasId"
      :canvas-id="canvasId"
      class="wave-canvas"
    />
  </view>
</template>

<script setup>
import { getCurrentInstance, nextTick, onMounted, onUnmounted } from 'vue'
import uCharts from '@qiun/ucharts'

const props = defineProps({
  canvasId: { type: String, required: true },
  color: { type: String, default: '#00e5ff' },
  points: { type: Number, default: 28 },     // 缓冲点数
  intervalMs: { type: Number, default: 800 }, // 追加节奏
  height: { type: Number, default: 38 },      // px（设计稿 38px）
})

const heightRpx = (props.height * 2) + 'rpx'   // px → rpx（750/375）

const instance = getCurrentInstance()
let chart = null
let timer = null
let buf = []
let last = 22

// 随机游走：在 8~30 区间小步漂移，形成温和起伏的运行波形
function nextVal() {
  last += (Math.random() - 0.5) * 8
  if (last < 8) last = 8
  if (last > 30) last = 30
  return Math.round(last * 10) / 10
}

function seed() {
  buf = []
  for (let i = 0; i < props.points; i++) buf.push(nextVal())
}

function cats() {
  // 空标签占位（x 轴隐藏，仅需长度对齐）
  return buf.map(() => '')
}

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
      chart = new uCharts({
        type: 'line',
        context: ctx,
        canvas2d: true,
        pixelRatio: dpr,
        width: w * dpr,
        height: h * dpr,
        categories: cats(),
        series: [{ name: 'wave', data: buf.slice() }],
        background: 'rgba(0,0,0,0)',
        color: [props.color],
        animation: false,
        padding: [6, 2, 0, 2],
        dataPointShape: false,        // 无数据点
        dataLabel: false,
        enableScroll: false,
        legend: { show: false },
        xAxis: { disabled: true, disableGrid: true, axisLine: false },
        yAxis: { disabled: true, disableGrid: true, showTitle: false, min: 0, max: 38 },
        extra: { line: { type: 'curve', width: 1.4, activeType: 'none' } },
      })
      tick()
    })
}

function tick() {
  if (timer) clearInterval(timer)
  timer = setInterval(() => {
    if (!chart) return
    buf.push(nextVal())
    if (buf.length > props.points) buf.shift()
    chart.updateData({ categories: cats(), series: [{ name: 'wave', data: buf.slice() }] })
  }, props.intervalMs)
}

onMounted(() => {
  seed()
  nextTick(() => setTimeout(render, 60))
})
onUnmounted(() => {
  if (timer) { clearInterval(timer); timer = null }
})
</script>

<style scoped>
.wave-box {
  margin: 20rpx 0 8rpx; border-radius: 20rpx; overflow: hidden;
  background: rgba(4, 10, 24, 0.6); border: 1rpx solid rgba(0, 229, 255, 0.12);
}
.wave-canvas { width: 100%; height: 100%; }
</style>
