/**
 * @module MOD-MINI-MARKDOWN
 * @description 轻量 Markdown → HTML 渲染器（零依赖），用于 <rich-text> 展示 AI 回复 / 工单说明。
 *
 * 为何自造而非用 marked：
 *   marked v13 在模块加载时 eager 构造正则 /^((?![*_])[\s\p{P}\p{S}])/u，
 *   使用 Unicode 属性转义 \p{P}\p{S}。部分安卓设备（如华为 NOH-AN00）的小程序 JS 引擎
 *   不支持字符类里的 \p{...}，new RegExp 直接抛错 → common/vendor.js 加载失败 → 全小程序白屏。
 *   本渲染器只用基础正则（无 \p{}），规避该设备兼容性坑。
 *
 * 覆盖：标题、加粗(**)、斜体(*)、行内代码(`)、围栏代码(```)、链接、有序/无序列表、引用(>)、
 *   分割线(---)、GFM 表格(|...|)、段落与换行(breaks)。刻意不支持 _ / __ 强调，避免技术文本里的下划线被误判为斜体/加粗。
 *   输出交给 <rich-text>，其标签白名单天然防 XSS；本模块仍先做 HTML 转义。
 */

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// 行内元素（入参为原始文本，先转义再套标签）。顺序：转义 → 行内代码 → 链接 → 加粗 → 斜体。
// 注意：不能对整篇预转义，否则 '>' 会变 '&gt;' 导致引用块无法识别。
function inline(text) {
  let t = escapeHtml(text)
  // 行内代码 `code`
  t = t.replace(/`([^`]+)`/g, (m, c) => `<code>${c}</code>`)
  // 链接 [text](url)
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => `<a href="${url}">${txt}</a>`)
  // 加粗 **text**
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  // 斜体 *text*（此时 ** 已被消费，剩余单 * 视作斜体）
  t = t.replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
  return t
}

const RE_HEADING = /^\s*(#{1,6})\s+(.*)$/
const RE_HR = /^\s*([-*_])\1\1+\s*$/
const RE_QUOTE = /^\s*>\s?(.*)$/
const RE_UL = /^\s*[-*+]\s+(.*)$/
const RE_OL = /^\s*\d+\.\s+(.*)$/

// GFM 表格：行以 | 开头结尾，分隔行仅含 | - : 空格且至少一个 -
const RE_TABLE_ROW = /^\|(.+)\|\s*$/
const RE_TABLE_SEP = /^\|[\s\-:|]+\|\s*$/

function isBlockStart(line) {
  return RE_HEADING.test(line) || RE_HR.test(line) || RE_QUOTE.test(line) ||
    RE_UL.test(line) || RE_OL.test(line) || /^```/.test(line.trim()) ||
    RE_TABLE_ROW.test(line)
}

/**
 * 从分隔行解析每列对齐方式：:--- → 左，:---: → 居中，---: → 右
 */
function parseAligns(sepLine) {
  const inner = sepLine.replace(/^\||\|\s*$/g, '')
  return inner.split('|').map(s => {
    s = s.trim()
    if (s.startsWith(':') && s.endsWith(':')) return 'center'
    if (s.endsWith(':')) return 'right'
    return 'left'
  })
}

export function renderMarkdown(src) {
  if (!src) return ''
  // 用原始文本做块级判定（'>' '#' 等未转义），转义延后到 inline()/代码块内进行。
  const lines = String(src).replace(/\r\n/g, '\n').split('\n')
  let html = ''
  let i = 0
  let list = null // 'ul' | 'ol'
  const closeList = () => { if (list) { html += `</${list}>`; list = null } }

  while (i < lines.length) {
    const line = lines[i]

    // 围栏代码块 ```
    if (/^```/.test(line.trim())) {
      closeList()
      i++
      let code = ''
      while (i < lines.length && !/^```/.test(lines[i].trim())) { code += escapeHtml(lines[i]) + '\n'; i++ }
      i++ // 跳过闭合 ```
      html += `<pre><code>${code}</code></pre>`
      continue
    }
    // 分割线
    if (RE_HR.test(line)) { closeList(); html += '<hr>'; i++; continue }
    // 标题
    const h = line.match(RE_HEADING)
    if (h) { closeList(); const lv = h[1].length; html += `<h${lv}>${inline(h[2])}</h${lv}>`; i++; continue }
    // 引用
    const q = line.match(RE_QUOTE)
    if (q) { closeList(); html += `<blockquote>${inline(q[1])}</blockquote>`; i++; continue }
    // 无序列表
    const ul = line.match(RE_UL)
    if (ul) { if (list !== 'ul') { closeList(); html += '<ul>'; list = 'ul' } html += `<li>${inline(ul[1])}</li>`; i++; continue }
    // 有序列表
    const ol = line.match(RE_OL)
    if (ol) { if (list !== 'ol') { closeList(); html += '<ol>'; list = 'ol' } html += `<li>${inline(ol[1])}</li>`; i++; continue }
    // GFM 表格：检测「表头行 + 分隔行」配对，然后贪婪消费后续数据行
    const tr = line.match(RE_TABLE_ROW)
    if (tr && i + 1 < lines.length && RE_TABLE_SEP.test(lines[i + 1].trim()) && /-/.test(lines[i + 1])) {
      closeList()
      const headers = tr[1].split('|').map(c => c.trim())
      const aligns = parseAligns(lines[i + 1])
      i += 2 // 跳过表头和分隔行
      html += '<table><thead><tr>'
      headers.forEach((h, idx) => {
        html += `<th style="text-align:${aligns[idx] || 'left'}">${inline(h)}</th>`
      })
      html += '</tr></thead><tbody>'
      while (i < lines.length && RE_TABLE_ROW.test(lines[i])) {
        const cells = lines[i].replace(/^\||\|\s*$/g, '').split('|').map(c => inline(c.trim()))
        html += '<tr>'
        cells.forEach((c, idx) => {
          html += `<td style="text-align:${aligns[idx] || 'left'}">${c}</td>`
        })
        html += '</tr>'
        i++
      }
      html += '</tbody></table>'
      continue
    }
    // 空行
    if (line.trim() === '') { closeList(); i++; continue }
    // 段落：聚合相邻非块级行，行内以 <br> 连接（breaks 语义）
    closeList()
    const para = [line]
    i++
    while (i < lines.length && lines[i].trim() !== '' && !isBlockStart(lines[i])) { para.push(lines[i]); i++ }
    html += `<p>${para.map(inline).join('<br>')}</p>`
  }
  closeList()
  return html
}

export default { renderMarkdown }
