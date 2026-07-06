/**
 * @vitest-environment jsdom
 *
 * Integration tests for MOD-001: ChatInputBar.vue
 * Simplified — text input + send button + voice toggle
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// ============================================================================
// Mock dependencies
// ============================================================================
vi.mock('@/utils/permission', () => ({
  requestPermission: vi.fn(),
}))

vi.mock('@/utils/voice-input', () => ({
  startRecording: vi.fn(),
  stopAndRecognize: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  BASE_URL: 'https://api.test.local',
  WS_BASE_URL: 'wss://api.test.local',
}))

vi.mock('@/utils/auth', () => ({
  getToken: vi.fn(() => 'mock-token'),
}))

import ChatInputBar from '@/components/ChatInputBar.vue'
import { requestPermission } from '@/utils/permission'
import { startRecording, stopAndRecognize } from '@/utils/voice-input'

// ============================================================================
// Helpers
// ============================================================================
function mountBar(props = {}) {
  return mount(ChatInputBar, {
    props: { wsConnected: true, isStreaming: false, ...props },
    global: { config: { warnHandler: () => {} } },
  })
}

function findTextarea(w) { return w.find('textarea') }
function findSendBtn(w) {
  // Send button is the first .icon-btn in text mode
  return w.findAll('.icon-btn')[0]
}
function findVoiceToggle(w) {
  // Voice toggle is the last .icon-btn
  const btns = w.findAll('.icon-btn')
  return btns[btns.length - 1]
}
function findHoldToSpeak(w) { return w.find('.hold-to-speak') }

function expectIcon(btn, icoClass) {
  const ico = btn.find('.ico')
  expect(ico.exists()).toBe(true)
  expect(ico.classes()).toContain(icoClass)
}

// ============================================================================
// Tests
// ============================================================================

describe('ChatInputBar — 初始状态', () => {
  beforeEach(() => vi.clearAllMocks())

  it('初始为文字模式，textarea 可见，发送按钮禁用', () => {
    const w = mountBar()
    expect(findTextarea(w).exists()).toBe(true)
    expect(findSendBtn(w).exists()).toBe(true)
    expect(findSendBtn(w).classes()).toContain('send-btn--disabled')
    expect(findHoldToSpeak(w).exists()).toBe(false)
    expectIcon(findVoiceToggle(w), 'ico-mic')
  })
})

describe('ChatInputBar — 模式切换', () => {
  beforeEach(() => vi.clearAllMocks())

  it('点击麦克风 → 语音模式', async () => {
    const w = mountBar()
    await findVoiceToggle(w).trigger('tap')
    await nextTick()

    expect(findTextarea(w).exists()).toBe(false)
    expect(findHoldToSpeak(w).exists()).toBe(true)
    expect(findHoldToSpeak(w).text()).toBe('按住说话')
    expectIcon(findVoiceToggle(w), 'ico-keyboard')
  })

  it('点击键盘 → 回到文字模式', async () => {
    const w = mountBar()
    await findVoiceToggle(w).trigger('tap')
    await nextTick()
    await findVoiceToggle(w).trigger('tap')
    await nextTick()

    expect(findTextarea(w).exists()).toBe(true)
    expect(findHoldToSpeak(w).exists()).toBe(false)
    expectIcon(findVoiceToggle(w), 'ico-mic')
  })

  it('WS 断开时模式切换仍可用', async () => {
    const w = mountBar({ wsConnected: false })
    await findVoiceToggle(w).trigger('tap')
    await nextTick()
    expect(findHoldToSpeak(w).exists()).toBe(true)
  })
})

describe('ChatInputBar — 禁用逻辑', () => {
  beforeEach(() => vi.clearAllMocks())

  it('!wsConnected → textarea 和 voice 禁用', () => {
    const w = mountBar({ wsConnected: false })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()
    expect(findSendBtn(w).classes()).toContain('send-btn--disabled')
  })

  it('isStreaming → textarea 禁用', () => {
    const w = mountBar({ isStreaming: true })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()
    expect(findSendBtn(w).classes()).toContain('send-btn--disabled')
  })

  it('正常 + 输入文字 → 发送按钮高亮', async () => {
    const w = mountBar()
    await findTextarea(w).setValue('hello')
    await nextTick()
    expect(findSendBtn(w).classes()).toContain('send-btn--active')
  })
})

describe('ChatInputBar — 发送', () => {
  beforeEach(() => vi.clearAllMocks())

  it('输入文字点击发送 → emit send 正确 payload', async () => {
    const w = mountBar()
    await findTextarea(w).setValue('你好世界')
    await nextTick()
    await findSendBtn(w).trigger('tap')
    await nextTick()

    expect(w.emitted('send')).toBeTruthy()
    expect(w.emitted('send')[0]).toEqual([{ text: '你好世界', media: [] }])
  })

  it('发送后输入框清空', async () => {
    const w = mountBar()
    await findTextarea(w).setValue('test')
    await nextTick()
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.find('textarea').element.value).toBe('')
  })

  it('空输入点击发送 → 不 emit', async () => {
    const w = mountBar()
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')).toBeFalsy()
  })
})

describe('ChatInputBar — 语音模式', () => {
  beforeEach(() => vi.clearAllMocks())

  it('语音模式下降权被拒 → emit error', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('denied')

    const w = mountBar()
    await findVoiceToggle(w).trigger('tap')
    await nextTick()
    await findHoldToSpeak(w).trigger('touchstart')
    await nextTick()

    const errs = w.emitted('error')
    expect(errs).toBeTruthy()
    expect(errs[0][0]).toMatchObject({
      code: 'PERMISSION_DENIED',
      message: expect.stringContaining('录音权限'),
    })
    expect(startRecording).not.toHaveBeenCalled()
  })

  it('按住说话 → 录音 → 松手 → ASR 识别 → emit send', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '今天天气怎么样' })

    const w = mountBar()
    await findVoiceToggle(w).trigger('tap')
    await nextTick()

    // Press
    await findHoldToSpeak(w).trigger('touchstart')
    await nextTick()
    expect(startRecording).toHaveBeenCalled()

    // Release
    await findHoldToSpeak(w).trigger('touchend')
    await nextTick()
    await new Promise(r => setTimeout(r, 20))
    await nextTick()

    expect(stopAndRecognize).toHaveBeenCalled()
    expect(w.emitted('send')[0]).toEqual([{ text: '今天天气怎么样', media: [] }])
  })

  it('语音模式在全局禁用时 hold-to-speak 不可交互', async () => {
    const w = mountBar({ isStreaming: true })
    await findVoiceToggle(w).trigger('tap')
    await nextTick()
    expect(findHoldToSpeak(w).classes()).toContain('hold-to-speak--disabled')
  })
})
