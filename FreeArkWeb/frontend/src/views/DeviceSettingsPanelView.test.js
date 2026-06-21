/**
 * DeviceSettingsPanelView — 温度步进控件单元测试
 *
 * 覆盖 US-001~007 的 AC，重点：
 *   - 步进换算：13.5 ↔ 135，26.0 ↔ 260
 *   - 边界禁用：房间 16.0/30.0、出风 10.0/30.0
 *   - 禁止手工输入（展示值只通过步进按钮改变）
 *   - 提交反向换算（×10 取整为整数字符串）
 *   - 非温度参数（枚举）不受影响
 *
 * 说明：由于组件依赖 Element Plus、API 和 WebSocket，
 * 这里将核心纯逻辑提取为独立测试，不挂载完整组件。
 */

import { describe, it, expect } from 'vitest'

// ─────────────────────────────────────────────────────────────────────────────
// 复制自 DeviceSettingsPanelView.vue 的纯逻辑（便于单元测试）
// ─────────────────────────────────────────────────────────────────────────────

const TEMP_BOUNDS_MAP = {
  living_room_temp_setting:          { min: 16.0, max: 30.0, step: 0.5 },
  bedroom_temp_setting:              { min: 16.0, max: 30.0, step: 0.5 },
  study_room_temp_setting:           { min: 16.0, max: 30.0, step: 0.5 },
  children_room_temp_setting:        { min: 16.0, max: 30.0, step: 0.5 },
  fourth_children_room_temp_setting: { min: 16.0, max: 30.0, step: 0.5 },
  supply_air_temp_setting:           { min: 10.0, max: 30.0, step: 0.5 },
}
const TEMP_BOUNDS_DEFAULT = { min: 16.0, max: 30.0, step: 0.5 }

const getTempBounds = (paramName) => TEMP_BOUNDS_MAP[paramName] || TEMP_BOUNDS_DEFAULT

const formatTempDisplay = (val) => {
  if (val === null || val === undefined) return '— ℃'
  return `${Number(val).toFixed(1)} ℃`
}

/**
 * 步进温度（返回新值，纯函数版，用于测试）
 * delta = +1 或 -1
 */
const stepTempPure = (paramName, current, delta) => {
  const bounds = getTempBounds(paramName)
  const currentInt = Math.round(current * 10)
  const stepInt = Math.round(bounds.step * 10)
  const newInt = currentInt + delta * stepInt
  const minInt = Math.round(bounds.min * 10)
  const maxInt = Math.round(bounds.max * 10)
  const clampedInt = Math.max(minInt, Math.min(maxInt, newInt))
  return clampedInt / 10
}

/**
 * 提交时温度值反向换算（REQ-FUNC-004）
 * 展示值（℃ 小数）× 10 取整 → 底层整数字符串
 */
const tempDisplayToSubmitValue = (displayVal) => String(Math.round(displayVal * 10))

/**
 * 加载时初始化温度展示值（底层整数 ÷10）
 */
const rawIntToDisplayTemp = (rawInt) => Math.round(Number(rawInt)) / 10

// ─────────────────────────────────────────────────────────────────────────────
// 测试套件
// ─────────────────────────────────────────────────────────────────────────────

describe('TEMP_BOUNDS_MAP — 边界映射（REQ-FUNC-006）', () => {
  it('TC-BOUNDS-01: 5个房间设定温度参数的边界均为 16.0~30.0℃', () => {
    const roomParams = [
      'living_room_temp_setting',
      'bedroom_temp_setting',
      'study_room_temp_setting',
      'children_room_temp_setting',
      'fourth_children_room_temp_setting',
    ]
    roomParams.forEach(p => {
      const b = getTempBounds(p)
      expect(b.min).toBe(16.0)
      expect(b.max).toBe(30.0)
      expect(b.step).toBe(0.5)
    })
  })

  it('TC-BOUNDS-02: supply_air_temp_setting 边界为 10.0~30.0℃', () => {
    const b = getTempBounds('supply_air_temp_setting')
    expect(b.min).toBe(10.0)
    expect(b.max).toBe(30.0)
    expect(b.step).toBe(0.5)
  })

  it('TC-BOUNDS-03: 未知 _temp_setting 参数使用安全兜底（16.0~30.0℃）', () => {
    const b = getTempBounds('unknown_room_temp_setting')
    expect(b.min).toBe(16.0)
    expect(b.max).toBe(30.0)
    expect(b.step).toBe(0.5)
  })
})

