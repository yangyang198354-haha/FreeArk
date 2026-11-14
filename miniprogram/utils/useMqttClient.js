/**
 * @module MOD-1110-FE-01
 * @implements IFC-1110-FE-01-1 (acquire), IFC-1110-FE-01-2 (release),
 *             IFC-1110-FE-01-3 (subscribe), IFC-1110-FE-01-4 (publishRead),
 *             IFC-1110-FE-01-5 (publishWrite), IFC-1110-FE-01-6 (waitConfirm),
 *             IFC-1110-FE-01-7 (onDeviceUpdate)
 * @depends screenMqtt.js (ScreenMqtt class)
 * @author sub_agent_software_developer
 * @description MQTT 全局单例 composable（v1.11.0_miniprogram_owner_home）。
 *
 *   ADR-1110-04 决策：模块级 composable（Option A），单例存于模块作用域变量。
 *   - _instance: ScreenMqtt 单例（null = 未连接）
 *   - _refCount: 活跃引用计数（acquire +1 / release -1，降至 0 时断开）
 *   - _connected: Vue ref<boolean>，响应式连接状态（随 ScreenMqtt 连接事件同步）
 *   - _desiredSubscriptions: 期望订阅的 screenMac 集合（跨重连保留）
 *   - _activeSubscriptions: 当前已在 broker 上生效的订阅集合（销毁实例时清空；
 *     mqtt.js 内置重连由其 resubscribe 机制自动恢复订阅）
 *   - _updateListeners: DeviceStatusUpdate 全局回调列表
 *
 *   FND-007（连接自愈）：连接失败或中途断线时按指数退避自动重连
 *   （3s→6s→…→60s 封顶），重连成功后自动恢复订阅；页面 onShow 也可调用
 *   ensureConnected() 立即补连。修复“启动时失败一次就整场会话永远橙色”。
 *
 *   param-settings.vue 迁移映射（零语义变更，ADR-1110-04 §迁移策略）:
 *     mqtt = new ScreenMqtt(broker, topics)  →  mqttClient.acquire(broker, topics)
 *     mqtt.onDeviceUpdate(cb)               →  const off = mqttClient.onDeviceUpdate(cb)
 *     mqtt.connect()                        →  （acquire 内部执行）
 *     mqtt.subscribeRoom(mac)               →  mqttClient.subscribe(mac)
 *     mqtt.readStatus(mac, sns)             →  mqttClient.publishRead(mac, sns)
 *     mqtt.writeAttrs(mac, sn, items)       →  mqttClient.publishWrite(mac, sn, items)
 *     mqtt.waitConfirm(sn, tag, val, ms)    →  mqttClient.waitConfirm(sn, tag, val, ms)
 *     mqtt.connected                        →  mqttClient.connected.value
 *     mqtt.disconnect() / mqtt = null       →  mqttClient.release()
 */

import { ref, computed } from 'vue'
import { ScreenMqtt } from './screenMqtt'

// ── 模块级单例状态（跨组件共享，不在函数内）──────────────────────────────────

/** 重连退避参数：首次 3s，逐次翻倍，60s 封顶 */
const RETRY_BASE_MS = 3000
const RETRY_MAX_MS = 60000

/** @type {ScreenMqtt|null} MQTT 客户端单例 */
let _instance = null

/** 活跃引用计数（acquire +1 / release -1） */
let _refCount = 0

/** 响应式连接状态（Vue ref，组件可直接 watch） */
const _connected = ref(false)

/** 期望订阅集合（断线重连后据此自动恢复订阅） */
const _desiredSubscriptions = new Set()

/** 当前已在 broker 上生效的订阅集合（销毁实例时清空，避免重复 SUBSCRIBE） */
const _activeSubscriptions = new Set()

/** DeviceStatusUpdate 全局回调列表（onDeviceUpdate 注册，返回注销函数） */
const _updateListeners = []

/** 连接状态回调列表（onConnectionChange 注册；重连成功后可重新拉取值） */
const _connListeners = []

/**
 * 在途连接 Promise（FND-005 修复）：发起连接时创建唯一 Promise，
 * 并发 acquire() 复用同一个并 await 它，彻底消除原 setInterval 轮询的竞态窗口
 * （并发场景偶发多次 CONNECT_FAILED reject）。null = 当前无在途连接。
 * @type {Promise<void>|null}
 */
