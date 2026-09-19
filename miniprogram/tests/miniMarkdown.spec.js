import { describe, it, expect } from 'vitest'
import { renderMarkdown } from '@/utils/miniMarkdown'

// 回归点：OpenClaw→LangGraph 重构后，结构化数据由 JSON 变成自由 markdown，
// 小程序 <rich-text> 不继承 CSS，表格需内联边框，否则无边框、裸 ** 符号。
describe('utils/miniMarkdown 表格与加粗渲染', () => {
  const table = [
    '| 设备 | 温度 | 状态 |',
    '|------|------|------|',
    '| 书房 | 24℃ | 正常 |',
  ].join('\n')

  it('GFM 表格：输出 <table> 并内联边框 + 表头加粗', () => {
    const html = renderMarkdown(table)
    expect(html).toContain('<table style="border-collapse:collapse')
    // 表头：有边框、表头底色、加粗
    expect(html).toContain('font-weight:bold')
    expect(html).toContain('border:1px solid #d0d7de')
    expect(html).toContain('background:#f6f8fa')
    expect(html).toContain('<th')
    expect(html).toContain('<td')
  })

  it('主题配色透传：赛博朋克色覆盖默认浅色边框', () => {
    const html = renderMarkdown(table, {
      tableBorderColor: 'rgba(56,230,224,0.3)',
      tableHeaderBg: 'rgba(47,244,224,0.08)',
    })
    expect(html).toContain('border:1px solid rgba(56,230,224,0.3)')
    expect(html).toContain('background:rgba(47,244,224,0.08)')
    expect(html).not.toContain('#d0d7de')
  })

  it('加粗：**text** → <strong>，不残留裸 **', () => {
    const html = renderMarkdown('**温度**：24℃，**湿度**：50%')
    expect(html).toContain('<strong>温度</strong>')
    expect(html).toContain('<strong>湿度</strong>')
    expect(html).not.toContain('**')
  })

  it('对齐列：:---: → 居中', () => {
    const html = renderMarkdown('| 名称 | 值 |\n|:----:|----:|\n| a | 1 |')
    expect(html).toContain('text-align:center')
    expect(html).toContain('text-align:right')
  })

  it('结论 + 表格混排：段落与表格都能识别', () => {
    const html = renderMarkdown('结论如下：\n\n' + table)
    expect(html).toContain('<p>结论如下：</p>')
    expect(html).toContain('<table')
    expect(html).toContain('书房')
  })
})
