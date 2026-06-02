<template>
  <div class="daily-usage-container">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">能耗日用量报表</h2>
        <p class="ph-sub">查看和分析每日能耗数据</p>
      </div>
    </div>

    <!-- 查询条件表单 -->
    <el-card class="query-form-card">
      <el-form :model="queryForm" label-position="top" size="small">
        <el-row :gutter="20">
          <!-- 楼栋-单元-户号选择 -->
          <el-col :xs="24" :sm="24" :md="12" :lg="6">
            <el-form-item label="楼栋-单元-户号" prop="specificPart">
              <CascadingSelector
                building-input-id="dailySelectedBuilding"
                unit-input-id="dailySelectedUnit"
                room-input-id="dailySelectedRoom"
                building-input-name="dailySelectedBuilding"
                unit-input-name="dailySelectedUnit"
                room-input-name="dailySelectedRoom"
              />
            </el-form-item>
          </el-col>

          <!-- 供能模式 -->
          <el-col :xs="24" :sm="24" :md="12" :lg="4">
            <el-form-item label="供能模式" prop="energyMode">
              <el-select v-model="queryForm.energyMode" placeholder="全部" clearable>
                <el-option label="全部" value="" />
                <el-option label="制冷" value="制冷" />
                <el-option label="制热" value="制热" />
              </el-select>
            </el-form-item>
          </el-col>

          <!-- 时间段 -->
          <el-col :xs="24" :sm="24" :md="24" :lg="8">
            <el-form-item label="时间段" prop="dateRange">
              <el-date-picker
                v-model="queryForm.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                align="right"
                :shortcuts="dateShortcuts"
                :disabled-date="disabledDate"
                :max-span="365"
              />
            </el-form-item>
          </el-col>

          <!-- 查询按钮组 -->
          <el-col :xs="24" :sm="24" :md="24" :lg="6" class="query-buttons" style="align-self: flex-end;">
            <el-button type="primary" @click="searchUsageData" :loading="loading">查询</el-button>
            <el-button @click="resetQueryForm">重置</el-button>
            <el-button type="success" @click="saveAsXLSX">保存</el-button>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 用量数据图表 -->
    <el-card class="chart-card">
      <template #header>
        <span class="section-label" style="margin:0;">用量趋势图表</span>
      </template>
      <div class="chart-container">
        <el-skeleton :rows="3" animated v-if="loading" />
        <el-empty description="暂无数据" v-else-if="usageData.length === 0" />
        <canvas ref="usageChart" v-else></canvas>
      </div>
    </el-card>

    <!-- 用量数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <span class="section-label" style="margin:0;">用量数据</span>
      </template>
      <el-skeleton :rows="5" animated v-if="loading" />
      <el-empty description="暂无数据" v-else-if="usageData.length === 0" />
      <el-table v-else :data="usageData" style="width: 100%" border stripe>
        <el-table-column prop="specific_part" label="专有部分" min-width="150" />
        <el-table-column prop="building" label="楼栋" min-width="80" />
        <el-table-column prop="unit" label="单元" min-width="80" />
        <el-table-column prop="room_number" label="房号" min-width="80" />
        <el-table-column prop="energy_mode" label="供能模式" min-width="100" />
        <el-table-column prop="initial_energy" label="初期能耗(kWh)" min-width="120" align="right" />
        <el-table-column prop="final_energy" label="末期能耗(kWh)" min-width="120" align="right" />
        <el-table-column prop="usage_quantity" label="使用量(kWh)" min-width="120" align="right" />
        <el-table-column prop="time_period" label="时间段" min-width="150" />
      </el-table>
      <div class="pagination-container" v-if="usageData.length > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="totalRecords"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script>
import CascadingSelector from '@/components/CascadingSelector.vue'
import Chart from 'chart.js/auto'
import ChartDataLabels from 'chartjs-plugin-datalabels'
import api from '@/utils/api.js'
import * as XLSX from 'xlsx'

