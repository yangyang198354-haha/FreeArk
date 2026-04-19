<template>
  <div class="device-history-container">
    <div class="page-header">
      <div class="header-left">
        <h2>设备历史参数</h2>
        <p class="page-subtitle">设备 {{ deviceId }} 的历史参数记录</p>
      </div>
      <div class="header-right">
        <el-button @click="goBack">
          <el-icon><Back /></el-icon>
          返回卡片面板
        </el-button>
      </div>
    </div>

    <!-- 过滤条件 -->
    <el-card class="filter-card">
      <el-form :inline="true" @submit.prevent="handleSearch">
        <el-form-item label="参数名称">
          <el-input
            v-model="filterParamName"
            placeholder="输入参数名称过滤"
            clearable
            style="width: 220px;"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="开始时间">
          <el-date-picker
            v-model="filterStartTime"
            type="datetime"
            placeholder="选择开始时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 200px;"
          />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker
            v-model="filterEndTime"
            type="datetime"
            placeholder="选择结束时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 200px;"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch" :loading="loading">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div class="card-header">
          <span>历史记录（共 {{ totalRecords }} 条）</span>
        </div>
      </template>

      <el-skeleton :rows="5" animated v-if="loading" />

      <el-empty description="暂无历史数据" v-else-if="historyList.length === 0" />

      <el-table
        v-else
        :data="historyList"
        style="width: 100%"
        border
        stripe
        :header-cell-style="{ backgroundColor: '#f5f7fa' }"
      >
        <el-table-column type="index" label="#" width="60" :index="indexMethod" />
        <el-table-column prop="param_name" label="参数名称" min-width="220" />
        <el-table-column prop="value" label="参数值" min-width="120" align="right">
          <template #default="scope">
            {{ scope.row.value !== null && scope.row.value !== undefined ? scope.row.value : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="collected_at" label="采集时间" min-width="180" />
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container" v-if="totalRecords > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
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
  name: 'DeviceParamHistoryView',
  components: {
    Back,
  },
  data() {
    return {
      deviceId: this.$route.params.deviceId || '',
      loading: false,
      filterParamName: '',
      filterStartTime: '',
      filterEndTime: '',
      historyList: [],
      totalRecords: 0,
      currentPage: 1,
      pageSize: 50,
    }
  },
  mounted() {
    this.fetchHistory()
  },
  watch: {
    '$route.params.deviceId'(newVal) {
      this.deviceId = newVal || ''
      this.currentPage = 1
      this.fetchHistory()
    },
  },
  methods: {
    async fetchHistory() {
      this.loading = true
      try {
        const params = {
          page: this.currentPage,
          page_size: this.pageSize,
        }
        if (this.filterParamName) params.param_name = this.filterParamName
        if (this.filterStartTime) params.start_time = this.filterStartTime
        if (this.filterEndTime) params.end_time = this.filterEndTime

        const response = await api.get(`/api/devices/param-history/${this.deviceId}/`, params)
        if (response && response.success) {
          this.historyList = response.results || []
          this.totalRecords = response.count || 0
        } else {
          this.historyList = []
          this.totalRecords = 0
        }
      } catch (error) {
        console.error('获取历史参数失败:', error)
        this.historyList = []
        this.totalRecords = 0
        this.$message.error('获取历史数据失败，请稍后重试')
      } finally {
        this.loading = false
      }
    },

    handleSearch() {
      this.currentPage = 1
      this.fetchHistory()
    },

    handleReset() {
      this.filterParamName = ''
      this.filterStartTime = ''
      this.filterEndTime = ''
      this.currentPage = 1
      this.fetchHistory()
    },

    handleSizeChange(size) {
      this.pageSize = size
      this.currentPage = 1
      this.fetchHistory()
    },

    handleCurrentChange(page) {
      this.currentPage = page
      this.fetchHistory()
    },

    indexMethod(index) {
      return (this.currentPage - 1) * this.pageSize + index + 1
    },

    goBack() {
      this.$router.push({ name: 'DeviceCards' })
    },
  },
}
</script>

<style scoped>
.device-history-container {
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
}

.page-subtitle {
  margin: 8px 0 0 0;
  color: #909399;
  font-size: 14px;
}

.filter-card {
  margin-bottom: 20px;
}

.data-table-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.card-header {
  font-weight: 500;
  font-size: 15px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  padding-top: 15px;
  border-top: 1px solid #e4e7ed;
}
</style>
