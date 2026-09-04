# 智能方舟座舱 测试版发布说明

> 本文档用于记录所有测试版本的发布信息。版本按**倒序**排列（最新版本在前）。
> 每次发布新版本时，请在表格顶部新增一行，并在下方对应版本补充详细变更说明。

---

## 版本发布总览

| 版本号 | 发布日期 | 发布说明链接 | APK 下载链接 |
| :----: | :------: | :----------: | :----------: |
| v1.0.4 | 2026-09-04 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1Fz_-t-xIgCtH73EYpxcJ1g?pwd=eib2) 提取码: eib2 |
| v1.0.3 | 2026-08-29 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1AwnJghE08O0nT5DIt03Q_Q?pwd=8qsj) 提取码: 8qsj |
| v1.0.2 | 2026-08-22 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1pkFqpoUGQUNjlSmKKQmgeQ?pwd=awzd) 提取码: awzd |
| v1.0.1 | 2026-08-03 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1UhZTQ0vrf3rB5bgmj3Iw1A?pwd=7xn9) 提取码: 7xn9 |
| v1.0.0 | 2026-07-31 | 见下方详情 | [百度网盘](https://pan.baidu.com/s/1cC1xA26b1quZbju3vM3RoQ?pwd=frpe) 提取码: frpe |

---

## 版本详情

<!-- ==================================================================
     v1.0.4
     ================================================================== -->

### v1.0.4 — 2026-09-04

**发布类型**：内测

**版本号**：versionName `1.0.4` / versionCode `10004`

> versionCode 延续 `major*10000 + minor*100 + patch` 规则（1.0.4 → 10004），
> 与微信小程序端的 versionCode `103/104` 永不撞号。
> ⚠️ 注意：`project.miniapp.json` 中的 `version/versionCode` 在 v1.0.2 后停止更新，
> 本次直接跳升到 `1.0.4 / 10004` 与 manifest 同步；若你有未登记的 v1.0.3 上传记录，
> 下次发布时请将 versionCode 继续 +1 到 10005，避免 Android 视为降级安装。

**APK 下载链接**：
- [百度网盘](https://pan.baidu.com/s/1Fz_-t-xIgCtH73EYpxcJ1g?pwd=eib2) 提取码: eib2
- APK 文件名：智能方舟座舱-测试版-1.0.4.apk

**关键变更**：
- **后端 LangGraph 多智能体 P0 作用域越权修复 + P1/P2 加固（生产已上线）**：新增 `SCOPED_QUERY_TOOLS` / `OWNER_SELF_TOOLS` / `FILTERED_OWNER_WORKORDER_TOOLS` 工具分类；`get_write_status` 等读工具注入 `_bound_specific_parts` 过滤，普通业主仅能看到自己房号的写记录；`set_persona` 等 Owner 自写工具启用 `_user_id` 强校验，并拒绝 admin/operator 账号误用；`_gate` 二次校验 `verify_owner_self_scope` 以真实用户主键注入写入链路。
- **后端 LangGraph P1 安全修复**：persona 字段写入启用注入防护（控制字符/换行符剔除 + 注入模式黑名单 + `PersonaInjectionError`），阻止持久化的恶意身份/称呼/语气每轮注入 SystemMessage；`_INTERNAL_CONTEXT_TOOLS` 改为从 scope_enforcer 导出 `UNDERSCORE_PARAM_TOOLS` 单一真源，避免新增需下划线参数工具时漏改造；`set_persona.save()` fallback 收窄为仅 `FieldError`，不再把 DB 断连/约束冲突吞为二次异常；`_poll_write_status_until_final` 新增 `final_status="not_found"` 语义（越权 0 条 vs 真 pending 解耦），不再误导用户以为"自家写操作还在等待 PLC 回执"。
- **后端 P2 代码质量与可观测性**：轮询超时 `POLL_TIMEOUT_SECONDS` 从硬编码 3s 提为模块常量；非标写记录信封 fallback 分支补 `logger.warning`；`_get_user_by_id` 对 `OperationalError/InterfaceError` 重新抛出，避免"DB 断连"被误译为"账号不存在"；E2E 测试 `FREEARK_POC_MOCK=1` 从模块级迁移到 `test_settings.py`，避免先 import 污染其他测试。
- **后端新模块**：`adjutant_recommendations` 副官推荐模块（功能开关/灰度/隐私说明），通过 `views_miniapp.py` + `urls_miniapp.py` 提供端点；新增 persona 偏好查询与设置端点；配套测试文件 `test_adjutant_recommendations.py` / `test_langgraph_phase_g.py` / `test_persona_preference.py`。
- **清理旧原型**：移除 `agents/langgraph-poc/` 整套旧原型（orchestrator / adapter / bench / fa_tools 等 20 个文件），删除各 `agents/<name>/SYSTEM_PROMPT.md` 旧版非 LangGraph 提示词，当前真源为同名 `*.langgraph.md`。
- **微信小程序主分支（main 8 commits 同步）**：
  - 副官推荐功能页：功能开关、图片懒加载与压缩、隐私安全文案（用户可关闭/重置）。
  - iOS 适配：tabBar 隐形配色 + onShow 双次 `hideTabBar` 兜底，消灭 iOS 启动 1~2 帧底栏闪烁；ArkTabBar 改为 `position:fixed bottom:0 z-index:999`，避免内容过长把底栏挤出视口；输入框底部占位精确等于 `100rpx + safe-area`。
  - iOS 录音：`voice-input.js` 不再无条件 `manager.stop()` 清理残留，状态机 idle/starting/recording/stopping 4 态防止重复 start，消除 iOS "recorder not start" 报错。
  - iOS 深色模式：bind 页自定义导航栏纯深色背景 + 左返回箭头 + 居中标题。
  - 新版 chat 页：ChatInputBar 整合文本输入 + 语音按钮，录音状态通过 `setStateChangeCallback` 实时点亮 UI（与 4.1 构建修复配套）。
  - 二维码解析：识别 `\d+:(.+)` 版本前缀自动剥离，兼容新旧二维码。
  - 环状 gauge 组件：uCharts custom 渐变在 iOS Safari 真机右半弧杂色修复。
- **多端 apk-test 合并（保留 Android 打包配置）**：main 合并到 apk-test 时，完整保留 `manifest.json app-plus` 段（包名 `com.freeark.cockpit`、权限、Camera+Record+Scanner 模块）、6 张 `freeark_icon_*` 多尺寸图标、`static/android/network_security_config.xml`（内网 HTTP 明文放行）、`project.miniapp.json` 的 `mini-android/mini-ios` 扩展 SDK 配置与 iOS 隐私描述。
- **多端构建工程化补齐**：
  - H5 端：新增 `miniprogram/index.html` 壳；`vite.config.js` 改为按 `UNI_PLATFORM` 分流输出目录（mp-weixin → `dist/build/mp-weixin`，h5 → `dist/build/h5`）；`package.json` 新增 `dev:h5` / `build:h5` 脚本；Vue lockstep 从 3.4.21 升到 3.5.38 并在 `overrides` 钉死 11 个子包，解决 `normalizeCssVarValue` 导出缺失导致的 H5 构建中断。
  - 微信小程序端：`utils/voice-input.js` 新增 `setStateChangeCallback` export（配合新版 ChatInputBar 的 UI 状态同步）、`_setState` 包装统一 fire UI 回调，13 处直接赋值迁移到统一入口。
- **版本号统一（单一真源）**：`manifest.json`（versionName × 2 / versionCode）、`app-plus.versionName`、`package.json` version、`project.miniapp.json` 的 version 与 versionCode 全部同步为 `1.0.4 / 10004`。
- **质量门**：Vitest 297/297（19 files，1.64s）；后端 P0 作用域 E2E 36/36；后端全量回归 2242 OK（14 skips 与 v1.0.3 相同）；微信小程序构建成功（150 files / 1.9 MB）；H5 构建成功（3 files / 62.7 KB）；后端生产健康检查 HTTP 200，systemd 服务 running。

**修复的问题**：
- **P0 越权**：普通业主可通过 `get_write_status` / `get_persona` 等绕过作用域查看他人写记录或调用未授权工具，修复后 ScopeEnforcer 注入 bound 过滤器，`final_status` 与 gate 双层防线均生效。
- **P1 持久型 prompt injection**：`set_persona` 之前仅 `strip()[:MAX]`，恶意身份字符串可写入数据库并在后续每轮 SystemMessage 中注入，修复后 `sanitize_persona_value` + 黑名单前置拒绝。
- **iOS 录音「点了没反应」假象**：`onStart` 回调晚于权限检查，UI `isRecording` 与内部状态不一致；修复后 4 态状态机 + `setStateChangeCallback` 保证 UI 点亮只在录音真正启动时发生，starting→stopping→idle 的路径覆盖快速点击场景。
- **H5 构建中断 `normalizeCssVarValue is not exported`**：DCloud alpha 编译器将 runtime-core 升到 3.5.38 但我们 package 锁了 vue 3.4，导致两套 Vue lockstep 失配；修复后顶层 vue 与 overrides 全 11 子包钉到 3.5.38。
- **H5 构建缺入口「Could not resolve entry module index.html」**：新增 `miniprogram/index.html` 作为 H5 壳。
- **新版 ChatInputBar 导入失败 `setStateChangeCallback is not a function`**：voice-input 缺少该 export，补 export + 13 处赋值迁移为 `_setState`。
- `project.miniapp.json` 的 version/versionCode 停留在 v1.0.2，与 manifest 脱节，修复后跳升对齐到 1.0.4/10004。

**APK 专项（本次 main→apk-test rebase 与构建链路的取舍）**：
- **main→apk-test 合并策略**：冲突时 `manifest.json app-plus` 段、`project.miniapp.json mini-android/mini-ios` 段、`static/android/*`、`freeark_icon_*` 6 张图标、`package.json app-plus*` 相关字段**一律以 apk-test 为准**，不被 main 删除覆盖；微信小程序源码 / Vue 页面 / JS 工具 / 后端代码**以 main 为准**（main 是主分支，包含副官推荐、iOS 适配、persona 设置、chat 新版等业务改动）。
- **版本号对齐策略**：main 合并前 manifest v1.0.3/10003、apk-test project.miniapp v1.0.2/10002，本次统一为 1.0.4/10004，两端同步。
- **新增构建脚本保留 apk-test 后端健康检查**：20s WebSocket 心跳、`wx.getAppAuthorizeSetting` 多端判断、Media/Camera/Record/Scanner 扩展 SDK（mini-android 声明为 `media/scanner=true`）、iOS 3 条隐私描述均保留。
- **Android APK 阻塞项（非代码问题，纯工具链）**：本地缺少 `@dcloudio/uni-app-plus` 适配包、HBuilderX CLI (hbx)、Gradle、Android SDK，导致无法本地生成 APK；当前推荐方案 **HBuilderX 云打包（路径 A）** 已在 APK 下载链接条目写明，无需额外改任何代码——所有打包配置已完整声明。

**已知问题 / 注意事项**：
- Android APK 构建需 HBuilderX（路径 A 云打包最快，20 分钟内完成；路径 B 离线 SDK+Android Studio 约 1 人日）。
- 14 skips 与 v1.0.3 相同：2 个 MySQL 并发测试（SQLite 文件锁无法模拟，需真实 MySQL CI）、12 个 Linux shell 脚本测试（本机 Windows，需 bash+sha256sum，部署树莓派环境下正常运行）。
- mp-weixin `project.miniapp.json` 本次从 10002 跳到 10004（跳过了 10003），若你在 2026-08-29 到 2026-09-04 之间曾以微信原生打包链路单独上传过 v1.0.3，请将 versionCode 再 +1 到 10005 后再发布，避免 Android 判定为降级。
- 本次后端部署（P0/P1/P2）无 DB migration，Rollback 仅需 git revert 到 v1.0.3 并 `systemctl restart freeark-backend`，5 分钟可完成。
- H5 路由为 history 模式，Nginx 部署需配 `try_files $uri $uri/ /index.html;`，否则刷新深层路由会 404。
- 小程序 uploadFile / request 合法域需在微信公众平台后台按环境配置，否则真机无法访问后端。

**本次发布包含的 Commit**：
- `a25e483` (main HEAD 汇入) — 副官推荐模块、persona 端点、main 微信小程序 8 commits、清理 langgraph-poc 旧原型、旧提示词
- `f936c83` (main HEAD 汇入) — SDLC P1/P2 代码 review 修复 + 生产部署 commit
- `8096c72` (main HEAD 汇入) — fix(P0-scope): LangGraph 作用域越权修复 + write-status/persona 工具 + E2E 测试
- `a10b09b` (apk-test merge commit) — Merge branch 'main' into apk-test（保留 apk-test Android 打包配置）
- 本地 apk-test 构建修复 commit（待你确认执行 commit & push 后会补入哈希）：
  - fix(mp-weixin build): voice-input 补 setStateChangeCallback export 与 _setState
  - fix(h5 build): 新增 index.html 壳 + vite 多端 outDir + build:h5 script + Vue 3.5.38 lockstep + overrides 钉死
  - chore(version): 1.0.3→1.0.4, versionCode 10003→10004（manifest × 2 处 / package.json / project.miniapp.json）
  - docs: 新增 RELEASE_NOTES_v1.0.4.md + CHANGELOG.md + 本 ReleaseNotes v1.0.4 段

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
