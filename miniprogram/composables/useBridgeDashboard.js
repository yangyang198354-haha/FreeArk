/**
 * @module MOD-BD-002
 * @implements IFC-BD-002-01 through IFC-BD-002-22
 * @depends api.js, ownerStore, authStore, PagePoller, arkZoneMap (worseStatus, STATUS_RANK)
 * @author sub_agent_software_developer
 * @description Bridge dashboard composable — data fetching, status aggregation,
 *   polling lifecycle, cockpit switching, compartment open/close.
 *
 *   Data flow:
 *     start() → fetchAll() → aggregateStatus() → reactive state
 *     poller (30s) → refresh() → fetchAll() → aggregateStatus()
 *     switchCockpit(sp) → fetchAll(sp) → aggregateStatus()
 */

import { reactive, computed } from 'vue'
import { api } from '@/utils/api'
import { useOwnerStore } from '@/store/owner'
import { PagePoller } from '@/utils/poller'
import { worseStatus, STATUS_RANK } from '@/subpackages/game/arkZoneMap'

// ── Constants ──────────────────────────────────────────────────

const POLL_INTERVAL_MS = 30000

// Energy-related keywords for filtering fault events (ADR-BD-06)
const ENERGY_KEYWORDS = [
  '能效', '能量', '电度', '电表', '功耗', '用电', '计量',
  '能源', 'energy', 'meter', 'power', 'energ',
]

// Product codes for subsystem → device-fault-summary mapping
const PRODUCT_MAP = {
  'fresh-air': 130004,
  'hydraulic': 270001,
  'air-quality': 100007,
}

// Default display names for subsystem compartments
const SUBSYSTEM_NAMES = {
  'fresh-air': '新风模块',
  'energy': '能耗中枢',
  'hydraulic': '水力模块',
  'air-quality': '空气品质',
}

// ── Internal Pure Functions (Aggregation Pipeline, ADR-BD-02) ──

/**
 * Map FaultEvent.severity to internal status.
 * 'error' → 'fault', 'warning' → 'warning', else → 'normal'.
 */
function severityToStatus(severity) {
  if (severity === 'error') return 'fault'
  if (severity === 'warning') return 'warning'
  if (severity === 'condensation') return 'warning'
  return 'normal'
}

/**
 * Check if a FaultEvent is related to energy devices.
 * Matches device_type_label and device_name against energy keywords.
 */
function isEnergyRelated(event) {
  const label = (event.device_type_label || '').toLowerCase()
  const name = (event.device_name || '').toLowerCase()
  return ENERGY_KEYWORDS.some((kw) => label.includes(kw) || name.includes(kw))
}

/**
 * Group fault events by room_name.
 * Returns Map<roomName, FaultEvent[]>.
 */
function groupFaultEventsByRoom(faultEvents) {
  const map = new Map()
  for (const ev of (faultEvents || [])) {
    const room = ev.room_name || '__unknown__'
    if (!map.has(room)) map.set(room, [])
    map.get(room).push(ev)
  }
  return map
}

/**
 * Derive energy subsystem status (ADR-BD-06, OQ-01 Option A).
 * @param {object} plcRate — { online_count, total_count }
 * @param {Array} faultEvents — all active fault events
 * @returns {SubsystemState}
 */
function deriveEnergyStatus(plcRate, faultEvents, cockpitPlcStatus) {
  const plcOnline = plcRate?.online_count ?? 0
  const plcTotal = plcRate?.total_count ?? 0

  // PLC status from fleet-wide aggregate (blocked for owners → cockpit fallback)
  let plcStatus = 'idle'
  if (plcTotal > 0) {
    if (plcOnline === plcTotal) plcStatus = 'normal'
    else if (plcOnline > 0) plcStatus = 'warning'
    else plcStatus = 'fault'
  } else if (cockpitPlcStatus === 'online') {
    // Fallback: use cockpit-level PLC status from /api/miniapp/owner/connectivity/
    plcStatus = 'normal'
  } else if (cockpitPlcStatus === 'offline') {
    plcStatus = 'warning'
  }

  // Filter energy-related fault events
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

  // Derive final status: energy is a derived aggregate without a discrete product code.
  // When no fleet PLC data AND no energy faults → 'normal' (no news = good news),
  // not 'idle' which implies a problem.
  let status
  if (plcTotal > 0) {
    status = worseStatus(plcStatus, eventStatus)
  } else if (cockpitPlcStatus) {
    status = worseStatus(plcStatus, eventStatus)
  } else if (energyFaults.length > 0) {
    status = eventStatus
  } else {
    status = 'normal'
  }

  const dataSource = plcTotal > 0
    ? 'PLC在线率'
    : (cockpitPlcStatus ? '座舱PLC' : 'FaultEvent')

  return {
    id: 'energy',
    name: SUBSYSTEM_NAMES['energy'],
    status,
    faultCount,
    warningCount,
    productCode: null,
    dataSource,
  }
}

