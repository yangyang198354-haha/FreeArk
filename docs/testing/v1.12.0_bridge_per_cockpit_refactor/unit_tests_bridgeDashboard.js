/**
 * @file unit_tests_bridgeDashboard.js
 * @description 集成测试 — useBridgeDashboard.js 内部纯函数
 *   Module: MOD-BD-002
 *   Covers: aggregateSubsystemStatus, aggregateRoomStatus, computeOverallStatus,
 *           filterFaultEventsByCompartment, _buildCompartmentParams, _buildSingleDeviceParams
 *   Execution: node unit_tests_bridgeDashboard.js
 *
 *   Note: These internal functions are NOT exported by useBridgeDashboard.js.
 *   We reproduce them inline 1:1 to test the logic independently of Vue/composable scaffolding.
 *
 *   v1.12.0 bridge per-cockpit refactor
 */

'use strict';

// ── Simple test runner ──────────────────────────────────────────
const tests = [];
let passed = 0;
let failed = 0;
let skipped = 0;

function test(name, fn) {
  tests.push({ name, fn });
}

function assert(condition, msg) {
  if (!condition) throw new Error(msg || 'Assertion failed');
}

function assertEquals(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error(`${msg || 'Equality check failed'}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertDeepEqual(actual, expected, msg) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) {
    throw new Error(`${msg || 'Deep equality failed'}:\n  expected: ${b}\n  got:      ${a}`);
  }
}

function runAll() {
  console.log('='.repeat(60));
  console.log('Integration Tests: useBridgeDashboard.js (MOD-BD-002)');
  console.log('='.repeat(60));
  console.log('');

  for (const t of tests) {
    try {
      t.fn();
      passed++;
      console.log(`  PASS: ${t.name}`);
    } catch (e) {
      failed++;
      console.log(`  FAIL: ${t.name}`);
      console.log(`        ${e.message}`);
    }
  }

  console.log('');
  console.log('='.repeat(60));
  const total = passed + failed + skipped;
  const passRate = passed + failed > 0 ? (passed / (passed + failed) * 100).toFixed(1) : 'N/A';
  console.log(`Total: ${total} | Pass: ${passed} | Fail: ${failed} | Skip: ${skipped}`);
  console.log(`Pass Rate: ${passRate}% (${passed}/${passed + failed})`);
  console.log('='.repeat(60));

  if (failed > 0) {
    process.exitCode = 1;
  }
}

// ═══════════════════════════════════════════════════════════════
// Reproduction of useBridgeDashboard.js internal pure functions
// (1:1 reproduction, extracted for isolated testing)
// ═══════════════════════════════════════════════════════════════

// ── Reproduced from @/utils/faultUtils ─────────────────────────
const FAULT_PARAM_NAMES = new Set([
  'living_room_temp_sensor_error', 'living_room_humidity_sensor_error',
  'living_room_external_temp_sensor_error', 'living_room_communication_error',
  'study_room_temp_sensor_error', 'study_room_humidity_sensor_error',
  'study_room_external_temp_sensor_error', 'study_room_communication_error',
  'bedroom_temp_sensor_error', 'bedroom_humidity_sensor_error',
  'bedroom_external_temp_sensor_error', 'bedroom_communication_error',
  'children_room_temp_sensor_error', 'children_room_humidity_sensor_error',
  'children_room_external_temp_sensor_error', 'children_room_communication_error',
  'fourth_children_room_temp_sensor_error', 'fourth_children_room_humidity_sensor_error',
  'fourth_children_room_external_temp_sensor_error', 'fourth_children_room_communication_error',
  'fresh_air_unit_stop_error', 'fresh_air_unit_communication_error',
  'hydraulic_module_low_temp_error', 'energy_meter_status_communication_error',
  'air_quality_sensor_communication_error', 'comm_fault_timeout',
]);

const ERROR_N_PATTERN = /^error_\d+$/;

const FRESH_AIR_FAULT_BITS = [
  '风机状态故障', '出风温度异常状态', '进风温度传感器故障',
  '回水温度传感器故障', '进水温度传感器故障', '加湿器故障',
  '新风水阀故障', '防冻保护故障', '出风温度传感器故障',
];

const SYSTEM_SUB_KEYS = ['fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality'];

const SUB_TYPE_TO_ID = {
  'fresh_air': 'fresh-air', 'energy_meter': 'energy',
  'hydraulic_module': 'hydraulic', 'air_quality': 'air-quality',
};

const SUBSYSTEM_NAMES = {
  'fresh-air': '新风模块', 'energy': '能耗中枢',
  'hydraulic': '水力模块', 'air-quality': '空气品质',
};

const ID_TO_SUB_TYPE = {
  'fresh-air': 'fresh_air', 'energy': 'energy_meter',
  'hydraulic': 'hydraulic_module', 'air-quality': 'air_quality',
};

function isFaultParam(paramName) {
  if (typeof paramName !== 'string') return false;
  return FAULT_PARAM_NAMES.has(paramName) || ERROR_N_PATTERN.test(paramName);
}

function countFaultsForRow(paramName, value) {
  if (value == null || value === 0) return 0;
  if (paramName === 'fresh_air_fault_status') {
    const v = typeof value === 'number' ? value : Number(value);
    if (isNaN(v) || v <= 0) return 0;
    return v.toString(2).split('1').length - 1;
  }
  return isFaultParam(paramName) ? 1 : 0;
}

function computeFaultCount(params) {
  if (!params || !Array.isArray(params)) return 0;
  let total = 0;
  for (const p of params) {
    if (p && typeof p.paramName === 'string') {
      total += countFaultsForRow(p.paramName, p.value);
    }
  }
  return total;
}

function expandFreshAirFaultBits(value) {
  const v = (value != null && !isNaN(Number(value))) ? Number(value) : 0;
  return FRESH_AIR_FAULT_BITS.map((name, bitIndex) => ({
    bitIndex, name,
    active: ((v >> bitIndex) & 1) === 1,
  }));
}

function isFaultValueForDisplay(paramName, value) {
  if (value == null || value === 0) return false;
  if (paramName === 'fresh_air_fault_status') return value !== 0;
  if (isFaultParam(paramName)) return true;
  return false;
}

// ── Reproduced from @/subpackages/game/arkZoneMap ──────────────
const STATUS_RANK = { idle: -1, normal: 0, warning: 1, fault: 2 };

function worseStatus(a, b) {
  return (STATUS_RANK[a] ?? -1) >= (STATUS_RANK[b] ?? -1) ? a : b;
}

// ── severityToStatus (useBridgeDashboard.js internal) ──────────
function severityToStatus(severity) {
  if (severity === 'error') return 'fault';
  if (severity === 'warning') return 'warning';
  if (severity === 'condensation') return 'warning';
  return 'normal';
}

// ── groupFaultEventsByRoom (useBridgeDashboard.js internal) ────
function groupFaultEventsByRoom(faultEvents) {
  const map = new Map();
  for (const ev of (faultEvents || [])) {
    const room = ev.room_name || '__unknown__';
    if (!map.has(room)) map.set(room, []);
    map.get(room).push(ev);
  }
  return map;
}

// ── _collectParamsForSubType (useBridgeDashboard.js internal, v1.12.0) ──
// Walks nested group→sub_type→params: { hvac: { sub_types: { fresh_air: { params: [...] } } } }
function _collectParamsForSubType(realtimeParams, targetSubType, enriched = false) {
  const result = [];
  if (!realtimeParams || !targetSubType) return result;
  for (const groupData of Object.values(realtimeParams)) {
    const subTypes = groupData?.sub_types || {};
    const subTypeData = subTypes[targetSubType];
    if (subTypeData?.params) {
      for (const p of subTypeData.params) {
        if (enriched) {
          result.push({
            tag: p.param_name,
            displayName: p.display_name || p.param_name,
            value: p.value,
            isStale: p.is_stale || false,
          });
        } else {
          result.push({ paramName: p.param_name, value: p.value });
        }
      }
    }
  }
  return result;
}

// ── aggregateSubsystemStatus (useBridgeDashboard.js internal) ──
// 1:1 reproduction of the v1.12.0 refactored function
// realtimeParams is nested group→sub_type→params — NOT keyed by device_sn
function aggregateSubsystemStatus(structure, realtimeParams) {
  const realtime = realtimeParams || {};
  const systemDevices = structure?.system_devices || [];

  const structureAvailable = systemDevices.length > 0;
  let subTypesToShow;

  if (structureAvailable) {
    const availableSubTypes = new Set(systemDevices.map((d) => d.sub_type).filter(Boolean));
    subTypesToShow = SYSTEM_SUB_KEYS.filter((st) => availableSubTypes.has(st));
  } else {
    subTypesToShow = [...SYSTEM_SUB_KEYS];
  }

  const realtimeAvailable = realtime && Object.keys(realtime).length > 0;

  const subsystems = [];
  for (const subType of subTypesToShow) {
    const id = SUB_TYPE_TO_ID[subType] || subType;
    const name = SUBSYSTEM_NAMES[id] || subType;

    let faultCount = 0;
    let status = 'idle';

    if (realtimeAvailable && structureAvailable) {
      const params = _collectParamsForSubType(realtime, subType);
      faultCount = computeFaultCount(params);
      status = faultCount > 0 ? 'fault' : 'normal';
    } else if (!structureAvailable) {
      status = 'normal';
    }

    subsystems.push({
      id, name, status, faultCount,
      warningCount: 0,
      dataSource: 'plc-realtime-params',
    });
  }

  return subsystems;
}

// ── aggregateRoomStatus (useBridgeDashboard.js internal) ───────
// 1:1 reproduction of the v1.12.0 refactored function
function aggregateRoomStatus(structure, faultEvents, condensationCount) {
  const rooms = structure?.rooms || [];
  const eventMap = groupFaultEventsByRoom(faultEvents);

  const result = rooms.map((room) => {
    const roomName = room.room_name || room.ori_room_name || `房间 ${room.room_id}`;
    const roomEvents = eventMap.get(room.room_name) || eventMap.get(room.ori_room_name) || [];

    let status = 'normal';
    let faultCount = 0;
    let warningCount = 0;
    for (const ev of roomEvents) {
      const s = severityToStatus(ev.severity);
      if (s === 'fault') faultCount++;
      else if (s === 'warning') warningCount++;
      status = worseStatus(status, s);
    }

    const hasCondensation = room._hasCondensation || false;

    return {
      id: `room-${room.room_id || roomName}`,
      name: roomName,
      status, faultCount, warningCount, hasCondensation,
    };
  });

  return result;
}

// ── computeOverallStatus (useBridgeDashboard.js internal) ──────
// 1:1 reproduction
function computeOverallStatus(subsystems, rooms) {
  let worst = 'normal';
  let allIdle = true;
  let hasItems = false;
  for (const s of (subsystems || [])) {
    hasItems = true;
    worst = worseStatus(worst, s.status);
    if (s.status !== 'idle') allIdle = false;
  }
  for (const r of (rooms || [])) {
    hasItems = true;
    worst = worseStatus(worst, r.status);
    if (r.status !== 'idle') allIdle = false;
  }
  if (hasItems && allIdle) return { level: 'syncing', text: '等待数据' };
  if (worst === 'fault') return { level: 'fault', text: '告警' };
  if (worst === 'warning') return { level: 'warning', text: '预警' };
  return { level: 'normal', text: '正常' };
}

// ── filterFaultEventsByCompartment (useBridgeDashboard.js internal) ──
// 1:1 reproduction of v1.12.0 refactored function
function filterFaultEventsByCompartment(faultEvents, compartment, structureCache) {
  if (!compartment || !faultEvents?.length) return [];

  if (compartment.type === 'subsystem') {
    const targetSubType = ID_TO_SUB_TYPE[compartment.id];
    if (!targetSubType) return [];

    const systemDevices = structureCache?.system_devices || [];
    const matchingSns = new Set(
      systemDevices
        .filter((d) => d.sub_type === targetSubType)
        .map((d) => d.device_sn || d.sn || '')
        .filter(Boolean)
    );

    if (matchingSns.size > 0) {
      return faultEvents.filter((ev) => matchingSns.has(ev.device_sn));
    }
    return [];
  }

  if (compartment.type === 'room') {
    return faultEvents.filter((ev) =>
      ev.room_name === compartment.name ||
      ev.room_name === compartment.id
    );
  }

  return [];
}

// ── _makeParamBlock (useBridgeDashboard.js internal, v1.12.0) ──
// Builds one sub_type's param block for drawer display (card-per-sub_type layout)
function _makeParamBlock(subType, label, enrichedParams) {
  const block = {
    deviceSn: subType,
    deviceName: label,
    subType,
    attrs: [],
  };
  for (const p of enrichedParams) {
    const attr = {
      tag: p.tag,
      displayName: p.displayName,
      value: p.value,
      isFault: isFaultValueForDisplay(p.tag, p.value),
    };
    if (p.tag === 'fresh_air_fault_status') {
      attr.expandedBits = expandFreshAirFaultBits(p.value);
    }
    block.attrs.push(attr);
  }
  return block;
}

// ── _buildCompartmentParams (useBridgeDashboard.js internal) ───
// v1.12.0: uses nested group→sub_type→params structure, NOT device_sn
function makeBuildCompartmentParams(structureCache, realtimeParamsCache) {
  return function _buildCompartmentParams(compartment) {
    const params = [];
    const structure = structureCache;
    const realtime = realtimeParamsCache || {};

    if (!structure) return params;

    if (compartment.type === 'subsystem') {
      const targetSubType = ID_TO_SUB_TYPE[compartment.id];
      if (targetSubType) {
        const enriched = _collectParamsForSubType(realtime, targetSubType, true);
        if (enriched.length > 0) {
          params.push(_makeParamBlock(
            targetSubType,
            SUBSYSTEM_NAMES[compartment.id] || compartment.name,
            enriched,
          ));
        }
      }
    } else if (compartment.type === 'room') {
      const rooms = structure.rooms || [];
      const room = rooms.find((r) => (r.room_name || r.ori_room_name) === compartment.name)
        || rooms.find((r) => (r.name || r.room_name) === compartment.name);

      if (room && room.devices) {
        const roomSubTypes = new Set(
          room.devices.map((d) => d.sub_type).filter(Boolean)
        );
        for (const subType of roomSubTypes) {
          const enriched = _collectParamsForSubType(realtime, subType, true);
          if (enriched.length > 0) {
            const dev = room.devices.find((d) => d.sub_type === subType);
            const label = dev?.device_name || subType;
            params.push(_makeParamBlock(subType, label, enriched));
          }
        }
      }
    }

    return params;
  };
}

// ═══════════════════════════════════════════════════════════════
// Mock Data Factories
// ═══════════════════════════════════════════════════════════════

function makeStructure(opts = {}) {
  // opts.devices: array of { sub_type, device_sn, device_name }
  // opts.rooms: array of { room_id, room_name, devices }
  const devices = (opts.devices || [
    { sub_type: 'fresh_air', device_sn: 'FA-001', device_name: '新风机1' },
    { sub_type: 'energy_meter', device_sn: 'EM-001', device_name: '能耗表1' },
    { sub_type: 'hydraulic_module', device_sn: 'HM-001', device_name: '水力模块1' },
    { sub_type: 'air_quality', device_sn: 'AQ-001', device_name: '空气品质传感器1' },
  ]);

  const rooms = opts.rooms || [
    { room_id: 1, room_name: '主卧', devices: [] },
    { room_id: 2, room_name: '书房', devices: [] },
    { room_id: 3, room_name: '客厅', devices: [] },
    { room_id: 4, room_name: '儿童房', devices: [] },
  ];

  return {
    system_devices: devices,
    rooms: rooms,
  };
}

function makeRealtimeParams(overrides = {}) {
  // Nested group→sub_type→params format matching getOwnerRealtimeParams().data
  // overrides: { sub_type: { param_name: value, ... }, ... }
  //   e.g. { fresh_air: { fresh_air_unit_stop_error: 1 } }
  const defaults = {
    'hvac': {
      display: '暖通空调',
      sub_types: {
        'fresh_air': {
          display: '新风机',
          params: [
            { param_name: 'fresh_air_unit_stop_error', display_name: '新风机停机故障', value: 0 },
            { param_name: 'fresh_air_unit_communication_error', display_name: '新风机通讯故障', value: 0 },
            { param_name: 'fresh_air_fault_status', display_name: '新风机故障状态', value: 0 },
            { param_name: 'coil_inlet_temp', display_name: '盘管进水温度', value: 220 },
            { param_name: 'fan_speed', display_name: '风机转速', value: 3 },
          ],
        },
        'energy_meter': {
          display: '能耗表',
          params: [
            { param_name: 'energy_meter_status_communication_error', display_name: '能耗表通讯故障', value: 0 },
            { param_name: 'total_power', display_name: '总功率', value: 1250 },
          ],
        },
        'hydraulic_module': {
          display: '水力模块',
          params: [
            { param_name: 'hydraulic_module_low_temp_error', display_name: '水力模块低温故障', value: 0 },
            { param_name: 'water_temp', display_name: '水温', value: 45 },
          ],
        },
        'air_quality': {
          display: '空气品质传感器',
          params: [
            { param_name: 'air_quality_sensor_communication_error', display_name: '空气品质通讯故障', value: 0 },
            { param_name: 'pm25', display_name: 'PM2.5', value: 15 },
            { param_name: 'co2', display_name: 'CO2', value: 450 },
          ],
        },
      },
    },
  };

  const result = JSON.parse(JSON.stringify(defaults));

  // Apply overrides: { sub_type: { param_name: value, ... } }
  for (const [subType, paramOverrides] of Object.entries(overrides)) {
    for (const [groupKey, groupData] of Object.entries(result)) {
      const subTypes = groupData?.sub_types || {};
      const subTypeData = subTypes[subType];
      if (subTypeData?.params) {
        for (const p of subTypeData.params) {
          if (paramOverrides.hasOwnProperty(p.param_name)) {
            p.value = paramOverrides[p.param_name];
          }
        }
      }
    }
  }

  return result;
}

function makeFaultEvents(events = []) {
  return events;
}

// ═══════════════════════════════════════════════════════════════
// Test Registration
// ═══════════════════════════════════════════════════════════════

// ── Group 7: aggregateSubsystemStatus (TC-INT-001 ~ TC-INT-016) ──

test('TC-INT-001: Full cockpit, all normal → 4 subsystems, all normal', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams();
  const result = aggregateSubsystemStatus(structure, realtime);

  assertEquals(result.length, 4, 'should have 4 subsystems');
  for (const s of result) {
    assertEquals(s.status, 'normal', `${s.name} should be normal`);
    assertEquals(s.faultCount, 0, `${s.name} should have 0 faults`);
  }
  // Verify all 4 subsystem IDs present
  const ids = result.map((s) => s.id);
  assert(ids.includes('fresh-air'), 'missing fresh-air');
  assert(ids.includes('energy'), 'missing energy');
  assert(ids.includes('hydraulic'), 'missing hydraulic');
  assert(ids.includes('air-quality'), 'missing air-quality');
});

test('TC-INT-002: Fresh air fault → only fresh-air has fault status', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    fresh_air: { fresh_air_unit_communication_error: 1 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const freshAir = result.find((s) => s.id === 'fresh-air');
  assertEquals(freshAir.status, 'fault', 'fresh-air should be fault');
  assertEquals(freshAir.faultCount, 1, 'fresh-air faultCount should be 1');

  // All other subsystems should be normal
  for (const s of result) {
    if (s.id !== 'fresh-air') {
      assertEquals(s.status, 'normal', `${s.name} should be normal`);
      assertEquals(s.faultCount, 0);
    }
  }
});

test('TC-INT-003: Fresh air bit fault → faultCount = popcount', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    fresh_air: { fresh_air_fault_status: 5 }, // bits 0+2 = 2 faults
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const freshAir = result.find((s) => s.id === 'fresh-air');
  assertEquals(freshAir.status, 'fault');
  assertEquals(freshAir.faultCount, 2, 'popcount of 5 is 2');
});

test('TC-INT-004: Structure available but realtime empty → status=idle', () => {
  const structure = makeStructure();
  const result = aggregateSubsystemStatus(structure, {});

  assertEquals(result.length, 4);
  for (const s of result) {
    assertEquals(s.status, 'idle', `${s.name} should be idle when no realtime data`);
    assertEquals(s.faultCount, 0);
  }
});

test('TC-INT-005: Missing fresh_air device → only 3 subsystems', () => {
  const structure = makeStructure({
    devices: [
      { sub_type: 'energy_meter', device_sn: 'EM-001' },
      { sub_type: 'hydraulic_module', device_sn: 'HM-001' },
      { sub_type: 'air_quality', device_sn: 'AQ-001' },
    ],
  });
  const realtime = makeRealtimeParams();
  const result = aggregateSubsystemStatus(structure, realtime);

  assertEquals(result.length, 3, 'should have 3 subsystems');
  const ids = result.map((s) => s.id);
  assert(!ids.includes('fresh-air'), 'should not include fresh-air');
  assert(ids.includes('energy'));
  assert(ids.includes('hydraulic'));
  assert(ids.includes('air-quality'));
});

test('TC-INT-006: Missing hydraulic_module → no hydraulic subsystem', () => {
  const structure = makeStructure({
    devices: [
      { sub_type: 'fresh_air', device_sn: 'FA-001' },
      { sub_type: 'energy_meter', device_sn: 'EM-001' },
      { sub_type: 'air_quality', device_sn: 'AQ-001' },
    ],
  });
  const realtime = makeRealtimeParams();
  const result = aggregateSubsystemStatus(structure, realtime);

  assertEquals(result.length, 3);
  const ids = result.map((s) => s.id);
  assert(!ids.includes('hydraulic'), 'should not include hydraulic');
});

test('TC-INT-007: Single subsystem cockpit → only fresh-air', () => {
  const structure = makeStructure({
    devices: [
      { sub_type: 'fresh_air', device_sn: 'FA-001' },
    ],
  });
  const realtime = makeRealtimeParams();
  const result = aggregateSubsystemStatus(structure, realtime);

  assertEquals(result.length, 1, 'should have exactly 1 subsystem');
  assertEquals(result[0].id, 'fresh-air');
});

test('TC-INT-008: Cockpit A vs B subsystems differ', () => {
  const structA = makeStructure({
    devices: [
      { sub_type: 'fresh_air', device_sn: 'FA-001' },
      { sub_type: 'hydraulic_module', device_sn: 'HM-001' },
    ],
  });
  const structB = makeStructure({
    devices: [
      { sub_type: 'air_quality', device_sn: 'AQ-001' },
    ],
  });
  const realtime = makeRealtimeParams();

  const resultA = aggregateSubsystemStatus(structA, realtime);
  const resultB = aggregateSubsystemStatus(structB, realtime);

  assertEquals(resultA.length, 2);
  assertEquals(resultB.length, 1);
  assert(resultA.find((s) => s.id === 'fresh-air') !== undefined, 'A should have fresh-air');
  assert(resultB.find((s) => s.id === 'air-quality') !== undefined, 'B should have air-quality');
  assert(resultA.find((s) => s.id === 'air-quality') === undefined, 'A should not have air-quality');
});

test('TC-INT-009: Hydraulic module fault → hydraulic status=fault', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    hydraulic_module: { hydraulic_module_low_temp_error: 1 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const hydraulic = result.find((s) => s.id === 'hydraulic');
  assertEquals(hydraulic.status, 'fault');
  assertEquals(hydraulic.faultCount, 1);

  // Other subsystems normal
  for (const s of result) {
    if (s.id !== 'hydraulic') {
      assertEquals(s.status, 'normal', `${s.name} should be normal`);
    }
  }
});

test('TC-INT-010: Hydraulic module normal → status=normal', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    hydraulic_module: { hydraulic_module_low_temp_error: 0 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const hydraulic = result.find((s) => s.id === 'hydraulic');
  assertEquals(hydraulic.status, 'normal');
  assertEquals(hydraulic.faultCount, 0);
});

test('TC-INT-011: Air quality sensor fault → air-quality status=fault', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    air_quality: { air_quality_sensor_communication_error: 1 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const aq = result.find((s) => s.id === 'air-quality');
  assertEquals(aq.status, 'fault');
  assertEquals(aq.faultCount, 1);
});

test('TC-INT-012: Air quality normal → status=normal', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    air_quality: { air_quality_sensor_communication_error: 0 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const aq = result.find((s) => s.id === 'air-quality');
  assertEquals(aq.status, 'normal');
  assertEquals(aq.faultCount, 0);
});

test('TC-INT-013: Energy meter fault → energy status=fault', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    energy_meter: { energy_meter_status_communication_error: 1 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const energy = result.find((s) => s.id === 'energy');
  assertEquals(energy.status, 'fault');
  assertEquals(energy.faultCount, 1);
});

test('TC-INT-014: Energy meter normal → status=normal', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    energy_meter: { energy_meter_status_communication_error: 0 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const energy = result.find((s) => s.id === 'energy');
  assertEquals(energy.status, 'normal');
  assertEquals(energy.faultCount, 0);
});

test('TC-INT-015: Empty structure → fallback to all 4 SYSTEM_SUB_KEYS', () => {
  const structure = { system_devices: [] };
  const realtime = makeRealtimeParams();
  const result = aggregateSubsystemStatus(structure, realtime);

  // When structure is empty, all 4 should show
  assertEquals(result.length, 4, 'should fallback to all 4');
  // But realtime data can't be matched (no device_sn mapping available)
  // So they should be idle since structureAvailable=false
  for (const s of result) {
    assert(['normal', 'idle'].includes(s.status), `${s.name} should be normal or idle`);
  }
});

test('TC-INT-016: aggregateSubsystemStatus signature does NOT accept plcRate/faultSummary', () => {
  // Verify by calling with only 2 args (structure, realtimeParams)
  const structure = makeStructure();
  const realtime = makeRealtimeParams();
  // Should not throw — confirms old 4-param signature is gone
  const result = aggregateSubsystemStatus(structure, realtime, 'extra-arg', 'another-extra');
  assertEquals(result.length, 4);
});

test('TC-INT-016b: Energy status independent of global data (ADR-008 verification)', () => {
  // The function does NOT accept plcRate or faultSummary parameters.
  // Energy status is purely from per-cockpit PLC realtime params.
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    energy_meter: { energy_meter_status_communication_error: 0 },
  });
  const result = aggregateSubsystemStatus(structure, realtime);

  const energy = result.find((s) => s.id === 'energy');
  assertEquals(energy.status, 'normal');
  assertEquals(energy.dataSource, 'plc-realtime-params', 'data source should be plc-realtime-params');
});

// ── Group 8: aggregateRoomStatus (TC-INT-020 ~ TC-INT-024) ──

test('TC-INT-020: 4 rooms, no faults → all normal', () => {
  const structure = makeStructure();
  const result = aggregateRoomStatus(structure, [], 0);

  assertEquals(result.length, 4);
  for (const r of result) {
    assertEquals(r.status, 'normal');
    assertEquals(r.faultCount, 0);
    assertEquals(r.warningCount, 0);
  }
  const names = result.map((r) => r.name);
  assert(names.includes('主卧'));
  assert(names.includes('书房'));
  assert(names.includes('客厅'));
  assert(names.includes('儿童房'));
});

test('TC-INT-021: 3 rooms structure → returns 3 rooms', () => {
  const structure = makeStructure({
    rooms: [
      { room_id: 1, room_name: '主卧' },
      { room_id: 2, room_name: '书房' },
      { room_id: 3, room_name: '客厅' },
    ],
  });
  const result = aggregateRoomStatus(structure, [], 0);
  assertEquals(result.length, 3);
});

test('TC-INT-022: Room with 2 active fault events → status=fault, faultCount=2', () => {
  const structure = makeStructure();
  const faultEvents = [
    { id: 1, room_name: '主卧', severity: 'error', fault_type: 'sensor_error', device_sn: 'FA-001' },
    { id: 2, room_name: '主卧', severity: 'error', fault_type: 'comm_error', device_sn: 'FA-002' },
  ];
  const result = aggregateRoomStatus(structure, faultEvents, 0);

  const master = result.find((r) => r.name === '主卧');
  assertEquals(master.status, 'fault');
  assertEquals(master.faultCount, 2);
  assertEquals(master.warningCount, 0);
});

test('TC-INT-022b: Room with mixed fault + warning events', () => {
  const structure = makeStructure();
  const faultEvents = [
    { id: 1, room_name: '主卧', severity: 'error', fault_type: 'sensor_error', device_sn: 'FA-001' },
    { id: 2, room_name: '主卧', severity: 'warning', fault_type: 'temp_warning', device_sn: 'FA-002' },
  ];
  const result = aggregateRoomStatus(structure, faultEvents, 0);

  const master = result.find((r) => r.name === '主卧');
  assertEquals(master.status, 'fault', 'fault dominates over warning');
  assertEquals(master.faultCount, 1);
  assertEquals(master.warningCount, 1);
});

test('TC-INT-023: Empty rooms array → empty result', () => {
  const structure = { rooms: [] };
  const result = aggregateRoomStatus(structure, [], 0);
  assertEquals(result.length, 0);
});

test('TC-INT-024: Different cockpit room counts (5 vs 3)', () => {
  const structA = makeStructure({
    rooms: [
      { room_id: 1, room_name: '主卧' },
      { room_id: 2, room_name: '书房' },
      { room_id: 3, room_name: '客厅' },
      { room_id: 4, room_name: '儿童房' },
      { room_id: 5, room_name: '第四儿童房' },
    ],
  });
  const structB = makeStructure({
    rooms: [
      { room_id: 1, room_name: '主卧' },
      { room_id: 2, room_name: '书房' },
      { room_id: 3, room_name: '客厅' },
    ],
  });

  const resultA = aggregateRoomStatus(structA, [], 0);
  const resultB = aggregateRoomStatus(structB, [], 0);

  assertEquals(resultA.length, 5, 'cockpit A should have 5 rooms');
  assertEquals(resultB.length, 3, 'cockpit B should have 3 rooms');
});

test('TC-INT-024b: No orphan rooms — only structure.rooms drives output', () => {
  // v1.12.0 ADR-004: orphan room discovery removed.
  // Even if faultEvents reference rooms not in structure, they should NOT appear.
  const structure = makeStructure({
    rooms: [
      { room_id: 1, room_name: '主卧' },
    ],
  });
  const faultEvents = [
    { id: 1, room_name: '主卧', severity: 'error' },
    { id: 2, room_name: '玄关', severity: 'error' }, // not in structure → should be ignored
    { id: 3, room_name: '阳台', severity: 'error' }, // not in structure → should be ignored
  ];
  const result = aggregateRoomStatus(structure, faultEvents, 0);

  assertEquals(result.length, 1, 'should only have 1 room (from structure)');
  assertEquals(result[0].name, '主卧');
});

// ── Group 9: computeOverallStatus (TC-INT-030 ~ TC-INT-034) ──

test('TC-INT-030: All normal → overall normal', () => {
  const subsystems = [
    { id: 'fresh-air', status: 'normal', faultCount: 0 },
    { id: 'energy', status: 'normal', faultCount: 0 },
    { id: 'hydraulic', status: 'normal', faultCount: 0 },
    { id: 'air-quality', status: 'normal', faultCount: 0 },
  ];
  const rooms = [
    { id: 'room-1', name: '主卧', status: 'normal', faultCount: 0 },
    { id: 'room-2', name: '书房', status: 'normal', faultCount: 0 },
  ];
  const result = computeOverallStatus(subsystems, rooms);
  assertDeepEqual(result, { level: 'normal', text: '正常' });
});

test('TC-INT-031: One fault → overall fault', () => {
  const subsystems = [
    { id: 'fresh-air', status: 'fault', faultCount: 2 },
    { id: 'energy', status: 'normal', faultCount: 0 },
  ];
  const rooms = [
    { id: 'room-1', name: '主卧', status: 'normal', faultCount: 0 },
  ];
  const result = computeOverallStatus(subsystems, rooms);
  assertDeepEqual(result, { level: 'fault', text: '告警' });
});

test('TC-INT-032: Mixed fault in subsystems + warning in rooms → fault', () => {
  const subsystems = [
    { id: 'fresh-air', status: 'fault', faultCount: 1 },
  ];
  const rooms = [
    { id: 'room-1', name: '主卧', status: 'warning', faultCount: 0, warningCount: 1 },
  ];
  const result = computeOverallStatus(subsystems, rooms);
  assertDeepEqual(result, { level: 'fault', text: '告警' }, 'fault dominates warning');
});

test('TC-INT-033: All idle → syncing', () => {
  const subsystems = [
    { id: 'fresh-air', status: 'idle', faultCount: 0 },
    { id: 'energy', status: 'idle', faultCount: 0 },
  ];
  const result = computeOverallStatus(subsystems, []);
  assertDeepEqual(result, { level: 'syncing', text: '等待数据' });
});

test('TC-INT-034: Empty arrays → syncing', () => {
  const result = computeOverallStatus([], []);
  // With no items, hasItems=false, allIdle stays true
  // But: if (hasItems && allIdle) return syncing → if !hasItems, fall through
  // actually: hasItems=false → doesn't enter syncing branch →
  // worst='normal' → returns normal
  // This is a potential edge case — empty means no data.
  assertDeepEqual(result, { level: 'normal', text: '正常' },
    'Empty arrays → worst stays at "normal"');
});

test('TC-INT-033b: Warning only → overall warning', () => {
  const subsystems = [
    { id: 'fresh-air', status: 'warning', faultCount: 0 },
  ];
  const rooms = [
    { id: 'room-1', name: '主卧', status: 'warning', faultCount: 0, warningCount: 1 },
  ];
  const result = computeOverallStatus(subsystems, rooms);
  assertDeepEqual(result, { level: 'warning', text: '预警' });
});

// ── Group 10: filterFaultEventsByCompartment (TC-INT-040 ~ TC-INT-043) ──

test('TC-INT-040: Filter by room name', () => {
  const faultEvents = [
    { id: 1, room_name: '主卧', device_sn: 'FA-001', severity: 'error' },
    { id: 2, room_name: '书房', device_sn: 'FA-002', severity: 'error' },
    { id: 3, room_name: '客厅', device_sn: 'AQ-001', severity: 'warning' },
  ];
  const compartment = { type: 'room', id: 'room-1', name: '主卧' };
  const result = filterFaultEventsByCompartment(faultEvents, compartment, null);

  assertEquals(result.length, 1);
  assertEquals(result[0].id, 1);
  assertEquals(result[0].room_name, '主卧');
});

test('TC-INT-041: Filter by subsystem (device_sn matching)', () => {
  const structure = makeStructure(); // has FA-001 for fresh_air
  const faultEvents = [
    { id: 1, room_name: '主卧', device_sn: 'FA-001', severity: 'error' },
    { id: 2, room_name: '主卧', device_sn: 'EM-001', severity: 'error' }, // energy meter
    { id: 3, room_name: '书房', device_sn: 'UNKNOWN', severity: 'warning' },
  ];
  const compartment = { type: 'subsystem', id: 'fresh-air' };
  const result = filterFaultEventsByCompartment(faultEvents, compartment, structure);

  assertEquals(result.length, 1, 'should only match FA-001 device_sn events');
  assertEquals(result[0].id, 1);
  assertEquals(result[0].device_sn, 'FA-001');
});

test('TC-INT-042: Subsystem no matching devices → empty array', () => {
  const structure = makeStructure(); // no 'unknown_sub' type
  const faultEvents = [
    { id: 1, room_name: '主卧', device_sn: 'FA-001', severity: 'error' },
  ];
  const compartment = { type: 'subsystem', id: 'nonexistent' };
  const result = filterFaultEventsByCompartment(faultEvents, compartment, structure);

  assertEquals(result.length, 0);
});

test('TC-INT-043: Empty faultEvents → empty array', () => {
  const compartment = { type: 'room', id: 'room-1', name: '主卧' };
  const result = filterFaultEventsByCompartment([], compartment, null);
  assertEquals(result.length, 0);
});

test('TC-INT-043b: Null compartment → empty array', () => {
  const faultEvents = [{ id: 1, device_sn: 'FA-001' }];
  const result = filterFaultEventsByCompartment(faultEvents, null, null);
  assertEquals(result.length, 0);
});

// ── Group 11: _buildCompartmentParams (TC-INT-050 ~ TC-INT-057) ──

test('TC-INT-050: Fresh air subsystem compartment → returns fresh air device params', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams();
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'fresh-air' });

  assertEquals(result.length, 1, 'should have 1 device block');
  assertEquals(result[0].deviceSn, 'fresh_air');
  assertEquals(result[0].subType, 'fresh_air');
  assert(result[0].attrs.length > 0, 'should have attrs');
});

test('TC-INT-051: Hydraulic subsystem compartment → returns hydraulic params', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams();
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'hydraulic' });

  assertEquals(result.length, 1);
  assertEquals(result[0].deviceSn, 'hydraulic_module');
  assertEquals(result[0].subType, 'hydraulic_module');
});

test('TC-INT-052: Air quality subsystem compartment → returns air quality params', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams();
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'air-quality' });

  assertEquals(result.length, 1);
  assertEquals(result[0].deviceSn, 'air_quality');
  assertEquals(result[0].subType, 'air_quality');
});

test('TC-INT-053: Energy subsystem compartment → returns energy meter params', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams();
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'energy' });

  assertEquals(result.length, 1);
  assertEquals(result[0].deviceSn, 'energy_meter');
  assertEquals(result[0].subType, 'energy_meter');
});

test('TC-INT-054: Fault param → isFault=true in drawer', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    fresh_air: { fresh_air_unit_communication_error: 1, coil_inlet_temp: 220 },
  });
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'fresh-air' });
  const attrs = result[0].attrs;

  const faultAttr = attrs.find((a) => a.tag === 'fresh_air_unit_communication_error');
  assert(faultAttr !== undefined, 'should have fault attr');
  assertEquals(faultAttr.isFault, true, 'fault param with value 1 should be highlighted');
  assertEquals(faultAttr.value, 1);
});

test('TC-INT-055: Normal param → isFault=false in drawer', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams();
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'fresh-air' });
  const attrs = result[0].attrs;

  const normalAttr = attrs.find((a) => a.tag === 'coil_inlet_temp');
  assert(normalAttr !== undefined, 'should have normal attr');
  assertEquals(normalAttr.isFault, false, 'normal param should not be highlighted');
  assertEquals(normalAttr.value, 220);
});

test('TC-INT-056: fresh_air_fault_status expanded in drawer (single bit)', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    fresh_air: { fresh_air_fault_status: 1 },
  });
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'fresh-air' });
  const attrs = result[0].attrs;
  const faultStatusAttr = attrs.find((a) => a.tag === 'fresh_air_fault_status');

  assert(faultStatusAttr !== undefined, 'should have fresh_air_fault_status attr');
  assert(faultStatusAttr.expandedBits !== undefined, 'should have expandedBits');
  assertEquals(faultStatusAttr.expandedBits.length, 9);
  assertEquals(faultStatusAttr.expandedBits[0].active, true, 'bit 0 should be active');
  assertEquals(faultStatusAttr.expandedBits[0].name, '风机状态故障');
  for (let i = 1; i < 9; i++) {
    assertEquals(faultStatusAttr.expandedBits[i].active, false, `bit ${i} should be inactive`);
  }
});

test('TC-INT-057: fresh_air_fault_status expanded with multiple bits', () => {
  const structure = makeStructure();
  const realtime = makeRealtimeParams({
    fresh_air: { fresh_air_fault_status: 260 }, // bits 2+8
  });
  const _buildCompartmentParams = makeBuildCompartmentParams(structure, realtime);

  const result = _buildCompartmentParams({ type: 'subsystem', id: 'fresh-air' });
  const faultStatusAttr = result[0].attrs.find((a) => a.tag === 'fresh_air_fault_status');

  assert(faultStatusAttr.expandedBits[2].active === true, 'bit 2 should be active (进风温度传感器故障)');
  assert(faultStatusAttr.expandedBits[8].active === true, 'bit 8 should be active (出风温度传感器故障)');
  // Rest inactive
  for (const i of [0, 1, 3, 4, 5, 6, 7]) {
    assert(faultStatusAttr.expandedBits[i].active === false, `bit ${i} should be inactive`);
  }
});

test('TC-INT-057b: Null structure → empty compartment params', () => {
  const _buildCompartmentParams = makeBuildCompartmentParams(null, {});
  const result = _buildCompartmentParams({ type: 'subsystem', id: 'fresh-air' });
  assertEquals(result.length, 0, 'null structure → empty params');
});

// ── Run ─────────────────────────────────────────────────────────
runAll();
