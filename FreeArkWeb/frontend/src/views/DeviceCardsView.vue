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
      <!-- REQ-FUNC-001: cards-scroll-row 支持横向滚动 -->
      <div v-else class="cards-scroll-row">
        <template v-for="(groupData, groupKey) in deviceData" :key="groupKey">
          <div
            v-for="(subTypeData, subKey) in groupData.sub_types"
            :key="subKey"
            class="subtype-col"
          >
            <!-- REQ-FUNC-006: 列标题区新增折叠/展开按钮（AC-006-1） -->
            <div class="col-header">
              <span class="col-title">{{ subTypeData.display }}</span>
              <button
                class="col-collapse-btn"
                :title="collapsedCols[subKey] ? '展开' : '折叠'"
                @click.stop="toggleCollapse(subKey)"
              >
                <!-- AC-006-2/3: 箭头图标随折叠状态旋转 -->
                <span class="collapse-arrow" :class="{ 'is-collapsed': collapsedCols[subKey] }">›</span>
              </button>
            </div>
            <!-- REQ-FUNC-006: v-show 控制参数列表显隐（AC-006-4/6, ADR-004） -->
            <div class="params-list" v-show="!collapsedCols[subKey]">
              <div
                v-for="param in expandParams(subTypeData.params)"
                :key="param.param_name"
                class="param-row"
              >
                <!-- REQ-FUNC-001: 移除 title 截断提示，标签改为完整显示（AC-001-1） -->
                <span class="param-label">{{ param.display_name }}</span>
                <!-- REQ-FUNC-005: 动态 class 绑定故障/正常状态颜色（AC-005-4/6, ADR-001） -->
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
      // REQ-FUNC-006: 卡片列折叠状态（ADR-004）
      // { [subKey]: boolean }，true = 已折叠；缺键/false = 展开（初始全部展开）
      collapsedCols: {},
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
      this.collapsedCols = {}  // REQ-FUNC-006: 切换专有部分时重置折叠状态
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

    // REQ-FUNC-006: 切换指定卡片列的折叠/展开状态（ADR-004，AC-006-4/6）
    toggleCollapse(subKey) {
      this.collapsedCols[subKey] = !this.collapsedCols[subKey]
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
/* REQ-FUNC-004: CSS 设计令牌（MODULE-UI-004），统一色彩变量 */
.device-panel {
  /* 主色系 */
  --color-primary: #409EFF;
  --color-primary-light: #ECF5FF;

  /* 文字色 */
  --color-text-primary: #303133;
  --color-text-secondary: #606266;
  --color-text-info: #909399;

  /* 背景色 */
  --color-bg-page: #f0f2f5;
  --color-bg-card: #ffffff;
  --color-bg-header: #EBF5FF;
  --color-bg-row-alt: #FAFCFF;

  /* 边框色 */
  --color-border-base: #E4E7ED;
  --color-border-light: #F0F2F5;

  /* 状态色（REQ-FUNC-005，AC-005-1/2） */
  --color-status-fault: #F56C6C;
  --color-status-ok: #67C23A;

  width: 100%;
  /* REQ-FUNC-003: 移除 min-height: 100vh，改为 height: auto（AC-003-1，ADR-003） */
  background-color: var(--color-bg-page);
  box-sizing: border-box;
}

/* 顶部导航栏 */
/* REQ-FUNC-004: padding 从 6px 12px 增大至 8px 16px（MODULE-UI-001 间距规范） */
.panel-nav-bar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0;
  background: #fff;
  border-bottom: 1px solid var(--color-border-base);
  padding: 8px 16px;
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
/* REQ-FUNC-001/003: padding/gap 增大（MODULE-UI-001 间距规范） */
.cards-scroll-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 16px;
  padding: 16px;
  overflow-x: auto;
}

/* REQ-FUNC-001: 宽度由内容决定，移除固定 min-width: 180px（ADR-002，AC-001-2） */
/* REQ-FUNC-004: border-radius 增大，box-shadow 加深（MODULE-UI-006 卡片投影） */
.subtype-col {
  width: max-content;
  min-width: 160px;
  flex-shrink: 0;
  background: var(--color-bg-card);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.10);
  overflow: hidden;
}

/* REQ-FUNC-004: 列标题配色（MODULE-UI-005 列标题设计，AC-004-2） */
.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px 8px;
  /* REQ-FUNC-004: 主蓝底线替代原浅灰线，主蓝浅色背景替代原 #fafafa */
  border-bottom: 2px solid var(--color-primary);
  background: var(--color-bg-header);
}

/* REQ-FUNC-004: 标题文字改为深蓝色（AC-004-2，MODULE-UI-005） */
.col-title {
  font-size: 13px;
  font-weight: 600;
  color: #1A6EBF;
  white-space: nowrap;
}

/* REQ-FUNC-006: 折叠/展开切换按钮（MODULE-UI-006，AC-006-1） */
.col-collapse-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  margin-left: 8px;
  color: #1A6EBF;
  display: flex;
  align-items: center;
  border-radius: 4px;
  flex-shrink: 0;
  transition: background 0.15s;
  line-height: 1;
}

.col-collapse-btn:hover {
  background: rgba(26, 110, 191, 0.12);
}

/* REQ-FUNC-006: 折叠箭头图标旋转动画（AC-006-2/3） */
.collapse-arrow {
  display: inline-block;
  font-size: 14px;
  line-height: 1;
  /* 展开状态：›旋转90°指向下 */
  transform: rotate(90deg);
  transition: transform 0.2s ease;
}

.collapse-arrow.is-collapsed {
  /* 折叠状态：›原始方向指向右 */
  transform: rotate(0deg);
}

.params-list {
  padding: 4px 0;
}

/* REQ-FUNC-004: 斑马纹行区分（MODULE-UI-004，AC-004-3） */
.param-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 14px;
  font-size: 13px;
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
  padding: 10px 16px;
  background: #fff;
  border-top: 1px solid var(--color-border-base);
  /* REQ-FUNC-002: text-align 从 right 改为 left（AC-002-1） */
  text-align: left;
}
</style>
