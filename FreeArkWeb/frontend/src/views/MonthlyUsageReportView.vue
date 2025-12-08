<template>
  <div class="monthly-usage-container">
    <div class="page-header">
      <h2>能耗月用量报表</h2>
      <p class="page-subtitle">查看和分析月度能耗数据</p>
    </div>
    
    <!-- 查询条件表单 -->
    <el-card class="query-form-card">
      <el-form :model="queryForm" label-position="top" size="small">
        <el-row :gutter="20">
          <!-- 楼栋-单元-户号选择 -->
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
          
          <!-- 供能模式 -->
          <el-col :xs="24" :sm="24" :md="12" :lg="4">
            <el-form-item label="供能模式" prop="energyMode">
              <el-select
                v-model="queryForm.energyMode"
                placeholder="全部"
                clearable
              >
                <el-option label="全部" value="" />
                <el-option label="制冷" value="制冷" />
                <el-option label="制热" value="制热" />
              </el-select>
            </el-form-item>
          </el-col>
          
          <!-- 用量月度 -->
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
                :picker-options="{
                  ranges: {
                    '本月': [new Date(new Date().getFullYear(), new Date().getMonth(), 1), new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0)],
                    '上月': [new Date(new Date().getFullYear(), new Date().getMonth() - 1, 1), new Date(new Date().getFullYear(), new Date().getMonth(), 0)],
                    '近3个月': [new Date(new Date().getFullYear(), new Date().getMonth() - 2, 1), new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0)],
                    '近6个月': [new Date(new Date().getFullYear(), new Date().getMonth() - 5, 1), new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0)],
                    '本年': [new Date(new Date().getFullYear(), 0, 1), new Date(new Date().getFullYear(), 11, 31)],
                    '去年': [new Date(new Date().getFullYear() - 1, 0, 1), new Date(new Date().getFullYear() - 1, 11, 31)]
                  },
                  maxSpan: { months: 12 },
                  minDate: new Date(2020, 0, 1),
                  maxDate: new Date(new Date().getFullYear() + 1, 0, 1)
                }"
              />
            </el-form-item>
          </el-col>
          
          <!-- 查询按钮组 -->
          <el-col :xs="24" :sm="24" :md="24" :lg="6" class="query-buttons" style="align-self: flex-end;">
            <el-button type="primary" @click="searchMonthlyUsageData" :loading="loading" style="margin-right: 15px;">
              查询
            </el-button>
            <el-button @click="resetQueryForm" style="margin-right: 15px;">
              重置
            </el-button>
            <el-button type="success" @click="saveAsXLSX">
              保存
            </el-button>
          </el-col>
        </el-row>
      </el-form>
    </el-card>
    
    <!-- 用量数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div class="card-header">
          <span>用量数据</span>
        </div>
      </template>
      
      <!-- 加载指示器 -->
      <el-skeleton :rows="5" animated v-if="loading" />
      
      <!-- 无数据提示 -->
      <el-empty description="暂无数据" v-else-if="monthlyUsageData.length === 0" />
      
      <!-- 数据表格 -->
      <el-table
        v-else
        :data="monthlyUsageData"
        style="width: 100%"
        border
        stripe
        :header-cell-style="{ backgroundColor: '#f5f7fa' }"
      >
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
      
      <!-- 分页控件 -->
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
  components: {
    CascadingSelector
  },
  data() {
    return {
      // 查询表单数据
      queryForm: {
        specificPart: '',
        energyMode: '',
        monthRange: []
      },
      // 分页数据
      currentPage: 1,
      pageSize: 10,
      totalRecords: 0,
      // 数据列表
      monthlyUsageData: [],
      // 加载状态
      loading: false
    }
  },
  methods: {
    // 重置查询表单
    resetQueryForm() {
      // 重置日期范围
      this.queryForm.monthRange = []
      
      // 重置楼栋-单元-户号选择
      const input = document.querySelector('.cascading-selector-input')
      const clearBtn = document.querySelector('.cascading-clear-btn')
      if (input) {
        input.value = ''
      }
      if (clearBtn) {
        clearBtn.style.display = 'none'
      }
      document.getElementById('monthlySelectedBuilding').value = ''
      document.getElementById('monthlySelectedUnit').value = ''
      document.getElementById('monthlySelectedRoom').value = ''
      
      // 重置供能模式选择
      this.queryForm.energyMode = ''
      
      // 重置分页和数据
      this.currentPage = 1
      this.monthlyUsageData = []
      this.totalRecords = 0
    },
    
    // 查询月度用量数据
    async searchMonthlyUsageData() {
      // 构建查询条件
      let specificPart = ''
      const building = document.getElementById('monthlySelectedBuilding').value
      const unit = document.getElementById('monthlySelectedUnit').value
      const room = document.getElementById('monthlySelectedRoom').value
      
      if (building && unit && room) {
        // 根据房号长度提取楼层号：3位数取第一位，4位数取前两位
        let floor = ''
        if (room.length === 3) {
          floor = room.charAt(0)  // 3位数房号，如302，取第一位作为楼层号
        } else if (room.length === 4) {
          floor = room.substring(0, 2)  // 4位数房号，如1002、3305，取前两位作为楼层号
        } else {
          floor = room.charAt(0)  // 其他情况默认取第一位
        }
        // 构建4部分格式：楼栋-单元-楼层-房号
        specificPart = `${building}-${unit}-${floor}-${room}`
      } else if (building && unit) {
        specificPart = building + '-' + unit
      } else if (building) {
        specificPart = building
      }
      
      const energyMode = this.queryForm.energyMode
      const startTime = this.queryForm.monthRange[0]
      const endTime = this.queryForm.monthRange[1]
      
      // 表单验证
      if (!startTime || !endTime) {
        this.$message.warning('请选择用量月度')
        return
      }
      
      this.loading = true
      try {
        // 构建查询参数
        const params = {
          page: this.currentPage,
          page_size: this.pageSize,
          specific_part: specificPart || '',
          energy_mode: energyMode || '',
          start_time: startTime,
          end_time: endTime
        }
        
        // 调用API获取数据
        const response = await api.get('/api/usage/quantity/monthly/', params)
        
        if (response.success) {
          this.monthlyUsageData = response.data
          this.totalRecords = response.total
        } else {
          this.monthlyUsageData = []
          this.totalRecords = 0
          this.$message.info('暂无数据')
        }
      } catch (error) {
        console.error('查询月度用量数据失败:', error)
        this.monthlyUsageData = []
        this.totalRecords = 0
        this.$message.error('查询失败，请稍后重试')
      } finally {
        this.loading = false
      }
    },
    
    // 保存为Excel
    async saveAsXLSX() {
      if (this.monthlyUsageData.length === 0) {
        this.$message.warning('暂无数据可导出')
        return
      }
      
      try {
        // 收集所有数据
        const allData = await this.collectAllData()
        
        // 准备导出数据
        const exportData = allData.map(item => ({
          '专有部分': item.specific_part || '-',
          '楼栋': item.building || '-',
          '单元': item.unit || '-',
          '房号': item.room_number || '-',
          '供能模式': item.energy_mode || '-',
          '初期能耗(kWh)': item.initial_energy !== null && item.initial_energy !== undefined ? item.initial_energy : '',
          '末期能耗(kWh)': item.final_energy !== null && item.final_energy !== undefined ? item.final_energy : '',
          '使用量(kWh)': (item.initial_energy !== null && item.initial_energy !== undefined && item.final_energy !== null && item.final_energy !== undefined) ? (item.final_energy - item.initial_energy) : '',
          '用量月度': item.usage_month || '-'
        }))
        
        // 导出为XLSX
        this.exportToXLSX(exportData, '能耗月用量报表_' + new Date().toLocaleDateString('zh-CN') + '.xlsx')
      } catch (error) {
        console.error('导出数据失败:', error)
        this.$message.error('导出数据失败，请重试')
      }
    },
    
    // 收集所有数据
    async collectAllData() {
      let allData = []
      let currentPage = 1
      let hasMore = true
      
      while (hasMore) {
        // 构建查询条件
        let specificPart = ''
        const building = document.getElementById('monthlySelectedBuilding').value
        const unit = document.getElementById('monthlySelectedUnit').value
        const room = document.getElementById('monthlySelectedRoom').value
        
        if (building && unit && room) {
          // 根据房号长度提取楼层号：3位数取第一位，4位数取前两位
          let floor = ''
          if (room.length === 3) {
            floor = room.charAt(0)  // 3位数房号，如302，取第一位作为楼层号
          } else if (room.length === 4) {
            floor = room.substring(0, 2)  // 4位数房号，如1002、3305，取前两位作为楼层号
          } else {
            floor = room.charAt(0)  // 其他情况默认取第一位
          }
          // 构建4部分格式：楼栋-单元-楼层-房号
          specificPart = `${building}-${unit}-${floor}-${room}`
        } else if (building && unit) {
          specificPart = building + '-' + unit
        } else if (building) {
          specificPart = building
        }
        
        const energyMode = this.queryForm.energyMode
        const startTime = this.queryForm.monthRange[0]
        const endTime = this.queryForm.monthRange[1]
        
        // 构建查询参数
        const params = {
          page: currentPage,
          page_size: 100, // 每页获取100条数据，加快收集速度
          specific_part: specificPart || '',
          energy_mode: energyMode || '',
          start_time: startTime,
          end_time: endTime
        }
        
        // 调用API获取数据
        const response = await api.get('/api/usage/quantity/monthly/', params)
        
        if (response.success && Array.isArray(response.data)) {
          allData = allData.concat(response.data)
          
          // 检查是否还有更多数据
          if (response.data.length < 100) {
            hasMore = false
          } else {
            currentPage++
          }
        } else {
          hasMore = false
        }
      }
      
      return allData
    },
    
    // 导出为XLSX
    exportToXLSX(data, filename) {
      // 创建工作簿
      const wb = XLSX.utils.book_new()
      
      // 创建工作表
      const ws = XLSX.utils.json_to_sheet(data)
      
      // 设置列宽
      const colWidths = [
        { wch: 20 }, // 专有部分
        { wch: 10 }, // 楼栋
        { wch: 10 }, // 单元
        { wch: 10 }, // 房号
        { wch: 12 }, // 供能模式
        { wch: 15 }, // 初期能耗(kWh)
        { wch: 15 }, // 末期能耗(kWh)
        { wch: 12 }, // 使用量(kWh)
        { wch: 15 }  // 用量月度
      ]
      ws['!cols'] = colWidths
      
      // 将工作表添加到工作簿
      XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')
      
      // 导出文件
      XLSX.writeFile(wb, filename)
    },
    
    // 分页大小变化
    handleSizeChange(size) {
      this.pageSize = parseInt(size)
      this.currentPage = 1
      this.searchMonthlyUsageData()
    },
    
    // 当前页码变化
    handleCurrentChange(page) {
      this.currentPage = page
      this.searchMonthlyUsageData()
    }
  }
}
</script>

