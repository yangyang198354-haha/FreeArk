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
 *
 * v1.5.1: 增加真机诊断日志（real-device diagnostic），用于定位 APP 端 WebSocket 断连问题。
 */

import { WS_BASE_URL } from './http'

// 诊断开关：APP 端真机调试时输出详细日志
const DIAG = true

function buildWsUrl(token, sessionKey, activeSp) {
  let url = `${WS_BASE_URL}/ws/miniapp/chat/?token=${encodeURIComponent(token)}`
  if (sessionKey) url += `&session_key=${encodeURIComponent(sessionKey)}`
  if (activeSp) url += `&active_sp=${encodeURIComponent(activeSp)}`
  return url
}

export class ChatWebSocket {
  constructor(callbacks) {
    this.socketTask = null
    this.connected = false
    this.callbacks = callbacks
    this._connSeq = 0
    this._heartbeatTimer = null
    this._reconnectTimer = null
    this._reconnectCount = 0
    this._manualClose = false
    // callbacks: {
    //   onConnected(sessionKey, sessionId, persona, cabinStatus),
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

  connect(token, sessionKey, activeSp = '') {
    this.close()
    const seq = ++this._connSeq
    const url = buildWsUrl(token, sessionKey, activeSp)
    // 真机诊断：输出连接 URL 以便排查
    if (DIAG) {
      console.log('[ChatWS] connect seq=' + seq + ' url=' + url)
      console.log('[ChatWS] platform=' + (typeof plus !== 'undefined' ? 'APP-PLUS' : 'MP-WEIXIN') +
        ' networkType=' + (uni.getNetworkTypeSync ? uni.getNetworkTypeSync() : 'unknown'))
    }
    const socketTask = uni.connectSocket({
      url,
      // #ifdef APP-PLUS
      // APP 端允许更宽松的 SSL 校验（自签名/不完整证书链）
      ssl: false,
      // #endif
      complete: () => {}
    })
    this.socketTask = socketTask

    socketTask.onOpen(() => {
      if (DIAG) console.log('[ChatWS] onOpen seq=' + seq + ' ws connected, waiting for server auth frame')
      // Do NOT mark connected here — wait for "connected" frame from server.
      // The backend sends { type: "connected", session_id: "...", session_key: "..." }
      // only after successful auth. Marking connected on onOpen would bypass auth check.
    })

    socketTask.onMessage(({ data }) => {
      if (seq !== this._connSeq || socketTask !== this.socketTask) return
      let msg
      try { msg = JSON.parse(data) } catch {
        if (DIAG) console.warn('[ChatWS] onMessage non-JSON data:', data)
        return
      }

      switch (msg.type) {
        case 'connected':
          this.connected = true
          this._reconnectCount = 0
          this._startHeartbeat()
          if (DIAG) console.log('[ChatWS] onMessage connected session_key=' + msg.session_key)
          this.callbacks.onConnected?.(
            msg.session_key, msg.session_id,
            msg.persona || null,
            msg.cabin_status || { is_bound: false, rooms: [], active_room: null },
          )
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
          if (DIAG) console.warn('[ChatWS] server error frame:', msg)
          this.callbacks.onError?.(msg)
          break
        case 'ping':
          // 服务端 ping → 回复 pong
          if (this.socketTask) {
            try { this.socketTask.send({ data: JSON.stringify({ type: 'pong' }) }) } catch {}
          }
          break
        default:
          // Unknown frame type — silently ignore
          if (DIAG) console.log('[ChatWS] unknown frame type:', msg.type)
          break
      }
    })

    socketTask.onClose(({ code, reason }) => {
      if (seq !== this._connSeq || socketTask !== this.socketTask) return
      this.connected = false
      this._stopHeartbeat()
      if (DIAG) console.warn('[ChatWS] onClose code=' + code + ' reason=' + reason + ' manualClose=' + this._manualClose)
      // 非正常关闭且非手动关闭时，自动重连
      if (!this._manualClose && code !== 1000 && code !== 4001) {
        this._scheduleReconnect(token, sessionKey, activeSp)
      }
      this.callbacks.onClose?.(code)
    })

    socketTask.onError((err) => {
      if (seq !== this._connSeq || socketTask !== this.socketTask) return
      const errMsg = (err && err.errMsg) || ''
      if (DIAG) console.warn('[ChatWS] onError errMsg=' + errMsg)
      // 给用户更明确的提示
      let userMsg = '连接异常'
      if (errMsg.includes('certificate') || errMsg.includes('ssl') || errMsg.includes('cert')) {
        userMsg = '连接失败：服务器证书校验失败'
      } else if (errMsg.includes('timeout') || errMsg.includes('timed out')) {
        userMsg = '连接超时，请检查网络'
      } else if (errMsg.includes('refused') || errMsg.includes('failed to connect')) {
        userMsg = '无法连接服务器，请检查网络'
      } else if (errMsg) {
        userMsg = '连接异常：' + errMsg
      }
      this.callbacks.onError?.({ code: 'WS_ERROR', message: userMsg, errMsg })
    })
  }

  /**
   * @implements IFC-002-02
   * Send a text message. Frame: { type: 'chat_message', message: text }.
   * Signature unchanged for backward compatibility (ADR-001, REQ-NFUNC-001).
   */
  send(message) {
    if (!this.socketTask || !this.connected) return
    this.socketTask.send({ data: JSON.stringify({ type: 'chat_message', message }) })
  }

  /**
   * @implements IFC-002-05
   * Send a message with image attachments.
   * Uses the existing backend protocol: chat_message + image_upload_ids field.
   * Backend consumers.py (v1.5.0/v1.9.0) already supports this format.
   *
   * @param {string} message - Text message (can be empty if only images)
   * @param {string[]} uploadIds - Array of upload_id strings from image-upload endpoint
   */
  sendWithImages(message, uploadIds) {
    if (!this.socketTask || !this.connected) return
    if (!Array.isArray(uploadIds) || uploadIds.length === 0) {
      // Fallback to plain text if no images
      this.send(message)
      return
    }
    this.socketTask.send({
      data: JSON.stringify({
        type: 'chat_message',
        message: message || '',
        image_upload_ids: uploadIds
      })
    })
  }

  sendConfirm(approved) {
    if (!this.socketTask) return
    this.socketTask.send({ data: JSON.stringify({ type: 'confirm_response', approved }) })
  }

  close() {
    this._manualClose = true
    this._stopHeartbeat()
    this._cancelReconnect()
    if (this.socketTask) {
      const closingTask = this.socketTask
      this._connSeq++
      this.socketTask = null
      this.connected = false
      try { closingTask.close({}) } catch {}
    }
  }

  _startHeartbeat() {
    this._stopHeartbeat()
    // 每 20 秒发 ping 保活，防止 Android 系统回收空闲 WebSocket 连接
    this._heartbeatTimer = setInterval(() => {
      if (!this.connected || !this.socketTask) return
      try {
        this.socketTask.send({ data: JSON.stringify({ type: 'ping' }) })
      } catch {}
    }, 20000)
  }

  _stopHeartbeat() {
    if (this._heartbeatTimer) {
      clearInterval(this._heartbeatTimer)
      this._heartbeatTimer = null
    }
  }

  _scheduleReconnect(token, sessionKey, activeSp) {
    this._cancelReconnect()
    if (this._reconnectCount >= 5) return
    const delay = Math.min(1000 * Math.pow(2, this._reconnectCount), 10000)
    this._reconnectCount++
    if (DIAG) console.warn('[ChatWS] 自动重连 #' + this._reconnectCount + '，延迟 ' + delay + 'ms')
    this._reconnectTimer = setTimeout(() => {
      this._manualClose = false
      this.connect(token, sessionKey, activeSp)
    }, delay)
  }

  _cancelReconnect() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer)
      this._reconnectTimer = null
    }
  }
}
