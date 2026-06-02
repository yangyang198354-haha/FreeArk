# FreeArk 前端全站 UI 统一改版 — 设计规范

**版本**: 1.0.0  
**日期**: 2026-06-02  
**来源**: `reference/Console-standalone.html` 深色科技风设计稿（只读基准）  
**状态**: APPROVED（已由 PM/用户批准，本文为后续批次开发的唯一设计依据）  
**维护人**: sub_agent_software_developer  

---

## 1. 范围与约束

| 项 | 说明 |
|---|---|
| 改版目标 | 27 个 .vue 视图 + Layout.vue，与 commit `37d5a8a` 登录页保持一致 |
| 排除页面 | `LoginView.vue`（已完成，勿改） |
| 设计稿（只读） | `reference/Console-standalone.html`、`reference/Login-standalone.html` |
| 代码根目录 | `FreeArkWeb/frontend/` (Vue 3 + Vite + Element Plus) |
| 字体限制 | **禁止**运行时外网字体（fonts.googleapis.com 等）；仅可用系统回退栈或本地打包 webfont |
| 生产约束 | Sidebar 保留 el-menu，做深色主题覆盖 |
| 部署约束 | 纯前端样式改版；生产部署需用户明确 CONFIRM 后方可执行 |

---

## 2. 颜色 Token 完整映射表

### 2.1 核心背景层级

| Token 名称 | 值 | 用途 |
|---|---|---|
| `--bg-0` | `#050a14` | 全局最底层背景（html/body） |
| `--bg-1` | `#0a1424` | 次层背景（sidebar 底色、弹窗遮罩底） |
| `--bg-2` | `#0f1d35` | 三层背景（卡片/panel 底色参考） |
| `--panel` | `rgba(15,29,53,0.55)` | 半透明卡片（.panel 标准背景） |
| `--panel-2` | `rgba(20,34,58,0.7)` | 较深半透明（hover 态 panel、dropdown） |

### 2.2 文字层级

| Token 名称 | 值 | 用途 |
|---|---|---|
| `--ink-0` | `#f0f6ff` | 主要文字（标题、重要数值） |
| `--ink-1` | `#c7d4ea` | 次要文字（正文、表格 td） |
| `--ink-2` | `#7a8bab` | 辅助文字（label、placeholder、icon） |
| `--ink-3` | `#4a5a78` | 最弱文字（disabled、分隔符、mono 标注） |

### 2.3 边框 / 分割线

| Token 名称 | 值 | 用途 |
|---|---|---|
| `--line` | `rgba(120,160,220,0.12)` | 标准边框（panel border、表格行分割） |
| `--line-2` | `rgba(120,160,220,0.22)` | 较重边框（hover 态边框、topbar/sidebar 分割） |

### 2.4 强调色 / 功能色

| Token 名称 | 值 | 用途 |
|---|---|---|
| `--acc` | `#3b82f6` | 主强调（按钮 primary、active 竖条、链接） |
| `--acc-2` | `#22d3ee` | 次强调（gradient 终点、active icon、subitem active） |
| `--acc-3` | `#60a5fa` | 三强调（hover 辅助、轻量高亮） |
| `--ok` | `#34d399` | 成功 / 在线绿 |
| `--warn` | `#fbbf24` | 警告黄 |
| `--danger` | `#f87171` | 危险红（故障、错误） |
| `--heat` | `#f0506e` | 制热红（温控） |
| `--cool` | `#3b82f6` | 制冷蓝（与 --acc 同值，语义区分） |
| `--violet` | `#a78bfa` | 紫色（特殊标注、AI 功能） |

### 2.5 Element Plus 主题变量覆盖（深色映射）

