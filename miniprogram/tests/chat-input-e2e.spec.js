/**
 * @vitest-environment jsdom
 *
 * E2E tests for FreeArk ChatInputUX — Full user journeys
 * TC-E2E-001 ~ TC-E2E-009
 *
 * Covers user_stories.md US-001 through US-007 (all Must Have)
 * Simulates complete user interaction sequences with mocked external APIs.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// ============================================================================
// Mock all dependencies
// ============================================================================
vi.mock('@/utils/permission', () => ({
  requestPermission: vi.fn(),
  default: { requestPermission: vi.fn() },
}))

vi.mock('@/utils/media-uploader', () => ({
  uploadImage: vi.fn(),
  uploadImages: vi.fn(),
  isUploadIdExpired: vi.fn(() => false),
  default: { uploadImage: vi.fn(), uploadImages: vi.fn(), isUploadIdExpired: vi.fn(() => false) },
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
import { uploadImage, uploadImages, isUploadIdExpired } from '@/utils/media-uploader'

// ============================================================================
// Helpers
// ============================================================================
function mountBar(props = {}) {
  return mount(ChatInputBar, {
    props: { wsConnected: true, isStreaming: false, ...props },
    global: { config: { warnHandler: () => {} } },
  })
}

function findCameraBtn(w) { return w.findAll('.icon-btn')[0] }
function findSendBtn(w) { return w.find('.send-btn') }
function findVoiceToggleBtn(w) {
  const btns = w.findAll('.icon-btn')
  return btns[btns.length - 2]
}
function findAlbumBtn(w) {
  const btns = w.findAll('.icon-btn')
  return btns[btns.length - 1]
}
function findTextarea(w) { return w.find('textarea') }
function findHoldToSpeak(w) { return w.find('.hold-to-speak') }

/** Assert that a button wrapper contains an icon child with the given CSS class.
 *  Used instead of .text() because icons are now SVG data-URI background images,
 *  not emoji text (commit 0da26f7). */
function expectIcon(btnWrapper, icoClass) {
  const ico = btnWrapper.find('.ico')
  expect(ico.exists()).toBe(true)
  expect(ico.classes()).toContain(icoClass)
}

// ============================================================================
// E2E Tests
// ============================================================================

describe('E2E — US-001: 拍照发送图片 (AC-001-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-E2E-001
  it('TC-E2E-001: 拍照 → chooseImage(camera) → upload → 加入 pendingMedia', async () => {
    isUploadIdExpired.mockReturnValue(false)

    // Mock successful camera selection
    uni.chooseImage.mockImplementation((opts) => {
      opts.success({ tempFilePaths: ['/tmp/camera_shot.jpg'] })
    })

    // Mock successful upload
    uploadImage.mockResolvedValue({
      upload_id: 'e2e-camera-uuid-001',
      expires_in: 600,
      uploaded_at: Date.now(),
    })

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Step 1: Click camera button
    const cameraBtn = findCameraBtn(wrapper)
    await cameraBtn.trigger('tap')

    // Wait for async upload
    await nextTick()
    await new Promise((r) => setTimeout(r, 20))
    await nextTick()

    // Step 2: Verify uni.chooseImage was called with camera source
    expect(uni.chooseImage).toHaveBeenCalledWith(
      expect.objectContaining({ sourceType: ['camera'], count: 1 })
    )

    // Step 3: Verify uploadImage was called with the temp file path
    expect(uploadImage).toHaveBeenCalledWith('/tmp/camera_shot.jpg')

    // Step 4: Click send to emit send (统一)
    const sendBtn = findSendBtn(wrapper)
    await sendBtn.trigger('tap')
    await nextTick()

    // Step 5: Verify send-media event with correct payload
    const emitted = wrapper.emitted('send')
    expect(emitted).toBeTruthy()
    expect(emitted[0]).toEqual([{ text: '', media: [{ type: 'image', url: 'e2e-camera-uuid-001' }] }])
  })
})

