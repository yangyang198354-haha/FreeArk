/**
 * @module MOD-SCREEN-MQTT
 * @description 屏端 MQTT 直连封装（v1.10.0_miniprogram_param_settings）。
 *   业主小程序直连厂端 broker（wxs://），订阅设备值推送、发布写命令。
 *   架构 ADR-01/02/03/04：直连、屏端自描述、mqtt.js wxs、写确认靠值反映（无独立 ack）。
 *
 *   纯逻辑函数（normalizeSn / parseDeviceUpdate / buildWriteItems / buildDeviceWrite /
 *   valueReflectsTarget）与 MQTT IO 解耦，便于 vitest 单测（不依赖真实 broker）。
 *
 *   实测协议（capture_findings_oq03.md）：
 *     写命令 DeviceWrite → topic /screen/service/cloud/to/screen/{screenMac}
 *     值推送 DeviceStatusUpdate → topic /screen/upload/screen/to/cloud/{screenMac}
 *     deviceSn 在 DeviceWrite 为字符串、DeviceStatusUpdate 为整数 → 统一归一为 String。
 */

import mqtt from 'mqtt/dist/mqtt.js'
import { buildUniStream } from './uniMqttStream'

// ── 纯逻辑（可单测）──────────────────────────────────────────────────────────

/** deviceSn 归一为字符串（写命令字符串 / 状态推送整数）。 */
export function normalizeSn(sn) {
  return sn === null || sn === undefined ? '' : String(sn)
}

/** 解析一条 DeviceStatusUpdate，返回 {deviceSn, productCode, attrs:{tag:val}} 或 null。 */
export function parseDeviceUpdate(payloadObj) {
  if (!payloadObj || typeof payloadObj !== 'object') return null
  const header = payloadObj.header || {}
  if (header.name !== 'DeviceStatusUpdate') return null
  const data = (payloadObj.payload && payloadObj.payload.data) || payloadObj.data || {}
  const sn = normalizeSn(data.deviceSn)
  if (!sn) return null
  const attrs = {}
  for (const it of data.items || []) {
    if (it && it.attrTag != null) attrs[String(it.attrTag)] = it.attrValue
  }
  return { deviceSn: sn, productCode: data.productCode != null ? Number(data.productCode) : null, attrs }
}

/**
 * 构造写 items。系统/能源主机改 mode 时联动追加 energy_supply_mode（ADR-08）。
 * @param productCode 设备 productCode（判断是否联动）
 * @param attrTag/attrValue 主改属性
 * @param config 后端下发 config（mode_energy_link / link_product_codes）
 */
export function buildWriteItems(productCode, attrTag, attrValue, config) {
  const items = [{ attrTag, attrValue }]
  const linkCodes = (config && config.link_product_codes) || []
  const linkMap = (config && config.mode_energy_link) || {}
  if (attrTag === 'mode' && linkCodes.includes(Number(productCode)) && linkMap[attrValue] != null) {
    items.push({ attrTag: 'energy_supply_mode', attrValue: linkMap[attrValue] })
  }
  return items
}

/** 构造 DeviceWrite envelope（云→屏）。requestId 放 payload.data 供本端审计关联（屏端忽略未知字段）。 */
export function buildDeviceWrite(screenMac, deviceSn, items, requestId) {
  return {
    header: {
      name: 'DeviceWrite',
      messageId: String(Date.now()),
      sn: normalizeSn(deviceSn),
      screenMac,
    },
    payload: {
      code: 200,
      message: '',
      data: { deviceSn: normalizeSn(deviceSn), requestId, items },
    },
  }
}

/** 构造 DeviceStatusRead envelope（云→屏，主动拉取当前值）。屏端会回一条 DeviceStatusUpdate。 */
export function buildDeviceRead(screenMac, deviceSn) {
  return {
    header: {
      name: 'DeviceStatusRead',
      messageId: String(Date.now()),
      sn: normalizeSn(deviceSn),
      screenMac,
    },
    payload: { data: { deviceSn: normalizeSn(deviceSn) } },
  }
}

/** 判断一条 DeviceStatusUpdate 是否反映了目标值（写确认，ADR-04）。 */
export function valueReflectsTarget(payloadObj, deviceSn, attrTag, target) {
  const parsed = parseDeviceUpdate(payloadObj)
  if (!parsed || parsed.deviceSn !== normalizeSn(deviceSn)) return false
  return String(parsed.attrs[attrTag]) === String(target)
}

/** 简易 uuid（无外部依赖，够审计关联用）。 */
export function genRequestId() {
  return 'mp-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10)
}

function fillTopic(tpl, screenMac) {
  return tpl.replace('{screenMac}', screenMac)
}

// ── MQTT IO 封装 ─────────────────────────────────────────────────────────────

