/**
 * @vitest-environment jsdom
 *
 * ChatInputBar E2E — textarea + send + voice, always visible
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

vi.mock('@/utils/permission', () => ({ requestPermission: vi.fn() }))
vi.mock('@/utils/voice-input', () => ({ startRecording: vi.fn(), stopAndRecognize: vi.fn() }))
vi.mock('@/utils/http', () => ({ BASE_URL: 'https://api.test.local', WS_BASE_URL: 'wss://api.test.local' }))
vi.mock('@/utils/auth', () => ({ getToken: vi.fn(() => 'mock-token') }))

import ChatInputBar from '@/components/ChatInputBar.vue'
import { requestPermission } from '@/utils/permission'
import { startRecording, stopAndRecognize } from '@/utils/voice-input'

function mountBar(props = {}) {
  return mount(ChatInputBar, {
    props: { wsConnected: true, isStreaming: false, ...props },
    global: { config: { warnHandler: () => {} } },
  })
}

function findTextarea(w) { return w.find('.cib-text') }
function findSendBtn(w) { return w.findAll('.cib-btn')[0] }
function findVoiceBtn(w) { return w.find('.cib-voice') }

// ============================================================================

describe('E2E — 文字输入发送', () => {
  beforeEach(() => vi.clearAllMocks())

  it('输入 → 高亮 → 发送 → 清空 → 恢复禁用', async () => {
    const w = mountBar()
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')

    await findTextarea(w).setValue('你好方舟')
    await nextTick()
    expect(findSendBtn(w).classes()).toContain('cib-send--active')

    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')[0]).toEqual([{ text: '你好方舟', media: [] }])
    expect(w.find('textarea').element.value).toBe('')
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
  })
})

describe('E2E — 语音录音发送', () => {
  beforeEach(() => vi.clearAllMocks())

  it('长按录音 → 松手识别 → emit 文字', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '天气怎么样' })

    const w = mountBar()
    const voice = findVoiceBtn(w)

    await voice.trigger('touchstart')
    await nextTick()
    expect(startRecording).toHaveBeenCalled()

    await voice.trigger('touchend')
    await nextTick()
    await new Promise(r => setTimeout(r, 20))
    await nextTick()

    expect(stopAndRecognize).toHaveBeenCalled()
    expect(w.emitted('send')[0]).toEqual([{ text: '天气怎么样', media: [] }])
  })

  it('权限拒绝 → 不录音', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('denied')

    const w = mountBar()
    await findVoiceBtn(w).trigger('touchstart')
    await nextTick()
    expect(w.emitted('error')[0][0]).toMatchObject({ code: 'PERMISSION_DENIED' })
    expect(startRecording).not.toHaveBeenCalled()
  })
})

describe('E2E — 状态管理', () => {
  beforeEach(() => vi.clearAllMocks())

  it('WS 断开 → textarea/send/voice 全部禁用', () => {
    const w = mountBar({ wsConnected: false })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
    expect(findVoiceBtn(w).classes()).toContain('cib-voice--disabled')
  })

  it('Streaming 结束 → 全部恢复', async () => {
    const w = mountBar({ isStreaming: true })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()

    await w.setProps({ isStreaming: false })
    await nextTick()
    expect(findTextarea(w).attributes('disabled')).toBeUndefined()
  })
})
