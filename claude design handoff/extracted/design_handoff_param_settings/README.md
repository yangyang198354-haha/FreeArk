# Handoff: 参数设置页 · 赛博朋克 HOLO-HUD 重设计 (Option 1A)

## Overview
业主端微信小程序「参数设置」页的视觉重设计。该页展示某套户下的全部设备/房间面板（主机、新风、客厅、主卧、次卧、书房、儿童房…），用户可在此查看实时读数（温度/湿度/露点/空气品质等）并下发控制指令（运行模式、风速、加湿开关、温度设定）。本次重设计代号 **1A · HOLO-HUD**：深空底 + 霓虹辉光的赛博朋克高级科技感。

页面是**数据驱动**的：套户结构由接口返回（`getOwnerStructure`），实时值经 MQTT 推送，卡片由 `paramPanels.js` 的 `buildPanels`/`buildCard` 合成。有几个房间/设备就渲染几张卡——README 中列举的 7 张卡是**示例**，真实数量随数据变化。

## About the Design Files
本包内的文件分两类，请勿混淆：

1. **`参数设置-赛博朋克_样机.dc.html`** — 用 HTML 制作的**设计参照样机**（仅展示视觉/交互意图，不是要直接搬进工程的生产代码）。它把卡片用固定示例数据摆出来，方便看清完整视觉。需要 `support.js` 与 `ios-frame.jsx` 才能打开（直接浏览器打开该 HTML 即可，外层是 iPhone 外壳预览）。

2. **`param-settings.vue`** — **已经实现好的目标工程代码**（uni-app + Vue3 `<script setup>` + WXSS）。这是把样机翻译成的、可直接进仓库运行的页面代码，数据/写链路完整保留。**任务的主体是在此文件基础上继续完善**，而不是从 HTML 重新写。

目标工程环境：**uni-app（Vue 3）+ Vite，编译目标 mp-weixin（微信小程序）**。请遵循该工程既有模式（rpx 单位、原生 `<switch>`/`<picker>`、`uni.*` API、WXSS 限制——不支持内联 SVG、`gap` 在旧基础库不稳、远程字体需域名白名单）。

## Fidelity
**High-fidelity (hifi)**。样机给出最终配色、字号、间距、动效与交互意图，请像素级还原。注意小程序渲染与浏览器有差异（辉光更淡、动画/`position:fixed` 表现因基础库而异），以**真机效果**为准做适配。

## 本次交接的核心任务（Gap 列表）
`param-settings.vue` 已落地 1A 约 90% 的视觉。还差两块 1A 标志性的数据可视化——样机用 SVG 实现，小程序不支持内联 SVG，当前 vue 版降级成了「大字 + 进度条」。**请用工程已安装的 `@qiun/ucharts`（canvas 渲染，真机稳定）补齐：**

1. **环形温度仪表盘** — 客厅及各房间卡的「当前温度」。样机效果：直径 ~118px 的圆环，`stroke-width` 8，渐变描边（青 `#7df9ff` → 紫 `#7c3aed`），缺口在底部（约 270° 弧），圆心叠「当前温度 24.5 / 设定 26.0℃」三行文字。用 ucharts arcbar/gauge 还原，配色见 Design Tokens。
2. **实时波形示波器** — 主机卡的运行波形（样机里是横向滚动的青色波形）。用 ucharts line（无点、细线、青色 `#00e5ff`、半透明、可滚动/定时追加点）还原，背景深色 `rgba(4,10,24,.6)`，高度 ~38px。

补齐后须保证：数据仍来自 `buildCard` 产出的卡片模型；写链路（点选即生效去抖下发、写确认、审计上报）**完全不动**。

## Screens / Views

### 参数设置页（单页，纵向滚动卡片流）
- **Purpose**: 查看设备实时读数 + 下发控制。
- **Layout**:
  - 全屏深空底（`#060912` + 三处径向霓虹光晕）。
  - **固定 HUD 背景层**（`position:fixed`，z-index 0/1，纯装饰不拦点击）：①网格 80rpx 漂移动画 ②自上而下扫描线扫过（5.5s 循环）③细扫描线纹理（repeating-linear-gradient）。
  - 内容层 z-index 2，盖在 HUD 之上。
  - 顶部**套户选择条**（`.unit-bar`）：左 PROPERTY 小标 + 套户名（多套户用 `<picker>`，单套户纯文本）；右**均衡器动效**（6 根青紫渐变竖条，连接时跳动）+ **连接状态药丸**（LINK·OK 绿 / LINK·… 橙，含呼吸 LED）。
  - 之下为**设备卡片流**，每张卡 `margin: 22rpx 24rpx`，青/紫按序交替（`ci % 2`）。
