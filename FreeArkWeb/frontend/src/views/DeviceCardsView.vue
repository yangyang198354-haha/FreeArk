<template>
  <div class="device-panel">
    <!-- 无专有部分提示 -->
    <el-alert
      v-if="!specificPart"
      title="请先选择专有部分"
      description="设备卡片面板需要在已选择专有部分的上下文中查看，请从专有部分详情页进入。"
      type="warning"
      show-icon
      :closable="false"
    />

    <template v-else>
      <!-- 顶部导航栏：每个子系统一个标签 + 历史数据链接 -->
      <div class="panel-nav-bar">
        <template v-for="(groupData, groupKey) in deviceData" :key="groupKey">
          <template v-for="(subTypeData, subKey) in groupData.sub_types" :key="subKey">
            <!-- 在第一个房间子面板前插入"温控面板"历史入口 -->
            <template v-if="subKey === 'panel_study_room'">
              <div class="nav-item">
                <span class="nav-label">温控面板</span>
                <el-button
                  type="primary"
                  link
                  size="small"
                  class="nav-history-btn"
                  @click="goToRoomHistory"
                >历史数据 ›</el-button>
              </div>
              <div class="nav-divider" />
            </template>

            <div class="nav-item">
              <span class="nav-label">{{ subTypeData.display }}</span>
              <el-button
                v-if="['main_thermostat', 'fresh_air', 'energy_meter', 'hydraulic_module'].includes(subKey)"
                type="primary"
                link
                size="small"
                class="nav-history-btn"
                @click="goToHistory(subKey, subTypeData.display)"
              >历史数据 ›</el-button>
            </div>
            <div class="nav-divider" />
          </template>
        </template>

        <el-button
          type="primary"
          :loading="loading"
          size="small"
          @click="fetchData"
          class="nav-refresh-btn"
        >
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <!-- 骨架屏 -->
      <el-skeleton :rows="8" animated v-if="loading && !hasData" style="padding: 16px;" />

      <!-- 无数据 -->
      <el-empty description="暂无设备参数数据" v-else-if="!loading && !hasData" />

      <!-- 横向卡片行：每个 sub_type 一列 -->
      <div v-else class="cards-scroll-row">
        <template v-for="(groupData, groupKey) in deviceData" :key="groupKey">
          <div
            v-for="(subTypeData, subKey) in groupData.sub_types"
            :key="subKey"
            class="subtype-col"
          >
            <div class="col-header">
              <span class="col-title">{{ subTypeData.display }}</span>
              <span class="col-time">{{ getCollectedAt(subTypeData.params) }}</span>
            </div>
            <div class="params-list">
              <div
                v-for="param in expandParams(subTypeData.params)"
                :key="param.param_name"
                class="param-row"
              >
                <span class="param-label" :title="param.display_name">{{ param.display_name }}</span>
                <span class="param-value">{{ formatValue(param.param_name, param.value) }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div class="panel-footer" v-if="hasData">
        <el-text type="info" size="small">每 30 秒自动刷新</el-text>
      </div>
    </template>
  </div>
</template>

<script>
import { Refresh } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

// 温度字段（int16 ÷10, °C）
const TEMP_PARAMS = new Set([
  'living_room_temperature', 'living_room_ntc_temp', 'living_room_dew_point_setting', 'living_room_temp_setting',
  'study_room_temperature', 'study_room_ntc_temperature', 'study_room_dew_point_setting', 'study_room_temp_setting',
  'bedroom_temperature', 'bedroom_ntc_temperature', 'bedroom_dew_point_setting', 'bedroom_temp_setting',
  'children_room_temperature', 'children_room_ntc_temperature', 'children_room_dew_point_setting', 'children_room_temp_setting',
  'fourth_children_room_temperature', 'fourth_children_room_ntc_temperature', 'fourth_children_room_dew_point_setting', 'fourth_children_room_temp_setting',
  'hydraulic_module_inlet_temp', 'hydraulic_module_outlet_temp',
  'fresh_air_inlet_temp', 'coil_inlet_temp', 'coil_outlet_temp', 'coil_supply_air_temp',
  'supply_air_temp_setting',
])

// 湿度字段（int16 ÷10, %）
const HUMIDITY_PARAMS = new Set([
  'living_room_humidity', 'study_room_humidity', 'bedroom_humidity',
  'children_room_humidity', 'fourth_children_room_humidity',
])

// 开关字段（0→关闭, 1→开启）
const SWITCH_PARAMS = new Set([
  'living_room_switch', 'study_room_switch', 'bedroom_switch',
  'children_room_switch', 'fourth_children_room_switch',
  'system_switch', 'humidification_switch',
])

// 新风机故障状态位定义（DB14.DBW388 bit 0-8）
const FRESH_AIR_FAULT_BITS = [
  '风机状态故障', '出风温度异常状态', '进风温度传感器故障', '回水温度传感器故障',
  '进水温度传感器故障', '加湿器故障', '新风水阀故障', '防冻保护故障', '出风温度传感器故障',
]

// 故障字段（0→无, 其他→故障）
const FAULT_PARAMS = new Set([
  'living_room_temp_sensor_error', 'living_room_humidity_sensor_error',
  'living_room_external_temp_sensor_error', 'living_room_communication_error',
  'study_room_temp_sensor_error', 'study_room_humidity_sensor_error',
  'study_room_external_temp_sensor_error', 'study_room_communication_error',
  'bedroom_temp_sensor_error', 'bedroom_humidity_sensor_error',
  'bedroom_external_temp_sensor_error', 'bedroom_communication_error',
  'children_room_temp_sensor_error', 'children_room_humidity_sensor_error',
  'children_room_external_temp_sensor_error', 'children_room_communication_error',
  'fourth_children_room_temp_sensor_error', 'fourth_children_room_humidity_sensor_error',
  'fourth_children_room_external_temp_sensor_error', 'fourth_children_room_communication_error',
  'fresh_air_unit_stop_error', 'fresh_air_unit_communication_error',
  'hydraulic_module_low_temp_error',
  'energy_meter_status_communication_error',
  'air_quality_sensor_communication_error',
])

export default {
  name: 'DeviceCardsView',
  components: { Refresh },
  data() {
    return {
      loading: false,
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
        const response = await api.get('/api/devices/realtime-params/', {
          specific_part: this.specificPart,
        })
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

    goToRoomHistory() {
      this.$router.push({
        name: 'RoomHistory',
        query: { specific_part: this.specificPart },
      })
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

    getCollectedAt(params) {
      if (!params || !params.length) return ''
      const t = params.find(p => p.collected_at)?.collected_at
      return t ? t.slice(11, 16) : ''
    },

    expandParams(params) {
      const result = []
      for (const param of params) {
        if (param.param_name === 'fresh_air_fault_status') {
          const raw = param.value !== null && param.value !== undefined ? Number(param.value) : 0
          FRESH_AIR_FAULT_BITS.forEach((name, i) => {
            result.push({
              param_name: `fresh_air_fault_bit_${i}`,
              display_name: name,
              value: (raw >> i) & 1,
            })
          })
        } else {
          result.push(param)
        }
      }
      return result
    },

    formatValue(paramName, rawValue) {
      if (rawValue === null || rawValue === undefined) return '-'
      const v = Number(rawValue)

      if (TEMP_PARAMS.has(paramName)) {
        return (v / 10).toFixed(1) + '°C'
      }

      if (HUMIDITY_PARAMS.has(paramName)) {
        return (v / 10).toFixed(1) + '%'
      }

      if (SWITCH_PARAMS.has(paramName)) {
        return v === 0 ? '关闭' : '开启'
      }

      if (paramName.startsWith('fresh_air_fault_bit_')) {
        return v === 0 ? '无' : '故障'
      }

      if (FAULT_PARAMS.has(paramName)) {
        return v === 0 ? '无' : '故障(' + v + ')'
      }

      if (paramName === 'hydraulic_module_valve_opening' || paramName === 'fresh_air_valve_opening') {
        return (v / 10).toFixed(1)
      }

      if (paramName === 'filter_alarm_hours_setting' || paramName === 'filter_used_hours') {
        return v + 'h'
      }

      if (paramName === 'work_time') {
        return v + 'h'
      }

      if (paramName === 'total_hot_quantity' || paramName === 'total_cold_quantity') {
        return v + 'kw·h'
      }

      if (paramName === 'co2') {
        return v + 'ppm'
      }

      if (paramName === 'pm25') {
        return v + 'μg/m³'
      }

      if (paramName === 'humidification_humidity_upper_limit' || paramName === 'humidification_humidity_lower_limit') {
        return v + '%'
      }

      if (paramName === 'fan_gear_feedback' || paramName === 'system_air_volume_setting') {
        const gears = { 0: '低速', 1: '中速', 2: '高速' }
        return gears[v] !== undefined ? gears[v] : String(v)
      }

      if (paramName === 'operation_mode') {
        const modes = { 1: '制冷', 2: '制热', 3: '通风', 4: '除湿' }
        return modes[v] !== undefined ? modes[v] : String(v)
      }

      if (paramName === 'central_energy_supply') {
        return v === 0 ? '无' : '有'
      }

      if (paramName === 'away_energy_saving') {
        return v === 0 ? '关闭' : '开启'
      }

      if (paramName === 'living_room_condensation_alert' ||
          paramName.endsWith('_condensation_alert')) {
        return String(v)
      }

      return String(rawValue)
    },

    startAutoRefresh() {
      this.refreshTimer = setInterval(() => { this.fetchData() }, 30000)
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
.device-panel {
  width: 100%;
  background-color: #f5f7fa;
  min-height: 100vh;
  box-sizing: border-box;
}

/* 顶部导航栏 */
.panel-nav-bar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  padding: 6px 12px;
  overflow-x: auto;
  white-space: nowrap;
}

.nav-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
  flex-shrink: 0;
}

.nav-label {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.nav-history-btn {
  font-size: 12px;
  padding: 0 2px;
}

.nav-divider {
  width: 1px;
  height: 16px;
  background: #dcdfe6;
  flex-shrink: 0;
}

.nav-refresh-btn {
  margin-left: auto;
  flex-shrink: 0;
}

/* 横向卡片滚动行 */
.cards-scroll-row {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 0;
  overflow-x: auto;
  padding: 12px 12px 16px;
  align-items: flex-start;
}

/* 每个 sub_type 列 */
.subtype-col {
  flex: 0 0 178px;
  width: 178px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-right: none;
  overflow: hidden;
}

.subtype-col:first-child {
  border-radius: 4px 0 0 4px;
}

.subtype-col:last-child {
  border-right: 1px solid #e4e7ed;
  border-radius: 0 4px 4px 0;
}

.col-header {
  padding: 6px 8px 4px;
  border-bottom: 2px solid #409eff;
  background: #f0f6ff;
  overflow: hidden;
}

.col-title {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.col-time {
  font-size: 11px;
  color: #909399;
  display: block;
  margin-top: 1px;
}

/* 参数列表 */
.params-list {
  padding: 4px 0;
}

.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 8px;
  border-bottom: 1px solid #f2f3f5;
  font-size: 12px;
  min-height: 24px;
}

.param-row:last-child {
  border-bottom: none;
}

.param-row:nth-child(even) {
  background-color: #f9fafb;
}

.param-label {
  color: #606266;
  flex: 1;
  min-width: 0;
  margin-right: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.param-value {
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
}

.panel-footer {
  text-align: center;
  padding: 8px 0 16px;
}
</style>
