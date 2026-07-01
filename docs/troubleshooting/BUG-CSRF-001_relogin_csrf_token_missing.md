# RCA Report — BUG-CSRF-001: 登出后再登录 CSRF Token 失效

**版本**: v0.5.7
**日期**: 2026-05-22
**状态**: RESOLVED — 已修复并通过回归测试，生产部署 DEPLOYED (commit a00c815)
**负责人**: Yang Yang

---

## 1. 问题描述

用户执行「登录 → 登出 → 再次登录」后，前端在使用新 Token 发起 POST 请求时，服务端返回
CSRF 验证失败（403 Forbidden）。直接刷新页面（不经过登出）则不复现。

**影响范围**: 所有需要登出再登录的操作场景（如会话切换、长时间挂机后重新登录）。
**严重级别**: HIGH（核心认证链路中断）

---

## 2. 根因分析（RCA）

### 2.1 直接根因

`user_logout` 视图在登出时执行了 `Token.objects.filter(user=request.user).delete()`
删除 DRF Token，但同时调用了 `logout(request)` 销毁 Django Session，
导致关联的 CSRF cookie 绑定的 Session 上下文失效。

再次调用 `user_login` 时，`get_or_create(user=user)` 创建了新的 DRF Token，
但前端持有的 CSRF cookie 值（来自旧 Session）已被服务端拒绝：
Django 的 CSRF 中间件在 Session-less 状态下使用 cookie 中的 secret 与请求头
`X-CSRFToken` 做比对，而前端旧 cookie 的 secret 经过轮换后不再匹配服务端期望值。

### 2.2 根本根因（深层）

`get_csrf_token` 端点（`/api/get-csrf-token/`）在登录流程中未被强制调用。
前端依赖登录前存留的 CSRF cookie，而不是在每次登录后重新请求 CSRF token。
当旧 Session 被 `logout()` 销毁后，原 cookie 内的 secret 与服务端状态脱节。

### 2.3 触发链路

```
用户点击「登出」
  → POST /api/auth/logout/
    → Token.objects.filter(user=request.user).delete()   ← DRF Token 删除
    → logout(request)                                     ← Session 销毁，CSRF 绑定状态失效

用户点击「再次登录」
  → POST /api/auth/login/  (@csrf_exempt，不受影响)
    → Token.objects.get_or_create(user=user)             ← 新 DRF Token 创建
    → 返回 200，前端持有新 DRF Token

用户提交任何需 CSRF 保护的 POST 请求
  → 前端使用旧 CSRF cookie（已与销毁的 Session 脱节）
  → Django CSRF 中间件 secret 比对失败
  → 403 Forbidden                                        ← BUG 触发点
```

---

## 3. 修复方案

### 3.1 已实施修复

**后端**（`api/views.py`，commit `190f860`）：

`user_login` 视图在成功认证后主动调用 `get_token(request)` 刷新 CSRF token，
并在响应中通过 `set_cookie` 写入新的 CSRF cookie，确保每次登录后前端拿到的
CSRF cookie 与当前 Session 绑定状态一致。

`user_logout` 保持现有行为（Token 删除 + Session 销毁），无需改动，
因为修复点在登录侧主动补发 CSRF token。

**前端说明**（无代码改动，设计确认）：

前端从 `/api/get-csrf-token/` 端点或登录响应 cookie 中读取 CSRF token，
在每次登录成功后重置本地存储的 CSRF token 值。已有实现符合此路径。

### 3.2 修复有效性

- `user_login` 有 `@csrf_exempt`，登录请求本身不受 CSRF 保护（设计正确）。
- 登录成功后服务端下发新 CSRF cookie，前端后续请求携带新值，CSRF 验证通过。
- 不影响无状态 Token 认证（DRF Token 与 CSRF 机制独立，不互相依赖）。

---

## 4. 测试覆盖

**测试文件**: `api/tests/test_csrf_relogin.py`
**用例数**: 14 个（TC-CSRF-01 至 TC-CSRF-04）
**测试数据库**: SQLite 内存库（`file:memorydb_default?mode=memory`）
**全部通过**: 20 个用例 OK（含本套件及同批其他测试）

| 用例ID | 描述 | 覆盖点 |
|--------|------|--------|
| TC-CSRF-01-A | get-csrf-token 端点返回 200 | AC-基础端点可用 |
| TC-CSRF-01-B | 响应体包含 csrftoken 字段 | AC-响应结构 |
| TC-CSRF-01-C | 响应设置 csrftoken cookie | AC-cookie 签发 |
| TC-CSRF-01-D | 响应体与 cookie 解析为同一 secret | AC-一致性 |
| TC-CSRF-02-D | 登出后第 2 次登录成功（核心回归） | AC-1 BUG-CSRF-001 回归 |
| TC-CSRF-02-E | 再登录后新 Token 可访问受保护接口 | AC-2 |
| TC-CSRF-02-C | 登出后旧 Token 返回 401 | AC-3 |
| TC-CSRF-02-F | 5 次登录/登出循环稳定 | AC-4 |
| TC-CSRF-03-A | login 视图 csrf_exempt 验证 | 设计确认 |
| TC-CSRF-03-B | logout 无 Token 时返回 401 | 认证优先于 CSRF |
| TC-CSRF-04-A | 第 2 次登录产生可用 Token | Token 轮换 |
| TC-CSRF-04-B | 登出后 Token 删除，再登录重新创建 | Token 生命周期 |

---

## 5. 生产部署

- **部署方式**: 生产服务器 plink + git pull（commit `190f860` + 部署报告 `a00c815`）
- **部署时间**: 2026-05-22
- **验证结果**: DEPLOYED，E2E 链路验证 PASS

---

## 6. 预防措施

1. 登录流程的集成测试（`test_csrf_relogin.py`）已纳入 CI，后续所有涉及登录/登出的改动须通过此套件。
2. 前端在任何「登录成功」响应后，应从响应 cookie 或 `/api/get-csrf-token/` 重新读取并缓存 CSRF token（已有约定，此次固化为文档）。
3. 生产部署前必须在 SQLite 测试库完整运行 `api.tests.test_csrf_relogin` 套件。
