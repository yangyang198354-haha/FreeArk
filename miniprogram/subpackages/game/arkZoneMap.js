/**
 * @module MOD-GAME-ARKZONEMAP
 * @description 方舟座舱·设备→分区映射 + 实时状态推导（纯函数，可单测）。
 *   把屏端 DeviceStatusUpdate 的 {productCode, attrs} 归并到 3 个子系统分区，
 *   并按后端 fault_consumer 同一套故障语汇推导每区状态（normal/warning/fault）。
 *
 *   故障判定忠实移植自后端 api/fault_consumer/fault_classifier.py（ADR-FM-03）：
 *     - error_<N>             : 值非 "0"/0 → 故障(fault)
 *     - comm_fault_timeout    : 值 != "normal" → 故障(fault)
 *     - fresh_air_fault_bit_* : 值非 0 → 告警(warning)
 *     - *_communication_error / *_sensor_error / 具名故障字段 : 非 0 → 故障(fault)
 *     - condensation_alarm    : 非 0 → 告警(warning，结露预警)
 *   屏端 DeviceStatusUpdate 实测含 error_N、comm_fault_timeout、condensation_alarm 等只读 attr
 *   （见 capture_findings_oq03.md），故可直接用实时流驱动。
 *
 *   productCode→分区取自 api/screen_param_config.py PRODUCT_CODE_ROLE（单一权威），
 *   归并为业务三恒：新风(恒氧)/温控(恒温)/除湿·能源(恒湿)。映射可按需调整。
 */

// ── productCode → 分区 id ────────────────────────────────────────────────────
// 来源：PRODUCT_CODE_ROLE（screen_param_config.py）
//   130004 新风机 / 100007 空气品质      → 新风（恒氧）
//   260001 主温控 / 120003 温控面板 / 10016 主机面板 → 温控（恒温）
//   270001 水力/能源主机 / 250001 能量计 → 除湿·能源（恒湿，水力模块负责除湿能源供应）
export const PRODUCT_CODE_ZONE = {
  130004: 'fresh_air',
  100007: 'fresh_air',
  260001: 'temp_control',
  120003: 'temp_control',
  10016: 'temp_control',
  270001: 'dehumid',
  250001: 'dehumid',
}

/** productCode → zoneId，未知返回 null（该设备不参与分区着色）。 */
export function classifyDeviceZone(productCode) {
  if (productCode === null || productCode === undefined) return null
  return PRODUCT_CODE_ZONE[Number(productCode)] || null
}

// ── 故障判定（移植 fault_classifier）─────────────────────────────────────────

const _ERROR_N = /^error_\d+$/
const _FRESH_AIR_BIT = /^fresh_air_fault_bit_\d+$/
const _NAMED_FAULT_SUFFIX = [
  '_communication_error',
  '_temp_sensor_error',
  '_humidity_sensor_error',
  '_external_temp_sensor_error',
]
const _NAMED_FAULT_EXACT = new Set([
  'fresh_air_unit_stop_error',
  'fresh_air_unit_communication_error',
  'hydraulic_module_low_temp_error',
  'energy_meter_status_communication_error',
  'air_quality_sensor_communication_error',
])

function isNamedFaultTag(tag) {
  if (_NAMED_FAULT_EXACT.has(tag)) return true
  return _NAMED_FAULT_SUFFIX.some((s) => tag.endsWith(s))
}

function nonZero(value) {
  const n = Number(value)
  if (!Number.isNaN(n)) return n !== 0
  return value !== '' && String(value) !== '0' && !!value
}

/** 移植 fault_classifier.is_fault_active：某 attr 当前值是否处于故障态。 */
export function isFaultActive(tag, value) {
  if (value === null || value === undefined) return false
  if (tag === 'comm_fault_timeout') return String(value) !== 'normal'
  if (_ERROR_N.test(tag)) return nonZero(value)
  if (_FRESH_AIR_BIT.test(tag)) {
    const n = Number(value)
    return Number.isNaN(n) ? false : n !== 0
  }
  if (isNamedFaultTag(tag)) return nonZero(value)
  return false
}

/**
 * 单个 attr → 严重度：'fault' | 'warning' | null（null = 非故障 attr 或未激活）。
 * 严重度对齐后端 severity：fresh_air_fault_bit_* = warning；condensation_alarm = warning；其余故障 = fault。
 */
export function attrSeverity(tag, value) {
  if (tag === 'condensation_alarm') return nonZero(value) ? 'warning' : null
  if (!isFaultActive(tag, value)) return null
  if (_FRESH_AIR_BIT.test(tag)) return 'warning'
  return 'fault'
}

// ── 状态聚合 ─────────────────────────────────────────────────────────────────

export const STATUS_RANK = { idle: -1, normal: 0, warning: 1, fault: 2 }

/** 取两状态中更严重者。 */
export function worseStatus(a, b) {
  return (STATUS_RANK[a] ?? -1) >= (STATUS_RANK[b] ?? -1) ? a : b
}

/** 单设备 attrs（{tag:val}）→ 状态。有数据但无故障 = normal。 */
export function deriveDeviceStatus(attrs) {
  let st = 'normal'
  for (const tag of Object.keys(attrs || {})) {
    const sev = attrSeverity(tag, attrs[tag])
    if (sev) st = worseStatus(st, sev)
  }
  return st
}

/**
 * 设备字典 → 各分区状态。
 * @param {object} deviceStore  sn -> { productCode, attrs }
 * @param {string[]} zoneIds    需要返回的分区 id 列表
 * @returns {object} zoneId -> 状态（无任何归属设备 = 'idle' 无数据）
 */
export function computeZoneStatuses(deviceStore, zoneIds) {
  const out = {}
  for (const id of zoneIds) out[id] = 'idle'
  for (const sn of Object.keys(deviceStore || {})) {
    const d = deviceStore[sn]
    if (!d) continue
    const zid = classifyDeviceZone(d.productCode)
    if (!zid || !(zid in out)) continue
    const ds = deriveDeviceStatus(d.attrs)
    out[zid] = out[zid] === 'idle' ? ds : worseStatus(out[zid], ds)
  }
  return out
}
