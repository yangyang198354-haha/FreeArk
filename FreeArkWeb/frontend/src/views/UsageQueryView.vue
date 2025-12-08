<template>
  <div class="usage-query-container">
    <div class="page-header">
      <h2>用量查询</h2>
      <p class="page-subtitle">查询和统计能耗数据</p>
    </div>
    
    <!-- 查询条件表单 -->
    <el-card class="query-form-card">
      <el-form :model="queryForm" label-position="top" size="small">
        <el-row :gutter="20">
          <!-- 楼栋-单元-户号选择 -->
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
          
          <!-- 时间段 -->
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
          
          <!-- 查询按钮组 -->
          <el-col :xs="24" :sm="24" :md="24" :lg="6" class="query-buttons" style="align-self: flex-end;">
            <el-button type="primary" @click="searchData" :loading="loading" style="margin-right: 15px;">
              查询
            </el-button>
            <el-button @click="resetForm" style="margin-right: 15px;">
              重置
            </el-button>
            <el-button type="success" @click="saveAsExcel">
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
      <el-empty description="暂无数据" v-else-if="consumptionData.length === 0" />
      
      <!-- 数据表格 -->
      <el-table
        v-else
        :data="consumptionData"
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
        <el-table-column prop="time_period" label="用量月度" min-width="120" />
      </el-table>
      
      <!-- 分页控件 -->
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
  components: {
    CascadingSelector
  },
  data() {
    return {
      // 查询表单数据
      queryForm: {
        specificPart: '',
        energyMode: '',
        dateRange: []
      },
      // 日期选择器快捷选项
      dateShortcuts: [
        {
          text: '今天',
          value: () => {
            const now = new Date()
            return [new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0), now]
          }
        },
        {
          text: '昨天',
          value: () => {
            const now = new Date()
            const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
            return [
              new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate(), 0, 0, 0),
              new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate(), 23, 59, 59)
            ]
          }
        },
        {
          text: '近7天',
          value: () => {
            const now = new Date()
            const sevenDaysAgo = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6)
            return [
              new Date(sevenDaysAgo.getFullYear(), sevenDaysAgo.getMonth(), sevenDaysAgo.getDate(), 0, 0, 0),
              now
            ]
          }
        },
        {
          text: '近30天',
          value: () => {
            const now = new Date()
            const thirtyDaysAgo = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29)
            return [
              new Date(thirtyDaysAgo.getFullYear(), thirtyDaysAgo.getMonth(), thirtyDaysAgo.getDate(), 0, 0, 0),
              now
            ]
          }
        },
        {
          text: '本月',
          value: () => {
            const now = new Date()
            return [
              new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0),
              now
            ]
          }
        },
        {
          text: '上月',
          value: () => {
            const now = new Date()
            const firstDayOfCurrentMonth = new Date(now.getFullYear(), now.getMonth(), 1)
            const lastDayOfLastMonth = new Date(firstDayOfCurrentMonth.getTime() - 1)
            return [
              new Date(lastDayOfLastMonth.getFullYear(), lastDayOfLastMonth.getMonth(), 1, 0, 0, 0),
              new Date(lastDayOfLastMonth.getFullYear(), lastDayOfLastMonth.getMonth(), lastDayOfLastMonth.getDate(), 23, 59, 59)
            ]
          }
        }
      ],
      // 分页数据
      currentPage: 1,
      pageSize: 10,
      totalRecords: 0,
      // 数据列表
      consumptionData: [],
      // 加载状态
      loading: false
    }
  },
  methods: {
    // 禁用日期函数
    disabledDate(date) {
      const minDate = new Date(2020, 1, 1) // 2020年2月1日
      const maxDate = new Date() // 当前日期
      return date < minDate || date > maxDate
    },
    
    // 重置查询表单
    resetForm() {
      // 重置日期范围
      this.queryForm.dateRange = []
      
      // 重置供能模式选择
      this.queryForm.energyMode = ''
      
      // 重置分页和数据
      this.currentPage = 1
      this.consumptionData = []
      this.totalRecords = 0
      
      // 重置楼栋-单元-户号选择
      const buildingInput = document.getElementById('consumptionSelectedBuilding')
      const unitInput = document.getElementById('consumptionSelectedUnit')
      const roomInput = document.getElementById('consumptionSelectedRoom')
      if (buildingInput) buildingInput.value = ''
      if (unitInput) unitInput.value = ''
      if (roomInput) roomInput.value = ''
      
      // 重置显示输入框
      const input = document.querySelector('.cascading-selector-input')
      const clearBtn = document.querySelector('.cascading-clear-btn')
      if (input) input.value = ''
      if (clearBtn) clearBtn.style.display = 'none'
    },
    
    // 查询能耗数据
    async searchData() {
      // 构建查询条件
      let specificPart = ''
      const building = document.getElementById('consumptionSelectedBuilding').value
      const unit = document.getElementById('consumptionSelectedUnit').value
      let room = document.getElementById('consumptionSelectedRoom').value
      
      // 确保room只包含纯房号，不包含完整的"building-unit-room"格式
      if (room.includes('-')) {
        const roomParts = room.split('-')
        room = roomParts[roomParts.length - 1] // 只取最后一部分作为纯房号
      }
      
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
      let startTime = this.queryForm.dateRange[0]
      let endTime = this.queryForm.dateRange[1]
      
      // 表单验证
      if (!startTime || !endTime) {
        this.$message.warning('请选择时间段')
        return
      }
      
      // 确保日期格式化为YYYY-MM-DD字符串
      if (startTime instanceof Date) {
        startTime = startTime.toISOString().split('T')[0]
      }
      if (endTime instanceof Date) {
        endTime = endTime.toISOString().split('T')[0]
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
        const response = await api.get('/api/usage/quantity/specifictimeperiod', params)
        
        if (response.success && Array.isArray(response.data)) {
          this.consumptionData = response.data
          this.totalRecords = response.total || 0
        } else {
          this.consumptionData = []
          this.totalRecords = 0
          this.$message.info('暂无数据')
        }
      } catch (error) {
        console.error('查询能耗数据失败:', error)
        this.consumptionData = []
        this.totalRecords = 0
        this.$message.error('查询失败，请稍后重试')
      } finally {
        this.loading = false
      }
    },
    
    // 保存为Excel
    async saveAsExcel() {
      if (this.consumptionData.length === 0) {
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
          '时间段': item.time_period || '-'
        }))
        
        // 导出为XLSX
        this.exportToXLSX(exportData, '能耗报表_' + new Date().toLocaleDateString('zh-CN') + '.xlsx')
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
        const building = document.getElementById('consumptionSelectedBuilding').value
        const unit = document.getElementById('consumptionSelectedUnit').value
        let room = document.getElementById('consumptionSelectedRoom').value
        
        // 确保room只包含纯房号，不包含完整的"building-unit-room"格式
        if (room.includes('-')) {
          const roomParts = room.split('-')
          room = roomParts[roomParts.length - 1] // 只取最后一部分作为纯房号
        }
        
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
        let startTime = this.queryForm.dateRange[0]
        let endTime = this.queryForm.dateRange[1]
        
        // 确保日期格式化为YYYY-MM-DD字符串
        if (startTime instanceof Date) {
          startTime = startTime.toISOString().split('T')[0]
        }
        if (endTime instanceof Date) {
          endTime = endTime.toISOString().split('T')[0]
        }
        
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
        const response = await api.get('/api/usage/quantity/specifictimeperiod', params)
        
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
        { wch: 15 }  // 时间段
      ]
      ws['!cols'] = colWidths
      
      // 将工作表添加到工作簿
      XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')
      
      // 导出文件
      XLSX.writeFile(wb, filename)
    },
    
    // 分页大小变化
    handleSizeChange(size) {
      this.pageSize = size
      this.currentPage = 1
      this.searchData()
    },
    
    // 当前页码变化
    handleCurrentChange(page) {
      this.currentPage = page
      this.searchData()
    }
  }
}
</script>

