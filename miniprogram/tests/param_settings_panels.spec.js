/**
 * param_settings_panels.spec.js — v1.12.0 参数设置页「按设备/房间分组面板」纯逻辑单测。
 *
 * 直接 import utils/paramPanels.js（已与 Vue 运行时解耦），覆盖：
 *   US-01 面板列表/排序、US-02 tab1 可写控件(OQ-01)、US-03 tab2 详细、US-06 动态面板、OQ-06 主温控独立面板。
 */

import { describe, it, expect } from 'vitest'
import {
  TAB1_FIELDS,
  resolveRoomName,
  buildControls,
  buildPanels,
  panelHasControls,
  formatValue,
  buildDetailRows,
} from '../utils/paramPanels.js'

// 模拟后端 config.writable_attrs（与 screen_param_config.py 对齐）
const WA = {
  switch: { control: 'toggle', label: '开关', options: [{ value: 'off', label: '关' }, { value: 'on', label: '开' }] },
  system_switch: { control: 'toggle', label: '系统开关', options: [{ value: 'off', label: '关' }, { value: 'on', label: '开' }] },
  temp_set: { control: 'number', label: '温度设定', unit: '℃', step: 0.5, min: 16, max: 30 },
  out_temp_set: { control: 'number', label: '出风温度设定', unit: '℃', step: 0.5, min: 10, max: 30 },
  mode: { control: 'select', label: '运行模式', options: [{ value: 'cold', label: '制冷' }, { value: 'hot', label: '制热' }] },
  energy_supply_mode: { control: 'select', label: '能源供应', options: [{ value: 'cold', label: '制冷' }, { value: 'no', label: '无' }] },
  energy_saving_sign: { control: 'toggle', label: '离家节能', options: [{ value: 'off', label: '未启用' }, { value: 'on', label: '启用' }] },
  wind_speed: { control: 'select', label: '风速', options: [{ value: 'normal', label: '普通' }, { value: 'high_speed', label: '高速' }] },
  humidification_enable: { control: 'toggle', label: '加湿', options: [{ value: 'off', label: '关' }, { value: 'on', label: '开' }] },
}
// 模拟后端 config.readonly_attrs（屏端自描述「只读」展示白名单）
const RA = {
  temp: { label: '当前温度', unit: '℃' },
  humidity: { label: '当前湿度', unit: '%' },
  condensation_alarm: { label: '结露报警', options: [{ value: '0', label: '正常' }, { value: '1', label: '报警' }] },
  co2: { label: 'CO₂', unit: 'ppm' },
}
const CONFIG = { writable_attrs: WA, readonly_attrs: RA, product_code_role: { 250001: '能量计', 100007: '空气质量' } }

// ── resolveRoomName ──────────────────────────────────────────────────────────
describe('resolveRoomName', () => {
  it('room_name 优先', () => expect(resolveRoomName({ room_name: '主卧', ori_room_name: 'bedroom' })).toBe('主卧'))
  it('room_name 空 → ori_room_name', () => expect(resolveRoomName({ room_name: '', ori_room_name: 'study' })).toBe('study'))
  it('均空 → 未知房间', () => expect(resolveRoomName({})).toBe('未知房间'))
})

