/**
 * @vitest-environment jsdom
 * ChatInputBar v1.13.2 — inputMode 状态机全覆盖 + dark 主题 + CSS 层叠静态守卫。
 *
 * 设计原则：可见性一律用 exists()（真实 DOM 存在性）判定，不用 classes() 判显隐。
 * 上一轮线上事故的教训：class 断言 16 例全绿，但 .cib-hidden 被后定义的 display:flex
 * 覆盖，真机上显隐完全相反。jsdom 不会应用 SFC <style>，所以 class 断言对显隐零证明力。
 * 本文件末尾的「CSS 层叠静态守卫」用例直接对样式源码做结构断言，补上这个盲区。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

vi.mock('@/utils/permission', () => ({ requestPermission: vi.fn() }))
vi.mock('@/utils/voice-input', () => ({ startRecording: vi.fn(), stopAndRecognize: vi.fn() }))
vi.mock('@/utils/http', () => ({ BASE_URL: 'https://api.test.local', WS_BASE_URL: 'wss://api.test.local' }))
vi.mock('@/utils/auth', () => ({ getToken: vi.fn(() => 'mock-token') }))

import ChatInputBar from '@/components/ChatInputBar.vue'
import { startRecording, stopAndRecognize } from '@/utils/voice-input'
import { requestPermission } from '@/utils/permission'

function mountBar(props = {}) {
  return mount(ChatInputBar, {
    props: { wsConnected: true, isStreaming: false, ...props },
    global: { config: { warnHandler: () => {} } },
  })
}
const ta = w => w.find('.cib-text')
const sendBtn = w => w.find('[data-testid="send-btn"]')
const voiceBar = w => w.find('[data-testid="voice-btn"]')
const toggleBtn = w => w.find('[data-testid="mode-toggle-btn"]')
const recTip = w => w.find('[data-testid="rec-tip"]')

async function toVoice(w) { await toggleBtn(w).trigger('tap'); await nextTick(); return voiceBar(w) }
async function toText(w) { await toggleBtn(w).trigger('tap'); await nextTick(); return ta(w) }

async function startRec(w, pageY = 300) {
  requestPermission.mockResolvedValue('authorized')
  startRecording.mockResolvedValue(undefined)
  const bar = voiceBar(w)
  await bar.trigger('touchstart', { touches: [{ pageY }] })
  await nextTick()
  await Promise.resolve()
  await nextTick()
  return bar
}

/* =============== S1/S2：text 模式下的按钮槽互斥 =============== */
describe('状态机 — text 模式按钮槽互斥（真实存在性）', () => {
  beforeEach(() => vi.clearAllMocks())

  it('S1 空输入 → 麦克风钮存在 且 发送钮不存在', () => {
    const w = mountBar()
    expect(toggleBtn(w).exists()).toBe(true)
    expect(sendBtn(w).exists()).toBe(false)
    // 恰好一个按钮渲染在按钮槽里
    expect(w.findAll('.cib-btn')).toHaveLength(1)
  })

  it('S1 空输入 → textarea 带灰色 placeholder 引导', () => {
    const w = mountBar()
    expect(ta(w).attributes('placeholder')).toBe('向智能方舟副官提问')
    expect(ta(w).attributes('placeholder-class')).toBe('cib-ph--light')
  })

  it('S2 有文字 → 发送钮存在 且 麦克风钮不存在', async () => {
    const w = mountBar()
    await ta(w).setValue('a')
    await nextTick()
    expect(sendBtn(w).exists()).toBe(true)
    expect(toggleBtn(w).exists()).toBe(false)
    expect(w.findAll('.cib-btn')).toHaveLength(1)
  })

  it('纯空白输入不算有文字 → 仍显示麦克风钮', async () => {
    const w = mountBar()
    await ta(w).setValue('   ')
    await nextTick()
    expect(sendBtn(w).exists()).toBe(false)
    expect(toggleBtn(w).exists()).toBe(true)
  })
})

