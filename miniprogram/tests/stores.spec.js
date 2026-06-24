import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/store/auth'
import { useChatStore } from '@/store/chat'

beforeEach(() => setActivePinia(createPinia()))

describe('store/auth', () => {
  it('login 写入 token/userInfo，isAdmin 判 role', () => {
    const s = useAuthStore()
    expect(s.isLoggedIn).toBe(false)
    s.login('tok', { username: 'bob', role: 'admin' })
    expect(s.isLoggedIn).toBe(true)
    expect(s.username).toBe('bob')
    expect(s.isAdmin).toBe(true)
    expect(s.role).toBe('admin')
  })

  it('普通用户 isAdmin=false', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'u', role: 'user' })
    expect(s.isAdmin).toBe(false)
  })

  it('logout 清空', () => {
    const s = useAuthStore()
    s.login('tok', { role: 'admin' })
    s.logout()
    expect(s.isLoggedIn).toBe(false)
    expect(s.isAdmin).toBe(false)
  })
})

describe('store/chat', () => {
  it('流式拼接：appendToken 累加到最后一条 streaming 消息', () => {
    const c = useChatStore()
    c.addMessage({ role: 'assistant', content: '', streaming: true })
    c.appendToken('he')
    c.appendToken('llo')
    expect(c.messages[0].content).toBe('hello')
  })

  it('reasoning 累加 + setStreamEnd 收尾', () => {
    const c = useChatStore()
    c.addMessage({ role: 'assistant', content: '', streaming: true, reasoning: '' })
    c.appendReasoningToken('think')
    expect(c.messages[0].reasoning).toBe('think')
    c.setStreamEnd()
    expect(c.messages[0].streaming).toBe(false)
  })

  it('setConnected 更新连接态与 sessionKey', () => {
    const c = useChatStore()
    c.setConnected(true, 'KEY', 'ID')
    expect(c.wsConnected).toBe(true)
    expect(c.sessionKey).toBe('KEY')
    expect(c.currentSessionId).toBe('ID')
  })

  it('resetSession 清空消息与连接态', () => {
    const c = useChatStore()
    c.addMessage({ role: 'user', content: 'hi' })
    c.setConnected(true, 'K')
    c.resetSession()
    expect(c.messages.length).toBe(0)
    expect(c.wsConnected).toBe(false)
    expect(c.sessionKey).toBeNull()
  })
})
