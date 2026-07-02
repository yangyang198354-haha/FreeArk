/**
 * Shared owner-side data cache for user miniapp pages.
 *
 * Goals:
 * - De-duplicate concurrent HTTP requests across home/profile/bind/settings.
 * - Show cached owner data immediately, then refresh silently.
 * - Reuse the existing owner_structure_{sp} cache used by param-settings.
 */

import { defineStore } from 'pinia'
import { api } from '@/utils/api'
import { getUserInfo } from '@/utils/auth'

const BINDINGS_TTL_MS = 5 * 60 * 1000
const CONFIG_TTL_MS = 10 * 60 * 1000
const STRUCTURE_TTL_MS = 30 * 24 * 60 * 60 * 1000
const STRUCTURE_PENDING_TTL_MS = 5 * 60 * 1000
const REALTIME_TTL_MS = 60 * 1000
const DEVICE_SNAPSHOT_TTL_MS = 30 * 1000

let bindingsPromise = null
let configPromise = null
const structurePromises = {}
const realtimePromises = {}

function now() {
  return Date.now()
}

function userKey(name) {
  const info = getUserInfo() || {}
  const userId = info.id != null ? info.id : (info.username || 'guest')
  return `owner_cache_${userId}_${name}`
}

function readStorage(key, fallback = null) {
  try {
    const value = uni.getStorageSync(key)
    return value === '' || value === undefined ? fallback : value
  } catch (e) {
    return fallback
  }
}

function writeStorage(key, value) {
  try { uni.setStorageSync(key, value) } catch (e) { /* ignore */ }
}

function removeStorage(key) {
  try { uni.removeStorageSync(key) } catch (e) { /* ignore */ }
}

function parseJson(raw) {
  if (!raw) return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(raw) } catch (e) { return null }
}

function readTs(key) {
  const raw = readStorage(key, '')
  if (!raw) return 0
  const t = new Date(raw).getTime()
  return Number.isFinite(t) ? t : 0
}

function fresh(ts, ttlMs) {
  return !!ts && now() - ts <= ttlMs
}

function normalizeBindings(res) {
  const list = res?.bindings || res?.data?.bindings || []
  return Array.isArray(list) ? list : []
}

function readBindingsCache() {
  const cached = parseJson(readStorage(userKey('bindings'), null))
  if (!cached) return { loaded: false, bindings: [], ts: 0 }
  return {
    loaded: true,
    bindings: Array.isArray(cached.bindings) ? cached.bindings : [],
    ts: Number(cached.ts || 0),
  }
}

function writeBindingsCache(bindings) {
  writeStorage(userKey('bindings'), { bindings, ts: now() })
}

function readConfigCache() {
  const cached = parseJson(readStorage(userKey('device_settings_config'), null))
  if (!cached) return { loaded: false, data: null, ts: 0 }
  return { loaded: true, data: cached.data || null, ts: Number(cached.ts || 0) }
}

function writeConfigCache(data) {
  writeStorage(userKey('device_settings_config'), { data, ts: now() })
}

function structureKey(sp) {
  return `owner_structure_${sp}`
}

function realtimeKey(sp) {
  return `owner_realtime_${sp}`
}

function readStructureCache(sp) {
  const data = parseJson(readStorage(structureKey(sp), null))
  const ts = readTs(`${structureKey(sp)}_ts`)
  const ttl = Number(readStorage(`${structureKey(sp)}_ttl`, STRUCTURE_TTL_MS)) || STRUCTURE_TTL_MS
  return { data, ts, ttl, expired: !fresh(ts, ttl) }
}

function writeStructureCache(sp, data) {
  const ttl = data?.sync_status === 'pending' ? STRUCTURE_PENDING_TTL_MS : STRUCTURE_TTL_MS
  writeStorage(structureKey(sp), JSON.stringify(data))
  writeStorage(`${structureKey(sp)}_ts`, new Date().toISOString())
  writeStorage(`${structureKey(sp)}_ttl`, ttl)
}

function readRealtimeCache(sp) {
  const data = parseJson(readStorage(realtimeKey(sp), null))
  const ts = readTs(`${realtimeKey(sp)}_ts`)
  return { data, ts, expired: !fresh(ts, REALTIME_TTL_MS) }
}

function writeRealtimeCache(sp, data) {
  writeStorage(realtimeKey(sp), JSON.stringify(data))
  writeStorage(`${realtimeKey(sp)}_ts`, new Date().toISOString())
}

