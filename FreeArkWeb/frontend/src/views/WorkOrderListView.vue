<template>
  <div class="wo-view">
    <!-- 页头 -->
    <div class="wo-page-head">
      <div class="wo-head-accent"></div>
      <div class="wo-head-text">
        <h2 class="wo-head-title">巡检工单</h2>
        <p class="wo-head-sub">巡检智能体的人工处置出口：查看诊断结论、对被拦截的写处置建议审批执行；来源故障已恢复的工单会标记提示</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="fetchList" style="margin-left:auto;align-self:center;">刷新</el-button>
    </div>

    <!-- 过滤栏 -->
    <div class="wo-filters">
      <el-select v-model="filters.status" placeholder="工单状态" clearable style="width:140px">
        <el-option label="待处理" value="OPEN" />
        <el-option label="处理中" value="IN_PROGRESS" />
        <el-option label="已解决" value="RESOLVED" />
        <el-option label="已取消" value="CANCELLED" />
      </el-select>
      <el-select v-model="filters.source_event_type" placeholder="来源类型" clearable style="width:150px">
        <el-option label="故障事件" value="fault_event" />
        <el-option label="结露预警事件" value="condensation_warning_event" />
      </el-select>
      <el-select v-model="filters.write_status" placeholder="写提案" clearable style="width:140px">
        <el-option label="待审批执行" value="PENDING" />
        <el-option label="已执行" value="EXECUTED" />
        <el-option label="执行失败" value="FAILED" />
        <el-option label="无写提案" value="NONE" />
      </el-select>
      <el-input v-model="filters.specific_part" placeholder="房号/设备（模糊）" clearable style="width:170px" />
      <el-input v-model="filters.ticket_id" placeholder="工单编号" clearable style="width:170px" />
      <el-button type="primary" @click="handleQuery">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
    </div>

    <!-- 工单表格 -->
    <el-table v-loading="loading" :data="rows" stripe border style="width:100%;margin-top:14px">
      <el-table-column label="工单编号" width="170">
        <template #default="{ row }">
          <el-link type="primary" @click="openDetail(row)">{{ row.ticket_id }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="affected_device" label="受影响设备" min-width="170" show-overflow-tooltip />
      <el-table-column prop="symptom" label="症状" min-width="150" show-overflow-tooltip />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_display }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="写提案" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="writeTagType(row.write_status)" size="small">{{ WRITE_LABELS[row.write_status] || row.write_status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源故障" width="110" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.source_active === false" type="success" size="small" effect="dark">已恢复</el-tag>
          <el-tag v-else-if="row.source_active === null" type="info" size="small">已删除</el-tag>
          <el-tag v-else type="danger" size="small" effect="plain">仍存在</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="wo-pagination">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handlePageSizeChange"
        @current-change="fetchList"
      />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detail ? `工单 ${detail.ticket_id}` : '工单详情'" width="780px" destroy-on-close top="6vh">
      <div v-if="detail" v-loading="detailLoading">
        <!-- 来源故障已恢复提示 -->
        <el-alert v-if="detail.source_active === false" type="success" show-icon :closable="false"
                  title="来源故障已恢复" description="该工单对应的故障/预警当前已不存在（is_active=false），确认无误后可标记为已解决。" style="margin-bottom:12px" />
        <el-alert v-else-if="detail.source_active === null" type="info" show-icon :closable="false"
                  title="来源事件已删除" style="margin-bottom:12px" />

        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)" size="small">{{ detail.status_display }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="严重级别">{{ detail.severity }}</el-descriptions-item>
          <el-descriptions-item label="受影响设备">{{ detail.affected_device }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ sourceTypeLabel(detail.source_event_type) }} #{{ detail.source_event_id }}</el-descriptions-item>
          <el-descriptions-item label="症状" :span="2">{{ detail.symptom }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="诊断摘要">{{ detail.diagnosis || '—' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 诊断报告（markdown） -->
        <div class="wo-section-label">诊断报告 / 建议处置</div>
        <div class="wo-markdown" v-html="renderedAction"></div>

        <!-- 写提案 + 审批执行 -->
        <template v-if="detail.proposed_tool">
          <div class="wo-section-label">写处置提案（被授权策略拦截，待人工审批）</div>
          <div class="wo-proposal">
            <div class="wo-proposal-row"><span class="wo-k">操作</span><span class="wo-v">{{ toolLabel(detail.proposed_tool) }}</span></div>
            <div class="wo-proposal-row"><span class="wo-k">参数</span><pre class="wo-args">{{ prettyArgs }}</pre></div>
            <div class="wo-proposal-row"><span class="wo-k">提案状态</span>
              <el-tag :type="writeTagType(detail.write_status)" size="small">{{ WRITE_LABELS[detail.write_status] || detail.write_status }}</el-tag>
            </div>
            <div v-if="detail.write_result" class="wo-proposal-row"><span class="wo-k">执行结果</span><span class="wo-v">{{ detail.write_result }}</span></div>
            <div v-if="detail.write_executed_by" class="wo-proposal-row"><span class="wo-k">执行人</span><span class="wo-v">{{ detail.write_executed_by }} @ {{ formatTime(detail.write_executed_at) }}</span></div>
          </div>

          <div v-if="detail.write_status === 'PENDING'" class="wo-approve-bar">
            <template v-if="isAdmin">
              <el-popconfirm title="确认下发该写操作到设备？此操作会真实写入 PLC。" width="280"
                             confirm-button-text="确认执行" cancel-button-text="取消" @confirm="approveWrite">
                <template #reference>
                  <el-button type="warning" :loading="approving">同意并执行写操作</el-button>
                </template>
              </el-popconfirm>
              <span class="wo-hint">下发后工单转「处理中」，待故障消失再标记已解决。</span>
            </template>
            <span v-else class="wo-hint">仅管理员可审批执行写操作。</span>
          </div>
        </template>
        <template v-else>
          <div class="wo-section-label">写处置提案</div>
          <div class="wo-none">本工单无可执行的写处置提案（结论为无需写处置 / 纯人工现场处理）。</div>
        </template>

        <!-- 收单 -->
        <div v-if="isAdmin && detail.status !== 'RESOLVED' && detail.status !== 'CANCELLED'" class="wo-resolve-bar">
          <el-button type="success" plain :loading="resolving" @click="resolveOrder">标记为已解决</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import api from '@/utils/api.js'

marked.use({ gfm: true, breaks: true })
const DOMPURIFY_CONFIG = {
  ALLOWED_TAGS: ['p', 'br', 'hr', 'strong', 'em', 'del', 'ul', 'ol', 'li',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'code', 'pre', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'span', 'div'],
  ALLOWED_ATTR: ['href', 'title', 'class', 'target', 'rel'],
}

const WRITE_LABELS = {
  NONE: '无写提案', PENDING: '待审批执行', EXECUTED: '已执行', FAILED: '执行失败',
}
const TOOL_LABELS = {
  set_device_params: '修改设备参数', trigger_refresh: '触发按需采集刷新',
}

const route = useRoute()
const isAdmin = (() => {
  try { return (JSON.parse(localStorage.getItem('userInfo') || '{}').role) === 'admin' }
  catch (e) { return false }
})()

const filters = reactive({
  status: '', source_event_type: '', write_status: '', specific_part: '', ticket_id: '',
})
const rows = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)

const detailVisible = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const approving = ref(false)
const resolving = ref(false)

const renderedAction = computed(() => {
  if (!detail.value || !detail.value.recommended_action) return '<p class="wo-empty">—</p>'
  return DOMPurify.sanitize(marked.parse(detail.value.recommended_action), DOMPURIFY_CONFIG)
})
const prettyArgs = computed(() => {
  try { return JSON.stringify(detail.value?.proposed_args || {}, null, 2) }
  catch (e) { return String(detail.value?.proposed_args) }
})

function statusTagType(s) {
  return { OPEN: 'danger', IN_PROGRESS: 'warning', RESOLVED: 'success', CANCELLED: 'info' }[s] || 'info'
}
function writeTagType(s) {
  return { PENDING: 'warning', EXECUTED: 'success', FAILED: 'danger', NONE: 'info' }[s] || 'info'
}
function sourceTypeLabel(t) {
  return { fault_event: '故障事件', condensation_warning_event: '结露预警事件' }[t] || t
}
function toolLabel(t) { return TOOL_LABELS[t] || t }
function formatTime(iso) { return iso ? String(iso).replace('T', ' ').slice(0, 19) : '—' }

async function fetchList() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    for (const k of ['status', 'source_event_type', 'write_status', 'specific_part', 'ticket_id']) {
      if (filters[k]) params[k] = filters[k]
    }
    const resp = await api.get('/api/workorders/', params)
    if (resp && resp.success) {
      rows.value = resp.data || []
      total.value = resp.total || 0
    } else {
      ElMessage.error('获取工单列表失败')
    }
  } catch (err) {
    ElMessage.error('获取工单列表失败：' + (err.message || '网络错误'))
  } finally {
    loading.value = false
  }
}

