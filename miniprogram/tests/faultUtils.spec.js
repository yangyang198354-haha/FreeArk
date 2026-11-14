/**
 * faultUtils 舰桥抽屉故障条目单测。
 * 覆盖：device_sn 类型统一、fresh_air 位域故障条目、MQTT/PLC 合并去重、
 *       子系统/主温控隔舱过滤。
 */
import { describe, it, expect } from 'vitest'
import {
  expandFreshAirFaultBits,
  sameDeviceSn,
  buildFreshAirRealtimeFaultEvents,
  mergeFaultEvents,
  filterFaultEventsByCompartment,
} from '@/utils/faultUtils'

function makeFreshAirBlock(value, collectedAt = '2026-11-14 12:43:59') {
  return {
    deviceSn: 'fresh_air',
    deviceName: '新风模块',
    subType: 'fresh_air',
    attrs: [
      {
        tag: 'fresh_air_fault_status',
        displayName: '新风机故障状态',
        value,
        isFault: value !== 0,
        collectedAt,
        expandedBits: expandFreshAirFaultBits(value),
      },
    ],
  }
}

describe('sameDeviceSn', () => {
  it('number 与 string 视为同一 SN', () => {
    expect(sameDeviceSn(22155, '22155')).toBe(true)
    expect(sameDeviceSn('22155', 22155)).toBe(true)
  })

  it('空值/null 不匹配', () => {
    expect(sameDeviceSn(null, '22155')).toBe(false)
    expect(sameDeviceSn('', '')).toBe(false)
    expect(sameDeviceSn(undefined, 22155)).toBe(false)
  })
})

describe('buildFreshAirRealtimeFaultEvents', () => {
  it('位域 64（bit6）→ 新风水阀故障', () => {
    const events = buildFreshAirRealtimeFaultEvents(makeFreshAirBlock(64))
    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      deviceName: '新风模块',
      severity: 'fault',
      faultType: '新风故障',
      faultCode: 'fresh_air_fault_bit_6',
      faultMessage: '新风水阀故障',
      firstSeenAt: '2026-11-14T12:43:59',
      source: 'plc-realtime',
    })
  })

  it('位域 3（bit0+bit1）→ 2 条', () => {
    const events = buildFreshAirRealtimeFaultEvents(makeFreshAirBlock(3))
    expect(events.map((e) => e.faultMessage)).toEqual([
      '风机状态故障',
      '出风温度异常状态',
    ])
  })

  it('位域 0 → 无条目', () => {
    expect(buildFreshAirRealtimeFaultEvents(makeFreshAirBlock(0))).toEqual([])
  })

  it('非 fresh_air 参数块 → 无条目', () => {
    const block = makeFreshAirBlock(64)
    block.subType = 'energy_meter'
    expect(buildFreshAirRealtimeFaultEvents(block)).toEqual([])
    expect(buildFreshAirRealtimeFaultEvents(null)).toEqual([])
  })
})

describe('mergeFaultEvents', () => {
  it('同 faultCode 时以 MQTT 事件为准，不重复', () => {
    const mqtt = [{ id: 1, faultCode: 'fresh_air_fault_bit_6' }]
    const plc = [
      { id: 'plc-fresh-air-bit-6', faultCode: 'fresh_air_fault_bit_6' },
      { id: 'plc-fresh-air-bit-0', faultCode: 'fresh_air_fault_bit_0' },
    ]
    const merged = mergeFaultEvents(mqtt, plc)
    expect(merged).toHaveLength(2)
    expect(merged[0].id).toBe(1)
    expect(merged.some((e) => e.id === 'plc-fresh-air-bit-6')).toBe(false)
    expect(merged.some((e) => e.id === 'plc-fresh-air-bit-0')).toBe(true)
  })

  it('空输入返回空数组', () => {
    expect(mergeFaultEvents(null, null)).toEqual([])
  })
})

describe('filterFaultEventsByCompartment', () => {
  const structure = {
    system_devices: [{ sub_type: 'fresh_air', device_sn: 22155 }],
  }

  it('子系统：structure number 与 fault_event string 能匹配', () => {
    const events = [
      { id: 1, device_sn: '22155', room_name: '全屋', severity: 'error' },
      { id: 2, device_sn: '22156', room_name: '全屋', severity: 'error' },
    ]
    const result = filterFaultEventsByCompartment(
      events,
      { type: 'subsystem', id: 'fresh-air', name: '新风模块' },
      structure,
    )
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe(1)
  })

  it('子系统：structure 无对应设备时返回空', () => {
    const result = filterFaultEventsByCompartment(
      [{ id: 1, device_sn: '22155' }],
      { type: 'subsystem', id: 'fresh-air' },
      { system_devices: [] },
    )
    expect(result).toEqual([])
  })

  it('主温控伪房间：number/string 混用能匹配', () => {
    const events = [{ id: 1, device_sn: '22158', room_name: '客厅' }]
    const result = filterFaultEventsByCompartment(
      events,
      {
        type: 'room',
        id: 'thermostat-22158',
        name: '主温控',
        _thermostatDeviceSn: 22158,
      },
      structure,
    )
    expect(result).toHaveLength(1)
  })

  it('普通房间按 room_name 匹配', () => {
    const events = [
      { id: 1, device_sn: '22554', room_name: '主卧' },
      { id: 2, device_sn: '22555', room_name: '儿童房' },
    ]
    const result = filterFaultEventsByCompartment(
      events,
      { type: 'room', id: 'room-1', name: '主卧' },
      structure,
    )
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe(1)
  })
})
