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
      <!-- 顶部导航栏：每个子系统一个标签 + 历史数据链接 + 按需采集加载指示 -->
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

        <!-- v0.5.6: 按需采集进行中显示小圆形加载指示，替代原刷新按钮 -->
        <div v-if="ondemandInFlight" class="nav-loading-indicator">
          <el-icon class="is-loading" style="font-size: 16px; color: #409eff;">
            <Loading />
          </el-icon>
          <span class="nav-loading-text">采集中…</span>
        </div>
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
              <!-- v0.5.6: 移除各列单独时间戳（AC-004-2），改为底部统一时间戳 -->
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

      <!-- v0.5.6: 统一时间戳（REQ-FUNC-004，AC-004-1） -->
      <div class="panel-footer" v-if="hasData">
        <el-text type="info" size="small">
          上次数据更新于：{{ lastUpdatedAt || '—' }}
        </el-text>
      </div>
    </template>
  </div>
</template>

<script>
import { Loading } from '@element-plus/icons-vue'
import api from '@/utils/api.js'
import mqtt from 'mqtt'

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
  components: { Loading },
  data() {
    return {
      loading: false,
      deviceData: {},
      refreshTimer: null,
      // v0.5.6: 按需采集状态（MOD-FE-01）
      ondemandInFlight: false,
      ondemandTimeoutTimer: null,
      _mqttDisconnect: null,
    }
  },
  computed: {
    specificPart() {
      return this.$route.query.specific_part || ''
    },
    hasData() {
      return Object.keys(this.deviceData).length > 0
    },
    // v0.5.6: 统一时间戳（REQ-FUNC-004，取所有参数 collected_at 最大值）
    lastUpdatedAt() {
      let maxTs = null
      for (const groupData of Object.values(this.deviceData)) {
        for (const subTypeData of Object.values(groupData.sub_types || {})) {
          for (const param of (subTypeData.params || [])) {
            if (param.collected_at && (!maxTs || param.collected_at > maxTs)) {
              maxTs = param.collected_at
            }
          }
        }
      }
      return maxTs || null
    },
  },
  mounted() {
    if (this.specificPart) {
      this.fetchData()
      this.triggerOndemandRefresh()  // 打开即触发一次按需采集
      this.startAutoRefresh()
      this.connectMqttDone()
    }
  },
  watch: {
    specificPart(newVal) {
      this.deviceData = {}
      this.stopAutoRefresh()
      this.disconnectMqttDone()
      this._clearOndemandTimeout()
      this.ondemandInFlight = false
      if (newVal) {
        this.fetchData()
        this.triggerOndemandRefresh()
        this.startAutoRefresh()
        this.connectMqttDone()
      }
    },
  },
  beforeUnmount() {
    this.stopAutoRefresh()
    this.disconnectMqttDone()
    this._clearOndemandTimeout()
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

    // v0.5.6: 触发按需采集请求（REQ-FUNC-001，MOD-FE-01）
    async triggerOndemandRefresh() {
      if (!this.specificPart) return
      if (this.ondemandInFlight) return  // 防重入：当前采集进行中则跳过

      this.ondemandInFlight = true
      try {
        await api.post('/api/devices/ondemand-refresh/', {
          specific_part: this.specificPart,
        })
        // 等待 MQTT done 通知触发 fetchData()
        // 超时 20 秒后降级重置，不阻塞下一轮
        this.ondemandTimeoutTimer = setTimeout(() => {
          console.warn('[DeviceCards] 按需采集 done 通知 20s 超时，重置 inFlight 标志')
          this.ondemandInFlight = false
          this.ondemandTimeoutTimer = null
          // 降级：直接读取 DB 快照
          this.fetchData()
        }, 20000)
      } catch (e) {
        // 降级：MQTT broker 不可达或 503，直接读 DB 快照
        console.warn('[DeviceCards] ondemand 请求失败，降级读取 DB:', e)
        this.ondemandInFlight = false
        await this.fetchData()
      }
    },

    // v0.5.6: 连接 MQTT WebSocket 订阅 done 通知（REQ-FUNC-003，AC-003-1）
    // 直接使用 paho mqtt 客户端，不通过 useMqttWebSocket composable（避免 Options API 中
    // onUnmounted 无法注册的问题），手动在 beforeUnmount 中调用 disconnectMqttDone()。
    connectMqttDone() {
      if (!this.specificPart) return
      const topic = `/datacollection/plc/ondemand/done/${this.specificPart}`
      try {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const brokerUrl = `${proto}://${window.location.host}/mqtt-ws/`
        const mqttClient = mqtt.connect(brokerUrl, { clean: true })
        mqttClient.on('connect', () => {
          mqttClient.subscribe(topic, { qos: 1 })
        })
        mqttClient.on('message', (receivedTopic, payload) => {
          this.handleOndemandDone({ topic: receivedTopic, payload: payload.toString() })
        })
        mqttClient.on('error', (err) => {
          console.warn('[DeviceCards] MQTT WebSocket 错误，降级为 30s 轮询:', err)
          this._mqttDisconnect = null
        })
        this._mqttDisconnect = () => { mqttClient.end() }
      } catch (e) {
        console.warn('[DeviceCards] MQTT WebSocket 连接失败，降级为 30s 轮询:', e)
        this._mqttDisconnect = null
      }
    },

    disconnectMqttDone() {
      if (this._mqttDisconnect) {
        try {
          this._mqttDisconnect()
        } catch (e) {
          // 忽略断开时的错误
        }
        this._mqttDisconnect = null
      }
    },

    // v0.5.6: 处理 MQTT done 通知（REQ-FUNC-003，AC-003-2）
    handleOndemandDone({ payload }) {
      try {
        const data = JSON.parse(payload)
        if (data.specific_part !== this.specificPart) return
        // 清除超时计时器，重置 inFlight 标志
        this._clearOndemandTimeout()
        this.ondemandInFlight = false
        // 立即拉取最新数据更新 UI
        this.fetchData()
      } catch (e) {
        // JSON 解析失败或字段不匹配，忽略
      }
    },

    _clearOndemandTimeout() {
      if (this.ondemandTimeoutTimer) {
        clearTimeout(this.ondemandTimeoutTimer)
        this.ondemandTimeoutTimer = null
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
        // v0.5.1: 枚举 1-4；旧值 0 兼容展示为制冷（REQ-NFR-001）
        const modes = { 0: '制冷', 1: '制冷', 2: '制热', 3: '通风', 4: '除湿' }
        return modes[v] !== undefined ? modes[v] : String(v)
      }

      if (paramName === 'central_energy_supply') {
        // v0.5.1: 三值枚举展示；旧值 0 兼容展示为「无」（REQ-FUNC-003, Q5）
        const supplyModes = { 1: '制冷', 2: '制热', 3: '无' }
        return supplyModes[v] !== undefined ? supplyModes[v] : '无'
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

    // v0.5.6: 30 秒定时器改为触发按需采集（REQ-FUNC-002，AC-002-1）
    // 若 MQTT WebSocket 不可用（_mqttDisconnect 为 null），30s 后降级直接读 DB
    startAutoRefresh() {
      this.refreshTimer = setInterval(() => {
        if (this._mqttDisconnect) {
          // MQTT 可用：触发按需采集，等待 done 通知更新 UI
          this.triggerOndemandRefresh()
        } else {
          // 降级：MQTT 不可用，直接读 DB 快照（AC-003-3）
          this.fetchData()
        }
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

/* v0.5.6: 按需采集进行中加载指示器（替代刷新按钮） */
.nav-loading-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  flex-shrink: 0;
  padding: 0 6px;
}

.nav-loading-text {
  font-size: 12px;
  color: #409eff;
}

/* 卡片主体区域 */
.cards-scroll-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 12px;
  padding: 12px;
  overflow-x: auto;
}

.subtype-col {
  min-width: 180px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 6px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}

.col-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.params-list {
  padding: 6px 0;
}

.param-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  font-size: 13px;
  border-bottom: 1px solid #f5f5f5;
}

.param-row:last-child {
  border-bottom: none;
}

.param-label {
  color: #606266;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 60%;
}

.param-value {
  color: #303133;
  font-weight: 500;
  flex-shrink: 0;
  margin-left: 8px;
}

/* v0.5.6: 底部统一时间戳（REQ-FUNC-004） */
.panel-footer {
  padding: 8px 12px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  text-align: right;
}
</style>
