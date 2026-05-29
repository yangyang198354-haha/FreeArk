<template>
  <div class="condensation-warning">
    <div class="page-header">
      <h2>结露预警</h2>
      <p class="page-subtitle">查看 MQTT 上报的结露报警历史记录，支持状态/房号/时间段过滤与分页浏览</p>
      <p class="page-notice">
        结露预警数据来自 MQTT 驱动写入（freeark-condensation-consumer），与设备列表页实时数据独立；
        大屏在线状态为查询时实时计算（15 分钟内活跃即为在线）。
      </p>
    </div>

    <!-- 过滤条件区 -->
    <el-form :inline="true" class="filter-bar" @submit.prevent="handleSearch">
      <!-- 状态三态筛选（镜像故障管理，默认"未回复"） -->
      <el-form-item label="状态">
        <el-radio-group v-model="filterIsActive" @change="handleSearch">
          <el-radio-button value="true">未回复</el-radio-button>
          <el-radio-button value="false">已回复</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <!-- 房号级联选择器（复用 CascadingSelector，getElementById 模式，与故障管理一致） -->
      <el-form-item label="房号">
        <div style="display: inline-block; vertical-align: middle; width: 180px;">
          <CascadingSelector
            building-input-id="cwBuilding"
            building-input-name="cwBuilding"
            unit-input-id="cwUnit"
            unit-input-name="cwUnit"
            room-input-id="cwRoom"
            room-input-name="cwRoom"
            ref="cwCascadingSelectorRef"
          />
        </div>
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

      <!-- 操作按钮 -->
      <el-form-item>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- 数据表格（12 列） -->
    <el-table
      v-loading="loading"
      :data="warningList"
      stripe
      border
      style="width: 100%"
      :header-cell-style="{ background: '#f5f7fa', color: '#606266' }"
    >
      <!-- 列1：房号 -->
      <el-table-column prop="specific_part" label="房号" min-width="120" fixed />

      <!-- 列2：房间 -->
      <el-table-column prop="room_name" label="房间" width="90" align="center">
        <template #default="{ row }">
          {{ row.room_name || '-' }}
        </template>
      </el-table-column>

      <!-- 列3：大屏是否在线（ADR-CW-05，实时计算注入） -->
      <el-table-column label="大屏在线" width="90" align="center">
        <template #default="{ row }">
          <span :style="{ color: row.is_screen_online ? '#67C23A' : '#909399' }">
            {{ row.is_screen_online ? '在线' : '离线' }}
          </span>
        </template>
      </el-table-column>

      <!-- 列4：系统开关（ADR-CW-04：on/off/unknown，RISK-CW-ARCH-01 双源处理后归一） -->
      <el-table-column label="系统开关" width="90" align="center">
        <template #default="{ row }">
          <span v-if="row.system_switch === 'on'" style="color: #67C23A;">开启</span>
          <span v-else-if="row.system_switch === 'off'" style="color: #909399;">关闭</span>
          <span v-else style="color: #C0C4CC;">-</span>
        </template>
      </el-table-column>

      <!-- 列5：预警类型 -->
      <el-table-column prop="warning_type" label="预警类型" min-width="90" />

      <!-- 列6：预警内容 -->
      <el-table-column prop="warning_message" label="预警内容" min-width="90" />

      <!-- 列7：露点温度 -->
      <el-table-column label="露点温度" width="90" align="center">
        <template #default="{ row }">
          {{ row.dew_point_temp ? row.dew_point_temp + ' °C' : '-' }}
        </template>
      </el-table-column>

      <!-- 列8：NTC温度 -->
      <el-table-column label="NTC温度" width="90" align="center">
        <template #default="{ row }">
          {{ row.ntc_temp ? row.ntc_temp + ' °C' : '-' }}
        </template>
      </el-table-column>

      <!-- 列9：湿度 -->
      <el-table-column label="湿度" width="75" align="center">
        <template #default="{ row }">
          {{ row.humidity ? row.humidity + ' %' : '-' }}
        </template>
      </el-table-column>

      <!-- 列10：预警发生时间 -->
      <el-table-column label="预警发生时间" min-width="160">
        <template #default="{ row }">
          {{ formatDatetime(row.first_seen_at) }}
        </template>
      </el-table-column>

      <!-- 列11：最后活跃 -->
      <el-table-column label="最后活跃" min-width="160">
        <template #default="{ row }">
          {{ formatDatetime(row.last_seen_at) }}
        </template>
      </el-table-column>

      <!-- 列12：恢复时间 -->
      <el-table-column label="恢复时间" min-width="160">
        <template #default="{ row }">
          {{ row.recovered_at ? formatDatetime(row.recovered_at) : '-' }}
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页（与 FaultManagementView 完全一致） -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="totalCount"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handlePageSizeChange"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import CascadingSelector from '@/components/CascadingSelector.vue'