function handleQuery() { currentPage.value = 1; fetchList() }
function handleReset() {
  Object.keys(filters).forEach(k => (filters[k] = ''))
  currentPage.value = 1
  fetchList()
}
function handlePageSizeChange() { currentPage.value = 1; fetchList() }

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const resp = await api.get(`/api/workorders/${row.id}/`)
    if (resp && resp.success) detail.value = resp.data
    else ElMessage.error('获取工单详情失败')
  } catch (err) {
    ElMessage.error('获取工单详情失败：' + (err.message || '网络错误'))
  } finally {
    detailLoading.value = false
  }
}

async function approveWrite() {
  if (!detail.value) return
  approving.value = true
  try {
    const resp = await api.post(`/api/workorders/${detail.value.id}/approve-write/`, {})
    if (resp && resp.success) {
      ElMessage.success(resp.message || '写操作已下发执行')
      await openDetail(detail.value)
      fetchList()
    } else {
      ElMessage.error(resp.message || '执行失败')
      await openDetail(detail.value)
    }
  } catch (err) {
    ElMessage.error('执行失败：' + (err.message || '网络错误'))
    await openDetail(detail.value)
  } finally {
    approving.value = false
  }
}

async function resolveOrder() {
  if (!detail.value) return
  resolving.value = true
  try {
    const resp = await api.post(`/api/workorders/${detail.value.id}/resolve/`, {})
    if (resp && resp.success) {
      ElMessage.success(resp.message || '已标记为已解决')
      await openDetail(detail.value)
      fetchList()
    } else {
      ElMessage.error(resp.message || '操作失败')
    }
  } catch (err) {
    ElMessage.error('操作失败：' + (err.message || '网络错误'))
  } finally {
    resolving.value = false
  }
}

