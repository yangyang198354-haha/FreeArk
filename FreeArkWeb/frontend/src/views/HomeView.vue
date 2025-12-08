<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>系统看板</h2>
      <p class="page-subtitle">实时监控系统运行状态和能耗数据</p>
    </div>
    
    <!-- 统计卡片区域 -->
    <div class="stats-cards">
      <el-card class="stat-card">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value">1,234.56</div>
            <div class="stat-label">总用电量 (kWh)</div>
          </div>
          <div class="stat-icon energy">
            <el-icon><Lightning /></el-icon>
          </div>
        </div>
      </el-card>
      
      <el-card class="stat-card">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value">89.32</div>
            <div class="stat-label">今日用电量 (kWh)</div>
          </div>
          <div class="stat-icon today">
            <el-icon><Calendar /></el-icon>
          </div>
        </div>
      </el-card>
      
      <el-card class="stat-card">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value">2,678.90</div>
            <div class="stat-label">本月用电量 (kWh)</div>
          </div>
          <div class="stat-icon month">
            <el-icon><Document /></el-icon>
          </div>
        </div>
      </el-card>
      
      <el-card class="stat-card">
        <div class="stat-content">
          <div class="stat-info">
            <div class="stat-value">98.5%</div>
            <div class="stat-label">系统运行率</div>
          </div>
          <div class="stat-icon system">
            <el-icon><CircleCheck /></el-icon>
          </div>
        </div>
      </el-card>
    </div>
    
    <!-- 图表区域 -->
    <div class="charts-section">
      <el-card class="chart-card">
        <template #header>
          <div class="card-header">
            <span>用电量趋势图</span>
          </div>
        </template>
        <div class="chart-container">
          <canvas ref="usageChart" width="400" height="200"></canvas>
        </div>
      </el-card>
      
      <el-card class="chart-card">
        <template #header>
          <div class="card-header">
            <span>系统运行状态</span>
          </div>
        </template>
        <div class="status-container">
          <div class="status-item">
            <el-badge :value="'运行中'" type="success" class="status-badge" />
            <span class="status-label">后端服务</span>
          </div>
          <div class="status-item">
            <el-badge :value="'运行中'" type="success" class="status-badge" />
            <span class="status-label">MQTT服务</span>
          </div>
          <div class="status-item">
            <el-badge :value="'运行中'" type="success" class="status-badge" />
            <span class="status-label">数据采集服务</span>
          </div>
          <div class="status-item">
            <el-badge :value="'正常'" type="success" class="status-badge" />
            <span class="status-label">数据库连接</span>
          </div>
        </div>
      </el-card>
    </div>
    
    <!-- 最近活动区域 -->
    <div class="recent-activities">
      <el-card>
        <template #header>
          <div class="card-header">
            <span>最近活动</span>
          </div>
        </template>
        <el-timeline>
          <el-timeline-item timestamp="2025-11-29 23:00" placement="top">
            系统自动生成月度用量报表
          </el-timeline-item>
          <el-timeline-item timestamp="2025-11-29 22:30" placement="top">
            用户admin登录系统
          </el-timeline-item>
          <el-timeline-item timestamp="2025-11-29 22:00" placement="top">
            数据采集服务完成今日数据采集
          </el-timeline-item>
          <el-timeline-item timestamp="2025-11-29 21:30" placement="top">
            系统自动清理7天前的PLC数据
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import Chart from 'chart.js/auto'
import { CircleCheck, Lightning, Calendar, Document } from '@element-plus/icons-vue'

export default {
  name: 'HomeView',
  components: {
    CircleCheck,
    Lightning,
    Calendar,
    Document
  },
  setup() {
    const usageChart = ref(null)
    let chartInstance = null
    
    onMounted(() => {
      // 初始化用电量趋势图
      initUsageChart()
    })
    
    const initUsageChart = () => {
      if (usageChart.value) {
        const ctx = usageChart.value.getContext('2d')
        chartInstance = new Chart(ctx, {
          type: 'line',
          data: {
            labels: ['11-23', '11-24', '11-25', '11-26', '11-27', '11-28', '11-29'],
            datasets: [{
              label: '用电量 (kWh)',
              data: [78.5, 82.3, 79.8, 85.2, 88.6, 91.3, 89.3],
              borderColor: '#667eea',
              backgroundColor: 'rgba(102, 126, 234, 0.1)',
              tension: 0.4,
              fill: true
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                display: false
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
    }
    
    return {
      usageChart
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

.stat-icon.energy {
  background-color: rgba(245, 106, 106, 0.1);
  color: #f56c6c;
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
  height: 300px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-container {
  height: calc(100% - 50px);
  width: 100%;
}

/* 状态容器样式 */
.status-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px 0;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-badge {
  margin-right: 10px;
}

.status-label {
  font-size: 14px;
  color: #303133;
}

/* 最近活动样式 */
.recent-activities {
  margin-bottom: 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .stats-cards {
    grid-template-columns: 1fr 1fr;
  }
  
  .charts-section {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .stats-cards {
    grid-template-columns: 1fr;
  }
}
</style>