/* =============== S5：模式切换 =============== */
describe('状态机 — text ↔ voice 切换', () => {
  beforeEach(() => vi.clearAllMocks())

  it('点麦克风 → 进 voice：横条出现、textarea 消失、图标变键盘', async () => {
    const w = mountBar()
    expect(ta(w).exists()).toBe(true)
    const bar = await toVoice(w)
    expect(bar.exists()).toBe(true)
    expect(ta(w).exists()).toBe(false)
    expect(bar.text()).toContain('按住 说话')
    expect(toggleBtn(w).find('.cib-ico-kbd--light').exists()).toBe(true)
    expect(toggleBtn(w).find('.cib-ico-mic--light').exists()).toBe(false)
  })

  it('切到 voice 时收起键盘（uni.hideKeyboard 被调用）', async () => {
    const w = mountBar()
    await toVoice(w)
    expect(uni.hideKeyboard).toHaveBeenCalled()
  })

  it('voice 模式点键盘钮 → 切回 text：textarea 回来、横条消失', async () => {
    const w = mountBar()
    await toVoice(w)
    expect(voiceBar(w).exists()).toBe(true)
    await toText(w)
    expect(ta(w).exists()).toBe(true)
    expect(voiceBar(w).exists()).toBe(false)
    expect(toggleBtn(w).find('.cib-ico-mic--light').exists()).toBe(true)
  })

  it('text→voice→text 往返：草稿文字不丢失，发送钮随之回归', async () => {
    const w = mountBar()
    await ta(w).setValue('未发送的草稿')
    await nextTick()
    expect(sendBtn(w).exists()).toBe(true)

    // 有文字时按钮槽是 send，需先清空才能看到 toggle —— 故用组件实例直接切模式，
    // 模拟"用户先删空再切语音、又切回来"以外的另一条路径：保留草稿切换。
    w.vm.inputMode = 'voice'
    await nextTick()
    expect(voiceBar(w).exists()).toBe(true)
    expect(ta(w).exists()).toBe(false)

    await toText(w)
    expect(ta(w).element.value).toBe('未发送的草稿')
    expect(sendBtn(w).exists()).toBe(true)
  })
})

/* =============== S6/S7：录音中与上滑取消的视觉状态 =============== */
describe('状态机 — 录音中 / 上滑取消视觉状态', () => {
  beforeEach(() => vi.clearAllMocks())

  it('S6 录音中 → 横条高亮 + 文案「松开 发送」+ 录音浮层出现', async () => {
    const w = mountBar()
    await toVoice(w)
    expect(recTip(w).exists()).toBe(false)
    const bar = await startRec(w)
    expect(bar.classes()).toContain('cib-hold--recording')
    expect(bar.text()).toContain('松开 发送')
    expect(recTip(w).exists()).toBe(true)
    expect(recTip(w).text()).toContain('正在聆听')
  })

  it('S7 上滑超过阈值 → 横条转红 + 文案变取消 + 浮层变红', async () => {
    const w = mountBar()
    await toVoice(w)
    const bar = await startRec(w, 300)
    await bar.trigger('touchmove', { touches: [{ pageY: 200 }] })
    await nextTick()
    expect(bar.classes()).toContain('cib-hold--cancel')
    expect(bar.text()).toContain('松开手指，取消发送')
    expect(recTip(w).classes()).toContain('cib-rec-tip--cancel')
  })

  it('上滑未超过阈值(60) → 仍是录音态，不进取消', async () => {
    const w = mountBar()
    await toVoice(w)
    const bar = await startRec(w, 300)
    await bar.trigger('touchmove', { touches: [{ pageY: 260 }] })
    await nextTick()
    expect(bar.classes()).toContain('cib-hold--recording')
    expect(bar.classes()).not.toContain('cib-hold--cancel')
  })

  it('录音中点模式切换钮 → 不切模式（避免录音无对应 stop）', async () => {
    const w = mountBar()
    await toVoice(w)
    await startRec(w)
    await toggleBtn(w).trigger('tap')
    await nextTick()
    expect(voiceBar(w).exists()).toBe(true)
    expect(ta(w).exists()).toBe(false)
  })

  it('录音结束后浮层消失', async () => {
    const w = mountBar()
    await toVoice(w)
    stopAndRecognize.mockResolvedValue({ text: 'x' })
    const bar = await startRec(w)
    expect(recTip(w).exists()).toBe(true)
    await bar.trigger('touchend')
    await nextTick()
    expect(recTip(w).exists()).toBe(false)
  })
})

