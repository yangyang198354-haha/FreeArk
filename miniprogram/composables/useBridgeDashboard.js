/**
 * @module MOD-BD-002
 * @implements IFC-BD-002-01 through IFC-BD-002-26
 * @depends api.js, ownerStore, authStore, PagePoller, arkZoneMap (worseStatus, STATUS_RANK),
 *   faultUtils (MOD-FAULT-UTILS)
 * @author sub_agent_software_developer
 * @description Bridge dashboard composable — data fetching, status aggregation,
 *   polling lifecycle, cockpit switching, compartment open/close.
 *
 *   v1.12.0 refactor — per-座舱 PLC 参数:
 *   - Subsystem status: from per-cockpit PLC realtime params (not global fault-summary)
 *   - Energy module: pure PLC parameter judgment (not global PLC rate + keywords)
 *   - Dynamic subsystem visibility: based on structure.system_devices sub_type
 *   - Room list: structure-driven only (no orphan fault-event rooms)
 *   - Drawer params: sub_type matching (not product_code)
 *
 *   Data flow:
 *     start() → _doFetch() → aggregateStatus() → reactive state
 *     poller (30s) → refresh() → _doFetch() → aggregateStatus()
 *     switchCockpit(sp) → _doFetch(sp) → aggregateStatus()
 */

import { reactive, computed } from 'vue'
import { api } from '@/utils/api'
import { useOwnerStore } from '@/store/owner'
import { PagePoller } from '@/utils/poller'
import { worseStatus, STATUS_RANK } from '@/subpackages/game/arkZoneMap'
import {
  computeFaultCount,
  expandFreshAirFaultBits,
  isFaultValueForDisplay,
  SYSTEM_SUB_KEYS,
  SUB_TYPE_TO_ID,
  ID_TO_SUB_TYPE,
} from '@/utils/faultUtils'

// ── Constants ──────────────────────────────────────────────────

const POLL_INTERVAL_MS = 30000

// Default display names for subsystem compartments
const SUBSYSTEM_NAMES = {
  'fresh-air': '新风模块',
  'energy': '能耗中枢',
  'hydraulic': '水力模块',
  'air-quality': '空气品质',
}

// ── Internal Pure Functions (Aggregation Pipeline) ────────────

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

// ── Subsystem Status Aggregation (v1.12.0: per-座舱 PLC params) ──

/**
 * IFC-BD-002-23: Aggregate subsystem status from per-cockpit PLC realtime params.
 *
 * Replaces old aggregateSubsystemStatus(faultSummary, plcRate, faultEvents, cockpitPlcStatus).
 * New signature: (structure, realtimeParams).
 *
 * Algorithm:
 *   1. Extract sub_types from structure.system_devices
 *   2. Intersect with SYSTEM_SUB_KEYS → determine which subsystems this cockpit has
 *   3. For each subsystem:
 *      a. Find all devices of that sub_type
 *      b. Collect their PLC params from realtimeParams
 *      c. Call computeFaultCount(params) → fault count
 *      d. faultCount > 0 → 'fault', faultCount === 0 → 'normal'
 *      e. If realtimeParams unavailable → 'idle'
 *   4. Return only subsystems this cockpit actually has
 *
 * REQ-NFUNC-004 fallback:
 *   - structure.system_devices empty/missing → show all 4 subsystems (SYSTEM_SUB_KEYS)
 *   - realtimeParams empty/missing → show all present subsystems with 'idle' status
 *
 * @param {object} structure — getOwnerStructure() response
 * @param {object} realtimeParams — getOwnerRealtimeParams() response, keyed by device_sn
 * @returns {Array<SubsystemState>}
 */
function aggregateSubsystemStatus(structure, realtimeParams) {
  const realtime = realtimeParams || {}
  const systemDevices = structure?.system_devices || []

  // Determine which subsystems to show
  const structureAvailable = systemDevices.length > 0
  let subTypesToShow

  if (structureAvailable) {
    const availableSubTypes = new Set(systemDevices.map((d) => d.sub_type).filter(Boolean))
    subTypesToShow = SYSTEM_SUB_KEYS.filter((st) => availableSubTypes.has(st))
  } else {
    // REQ-NFUNC-004 fallback: structure unavailable → show all 4
    subTypesToShow = [...SYSTEM_SUB_KEYS]
  }

  const realtimeAvailable = realtime && Object.keys(realtime).length > 0

  const subsystems = []
  for (const subType of subTypesToShow) {
    const id = SUB_TYPE_TO_ID[subType] || subType
    const name = SUBSYSTEM_NAMES[id] || subType

    let faultCount = 0
    let status = 'idle'

    if (realtimeAvailable && structureAvailable) {
      // Find all devices of this sub_type
      const devices = systemDevices.filter((d) => d.sub_type === subType)

      // Collect all PLC params from these devices
      const params = []
      for (const dev of devices) {
        const sn = dev.device_sn || dev.sn || ''
        const attrs = realtime[sn] || {}
        for (const [tag, value] of Object.entries(attrs)) {
          params.push({ paramName: tag, value })
        }
      }

      // Compute fault count using fault_utils equivalent logic
      faultCount = computeFaultCount(params)
      status = faultCount > 0 ? 'fault' : 'normal'
    } else if (!structureAvailable) {
      // Structure unavailable → no device info to match params
      // Show 'normal' as default (don't alarm without structure context)
      status = 'normal'
    }

    subsystems.push({
      id,
      name,
      status,
      faultCount,
      warningCount: 0,
      dataSource: 'plc-realtime-params',
    })
  }

  return subsystems
}

