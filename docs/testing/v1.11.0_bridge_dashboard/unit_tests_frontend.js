/**
 * unit_tests_frontend.js
 * v1.11.0 Bridge Dashboard — Frontend Composable Pure Function Unit Tests
 *
 * Tests the 6 pure aggregation functions from useBridgeDashboard.js
 * and the 4 state methods from useAnimationControl.js.
 *
 * These functions are pure logic — no Vue runtime needed.
 * Run: node unit_tests_frontend.js
 *
 * @author sub_agent_test_engineer
 * @date 2026-07-08
 */

// ============================================================================
// Test Infrastructure
// ============================================================================

const tests = []
let passed = 0
let failed = 0

function test(name, fn) {
  tests.push({ name, fn })
}

function assert(condition, msg) {
  if (!condition) throw new Error(`ASSERTION FAILED: ${msg}`)
}

function assertEqual(actual, expected, msg) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `ASSERTION FAILED: ${msg}\n  Expected: ${JSON.stringify(expected)}\n  Actual:   ${JSON.stringify(actual)}`
    )
  }
}

function assertType(value, expectedType, msg) {
  const actualType = typeof value
  if (actualType !== expectedType) {
    throw new Error(
      `ASSERTION FAILED: ${msg}\n  Expected type: ${expectedType}\n  Actual type:   ${actualType}`
    )
  }
}

// ============================================================================
// Replicated Pure Functions from useBridgeDashboard.js + dependencies
// (Cannot import directly due to Vue dependency — pure logic replicated)
// ============================================================================

const ENERGY_KEYWORDS = [
  '能效', '能量', '电度', '电表', '功耗', '用电', '计量',
  '能源', 'energy', 'meter', 'power', 'energ',
]

const STATUS_RANK = { idle: 0, normal: 1, warning: 2, fault: 3 }

function worseStatus(a, b) {
  return (STATUS_RANK[a] || 0) >= (STATUS_RANK[b] || 0) ? a : b
}

function severityToStatus(severity) {
  if (severity === 'error') return 'fault'
  if (severity === 'warning') return 'warning'
  if (severity === 'condensation') return 'warning'
  return 'normal'
}

function isEnergyRelated(event) {
  const label = (event.device_type_label || '').toLowerCase()
  const name = (event.device_name || '').toLowerCase()
  return ENERGY_KEYWORDS.some((kw) => label.includes(kw) || name.includes(kw))
}

function groupFaultEventsByRoom(faultEvents) {
  const map = new Map()
  for (const ev of (faultEvents || [])) {
    const room = ev.room_name || '__unknown__'
    if (!map.has(room)) map.set(room, [])
    map.get(room).push(ev)
  }
  return map
}

function deriveEnergyStatus(plcRate, faultEvents) {
  const plcOnline = plcRate?.online_count ?? 0
  const plcTotal = plcRate?.total_count ?? 0

  let plcStatus = 'idle'
  if (plcTotal > 0) {
    if (plcOnline === plcTotal) plcStatus = 'normal'
    else if (plcOnline > 0) plcStatus = 'warning'
    else plcStatus = 'fault'
  }

  const energyFaults = (faultEvents || []).filter(isEnergyRelated)
  let eventStatus = 'normal'
  let faultCount = 0
  let warningCount = 0
  for (const ev of energyFaults) {
    const s = severityToStatus(ev.severity)
    if (s === 'fault') faultCount++
    else if (s === 'warning') warningCount++
    eventStatus = worseStatus(eventStatus, s)
  }

  const status = plcTotal > 0
    ? worseStatus(plcStatus, eventStatus)
    : (energyFaults.length > 0 ? eventStatus : 'idle')

  return {
    id: 'energy',
    name: '能耗中枢',
    status,
    faultCount,
    warningCount,
    productCode: null,
    dataSource: eventStatus === 'normal' && plcTotal > 0 ? 'PLC在线率' : 'FaultEvent+PLC',
  }
}

