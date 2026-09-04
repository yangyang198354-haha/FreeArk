# RELEASE NOTES · 智能方舟座舱（FreeArk Multi-End） v1.0.4

发布日期：2026-09-04
发布范围：`apk-test` 分支（已合并 `main` 的微信小程序主分支 8 次提交，并保留 Android `app-plus` 打包配置）
代码快照：apk-test 最新提交（含 main→apk-test 合并 commit 与本地构建修复）
后端基线：`main` 分支的 LangGraph P0 作用域修复 + P1/P2 加固提交（已部署到树莓派生产环境健康检查 200）
验证状态：Vitest 297/297 通过 · Python E2E 36/36 通过 · 全量回归 2242/2242 通过（14 skips：2 个 MySQL 并发 + 12 个 Linux shell 脚本）· 微信小程序端构建 DONE · H5 端构建 DONE · Android APK 构建需 HBuilderX（详见 §10 已知问题）

---

## 1. 版本号同步（单一真源 SSOT）

| 端/文件 | 字段 | v1.0.3 | v1.0.4 |
|---|---|---|---|
| uni-app 多端版本真源（`miniprogram/manifest.json` L5-L6） | `versionName` / `versionCode` | 1.0.3 / 10003 | 1.0.4 / 10004 |
| Android APK 打包（`manifest.json` → `app-plus.versionName` L56） | `app-plus.versionName` | 1.0.3 | 1.0.4 |
| npm / H5 构建注入（`miniprogram/package.json` L3） | `version` | 1.0.3 | 1.0.4 |
| 微信小程序原生打包链路（`project.miniapp.json` L5-L6） | `version` / `versionCode` | 1.0.2 / 10002 | 1.0.4 / 10004 |

> 注：`project.config.json` 的 `versionCode=150` 是微信开发者工具 **工程配置版本号**，与应用发布版本号解耦，保持不变。

---

## 2. 后端 · LangGraph 多智能体 P0/P1/P2 安全加固（生产已上线）

### 2.1 P0 作用域越权修复（已在 `main` 8096c72 合入，现同步到 apk-test）
- 新增作用域分类：`SCOPED_QUERY_TOOLS` / `OWNER_SELF_TOOLS` / `FILTERED_OWNER_WORKORDER_TOOLS`
- `ScopeEnforcer.check_and_enforce`：对 `get_write_status` 等工具注入 `_bound_specific_parts`，防止普通业主查看别家写记录；对 `set_persona` 等 Owner 自写工具校验 `_user_id` 并拒绝 admin/operator 账号误用
- `build_user_scope`：新增 `user_id` 字段，WebSocket 握手阶段填充
- `orchestrator._gate`：对 OWNER_SELF_TOOLS 跳过 specific_part 校验，但保留 `verify_owner_self_scope` 二次校验并返回真实 `user.pk` 给 `execute_write` 注入
- 新增 36/36 E2E：[test_p0_scope_tools_e2e.py](../FreeArkWeb/backend/freearkweb/api/tests/test_p0_scope_tools_e2e.py)（3 角色 × 工具分类 × 越权负向）

### 2.2 P1 中危修复（SDLC 阶段代码 review 发现并在本次全端合入）
| 编号 | 修复点 | 文件 | 效果 |
|---|---|---|---|
| P1-1 | persona 值提示注入防护：新增 `sanitize_persona_value` + `PersonaInjectionError` + 注入模式黑名单，剔除换行与控制字符，防止持久化的恶意 identity/address/tone 每轮注入 SystemMessage | [persona.py](../FreeArkWeb/backend/freearkweb/api/persona.py) | 阻止持久型 prompt injection 攻击 |
| P1-2 | persona 工具域污染：拆 `PERSONA_TOOLS` 独立工具组，`ENERGY_TOOLS ∪ PERSONA_TOOLS` 绑定 freeark-expert，减少 LLM 误调能耗→人格工具 | [fa_tools.py](../FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py) | 工具 token 预算更高效，LLM 误调概率↓ |
| P1-3 | `_INTERNAL_CONTEXT_TOOLS` 硬编码 → 从 scope_enforcer 导出 `UNDERSCORE_PARAM_TOOLS` 作单一真源 | [scope_enforcer.py](../FreeArkWeb/backend/freearkweb/api/langgraph_chat/scope_enforcer.py) + [orchestrator.py](../FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py) | 新增需下划线参数工具时免双写遗漏 |
| P1-4 | `set_persona.save()` 的异常 fallback 收窄为仅 `FieldError`（DB 断连/约束冲突不再被二次 retry 产生两条错误日志） | [fa_tools.py](../FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py) | 错误语义更准，生产排查更快 |
| P1-5 | `_poll_write_status_until_final`：当 `bound_set` 过滤后 0 条，新增 `final_status="not_found"` 语义，不再误导用户以为"自己家的写操作还在 pending" | 同上 | UX 修正，越权 0 条返回与真 pending 解耦 |