// ── buildControls：OQ-01 各面板 tab1 字段 ────────────────────────────────────
describe('buildControls — OQ-01 可写白名单', () => {
  it('主机(270001) → system_switch/mode/energy_saving_sign（#1：不含 energy_supply_mode，写 mode 时自动联动）', () => {
    const ctrls = buildControls({ product_code: '270001', params: [] }, WA)
    expect(ctrls.map((c) => c.tag)).toEqual(['system_switch', 'mode', 'energy_saving_sign'])
    expect(ctrls.some((c) => c.tag === 'energy_supply_mode')).toBe(false)
  })

  it('运行模式 mode 控件类型被改写为 dots（#6 圆点控件）', () => {
    const mode = buildControls({ product_code: '270001', params: [] }, WA).find((c) => c.tag === 'mode')
    expect(mode.control).toBe('dots')
    expect(mode.optionLabels).toEqual(['制冷', '制热'])
  })

  it('主温控(260001) → switch/temp_set，不含 system_switch（OQ-01：只在主机）', () => {
    const ctrls = buildControls({ product_code: '260001', params: [] }, WA)
    expect(ctrls.map((c) => c.tag)).toEqual(['switch', 'temp_set'])
    expect(ctrls.some((c) => c.tag === 'system_switch')).toBe(false)
  })

  it('新风传感器(130004) → 无可设置项（#2：去掉出风温度设定，即便骨架含 out_temp_set 也不渲染）', () => {
    expect(buildControls({ product_code: '130004', params: [{ param_name: 'out_temp_set' }] }, WA)).toEqual([])
  })

  it('面板控制器(10016) → wind_speed/humidification_enable（#2 新风风速/加湿）', () => {
    expect(buildControls({ product_code: '10016', params: [] }, WA).map((c) => c.tag)).toEqual(['wind_speed', 'humidification_enable'])
  })

  it('房间末端(120003) → switch/temp_set', () => {
    expect(buildControls({ product_code: '120003', params: [] }, WA).map((c) => c.tag)).toEqual(['switch', 'temp_set'])
  })

  it('product_code 为数字时也按字符串匹配白名单', () => {
    expect(buildControls({ product_code: 10016, params: [] }, WA).map((c) => c.tag)).toEqual(['wind_speed', 'humidification_enable'])
  })

  it('控件定义形状正确（number 带 unit/step/min/max，select 带 optionLabels）', () => {
    const ctrls = buildControls({ product_code: '120003', params: [] }, WA)
    const tempSet = ctrls.find((c) => c.tag === 'temp_set')
    expect(tempSet).toMatchObject({ control: 'number', unit: '℃', step: 0.5, min: 16, max: 30 })
    const mode = buildControls({ product_code: '270001', params: [] }, WA).find((c) => c.tag === 'mode')
    expect(mode.optionLabels).toEqual(['制冷', '制热'])
  })

  it('未知 product_code → 退回设备骨架里的可写参数', () => {
    const dev = { product_code: '999999', params: [{ param_name: 'temp_set' }, { param_name: 'humidity' }] }
    expect(buildControls(dev, WA).map((c) => c.tag)).toEqual(['temp_set']) // humidity 非可写被滤除
  })

  it('TAB1_FIELDS 常量锁定（防回归）', () => {
    expect(TAB1_FIELDS['270001']).toContain('system_switch')
    expect(TAB1_FIELDS['270001']).not.toContain('energy_supply_mode') // #1：能源供应不单列
    expect(TAB1_FIELDS['260001']).not.toContain('system_switch')
  })
})