<style scoped>
.monthly-usage-container {
  width: 100%;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  color: #303133;
  font-size: 20px;
  font-weight: 600;
}

.page-subtitle {
  margin: 5px 0 0 0;
  color: #909399;
  font-size: 14px;
}

.query-form-card {
  margin-bottom: 20px;
}

.data-table-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.query-form-card .el-form {
  margin-bottom: 0;
}

.query-form-card .el-form-item {
  margin-bottom: 5px; /* 减少表单元素底部间距 */
}

.query-form-card .el-form-item__label {
  margin-bottom: 2px; /* 减少标签与输入框之间的间距 */
  font-size: 12px; /* 减小标签字体大小 */
}

.query-buttons {
  display: flex;
  align-items: flex-end;
  height: 100%;
  justify-content: flex-start;
  padding-top: 19px; /* 调整此值使按钮组总高度与时间段组一致 */
  margin-bottom: 5px; /* 与时间段组保持一致，与父容器底部有相同的margin */
}

.query-buttons .el-button {
  margin-right: 15px;
  height: 36px;
  padding: 0 15px;
  font-size: 13px;
  line-height: 36px;
  border-radius: 4px;
}

/* 确保日期选择器高度与按钮一致 */
.query-form-card :deep(.el-date-editor) {
  height: 36px;
}

.query-form-card :deep(.el-date-editor .el-range-input),
.query-form-card :deep(.el-date-editor .el-range-separator) {
  height: 36px;
  line-height: 36px;
  padding: 0 5px;
}

/* 确保日期选择器输入框包装器高度一致 */
.query-form-card :deep(.el-date-editor .el-input__wrapper) {
  height: 36px;
}

.query-form-card :deep(.el-date-editor .el-input__inner) {
  height: 36px;
  line-height: 36px;
}

/* 确保下拉选择器高度与其他组件一致 */
.query-form-card :deep(.el-select__wrapper) {
  height: 36px;
}

/* 确保级联选择器输入框与其他组件高度一致 */
.query-form-card :deep(.cascading-selector-input) {
  height: 36px;
  line-height: 36px;
  padding: 0 10px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>