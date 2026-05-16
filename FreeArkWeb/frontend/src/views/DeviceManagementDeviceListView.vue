<!--
  MOD-FE-02 — 设备管理：设备列表页面
  author_agent: sub_agent_software_developer
  project: FreeArk_DeviceManagement
  invocation_id: INVOKE-GROUP_C-002

  变更记录（2026-05-01）：
  - 移除「大屏检测时间」列（screen_last_checked_at）
  - 新增「PLC状态」列（绿/红/灰 el-tag）
  - 新增「PLC最后在线时间」列
  - 过滤栏新增「PLC状态」el-select 下拉
  - 操作列新增「PLC历史」按钮，点击打开 el-dialog 弹窗
-->
<template>
  <div class="device-management-device-list">
    <div class="page-header">
      <h2>设备列表</h2>
    </div>

    <!-- 过滤栏 -->
    <div class="filter-bar">
      <div style="display: inline-block; vertical-align: middle; width: 180px;">
        <CascadingSelector
          building-input-id="dlBuilding"
          building-input-name="dlBuilding"
          unit-input-id="dlUnit"
          unit-input-name="dlUnit"
          room-input-id="dlRoom"
          room-input-name="dlRoom"
          ref="cascadingSelectorRef"
        />
      </div>
      <el-select
        v-model="filterScreenStatus"
        placeholder="大屏状态"
        clearable
        style="width: 140px"
        @change="handleSearch"
      >
        <el-option label="在线" value="online" />
        <el-option label="离线" value="offline" />
        <el-option label="未知" value="unknown" />
      </el-select>
      <el-select
        v-model="filterPlcStatus"
        placeholder="PLC状态"
        clearable
        style="width: 140px"
        @change="handleSearch"
      >
        <el-option label="在线" value="online" />
        <el-option label="离线" value="offline" />
      </el-select>
      <el-select
        v-model="filterSystemSwitch"
        placeholder="系统开关"
        clearable
        style="width: 140px"
        @change="handleSearch"
      >
        <el-option label="开" value="on" />
        <el-option label="关" value="off" />
      </el-select>
      <el-select
        v-model="filterOperationMode"
        placeholder="运行模式"
        clearable
        style="width: 140px"
        @change="handleSearch"
      >
        <el-option label="制冷" :value="1" />
        <el-option label="制热" :value="2" />
        <el-option label="通风" :value="3" />
        <el-option label="除湿" :value="4" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
      <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
    </div>

    <!-- 数据表格 -->
    <el-table
      v-loading="loading"
      :data="tableData"
      stripe
      border
      style="width: 100%; margin-top: 16px"
    >
      <el-table-column prop="building" label="楼栋" width="80" align="center" />
      <el-table-column prop="unit" label="单元" width="80" align="center" />
      <el-table-column prop="room_number" label="户号" width="100" align="center" />
      <el-table-column label="大屏状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag
            :type="screenStatusTagType(row.screen_status)"
            size="small"
          >
            {{ screenStatusLabel(row.screen_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="PLC状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag
            :type="plcStatusTagType(row.plc_status)"
            size="small"
          >
            {{ plcStatusLabel(row.plc_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="PLC最后在线时间" min-width="160" align="center">
        <template #default="{ row }">
          <span>{{ formatDateTime(row.plc_last_online_time) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="系统开关" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            :type="systemSwitchTagType(row.system_switch_display)"
            size="small"
          >
            {{ row.system_switch_display }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="运行模式" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            :type="operationModeTagType(row.operation_mode_display)"
            size="small"
          >
            {{ row.operation_mode_display || '未知' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="handleGoToDevicePanel(row)"
          >
            设备面板
          </el-button>
          <el-button
            type="info"
            link
            size="small"
            @click="handleOpenPlcHistory(row)"
          >
            PLC历史
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        background
        @size-change="handlePageSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <!-- PLC历史弹窗 -->
    <el-dialog
      v-model="plcHistoryDialogVisible"
      :title="`PLC 状态历史 — ${plcHistorySpecificPart}`"
      width="600px"
      destroy-on-close
    >
      <div v-loading="plcHistoryLoading" class="plc-history-content">
        <div v-if="!plcHistoryLoading && plcHistoryList.length === 0" class="no-data">
          暂无 PLC 状态变化记录
        </div>
        <el-table
          v-if="plcHistoryList.length > 0"
          :data="plcHistoryList"
          stripe
          border
          size="small"
          style="width: 100%"
        >
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'online' ? 'success' : 'danger'"
                size="small"
              >
                {{ row.status === 'online' ? '上线' : '离线' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="变化时间" align="center">
            <template #default="{ row }">
              <span>{{ formatDateTime(row.change_time) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="plcHistoryDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, RefreshLeft } from '@element-plus/icons-vue'
import api from '@/utils/api.js'
import CascadingSelector from '@/components/CascadingSelector.vue'

export default {
  name: 'DeviceManagementDeviceListView',

  components: { Search, RefreshLeft, CascadingSelector },

  setup() {
    const router = useRouter()

    // --- 状态 ---
    const tableData = ref([])
    const total = ref(0)
    const currentPage = ref(1)
    const pageSize = ref(20)
    const loading = ref(false)
    const cascadingSelectorRef = ref(null)
    const filterScreenStatus = ref('')
    const filterPlcStatus = ref('')
    const filterSystemSwitch = ref('')
    const filterOperationMode = ref(null)

    // PLC 历史弹窗状态
    const plcHistoryDialogVisible = ref(false)
    const plcHistoryLoading = ref(false)
    const plcHistoryList = ref([])
    const plcHistorySpecificPart = ref('')

    // --- API 调用 ---
    const fetchList = async () => {
      loading.value = true
      try {
        const params = {
          page: currentPage.value,
          page_size: pageSize.value,
        }
        const dlBuilding = document.getElementById('dlBuilding')?.value || ''
        const dlUnit = document.getElementById('dlUnit')?.value || ''
        const dlRoom = document.getElementById('dlRoom')?.value || ''
        if (dlBuilding) {
          let roomNo = dlBuilding
          if (dlUnit) roomNo += `-${dlUnit}`
          if (dlRoom) roomNo += `-${dlRoom}`
          params.room_no = roomNo
        }
        if (filterScreenStatus.value) {
          params.screen_status = filterScreenStatus.value
        }
        if (filterSystemSwitch.value) {
          params.system_switch = filterSystemSwitch.value
        }
        if (filterPlcStatus.value) {
          params.plc_status = filterPlcStatus.value
        }
        if (filterOperationMode.value !== null && filterOperationMode.value !== '') {
          params.operation_mode = filterOperationMode.value
        }

        const queryString = new URLSearchParams(params).toString()
        const response = await api.get(`/api/device-management/device-list/?${queryString}`)

        if (response && response.results !== undefined) {
          tableData.value = response.results
          total.value = response.count || 0
        } else if (response && response.success === false) {
          ElMessage.error(response.error || '获取设备列表失败')
          tableData.value = []
          total.value = 0
        } else {
          tableData.value = []
          total.value = 0
        }
      } catch (err) {
        ElMessage.error('获取设备列表失败，请检查网络或联系管理员')
        tableData.value = []
        total.value = 0
      } finally {
        loading.value = false
      }
    }

    const fetchPlcHistory = async (specificPart) => {
      plcHistoryLoading.value = true
      plcHistoryList.value = []
      try {
        const response = await api.get(`/api/plc/status-change-history/${encodeURIComponent(specificPart)}/`)
        // 响应格式：{ total, data: [...] }
        if (response && Array.isArray(response.data)) {
          // 倒序展示（最新的在最前面）
          plcHistoryList.value = [...response.data].reverse()
        } else if (Array.isArray(response)) {
          plcHistoryList.value = [...response].reverse()
        } else {
          plcHistoryList.value = []
        }
      } catch (err) {
        ElMessage.error('获取 PLC 历史记录失败')
        plcHistoryList.value = []
      } finally {
        plcHistoryLoading.value = false
      }
    }

    // --- 事件处理 ---
    const handleSearch = () => {
      currentPage.value = 1
      fetchList()
    }

    const handleReset = () => {
      if (cascadingSelectorRef.value) {
        cascadingSelectorRef.value.clearSelection?.()
      }
      filterScreenStatus.value = ''
      filterPlcStatus.value = ''
      filterSystemSwitch.value = ''
      filterOperationMode.value = null
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

    const handleGoToDevicePanel = (row) => {
      router.push(`/device-cards?specific_part=${encodeURIComponent(row.specific_part)}`)
    }

    const handleOpenPlcHistory = (row) => {
      plcHistorySpecificPart.value = row.specific_part
      plcHistoryDialogVisible.value = true
      fetchPlcHistory(row.specific_part)
    }

    // --- 辅助函数 ---
    const screenStatusLabel = (status) => {
      if (status === 'online') return '在线'
      if (status === 'offline') return '离线'
      return '未知'
    }

    const screenStatusTagType = (status) => {
      if (status === 'online') return 'success'
      if (status === 'offline') return 'danger'
      return 'info'
    }

    const plcStatusLabel = (status) => {
      if (status === 'online') return '在线'
      if (status === 'offline') return '离线'
      return '未知'
    }

    const plcStatusTagType = (status) => {
      if (status === 'online') return 'success'
      if (status === 'offline') return 'danger'
      return 'info'
    }

    const systemSwitchTagType = (display) => {
      if (display === '开') return 'success'
      if (display === '关') return 'danger'
      return 'info'
    }

    // REQ-FUNC-003: 运行模式 tag 颜色（制冷=info/蓝, 制热=danger/红, 通风=success/绿, 除湿=warning/黄）
    const operationModeTagType = (display) => {
      if (display === '制冷') return 'primary'
      if (display === '制热') return 'danger'
      if (display === '通风') return 'success'
      if (display === '除湿') return 'warning'
      return 'info'
    }

    const formatDateTime = (isoStr) => {
      if (!isoStr) return '—'
      try {
        const d = new Date(isoStr)
        const pad = (n) => String(n).padStart(2, '0')
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
      } catch {
        return isoStr
      }
    }

    onMounted(() => {
      fetchList()
    })

    onBeforeUnmount(() => {
      // 无需清理
    })

    return {
      tableData,
      total,
      currentPage,
      pageSize,
      loading,
      cascadingSelectorRef,
      filterScreenStatus,
      filterPlcStatus,
      filterSystemSwitch,
      filterOperationMode,
      plcHistoryDialogVisible,
      plcHistoryLoading,
      plcHistoryList,
      plcHistorySpecificPart,
      Search,
      RefreshLeft,
      fetchList,
      handleSearch,
      handleReset,
      handlePageChange,
      handlePageSizeChange,
      handleGoToDevicePanel,
      handleOpenPlcHistory,
      screenStatusLabel,
      screenStatusTagType,
      plcStatusLabel,
      plcStatusTagType,
      systemSwitchTagType,
      operationModeTagType,
      formatDateTime,
    }
  },
}
</script>

<style scoped>
.device-management-device-list {
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
  gap: 12px;
  flex-wrap: wrap;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.plc-history-content {
  min-height: 100px;
}

.no-data {
  text-align: center;
  color: #c0c4cc;
  padding: 30px 0;
  font-size: 14px;
}

.batch-sync-content {
  padding: 8px 0;
}

.batch-summary {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-counter {
  color: #606266;
  font-size: 14px;
}

.batch-errors {
  margin-top: 12px;
}

.batch-errors-title {
  font-size: 13px;
  color: #f56c6c;
  margin-bottom: 6px;
}
</style>