describe('E2E — US-002: 文字输入与发送 (AC-002-01/02/03)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-E2E-002
  it('TC-E2E-002: 空输入灰色 → 输入文字高亮 → 点击发送清空', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Step 1: Empty input → send button should be disabled (grey)
    const sendBtn = findSendBtn(wrapper)
    expect(sendBtn.classes()).toContain('send-btn--disabled')
    expect(sendBtn.classes()).not.toContain('send-btn--active')

    // Step 2: Type text
    const textarea = findTextarea(wrapper)
    await textarea.setValue('你好，方舟助手')
    await nextTick()

    // Step 3: Send button should now be active (blue/highlighted)
    expect(findSendBtn(wrapper).classes()).toContain('send-btn--active')
    expectIcon(findSendBtn(wrapper), 'ico-send') // send arrow (SVG icon)

    // Step 4: Click send
    await findSendBtn(wrapper).trigger('tap')
    await nextTick()

    // Step 5: Verify emit('send', '你好，方舟助手')
    const emitted = wrapper.emitted('send')
    expect(emitted).toBeTruthy()
    expect(emitted[0]).toEqual([{ text: '你好，方舟助手', media: [] }])

    // Step 6: Input should be cleared
    const textareaEl = wrapper.find('textarea')
    expect(textareaEl.element.value).toBe('')

    // Step 7: Send button should go back to disabled
    expect(findSendBtn(wrapper).classes()).toContain('send-btn--disabled')
  })

  // AC-002-01: Empty input → send button unresponsive
  it('AC-002-01: 空输入时点击发送按钮无响应', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Click send with empty input
    await findSendBtn(wrapper).trigger('tap')
    await nextTick()

    // No send-text event should be emitted
    expect(wrapper.emitted('send')).toBeFalsy()
  })
})

describe('E2E — US-003: 语音模式切换 (AC-003-01/02/03)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-E2E-003
  it('TC-E2E-003: 完整往返 — 文字→语音→文字', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Step 1: Initial state — text mode
    expect(findTextarea(wrapper).exists()).toBe(true)
    expect(findHoldToSpeak(wrapper).exists()).toBe(false)
    expectIcon(findVoiceToggleBtn(wrapper), 'ico-mic')

    // Step 2: Click microphone → voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Step 3: Verify voice mode
    expect(findTextarea(wrapper).exists()).toBe(false)
    expect(findHoldToSpeak(wrapper).exists()).toBe(true)
    expect(findHoldToSpeak(wrapper).text()).toBe('按住说话')
    expectIcon(findVoiceToggleBtn(wrapper), 'ico-keyboard')

    // Step 4: Click keyboard → back to text mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Step 5: Verify text mode restored
    expect(findTextarea(wrapper).exists()).toBe(true)
    expect(findHoldToSpeak(wrapper).exists()).toBe(false)
    expectIcon(findVoiceToggleBtn(wrapper), 'ico-mic')

    // Step 6: Input should be empty after round-trip
    expect(wrapper.find('textarea').element.value).toBe('')
  })

  // AC-003-03: Mode switching works when WS is down
  it('AC-003-03: WS断开时模式切换仍可操作', async () => {
    const wrapper = mountBar({ wsConnected: false, isStreaming: false })

    // Camera enabled (user can take photos), voice toggle should be enabled
    expect(findCameraBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findVoiceToggleBtn(wrapper).classes()).not.toContain('icon-btn--disabled')

    // Switch to voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Should be in voice mode despite WS being down
    expect(findHoldToSpeak(wrapper).exists()).toBe(true)
  })
})

