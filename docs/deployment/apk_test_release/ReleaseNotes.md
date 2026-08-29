# 智能方舟座舱 测试版发布说明

> 本文档用于记录所有测试版本的发布信息。版本按**倒序**排列（最新版本在前）。
> 每次发布新版本时，请在表格顶部新增一行，并在下方对应版本补充详细变更说明。

---

## 版本发布总览

| 版本号 | 发布日期 | 发布说明链接 | APK 下载链接 |
| :----: | :------: | :----------: | :----------: |
| v1.0.3 | 2026-08-29 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1AwnJghE08O0nT5DIt03Q_Q?pwd=8qsj) 提取码: 8qsj |
| v1.0.2 | 2026-08-22 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1pkFqpoUGQUNjlSmKKQmgeQ?pwd=awzd) 提取码: awzd |
| v1.0.1 | 2026-08-03 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1UhZTQ0vrf3rB5bgmj3Iw1A?pwd=7xn9) 提取码: 7xn9 |
| v1.0.0 | 2026-07-31 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1cC1xA26b1quZbju3vM3RoQ?pwd=frpe) 提取码: frpe |

---

## 版本详情

<!-- ==================================================================
     新版本发布时：在此上方插入新版本详情块（复制下方模板填写即可）
     ================================================================== -->

<!-- ==================================================================
     v1.0.3
     ================================================================== -->

### v1.0.3 — 2026-08-29

**发布类型**：内测

**版本号**：versionName `1.0.3` / versionCode `10003`

> versionCode 延续 `major*10000 + minor*100 + patch` 规则（1.0.3 → 10003），
> 与微信小程序端的 versionCode `103` 永不撞号。

