# Handoff: 方舟座舱 (ARK Cockpit) — AI 问答 & 个人中心（方案1）

## Overview
This package covers **two screens** of the *方舟座舱 / ARK Cockpit* WeChat Mini-Program (胖子熊·智能 / FreeArk 业主端), both in the established cyberpunk / sci-fi HUD style shared with the login screen:

1. **AI 问答（方案1 · 对话气泡）** — a conversational AI assistant ("方舟助手 / ARK") for device control, fault diagnosis, and HVAC/fresh-air knowledge.
2. **个人中心（方案1 · 卡片流）** — owner profile with **房号（专有部分）绑定** (property/room binding — NOT device binding), 参数设置 entry, and logout.

> Only **方案1 (option 1)** of each page is in scope for this handoff. The source design files also contain a 方案2 alternative (ai2 终端HUD / me2 凭证仪表盘) — ignore those unless asked.

## About the Design Files
The reference screens in `screens/` are **design references created in HTML** — live, static mockups showing the intended look. **They are not production code to copy directly.**

Recreate these in the target environment. For a WeChat Mini-Program that means **WXML + WXSS + JS** (or Taro / uni-app). Reproduce the visual spec faithfully; where an animation is impractical on-platform, ship the static state first and add motion as the platform allows.

> **Platform chrome is mocked, do not build it:** the iPhone bezel/notch/home-indicator, the top status bar (14:04 / signal / battery), and the WeChat `···`/`◉` capsule are drawn by the device / WeChat itself. They appear in the mockups only to frame the screen. Build everything *inside* the page.

## Fidelity
**High-fidelity.** Colors, type, spacing, radii, shadows and interactions are final. The mocked device/WeChat chrome above is the only out-of-scope part.

---

## Shared System (both screens)

### Screen frame
- Content area ≈ **366×786px** portrait (inside a 392×812 bezel). Build responsive to safe-area height.
- Vertical layout: **status bar → header → (sub-bar) → scrollable body (flex:1) → [input bar, AI only] → bottom tab bar**. The body is the only scrolling region; header, input bar and tab bar are pinned.
- Screen background: `radial-gradient(90% 50% at 15% 0%, rgba(101,55,180,.30), transparent 55%)`, `radial-gradient(80% 45% at 100% 5%, rgba(20,180,170,.22), transparent 55%)`, over `linear-gradient(180deg,#0b0a1a,#07101c 60%,#050811)`.
- Decorative (both `pointer-events:none`): a faint 40px cyan **grid** `rgba(56,230,224,.06)` masked to fade out toward the bottom, and one blurred **glow blob** that slowly floats (`ark-float` 16s). Both are always-on ambient decoration.

### Bottom tab bar (shared, 4 tabs)
- Height 64px + 16px bottom safe-area pad; background `rgba(6,10,20,.9)`; top border `1px solid rgba(56,230,224,.14)`.
- Tabs, left→right: **首页** (home) · **设备** (device / grid icon) · **AI问答** (chat icon) · **我的** (person icon). Each = 22px stroke icon + 10px label, stacked, centered.
- **Inactive**: `rgba(170,195,230,.5)`. **Active**: cyan `#2ff4e0`, icon gets `drop-shadow(0 0 6px rgba(47,244,224,.7))`, label gets text-shadow, plus a 26×2px cyan glow pill at the top edge of the cell.
- On the AI page the active tab is **AI问答**; on the profile page it's **我的**.

### Header
- 46px tall, title centered. AI page: back chevron on the left, title 方舟助手 (17px/700, letter-spacing 2px), WeChat capsule mock on the right. Profile page: title 个人中心 (17px/700, letter-spacing 4px), no back button.

---

## Screen 1 — AI 问答（方案1 对话气泡）
File: `screens/AI-QA-option1.html`

### Sub-bar (below header)
- Left: pill **＋ 新建会话** (new session) — cyan text, `1px solid rgba(56,230,224,.4)`, `rgba(47,244,224,.06)` fill, radius 14px.
- Right: **历史会话 ▾** (history sessions dropdown) — muted `rgba(143,217,255,.7)`.

