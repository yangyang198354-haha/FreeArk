/**
 * @module MOD-STORE-CHAT
 * @author sub_agent_software_developer
 * @description Pinia chat store. Holds message list, streaming state, session key.
 *   wsConnected is set true ONLY after receiving the "connected" WS frame (not onOpen).
 */

import { defineStore } from 'pinia'

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessionKey: null,
    messages: [],
    wsConnected: false,
    sessionList: [],
    currentSessionId: null,
    // v1.12.0: 人格偏好 + 座舱绑定状态（来自 WS connected 帧）
    persona: null,       // {greeting_style, tone_style} | null
    cabinStatus: { is_bound: false, rooms: [], active_room: null },
  }),
  actions: {
    addMessage(msg) {
      this.messages.push(msg)
    },
    appendToken(token) {
      const last = this.messages[this.messages.length - 1]
      if (last && last.streaming) last.content += token
    },
    appendReasoningToken(token) {
      const last = this.messages[this.messages.length - 1]
      if (last && last.streaming) last.reasoning = (last.reasoning || '') + token
    },
    setStreamEnd() {
      const last = this.messages[this.messages.length - 1]
      if (last) last.streaming = false
    },
    setStatusText(text) {
      const last = this.messages[this.messages.length - 1]
      if (last && last.streaming) last.statusText = text
    },
    // Only called from ChatWebSocket.onConnected callback (not onOpen)
    // v1.12.0: 扩展签名接收 persona + cabinStatus
    setConnected(val, sessionKey, sessionId, persona, cabinStatus) {
      this.wsConnected = val
      if (sessionKey) this.sessionKey = sessionKey
      if (sessionId) this.currentSessionId = sessionId
      if (persona !== undefined) this.persona = persona
      if (cabinStatus !== undefined) this.cabinStatus = cabinStatus
    },
    setPersona(persona) {
      this.persona = persona
    },
    setCabinStatus(cabinStatus) {
      this.cabinStatus = cabinStatus
    },
    resetSession() {
      this.messages = []
      this.wsConnected = false
      this.sessionKey = null
      // persona 和 cabinStatus 不重置——它们是用户级状态，跨会话保持
    },
    setSessionList(list) {
      this.sessionList = list
    },
  },
})