- **Components（每张设备卡 `.dev-card`）**:
  - **四角 HUD 括号**（4 个 22rpx 的 L 形角标，上亮下暗）。
  - **呼吸辉光**：`hueFloat` 7s 循环 box-shadow 在青↔紫间流动。
  - **头部**：72rpx 霓虹图标 chip（圆角 18rpx，半透底 + 描边 + 辉光，内含 emoji/缩写）+ 标题（34rpx 700 `#eaf6ff`）+ 等宽编号副标题（Orbitron，20rpx，字距 3rpx，如 `HOST · 270001`）+ 右侧原生 `<switch>`（主开关，color `#00e5ff`）。
  - **指标区** `.metric-row`：双列网格（每项 `width: calc(50% - 14rpx)`），每项 = 小标签（22rpx `#7f8db0`）+ 大字霓虹读数（Orbitron 40rpx 700，青 `#7df9ff` 带辉光；紫卡用 `#c4a6ff`）。**这里是温度/湿度等只读读数；客厅/房间的温度改为环形仪表盘（见任务）。**
  - **运行模式** `.mode-block`：图标药卡，flex wrap，每枚 = emoji 图标 + 文字；选中态青紫渐变 + 辉光边。图标映射：制冷❄ / 制热☀ / 通风🌀 / 除湿💧。
  - **风速等少选项** `.seg`：胶囊分段控件，选中态青蓝渐变（紫卡为紫品红渐变）+ 辉光。
  - **加湿等开关** `.ctl-row`：左标签 + 右原生 `<switch>`。
  - **温度设定** `.num-ctl`：`−` 按钮(96×92rpx) + 中央大字值(Orbitron 48rpx 800 霓虹, 青紫渐变底 + 内辉光) + `＋` 按钮。
  - **查看全部** `.more-row`：等宽小字「查看全部 N 项 ›」，点按展开 `.rest-list`（其余只读读数逐行）。
- **示例卡（样机中）**: 主机(HC·270001)、新风(FA·270002)、客厅(LR·270003)、主卧(270004)、次卧(270005)、书房(270006)、儿童房(270007)。真实页按数据渲染。

## Interactions & Behavior
- **点选即生效**：模式/风速/开关/步进任意改动 → `setEdit` 写入待发 → `scheduleFlush` 去抖 600ms → `applyDevice` 经 MQTT 下发 → `waitConfirm`(8s) 写确认 → `reportDeviceSettingsAudit` 审计上报 → toast（已生效/未确认/部分成功）。数值步进连点会被去抖合并为一次写。点当前态不重复下发。
- **套户切换**：`<picker>` change → `selectUnit` → 加载结构（缓存优先秒开 + 后台静默刷新）→ `connectRoom` 重订阅 MQTT 并主动 `publishRead`。
- **结构缓存**：`owner_structure_{sp}` TTL 30 天；`sync_status=pending` 时 5 分钟。过期旧数据先撑骨架再网络重拉（指数退避 3 次）。
- **空/异常态**：未绑定→去绑定；结构加载中/pending/失败→对应提示 + 重试；无设备→空卡「采集中…/设备未上报」。
- **动画**：HUD 网格漂移 16s linear；扫描线 5.5s linear；卡片呼吸辉光 7s；均衡器条 1.1s；LED 呼吸 1.8s。

## State Management
（`param-settings.vue` 已实现，勿改语义）
- `rooms / roomIndex / currentRoom`：套户列表与当前选中。
- `devices`（sn→{productCode,attrs}）：MQTT 实时值。`edits`（sn→{tag:val}）：待下发。
- `partState`（sp→{structure,structureLoading,errorMsg}）：按套户的结构骨架。
- `panels = buildPanels(structure, config)`；`cards = panels.map(buildCard(...))`：派生卡片模型。
- `expanded`（cardId→bool）：查看全部展开态。
- `mqttConnected`：连接状态（驱动均衡器/药丸）。
- 数据获取：`getDeviceSettingsConfig`（配置+broker+套户）、`getOwnerStructure(sp)`（结构）、MQTT（实时值/写/确认）、`reportDeviceSettingsAudit`（审计）。

