/**
 * param_settings_devicelist.spec.js
 *
 * 测试 v1.11.3 deviceList computed 中的核心算法逻辑。
 * 由于 param-settings.vue 是 Vue3 SFC，无法在 Node/Vitest 环境下直接 import，
 * 此处将三个核心纯函数在测试文件内复现，测试算法语义而非 Vue 绑定。
 *
 * 覆盖 AC：
 *   AC-001-01 / AC-001-02 / AC-001-03 (US-001)
 *   AC-002-01 / AC-002-02 / AC-002-03 (US-002)
 *   AC-003-01 / AC-003-02             (US-003)
 *   AC-005-01 / AC-005-02             (US-005)
 *
 * NOT_TESTABLE（需 Vue 运行时或微信开发者工具）：
 *   AC-003-03 / AC-004-01 / AC-004-02 / AC-004-03
 */

import { describe, it, expect } from 'vitest'

// ─────────────────────────────────────────────────────────────────────────────
// 从 param-settings.vue 提取的纯函数（语义完全一致，不依赖 Vue 运行时）
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 与 SFC 中 IFC-1111-FE-01-5 resolveRoomName 完全一致。
 */
function resolveRoomName(room) {
  return room.room_name || room.ori_room_name || '未知房间'
}

/**
 * 从 structure 构建 deviceSn(string) → 房间名 Map。
 * 对应 deviceList computed 中的同名逻辑块（约第 329-337 行）。
 */
function buildRoomNameMap(structure) {
  const roomNameMap = new Map()
  if (structure?.rooms) {
    for (const room of structure.rooms) {
      const name = resolveRoomName(room)
      for (const device of (room.devices || [])) {
        roomNameMap.set(String(device.device_sn), name) // String() 归一化
      }
    }
  }
  return roomNameMap
}

/**
 * 三层优先级 role 计算。
 * 对应 deviceList computed 中约第 360 行：
 *   role: roomNameMap.get(sn) ?? roleMap[productCode] ?? `设备 ${productCode || ''}`
 */
function computeRole(sn, roomNameMap, productCode, roleMap) {
  return roomNameMap.get(sn) ?? roleMap[productCode] ?? `设备 ${productCode || ''}`
}

// ─────────────────────────────────────────────────────────────────────────────
// TC-UNIT-001 ~ TC-UNIT-003 — resolveRoomName（US-001 AC-001-01/02/03）
// ─────────────────────────────────────────────────────────────────────────────