### 2.3 P2 代码质量/可观测性
- `POLL_TIMEOUT_SECONDS = 3` 模块常量（原为硬编码 3s）
- `_extract_write_records_from_handler` 非标信封 fallback：补 warning 日志
- `_get_user_by_id`：对 `OperationalError/InterfaceError` re-raise，不再把 DB 断连吞为"账号不存在"
- E2E 测试：`FREEARK_POC_MOCK=1` 从模块级迁移到 `test_settings.py`（避免先 import 本模块污染其他测试）
- `FILTERED_OWNER_WORKORDER_TOOLS` 空集合：补 `TODO(v1.14): workorder tools` 标记

### 2.4 新增模块：副官推荐（adjutant_recommendations）
- 后端：`api/adjutant_recommendations.py`，功能开关/文案/灰度控制
- API：`views_miniapp.py` + `urls_miniapp.py` 端点接入（小程序/H5/Android 同源）
- 测试：`test_adjutant_recommendations.py` + `test_persona_preference.py`

### 2.5 清理：旧原型下线
- 删除 `agents/langgraph-poc/` 整套旧原型（orchestrator/adapter/bench/fa_tools 等 20 个文件）
- 删除各 `agents/<name>/SYSTEM_PROMPT.md` 旧版非 LangGraph 提示词文件；当前真源：各专家 `*.langgraph.md`

---

## 3. 多端前端 · 微信小程序主分支（main 合并 8 commits）

### 3.1 副官推荐 · 个人化
- 副官推荐功能页：功能开关、图片大小与懒加载优化、隐私安全文案（用户可关闭/重置）
- persona 偏好：聊天页首次对话自动检测未设置称呼、末尾自然询问；支持"更换自称/称呼/语气"立即生效（已受后端 2.2 P1-1 注入防护保护）

### 3.2 iOS 适配
- iOS tabBar：关闭原生 tabBar 时使用双重 hide（onShow 立即 + `setTimeout 100ms` 兜底），确保不与页内 `ArkTabBar` 重叠
- iOS 输入框：键盘弹起自动滚动，防止被遮挡；placeholder 颜色适配深色模式
- iOS 录音：`voice-input.js` 不再 `manager.stop()` 预清理残留，避免 iOS 触发 "recorder not start"；状态机 idle/starting/recording/stopping 4 态防重复 start
- iOS 深色模式：自定义导航栏 `bind` 页纯黑背景；返回按钮/导航标题白色
- 环状 gauge 组件：iOS Safari 渐变渲染异常修复（stroke 替换写法兼容 iOS ≥ 14）

### 3.3 bind 页
- 自定义导航：纯深色背景 + 左返回 + 居中标题
- 二维码扫描结果解析：识别 `\d+:(.+)` 版本前缀自动剥离，兼容新旧二维码

### 3.4 chat 页新版
- 底部栏 `ChatInputBar`：输入 + 录音按钮整合；录音状态通过 `setStateChangeCallback` 实时点亮 UI（配合 4.1 构建修复）
- 副官推荐卡片位 inline 展示（来自后端 `adjutant_recommendations` 端点）
- 语音输入录音时长/振幅波形条可选展示（无数据时自动降级为 toast "正在聆听…"）

---

## 4. 多端前端 · apk-test 工程适配（Android/H5 补齐）

### 4.1 微信小程序端构建修复（main 合并后破坏的缺口）
- `utils/voice-input.js`：新增 `setStateChangeCallback` export（ChatInputBar 需要）；新增 `_setState(state)` 包装统一 fire UI 回调；13 处 `_state = X` 直接赋值→`_setState(X)` 覆盖 onStart/onError/startRecording/stopAndRecognize 全部分支
- **验证**：Vitest 297/297（voice-input 7 条新增用例通过）；`npm run build:mp-weixin` → Build complete，产物 150 files / 1.9 MB

