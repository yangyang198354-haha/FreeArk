<template>
  <div class="plc-write-record">
    <div class="page-header">
      <h2>设置记录</h2>
    </div>

    <div class="filter-bar">
      <el-input
        v-model="filterSpecificPart"
        placeholder="专有部分（如 3-1-7-702）"
        clearable
        style="width:200px; margin-right:8px"
      />
      <el-input
        v-model="filterOperator"
        placeholder="操作人"
        clearable
        style="width:140px; margin-right:8px"
      />
      <el-select
        v-model="filterStatus"
        placeholder="状态"
        clearable
        style="width:120px; margin-right:8px"
      >
        <el-option label="待回执" value="pending" />
        <el-option label="写入成功" value="success" />
        <el-option label="写入失败" value="failed" />
        <el-option label="超时" value="timeout" />
      </el-select>
      <el-date-picker
        v-model="filterTimeRange"
        type="daterange"
        range-separator="~"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        style="width:240px; margin-right:8px"
      />
      <el-button type="primary" @click="handleSearch">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="tableData"
      stripe
      border
      size="small"
      style="width:100%; margin-top:16px"
    >
      <el-table-column label="请求ID" prop="request_id" width="200" show-overflow-tooltip />
      <el-table-column label="专有部分" prop="specific_part" width="120" />
      <el-table-column label="参数" prop="param_name" width="180" show-overflow-tooltip />
      <el-table-column label="写前值" prop="old_value" width="80" align="center" />
      <el-table-column label="目标值" prop="new_value" width="80" align="center" />
      <el-table-column label="操作人" prop="operator" width="100" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="下发时间" width="160">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="回执时间" width="160">
        <template #default="{ row }">{{ formatDateTime(row.acked_at) }}</template>
      </el-table-column>
      <el-table-column label="失败原因" prop="error_message" show-overflow-tooltip />
    </el-table>

    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        background
        @size-change="handlePageSizeChange"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'

export default {
  name: 'PlcWriteRecordView',

  setup() {
    const loading = ref(false)
    const tableData = ref([])
    const total = ref(0)
    const currentPage = ref(1)
    const pageSize = ref(20)

    const filterSpecificPart = ref('')
    const filterOperator = ref('')
    const filterStatus = ref('')
    const filterTimeRange = ref(null)

    const fetchList = async () => {
      loading.value = true
      try {
        const params = { page: currentPage.value, page_size: pageSize.value }
        if (filterSpecificPart.value) params.specific_part = filterSpecificPart.value
        if (filterOperator.value) params.operator = filterOperator.value
        if (filterStatus.value) params.status = filterStatus.value
        if (filterTimeRange.value && filterTimeRange.value[0]) {
          params.start_time = filterTimeRange.value[0]
          params.end_time = filterTimeRange.value[1]
        }
        const qs = new URLSearchParams(params).toString()
        const res = await api.get(`/api/device-settings/records/?${qs}`)
        tableData.value = res.results || []
        total.value = res.count || 0
      } catch {
        ElMessage.error('获取设置记录失败')
        tableData.value = []
        total.value = 0
      } finally {
        loading.value = false
      }
    }

    const handleSearch = () => {
      currentPage.value = 1
      fetchList()
    }

    const handleReset = () => {
      filterSpecificPart.value = ''
      filterOperator.value = ''
      filterStatus.value = ''
      filterTimeRange.value = null
      currentPage.value = 1
      fetchList()
    }

    const handlePageChange = (page) => {
      currentPage.value = page
      fetchList()
    }

    const handlePageSizeChange = (size) => {
      pageSize.value = size
      currentPage.value = 1
      fetchList()
    }

    const statusLabel = (s) => {
      const map = { pending: '待回执', success: '写入成功', failed: '写入失败', timeout: '超时' }
      return map[s] || s
    }

    const statusTagType = (s) => {
      if (s === 'success') return 'success'
      if (s === 'failed') return 'danger'
      if (s === 'timeout') return 'warning'
      return 'info'
    }

    const formatDateTime = (iso) => {
      if (!iso) return '—'
      try {
        const d = new Date(iso)
        const pad = n => String(n).padStart(2, '0')
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
      } catch {
        return iso
      }
    }

    onMounted(fetchList)

    return {
      loading, tableData, total, currentPage, pageSize,
      filterSpecificPart, filterOperator, filterStatus, filterTimeRange,
      handleSearch, handleReset, handlePageChange, handlePageSizeChange,
      statusLabel, statusTagType, formatDateTime,
    }
  },
}
</script>

<style scoped>
.plc-write-record {
  padding: 0;
}
.page-header {
  margin-bottom: 16px;
}
.page-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}
.filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}
.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
