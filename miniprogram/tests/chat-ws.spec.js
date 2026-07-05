import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ChatWebSocket } from '@/utils/chat-ws'

// 伪 SocketTask：捕获 onOpen/onMessage/onClose/onError 回调，便于模拟服务端帧
function makeFakeSocket() {
  const h = {}
  return {
    onOpen: (cb) => { h.open = cb },
    onMessage: (cb) => { h.message = cb },
    onClose: (cb) => { h.close = cb },
    onError: (cb) => { h.error = cb },
    send: vi.fn(),
    close: vi.fn(),
    // 测试辅助：模拟收到一帧
    emitFrame: (frame) => h.message && h.message({ data: JSON.stringify(frame) }),
    emitClose: (code) => h.close && h.close({ code }),
  }
}

describe('utils/chat-ws ChatWebSocket（协议复刻）', () => {
  let socket
  beforeEach(() => {
    socket = makeFakeSocket()
    uni.connectSocket = vi.fn(() => socket)
  })

  it('connect: token 走 query param，含 session_key', () => {
    const ws = new ChatWebSocket({})
    ws.connect('TOK', 'SESS')
    const url = uni.connectSocket.mock.calls[0][0].url
    expect(url).toContain('/ws/miniapp/chat/?token=TOK')
    expect(url).toContain('session_key=SESS')
  })

  it('connected 帧（非 onOpen）才置 connected 并回调', () => {
    const onConnected = vi.fn()
    const ws = new ChatWebSocket({ onConnected })
    ws.connect('TOK')
    expect(ws.connected).toBe(false) // onOpen 不置连
    socket.emitFrame({ type: 'connected', session_key: 'k', session_id: 'i' })
    expect(ws.connected).toBe(true)
    expect(onConnected).toHaveBeenCalledWith('k', 'i', null, { is_bound: false, rooms: [], active_room: null })
  })

  it('各帧类型分发到对应回调', () => {
    const cbs = {
      onStatusUpdate: vi.fn(), onReasoningToken: vi.fn(), onReasoningEnd: vi.fn(),
      onToken: vi.fn(), onStreamEnd: vi.fn(), onConfirmRequired: vi.fn(), onError: vi.fn(),
    }
    const ws = new ChatWebSocket(cbs)
    ws.connect('TOK')
    socket.emitFrame({ type: 'status_update', message: 'm' })
    socket.emitFrame({ type: 'reasoning_token', token: 'r' })
    socket.emitFrame({ type: 'reasoning_end' })
    socket.emitFrame({ type: 'stream_token', token: 'hi' })
    socket.emitFrame({ type: 'stream_end' })
    socket.emitFrame({ type: 'confirm_required', actions: [{ x: 1 }] })
    socket.emitFrame({ type: 'error', message: 'boom' })
    expect(cbs.onStatusUpdate).toHaveBeenCalledWith('m')
    expect(cbs.onReasoningToken).toHaveBeenCalledWith('r')
    expect(cbs.onReasoningEnd).toHaveBeenCalled()
    expect(cbs.onToken).toHaveBeenCalledWith('hi')
    expect(cbs.onStreamEnd).toHaveBeenCalled()
    expect(cbs.onConfirmRequired).toHaveBeenCalledWith([{ x: 1 }])
    expect(cbs.onError).toHaveBeenCalled()
  })

  it('send 仅在 connected 时发送 chat_message 帧', () => {
    const ws = new ChatWebSocket({})
    ws.connect('TOK')
    ws.send('hello')
    expect(socket.send).not.toHaveBeenCalled() // 未连接不发
    socket.emitFrame({ type: 'connected' })
    ws.send('hello')
    expect(socket.send).toHaveBeenCalledWith({ data: JSON.stringify({ type: 'chat_message', message: 'hello' }) })
  })

  it('sendConfirm 发送 confirm_response 帧', () => {
    const ws = new ChatWebSocket({})
    ws.connect('TOK')
    ws.sendConfirm(true)
    expect(socket.send).toHaveBeenCalledWith({ data: JSON.stringify({ type: 'confirm_response', approved: true }) })
  })

  it('onClose 回调透传 code（如 4001 鉴权失败）', () => {
    const onClose = vi.fn()
    const ws = new ChatWebSocket({ onClose })
    ws.connect('TOK')
    socket.emitFrame({ type: 'connected' })
    socket.emitClose(4001)
    expect(ws.connected).toBe(false)
    expect(onClose).toHaveBeenCalledWith(4001)
  })

  it('close 调用 socketTask.close 并复位', () => {
    const ws = new ChatWebSocket({})
    ws.connect('TOK')
    socket.emitFrame({ type: 'connected' })
    ws.close()
    expect(socket.close).toHaveBeenCalled()
    expect(ws.connected).toBe(false)
  })
})