### Chat feed (scrollable, gap 13px)
Message types:
- **AI bubble**: left-aligned. 34×34px **ARK avatar** (Orbitron 900, cyan-purple gradient fill, cyan border, `ARK` glyph) + bubble: `rgba(14,22,42,.85)` fill, `1px solid rgba(56,230,224,.2)`, radius `5px 14px 14px 14px` (notched top-left toward avatar), 13.5px/1.65 text `#dbeeff`, max-width ~78%. Key values inside answers are highlighted cyan `#2ff4e0` (e.g. 制冷 / 15.8°C / 23.3°C); purple `#c4a6ff` used for secondary metrics (e.g. 668h).
- **Streaming cursor**: at the end of an in-progress AI answer, a 7×15px cyan block with `ark-blink` (1s steps) + cyan glow — the "AI is typing / streaming output" indicator.
- **Quick-ask chips** (under the greeting): wrapping row of pill chips, 12px `#9fe9e0`, `1px solid rgba(56,230,224,.35)`, radius 14px. Sample: 客厅主机不制冷？ / 如何开启离家节能 / 新风滤网多久换. Tapping a chip submits it as a question.
- **User bubble**: right-aligned. Gradient fill `linear-gradient(95deg,#22e6da,#3a8bff)`, text `#04121f`/600, radius `14px 5px 14px 14px` (notched top-right), glow `0 0 18px rgba(47,244,224,.3)`, max-width ~78%. No avatar.
- **Thinking indicator**: AI avatar + a small bubble containing **three 7px cyan dots** bouncing in sequence (`ark-dot` 1.2s, staggered .15s/.3s) — shown while awaiting the response.

Sample conversation content (domain = the three scenarios the product covers): 设备控制 (device control), 故障原因查询 (fault diagnosis, e.g. "客厅主机不制冷是什么原因？" → checks host mode / water temps / suggests filter), 空调知识科普 (HVAC knowledge, e.g. filter replacement).

### Input bar (pinned above tab bar)
- Row: input field (flex, 42px, radius 21px, `rgba(4,10,22,.7)`, cyan-tinted border, placeholder 向方舟助手提问…) + **voice button** (42px circle, mic icon, cyan outline) + **send button** (42px circle, gradient fill `#22e6da→#3a8bff`, paper-plane icon, cyan glow).
- Voice button opens speech input; send submits the message.

### AI-page interactions
- Tap **＋ 新建会话** → start a fresh conversation (clear feed).
- Tap **历史会话** → open session history list.
- Tap a **quick-ask chip** → send it as the user message.
- Type + **send** (or press enter) → append user bubble, show **thinking indicator**, then stream the AI answer with the blinking cursor until complete.
- Tap **voice button** → begin speech-to-text capture.
- The AI/thinking/streaming states shown are static mockups — wire them to the real assistant streaming API.

---

## Screen 2 — 个人中心（方案1 卡片流）
File: `screens/Profile-option1.html`

### Profile card (corner-bracketed)
- Rounded 16px card, `linear-gradient(180deg, rgba(14,22,42,.75), rgba(8,14,28,.8))`, `1px solid rgba(56,230,224,.18)`, four 22px cyan **corner brackets**.
- Left: 64px **avatar** — dashed cyan ring around a 54px circle (cyan-purple gradient, cyan border) showing the surname glyph 胖 (Noto Sans SC 900, 24px, cyan text + glow). Replace with the user's real avatar image when available.
- Middle: **昵称** 胖子熊 (19px/700 `#f4fbff`) + a mono **已认证** badge (9px cyan-green `#5ff0b6`, bordered, `white-space:nowrap`); **ID · ARK-2049** (mono, 11px); **138****1234** (masked phone, 12px muted).
- Right: 34px square **edit** button (pencil icon, cyan, bordered) → edit profile.

### Property section — 房号（专有部分）绑定
> This is the core of this screen: owners bind **房号 / 专有部分 (properties/rooms)**, NOT devices.
- Section label: mono `PROPERTY · 我的房号` (cyan .7) + **查看全部 ›** on the right.
- **Property list card** (rounded 16px, list container). Each row:
  - 42px rounded-square **house icon** (cyan for the default, purple `#c4a6ff` for others).
  - **小区名 (community name)** 15px/700 (e.g. 成都乐府（二仙桥） / 天府新区·云麓) with, for the default property, a mono **默认** badge.
  - Sub-line: **房号 · 专有部分** in mono (e.g. `3-1-702 · 专有部分`).
  - Trailing **切换 ›** (switch active property).
  - Rows separated by a faded cyan hairline.
- **＋ 绑定新房号** — full-width dashed-border action row (cyan, `rgba(47,244,224,.04)` fill) → start binding a new property/room.

> Property data format follows the FreeArk owner app (小区 + 楼-单元-房号, marked 专有部分). Replace the samples with the user's real bound properties.

