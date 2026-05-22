<template>
  <div class="plc-write-record">
    <div class="page-header">
      <h2>设置记录</h2>
      <!-- REQ-FUNC-030 / AC-017-06 -->
      <p class="page-subtitle">查看 PLC 参数写入操作的历史记录</p>
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
      <el-table-column label="写前值" width="120" align="center">
        <template #default="{ row }">{{ formatValue(row.param_name, row.old_value) }}</template>
      </el-table-column>
      <el-table-column label="目标值" width="120" align="center">
        <template #default="{ row }">{{ formatValue(row.param_name, row.new_value) }}</template>
      </el-table-column>
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

    // Q12 决策：param_name -> value_options 映射缓存，用于 raw_value (label) 格式展示
    const paramLabelCache = ref({})

    const fetchParamOptions = async (specificPart) => {
      if (!specificPart || paramLabelCache.value[specificPart] !== undefined) return
      try {
        const data = await api.get(`/api/device-settings/params/${encodeURIComponent(specificPart)}/`)
        const map = {}
        for (const group of data.groups || []) {
          for (const p of group.params || []) {
            if (p.value_options && p.value_options.length > 0) {
              map[p.param_name] = p.value_options
            }
          }
        }
        paramLabelCache.value[specificPart] = map
      } catch {
        paramLabelCache.value[specificPart] = {}
      }
    }

    const getLabel = (specificPart, paramName, rawValue) => {
      const spMap = paramLabelCache.value[specificPart]
      if (!spMap) return null
      const opts = spMap[paramName]
      if (!opts) return null
      const found = opts.find(o => String(o.raw) === String(rawValue))
      return found ? found.label : null
    }

    const formatValue = (paramName, rawValue) => {
      if (rawValue === null || rawValue === undefined || rawValue === '') return '—'
      // 在当前 tableData 的 specific_part 中查标签
      const label = (() => {
        for (const row of tableData.value) {
          if (row.param_name === paramName) {
            const l = getLabel(row.specific_part, paramName, rawValue)
            if (l !== null) return l
          }
        }
        return null
      })()
      if (label !== null) return `${rawValue} (${label})`
      return rawValue
    }

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
        // 拉取各 specific_part 的参数选项，以便展示标签
        const parts = [...new Set(tableData.value.map(r => r.specific_part).filter(Boolean))]
        for (const sp of parts) {
          await fetchParamOptions(sp)
        }
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
      statusLabel, statusTagType, formatDateTime, formatValue,
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

/* REQ-FUNC-030: 副标题 */
.page-subtitle {
  margin: 5px 0 0 0;
  color: #909399;
  font-size: 13px;
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
