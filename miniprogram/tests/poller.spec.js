import { describe, it, expect, vi } from 'vitest'
import { PagePoller } from '@/utils/poller'

describe('utils/poller PagePoller', () => {
  it('start 立即执行一次，随后按间隔执行；stop 后停止', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const p = new PagePoller(fn, 1000)

    p.start()
    expect(fn).toHaveBeenCalledTimes(1) // 立即一次

    vi.advanceTimersByTime(2500)
    expect(fn).toHaveBeenCalledTimes(3) // +2 次（1000/2000ms）

    p.stop()
    vi.advanceTimersByTime(5000)
    expect(fn).toHaveBeenCalledTimes(3) // stop 后不再触发

    vi.useRealTimers()
  })

  it('stop 可安全重复调用', () => {
    const p = new PagePoller(() => {}, 1000)
    expect(() => { p.stop(); p.stop() }).not.toThrow()
  })
})
