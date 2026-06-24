# 技术选型表 — v1.5.0 微信小程序移动端

**文档编号**: ARCH-MP-v150-003
**项目名称**: FreeArk 微信小程序移动端（v1.5.0_wechat_miniprogram）
**版本**: 1.0.0
**状态**: DRAFT — 待用户确认
**创建日期**: 2026-06-23
**作者**: system-architect (via pm-orchestrator)
**输入文档**: ARCH-MP-v150-001

---

## 技术选型汇总表

| 类别 | 选型 | 版本目标 | 选择理由 | 备选方案 | 排除原因 |
|------|------|---------|---------|---------|---------|
| **小程序框架** | uni-app（Vue 3 + Composition API） | ^3.x（Vue 3） | 现有 Web 已是 Vue 3，零切换成本；uCharts/uni-ui 生态成熟；单人维护成本最低 | Taro（React） | 引入 React 技术栈，增加维护成本 |
| **UI 组件库** | wot-design-uni | ^1.x | 轻量（< 200KB），小程序兼容好，组件丰富；全 Vue 3 Composition API | uni-ui | uni-ui 功能覆盖稍弱；wot-design-uni 更现代 |
| **状态管理** | Pinia | ^2.x | Vue 3 官方推荐，uni-app 原生支持，类型友好 | Vuex | Vuex 已被 Vue 官方降为维护模式 |
| **图表库** | uCharts | ^2.x | 专为 uni-app/小程序 Canvas 适配，轻量（压缩约 200KB），中文文档完善 | ECharts for uni-app | ECharts 体积更大（~1MB+），在主包引入更吃紧 |
| **Markdown 渲染** | towxml | ^3.x | 专为微信小程序设计，内置 Markdown 静态解析，无 eval，支持代码高亮 | mp-html | mp-html 默认处理 HTML，Markdown 支持需额外插件 |
| **WebSocket 通信** | uni.connectSocket / SocketTask | — | uni-app 官方 API，小程序原生 WebSocket，兼容后端现有 `/ws/chat/` 协议 | HTTP SSE | 后端无 SSE 端点（经代码确认），仅 WebSocket |
| **HTTP 请求** | uni.request（封装为 http.js） | — | uni-app 官方 API，封装后统一鉴权头、401 拦截、baseURL 管理 | axios-miniprogram-adapter | 增加依赖，uni.request 已足够 |
| **本地存储** | uni.setStorageSync / uni.getStorageSync | — | 微信小程序本地持久化标准 API（替代 Web 端 localStorage） | wx.setStorage（异步） | Sync 版本在启动时读取更可靠，避免异步竞态 |
| **构建工具** | uni-app 内置（基于 Vite） | Vite 5.x | uni-app HBuilderX/CLI 内置，无需额外配置 | Webpack | uni-app CLI 已从 Webpack 迁移到 Vite，性能更好 |
| **包管理** | npm | — | 与现有 FreeArkWeb/frontend 保持一致，miniprogram/ 独立 package.json | yarn/pnpm | 无特殊需求，npm 已足够 |
| **代码语言** | Vue SFC + JavaScript（ES2020+） | — | 与现有 Web 端一致，单人维护无 TypeScript 切换成本 | TypeScript | 首期 MVP 不引入，后期可按需迁移 |
| **目标平台** | 微信小程序（首发），H5/App（后续） | 微信基础库 ≥ 3.0 | 需求明确，uni-app 一套代码多端编译 | 原生小程序开发 | 原生开发无法复用现有 Vue 代码经验 |

---

## 后端技术栈（复用现有，无新增）

| 类别 | 现有选型 | 版本 | 小程序适配说明 |
|------|---------|------|--------------|
| **Web 框架** | Django | 4.x | 完全复用，无改动 |
| **API 框架** | Django REST Framework | 3.x | Token 认证直接适配小程序 |
| **WebSocket** | Django Channels + Daphne（ASGI） | 4.x | `ws/chat/` 端点直接适配，token 经 query param 鉴权 |
| **认证** | SlidingWindowTokenAuthentication（自定义） | — | Token 经 `Authorization: Token xxx` 头传递，无 Cookie/CSRF 依赖 |
| **数据库** | MySQL 8.x | — | 完全复用，无改动 |
| **消息代理** | MQTT（内网） | — | 完全复用，无改动 |
| **AI 推理** | LangGraph + OpenClaw/DeepSeek | — | 完全复用 |
| **反向代理** | Nginx | — | 需新增 SSL 终止配置（BA-03/04 适配项） |
| **部署** | 物理机（树莓派 Pi4 aarch64），git pull | — | 无 Docker，后端适配改动均通过 git pull + 重启服务部署 |

---

## 前端依赖清单（miniprogram/package.json 关键依赖）

```json
{
  "dependencies": {
    "@dcloudio/uni-app": "^3.0.0",
    "@dcloudio/uni-ui": "^1.4.0",
    "wot-design-uni": "^1.0.0",
    "pinia": "^2.1.0",
    "towxml": "^3.0.0",
    "u-charts": "^2.4.0"
  },
  "devDependencies": {
    "@dcloudio/uni-mp-weixin": "^3.0.0",
    "vite": "^5.0.0",
    "@vitejs/plugin-vue": "^5.0.0"
  }
}
```

---

## 版本约束与兼容性说明

| 约束项 | 要求 | 说明 |
|-------|------|------|
| 微信基础库版本 | ≥ 3.0（建议）/ 最低 2.24.x | Canvas 2D API（uCharts 使用）需 2.9.x+；towxml 3.x 需 2.x+ |
| 微信客户端版本 | ≥ 8.0 | NFR-MP-06 要求 |
| iOS 版本 | iOS 13+ | 微信 8.0 最低支持版本 |
| Android 版本 | Android 7.0+ | 微信 8.0 最低支持版本 |
| 主包大小限制 | ≤ 2MB | 微信平台强制要求 |
| 总包大小限制 | ≤ 20MB | 微信平台强制要求（含所有分包） |
| WebSocket 并发 | ≤ 2 个 | 微信平台限制；AI 问答占 1 个 |

---

## 开发环境要求

| 工具 | 版本要求 | 说明 |
|------|---------|------|
| 微信开发者工具 | 最新稳定版（≥ 1.06.x） | 小程序调试、预览、上传 |
| Node.js | ≥ 18 LTS | 与现有 FreeArkWeb/frontend 生产服务器 Node 22 一致（开发机 ≥ 18 即可） |
| HBuilderX | ≥ 4.x（可选） | DCloud 官方 IDE，uni-app 开发体验更好；也可纯 CLI 开发 |
| VS Code + uni-app 插件 | — | 若不用 HBuilderX，VS Code + Volar + uni-app 插件可替代 |

---

## 技术选型风险说明

| 选型 | 潜在风险 | 缓解措施 |
|------|---------|---------|
| uCharts | iOS 微信某些版本 Canvas 渲染异常 | 开发阶段 iOS/Android 真机双端验证；备选 ECharts for uni-app（可替换，接口结构相近） |
| towxml | 复杂 Markdown（表格/代码块）在低版本基础库渲染可能有小 bug | 测试目标基础库版本，必要时降级为 mp-html |
| wot-design-uni | 相对较新，部分边缘组件可能有 bug | 有充分备选（uni-ui），组件间切换成本低 |
| uni-app CLI 模式 | Vite 5 + uni-app 插件偶有构建兼容问题 | 锁定版本；HBuilderX 作为备用开发环境 |