onMounted(() => {
  if (route.query.ticket_id) filters.ticket_id = String(route.query.ticket_id)
  fetchList()
})
</script>

<style scoped>
.wo-view { padding: 0; }
.wo-page-head {
  display: flex; align-items: flex-start; gap: var(--space-3, 12px);
  margin-bottom: var(--space-5, 20px); padding-bottom: var(--space-4, 16px);
  border-bottom: 1px solid var(--line, #e5e7eb);
}
.wo-head-accent {
  width: 3px; min-height: 38px; border-radius: 2px;
  background: linear-gradient(180deg, var(--violet, #a78bfa), var(--acc, #3b82f6));
  flex-shrink: 0; margin-top: 2px;
}
.wo-head-title { margin: 0 0 4px 0; color: var(--ink-0, #111); font-size: var(--font-size-lg, 18px); font-weight: 600; line-height: 1.2; }
.wo-head-sub { margin: 0; color: var(--ink-2, #6b7280); font-size: var(--font-size-sm, 13px); }
.wo-filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.wo-pagination { margin-top: 14px; display: flex; justify-content: flex-end; }

.wo-section-label { margin: 16px 0 8px; font-size: 13px; color: var(--ink-1, #374151); font-weight: 600; }
.wo-markdown {
  background: var(--bg-1, #f8fafc); border: 1px solid var(--line, #e5e7eb);
  border-radius: 6px; padding: 12px 16px; font-size: 13px; line-height: 1.7;
  color: var(--ink-0, #111); max-height: 360px; overflow: auto;
}
.wo-markdown :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; }
.wo-markdown :deep(th), .wo-markdown :deep(td) { border: 1px solid var(--line, #e5e7eb); padding: 4px 8px; text-align: left; }
.wo-markdown :deep(h1), .wo-markdown :deep(h2), .wo-markdown :deep(h3) { margin: 10px 0 6px; }
.wo-empty { color: var(--ink-2, #6b7280); }

.wo-proposal { background: var(--bg-1, #f8fafc); border: 1px solid var(--line, #e5e7eb); border-radius: 6px; padding: 10px 14px; }
.wo-proposal-row { display: flex; gap: 10px; padding: 4px 0; font-size: 13px; align-items: flex-start; }
.wo-k { width: 64px; flex-shrink: 0; color: var(--ink-2, #6b7280); }
.wo-v { color: var(--ink-0, #111); word-break: break-all; }
.wo-args { margin: 0; font-family: var(--font-family-mono, monospace); font-size: 12px; background: rgba(5,10,20,0.04); padding: 6px 10px; border-radius: 4px; white-space: pre-wrap; word-break: break-all; }

.wo-approve-bar { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
.wo-resolve-bar { margin-top: 16px; padding-top: 12px; border-top: 1px dashed var(--line, #e5e7eb); }
.wo-hint { font-size: 12px; color: var(--ink-2, #6b7280); }
.wo-none { color: var(--ink-2, #6b7280); font-size: 13px; padding: 4px 0; }
</style>