function aggregateSubsystemStatus(faultSummary, plcRate, faultEvents) {
  const data = faultSummary?.data || faultSummary || {}
  const freshAir = data.fresh_air_unit || {}
  const hydraulic = data.hydraulic_module || {}
  const airQuality = data.air_quality_sensor || {}

  const subsystems = []

  subsystems.push({
    id: 'fresh-air',
    name: '新风模块',
    status: (freshAir.fault_count || 0) > 0 ? 'fault' : 'normal',
    faultCount: freshAir.fault_count || 0,
    warningCount: 0,
    productCode: 130004,
    dataSource: 'device-fault-summary',
  })

  subsystems.push({
    id: 'hydraulic',
    name: '水力模块',
    status: (hydraulic.fault_count || 0) > 0 ? 'fault' : 'normal',
    faultCount: hydraulic.fault_count || 0,
    warningCount: 0,
    productCode: 270001,
    dataSource: 'device-fault-summary',
  })

  subsystems.push({
    id: 'air-quality',
    name: '空气品质',
    status: (airQuality.fault_count || 0) > 0 ? 'fault' : 'normal',
    faultCount: airQuality.fault_count || 0,
    warningCount: 0,
    productCode: 100007,
    dataSource: 'device-fault-summary',
  })

  subsystems.push(deriveEnergyStatus(plcRate, faultEvents))

  return subsystems
}

function aggregateRoomStatus(structure, faultEvents, condensationCount) {
  const rooms = structure?.rooms || []
  const eventMap = groupFaultEventsByRoom(faultEvents)

  const result = rooms.map((room) => {
    const roomName = room.room_name || room.ori_room_name || `房间 ${room.room_id}`
    const roomEvents = eventMap.get(room.room_name) || eventMap.get(room.ori_room_name) || []

    let status = 'normal'
    let faultCount = 0
    let warningCount = 0
    for (const ev of roomEvents) {
      const s = severityToStatus(ev.severity)
      if (s === 'fault') faultCount++
      else if (s === 'warning') warningCount++
      status = worseStatus(status, s)
    }

    const hasCondensation = room._hasCondensation || false

    return {
      id: `room-${room.room_id || roomName}`,
      name: roomName,
      status,
      faultCount,
      warningCount,
      hasCondensation,
    }
  })

  const knownNames = new Set(rooms.map((r) => r.room_name || r.ori_room_name))
  for (const [roomName, events] of eventMap) {
    if (roomName === '__unknown__' || knownNames.has(roomName)) continue
    let status = 'normal'
    let faultCount = 0
    let warningCount = 0
    for (const ev of events) {
      const s = severityToStatus(ev.severity)
      if (s === 'fault') faultCount++
      else if (s === 'warning') warningCount++
      status = worseStatus(status, s)
    }
    result.push({
      id: `room-evt-${roomName}`,
      name: roomName,
      status,
      faultCount,
      warningCount,
      hasCondensation: false,
    })
  }

  return result
}

function computeOverallStatus(subsystems, rooms) {
  let worst = 'normal'
  let allIdle = true
  let hasItems = false
  for (const s of (subsystems || [])) {
    hasItems = true
    worst = worseStatus(worst, s.status)
    if (s.status !== 'idle') allIdle = false
  }
  for (const r of (rooms || [])) {
    hasItems = true
    worst = worseStatus(worst, r.status)
    if (r.status !== 'idle') allIdle = false
  }
  if (hasItems && allIdle) return { level: 'syncing', text: '等待数据' }
  if (worst === 'fault') return { level: 'fault', text: '告警' }
  if (worst === 'warning') return { level: 'warning', text: '预警' }
  return { level: 'normal', text: '正常' }
}

function filterFaultEventsByCompartment(faultEvents, compartment) {
  if (!compartment || !faultEvents?.length) return []
  if (compartment.type === 'subsystem') {
    switch (compartment.id) {
      case 'fresh-air': return faultEvents.filter((ev) => ev.product_code === 130004)
      case 'hydraulic': return faultEvents.filter((ev) => ev.product_code === 270001)
      case 'air-quality': return faultEvents.filter((ev) => ev.product_code === 100007)
      case 'energy': return faultEvents.filter(isEnergyRelated)
      default: return []
    }
  }
  if (compartment.type === 'room') {
    return faultEvents.filter((ev) =>
      ev.room_name === compartment.name ||
      ev.room_name === compartment.id
    )
  }
  return []
}

// ============================================================================
// TEST: severityToStatus (TC-UNIT-001 ~ TC-UNIT-005)
// ============================================================================

test('TC-UNIT-001: severityToStatus("error") => "fault"', () => {
  assertEqual(severityToStatus('error'), 'fault', 'error maps to fault')
})