function deviceSnapshotKey(sp) {
  return userKey(`device_snapshot_${sp}`)
}

function readDeviceSnapshot(sp) {
  const data = parseJson(readStorage(deviceSnapshotKey(sp), null))
  const ts = readTs(`${deviceSnapshotKey(sp)}_ts`)
  return { data, ts, expired: !fresh(ts, DEVICE_SNAPSHOT_TTL_MS) }
}

function writeDeviceSnapshot(sp, data) {
  writeStorage(deviceSnapshotKey(sp), JSON.stringify(data))
  writeStorage(`${deviceSnapshotKey(sp)}_ts`, new Date().toISOString())
}

const initialBindings = readBindingsCache()
const initialConfig = readConfigCache()

export const useOwnerStore = defineStore('owner', {
  state: () => ({
    bindings: initialBindings.bindings,
    bindingsLoaded: initialBindings.loaded,
    bindingsTs: initialBindings.ts,

    deviceSettingsConfig: initialConfig.data,
    deviceSettingsConfigLoaded: initialConfig.loaded,
    deviceSettingsConfigTs: initialConfig.ts,

    activeSpecificPart: readStorage('active_specific_part', ''),
    structuresByPart: {},
    structureTsByPart: {},
    structureTtlByPart: {},
    realtimeByPart: {},
    realtimeTsByPart: {},
    deviceSnapshotsByPart: {},
    deviceSnapshotTsByPart: {},
  }),

  getters: {
    structureFor: (state) => (sp) => state.structuresByPart[sp] || null,
    realtimeFor: (state) => (sp) => state.realtimeByPart[sp] || null,
    deviceSnapshotFor: (state) => (sp) => state.deviceSnapshotsByPart[sp] || null,
  },

  actions: {
    setActiveSpecificPart(sp) {
      this.activeSpecificPart = sp || ''
      if (sp) writeStorage('active_specific_part', sp)
    },

    setBindings(bindings) {
      this.bindings = Array.isArray(bindings) ? bindings : []
      this.bindingsLoaded = true
      this.bindingsTs = now()
      writeBindingsCache(this.bindings)
    },

    async refreshBindings() {
      if (bindingsPromise) return bindingsPromise
      bindingsPromise = api.getBindStatus()
        .then((res) => {
          const list = normalizeBindings(res)
          this.setBindings(list)
          return list
        })
        .finally(() => { bindingsPromise = null })
      return bindingsPromise
    },

    async ensureBindings(options = {}) {
      const force = !!options.force
      const allowStale = !!options.allowStale
      const maxAgeMs = options.maxAgeMs || BINDINGS_TTL_MS
      const isFresh = this.bindingsLoaded && fresh(this.bindingsTs, maxAgeMs)

      if (!force && this.bindingsLoaded && (isFresh || allowStale)) {
        if (!isFresh && allowStale && !bindingsPromise) this.refreshBindings().catch(() => {})
        return this.bindings
      }
      return this.refreshBindings()
    },

    invalidateOwnerConfig() {
      this.deviceSettingsConfigLoaded = false
      this.deviceSettingsConfigTs = 0
      this.deviceSettingsConfig = null
      removeStorage(userKey('device_settings_config'))
    },

    markBindingChanged() {
      this.bindingsLoaded = false
      this.bindingsTs = 0
      removeStorage(userKey('bindings'))
      this.invalidateOwnerConfig()
    },

    setDeviceSettingsConfig(data) {
      this.deviceSettingsConfig = data || null
      this.deviceSettingsConfigLoaded = true
      this.deviceSettingsConfigTs = now()
      writeConfigCache(this.deviceSettingsConfig)
    },

    async refreshDeviceSettingsConfig() {
      if (configPromise) return configPromise
      configPromise = api.getDeviceSettingsConfig()
        .then((res) => {
          this.setDeviceSettingsConfig(res)
          return res
        })
        .finally(() => { configPromise = null })
      return configPromise
    },

    async ensureDeviceSettingsConfig(options = {}) {
      const force = !!options.force
      const allowStale = !!options.allowStale
      const maxAgeMs = options.maxAgeMs || CONFIG_TTL_MS
      const isFresh = this.deviceSettingsConfigLoaded && fresh(this.deviceSettingsConfigTs, maxAgeMs)

      if (!force && this.deviceSettingsConfigLoaded && (isFresh || allowStale)) {
        if (!isFresh && allowStale && !configPromise) this.refreshDeviceSettingsConfig().catch(() => {})
        return this.deviceSettingsConfig
      }
      return this.refreshDeviceSettingsConfig()
    },

    hydrateStructure(sp) {
      if (!sp) return null
      if (this.structuresByPart[sp]) return this.structuresByPart[sp]
      const cached = readStructureCache(sp)
      if (!cached.data) return null
      this.structuresByPart[sp] = cached.data
      this.structureTsByPart[sp] = cached.ts
      this.structureTtlByPart[sp] = cached.ttl
      return cached.data
    },

    setStructure(sp, data) {
      if (!sp || !data) return
      this.structuresByPart[sp] = data
      this.structureTsByPart[sp] = now()
      this.structureTtlByPart[sp] = data.sync_status === 'pending' ? STRUCTURE_PENDING_TTL_MS : STRUCTURE_TTL_MS
      writeStructureCache(sp, data)
    },

    async refreshStructure(sp) {
      if (!sp) return null
      if (structurePromises[sp]) return structurePromises[sp]
      structurePromises[sp] = api.getOwnerStructure(sp)
        .then((res) => {
          if (res && res.success !== false) this.setStructure(sp, res)
          return res
        })
        .finally(() => { delete structurePromises[sp] })
      return structurePromises[sp]
    },

    async ensureStructure(sp, options = {}) {
      if (!sp) return null
      const force = !!options.force
      const allowStale = !!options.allowStale
      this.hydrateStructure(sp)

      const data = this.structuresByPart[sp]
      const ts = this.structureTsByPart[sp] || 0
      const ttl = this.structureTtlByPart[sp] || STRUCTURE_TTL_MS
      const isFresh = data && fresh(ts, ttl)

      if (!force && data && (isFresh || allowStale)) {
        if (!isFresh && allowStale && !structurePromises[sp]) this.refreshStructure(sp).catch(() => {})
        return data
      }
      return this.refreshStructure(sp)
    },

    hydrateRealtime(sp) {
      if (!sp) return null
      if (this.realtimeByPart[sp]) return this.realtimeByPart[sp]
      const cached = readRealtimeCache(sp)
      if (!cached.data) return null
      this.realtimeByPart[sp] = cached.data
      this.realtimeTsByPart[sp] = cached.ts
      return cached.data
    },

    setRealtime(sp, data) {
      if (!sp || !data) return
      this.realtimeByPart[sp] = data
      this.realtimeTsByPart[sp] = now()
      writeRealtimeCache(sp, data)
    },

    async refreshRealtime(sp) {
      if (!sp) return null
      if (realtimePromises[sp]) return realtimePromises[sp]
      realtimePromises[sp] = api.getOwnerRealtimeParams(sp)
        .then((res) => {
          if (res && res.success !== false) this.setRealtime(sp, res)
          return res
        })
        .finally(() => { delete realtimePromises[sp] })
      return realtimePromises[sp]
    },

    async ensureRealtime(sp, options = {}) {
      if (!sp) return null
      const force = !!options.force
      const allowStale = !!options.allowStale
      const maxAgeMs = options.maxAgeMs || REALTIME_TTL_MS
      this.hydrateRealtime(sp)

      const data = this.realtimeByPart[sp]
      const ts = this.realtimeTsByPart[sp] || 0
      const isFresh = data && fresh(ts, maxAgeMs)

      if (!force && data && (isFresh || allowStale)) {
        if (!isFresh && allowStale && !realtimePromises[sp]) this.refreshRealtime(sp).catch(() => {})
        return data
      }
      return this.refreshRealtime(sp)
    },

    bootstrapAfterLogin() {
      return Promise.allSettled([
        this.ensureBindings({ force: true }),
        this.ensureDeviceSettingsConfig({ force: true }),
      ])
    },

    setDeviceSnapshot(sp, devices) {
      if (!sp || !devices) return
      this.deviceSnapshotsByPart[sp] = { ...devices }
      this.deviceSnapshotTsByPart[sp] = now()
      writeDeviceSnapshot(sp, devices)
    },

    hydrateDeviceSnapshot(sp) {
      if (!sp) return null
      if (this.deviceSnapshotsByPart[sp]) return this.deviceSnapshotsByPart[sp]
      const cached = readDeviceSnapshot(sp)
      if (cached.data) {
        this.deviceSnapshotsByPart[sp] = cached.data
        this.deviceSnapshotTsByPart[sp] = cached.ts
      }
      return cached.data
    },
  },
})

export default useOwnerStore
