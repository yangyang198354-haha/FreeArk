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

    <!-- 过滤条件区 -->
    <el-form :inline="true" class="filter-bar" @submit.prevent="handleSearch">
      <!-- 状态三态筛选（FR-FM-UX-04，替换原 el-switch，AQ-03：重置回'true'）-->
      <el-form-item label="状态">
        <el-radio-group v-model="filterIsActive" @change="handleSearch">
          <el-radio-button value="true">未恢复</el-radio-button>
          <el-radio-button value="false">已恢复</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <!-- 房号级联选择器（FR-FM-UX-02，替换原 el-input，AQ-02：getElementById 模式）-->
      <el-form-item label="房号">
        <div style="display: inline-block; vertical-align: middle; width: 180px;">
          <CascadingSelector
            building-input-id="fmBuilding"
            building-input-name="fmBuilding"
            unit-input-id="fmUnit"
            unit-input-name="fmUnit"
            room-input-id="fmRoom"
            room-input-name="fmRoom"
            ref="fmCascadingSelectorRef"
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

      <!-- 房间多选（v0.6.4-FM-ROOM，FR-FM-009-filter）-->
      <el-form-item label="房间">
        <el-select
          v-model="filters.room_names"
          multiple
          collapse-tags
          collapse-tags-tooltip
          clearable
          placeholder="全部房间"
          style="width: 160px"
          @change="handleSearch"
        >
          <el-option
            v-for="room in ROOM_OPTIONS"
            :key="room"
            :label="room"
            :value="room"
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
      <!-- 设备名称列（FR-FM-UX-03，三级降级渲染：device_name → device_type_label → device_sn+未识别）-->
      <el-table-column label="设备名称" min-width="120">
        <template #default="{ row }">
          <span v-if="row.device_name">{{ row.device_name }}</span>
          <span v-else-if="row.device_type_label">{{ row.device_type_label }}</span>
          <span v-else>
            {{ row.device_sn }}
            <el-tag size="small" type="info" style="margin-left: 4px;">未识别</el-tag>
          </span>
        </template>
      </el-table-column>
      <!-- 房间列（v0.6.4-FM-ROOM，FR-FM-009-display）-->
      <el-table-column prop="room_name" label="房间" width="100" align="center">
        <template #default="scope">
          {{ scope.row.room_name || '-' }}
        </template>
      </el-table-column>
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
      <!-- REQ-UI-003：文案"查看设备面板" → "设备面板" -->
      <el-table-column label="操作" min-width="100" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            @click="handleViewDevicePanel(row)"
          >
            设备面板
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
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'
import CascadingSelector from '@/components/CascadingSelector.vue'

const router = useRouter()
const route = useRoute()  // FR-FM-UX-04：URL 参数优先（AQ-02 补充 useRoute import）

// ---------------------------------------------------------------------------
// 房号级联选择器 ref（AQ-02：getElementById 模式，ref 仅用于 clearSelection）
// ---------------------------------------------------------------------------

const fmCascadingSelectorRef = ref(null)

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

// 房间过滤器选项（v0.6.4-FM-ROOM，静态写死，与后端 VALID_ROOM_NAMES 保持一致）
const ROOM_OPTIONS = ['客厅', '主卧', '次卧', '儿童房', '书房']

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
  fault_types: [],
  sub_types: [],
  room_names: [],   // 新增（v0.6.4-FM-ROOM）
  dateRange: [...defaultDateRange],
})

// FR-FM-UX-04：三态筛选变量（替换原 is_active_only bool）
// 取值：'true'（未恢复，默认）/ 'false'（已恢复）/ 'all'（全部）
// AQ-03 裁决：重置时恢复为 'true'，与首次进入行为一致
const filterIsActive = ref('true')

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