<style scoped>
.usage-query-container {
  width: 100%;
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
  box-sizing: border-box;
}

.page-header {
  margin-bottom: 25px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e4e7ed;
}

.page-header h2 {
  margin: 0;
  color: #303133;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.page-subtitle {
  margin: 8px 0 0 0;
  color: #909399;
  font-size: 14px;
  line-height: 1.5;
}

.query-form-card {
  margin-bottom: 25px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  transition: all 0.3s ease;
  background-color: #fff;
}

/* 卡片悬停效果 */
.query-form-card:hover {
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.08);
}

.data-table-card {
  margin-bottom: 20px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  transition: all 0.3s ease;
  background-color: #fff;
}

/* 卡片悬停效果 */
.data-table-card:hover {
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 10px;
  font-weight: 500;
  font-size: 15px;
}

.query-form-card .el-form {
  margin-bottom: 0;
}

.query-form-card .el-form-item {
  margin-bottom: 5px; /* 与其他页面一致的表单元素底部间距 */
}

.query-form-card .el-form-item__label {
  margin-bottom: 2px; /* 与其他页面一致的标签与输入框之间的间距 */
  font-size: 12px; /* 与其他页面一致的标签字体大小 */
  font-weight: 500;
}

/* 统一所有表单控件样式 */
.query-form-card .el-input__wrapper,
.query-form-card .el-select__wrapper,
.query-form-card .el-picker__wrapper {
  height: 36px !important;
  box-sizing: border-box !important;
}

