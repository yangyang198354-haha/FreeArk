<!--
  MOD-FE-02 — 设备管理：设备列表页面（UI refresh batch-3）
-->
<template>
  <div class="device-management-device-list">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">设备列表</h2>
        <p class="ph-sub">查看和管理所有设备的运行状态</p>
      </div>
    </div>

    <!-- 过滤栏 -->
    <div class="filter-bar">
      <div style="display: inline-block; vertical-align: middle; width: 180px;">
        <CascadingSelector building-input-id="dlBuilding" building-input-name="dlBuilding" unit-input-id="dlUnit" unit-input-name="dlUnit" room-input-id="dlRoom" room-input-name="dlRoom" ref="cascadingSelectorRef" />
      </div>
      <el-select v-model="filterScreenStatus" placeholder="大屏状态" clearable style="width: 140px" @change="handleSearch">
        <el-option label="在线" value="online" /><el-option label="离线" value="offline" /><el-option label="未知" value="unknown" />
      </el-select>
      <el-select v-model="filterPlcStatus" placeholder="PLC状态" clearable style="width: 140px" @change="handleSearch">
        <el-option label="在线" value="online" /><el-option label="离线" value="offline" />
      </el-select>
      <el-select v-model="filterSystemSwitch" placeholder="系统开关" clearable style="width: 140px" @change="handleSearch">
        <el-option label="开" value="on" /><el-option label="关" value="off" />
      </el-select>
      <el-select v-model="filterOperationMode" placeholder="运行模式" clearable style="width: 140px" @change="handleSearch">
        <el-option label="制冷" :value="1" /><el-option label="制热" :value="2" /><el-option label="通风" :value="3" /><el-option label="除湿" :value="4" />
      </el-select>
      <el-select v-model="filterFaultStatus" placeholder="故障状态" clearable style="width: 140px" @change="handleSearch">
        <el-option label="仅有故障" value="has_fault" /><el-option label="仅无故障" value="no_fault" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
      <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
    </div>

    <!-- 数据表格 -->
    <el-table v-loading="loading" :data="tableData" stripe border style="width: 100%; margin-top: 16px">
      <el-table-column prop="building" label="楼栋" width="80" align="center" />
      <el-table-column prop="unit" label="单元" width="80" align="center" />
      <el-table-column prop="room_number" label="户号" width="100" align="center" />
      <el-table-column label="大屏状态" width="120" align="center">
        <template #default="{ row }"><el-tag :type="screenStatusTagType(row.screen_status)" size="small">{{ screenStatusLabel(row.screen_status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="PLC状态" width="120" align="center">
        <template #default="{ row }"><el-tag :type="plcStatusTagType(row.plc_status)" size="small">{{ plcStatusLabel(row.plc_status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="PLC上次心跳" width="150" align="center">
        <template #default="{ row }"><span>{{ formatDateTime(row.plc_last_online_time) }}</span></template>
      </el-table-column>
      <el-table-column label="系统开关" width="110" align="center">
        <template #default="{ row }"><el-tag :type="systemSwitchTagType(row.system_switch_display)" size="small">{{ row.system_switch_display }}</el-tag></template>
      </el-table-column>
      <el-table-column label="运行模式" width="110" align="center">
        <template #default="{ row }"><el-tag :type="operationModeTagType(row.operation_mode_display)" size="small">{{ row.operation_mode_display || '未知' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="故障数量" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.fault_count === null || row.fault_count === undefined" style="color: var(--ink-2);">—</span>
          <span v-else :style="{ color: row.fault_count === 0 ? 'var(--ok)' : 'var(--danger)', fontWeight: 600 }">{{ row.fault_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凝露提醒" width="100" align="center">
        <template #default="{ row }">
          <span :style="{ color: row.has_active_condensation ? 'var(--warn)' : 'var(--ink-2)', fontWeight: 600 }">{{ row.has_active_condensation ? '有' : '无' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="handleGoToDevicePanel(row)">设备面板</el-button>
          <el-button type="info" link size="small" @click="handleOpenPlcHistory(row)">PLC历史</el-button>
          <el-button type="warning" link size="small" @click="handleOpenSettings(row)">设置</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" background @size-change="handlePageSizeChange" @current-change="handlePageChange" />
    </div>

    <!-- PLC历史弹窗 -->
    <el-dialog v-model="plcHistoryDialogVisible" :title="`PLC 状态历史 — ${plcHistorySpecificPart}`" width="600px" destroy-on-close>
      <div v-loading="plcHistoryLoading" class="plc-history-content">
        <div v-if="!plcHistoryLoading && plcHistoryList.length === 0" class="no-data">暂无 PLC 状态变化记录</div>
        <el-table v-if="plcHistoryList.length > 0" :data="plcHistoryList" stripe border size="small" style="width: 100%">
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }"><el-tag :type="row.status === 'online' ? 'success' : 'danger'" size="small">{{ row.status === 'online' ? '上线' : '离线' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="变化时间" align="center">
            <template #default="{ row }"><span>{{ formatDateTime(row.change_time) }}</span></template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer><el-button @click="plcHistoryDialogVisible = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, RefreshLeft } from '@element-plus/icons-vue'
import api from '@/utils/api.js'
import CascadingSelector from '@/components/CascadingSelector.vue'

export default {
  name: 'DeviceManagementDeviceListView',
  components: { Search, RefreshLeft, CascadingSelector },
  setup() {
    const router = useRouter()
    const tableData = ref([]), total = ref(0), currentPage = ref(1), pageSize = ref(20), loading = ref(false)
    const cascadingSelectorRef = ref(null)
    const filterScreenStatus = ref(''), filterPlcStatus = ref(''), filterSystemSwitch = ref(''), filterOperationMode = ref(null), filterFaultStatus = ref('')
    const plcHistoryDialogVisible = ref(false), plcHistoryLoading = ref(false), plcHistoryList = ref([]), plcHistorySpecificPart = ref('')

    const fetchList = async () => {
      loading.value = true
      try {
        const params = { page: currentPage.value, page_size: pageSize.value }
        const dlBuilding = document.getElementById('dlBuilding')?.value || '', dlUnit = document.getElementById('dlUnit')?.value || '', dlRoom = document.getElementById('dlRoom')?.value || ''
        if (dlBuilding) { let r = dlBuilding; if (dlUnit) r += `-${dlUnit}`; if (dlRoom) r += `-${dlRoom}`; params.room_no = r }
        if (filterScreenStatus.value) params.screen_status = filterScreenStatus.value
        if (filterSystemSwitch.value) params.system_switch = filterSystemSwitch.value
        if (filterPlcStatus.value) params.plc_status = filterPlcStatus.value
        if (filterOperationMode.value !== null && filterOperationMode.value !== '') params.operation_mode = filterOperationMode.value
        if (filterFaultStatus.value) params.fault_status = filterFaultStatus.value
        const queryString = new URLSearchParams(params).toString()
        const response = await api.get(`/api/device-management/device-list/?${queryString}`)
        if (response && response.results !== undefined) { tableData.value = response.results; total.value = response.count || 0 }
        else { tableData.value = []; total.value = 0 }
      } catch (err) { ElMessage.error('获取设备列表失败，请检查网络或联系管理员'); tableData.value = []; total.value = 0 }
      finally { loading.value = false }
    }

    const fetchPlcHistory = async (specificPart) => {
      plcHistoryLoading.value = true; plcHistoryList.value = []
      try {
        const response = await api.get(`/api/plc/status-change-history/${encodeURIComponent(specificPart)}/`)
        if (response && Array.isArray(response.data)) plcHistoryList.value = [...response.data].reverse()
        else if (Array.isArray(response)) plcHistoryList.value = [...response].reverse()
        else plcHistoryList.value = []
      } catch (err) { ElMessage.error('获取 PLC 历史记录失败'); plcHistoryList.value = [] }
      finally { plcHistoryLoading.value = false }
    }

    const handleSearch = () => { currentPage.value = 1; fetchList() }
    const handleReset = () => { if (cascadingSelectorRef.value) cascadingSelectorRef.value.clearSelection?.(); filterScreenStatus.value = ''; filterPlcStatus.value = ''; filterSystemSwitch.value = ''; filterOperationMode.value = null; filterFaultStatus.value = ''; currentPage.value = 1; fetchList() }
    const handlePageChange = (page) => { currentPage.value = page; fetchList() }
    const handlePageSizeChange = (size) => { pageSize.value = size; currentPage.value = 1; fetchList() }
    const handleGoToDevicePanel = (row) => { router.push(`/device-cards?specific_part=${encodeURIComponent(row.specific_part)}`) }
    const handleOpenPlcHistory = (row) => { plcHistorySpecificPart.value = row.specific_part; plcHistoryDialogVisible.value = true; fetchPlcHistory(row.specific_part) }
    const handleOpenSettings = (row) => { router.push('/device-management/device-settings?specific_part=' + encodeURIComponent(row.specific_part)) }

    const screenStatusLabel = s => s === 'online' ? '在线' : s === 'offline' ? '离线' : '未知'
    const screenStatusTagType = s => s === 'online' ? 'success' : s === 'offline' ? 'danger' : 'info'
    const plcStatusLabel = s => s === 'online' ? '在线' : s === 'offline' ? '离线' : '未知'
    const plcStatusTagType = s => s === 'online' ? 'success' : s === 'offline' ? 'danger' : 'info'
    const systemSwitchTagType = d => d === '开' ? 'success' : d === '关' ? 'danger' : 'info'
    const operationModeTagType = d => d === '制冷' ? 'primary' : d === '制热' ? 'danger' : d === '通风' ? 'success' : d === '除湿' ? 'warning' : 'info'
    const formatDateTime = (isoStr) => {
      if (!isoStr) return '—'
      try { const d = new Date(isoStr); const pad = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` }
      catch { return isoStr }
    }

    onMounted(() => { fetchList() })

    return { tableData, total, currentPage, pageSize, loading, cascadingSelectorRef, filterScreenStatus, filterPlcStatus, filterSystemSwitch, filterOperationMode, filterFaultStatus, plcHistoryDialogVisible, plcHistoryLoading, plcHistoryList, plcHistorySpecificPart, Search, RefreshLeft, fetchList, handleSearch, handleReset, handlePageChange, handlePageSizeChange, handleGoToDevicePanel, handleOpenPlcHistory, handleOpenSettings, screenStatusLabel, screenStatusTagType, plcStatusLabel, plcStatusTagType, systemSwitchTagType, operationModeTagType, formatDateTime }
  },
}
</script>

<style scoped>
.device-management-device-list { padding: 0; }
.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 20px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
.filter-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.pagination-wrapper { display: flex; justify-content: flex-end; margin-top: 16px; }
.plc-history-content { min-height: 100px; }
.no-data { text-align: center; color: var(--ink-3); padding: 30px 0; font-size: 14px; }
</style>