export class ScreenMqtt {
  constructor(broker, topics) {
    this.broker = broker          // {protocol,host,port,path,username,password}
    this.topics = topics          // {value_uplink, write_downlink}（含 {screenMac} 占位）
    this.client = null
    this._updateCbs = []
    this._connected = false
  }

  connect() {
    const b = this.broker
    // 直接用自定义 uni.connectSocket 流构造 MqttClient，绕开 mqtt.js v4 在
    // uni-app+vite 微信小程序里全不可用的自带传输（wx.js / ws.js / 协议探测）。
    const opts = {
      protocol: b.protocol,        // 'wxs'（buildUniStream 内部映射 wss）
      hostname: b.host,
      host: b.host,
      port: b.port,
      path: b.path || '/mqtt',
      username: b.username,
      password: b.password,
      clientId: 'mp-owner-' + genRequestId(),
      keepalive: 30,
      reconnectPeriod: 3000,
      connectTimeout: 8000,
      clean: true,
      protocolId: 'MQTT',
      protocolVersion: 4,
    }
    console.log('[ScreenMqtt] connect (custom uni stream) host=', b.host, 'user=', b.username)
    return new Promise((resolve, reject) => {
      let settled = false
      const finish = (fn, arg) => { if (!settled) { settled = true; fn(arg) } }
      const hardTimer = setTimeout(() => {
        console.error('[ScreenMqtt] HARD TIMEOUT 12s — 未收到 CONNACK')
        try { this.client && this.client.end(true) } catch (e) { /* ignore */ }
        finish(reject, new Error('CONNECT_TIMEOUT'))
      }, 12000)

      this.client = new mqtt.MqttClient(buildUniStream(opts), opts)
      this.client.on('connect', () => {
        console.log('[ScreenMqtt] event: connect (CONNACK ok)')
        this._connected = true
        clearTimeout(hardTimer)
        finish(resolve)
      })
      this.client.on('message', (topic, payload) => this._onMessage(topic, payload))
      this.client.on('error', (err) => {
        console.error('[ScreenMqtt] event: error ->', err && err.message)
        clearTimeout(hardTimer)
        finish(reject, err)
      })
      this.client.on('reconnect', () => console.log('[ScreenMqtt] event: reconnect'))
      this.client.on('offline', () => console.warn('[ScreenMqtt] event: offline'))
      this.client.on('close', () => {
        console.warn('[ScreenMqtt] event: close')
        this._connected = false
      })
    })
  }

  subscribeRoom(screenMac) {
    if (!this.client) return
    this.client.subscribe(fillTopic(this.topics.value_uplink, screenMac), { qos: 0 })
  }

  onDeviceUpdate(cb) { this._updateCbs.push(cb) }

  _onMessage(topic, payload) {
    let obj = null
    try { obj = JSON.parse(payload.toString()) } catch (e) { return }
    const parsed = parseDeviceUpdate(obj)
    if (parsed) this._updateCbs.forEach((cb) => cb(parsed))
  }

  /** 主动拉取一批 deviceSn 的当前值（发 DeviceStatusRead，屏端会回 DeviceStatusUpdate）。 */
  readStatus(screenMac, deviceSns) {
    if (!this.client) return
    const topic = fillTopic(this.topics.write_downlink, screenMac)
    for (const sn of deviceSns) {
      const msg = buildDeviceRead(screenMac, sn)
      this.client.publish(topic, JSON.stringify(msg), { qos: 0 })
    }
  }

  /** 发布写命令，返回 requestId。 */
  writeAttrs(screenMac, deviceSn, items) {
    const requestId = genRequestId()
    const msg = buildDeviceWrite(screenMac, deviceSn, items, requestId)
    const topic = fillTopic(this.topics.write_downlink, screenMac)
    this.client.publish(topic, JSON.stringify(msg), { qos: 0 })
    return requestId
  }

  /**
   * 等待写确认：监听目标 deviceSn 的下一条 DeviceStatusUpdate 是否反映 target。
   * 无独立 ack（ADR-04）；超时 reject。
   */
  waitConfirm(deviceSn, attrTag, target, timeoutMs = 8000) {
    return new Promise((resolve, reject) => {
      const handler = (parsed) => {
        if (parsed.deviceSn === normalizeSn(deviceSn) &&
            String(parsed.attrs[attrTag]) === String(target)) {
          cleanup(); resolve(true)
        }
      }
      const timer = setTimeout(() => { cleanup(); reject(new Error('CONFIRM_TIMEOUT')) }, timeoutMs)
      const cleanup = () => {
        clearTimeout(timer)
        const i = this._updateCbs.indexOf(handler)
        if (i >= 0) this._updateCbs.splice(i, 1)
      }
      this._updateCbs.push(handler)
    })
  }

  get connected() { return this._connected }

  disconnect() {
    if (this.client) {
      try { this.client.end(true) } catch (e) { /* ignore */ }
      this.client = null
    }
    this._updateCbs = []
    this._connected = false
  }
}

export default ScreenMqtt
