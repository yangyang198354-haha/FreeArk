/**
 * @module MOD-FAULT-UTILS
 * @implements IFC-FU-001, IFC-FU-002, IFC-FU-003, IFC-FU-004, IFC-FU-005
 * @depends 无（纯函数，零依赖）
 * @author sub_agent_software_developer
 * @description 故障判定纯函数模块 — 与后端 fault_utils.py 等效实现。
 *   所有函数无副作用、无外部依赖、输入输出确定。
 *
 *   同步来源：
 *     - FAULT_PARAM_NAMES ← fault_utils.py FAULT_PARAM_NAMES frozenset (26 个字段)
 *     - ERROR_N_PATTERN    ← fault_utils.py _ERROR_N_PATTERN = re.compile(r'^error_\d+$')
 *     - FRESH_AIR_FAULT_BITS ← DeviceCardsView.vue FRESH_AIR_FAULT_BITS (9 个 bit)
 *     - SYSTEM_SUB_KEYS      ← DeviceCardsView.vue SYSTEM_SUB_KEYS (4 个 sub_type)
 *
 *   技术栈约束：
 *     - 禁止使用 \p{} Unicode 属性正则（华为安卓引擎不支持）
 *     - 所有正则使用标准 JS RegExp，不带 'u' flag
 *     - 使用 ES6 Set 实现 O(1) 成员判断（微信基础库 2.x+ 均支持）
 */

// ── 导出常量 — 故障字段集合 ────────────────────────────────
// 同步来源：fault_utils.py FAULT_PARAM_NAMES frozenset（共 26 个字段）
// 修改此处时必须同步修改后端 frozenset，反之亦然。

export const FAULT_PARAM_NAMES = new Set([
  // 客厅温控面板（4 个）
  'living_room_temp_sensor_error',
  'living_room_humidity_sensor_error',
  'living_room_external_temp_sensor_error',
  'living_room_communication_error',
  // 书房温控面板（4 个）
  'study_room_temp_sensor_error',
  'study_room_humidity_sensor_error',
  'study_room_external_temp_sensor_error',
  'study_room_communication_error',
  // 主卧温控面板（4 个）
  'bedroom_temp_sensor_error',
  'bedroom_humidity_sensor_error',
  'bedroom_external_temp_sensor_error',
  'bedroom_communication_error',
  // 儿童房温控面板（4 个）
  'children_room_temp_sensor_error',
  'children_room_humidity_sensor_error',
  'children_room_external_temp_sensor_error',
  'children_room_communication_error',
  // 第四儿童房温控面板（4 个）
  'fourth_children_room_temp_sensor_error',
  'fourth_children_room_humidity_sensor_error',
  'fourth_children_room_external_temp_sensor_error',
  'fourth_children_room_communication_error',
  // 新风机（2 个）
  'fresh_air_unit_stop_error',
  'fresh_air_unit_communication_error',
  // 水利模块、能耗表、空气品质传感器（3 个）
  'hydraulic_module_low_temp_error',
  'energy_meter_status_communication_error',
  'air_quality_sensor_communication_error',
  // PLC 通信故障（1 个）
  'comm_fault_timeout',
])

// ── 导出常量 — error_N 正则 ────────────────────────────────
// 同步来源：fault_utils.py _ERROR_N_PATTERN = re.compile(r'^error_\d+$')
// 注意：不带 'u' flag（华为安卓兼容）

export const ERROR_N_PATTERN = /^error_\d+$/

// ── 导出常量 — 新风机故障 bit 位定义 ────────────────────────
// 同步来源：FreeArkWeb/frontend/src/views/DeviceCardsView.vue FRESH_AIR_FAULT_BITS
// 名称顺序必须与 Web 端完全一致（bit 0 → bit 8）

export const FRESH_AIR_FAULT_BITS = [
  '风机状态故障',
  '出风温度异常状态',
  '进风温度传感器故障',
  '回水温度传感器故障',
  '进水温度传感器故障',
  '加湿器故障',
  '新风水阀故障',
  '防冻保护故障',
  '出风温度传感器故障',
]