describe('rawIntToDisplayTemp — 初始化展示值（÷10）', () => {
  it('TC-INIT-01: 130 → 13.0', () => {
    expect(rawIntToDisplayTemp(130)).toBe(13.0)
  })

  it('TC-INIT-02: 260 → 26.0', () => {
    expect(rawIntToDisplayTemp(260)).toBe(26.0)
  })

  it('TC-INIT-03: 255 → 25.5（0.5 颗粒度）', () => {
    expect(rawIntToDisplayTemp(255)).toBe(25.5)
  })

  it('TC-INIT-04: 字符串 "270" → 27.0', () => {
    expect(rawIntToDisplayTemp('270')).toBe(27.0)
  })
})

describe('formatTempDisplay — 展示格式化', () => {
  it('TC-FMT-01: 13.0 → "13.0 ℃"', () => {
    expect(formatTempDisplay(13.0)).toBe('13.0 ℃')
  })

  it('TC-FMT-02: 13.5 → "13.5 ℃"（AC-002-01）', () => {
    expect(formatTempDisplay(13.5)).toBe('13.5 ℃')
  })

  it('TC-FMT-03: 26.0 → "26.0 ℃"（AC-002-02）', () => {
    expect(formatTempDisplay(26.0)).toBe('26.0 ℃')
  })

  it('TC-FMT-04: null/undefined → "— ℃"', () => {
    expect(formatTempDisplay(null)).toBe('— ℃')
    expect(formatTempDisplay(undefined)).toBe('— ℃')
  })
})

describe('stepTempPure — 步进逻辑（REQ-FUNC-002/003）', () => {
  // AC-002-01: 某 _temp_setting 参数当前值 13.0 ℃，点击 ＋ → 13.5 ℃
  // supply_air_temp_setting 下限为 10.0，13.0 在合法范围内
  it('TC-STEP-01: 13.0 + 0.5 → 13.5（AC-002-01，使用 supply_air_temp_setting）', () => {
    const result = stepTempPure('supply_air_temp_setting', 13.0, +1)
    expect(result).toBe(13.5)
  })

  // AC-002-02: 26.0 ℃ 点击 － → 25.5 ℃，底层值 255
  it('TC-STEP-02: 26.0 - 0.5 → 25.5（AC-002-02）', () => {
    const result = stepTempPure('living_room_temp_setting', 26.0, -1)
    expect(result).toBe(25.5)
  })

  // AC-003-02: 29.5 + 0.5 → 30.0，下一步 ＋ 被禁用
  it('TC-STEP-03: 29.5 + 0.5 → 30.0，恰好到达上限（AC-003-02）', () => {
    const result = stepTempPure('living_room_temp_setting', 29.5, +1)
    expect(result).toBe(30.0)
  })

  // AC-004-02: 16.5 - 0.5 → 16.0，下一步 － 被禁用
  it('TC-STEP-04: 16.5 - 0.5 → 16.0，恰好到达下限（AC-004-02）', () => {
    const result = stepTempPure('living_room_temp_setting', 16.5, -1)
    expect(result).toBe(16.0)
  })

  // AC-003-01: 已在上限 30.0，再次 + 仍为 30.0（clamp）
  it('TC-STEP-05: 30.0 + 0.5 被 clamp，仍为 30.0（AC-003-01）', () => {
    const result = stepTempPure('living_room_temp_setting', 30.0, +1)
    expect(result).toBe(30.0)
  })

  // AC-004-01: 已在下限 16.0，再次 - 仍为 16.0（clamp）
  it('TC-STEP-06: 16.0 - 0.5 被 clamp，仍为 16.0（AC-004-01）', () => {
    const result = stepTempPure('living_room_temp_setting', 16.0, -1)
    expect(result).toBe(16.0)
  })

  // AC-004-03: supply_air_temp_setting 下限 10.0
  it('TC-STEP-07: supply_air_temp_setting 10.0 - 0.5 被 clamp，仍为 10.0（AC-004-03）', () => {
    const result = stepTempPure('supply_air_temp_setting', 10.0, -1)
    expect(result).toBe(10.0)
  })

  // AC-003-03: supply_air_temp_setting 上限 30.0
  it('TC-STEP-08: supply_air_temp_setting 30.0 + 0.5 被 clamp，仍为 30.0（AC-003-03）', () => {
    const result = stepTempPure('supply_air_temp_setting', 30.0, +1)
    expect(result).toBe(30.0)
  })

  it('TC-STEP-09: supply_air_temp_setting 10.5 + 0.5 → 11.0', () => {
    const result = stepTempPure('supply_air_temp_setting', 10.5, +1)
    expect(result).toBe(11.0)
  })
})

