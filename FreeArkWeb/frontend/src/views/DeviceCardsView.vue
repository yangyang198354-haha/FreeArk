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
      <!-- REQ-FUNC-033/034: 页面头部 — 返回按钮 + 标题 + 副标题 + 设置入口（OQ-03） -->
      <div class="panel-page-header">
        <div class="panel-header-left">
          <el-button :icon="ArrowLeft" size="small" @click="goBack">返回</el-button>
          <h2 class="panel-title">设备面板</h2>
          <p class="page-subtitle">专有部分：{{ specificPart }}</p>
        </div>
        <div class="panel-header-right">
          <el-button type="warning" size="small" @click="goToSettings">参数设置</el-button>
        </div>
      </div>

      <!-- REQ-UI-005-B: 顶部导航栏分两行：第一行温控面板，第二行系统设备 -->
      <div class="panel-nav-bar">

        <!-- 第一行：温控面板组 -->
        <div class="nav-row nav-row--thermostat">
          <!-- 行首：分类标题 + 温控历史数据链接 -->
          <div class="nav-item nav-row-header">
            <span class="nav-label nav-category-label">温控面板</span>
            <el-button
              type="primary"
              link
              size="small"
              class="nav-history-btn"
              @click="goToRoomHistory"
            >历史数据 ›</el-button>
          </div>
          <div class="nav-divider" />
          <!-- 温控 Tab：按白名单顺序，仅渲染 deviceData 中实际存在的 -->
          <template v-for="{ subKey, subTypeData } in thermostatTabs" :key="subKey">
            <div class="nav-item">
              <span class="nav-label">{{ subTypeData.display }}</span>
            </div>
            <div class="nav-divider" />
          </template>
        </div>

        <!-- 行间分隔 -->
        <div class="nav-row-separator" />

        <!-- 第二行：系统设备组（固定 4 个：新风/能耗/水力/空气） -->
        <div class="nav-row nav-row--system">
          <div class="nav-item nav-row-header">
            <span class="nav-label nav-category-label">系统设备</span>
          </div>
          <div class="nav-divider" />
          <template v-for="{ subKey, subTypeData } in systemTabs" :key="subKey">
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
        </div>

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

      <!-- AC-UI-003-01/02: CSS Grid 布局，移除横向滚动与折叠控件（§10.1）-->
      <div v-else class="cards-grid">
        <template v-for="(groupData, groupKey) in deviceData" :key="groupKey">
          <div
            v-for="(subTypeData, subKey) in groupData.sub_types"
            :key="subKey"
            class="subtype-col"
          >
            <!-- AC-UI-003-01: 列标题区 — 移除折叠按钮，仅保留标题与历史数据按钮（§10.1）-->
            <div class="col-header">
              <span class="col-title">{{ subTypeData.display }}</span>
            </div>
            <!-- AC-UI-003-02: params-list 始终展开，无 v-show 隐藏逻辑（§10.1）-->
            <div class="params-list">
              <div
                v-for="param in expandParams(subTypeData.params)"
                :key="param.param_name"
                class="param-row"
              >
                <span class="param-label">{{ param.display_name }}</span>
                <span
                  class="param-value"
                  :class="getValueClass(param.param_name, param.value)"
                >{{ formatValue(param.param_name, param.value) }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- v0.5.6: 统一时间戳 — REQ-FUNC-002: 左对齐（AC-002-1） -->
      <div class="panel-footer" v-if="hasData">
        <el-text type="info" size="small">
          上次数据更新于：{{ lastUpdatedAt || '—' }}
        </el-text>
      </div>
    </template>
  </div>
</template>

<script>
import { Loading, ArrowLeft } from '@element-plus/icons-vue'
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

// 故障字段（0→正常, 其他→故障）— REQ-FUNC-005
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
  components: { Loading, ArrowLeft },
  data() {
    return {
      loading: false,
      deviceData: {},
      refreshTimer: null,
      // v0.5.6: 按需采集状态（MOD-FE-01）
      ondemandInFlight: false,
      ondemandTimeoutTimer: null,
      _mqttDisconnect: null,
      // AC-UI-003-01/02: collapsedCols 已移除（折叠功能取消，§10.1）
    }
  },
  computed: {
    specificPart() {
      return this.$route.query.specific_part || ''
    },
    hasData() {
      return Object.keys(this.deviceData).length > 0
    },

    // REQ-UI-005-B: 温控面板 Tab 白名单（按展示顺序排列）
    // subKey 以 panel_ 开头的子类型，5 房有 5 个，4 房有 4 个
    thermostatTabOrder() {
      return [
        'panel_living_room',
        'panel_study_room',
        'panel_bedroom',
        'panel_children_room',
        'panel_fourth_children_room',
      ]
    },

    // REQ-UI-005-B: 系统设备 Tab 白名单（固定 4 个，按展示顺序排列）
    systemTabOrder() {
      return ['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality']
    },

    // REQ-UI-005-B: 从 deviceData 中提取温控面板 Tab 列表（按白名单顺序）
    thermostatTabs() {
      const result = []
      for (const subKey of this.thermostatTabOrder) {
        for (const groupData of Object.values(this.deviceData)) {
          if (groupData.sub_types && groupData.sub_types[subKey]) {
            result.push({ subKey, subTypeData: groupData.sub_types[subKey] })
            break
          }
        }
      }
      return result
    },

    // REQ-UI-005-B: 从 deviceData 中提取系统设备 Tab 列表（按白名单顺序）
    systemTabs() {
      const result = []
      for (const subKey of this.systemTabOrder) {
        for (const groupData of Object.values(this.deviceData)) {
          if (groupData.sub_types && groupData.sub_types[subKey]) {
            result.push({ subKey, subTypeData: groupData.sub_types[subKey] })
            break
          }
        }
      }
      return result
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
      // collapsedCols 已移除（AC-UI-003-01/02）
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
    // REQ-UI-004: 返回按钮 — 读取 from query 参数，按来源页动态跳转
    goBack() {
      const from = this.$route.query.from
      if (from === 'fault-management') {
        this.$router.push('/device-management/faults')
      } else if (from === 'condensation-warnings') {
        this.$router.push('/device-management/condensation-warnings')
      } else {
        // from=device-list、无值或未知值：保持原有逻辑（同页跳转时 history > 1）
        if (window.history.length > 1) {
          this.$router.back()
        } else {
          this.$router.push('/device-management/device-list')
        }
      }
    },

    // REQ-FUNC-034 / OQ-03: 设备面板内的设置入口
    goToSettings() {
      if (this.specificPart) {
        this.$router.push(
          '/device-management/device-settings?specific_part=' +
          encodeURIComponent(this.specificPart)
        )
      }
    },

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

    // REQ-FUNC-005: 判断是否为状态类参数（故障/正常二值参数）（ADR-001）
    isStatusParam(paramName) {
      return FAULT_PARAMS.has(paramName) || paramName.startsWith('fresh_air_fault_bit_')
    },

    // REQ-FUNC-005: 返回动态 CSS class（AC-005-4/6，ADR-001）
    // 故障（非零） → 'status-fault'（红色）；正常（零） → 'status-ok'（绿色）；普通参数 → ''
    getValueClass(paramName, rawValue) {
      if (!this.isStatusParam(paramName)) return ''
      const v = rawValue === null || rawValue === undefined ? 0 : Number(rawValue)
      return v === 0 ? 'status-ok' : 'status-fault'
    },

    // AC-UI-003-01: toggleCollapse 已移除（折叠功能取消，§10.1）

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

      // REQ-FUNC-005: 新风机故障位（AC-005-3/4）—— '无'/'故障' → '正常'/'故障'
      if (paramName.startsWith('fresh_air_fault_bit_')) {
        return v === 0 ? '正常' : '故障'
      }

      // REQ-FUNC-005: 通用故障字段（AC-005-1/2/5）—— '无'/'故障(N)' → '正常'/'故障'
      if (FAULT_PARAMS.has(paramName)) {
        return v === 0 ? '正常' : '故障'
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
/* AC-UI-001-01: 对齐全局 Design Token（global.css），移除旧的局部颜色覆盖 */
.device-panel {
  /* 状态色（REQ-FUNC-005，AC-005-1/2）— 对齐全局 Token */
  --color-status-fault: var(--color-danger);
  --color-status-ok:   var(--color-success);

  /* 行间背景（微差）*/
  --color-bg-row-alt: rgba(37, 99, 235, 0.03);

  width: 100%;
  background-color: var(--color-bg-page);
  box-sizing: border-box;
}

/* REQ-FUNC-033/034 / REQ-UI-005-A: 页面头部（返回按钮 + 标题 + 设置入口） */
/* REQ-UI-005-A: padding 加入左右 16px，防止按钮贴边 */
.panel-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px 16px;
  margin-bottom: 4px;
}

.panel-header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel-header-left .el-button {
  align-self: flex-start;
}

/* REQ-UI-005-A: 返回与参数设置按钮统一最小宽度 80px */
.panel-header-left .el-button,
.panel-header-right .el-button {
  min-width: 80px;
}

.panel-title {
  margin: 4px 0 0 0;
  font-size: var(--font-size-lg, 20px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #303133);
}

.page-subtitle {
  margin: 2px 0 0 0;
  color: #909399;
  font-size: 13px;
}

.panel-header-right {
  display: flex;
  align-items: center;
  padding-top: 2px;
}

/* REQ-UI-005-B: 顶部导航栏改为两行布局，每行 flex-wrap: wrap */
.panel-nav-bar {
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-4);
}

/* REQ-UI-005-B: 每行导航（温控行 / 系统设备行）*/
.nav-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0;
  padding: 4px 0;
}

/* REQ-UI-005-B: 行间分隔线（明确区分两类设备）*/
.nav-row-separator {
  height: 1px;
  background: var(--color-border);
  margin: 2px 0;
}

/* REQ-UI-005-B: 分类标题标签（加粗，区分普通 nav-label）*/
.nav-category-label {
  font-weight: 700;
  color: var(--color-primary-dark, #1d4ed8);
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
  color: var(--color-text-primary);
  /* REQ-FUNC-001: 导航栏子系统名称不截断（AC-001-3） */
  white-space: nowrap;
  overflow: visible;
}

.nav-history-btn {
  font-size: 12px;
  padding: 0 2px;
}

.nav-divider {
  width: 1px;
  height: 16px;
  background: var(--color-border);
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
  font-size: var(--font-size-xs);
  color: var(--color-primary);
}

/* AC-UI-003-01/02/03: CSS Grid 自适应多列（§8.3，§10.1）
   取消横向滚动，auto-fill minmax(280px,1fr) 自适应列数 */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
  padding: var(--space-4);
  width: 100%;
}

/* AC-UI-003-03: 宽屏最多5列（§8.3）*/
@media (min-width: 1800px) {
  .cards-grid {
    grid-template-columns: repeat(5, 1fr);
  }
}

/* AC-UI-003-01: Grid 单元格，宽度由栅格决定（§10.1）*/
.subtype-col {
  width: 100%;
  background: var(--color-bg-card);
  border-radius: var(--radius-base);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: box-shadow 250ms ease-out;
}

.subtype-col:hover {
  box-shadow: var(--shadow-base);
}

/* 列标题区（对齐 Design Token §2，§10.1）*/
.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4) var(--space-2);
  border-bottom: 2px solid var(--color-primary);
  background: var(--color-primary-bg);
}

