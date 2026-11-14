/**
 * useMqttClient 连接自愈单测（FND-007）。
 * 用可控的 FakeScreenMqtt 替换真实 ScreenMqtt，配合 fake timers 验证：
 *   指数退避重连、重连后恢复订阅、过期重连计时器不拆健康连接、
 *   ensureConnected 补连、release 取消重连、unsubscribe 不再恢复旧订阅、
 *   onConnectionChange 通知。
 * 模块级单例状态跨用例共享，故每个用例 vi.resetModules() 后重新 import。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const h = vi.hoisted(() => ({ instances: [], plan: [] }))

vi.mock('../utils/screenMqtt', () => {
  class FakeScreenMqtt {
    constructor(broker, topics) {
      this.broker = broker
      this.topics = topics
      this._connected = false
      this._stateCbs = []
      this._updateCbs = []
      this.subscribeRoom = vi.fn()
      this.unsubscribeRoom = vi.fn()
      this.readStatus = vi.fn()
      this.disconnected = false
      h.instances.push(this)
    }
    onStateChange(cb) { this._stateCbs.push(cb) }
    onDeviceUpdate(cb) { this._updateCbs.push(cb) }
    _setConnected(next) {
      if (this._connected === next) return
      this._connected = next
      this._stateCbs.slice().forEach((cb) => cb(next))
    }
    /** 按 h.plan 依次决定本次连接结果：'ok' | 'fail'（缺省 'ok'） */
    connect() {
      const outcome = h.plan.length ? h.plan.shift() : 'ok'
      if (outcome === 'fail') return Promise.reject(new Error('CONNECT_TIMEOUT'))
      this._setConnected(true)
      return Promise.resolve()
    }
    disconnect() {
      this.disconnected = true
      this._updateCbs = []
      this._setConnected(false)
    }
    get connected() { return this._connected }
  }
  return { ScreenMqtt: FakeScreenMqtt, default: FakeScreenMqtt }
})

const BROKER = { protocol: 'wxs', host: 'b.example', port: 443 }
const TOPICS = { value_uplink: 'up/{screenMac}', write_downlink: 'down/{screenMac}' }

let useMqttClient
const last = () => h.instances[h.instances.length - 1]

beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  h.instances.length = 0
  h.plan.length = 0
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
  ;({ useMqttClient } = await import('../utils/useMqttClient'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('acquire / 首连失败自愈', () => {
  it('首连失败抛错，3s 后自动重连成功并恢复期望订阅', async () => {
    const c = useMqttClient()
    h.plan.push('fail')
    c.subscribe('macA') // 未连接：仅登记
    await expect(c.acquire(BROKER, TOPICS)).rejects.toThrow('CONNECT_TIMEOUT')
    expect(c.connected.value).toBe(false)
    expect(h.instances).toHaveLength(1)
    expect(h.instances[0].disconnected).toBe(true)

    await vi.advanceTimersByTimeAsync(2999)
    expect(h.instances).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(h.instances).toHaveLength(2)
    expect(c.connected.value).toBe(true)
    expect(last().subscribeRoom).toHaveBeenCalledWith('macA')
  })

  it('连续失败按 3s→6s→12s 翻倍退避，60s 封顶', async () => {
    const c = useMqttClient()
    h.plan.push('fail', 'fail', 'fail', 'fail', 'fail', 'fail', 'fail')
    await expect(c.acquire(BROKER, TOPICS)).rejects.toThrow()

    const delays = [3000, 6000, 12000, 24000, 48000, 60000]
    for (const d of delays) {
      const before = h.instances.length
      await vi.advanceTimersByTimeAsync(d - 1)
      expect(h.instances.length).toBe(before)
      await vi.advanceTimersByTimeAsync(1)
      expect(h.instances.length).toBe(before + 1)
    }
    // 第 8 次（plan 已空 → 成功）同样是 60s 封顶
    await vi.advanceTimersByTimeAsync(60000)
    expect(c.connected.value).toBe(true)
  })

  it('并发 acquire 复用同一在途连接，只建一个实例', async () => {
    const a = useMqttClient()
    const b = useMqttClient()
    await Promise.all([a.acquire(BROKER, TOPICS), b.acquire(BROKER, TOPICS)])
    expect(h.instances).toHaveLength(1)
    expect(a.connected.value).toBe(true)
  })
})

describe('中途断线', () => {
  it('意外断线后排队重连，并重新订阅', async () => {
    const c = useMqttClient()
    await c.acquire(BROKER, TOPICS)
    c.subscribe('macA')
    const first = last()
    expect(first.subscribeRoom).toHaveBeenCalledTimes(1)

    first._setConnected(false) // 模拟 close/offline
    expect(c.connected.value).toBe(false)
    await vi.advanceTimersByTimeAsync(3000)
    expect(h.instances).toHaveLength(2)
    expect(first.disconnected).toBe(true)
    expect(c.connected.value).toBe(true)
    expect(last().subscribeRoom).toHaveBeenCalledWith('macA')
  })

  it('mqtt.js 内置重连先恢复时，取消过期的退避计时器，不拆健康连接', async () => {
    const c = useMqttClient()
    await c.acquire(BROKER, TOPICS)
    const inst = last()

    inst._setConnected(false) // 断线 → 排队 3s 重连
    inst._setConnected(true)  // mqtt.js 内置重连抢先成功
    await vi.advanceTimersByTimeAsync(120000)

    expect(h.instances).toHaveLength(1)
    expect(inst.disconnected).toBe(false)
    expect(c.connected.value).toBe(true)
  })
})

describe('ensureConnected', () => {
  it('已持有引用且未连接时立即补连并取消待执行的退避', async () => {
    const c = useMqttClient()
    h.plan.push('fail')
    await expect(c.acquire(BROKER, TOPICS)).rejects.toThrow()

    await c.ensureConnected()
    expect(h.instances).toHaveLength(2)
    expect(c.connected.value).toBe(true)
    await vi.advanceTimersByTimeAsync(60000)
    expect(h.instances).toHaveLength(2)
  })

  it('已连接或未 acquire 时为 no-op', async () => {
    const c = useMqttClient()
    await c.ensureConnected()
    expect(h.instances).toHaveLength(0)
    await c.acquire(BROKER, TOPICS)
    await c.ensureConnected()
    expect(h.instances).toHaveLength(1)
  })

  it('补连失败后继续退避重试', async () => {
    const c = useMqttClient()
    h.plan.push('fail', 'fail')
    await expect(c.acquire(BROKER, TOPICS)).rejects.toThrow()
    await expect(c.ensureConnected()).rejects.toThrow()
    await vi.advanceTimersByTimeAsync(3000)
    expect(c.connected.value).toBe(true)
  })
})

describe('release', () => {
  it('引用计数归零取消重连并断开', async () => {
    const c = useMqttClient()
    h.plan.push('fail')
    await expect(c.acquire(BROKER, TOPICS)).rejects.toThrow()
    c.release()
    await vi.advanceTimersByTimeAsync(120000)
    expect(h.instances).toHaveLength(1)
    expect(c.connected.value).toBe(false)
  })

  it('主动断开不触发重连，也不通知连接监听', async () => {
    const c = useMqttClient()
    const cb = vi.fn()
    c.onConnectionChange(cb)
    await c.acquire(BROKER, TOPICS)
    cb.mockClear()
    c.release()
    await vi.advanceTimersByTimeAsync(120000)
    expect(cb).not.toHaveBeenCalled()
    expect(h.instances).toHaveLength(1)
  })
})

describe('subscribe / unsubscribe', () => {
  it('已生效订阅幂等，不重复 SUBSCRIBE', async () => {
    const c = useMqttClient()
    await c.acquire(BROKER, TOPICS)
    c.subscribe('macA')
    c.subscribe('macA')
    expect(last().subscribeRoom).toHaveBeenCalledTimes(1)
  })

  it('unsubscribe 退订并移出期望集合，重连后不再恢复', async () => {
    const c = useMqttClient()
    await c.acquire(BROKER, TOPICS)
    c.subscribe('macA')
    c.subscribe('macB')
    c.unsubscribe('macA')
    expect(last().unsubscribeRoom).toHaveBeenCalledWith('macA')

    last()._setConnected(false)
    await vi.advanceTimersByTimeAsync(3000)
    const subs = last().subscribeRoom.mock.calls.map((x) => x[0])
    expect(subs).toEqual(['macB'])
  })

  it('未连接时 unsubscribe 仅移出期望集合', async () => {
    const c = useMqttClient()
    c.subscribe('macA')
    c.unsubscribe('macA')
    await c.acquire(BROKER, TOPICS)
    expect(last().subscribeRoom).not.toHaveBeenCalled()
    expect(last().unsubscribeRoom).not.toHaveBeenCalled()
  })
})

describe('onConnectionChange', () => {
  it('连接成功/断线时通知，注销后不再通知', async () => {
    const c = useMqttClient()
    const cb = vi.fn()
    const off = c.onConnectionChange(cb)
    await c.acquire(BROKER, TOPICS)
    expect(cb).toHaveBeenLastCalledWith(true)
    last()._setConnected(false)
    expect(cb).toHaveBeenLastCalledWith(false)
    off()
    await vi.advanceTimersByTimeAsync(3000)
    expect(cb).toHaveBeenCalledTimes(2)
  })

  it('连接成功回调触发时期望订阅已恢复（页面可直接 publishRead）', async () => {
    const c = useMqttClient()
    c.subscribe('macA')
    let subscribedAtCb = null
    c.onConnectionChange((ok) => {
      if (ok) subscribedAtCb = last().subscribeRoom.mock.calls.length
    })
    await c.acquire(BROKER, TOPICS)
    expect(subscribedAtCb).toBe(1)
  })
})