| EP 变量 | 映射值 | 备注 |
|---|---|---|
| `--el-color-primary` | `#3b82f6` (--acc) | 主色 |
| `--el-bg-color` | `#0a1424` (--bg-1) | 替换白底 |
| `--el-bg-color-page` | `#050a14` (--bg-0) | 页面底色 |
| `--el-bg-color-overlay` | `rgba(10,20,36,0.95)` | 弹窗/dropdown 底色 |
| `--el-fill-color-blank` | `rgba(5,10,20,0.5)` | input/select 输入框底色 |
| `--el-fill-color` | `rgba(15,29,53,0.55)` | 表格偶数行、卡片填充 |
| `--el-fill-color-light` | `rgba(15,29,53,0.3)` | 轻量填充 |
| `--el-border-color` | `rgba(120,160,220,0.22)` (--line-2) | 标准边框 |
| `--el-border-color-light` | `rgba(120,160,220,0.12)` (--line) | 轻量边框 |
| `--el-text-color-primary` | `#f0f6ff` (--ink-0) | 主文字 |
| `--el-text-color-regular` | `#c7d4ea` (--ink-1) | 次文字 |
| `--el-text-color-secondary` | `#7a8bab` (--ink-2) | 辅助文字 |
| `--el-text-color-placeholder` | `#4a5a78` (--ink-3) | placeholder |
| `--el-text-color-disabled` | `#4a5a78` (--ink-3) | disabled |
| `--el-border-radius-base` | `9px` | 统一圆角 |
| `--el-border-radius-small` | `6px` | 小圆角 |
| `--el-mask-color` | `rgba(3,7,15,0.75)` | dialog 遮罩 |
| `--el-box-shadow` | `0 8px 32px rgba(0,0,0,0.45)` | 弹窗阴影 |
| `--el-menu-bg-color` | `transparent` | menu 背景（由外层控制） |
| `--el-menu-text-color` | `#7a8bab` | menu 项文字 |
| `--el-menu-active-color` | `#f0f6ff` | menu active 文字 |
| `--el-menu-hover-bg-color` | `rgba(120,160,220,0.06)` | menu hover 背景 |
| `--el-table-header-bg-color` | `rgba(7,14,28,0.5)` | 表头背景 |
| `--el-table-tr-bg-color` | `transparent` | 表格行背景 |
| `--el-table-row-hover-bg-color` | `rgba(59,130,246,0.06)` | 表格行 hover |
| `--el-table-border-color` | `rgba(120,160,220,0.12)` | 表格边框 |
| `--el-card-bg-color` | `rgba(15,29,53,0.55)` | 卡片背景 |
| `--el-dialog-bg-color` | `#0a1424` | 对话框背景 |
| `--el-input-bg-color` | `rgba(5,10,20,0.5)` | 输入框背景 |
| `--el-select-option-hover-background` | `rgba(59,130,246,0.12)` | select option hover |
| `--el-tag-primary-color` | `rgba(59,130,246,0.15)` | primary tag 背景 |
| `--el-tag-success-color` | `rgba(52,211,153,0.15)` | success tag 背景 |
| `--el-tag-danger-color` | `rgba(248,113,113,0.15)` | danger tag 背景 |
| `--el-tag-warning-color` | `rgba(251,191,36,0.15)` | warning tag 背景 |

---

## 3. 字体规范

### 3.1 字体回退栈（系统字体，无外网依赖）

```css
/* 正文/UI */
font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;

/* 等宽/数值 */
font-family: "JetBrains Mono", ui-monospace, "Cascadia Code", Consolas, monospace;
```

**约束**：绝对禁止在 `index.html` 或 CSS 中使用 `@import url(https://fonts.googleapis.com/...)` 或任何外网字体 CDN。如需 webfont，必须通过 `@fontsource` 本地打包。

### 3.2 字号体系

| Token | 值 | 用途 |
|---|---|---|
| `--font-size-xs` | `11px` | 辅助标注、徽标 |
| `--font-size-sm` | `12px` | section-label、表头、badge |
| `--font-size-base` | `15px` | 基准正文（相比原 14px 上调） |
| `--font-size-md` | `13.5px` | nav-item、表格 td |
| `--font-size-lg` | `22px` | 页面标题 |
| `--font-size-xl` | `28px` | 大数值（stat card） |
| `--font-size-2xl` | `clamp(28px, 2.8vw, 40px)` | 超大数值（4K 自适应） |
| `--font-size-3xl` | `clamp(36px, 3.5vw, 52px)` | 看板核心指标 |

### 3.3 字重

| Token | 值 |
|---|---|
| `--font-weight-regular` | `400` |
| `--font-weight-medium` | `500` |
| `--font-weight-semibold` | `600` |
| `--font-weight-bold` | `700` |

---

## 4. 响应式断点规范

| 断点 | 条件 | `html font-size` | Sidebar 宽度 | 内容区 max-width |
|---|---|---|---|---|
| 4K | `min-width: 3840px` | `18px` | `260px` | `2200px` |
| 2.5K | `2560px – 3839px` | `16px` | `252px` | `1920px` |
| 基准 | `1920px – 2559px` | `15px` | `244px` | `1680px` |
| 收缩 | `< 1340px` | `14px` | `64px`（可折叠至） | `100%` |
| 移动 | `< 720px` | `14px` | `0`（隐藏） | `100%` |

**实现方式**：通过 `@media` 设置 `html { font-size: Npx; }`，其余尺寸均用 `rem` 或 `em`，大数值用 `clamp(minpx, Xvw, maxpx)`。