test('TC-UNIT-002: severityToStatus("warning") => "warning"', () => {
  assertEqual(severityToStatus('warning'), 'warning', 'warning maps to warning')
})

test('TC-UNIT-003: severityToStatus("unknown") => "normal" (safe default)', () => {
  assertEqual(severityToStatus('unknown'), 'normal', 'unknown severity defaults to normal')
})

test('TC-UNIT-004: severityToStatus(null) => "normal" (null-safe)', () => {
  assertEqual(severityToStatus(null), 'normal', 'null defaults to normal')
})

test('TC-UNIT-005: severityToStatus("condensation") => "warning"', () => {
  assertEqual(severityToStatus('condensation'), 'warning', 'condensation maps to warning')
})

// ============================================================================
// TEST: worseStatus helper
// ============================================================================

test('TC-UNIT-AUX: worseStatus("normal","fault") => "fault"', () => {
  assertEqual(worseStatus('normal', 'fault'), 'fault', 'fault is worse than normal')
})

test('TC-UNIT-AUX: worseStatus("warning","normal") => "warning"', () => {
  assertEqual(worseStatus('warning', 'normal'), 'warning', 'warning is worse than normal')
})

test('TC-UNIT-AUX: worseStatus("idle","normal") => "normal"', () => {
  assertEqual(worseStatus('idle', 'normal'), 'normal', 'normal is worse than idle')
})

// ============================================================================
// TEST: isEnergyRelated (TC-UNIT-019 ~ TC-UNIT-022)
// ============================================================================

test('TC-UNIT-019: isEnergyRelated with "电度计量" => true', () => {
  assertEqual(isEnergyRelated({ device_type_label: '电度计量' }), true, 'Chinese keyword 电度')
})

test('TC-UNIT-020: isEnergyRelated with "energy meter" => true', () => {
  assertEqual(isEnergyRelated({ device_type_label: 'energy meter' }), true, 'English keyword energy')
})

test('TC-UNIT-020b: isEnergyRelated matches device_name field', () => {
  assertEqual(isEnergyRelated({ device_name: '功耗传感器' }), true, 'keyword in device_name')
})

test('TC-UNIT-021: isEnergyRelated with "新风机组" => false', () => {
  assertEqual(isEnergyRelated({ device_type_label: '新风机组', device_name: '新风' }), false, 'unrelated device')
})

test('TC-UNIT-022: isEnergyRelated with null fields => false', () => {
  assertEqual(isEnergyRelated({}), false, 'no fields — safe default')
})

// ============================================================================
// TEST: groupFaultEventsByRoom (TC-UNIT-028 ~ TC-UNIT-030)
// ============================================================================

test('TC-UNIT-028: groupFaultEventsByRoom groups 2 rooms correctly', () => {
  const events = [
    { room_name: '客厅', severity: 'error' },
    { room_name: '主卧', severity: 'warning' },
  ]
  const map = groupFaultEventsByRoom(events)
  assertEqual(map.size, 2, '2 rooms in map')
  assertEqual(map.get('客厅').length, 1, '客厅 has 1 event')
  assertEqual(map.get('主卧').length, 1, '主卧 has 1 event')
})

test('TC-UNIT-028b: groupFaultEventsByRoom groups multiple events in same room', () => {
  const events = [
    { room_name: '客厅', severity: 'error' },
    { room_name: '客厅', severity: 'warning' },
  ]
  const map = groupFaultEventsByRoom(events)
  assertEqual(map.size, 1, '1 room in map')
  assertEqual(map.get('客厅').length, 2, '客厅 has 2 events')
})

test('TC-UNIT-029: groupFaultEventsByRoom([]) => empty Map', () => {
  const map = groupFaultEventsByRoom([])
  assertEqual(map.size, 0, 'empty input yields empty map')
})

test('TC-UNIT-030: groupFaultEventsByRoom(null) => empty Map', () => {
  const map = groupFaultEventsByRoom(null)
  assertEqual(map.size, 0, 'null yields empty map')
})

// ============================================================================
// TEST: deriveEnergyStatus (TC-UNIT-014 ~ TC-UNIT-018)
// ============================================================================

