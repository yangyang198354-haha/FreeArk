/**
 * screenMqtt 纯逻辑单测（v1.10.0）。不依赖真实 broker，mock 掉 mqtt 库。
 * 覆盖：deviceSn 归一、DeviceStatusUpdate 解析、写 items（mode↔energy 联动）、
 *       DeviceWrite envelope、写确认匹配。
 */
import { describe, it, expect, vi } from 'vitest'

// 避免 node 下加载 mqtt 浏览器构建
vi.mock('mqtt/dist/mqtt.js', () => ({ default: { connect: () => ({}) } }))

import {
  normalizeSn,
  parseDeviceUpdate,
  buildWriteItems,
  buildDeviceWrite,
  valueReflectsTarget,
  genRequestId,
} from '@/utils/screenMqtt'

const CONFIG = {
  mode_energy_link: { cold: 'cold', hot: 'hot', wind: 'no', dehumidification: 'cold' },
  link_product_codes: [270001],
}

describe('normalizeSn', () => {
  it('整数与字符串归一为字符串', () => {
    expect(normalizeSn(22158)).toBe('22158')
    expect(normalizeSn('22158')).toBe('22158')
    expect(normalizeSn(null)).toBe('')
  })
})

describe('parseDeviceUpdate', () => {
  const msg = {
    header: { name: 'DeviceStatusUpdate', screenMac: 'mac1' },
    payload: { code: 200, data: { deviceSn: 22158, productCode: 260001,
      items: [{ attrTag: 'temp_set', attrValue: '26.0' }, { attrTag: 'switch', attrValue: 'on' }] } },
  }
  it('解析出 deviceSn/productCode/attrs', () => {
    const p = parseDeviceUpdate(msg)
    expect(p.deviceSn).toBe('22158')
    expect(p.productCode).toBe(260001)
    expect(p.attrs.temp_set).toBe('26.0')
    expect(p.attrs.switch).toBe('on')
  })
  it('非 DeviceStatusUpdate 返回 null', () => {
    expect(parseDeviceUpdate({ header: { name: 'DeviceWrite' } })).toBeNull()
  })
  it('缺 deviceSn 返回 null', () => {
    expect(parseDeviceUpdate({ header: { name: 'DeviceStatusUpdate' }, payload: { data: { items: [] } } })).toBeNull()
  })
})

describe('buildWriteItems', () => {
  it('系统机改 mode 联动 energy_supply_mode（wind→no）', () => {
    const items = buildWriteItems(270001, 'mode', 'wind', CONFIG)
    expect(items).toEqual([
      { attrTag: 'mode', attrValue: 'wind' },
      { attrTag: 'energy_supply_mode', attrValue: 'no' },
    ])
  })
  it('系统机 cold→cold 联动', () => {
    const items = buildWriteItems(270001, 'mode', 'cold', CONFIG)
    expect(items[1]).toEqual({ attrTag: 'energy_supply_mode', attrValue: 'cold' })
  })
  it('非系统机改 mode 不联动', () => {
    expect(buildWriteItems(260001, 'mode', 'cold', CONFIG)).toEqual([{ attrTag: 'mode', attrValue: 'cold' }])
  })
  it('非 mode 属性不联动', () => {
    expect(buildWriteItems(270001, 'switch', 'on', CONFIG)).toEqual([{ attrTag: 'switch', attrValue: 'on' }])
  })
})

describe('buildDeviceWrite', () => {
  it('envelope 结构正确且带 requestId', () => {
    const env = buildDeviceWrite('mac1', 22154, [{ attrTag: 'mode', attrValue: 'cold' }], 'req-1')
    expect(env.header.name).toBe('DeviceWrite')
    expect(env.header.sn).toBe('22154')
    expect(env.header.screenMac).toBe('mac1')
    expect(env.payload.data.deviceSn).toBe('22154')
    expect(env.payload.data.requestId).toBe('req-1')
    expect(env.payload.data.items[0].attrTag).toBe('mode')
  })
})

describe('valueReflectsTarget', () => {
  const upd = {
    header: { name: 'DeviceStatusUpdate' },
    payload: { data: { deviceSn: 22158, items: [{ attrTag: 'temp_set', attrValue: '26.0' }] } },
  }
  it('值匹配返回 true', () => {
    expect(valueReflectsTarget(upd, '22158', 'temp_set', '26.0')).toBe(true)
  })
  it('值不匹配返回 false', () => {
    expect(valueReflectsTarget(upd, '22158', 'temp_set', '27.0')).toBe(false)
  })
  it('deviceSn 不匹配返回 false', () => {
    expect(valueReflectsTarget(upd, '99999', 'temp_set', '26.0')).toBe(false)
  })
})

describe('genRequestId', () => {
  it('两次不相同', () => {
    expect(genRequestId()).not.toBe(genRequestId())
  })
})
