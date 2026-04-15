<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>系统看板</h2>
      <p class="page-subtitle">实时监控系统运行状态和能耗数据</p>
    </div>

    <!-- 总电量时间选择器 -->
    <div class="total-energy-section">
      <el-card>
        <template #header>
          <div class="card-header">
            <span>总电量查询</span>
            <div class="date-picker-group">
              <el-date-picker
                v-model="totalEnergyDateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                :shortcuts="dateShortcuts"
                @change="fetchTotalEnergy"
              />
            </div>
          </div>
        </template>
        <div class="total-energy-values" v-loading="loading.totalEnergy">
          <div class="energy-item">
            <div class="energy-value">{{ totalEnergy.total_kwh.toLocaleString() }}</div>
            <div class="energy-label">总电量 (kWh)</div>
          </div>
          <div class="energy-item cooling">
            <div class="energy-value">{{ totalEnergy.cooling_kwh.toLocaleString() }}</div>
            <div class="energy-label">制冷 (kWh)</div>
          </div>
          <div class="energy-item heating">
            <div class="energy-value">{{ totalEnergy.heating_kwh.toLocaleString() }}</div>
            <div class="energy-label">制热 (kWh)</div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 统计卡片区域 -->
    <div class="stats-cards">
      <el-card class="stat-card" v-loading="loading.summary">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value">{{ summary.today_kwh.toLocaleString() }}</div>
            <div class="stat-label">今日用电量 (kWh)</div>
          </div>
          <div class="stat-icon today">
            <el-icon><Calendar /></el-icon>
          </div>
        </div>
      </el-card>

      <el-card class="stat-card" v-loading="loading.summary">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value">{{ summary.month_kwh.toLocaleString() }}</div>
            <div class="stat-label">本月用电量 (kWh)</div>
          </div>
          <div class="stat-icon month">
            <el-icon><Document /></el-icon>
          </div>
        </div>
      </el-card>

      <el-card class="stat-card" v-loading="loading.plcRate">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value">{{ plcRate.rate }}%</div>
            <div class="stat-label">系统运行率 ({{ plcRate.online_count }}/{{ plcRate.total_count }})</div>
          </div>
          <div class="stat-icon system">
            <el-icon><CircleCheck /></el-icon>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 图表区域 -->
    <div class="charts-section">
      <el-card class="chart-card" v-loading="loading.trend">
        <template #header>
          <div class="card-header">
            <span>近 7 天用电量趋势图</span>
          </div>
        </template>
        <div class="chart-container">
          <canvas ref="usageChart" width="400" height="200"></canvas>
        </div>
      </el-card>

      <el-card class="chart-card" v-loading="loading.services">
        <template #header>
          <div class="card-header">
            <span>系统运行状态</span>
            <el-button size="small" @click="fetchServices">刷新</el-button>
          </div>
        </template>
        <div class="status-container">
          <div
            v-for="svc in services"
            :key="svc.name"
            class="status-item"
          >
            <el-tag
              :type="svc.is_active ? 'success' : 'danger'"
              size="small"
              class="status-badge"
            >
              {{ svc.is_active ? '运行中' : '已停止' }}
            </el-tag>
            <span class="status-label">{{ svc.name }}</span>
          </div>
          <div v-if="services.length === 0" class="no-data">暂无服务状态数据</div>
        </div>
      </el-card>
    </div>

    <!-- 最近活动区域 -->
    <div class="recent-activities">
      <el-card v-loading="loading.activities">
        <template #header>
          <div class="card-header">
            <span>最近活动</span>
          </div>
        </template>
        <el-timeline v-if="activities.length > 0">
          <el-timeline-item
            v-for="(activity, idx) in activities"
            :key="idx"
            :timestamp="activity.timestamp"
            placement="top"
          >
            {{ activity.message }}
          </el-timeline-item>
        </el-timeline>
        <div v-else class="no-data">暂无活动记录</div>
      </el-card>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import Chart from 'chart.js/auto'