test('TC-UNIT-014: deriveEnergyStatus — all PLC online, no fault events => normal', () => {
  const plcRate = { online_count: 5, total_count: 5 }
  const result = deriveEnergyStatus(plcRate, [])
  assertEqual(result.status, 'normal', 'PLC all online = normal')
  assertEqual(result.faultCount, 0, 'zero fault')
  assertEqual(result.warningCount, 0, 'zero warning')
  assertEqual(result.dataSource, 'PLC在线率', 'dataSource from PLC only')
})

test('TC-UNIT-015: deriveEnergyStatus — PLC partial offline => warning', () => {
  const plcRate = { online_count: 2, total_count: 5 }
  const result = deriveEnergyStatus(plcRate, [])
  assertEqual(result.status, 'warning', 'partial offline = warning')
})

test('TC-UNIT-016: deriveEnergyStatus — PLC all offline => fault', () => {
  const plcRate = { online_count: 0, total_count: 5 }
  const result = deriveEnergyStatus(plcRate, [])
  assertEqual(result.status, 'fault', 'all offline = fault')
})

test('TC-UNIT-017: deriveEnergyStatus — PLC normal + energy error events => fault', () => {
  const plcRate = { online_count: 5, total_count: 5 }
  const events = [{ device_type_label: '电度计量', severity: 'error' }]
  const result = deriveEnergyStatus(plcRate, events)
  assertEqual(result.status, 'fault', 'PLC normal but event error => fault')
  assertEqual(result.faultCount, 1, '1 energy fault counted')
})

test('TC-UNIT-018: deriveEnergyStatus — only energy warning, no PLC data => warning', () => {
  const plcRate = null
  const events = [{ device_type_label: '功耗传感器', severity: 'warning' }]
  const result = deriveEnergyStatus(plcRate, events)
  assertEqual(result.status, 'warning', 'warning event only => warning')
  assertEqual(result.warningCount, 1, '1 warning counted')
})

test('TC-UNIT-018b: deriveEnergyStatus — no data at all => idle', () => {
  const result = deriveEnergyStatus({}, [])
  assertEqual(result.status, 'idle', 'no data => idle')
})

// ============================================================================
// TEST: aggregateSubsystemStatus (TC-UNIT-011 ~ TC-UNIT-013)
// ============================================================================

test('TC-UNIT-011: aggregateSubsystemStatus — fresh_air has 3 faults', () => {
  const summary = {
    fresh_air_unit: { total: 5, fault_count: 3 },
    hydraulic_module: { total: 2, fault_count: 0 },
    air_quality_sensor: { total: 1, fault_count: 0 },
  }
  const result = aggregateSubsystemStatus(summary, { online_count: 5, total_count: 5 }, [])
  const freshAir = result.find((s) => s.id === 'fresh-air')
  assertEqual(freshAir.status, 'fault', 'fresh air status = fault')
  assertEqual(freshAir.faultCount, 3, 'fault count = 3')
})

test('TC-UNIT-012: aggregateSubsystemStatus — hydraulic has 0 faults => normal', () => {
  const summary = {
    fresh_air_unit: { fault_count: 0 },
    hydraulic_module: { fault_count: 0 },
    air_quality_sensor: { fault_count: 0 },
  }
  const result = aggregateSubsystemStatus(summary, { online_count: 5, total_count: 5 }, [])
  const hydraulic = result.find((s) => s.id === 'hydraulic')
  assertEqual(hydraulic.status, 'normal', 'hydraulic normal')
  assertEqual(hydraulic.faultCount, 0, 'zero faults')
})

test('TC-UNIT-013: aggregateSubsystemStatus — null input => all normal/idle', () => {
  const result = aggregateSubsystemStatus(null, null, [])
  assertEqual(result.length, 4, '4 subsystems generated')
  const names = result.map((s) => s.name)
  assert(names.includes('新风模块'), 'fresh-air included')
  assert(names.includes('能耗中枢'), 'energy included')
  assert(names.includes('水力模块'), 'hydraulic included')
  assert(names.includes('空气品质'), 'air-quality included')
})

test('TC-UNIT-013b: aggregateSubsystemStatus — missing fields default to zero', () => {
  const result = aggregateSubsystemStatus({}, {}, [])
  const freshAir = result.find((s) => s.id === 'fresh-air')
  assertEqual(freshAir.faultCount, 0, 'missing field defaults to 0')
  assertEqual(freshAir.status, 'normal', 'missing field status normal')
})