### 4.2 H5 端构建补齐（apk-test 多端 H5 壳）
- **新增构建入口**：`miniprogram/index.html`（H5 壳，`#app` 挂载点 + `<script type="module" src="/main.js"></script>`）
- **多端 outDir 分流**：`vite.config.js` 改为函数式配置，按 `process.env.UNI_PLATFORM` 自动选输出目录：
  - `h5` → `dist/build/h5`
  - `mp-weixin`（默认）→ `dist/build/mp-weixin`
- **新增脚本**：`package.json` 增加 `dev:h5` / `build:h5`（`cross-env UNI_INPUT_DIR=. uni build -p h5`）
- **Vue lockstep 版本修复**：`vue 3.4.21 → 3.5.38`（精确钉住 DCloud alpha 编译器已依赖的 runtime 版本）；新增 `overrides` 段钉 11 子包到同一版本：`compiler-core/dom/sfc/ssr` / `reactivity` / `runtime-core/dom` / `server-renderer` / `shared` / `vue`
- **验证**：`npm run build:h5` → Build complete；产物 3 files / 62.7 KB；路由 history 模式已声明

### 4.3 Android APK 端保留（apk-test 合入 main 时**未被 main 删除覆盖**，已全部保留）
- `manifest.json app-plus` 段：`package=com.freeark.cockpit`、应用名 `智能方舟座舱`、`versionName=1.0.4`、`targetSdkVersion=31`
- Android 权限：声明 `ACCESS_*_LOCATION / CAMERA / RECORD_AUDIO / POST_NOTIFICATIONS / READ_MEDIA_* / READ_/WRITE_EXTERNAL_STORAGE`，附私有描述文案
- DCloud 模块：`Camera` / `Record` / `Scanner`（SDK 对应 `.aar` 在 HBuilderX 打包时自动引入）
- 图标源：6 张 `freeark_icon_*.png`（1024×1024 iOS AppStore / 512 Android xxhdpi / 192 hdpi / 180/120/81 iOS 多尺寸）全部保留
- `static/android/network_security_config.xml`：Cleartext http 允许（内网 PLC / 树莓派联调）
- `project.miniapp.json` 的 `mini-android`/`mini-ios`：保留 `sdkVersion`、`package`、`useExtendedSdk.media/scanner`、图标映射、iOS 隐私描述 `NSPhotoLibraryUsageDescription/NSCameraUsageDescription/NSMicrophoneUsageDescription`

---

## 5. 质量门验证

| 端/层 | 质量门 | 结果 |
|---|---|---|
| 多端组件 UT（Vitest） | 19 files / 297 tests | ✅ 全部通过（1.64s） |
| 后端 P0 作用域 E2E | `test_p0_scope_tools_e2e` | ✅ 36/36 通过 |
| 后端全量回归 | `python manage.py test api`（SQLite 内存库 + FREEARK_POC_MOCK） | ✅ 2242 tests，OK（14 skips，详见 §10） |
| 微信小程序构建 | `npm run build:mp-weixin` | ✅ DONE，150 files / 1.9 MB |
| H5 构建 | `npm run build:h5` | ✅ DONE，3 files / 62.7 KB |
| 后端生产环境健康检查 | `curl /health`（树莓派 192.168.31.51） | ✅ HTTP 200；`freeark-backend.service active(running)` |

---

## 6. 产物部署

| 产物 | 路径 | 如何使用 |
|---|---|---|
| 微信小程序包 | `miniprogram/dist/build/mp-weixin/` | 微信开发者工具 → 导入项目 → 选此目录 → 编译/真机调试 → 上传体验版 |
| H5 静态包 | `miniprogram/dist/build/h5/index.html` + `assets/` | 任何静态托管（Nginx `try_files $uri $uri/ /index.html` 解 history 路由）/ 公众号 WebView / Android WebView 壳 |
| Android APK | 需 HBuilderX（见 §10）打开 `miniprogram/` 目录 → 发行 → 原生 App-云打包 → 下载 `*.apk` | 直接在 Android 设备安装，或上传应用商店 |
| 后端 | 已部署到生产（树莓派 192.168.31.51，`main` → `apk-test` 的 P0/P1/P2 代码一致） | 健康检查 200；无需 migration |