const route = useRoute()

// ---------------------------------------------------------------------------
// 房号级联选择器 ref（AQ-02 模式：getElementById 读值，ref 仅用于 clearSelection）
// ---------------------------------------------------------------------------

const cwCascadingSelectorRef = ref(null)

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
  dateRange: [...defaultDateRange],
})

// 状态三态筛选（默认"未回复"，与故障管理对齐但 label 用"回复"而非"恢复"）
const filterIsActive = ref('true')

// ---------------------------------------------------------------------------
// 表格状态
// ---------------------------------------------------------------------------

const warningList = ref([])
const totalCount = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/**
 * 格式化 ISO8601 时间字符串为本地时间（复用故障管理的格式化函数）。
 */
function formatDatetime(isoStr) {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-')
  } catch {
    return isoStr
  }
}

/**
 * 从 CascadingSelector 的 hidden input 读取选中值，组装 specific_part 参数。
 * 镜像 FaultManagementView.getSelectedSpecificPart（AQ-02 getElementById 模式）。
 */
function getSelectedSpecificPart() {
  const building = document.getElementById('cwBuilding')?.value || ''
  const unit = document.getElementById('cwUnit')?.value || ''
  const room = document.getElementById('cwRoom')?.value || ''

  if (building && unit && room) {
    return `${building}-${unit}-${room}`
  } else if (building && unit) {
    return `${building}-${unit}`
  } else if (building) {
    return building
  }
  return ''
}

// ---------------------------------------------------------------------------
// API 调用
// ---------------------------------------------------------------------------

async function fetchWarnings() {
  loading.value = true
  try {
    // BUG-FM-003 修复经验：使用 URLSearchParams 手动 append，生成无方括号的重复参数
    const qs = new URLSearchParams()

    qs.append('page', currentPage.value)
    qs.append('page_size', pageSize.value)

    // 房号过滤（CascadingSelector → specific_part，段数映射由后端处理）
    const sp = getSelectedSpecificPart()
    if (sp) {
      qs.append('specific_part', sp)
    }

    // is_active 三态
    if (filterIsActive.value === 'true') {
      qs.append('is_active', 'true')
    } else if (filterIsActive.value === 'false') {
      qs.append('is_active', 'false')
    }
    // filterIsActive === 'all' 时不传 is_active，后端返回全部记录

    // 时间范围
    if (filters.dateRange && filters.dateRange.length === 2) {
      qs.append('first_seen_after', filters.dateRange[0] + 'T00:00:00')
      qs.append('first_seen_before', filters.dateRange[1] + 'T23:59:59')
    } else {
      // 默认最近 7 天
      qs.append('first_seen_after', sevenDaysAgo.toISOString().slice(0, 10) + 'T00:00:00')
    }

    const resp = await axios.get('/api/devices/condensation-warning-events/?' + qs.toString())
    warningList.value = resp.data.results || []
    totalCount.value = resp.data.count || 0
  } catch (err) {
    console.error('fetchWarnings 失败:', err)
    warningList.value = []
    totalCount.value = 0
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// 事件处理
// ---------------------------------------------------------------------------

function handleSearch() {
  currentPage.value = 1
  fetchWarnings()
}

function handleReset() {
  if (cwCascadingSelectorRef.value) {
    cwCascadingSelectorRef.value.clearSelection()
  }
  filters.dateRange = [...defaultDateRange]
  filterIsActive.value = 'true'
  currentPage.value = 1
  pageSize.value = 20
  fetchWarnings()
}

function handlePageChange(page) {
  currentPage.value = page
  fetchWarnings()
}

function handlePageSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
  fetchWarnings()
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

onMounted(async () => {
  // URL 参数优先（与故障管理一致）
  const urlIsActive = route.query.is_active
  if (urlIsActive === 'true' || urlIsActive === 'false') {
    filterIsActive.value = urlIsActive
  } else {
    filterIsActive.value = 'true'
  }

  await fetchWarnings()
})
</script>

<style scoped>
.condensation-warning {
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
