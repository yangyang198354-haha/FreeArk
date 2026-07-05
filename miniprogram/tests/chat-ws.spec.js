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
// MOD-002 EXTEND: sendWithImages (IFC-002-05) — TC-UNIT-016 ~ TC-UNIT-020
// Sends chat_message + image_upload_ids to match backend consumers.py protocol
// ============================================================================
describe('utils/chat-ws — sendWithImages 图文发送', () => {
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
  it('TC-UNIT-016: 正常帧格式 {type:chat_message, message, image_upload_ids:[...]}', () => {
    const uploadIds = ['uuid-1234-abcd']
    ws.sendWithImages('描述文字', uploadIds)

    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData).toEqual({
      type: 'chat_message',
      message: '描述文字',
      image_upload_ids: ['uuid-1234-abcd'],
    })
  })

  // TC-UNIT-017: Empty uploadIds array → falls back to send()
  it('TC-UNIT-017: 空数组 → fallback 为纯文本 send()', () => {
    ws.sendWithImages('hello', [])
    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData).toEqual({ type: 'chat_message', message: 'hello' })
  })

  // TC-UNIT-018: Non-array parameter → falls back to send()
  it('TC-UNIT-018: 非数组参数 → fallback 为纯文本 send()', () => {
    ws.sendWithImages('hello', 'not-an-array')
    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData).toEqual({ type: 'chat_message', message: 'hello' })
  })

  it('TC-UNIT-018-b: null → fallback 为纯文本 send()', () => {
    ws.sendWithImages('hello', null)
    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData).toEqual({ type: 'chat_message', message: 'hello' })
  })

  // TC-UNIT-019: Not connected
  it('TC-UNIT-019: 未连接状态(connected=false) → 不发送', () => {
    ws.close() // disconnect
    ws.sendWithImages('test', ['uuid-123'])
    expect(socket.send).not.toHaveBeenCalled()
  })

  // TC-UNIT-020: Multiple upload ids
  it('TC-UNIT-020: 多个图片 → 全部包含在 image_upload_ids 数组中', () => {
    const uploadIds = ['uuid-aaa', 'uuid-bbb', 'uuid-ccc']
    ws.sendWithImages('三张图', uploadIds)

    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData.type).toBe('chat_message')
    expect(sentData.message).toBe('三张图')
    expect(sentData.image_upload_ids).toHaveLength(3)
    expect(sentData.image_upload_ids).toEqual(uploadIds)
  })

  // Bonus: empty message with images (backend generates default text)
  it('空消息+图片 → message为空字符串, image_upload_ids正常', () => {
    ws.sendWithImages('', ['uuid-img'])
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData.message).toBe('')
    expect(sentData.image_upload_ids).toEqual(['uuid-img'])
  })

  // Bonus: backward compatibility — send() is unchanged
  it('send()保持不变 — chat_message文本帧格式不变', () => {
    ws.send('hello world')

    expect(socket.send).toHaveBeenCalledTimes(1)
    const sentData = JSON.parse(socket.send.mock.calls[0][0].data)
    expect(sentData).toEqual({ type: 'chat_message', message: 'hello world' })
  })
})
