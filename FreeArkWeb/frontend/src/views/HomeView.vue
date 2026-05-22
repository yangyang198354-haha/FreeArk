<template>
  <div class="home-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>系统看板</h2>
      <p class="page-subtitle">实时监控系统运行状态和能耗数据</p>
    </div>

    <!-- 顶部卡片行：总电量查询 + 系统开机状况（并排，OQ-004） -->
    <div class="top-cards-row">
      <!-- 总电量查询（原有） -->
      <div class="total-energy-wrapper">
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

      <!-- 系统开机状况（新增，v0.5.3；重设计 v0.5.3-r1） -->
      <div class="power-status-wrapper">
        <el-card class="power-status-card">
          <template #header>
            <div class="card-header">
              <span>开机情况</span>
            </div>
          </template>
          <div class="power-status-content" v-loading="loading.powerStatus">
            <!-- 主信息行：图标圆圈 + 开机率大数字 + 标签 -->
            <div class="ps-main-row">
              <div class="ps-icon-circle">
                <el-icon style="font-size: 24px; color: #67c23a;"><Cpu /></el-icon>
              </div>
              <div class="ps-rate-info">
                <div class="ps-rate-value">{{ powerStatus.power_on_rate.toFixed(1) }}%</div>
                <div class="ps-rate-label">开机率</div>
              </div>
            </div>
            <!-- 模式合计行：4 个 chip 水平排布 -->
            <div class="ps-mode-chips">
              <div class="ps-chip">
                <div class="ps-chip-num" style="color: var(--color-cooling);">{{ powerStatus.mode_distribution.cooling }}</div>
                <div class="ps-chip-name">制冷</div>
              </div>
              <div class="ps-chip">
                <div class="ps-chip-num" style="color: var(--color-heating);">{{ powerStatus.mode_distribution.heating }}</div>
                <div class="ps-chip-name">制热</div>
              </div>
              <div class="ps-chip">
                <div class="ps-chip-num" style="color: #e6a23c;">{{ powerStatus.mode_distribution.ventilation }}</div>
                <div class="ps-chip-name">通风</div>
              </div>
              <div class="ps-chip">
                <div class="ps-chip-num" style="color: #13c2c2;">{{ powerStatus.mode_distribution.dehumidification }}</div>
                <div class="ps-chip-name">除湿</div>
              </div>
              <div class="ps-chip" v-if="powerStatus.mode_distribution.unknown > 0">
                <div class="ps-chip-num" style="color: #909399;">{{ powerStatus.mode_distribution.unknown }}</div>
                <div class="ps-chip-name">未知</div>
              </div>
            </div>
          </div>
        </el-card>
      </div>
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
            <div class="stat-value" style="color: var(--color-success)">{{ plcRate.online_count }}</div>
            <div class="stat-label">PLC 在线</div>
            <div class="stat-sub">在线率 {{ plcRate.rate }}%</div>
          </div>
          <div class="stat-icon plc-online">
            <el-icon><CircleCheck /></el-icon>
          </div>
        </div>
      </el-card>

      <el-card class="stat-card" v-loading="loading.screenRate">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value" style="color: var(--color-success)">{{ screenRate.online_count }}</div>
            <div class="stat-label">大屏在线</div>
            <div class="stat-sub">在线率 {{ screenRate.rate }}%</div>
          </div>
          <div class="stat-icon screen-online">
            <el-icon><Monitor /></el-icon>
          </div>
        </div>
      </el-card>

      <el-card class="stat-card" v-loading="loading.plcRate">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value" style="color: var(--color-primary)">{{ plcRate.total_count }}</div>
            <div class="stat-label">总设备数</div>
          </div>
          <div class="stat-icon plc-total">
            <el-icon><Cpu /></el-icon>
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
import ChartDataLabels from 'chartjs-plugin-datalabels'
import { CircleCheck, CircleClose, Cpu, Calendar, Document, Monitor } from '@element-plus/icons-vue'
import api from '../utils/api.js'

// AC-UI-002-01/02/03: 注册 chartjs-plugin-datalabels 插件
Chart.register(ChartDataLabels)

