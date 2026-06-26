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
    const url = `${b.protocol}://${b.host}:${b.port}${b.path || ''}`
    return new Promise((resolve, reject) => {
      let settled = false
      this.client = mqtt.connect(url, {
        username: b.username,
        password: b.password,
        clientId: 'mp-owner-' + genRequestId(),
        keepalive: 30,
        reconnectPeriod: 3000,
        connectTimeout: 8000,
      })
      this.client.on('connect', () => {
        this._connected = true
        if (!settled) { settled = true; resolve() }
      })
      this.client.on('message', (topic, payload) => this._onMessage(topic, payload))
      this.client.on('error', (err) => {
        if (!settled) { settled = true; reject(err) }
      })
      this.client.on('close', () => { this._connected = false })
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
