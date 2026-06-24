import { describe, it, expect } from 'vitest'
import { saveAuth, getToken, getUserInfo, isAdmin, clearAuth } from '@/utils/auth'

describe('utils/auth', () => {
  it('saveAuth + getToken/getUserInfo 往返', () => {
    saveAuth('tok123', { username: 'alice', role: 'admin' })
    expect(getToken()).toBe('tok123')
    expect(getUserInfo()).toEqual({ username: 'alice', role: 'admin' })
  })

  it('getToken 无值返回 null', () => {
    expect(getToken()).toBeNull()
  })

  it('getUserInfo 脏数据不抛错（返回 null）', () => {
    uni.setStorageSync('userInfo', '{not json')
    expect(getUserInfo()).toBeNull()
  })

  it('isAdmin 仅在 role==="admin" 时为真', () => {
    saveAuth('t', { role: 'user' })
    expect(isAdmin()).toBe(false)
    saveAuth('t', { role: 'admin' })
    expect(isAdmin()).toBe(true)
  })

  it('clearAuth 清空 token 与 userInfo', () => {
    saveAuth('t', { role: 'admin' })
    clearAuth()
    expect(getToken()).toBeNull()
    expect(getUserInfo()).toBeNull()
  })
})