**APK 下载链接**：
- [百度网盘](https://pan.baidu.com/s/1AwnJghE08O0nT5DIt03Q_Q?pwd=8qsj) 提取码: 8qsj

**关键变更**：
- **副官功能开关**：后端新增副官配置接口（`adjutant_config` 模块），管理端可全局
  开启/关闭副官功能。关闭后副官页面展示「副官外出中」占位插画，不再建立 WebSocket
  会话。API 迁移 `0048` 对应数据库表结构。
- **副官体验优化**：对话气泡由 `flex` 改 `inline-block + vertical-align`，修复 iOS 下
  中文气泡高度异常、文字溢出问题。头像布局从 `flex:0 0 auto` 改为 `display:block`，
  消除 iOS Safari flex 基线计算偏差。
- **副官占位插画优化**：原图 `adjutant-away.png`（2.4MB）替换为 `adjutant-away.jpg`
  （70KB），加载速度提升 97%。新增 `vite.config.js` 的 `copyStaticPlugin` 插件，
  构建后自动同步 `static/` 目录到产物，彻底解决静态资源不被打包的问题。

**修复的问题**：
- **iOS 原生 tabBar 闪烁**：启动时原生底栏先渲染再被 `hideTabBar` 隐藏，产生
  1~2 帧闪烁。根因是 JS 不可能比 native 渲染更早。修复：将 tabBar 的
  `color`/`selectedColor`/`backgroundColor`/`borderStyle` 全部设为页面背景色
  `#05070f`（隐形配色），即使原生底栏画出来用户也看不到，配合 `hideTabBar`
  后隐藏，视觉上无跳变。
- **iOS 两套 tabBar 叠显**：`onLaunch` 中 5 级 `hideTabBar` 重试（0/50/150/300/600ms）
  + 4 个 tab 页 `onShow` 双次兜底，确保任何时机初始化的原生 tabBar 都被隐藏。
- **iOS 舰长休息室 tabBar 消失**：`ArkTabBar` 从 `position:relative`（参与 flex 高度
  计算）改为 `position:fixed; bottom:0; z-index:999`，永远钉在屏幕底部，页面内容
  再长也不会把底栏挤出视口。4 个 tab 页外层容器统一加
  `padding-bottom: calc(100rpx + env(safe-area-inset-bottom))` 占位。
- **ArkTabBar 实际高度多算一倍安全区**：`content-box` 下 `height` 不含 `padding`，
  原写法 `height: calc(100rpx + safe-area)` + `padding-bottom: safe-area` 实际总高
  = `100rpx + 2×safe-area`，比占位多 68rpx（iPhone 刘海屏），导致输入框/退出按钮
  恰好被遮住下半截。修复：`height: 100rpx`，`padding-bottom: env(safe-area)`，
  实际总高精确等于占位值。
- **副官页输入框被 tabBar 遮挡**：`.ai-page` 的 inline `padding-bottom` 原先只写
  `keyboardHeight px`，覆盖了 CSS 里的 tabBar 占位。修复：改为
  `calc(${keyboardHeight}px + 100rpx + env(safe-area-inset-bottom))`，键盘避让与
  tabBar 避让同时生效。
- **舰长休息室退出登录被遮 + 对齐错位**：`logout-bar` 移入 `scroll-view` 内部
  使其可滚动，左右 `padding` 置零靠外层 `.body` 的 36rpx 统一缩进；底部新增
  `bottom-tabbar-spacer` 保证滚到底时按钮完整出现在 fixed tabBar 上方。
- **绑定座舱页无返回按钮**：新增自定义 header 含返回箭头，用户可点击返回
  而非只能右滑手势退出。
- **隐私保护指引标签过长**：「隐私保护指引」改为「隐私保护」，内容不变。
- **RingGauge 右侧深紫杂色**：uCharts `linearType:custom` 的水平渐变在小程序
  真机右半弧产生明显色差。改为 `gap:0` + 单色绘制，消除杂色。

**APK 专项**：
- Cherry-pick 主分支 4 个 commit（副官功能开关 + 体验优化 + 图片优化），
  冲突解决时统一取 main 的 `block` 布局版本（iOS/安卓通用写法），不影响
  apk-test 的多端改造（20s 心跳、`wx.getAppAuthorizeSetting` 多端判断等）。

**已知问题 / 注意事项**：
- 微信开发者工具中 `adjutant-away.jpg` 路径需用 JS 变量拼接
  （`'/static/' + 'adjutant-away.jpg'`），不能用模板字面量——uni-app 模板编译器
  会把字面量静态路径自动转为 Vite asset import，但小程序平台下实际文件不会被复制。

**本次发布包含的 Commit**：
- `dd1d94f` — fix: optimize miniapp adjutant image
- `9090c30` — feat: refine miniapp adjutant experience
- `d222fac` — feat: add miniapp adjutant feature switch
- `430da60` — fix(mp-weixin): iOS tabBar 闪烁/叠显/消失 + 输入框与退出登录被遮修复，版本升 1.0.3

<!--
### vX.X.X — YYYY-MM-DD

**发布类型**：内测 / 公测 / 正式

**APK 下载链接**：
- [ ] 待补充

**关键变更**：
- 
- 
- 

**修复的问题**：
- 
- 

**已知问题 / 注意事项**：
- 

**本次发布包含的 Commit**：
- `commit-hash` — commit message

-->

<!-- ==================================================================
     v1.0.2
     ================================================================== -->

### v1.0.2 — 2026-08-22

**发布类型**：内测

**版本号**：versionName `1.0.2` / versionCode `10002`

> ⚠️ versionCode 从 `150` 跳到 `10002` 而非 `102`：v1.0.0 与 v1.0.1 两个已发布 APK
> 都沿用了 `150`（该字段自 v1.5.0 小程序版起从未更新）。Android 要求 versionCode
> 单调递增，写成 `102` 会低于已装版本、被系统判为降级而无法覆盖安装。
> 现统一为 `major*10000 + minor*100 + patch`，后续 1.1.0 → `10100`，从版本号可直接推导。

**APK 下载链接**：
- [百度网盘](https://pan.baidu.com/s/1pkFqpoUGQUNjlSmKKQmgeQ?pwd=awzd) 提取码: awzd

**关键变更**：
- **副官人格可在对话中修改并跨会话记忆**：对副官说「以后叫我胖子熊大人」即可改称呼，
  退出重进依然生效。此前该能力的写入通路根本没接通（接口有、无调用方），
  且人格提示词会让副官以「我必须遵循守则」为由拒绝改口。
- **舰长休息室新增「副官人格」设置页**：可分别设置副官自称 / 对我的称呼 / 说话语气，
  带实时预览与「恢复默认人格」；对话式修改之外的确定性入口。
- **首次对话主动询问称呼偏好**（US-001 AC-001-02）：新用户首次发言时，
  副官会在回答末尾自然地问一句希望被如何称呼，每连接只问一次。
- 隐私保护指引与微信公众平台填报内容逐条对齐；补充 scope.camera 用于座舱扫码绑定。
- 指挥室卡片入场动画；副官页断连横幅提示；开启会话转发。
- 移除 game 子包 POC 页面（ark-poc / agent-scene），避免审核触发深度合成审查。

**修复的问题**：
- 副官身份自称不一致：同一句「你是谁」，有时答「智能方舟的副官」、有时答「方舟智能体」。
  根因是人格注入只做了专家分支，域外/闲聊分支与多专家融合分支被漏掉，
  而身份提问恰恰最容易落到域外分支。
- 人格字段语义混淆：`tone_style` 在默认分支是「称呼」、自定义分支变成「风格」，
  设成「胖子熊大人」后副官反而自称该名字。现拆为
  `identity`(自称) / `address`(称呼用户) / `tone`(语气) 三个语义单一的键。
- 修复舰桥页面故障状态面板隐形问题。
- 温控面板房间标签按户型解析生产标定真值；逆映射在户型未知时回退关键词匹配。
- 后端写操作三改进：超时清理 + MQTT 静默失聪自愈 + 写后 UX 回显。

**APK 专项（本次 rebase 主分支时的取舍）**：
- **重连机制收敛为单一所有者**。此前 `chat-ws.js` 内部与 `pages/chat/index.vue` 页面层
  各有一套指数退避，同一次断开会触发两轮连接（仅靠 `_connSeq` 序号守卫才没产生重复
  socket）。现统一由页面层负责——它感知 `onHide` 挂起、驱动断连横幅、提供手动重连按钮。
- **保留 APK 专属能力**：20 秒心跳（防 Android 回收空闲 WebSocket）、
  `wx.getAppAuthorizeSetting` 运行时多端判断、真机诊断日志。
- APK 端断连提示由「弹窗询问是否重连」改为「横幅 + 自动退避重连」，
  避免快速切页时连弹多个弹窗。

**已知问题 / 注意事项**：
- 客户端每 20 秒发送的 `{"type":"ping"}` 心跳帧，后端未做识别（静默忽略）。
  保活目的靠出站流量达成，不影响功能，但后端日志不会有对应记录。
- 小程序端与 APK 端共用同一份 `pages.json`，新增的「副官人格」页在两端均已注册。

<!-- ==================================================================
     v1.0.1
     ================================================================== -->

### v1.0.1

**发布类型**：内测

**APK 下载链接**：
- [百度网盘](https://pan.baidu.com/s/1UhZTQ0vrf3rB5bgmj3Iw1A?pwd=7xn9) 提取码: 7xn9

**关键变更**：
- 录音状态机重构：引入 `setStateChangeCallback` 回调机制，UI 状态与内部状态实时同步
- 修复 `isRecording` 提前设置导致权限检查期间松手状态不一致的问题
- 修复 APK 白屏问题：移除 `wx.setEnableDebug` 调用，`tabBar` 配置 `custom: true`
- 修复 project.config.json Media SDK 配置不一致问题，统一为 `true`

**修复的问题**：
- 多端 APK 中 `wx.getAppAuthorizeSetting` 回调不触发导致录音启动卡死（添加 1.5s 超时降级）
- `onStart` 超时后错误销毁录音导致录音数据丢失（超时降级为 recording 状态）
- ChatInputBar 双重异步权限检查导致 `_recording` 与 `isRecording` 不同步
- 上滑取消阈值计算异常（异步边界后 touch 事件对象被回收，改为同步读取）

**包含的文件改动**：
- `miniprogram/utils/voice-input.js` — 状态机重构 + 回调机制
- `miniprogram/components/ChatInputBar.vue` — 状态同步逻辑修复
- `miniprogram/App.vue` — 移除调试模式调用
- `miniprogram/pages.json` — tabBar custom 配置
- `miniprogram/project.config.json` — Media SDK 配置

**已知问题 / 注意事项**：
-

<!-- ==================================================================
     v1.0.0
     ================================================================== -->

### v1.0.0

**发布类型**：内测（首版）

**APK 下载链接**：
- [百度网盘](https://pan.baidu.com/s/1cC1xA26b1quZbju3vM3RoQ?pwd=frpe) 提取码: frpe

**关键变更**：
- 多端应用 APK 首版发布
- 支持业主端设备实时参数查看与新风面板控制
- 支持副官页面语音输入与聊天功能
- 支持二维码扫描绑定业主身份
- 支持语音识别（ASR）离线识别服务

**修复的问题**：
- 业主端接口 specific_part 段数兼容（前端 4 段 vs 后端 3 段格式）
- 新风面板出风温度标签修正，按生产标定改正显示名称
- 新风四温度点标签修正，卡面大字改为真·出风温度

**包含的关键 Commit**：
- `27c3ecc` — fix(miniapp): 业主端接口 specific_part 段数兼容
- `1453187` — fix(miniapp): 新风卡「新风入口温度」收进「查看全部」折叠区
- `1e3ccb9` — fix(miniapp): 新风四温度点按生产标定改正标签
- `5da0000` — fix(params): 修正房间/加湿标注，逆向翻译按户型解析

**已知问题 / 注意事项**：
-

---

## 发布操作 Checklist

每次发布新版本前，按以下清单执行：

- [ ] 编译 APK 成功，安装包已生成
- [ ] 在上方**版本发布总览**表格顶部新增新版本行（倒序）
- [ ] 在此文件下方**版本详情**区，按模板填充新版本发布说明
- [ ] 填写 APK 下载链接
- [ ] 提交本文档的 Commit
- [ ] 通知测试人员对应版本的下载地址和变更内容