/**
 * Aggregate subsystem status from device-fault-summary API response.
 * @param {object} faultSummary — response from getDashboardDeviceFaultSummary
 * @param {object} plcRate — PLC online rate response
 * @param {Array} faultEvents — all active fault events
 * @returns {Array<SubsystemState>}
 */
function aggregateSubsystemStatus(faultSummary, plcRate, faultEvents, cockpitPlcStatus) {
  const data = faultSummary?.data || faultSummary || {}
  const freshAir = data.fresh_air_unit || {}
  const hydraulic = data.hydraulic_module || {}
  const airQuality = data.air_quality_sensor || {}

  const subsystems = []

  // Fresh-air
  subsystems.push({
    id: 'fresh-air',
    name: SUBSYSTEM_NAMES['fresh-air'],
    status: (freshAir.fault_count || 0) > 0 ? 'fault' : 'normal',
    faultCount: freshAir.fault_count || 0,
    warningCount: 0,
    productCode: PRODUCT_MAP['fresh-air'],
    dataSource: 'device-fault-summary',
  })

  // Hydraulic
  subsystems.push({
    id: 'hydraulic',
    name: SUBSYSTEM_NAMES['hydraulic'],
    status: (hydraulic.fault_count || 0) > 0 ? 'fault' : 'normal',
    faultCount: hydraulic.fault_count || 0,
    warningCount: 0,
    productCode: PRODUCT_MAP['hydraulic'],
    dataSource: 'device-fault-summary',
  })

  // Air-quality
  subsystems.push({
    id: 'air-quality',
    name: SUBSYSTEM_NAMES['air-quality'],
    status: (airQuality.fault_count || 0) > 0 ? 'fault' : 'normal',
    faultCount: airQuality.fault_count || 0,
    warningCount: 0,
    productCode: PRODUCT_MAP['air-quality'],
    dataSource: 'device-fault-summary',
  })

  // Energy (derived)
  subsystems.push(deriveEnergyStatus(plcRate, faultEvents, cockpitPlcStatus))

  return subsystems
}

/**
 * Aggregate room status from structure + fault events + condensation data.
 * @param {object} structure — getOwnerStructure() response
 * @param {Array} faultEvents — active fault events
 * @param {number} condensationCount — active condensation warning count
 * @returns {Array<RoomState>}
 */
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

  // Also include rooms that appear in fault events but not in structure
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

/**
 * Compute overall bridge health status from subsystems + rooms.
 * Any fault → fault; any warning → warning; all normal → normal; no data → syncing.
 */
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

/**
 * Filter fault events to match a specific compartment.
 * @param {Array} faultEvents — all active faults
 * @param {object} compartment — { type, id, name }
 * @returns {Array}
 */