// ── 导出常量 — 系统设备子类型白名单 ─────────────────────────
// 同步来源：FreeArkWeb/frontend/src/views/DeviceCardsView.vue SYSTEM_SUB_KEYS
// 与 Web 端 getOwnerRealtimeParams 返回的 group→sub_type 嵌套结构对齐

export const SYSTEM_SUB_KEYS = [
  'fresh_air',
  'energy_meter',
  'hydraulic_module',
  'air_quality',
]

// ── 子系统 sub_type → ID 映射 ──────────────────────────────

export const SUB_TYPE_TO_ID = {
  'fresh_air': 'fresh-air',
  'energy_meter': 'energy',
  'hydraulic_module': 'hydraulic',
  'air_quality': 'air-quality',
  'main_thermostat': 'main-thermostat',
}

// ── 子系统 ID → 中文名映射 ─────────────────────────────────

export const SUBSYSTEM_NAMES = {
  'fresh-air': '新风模块',
  'energy': '能耗中枢',
  'hydraulic': '水力模块',
  'air-quality': '空气品质',
  'main-thermostat': '主温控',
}

// ── 子系统 ID → sub_type 反向映射 ─────────────────────────

export const ID_TO_SUB_TYPE = {
  'fresh-air': 'fresh_air',
  'energy': 'energy_meter',
  'hydraulic': 'hydraulic_module',
  'air-quality': 'air_quality',
  'main-thermostat': 'main_thermostat',
}

// ═══════════════════════════════════════════════════════════════
// 公共接口 — 故障字段识别
// ═══════════════════════════════════════════════════════════════

/**
 * IFC-FU-001: 判断参数名是否属于故障字段集合。
 *
 * 规则：
 *   1. paramName in FAULT_PARAM_NAMES（26 个具名字段 + comm_fault_timeout）
 *   2. 匹配正则 /^error_\d+$/（PLC 故障码位字段，如 error_82、error_703）
 *
 * 注意：fresh_air_fault_status 不在此函数覆盖范围内，
 *       它由 countFaultsForRow() 单独处理（位域 popcount）。
 *
 * 等价于后端：fault_utils.is_fault_param(param_name)
 *
 * @param {string} paramName - PLC 参数名
 * @returns {boolean} 是否为故障字段
 */
export function isFaultParam(paramName) {
  if (typeof paramName !== 'string') return false
  return FAULT_PARAM_NAMES.has(paramName) || ERROR_N_PATTERN.test(paramName)
}

// ═══════════════════════════════════════════════════════════════
// 公共接口 — 单行故障贡献计算
// ═══════════════════════════════════════════════════════════════

/**
 * IFC-FU-002: 计算单行参数的故障贡献值。
 *
 * 规则（与后端 fault_utils.count_faults_for_row 完全一致）：
 *   - value 为 null/undefined/0 → 返回 0
 *   - paramName === 'fresh_air_fault_status' → popcount（每个置 1 的 bit 计 1）
 *   - isFaultParam(paramName) && value !== 0 → 返回 1
 *   - 其他 → 返回 0
 *
 * 等价于后端：fault_utils.count_faults_for_row(param_name, value)
 *
 * @param {string} paramName - PLC 参数名
 * @param {number|null|undefined} value - PLC 参数值
 * @returns {number} 故障贡献值（0 或正整数）
 */
export function countFaultsForRow(paramName, value) {
  if (value == null || value === 0) return 0

  if (paramName === 'fresh_air_fault_status') {
    // ADR-FC-006: 按位计数，每个置 1 的 bit 算一个独立故障
    // 与后端 count_faults_for_row 的 popcount 口径一致
    // popcount 等效实现：bin(value).count('1') → JS: toString(2).split('1').length - 1
    const v = typeof value === 'number' ? value : Number(value)
    if (isNaN(v) || v <= 0) return 0
    return v.toString(2).split('1').length - 1
  }

  return isFaultParam(paramName) ? 1 : 0
}

// ═══════════════════════════════════════════════════════════════
// 公共接口 — 批量故障数计算
// ═══════════════════════════════════════════════════════════════

/**
 * IFC-FU-003: 批量计算一组参数的故障总数。
 *
 * 对每个参数调用 countFaultsForRow，累加结果。
 *
 * 等价于后端：fault_utils.compute_fault_count_v2(records)
 *
 * @param {Array<{paramName: string, value: number}>} params - 参数数组
 * @returns {number} 故障总数（非负整数）
 */
