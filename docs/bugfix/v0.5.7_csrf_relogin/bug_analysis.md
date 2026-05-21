# 缺陷根因分析报告 — CSRF Token Missing on Re-login
# version: v0.5.7_csrf_relogin
# author_agent: sub_agent_requirement_analyst (orchestrated by main_agent_pm)
# status: APPROVED
# date: 2026-05-21

---

## 1. 缺陷摘要

| 字段 | 内容 |
|------|------|
| 缺陷 ID | BUG-CSRF-001 |
| 严重级别 | HIGH — 影响核心认证链路，登出后无法再次使用系统 |
| 报告版本 | v0.5.7 |
| 影响范围 | 所有用户，任何"登录 → 登出 → 再登录"操作 |
| 错误信息 | `CSRF failed: CSRF token missing.` |

---

## 2. 复现步骤

1. 打开浏览器，访问系统登录页 `/login`。
2. 输入用户名/密码，点击「登录」→ 登录成功，跳转至首页。
3. 点击右上角用户名下拉 → 选择「退出登录」。
4. 页面跳转回 `/login`。
5. 再次输入用户名/密码，点击「登录」。
6. **观察到错误**：控制台或响应体显示 `CSRF failed: CSRF token missing.`，页面停留在登录页。

**注**：第 1 次登录（步骤 2）100% 成功；第 2 次及后续登录（步骤 5）必现失败。

---

## 3. 根因定位

### 3.1 关键代码路径

#### 3.1.1 CSRF token 缓存变量（`frontend/src/utils/api.js`, 第 13 行）

```js
let cachedCSRFToken = null;   // 模块级变量，生命周期 = 浏览器 tab 会话
```

该变量在 SPA 初始加载时为 `null`，第一次 `ensureCSRFToken()` 被调用时从 `/api/get-csrf-token/` 获取并缓存。只要页面不刷新，该值永远不会重置为 `null`。

#### 3.1.2 `ensureCSRFToken` 的短路逻辑（`api.js`, 第 39-75 行）

```js
async function ensureCSRFToken() {
  if (cachedCSRFToken) {    // ← 只要有缓存，立即返回，不重新获取
    return true;
  }
  // ... 调用 /api/get-csrf-token/
}
```

#### 3.1.3 前端 `handleLogout` 实现（`frontend/src/components/Layout.vue`, 第 199-208 行）

```js
const handleLogout = () => {
  localStorage.removeItem('userToken')
  localStorage.removeItem('isAuthenticated')
  localStorage.removeItem('userInfo')
  document.cookie = 'auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;'
  router.push('/login')
}
```

**问题所在**：
- 未调用后端 `/api/auth/logout/` 端点（Django session 未销毁，Token 未删除）。
- 未清除浏览器的 `csrftoken` cookie。
- **最关键**：未将 `cachedCSRFToken` 重置为 `null`。

#### 3.1.4 后端 `user_login` 视图（`views.py`, 第 74-97 行）

```python
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@csrf_exempt          # ← 登录本身豁免 CSRF 检查
def user_login(request):
    ...
    login(request, user)   # ← Django 的 login() 内部调用 rotate_token()
```

Django 的 `login()` 函数内部调用 `django.middleware.csrf.rotate_token(request)`，这会使旧的 CSRF token 失效并生成新的 token。新 token 写入 Set-Cookie 响应头。

### 3.2 完整故障时序

```
第1次登录（正常）：
  Browser                         Backend
    |--GET /api/get-csrf-token/ -->|
    |<-- Set-Cookie: csrftoken=T1 -|
    |  cachedCSRFToken = T1        |
    |                              |
    |--POST /api/auth/login/ ------>|  (csrf_exempt，无需验证)
    |<-- token=K1, Set-Cookie: csrftoken=T2 (rotate_token 生成新 token)
    |  cachedCSRFToken = T1  ← 未刷新！cookie 中已是 T2，内存中仍 T1
    |                              |
    |--GET /api/auth/me/ ---------->|  (GET，CSRF 不检查，正常)

登出（前端仅本地清理）：
  Browser                         Backend
    |  localStorage cleared        |
    |  auth_token cookie cleared   |
    |  csrftoken cookie: T2 (未清) |  (后端 session/Token 未销毁)
    |  cachedCSRFToken = T1 (未清) |
    |  router.push('/login')       |

第2次登录（失败复现）：
  Browser                         Backend
    |  LoginView mounted           |
    |  handleLogin() called        |
    |                              |
    |--POST /api/auth/login/ ------>|  (csrf_exempt，成功)
    |<-- token=K2, Set-Cookie: csrftoken=T3 (rotate_token 再次轮换)
    |  router.push('/')            |
    |                              |
    |  Layout.vue onMounted        |
    |  loadUserInfo() called       |
    |  authenticatedFetch('/api/auth/me/')
    |    getCSRFToken() → returns cachedCSRFToken = T1 (缓存，未刷新)
    |    但 /api/auth/me/ 是 GET，CSRF 不检查 → 正常
    |                              |
    |  随后第一个 POST 请求（如果有）:
    |    X-CSRFToken: T1           |  ← 过期 token
    |<-- 403 CSRF failed: CSRF token missing
```