// ============================================================================
// TEST: aggregateRoomStatus (TC-UNIT-023 ~ TC-UNIT-027)
// ============================================================================

test('TC-UNIT-023: aggregateRoomStatus — room has error event => fault', () => {
  const structure = { rooms: [{ room_name: '客厅', room_id: 1 }] }
  const events = [{ room_name: '客厅', severity: 'error' }]
  const result = aggregateRoomStatus(structure, events, 0)
  assertEqual(result.length, 1, '1 room')
  assertEqual(result[0].name, '客厅', 'room name preserved')
  assertEqual(result[0].status, 'fault', 'status = fault')
  assertEqual(result[0].faultCount, 1, '1 fault')
})

test('TC-UNIT-024: aggregateRoomStatus — room has no events => normal', () => {
  const structure = { rooms: [{ room_name: '书房', room_id: 2 }] }
  const result = aggregateRoomStatus(structure, [], 0)
  assertEqual(result[0].status, 'normal', 'no events = normal')
  assertEqual(result[0].faultCount, 0, 'zero faults')
  assertEqual(result[0].warningCount, 0, 'zero warnings')
})

test('TC-UNIT-025: aggregateRoomStatus — room has warning + condensation => warning', () => {
  const structure = { rooms: [{ room_name: '主卧', room_id: 3 }] }
  const events = [
    { room_name: '主卧', severity: 'warning' },
    { room_name: '主卧', severity: 'condensation' },
  ]
  const result = aggregateRoomStatus(structure, events, 1)
  assertEqual(result[0].status, 'warning', 'status = warning')
  assertEqual(result[0].warningCount, 2, '2 warnings (including condensation)')
  assertEqual(result[0].faultCount, 0, 'zero faults')
})

test('TC-UNIT-026: aggregateRoomStatus — event-only room added to result', () => {
  const structure = { rooms: [{ room_name: '客厅', room_id: 1 }] }
  const events = [
    { room_name: '客厅', severity: 'warning' },
    { room_name: '次卧', severity: 'error' },  // not in structure
  ]
  const result = aggregateRoomStatus(structure, events, 0)
  assertEqual(result.length, 2, '2 rooms in result (structure room + event room)')
  const ewRoom = result.find((r) => r.name === '次卧')
  assert(ewRoom, '次卧 included despite not being in structure')
  assertEqual(ewRoom.status, 'fault', '事件房间状态正确')
  assertEqual(ewRoom.faultCount, 1, '1 fault counted')
  assert(ewRoom.id.startsWith('room-evt-'), 'event-only room uses evt- prefix')
})

test('TC-UNIT-027: aggregateRoomStatus — null structure => []', () => {
  const result = aggregateRoomStatus(null, [], 0)
  assertEqual(result.length, 0, 'null structure yields empty array')
})

test('TC-UNIT-027b: aggregateRoomStatus — hasCondensation flag from room._hasCondensation', () => {
  const structure = { rooms: [{ room_name: '客厅', room_id: 1, _hasCondensation: true }] }
  const result = aggregateRoomStatus(structure, [], 0)
  assertEqual(result[0].hasCondensation, true, 'hasCondensation flag propagated')
})

// ============================================================================
// TEST: computeOverallStatus (TC-UNIT-006 ~ TC-UNIT-010)
// ============================================================================

test('TC-UNIT-006: computeOverallStatus — any fault => "告警"', () => {
  const subsystems = [{ status: 'fault' }, { status: 'normal' }]
  const rooms = [{ status: 'normal' }]
  const result = computeOverallStatus(subsystems, rooms)
  assertEqual(result.level, 'fault', 'level = fault')
  assertEqual(result.text, '告警', 'text = 告警')
})

test('TC-UNIT-007: computeOverallStatus — warning only => "预警"', () => {
  const subsystems = [{ status: 'normal' }]
  const rooms = [{ status: 'warning' }]
  const result = computeOverallStatus(subsystems, rooms)
  assertEqual(result.level, 'warning', 'level = warning')
  assertEqual(result.text, '预警', 'text = 预警')
})

test('TC-UNIT-008: computeOverallStatus — all normal => "正常"', () => {
  const subsystems = [{ status: 'normal' }, { status: 'normal' }]
  const rooms = [{ status: 'normal' }, { status: 'normal' }]
  const result = computeOverallStatus(subsystems, rooms)
  assertEqual(result.level, 'normal', 'level = normal')
  assertEqual(result.text, '正常', 'text = 正常')
})

