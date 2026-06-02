<template>
  <div class="specific-part-detail-container">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">设备详情</h2>
        <p class="ph-sub">查看PLC设备的连接状态和状态变化历史</p>
      </div>
      <div class="ph-actions">
        <el-button type="success" @click="goToDeviceCards"><el-icon><Monitor /></el-icon>设备面板</el-button>
        <el-button type="primary" @click="goBack"><el-icon><Back /></el-icon>返回列表</el-button>
      </div>
    </div>

    <!-- 设备基本信息卡片 -->
    <el-card class="info-card">
      <template #header><span class="section-label" style="margin:0;">设备基本信息</span></template>
      <div class="info-grid">
        <div class="info-item">
          <div class="info-label">设备标识</div>
          <div class="info-value">{{ deviceInfo.specific_part }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">当前状态</div>
          <div class="info-value">
            <span :class="['badge', deviceInfo.connection_status === 'online' ? 'on' : 'off']">
              <span class="bd"></span>{{ deviceInfo.connection_status === 'online' ? '在线' : '离线' }}
            </span>
          </div>
        </div>
        <div class="info-item">
          <div class="info-label">最后在线时间</div>
          <div class="info-value">{{ formatDateTime(deviceInfo.last_online_time) }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">所属楼栋</div>
          <div class="info-value">{{ deviceInfo.building }}栋</div>
        </div>
        <div class="info-item">
          <div class="info-label">所属单元</div>
          <div class="info-value">{{ deviceInfo.unit }}单元</div>
        </div>
        <div class="info-item">
          <div class="info-label">房号</div>
          <div class="info-value">{{ deviceInfo.room_number }}</div>
        </div>
      </div>
    </el-card>

    <!-- 状态变化历史表格 -->
    <el-card class="data-table-card">
      <template #header><span class="section-label" style="margin:0;">状态变化历史</span></template>
      <el-skeleton :rows="5" animated v-if="loading" />
      <el-empty description="暂无数据" v-else-if="statusHistory.length === 0" />
      <el-table v-else :data="statusHistory" style="width: 100%" border stripe>
        <el-table-column prop="status" label="状态" min-width="100">
          <template #default="scope">
            <span :class="['badge', scope.row.status === 'online' ? 'on' : 'off']">
              <span class="bd"></span>{{ scope.row.status === 'online' ? '上线' : '离线' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="change_time" label="变化时间" min-width="200">
          <template #default="scope">{{ formatDateTime(scope.row.change_time) }}</template>
        </el-table-column>
        <el-table-column prop="building" label="楼栋" min-width="80" />
        <el-table-column prop="unit" label="单元" min-width="80" />
        <el-table-column prop="room_number" label="房号" min-width="80" />
      </el-table>
      <div class="pagination-container" v-if="statusHistory.length > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="totalRecords"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script>
import { Back, Monitor } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'SpecificPartDetailView',
  components: { Back, Monitor },
  data() {
    return {
      specificPart: this.$route.params.specificPart,
      deviceInfo: { specific_part: '', connection_status: 'offline', last_online_time: null, building: '', unit: '', room_number: '' },
      currentPage: 1, pageSize: 10, totalRecords: 0,
      statusHistory: [], loading: false
    }
  },
  mounted() { this.getDeviceInfo(); this.searchData() },
  watch: {
    '$route.params.specificPart': function(newVal) { this.specificPart = newVal; this.getDeviceInfo(); this.searchData() }
  },
  methods: {
    goBack() { this.$router.push('/plc-status') },
    goToDeviceCards() { this.$router.push({ name: 'DeviceCards', query: { specific_part: this.specificPart } }) },
    async getDeviceInfo() {
      try { const response = await api.get(`/api/plc/connection-status/${this.specificPart}/`); if (response.success) this.deviceInfo = response.data }
      catch (error) { console.error('获取设备基本信息失败:', error); this.$message.error('获取设备信息失败，请稍后重试') }
    },
    async searchData() {
      this.loading = true
      try {
        const response = await api.get(`/api/plc/status-change-history/${this.specificPart}/`, { page: this.currentPage, page_size: this.pageSize })
        if (response.success && Array.isArray(response.data)) { this.statusHistory = response.data; this.totalRecords = response.total || 0 }
        else { this.statusHistory = []; this.totalRecords = 0; this.$message.info('暂无数据') }
      } catch (error) { console.error('查询状态变化历史失败:', error); this.statusHistory = []; this.totalRecords = 0; this.$message.error('查询数据失败，请稍后重试') }
      finally { this.loading = false }
    },
    formatDateTime(dateTimeStr) {
      if (!dateTimeStr) return '-'
      const date = new Date(dateTimeStr); if (isNaN(date.getTime())) return '-'
      const y = date.getFullYear(), mo = date.getMonth() + 1, d = date.getDate(), h = date.getHours(), mi = date.getMinutes(), s = date.getSeconds()
      return `${y}/${mo}/${d} ${String(h).padStart(2,'0')}:${String(mi).padStart(2,'0')}:${String(s).padStart(2,'0')}`
    },
    handleSizeChange(size) { this.pageSize = size; this.currentPage = 1; this.searchData() },
    handleCurrentChange(page) { this.currentPage = page; this.searchData() }
  }
}
</script>

<style scoped>
.specific-part-detail-container { width: 100%; }

.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 24px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-text { flex: 1; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
.ph-actions { display: flex; gap: 8px; flex-shrink: 0; }

.info-card { margin-bottom: 24px; }
.data-table-card { margin-bottom: 20px; }

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 20px;
  padding: 8px 0;
}
.info-item {}
.info-label { font-size: var(--font-size-sm); color: var(--ink-2); margin-bottom: 5px; }
.info-value { font-size: var(--font-size-base); font-weight: 500; color: var(--ink-0); }

.pagination-container { margin-top: 20px; display: flex; justify-content: flex-end; padding-top: 15px; border-top: 1px solid var(--line); }
</style>
