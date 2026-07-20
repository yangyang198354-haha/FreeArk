/**
 * @vitest-environment jsdom
 * ChatInputBar tests — v1.13.2 显式 inputMode 状态机（text | voice）。
 *
 * 相对 v1.13.1 的用例调整总纲（逐例理由见各 it 上方注释）：
 *   1. 显隐改由 v-if/v-else 承担，因此"某按钮不可用"一律断言 exists()===false，
 *      而不是断言某个 class 名。上一轮线上事故正是"class 断言全绿、真实显隐相反"。
 *   2. data-testid="voice-btn" 的载体从麦克风圆钮改为「按住 说话」横条（它才是录音控件），
 *      横条只在 voice 模式渲染，故所有语音用例需先经 mode-toggle-btn 切换模式。
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
function findSendBtn(w) { return w.find('[data-testid="send-btn"]') }
function findVoiceBar(w) { return w.find('[data-testid="voice-btn"]') }
function findToggleBtn(w) { return w.find('[data-testid="mode-toggle-btn"]') }

/** 切到语音模式：新交互下所有录音操作的前置步骤 */
async function toVoice(w) {
  await findToggleBtn(w).trigger('tap')
  await nextTick()
  return findVoiceBar(w)
}

describe('ChatInputBar — 初始状态', () => {
  beforeEach(() => vi.clearAllMocks())

  // [改] 原断言"textarea/发送/语音三者都存在"。新模型下按钮槽是二选一：
  // 空输入时只渲染 mode-toggle-btn，send-btn 结构上不存在。
  it('空输入 → textarea + 模式切换钮存在，发送钮不存在', () => {
    const w = mountBar()
    expect(findTextarea(w).exists()).toBe(true)
    expect(findToggleBtn(w).exists()).toBe(true)
    expect(findSendBtn(w).exists()).toBe(false)
  })

  // [改] 原为 `expect(sendBtn.classes()).toContain('cib-send--disabled')`。
  // 新模型里"空输入不可发送"由不渲染表达，断言真实存在性而非 class。
  it('空输入 → 显示麦克风图标（提示可切语音）', () => {
    const w = mountBar()
    expect(findToggleBtn(w).exists()).toBe(true)
    expect(findToggleBtn(w).find('.cib-ico-mic--light').exists()).toBe(true)
  })

  // [保留 + 增强] cib-send--active 类名未变；补一条 toggle 消失的可见性断言。
  it('输入文字后 → 发送钮出现并高亮，切换钮消失', async () => {
    const w = mountBar()
    await findTextarea(w).setValue('hello')
    await nextTick()
    expect(findSendBtn(w).exists()).toBe(true)
    expect(findSendBtn(w).classes()).toContain('cib-send--active')
    expect(findToggleBtn(w).exists()).toBe(false)
  })

  // [改] 原为"语音按钮默认存在且 class 含 cib-mic"。voice-btn 现在是「按住说话」横条，
  // 默认 text 模式下不渲染，需先切模式。
  it('默认无语音横条；切到语音模式后出现', async () => {
    const w = mountBar()
    expect(findVoiceBar(w).exists()).toBe(false)
    const bar = await toVoice(w)
    expect(bar.exists()).toBe(true)
    expect(bar.text()).toContain('按住 说话')
  })
})

describe('ChatInputBar — 发送文字', () => {
  beforeEach(() => vi.clearAllMocks())

  // [保留] 逐字未改。
  it('输入 → 发送 → emit + 清空', async () => {
    const w = mountBar()
    await findTextarea(w).setValue('你好')
    await nextTick()
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')[0]).toEqual([{ text: '你好', media: [] }])
    expect(w.find('textarea').element.value).toBe('')
  })

  // [改写] 原用例对空输入态的 send-btn 直接 trigger('tap')。新设计下该元素不存在，
  // 用例拆成两半：(1) 空输入下元素确实不存在；(2) JS 守卫仍在（见下一例）。
  it('空输入 → 发送钮不存在，无法误触发送', async () => {
    const w = mountBar()
    expect(findSendBtn(w).exists()).toBe(false)
    expect(w.emitted('send')).toBeFalsy()
  })

  it('有文字但 WS 断开 → 发送钮可见但点击不 emit（JS 守卫）', async () => {
    const w = mountBar({ wsConnected: false })
    await findTextarea(w).setValue('你好')
    await nextTick()
    expect(findSendBtn(w).exists()).toBe(true)
    expect(findSendBtn(w).classes()).toContain('cib-send--disabled')
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')).toBeFalsy()
  })
})

describe('ChatInputBar — 语音录音', () => {
  beforeEach(() => vi.clearAllMocks())

  // [改] 仅新增 toVoice() 前置步骤，录音断言逐字未改。
  it('长按→录音→松手→emit', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '识别结果' })
    const w = mountBar()
    const bar = await toVoice(w)
    await bar.trigger('touchstart')
    await nextTick()
    expect(startRecording).toHaveBeenCalled()
    await bar.trigger('touchend')
    await nextTick()
    await new Promise(r => setTimeout(r, 20))
    await nextTick()
    expect(stopAndRecognize).toHaveBeenCalled()
    expect(w.emitted('send')[0]).toEqual([{ text: '识别结果', media: [] }])
  })

  // [改] 仅新增 toVoice() 前置步骤。
  it('权限拒绝 → emit error', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('denied')
    const w = mountBar()
    const bar = await toVoice(w)
    await bar.trigger('touchstart')
    await nextTick()
    expect(w.emitted('error')[0][0]).toMatchObject({ code: 'PERMISSION_DENIED' })
    expect(startRecording).not.toHaveBeenCalled()
  })

  // [改] 仅新增 toVoice() 前置步骤；上滑阈值 60 的语义未变。
  it('上滑取消 → 不发送', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    const w = mountBar()
    const bar = await toVoice(w)
    await bar.trigger('touchstart', { touches: [{ pageY: 300 }] })
    await nextTick()
    await bar.trigger('touchmove', { touches: [{ pageY: 200 }] })
    await nextTick()
    await bar.trigger('touchend')
    await nextTick()
    expect(w.emitted('send')).toBeFalsy()
  })
})

describe('ChatInputBar — 禁用逻辑', () => {
  beforeEach(() => vi.clearAllMocks())

  // [改] send-btn 断言换成"空输入下不存在"；语音拦截断言加 toVoice 前置。
  it('WS断开 → textarea仍可输入 + 空输入无发送钮 + 语音操作被拦截', async () => {
    const w = mountBar({ wsConnected: false })
    expect(findTextarea(w).attributes('disabled')).toBeUndefined()
    expect(findSendBtn(w).exists()).toBe(false)
    const bar = await toVoice(w)
    expect(bar.exists()).toBe(true)
    await bar.trigger('touchstart')
    await nextTick()
    expect(startRecording).not.toHaveBeenCalled()
  })

  // [改] 同上。
  it('Streaming → 可输入但发送/语音被拦截', async () => {
    const w = mountBar({ isStreaming: true })
    expect(findTextarea(w).attributes('disabled')).toBeUndefined()
    expect(findSendBtn(w).exists()).toBe(false)
    const bar = await toVoice(w)
    await bar.trigger('touchstart')
    await nextTick()
    expect(startRecording).not.toHaveBeenCalled()
  })
})