### Settings & logout
- **参数设置** row → opens the parameter-settings page (gear icon, chevron). This is the entry to the device parameter screen the login/settings style came from.
- **退出登录** — pinned to the bottom of the body (`margin-top:auto`). Pill button, **magenta/pink** accent `#ff7ab5` on `1px solid rgba(255,61,166,.5)` + `rgba(255,61,166,.06)` fill + soft pink glow (the one destructive action). → sign out.

### Profile-page interactions
- Tap **edit** → edit profile (avatar / nickname).
- Tap a property row / **切换** → set it as the active property.
- Tap **查看全部** → full property list.
- Tap **＋ 绑定新房号** → property-binding flow.
- Tap **参数设置** → parameter settings page.
- Tap **退出登录** → confirm + sign out.

---

## Design Tokens

### Colors
- Primary cyan / neon accent: `#2ff4e0` (variants `rgba(47,244,224,*)`, grid `rgba(56,230,224,*)`)
- Cyan bright text (avatars/ARK): `#aef9f2`; light text `#eaf6ff`; body-in-bubble `#dbeeff`; title white `#f4fbff`
- Purple accent: `#8b5cf6` / `#c4a6ff` (secondary property icon, secondary metrics); blob `rgba(101,55,180,*)`
- Success / online / 已认证 green: `#5ff0b6` (border `rgba(95,240,182,.5)`)
- Destructive (logout): `#ff7ab5` (border `rgba(255,61,166,.5)`, glow `rgba(255,61,166,.18)`)
- Gradient (user bubble / send / avatars): `#22e6da → #3a8bff` (→ `#8b5cf6` on avatars). Text on gradient: `#04121f`
- Muted blues: label `rgba(143,217,255,.7)`, dim `rgba(143,217,255,.5)`; inactive tab `rgba(170,195,230,.5)`; chip text `#9fe9e0`
- Surfaces: screen base `#0b0a1a`/`#07101c`/`#050811`; card `rgba(14,22,42,.7–.85)`; input `rgba(4,10,22,.7)`; tab/input bars `rgba(6–8,10–14,20–28,.7–.9)`

### Typography
- **Orbitron** (500/700/900) — ARK avatar glyph, section brand marks.
- **Rajdhani** (500/600/700) — status-bar time, numeric callouts.
- **Share Tech Mono** — mono meta text: IDs, 房号, badges (已认证/默认), section labels (PROPERTY · …).
- **Noto Sans SC** (400/500/700/900) — all Chinese UI text.
- Sizes: 9 / 10 / 11 / 12 / 13.5 / 14 / 15 / 17 / 19 / 24 px. Chinese titles use heavy letter-spacing (2–4px); mono labels 1–2px.

### Spacing / radii / shadows
- Body padding 10–18px; card padding 14–18px; list-row padding 14px 16px; inter-block gap 13–16px.
- Radii: bubbles 14px (with a 5px notch corner toward the sender), cards 16px, list icons 11px, avatars/circle buttons 50%, pills 14–21px, chips 6–14px.
- Card shadow `inset 0 0 26px rgba(20,40,80,.35)`; glows are `0 0 8–18px` of the accent color; corner brackets are 2px accent-colored L-shapes at the card corners.

### Animations (keyframes, all subtle/ambient — motion is intentionally restrained: no scan-sweep, no glitch)
- `ark-dot` 1.2s — thinking-dots bounce (staggered).
- `ark-blink` 1s steps — streaming text cursor.
- `ark-pulse` 1.6–1.8s — online status dots.
- `ark-wave` 1s — voice-input bars (see 方案2; option1 uses a static mic).
- `ark-float` 16s — background glow-blob drift.

## Assets
- **No raster assets.** All icons are inline SVG (chevron, mic, paper-plane, grid, house, gear, power, person, WeChat capsule); the ARK/胖 marks are text. The device bezel/notch/status-bar/WeChat-capsule are mock chrome — do not ship.
- Fonts load from Google Fonts; in a Mini-Program self-host or `@font-face` them (or substitute platform equivalents, keeping the letter-spacing).

## Files in this package
- `screens/AI-QA-option1.html` — standalone reference, AI 问答 方案1 (open in a browser).
- `screens/Profile-option1.html` — standalone reference, 个人中心 方案1.
- `source/AI问答.dc.html`, `source/个人中心.dc.html` — full design-component sources (contain both 方案1 and 方案2; 方案1 = the `ai1` / `me1` blocks).
- `login-reference.png` — original WeChat login screenshot, for style context.