// ── buildPanels：排序 / claim / 动态 ─────────────────────────────────────────
describe('buildPanels', () => {
  it('sync_status=pending → 空列表', () => {
    expect(buildPanels({ sync_status: 'pending', rooms: [], system_devices: [] }, CONFIG)).toEqual([])
  })
  it('structure 为 null → 空列表', () => {
    expect(buildPanels(null, CONFIG)).toEqual([])
  })

  it('全量：主机/新风/客厅 + 房间 顺序正确，动态渲染', () => {
    const structure = {
      rooms: [
        { room_id: 1, room_name: '主卧', devices: [{ device_sn: 1001, product_code: '120003', params: [] }] },
        { room_id: 2, room_name: '次卧', devices: [{ device_sn: 1002, product_code: '120003', params: [] }] },
      ],
      system_devices: [
        { device_sn: 9001, product_code: '270001', device_name: '主机', params: [] },
        { device_sn: 9002, product_code: '130004', device_name: '新风', params: [{ param_name: 'fan_speed', display_name: '风量' }] },
        { device_sn: 9005, product_code: '10016', device_name: '面板', params: [] },
        { device_sn: 9003, product_code: '260001', device_name: '主温控', params: [] },
      ],
    }
    const panels = buildPanels(structure, CONFIG)
    expect(panels.map((p) => p.title)).toEqual(['主机', '新风', '客厅', '主卧', '次卧'])
  })

  it('#2 新风面板合并 130004(传感)+10016(面板控制器)，风速/加湿控件来自 10016', () => {
    const structure = {
      rooms: [],
      system_devices: [
        { device_sn: 9002, product_code: '130004', device_name: '新风', params: [{ param_name: 'fan_speed', display_name: '风量' }] },
        { device_sn: 9005, product_code: '10016', device_name: '面板', params: [] },
      ],
    }
    const panels = buildPanels(structure, CONFIG)
    expect(panels.map((p) => p.title)).toEqual(['新风'])
    const fresh = panels[0]
    expect(fresh.devices.map((d) => d.deviceSn).sort()).toEqual(['9002', '9005'])
    // 控件全部来自 10016；130004 无控件
    const ctrl10016 = fresh.devices.find((d) => d.deviceSn === '9005')
    const ctrl130004 = fresh.devices.find((d) => d.deviceSn === '9002')
    expect(ctrl10016.controls.map((c) => c.tag)).toEqual(['wind_speed', 'humidification_enable'])
    expect(ctrl130004.controls).toEqual([])
    // 合并面板非空（10016 有控件）→ 不被 #4 隐藏
    expect(panelHasControls(fresh)).toBe(true)
  })

  it('OQ-06 + #3：主温控(260001)落在某房间内也抽为独立面板「客厅」，且不在该房间面板重复', () => {
    const structure = {
      rooms: [
        // 主温控(260001) 误归在一个面板房间内，同时该房间有末端(120003)
        { room_id: 5, room_name: '主卧', devices: [
          { device_sn: 2001, product_code: '120003', params: [] },
          { device_sn: 2002, product_code: '260001', params: [] },
        ] },
      ],
      system_devices: [],
    }
    const panels = buildPanels(structure, CONFIG)
    const titles = panels.map((p) => p.title)
    expect(titles).toEqual(['客厅', '主卧'])
    // 客厅(主温控)面板只含 2002；主卧面板只含 2001（无重复）
    const main = panels.find((p) => p.title === '客厅')
    const bedroom = panels.find((p) => p.title === '主卧')
    expect(main.devices.map((d) => d.deviceSn)).toEqual(['2002'])
    expect(bedroom.devices.map((d) => d.deviceSn)).toEqual(['2001'])
  })

  it('US-06 动态：缺新风则不渲染新风面板', () => {
    const structure = {
      rooms: [{ room_id: 1, room_name: '主卧', devices: [{ device_sn: 1001, product_code: '120003', params: [] }] }],
      system_devices: [{ device_sn: 9001, product_code: '270001', params: [] }],
    }
    expect(buildPanels(structure, CONFIG).map((p) => p.title)).toEqual(['主机', '主卧'])
  })

  it('其余系统设备（能量计/空气质量，有只读参数）兜底为额外面板，不丢信息', () => {
    const structure = {
      rooms: [],
      system_devices: [
        { device_sn: 7001, product_code: '250001', params: [{ param_name: 'energy', display_name: '用电量' }] },
        { device_sn: 7002, product_code: '100007', params: [{ param_name: 'co2', display_name: 'CO₂' }] },
      ],
    }
    expect(buildPanels(structure, CONFIG).map((p) => p.title)).toEqual(['能量计', '空气质量'])
  })

  it('#4 隐藏真正为空的面板（无控件且无参数定义的设备）', () => {
    const structure = {
      rooms: [{ room_id: 1, room_name: '主卧', devices: [{ device_sn: 1001, product_code: '120003', params: [] }] }],
      system_devices: [
        { device_sn: 8888, product_code: '999999', params: [] }, // 未知类型、无参数、无可写 → 空面板
      ],
    }
    const titles = buildPanels(structure, CONFIG).map((p) => p.title)
    expect(titles).toEqual(['主卧'])           // 主卧有 switch/temp_set 控件，保留
    expect(titles).not.toContain('系统设备')   // 空面板被隐藏
  })

  it('房间名 fallback 用于面板标题', () => {
    const structure = {
      rooms: [{ room_id: 3, room_name: '', ori_room_name: 'study', devices: [{ device_sn: 1, product_code: '120003', params: [] }] }],
      system_devices: [],
    }
    expect(buildPanels(structure, CONFIG)[0].title).toBe('study')
  })

  it('toPanelDevice 暴露 deviceSn(字符串)/productCode/controls/allParams', () => {
    const structure = {
      rooms: [{ room_id: 1, room_name: '主卧', devices: [
        { device_sn: 1001, product_code: '120003', params: [{ param_name: 'switch', display_name: '开关' }, { param_name: 'room_temp', display_name: '室温' }] },
      ] }],
      system_devices: [],
    }
    const dev = buildPanels(structure, CONFIG)[0].devices[0]
    expect(dev.deviceSn).toBe('1001')
    expect(dev.controls.map((c) => c.tag)).toEqual(['switch', 'temp_set'])
    expect(dev.allParams.map((p) => p.param_name)).toEqual(['switch', 'room_temp']) // tab2 含只读 room_temp
  })
})