let _connectPromise = null

/** 当前 broker/topics 配置（重连时复用） */
let _currentBroker = null
let _currentTopics = null

/** 自动重连定时器与当前退避时长 */
let _retryTimer = null
let _retryDelay = RETRY_BASE_MS

/** 主动销毁实例期间置真，避免 disconnect 触发的 close 事件又去排队重连 */
let _destroying = false

// ── 内部工具 ────────────────────────────────────────────────────────────────

function _onDeviceUpdateGlobal(parsed) {
  // 广播给所有注册的监听器
  for (const cb of _updateListeners) {
    try { cb(parsed) } catch (e) { console.error('[useMqttClient] listener error:', e) }
  }
}

/** 重连成功后恢复期望订阅（幂等：已生效的 mac 不重复 SUBSCRIBE） */
function _replaySubscriptions() {
  if (!_instance || !_connected.value) return
  for (const mac of _desiredSubscriptions) {
    if (_activeSubscriptions.has(mac)) continue
    try {
      _instance.subscribeRoom(mac)
      _activeSubscriptions.add(mac)
    } catch (e) {
      console.warn('[useMqttClient] 恢复订阅失败 mac=', mac, e && e.message)
    }
  }
}

function _setupInstance(broker, topics) {
  _instance = new ScreenMqtt(broker, topics)
  _instance.onDeviceUpdate(_onDeviceUpdateGlobal)
  _instance.onStateChange(_onInstanceState)
  _currentBroker = broker
  _currentTopics = topics
}

/** 连接状态变化回调：同步 UI 状态；连接成功恢复订阅；意外断线排队重连。 */
function _onInstanceState(next) {
  _connected.value = next
  if (next) {
    // 无论经由哪条路径连上（含 mqtt.js 内置重连），都取消待执行的退避重连，
    // 否则过期计时器会把刚恢复的健康连接拆掉重建
    _clearRetry()
    _retryDelay = RETRY_BASE_MS
    _replaySubscriptions()
  }
  for (const cb of (_destroying ? [] : _connListeners)) {
    try { cb(next) } catch (e) { console.error('[useMqttClient] conn listener error:', e) }
  }
  if (next) return
  // 正在 connects/主动销毁/页面已释放时不排队，避免无意义重连
  if (_connectPromise || _destroying || _refCount <= 0) return
  _scheduleRetry()
}

function _destroyInstance() {
  _activeSubscriptions.clear()
  if (!_instance) {
    _connected.value = false
    return
  }
  _destroying = true
  try { _instance.disconnect() } catch (e) { /* ignore */ }
  _instance = null
  _destroying = false
  _connected.value = false
}

function _clearRetry() {
  if (_retryTimer) {
    clearTimeout(_retryTimer)
    _retryTimer = null
  }
}

/** 按当前退避时长排队一次重连；失败则退避翻倍后继续。 */
function _scheduleRetry() {
  if (_retryTimer || _refCount <= 0 || !_currentBroker || _connectPromise) return
  const delay = _retryDelay
  console.log('[useMqttClient] 将在', delay, 'ms 后自动重连')
  _retryTimer = setTimeout(async () => {
    _retryTimer = null
    if (_refCount <= 0 || !_currentBroker || _connected.value) return
    try {
      await _connectOnce(_currentBroker, _currentTopics)
    } catch (e) {
      console.warn('[useMqttClient] 自动重连失败，继续退避:', e && e.message)
      _retryDelay = Math.min(_retryDelay * 2, RETRY_MAX_MS)
      _scheduleRetry()
    }
  }, delay)
}

/** 建立唯一在途连接（并发调用复用同一 Promise）。 */
function _connectOnce(broker, topics) {
  if (_connectPromise) return _connectPromise
  _connectPromise = (async () => {
    _destroyInstance()
    _setupInstance(broker, topics)
    await _instance.connect()
    _connected.value = true
    _retryDelay = RETRY_BASE_MS
    _replaySubscriptions()
  })()
  return _connectPromise
    .catch((e) => {
      _destroyInstance()
      throw e
    })
    .finally(() => { _connectPromise = null })
}

