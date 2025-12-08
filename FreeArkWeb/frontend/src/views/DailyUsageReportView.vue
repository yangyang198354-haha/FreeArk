<template>
  <div class="daily-usage-container">
    <div class="page-header">
      <h2>能耗日用量报表</h2>
      <p class="page-subtitle">查看和分析每日能耗数据</p>
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
            <el-button type="primary" @click="searchUsageData" :loading="loading" style="margin-right: 15px;">
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
    
    <!-- 用量数据图表 -->
    <el-card class="chart-card">
      <template #header>
        <div class="card-header">
          <span>用量趋势图表</span>
        </div>
      </template>
      
      <!-- 图表容器 -->
      <div class="chart-container">
        <el-skeleton :rows="3" animated v-if="loading" />
        <el-empty description="暂无数据" v-else-if="usageData.length === 0" />
        <canvas ref="usageChart" v-else></canvas>
      </div>
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
      <el-empty description="暂无数据" v-else-if="usageData.length === 0" />
      
      <!-- 数据表格 -->
      <el-table
        v-else
        :data="usageData"
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
        <el-table-column prop="time_period" label="时间段" min-width="150" />
      </el-table>
      
      <!-- 分页控件 -->
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

// 注册数据标签插件
Chart.register(ChartDataLabels)