Chart.register(ChartDataLabels)

export default {
  name: 'DailyUsageReportView',
  components: { CascadingSelector },
  data() {
    return {
      queryForm: { specificPart: '', energyMode: '', dateRange: [] },
      dateShortcuts: [
        { text: '今天', value: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth(), n.getDate(), 0, 0, 0), n] } },
        { text: '昨天', value: () => { const n = new Date(); const y = new Date(n.getFullYear(), n.getMonth(), n.getDate() - 1); return [new Date(y.getFullYear(), y.getMonth(), y.getDate(), 0, 0, 0), new Date(y.getFullYear(), y.getMonth(), y.getDate(), 23, 59, 59)] } },
        { text: '近7天', value: () => { const n = new Date(); const s = new Date(n.getFullYear(), n.getMonth(), n.getDate() - 6); return [new Date(s.getFullYear(), s.getMonth(), s.getDate(), 0, 0, 0), n] } },
        { text: '近30天', value: () => { const n = new Date(); const s = new Date(n.getFullYear(), n.getMonth(), n.getDate() - 29); return [new Date(s.getFullYear(), s.getMonth(), s.getDate(), 0, 0, 0), n] } },
        { text: '本月', value: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth(), 1, 0, 0, 0), n] } },
        { text: '上月', value: () => { const n = new Date(); const f = new Date(n.getFullYear(), n.getMonth(), 1); const l = new Date(f.getTime() - 1); return [new Date(l.getFullYear(), l.getMonth(), 1, 0, 0, 0), new Date(l.getFullYear(), l.getMonth(), l.getDate(), 23, 59, 59)] } }
      ],
      currentPage: 1,
      pageSize: 20,
      totalRecords: 0,
      usageData: [],
      loading: false,
      chartInstance: null
    }
  },
  methods: {
    disabledDate(date) {
      return date < new Date(2020, 1, 1) || date > new Date()
    },
    resetQueryForm() {
      this.queryForm.dateRange = []
      const input = document.querySelector('.cascading-selector-input')
      const clearBtn = document.querySelector('.cascading-clear-btn')
      if (input) input.value = ''
      if (clearBtn) clearBtn.style.display = 'none'
      document.getElementById('dailySelectedBuilding').value = ''
      document.getElementById('dailySelectedUnit').value = ''
      document.getElementById('dailySelectedRoom').value = ''
      this.queryForm.energyMode = ''
      this.currentPage = 1
      this.usageData = []
      this.totalRecords = 0
      this.destroyChart()
    },
    async searchUsageData() {
      let specificPart = ''
      const building = document.getElementById('dailySelectedBuilding').value
      const unit = document.getElementById('dailySelectedUnit').value
      const room = document.getElementById('dailySelectedRoom').value
      if (building && unit && room) {
        let floor = room.length === 4 ? room.substring(0, 2) : room.charAt(0)
        specificPart = `${building}-${unit}-${floor}-${room}`
      } else if (building && unit) {
        specificPart = building + '-' + unit
      } else if (building) {
        specificPart = building
      }
      const energyMode = this.queryForm.energyMode
      let startTime = this.queryForm.dateRange[0]
      let endTime = this.queryForm.dateRange[1]
      if (!startTime || !endTime) { this.$message.warning('请选择时间段'); return }
      if (startTime instanceof Date) startTime = startTime.toISOString().split('T')[0]
      if (endTime instanceof Date) endTime = endTime.toISOString().split('T')[0]
      this.loading = true
      try {
        const params = { page: this.currentPage, page_size: this.pageSize, specific_part: specificPart || '', energy_mode: energyMode || '', start_time: startTime, end_time: endTime }
        const response = await api.get('/api/usage/quantity/', params)
        if (response.success) {
          this.usageData = response.data
          this.totalRecords = response.total
          this.updateChart()
        } else {
          this.usageData = []; this.totalRecords = 0; this.destroyChart(); this.$message.info('暂无数据')
        }
      } catch (error) {
        console.error('查询用量数据失败:', error)
        this.usageData = []; this.totalRecords = 0; this.destroyChart(); this.$message.error('查询失败，请稍后重试')
      } finally { this.loading = false }
    },
    async saveAsXLSX() {
      if (this.usageData.length === 0) { this.$message.warning('暂无数据可导出'); return }
      try {
        const allData = await this.collectAllData()
        const exportData = allData.map(item => ({
          '专有部分': item.specific_part || '-', '楼栋': item.building || '-', '单元': item.unit || '-', '房号': item.room_number || '-',
          '供能模式': item.energy_mode || '-',
          '初期能耗(kWh)': item.initial_energy ?? '',
          '末期能耗(kWh)': item.final_energy ?? '',
          '使用量(kWh)': (item.initial_energy != null && item.final_energy != null) ? (item.final_energy - item.initial_energy) : '',
          '时间段': item.time_period || '-'
        }))
        this.exportToXLSX(exportData, '能耗日用量报表_' + new Date().toLocaleDateString('zh-CN') + '.xlsx')
      } catch (error) { console.error('导出数据失败:', error); this.$message.error('导出数据失败，请重试') }
    },
    async collectAllData() {
      let allData = [], page = 1, hasMore = true
      while (hasMore) {
        const building = document.getElementById('dailySelectedBuilding')?.value || ''
        const unit = document.getElementById('dailySelectedUnit')?.value || ''
        const room = document.getElementById('dailySelectedRoom')?.value || ''
        let specificPart = ''
        if (building && unit && room) {
          let floor = room.length === 4 ? room.substring(0, 2) : room.charAt(0)
          specificPart = `${building}-${unit}-${floor}-${room}`
        } else if (building && unit) { specificPart = building + '-' + unit } else if (building) { specificPart = building }
        let startTime = this.queryForm.dateRange[0], endTime = this.queryForm.dateRange[1]
        if (startTime instanceof Date) startTime = startTime.toISOString().split('T')[0]
        if (endTime instanceof Date) endTime = endTime.toISOString().split('T')[0]
        const response = await api.get('/api/usage/quantity/', { page, page_size: 100, specific_part: specificPart || '', energy_mode: this.queryForm.energyMode || '', start_time: startTime, end_time: endTime })
        if (response.success && Array.isArray(response.data)) { allData = allData.concat(response.data); hasMore = response.data.length >= 100 ? (page++, true) : false } else { hasMore = false }
      }
      return allData
    },
    exportToXLSX(data, filename) {
      const wb = XLSX.utils.book_new()
      const ws = XLSX.utils.json_to_sheet(data)
      ws['!cols'] = [{ wch: 20 }, { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 12 }, { wch: 15 }, { wch: 15 }, { wch: 12 }, { wch: 15 }]
      XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')
      XLSX.writeFile(wb, filename)
    },
    async updateChart() {
      if (this.usageData.length === 0) { this.destroyChart(); return }
      this.destroyChart()
      await this.$nextTick()
      if (!this.$refs.usageChart) return
      const groupedData = {}, dates = new Set(), modes = new Set()
      const safeData = Array.isArray(this.usageData) ? this.usageData : []
      safeData.forEach(item => {
        if (item && item.time_period && item.energy_mode) {
          const date = item.time_period, mode = item.energy_mode
          const usage = item.usage_quantity != null ? parseFloat(item.usage_quantity) || 0 : 0
          dates.add(date); modes.add(mode)
          if (!groupedData[date]) groupedData[date] = {}
          groupedData[date][mode] = (groupedData[date][mode] || 0) + usage
        }
      })
      const sortedDates = Array.from(dates).sort()
      const modeColors = { '制冷': 'rgba(59,130,246,0.9)', '制热': 'rgba(248,113,113,0.9)' }
      const datasets = []
      modes.forEach(mode => {
        if (mode) {
          datasets.push({
            label: mode,
            data: sortedDates.map(d => groupedData[d]?.[mode] || 0),
            borderColor: modeColors[mode] || 'rgba(167,139,250,0.9)',
            backgroundColor: modeColors[mode] ? modeColors[mode].replace('0.9', '0.15') : 'rgba(167,139,250,0.15)',
            tension: 0.4, fill: false, pointRadius: 5, pointHoverRadius: 7,
            pointBackgroundColor: modeColors[mode] || 'rgba(167,139,250,0.9)',
            pointBorderColor: 'rgba(15,29,53,0.8)', pointBorderWidth: 2
          })
        }
      })
      try {
        const ctx = this.$refs.usageChart.getContext('2d')
        this.chartInstance = new Chart(ctx, {
          type: 'line',
          data: { labels: sortedDates, datasets },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
              title: { display: true, text: '不同供能模式下的每日使用量', color: 'rgba(199,212,234,0.9)', font: { size: 13 } },
              legend: { display: true, position: 'top', labels: { color: 'rgba(199,212,234,0.85)', padding: 15, usePointStyle: true, boxWidth: 6 } },
              tooltip: { mode: 'index', intersect: false, backgroundColor: 'rgba(10,20,36,0.95)', titleColor: 'rgba(199,212,234,0.9)', bodyColor: 'rgba(199,212,234,0.8)', borderColor: 'rgba(120,160,220,0.22)', borderWidth: 1, callbacks: { label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + ' kWh' } },
              datalabels: {
                display: ctx => ctx && ctx.parsed && ctx.parsed.y > 0,
                color: ctx => ctx && ctx.dataset && ctx.dataset.borderColor ? ctx.dataset.borderColor : 'rgba(199,212,234,0.8)',
                formatter: v => (v == null || isNaN(v)) ? '' : v.toFixed(2) + ' kWh',
                font: { weight: 'bold', size: 11 }, offset: 10, align: 'top'
              }
            },
            scales: {
              y: { beginAtZero: true, title: { display: true, text: '使用量 (kWh)', color: 'rgba(122,139,171,0.9)' }, ticks: { color: 'rgba(122,139,171,0.9)' }, grid: { color: 'rgba(120,160,220,0.1)' } },
              x: { title: { display: true, text: '日期', color: 'rgba(122,139,171,0.9)' }, ticks: { color: 'rgba(122,139,171,0.9)' }, grid: { color: 'rgba(120,160,220,0.08)' } }
            }
          }
        })
      } catch (error) { console.error('渲染图表失败:', error) }
    },
    destroyChart() { if (this.chartInstance) { this.chartInstance.destroy(); this.chartInstance = null } },
    handleSizeChange(size) { this.pageSize = parseInt(size); this.currentPage = 1; this.searchUsageData() },
    handleCurrentChange(page) { this.currentPage = page; this.searchUsageData() }
  },
  beforeUnmount() { this.destroyChart() }
}
</script>

<style scoped>
.daily-usage-container { width: 100%; }

.page-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 24px;
}
.ph-accent {
  width: 4px;
  height: 44px;
  border-radius: 2px;
  background: linear-gradient(180deg, var(--acc), var(--acc-2));
  flex-shrink: 0;
  margin-top: 2px;
}
.ph-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--ink-0);
  line-height: 1.3;
}
.ph-sub {
  margin: 4px 0 0 0;
  font-size: var(--font-size-sm);
  color: var(--ink-2);
}

.query-form-card { margin-bottom: 20px; }
.chart-card { margin-bottom: 20px; }
.data-table-card { margin-bottom: 20px; }

.query-buttons {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding-top: 19px;
  margin-bottom: 5px;
}

.chart-container { height: 300px; width: 100%; position: relative; }

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
