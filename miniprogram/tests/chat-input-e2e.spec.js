/**
 * @vitest-environment jsdom
 *
 * E2E tests for ChatInputBar — Simplified (text + send + voice toggle)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

function findTextarea(w) { return w.find(".cib-text") }
function findSendBtn(w) { return w.findAll('.cib-btn')[0] }
function findVoiceToggle(w) {
  const btns = w.findAll('.cib-btn')
  return btns[btns.length - 1]
}
function findHoldToSpeak(w) { return w.find('.cib-hold') }

// ============================================================================
// E2E Tests
// ============================================================================

describe('E2E — 文字输入与发送', () => {
  beforeEach(() => vi.clearAllMocks())

  it('完整流程：输入 → 高亮 → 发送 → 清空 → 按钮恢复禁用', async () => {
    const w = mountBar()

    // Empty → send disabled
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')

    // Type → send active
    await findTextarea(w).setValue('你好，方舟助手')
    await nextTick()
    expect(findSendBtn(w).classes()).toContain('cib-send--active')

    // Click send
    await findSendBtn(w).trigger('tap')
    await nextTick()

    // Verify emit
    expect(w.emitted('send')[0]).toEqual([{ text: '你好，方舟助手', media: [] }])

    // Input cleared
    expect(w.find('textarea').element.value).toBe('')

    // Send disabled again
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
  })

  it('空输入点击发送 → 无响应', async () => {
    const w = mountBar()
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')).toBeFalsy()
  })
})

describe('E2E — 语音模式切换往返', () => {
  beforeEach(() => vi.clearAllMocks())

  it('文字 → 语音 → 文字 完整往返', async () => {
    const w = mountBar()

    // Start: text mode
    expect(findTextarea(w).exists()).toBe(true)
    expect(findHoldToSpeak(w).exists()).toBe(false)

    // Switch to voice
    await findVoiceToggle(w).trigger('tap')
    await nextTick()
    expect(findTextarea(w).exists()).toBe(false)
    expect(findHoldToSpeak(w).exists()).toBe(true)
    expect(findHoldToSpeak(w).text()).toBe('按住说话')

    // Switch back to text
    await findVoiceToggle(w).trigger('tap')
    await nextTick()
    expect(findTextarea(w).exists()).toBe(true)
    expect(findHoldToSpeak(w).exists()).toBe(false)
    expect(w.find('textarea').element.value).toBe('')
  })
})

describe('E2E — 按住说话发送语音', () => {
  beforeEach(() => vi.clearAllMocks())

  it('按住 → 录音 → 松手 → ASR → emit send', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '今天天气怎么样' })

    const w = mountBar()
    await findVoiceToggle(w).trigger('tap')
    await nextTick()

    const hts = findHoldToSpeak(w)
    expect(hts.text()).toBe('按住说话')

    await hts.trigger('touchstart')
    await nextTick()
    expect(rp).toHaveBeenCalledWith('scope.record', expect.objectContaining({ name: '录音' }))
    expect(startRecording).toHaveBeenCalled()

    await hts.trigger('touchend')
    await nextTick()
    await new Promise(r => setTimeout(r, 20))
    await nextTick()

    expect(stopAndRecognize).toHaveBeenCalled()
    expect(w.emitted('send')[0]).toEqual([{ text: '今天天气怎么样', media: [] }])
  })

  it('权限拒绝 → emit error，不开始录音', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('denied')

    const w = mountBar()
    await findVoiceToggle(w).trigger('tap')
    await nextTick()
    await findHoldToSpeak(w).trigger('touchstart')
    await nextTick()

    expect(w.emitted('error')[0][0]).toMatchObject({ code: 'PERMISSION_DENIED' })
    expect(startRecording).not.toHaveBeenCalled()
  })
})

describe('E2E — 状态管理', () => {
  beforeEach(() => vi.clearAllMocks())

  it('WS 断开 → textarea 禁用 + 发送禁用', () => {
    const w = mountBar({ wsConnected: false })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
  })

  it('Streaming → 全局禁用 → stream 结束后恢复', async () => {
    const w = mountBar({ isStreaming: true })
    expect(findTextarea(w).attributes('disabled')).toBeDefined()
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')

    await w.setProps({ isStreaming: false })
    await nextTick()
    expect(findTextarea(w).attributes('disabled')).toBeUndefined()
  })
})