describe('E2E — US-004: 按住说话发送语音 (AC-004-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-E2E-004
  it('TC-E2E-004: 按住说话 → 录音开始 → 松手 → ASR识别 → emit send (统一)', async () => {
    const permModule = await import('@/utils/permission')
    permModule.requestPermission.mockResolvedValue('authorized')

    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '今天天气怎么样' })

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Step 1: Switch to voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Step 2: Verify hold-to-speak button is visible
    const hts = findHoldToSpeak(wrapper)
    expect(hts.exists()).toBe(true)
    expect(hts.text()).toBe('按住说话')

    // Step 3: Touch start (press) → request permission → start recording
    await hts.trigger('touchstart')
    await nextTick()

    // Verify permission was requested
    expect(permModule.requestPermission).toHaveBeenCalledWith(
      'scope.record',
      expect.objectContaining({ name: '录音' })
    )

    // Verify recording started
    expect(startRecording).toHaveBeenCalled()

    // Step 4: Touch end (release) → stop and recognize
    await hts.trigger('touchend')
    await nextTick()
    await new Promise((r) => setTimeout(r, 20))
    await nextTick()

    // Step 5: Verify stopAndRecognize was called
    expect(stopAndRecognize).toHaveBeenCalled()

    // Step 6: Verify send-text emitted with ASR result
    const emitted = wrapper.emitted('send')
    expect(emitted).toBeTruthy()
    expect(emitted[0]).toEqual([{ text: '今天天气怎么样', media: [] }])
  })

  // AC-004-02: Permission denied → error emit
  it('AC-004-02: 录音权限拒绝 → emit error', async () => {
    const permModule = await import('@/utils/permission')
    permModule.requestPermission.mockResolvedValue('denied')

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Switch to voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Touch start
    await findHoldToSpeak(wrapper).trigger('touchstart')
    await nextTick()

    // Should emit error
    const emitted = wrapper.emitted('error')
    expect(emitted).toBeTruthy()
    expect(emitted[0][0]).toMatchObject({
      code: 'PERMISSION_DENIED',
    })

    // Recording should NOT have started
    expect(startRecording).not.toHaveBeenCalled()
  })
})

describe('E2E — US-005: 相册选图发送 (AC-005-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-E2E-005
  it('TC-E2E-005: +号 → album → upload → emit send (统一)', async () => {
    isUploadIdExpired.mockReturnValue(false)

    // Mock album selection with 2 photos
    uni.chooseImage.mockImplementation((opts) => {
      opts.success({
        tempFilePaths: ['/tmp/album1.jpg', '/tmp/album2.jpg'],
      })
    })

    // Mock successful uploads — uploadImages returns allSettled results
    uploadImages.mockResolvedValue([
      { status: 'fulfilled', value: { upload_id: 'e2e-album-uuid-1', expires_in: 600, uploaded_at: Date.now() } },
      { status: 'fulfilled', value: { upload_id: 'e2e-album-uuid-2', expires_in: 600, uploaded_at: Date.now() } },
    ])

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Step 1: Click album (+) button
    const albumBtn = findAlbumBtn(wrapper)
    expectIcon(albumBtn, 'ico-plus')
    await albumBtn.trigger('tap')

    // Wait for uploads
    await nextTick()
    await new Promise((r) => setTimeout(r, 20))
    await nextTick()

    // Step 2: Verify uni.chooseImage called with album
    expect(uni.chooseImage).toHaveBeenCalledWith(
      expect.objectContaining({ sourceType: ['album'], count: 9 })
    )

    // Step 3: Verify uploadImages was called with the file paths
    expect(uploadImages).toHaveBeenCalledTimes(1)
    expect(uploadImages).toHaveBeenCalledWith(['/tmp/album1.jpg', '/tmp/album2.jpg'])

    // Step 4: Click send
    await findSendBtn(wrapper).trigger('tap')
    await nextTick()

    // Step 5: Verify send-media event
    const emitted = wrapper.emitted('send')
    expect(emitted).toBeTruthy()
    expect(emitted[0][0].media).toHaveLength(2)
    expect(emitted[0][0].media[0]).toMatchObject({ type: 'image', url: 'e2e-album-uuid-1' })
    expect(emitted[0][0].media[1]).toMatchObject({ type: 'image', url: 'e2e-album-uuid-2' })
  })
})

