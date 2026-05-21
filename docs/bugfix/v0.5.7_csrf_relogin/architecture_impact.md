# 架构影响评估 — CSRF Re-login Bug Fix
# version: v0.5.7_csrf_relogin
# author_agent: sub_agent_system_architect (orchestrated by main_agent_pm)
# status: APPROVED
# date: 2026-05-21

---

## 1. 变更范围

本次修复涉及前端两个文件，后端无须修改。

| 文件 | 变更类型 | 原因 |
|------|---------|------|
| `FreeArkWeb/frontend/src/utils/api.js` | 修改 | 暴露 `clearCSRFToken()`；修复 `getCSRFToken()` 缓存短路 |
| `FreeArkWeb/frontend/src/components/Layout.vue` | 修改 | `handleLogout` 调用后端 logout、清除 CSRF 缓存、清除 cookie |

---

## 2. 模块依赖关系（修复前 vs 修复后）

### 修复前

```
Layout.vue
  └── handleLogout()
        ├── localStorage.removeItem(...)
        ├── document.cookie = 'auth_token=; ...'
        └── router.push('/login')
        ← 未调用 api.logout()
        ← 未清除 cachedCSRFToken
        ← 未清除 csrftoken cookie
```

### 修复后

```
Layout.vue
  └── handleLogout()
        ├── api.logout()              ← NEW: 调用后端 /api/auth/logout/
        │     └── authenticatedFetch('/api/auth/logout/', {method: 'POST'})
        ├── api.clearCSRFToken()      ← NEW: 重置内存缓存
        ├── localStorage.removeItem(...)
        ├── document.cookie = 'auth_token=; ...'
        ├── document.cookie = 'csrftoken=; ...'  ← NEW: 清除 CSRF cookie
        └── router.push('/login')

api.js
  ├── clearCSRFToken()               ← NEW export
  ├── getCSRFToken()                 ← MODIFIED: 移除内部缓存短路，每次从 cookie 读
  └── ensureCSRFToken()              ← MODIFIED: 缓存由此函数统一维护
```

---

## 3. 认证流程（修复后全链路）

```
用户操作               前端 (api.js / Layout.vue)           后端 (Django)
─────────────────────────────────────────────────────────────────────
首次访问登录页
  └──> LoginView 渲染
       └──> 无需 CSRF（登录 POST csrf_exempt）

点击「登录」
  └──> POST /api/auth/login/        ──────────────────────> user_login()
                                                              login(request, user)
                                                              rotate_token()    ← 生成新 CSRF token
                                    <──────────────────────  Set-Cookie: csrftoken=T_new
       └──> localStorage.userToken = token
       └──> router.push('/home')

Layout.vue onMounted
  └──> api.get('/api/auth/me/')
        └──> authenticatedFetch()
              └──> ensureCSRFToken()
                    └──> cachedCSRFToken == null → GET /api/get-csrf-token/ ──> get_token()
                    <────────────────────────────────────────── csrftoken=T_new (已由 login 设置)
                    └──> cachedCSRFToken = T_new (从 cookie 读)
              └──> GET (无需 CSRF) → 200 OK

用户点击「退出登录」
  └──> handleLogout()
        └──> await api.logout()     ──────────────────────> user_logout()
                                                              Token.delete()
                                                              logout(request)   ← session 销毁
                                    <──────────────────────  200 OK
        └──> api.clearCSRFToken()   [cachedCSRFToken = null]
        └──> cookie 'auth_token' 清除
        └──> cookie 'csrftoken' 清除
        └──> localStorage 清除
        └──> router.push('/login')

再次点击「登录」
  └──> POST /api/auth/login/        ──────────────────────> user_login()
                                                              login(request, user)
                                                              rotate_token()    ← 生成新 CSRF token T_new2
                                    <──────────────────────  Set-Cookie: csrftoken=T_new2
       └──> router.push('/home')

Layout.vue onMounted (第2次)
  └──> api.get('/api/auth/me/')
        └──> authenticatedFetch()
              └──> ensureCSRFToken()
                    └──> cachedCSRFToken == null ← 已被清除
                    → GET /api/get-csrf-token/ → 获取 T_new2
                    └──> cachedCSRFToken = T_new2
              └──> 正常请求
```

---

## 4. 架构决策记录（ADR-001）

**ADR-001: 选择"登出时主动清除 + 去除 getCSRFToken 内部缓存短路"组合方案**

**背景**：需在"性能（减少 cookie 读操作）"和"正确性（每次用最新 token）"之间取舍。

**方案 A: 仅清除缓存（最小修复）**
- 优点：改动最小
- 缺点：若未来有其他代码路径导致 `cachedCSRFToken` 非 null 但 token 已失效，问题复现

**方案 B: 完全去除缓存（每次从 cookie 读）**
- 优点：无状态，最健壮
- 缺点：频繁 cookie 字符串解析（开销极小，可忽略）

**方案 C: 方案 A + B（本次选择）**
- `clearCSRFToken()` 解决登出时的直接根因
- `getCSRFToken()` 去除内部缓存短路，改为直接读 cookie；`cachedCSRFToken` 的赋值统一由 `ensureCSRFToken()` 负责（在实际调用 `/api/get-csrf-token/` 后赋值）
- 结果：登录后首次 POST 前，`ensureCSRFToken()` 总会从 cookie 读到最新 token

**决定**：方案 C。两种机制互补，代码改动量低（< 20 行），不引入新依赖。

---

## 5. 接口变更

### 5.1 `api.js` 新增导出

```js
// 新增：清除 CSRF token 缓存（供 logout 使用）
export function clearCSRFToken() { ... }

// 新增：调用后端 logout 端点
export async function logout() { ... }
```

`api` 对象（default export）也增加 `logout` 方法和 `clearCSRFToken` 方法，以统一调用接口。

### 5.2 `Layout.vue` 接口变更

`handleLogout` 从同步函数改为 `async` 函数（需等待后端 logout 完成）。

---

## 6. 不影响范围确认

| 模块 | 是否受影响 | 说明 |
|------|-----------|------|
| 所有后端 API views | 否 | 后端无代码修改 |
| Django CSRF 中间件配置 | 否 | settings.py 无变更 |
| CORS 配置 | 否 | 无变更 |
| 数据模型 / migrations | 否 | 无变更 |
| 其他前端 Vue 组件 | 否 | 仅 Layout.vue 修改 |
| 数据采集服务 | 否 | 无关 |

---

## 7. 回滚策略

若修复引入新问题，回滚方式：
1. `git revert` 本次提交（单 commit）。
2. 前端重新构建 + 生产部署（走 `git pull` 流程）。
3. 无需 DB migration 回滚（无 DB 变更）。
