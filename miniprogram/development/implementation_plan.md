<!--
file_header:
  agent: sub_agent_software_developer
  project: FreeArk miniprogram walking skeleton
  status: APPROVED
  date: 2026-06-23
-->

# Implementation Plan — FreeArk Miniprogram Walking Skeleton

## 实现概览

- 总模块数：9
- 总文件数：18
- 实现顺序：工具层 → Store 层 → 组件层 → 页面层（拓扑排序，被依赖者先实现）

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-UTIL-AUTH | Auth 工具 | utils/auth.js | — | L | DONE |
| 2 | MOD-HTTP | HTTP 客户端 | utils/http.js | MOD-UTIL-AUTH | M | DONE |
| 3 | MOD-API | API 目录 | utils/api.js | MOD-HTTP | L | DONE |
| 4 | MOD-POLLER | 轮询器 | utils/poller.js | — | L | DONE |
| 5 | MOD-CHAT-WS | WebSocket 客户端 | utils/chat-ws.js | MOD-HTTP | M | DONE |
| 6 | MOD-STORE-AUTH | Auth Store | store/auth.js | MOD-UTIL-AUTH | L | DONE |
| 7 | MOD-STORE-CHAT | Chat Store | store/chat.js | — | L | DONE |
| 8 | MOD-COMP-METRIC | MetricCard 组件 | components/MetricCard.vue | — | L | DONE |
| 9 | MOD-COMP-BUBBLE | ChatBubble 组件 | components/ChatBubble.vue | — | M | DONE |
| 10 | MOD-PAGE-LOGIN | 登录页 | pages/login/index.vue | MOD-STORE-AUTH, MOD-API | M | DONE |
| 11 | MOD-PAGE-HOME | 首页仪表盘 | pages/home/index.vue | MOD-STORE-AUTH, MOD-API, MOD-POLLER, MOD-COMP-METRIC | M | DONE |
| 12 | MOD-PAGE-CHAT-IDX | 会话列表页 | subpackages/chat/pages/index.vue | MOD-STORE-AUTH, MOD-STORE-CHAT, MOD-API | M | DONE |
| 13 | MOD-PAGE-CHAT-SES | 聊天页 | subpackages/chat/pages/session.vue | MOD-STORE-AUTH, MOD-STORE-CHAT, MOD-CHAT-WS, MOD-API, MOD-COMP-BUBBLE | H | DONE |

## 配置文件

| 文件 | 说明 |
|------|------|
| package.json | uni-app Vue3 依赖；cross-env 用于 UNI_INPUT_DIR 设置 |
| manifest.json | 小程序基本配置，appid 为占位符 wx0000000000000000 |
| pages.json | 页面路由 + tabBar + subPackages |
| vite.config.js | vite + uni 插件配置 |
| App.vue | 全局样式 |
| main.js | 创建 SSR App + Pinia |
| .gitignore | 排除 node_modules, dist, unpackage |

## 架构偏差记录

| 偏差ID | 偏差描述 | 原设计 | 偏差原因 |
|--------|---------|--------|---------|
| DEV-001 | package.json 版本号从 3.0.0-4020920250604001 改为 3.0.0-alpha-5010320260611001 | 任务说明指定 4020920250604001 | 该版本在 npm registry 不存在；使用实际可用的最新 alpha 版本（经 npm show 确认） |
| DEV-002 | 新增 cross-env devDependency + UNI_INPUT_DIR=. 前缀 | 原始 scripts 无 cross-env | uni-app 5.x alpha 默认 UNI_INPUT_DIR=./src；源文件在根目录需显式覆盖此环境变量 |

## 构建结果

```
DONE  Build complete.
Run method: open Weixin Mini Program Devtools, import dist\build\mp-weixin run.
```

构建输出位于：`miniprogram/dist/build/mp-weixin/`
