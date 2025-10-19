<template>
  <div class="home-container">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span>系统概览</span>
        </div>
      </template>
      <div class="dashboard-stats">
        <el-row :gutter="20">
          <el-col :span="8">
            <div class="stat-card">
              <el-icon><Cpu /></el-icon>
              <div class="stat-info">
                <div class="stat-value">{{ deviceCount }}</div>
                <div class="stat-label">设备总数</div>
              </div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card">
              <el-icon><DataAnalysis /></el-icon>
              <div class="stat-info">
                <div class="stat-value">{{ activeDevices }}</div>
                <div class="stat-label">活跃设备</div>
              </div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card">
              <el-icon><DocumentCopy /></el-icon>
              <div class="stat-info">
                <div class="stat-value">{{ dataPointCount }}</div>
                <div class="stat-label">数据点总数</div>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>
      
      <div class="system-status">
        <h3>系统状态</h3>
        <el-button type="primary" @click="checkSystemStatus" :loading="checkingStatus">
          <el-icon v-if="!checkingStatus"><Refresh /></el-icon>
          检查系统状态
        </el-button>
        <el-alert
          v-if="systemStatus"
          :title="systemStatus.status === 'ok' ? '系统正常' : '系统异常'"
          :description="systemStatus.message"
          :type="systemStatus.status === 'ok' ? 'success' : 'error'"
          show-icon
          style="margin-top: 15px;"
        />
      </div>
    </el-card>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { Cpu, DataAnalysis, DocumentCopy, Refresh } from '@element-plus/icons-vue'

export default {
  name: 'HomeView',
  components: {
    Cpu,
    DataAnalysis,
    DocumentCopy,
    Refresh
  },
  setup() {
    const deviceCount = ref(0)
    const activeDevices = ref(0)
    const dataPointCount = ref(0)
    const systemStatus = ref(null)
    const checkingStatus = ref(false)

    // 模拟数据统计
    const loadStats = () => {
      // 在实际项目中，这里应该从API获取真实数据
      deviceCount.value = 10
      activeDevices.value = 8
      dataPointCount.value = 5000
    }

    // 检查系统状态
    const checkSystemStatus = async () => {
      checkingStatus.value = true
      try {
        const response = await axios.get('/api/health/')
        systemStatus.value = response.data
      } catch (error) {
        systemStatus.value = {
          status: 'error',
          message: '无法连接到后端服务'
        }
      } finally {
        checkingStatus.value = false
      }
    }

    onMounted(() => {
      loadStats()
    })

    return {
      deviceCount,
      activeDevices,
      dataPointCount,
      systemStatus,
      checkingStatus,
      checkSystemStatus
    }
  }
}
</script>

<style scoped>
.home-container {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dashboard-stats {
  margin: 20px 0;
}

.stat-card {
  background-color: #f5f7fa;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stat-card .el-icon {
  font-size: 32px;
  margin-right: 15px;
  color: #409eff;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

.system-status {
  margin-top: 30px;
}

.system-status h3 {
  margin-bottom: 15px;
  color: #303133;
}
</style>