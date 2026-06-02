<template>
  <div class="monthly-usage-container">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">能耗月用量报表</h2>
        <p class="ph-sub">查看和分析月度能耗数据</p>
      </div>
    </div>

    <!-- 查询条件表单 -->
    <el-card class="query-form-card">
      <el-form :model="queryForm" label-position="top" size="small">
        <el-row :gutter="20">
          <el-col :xs="24" :sm="24" :md="12" :lg="6">
            <el-form-item label="楼栋-单元-户号" prop="specificPart">
              <CascadingSelector
                building-input-id="monthlySelectedBuilding"
                unit-input-id="monthlySelectedUnit"
                room-input-id="monthlySelectedRoom"
                building-input-name="monthlySelectedBuilding"
                unit-input-name="monthlySelectedUnit"
                room-input-name="monthlySelectedRoom"
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
          <el-col :xs="24" :sm="24" :md="24" :lg="8">
            <el-form-item label="用量月度" prop="monthRange">
              <el-date-picker
                v-model="queryForm.monthRange"
                type="monthrange"
                range-separator="至"
                start-placeholder="开始月份"
                end-placeholder="结束月份"
                format="YYYY-MM"
                value-format="YYYY-MM"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="24" :lg="6" class="query-buttons" style="align-self: flex-end;">
            <el-button type="primary" @click="searchMonthlyUsageData" :loading="loading">查询</el-button>
            <el-button @click="resetQueryForm">重置</el-button>
            <el-button type="success" @click="saveAsXLSX">保存</el-button>
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
      <el-empty description="暂无数据" v-else-if="monthlyUsageData.length === 0" />
      <el-table v-else :data="monthlyUsageData" style="width: 100%" border stripe>
        <el-table-column prop="specific_part" label="专有部分" min-width="150" />
        <el-table-column prop="building" label="楼栋" min-width="80" />
        <el-table-column prop="unit" label="单元" min-width="80" />
        <el-table-column prop="room_number" label="房号" min-width="80" />
        <el-table-column prop="energy_mode" label="供能模式" min-width="100" />
        <el-table-column prop="initial_energy" label="初期能耗(kWh)" min-width="120" align="right" />
        <el-table-column prop="final_energy" label="末期能耗(kWh)" min-width="120" align="right" />
        <el-table-column prop="usage_quantity" label="使用量(kWh)" min-width="120" align="right" />
        <el-table-column prop="usage_month" label="用量月度" min-width="120" />
      </el-table>
      <div class="pagination-container" v-if="monthlyUsageData.length > 0">
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
  name: 'MonthlyUsageReportView',
  components: { CascadingSelector },
  data() {
    return {
      queryForm: { specificPart: '', energyMode: '', monthRange: [] },
      currentPage: 1,
      pageSize: 10,
      totalRecords: 0,
      monthlyUsageData: [],
      loading: false
    }
  },
  methods: {
    resetQueryForm() {
      this.queryForm.monthRange = []
      const input = document.querySelector('.cascading-selector-input')
      const clearBtn = document.querySelector('.cascading-clear-btn')
      if (input) input.value = ''
      if (clearBtn) clearBtn.style.display = 'none'
      document.getElementById('monthlySelectedBuilding').value = ''
      document.getElementById('monthlySelectedUnit').value = ''
      document.getElementById('monthlySelectedRoom').value = ''
      this.queryForm.energyMode = ''
      this.currentPage = 1
      this.monthlyUsageData = []
      this.totalRecords = 0
    },
    async searchMonthlyUsageData() {
      let specificPart = ''
      const building = document.getElementById('monthlySelectedBuilding').value
      const unit = document.getElementById('monthlySelectedUnit').value
      const room = document.getElementById('monthlySelectedRoom').value
      if (building && unit && room) {
        let floor = room.length === 4 ? room.substring(0, 2) : room.charAt(0)
        specificPart = `${building}-${unit}-${floor}-${room}`
      } else if (building && unit) { specificPart = building + '-' + unit } else if (building) { specificPart = building }
      const startTime = this.queryForm.monthRange[0], endTime = this.queryForm.monthRange[1]
      if (!startTime || !endTime) { this.$message.warning('请选择用量月度'); return }
      this.loading = true
      try {
        const params = { page: this.currentPage, page_size: this.pageSize, specific_part: specificPart || '', energy_mode: this.queryForm.energyMode || '', start_month: startTime, end_month: endTime }
        const response = await api.get('/api/usage/quantity/monthly/', params)
        if (response.success) { this.monthlyUsageData = response.data; this.totalRecords = response.total }
        else { this.monthlyUsageData = []; this.totalRecords = 0; this.$message.info('暂无数据') }
      } catch (error) { console.error('查询月度用量数据失败:', error); this.monthlyUsageData = []; this.totalRecords = 0; this.$message.error('查询失败，请稍后重试') }
      finally { this.loading = false }
    },
    async saveAsXLSX() {
      if (this.monthlyUsageData.length === 0) { this.$message.warning('暂无数据可导出'); return }
      try {
        const allData = await this.collectAllData()
        const exportData = allData.map(item => ({
          '专有部分': item.specific_part || '-', '楼栋': item.building || '-', '单元': item.unit || '-', '房号': item.room_number || '-',
          '供能模式': item.energy_mode || '-', '初期能耗(kWh)': item.initial_energy ?? '', '末期能耗(kWh)': item.final_energy ?? '',
          '使用量(kWh)': (item.initial_energy != null && item.final_energy != null) ? (item.final_energy - item.initial_energy) : '',
          '用量月度': item.usage_month || '-'
        }))
        this.exportToXLSX(exportData, '能耗月用量报表_' + new Date().toLocaleDateString('zh-CN') + '.xlsx')
      } catch (error) { console.error('导出数据失败:', error); this.$message.error('导出数据失败，请重试') }
    },
    async collectAllData() {
      let allData = [], page = 1, hasMore = true
      while (hasMore) {
        const building = document.getElementById('monthlySelectedBuilding').value
        const unit = document.getElementById('monthlySelectedUnit').value
        const room = document.getElementById('monthlySelectedRoom').value
        let specificPart = ''
        if (building && unit && room) {
          let floor = room.length === 4 ? room.substring(0, 2) : room.charAt(0)
          specificPart = `${building}-${unit}-${floor}-${room}`
        } else if (building && unit) { specificPart = building + '-' + unit } else if (building) { specificPart = building }
        const response = await api.get('/api/usage/quantity/monthly/', { page, page_size: 100, specific_part: specificPart || '', energy_mode: this.queryForm.energyMode || '', start_month: this.queryForm.monthRange[0], end_month: this.queryForm.monthRange[1] })
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
    handleSizeChange(size) { this.pageSize = parseInt(size); this.currentPage = 1; this.searchMonthlyUsageData() },
    handleCurrentChange(page) { this.currentPage = page; this.searchMonthlyUsageData() }
  }
}
</script>

<style scoped>
.monthly-usage-container { width: 100%; }

.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 24px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }

.query-form-card { margin-bottom: 20px; }
.data-table-card { margin-bottom: 20px; }
.query-buttons { display: flex; align-items: flex-end; gap: 8px; padding-top: 19px; margin-bottom: 5px; }
.pagination-container { margin-top: 20px; display: flex; justify-content: flex-end; }
</style>