export default {
  name: 'HomeView',
  components: {
    CircleCheck,
    CircleClose,
    Cpu,
    Calendar,
    Document,
    Monitor
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
    const screenRate = reactive({ online_count: 0, total_count: 0, rate: 0 })
    const services = ref([])
    const activities = ref([])
    const trendData = ref([])
    // v0.5.3：系统开机状况
    const powerStatus = reactive({
      powered_on_count: 0,
      total_count: 0,
      power_on_rate: 0.0,
      mode_distribution: {
        cooling: 0,
        heating: 0,
        ventilation: 0,
        dehumidification: 0,
        unknown: 0
      }
    })

    const loading = reactive({
      totalEnergy: false,
      summary: false,
      plcRate: false,
      screenRate: false,
      trend: false,
      services: false,
      activities: false,
      powerStatus: false
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

    async function fetchScreenRate() {
      loading.screenRate = true
      try {
        const res = await api.get('/api/dashboard/screen-online-rate/')
        if (res.success) {
          screenRate.online_count = res.data.online_count
          screenRate.total_count = res.data.total_count
          screenRate.rate = res.data.rate
        }
      } catch (e) {
        console.error('大屏在线率查询失败:', e.message)
      } finally {
        loading.screenRate = false
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

    // AC-UI-002-01~07: Combo Chart（§9.4）
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
        // AC-UI-002-01: 容器类型 bar 支持混合图
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              // AC-UI-002-01(c): 总用电量 — 折线，深灰（#1E293B）
              type: 'line',
              label: '总用电量 (kWh)',
              data: totalValues,
              borderColor: '#1E293B',
              backgroundColor: 'rgba(30, 41, 59, 0.05)',
              borderWidth: 2,
              tension: 0.35,
              fill: false,
              pointRadius: 4,
              pointHoverRadius: 6,
              pointBackgroundColor: '#1E293B',
              order: 0,
              // AC-UI-002-03: 折线数据标签
              datalabels: {
                anchor: 'end',
                align: 'top',
                formatter: v => v.toFixed(1),
                font: { size: 11, weight: '500' },
                color: '#1E293B',
                offset: 4,
                clamp: true,
                clip: false
              }
            },
            {
              // AC-UI-002-01(a): 制冷 — 柱状，蓝色（#2563EB）
              type: 'bar',
              label: '制冷 (kWh)',
              data: coolingValues,
              backgroundColor: 'rgba(37, 99, 235, 0.75)',
              borderColor: '#2563EB',
              borderWidth: 1,
              borderRadius: 3,
              order: 1,
              // AC-UI-002-02: 柱状数据标签（零值不显示，AC-UI-002-04）
              datalabels: {
                anchor: 'end',
                align: 'top',
                formatter: v => v > 0 ? v.toFixed(1) : '',
                font: { size: 11, weight: '500' },
                color: '#2563EB',
                clamp: true,
                clip: false
              }
            },
            {
              // AC-UI-002-01(b): 制热 — 柱状，红色（#EF4444）
              type: 'bar',
              label: '制热 (kWh)',
              data: heatingValues,
              backgroundColor: 'rgba(239, 68, 68, 0.75)',
              borderColor: '#EF4444',
              borderWidth: 1,
              borderRadius: 3,
              order: 2,
              // AC-UI-002-02: 柱状数据标签（零值不显示，AC-UI-002-04）
              datalabels: {
                anchor: 'end',
                align: 'top',
                formatter: v => v > 0 ? v.toFixed(1) : '',
                font: { size: 11, weight: '500' },
                color: '#EF4444',
                clamp: true,
                clip: false
              }
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            // AC-UI-002-06: 图例
            legend: {
              display: true,
              position: 'top'
            },
            // AC-UI-002-05: tooltip 显示同一日期全部系列
            tooltip: {
              mode: 'index',
              intersect: false,
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} kWh`
              }
            },
            // 全局 datalabels 默认（被各 dataset 自有配置覆盖）
            datalabels: {}
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { font: { size: 12 }, color: '#475569' }
            },
            y: {
              beginAtZero: true,
              grid: { color: '#F1F5F9' },
              ticks: {
                font: { size: 12 },
                color: '#475569',
                callback: v => v.toFixed(0)
              }
            }
          },
          // §9.5: 顶部留白给数据标签
          layout: {
            padding: { top: 24 }
          }
        }
      })
    }

    // v0.5.3：系统开机状况 API 调用
    async function fetchPowerStatus() {
      loading.powerStatus = true
      try {
        const res = await api.get('/api/dashboard/power-status/')
        if (res.success) {
          powerStatus.powered_on_count = res.data.powered_on_count
          powerStatus.total_count = res.data.total_count
          powerStatus.power_on_rate = res.data.power_on_rate
          Object.assign(powerStatus.mode_distribution, res.data.mode_distribution)
        }
      } catch (e) {
        console.error('开机状况查询失败:', e.message)
      } finally {
        loading.powerStatus = false
      }
    }

    onMounted(() => {
      fetchTotalEnergy()
      fetchSummary()
      fetchPlcRate()
      fetchScreenRate()
      fetchTrend()
      fetchServices()
      fetchActivities()
      fetchPowerStatus()
    })

    return {
      usageChart,
      totalEnergyDateRange,
      dateShortcuts,
      totalEnergy,
      summary,
      plcRate,
      screenRate,
      services,
      activities,
      trendData,
      loading,
      fetchTotalEnergy,
      fetchServices,
      powerStatus
    }
  }
}
</script>

<style scoped>
/* MOD-UI-001-A: 根容器改为 .home-view，无 background/shadow/padding（由 Layout .content-wrapper 提供） */
.home-view {
  width: 100%;
}

.page-header {
  margin-bottom: 20px;
}

/* 页面标题对齐 Design Token（§11.5）*/
.page-header h2 {
  margin: 0;
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
}

.page-subtitle {
  margin: var(--space-1) 0 0 0;
  color: var(--color-text-placeholder);
  font-size: var(--font-size-sm);
}

/* 顶部卡片并排行（v0.5.3：总电量查询 + 系统开机状况） */
.top-cards-row {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
  align-items: stretch;
}

.total-energy-wrapper {
  flex: 2;
  display: flex;
  flex-direction: column;
}

.power-status-wrapper {
  flex: 1;
  min-width: 280px;
  display: flex;
  flex-direction: column;
}

/* flex 高度传递链：两个 wrapper 内的 el-card 撑满 wrapper 高度 */
.total-energy-wrapper :deep(.el-card),
.power-status-wrapper :deep(.el-card) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.total-energy-wrapper :deep(.el-card__body),
.power-status-wrapper :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* 系统开机状况卡片内容（v0.5.3-r1 重设计） */
.power-status-content {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex: 1;
  min-height: 100px;
}

/* 主信息行：图标圆圈 + 开机率 */
.ps-main-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.ps-icon-circle {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background-color: rgba(103, 194, 58, 0.1);
  display: flex;
  justify-content: center;
  align-items: center;
  flex-shrink: 0;
}

.ps-rate-info {
  display: flex;
  flex-direction: column;
}

.ps-rate-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
}

.ps-rate-label {
  font-size: 14px;
  color: #909399;
  margin-top: 2px;
}

/* 模式合计行：4 chip 水平排布 */
.ps-mode-chips {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
}

.ps-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
}

.ps-chip-num {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
}

.ps-chip-name {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
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

/* 对齐 Design Token（§2.3）*/
.energy-item.cooling .energy-value {
  color: var(--color-cooling);
}

.energy-item.heating .energy-value {
  color: var(--color-heating);
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

/* AC-UI-001-06: 统计卡片 hover（§5.4）*/
.stat-card {
  transition: transform 250ms ease-out, box-shadow 250ms ease-out;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-card-hover);
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
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-1);
}

.stat-label {
  font-size: var(--font-size-base);
  color: var(--color-text-placeholder);
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

.stat-icon.plc-online {
  background-color: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.stat-icon.screen-online {
  background-color: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.stat-icon.plc-offline {
  background-color: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.stat-icon.plc-total {
  background-color: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.stat-sub {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 2px;
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

/* §9.5: 固定高度，给数据标签充分空间 */
.chart-container {
  height: 300px;
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

/* MOD-UI-003: 删除 font-family: monospace，通过继承获得全局字体族 */
.status-label {
  font-size: 13px;
  color: #303133;
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