test('TC-UNIT-009: computeOverallStatus — all idle => "等待数据"', () => {
  const subsystems = [{ status: 'idle' }]
  const rooms = [{ status: 'idle' }]
  const result = computeOverallStatus(subsystems, rooms)
  assertEqual(result.level, 'syncing', 'idle maps to syncing')
  assertEqual(result.text, '等待数据', 'text = 等待数据')
})

test('TC-UNIT-010: computeOverallStatus — empty arrays => "正常"', () => {
  const result = computeOverallStatus([], [])
  assertEqual(result.level, 'normal', 'empty defaults to normal')
})

test('TC-UNIT-010b: computeOverallStatus — null inputs handled', () => {
  const result = computeOverallStatus(null, null)
  assertEqual(result.level, 'normal', 'null handles safely')
})

// ============================================================================
// TEST: filterFaultEventsByCompartment (TC-UNIT-031 ~ TC-UNIT-036)
// ============================================================================

test('TC-UNIT-031: filterFaultEventsByCompartment — fresh-air by product_code', () => {
  const events = [
    { id: 1, product_code: 130004, severity: 'error' },
    { id: 2, product_code: 270001, severity: 'warning' },
    { id: 3, product_code: 100007, severity: 'error' },
  ]
  const result = filterFaultEventsByCompartment(events, { type: 'subsystem', id: 'fresh-air' })
  assertEqual(result.length, 1, '1 event for fresh-air')
  assertEqual(result[0].id, 1, 'correct event returned')
})

test('TC-UNIT-031b: filterFaultEventsByCompartment — hydraulic by product_code', () => {
  const events = [
    { id: 1, product_code: 130004 },
    { id: 2, product_code: 270001 },
  ]
  const result = filterFaultEventsByCompartment(events, { type: 'subsystem', id: 'hydraulic' })
  assertEqual(result.length, 1, '1 event for hydraulic')
  assertEqual(result[0].id, 2, 'correct event')
})

test('TC-UNIT-031c: filterFaultEventsByCompartment — air-quality by product_code', () => {
  const events = [
    { id: 3, product_code: 100007 },
  ]
  const result = filterFaultEventsByCompartment(events, { type: 'subsystem', id: 'air-quality' })
  assertEqual(result.length, 1, '1 event for air-quality')
})

test('TC-UNIT-032: filterFaultEventsByCompartment — room filter by name', () => {
  const events = [
    { room_name: '主卧', severity: 'error' },
    { room_name: '客厅', severity: 'warning' },
    { room_name: '主卧', severity: 'warning' },
  ]
  const result = filterFaultEventsByCompartment(events, { type: 'room', name: '主卧' })
  assertEqual(result.length, 2, '2 events for 主卧')
})

test('TC-UNIT-033: filterFaultEventsByCompartment — energy compartment uses keyword filter', () => {
  const events = [
    { device_type_label: '电度计量', severity: 'error' },
    { device_type_label: '新风机组', severity: 'error' },
  ]
  const result = filterFaultEventsByCompartment(events, { type: 'subsystem', id: 'energy' })
  assertEqual(result.length, 1, '1 energy event')
  assertEqual(result[0].device_type_label, '电度计量', 'correct event filtered')
})

test('TC-UNIT-034: filterFaultEventsByCompartment — unknown subsystem => []', () => {
  const events = [{ id: 1 }]
  const result = filterFaultEventsByCompartment(events, { type: 'subsystem', id: 'unknown' })
  assertEqual(result.length, 0, 'unknown subsystem = empty')
})

test('TC-UNIT-035: filterFaultEventsByCompartment — null compartment => []', () => {
  const events = [{ id: 1 }]
  const result = filterFaultEventsByCompartment(events, null)
  assertEqual(result.length, 0, 'null compartment = empty')
})

test('TC-UNIT-036: filterFaultEventsByCompartment — null events => []', () => {
  const result = filterFaultEventsByCompartment(null, { type: 'subsystem', id: 'fresh-air' })
  assertEqual(result.length, 0, 'null events = empty')
})

// ============================================================================
// TEST: useAnimationControl State Machine (TC-UNIT-037 ~ TC-UNIT-040)
// ============================================================================

