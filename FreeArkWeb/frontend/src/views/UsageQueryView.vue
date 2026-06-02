<template>
  <div class="usage-query-view">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">用量查询</h2>
        <p class="ph-sub">查询和统计能耗数据</p>
      </div>
    </div>

    <!-- 查询条件表单 -->
    <el-card class="query-form-card">
      <el-form :model="queryForm" label-position="top" size="small">
        <el-row :gutter="20">
          <el-col :xs="24" :sm="24" :md="12" :lg="6">
            <el-form-item label="楼栋-单元-户号" prop="specificPart">
              <CascadingSelector
                building-input-id="consumptionSelectedBuilding"
                unit-input-id="consumptionSelectedUnit"
                room-input-id="consumptionSelectedRoom"
                building-input-name="consumptionSelectedBuilding"
                unit-input-name="consumptionSelectedUnit"
                room-input-name="consumptionSelectedRoom"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="12" :lg="4">
            <el-form-item label="供能模式" prop="energyMode">
              <el-select v-model="queryForm.energyMode" placeholder="全部" clearable>
                <el-option label="全部" value="" />
                <el-option label="制冷" value="制冷" />
                <el-option label="制热" value="制热" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="24" :lg="8" style="align-self: flex-end;">
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
          <el-col :xs="24" :sm="24" :md="24" :lg="6" class="query-buttons" style="align-self: flex-end;">
            <el-button type="primary" @click="searchData" :loading="loading">查询</el-button>
            <el-button @click="resetForm">重置</el-button>
            <el-button type="success" @click="saveAsExcel">保存</el-button>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 用量数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <span class="section-label" style="margin:0;">用量数据</span>
      </template>
      <el-skeleton :rows="5" animated v-if="loading" />
      <el-empty description="暂无数据" v-else-if="consumptionData.length === 0" />
      <el-table v-else :data="consumptionData" style="width: 100%" border stripe>
        <el-table-column prop="specific_part" label="专有部分" min-width="150" />
        <el-table-column prop="building" label="楼栋" min-width="80" />
        <el-table-column prop="unit" label="单元" min-width="80" />
        <el-table-column prop="room_number" label="房号" min-width="80" />
        <el-table-column prop="energy_mode" label="供能模式" min-width="100" />
        <el-table-column prop="initial_energy" label="初期能耗(kWh)" min-width="120" align="right" />
        <el-table-column prop="final_energy" label="末期能耗(kWh)" min-width="120" align="right" />
        <el-table-column prop="usage_quantity" label="使用量(kWh)" min-width="120" align="right" />
        <el-table-column prop="time_period" label="用量月度" min-width="120" />
      </el-table>
      <div class="pagination-container" v-if="consumptionData.length > 0">
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
import api from '@/utils/api.js'
import * as XLSX from 'xlsx'