export function computeFaultCount(params) {
  if (!params || !Array.isArray(params)) return 0
  let total = 0
  for (const p of params) {
    if (p && typeof p.paramName === 'string') {
      total += countFaultsForRow(p.paramName, p.value)
    }
  }
  return total
}

// ═══════════════════════════════════════════════════════════════
// 公共接口 — 新风机故障位域展开
// ═══════════════════════════════════════════════════════════════

/**
 * IFC-FU-004: 将 fresh_air_fault_status 位域值展开为 9 个具名故障 bit 项。
 *
 * 位域规则：
 *   bit 0: 风机状态故障
 *   bit 1: 出风温度异常状态
 *   bit 2: 进风温度传感器故障
 *   bit 3: 回水温度传感器故障
 *   bit 4: 进水温度传感器故障
 *   bit 5: 加湿器故障
 *   bit 6: 新风水阀故障
 *   bit 7: 防冻保护故障
 *   bit 8: 出风温度传感器故障
 *
 * 判定规则：((value >> bitIndex) & 1) === 1 → active=true
 *
 * 等价于 Web 端：DeviceCardsView.vue FRESH_AIR_FAULT_BITS.forEach((name, i) => ...)
 *
 * @param {number|null|undefined} value - fresh_air_fault_status 的整数值
 * @returns {Array<{bitIndex: number, name: string, active: boolean}>} 9 元素数组
 */
export function expandFreshAirFaultBits(value) {
  const v = (value != null && !isNaN(Number(value))) ? Number(value) : 0
  return FRESH_AIR_FAULT_BITS.map((name, bitIndex) => ({
    bitIndex,
    name,
    active: ((v >> bitIndex) & 1) === 1,
  }))
}

// ═══════════════════════════════════════════════════════════════
// 公共接口 — 故障展示判定
// ═══════════════════════════════════════════════════════════════

/**
 * IFC-FU-005: 判断参数值是否应在 UI 中以故障样式（红/橙）展示。
 *
 * 规则：
 *   - isFaultParam(paramName) && value != null && value !== 0 → true
 *   - paramName === 'fresh_air_fault_status' && value != null && value !== 0 → true
 *   - ERROR_N_PATTERN.test(paramName) && value != null && value !== 0 → true
 *
 * 等价于 Web 端：DeviceCardsView.vue getValueClass(param_name, value) 红色告警逻辑
 *
 * @param {string} paramName - PLC 参数名
 * @param {number|null|undefined} value - PLC 参数值
 * @returns {boolean} 是否应以故障高亮样式展示
 */
export function isFaultValueForDisplay(paramName, value) {
  if (value == null || value === 0) return false
  if (paramName === 'fresh_air_fault_status') return value !== 0
  if (isFaultParam(paramName)) return true
  return false
}

// ═══════════════════════════════════════════════════════════════
// 参数分类集合 — 同步来源：Web DeviceCardsView.vue
// ═══════════════════════════════════════════════════════════════
// 修改此处时必须同步修改 Web 端对应的常量集合。

// 温度字段 — int16 ÷ 10 → °C
export const TEMP_PARAMS = new Set([
  'living_room_temperature', 'living_room_ntc_temp', 'living_room_dew_point_setting', 'living_room_temp_setting',
  'study_room_temperature', 'study_room_ntc_temperature', 'study_room_dew_point_setting', 'study_room_temp_setting',
  'bedroom_temperature', 'bedroom_ntc_temperature', 'bedroom_dew_point_setting', 'bedroom_temp_setting',
  'children_room_temperature', 'children_room_ntc_temperature', 'children_room_dew_point_setting', 'children_room_temp_setting',
  'fourth_children_room_temperature', 'fourth_children_room_ntc_temperature', 'fourth_children_room_dew_point_setting', 'fourth_children_room_temp_setting',
  'hydraulic_module_inlet_temp', 'hydraulic_module_outlet_temp',
  'fresh_air_inlet_temp', 'coil_inlet_temp', 'coil_outlet_temp', 'coil_supply_air_temp',
  'supply_air_temp_setting',
])