**实际触发路径说明**：
- `user_login` 视图有 `@csrf_exempt`，登录 POST 本身不触发 CSRF 错误。
- 错误发生在登录成功后，用户执行第一个需要 CSRF 验证的 POST/PUT/PATCH/DELETE 请求时，此时 `cachedCSRFToken` 持有的是第一次会话的旧 token（T1），而 Django 已经轮换到 T3，导致验证失败。
- 错误信息 `CSRF token missing` 表明后端收到的 `X-CSRFToken` header 值与当前 session 绑定的 token 不匹配（Django 将这种不匹配也归类为 missing）。

### 3.3 根因总结

| # | 根因 | 文件 | 行号 |
|---|------|------|------|
| RC-1 | `handleLogout` 未重置 `cachedCSRFToken = null` | `Layout.vue` | 199-208 |
| RC-2 | `handleLogout` 未调用后端 `/api/auth/logout/`，导致 Django session 未销毁、Token 未删除 | `Layout.vue` | 199-208 |
| RC-3 | `ensureCSRFToken` 有缓存短路，只要 `cachedCSRFToken` 非 null 就跳过重新获取 | `api.js` | 39-44 |
| RC-4 | Django `login()` 调用 `rotate_token()`，使旧 CSRF token 失效，但前端缓存未感知 | `views.py` | 80 |

---

## 4. 修复方案概述

### 4.1 主修复（必须）

**在 `api.js` 中暴露 `clearCSRFToken()` 函数**：

```js
function clearCSRFToken() {
  cachedCSRFToken = null;
}
```

**在 `Layout.vue` 的 `handleLogout` 中**：
1. 调用 `clearCSRFToken()` 清除内存缓存。
2. 调用后端 `/api/auth/logout/` 正确销毁 session 和 Token。
3. 手动清除 `csrftoken` cookie。

### 4.2 防御性修复（推荐）

在 `ensureCSRFToken` 中，在调用后重新从 cookie 读取 token（而非依赖之前的缓存），确保总是拿到服务端最新签发的值：

```js
// 调用 /api/get-csrf-token/ 后，不依赖 cachedCSRFToken 的旧值
// 而是重新从 cookie 解析
cachedCSRFToken = getCSRFToken();
```

这个逻辑已存在（`api.js` 第 66 行），但问题是 `getCSRFToken()` 自身也有缓存逻辑（第 18-20 行）——若 `cachedCSRFToken` 已经非 null，它也会短路返回旧值。需要在 `getCSRFToken()` 中删除缓存短路，改为每次都从 cookie 读取，仅由 `ensureCSRFToken` 负责缓存更新。

### 4.3 方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: 登出时清除缓存 | 最小改动，精准解决 | 需记住每次登出都要清 |
| B: 完全去除缓存，每次从 cookie 读 | 简单，无状态 | 略多 cookie 读操作（可忽略） |
| C: A + B 组合 | 最健壮 | 改动稍多 |

**选择方案 C**，理由：A 解决直接根因，B 防御 Django `rotate_token` 后的 stale 问题。

---

## 5. 验收标准（Acceptance Criteria）

### AC-1（Given/When/Then）
- **Given** 用户已登录成功（第 1 次）
- **When** 用户点击「退出登录」后，再次输入正确用户名密码点击「登录」
- **Then** 第 2 次登录成功，不出现 CSRF 相关错误，正常跳转至首页

### AC-2
- **Given** 用户完成「登录 → 登出 → 再登录」完整链路
- **When** 执行任何 POST/PUT/PATCH/DELETE API 请求（如修改密码）
- **Then** 请求正常返回，不出现 403 CSRF 错误

### AC-3
- **Given** 用户执行登出操作
- **When** 登出完成
- **Then** 后端 Token 已删除，再次使用旧 Token 请求 API 返回 401

### AC-4
- **Given** 用户反复执行「登录 → 登出」循环（5 次）
- **When** 每次均重新登录后执行 POST 请求
- **Then** 全部成功，无 CSRF 错误累积

---

## 6. 不在本次修复范围

- 生产环境 HTTPS 升级（`CSRF_COOKIE_SECURE=True` 配置）
- CSRF_COOKIE_SAMESITE 从 Lax 改为 Strict（不影响本 Bug）
- 前端 SPA 的 Token 刷新机制（session 超时问题）