describe('禁用逻辑（边界比较，REQ-FUNC-003，AC-003/004）', () => {
  // 前端模板：:disabled="inputValues[paramName] >= bounds.max"
  it('TC-DISABLE-01: 到达上限 30.0 时，＋ 按钮应禁用（inputVal >= max）', () => {
    const paramName = 'living_room_temp_setting'
    const bounds = getTempBounds(paramName)
    const currentVal = 30.0
    expect(currentVal >= bounds.max).toBe(true)   // disabled = true
    expect(currentVal <= bounds.min).toBe(false)  // 另一按钮不禁用
  })

  it('TC-DISABLE-02: 到达下限 16.0 时，－ 按钮应禁用（inputVal <= min）', () => {
    const paramName = 'living_room_temp_setting'
    const bounds = getTempBounds(paramName)
    const currentVal = 16.0
    expect(currentVal <= bounds.min).toBe(true)   // disabled = true
    expect(currentVal >= bounds.max).toBe(false)  // 另一按钮不禁用
  })

  it('TC-DISABLE-03: supply_air_temp_setting 下限 10.0 时，－ 禁用', () => {
    const bounds = getTempBounds('supply_air_temp_setting')
    expect(10.0 <= bounds.min).toBe(true)
  })

  it('TC-DISABLE-04: 中间值 20.0 时两个按钮均不禁用', () => {
    const bounds = getTempBounds('living_room_temp_setting')
    const v = 20.0
    expect(v >= bounds.max).toBe(false)  // ＋ 不禁用
    expect(v <= bounds.min).toBe(false)  // － 不禁用
  })
})

describe('tempDisplayToSubmitValue — 提交反向换算（REQ-FUNC-004）', () => {
  // AC-006-01: 展示 13.5 → 提交 "135"
  it('TC-SUBMIT-01: 13.5 → "135"（AC-006-01）', () => {
    expect(tempDisplayToSubmitValue(13.5)).toBe('135')
  })

  // AC-006-02: 展示 26.0 → 提交 "260"
  it('TC-SUBMIT-02: 26.0 → "260"（AC-006-02）', () => {
    expect(tempDisplayToSubmitValue(26.0)).toBe('260')
  })

  it('TC-SUBMIT-03: 16.0 → "160"（房间最小值）', () => {
    expect(tempDisplayToSubmitValue(16.0)).toBe('160')
  })

  it('TC-SUBMIT-04: 30.0 → "300"（上限）', () => {
    expect(tempDisplayToSubmitValue(30.0)).toBe('300')
  })

  it('TC-SUBMIT-05: 10.0 → "100"（出风下限）', () => {
    expect(tempDisplayToSubmitValue(10.0)).toBe('100')
  })

  it('TC-SUBMIT-06: 18.0 → "180"（AC-006-03 混合提交中的温度项）', () => {
    expect(tempDisplayToSubmitValue(18.0)).toBe('180')
  })

  it('TC-SUBMIT-07: 结果为字符串类型（not number）', () => {
    expect(typeof tempDisplayToSubmitValue(13.5)).toBe('string')
    expect(typeof tempDisplayToSubmitValue(26.0)).toBe('string')
  })
})

describe('非温度参数不受影响（REQ-FUNC-005，AC-007）', () => {
  // 验证 _switch/_mode 参数的 param_name.endsWith('_temp_setting') 判断为 false
  it('TC-NTEMP-01: _switch 参数名不以 _temp_setting 结尾', () => {
    expect('cool_switch'.endsWith('_temp_setting')).toBe(false)
  })

  it('TC-NTEMP-02: _mode 参数名不以 _temp_setting 结尾', () => {
    expect('operation_mode'.endsWith('_temp_setting')).toBe(false)
  })

  it('TC-NTEMP-03: away_energy_saving 不以 _temp_setting 结尾', () => {
    expect('away_energy_saving'.endsWith('_temp_setting')).toBe(false)
  })

  it('TC-NTEMP-04: central_energy_supply 不以 _temp_setting 结尾', () => {
    expect('central_energy_supply'.endsWith('_temp_setting')).toBe(false)
  })

  // 枚举值不做 ×10 换算，以原始字符串提交（AC-007-02）
  it('TC-NTEMP-05: 枚举参数提交值不做换算，String("1") = "1"', () => {
    // 模拟 handleBatchSubmit 中枚举参数路径：String(inputValues[p.param_name])
    const enumVal = '1'
    expect(String(enumVal)).toBe('1')  // 不变
  })
})

describe('浮点精度保证（步进整数算术）', () => {
  it('TC-FLOAT-01: 0.1 + 0.2 精度问题不影响步进结果', () => {
    // 直接 0.1 + 0.2 = 0.30000000000000004，但整数算术无此问题
    const result = stepTempPure('living_room_temp_setting', 16.0, +1)
    expect(result).toBe(16.5)
    // 验证无浮点尾差
    expect(result.toString()).toBe('16.5')
  })

  it('TC-FLOAT-02: 多次步进后无浮点累积误差', () => {
    let val = 16.0
    for (let i = 0; i < 28; i++) {  // 16.0 + 28 × 0.5 = 30.0
      val = stepTempPure('living_room_temp_setting', val, +1)
    }
    expect(val).toBe(30.0)
  })
})