export default {
  name: 'DailyUsageReportView',
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
      pageSize: 20,
      totalRecords: 0,
      // 数据列表
      usageData: [],
      // 加载状态
      loading: false,
      // 图表实例
      chartInstance: null
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
    resetQueryForm() {
      // 重置日期范围
      this.queryForm.dateRange = []
      
      // 重置楼栋-单元-户号选择
      const input = document.querySelector('.cascading-selector-input')
      const clearBtn = document.querySelector('.cascading-clear-btn')
      if (input) {
        input.value = ''
      }
      if (clearBtn) {
        clearBtn.style.display = 'none'
      }
      document.getElementById('dailySelectedBuilding').value = ''
      document.getElementById('dailySelectedUnit').value = ''
      document.getElementById('dailySelectedRoom').value = ''
      
      // 重置供能模式选择
      this.queryForm.energyMode = ''
      
      // 重置分页和数据
      this.currentPage = 1
      this.usageData = []
      this.totalRecords = 0
      this.destroyChart()
    },
    
    // 查询用量数据
    async searchUsageData() {
      // 构建查询条件
      let specificPart = ''
      const building = document.getElementById('dailySelectedBuilding').value
      const unit = document.getElementById('dailySelectedUnit').value
      const room = document.getElementById('dailySelectedRoom').value
      
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
        const response = await api.get('/api/usage/quantity/', params)
        
        if (response.success) {
          this.usageData = response.data
          this.totalRecords = response.total
          
          // 更新图表
          this.updateChart()
        } else {
          this.usageData = []
          this.totalRecords = 0
          this.destroyChart()
          this.$message.info('暂无数据')
        }
      } catch (error) {
        console.error('查询用量数据失败:', error)
        this.usageData = []
        this.totalRecords = 0
        this.destroyChart()
        this.$message.error('查询失败，请稍后重试')
      } finally {
        this.loading = false
      }
    },
    
    // 保存为Excel
    async saveAsXLSX() {
      if (this.usageData.length === 0) {
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
        this.exportToXLSX(exportData, '能耗日用量报表_' + new Date().toLocaleDateString('zh-CN') + '.xlsx')
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
          const buildingElement = document.getElementById('dailySelectedBuilding')
          const unitElement = document.getElementById('dailySelectedUnit')
          const roomElement = document.getElementById('dailySelectedRoom')
          
          const building = buildingElement ? buildingElement.value : ''
          const unit = unitElement ? unitElement.value : ''
          const room = roomElement ? roomElement.value : ''
          
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
        const response = await api.get('/api/usage/quantity/', params)
        
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
    
    // 更新图表
    async updateChart() {
      if (this.usageData.length === 0) {
        this.destroyChart()
        return
      }
      
      // 销毁现有图表
      this.destroyChart()
      
      // 等待DOM更新，确保canvas元素已渲染
      await this.$nextTick()
      
      // 检查canvas元素是否存在
      if (!this.$refs.usageChart) {
        console.error('Canvas元素未找到，无法渲染图表')
        return
      }
      
      // 按日期和供能模式分组数据
      const groupedData = {};
      const dates = new Set();
      const modes = new Set();
      
      // 确保usageData是数组
      const safeUsageData = Array.isArray(this.usageData) ? this.usageData : [];
      
      safeUsageData.forEach(item => {
        if (item && item.time_period && item.energy_mode) {
          const date = item.time_period;
          const mode = item.energy_mode;
          const usage = item.usage_quantity !== null && item.usage_quantity !== undefined ? parseFloat(item.usage_quantity) || 0 : 0;
          
          dates.add(date);
          modes.add(mode);
          
          if (!groupedData[date]) {
            groupedData[date] = {};
          }
          groupedData[date][mode] = (groupedData[date][mode] || 0) + usage;
        }
      });
      
      // 排序日期
      const sortedDates = Array.from(dates).sort();
      
      // 准备图表数据
      const datasets = [];
      const modeColors = {
        '制冷': 'rgb(75, 192, 192)',
        '制热': 'rgb(255, 99, 132)'
      };
      
      // 确保modes是可迭代的
      const safeModes = modes instanceof Set ? modes : new Set();
      
      safeModes.forEach(mode => {
        if (mode) {
          const dataPoints = sortedDates.map(date => groupedData[date]?.[mode] || 0);
          datasets.push({
            label: mode,
            data: dataPoints,
            borderColor: modeColors[mode] || 'rgb(201, 203, 207)',
            backgroundColor: modeColors[mode] ? modeColors[mode] + '33' : 'rgba(201, 203, 207, 0.2)',
            tension: 0.4,
            fill: false,
            pointRadius: 5,
            pointHoverRadius: 7,
            pointBackgroundColor: modeColors[mode] || 'rgb(201, 203, 207)',
            pointBorderColor: '#fff',
            pointBorderWidth: 2
          });
        }
      });
      
      // 创建新图表
      try {
        const ctx = this.$refs.usageChart.getContext('2d')
        this.chartInstance = new Chart(ctx, {
          type: 'line',
          data: {
            labels: sortedDates,
            datasets: datasets
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: '不同供能模式下的每日使用量'
              },
              legend: {
                display: true,
                position: 'top',
                labels: {
                  padding: 15,
                  usePointStyle: true,
                  boxWidth: 6
                }
              },
              tooltip: {
                mode: 'index',
                intersect: false,
                callbacks: {
                  label: function(context) {
                    return context.dataset.label + ': ' + context.parsed.y.toFixed(2) + ' kWh';
                  }
                }
              },
              datalabels: {
                display: function(context) {
                  // 只显示非空和非零的数据点，确保context.parsed存在
                  return context && context.parsed && context.parsed.y !== null && context.parsed.y !== undefined && context.parsed.y > 0;
                },
                color: function(context) {
                  // 使用与数据集相同的颜色，确保context.dataset存在
                  return context && context.dataset && context.dataset.borderColor ? context.dataset.borderColor : '#000000';
                },
                formatter: function(value) {
                  // 格式化数值，保留2位小数，确保value存在且为数字
                  if (value === null || value === undefined || isNaN(value)) {
                    return '';
                  }
                  return value.toFixed(2) + ' kWh';
                },
                font: {
                  weight: 'bold',
                  size: 12
                },
                offset: 10,
                align: 'top'
              }
            },
            scales: {
              y: {
                beginAtZero: true,
                title: {
                  display: true,
                  text: '使用量 (kWh)'
                }
              },
              x: {
                title: {
                  display: true,
                  text: '日期'
                }
              }
            }
          }
        })
      } catch (error) {
        console.error('渲染图表失败:', error)
      }
    },
    
    // 销毁图表
    destroyChart() {
      if (this.chartInstance) {
        this.chartInstance.destroy()
        this.chartInstance = null
      }
    },
    
    // 分页大小变化
    handleSizeChange(size) {
      this.pageSize = parseInt(size)
      this.currentPage = 1
      this.searchUsageData()
    },
    
    // 当前页码变化
    handleCurrentChange(page) {
      this.currentPage = page
      this.searchUsageData()
    }
  },
  beforeUnmount() {
    // 组件销毁前销毁图表
    this.destroyChart()
  }
}
</script>

<style scoped>
.daily-usage-container {
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

.chart-card {
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
  margin-right: 10px;
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

.chart-container {
  height: 300px;
  width: 100%;
  position: relative;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>