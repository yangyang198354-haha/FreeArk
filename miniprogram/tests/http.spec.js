import { describe, it, expect, vi } from 'vitest'
import http from '@/utils/http'

describe('utils/http', () => {
  it('GET 拼接 query、带 Token 头、resolve data', async () => {
    uni.setStorageSync('userToken', 'tok')
    uni.request = vi.fn((o) => o.success({ statusCode: 200, data: { ok: 1 } }))

    const data = await http.get('/api/x', { a: 1, b: 2 })
    expect(data).toEqual({ ok: 1 })

    const opt = uni.request.mock.calls[0][0]
    expect(opt.url).toContain('/api/x?a=1&b=2')
    expect(opt.method).toBe('GET')
    expect(opt.header.Authorization).toBe('Token tok')
  })

  it('buildQuery 跳过 null/undefined', async () => {
    uni.setStorageSync('userToken', 'tok')
    uni.request = vi.fn((o) => o.success({ statusCode: 200, data: {} }))
    await http.get('/api/y', { a: 1, b: null, c: undefined, d: 2 })
    const opt = uni.request.mock.calls[0][0]
    expect(opt.url).toContain('/api/y?a=1&d=2')
    expect(opt.url).not.toContain('b=')
    expect(opt.url).not.toContain('c=')
  })

  it('未登录访问非 login 接口 → reLaunch 登录并 reject', async () => {
    // 无 token
    await expect(http.get('/api/x')).rejects.toThrow('NOT_LOGGED_IN')
    expect(uni.reLaunch).toHaveBeenCalled()
  })

  it('401 → 清理凭证 + 提示 + 跳登录', async () => {
    vi.useFakeTimers()
    uni.setStorageSync('userToken', 'tok')
    uni.request = vi.fn((o) => o.success({ statusCode: 401 }))

    await expect(http.get('/api/x')).rejects.toThrow('SESSION_EXPIRED')
    expect(uni.getStorageSync('userToken')).toBeFalsy() // 已清理
    expect(uni.showToast).toHaveBeenCalled()

    vi.advanceTimersByTime(2100) // 触发 setTimeout 内的 reLaunch + 复位标志
    expect(uni.reLaunch).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('login 接口在无 token 时也放行', async () => {
    uni.request = vi.fn((o) => o.success({ statusCode: 200, data: { success: true } }))
    const d = await http.post('/api/auth/login/', { username: 'a' })
    expect(d).toEqual({ success: true })
  })
})