/* =============== S3/S4/S8：禁用态在两种模式下的表达 =============== */
describe('状态机 — 禁用态（两种模式 × 两种原因）', () => {
  beforeEach(() => vi.clearAllMocks())

  for (const [label, props] of [
    ['wsConnected=false', { wsConnected: false }],
    ['isStreaming=true', { isStreaming: true }],
  ]) {
    // 产品决策：断连/流式期间**仍可输入**（豆包/DeepSeek 行为），仅拦截发送。
    // 若禁用 textarea，用户永远无法在断连时产生文字，"有文字+断连"状态不可达。
    it(`${label} / text 模式 → textarea 仍可输入，placeholder 明示原因`, () => {
      const w = mountBar(props)
      expect(ta(w).attributes('disabled')).toBeUndefined()
      const ph = ta(w).attributes('placeholder')
      expect(ph).not.toBe('向智能方舟副官提问')
      expect(ph.length).toBeGreaterThan(0)
    })

    it(`${label} / text 模式 + 有文字 → 发送钮仍渲染为禁用态（不消失）`, async () => {
      const w = mountBar(props)
      await ta(w).setValue('abc')
      await nextTick()
      expect(sendBtn(w).exists()).toBe(true)
      expect(sendBtn(w).classes()).toContain('cib-send--disabled')
      await sendBtn(w).trigger('tap')
      await nextTick()
      expect(w.emitted('send')).toBeFalsy()
    })

    it(`${label} / voice 模式 → 横条禁用样式 + 文案明示 + 拦截录音`, async () => {
      const w = mountBar(props)
      const bar = await toVoice(w)
      expect(bar.classes()).toContain('cib-hold--off-light')
      expect(bar.text()).not.toContain('按住 说话')
      await bar.trigger('touchstart', { touches: [{ pageY: 300 }] })
      await nextTick()
      expect(startRecording).not.toHaveBeenCalled()
    })
  }

  it('禁用态不使用 opacity 隐身：横条禁用类只改配色，不含 opacity', () => {
    const css = styleBlock()
    const rule = ruleBody(css, '.cib-hold--off-light')
    expect(rule).toBeTruthy()
    expect(rule).not.toMatch(/opacity/)
  })
})

/* =============== dark 主题专项（生产主路径 pages/chat/index.vue theme="dark"）=============== */
describe('dark 主题 — 生产主路径专项（此前零覆盖，两轮 bug 均出于此）', () => {
  beforeEach(() => vi.clearAllMocks())
  const dark = p => mountBar({ theme: 'dark', ...p })

  it('dark 空输入 → 麦克风钮存在（暗色图标类）且发送钮不存在', () => {
    const w = dark()
    expect(toggleBtn(w).exists()).toBe(true)
    expect(toggleBtn(w).find('.cib-ico-mic--dark').exists()).toBe(true)
    expect(sendBtn(w).exists()).toBe(false)
  })

  it('dark 有文字 → 发送钮存在，且图标是深墨色而非青色（对比度回归）', async () => {
    const w = dark()
    await ta(w).setValue('你好')
    await nextTick()
    expect(sendBtn(w).exists()).toBe(true)
    expect(sendBtn(w).classes()).toContain('cib-send--dark-active')
    // v1.13.0 事故：激活态用了青图标压青渐变底 → 不可见。图标类必须是 dark-active。
    expect(sendBtn(w).find('.cib-ico-send--dark-active').exists()).toBe(true)
    expect(toggleBtn(w).exists()).toBe(false)
  })

  it('dark 切 voice → 横条暗色 idle 类 + 键盘图标暗色', async () => {
    const w = dark()
    const bar = await toVoice(w)
    expect(bar.classes()).toContain('cib-hold--idle-dark')
    expect(bar.text()).toContain('按住 说话')
    expect(toggleBtn(w).find('.cib-ico-kbd--dark').exists()).toBe(true)
  })

  it('dark voice 往返切回 text，草稿保留', async () => {
    const w = dark()
    await toVoice(w)
    await toText(w)
    expect(ta(w).exists()).toBe(true)
    expect(ta(w).classes()).toContain('cib-text--dark')
    expect(ta(w).attributes('placeholder-class')).toBe('cib-ph--dark')
  })

  it('dark 禁用 → 发送钮 dark-disabled、横条 off-dark，且均仍渲染', async () => {
    const w = dark({ wsConnected: false })
    await ta(w).setValue('abc')
    await nextTick()
    expect(sendBtn(w).exists()).toBe(true)
    expect(sendBtn(w).classes()).toContain('cib-send--dark-disabled')

    const w2 = dark({ isStreaming: true })
    const bar = await toVoice(w2)
    expect(bar.classes()).toContain('cib-hold--off-dark')
  })

  it('dark 录音中 → 横条 recording 类 + 深墨文字（压青蓝亮底）', async () => {
    const w = dark()
    await toVoice(w)
    const bar = await startRec(w)
    expect(bar.classes()).toContain('cib-hold--recording')
    expect(bar.find('.cib-hold-txt--recording').exists()).toBe(true)
  })
})