## Design Tokens
**颜色**
- 背景：`#060912`（深空底）；卡片青底渐变 `rgba(20,30,56,.74)→rgba(10,16,33,.84)`；卡片紫底渐变 `rgba(28,20,52,.74)→rgba(14,9,30,.84)`。
- 主色青：`#00e5ff` / 文字青 `#7df9ff` / 描边 `rgba(0,229,255,.22)`。
- 主色紫：`#7c3aed` / 文字紫 `#c4a6ff` / 品红 `#c026d3`。
- 强调品红（露点等）：`#ff2e97` / `#ff6fb5`。
- 成功绿（LINK·OK / 设定值）：`#27f5b5`。
- 警告橙（未连接）：`#f59e0b`。
- 文本：主 `#eaf6ff`；次 `#aab6d6`/`#9fb0d6`；弱 `#7f8db0`/`#5f7da6`；编号 `#5f7da6`(青卡)/`#7a6aa6`(紫卡)。

**字体**
- 数字/拉丁铭牌：`Orbitron`（`uni.loadFontFace global:true` 加载，仅作用数字与编号），fallback `'Menlo','Monaco',monospace`。
- 中文/正文：系统默认（`-apple-system` 等）。

**字号（rpx）**：编号副标题 20｜小标签 22-26｜模式文字 26｜标题 34｜指标大字 40｜步进中央值 48。
**圆角（rpx）**：图标 18｜指标/模式 16｜步进按钮 22｜卡片 24｜胶囊/药丸 999。
**辉光**：文字 `text-shadow:0 0 14rpx rgba(0,229,255,.45)`；卡片呼吸 `box-shadow 0 0 28→36rpx`；选中控件 `0 0 16-22rpx` 对应色。
**间距**：卡片外距 22rpx 24rpx；卡片内距 30rpx；控件分隔 `border-top 1rpx rgba(120,160,255,.10)`。
**注意**：所有 flex `gap` 已改为 margin 实现（旧基础库不支持 `gap`），新增布局请沿用 margin 方案。

## Assets
- **Orbitron 字体**：样机用 Google Fonts CDN；vue 版用 `uni.loadFontFace` 从 `cdn.jsdelivr.net` 加载 → **真机需在小程序后台「downloadFile 合法域名」加入 `https://cdn.jsdelivr.net`**，或自托管 ttf / 转 base64（更稳，推荐）。
- **图标**：模式用 emoji（❄☀🌀💧），设备图标用缩写/emoji。如工程有自有图标库，请替换为其图标组件。
- **图表库**：`@qiun/ucharts`（已在 `miniprogram/package.json`），用于补环形仪表盘 + 波形。
- 无位图资源；所有视觉由 CSS/canvas 生成。

## Files
本包内：
- `参数设置-赛博朋克_样机.dc.html` — 1A 视觉样机（设计参照；需同目录 `support.js` + `ios-frame.jsx` 打开）。
- `param-settings.vue` — **目标工程页面代码（在此基础上补 ucharts 图表）**。
- `support.js` / `ios-frame.jsx` — 仅样机预览所需运行时，**不进生产工程**。

仓库内相关文件（在交接对象的 FreeArk 工程中）：
- `miniprogram/subpackages/control/pages/param-settings.vue` — 用本包的同名文件覆盖。
- `miniprogram/utils/paramPanels.js` — 卡片数据逻辑（`buildPanels`/`buildCard`），**勿改**，图表数据从其产出读取。
- `miniprogram/utils/useMqttClient.js` / `screenMqtt.js` / `api.js` — 通道与写链路依赖。
- `miniprogram/package.json` — 确认 `@qiun/ucharts` 已装。

## 给 Claude Code 的一句话指令
> 这是 uni-app(Vue3)+Vite 微信小程序的「参数设置」页。`param-settings.vue` 已实现 1A 赛博朋克 HOLO-HUD UI。请用工程已装的 `@qiun/ucharts` 把客厅/各房间的「当前温度」做成**环形仪表盘**、主机做成**实时波形折线**，替换现有「大字+进度条」，配色/尺寸照本 README 的 Design Tokens；数据继续来自 `buildCard`，MQTT 写链路与审计逻辑保持不变；注意小程序不支持内联 SVG、flex `gap` 用 margin、远程字体需域名白名单。
