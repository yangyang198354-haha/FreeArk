/**
 * 副官人格设置页相关契约测试（v1.13.0 第4步）
 *
 * 覆盖三件事：
 *   1. api 层的接口路径/参数契约（含"空串=清空该字段"的提交形态）
 *   2. chat store 的 personaStale 标记——设置页改完人格后，聊天页据此强制重连；
 *      不重连的话后端 self.persona 还是 connect 时的库快照，开场问候语仍是旧称呼
 *   3. 预览文案与聊天页 personaGreeting 同一拼法（所见即所得）
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/utils/http', () => {
  const m = {
    get: vi.fn(() => Promise.resolve({})),
    post: vi.fn(() => Promise.resolve({})),
    put: vi.fn(() => Promise.resolve({})),
    del: vi.fn(() => Promise.resolve({})),
  }
  return { default: m, http: m, WS_BASE_URL: 'ws://test', BASE_URL: 'http://test' }
})

import http from '@/utils/http'
import { api } from '@/utils/api'
import { useChatStore } from '@/store/chat'

beforeEach(() => setActivePinia(createPinia()))

describe('utils/api 人格接口契约', () => {
  it('读人格走 GET /api/miniapp/persona/', () => {
    api.getPersona()
    expect(http.get).toHaveBeenCalledWith('/api/miniapp/persona/')
  })

  it('写人格走 PUT /api/miniapp/persona/update/', () => {
    api.updatePersona({ address: '胖子熊大人' })
    expect(http.put).toHaveBeenCalledWith(
      '/api/miniapp/persona/update/', { address: '胖子熊大人' })
  })

  it('设置页全量提交：空串表示清空该字段', () => {
    api.updatePersona({ identity: '', address: '胖子熊大人', tone: '' })
    expect(http.put).toHaveBeenCalledWith(
      '/api/miniapp/persona/update/',
      { identity: '', address: '胖子熊大人', tone: '' })
  })

  it('恢复默认走 reset=true', () => {
    api.updatePersona({ reset: true })
    expect(http.put).toHaveBeenCalledWith(
      '/api/miniapp/persona/update/', { reset: true })
  })
})

describe('store/chat personaStale', () => {
  it('默认为 false', () => {
    expect(useChatStore().personaStale).toBe(false)
  })

  it('markPersonaStale 置真、clear 复位', () => {
    const s = useChatStore()
    s.markPersonaStale()
    expect(s.personaStale).toBe(true)
    s.clearPersonaStale()
    expect(s.personaStale).toBe(false)
  })

  it('setPersona 写入三键规范形态', () => {
    const s = useChatStore()
    s.setPersona({ identity: '管家', address: '老板', tone: null })
    expect(s.persona.identity).toBe('管家')
    expect(s.persona.address).toBe('老板')
  })

  it('resetSession 不清 persona（用户级状态跨会话保持）', () => {
    const s = useChatStore()
    s.setPersona({ address: '胖子熊大人' })
    s.resetSession()
    expect(s.persona.address).toBe('胖子熊大人')
  })
})

describe('人格预览文案', () => {
  // 与 pages/persona/index.vue 的 previewText 及 chat/index.vue 的
  // personaGreeting 保持同一拼法——两处若漂移，用户在设置页看到的就不是真效果
  const DEFAULT_IDENTITY = '智能方舟的副官'
  const DEFAULT_ADDRESS = '尊敬的舰长大人'
  const preview = (identity, address) => {
    const i = (identity || '').trim() || DEFAULT_IDENTITY
    const a = (address || '').trim() || DEFAULT_ADDRESS
    return `${a}，我是${i}。可以帮您控制设备、排查故障，也能解答空调与新风知识。`
  }

  it('留空时用默认人格', () => {
    expect(preview('', '')).toContain('尊敬的舰长大人，我是智能方舟的副官。')
  })

  it('自定义称呼在前、自称在后', () => {
    expect(preview('', '胖子熊大人')).toContain('胖子熊大人，我是智能方舟的副官。')
  })

  it('称呼不会被误用成自称（v1.12.0 的原始 bug）', () => {
    const t = preview('', '胖子熊大人')
    expect(t.startsWith('胖子熊大人，我是')).toBe(true)
    expect(t).not.toContain('我是胖子熊大人')
  })
})