---

## 5. 布局结构规范

### 5.1 App Shell — CSS Grid

```
┌──────────────┬──────────────────────────────────┐
│  brand-box   │  topbar                          │  高度: 60px
│  (244px)     │  (flex: 1)                       │
├──────────────┼──────────────────────────────────┤
│              │                                  │
│  sidebar     │  main content                    │
│  (244px)     │  (flex: 1, overflow-y: auto)     │
│              │                                  │
└──────────────┴──────────────────────────────────┘
```

Grid 定义：
```css
display: grid;
grid-template-columns: var(--sidebar-w) 1fr;
grid-template-rows: var(--topbar-h) 1fr;
grid-template-areas: "brand top" "side main";
```

全局背景（app-level）：
```css
background:
  radial-gradient(1100px 700px at 80% -5%, rgba(56,189,248,0.07), transparent 60%),
  radial-gradient(900px 600px at 0% 100%, rgba(59,130,246,0.06), transparent 60%),
  linear-gradient(180deg, #050a14 0%, #060d1c 100%);
```

网格纹理（伪元素 `::before` fixed overlay）：
```css
background-image:
  linear-gradient(rgba(120,160,220,0.035) 1px, transparent 1px),
  linear-gradient(90deg, rgba(120,160,220,0.035) 1px, transparent 1px);
background-size: 54px 54px;
mask-image: radial-gradient(1200px 800px at 70% 30%, #000 0%, transparent 80%);
```

### 5.2 Topbar

- 高度: `60px`
- 背景: `rgba(7,14,28,0.45)`，`backdrop-filter: blur(10px)`
- 底部边框: `1px solid var(--line)`
- 右侧 user-pill: `border: 1px solid var(--line)`，hover `var(--panel-2)`
- avatar: `linear-gradient(135deg, var(--acc), var(--acc-2))`，字色 `#06182a`

### 5.3 Sidebar（保留 el-menu，深色覆盖）

- 背景: `rgba(7,14,28,0.55)`，`backdrop-filter: blur(10px)`
- 右侧边框: `1px solid var(--line)`
- nav-item 高度: `~44px`，`border-radius: 10px`
- Active 态: `background: linear-gradient(90deg, rgba(59,130,246,0.22), rgba(59,130,246,0.05))`
- Active 左竖条: `position: absolute; left: 0; width: 3px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); box-shadow: 0 0 12px var(--acc)`
- Sub-menu item: `padding-left: 44px`，active 时 `color: var(--acc-2)`，有小圆点 indicator

### 5.4 内容区 (main)

- 无白色卡片包裹，直接 `padding: 28px 32px 48px`
- 背景透明（继承 app shell 背景）
- `max-width: 1680px; margin: 0 auto`
- 内容区不设独立背景色，页面级卡片用 `.panel` 类

---

## 6. 组件规格

### 6.1 .panel（卡片/容器）

```css
background: linear-gradient(180deg, rgba(15,29,53,0.55), rgba(10,20,36,0.4));
border: 1px solid var(--line);
border-radius: 14px;
position: relative;
overflow: hidden;
```

`.panel.glow::after`（可选发光边框内嵌）:
```css
box-shadow: 0 0 0 1px rgba(120,160,220,0.04) inset;
```

**el-card 覆盖**：将 el-card 的背景/边框/阴影映射到 .panel 规格。

### 6.2 .section-label（分组标签）

```css
display: flex;
align-items: center;
gap: 10px;
font-size: 12px;
letter-spacing: 0.16em;
color: var(--ink-2);
text-transform: uppercase;
/* ::after 延伸线 */
&::after { content:""; flex:1; height:1px; background: var(--line); }
```

### 6.3 .stat-card（统计数值卡）

```css
padding: 18px;
position: relative;
/* 左竖色条 */
.stat-accent {
  position: absolute;
  left: 0; top: 14px; bottom: 14px;
  width: 2px;
  border-radius: 2px;
  /* 颜色按语义：--acc / --ok / --warn / --heat / --cool */
}
/* 数值发光 */
.stat-value {
  font-size: clamp(28px, 2.8vw, 40px);
  font-family: var(--font-mono);
  text-shadow: 0 0 24px currentColor;
}
```

### 6.4 .badge（状态徽标）