// ── Room Status Aggregation ────────────────────────────────────

/**
 * Aggregate room status from structure + fault events + condensation data.
 *
 * v1.12.0: Removed orphan room discovery (ADR-004).
 * Room list is now strictly from structure.rooms — no fault-event-driven append.
 *
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
 *
 * v1.12.0: Subsystem matching changed from product_code to
 * device_sn-based matching via structure.system_devices (sub_type).
 * Room matching unchanged.
 *
 * @param {Array} faultEvents — all active faults
 * @param {object} compartment — { type, id, name }
 * @param {object} structureCache — _structureCache reference for device_sn lookup
 * @returns {Array}
 */
function filterFaultEventsByCompartment(faultEvents, compartment, structureCache) {
  if (!compartment || !faultEvents?.length) return []

  if (compartment.type === 'subsystem') {
    const targetSubType = ID_TO_SUB_TYPE[compartment.id]
    if (!targetSubType) return []

    // Get device_sns for this sub_type from structure cache
    const systemDevices = structureCache?.system_devices || []
    const matchingSns = new Set(
      systemDevices
        .filter((d) => d.sub_type === targetSubType)
        .map((d) => d.device_sn || d.sn || '')
        .filter(Boolean)
    )

    // If we have matching device_sns, filter by them; otherwise return empty
    if (matchingSns.size > 0) {
      return faultEvents.filter((ev) => matchingSns.has(ev.device_sn))
    }
    return []
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

    /** IFC-BD-002-10: PLC online count (retained for interface compat, no longer updated). */
    plcOnline: 0,

    /** IFC-BD-002-11: Total PLC count (retained for interface compat, no longer updated). */
    plcTotal: 0,

    /** IFC-BD-002-11a: PLC connectivity status for current cockpit (online/offline/unknown). */
    plcCockpitStatus: 'unknown',

    /** IFC-BD-002-11b: Screen (大屏) connectivity status for current cockpit. */
    screenCockpitStatus: 'unknown',

    /** IFC-BD-002-12: Active condensation warning count. */
    condensationCount: 0,

    /** IFC-BD-002-13: Currently opened compartment detail (null = closed). */
    activeCompartment: null,

    /** IFC-BD-002-14: Per-subsystem error messages (v1.12.0: keys updated). */
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

  // ── Core fetch logic (v1.12.0: removed device-fault-summary + plc-online-rate) ──

  async function _doFetch(isInitialLoad = false) {
    const sp = state.selectedSp
    if (!sp) return

    state.subsystemErrors = {}

    // v1.12.0: Removed items [1] getDashboardDeviceFaultSummary and [2] getDashboardPlcOnlineRate.
    // New indices: 0=structure, 1=faultEvents, 2=condensation, 3=bindings, 4=realtimeParams, 5=connectivity
    const results = await Promise.allSettled([
      // 0: structure
      api.getOwnerStructure(sp),
      // 1: fault events
      api.getFaultEvents({ specific_part: sp, is_active: true, page_size: 200 }),
      // 2: condensation count
      api.getCondensationWarningCount(),
      // 3: bindings (refresh cockpit list)
      api.getBindStatus(),
      // 4: realtime params (for subsystem status + drawer device detail)
      api.getOwnerRealtimeParams(sp),
      // 5: cockpit connectivity (PLC + screen status for bridge indicators)
      api.getOwnerConnectivity(sp),
    ])

    // Bindings (was index 5, now index 3)
    if (results[3].status === 'fulfilled' && results[3].value) {
      const res = results[3].value
      state.bindings = res?.bindings || res?.data?.bindings || []
    }

    // Realtime params (was index 6, now index 4)
    // Per-座舱 PLC params — primary data source for subsystem status (v1.12.0)
    if (results[4].status === 'fulfilled' && results[4].value?.success !== false) {
      _realtimeParamsCache = results[4].value?.data || results[4].value || null
      state.subsystemErrors['realtime-params'] = null
    } else {
      _realtimeParamsCache = null
      state.subsystemErrors['realtime-params'] = '设备参数暂不可用'
    }

    // Cockpit connectivity (was index 7, now index 5)
    if (results[5].status === 'fulfilled' && results[5].value?.success) {
      const conn = results[5].value
      state.plcCockpitStatus = conn.plc_status || 'unknown'
      state.screenCockpitStatus = conn.screen_status || 'unknown'
      state.subsystemErrors['connectivity'] = null
    } else {
      state.subsystemErrors['connectivity'] = '连接状态暂不可用'
    }

    // Structure (index 0 — unchanged)
    let structure = null
    if (results[0].status === 'fulfilled' && results[0].value?.success !== false) {
      structure = results[0].value
      _structureCache = structure
      state.subsystemErrors['structure'] = null
    } else {
      state.subsystemErrors['structure'] = '房间结构暂不可用'
    }

    // Fault events (was index 3, now index 1)
    let faultEvents = []
    if (results[1].status === 'fulfilled' && results[1].value) {
      faultEvents = results[1].value.results || results[1].value.data?.results || []
      _faultEventsCache = faultEvents
      state.subsystemErrors['fault-events'] = null
    } else {
      state.subsystemErrors['fault-events'] = '故障数据暂不可用'
    }

    // Condensation count (was index 4, now index 2)
    if (results[2].status === 'fulfilled' && results[2].value) {
      const d = results[2].value
      if (typeof d?.count === 'number') {
        state.condensationCount = d.count
      } else if (typeof d?.data?.count === 'number') {
        state.condensationCount = d.data.count
      } else {
        state.condensationCount = 0
      }
    }

    // ── v1.12.0: Aggregate with new data sources ──────────
    // Subsystem status: per-cockpit PLC realtime params (replaces faultSummary + plcRate)
    // Room status: structure + fault events (removes orphan room logic internally)
    const hasAnyData = structure || faultEvents.length > 0
    if (hasAnyData) {
      state.subsystems = aggregateSubsystemStatus(structure || {}, _realtimeParamsCache)
      state.rooms = aggregateRoomStatus(structure || {}, faultEvents, state.condensationCount)
      state.overallStatus = computeOverallStatus(state.subsystems, state.rooms)
    }

    // Global error: all major APIs failed
    // v1.12.0: updated critical keys from 'device-summary' → 'realtime-params'
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

  // ── Compartment Drawer Helpers ──────────────────────────

  /**
   * IFC-BD-002-25/26: Build device param list from structure + realtime data
   * for a given compartment.
   *
   * v1.12.0 changes:
   *   - Subsystem matching uses sub_type (not product_code)
   *   - Removed energy compensation logic (all subsystems use unified pipeline)
   *   - Integrated expandFreshAirFaultBits for fresh_air_fault_status
   *
   * @param {object} compartment — { type, id, name }
   * @returns {Array<DeviceParamBlock>}
   */
  function _buildCompartmentParams(compartment) {
    const params = []
    const structure = _structureCache
    const realtime = _realtimeParamsCache || {}

    if (!structure) return params

    const rooms = structure.rooms || []
    const systemDevices = structure.system_devices || []

    if (compartment.type === 'room') {
      // Room: find devices in this room
      const room = rooms.find((r) => (r.name || r.room_name) === compartment.name)
      if (room && room.devices) {
        for (const dev of room.devices) {
          params.push(_buildSingleDeviceParams(dev, realtime))
        }
      }
    } else if (compartment.type === 'subsystem') {
      // v1.12.0: Subsystem matching by sub_type (not product_code)
      const targetSubType = ID_TO_SUB_TYPE[compartment.id]
      if (targetSubType) {
        const matchedDevices = systemDevices.filter((d) => d.sub_type === targetSubType)
        for (const dev of matchedDevices) {
          params.push(_buildSingleDeviceParams(dev, realtime))
        }
      }
    }

    return params
  }

  /**
   * Build a single device's param block for drawer display.
   *
   * v1.12.0: Integrates expandFreshAirFaultBits for fresh_air_fault_status
   * and isFaultValueForDisplay for fault highlighting.
   *
   * @param {object} dev — device entry from structure
   * @param {object} realtime — realtime params cache
   * @returns {DeviceParamBlock}
   */
  function _buildSingleDeviceParams(dev, realtime) {
    const sn = dev.device_sn || dev.sn || ''
    const attrs = realtime[sn] || {}

    const block = {
      deviceSn: sn,
      deviceName: dev.name || dev.device_name || sn,
      subType: dev.sub_type || '',
      attrs: [],
    }

    for (const [tag, value] of Object.entries(attrs)) {
      const attr = {
        tag,
        displayName: tag,
        value,
        isFault: isFaultValueForDisplay(tag, value),
      }

      // v1.12.0: Expand fresh_air_fault_status bit field (ADR-007)
      if (tag === 'fresh_air_fault_status') {
        attr.expandedBits = expandFreshAirFaultBits(value)
      }

      block.attrs.push(attr)
    }

    return block
  }

  /** IFC-BD-002-19: Open compartment drawer. */
  function openCompartment(compartment) {
    // v1.12.0: filterFaultEventsByCompartment now accepts structureCache for sub_type→device_sn mapping
    const events = filterFaultEventsByCompartment(_faultEventsCache, compartment, _structureCache)
    const params = _buildCompartmentParams(compartment)

    // v1.12.0: type detection — SubsystemState no longer has productCode.
    // Use ID_TO_SUB_TYPE mapping to detect subsystem compartments by id.
    state.activeCompartment = {
      type: compartment.type || (ID_TO_SUB_TYPE[compartment.id] ? 'subsystem' : 'room'),
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