// 湿度字段 — int16 ÷ 10 → %
export const HUMIDITY_PARAMS = new Set([
  'living_room_humidity', 'study_room_humidity', 'bedroom_humidity',
  'children_room_humidity', 'fourth_children_room_humidity',
])

// 开关字段 — 0→关闭, 1→开启
export const SWITCH_PARAMS = new Set([
  'living_room_switch', 'study_room_switch', 'bedroom_switch',
  'children_room_switch', 'fourth_children_room_switch',
  'system_switch', 'humidification_switch',
])

// ═══════════════════════════════════════════════════════════════
// 公共接口 — 参数值格式化（1:1 复制 Web DeviceCardsView.formatValue）
// ═══════════════════════════════════════════════════════════════

/**
 * IFC-FU-006: Format a PLC parameter value for display.
 *
 * 1:1 reproduction of Web DeviceCardsView.vue formatValue(paramName, rawValue).
 * Applies unit suffixes (°C, %, ppm, h, kw·h, μg/m³), enum mappings
 * (开关/运行模式/风机档位), and ÷10 scaling for fixed-point int16 values.
 *
 * @param {string} paramName - PLC parameter name
 * @param {number|null|undefined} rawValue - raw PLC value
 * @returns {string} formatted display string
 */
export function formatAttrValue(paramName, rawValue) {
  if (rawValue === null || rawValue === undefined) return '—'
  const v = Number(rawValue)

  // 温度 ÷10 → °C
  if (TEMP_PARAMS.has(paramName)) {
    return (v / 10).toFixed(1) + '°C'
  }

  // 湿度 ÷10 → %
  if (HUMIDITY_PARAMS.has(paramName)) {
    return (v / 10).toFixed(1) + '%'
  }

  // 开关
  if (SWITCH_PARAMS.has(paramName)) {
    return v === 0 ? '关闭' : '开启'
  }

  // 新风机故障位（展开后的虚拟字段名 fresh_air_fault_bit_N）
  if (paramName.startsWith('fresh_air_fault_bit_')) {
    return v === 0 ? '正常' : '故障'
  }

  // 通用故障字段
  if (isFaultParam(paramName)) {
    return v === 0 ? '正常' : '故障'
  }

  // 阀门开度
  if (paramName === 'hydraulic_module_valve_opening' || paramName === 'fresh_air_valve_opening') {
    return (v / 10).toFixed(1)
  }

  // 滤网小时
  if (paramName === 'filter_alarm_hours_setting' || paramName === 'filter_used_hours') {
    return v + 'h'
  }

  // 工时
  if (paramName === 'work_time') {
    return v + 'h'
  }

  // 冷热量
  if (paramName === 'total_hot_quantity' || paramName === 'total_cold_quantity') {
    return v + 'kw·h'
  }

  // CO2
  if (paramName === 'co2') {
    return v + 'ppm'
  }

  // PM2.5
  if (paramName === 'pm25') {
    return v + 'μg/m³'
  }

  // 加湿限值
  if (paramName === 'humidification_humidity_upper_limit' || paramName === 'humidification_humidity_lower_limit') {
    return v + '%'
  }

  // 风机档位
  if (paramName === 'fan_gear_feedback' || paramName === 'system_air_volume_setting') {
    const gears = { 0: '低速', 1: '中速', 2: '高速' }
    return gears[v] !== undefined ? gears[v] : String(v)
  }

  // 运行模式
  if (paramName === 'operation_mode') {
    const modes = { 0: '制冷', 1: '制冷', 2: '制热', 3: '通风', 4: '除湿' }
    return modes[v] !== undefined ? modes[v] : String(v)
  }

  // 集中能源供给
  if (paramName === 'central_energy_supply') {
    const supplyModes = { 1: '制冷', 2: '制热', 3: '无' }
    return supplyModes[v] !== undefined ? supplyModes[v] : '无'
  }

  // 离家节能
  if (paramName === 'away_energy_saving') {
    return v === 0 ? '关闭' : '开启'
  }

  // 凝露提醒
  if (paramName === 'living_room_condensation_alert' || paramName.endsWith('_condensation_alert')) {
    return v === 0 ? '无' : '告警'
  }

  return String(rawValue)
}