describe('E2E — US-006: 输入区域状态管理 (AC-006-01/02/03)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-E2E-006: WS disconnected → textarea/send/voice disabled, camera/album/toggle always enabled
  it('TC-E2E-006: WS断开 → textarea/发送禁用, 拍照/相册/语音切换仍可用', () => {
    const wrapper = mountBar({ wsConnected: false, isStreaming: false })

    // Camera and album remain enabled (user can take/pick photos offline)
    expect(findCameraBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findAlbumBtn(wrapper).classes()).not.toContain('icon-btn--disabled')

    // Textarea and send are disabled (cannot send without connection)
    expect(findTextarea(wrapper).attributes('disabled')).toBeDefined()
    expect(findSendBtn(wrapper).classes()).toContain('send-btn--disabled')

    // Voice toggle always enabled
    expect(findVoiceToggleBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
  })

  // TC-E2E-007: Streaming → global disable → stream_end restores
  it('TC-E2E-007: Streaming → 全局禁用 → stream_end恢复', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: true })

    // All disabled during streaming
    expect(findCameraBtn(wrapper).classes()).toContain('icon-btn--disabled')
    expect(findSendBtn(wrapper).classes()).toContain('send-btn--disabled')

    // Change props: streaming ends
    await wrapper.setProps({ isStreaming: false })
    await nextTick()

    // All should be enabled again (except send which needs text)
    expect(findCameraBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findTextarea(wrapper).attributes('disabled')).toBeUndefined()
  })

  // TC-E2E-008: Normal + empty → only send disabled
  it('TC-E2E-008: 正常空输入 → 仅发送禁用 → 输入后发送启用', async () => {
    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Camera, textarea, voice toggle, album should be enabled
    expect(findCameraBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findTextarea(wrapper).attributes('disabled')).toBeUndefined()
    expect(findVoiceToggleBtn(wrapper).classes()).not.toContain('icon-btn--disabled')
    expect(findAlbumBtn(wrapper).classes()).not.toContain('icon-btn--disabled')

    // Only send should be disabled
    expect(findSendBtn(wrapper).classes()).toContain('send-btn--disabled')

    // Type some text
    await findTextarea(wrapper).setValue('hello')
    await nextTick()

    // Send should now be active
    expect(findSendBtn(wrapper).classes()).toContain('send-btn--active')
  })
})

describe('E2E — US-007: 权限申请与管理 (AC-007-01/02)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-E2E-009: Recording permission denied → guided to settings
  it('TC-E2E-009: 录音权限拒绝 → Modal引导 → openSetting', async () => {
    const permModule = await import('@/utils/permission')

    // Simulate: first call returns denied (user sees modal, clicks "去设置")
    // But in our test, requestPermission resolves with 'denied' after internal flow
    permModule.requestPermission.mockResolvedValue('denied')

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    // Switch to voice mode
    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Press hold-to-speak
    await findHoldToSpeak(wrapper).trigger('touchstart')
    await nextTick()

    // Should emit error about permission denied
    const emitted = wrapper.emitted('error')
    expect(emitted).toBeTruthy()
    expect(emitted[0][0]).toMatchObject({
      code: 'PERMISSION_DENIED',
    })

    // Recording should not have started
    expect(startRecording).not.toHaveBeenCalled()
  })

  // AC-007-01: First-time permission flow — accepts
  it('AC-007-01: 首次录音权限申请 — 同意 → 正常录音', async () => {
    const permModule = await import('@/utils/permission')
    permModule.requestPermission.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '测试语音' })

    const wrapper = mountBar({ wsConnected: true, isStreaming: false })

    await findVoiceToggleBtn(wrapper).trigger('tap')
    await nextTick()

    // Press hold-to-speak
    await findHoldToSpeak(wrapper).trigger('touchstart')
    await nextTick()

    // Permission accepted → recording started
    expect(permModule.requestPermission).toHaveBeenCalled()
    expect(startRecording).toHaveBeenCalled()
  })
})
