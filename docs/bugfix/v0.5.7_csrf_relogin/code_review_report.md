# 代码评审报告 — BUG-CSRF-001 修复
# version: v0.5.7_csrf_relogin
# author_agent: sub_agent_software_developer (orchestrated by main_agent_pm)
# status: APPROVED
# date: 2026-05-21

---

## 1. 评审范围

| 文件 | 变更行数 | 变更类型 |
|------|---------|---------|
| `FreeArkWeb/frontend/src/utils/api.js` | +30 / -18 | 修复 CSRF token 缓存逻辑 |
| `FreeArkWeb/frontend/src/components/Layout.vue` | +10 / -6 | 修复 handleLogout |

---

## 2. 变更逐项评审

### 2.1 `api.js` — `clearCSRFToken()` 新增（第 18-22 行）

```js
function clearCSRFToken() {
  cachedCSRFToken = null;
}
```

**评审结论**: PASS
- 语义清晰，职责单一。
- 通过 `api.clearCSRFToken` 暴露，外部调用者无需了解内部变量名。
- 无副作用，幂等安全。

### 2.2 `api.js` — `getCSRFToken()` 去除内部缓存短路

**修改前**:
```js
function getCSRFToken() {
  if (cachedCSRFToken) { return cachedCSRFToken; }  // 缓存短路（BUG 根因之一）
  // 读 cookie...
}
```

**修改后**:
```js
function getCSRFToken() {
  // 直接从 cookie 读取，无内部缓存
  const cookieParts = document.cookie.split('; ');
  ...
}
```

**评审结论**: PASS
- 去除了 `getCSRFToken` 的状态依赖，使其成为纯函数（输入: cookie 字符串，输出: token 或 null）。
- cookie 解析性能：document.cookie 读取为 O(1)，字符串 split 为 O(n) where n = cookie 数量，典型场景下 cookie 数量 < 10，开销可忽略。
- 调用频率：每次 `authenticatedFetch` 调用一次，系统正常使用频率在合理范围内。

**潜在风险**: NONE
- 原有调用方（`authenticatedFetch`）逻辑不变：先调 `getCSRFToken()`，null 时再调 `ensureCSRFToken()`。行为正确。

### 2.3 `api.js` — `ensureCSRFToken()` 修复

**修改前**: 以 `cachedCSRFToken` 是否非空作为短路条件，调用后端接口后用 `getCSRFToken()`（当时仍有缓存短路）赋值。

**修改后**: 先尝试从 cookie 读（`getCSRFToken()` 已无缓存），有则直接用；无则调后端接口，调用后从 cookie 读最新值。

**评审结论**: PASS
- 逻辑正确：Django `login()` 的 `rotate_token()` 会通过 `Set-Cookie` 写入新 token，此后 `getCSRFToken()` 能读到最新值。
- 无竞态条件：整个流程是串行 async/await，无并发写问题。
- 错误处理保留完整（catch 块）。

### 2.4 `api.js` — `api.logout()` 新增方法

```js
async logout() {
  try {
    await authenticatedFetch('/api/auth/logout/', { method: 'POST' });
  } catch (e) {
    console.warn('后端登出请求失败，继续本地清理:', e.message);
  } finally {
    clearCSRFToken();
  }
},
```

**评审结论**: PASS
- `finally` 块确保即使后端请求失败，`clearCSRFToken()` 也一定执行 — 正确的错误处理模式。
- `try/catch/finally` 结构清晰，不会因网络异常中断登出流程，用户体验良好。
- `authenticatedFetch` 需要 token，若 token 已失效会抛 `'未登录或登录已过期'`，被 catch 捕获后继续清理 — 行为正确（用户本地已无效 token 时仍能完成本地登出）。

**潜在问题**: MINOR (不阻断)
- `authenticatedFetch` 在 token 缺失时抛错，`console.warn` 的错误信息可能不够直观（"后端登出请求失败"包含网络错误和认证错误两种情况，合并处理可接受）。

### 2.5 `Layout.vue` — `handleLogout` 修复

**修改前**: 同步函数，不调用后端，不清除 CSRF 状态。

**修改后**:
```js
const handleLogout = async () => {
  await api.logout()           // 1. 后端 + CSRF 缓存清除
  localStorage.removeItem(...)  // 2. 本地存储清除
  document.cookie = 'auth_token=; ...'   // 3. 认证 cookie 清除
  document.cookie = 'csrftoken=; ...'   // 4. CSRF cookie 清除（新增）
  router.push('/login')        // 5. 跳转
}
```

**评审结论**: PASS
- 操作顺序正确：先清除后端状态（logout），再清除本地状态，最后跳转。
- `csrftoken` cookie 清除：即使 `clearCSRFToken()` 已清除内存缓存，显式清除 cookie 可防止某些 SPA 框架的 cookie 复用场景（如 Service Worker 缓存）。
- `async` 改造：正确使用 `await api.logout()`，不存在未处理的 Promise。

**评审关注点**: INFO
- 若网络极慢（如内网穿透延迟），用户点击「退出登录」后需等待后端响应（通常 < 200ms）才跳转到登录页。建议 UI 层面增加 loading 状态（非本次 Bug 修复范围，可后续优化）。

---

## 3. CRITICAL Findings

**无**

---

## 4. MAJOR Findings

**无**

---

## 5. MINOR Findings

| # | 文件 | 位置 | 描述 | 建议 |
|---|------|------|------|------|
| M-01 | `Layout.vue` | `handleLogout` | 登出时无 loading 状态，后端慢响应时用户体验轻微受影响 | 后续迭代添加 loading；不影响正确性 |
| M-02 | `api.js` | `logout()` catch | console.warn 消息合并了认证失败和网络失败 | 可后续区分；当前行为正确 |

---

## 6. 安全审查

| 检查项 | 结论 |
|-------|------|
| CSRF token 不在 URL 中传输 | PASS — 仅在 `X-CSRFToken` header 中传递 |
| CSRF cookie 清除时无 Secure/HttpOnly 冲突 | PASS — `CSRF_COOKIE_HTTPONLY=False`，前端可读/清除 |
| 后端 Token 通过 `/api/auth/logout/` 正确删除 | PASS — `Token.objects.filter(user=...).delete()` |
| 登出后旧 Token 立即失效 | PASS — 后端 Token 删除后，旧 Authorization header 返回 401 |
| 无敏感信息在日志中泄露 | PASS — console.warn 仅输出错误消息，不含 token 值 |

---

## 7. 评审结论

**APPROVED** — 无 CRITICAL/MAJOR finding。MINOR 项不影响正确性，可后续迭代处理。

修复完整覆盖了 bug_analysis.md 中识别的 4 个根因（RC-1 至 RC-4）。