// ============================================================================
// MOD-002 EXTEND: sendMultimedia (IFC-002-05) — TC-UNIT-016 ~ TC-UNIT-020
// ============================================================================
describe('utils/chat-ws — sendMultimedia 多媒体发送', () => {
  let socket
  let ws

  beforeEach(() => {
    socket = makeFakeSocket()
    uni.connectSocket = vi.fn(() => socket)
    ws = new ChatWebSocket({})
    ws.connect('TOK')
    socket.emitFrame({ type: 'connected' }) // establish connection
  })

  // TC-UNIT-016: Normal frame format
  it('TC-UNIT-016: 正常帧格式 {type:chat_multimedia, media:[{type:image,url:...}]}', () => {
    const mediaList = [{ type: 'image', url: 'https://example.com/img1.jpg' }]
    ws.sendMultimedia(mediaList)

    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData).toEqual({
      type: 'chat_multimedia',
      media: [{ type: 'image', url: 'https://example.com/img1.jpg' }],
    })
  })

  // TC-UNIT-017: Empty array
  it('TC-UNIT-017: 空数组 → 不发送', () => {
    ws.sendMultimedia([])
    expect(socket.send).not.toHaveBeenCalled()
  })

  // TC-UNIT-018: Non-array parameter
  it('TC-UNIT-018: 非数组参数 → 不发送', () => {
    ws.sendMultimedia('not-an-array')
    expect(socket.send).not.toHaveBeenCalled()
  })

  it('TC-UNIT-018-b: null参数 → 不发送', () => {
    ws.sendMultimedia(null)
    expect(socket.send).not.toHaveBeenCalled()
  })

  // TC-UNIT-019: Not connected
  it('TC-UNIT-019: 未连接状态(connected=false) → 不发送', () => {
    ws.close() // disconnect
    ws.sendMultimedia([{ type: 'image', url: 'test.jpg' }])
    expect(socket.send).not.toHaveBeenCalled()
  })

  // TC-UNIT-020: Multiple media items
  it('TC-UNIT-020: 多个媒体项 → 全部包含在media数组中', () => {
    const mediaList = [
      { type: 'image', url: 'https://example.com/img1.jpg' },
      { type: 'image', url: 'https://example.com/img2.jpg' },
    ]
    ws.sendMultimedia(mediaList)

    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData.type).toBe('chat_multimedia')
    expect(sentData.media).toHaveLength(2)
    expect(sentData.media[0].url).toBe('https://example.com/img1.jpg')
    expect(sentData.media[1].url).toBe('https://example.com/img2.jpg')
  })

  // Bonus: media items with extra fields (text) are mapped correctly
  it('media项额外字段(如text)不出现在输出帧中(仅映射type和url)', () => {
    const mediaList = [
      { type: 'image', url: 'test.jpg', text: 'extra', other: 'field' },
    ]
    ws.sendMultimedia(mediaList)

    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData.media[0]).toEqual({ type: 'image', url: 'test.jpg' })
    expect(sentData.media[0].text).toBeUndefined()
  })

  // Bonus: backward compatibility — send() is unchanged
  it('send()保持不变 — chat_message文本帧格式不变', () => {
    ws.send('hello world')

    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData).toEqual({ type: 'chat_message', message: 'hello world' })
  })
})
