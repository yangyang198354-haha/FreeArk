<template>
  <div class="services-view">
    <div class="page-header">
      <h2>服务管理</h2>
      <el-button
        :icon="Refresh"
        :loading="listLoading"
        @click="fetchList"
      >
        刷新
      </el-button>
    </div>

    <!-- 服务列表表格 -->
    <el-table
      v-loading="listLoading"
      :data="serviceList"
      stripe
      border
      style="width: 100%; margin-top: 16px"
    >
      <el-table-column prop="name" label="服务名称" min-width="200" />

      <el-table-column label="运行状态" width="130" align="center">
        <template #default="{ row }">
          <el-tag :type="activeStateTagType(row.active_state)" size="small">
            {{ row.active_state || '未知' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="自启动" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.enabled === 'enabled' ? 'success' : row.enabled === 'disabled' ? 'danger' : 'info'"
            size="small"
          >
            {{ row.enabled || '未知' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="280" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="success"
            size="small"
            :loading="actionLoading[row.name] === 'start'"
            :disabled="!!actionLoading[row.name]"
            @click="handleAction(row, 'start')"
          >
            启动
          </el-button>
          <el-button
            type="danger"
            size="small"
            :loading="actionLoading[row.name] === 'stop'"
            :disabled="!!actionLoading[row.name]"
            @click="handleAction(row, 'stop')"
          >
            停止
          </el-button>
          <el-button
            type="warning"
            size="small"
            :loading="actionLoading[row.name] === 'restart'"
            :disabled="!!actionLoading[row.name]"
            @click="handleAction(row, 'restart')"
          >
            重启
          </el-button>
          <el-button
            type="primary"
            link
            size="small"
            @click="handleShowDetail(row)"
          >
            详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 服务详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="`服务详情 — ${detailServiceName}`"
      width="700px"
      destroy-on-close
    >
      <div v-if="detailLoading" class="detail-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <template v-else-if="detailData">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="运行状态">
            <el-tag :type="activeStateTagType(detailData.active_state)" size="small">
              {{ detailData.active_state || '未知' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="子状态">
            {{ detailData.sub_state || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="PID">
            {{ detailData.pid !== null && detailData.pid !== undefined ? detailData.pid : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="内存占用">
            {{ detailData.memory || '—' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="raw-output-label">systemctl status 原始输出：</div>
        <pre class="raw-output">{{ detailData.raw_output || '（无输出）' }}</pre>
      </template>

      <el-alert
        v-else-if="detailError"
        :title="detailError"
        type="error"
        :closable="false"
        show-icon
      />
    </el-dialog>

    <!-- 操作确认弹窗 -->
    <el-dialog
      v-model="confirmVisible"
      title="确认操作"
      width="400px"
    >
      <p>
        确认对服务
        <strong>{{ confirmServiceName }}</strong>
        执行
        <strong>{{ confirmActionLabel }}</strong>
        操作？
      </p>
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button
          :type="confirmButtonType"
          :loading="confirmExecuting"
          @click="executeConfirmedAction"
        >
          确认
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Loading } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'ServicesView',

  components: { Refresh, Loading },

  setup() {
    // --- 列表状态 ---
    const serviceList = ref([])
    const listLoading = ref(false)

    // actionLoading: { [serviceName]: 'start'|'stop'|'restart'|null }
    const actionLoading = reactive({})

    // --- 详情弹窗状态 ---
    const detailVisible = ref(false)
    const detailServiceName = ref('')
    const detailData = ref(null)
    const detailLoading = ref(false)
    const detailError = ref('')

    // --- 确认弹窗状态 ---
    const confirmVisible = ref(false)
    const confirmServiceName = ref('')
    const confirmAction = ref('')
    const confirmExecuting = ref(false)

    const ACTION_LABELS = { start: '启动', stop: '停止', restart: '重启' }
    const ACTION_BUTTON_TYPES = { start: 'success', stop: 'danger', restart: 'warning' }

    const confirmActionLabel = ref('')
    const confirmButtonType = ref('primary')

    // --- 辅助函数 ---
    const activeStateTagType = (state) => {
      if (state === 'active') return 'success'
      if (state === 'failed') return 'danger'
      if (state === 'inactive') return 'warning'
      return 'info'
    }

    // --- API：获取服务列表 ---
    const fetchList = async () => {
      listLoading.value = true
      try {
        const resp = await api.get('/api/services/list/')
        if (resp && resp.success) {
          serviceList.value = resp.data || []
        } else {
          ElMessage.error(resp?.error || '获取服务列表失败')
        }
      } catch (err) {
        ElMessage.error('获取服务列表失败：' + (err.message || '网络错误'))
      } finally {
        listLoading.value = false
      }
    }

    // --- 操作：弹出确认框 ---
    const handleAction = (row, action) => {
      confirmServiceName.value = row.name
      confirmAction.value = action
      confirmActionLabel.value = ACTION_LABELS[action] || action
      confirmButtonType.value = ACTION_BUTTON_TYPES[action] || 'primary'
      confirmVisible.value = true
    }

    // --- 操作：确认后执行 ---
    const executeConfirmedAction = async () => {
      const name = confirmServiceName.value
      const action = confirmAction.value
      confirmExecuting.value = true
      actionLoading[name] = action

      try {
        const resp = await api.post(`/api/services/${encodeURIComponent(name)}/action/`, { action })
        if (resp && resp.success) {
          ElMessage.success(resp.message || `${name} ${action} 成功`)
          // 更新列表中该服务的 active_state
          const item = serviceList.value.find(s => s.name === name)
          if (item && resp.new_status) {
            item.active_state = resp.new_status
            item.is_active = resp.new_status === 'active'
          }
        } else {
          ElMessage.error(resp?.error || `${name} ${action} 失败`)
        }
      } catch (err) {
        ElMessage.error(`执行失败：${err.message || '网络错误'}`)
      } finally {
        confirmExecuting.value = false
        confirmVisible.value = false
        actionLoading[name] = null
      }
    }

    // --- 详情：打开弹窗并加载 ---
    const handleShowDetail = async (row) => {
      detailServiceName.value = row.name
      detailData.value = null
      detailError.value = ''
      detailLoading.value = true
      detailVisible.value = true

      try {
        const resp = await api.get(`/api/services/${encodeURIComponent(row.name)}/detail/`)
        if (resp && resp.success) {
          detailData.value = resp.detail || {}
        } else {
          detailError.value = resp?.error || '获取服务详情失败'
        }
      } catch (err) {
        detailError.value = '获取服务详情失败：' + (err.message || '网络错误')
      } finally {
        detailLoading.value = false
      }
    }

    onMounted(() => {
      fetchList()
    })

    return {
      serviceList,
      listLoading,
      actionLoading,
      detailVisible,
      detailServiceName,
      detailData,
      detailLoading,
      detailError,
      confirmVisible,
      confirmServiceName,
      confirmActionLabel,
      confirmButtonType,
      confirmExecuting,
      Refresh,
      Loading,
      activeStateTagType,
      fetchList,
      handleAction,
      executeConfirmedAction,
      handleShowDetail,
    }
  },
}
</script>

<style scoped>
.services-view {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.page-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.detail-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  padding: 20px 0;
  justify-content: center;
}

.raw-output-label {
  margin-top: 16px;
  margin-bottom: 6px;
  font-size: 13px;
  color: #606266;
  font-weight: 500;
}

.raw-output {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', 'Courier New', monospace;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 320px;
  overflow-y: auto;
}
</style>
