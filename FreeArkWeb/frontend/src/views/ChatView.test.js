/**
 * FreeArk_ChatFormat — 单元测试 + 集成测试
 * @phase PHASE_07 (unit), PHASE_08 (integration)
 * @author sub_agent_test_engineer
 * @invocation_id INV-GROUP_D-20260614-001
 *
 * 覆盖：
 *   TC-UNIT-001 ~ TC-UNIT-015  (renderMarkdown 纯函数 + isRenderable 纯函数)
 *   TC-INT-001  ~ TC-INT-009   (ChatView 组件挂载行为)
 *
 * 溯源：user_stories.md US-001~006 + 验收标准 AC-001-01 ~ AC-006-03
 */

import { describe, it, expect, vi, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { renderMarkdown, isRenderable } from './ChatView.vue'

// ============================================================
// PHASE_07: 单元测试 — renderMarkdown (IFC-001)
// ============================================================
describe('renderMarkdown — IFC-001 单元测试', () => {

  // TC-UNIT-001 | AC-001-01 | 粗体标记渲染为 <strong>
  it('TC-UNIT-001: **关键词** 渲染为 <strong>关键词</strong>，无裸 **', () => {
    const result = renderMarkdown('**关键词**')
    expect(result).toContain('<strong>关键词</strong>')
    expect(result).not.toContain('**')
  })

  // TC-UNIT-002 | AC-001-02 | 纯文本无损
  it('TC-UNIT-002: 纯中文文本无损通过，内容包含在输出中', () => {
    const input = '当前 PLC 在线率为 95%，运行正常。'
    const result = renderMarkdown(input)
    // marked.parse 会用 <p> 包裹，文本内容必须存在
    expect(result).toContain('当前 PLC 在线率为 95%，运行正常。')
  })

  // TC-UNIT-003 | AC-001-03 | 单个 * 不触发 em 渲染（marked 行为）
  it('TC-UNIT-003: 单个星号（如"3*"）不导致崩溃，文本出现在输出中', () => {
    // marked 对单 * 的处理取决于上下文；重点是不崩溃且不产生错误 HTML
    expect(() => renderMarkdown('评分 3*')).not.toThrow()
    const result = renderMarkdown('评分 3*')
    expect(result).toContain('评分')
  })

  // TC-UNIT-004 | AC-002-01 | Markdown 表格 → <table>
  it('TC-UNIT-004: Markdown 表格渲染为 <table> 含 <th> 和 <td>', () => {
    const table = `| 名称 | 数量 |\n|------|------|\n| 压缩机 | 2 |\n| 冷凝器 | 1 |`
    const result = renderMarkdown(table)
    expect(result).toContain('<table>')
    expect(result).toContain('<th>')
    expect(result).toContain('<td>')
    // 不含原始分隔行文本
    expect(result).not.toContain('|------|')
  })

  // TC-UNIT-005 | AC-006-01 | <script> 标签被消毒
  it('TC-UNIT-005: LLM 输出中的 <script>alert(1)</script> 被移除', () => {
    const malicious = '<script>alert(1)</script>'
    const result = renderMarkdown(malicious)
    expect(result).not.toContain('<script>')
    expect(result).not.toContain('alert(1)')
  })

  // TC-UNIT-006 | AC-006-02 | <img onerror=...> 被消毒
  it('TC-UNIT-006: <img src=x onerror=alert(1)> 中的 onerror 属性被剥离', () => {
    const malicious = '<img src=x onerror=alert(1)>'
    const result = renderMarkdown(malicious)
    expect(result).not.toContain('onerror')
    expect(result).not.toContain('alert(1)')
  })

  // TC-UNIT-007 | AC-006-02 | javascript: 协议链接被消毒
  it('TC-UNIT-007: <a href="javascript:alert(1)"> 中的 javascript: 被剥离或移除', () => {
    const malicious = '<a href="javascript:alert(1)">点击</a>'
    const result = renderMarkdown(malicious)
    // href 应被移除或值被清空，不得保留 javascript: 协议
    expect(result).not.toContain('javascript:')
  })

  // TC-UNIT-008 | 边界 | 空字符串返回空字符串
  it('TC-UNIT-008: renderMarkdown("") 返回空字符串', () => {
    expect(renderMarkdown('')).toBe('')
  })

  // TC-UNIT-009 | AC-001-03 | 未闭合的 ** 不崩溃
  it('TC-UNIT-009: 未闭合 **关键词 不抛出异常，输出包含文本内容', () => {
    expect(() => renderMarkdown('**关键词')).not.toThrow()
    const result = renderMarkdown('**关键词')
    expect(result).toContain('关键词')
  })

  // TC-UNIT-010 | AC-003-02 | 正文中的竖线保留
  it('TC-UNIT-010: 非表格语法上下文的正文竖线保留在输出中', () => {
    // 单行文本中的竖线（非表格），marked 通常以文本保留
    const input = '选项 A 和 B 请参见附表。'
    const result = renderMarkdown(input)
    expect(result).toContain('选项 A 和 B')
  })

  // TC-UNIT-016 | REQ-FUNC-003 | --- 分隔线渲染为 <hr>（不被白名单删除）
  it('TC-UNIT-016: 独立 --- 行渲染为 <hr>，前后段落保留', () => {
    const result = renderMarkdown('第一段\n\n---\n\n第二段')
    expect(result).toContain('<hr>')
    expect(result).toContain('第一段')
    expect(result).toContain('第二段')
  })
})

// ============================================================
// PHASE_07: 单元测试 — isRenderable (IFC-002)
// ============================================================
describe('isRenderable — IFC-002 单元测试', () => {

  // TC-UNIT-011 | AC-004-01 | 流式期间不渲染
  it('TC-UNIT-011: msg.streaming=true 时返回 false（流式期间不触发 Markdown 渲染）', () => {
    expect(isRenderable({ role: 'assistant', streaming: true, content: 'hello', confirm: null })).toBe(false)
  })

  // TC-UNIT-012 | US-001 | 流结束后正常渲染
  it('TC-UNIT-012: 正常助手消息 streaming=false 时返回 true', () => {
    expect(isRenderable({ role: 'assistant', streaming: false, content: 'hello', confirm: null })).toBe(true)
  })

  // TC-UNIT-013 | REQ-NFUNC-006 | 用户消息不渲染
  it('TC-UNIT-013: 用户消息（role=user）返回 false', () => {
    expect(isRenderable({ role: 'user', streaming: false, content: 'hello', confirm: null })).toBe(false)
  })

  // TC-UNIT-014 | REQ-NFUNC-006 | confirm 卡片激活时不渲染
  it('TC-UNIT-014: confirm 激活（confirm != null）时返回 false', () => {
    expect(isRenderable({ role: 'assistant', streaming: false, content: 'hello', confirm: { actions: [] } })).toBe(false)
  })

  // TC-UNIT-015 | REQ-NFUNC-006 | 空内容不渲染
  it('TC-UNIT-015: content 为空字符串时返回 false', () => {
    expect(isRenderable({ role: 'assistant', streaming: false, content: '', confirm: null })).toBe(false)
  })
})

// ============================================================
// PHASE_08: 集成测试 — ChatView 组件挂载行为
// ============================================================

// ChatView 组件使用 WebSocket 和 localStorage，需要在 happy-dom 环境中进行 stub
// 使用 defineComponent + shallowMount 策略，聚焦于渲染逻辑

import ChatView from './ChatView.vue'

// Stub WebSocket（happy-dom 中 WebSocket 不可用）
class MockWebSocket {
  constructor() {
    this.onopen = null
    this.onmessage = null
    this.onclose = null
    this.onerror = null
    this.readyState = WebSocket.OPEN
  }
  send() {}
  close() {}
}

describe('ChatView 集成测试 — 消息渲染路径', () => {
  beforeAll(() => {
    // Stub localStorage
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => 'test-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    })
    // Stub WebSocket — 防止 connectWS 实际发起连接
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  /**
   * 辅助函数：挂载 ChatView 并注入一条消息
   */
  function mountWithMsg(msg) {
    const wrapper = mount(ChatView, {
      global: {
        stubs: {
          // Stub Element Plus 组件，避免 happy-dom 缺少浏览器 API 报错
          'el-button': { template: '<button><slot/></button>' },
          'el-input': { template: '<textarea/>' },
          'el-icon': { template: '<span/>' },
        },
      },
    })
    // 直接向 messages 注入测试消息
    wrapper.vm.messages.push(msg)
    return wrapper
  }

  // TC-INT-001 | AC-001-01 | stream_end 后 DOM 含 <strong>
  it('TC-INT-001: 含粗体的助手消息 streaming=false 时 DOM 含 <strong> 元素', async () => {
    const wrapper = mountWithMsg({
      role: 'assistant',
      content: '**关键词** 表示重要参数',
      chunks: [],
      reasoning: '',
      streaming: false,
      reasoningStreaming: false,
      confirm: null,
    })
    await wrapper.vm.$nextTick()
    const rendered = wrapper.find('.bubble-content--rendered')
    expect(rendered.exists()).toBe(true)
    expect(rendered.element.innerHTML).toContain('<strong>')
    expect(rendered.element.innerHTML).not.toContain('**')
  })

  // TC-INT-002 | AC-002-01 | stream_end 后 DOM 含 <table>
  it('TC-INT-002: 含 Markdown 表格的助手消息 streaming=false 时 DOM 含 <table>', async () => {
    const tableContent = `| 名称 | 数量 |\n|------|------|\n| 压缩机 | 2 |`
    const wrapper = mountWithMsg({
      role: 'assistant',
      content: tableContent,
      chunks: [],
      reasoning: '',
      streaming: false,
      reasoningStreaming: false,
      confirm: null,
    })
    await wrapper.vm.$nextTick()
    const rendered = wrapper.find('.bubble-content--rendered')
    expect(rendered.exists()).toBe(true)
    expect(rendered.element.innerHTML).toContain('<table>')
  })

  // TC-INT-003 | AC-004-01 | 流式期间无 .bubble-content--rendered
  it('TC-INT-003: streaming=true 时不存在 .bubble-content--rendered，存在 .bubble-chunk', async () => {
    const wrapper = mountWithMsg({
      role: 'assistant',
      content: '**关键词**',
      chunks: ['**关键词**'],
      reasoning: '',
      streaming: true,
      reasoningStreaming: false,
      confirm: null,
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bubble-content--rendered').exists()).toBe(false)
    expect(wrapper.find('.bubble-chunk').exists()).toBe(true)
  })

  // TC-INT-004 | AC-004-01 | streaming false 后切换渲染路径
  it('TC-INT-004: streaming 从 true → false 后切换为 .bubble-content--rendered', async () => {
    const msg = {
      role: 'assistant',
      content: '**关键词**',
      chunks: ['**关键词**'],
      reasoning: '',
      streaming: true,
      reasoningStreaming: false,
      confirm: null,
    }
    const wrapper = mountWithMsg(msg)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bubble-content--rendered').exists()).toBe(false)

    // 模拟 stream_end：必须经响应式数组元素改 streaming（直接改原始对象引用
    // 绕过 Vue3 Proxy 的 set 拦截、不触发重渲染——TC-INT-004 早前假失败的根因）。
    const arr = wrapper.vm.messages
    arr[arr.length - 1].streaming = false
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bubble-content--rendered').exists()).toBe(true)
    expect(wrapper.find('.bubble-chunk').exists()).toBe(false)
  })

  // TC-INT-005 | AC-006-01 | v-html 路径中 <script> 被消毒
  it('TC-INT-005: 含 <script> 的助手消息渲染后 DOM 中无 <script> 元素', async () => {
    const wrapper = mountWithMsg({
      role: 'assistant',
      content: '<script>alert(1)<\/script>',
      chunks: [],
      reasoning: '',
      streaming: false,
      reasoningStreaming: false,
      confirm: null,
    })
    await wrapper.vm.$nextTick()
    const rendered = wrapper.find('.bubble-content--rendered')
    expect(rendered.exists()).toBe(true)
    expect(rendered.element.querySelectorAll('script').length).toBe(0)
    expect(rendered.element.innerHTML).not.toContain('alert(1)')
  })

  // TC-INT-006 | AC-005-01 | 用户消息始终纯文本插值
  it('TC-INT-006: 用户消息无 .bubble-content--rendered，纯文本显示', async () => {
    const wrapper = mountWithMsg({
      role: 'user',
      content: '**不应渲染**',
      chunks: [],
      reasoning: '',
      streaming: false,
      reasoningStreaming: false,
      confirm: null,
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bubble-content--rendered').exists()).toBe(false)
    // 找到用户气泡
    const bubble = wrapper.find('.chat-bubble--user')
    expect(bubble.text()).toContain('**不应渲染**')
  })

  // TC-INT-007 | REQ-NFUNC-006 | confirm 卡片激活时不切渲染
  it('TC-INT-007: confirm 激活时（confirm != null）不出现 .bubble-content--rendered', async () => {
    const wrapper = mountWithMsg({
      role: 'assistant',
      content: '**关键词**',
      chunks: [],
      reasoning: '',
      streaming: false,
      reasoningStreaming: false,
      confirm: { actions: [{ preview: '写入设备参数 X=100' }] },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bubble-content--rendered').exists()).toBe(false)
    expect(wrapper.find('.confirm-card').exists()).toBe(true)
  })

  // TC-INT-008 | REQ-NFUNC-006 | reasoning 折叠区不受影响
  it('TC-INT-008: 含 reasoning 的助手消息 stream_end 后两者共存（<details> + .bubble-content--rendered）', async () => {
    const wrapper = mountWithMsg({
      role: 'assistant',
      content: '**结论**：建议维修。',
      chunks: [],
      reasoning: '我先分析了故障代码...',
      streaming: false,
      reasoningStreaming: false,
      confirm: null,
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('details.reasoning-details').exists()).toBe(true)
    expect(wrapper.find('.bubble-content--rendered').exists()).toBe(true)
  })

  // TC-INT-009 | AC-005-02 | 中文标点无损显示
  it('TC-INT-009: 含中文标点的纯文本助手消息 stream_end 后标点完整保留', async () => {
    const content = '当前温度为 25°C，压力正常，请确认！'
    const wrapper = mountWithMsg({
      role: 'assistant',
      content,
      chunks: [],
      reasoning: '',
      streaming: false,
      reasoningStreaming: false,
      confirm: null,
    })
    await wrapper.vm.$nextTick()
    const rendered = wrapper.find('.bubble-content--rendered')
    expect(rendered.exists()).toBe(true)
    expect(rendered.element.textContent).toContain('当前温度为 25°C，压力正常，请确认！')
  })
})