// ── 公开 composable 工厂 ─────────────────────────────────────────────────────

/**
 * 获取 MQTT 全局单例 composable 接口。
 * 所有消费方调用同一份函数，返回操作同一个模块级单例的方法集合。
 */
export function useMqttClient() {
  // 只读计算属性包装 _connected ref
  const connected = computed(() => _connected.value)

  /**
   * IFC-1110-FE-01-1: acquire
   * 增加引用计数；若引用计数从 0 升至 1，创建 ScreenMqtt 并 connect()。
   * 若已连接且 broker 配置相同，直接返回（幂等）。
   * 连接失败时进入指数退避自动重连，并向调用方抛出首次错误。
   * @param {object} broker - {protocol, host, port, path, username, password}
   * @param {object} topics - {value_uplink, write_downlink}
   * @returns {Promise<void>}
   */
  async function acquire(broker, topics) {
    _refCount = Math.max(0, _refCount) + 1
    if (_refCount === 1) _retryDelay = RETRY_BASE_MS
    console.log('[useMqttClient] acquire refCount=', _refCount)

    if (_instance && _connected.value) {
      // 已连接，直接复用（幂等）
      console.log('[useMqttClient] acquire: 已连接，复用单例')
      return
    }

    // 已有在途连接：复用同一 Promise（FND-005：并发 acquire 均 await 同一结果，
    // 不再各自轮询，消除竞态误判）。await 会随该连接的成功/失败一并 resolve/reject。
    if (_connectPromise) {
      console.log('[useMqttClient] acquire: 复用在途连接 Promise，等待...')
      await _connectPromise
      return
    }

    _clearRetry()
    try {
      await _connectOnce(broker, topics)
      console.log('[useMqttClient] acquire: 连接成功')
    } catch (e) {
      console.error('[useMqttClient] acquire: 连接失败:', e && e.message)
      _scheduleRetry()
      throw e
    }
  }

  /**
   * 补连：不改变引用计数，仅在“已持有引用但当前未连接”时立即重连。
   * 页面 onShow / 切回前台时调用，配合自动重连让链路可自愈。
   * @returns {Promise<void>}
   */
  async function ensureConnected() {
    if (_refCount <= 0 || _connected.value || !_currentBroker) return
    if (_connectPromise) {
      await _connectPromise
      return
    }
    _clearRetry()
    try {
      await _connectOnce(_currentBroker, _currentTopics)
      console.log('[useMqttClient] ensureConnected: 补连成功')
    } catch (e) {
      console.warn('[useMqttClient] ensureConnected: 补连失败:', e && e.message)
      _scheduleRetry()
      throw e
    }
  }

  /**
   * IFC-1110-FE-01-2: release
   * 减少引用计数；若降至 0，取消重连、调用 disconnect() 并清空单例。
   * _refCount 有下界保护（不降至负数）。
   */
  function release() {
    _refCount = Math.max(0, _refCount - 1)
    console.log('[useMqttClient] release refCount=', _refCount)
    if (_refCount === 0) {
      console.log('[useMqttClient] release: 引用计数归零，断开 MQTT')
      _clearRetry()
      _destroyInstance()
      _desiredSubscriptions.clear()
      _currentBroker = null
      _currentTopics = null
      _retryDelay = RETRY_BASE_MS
    }
  }

  /**
   * IFC-1110-FE-01-3: subscribe
   * 订阅 screenMac 的上行 topic（幂等）。未连接时登记，重连成功后自动补订阅。
   * @param {string} screenMac
   */
  function subscribe(screenMac) {
    if (!screenMac) return
    _desiredSubscriptions.add(screenMac)
    if (!_instance || !_connected.value) {
      console.warn('[useMqttClient] subscribe: 未连接，登记待重连后订阅 mac=', screenMac)
      return
    }
    if (_activeSubscriptions.has(screenMac)) {
      console.log('[useMqttClient] subscribe: 已订阅，跳过 mac=', screenMac)
      return
    }
    _instance.subscribeRoom(screenMac)
    _activeSubscriptions.add(screenMac)
    console.log('[useMqttClient] subscribe: 已订阅 mac=', screenMac)
  }

  /**
   * 取消订阅 screenMac（切换套户时调用），同时移出期望集合，重连后不再恢复。
   * @param {string} screenMac
   */
  function unsubscribe(screenMac) {
    if (!screenMac) return
    _desiredSubscriptions.delete(screenMac)
    if (!_activeSubscriptions.has(screenMac)) return
    _activeSubscriptions.delete(screenMac)
    if (_instance && _connected.value) {
      try { _instance.unsubscribeRoom(screenMac) } catch (e) { /* ignore */ }
    }
    console.log('[useMqttClient] unsubscribe: mac=', screenMac)
  }

  /**
   * IFC-1110-FE-01-4: publishRead
   * 向 screenMac 发布 DeviceStatusRead 消息（每个 deviceSn 一条）。
   * 对应 param-settings 现有 mqtt.readStatus(mac, sns)。
   * @param {string} screenMac
   * @param {string[]} deviceSns - 设备 SN 列表（字符串形式）
   */
  function publishRead(screenMac, deviceSns) {
    if (!_instance || !_connected.value) {
      console.warn('[useMqttClient] publishRead: 未连接，跳过 mac=', screenMac)
      return
    }
    _instance.readStatus(screenMac, deviceSns)
    console.log('[useMqttClient] publishRead: mac=', screenMac, 'sns=', deviceSns)
  }

  /**
   * IFC-1110-FE-01-5: publishWrite
   * 向 screenMac 发布 DeviceWrite 消息，返回 requestId。
   * 对应 param-settings 现有 mqtt.writeAttrs(mac, sn, items)。
   * @param {string} screenMac
   * @param {string} deviceSn
   * @param {Array<{attrTag: string, attrValue: unknown}>} items
   * @returns {string} requestId
   */
  function publishWrite(screenMac, deviceSn, items) {
    if (!_instance || !_connected.value) {
      console.warn('[useMqttClient] publishWrite: 未连接，跳过 mac=', screenMac)
      return ''
    }
    return _instance.writeAttrs(screenMac, deviceSn, items)
  }

  /**
   * IFC-1110-FE-01-6: waitConfirm
   * 等待 DeviceStatusUpdate 反映目标值（写确认），超时 reject。
   * 对应 param-settings 现有 mqtt.waitConfirm(sn, tag, val, ms)。
   * @param {string} deviceSn
   * @param {string} attrTag
   * @param {string} target
   * @param {number} [timeoutMs=8000]
   * @returns {Promise<boolean>}
   */
  function waitConfirm(deviceSn, attrTag, target, timeoutMs = 8000) {
    if (!_instance) return Promise.reject(new Error('MQTT_NOT_CONNECTED'))
    return _instance.waitConfirm(deviceSn, attrTag, target, timeoutMs)
  }

  /**
   * IFC-1110-FE-01-7: onDeviceUpdate
   * 注册 DeviceStatusUpdate 回调；返回注销函数。
   * @param {function} cb - (parsed: {deviceSn, productCode, attrs}) => void
   * @returns {function} 注销函数（调用后取消监听）
   */
  function onDeviceUpdate(cb) {
    // FND-006：去重注册——同一回调引用重复注册只保留一次，避免 off() 仅删首个导致泄漏
    if (_updateListeners.indexOf(cb) === -1) {
      _updateListeners.push(cb)
    }
    return function off() {
      const i = _updateListeners.indexOf(cb)
      if (i >= 0) _updateListeners.splice(i, 1)
    }
  }

  /**
   * 注册连接状态回调（true=已连接 / false=已断开，含自动重连结果）。
   * 页面可据此在重连成功后补订阅、重新发布 DeviceStatusRead。
   * @param {function} cb - (connected: boolean) => void
   * @returns {function} 注销函数
   */
  function onConnectionChange(cb) {
    if (typeof cb !== 'function') return () => {}
    if (_connListeners.indexOf(cb) === -1) _connListeners.push(cb)
    return function off() {
      const i = _connListeners.indexOf(cb)
      if (i >= 0) _connListeners.splice(i, 1)
    }
  }

  return {
    connected,
    acquire,
    ensureConnected,
    release,
    subscribe,
    unsubscribe,
    publishRead,
    publishWrite,
    waitConfirm,
    onDeviceUpdate,
    onConnectionChange,
  }
}

export default useMqttClient