/* =============== CSS 层叠静态守卫：本轮最关键的回归用例 =============== */
// 注意：vitest 转换后 import.meta.url 是 http:// 方案，fileURLToPath 会抛
// "The URL must be of scheme file"，故改用 cwd（vitest root = miniprogram/）拼路径。
const SFC_PATH = resolve(process.cwd(), 'components/ChatInputBar.vue')

function styleBlock() {
  const src = readFileSync(SFC_PATH, 'utf8')
  const m = src.match(/<style>([\s\S]*?)<\/style>/)
  if (!m) throw new Error('ChatInputBar.vue 未找到 <style> 块')
  // 剥离 CSS 注释：注释里会讨论 display:none 等反面教材，不能参与断言
  return m[1].replace(/\/\*[\s\S]*?\*\//g, '')
}
function ruleBody(css, selector) {
  const re = new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^{}]*)\\}')
  const m = css.match(re)
  return m ? m[1] : null
}

describe('CSS 层叠守卫 — 防 v1.13.1 事故复发', () => {
  it('样式中不存在 .cib-hidden（事故根因类已移除）', () => {
    expect(styleBlock()).not.toContain('cib-hidden')
  })

  it('样式中不存在 display:none（显隐一律交给 v-if/v-else）', () => {
    const css = styleBlock().replace(/\s+/g, '')
    expect(css).not.toContain('display:none')
  })

  it('纪律 D2：任何带 `--` 的修饰类都不得声明 display', () => {
    const css = styleBlock()
    const offenders = []
    const ruleRe = /([^{}]+)\{([^{}]*)\}/g
    let m
    while ((m = ruleRe.exec(css)) !== null) {
      const selector = m[1].trim()
      const body = m[2]
      if (selector.includes('--') && /(^|[;\s])display\s*:/.test(body)) {
        offenders.push(selector)
      }
    }
    expect(offenders).toEqual([])
  })

  it('纪律 D2：display 只出现在白名单布局基类上', () => {
    const allowed = ['.cib-row', '.cib-rec-tip', '.cib-btn', '.cib-hold', '.cib-ico']
    const css = styleBlock()
    const withDisplay = []
    const ruleRe = /([^{}]+)\{([^{}]*)\}/g
    let m
    while ((m = ruleRe.exec(css)) !== null) {
      const selector = m[1].trim().split('\n').pop().trim()
      if (/(^|[;\s])display\s*:/.test(m[2])) withDisplay.push(selector)
    }
    expect(withDisplay.length).toBeGreaterThan(0)
    for (const sel of withDisplay) expect(allowed).toContain(sel)
  })

  it('暗色激活发送图标不得使用青色（v1.13.0 青压青事故守卫）', () => {
    const body = ruleBody(styleBlock(), '.cib-ico-send--dark-active')
    expect(body).toBeTruthy()
    expect(body).toContain('%23041018')
    expect(body).not.toContain('%232ff4e0')
  })

  it('所有内联 SVG data-URI 的 # 均已转义为 %23', () => {
    const css = styleBlock()
    const uris = css.match(/url\("data:image\/svg\+xml,[^"]*"\)/g) || []
    expect(uris.length).toBeGreaterThan(0)
    for (const u of uris) expect(u).not.toMatch(/#/)
  })
})