/* 统一所有输入框样式 */
.query-form-card :deep(.el-input__inner),
.query-form-card :deep(.el-select__input),
.query-form-card :deep(.el-picker__input) {
  height: 36px !important;
  line-height: 34px !important;
  font-size: 14px !important;
  padding: 0 12px !important;
  font-family: inherit !important;
  color: #606266 !important;
  box-sizing: border-box !important;
}

/* 统一选择器下拉容器样式 */
.query-form-card :deep(.el-select__wrapper) {
  height: 36px !important;
  min-height: 36px !important;
  box-sizing: border-box !important;
}

/* 统一日期选择器容器样式 */
.query-form-card :deep(.el-picker__wrapper) {
  height: 36px !important;
  box-sizing: border-box !important;
}

/* 级联选择器样式统一 */
.query-form-card :deep(.cascading-selector-input) {
  height: 36px !important;
  line-height: 36px !important;
  font-size: 14px !important;
  padding: 0 12px !important;
  font-family: inherit !important;
  color: #606266 !important;
  box-sizing: border-box !important;
  border: 1px solid #dcdfe6 !important;
  border-radius: 4px !important;
  transition: border-color 0.2s, box-shadow 0.2s !important;
}

/* Element Plus Select 组件内部样式优化 */
.query-form-card :deep(.el-select__wrapper) {
  min-height: 36px !important;
  height: 36px !important;
}

/* Element Plus Select 组件样式优化 */
.query-form-card :deep(.el-select__wrapper) {
  height: 36px !important;
  min-height: 36px !important;
}

.query-form-card :deep(.el-select .el-input__inner) {
  height: 36px !important;
  line-height: 36px !important;
}

/* Element Plus Date Picker 组件样式优化 */
.query-form-card :deep(.el-date-editor) {
  height: 36px !important;
}

.query-form-card :deep(.el-date-editor .el-input__wrapper) {
  height: 36px !important;
  min-height: 36px !important;
}

.query-form-card :deep(.el-date-editor .el-range-input) {
  height: 36px !important;
  line-height: 36px !important;
}

.query-form-card :deep(.el-date-editor .el-range-separator) {
  height: 36px !important;
  line-height: 36px !important;
}

.query-form-card :deep(.el-date-editor .el-input__inner) {
  height: 36px !important;
  line-height: 36px !important;
}

/* 确保所有内部元素高度一致 */
.query-form-card :deep(.el-input-group),
.query-form-card :deep(.el-input-group__append),
.query-form-card :deep(.el-input-group__prepend) {
  height: 36px !important;
}

