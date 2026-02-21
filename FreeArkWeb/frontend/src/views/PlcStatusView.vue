<template>
  <div class="plc-status-container">
    <div class="page-header">
      <h2>PLC在线离线监控</h2>
      <p class="page-subtitle">实时监控PLC设备连接状态</p>
    </div>
    
    <!-- 统计卡片 -->
    <div class="statistics-cards">
      <el-card class="stat-card online-card">
        <div class="stat-content">
          <div class="stat-value">{{ statistics.online_count }}</div>
          <div class="stat-label">当前在线</div>
        </div>
      </el-card>
      
      <el-card class="stat-card offline-card">
        <div class="stat-content">
          <div class="stat-value">{{ statistics.offline_count }}</div>
          <div class="stat-label">当前离线</div>
        </div>
      </el-card>
      
      <el-card class="stat-card total-card">
        <div class="stat-content">
          <div class="stat-value">{{ statistics.total_devices }}</div>
          <div class="stat-label">设备总数</div>
        </div>
      </el-card>
      
      <el-card class="stat-card rate-card">
        <div class="stat-content">
          <div class="stat-value">{{ statistics.online_rate }}%</div>
          <div class="stat-label">在线率</div>
        </div>
      </el-card>
    </div>
    
    <!-- 筛选条件表单 -->
    <el-card class="filter-form-card">
      <el-form :model="filterForm" label-position="top" size="small">
        <el-row :gutter="20">
          <!-- 楼栋 -->
          <el-col :xs="24" :sm="24" :md="8" :lg="4">
            <el-form-item label="楼栋" prop="building">
              <el-select
                v-model="filterForm.building"
                placeholder="全部"
                clearable
                @change="handleFilterChange"
              >
                <el-option label="全部" value="" />
                <el-option
                  v-for="building in buildingOptions"
                  :key="building"
                  :label="building"
                  :value="building"
                />
              </el-select>
            </el-form-item>
          </el-col>
          
          <!-- 单元 -->
          <el-col :xs="24" :sm="24" :md="8" :lg="4">
            <el-form-item label="单元" prop="unit">
              <el-select
                v-model="filterForm.unit"
                placeholder="全部"
                clearable
                @change="handleFilterChange"
              >
                <el-option label="全部" value="" />
                <el-option
                  v-for="unit in unitOptions"
                  :key="unit"
                  :label="unit"
                  :value="unit"
                />
              </el-select>
            </el-form-item>
          </el-col>
          
          <!-- 连接状态 -->
          <el-col :xs="24" :sm="24" :md="8" :lg="4">
            <el-form-item label="连接状态" prop="connectionStatus">
              <el-select
                v-model="filterForm.connectionStatus"
                placeholder="全部"
                clearable
                @change="handleFilterChange"
              >
                <el-option label="全部" value="" />
                <el-option label="在线" value="online" />
                <el-option label="离线" value="offline" />
              </el-select>
            </el-form-item>
          </el-col>
          
          <!-- 刷新按钮 -->
          <el-col :xs="24" :sm="24" :md="8" :lg="12" style="display: flex; align-items: flex-end; padding-bottom: 4px;">
            <div class="refresh-button-wrapper">
              <el-button 
                type="primary" 
                @click="refreshData" 
                :loading="loading"
              >
                <el-icon><Refresh /></el-icon>
                刷新数据
              </el-button>
            </div>
          </el-col>
        </el-row>
      </el-form>
    </el-card>
    
    <!-- PLC状态数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div class="card-header">
          <span>PLC设备连接状态</span>
        </div>
      </template>
      
      <!-- 加载指示器 -->
      <el-skeleton :rows="5" animated v-if="loading" />
      
      <!-- 无数据提示 -->
      <el-empty description="暂无数据" v-else-if="plcStatusData.length === 0" />
      
      <!-- 数据表格 -->
      <el-table
        v-else
        :data="plcStatusData"
        style="width: 100%"
        border
        stripe
        :header-cell-style="{ backgroundColor: '#f5f7fa' }"
        @row-click="handleRowClick"
        row-key="specific_part"
      >
        <el-table-column prop="specific_part" label="设备标识" min-width="150" />
        <el-table-column prop="connection_status" label="连接状态" min-width="120">
          <template #default="scope">
            <el-tag
              :type="scope.row.connection_status === 'online' ? 'success' : 'danger'"
              size="small"
            >
              {{ scope.row.connection_status === 'online' ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后在线时间" min-width="180">
          <template #default="scope">
            <span v-if="scope.row.connection_status === 'offline'">
              {{ formatDateTime(scope.row.last_online_time) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="building" label="楼栋" min-width="80" />
        <el-table-column prop="unit" label="单元" min-width="80" />
        <el-table-column prop="room_number" label="房号" min-width="80" />
      </el-table>
      
      <!-- 分页控件 -->
      <div class="pagination-container" v-if="plcStatusData.length > 0">
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
import { Refresh } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'PlcStatusView',
  components: {
    Refresh
  },
  data() {
    return {
      // 筛选表单数据
      filterForm: {
        building: '',
        unit: '',
        connectionStatus: ''
      },
      // 分页数据
      currentPage: 1,
      pageSize: 10,
      totalRecords: 0,
      // 数据列表
      plcStatusData: [],
      // 加载状态
      loading: false,
      // 统计数据
      statistics: {
        online_count: 0,
        offline_count: 0,
        total_devices: 0,
        online_rate: 0
      },
      // 选项数据
      buildingOptions: [],
      unitOptions: []
    }
  },
  mounted() {
    // 页面加载时获取数据
    this.getData()
    // 初始化选项数据
    this.initOptions()
  },
  methods: {
    // 初始化选项数据
    initOptions() {
      // 这里可以从API或本地数据获取楼栋和单元选项
      // 暂时使用静态数据
      this.buildingOptions = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
      this.unitOptions = ['1', '2', '3']
    },
    
    // 获取PLC连接状态数据
    async getData() {
      this.loading = true
      try {
        // 构建查询参数
        const params = {
          page: this.currentPage,
          page_size: this.pageSize,
          building: this.filterForm.building || '',
          unit: this.filterForm.unit || '',
          connection_status: this.filterForm.connectionStatus || ''
        }
        
        // 调用API获取数据
        const response = await api.get('/api/plc/connection-status/', params)
        
        if (response.success && Array.isArray(response.data)) {
          this.plcStatusData = response.data
          this.totalRecords = response.total || 0
          // 更新统计数据
          if (response.statistics) {
            this.statistics = response.statistics
          }
        } else {
          this.plcStatusData = []
          this.totalRecords = 0
          this.$message.info('暂无数据')
        }
      } catch (error) {
        console.error('获取PLC连接状态数据失败:', error)
        this.plcStatusData = []
        this.totalRecords = 0
        this.$message.error('获取数据失败，请稍后重试')
      } finally {
        this.loading = false
      }
    },
    
    // 刷新数据
    refreshData() {
      this.currentPage = 1
      this.getData()
    },
    
    // 处理筛选条件变化
    handleFilterChange() {
      this.currentPage = 1
      this.getData()
    },
    
    // 格式化日期时间
    formatDateTime(dateTimeStr) {
      if (!dateTimeStr) {
        return '-'  
      }
      const date = new Date(dateTimeStr)
      if (isNaN(date.getTime())) {
        return '-'  
      }
      return date.toLocaleString('zh-CN')
    },
    
    // 处理表格行点击事件
    handleRowClick(row) {
      // 跳转到specific_part详情页面
      this.$router.push({
        name: 'SpecificPartDetail',
        params: { specificPart: row.specific_part }
      })
    },
    
    // 处理分页大小变化
    handleSizeChange(size) {
      this.pageSize = size
      this.currentPage = 1
      this.getData()
    },
    
    // 处理当前页码变化
    handleCurrentChange(page) {
      this.currentPage = page
      this.getData()
    }
  }
}
</script>

<style scoped>
.plc-status-container {
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

/* 统计卡片样式 */
.statistics-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 25px;
}

.stat-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  transition: all 0.3s ease;
  cursor: pointer;
}

.stat-card:hover {
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.stat-content {
  text-align: center;
  padding: 20px 0;
}

.stat-value {
  font-size: 32px;
  font-weight: 600;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

/* 不同状态卡片的颜色 */
.online-card .stat-value {
  color: #67c23a;
}

.offline-card .stat-value {
  color: #f56c6c;
}

.total-card .stat-value {
  color: #409eff;
}

.rate-card .stat-value {
  color: #e6a23c;
}

/* 筛选表单样式 */
.filter-form-card {
  margin-bottom: 25px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  background-color: #fff;
}

.filter-form-card:hover {
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.08);
}

.filter-form-card .el-form {
  margin-bottom: 0;
}

.filter-form-card .el-form-item {
  margin-bottom: 5px;
}

.filter-form-card .el-form-item__label {
  margin-bottom: 2px;
  font-size: 12px;
  font-weight: 500;
}

.refresh-button-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: flex-start;
}

/* 数据表格样式 */
.data-table-card {
  margin-bottom: 20px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  background-color: #fff;
}

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

/* 表格样式 */
.data-table-card .el-table {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}

.data-table-card .el-table__row {
  transition: background-color 0.2s ease;
  cursor: pointer;
}

.data-table-card .el-table__row:hover {
  background-color: #f5f7fa;
}

.data-table-card .el-table__header-wrapper .el-table__header {
  background-color: #f5f7fa;
}

.data-table-card .el-table__header-wrapper th {
  font-weight: 500;
  color: #303133;
  background-color: #f5f7fa;
}

.data-table-card .el-table__body-wrapper td {
  color: #606266;
  border-bottom: 1px solid #ebeef5;
}

/* 分页样式 */
.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  padding-top: 15px;
  border-top: 1px solid #e4e7ed;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .statistics-cards {
    grid-template-columns: 1fr 1fr;
  }
  
  .refresh-button-col {
    margin-top: 15px;
    padding-top: 0;
  }
  
  .refresh-button-wrapper {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

@media (max-width: 576px) {
  .statistics-cards {
    grid-template-columns: 1fr;
  }
}
</style>