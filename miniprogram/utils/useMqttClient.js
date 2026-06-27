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
 *   - _connected: Vue ref<boolean>，响应式连接状态
 *   - _activeSubscriptions: 已订阅的 screenMac 集合（订阅去重）
 *   - _updateListeners: DeviceStatusUpdate 全局回调列表
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

/** @type {ScreenMqtt|null} MQTT 客户端单例 */
let _instance = null

/** 活跃引用计数（acquire +1 / release -1） */
let _refCount = 0

/** 响应式连接状态（Vue ref，组件可直接 watch） */
const _connected = ref(false)

/** 已订阅的 screenMac 集合（幂等订阅去重） */
const _activeSubscriptions = new Set()

/** DeviceStatusUpdate 全局回调列表（onDeviceUpdate 注册，返回注销函数） */
const _updateListeners = []

/**
 * 在途连接 Promise（FND-005 修复）：发起连接时创建唯一 Promise，
 * 并发 acquire() 复用同一个并 await 它，彻底消除原 setInterval 轮询的竞态窗口
 * （并发场景偶发多次 CONNECT_FAILED reject）。null = 当前无在途连接。
 * @type {Promise<void>|null}
 */
let _connectPromise = null

/** 当前 broker/topics 配置（用于相同配置时跳过重新连接） */
let _currentBroker = null
let _currentTopics = null

// ── 内部工具 ────────────────────────────────────────────────────────────────

function _onDeviceUpdateGlobal(parsed) {
  // 广播给所有注册的监听器
  for (const cb of _updateListeners) {
    try { cb(parsed) } catch (e) { console.error('[useMqttClient] listener error:', e) }
  }
}

function _setupInstance(broker, topics) {
  _instance = new ScreenMqtt(broker, topics)
  _instance.onDeviceUpdate(_onDeviceUpdateGlobal)
  _currentBroker = broker
  _currentTopics = topics
}

function _teardown() {
  if (_instance) {
    try { _instance.disconnect() } catch (e) { /* ignore */ }
    _instance = null
  }
  _connected.value = false
  _activeSubscriptions.clear()
  _currentBroker = null
  _currentTopics = null
  _refCount = 0
  _connectPromise = null
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
   * @param {object} broker - {protocol, host, port, path, username, password}
   * @param {object} topics - {value_uplink, write_downlink}
   * @returns {Promise<void>}
   */
  async function acquire(broker, topics) {
    _refCount = Math.max(0, _refCount) + 1
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

    // 发起新连接：创建唯一在途 Promise 存入模块级变量，供并发 acquire 复用。
    _connectPromise = (async () => {
      if (_instance) {
        // 旧实例存在但未连接，清理后重建
        try { _instance.disconnect() } catch (e) { /* ignore */ }
        _instance = null
        _activeSubscriptions.clear()
      }
      _setupInstance(broker, topics)
      await _instance.connect()
      _connected.value = true
      console.log('[useMqttClient] acquire: 连接成功')
    })()

    try {
      await _connectPromise
    } catch (e) {
      console.error('[useMqttClient] acquire: 连接失败:', e && e.message)
      _teardown()   // 注意：_teardown 内会把 _connectPromise 置回 null
      throw e
    } finally {
      // 成功路径在此清空在途 Promise（失败路径已由 _teardown 清空，重复赋 null 无害）
      _connectPromise = null
    }
  }

  /**
   * IFC-1110-FE-01-2: release
   * 减少引用计数；若降至 0，调用 disconnect() 并清空单例。
   * _refCount 有下界保护（不降至负数）。
   */
  function release() {
    _refCount = Math.max(0, _refCount - 1)
    console.log('[useMqttClient] release refCount=', _refCount)
    if (_refCount === 0) {
      console.log('[useMqttClient] release: 引用计数归零，断开 MQTT')
      _teardown()
    }
  }

  /**
   * IFC-1110-FE-01-3: subscribe
   * 订阅 screenMac 的上行 topic（幂等：已订阅则跳过）。
   * @param {string} screenMac
   */
  function subscribe(screenMac) {
    if (!_instance || !_connected.value) {
      console.warn('[useMqttClient] subscribe: 未连接，跳过订阅 mac=', screenMac)
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

  return {
    connected,
    acquire,
    release,
    subscribe,
    publishRead,
    publishWrite,
    waitConfirm,
    onDeviceUpdate,
  }
}

export default useMqttClient
