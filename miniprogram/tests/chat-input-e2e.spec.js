/**
 * @vitest-environment jsdom
 * ChatInputBar E2E — v1.13.2: 显式 inputMode 状态机；显隐由 v-if/v-else 承担。
 * 调整同 chat-input-bar.spec.js：语音路径需先经 mode-toggle-btn 切到 voice 模式。
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
async function toVoice(w) {
  await findToggleBtn(w).trigger('tap')
  await nextTick()
  return findVoiceBar(w)
}

describe('E2E — 文字输入发送', () => {
  beforeEach(() => vi.clearAllMocks())

  // [改] 首尾两处"发送钮为 disabled 类"改为"发送钮不存在、切换钮在位"——
  // 这才是新模型下空输入的真实 DOM 状态，且是真可见性断言而非 class 断言。
  it('空输入无发送钮 → 输入后出现并高亮 → 发送 → 清空 → 退回切换钮', async () => {
    const w = mountBar()
    expect(findSendBtn(w).exists()).toBe(false)
    expect(findToggleBtn(w).exists()).toBe(true)

    await findTextarea(w).setValue('你好方舟')
    await nextTick()
    expect(findSendBtn(w).exists()).toBe(true)
    expect(findSendBtn(w).classes()).toContain('cib-send--active')
    expect(findToggleBtn(w).exists()).toBe(false)

    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')[0]).toEqual([{ text: '你好方舟', media: [] }])
    expect(w.find('textarea').element.value).toBe('')
    expect(findSendBtn(w).exists()).toBe(false)
    expect(findToggleBtn(w).exists()).toBe(true)
  })
})

describe('E2E — 语音录音发送', () => {
  beforeEach(() => vi.clearAllMocks())

  // [改] 仅新增 toVoice() 前置步骤。
  it('切语音 → 长按录音 → 松手识别 → emit 文字', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue({ text: '天气怎么样' })
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
    expect(w.emitted('send')[0]).toEqual([{ text: '天气怎么样', media: [] }])
  })

  // [改] 仅新增 toVoice() 前置步骤。
  it('权限拒绝 → 不录音', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('denied')
    const w = mountBar()
    const bar = await toVoice(w)
    await bar.trigger('touchstart')
    await nextTick()
    expect(w.emitted('error')[0][0]).toMatchObject({ code: 'PERMISSION_DENIED' })
    expect(startRecording).not.toHaveBeenCalled()
  })

  // [新增] 语音识别返回裸 string 的兼容形态（stopAndRecognize 双返回形态之一），
  // 该分支此前无任何用例覆盖。
  it('识别结果为裸 string 形态 → 同样 emit', async () => {
    const { requestPermission: rp } = await import('@/utils/permission')
    rp.mockResolvedValue('authorized')
    startRecording.mockResolvedValue(undefined)
    stopAndRecognize.mockResolvedValue('纯字符串结果')
    const w = mountBar()
    const bar = await toVoice(w)
    await bar.trigger('touchstart')
    await nextTick()
    await bar.trigger('touchend')
    await new Promise(r => setTimeout(r, 20))
    await nextTick()
    expect(w.emitted('send')[0]).toEqual([{ text: '纯字符串结果', media: [] }])
  })
})

describe('E2E — 状态管理', () => {
  beforeEach(() => vi.clearAllMocks())

  // [改] send 断言改为存在性；语音拦截加 toVoice 前置。
  it('WS 断开 → textarea 仍可输入 + 空输入无发送钮 + 语音操作被拦截', async () => {
    const w = mountBar({ wsConnected: false })
    expect(findTextarea(w).attributes('disabled')).toBeUndefined()
    expect(findSendBtn(w).exists()).toBe(false)
    const bar = await toVoice(w)
    expect(bar.exists()).toBe(true)
    await bar.trigger('touchstart')
    await nextTick()
    expect(startRecording).not.toHaveBeenCalled()
  })

  // [改] textarea 不再被禁用，改以 placeholder + 发送钮可用性表达恢复。
  it('Streaming 结束 → 提示与发送能力恢复', async () => {
    const w = mountBar({ isStreaming: true })
    expect(findTextarea(w).attributes('placeholder')).toBe('副官正在回复…')

    await findTextarea(w).setValue('你好')
    await nextTick()
    // 流式期间：发送钮渲染但为禁用态，点击不 emit
    expect(findSendBtn(w).exists()).toBe(true)
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')).toBeFalsy()

    await w.setProps({ isStreaming: false })
    await nextTick()
    expect(findTextarea(w).attributes('placeholder')).toBe('向智能方舟副官提问')
    await findSendBtn(w).trigger('tap')
    await nextTick()
    expect(w.emitted('send')).toBeTruthy()
  })
})