.col-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary-dark);
  white-space: nowrap;
}

/* AC-UI-003-01: .col-collapse-btn 和 .collapse-arrow 已移除（折叠功能取消，§10.1）*/

.params-list {
  padding: 4px 0;
}

/* REQ-FUNC-004: 斑马纹行区分（MODULE-UI-004，AC-004-3） */
.param-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 14px;
  font-size: var(--font-size-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.param-row:last-child {
  border-bottom: none;
}

/* REQ-FUNC-004: 斑马纹（MODULE-UI-004，AC-004-3） */
.param-row:nth-child(even) {
  background-color: var(--color-bg-row-alt);
}

.param-row:nth-child(odd) {
  background-color: #ffffff;
}

/* REQ-FUNC-001: 移除 overflow: hidden / text-overflow: ellipsis / max-width: 60%，
   改为 white-space: nowrap + overflow: visible，标签完整显示撑开列宽（AC-001-1，ADR-002） */
.param-label {
  color: var(--color-text-secondary);
  flex: 1;
  white-space: nowrap;
  overflow: visible;
}

/* REQ-FUNC-001: margin-left 从 8px 增大至 12px（MODULE-UI-001，AC-001-1） */
.param-value {
  color: var(--color-text-primary);
  font-weight: 500;
  flex-shrink: 0;
  margin-left: 12px;
  white-space: nowrap;
}

/* REQ-FUNC-005: 故障状态——红色加粗（AC-005-1/3，ADR-001，OQ-003 定稿：静态颜色，无闪烁） */
.status-fault {
  color: var(--color-status-fault);
  font-weight: 600;
}

/* REQ-FUNC-005: 正常状态——淡绿色（AC-005-2/4，ADR-001） */
.status-ok {
  color: var(--color-status-ok);
  font-weight: 500;
}

/* REQ-FUNC-002/004: 底部时间戳——左对齐，与卡片区 padding 对齐（AC-002-1/2，MODULE-UI-002） */
.panel-footer {
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-card);
  border-top: 1px solid var(--color-border);
  text-align: left;
}
</style>