import { CircleCheck, Calendar, Document } from '@element-plus/icons-vue'
import api from '../utils/api.js'

export default {
  name: 'HomeView',
  components: {
    CircleCheck,
    Calendar,
    Document
  },
  setup() {
    const usageChart = ref(null)
    let chartInstance = null

    // 日期范围（默认本年）
    const currentYear = new Date().getFullYear()
    const totalEnergyDateRange = ref([
      `${currentYear}-01-01`,
      new Date().toISOString().slice(0, 10)
    ])

    const dateShortcuts = [
      {
        text: '本年',
        value: () => {
          const now = new Date()
          return [new Date(now.getFullYear(), 0, 1), now]
        }
      },
      {
        text: '本月',
        value: () => {
          const now = new Date()
          return [new Date(now.getFullYear(), now.getMonth(), 1), now]
        }
      },
      {
        text: '近30天',
        value: () => {
          const end = new Date()
          const start = new Date()
          start.setDate(start.getDate() - 29)
          return [start, end]
        }
      }
    ]

    // 数据状态
    const totalEnergy = reactive({ total_kwh: 0, cooling_kwh: 0, heating_kwh: 0 })
    const summary = reactive({ today_kwh: 0, month_kwh: 0 })
    const plcRate = reactive({ online_count: 0, offline_count: 0, total_count: 0, rate: 0 })
    const services = ref([])
    const activities = ref([])
    const trendData = ref([])

    const loading = reactive({
      totalEnergy: false,
      summary: false,
      plcRate: false,
      trend: false,
      services: false,
      activities: false
    })

    // API 调用
    async function fetchTotalEnergy() {
      loading.totalEnergy = true
      try {
        let params = {}
        if (totalEnergyDateRange.value && totalEnergyDateRange.value.length === 2) {
          params.start_date = totalEnergyDateRange.value[0]
          params.end_date = totalEnergyDateRange.value[1]
        }
        const res = await api.get('/api/dashboard/total-energy/', params)
        if (res.success) {
          totalEnergy.total_kwh = res.data.total_kwh
          totalEnergy.cooling_kwh = res.data.cooling_kwh
          totalEnergy.heating_kwh = res.data.heating_kwh
        }
      } catch (e) {
        console.error('总电量查询失败:', e.message)
      } finally {
        loading.totalEnergy = false
      }
    }

    async function fetchSummary() {
      loading.summary = true
      try {
        const res = await api.get('/api/dashboard/summary/')
        if (res.success) {
          summary.today_kwh = res.data.today_kwh
          summary.month_kwh = res.data.month_kwh
        }
      } catch (e) {
        console.error('汇总数据查询失败:', e.message)
      } finally {
        loading.summary = false
      }
    }

    async function fetchPlcRate() {
      loading.plcRate = true
      try {
        const res = await api.get('/api/dashboard/plc-online-rate/')
        if (res.success) {
          plcRate.online_count = res.data.online_count
          plcRate.offline_count = res.data.offline_count
          plcRate.total_count = res.data.total_count
          plcRate.rate = res.data.rate
        }
      } catch (e) {
        console.error('PLC运行率查询失败:', e.message)
      } finally {
        loading.plcRate = false
      }
    }

    async function fetchTrend() {
      loading.trend = true
      try {
        const res = await api.get('/api/dashboard/trend/', { days: 7 })
        if (res.success) {
          trendData.value = res.data
          renderChart(res.data)
        }
      } catch (e) {
        console.error('趋势数据查询失败:', e.message)
      } finally {
        loading.trend = false
      }
    }

    async function fetchServices() {
      loading.services = true
      try {
        const res = await api.get('/api/dashboard/services/')
        if (res.success) {
          services.value = res.data
        }
      } catch (e) {
        console.error('服务状态查询失败:', e.message)
      } finally {
        loading.services = false
      }
    }

    async function fetchActivities() {
      loading.activities = true
      try {
        const res = await api.get('/api/dashboard/activities/', { limit: 20 })
        if (res.success) {
          activities.value = res.data
        }
      } catch (e) {
        console.error('最近活动查询失败:', e.message)
      } finally {
        loading.activities = false
      }
    }

    function renderChart(data) {
      if (!usageChart.value) return
      const labels = data.map(d => d.date.slice(5))  // MM-DD
      const totalValues = data.map(d => d.total_kwh)
      const coolingValues = data.map(d => d.cooling_kwh)
      const heatingValues = data.map(d => d.heating_kwh)

      if (chartInstance) {
        chartInstance.destroy()
      }
      const ctx = usageChart.value.getContext('2d')
      chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: '总用电量 (kWh)',
              data: totalValues,
              borderColor: '#667eea',
              backgroundColor: 'rgba(102, 126, 234, 0.1)',
              tension: 0.4,
              fill: true
            },
            {
              label: '制冷 (kWh)',
              data: coolingValues,
              borderColor: '#f56c6c',
              backgroundColor: 'rgba(245, 108, 108, 0.05)',
              tension: 0.4,
              fill: false
            },
            {
              label: '制热 (kWh)',
              data: heatingValues,
              borderColor: '#e6a23c',
              backgroundColor: 'rgba(230, 162, 60, 0.05)',
              tension: 0.4,
              fill: false
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              position: 'top'
            }
          },
          scales: {
            y: {
              beginAtZero: true
            }
          }
        }
      })
    }

    onMounted(() => {
      fetchTotalEnergy()
      fetchSummary()
      fetchPlcRate()
      fetchTrend()
      fetchServices()
      fetchActivities()
    })

    return {
      usageChart,
      totalEnergyDateRange,
      dateShortcuts,
      totalEnergy,
      summary,
      plcRate,
      services,
      activities,
      trendData,
      loading,
      fetchTotalEnergy,
      fetchServices
    }
  }
}
</script>

