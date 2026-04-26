<template>
  <div class="room-history-page">
    <div class="page-header">
      <div class="header-left">
        <h2>房间面板 历史数据</h2>
        <p class="subtitle">专有部分：{{ specificPart }}</p>
      </div>
      <el-button @click="goBack">
        <el-icon><Back /></el-icon>
        返回卡片面板
      </el-button>
    </div>

    <!-- 房间 Tab -->
    <el-tabs v-model="activeTab" @tab-change="handleTabChange" class="room-tabs">
      <el-tab-pane
        v-for="room in ROOM_TABS"
        :key="room.key"
        :label="room.label"
        :name="room.key"
      />
    </el-tabs>

    <!-- 过滤栏 -->
    <el-card class="filter-card">
      <el-form inline @submit.prevent="handleQuery">
        <el-form-item label="属性">
          <el-select
            v-model="selectedParams"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="请选择参数"
            style="width: 260px;"
          >
            <el-option
              v-for="p in currentRoomParams"
              :key="p.param"
              :label="p.label"
              :value="p.param"
              :disabled="selectedParams.length >= 4 && !selectedParams.includes(p.param)"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="时间">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="-"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 260px;"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleQuery" :loading="loading">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
          <el-button type="success" @click="handleExport" :disabled="!hasData">导出</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-skeleton v-if="loading" :rows="10" animated style="margin-top:16px;" />

    <el-empty
      v-else-if="queried && !hasData"
      description="所选时间段内暂无历史数据"
      style="margin-top:40px;"
    />

    <template v-else>
      <el-card
        v-for="param in selectedParams"
        :key="param"
        class="chart-card"
      >
        <template #header>
          <span class="chart-title">
            {{ getParamDef(param).label }}
            <span v-if="getParamDef(param).unit" class="chart-unit">（{{ getParamDef(param).unit }}）</span>
          </span>
        </template>
        <div
          :ref="(el) => setChartRef(param, el)"
          class="chart-box"
        />
      </el-card>
    </template>
  </div>
</template>

<script>
import { Back } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import * as XLSX from 'xlsx'
import api from '@/utils/api.js'

const ROOM_TABS = [
  {
    key: 'study_room',
    label: '书房',
    params: [
      { label: '开关',    param: 'study_room_switch',           unit: '',    isSwitch: true },
      { label: '湿度',    param: 'study_room_humidity',         unit: '%',   scale: 0.1 },
      { label: '温度',    param: 'study_room_temperature',      unit: '°C',  scale: 0.1 },
      { label: '系统开关', param: 'system_switch',              unit: '',    isSwitch: true },
      { label: '凝露提醒', param: 'study_room_dew_point_setting', unit: '°C', scale: 0.1 },
    ],
  },
  {
    key: 'bedroom',
    label: '次卧',
    params: [
      { label: '开关',    param: 'bedroom_switch',              unit: '',    isSwitch: true },
      { label: '湿度',    param: 'bedroom_humidity',            unit: '%',   scale: 0.1 },
      { label: '温度',    param: 'bedroom_temperature',         unit: '°C',  scale: 0.1 },
      { label: '系统开关', param: 'system_switch',              unit: '',    isSwitch: true },
      { label: '凝露提醒', param: 'bedroom_dew_point_setting',  unit: '°C',  scale: 0.1 },
    ],
  },
  {
    key: 'children_room',
    label: '主卧',
    params: [
      { label: '开关',    param: 'children_room_switch',        unit: '',    isSwitch: true },
      { label: '湿度',    param: 'children_room_humidity',      unit: '%',   scale: 0.1 },
      { label: '温度',    param: 'children_room_temperature',   unit: '°C',  scale: 0.1 },
      { label: '系统开关', param: 'system_switch',              unit: '',    isSwitch: true },
      { label: '凝露提醒', param: 'children_room_dew_point_setting', unit: '°C', scale: 0.1 },
    ],
  },
  {
    key: 'fourth_children_room',
    label: '儿童房',
    params: [
      { label: '开关',    param: 'fourth_children_room_switch',   unit: '',   isSwitch: true },
      { label: '湿度',    param: 'fourth_children_room_humidity', unit: '%',  scale: 0.1 },
      { label: '温度',    param: 'fourth_children_room_temperature', unit: '°C', scale: 0.1 },
      { label: '系统开关', param: 'system_switch',               unit: '',   isSwitch: true },
      { label: '凝露提醒', param: 'fourth_children_room_dew_point_setting', unit: '°C', scale: 0.1 },
    ],
  },
]