---

## 7. 对业务功能的影响矩阵

| 场景 | 端 | 本次变化 | 用户体感 |
|---|---|---|---|
| 登录/绑定房号 | 全端 | bind 页 iOS 深色模式 UI；二维码版本前缀剥离 | ✅ 兼容新旧二维码；暗模式美观一致性↑ |
| 能耗查询 / 设备设定 / 写操作确认 | 全端 | LangGraph 作用域越权修复 + `get_write_status` bound 过滤 + `not_found` 语义 | ✅ 跨户读取被拒；"别人的写记录"不再 pending 误导 |
| 语音输入 | 微信小程序/Android | iOS "recorder not start" 消除；录音状态机 4 态 + UI 按钮点亮同步 | ✅ 录音成功率↑；UI 无"点了没反应"假象 |
| 副官个性化（自称/称呼/语气） | 全端 | persona 持久化 + 防注入；首次对话询问称呼偏好 | ✅ 个性化成功生效；用户恶意值不再污染系统设定 |
| 副官推荐 | 全端 | 新模块，功能开关/灰度/隐私文案 | ✅ 推荐功能上线，用户可关闭/重置 |
| Chat 页底部栏 | 微信小程序 | 新版 ChatInputBar，整合输入+录音+状态反馈 | ✅ 单页操作成本↓，录音 UX 与微信语音一致 |
| 关于页/版本展示 | 全端 | npm_package_version / uni.getSystemInfoSync.appVersion → v1.0.4 | ✅ 版本号与发布号统一 |
| H5 部署 | WebView / 公众号 | 新增 index.html 壳 + outDir 分流 + Vue lockstep | ✅ 可直接部署为 H5，无需额外工程改造 |

---

## 8. 向后兼容性（Breaking Change Check）

- ❌ **无破坏性变更**：后端 API 端点签名不变、schema 无增删、无 migration 需求
- 作用域收紧后，admin/operator 调用 `set_persona` 会被拒绝（语义拒绝，不是破坏；本来就不允许管理员通过工具改用户人格）
- H5 路由 history 模式保持与 v1.0.3 一致，Nginx conf 无需改

---

## 9. Rollback 方案

| 层 | 回滚方式 |
|---|---|
| 前端任意端 | Git `git revert <merge+构建修复 commit>` → 重 build → 上传/发布 |
| 后端生产 | Git 回滚到 `v1.0.3 → systemctl restart freeark-backend`；无 DB 改动，5 分钟内可完成 |
| 已上传小程序版本 | 微信公众平台 → 版本管理 → 回退到 v1.0.3 体验版 / 线上版 |

---

## 10. 已知问题 / 阻塞（下一版本计划 v1.0.5）

1. **Android APK 构建工具链缺失**（[选择 HBuilderX 路径 A 即可解决](#)）：
   - 本地无 `@dcloudio/uni-app-plus` 适配包 / 无 HBuilderX CLI hbx / 无 gradle / 无 Android SDK
   - **推荐最快路径**：安装 HBuilderX App 开发版 → 打开 `miniprogram/` 目录 → 发行 → 原生 App-云打包 → Android → 公共测试证书（免费）。当前 manifest 已声明完全的 `app-plus` 配置、权限、模块、图标，HBuilderX 打包会直接读取，无需额外改代码
   - 备选离线路径：DCloud Android 离线 SDK（5.13+）+ Android Studio → `生成本地打包 App 资源` → 包进 `_www` → `gradlew assembleRelease`（预计 1 人日环境安装）
2. 14 个 skipped tests 非阻塞（与 v1.0.3 相同）：
   - 2 个 MySQL 并发测试（SQLite 文件锁无法模拟多进程并发，保持 skipped，在真实 MySQL CI 环境运行）
   - 12 个 shell 脚本测试（本机 Windows，需 bash+sha256sum，Linux 部署环境正常执行）
3. mp-weixin `project.miniapp.json` 中 `version/versionCode` 之前停留在 v1.0.2/10002（旧微信原生打包链路遗留），本次直接跳升与 manifest 对齐到 1.0.4/10004。若你仍有"1.0.3 已单独上传但 project.miniapp.json 未改"的历史发布，请在 `versionCode` 上继续 `+1` 到 `10005` 再下一次发布，避免覆盖。
