/**
 * @vitest-environment jsdom
 *
 * ChatInputBar tests — ultra-simple: textarea + send + voice (always visible)
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
function findVoiceBtn(w) { return w.findAll('.cib-btn')[1] }

// ============================================================================

describe('ChatInputBar — 初始状态', () => {
  beforeEach(() => vi.clearAllMocks())

  it('三个元素同时存在: textarea, 发送, 语音', () => {
    const w = mountBar()
    expect(findTextarea(w).exists()).toBe(true)
    expect(findSendBtn(w).exists()).toBe(true)
    expect(findVoiceBtn(w).exists()).toBe(true)
  })

  it('空输入时发送按钮禁用', () => {
    const w = mountBar()
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
  })

  it('输入文字后发送按钮高亮', async () => {
    const w = mountBar()
    await findTextarea(w).setValue('hello')
    await nextTick()
    expect(findSendBtn(w).classes()).toContain('cib-send--active')
  })
})

describe('ChatInputBar — 发送文字', () => {
  beforeEach(() => vi.clearAllMocks())

  it('输入 → 点击发送 → emit + 清空', async () => {
    const w = mountBar()
    await findTextarea(w).setValue('你好')
    await nextTick()
    await findSendBtn(w).trigger('tap')
    await nextTick()

    expect(w.emitted('send')[0]).toEqual([{ text: '你好', media: [] }])
    expect(w.find('textarea').element.value).toBe('')
  })

  it('空输入点发送 → 不 emit', async () => {
    const w = mountBar()
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')).toBeFalsy()
  })
})

describe('ChatInputBar — 语音录音', () => {
  beforeEach(() => vi.clearAllMocks())

  it('长按 → 录音 → 松手 → 识别 → emit send', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '识别结果' })

    const w = mountBar()
    const voice = findVoiceBtn(w)

    // Press
    await voice.trigger('touchstart')
    await nextTick()
    expect(rp).toHaveBeenCalled()
    expect(startRecording).toHaveBeenCalled()
    expect(voice.classes()).toContain('cib-voice--recording')

    // Release
    await voice.trigger('touchend')
    await nextTick()
    await new Promise(r => setTimeout(r, 20))
    await nextTick()

    expect(stopAndRecognize).toHaveBeenCalled()
    expect(w.emitted('send')[0]).toEqual([{ text: '识别结果', media: [] }])
  })

  it('权限拒绝 → emit error，不录音', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('denied')

    const w = mountBar()
    await findVoiceBtn(w).trigger('touchstart')
    await nextTick()

    expect(w.emitted('error')[0][0]).toMatchObject({ code: 'PERMISSION_DENIED' })
    expect(startRecording).not.toHaveBeenCalled()
  })

  it('上滑取消 → 不发送', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)

    const w = mountBar()
    const voice = findVoiceBtn(w)

    // Press
    await voice.trigger('touchstart', { touches: [{ pageY: 300 }] })
    await nextTick()

    // Slide up (cancel)
    await voice.trigger('touchmove', { touches: [{ pageY: 200 }] })
    await nextTick()
    expect(voice.classes()).toContain('cib-voice--cancelling')

    // Release
    await voice.trigger('touchend')
    await nextTick()

    expect(w.emitted('send')).toBeFalsy()
  })
})

describe('ChatInputBar — 禁用逻辑', () => {
  beforeEach(() => vi.clearAllMocks())

  it('WS 断开 → textarea 禁用 + 发送禁用 + 语音禁用', () => {
    const w = mountBar({ wsConnected: false })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
    expect(findVoiceBtn(w).classes()).toContain('cib-voice--disabled')
  })

  it('Streaming → 全局禁用', () => {
    const w = mountBar({ isStreaming: true })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
    expect(findVoiceBtn(w).classes()).toContain('cib-voice--disabled')
  })
})
