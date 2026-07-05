/**
 * @vitest-environment jsdom
 *
 * Integration tests for MOD-001: ChatInputBar.vue
 * TC-INT-001 ~ TC-INT-019
 *
 * Covers:
 *   - Mode switching (text ↔ voice)
 *   - Disable matrix (per module_design.md table)
 *   - Event emission (@send-text, @send-media, @error)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// ============================================================================
// Mock all dependencies BEFORE importing the component
// ============================================================================

vi.mock('@/utils/permission', () => ({
  requestPermission: vi.fn(),
  default: { requestPermission: vi.fn() },
}))

vi.mock('@/utils/media-uploader', () => ({
  uploadImage: vi.fn(),
  uploadImages: vi.fn(),
  isUploadIdExpired: vi.fn(),
  default: { uploadImage: vi.fn(), uploadImages: vi.fn(), isUploadIdExpired: vi.fn() },
}))

vi.mock('@/utils/voice-input', () => ({
  startRecording: vi.fn(),
  stopAndRecognize: vi.fn(),
  default: { startRecording: vi.fn(), stopAndRecognize: vi.fn() },
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
import { uploadImage, isUploadIdExpired } from '@/utils/media-uploader'

// ============================================================================
// Helper: mount the component with default props
// ============================================================================
function mountBar(props = {}) {
  return mount(ChatInputBar, {
    props: {
      wsConnected: true,
      isStreaming: false,
      ...props,
    },
    global: {
      // Suppress template warnings about unrecognized uni-app components
      config: {
        warnHandler: () => {},
      },
    },
  })
}

// ============================================================================
// Helper: find elements by their text/class selectors
// ============================================================================
function findCameraBtn(wrapper) {
  // Camera button is the first .icon-btn (📷)
  return wrapper.findAll('.icon-btn')[0]
}

function findSendBtn(wrapper) {
  // Send button has class .send-btn
  return wrapper.find('.send-btn')
}

function findVoiceToggleBtn(wrapper) {
  // Voice/Keyboard toggle is always the second-to-last .icon-btn element.
  // In text mode:  [camera, send, voice-toggle, album] → index 2 of 4
  // In voice mode: [camera, voice-toggle, album]          → index 1 of 3
  // So we use the element second from the end.
  const btns = wrapper.findAll('.icon-btn')
  return btns[btns.length - 2]
}

function findAlbumBtn(wrapper) {
  const btns = wrapper.findAll('.icon-btn')
  return btns[btns.length - 1]
}

function findTextarea(wrapper) {
  return wrapper.find('textarea')
}

function findHoldToSpeak(wrapper) {
  return wrapper.find('.hold-to-speak')
}

// ============================================================================
// Integration Tests
// ============================================================================

describe('ChatInputBar — 模式切换 (TC-INT-001 ~ TC-INT-004, TC-INT-019)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-INT-001: Initial state = text mode
  it('TC-INT-001: 初始状态 isVoiceMode=false，显示 textarea+发送按钮', () => {
    const wrapper = mountBar()

    // Textarea should be visible
    const textarea = findTextarea(wrapper)
    expect(textarea.exists()).toBe(true)
    expect(textarea.attributes('placeholder')).toBe('输入消息…')

    // Hold-to-speak should not be visible
    const hts = findHoldToSpeak(wrapper)
    expect(hts.exists()).toBe(false)

    // Send button should exist
    const sendBtn = findSendBtn(wrapper)
    expect(sendBtn.exists()).toBe(true)
  })

  // TC-INT-002: Click microphone → voice mode
  it('TC-INT-002: 点击麦克风 → isVoiceMode=true, textarea消失, 按住说话出现', async () => {
    const wrapper = mountBar()

    // Click voice toggle (microphone icon)
    const voiceBtn = findVoiceToggleBtn(wrapper)
    expect(voiceBtn.text()).toBe('🎤') // initially microphone

    await voiceBtn.trigger('tap')
    await nextTick()

    // Textarea should disappear
    expect(findTextarea(wrapper).exists()).toBe(false)

    // Hold-to-speak should appear
    const hts = findHoldToSpeak(wrapper)
    expect(hts.exists()).toBe(true)
    expect(hts.text()).toBe('按住说话')

    // Voice toggle icon should change to keyboard
    expect(findVoiceToggleBtn(wrapper).text()).toBe('⌨')
  })

  // TC-INT-003: Click keyboard → back to text mode
  it('TC-INT-003: 点击键盘 → 恢复文字模式，textarea恢复', async () => {
    const wrapper = mountBar()

    // First switch to voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Now click keyboard to go back
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Textarea should be back
    expect(findTextarea(wrapper).exists()).toBe(true)
    expect(findHoldToSpeak(wrapper).exists()).toBe(false)

    // Icon should be microphone again
    expect(findVoiceToggleBtn(wrapper).text()).toBe('🎤')
  })

  // TC-INT-004: Mode switch works even when WS disconnected
  it('TC-INT-004: WS断开时模式切换仍可用 (AC-003-03)', async () => {
    const wrapper = mountBar({ wsConnected: false })

    const voiceBtn = findVoiceToggleBtn(wrapper)

    // Voice toggle should NOT be disabled
    expect(voiceBtn.classes()).not.toContain('icon-btn--disabled')

    // Should still be able to switch
    await voiceBtn.trigger('tap')
    await nextTick()

    // Should be in voice mode
    expect(findHoldToSpeak(wrapper).exists()).toBe(true)
  })

  // TC-INT-019: Icon changes between microphone and keyboard
  it('TC-INT-019: 语音切换时图标在🎤和⌨之间切换', async () => {
    const wrapper = mountBar()
    const voiceBtn = findVoiceToggleBtn(wrapper)

    expect(voiceBtn.text()).toBe('🎤')

    await voiceBtn.trigger('tap')
    await nextTick()
    expect(findVoiceToggleBtn(wrapper).text()).toBe('⌨')

    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()
    expect(findVoiceToggleBtn(wrapper).text()).toBe('🎤')
  })
})

describe('ChatInputBar — 禁用矩阵 (!wsConnected) — TC-INT-005 ~ TC-INT-009', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountDisconnected() {
    return mountBar({ wsConnected: false, isStreaming: false })
  }

  // TC-INT-005: Camera disabled when WS down
  it('TC-INT-005: !wsConnected → 拍照按钮 disabled', () => {
    const wrapper = mountDisconnected()
    const cameraBtn = findCameraBtn(wrapper)
    expect(cameraBtn.classes()).toContain('icon-btn--disabled')
  })

  // TC-INT-006: Textarea disabled when WS down
  it('TC-INT-006: !wsConnected → textarea disabled', () => {
    const wrapper = mountDisconnected()
    const textarea = findTextarea(wrapper)
    expect(textarea.attributes('disabled')).toBeDefined()
  })

  // TC-INT-007: Send button disabled when WS down
  it('TC-INT-007: !wsConnected → 发送按钮 disabled', () => {
    const wrapper = mountDisconnected()
    const sendBtn = findSendBtn(wrapper)
    // Can be either send-btn--disabled or the global disabled state
    expect(sendBtn.classes()).toContain('send-btn--disabled')
  })

  // TC-INT-008: Voice toggle enabled when WS down
  it('TC-INT-008: !wsConnected → 语音切换按钮 enabled', () => {
    const wrapper = mountDisconnected()
    const voiceBtn = findVoiceToggleBtn(wrapper)
    expect(voiceBtn.classes()).not.toContain('icon-btn--disabled')
  })

  // TC-INT-009: Album disabled when WS down
  it('TC-INT-009: !wsConnected → 相册按钮 disabled', () => {
    const wrapper = mountDisconnected()
    const albumBtn = findAlbumBtn(wrapper)
    expect(albumBtn.classes()).toContain('icon-btn--disabled')
  })
})

describe('ChatInputBar — 禁用矩阵 (isStreaming) — TC-INT-010 ~ TC-INT-012', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountStreaming() {
    return mountBar({ wsConnected: true, isStreaming: true })
  }

  // TC-INT-010: Camera disabled when streaming
  it('TC-INT-010: isStreaming → 拍照按钮 disabled', () => {
    const wrapper = mountStreaming()
    expect(findCameraBtn(wrapper).classes()).toContain('icon-btn--disabled')
  })

  // TC-INT-011: Textarea disabled when streaming
  it('TC-INT-011: isStreaming → textarea disabled', () => {
    const wrapper = mountStreaming()
    expect(findTextarea(wrapper).attributes('disabled')).toBeDefined()
  })

  // TC-INT-012: Voice toggle enabled when streaming
  it('TC-INT-012: isStreaming → 语音切换按钮 enabled (AC-003-03)', () => {
    const wrapper = mountStreaming()
    expect(findVoiceToggleBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
  })
})

describe('ChatInputBar — 禁用矩阵 (正常状态) — TC-INT-013 ~ TC-INT-014', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-INT-013: Normal + empty → only send disabled
  it('TC-INT-013: 正常+空输入 → 仅发送按钮 disabled', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // All action buttons should be enabled
    expect(findCameraBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findVoiceToggleBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findAlbumBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findTextarea(wrapper).attributes('disabled')).toBeUndefined()

    // Only send button should be disabled
    const sendBtn = findSendBtn(wrapper)
    expect(sendBtn.classes()).toContain('send-btn--disabled')
  })

  // TC-INT-014: Normal + has text → send button active (blue)
  it('TC-INT-014: 正常+有输入 → 发送按钮高亮 send-btn--active', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Type text into the textarea
    const textarea = findTextarea(wrapper)
    await textarea.setValue('hello')
    await nextTick()

    // Send button should now be active
    const sendBtn = findSendBtn(wrapper)
    expect(sendBtn.classes()).toContain('send-btn--active')
    expect(sendBtn.classes()).not.toContain('send-btn--disabled')
  })
})

describe('ChatInputBar — 事件发射 (emit) — TC-INT-015 ~ TC-INT-018', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-INT-015: emit send with correct payload (text only)
  it('TC-INT-015: 输入文字点击发送 → emit send 正确 payload (仅文本)', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Type text
    const textarea = findTextarea(wrapper)
    await textarea.setValue('你好世界')
    await nextTick()

    // Click send
    await findSendBtn(wrapper).trigger('tap')
    await nextTick()

    // Check emit
    const emitted = wrapper.emitted('send')
    expect(emitted).toBeTruthy()
    expect(emitted[0]).toEqual([{ text: '你好世界', media: [] }])
  })

  // TC-INT-016: emit send with text + media
  it('TC-INT-016: 有图片上传后点击发送 → emit send 正确结构 (图文)', async () => {
    // Mock isUploadIdExpired to return false (not expired)
    isUploadIdExpired.mockReturnValue(false)

    // Setup chooseImage and upload mocks
    uni.chooseImage.mockImplementation((opts) => {
      opts.success({ tempFilePaths: ['/tmp/photo.jpg'] })
    })
    uploadImage.mockResolvedValue({
      upload_id: 'test-upload-id-001',
      expires_in: 600,
      uploaded_at: Date.now(),
    })

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Click camera button to trigger photo flow
    const cameraBtn = findCameraBtn(wrapper)
    await cameraBtn.trigger('tap')

    // Wait for async upload to complete
    await nextTick()
    await new Promise((r) => setTimeout(r, 10))
    await nextTick()

    // Now click send
    const sendBtn = findSendBtn(wrapper)
    await sendBtn.trigger('tap')
    await nextTick()

    // Check unified send emit
    const emitted = wrapper.emitted('send')
    expect(emitted).toBeTruthy()
    expect(emitted[0]).toEqual([{ text: '', media: [{ type: 'image', url: 'test-upload-id-001' }] }])
  })

  // TC-INT-017: emit error with correct format
  it('TC-INT-017: 权限拒绝 → emit error {code, message}', async () => {
    // Mock permission denied
    const permModule = await import('@/utils/permission')
    permModule.requestPermission.mockResolvedValue('denied')

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Switch to voice mode first
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Press hold-to-speak
    const hts = findHoldToSpeak(wrapper)
    await hts.trigger('touchstart')
    await nextTick()

    // Check error emit
    const emitted = wrapper.emitted('error')
    expect(emitted).toBeTruthy()
    expect(emitted[0][0]).toMatchObject({
      code: 'PERMISSION_DENIED',
      message: expect.stringContaining('录音权限'),
    })
  })

  // TC-INT-018: Text cleared after send
  it('TC-INT-018: 发送后输入框清空', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    const textarea = findTextarea(wrapper)
    await textarea.setValue('test message')
    await nextTick()

    // Click send
    await findSendBtn(wrapper).trigger('tap')
    await nextTick()

    // Input should be cleared
    const textareaEl = wrapper.find('textarea')
    expect(textareaEl.element.value).toBe('')
  })
})

describe('ChatInputBar — 语音模式禁用逻辑', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('语音模式下 "按住说话" 在全局禁用时不可交互', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: true })

    // Switch to voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Hold-to-speak should have disabled class
    const hts = findHoldToSpeak(wrapper)
    expect(hts.exists()).toBe(true)
    expect(hts.classes()).toContain('hold-to-speak--disabled')
  })

  it('语音模式下 "按住说话" 在正常状态时可交互', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Switch to voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    const hts = findHoldToSpeak(wrapper)
    expect(hts.exists()).toBe(true)
    expect(hts.classes()).not.toContain('hold-to-speak--disabled')
  })
})
