# Changelog · 智能方舟座舱（FreeArk）

> 版本发布说明的详细版位于 `miniprogram/RELEASE_NOTES_v<version>.md`（含各端验证状态、质量门数据、回滚与已知问题）。
> 本文件为仓库根聚合版，便于 Git Release 页直接复制粘贴或查阅历史。

---

## [v1.0.4] · 2026-09-04 · apk-test 分支（已合并 main 微信小程序主分支全量改动 + LangGraph 加固 + 多端构建补齐）

- 适用端：**微信小程序 / H5 / Android APK 打包链路（app-plus）**
- 后端：与 `main` 同步，已部署生产（树莓派健康检查 200 OK），**无 migration / 无破坏性 API 变更**

### 关键新增
- **后端 LangGraph 多智能体 P0 作用域越权修复 + P1/P2 加固**：新增 SCOPED_QUERY / OWNER_SELF 工具分类，普通业主访问被 strict 约束到绑定房间；persona 写入启用注入防护；poll 状态新增 `not_found` 语义；UNDERSCORE 参数工具组改为单一真源。配套 E2E 36/36 OK。
- **后端新模块：副官推荐（adjutant_recommendations）** + persona 偏好端点。
- **微信小程序主分支（main 8 commits）**：副官推荐功能 + 图片/隐私优化；iOS tabBar/输入框/录音/深色返回/环状 gauge 修复；bind 页自定义导航深色；chat 页新版 ChatInputBar + voice-input 状态回调；人格设置 UI。
- **apk-test 多端工程化**：main 合并后保留 Android app-plus 打包配置（包名/权限/Camera+Record+Scanner/6 张图标、network_security_config、mini-android/ios 扩展 SDK 与 iOS 隐私描述）未被 main 删除覆盖。H5 端补齐 index.html 壳、vite outDir 分流、Vue 3.5.38 lockstep + overrides。voice-input 补 `setStateChangeCallback` 导出让新 ChatInputBar 可用。
- **版本号统一**：manifest.versionName/versionCode + app-plus.versionName + package.json version + project.miniapp.json version/versionCode → `1.0.4 / 10004`。

### 质量门
- Vitest 297/297 通过（19 files）
- Python E2E P0 作用域测试 36/36 通过
- 后端全量回归 2242 OK（14 skips 为 Windows/Mock 环境限制，与 v1.0.3 一致）
- 微信小程序构建 DONE：150 files / 1.9 MB → `miniprogram/dist/build/mp-weixin/`
- H5 构建 DONE：3 files / 62.7 KB → `miniprogram/dist/build/h5/`
- Android APK：需 HBuilderX 发行 → 原生 App-云打包（当前 manifest 配置已齐全，详见详细版 §10）

### 已知问题（下版本计划）
1. 本地无 HBuilderX / uni-app-plus / gradle / Android SDK，Android APK 需走 HBuilderX 云打包（推荐）或配离线 SDK。
2. 14 skipped tests 与 v1.0.3 相同：2 MySQL 并发、12 Linux shell。
3. `project.miniapp.json` 上一版本停在 1.0.2/10002，本次跳升到 1.0.4/10004 同步。如下次发布前你已有独立上传，请继续将 `versionCode +1` 防止版本号回退。

详细发布说明（含影响矩阵、Rollback 方案、单步 H5/小程序部署指引）见：[`miniprogram/RELEASE_NOTES_v1.0.4.md`](./miniprogram/RELEASE_NOTES_v1.0.4.md)。
