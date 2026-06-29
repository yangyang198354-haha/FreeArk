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
  buildCard,
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
// 模拟后端 config.readonly_attrs（屏端自描述「只读」展示白名单，含各卡片版面引用的 tag）
const RA = {
  temp: { label: '当前温度', unit: '℃' },
  humidity: { label: '当前湿度', unit: '%' },
  dew_point_temp: { label: '露点温度', unit: '℃' },
  NTC_temp: { label: '探头温度(NTC)', unit: '℃' },
  condensation_alarm: { label: '结露报警', options: [{ value: '0', label: '正常' }, { value: '1', label: '报警' }] },
  '2nd_inwater_temp_detect': { label: '二次进水温度', unit: '℃' },
  '2nd_outwater_temp_detect': { label: '二次出水温度', unit: '℃' },
  primary_valve_opening: { label: '一次阀开度', unit: '%' },
  fan_speed: { label: '风机转速', unit: 'rpm' },
  pau_out_temp: { label: '送风温度', unit: '℃' },
  filter_working_time: { label: '滤网已运行', unit: 'h' },
  total_cold_quantity: { label: '累计冷量' },
  total_hot_quantity: { label: '累计热量' },
  co2: { label: 'CO₂', unit: 'ppm' },
  pm25: { label: 'PM2.5', unit: 'µg/m³' },
  hcho: { label: '甲醛', unit: 'mg/m³' },
  tvoc: { label: 'TVOC', unit: 'mg/m³' },
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

  it('运行模式 mode 控件类型被改写为 pills（图标药丸）', () => {
    const mode = buildControls({ product_code: '270001', params: [] }, WA).find((c) => c.tag === 'mode')
    expect(mode.control).toBe('pills')
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
    expect(buildPanels(structure, CONFIG).map((p) => p.title)).toEqual(['能耗表', '空气质量'])
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

// ── buildCard：米家风卡片视图模型 ────────────────────────────────────────────
// 工具：用 buildControls 造真实控件，组一个面板设备
function panelDev(sn, pc) {
  return { deviceSn: String(sn), productCode: pc, controls: buildControls({ product_code: pc, params: [] }, WA), allParams: [] }
}

describe('buildCard', () => {
  it('客厅(260001)：switch 抽为头部开关、temp_set 为卡面控件，温度/湿度/露点统一小字 chips、NTC_temp 进查看全部', () => {
    const panel = { id: 'sys-260001', title: '客厅', devices: [panelDev(2222, '260001')] }
    const attrs = { 2222: { switch: 'off', temp: '24.5', humidity: '55.0', temp_set: '26.0', NTC_temp: '24.5', comm_fault_timeout: 'normal', error_1: '0' } }
    const card = buildCard(panel, attrs, CONFIG)
    expect(card.icon).toBe('🌡')
    expect(card.switchCtl.w.tag).toBe('switch')
    expect(card.controls.map((c) => c.w.tag)).toEqual(['temp_set'])
    expect(card.big).toBeUndefined() // #1：不再有大字区
    expect(card.small.map((m) => m.tag)).toEqual(['temp', 'humidity', 'dew_point_temp'])
    expect(card.small.find((m) => m.tag === 'temp').value).toBe('24.5℃')
    expect(card.small.find((m) => m.tag === 'humidity').value).toBe('55.0%') // 原值拼单位，不做小数裁剪
    expect(card.small.find((m) => m.tag === 'dew_point_temp').value).toBe('—') // 无值占位
    expect(card.rest.map((r) => r.tag)).toEqual(['NTC_temp']) // comm_fault/error 被过滤
  })

  it('主机(270001)：system_switch 头部、mode(dots) 排首位、能源供应/阀开度进查看全部', () => {
    const panel = { id: 'sys-270001', title: '主机', devices: [panelDev(9001, '270001')] }
    const attrs = { 9001: {
      system_switch: 'on', mode: 'cold', energy_saving_sign: 'off', energy_supply_mode: 'cold',
      '2nd_inwater_temp_detect': '15.5', '2nd_outwater_temp_detect': '22.8', primary_valve_opening: '0.3', comm_fault_timeout: 'normal',
    } }
    const card = buildCard(panel, attrs, CONFIG)
    expect(card.icon).toBe('🔥')
    expect(card.switchCtl.w.tag).toBe('system_switch')
    expect(card.controls.map((c) => c.w.tag)).toEqual(['mode', 'energy_saving_sign']) // primaryTags 把 mode 排首
    expect(card.controls[0].w.control).toBe('pills')
    expect(card.small.map((m) => m.tag)).toEqual(['2nd_inwater_temp_detect', '2nd_outwater_temp_detect'])
    expect(card.small[0].value).toBe('15.5℃')
    expect(card.rest.map((r) => r.tag)).toEqual(['energy_supply_mode', 'primary_valve_opening'])
  })

  it('空气品质(100007)：无开关无控件，co2/pm25/hcho/tvoc 统一小字 chips（#6 不重叠/字体统一）', () => {
    const panel = { id: 'sys-extra-100007', title: '空气质量', devices: [panelDev(7002, '100007')] }
    const attrs = { 7002: { co2: '606', pm25: '0', hcho: '0.000', tvoc: '0.000', comm_fault_timeout: 'normal', error_265: '0' } }
    const card = buildCard(panel, attrs, CONFIG)
    expect(card.icon).toBe('🌫️')
    expect(card.switchCtl).toBeNull()
    expect(card.controls).toEqual([])
    expect(card.grid).toBeUndefined() // #6：取消网格特例
    expect(card.small.map((m) => m.tag)).toEqual(['co2', 'pm25', 'hcho', 'tvoc'])
    expect(card.small.find((m) => m.tag === 'co2').value).toBe('606ppm')
    expect(card.rest).toEqual([]) // 指标已展示 + 诊断过滤
  })

  it('新风合并卡(130004+10016)：控件来自 10016（风速/加湿），小字来自 130004，无头部开关，#2 隐藏 10016 的 mode/system_switch', () => {
    const panel = { id: 'sys-130004-10016', title: '新风', devices: [panelDev(9002, '130004'), panelDev(9005, '10016')] }
    const attrs = {
      9002: { fan_speed: '1674', pau_out_temp: '15.4', filter_working_time: '653', out_temp_set: '13.0', comm_fault_timeout: 'normal' },
      9005: { wind_speed: 'normal', humidification_enable: 'off', mode: 'cold', system_switch: 'on' }, // 10016 会镜像推 mode/system_switch
    }
    const card = buildCard(panel, attrs, CONFIG)
    expect(card.icon).toBe('💨')
    expect(card.switchCtl).toBeNull() // 10016 无 system_switch 控件 → 不出头部开关
    expect(card.controls.map((c) => c.w.tag)).toEqual(['wind_speed', 'humidification_enable'])
    expect(card.small.map((m) => m.tag)).toEqual(['pau_out_temp', 'filter_working_time'])
    expect(card.small.find((m) => m.tag === 'pau_out_temp').value).toBe('15.4℃')
    // #2：mode / system_switch（10016 镜像）不出现在任何位置
    const restTags = card.rest.map((r) => r.tag)
    expect(restTags).not.toContain('mode')
    expect(restTags).not.toContain('system_switch')
    // out_temp_set/fan_speed 未在卡面突出 → 进查看全部
    expect(restTags).toEqual(['out_temp_set', 'fan_speed'])
  })

  it('风速 select 控件携带 options 供分段 chips 渲染', () => {
    const panel = { id: 'sys-130004-10016', title: '新风', devices: [panelDev(9005, '10016')] }
    const ws = buildCard(panel, { 9005: {} }, CONFIG).controls.find((c) => c.w.tag === 'wind_speed')
    expect(ws.w.control).toBe('select')
    expect(ws.w.options.map((o) => o.value)).toEqual(['normal', 'high_speed'])
  })
})
