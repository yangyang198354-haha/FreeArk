/**
 * @module MOD-CHAT-WS
 * @author sub_agent_software_developer
 * @description WebSocket client for AI chat. Strictly replicates the backend WS protocol:
 *   - URL: ws://{host}/ws/miniapp/chat/?token={userToken}[&session_key={uuid}]
 *   - Auth: token as query param (NOT header)
 *   - connected frame (NOT onOpen) gates wsConnected=true
 *   - onHide must call close() to prevent backend hang-up
 *
 * Frame types handled:
 *   connected, status_update, reasoning_token, reasoning_end,
 *   stream_token, stream_end, confirm_required, error
 *
 * Auth failure: server closes with code 4001 → caller should re-login.
 */

import { WS_BASE_URL } from './http'

function buildWsUrl(token, sessionKey) {
  let url = `${WS_BASE_URL}/ws/miniapp/chat/?token=${encodeURIComponent(token)}`
  if (sessionKey) url += `&session_key=${encodeURIComponent(sessionKey)}`
  return url
}

export class ChatWebSocket {
  constructor(callbacks) {
    this.socketTask = null
    this.connected = false
    this.callbacks = callbacks
    this._connSeq = 0
    // callbacks: {
    //   onConnected(sessionKey, sessionId),
    //   onStatusUpdate(message),
    //   onReasoningToken(token),
    //   onReasoningEnd(),
    //   onToken(token),
    //   onStreamEnd(),
    //   onConfirmRequired(actions),
    //   onError(errObj),
    //   onClose(code),
    // }
  }

  connect(token, sessionKey) {
    this.close()
    const seq = ++this._connSeq
    const url = buildWsUrl(token, sessionKey)
    const socketTask = uni.connectSocket({ url, complete: () => {} })
    this.socketTask = socketTask

    socketTask.onOpen(() => {
      // Do NOT mark connected here — wait for "connected" frame from server.
      // The backend sends { type: "connected", session_id: "...", session_key: "..." }
      // only after successful auth. Marking connected on onOpen would bypass auth check.
    })

    socketTask.onMessage(({ data }) => {
      if (seq !== this._connSeq || socketTask !== this.socketTask) return
      let msg
      try { msg = JSON.parse(data) } catch { return }

      switch (msg.type) {
        case 'connected':
          this.connected = true
          this.callbacks.onConnected?.(msg.session_key, msg.session_id)
          break
        case 'status_update':
          this.callbacks.onStatusUpdate?.(msg.message)
          break
        case 'reasoning_token':
          this.callbacks.onReasoningToken?.(msg.token)
          break
        case 'reasoning_end':
          this.callbacks.onReasoningEnd?.()
          break
        case 'stream_token':
          this.callbacks.onToken?.(msg.token)
          break
        case 'stream_end':
          this.callbacks.onStreamEnd?.()
          break
        case 'confirm_required':
          this.callbacks.onConfirmRequired?.(msg.actions)
          break
        case 'error':
          this.callbacks.onError?.(msg)
          break
        default:
          // Unknown frame type — silently ignore
          break
      }
    })

    socketTask.onClose(({ code }) => {
      if (seq !== this._connSeq || socketTask !== this.socketTask) return
      this.connected = false
      this.callbacks.onClose?.(code)
    })

    socketTask.onError(() => {
      if (seq !== this._connSeq || socketTask !== this.socketTask) return
      this.callbacks.onError?.({ code: 'WS_ERROR', message: '连接异常' })
    })
  }

  send(message) {
    if (!this.socketTask || !this.connected) return
    this.socketTask.send({ data: JSON.stringify({ type: 'chat_message', message }) })
  }

  sendConfirm(approved) {
    if (!this.socketTask) return
    this.socketTask.send({ data: JSON.stringify({ type: 'confirm_response', approved }) })
  }

  close() {
    if (this.socketTask) {
      const closingTask = this.socketTask
      this._connSeq++
      this.socketTask = null
      this.connected = false
      try { closingTask.close({}) } catch {}
    }
  }
}
