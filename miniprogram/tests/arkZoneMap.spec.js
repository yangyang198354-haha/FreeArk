/**
 * arkZoneMap 纯函数单测（MOD-GAME-ARKZONEMAP）。
 * 覆盖：productCode→分区、故障判定（移植 fault_classifier）、严重度、分区状态聚合。
 */
import { describe, it, expect } from 'vitest'
import {
  classifyDeviceZone,
  isFaultActive,
  attrSeverity,
  deriveDeviceStatus,
  worseStatus,
  computeZoneStatuses,
} from '@/subpackages/game/arkZoneMap'

describe('classifyDeviceZone', () => {
  it('新风机/空气品质 → fresh_air', () => {
    expect(classifyDeviceZone(130004)).toBe('fresh_air')
    expect(classifyDeviceZone(100007)).toBe('fresh_air')
  })
  it('主温控/温控面板/主机 → temp_control', () => {
    expect(classifyDeviceZone(260001)).toBe('temp_control')
    expect(classifyDeviceZone(120003)).toBe('temp_control')
    expect(classifyDeviceZone(10016)).toBe('temp_control')
  })
  it('水力/能量计 → dehumid', () => {
    expect(classifyDeviceZone(270001)).toBe('dehumid')
    expect(classifyDeviceZone(250001)).toBe('dehumid')
  })
  it('字符串 productCode 也能归类', () => {
    expect(classifyDeviceZone('130004')).toBe('fresh_air')
  })
  it('未知/空 → null', () => {
    expect(classifyDeviceZone(999999)).toBeNull()
    expect(classifyDeviceZone(null)).toBeNull()
    expect(classifyDeviceZone(undefined)).toBeNull()
  })
})

describe('isFaultActive（移植 fault_classifier.is_fault_active）', () => {
  it('comm_fault_timeout: 非 "normal" 即故障', () => {
    expect(isFaultActive('comm_fault_timeout', 'normal')).toBe(false)
    expect(isFaultActive('comm_fault_timeout', 'timeout')).toBe(true)
  })
  it('error_N: "0"/0 正常，非零故障', () => {
    expect(isFaultActive('error_673', '0')).toBe(false)
    expect(isFaultActive('error_673', 0)).toBe(false)
    expect(isFaultActive('error_673', '673')).toBe(true)
    expect(isFaultActive('error_82', 1)).toBe(true)
  })
  it('fresh_air_fault_bit_N: 非零故障', () => {
    expect(isFaultActive('fresh_air_fault_bit_3', 0)).toBe(false)
    expect(isFaultActive('fresh_air_fault_bit_3', 1)).toBe(true)
  })
  it('具名故障字段：非零故障', () => {
    expect(isFaultActive('fresh_air_unit_stop_error', 1)).toBe(true)
    expect(isFaultActive('living_room_communication_error', 0)).toBe(false)
    expect(isFaultActive('living_room_communication_error', 1)).toBe(true)
  })
  it('普通只读值（temp/humidity）不算故障', () => {
    expect(isFaultActive('temp', '26.0')).toBe(false)
    expect(isFaultActive('humidity', '55')).toBe(false)
  })
  it('null/undefined → false', () => {
    expect(isFaultActive('error_1', null)).toBe(false)
    expect(isFaultActive('error_1', undefined)).toBe(false)
  })
})

describe('attrSeverity', () => {
  it('error_N 激活 → fault', () => {
    expect(attrSeverity('error_673', '673')).toBe('fault')
  })
  it('fresh_air_fault_bit_N 激活 → warning', () => {
    expect(attrSeverity('fresh_air_fault_bit_2', 1)).toBe('warning')
  })
  it('condensation_alarm 激活 → warning', () => {
    expect(attrSeverity('condensation_alarm', 1)).toBe('warning')
    expect(attrSeverity('condensation_alarm', 0)).toBeNull()
  })
  it('未激活/普通 attr → null', () => {
    expect(attrSeverity('error_1', '0')).toBeNull()
    expect(attrSeverity('temp', '26')).toBeNull()
  })
})

describe('worseStatus / deriveDeviceStatus', () => {
  it('worseStatus 取更严重', () => {
    expect(worseStatus('normal', 'fault')).toBe('fault')
    expect(worseStatus('warning', 'normal')).toBe('warning')
    expect(worseStatus('idle', 'normal')).toBe('normal')
  })
  it('有数据无故障 = normal', () => {
    expect(deriveDeviceStatus({ temp: '26', humidity: '50', error_1: '0' })).toBe('normal')
  })
  it('含激活 error_N = fault', () => {
    expect(deriveDeviceStatus({ temp: '26', error_679: '679' })).toBe('fault')
  })
  it('仅结露告警 = warning', () => {
    expect(deriveDeviceStatus({ temp: '26', condensation_alarm: 1 })).toBe('warning')
  })
  it('故障盖过告警', () => {
    expect(deriveDeviceStatus({ condensation_alarm: 1, error_82: 1 })).toBe('fault')
  })
})

describe('computeZoneStatuses', () => {
  const ZONES = ['fresh_air', 'temp_control', 'dehumid']

  it('无设备 → 全 idle', () => {
    expect(computeZoneStatuses({}, ZONES)).toEqual({
      fresh_air: 'idle', temp_control: 'idle', dehumid: 'idle',
    })
  })

  it('按 productCode 归区并聚合最严重', () => {
    const store = {
      // 新风机正常
      '1': { productCode: 130004, attrs: { temp: '24' } },
      // 客厅主温控故障
      '2': { productCode: 260001, attrs: { error_679: '679' } },
      // 温控面板仅结露告警（同区，被故障盖过的对照在别区）
      '3': { productCode: 120003, attrs: { condensation_alarm: 1 } },
      // 水力模块正常
      '4': { productCode: 270001, attrs: { temp: '40' } },
    }
    const r = computeZoneStatuses(store, ZONES)
    expect(r.fresh_air).toBe('normal')
    expect(r.temp_control).toBe('fault')   // 故障(2) 盖过告警(3)
    expect(r.dehumid).toBe('normal')
  })

  it('未知 productCode 设备被忽略', () => {
    const store = { '9': { productCode: 999999, attrs: { error_1: 1 } } }
    expect(computeZoneStatuses(store, ZONES)).toEqual({
      fresh_air: 'idle', temp_control: 'idle', dehumid: 'idle',
    })
  })
})
