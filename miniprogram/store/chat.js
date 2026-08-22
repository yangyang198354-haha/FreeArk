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
    persona: null,       // v1.13.0: {identity, address, tone} | null（旧键 greeting_style/tone_style 已废）
    cabinStatus: { is_bound: false, rooms: [], active_room: null },
    // v1.13.0: 设置页改过人格后置真。当前 WS 连接持的是 connect 时读的 persona
    // 快照，不重连的话副官页开场问候语还是旧称呼。聊天页据此决定是否重连。
    personaStale: false,
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
    // 设置页保存后调用；聊天页 onShow 消费并重连，随后清标记
    markPersonaStale() {
      this.personaStale = true
    },
    clearPersonaStale() {
      this.personaStale = false
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
