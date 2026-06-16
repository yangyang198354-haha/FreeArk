<template>
  <div class="worklog-view">
    <!-- 页头 -->
    <div class="wl-page-head">
      <div class="wl-head-accent"></div>
      <div class="wl-head-text">
        <h2 class="wl-head-title">巡检智能体工作日志</h2>
        <p class="wl-head-sub">记录 inspection-agent 对每条故障/预警事件的决策全过程：委托调用、写提案拦截、工单创建结论</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="fetchLogs" style="margin-left:auto;align-self:center;">刷新</el-button>
    </div>

    <!-- 过滤栏 -->
    <div class="wl-filters">
      <el-select v-model="filters.event_type" placeholder="事件类型" clearable style="width:160px">
        <el-option label="故障事件" value="fault_event" />
        <el-option label="结露预警事件" value="condensation_warning_event" />
      </el-select>
      <el-input v-model="filters.specific_part" placeholder="房号（模糊）" clearable style="width:160px" />
      <el-select v-model="filters.step" placeholder="决策步骤" clearable style="width:160px">
        <el-option v-for="(label, code) in STEP_LABELS" :key="code" :label="label" :value="code" />
      </el-select>
      <el-select v-model="filters.result" placeholder="结果" clearable style="width:120px">
        <el-option label="成功" value="SUCCESS" />
        <el-option label="已拦截" value="BLOCKED" />
        <el-option label="错误" value="ERROR" />
        <el-option label="已跳过" value="SKIPPED" />
        <el-option label="信息" value="INFO" />
      </el-select>
      <el-date-picker
        v-model="filters.dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width:260px"
      />
      <el-button type="primary" @click="handleQuery">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
    </div>

    <!-- 日志表格 -->
    <el-table v-loading="loading" :data="logs" stripe border style="width:100%;margin-top:14px">
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="房号" width="120">
        <template #default="{ row }">
          <el-link type="primary" @click="filterByPart(row.specific_part)">{{ row.specific_part || '—' }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="event_type_display" label="事件类型" width="110" />
      <el-table-column prop="source_event_id" label="来源ID" width="90" align="center" />
      <el-table-column label="决策步骤" width="150">
        <template #default="{ row }">
          <el-tag :type="stepTagType(row.step)" size="small">{{ STEP_LABELS[row.step] || row.step }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结果" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="resultTagType(row.result)" size="small">{{ row.result }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="work_order_ticket" label="工单编号" width="160">
        <template #default="{ row }">{{ row.work_order_ticket || '—' }}</template>
      </el-table-column>
      <el-table-column label="详情" min-width="100">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="showDetail(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="wl-pagination">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handlePageSizeChange"
        @current-change="fetchLogs"
      />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="决策步骤详情" width="640px" destroy-on-close>
      <el-descriptions :column="2" border size="small" v-if="detailRow">
        <el-descriptions-item label="时间">{{ formatTime(detailRow.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="房号">{{ detailRow.specific_part }}</el-descriptions-item>
        <el-descriptions-item label="事件">{{ detailRow.event_type_display }} #{{ detailRow.source_event_id }}</el-descriptions-item>
        <el-descriptions-item label="步骤/结果">{{ STEP_LABELS[detailRow.step] || detailRow.step }} / {{ detailRow.result }}</el-descriptions-item>
      </el-descriptions>
      <div class="wl-detail-label">step_detail：</div>
      <pre class="wl-detail-json">{{ prettyDetail }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

// 步骤代码 → 中文（与后端 InspectionLog.STEP_CHOICES 对齐）
const STEP_LABELS = {
  PROCESS_STARTED: '开始处理',
  EVENT_SKIPPED: '事件已恢复跳过',
  DELEGATION_CALLED: '子专家委托',
  DELEGATION_ERROR: '委托异常',
  WRITE_PROPOSAL: 'LLM写提案',
  WRITE_BLOCKED: '写提案被拦截',
  WRITE_EXECUTED: '写操作执行',
  WORKORDER_CREATED: '工单创建',
  WORKORDER_EXISTED: '工单已存在',
  DECISION_TIMEOUT: '决策超时兜底',
  DECISION_ERROR: '决策异常兜底',
  PROCESS_COMPLETED: '处置完成',
}

const today = new Date()
const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)
const defaultDateRange = [sevenDaysAgo.toISOString().slice(0, 10), today.toISOString().slice(0, 10)]

const filters = reactive({
  event_type: '',
  specific_part: '',
  step: '',
  result: '',
  dateRange: [...defaultDateRange],
})

const logs = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)

const detailVisible = ref(false)
const detailRow = ref(null)
const prettyDetail = computed(() => {
  if (!detailRow.value) return ''
  try {
    return JSON.stringify(detailRow.value.step_detail || {}, null, 2)
  } catch (e) {
    return String(detailRow.value.step_detail)
  }
})

function stepTagType(step) {
  if (step === 'WORKORDER_CREATED' || step === 'WRITE_EXECUTED' || step === 'PROCESS_COMPLETED') return 'success'
  if (step === 'WRITE_BLOCKED' || step === 'WRITE_PROPOSAL') return 'warning'
  if (step === 'DECISION_TIMEOUT' || step === 'DECISION_ERROR' || step === 'DELEGATION_ERROR') return 'danger'
  if (step === 'DELEGATION_CALLED') return 'info'
  return 'info'
}

function resultTagType(result) {
  if (result === 'SUCCESS') return 'success'
  if (result === 'BLOCKED') return 'warning'
  if (result === 'ERROR') return 'danger'
  return 'info'
}

function formatTime(iso) {
  if (!iso) return '—'
  return String(iso).replace('T', ' ').slice(0, 19)
}

async function fetchLogs() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (filters.event_type) params.event_type = filters.event_type
    if (filters.specific_part) params.specific_part = filters.specific_part
    if (filters.step) params.step = filters.step
    if (filters.result) params.result = filters.result
    if (filters.dateRange && filters.dateRange.length === 2) {
      params.date_from = filters.dateRange[0]
      params.date_to = `${filters.dateRange[1]} 23:59:59`
    }
    const resp = await api.get('/api/inspection/logs/', params)
    if (resp && resp.success) {
      logs.value = resp.data || []
      total.value = resp.total || 0
    } else {
      ElMessage.error('获取工作日志失败')
    }
  } catch (err) {
    ElMessage.error('获取工作日志失败：' + (err.message || '网络错误'))
  } finally {
    loading.value = false
  }
}

function handleQuery() {
  currentPage.value = 1
  fetchLogs()
}

function handleReset() {
  filters.event_type = ''
  filters.specific_part = ''
  filters.step = ''
  filters.result = ''
  filters.dateRange = [...defaultDateRange]
  currentPage.value = 1
  fetchLogs()
}

function handlePageSizeChange() {
  currentPage.value = 1
  fetchLogs()
}

function filterByPart(part) {
  if (!part) return
  filters.specific_part = part
  handleQuery()
}

function showDetail(row) {
  detailRow.value = row
  detailVisible.value = true
}

onMounted(fetchLogs)
</script>

<style scoped>
.worklog-view { padding: 0; }

.wl-page-head {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3, 12px);
  margin-bottom: var(--space-5, 20px);
  padding-bottom: var(--space-4, 16px);
  border-bottom: 1px solid var(--line, #e5e7eb);
}
.wl-head-accent {
  width: 3px; min-height: 38px; border-radius: 2px;
  background: linear-gradient(180deg, var(--violet, #a78bfa), var(--acc, #3b82f6));
  flex-shrink: 0; margin-top: 2px;
}
.wl-head-title {
  margin: 0 0 4px 0; color: var(--ink-0, #111);
  font-size: var(--font-size-lg, 18px); font-weight: 600; line-height: 1.2;
}
.wl-head-sub { margin: 0; color: var(--ink-2, #6b7280); font-size: var(--font-size-sm, 13px); }

.wl-filters {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
}
.wl-pagination { margin-top: 14px; display: flex; justify-content: flex-end; }

.wl-detail-label { margin: 14px 0 6px; font-size: 13px; color: var(--ink-2, #6b7280); font-weight: 500; }
.wl-detail-json {
  background: rgba(5,10,20,0.8); color: #c7d4ea; padding: 12px 16px;
  border-radius: 6px; border: 1px solid var(--line, #e5e7eb);
  font-size: 12px; font-family: var(--font-family-mono, monospace); line-height: 1.6;
  overflow: auto; max-height: 360px; white-space: pre-wrap; word-break: break-all;
}
</style>