/**
 * 从 CascadingSelector 的 hidden input 读取选中值，组装 specific_part 参数。
 * ADR-UX-02：icontains 容错方案，3 段 room_no 直接作为 icontains 查询参数。
 * AQ-02：使用 document.getElementById 模式（与 DeviceManagementDeviceListView 第310-319行一致）。
 *
 * 组装规则：
 *   building + unit + room → "{building}-{unit}-{room}"（如 "3-1-702"，icontains 命中 "3-1-7-702"）
 *   building + unit        → "{building}-{unit}"（如 "3-1"，命中 3栋1单元全部房间）
 *   building only          → "{building}"（如 "3"，命中 3栋全部）
 *   均空                   → ''（不传 specific_part 参数）
 */
function getSelectedSpecificPart() {
  const building = document.getElementById('fmBuilding')?.value || ''
  const unit = document.getElementById('fmUnit')?.value || ''
  const room = document.getElementById('fmRoom')?.value || ''

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
    // BUG-FM-003 修复：axios 1.x 默认将数组序列化为 fault_type[]=comm&fault_type[]=sensor
    // （带方括号），后端 getlist('fault_type') 无法识别，导致过滤器无效。
    // 修复方案：改用 URLSearchParams 手动 append，保证生成
    // fault_type=comm&fault_type=sensor（无方括号）的重复参数形式。
    const qs = new URLSearchParams()

    qs.append('page', currentPage.value)
    qs.append('page_size', pageSize.value)

    // FR-FM-UX-02：房号过滤（CascadingSelector → specific_part，icontains 容错）
    const sp = getSelectedSpecificPart()
    if (sp) {
      qs.append('specific_part', sp)
    }

    // 故障类型多值过滤（BUG-FM-003 修复：逐一 append，生成重复参数名）
    for (const ft of filters.fault_types) {
      qs.append('fault_type', ft)
    }

    // 设备类型多值过滤（BUG-FM-003 修复：同上）
    for (const st of filters.sub_types) {
      qs.append('sub_type', st)
    }

    // 房间多值过滤（v0.6.4-FM-ROOM）
    for (const rn of filters.room_names) {
      qs.append('room_name', rn)
    }

    // FR-FM-UX-04：三态 is_active 传参（ADR-UX-04）
    if (filterIsActive.value === 'true') {
      qs.append('is_active', 'true')
    } else if (filterIsActive.value === 'false') {
      qs.append('is_active', 'false')
    }
    // filterIsActive === 'all' 时不传 is_active 参数，后端返回全部记录

    // 时间范围
    if (filters.dateRange && filters.dateRange.length === 2) {
      qs.append('first_seen_after', filters.dateRange[0] + 'T00:00:00')
      qs.append('first_seen_before', filters.dateRange[1] + 'T23:59:59')
    } else {
      // 默认最近 7 天
      qs.append('first_seen_after', sevenDaysAgo.toISOString().slice(0, 10) + 'T00:00:00')
    }

    const resp = await axios.get('/api/devices/fault-events/?' + qs.toString())
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
  // FR-FM-UX-02：清空 CascadingSelector（通过 ref 调用 clearSelection）
  if (fmCascadingSelectorRef.value) {
    fmCascadingSelectorRef.value.clearSelection()
  }
  filters.fault_types = []
  filters.sub_types = []
  filters.room_names = []   // 新增（v0.6.4-FM-ROOM）
  filters.dateRange = [...defaultDateRange]
  // FR-FM-UX-04 + AQ-03：重置回默认"未恢复"（与首次进入行为一致）
  filterIsActive.value = 'true'
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
 * REQ-UI-003 / REQ-UI-004：同标签页内跳转到设备面板（用户方案2，2026-05-30）。
 * 通过 router.push 携带 from=fault-management，设备面板"返回"按钮
 * 读取该参数后跳回故障管理页。
 * 原 window.open('_blank') 方式已废弃。
 */
function handleViewDevicePanel(row) {
  router.push({
    name: 'DeviceCards',
    query: { specific_part: row.specific_part, from: 'fault-management' },
  })
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

onMounted(async () => {
  // FR-FM-UX-04：URL 参数优先于前端默认值（ADR-UX-04）
  const urlIsActive = route.query.is_active
  if (urlIsActive === 'true' || urlIsActive === 'false') {
    filterIsActive.value = urlIsActive
  } else {
    filterIsActive.value = 'true'  // 默认"未恢复"
  }

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