function defaultDateRange() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 6)
  const fmt = d => d.toISOString().slice(0, 10)
  return [fmt(start), fmt(end)]
}

export default {
  name: 'RoomHistoryView',
  components: { Back },

  data() {
    return {
      ROOM_TABS,
      activeTab: ROOM_TABS[0].key,
      loading: false,
      queried: false,
      selectedParams: [],
      dateRange: defaultDateRange(),
      chartData: {},
      chartDomMap: {},
      chartInstMap: {},
    }
  },

  computed: {
    specificPart() { return this.$route.query.specific_part || '' },
    currentRoomDef() {
      return ROOM_TABS.find(r => r.key === this.activeTab) || ROOM_TABS[0]
    },
    currentRoomParams() { return this.currentRoomDef.params },
    hasData() {
      return Object.values(this.chartData).some(arr => arr.length > 0)
    },
  },

  mounted() {
    this.resetParamSelection()
    this.handleQuery()
  },

  beforeUnmount() {
    this.destroyAllCharts()
  },

  methods: {
    resetParamSelection() {
      this.selectedParams = this.currentRoomParams.slice(0, 4).map(p => p.param)
    },

    handleTabChange() {
      this.destroyAllCharts()
      this.chartData = {}
      this.queried = false
      this.resetParamSelection()
      this.handleQuery()
    },

    setChartRef(param, el) {
      if (el) {
        this.chartDomMap[param] = el
      } else {
        delete this.chartDomMap[param]
        if (this.chartInstMap[param]) {
          this.chartInstMap[param].dispose()
          delete this.chartInstMap[param]
        }
      }
    },

    getParamDef(param) {
      return this.currentRoomParams.find(p => p.param === param) || { label: param, unit: '' }
    },

    async handleQuery() {
      if (!this.specificPart || !this.selectedParams.length || !this.dateRange?.length) return
      this.loading = true
      this.queried = false
      try {
        const resp = await api.get('/api/devices/param-history/', {
          specific_part: this.specificPart,
          param_names: this.selectedParams.join(','),
          start_time: `${this.dateRange[0]} 00:00:00`,
          end_time: `${this.dateRange[1]} 23:59:59`,
          chart: 'true',
        })
        if (resp && resp.success) {
          const grouped = {}
          for (const p of this.selectedParams) grouped[p] = []
          for (const row of (resp.results || [])) {
            if (grouped[row.param_name] !== undefined) grouped[row.param_name].push(row)
          }
          this.chartData = grouped
        } else {
          this.chartData = {}
        }
        this.queried = true
      } catch (e) {
        console.error('历史查询失败:', e)
        this.$message.error('获取历史数据失败')
        this.chartData = {}
        this.queried = true
      } finally {
        this.loading = false
        this.$nextTick(() => this.initAllCharts())
      }
    },

    handleReset() {
      this.resetParamSelection()
      this.dateRange = defaultDateRange()
      this.chartData = {}
      this.queried = false
      this.destroyAllCharts()
    },

    handleExport() {
      const header = ['时间', ...this.selectedParams.map(p => this.getParamDef(p).label)]
      const timeSet = new Set()
      for (const arr of Object.values(this.chartData))
        for (const r of arr) timeSet.add(r.collected_at)
      const times = [...timeSet].sort()

      const rows = [header]
      for (const t of times) {
        const row = [t]
        for (const param of this.selectedParams) {
          const rec = (this.chartData[param] || []).find(r => r.collected_at === t)
          if (!rec) { row.push(''); continue }
          const def = this.getParamDef(param)
          const v = Number(rec.value)
          if (def.isSwitch) row.push(v === 0 ? '关闭' : '开启')
          else if (def.scale) row.push(+(v * def.scale).toFixed(1))
          else row.push(v)
        }
        rows.push(row)
      }

      const ws = XLSX.utils.aoa_to_sheet(rows)
      const wb = XLSX.utils.book_new()
      XLSX.utils.book_append_sheet(wb, ws, '历史数据')
      XLSX.writeFile(wb, `${this.currentRoomDef.label}_${this.dateRange[0]}_${this.dateRange[1]}.xlsx`)
    },

    initAllCharts() {
      for (const param of this.selectedParams) {
        const dom = this.chartDomMap[param]
        if (!dom) continue
        if (!this.chartInstMap[param]) {
          this.chartInstMap[param] = echarts.init(dom)
        }
        const def = this.getParamDef(param)
        const raw = this.chartData[param] || []
        this.chartInstMap[param].setOption(this.buildOption(def, raw), true)
      }
    },

    destroyAllCharts() {
      for (const c of Object.values(this.chartInstMap)) c.dispose()
      this.chartInstMap = {}
      this.chartDomMap = {}
    },

    buildOption(def, rawData) {
      const seriesData = rawData.map(r => {
        const v = Number(r.value)
        const y = def.isSwitch ? v : (def.scale ? +(v * def.scale).toFixed(2) : v)
        return [r.collected_at, y]
      })

      const yAxis = def.isSwitch
        ? { type: 'value', min: 0, max: 1, interval: 1,
            axisLabel: { formatter: v => v === 0 ? '关闭' : '开启' } }
        : { type: 'value',
            axisLabel: { formatter: v => v + (def.unit ? ' ' + def.unit : '') } }

      return {
        grid: { left: 72, right: 24, top: 20, bottom: 60 },
        xAxis: {
          type: 'time',
          axisLabel: {
            formatter: { day: '{MM}-{dd}', hour: '{MM}-{dd} {HH}:{mm}', minute: '{HH}:{mm}' },
          },
        },
        yAxis,
        series: [{
          type: 'line',
          data: seriesData,
          smooth: !def.isSwitch,
          step: def.isSwitch ? 'end' : false,
          symbol: 'circle',
          symbolSize: 5,
          showSymbol: false,
          lineStyle: { color: '#00b4a6', width: 2 },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(0,180,166,0.28)' },
                { offset: 1, color: 'rgba(0,180,166,0)' },
              ],
            },
          },
        }],
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'cross', crossStyle: { color: '#999' } },
          formatter: params => {
            if (!params.length) return ''
            const p = params[0]
            const t = typeof p.axisValue === 'number'
              ? new Date(p.axisValue).toLocaleString('zh-CN', { hour12: false })
              : p.axisValue
            const v = p.value[1]
            const vStr = def.isSwitch
              ? (v === 0 ? '关闭' : '开启')
              : v.toFixed(def.scale ? 1 : 0) + (def.unit ? ' ' + def.unit : '')
            return `${t}<br/>${def.label}: <b>${vStr}</b>`
          },
        },
        dataZoom: [
          { type: 'inside', xAxisIndex: 0 },
          { type: 'slider', xAxisIndex: 0, bottom: 5, height: 18, borderColor: 'transparent' },
        ],
      }
    },

    goBack() {
      this.$router.push({ name: 'DeviceCards', query: { specific_part: this.specificPart } })
    },
  },
}
</script>

<style scoped>
.room-history-page {
  width: 100%;
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
  box-sizing: border-box;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e4e7ed;
}

.page-header h2 {
  margin: 0;
  color: #303133;
  font-size: 22px;
  font-weight: 600;
}

.subtitle {
  margin: 6px 0 0;
  color: #909399;
  font-size: 13px;
}

.room-tabs { margin-bottom: 8px; }

.filter-card { margin-bottom: 16px; }

.chart-card { margin-bottom: 16px; }

.chart-title { font-weight: 500; font-size: 15px; }

.chart-unit { color: #909399; font-size: 13px; }

.chart-box { height: 260px; width: 100%; }
</style>