export default {
  name: 'UsageQueryView',
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
      pageSize: 10,
      totalRecords: 0,
      consumptionData: [],
      loading: false
    }
  },
  methods: {
    disabledDate(date) { return date < new Date(2020, 1, 1) || date > new Date() },
    resetForm() {
      this.queryForm.dateRange = []
      this.queryForm.energyMode = ''
      this.currentPage = 1
      this.consumptionData = []
      this.totalRecords = 0
      const b = document.getElementById('consumptionSelectedBuilding'), u = document.getElementById('consumptionSelectedUnit'), r = document.getElementById('consumptionSelectedRoom')
      if (b) b.value = ''; if (u) u.value = ''; if (r) r.value = ''
      const inp = document.querySelector('.cascading-selector-input'), clr = document.querySelector('.cascading-clear-btn')
      if (inp) inp.value = ''; if (clr) clr.style.display = 'none'
    },
    async searchData() {
      let specificPart = ''
      const building = document.getElementById('consumptionSelectedBuilding').value
      const unit = document.getElementById('consumptionSelectedUnit').value
      let room = document.getElementById('consumptionSelectedRoom').value
      if (room.includes('-')) { const p = room.split('-'); room = p[p.length - 1] }
      if (building && unit && room) {
        let floor = room.length === 4 ? room.substring(0, 2) : room.charAt(0)
        specificPart = `${building}-${unit}-${floor}-${room}`
      } else if (building && unit) { specificPart = building + '-' + unit } else if (building) { specificPart = building }
      let startTime = this.queryForm.dateRange[0], endTime = this.queryForm.dateRange[1]
      if (!startTime || !endTime) { this.$message.warning('请选择时间段'); return }
      if (startTime instanceof Date) startTime = startTime.toISOString().split('T')[0]
      if (endTime instanceof Date) endTime = endTime.toISOString().split('T')[0]
      this.loading = true
      try {
        const params = { page: this.currentPage, page_size: this.pageSize, specific_part: specificPart || '', energy_mode: this.queryForm.energyMode || '', start_time: startTime, end_time: endTime }
        const response = await api.get('/api/usage/quantity/specifictimeperiod', params)
        if (response.success && Array.isArray(response.data)) { this.consumptionData = response.data; this.totalRecords = response.total || 0 }
        else { this.consumptionData = []; this.totalRecords = 0; this.$message.info('暂无数据') }
      } catch (error) { console.error('查询能耗数据失败:', error); this.consumptionData = []; this.totalRecords = 0; this.$message.error('查询失败，请稍后重试') }
      finally { this.loading = false }
    },
    async saveAsExcel() {
      if (this.consumptionData.length === 0) { this.$message.warning('暂无数据可导出'); return }
      try {
        const allData = await this.collectAllData()
        const exportData = allData.map(item => ({
          '专有部分': item.specific_part || '-', '楼栋': item.building || '-', '单元': item.unit || '-', '房号': item.room_number || '-',
          '供能模式': item.energy_mode || '-', '初期能耗(kWh)': item.initial_energy ?? '', '末期能耗(kWh)': item.final_energy ?? '',
          '使用量(kWh)': (item.initial_energy != null && item.final_energy != null) ? (item.final_energy - item.initial_energy) : '',
          '时间段': item.time_period || '-'
        }))
        this.exportToXLSX(exportData, '能耗报表_' + new Date().toLocaleDateString('zh-CN') + '.xlsx')
      } catch (error) { console.error('导出数据失败:', error); this.$message.error('导出数据失败，请重试') }
    },
    async collectAllData() {
      let allData = [], page = 1, hasMore = true
      while (hasMore) {
        const building = document.getElementById('consumptionSelectedBuilding').value
        const unit = document.getElementById('consumptionSelectedUnit').value
        let room = document.getElementById('consumptionSelectedRoom').value
        if (room.includes('-')) { const p = room.split('-'); room = p[p.length - 1] }
        let specificPart = ''
        if (building && unit && room) {
          let floor = room.length === 4 ? room.substring(0, 2) : room.charAt(0)
          specificPart = `${building}-${unit}-${floor}-${room}`
        } else if (building && unit) { specificPart = building + '-' + unit } else if (building) { specificPart = building }
        let startTime = this.queryForm.dateRange[0], endTime = this.queryForm.dateRange[1]
        if (startTime instanceof Date) startTime = startTime.toISOString().split('T')[0]
        if (endTime instanceof Date) endTime = endTime.toISOString().split('T')[0]
        const response = await api.get('/api/usage/quantity/specifictimeperiod', { page, page_size: 100, specific_part: specificPart || '', energy_mode: this.queryForm.energyMode || '', start_time: startTime, end_time: endTime })
        if (response.success && Array.isArray(response.data)) { allData = allData.concat(response.data); hasMore = response.data.length >= 100 ? (page++, true) : false } else { hasMore = false }
      }
      return allData
    },
    exportToXLSX(data, filename) {
      const wb = XLSX.utils.book_new(); const ws = XLSX.utils.json_to_sheet(data)
      ws['!cols'] = [{ wch: 20 }, { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 12 }, { wch: 15 }, { wch: 15 }, { wch: 12 }, { wch: 15 }]
      XLSX.utils.book_append_sheet(wb, ws, 'Sheet1'); XLSX.writeFile(wb, filename)
    },
    handleSizeChange(size) { this.pageSize = size; this.currentPage = 1; this.searchData() },
    handleCurrentChange(page) { this.currentPage = page; this.searchData() }
  }
}
</script>

<style scoped>
.usage-query-view { width: 100%; }
.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 24px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
.query-form-card { margin-bottom: 20px; }
.data-table-card { margin-bottom: 20px; }
.query-buttons { display: flex; align-items: flex-end; gap: 8px; padding-top: 19px; margin-bottom: 5px; }
.pagination-container { margin-top: 20px; display: flex; justify-content: flex-end; padding-top: 15px; border-top: 1px solid var(--line); }
</style>