<style scoped>
.page-container {
  width: 100%;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  color: #303133;
  font-size: 20px;
  font-weight: 600;
}

.page-subtitle {
  margin: 5px 0 0 0;
  color: #909399;
  font-size: 14px;
}

/* 总电量查询区域 */
.total-energy-section {
  margin-bottom: 20px;
}

.total-energy-values {
  display: flex;
  gap: 40px;
  padding: 10px 0;
}

.energy-item {
  text-align: center;
}

.energy-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.energy-item.cooling .energy-value {
  color: #409eff;
}

.energy-item.heating .energy-value {
  color: #f56c6c;
}

.energy-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

/* 统计卡片样式 */
.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  transition: all 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
}

.stat-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 5px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 24px;
}

.stat-icon.today {
  background-color: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.stat-icon.month {
  background-color: rgba(144, 147, 153, 0.1);
  color: #909399;
}

.stat-icon.system {
  background-color: rgba(102, 126, 234, 0.1);
  color: #667eea;
}

/* 图表区域样式 */
.charts-section {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

.chart-card {
  height: 320px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.date-picker-group {
  margin-left: auto;
}

.chart-container {
  height: calc(100% - 50px);
  width: 100%;
}

/* 状态容器样式 */
.status-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 10px 0;
  overflow-y: auto;
  max-height: 220px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-badge {
  min-width: 56px;
  text-align: center;
}

.status-label {
  font-size: 13px;
  color: #303133;
  font-family: monospace;
}

/* 最近活动样式 */
.recent-activities {
  margin-bottom: 20px;
}

.no-data {
  text-align: center;
  color: #c0c4cc;
  padding: 30px 0;
  font-size: 14px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .stats-cards {
    grid-template-columns: 1fr 1fr;
  }

  .charts-section {
    grid-template-columns: 1fr;
  }

  .total-energy-values {
    flex-wrap: wrap;
    gap: 20px;
  }
}

@media (max-width: 480px) {
  .stats-cards {
    grid-template-columns: 1fr;
  }
}
</style>