/* 确保供能模式选择器高度一致 */
.query-form-card :deep(.el-select .el-input__wrapper) {
  height: 36px !important;
}

.query-form-card :deep(.el-select .el-input__inner) {
  height: 36px !important;
  line-height: 36px !important;
}

/* 确保日期选择器高度一致 */
.query-form-card :deep(.el-date-editor .el-input__wrapper) {
  height: 36px !important;
}

.query-form-card :deep(.el-date-editor .el-input__inner) {
  height: 36px !important;
  line-height: 36px !important;
}

/* 确保选择器选项高度一致 */
.query-form-card .el-select-dropdown__item {
  line-height: 30px !important;
}

/* 确保日期选择器面板高度一致 */
.query-form-card .el-picker-panel {
  line-height: 30px !important;
}

.query-buttons {
  display: flex;
  align-items: flex-end;
  height: 100%; /* 与父容器高度一致 */
  justify-content: flex-start;
  padding-top: 19px; /* 调整此值使按钮组总高度与时间段组一致 */
  margin-bottom: 5px; /* 与时间段组保持一致，与父容器底部有相同的margin */
}

/* 响应式设计：在小屏幕尺寸下调整按钮组样式 */
@media (max-width: 1200px) {
  .query-buttons {
    margin-top: 15px; /* 小屏幕下调整margin，确保对齐 */
    justify-content: flex-start;
    margin-left: 0;
  }
}

@media (max-width: 992px) {
  .query-buttons {
    margin-top: 15px;
    justify-content: flex-start;
  }
}

@media (max-width: 768px) {
  .query-buttons {
    margin-top: 15px;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
  
  .query-buttons .el-button {
    margin-bottom: 10px;
  }
}

@media (max-width: 576px) {
  .query-buttons {
    margin-top: 15px;
    justify-content: flex-start;
    flex-direction: column;
    align-items: flex-start;
  }
  
  .query-buttons .el-button {
    margin-right: 0;
    margin-bottom: 10px;
    width: auto;
  }
}

.query-buttons .el-button {
  margin-right: 15px; /* 调整按钮之间的间距 */
  height: 36px; /* 与输入框高度一致 */
  padding: 0 20px; /* 调整按钮内边距 */
  font-size: 13px;
  font-weight: 500;
  line-height: 34px;
  border-radius: 4px;
  transition: all 0.3s ease;
}

/* 优化按钮悬停效果 */
.query-buttons .el-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

/* 优化按钮点击效果 */
.query-buttons .el-button:active {
  transform: translateY(0);
}

/* 优化主按钮样式 */
.query-buttons .el-button--primary {
  background-color: #1890ff;
  border-color: #1890ff;
}

/* 优化成功按钮样式 */
.query-buttons .el-button--success {
  background-color: #52c41a;
  border-color: #52c41a;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  padding-top: 15px;
  border-top: 1px solid #e4e7ed;
}

/* 优化表格样式 */
.data-table-card .el-table {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}

/* 优化表格行样式 */
.data-table-card .el-table__row {
  transition: background-color 0.2s ease;
}

/* 优化表格行悬停效果 */
.data-table-card .el-table__row:hover {
  background-color: #f5f7fa;
}

/* 优化表格头样式 */
.data-table-card .el-table__header-wrapper .el-table__header {
  background-color: #f5f7fa;
}

.data-table-card .el-table__header-wrapper th {
  font-weight: 500;
  color: #303133;
  background-color: #f5f7fa;
}

/* 优化表格单元格样式 */
.data-table-card .el-table__body-wrapper td {
  color: #606266;
  border-bottom: 1px solid #ebeef5;
}

/* 优化分页控件样式 */
.data-table-card .el-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.data-table-card .el-pagination__sizes .el-input__wrapper {
  height: 30px;
}

.data-table-card .el-pagination__sizes .el-input__inner {
  height: 30px;
  line-height: 28px;
}

.data-table-card .el-pagination__btn {
  height: 30px;
  line-height: 30px;
}

.data-table-card .el-pagination__number {
  height: 30px;
  line-height: 30px;
  min-width: 30px;
}
</style>