// ── panelHasControls ─────────────────────────────────────────────────────────
describe('panelHasControls', () => {
  it('有控件 → true', () => {
    const panel = { devices: [{ controls: [{ tag: 'switch' }] }] }
    expect(panelHasControls(panel)).toBe(true)
  })
  it('无控件（纯只读设备）→ false', () => {
    const panel = { devices: [{ controls: [] }] }
    expect(panelHasControls(panel)).toBe(false)
  })
})

// ── formatValue ──────────────────────────────────────────────────────────────
describe('formatValue', () => {
  it('options 映射：on→开 / cold→制冷', () => {
    expect(formatValue('switch', 'on', WA)).toBe('开')
    expect(formatValue('mode', 'cold', WA)).toBe('制冷')
  })
  it('unit 拼接：temp_set 26 → 26℃', () => {
    expect(formatValue('temp_set', 26, WA)).toBe('26℃')
  })
  it('只读属性（非白名单）→ 原值字符串', () => {
    expect(formatValue('room_temp', 25.4, WA)).toBe('25.4')
  })
  it('空值 → null（占位交由调用方）', () => {
    expect(formatValue('switch', undefined, WA)).toBeNull()
    expect(formatValue('switch', '', WA)).toBeNull()
  })
})

// ── buildDetailRows：屏端自描述详细 tab（命中白名单才显示）────────────────────
describe('buildDetailRows', () => {
  it('只展示「可写∪只读」白名单内 attrTag，过滤 error_*/comm_fault/plc_*/空 tag', () => {
    const attrs = {
      switch: 'off', temp: '24.5', humidity: '55.0',
      comm_fault_timeout: 'normal', error_673: '0', plc_ip_1: '49320', '': 'x',
    }
    const rows = buildDetailRows(attrs, WA, RA)
    // 可写项(switch)在前、只读项(temp/humidity)在后；诊断/内部项被滤除
    expect(rows.map((r) => r.tag)).toEqual(['switch', 'temp', 'humidity'])
  })

  it('值格式化：options→中文、unit 拼接', () => {
    const rows = buildDetailRows({ switch: 'on', temp: '24.5', condensation_alarm: '0' }, WA, RA)
    const byTag = Object.fromEntries(rows.map((r) => [r.tag, r.value]))
    expect(byTag.switch).toBe('开')          // 可写 options
    expect(byTag.temp).toBe('24.5℃')         // 只读 unit
    expect(byTag.condensation_alarm).toBe('正常') // 只读 options 0→正常
  })

  it('writable 标记正确（可写 true / 只读 false）', () => {
    const rows = buildDetailRows({ switch: 'on', temp: '24.5' }, WA, RA)
    expect(rows.find((r) => r.tag === 'switch').writable).toBe(true)
    expect(rows.find((r) => r.tag === 'temp').writable).toBe(false)
  })

  it('空 attrs / null → []', () => {
    expect(buildDetailRows({}, WA, RA)).toEqual([])
    expect(buildDetailRows(null, WA, RA)).toEqual([])
  })

  it('值为空串的项不渲染', () => {
    expect(buildDetailRows({ temp: '' }, WA, RA).length).toBe(0)
  })
})
