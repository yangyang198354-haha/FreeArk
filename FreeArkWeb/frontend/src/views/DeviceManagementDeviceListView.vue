<!--
  MOD-FE-02 — 设备管理：设备列表页面
  author_agent: sub_agent_software_developer
  project: FreeArk_DeviceManagement
  invocation_id: INVOKE-GROUP_C-001

  US-002~007：分页表格、三维过滤（房号/大屏状态/系统开关）、操作列跳转至设备面板。
-->
<template>
  <div class="device-management-device-list">
    <div class="page-header">
      <h2>设备列表</h2>
    </div>

    <!-- 过滤栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filterRoomNo"
        placeholder="房号（如 3-1-702）"
        clearable
        style="width: 180px"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
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
        v-model="filterSystemSwitch"
        placeholder="系统开关"
        clearable
        style="width: 140px"
        @change="handleSearch"
      >
        <el-option label="开" value="on" />
        <el-option label="关" value="off" />
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
      <el-table-column label="大屏检测时间" min-width="160" align="center">
        <template #default="{ row }">
          <span>{{ row.screen_last_checked_at || '—' }}</span>
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
      <el-table-column label="操作" width="120" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="handleGoToDevicePanel(row)"
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
        :total="total"
        :page-sizes="[10, 20, 50]"
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
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, RefreshLeft } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'DeviceManagementDeviceListView',

  components: { Search, RefreshLeft },

  setup() {
    const router = useRouter()

    // --- 状态 ---
    const tableData = ref([])
    const total = ref(0)
    const currentPage = ref(1)
    const pageSize = ref(20)
    const loading = ref(false)
    const filterRoomNo = ref('')
    const filterScreenStatus = ref('')
    const filterSystemSwitch = ref('')

    // --- API 调用 ---
    const fetchList = async () => {
      loading.value = true
      try {
        const params = {
          page: currentPage.value,
          page_size: pageSize.value,
        }
        if (filterRoomNo.value.trim()) {
          params.room_no = filterRoomNo.value.trim()
        }
        if (filterScreenStatus.value) {
          params.screen_status = filterScreenStatus.value
        }
        if (filterSystemSwitch.value) {
          params.system_switch = filterSystemSwitch.value
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

    // --- 事件处理 ---
    const handleSearch = () => {
      currentPage.value = 1
      fetchList()
    }

    const handleReset = () => {
      filterRoomNo.value = ''
      filterScreenStatus.value = ''
      filterSystemSwitch.value = ''
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

    const systemSwitchTagType = (display) => {
      if (display === '开') return 'success'
      if (display === '关') return 'danger'
      return 'info'
    }

    onMounted(() => {
      fetchList()
    })

    return {
      tableData,
      total,
      currentPage,
      pageSize,
      loading,
      filterRoomNo,
      filterScreenStatus,
      filterSystemSwitch,
      Search,
      RefreshLeft,
      fetchList,
      handleSearch,
      handleReset,
      handlePageChange,
      handlePageSizeChange,
      handleGoToDevicePanel,
      screenStatusLabel,
      screenStatusTagType,
      systemSwitchTagType,
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
</style>
