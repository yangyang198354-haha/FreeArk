<!--
file_header:
  agent: sub_agent_software_developer
  project: FreeArk miniprogram walking skeleton
  status: APPROVED
  date: 2026-06-23
-->

# Code Review Report — FreeArk Miniprogram Walking Skeleton

## 评审摘要

- 评审文件总数：18
- Finding 统计：CRITICAL 0 条、MAJOR 2 条、MINOR 4 条
- 5 维总体评分（各维平均）：

| 维度 | 得分 |
|------|------|
| Correctness（正确性） | 9/10 |
| Security（安全性） | 9/10 |
| Performance（性能） | 8/10 |
| Maintainability（可维护性） | 9/10 |
| Test Coverage（可测试性） | 7/10 |

---

## 按模块评审详情

---
**MOD-UTIL-AUTH: utils/auth.js**
- Correctness: 10/10
- Security: 9/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage (可测试性): 9/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-001 | MINOR | utils/auth.js:L10 | getUserInfo 中的 try/catch 空 catch 静默吞掉 JSON.parse 错误，调试时无日志 | DOCUMENTED |

---
**MOD-HTTP: utils/http.js**
- Correctness: 9/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage (可测试性): 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-002 | MAJOR | utils/http.js:L13-L14 | BASE_URL 和 WS_BASE_URL 硬编码内网 IP 192.168.31.51。这不是生产凭据（符合 INF-1），但切换到生产 HTTPS 时需手动改代码。建议：从 uni.env 或 .env 文件读取，或在 vite.config.js 中注入 import.meta.env.VITE_API_BASE_URL。 | DOCUMENTED — 骨架阶段已知，生产切换前需处理 |

---
**MOD-API: utils/api.js**
- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage (可测试性): 9/10

无 Finding。4 个 Dashboard API 调用与 NQ-01 确认一致。结露预警复用分页列表 API 读 count，无新后端接口。

---
**MOD-POLLER: utils/poller.js**
- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage (可测试性): 10/10

无 Finding。

---
**MOD-CHAT-WS: utils/chat-ws.js**
- Correctness: 10/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage (可测试性): 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-003 | MINOR | utils/chat-ws.js:L71-L74 | onClose 回调仅返回 code 给 caller，但 reason string 也可能有调试价值（尤其 4001 以外的关闭原因） | DOCUMENTED |

---
**MOD-STORE-AUTH: store/auth.js**
- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage (可测试性): 9/10

无 Finding。isAdmin 仅用 role==='admin'，与项目约定一致（不依赖 is_staff）。

---
**MOD-STORE-CHAT: store/chat.js**
- Correctness: 10/10
- Security: 10/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage (可测试性): 8/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-004 | MINOR | store/chat.js:L32-L37 | appendToken/appendReasoningToken 直接修改 messages 数组末项属性（非 Pinia action 推荐的 $patch）。在极高频 token 流下（逐字符）可能有响应式追踪开销。骨架阶段可接受，高性能场景建议改为批量更新。 | DOCUMENTED |

---
**MOD-COMP-METRIC: components/MetricCard.vue**
- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage (可测试性): 10/10

无 Finding。

---
**MOD-COMP-BUBBLE: components/ChatBubble.vue**
- Correctness: 9/10
- Security: 10/10
- Performance: 8/10
- Maintainability: 9/10
- Test Coverage (可测试性): 8/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-005 | MAJOR | components/ChatBubble.vue:L34-L35 | streaming && content 和 !streaming && content 两个 v-if 都渲染 bubble-text，但逻辑略有重叠（streaming=true 时也可能同时满足 streaming && !content 占位文字）。逻辑正确但可读性待提升，建议用 v-if/v-else-if/v-else 链重构。 | DOCUMENTED |

---
**MOD-PAGE-LOGIN: pages/login/index.vue**
- Correctness: 10/10
- Security: 9/10
- Performance: 10/10
- Maintainability: 9/10
- Test Coverage (可测试性): 8/10

无 CRITICAL/MAJOR Finding。正确读取 res.user（非 res.user_info）。401 → 'SESSION_EXPIRED' 错误映射已覆盖。

---
**MOD-PAGE-HOME: pages/home/index.vue**
- Correctness: 10/10
- Security: 10/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage (可测试性): 7/10

无 CRITICAL/MAJOR Finding。Promise.allSettled 保证任一 API 失败不阻塞其他卡片。

---
**MOD-PAGE-CHAT-IDX: subpackages/chat/pages/index.vue**
- Correctness: 9/10
- Security: 10/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage (可测试性): 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-006 | MINOR | subpackages/chat/pages/index.vue:L100-L104 | loadSessions 中 loading guard（`if (loading.value) return`）在 reset=true 时也会被 guard，若连续两次 onShow 触发（快速切换 tab）可能跳过 reset。建议：reset 时强制重置 loading。 | DOCUMENTED |

---
**MOD-PAGE-CHAT-SES: subpackages/chat/pages/session.vue**
- Correctness: 10/10
- Security: 10/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage (可测试性): 7/10

无 CRITICAL/MAJOR Finding。
- onHide 正确调用 chatWs.close()。
- wsConnected 仅在 "connected" frame 回调中设 true（非 onOpen）。
- 4001 关闭码正确触发 logout + reLaunch。

---

## 未解决的 CRITICAL 问题

无。

## 遗留 MAJOR 问题说明

共 2 条 MAJOR（未超过 3 条阈值，无需额外备注，但已记录）：

- **FND-002**（utils/http.js）：BASE_URL 硬编码为开发内网 IP。骨架阶段为预期行为；生产切换前需改为 import.meta.env.VITE_API_BASE_URL 注入。不影响 WeChat 小程序构建或运行时正确性。
- **FND-005**（ChatBubble.vue）：v-if 链可读性问题，不影响功能正确性，建议在 UI 精化阶段重构。

## 自检清单结果

| 项目 | 结果 |
|------|------|
| 1. login 读 res.user（非 res.user_info） | PASS — pages/login/index.vue:L62 |
| 2. WS 仅在 connected frame 标记 wsConnected=true（非 onOpen） | PASS — utils/chat-ws.js:L55-L59, store/chat.js setConnected 仅在 onConnected 回调 |
| 3. onHide 调用 chatWs.close() | PASS — subpackages/chat/pages/session.vue onHide handler |
| 4. 首页使用 4 个独立 API 调用 | PASS — pages/home/index.vue:L85-L89，Promise.allSettled 4 个调用 |
| 5. isAdmin 仅用 role === 'admin' | PASS — store/auth.js:L16, utils/auth.js:L20 |
| 6. 每个受保护页面有 auth guard | PASS — login/home/chat-index/chat-session 均有 isLoggedIn 检查 |
| 7. 所有请求通过 http.js（无裸 uni.request） | PASS — 所有 API 调用经 api.js → http.js，无直接 uni.request 调用 |