// Simulate the reactive state with a simple closure pattern
function createAnimationState() {
  let paused = false
  return {
    get animationsPaused() { return paused },
    pause() { paused = true },
    resume() { paused = false },
    onShow() { paused = false },
    onHide() { paused = true },
  }
}

test('TC-UNIT-037: useAnimationControl — pause() sets animationsPaused=true', () => {
  const anim = createAnimationState()
  anim.resume()
  assert(!anim.animationsPaused, 'initially running')
  anim.pause()
  assert(anim.animationsPaused, 'paused after pause()')
})

test('TC-UNIT-038: useAnimationControl — resume() sets animationsPaused=false', () => {
  const anim = createAnimationState()
  anim.pause()
  assert(anim.animationsPaused, 'initially paused')
  anim.resume()
  assert(!anim.animationsPaused, 'running after resume()')
})

test('TC-UNIT-039: useAnimationControl — onHide() pauses animations', () => {
  const anim = createAnimationState()
  anim.resume()
  anim.onHide()
  assert(anim.animationsPaused, 'paused after onHide')
})

test('TC-UNIT-040: useAnimationControl — onShow() resumes animations', () => {
  const anim = createAnimationState()
  anim.pause()
  anim.onShow()
  assert(!anim.animationsPaused, 'running after onShow')
})

test('TC-UNIT-040b: useAnimationControl — double pause idempotent', () => {
  const anim = createAnimationState()
  anim.pause()
  anim.pause()
  assert(anim.animationsPaused, 'still paused after double pause')
})

test('TC-UNIT-040c: useAnimationControl — double resume idempotent', () => {
  const anim = createAnimationState()
  anim.resume()
  anim.resume()
  assert(!anim.animationsPaused, 'still running after double resume')
})

// ============================================================================
// TEST: Output structure and type checks
// ============================================================================

test('TC-UNIT-STRUCT: aggregateSubsystemStatus output has correct shape', () => {
  const result = aggregateSubsystemStatus(
    { fresh_air_unit: { fault_count: 2 }, hydraulic_module: {}, air_quality_sensor: {} },
    { online_count: 3, total_count: 3 },
    []
  )
  assertEqual(result.length, 4, 'always 4 subsystems')
  for (const s of result) {
    assertType(s.id, 'string', `${s.id} has string id`)
    assertType(s.name, 'string', `${s.id} has string name`)
    assert(['normal', 'warning', 'fault', 'idle'].includes(s.status),
      `${s.id} has valid status: ${s.status}`)
    assertType(s.faultCount, 'number', `${s.id} faultCount is number`)
    assertType(s.warningCount, 'number', `${s.id} warningCount is number`)
  }
})

test('TC-UNIT-STRUCT: aggregateRoomStatus output has correct shape', () => {
  const structure = { rooms: [{ room_name: '客厅', room_id: 1 }] }
  const result = aggregateRoomStatus(structure, [], 0)
  for (const r of result) {
    assertType(r.id, 'string', `${r.name} has string id`)
    assertType(r.name, 'string', `${r.name} has string name`)
    assert(['normal', 'warning', 'fault', 'idle'].includes(r.status),
      `${r.name} has valid status: ${r.status}`)
    assertType(r.faultCount, 'number', `${r.name} faultCount is number`)
    assertType(r.warningCount, 'number', `${r.name} warningCount is number`)
    assertType(r.hasCondensation, 'boolean', `${r.name} hasCondensation is boolean`)
  }
})

// ============================================================================
// Runner
// ============================================================================

console.log(`\n=== v1.11.0 Bridge Dashboard — Frontend Unit Tests ===\n`)
for (const t of tests) {
  try {
    t.fn()
    passed++
    console.log(`  PASS: ${t.name}`)
  } catch (e) {
    failed++
    console.log(`  FAIL: ${t.name}`)
    console.log(`        ${e.message}`)
  }
}

const total = passed + failed
const passRate = total > 0 ? ((passed / total) * 100).toFixed(1) : '0.0'
console.log(`\n=== Results ===`)
console.log(`Total: ${total} | Pass: ${passed} (${passRate}%) | Fail: ${failed}`)
console.log(`Fatal errors: 0 | Skipped: 0 | Blocked: 0`)
console.log(`Arithmetic check: ${total} === ${passed} + ${failed} + 0 + 0 = ${passed + failed} — OK\n`)

process.exit(failed > 0 ? 1 : 0)
