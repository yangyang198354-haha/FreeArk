<template>
  <div class="fault-management">
    <div class="page-header">
      <h2>故障管理</h2>
      <p class="page-subtitle">查看 MQTT 上报的设备故障历史记录，支持多维过滤与分页浏览</p>
      <p class="page-notice">
        故障历史数据来自 MQTT 驱动写入，与设备列表页的实时故障数量统计独立；
        如需实时快照，请查看设备面板。
      </p>
    </div>

    <!-- 只看未恢复 Toggle -->
    <div class="active-only-toggle">
      <el-switch
        v-model="filters.is_active_only"
        active-text="只看未恢复"
        inactive-text="显示全部"
        @change="handleSearch"
      />
    </div>

    <!-- 过滤条件区 -->
    <el-form :inline="true" class="filter-bar" @submit.prevent="handleSearch">
      <!-- 房号模糊搜索 -->
      <el-form-item label="房号">
        <el-input
          v-model="filters.specific_part"
          placeholder="输入房号模糊搜索"
          clearable
          style="width: 160px"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        />
      </el-form-item>

      <!-- 时间段选择器（默认最近 7 天） -->
      <el-form-item label="时间段">
        <el-date-picker
          v-model="filters.dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 260px"
          value-format="YYYY-MM-DD"
          @change="handleSearch"
        />
      </el-form-item>

      <!-- 故障类型多选 -->
      <el-form-item label="故障类型">
        <el-select
          v-model="filters.fault_types"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="选择故障类型"
          style="width: 180px"
          @change="handleSearch"
        >
          <el-option
            v-for="opt in faultTypeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <!-- 设备类型多选 -->
      <el-form-item label="设备类型">
        <el-select
          v-model="filters.sub_types"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="选择设备类型"
          style="width: 180px"
          @change="handleSearch"
        >
          <el-option
            v-for="opt in subTypeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <!-- 操作按钮 -->
      <el-form-item>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- 数据表格 -->
    <el-table
      v-loading="loading"
      :data="tableData"
      stripe
      border
      style="width: 100%"
      :header-cell-style="{ background: '#f5f7fa', color: '#606266' }"
    >
      <el-table-column prop="specific_part" label="房号" min-width="110" fixed />
      <el-table-column prop="device_sn" label="设备SN" min-width="100" />
      <el-table-column prop="fault_code" label="故障码" min-width="200" show-overflow-tooltip />
      <el-table-column prop="fault_message" label="故障描述" min-width="180" show-overflow-tooltip />
      <el-table-column prop="fault_type" label="故障类型" min-width="100">
        <template #default="{ row }">
          {{ faultTypeLabel(row.fault_type) }}
        </template>
      </el-table-column>
      <el-table-column prop="severity" label="严重级别" min-width="90">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity, row.is_active)" size="small">
            {{ row.severity === 'error' ? 'Error' : 'Warning' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="first_seen_at" label="首次发生" min-width="160">
        <template #default="{ row }">
          {{ formatDatetime(row.first_seen_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="last_seen_at" label="最后活跃" min-width="160">
        <template #default="{ row }">
          {{ formatDatetime(row.last_seen_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="recovered_at" label="恢复时间" min-width="160">
        <template #default="{ row }">
          {{ row.recovered_at ? formatDatetime(row.recovered_at) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" min-width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'danger' : 'success'" size="small">
            {{ row.is_active ? '未恢复' : '已恢复' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="120" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            @click="handleViewDevicePanel(row)"
          >
            查看设备面板
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handlePageSizeChange"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()

// ---------------------------------------------------------------------------
// 过滤状态
// ---------------------------------------------------------------------------

const today = new Date()
const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)

const defaultDateRange = [
  sevenDaysAgo.toISOString().slice(0, 10),
  today.toISOString().slice(0, 10),
]

const filters = reactive({
  specific_part: '',
  fault_types: [],
  sub_types: [],
  is_active_only: false,
  dateRange: [...defaultDateRange],
})

// ---------------------------------------------------------------------------
// 表格状态
// ---------------------------------------------------------------------------

const tableData = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)

// ---------------------------------------------------------------------------
// 下拉选项状态
// ---------------------------------------------------------------------------

const faultTypeOptions = ref([])
const subTypeOptions = ref([])

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

function formatDatetime(isoStr) {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-')
  } catch {
    return isoStr
  }
}

function faultTypeLabel(faultType) {
  const opt = faultTypeOptions.value.find(o => o.value === faultType)
  return opt ? opt.label : faultType
}

/**
 * 根据 severity 和 is_active 返回 Element Plus Tag 的 type。
 *   活跃 + error   → danger（红色）
 *   活跃 + warning → warning（橙色）
 *   已恢复         → ''（灰色）
 */
function severityTagType(severity, isActive) {
  if (!isActive) return ''
  return severity === 'error' ? 'danger' : 'warning'
}

// ---------------------------------------------------------------------------
// API 调用
// ---------------------------------------------------------------------------

async function fetchCategories() {
  try {
    const resp = await axios.get('/api/devices/fault-event-categories/')
    faultTypeOptions.value = resp.data.fault_types || []
    subTypeOptions.value = resp.data.sub_types || []
  } catch (err) {
    console.error('fetchCategories 失败:', err)
  }
}

async function fetchFaultEvents() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
    }

    if (filters.specific_part.trim()) {
      params.specific_part = filters.specific_part.trim()
    }

    if (filters.fault_types.length > 0) {
      // axios 会将数组自动序列化为重复参数：fault_type=comm&fault_type=sensor
      params.fault_type = filters.fault_types
    }

    if (filters.sub_types.length > 0) {
      params.sub_type = filters.sub_types
    }

    if (filters.is_active_only) {
      params.is_active = 'true'
    }

    // 时间范围
    if (filters.dateRange && filters.dateRange.length === 2) {
      params.first_seen_after = filters.dateRange[0] + 'T00:00:00'
      params.first_seen_before = filters.dateRange[1] + 'T23:59:59'
    } else {
      // 默认最近 7 天
      params.first_seen_after = sevenDaysAgo.toISOString().slice(0, 10) + 'T00:00:00'
    }

    const resp = await axios.get('/api/devices/fault-events/', { params })
    tableData.value = resp.data.results || []
    total.value = resp.data.count || 0
  } catch (err) {
    console.error('fetchFaultEvents 失败:', err)
    tableData.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// 事件处理
// ---------------------------------------------------------------------------

function handleSearch() {
  currentPage.value = 1
  fetchFaultEvents()
}

function handleReset() {
  filters.specific_part = ''
  filters.fault_types = []
  filters.sub_types = []
  filters.is_active_only = false
  filters.dateRange = [...defaultDateRange]
  currentPage.value = 1
  pageSize.value = 20
  fetchFaultEvents()
}

function handlePageChange(page) {
  currentPage.value = page
  fetchFaultEvents()
}

function handlePageSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
  fetchFaultEvents()
}

/**
 * 在新标签页打开指定房号的设备面板（AC-FM-05-02）。
 * OQ-12 裁决：不附加子设备高亮参数。
 */
function handleViewDevicePanel(row) {
  const route = router.resolve({
    name: 'DeviceCards',
    query: { specific_part: row.specific_part },
  })
  window.open(route.href, '_blank')
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

onMounted(async () => {
  await fetchCategories()
  await fetchFaultEvents()
})
</script>

<style scoped>
.fault-management {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0 0 6px 0;
  font-size: 20px;
  color: #303133;
}

.page-subtitle {
  margin: 0 0 4px 0;
  font-size: 13px;
  color: #909399;
}

.page-notice {
  margin: 0;
  font-size: 12px;
  color: #e6a23c;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 4px;
  padding: 6px 10px;
  display: inline-block;
}

.active-only-toggle {
  margin-bottom: 16px;
}

.filter-bar {
  background: #f9fafc;
  padding: 16px 16px 8px;
  border-radius: 6px;
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
