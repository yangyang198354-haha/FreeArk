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
    setConnected(val, sessionKey, sessionId) {
      this.wsConnected = val
      if (sessionKey) this.sessionKey = sessionKey
      if (sessionId) this.currentSessionId = sessionId
    },
    resetSession() {
      this.messages = []
      this.wsConnected = false
      this.sessionKey = null
    },
    setSessionList(list) {
      this.sessionList = list
    },
  },
})
