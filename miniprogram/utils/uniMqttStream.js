/**
 * @module MOD-UNI-MQTT-STREAM
 * @description 基于 uni.connectSocket 的 mqtt.js 流构造器（v1.10.0 终极修复）。
 *
 *   mqtt.js v4 自带传输在 uni-app + vite 微信小程序里全不可用（wx.js 连上即 offline；
 *   ws.js 依赖取不到的全局 WebSocket；协议探测误判为 Node net.createConnection）。
 *   而改用 readable-stream/duplexify 自建流又会拉入 events/process 等 Node 内建，
 *   小程序未 polyfill → "process is not defined" 启动崩溃。
 *
 *   故本模块**零 Node 依赖**手写一个 mqtt.js 需要的最小 duplex：内联事件发射器、
 *   底层用原生 uni.connectSocket（实测可正常握手该 broker），socket 未 open 前的
 *   写入先缓存、open 后按序 flush，收到的二进制以 Buffer 向上游（mqtt-packet 解析器）push。
 *
 *   mqtt 对 stream 的用法：write（mqtt-packet 每包多次小写）、pipe(writable)、
 *   on/once、end、destroy、removeListener、setMaxListeners。
 */
import { Buffer } from 'buffer'

// 内联最小 EventEmitter（避免引入 Node 'events' → 连带 process polyfill 崩溃）
class Emitter {
  constructor () { this._h = Object.create(null) }
  on (t, f) { (this._h[t] || (this._h[t] = [])).push(f); return this }
  addListener (t, f) { return this.on(t, f) }
  prependListener (t, f) { (this._h[t] || (this._h[t] = [])).unshift(f); return this }
  once (t, f) { const g = (...a) => { this.removeListener(t, g); f(...a) }; g._o = f; return this.on(t, g) }
  removeListener (t, f) {
    const a = this._h[t]; if (a) { const i = a.findIndex((x) => x === f || x._o === f); if (i >= 0) a.splice(i, 1) }
    return this
  }
  removeAllListeners (t) { if (t) delete this._h[t]; else this._h = Object.create(null); return this }
  emit (t, ...a) {
    const a2 = (this._h[t] || []).slice()
    a2.forEach((f) => { try { f(...a) } catch (e) { console.error('[uniMqttStream] listener err', e) } })
    return a2.length > 0
  }
  listeners (t) { return (this._h[t] || []).slice() }
  listenerCount (t) { return (this._h[t] || []).length }
  eventNames () { return Object.keys(this._h) }
  setMaxListeners () { return this }
  getMaxListeners () { return 1000 }
}

/**
 * 返回 mqtt.js 期望的 streamBuilder：`function(client) -> duplexStream`。
 * @param {Object} opts 连接选项（protocol/hostname/port/path/protocolId/protocolVersion）
 */
export function buildUniStream (opts) {
  return function streamBuilder (/* client */) {
    const proto = opts.protocol === 'wxs' ? 'wss' : (opts.protocol === 'wx' ? 'ws' : opts.protocol)
    const url = proto + '://' + opts.hostname + ':' + opts.port + (opts.path || '')
    const subProtocol = (opts.protocolId === 'MQIsdp' && opts.protocolVersion === 3) ? 'mqttv3.1' : 'mqtt'
    console.log('[uniMqttStream] connectSocket ->', url, 'sub=', subProtocol)

    const stream = new Emitter()
    let opened = false
    let destroyed = false
    let outbox = []        // 待发送的字节块（Uint8Array），合并成一帧再发
    let flushScheduled = false

    // eslint-disable-next-line no-undef
    const socketTask = uni.connectSocket({ url, protocols: [subProtocol], tcpNoDelay: true, complete: () => {} })

    // 合并写：mqtt-packet 把一个 MQTT 包拆成多次小 write（header/len/payload），
    // 必须合并成**一个完整帧**再 send，否则 broker 收到碎片帧会断开（实测 onClose 1000）。
    function flush () {
      flushScheduled = false
      if (!opened || destroyed || outbox.length === 0) return
      let total = 0
      for (let i = 0; i < outbox.length; i++) total += outbox[i].byteLength
      const merged = new Uint8Array(total)
      let off = 0
      for (let i = 0; i < outbox.length; i++) { merged.set(outbox[i], off); off += outbox[i].byteLength }
      outbox = []
      try { socketTask.send({ data: merged.buffer }) } catch (e) { stream.emit('error', e) }
    }
    function scheduleFlush () {
      if (flushScheduled) return
      flushScheduled = true
      Promise.resolve().then(flush)   // 同一宏任务内的多次 write 合并为一帧
    }

    socketTask.onOpen(function () {
      opened = true
      console.log('[uniMqttStream] onOpen ✅ flush', outbox.length, 'chunks')
      flush()
      stream.emit('connect')   // 部分 mqtt 路径会等 stream 'connect' 后再发 CONNECT
    })
    socketTask.onMessage(function (res) {
      let d = res && res.data
      d = (d instanceof ArrayBuffer) ? Buffer.from(d) : Buffer.from(String(d == null ? '' : d), 'utf8')
      stream.emit('data', d)
    })
    socketTask.onClose(function (res) {
      console.warn('[uniMqttStream] onClose', res && res.code, res && res.reason)
      stream.emit('close')
    })
    socketTask.onError(function (res) {
      console.error('[uniMqttStream] onError ❌', res && res.errMsg)
      stream.emit('error', new Error((res && res.errMsg) || 'socket error'))
    })

    // —— mqtt 写出：mqtt-packet 每包多次 write（header/length/payload），入队合并 ——
    stream.write = function (chunk, encOrCb, cb) {
      if (typeof encOrCb === 'function') { cb = encOrCb }
      let u
      if (chunk instanceof ArrayBuffer) u = new Uint8Array(chunk)
      else if (chunk && chunk.buffer instanceof ArrayBuffer && typeof chunk.byteOffset === 'number') {
        u = new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength) // 精确视图，勿带整个缓冲池
      } else if (typeof chunk === 'string') {
        u = new Uint8Array(Buffer.from(chunk, 'utf8'))
      } else { u = new Uint8Array(chunk) }
      outbox.push(u)
      scheduleFlush()
      if (cb) cb()
      return true   // 恒返回 true → mqtt-packet 不会等 'drain'
    }

    // —— mqtt 读入：stream.pipe(mqtt 的 Writable 解析器) ——
    stream.pipe = function (dest) {
      stream.on('data', (c) => { try { dest.write(c) } catch (e) { /* ignore */ } })
      stream.on('end', () => { if (dest && typeof dest.end === 'function') dest.end() })
      return dest
    }

    stream.end = function (chunk, encOrCb, cb) {
      if (chunk && chunk !== undefined && typeof chunk !== 'function') stream.write(chunk)
      const done = (typeof encOrCb === 'function') ? encOrCb : cb
      try { socketTask.close({}) } catch (e) { /* ignore */ }
      if (done) done()
      return stream
    }
    stream.destroy = function (err) {
      if (destroyed) return stream
      destroyed = true
      try { socketTask.close({}) } catch (e) { /* ignore */ }
      if (err) stream.emit('error', err)
      stream.emit('close')
      return stream
    }

    return stream
  }
}

export default buildUniStream