describe('resolveRoomName', () => {
  it('TC-UNIT-001 [AC-001-01] room_name 有值 → 返回 room_name', () => {
    // Given: 房间对象 room_name="主卧", ori_room_name="bedroom"
    // When:  调用 resolveRoomName
    // Then:  返回 "主卧"
    const room = { room_name: '主卧', ori_room_name: 'bedroom' }
    expect(resolveRoomName(room)).toBe('主卧')
  })

  it('TC-UNIT-002 [AC-001-02] room_name 为空，ori_room_name 有值 → 返回 ori_room_name', () => {
    // Given: room_name="" (falsy), ori_room_name="bedroom"
    // When:  调用 resolveRoomName
    // Then:  返回 "bedroom"
    const room = { room_name: '', ori_room_name: 'bedroom' }
    expect(resolveRoomName(room)).toBe('bedroom')
  })

  it('TC-UNIT-003 [AC-001-03] room_name 和 ori_room_name 均为空 → 返回 "未知房间"', () => {
    // Given: room_name="", ori_room_name=""
    // When:  调用 resolveRoomName
    // Then:  返回 "未知房间"
    const room = { room_name: '', ori_room_name: '' }
    expect(resolveRoomName(room)).toBe('未知房间')
  })

  it('TC-UNIT-004 [AC-001-03] room_name/ori_room_name 均缺失（undefined）→ 返回 "未知房间"', () => {
    const room = {}
    expect(resolveRoomName(room)).toBe('未知房间')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// TC-UNIT-005 ~ TC-UNIT-009 — buildRoomNameMap（Map 构建逻辑）
// ─────────────────────────────────────────────────────────────────────────────

describe('buildRoomNameMap', () => {
  it('TC-UNIT-005 [AC-001-01] 正常 structure → Map 填充正确', () => {
    const structure = {
      rooms: [
        {
          room_name: '主卧',
          devices: [{ device_sn: '1001' }, { device_sn: '1002' }],
        },
        {
          room_name: '次卧',
          devices: [{ device_sn: '1003' }],
        },
      ],
    }
    const map = buildRoomNameMap(structure)
    expect(map.get('1001')).toBe('主卧')
    expect(map.get('1002')).toBe('主卧')
    expect(map.get('1003')).toBe('次卧')
    expect(map.size).toBe(3)
  })

  it('TC-UNIT-006 [AC-005-01] device_sn 为数字时 String() 归一化 → key 为字符串', () => {
    // Given: MQTT key 是字符串 "1001"，structure device_sn 是数字 1001
    // When:  buildRoomNameMap 构建 Map
    // Then:  Map.get("1001") 命中，而非 Map.get(1001)
    const structure = {
      rooms: [
        {
          room_name: '书房',
          devices: [{ device_sn: 1001 }], // 数字类型
        },
      ],
    }
    const map = buildRoomNameMap(structure)
    expect(map.has(1001)).toBe(false)         // 数字 key 不存在
    expect(map.get('1001')).toBe('书房')      // 字符串 key 命中
  })

  it('TC-UNIT-007 [AC-005-02] device_sn 已是字符串 → String() 幂等，匹配成功', () => {
    const structure = {
      rooms: [
        {
          room_name: '客厅',
          devices: [{ device_sn: '1002' }], // 已是字符串
        },
      ],
    }
    const map = buildRoomNameMap(structure)
    expect(map.get('1002')).toBe('客厅')
  })

  it('TC-UNIT-008 [AC-003-01] structure = null → Map 为空（不崩溃）', () => {
    const map = buildRoomNameMap(null)
    expect(map.size).toBe(0)
  })

  it('TC-UNIT-009 [AC-003-01] structure.rooms 为空数组 → Map 为空', () => {
    const map = buildRoomNameMap({ rooms: [] })
    expect(map.size).toBe(0)
  })

  it('TC-UNIT-010 [AC-003-02] structure = null，多 sn 查询 → 均返回 undefined（无 TypeError）', () => {
    // Given: structure = null（null structure 场景）
    // When:  对多个 sn 调用 Map.get
    // Then:  全部返回 undefined，不抛异常
    const map = buildRoomNameMap(null)
    expect(() => {
      const results = ['1001', '1002', '1003'].map(sn => map.get(sn))
      results.forEach(r => expect(r).toBeUndefined())
    }).not.toThrow()
  })

  it('TC-UNIT-011 room.devices 缺失（undefined）→ 不崩溃，Map 仍为空', () => {
    const structure = {
      rooms: [
        { room_name: '车库' }, // devices 字段缺失
      ],
    }
    expect(() => buildRoomNameMap(structure)).not.toThrow()
    expect(buildRoomNameMap(structure).size).toBe(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// TC-UNIT-012 ~ TC-UNIT-014 — computeRole 三层优先级（US-002）
// ─────────────────────────────────────────────────────────────────────────────

describe('computeRole 三层优先级', () => {
  it('TC-UNIT-012 [AC-001-01/AC-002-01] roomNameMap 命中 → 返回房间名（不返回 roleMap 值）', () => {
    // Given: roomNameMap 有 sn="1001"→"主卧"，roleMap 有 productCode→"末端温控"
    // When:  computeRole
    // Then:  返回 "主卧"（roomNameMap 优先）
    const map = new Map([['1001', '主卧']])
    const roleMap = { 'ACU-01': '末端温控' }
    expect(computeRole('1001', map, 'ACU-01', roleMap)).toBe('主卧')
  })

  it('TC-UNIT-013 [AC-002-01] roomNameMap 未命中，roleMap 有值 → 返回 roleMap 角色名', () => {
    // Given: roomNameMap 无 sn="9001"，roleMap 有 productCode="SYS-01"→"主机"
    // When:  computeRole
    // Then:  返回 "主机"
    const map = new Map()
    const roleMap = { 'SYS-01': '主机' }
    expect(computeRole('9001', map, 'SYS-01', roleMap)).toBe('主机')
  })

  it('TC-UNIT-014 两者均未命中 → 返回 `设备 ${productCode}`', () => {
    const map = new Map()
    const roleMap = {}
    expect(computeRole('9999', map, 'XYZ', roleMap)).toBe('设备 XYZ')
  })

  it('TC-UNIT-015 两者均未命中且 productCode 为空 → 返回 "设备 "', () => {
    const map = new Map()
    const roleMap = {}
    expect(computeRole('9999', map, '', roleMap)).toBe('设备 ')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// TC-UNIT-016 — 复合场景：末端温控 + 系统设备同时存在（AC-002-03）
// ─────────────────────────────────────────────────────────────────────────────

describe('复合场景：末端温控与系统设备互不干扰 [AC-002-03]', () => {
  it('TC-UNIT-016 末端温控显示房间名，系统设备显示角色名', () => {
    // Given:
    //   structure.rooms 包含末端温控 sn="1001"（主卧）和 sn="1002"（次卧）
    //   系统设备 sn="9001" 不在 structure.rooms 中，只在 roleMap 中
    // When: 分别查询 role
    // Then: 末端温控 → 房间名；系统设备 → roleMap 角色名
    const structure = {
      rooms: [
        { room_name: '主卧', devices: [{ device_sn: '1001' }] },
        { room_name: '次卧', devices: [{ device_sn: '1002' }] },
      ],
    }
    const map = buildRoomNameMap(structure)
    const roleMap = { 'SYS-01': '冷水机组' }

    // 末端温控（在 rooms 中）
    expect(computeRole('1001', map, 'ACU-01', roleMap)).toBe('主卧')
    expect(computeRole('1002', map, 'ACU-01', roleMap)).toBe('次卧')

    // 系统设备（不在 rooms 中）
    expect(computeRole('9001', map, 'SYS-01', roleMap)).toBe('冷水机组')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// TC-UNIT-017 ~ TC-UNIT-019 — AC-001-01/02/03 完整 Given/When/Then 场景
// ─────────────────────────────────────────────────────────────────────────────

describe('AC-001 完整 Given/When/Then 场景', () => {
  it('TC-UNIT-017 [AC-001-01] structure 已缓存，room_name 有值 → role = 房间名', () => {
    // Given: structure 已缓存（模拟已加载），room 有 room_name="书房"
    // When:  buildRoomNameMap + computeRole
    // Then:  role = "书房"（不显示"末端温控"）
    const structure = {
      rooms: [{ room_name: '书房', devices: [{ device_sn: '2001' }] }],
    }
    const map = buildRoomNameMap(structure)
    const roleMap = { 'ACU-02': '末端温控' }
    const role = computeRole('2001', map, 'ACU-02', roleMap)
    expect(role).toBe('书房')
    expect(role).not.toBe('末端温控')
  })

  it('TC-UNIT-018 [AC-001-02] room_name 为空，ori_room_name 有值 → role = ori_room_name', () => {
    // Given: room.room_name="" (falsy), room.ori_room_name="living_room"
    // When:  buildRoomNameMap + computeRole
    // Then:  role = "living_room"
    const structure = {
      rooms: [
        {
          room_name: '',
          ori_room_name: 'living_room',
          devices: [{ device_sn: '2002' }],
        },
      ],
    }
    const map = buildRoomNameMap(structure)
    const roleMap = {}
    expect(computeRole('2002', map, 'ACU-02', roleMap)).toBe('living_room')
  })

  it('TC-UNIT-019 [AC-001-03] room_name 和 ori_room_name 均为空 → role = "未知房间"', () => {
    // Given: room_name="" ori_room_name=""
    // When:  buildRoomNameMap + computeRole
    // Then:  role = "未知房间"
    const structure = {
      rooms: [
        {
          room_name: '',
          ori_room_name: '',
          devices: [{ device_sn: '2003' }],
        },
      ],
    }
    const map = buildRoomNameMap(structure)
    const roleMap = {}
    expect(computeRole('2003', map, 'ACU-02', roleMap)).toBe('未知房间')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// TC-UNIT-020 ~ TC-UNIT-021 — AC-005 类型归一化（US-005）
// ─────────────────────────────────────────────────────────────────────────────

describe('AC-005 deviceSn 类型归一化', () => {
  it('TC-UNIT-020 [AC-005-01] MQTT key 字符串 "1001" vs structure device_sn 数字 1001 → 匹配成功', () => {
    // Given: MQTT 推送的 sn 为字符串 "1001"，structure 中 device_sn 为数字 1001
    // When:  buildRoomNameMap + computeRole
    // Then:  Map.get("1001") 命中房间名（不因类型不匹配而 fallback）
    const structure = {
      rooms: [{ room_name: '儿童房', devices: [{ device_sn: 1001 }] }],
    }
    const map = buildRoomNameMap(structure)
    const roleMap = { 'ACU-03': '末端温控' }
    // MQTT key 是字符串 "1001"
    expect(computeRole('1001', map, 'ACU-03', roleMap)).toBe('儿童房')
  })

  it('TC-UNIT-021 [AC-005-02] device_sn 已是字符串 "1002" → String() 幂等，匹配成功', () => {
    // Given: structure device_sn 已是字符串 "1002"
    // When:  buildRoomNameMap + computeRole
    // Then:  String("1002") === "1002"，正常命中
    const structure = {
      rooms: [{ room_name: '餐厅', devices: [{ device_sn: '1002' }] }],
    }
    const map = buildRoomNameMap(structure)
    const roleMap = {}
    expect(computeRole('1002', map, 'ACU-03', roleMap)).toBe('餐厅')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// TC-UNIT-022 — AC-002-02：system_devices 中的设备不在 rooms → role = roleMap 值
// ─────────────────────────────────────────────────────────────────────────────

describe('AC-002-02 system_devices 不在 rooms 中', () => {
  it('TC-UNIT-022 设备仅在 system_devices，rooms 中不存在 → role 走 roleMap', () => {
    // Given: structure.rooms 无 sn="8001"，structure.system_devices 有（但不影响 Map 构建）
    // When:  buildRoomNameMap 只遍历 rooms，computeRole 对 "8001" 查不到
    // Then:  role = roleMap["CHILLER"] = "冷水机"
    const structure = {
      rooms: [{ room_name: '主卧', devices: [{ device_sn: '1001' }] }],
      system_devices: [{ device_sn: '8001', product_code: 'CHILLER' }],
    }
    const map = buildRoomNameMap(structure)
    expect(map.has('8001')).toBe(false) // system_devices 不被加入 Map
    const roleMap = { CHILLER: '冷水机' }
    expect(computeRole('8001', map, 'CHILLER', roleMap)).toBe('冷水机')
  })
})
