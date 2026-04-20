<template>
  <div class="device-cards-container">
    <div class="page-header">
      <div class="header-left">
        <h2>设备实时参数</h2>
        <p class="page-subtitle" v-if="specificPart">
          专有部分：{{ specificPart }}
        </p>
      </div>
      <div class="header-right">
        <el-select v-model="groupFilter" placeholder="全部系统" clearable @change="fetchData" style="width: 160px; margin-right: 12px;">
          <el-option label="暖通 (HVAC)" value="hvac" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="fetchData">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 未选择专有部分时的提示 -->
    <el-alert
      v-if="!specificPart"
      title="请先选择专有部分"
      description="设备卡片面板需要在已选择专有部分的上下文中查看，请从专有部分详情页进入。"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 20px;"
    />

    <template v-else>
      <!-- 加载骨架 -->
      <el-skeleton :rows="6" animated v-if="loading && !hasData" />

      <!-- 无数据提示 -->
      <el-empty description="暂无设备参数数据" v-else-if="!loading && !hasData" />

      <!-- 分组展示 -->
      <div v-else class="groups-row">
        <div v-for="(groupData, groupKey) in deviceData" :key="groupKey" class="group-section">
          <h3 class="group-title">{{ groupData.display }}</h3>

          <div v-for="(subTypeData, subKey) in groupData.sub_types" :key="subKey" class="subtype-section">
            <div class="subtype-header">
              <h4 class="subtype-title">{{ subTypeData.display }}</h4>
              <el-button
                type="primary"
                link
                size="small"
                @click="goToHistory(subKey, subTypeData.display)"
              >
                历史数据 >
              </el-button>
            </div>

            <!-- 无参数提示 -->
            <div v-if="subTypeData.params.length === 0" class="no-params">
              <el-text type="info">暂无参数数据</el-text>
            </div>

            <!-- 参数键值对列表（卡片形式） -->
            <el-card v-else class="subtype-card" shadow="hover">
              <div class="params-list">
                <div
                  v-for="param in subTypeData.params"
                  :key="param.param_name"
                  class="param-row"
                >
                  <span class="param-name">{{ param.display_name || param.param_name }}</span>
                  <span class="param-value">
                    {{ param.value !== null && param.value !== undefined ? param.value : '-' }}
                    <el-tag
                      v-if="param.is_stale"
                      type="warning"
                      size="small"
                      class="stale-tag"
                    >数据超时</el-tag>
                  </span>
                </div>
              </div>

              <div class="card-footer">
                <el-text type="info" size="small">
                  最后更新: {{ getLastUpdated(subTypeData.params) }}
                </el-text>
              </div>
            </el-card>
          </div>
        </div>
      </div>

      <!-- 自动刷新提示 -->
      <div class="refresh-tip" v-if="hasData">
        <el-text type="info" size="small">每 30 秒自动刷新一次</el-text>
      </div>
    </template>
  </div>
</template>

<script>
import { Refresh } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'DeviceCardsView',
  components: {
    Refresh,
  },
  data() {
    return {
      loading: false,
      groupFilter: '',
      deviceData: {},
      refreshTimer: null,
    }
  },
  computed: {
    specificPart() {
      return this.$route.query.specific_part || ''
    },
    hasData() {
      return Object.keys(this.deviceData).length > 0
    },
  },
  mounted() {
    if (this.specificPart) {
      this.fetchData()
      this.startAutoRefresh()
    }
  },
  watch: {
    specificPart(newVal) {
      this.deviceData = {}
      this.stopAutoRefresh()
      if (newVal) {
        this.fetchData()
        this.startAutoRefresh()
      }
    },
  },
  beforeUnmount() {
    this.stopAutoRefresh()
  },
  methods: {
    async fetchData() {
      if (!this.specificPart) return
      this.loading = true
      try {
        const params = { specific_part: this.specificPart }
        if (this.groupFilter) {
          params.group = this.groupFilter
        }
        const response = await api.get('/api/devices/realtime-params/', params)
        if (response && response.success) {
          this.deviceData = response.data || {}
        } else {
          this.deviceData = {}
          this.$message.error('获取设备数据失败')
        }
      } catch (error) {
        console.error('获取设备实时参数失败:', error)
        this.$message.error('获取设备数据失败，请稍后重试')
      } finally {
        this.loading = false
      }
    },

    goToHistory(subType, subTypeDisplay) {
      this.$router.push({
        name: 'DeviceParamHistory',
        query: {
          specific_part: this.specificPart,
          sub_type: subType,
          sub_type_display: subTypeDisplay,
        },
      })
    },

    getLastUpdated(params) {
      const timestamps = params
        .filter(p => p.collected_at)
        .map(p => p.collected_at)
        .sort()
        .reverse()
      return timestamps.length > 0 ? timestamps[0] : '-'
    },

    startAutoRefresh() {
      this.refreshTimer = setInterval(() => {
        this.fetchData()
      }, 30000)
    },

    stopAutoRefresh() {
      if (this.refreshTimer) {
        clearInterval(this.refreshTimer)
        this.refreshTimer = null
      }
    },
  },
}
</script>

<style scoped>
.device-cards-container {
  width: 100%;
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
  box-sizing: border-box;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 25px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e4e7ed;
}

.header-left {
  flex: 1;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-header h2 {
  margin: 0;
  color: #303133;
  font-size: 22px;
  font-weight: 600;
}

.page-subtitle {
  margin: 8px 0 0 0;
  color: #909399;
  font-size: 14px;
}

.groups-row {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 24px;
  overflow-x: auto;
  padding-bottom: 12px;
}

.group-section {
  flex: 0 0 auto;
  min-width: 320px;
  max-width: 480px;
  margin-bottom: 0;
}

.group-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 16px 0;
  padding: 8px 0;
  border-bottom: 2px solid #409eff;
  display: inline-block;
}

.subtype-section {
  margin-bottom: 24px;
}

.subtype-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.subtype-title {
  font-size: 15px;
  font-weight: 500;
  color: #606266;
  margin: 0;
  padding-left: 10px;
  border-left: 3px solid #409eff;
}

.subtype-card {
  border-radius: 8px;
  transition: box-shadow 0.2s;
}

.no-params {
  padding: 12px 0;
  text-align: center;
}

.params-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid #f2f3f5;
  font-size: 13px;
}

.param-row:last-child {
  border-bottom: none;
}

.param-name {
  color: #606266;
  flex: 1;
  margin-right: 8px;
  word-break: break-all;
}

.param-value {
  font-weight: 500;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
  text-align: right;
}

.stale-tag {
  flex-shrink: 0;
}

.card-footer {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid #f2f3f5;
  text-align: right;
}

.refresh-tip {
  text-align: center;
  margin-top: 24px;
  padding-bottom: 16px;
}
</style>