function filterFaultEventsByCompartment(faultEvents, compartment) {
  if (!compartment || !faultEvents?.length) return []

  if (compartment.type === 'subsystem') {
    switch (compartment.id) {
      case 'fresh-air':
        return faultEvents.filter((ev) => ev.product_code === PRODUCT_MAP['fresh-air'])
      case 'hydraulic':
        return faultEvents.filter((ev) => ev.product_code === PRODUCT_MAP['hydraulic'])
      case 'air-quality':
        return faultEvents.filter((ev) => ev.product_code === PRODUCT_MAP['air-quality'])
      case 'energy':
        return faultEvents.filter(isEnergyRelated)
      default:
        return []
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

// ── Composable ─────────────────────────────────────────────────

export function useBridgeDashboard() {
  const ownerStore = useOwnerStore()

  // ── Reactive State ──────────────────────────────────────

  const state = reactive({
    /** IFC-BD-002-01: First load in progress. */
    loading: true,

    /** IFC-BD-002-02: Background refresh in progress (don't blank the UI). */
    refreshing: false,

    /** IFC-BD-002-03: Global error (all APIs failed). */
    error: null,

    /** IFC-BD-002-04: Bound cockpit list. */
    bindings: [],

    /** IFC-BD-002-05: Currently selected specific_part. */
    selectedSp: '',

    /** IFC-BD-002-06: Display label for current cockpit. */
    selectedLabel: '',

    /** IFC-BD-002-07: Overall health status { level, text }. */
    overallStatus: { level: 'syncing', text: '同步中' },

    /** IFC-BD-002-08: Subsystem compartment states. */
    subsystems: [],

    /** IFC-BD-002-09: Room compartment states. */
    rooms: [],

    /** IFC-BD-002-10: PLC online count. */
    plcOnline: 0,

    /** IFC-BD-002-11: Total PLC count. */
    plcTotal: 0,

    /** IFC-BD-002-11a: PLC connectivity status for current cockpit (online/offline/unknown). */
    plcCockpitStatus: 'unknown',

    /** IFC-BD-002-11b: Screen (大屏) connectivity status for current cockpit. */
    screenCockpitStatus: 'unknown',

    /** IFC-BD-002-12: Active condensation warning count. */
    condensationCount: 0,

    /** IFC-BD-002-13: Currently opened compartment detail (null = closed). */
    activeCompartment: null,

    /** IFC-BD-002-14: Per-subsystem error messages. */
    subsystemErrors: {},

    /** Device params for currently opened compartment (replicating web system panel). */
    compartmentParams: null,
  })

  // Internal caches for drawer data
  let _faultEventsCache = []
  let _condensationEventsCache = []
  let _structureCache = null
  let _realtimeParamsCache = null

  // ── Poller ──────────────────────────────────────────────

  let _poller = null

  function _createPoller() {
    if (_poller) _poller.stop()
    _poller = new PagePoller(() => {
      state.refreshing = true
      _doFetch(false).finally(() => {
        state.refreshing = false
      })
    }, POLL_INTERVAL_MS)
  }

  // ── Core fetch logic ────────────────────────────────────

  async function _doFetch(isInitialLoad = false) {
    const sp = state.selectedSp
    if (!sp) return

    state.subsystemErrors = {}

    const results = await Promise.allSettled([
      // 0: structure
      api.getOwnerStructure(sp),
      // 1: device fault summary
      api.getDashboardDeviceFaultSummary(),
      // 2: PLC online rate
      api.getDashboardPlcOnlineRate(),
      // 3: fault events
      api.getFaultEvents({ specific_part: sp, is_active: true, page_size: 200 }),
      // 4: condensation count
      api.getCondensationWarningCount(),
      // 5: bindings (refresh cockpit list)
      api.getBindStatus(),
      // 6: realtime params (for drawer device detail)
      api.getOwnerRealtimeParams(sp),
      // 7: cockpit connectivity (PLC + screen status for bridge indicators)
      api.getOwnerConnectivity(sp),
    ])

    // Bindings
    if (results[5].status === 'fulfilled' && results[5].value) {
      const res = results[5].value
      state.bindings = res?.bindings || res?.data?.bindings || []
    }

    // Realtime params (for drawer device detail)
    if (results[6].status === 'fulfilled' && results[6].value?.success !== false) {
      _realtimeParamsCache = results[6].value?.data || results[6].value || null
    }

    // Cockpit connectivity (PLC + screen status)
    if (results[7].status === 'fulfilled' && results[7].value?.success) {
      const conn = results[7].value
      state.plcCockpitStatus = conn.plc_status || 'unknown'
      state.screenCockpitStatus = conn.screen_status || 'unknown'
    }

    // Structure
    let structure = null
    if (results[0].status === 'fulfilled' && results[0].value?.success !== false) {
      structure = results[0].value
      _structureCache = structure
      state.subsystemErrors['structure'] = null
    } else {
      state.subsystemErrors['structure'] = '房间结构暂不可用'
    }

    // Device fault summary
    let faultSummary = null
    if (results[1].status === 'fulfilled' && results[1].value) {
      faultSummary = results[1].value
      state.subsystemErrors['device-summary'] = null
    } else {
      state.subsystemErrors['device-summary'] = '设备状态暂不可用'
    }

    // PLC online rate
    let plcRate = null
    if (results[2].status === 'fulfilled' && results[2].value?.data) {
      plcRate = results[2].value.data
      state.plcOnline = plcRate.online_count || 0
      state.plcTotal = plcRate.total_count || 0
      state.subsystemErrors['plc'] = null
    } else {
      state.subsystemErrors['plc'] = 'PLC状态暂不可用'
    }

    // Fault events
    let faultEvents = []
    if (results[3].status === 'fulfilled' && results[3].value) {
      faultEvents = results[3].value.results || results[3].value.data?.results || []
      _faultEventsCache = faultEvents
      state.subsystemErrors['fault-events'] = null
    } else {
      state.subsystemErrors['fault-events'] = '故障数据暂不可用'
    }

    // Condensation count
    if (results[4].status === 'fulfilled' && results[4].value) {
      const d = results[4].value
      if (typeof d?.count === 'number') {
        state.condensationCount = d.count
      } else if (typeof d?.data?.count === 'number') {
        state.condensationCount = d.data.count
      } else {
        state.condensationCount = 0
      }
    }

    // Aggregate
    const hasAnyData = faultSummary || structure || faultEvents.length > 0
    if (hasAnyData) {
      state.subsystems = aggregateSubsystemStatus(faultSummary || {}, plcRate, faultEvents, state.plcCockpitStatus)
      state.rooms = aggregateRoomStatus(structure || {}, faultEvents, state.condensationCount)
      state.overallStatus = computeOverallStatus(state.subsystems, state.rooms)
    }

    // Global error: all major APIs failed
    const criticalFailures = [
      'structure', 'device-summary', 'fault-events',
    ].every((k) => state.subsystemErrors[k] !== undefined || state.subsystemErrors[k])
    const allFailed = results.every((r) => r.status === 'rejected')
    if (allFailed) {
      state.error = '数据加载失败，请下拉刷新重试'
    } else {
      state.error = null
    }
  }

  // ── Public Methods ──────────────────────────────────────

  /** IFC-BD-002-15: Start — initial load + begin polling. */
  async function start() {
    // Fast path: get cached bindings
    try {
      await ownerStore.ensureBindings({ allowStale: true })
      state.bindings = ownerStore.bindings || []
    } catch (e) {
      state.bindings = []
    }

    if (state.bindings.length === 0) {
      state.loading = false
      state.overallStatus = { level: 'syncing', text: '等待绑定' }
      return
    }

    // Select initial cockpit
    const activeSp = ownerStore.activeSpecificPart
      || (() => { try { return uni.getStorageSync('active_specific_part') || '' } catch (e) { return '' } })()

    const matchedIdx = state.bindings.findIndex((b) => b.specific_part === activeSp)
    const idx = matchedIdx >= 0 ? matchedIdx : 0
    const sp = state.bindings[idx]?.specific_part || ''
    state.selectedSp = sp
    state.selectedLabel = state.bindings[idx]?.location_name || sp || '未命名座舱'

    if (sp) {
      ownerStore.setActiveSpecificPart(sp)
    }

    // Initial fetch
    state.loading = true
    try {
      await _doFetch(true)
    } catch (e) {
      state.error = '初始化失败，请重试'
    }
    state.loading = false

    // Start polling
    _createPoller()
    _poller.start()
  }

  /** IFC-BD-002-16: Stop polling. */
  function stop() {
    if (_poller) {
      _poller.stop()
      _poller = null
    }
  }

  /** IFC-BD-002-17: Manual refresh (called from pull-down). */
  async function refresh(force = false) {
    state.refreshing = true
    try {
      await _doFetch(force)
    } catch (e) {
      state.error = '刷新失败，请重试'
    }
    state.refreshing = false
  }

  /** IFC-BD-002-18: Switch to another cockpit. */
  async function switchCockpit(sp) {
    if (!sp || sp === state.selectedSp) return
    state.selectedSp = sp
    const binding = state.bindings.find((b) => b.specific_part === sp)
    state.selectedLabel = binding?.location_name || sp || '未命名座舱'
    ownerStore.setActiveSpecificPart(sp)

    state.loading = true
    try {
      await _doFetch(true)
    } catch (e) {
      state.error = '座舱切换失败，请重试'
    }
    state.loading = false

    // Restart poller for new cockpit
    _createPoller()
    if (_poller) _poller.start()
  }

  /** Build device param list from structure + realtime data for a compartment. */
  function _buildCompartmentParams(compartment) {
    const params = []
    const structure = _structureCache
    const realtime = _realtimeParamsCache || {}

    if (!structure) return params

    // Collect devices for this compartment
    const rooms = structure.rooms || []
    const systemDevices = structure.system_devices || []

    if (compartment.type === 'room' || compartment.id === compartment.name) {
      // Room: find devices in this room
      const room = rooms.find(r => (r.name || r.room_name) === compartment.name)
      if (room && room.devices) {
        for (const dev of room.devices) {
          const sn = dev.device_sn || dev.sn || ''
          const attrs = realtime[sn] || {}
          params.push({
            deviceSn: sn,
            deviceName: dev.name || dev.device_name || sn,
            productCode: dev.product_code || '',
            deviceType: dev.device_type || dev.type_label || '',
            attrs: Object.entries(attrs).map(([tag, val]) => ({ tag, value: val })),
          })
        }
      }
    } else if (compartment.type === 'subsystem') {
      // Subsystem: find matching system devices
      const productMap = { 'fresh-air': 130004, 'hydraulic': 270001, 'air-quality': 100007 }
      const targetCode = productMap[compartment.id]
      const candidates = targetCode
        ? systemDevices.filter(d => d.product_code === targetCode)
        : systemDevices
      for (const dev of candidates) {
        const sn = dev.device_sn || dev.sn || ''
        const attrs = realtime[sn] || {}
        params.push({
          deviceSn: sn,
          deviceName: dev.name || dev.device_name || sn,
          productCode: dev.product_code || '',
          deviceType: dev.device_type || dev.type_label || '',
          attrs: Object.entries(attrs).map(([tag, val]) => ({ tag, value: val })),
        })
      }
      // Energy: also include devices found via energy keywords in fault events
      if (compartment.id === 'energy') {
        for (const dev of systemDevices) {
          const sn = dev.device_sn || dev.sn || ''
          if (!params.find(p => p.deviceSn === sn)) {
            const attrs = realtime[sn] || {}
            const hasData = Object.keys(attrs).length > 0
            if (hasData) {
              params.push({
                deviceSn: sn,
                deviceName: dev.name || dev.device_name || sn,
                productCode: dev.product_code || '',
                deviceType: dev.device_type || dev.type_label || '',
                attrs: Object.entries(attrs).map(([tag, val]) => ({ tag, value: val })),
              })
            }
          }
        }
      }
    }

    return params
  }

  /** IFC-BD-002-19: Open compartment drawer. */
  function openCompartment(compartment) {
    const events = filterFaultEventsByCompartment(_faultEventsCache, compartment)
    const params = _buildCompartmentParams(compartment)

    state.activeCompartment = {
      type: compartment.type || (compartment.productCode !== undefined ? 'subsystem' : 'room'),
      id: compartment.id,
      name: compartment.name,
      status: compartment.status,
      faultEvents: events.map((ev) => ({
        id: ev.id,
        deviceName: ev.device_name || '未知设备',
        deviceTypeLabel: ev.device_type_label || '',
        severity: ev.severity === 'error' ? 'fault' : (ev.severity || 'warning'),
        faultType: ev.fault_type || '',
        faultMessage: ev.fault_message || '',
        firstSeenAt: ev.first_seen_at || '',
        roomName: ev.room_name || '',
      })),
    }
    state.compartmentParams = params
  }

  /** IFC-BD-002-20: Close compartment drawer. */
  function closeCompartment() {
    state.activeCompartment = null
    state.compartmentParams = null
  }

  // ── Return ──────────────────────────────────────────────

  return {
    state,

    // Computed helpers for template convenience
    /** True when there are no bindings at all. */
    hasNoBindings: computed(() => !state.loading && state.bindings.length === 0),

    /** Selected binding index in bindings array. */
    selectedBindingIndex: computed(() => {
      const idx = state.bindings.findIndex((b) => b.specific_part === state.selectedSp)
      return idx >= 0 ? idx : 0
    }),

    /** Whether to show the cockpit switcher. */
    showCabinSwitcher: computed(() => state.bindings.length > 1),

    // Methods
    start,
    stop,
    refresh,
    switchCockpit,
    openCompartment,
    closeCompartment,
  }
}
