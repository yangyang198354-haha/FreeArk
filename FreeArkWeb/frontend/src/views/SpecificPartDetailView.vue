<template>
  <div class="specific-part-detail-container">
    <div class="page-header">
      <div class="header-left">
        <h2>设备详情</h2>
        <p class="page-subtitle">查看PLC设备的连接状态和状态变化历史</p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="goBack">
          <el-icon><Back /></el-icon>
          返回列表
        </el-button>
      </div>
    </div>
    
    <!-- 设备基本信息卡片 -->
    <el-card class="info-card">
      <template #header>
        <div class="card-header">
          <span>设备基本信息</span>
        </div>
      </template>
      
      <div class="info-content">
        <div class="info-row">
          <div class="info-item">
            <div class="info-label">设备标识</div>
            <div class="info-value">{{ deviceInfo.specific_part }}</div>
          </div>
          <div class="info-item">
            <div class="info-label">当前状态</div>
            <div class="info-value">
              <el-tag
                :type="deviceInfo.connection_status === 'online' ? 'success' : 'danger'"
                size="small"
              >
                {{ deviceInfo.connection_status === 'online' ? '在线' : '离线' }}
              </el-tag>
            </div>
          </div>
        </div>
        
        <div class="info-row">
          <div class="info-item">
            <div class="info-label">最后在线时间</div>
            <div class="info-value">{{ formatDateTime(deviceInfo.last_online_time) }}</div>
          </div>
          <div class="info-item">
            <div class="info-label">所属楼栋</div>
            <div class="info-value">{{ deviceInfo.building }}栋</div>
          </div>
        </div>
        
        <div class="info-row">
          <div class="info-item">
            <div class="info-label">所属单元</div>
            <div class="info-value">{{ deviceInfo.unit }}单元</div>
          </div>
          <div class="info-item">
            <div class="info-label">房号</div>
            <div class="info-value">{{ deviceInfo.room_number }}</div>
          </div>
        </div>
      </div>
    </el-card>
    
    <!-- 状态变化历史表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div class="card-header">
          <span>状态变化历史</span>
        </div>
      </template>
      
      <!-- 加载指示器 -->
      <el-skeleton :rows="5" animated v-if="loading" />
      
      <!-- 无数据提示 -->
      <el-empty description="暂无数据" v-else-if="statusHistory.length === 0" />
      
      <!-- 数据表格 -->
      <el-table
        v-else
        :data="statusHistory"
        style="width: 100%"
        border
        stripe
        :header-cell-style="{ backgroundColor: '#f5f7fa' }"
      >
        <el-table-column prop="status" label="状态" min-width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'online' ? 'success' : 'danger'">
              {{ scope.row.status === 'online' ? '上线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="change_time" label="变化时间" min-width="200">
          <template #default="scope">
            {{ formatDateTime(scope.row.change_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="building" label="楼栋" min-width="80" />
        <el-table-column prop="unit" label="单元" min-width="80" />
        <el-table-column prop="room_number" label="房号" min-width="80" />
      </el-table>
      
      <!-- 分页控件 -->
      <div class="pagination-container" v-if="statusHistory.length > 0">
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
import { Back } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'SpecificPartDetailView',
  components: {
    Back
  },
  data() {
    return {
      // 路由参数
      specificPart: this.$route.params.specificPart,
      // 设备基本信息
      deviceInfo: {
        specific_part: '',
        connection_status: 'offline',
        last_online_time: null,
        building: '',
        unit: '',
        room_number: ''
      },
      // 分页数据
      currentPage: 1,
      pageSize: 10,
      totalRecords: 0,
      // 状态变化历史列表
      statusHistory: [],
      // 加载状态
      loading: false
    }
  },
  mounted() {
    // 页面加载时获取设备基本信息和状态变化历史
    this.getDeviceInfo()
    this.searchData()
  },
  watch: {
    // 监听路由参数变化
    '$route.params.specificPart': function(newVal) {
      this.specificPart = newVal
      this.getDeviceInfo()
      this.searchData()
    }
  },
  methods: {
    // 返回列表页
    goBack() {
      this.$router.push('/plc-status')
    },
    
    // 获取设备基本信息
    async getDeviceInfo() {
      try {
        const response = await api.get(`/api/plc/connection-status/${this.specificPart}/`)
        if (response.success) {
          this.deviceInfo = response.data
        }
      } catch (error) {
        console.error('获取设备基本信息失败:', error)
        this.$message.error('获取设备信息失败，请稍后重试')
      }
    },
    
    // 获取状态变化历史数据
    async searchData() {
      this.loading = true
      try {
        // 构建查询参数
        const params = {
          page: this.currentPage,
          page_size: this.pageSize
        }
        
        // 调用API获取数据
        const response = await api.get(`/api/plc/status-change-history/${this.specificPart}/`, params)
        
        if (response.success && Array.isArray(response.data)) {
          this.statusHistory = response.data
          this.totalRecords = response.total || 0
        } else {
          this.statusHistory = []
          this.totalRecords = 0
          this.$message.info('暂无数据')
        }
      } catch (error) {
        console.error('查询状态变化历史失败:', error)
        this.statusHistory = []
        this.totalRecords = 0
        this.$message.error('查询数据失败，请稍后重试')
      } finally {
        this.loading = false
      }
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
      // 格式化日期时间为 2026/2/16 23:00:36 格式
      const year = date.getFullYear()
      const month = date.getMonth() + 1 // 月份从0开始，需要加1
      const day = date.getDate()
      const hours = date.getHours()
      const minutes = date.getMinutes()
      const seconds = date.getSeconds()
      
      // 拼接成指定格式
      return `${year}/${month}/${day} ${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
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
.specific-part-detail-container {
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
  margin-bottom: 25px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e4e7ed;
}

.header-left {
  flex: 1;
}

.header-right {
  display: flex;
  gap: 10px;
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

/* 基本信息卡片样式 */
.info-card {
  margin-bottom: 25px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  background-color: #fff;
}

.info-card:hover {
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

.info-content {
  padding: 20px;
}

.info-row {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 15px;
}

.info-item {
  flex: 1;
  min-width: 200px;
  margin-right: 20px;
  margin-bottom: 15px;
}

.info-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 5px;
}

.info-value {
  font-size: 16px;
  font-weight: 500;
  color: #303133;
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

.data-table-card .el-table {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}

.data-table-card .el-table__row {
  transition: background-color 0.2s ease;
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

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  padding-top: 15px;
  border-top: 1px solid #e4e7ed;
}
</style>