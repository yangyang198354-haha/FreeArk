<!--
  @module MOD-COMPONENT-LINECHART
  @description 基于 @qiun/ucharts 的折线图（mp-weixin canvas 2d 模式）。
    单系列折线，props: canvasId / categories(x轴标签) / data(数值数组) / name / unit / height。
    注：canvas 2d 需通过 SelectorQuery 取 node + dpr 缩放（uCharts 官方 mp-weixin 用法）。
    运行时渲染须在微信开发者工具/真机验证；构建仅保证可编译。
-->
<template>
  <view class="chart-wrap" :style="{ height: height + 'px' }">
    <canvas
      type="2d"
      :id="canvasId"
      :canvas-id="canvasId"
      class="chart-canvas"
      :style="{ width: '100%', height: height + 'px' }"
    />
    <view v-if="!hasData" class="chart-empty"><text>暂无数据</text></view>
  </view>
</template>

<script setup>
import { computed, getCurrentInstance, nextTick, onMounted, watch } from 'vue'
import uCharts from '@qiun/ucharts'

const props = defineProps({
  canvasId: { type: String, required: true },
  categories: { type: Array, default: () => [] },
  data: { type: Array, default: () => [] },
  name: { type: String, default: '' },
  unit: { type: String, default: '' },
  height: { type: Number, default: 240 },
})

const instance = getCurrentInstance()
let chart = null

const hasData = computed(() => Array.isArray(props.data) && props.data.length > 0)

function render() {
  if (!hasData.value) return
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
        categories: props.categories,
        series: [{ name: props.name || '数值', data: props.data }],
        animation: false,
        background: '#FFFFFF',
        color: ['#1a73e8'],
        padding: [12, 12, 0, 12],
        legend: { show: false },
        xAxis: { disableGrid: true, itemCount: 4, fontSize: 9, fontColor: '#999' },
        yAxis: {
          gridType: 'dash',
          dashLength: 2,
          fontColor: '#999',
          data: [{ unit: props.unit || '' }],
        },
        extra: {
          line: { type: 'curve', width: 2, activeType: 'none' },
        },
      })
    })
}

onMounted(() => nextTick(() => setTimeout(render, 60)))
watch(
  () => [props.categories, props.data],
  () => nextTick(() => setTimeout(render, 60)),
  { deep: true }
)
</script>

<style scoped>
.chart-wrap {
  position: relative;
  width: 100%;
}
.chart-canvas {
  width: 100%;
}
.chart-empty {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #bbb;
  font-size: 26rpx;
}
</style>
