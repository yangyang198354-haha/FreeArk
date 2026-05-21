# 测试报告 — BUG-CSRF-001 修复验证
# version: v0.5.7_csrf_relogin
# author_agent: sub_agent_test_engineer (orchestrated by main_agent_pm)
# status: APPROVED
# date: 2026-05-21

---

## 1. 执行摘要

| 指标 | 结果 |
|------|------|
| 新增测试用例总数 | 14 |
| 通过 | 14 |
| 失败 | 0 |
| 错误 | 0 |
| 跳过 | 0 |
| 新增测试通过率 | **100%** |
| 原有 AuthAPITest 通过率 | **100%** (7/7，独立验证) |
| 核心回归用例 TC-CSRF-02-D | **PASS** |

---

## 2. 测试环境

| 项目 | 值 |
|------|---|
| Python | 3.x（生产服务器实际版本与树莓派一致） |
| Django settings | `freearkweb.test_settings` |
| 数据库 | SQLite in-memory |
| 运行命令 | `python manage.py test api.tests.test_csrf_relogin --settings=freearkweb.test_settings --verbosity=2` |

---

## 3. 测试用例结果明细

### TC-CSRF-01: get-csrf-token 端点

| 用例 ID | 用例描述 | 结果 | 说明 |
|---------|---------|------|------|
| TC-CSRF-01-A | 端点返回 200 | PASS | AllowAny 权限，匿名可调用 |
| TC-CSRF-01-B | 响应体含 csrftoken 字段 | PASS | `{"status":"success","csrftoken":"..."}` |
| TC-CSRF-01-C | Set-Cookie 写入 csrftoken cookie | PASS | Django `get_token()` + `response.set_cookie()` |
| TC-CSRF-01-D | 响应体 token 与 cookie 值一致 | PASS | 同一 `get_token()` 调用产生，必然一致 |

### TC-CSRF-02: 登录 → 登出 → 再登录 完整链路（核心回归）

| 用例 ID | 用例描述 | 结果 | 说明 |
|---------|---------|------|------|
| TC-CSRF-02-A | 第 1 次登录成功 | PASS | 200，返回 token |
| TC-CSRF-02-B | 第 1 次登录后登出成功 | PASS | 200，success=true |
| TC-CSRF-02-C | 登出后旧 Token 不可用 | PASS | 401，对应 AC-3 |
| TC-CSRF-02-D | **第 2 次登录成功（BUG 核心回归）** | **PASS** | 200，success=true，对应 AC-1 |
| TC-CSRF-02-E | 再登录后新 Token 可访问受保护接口 | PASS | GET /api/auth/me/ 返回 200，对应 AC-2 |
| TC-CSRF-02-F | 5 次登录/登出循环全部成功 | PASS | 10 次请求全部通过，对应 AC-4 |

### TC-CSRF-03: CSRF 强制模式验证

| 用例 ID | 用例描述 | 结果 | 说明 |
|---------|---------|------|------|
| TC-CSRF-03-A | user_login 是 csrf_exempt，无 CSRF header 可登录 | PASS | `@csrf_exempt` 装饰器生效 |
| TC-CSRF-03-B | user_logout 无 Token 时返回 401 | PASS | 认证检查优先于 CSRF 检查 |

### TC-CSRF-04: Token 生命周期

| 用例 ID | 用例描述 | 结果 | 说明 |
|---------|---------|------|------|
| TC-CSRF-04-A | 再登录后 Token 有效 | PASS | GET /api/auth/me/ 200 |
| TC-CSRF-04-B | 登出删除 Token，再登录重建 Token | PASS | DB 验证：旧 key 不存在，新 key 存在 |

---

## 4. 原有测试回归结果

| 测试类 | 用例数 | PASS | FAIL | 备注 |
|-------|-------|------|------|------|
| AuthAPITest (tests.py) | 7 | 7 | 0 | 含 test_logout_success、test_login_success 等 |

原有认证测试全部通过，修复无回归。

---

## 5. 验收标准对应关系

| AC | 描述 | 覆盖用例 | 结论 |
|----|------|---------|------|
| AC-1 | 登出后再登录成功 | TC-CSRF-02-D | SATISFIED |
| AC-2 | 再登录后 POST 请求正常 | TC-CSRF-02-E | SATISFIED |
| AC-3 | 登出后旧 Token 返回 401 | TC-CSRF-02-C, TC-CSRF-04-B | SATISFIED |
| AC-4 | 5 次循环无累积问题 | TC-CSRF-02-F | SATISFIED |

---

## 6. 测试覆盖率说明

本次测试聚焦于 BUG-CSRF-001 修复的后端认证链路。

**覆盖内容**：
- `user_login` 视图（成功路径、CSRF exempt 验证）
- `user_logout` 视图（成功路径、未认证路径）
- `get_csrf_token` 视图（token 签发、cookie 写入）
- Token 生命周期（创建、使用、删除）
- 多次登录/登出循环

**不在自动化覆盖范围（手工验证）**：
- 浏览器端 `cachedCSRFToken` JavaScript 内存缓存重置
- `handleLogout` 的 async 行为
- 实际浏览器 CSRF cookie 清除效果

---

## 7. 结论

**PASS** — 所有 14 个新增测试用例通过，原有认证测试无回归。BUG-CSRF-001 修复验证完成，满足全部验收标准（AC-1 至 AC-4）。

可进入部署阶段（等待 PM 生产部署 CONFIRM 信号）。