| 类名 | 文字色 | 背景 | 边框 |
|---|---|---|---|
| `.badge.on` | `#5ee7a8` | `rgba(52,211,153,0.12)` | `rgba(52,211,153,0.28)` |
| `.badge.off` | `#ff9aa8` | `rgba(248,80,110,0.12)` | `rgba(248,80,110,0.3)` |
| `.badge.unknown` | `var(--ink-2)` | `rgba(120,160,220,0.08)` | `var(--line-2)` |
| `.badge.cool` | `#7db8ff` | `rgba(59,130,246,0.14)` | `rgba(59,130,246,0.3)` |
| `.badge.heat` | `#ff9aa8` | `rgba(240,80,110,0.12)` | `rgba(240,80,110,0.28)` |
| `.badge.warn` | `#fbbf24` | `rgba(251,191,36,0.12)` | `rgba(251,191,36,0.28)` |

每个 badge 含 5px 圆点 `.bd`，active 态有 `box-shadow: 0 0 6px {color}`。

### 6.5 .btn（按钮）

```css
/* 默认 */
height: 38px; padding: 0 18px; border-radius: 9px;
border: 1px solid var(--line-2); background: var(--panel); color: var(--ink-1);

/* hover */
border-color: rgba(120,160,220,0.4); background: var(--panel-2); color: var(--ink-0);

/* primary */
border: 0;
background: linear-gradient(90deg, var(--acc), var(--acc-2));
color: #06182a; font-weight: 600;
box-shadow: 0 8px 22px -10px rgba(59,130,246,0.6);
```

**el-button 覆盖方向**：将 EP 的 primary 按钮映射至上述 gradient 风格。

### 6.6 el-table 深色覆盖

```css
表头: background rgba(7,14,28,0.5); color var(--ink-2); font-size 12px; letter-spacing 0.08em
单元格: color var(--ink-1); font-size 13px
行边框: 1px solid var(--line)
行hover: rgba(59,130,246,0.06)
奇偶行交替: 不使用斑马纹（统一透明底）
```

### 6.7 el-input / el-select 深色覆盖

```css
背景: rgba(5,10,20,0.5)
边框: 1px solid var(--line)
focus边框: rgba(59,130,246,0.6)
focus glow: box-shadow 0 0 0 3px rgba(59,130,246,0.12)
文字: var(--ink-0)
placeholder: var(--ink-3)
```

### 6.8 el-dialog 深色覆盖

```css
背景: #0a1424
边框: 1px solid var(--line-2)
遮罩: rgba(3,7,15,0.75)
标题: var(--ink-0); font-weight 600
内容: var(--ink-1)
```

### 6.9 el-pagination 深色覆盖

```css
按钮背景: rgba(5,10,20,0.5); 边框: var(--line)
active: linear-gradient(90deg, var(--acc), var(--acc-2)); color #06182a
字体: "JetBrains Mono" monospace
```

### 6.10 滚动条

```css
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(120,160,220,0.22);
  border-radius: 99px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background: rgba(120,160,220,0.4); }
```

---

## 7. 动效规范

| 场景 | 属性 | 时长 | 缓动 |
|---|---|---|---|
| micro（颜色/透明度） | color, background, border, opacity | `150ms` | `ease-in-out` |
| 组件出现 | opacity, transform | `250ms` | `ease-out` |
| sidebar 折叠 | width | `300ms` | `cubic-bezier(0.4, 0, 0.2, 1)` |
| 页面路由切换 | opacity + translateY(10px) | `400ms in / 200ms out` | `ease-out` |
| panel hover | box-shadow | `200ms` | `ease-out` |

---

## 8. 页面改版批次计划

| 批次 | 内容 | 文件 | 状态 |
|---|---|---|---|
| 批次 1 | 基础设施基线 | `global.css`, `index.html`, `Layout.vue` | **本轮执行** |
| 批次 2 | 核心数据页面 | Dashboard/HomeView, DeviceList, FaultManagement | 待批次 1 通过后执行 |
| 批次 3 | 报表类页面 | MonthlyReport, DailyReport, UsageQuery | 待批次 2 通过后执行 |
| 批次 4 | 管理类页面 | OwnerManagement, UserList, CreateUser 等 | 待批次 3 通过后执行 |
| 批次 5 | 特殊页面 | Chat, CondesationWarnings, Services 等剩余 | 待批次 4 通过后执行 |

---

## 9. 质量门控要求

- 每批次开发完成后必须运行 `cd FreeArkWeb/frontend && npm run build`，提供真实 stdout/stderr 和 exit code。
- 不接受口头声称"构建通过"，必须有命令实际输出作为证据。
- 深色覆盖必须消除所有白底漏光（el-card、el-table、el-input、el-select、el-dialog、el-menu）。
- 不得向 `index.html` 添加任何外网字体 CDN 链接。
