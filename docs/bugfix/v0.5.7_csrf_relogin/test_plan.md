# 测试计划 — BUG-CSRF-001 修复验证
# version: v0.5.7_csrf_relogin
# author_agent: sub_agent_test_engineer (orchestrated by main_agent_pm)
# status: APPROVED
# date: 2026-05-21

---

## 1. 测试目标

验证 BUG-CSRF-001 修复的正确性，确保：
1. 登录 → 登出 → 再登录 完整链路无 CSRF 错误。
2. 登出后旧 Token 失效。
3. 修复不引入回归（认证相关接口原有测试全部通过）。

---

## 2. 测试范围

### 2.1 新增测试（回归用例，文件：`api/tests/test_csrf_relogin.py`）

| 测试类 | 测试方法 | 用例 ID | 对应 AC |
|-------|---------|---------|---------|
| GetCSRFTokenEndpointTest | test_csrf_token_endpoint_returns_200 | TC-CSRF-01-A | - |
| GetCSRFTokenEndpointTest | test_csrf_token_endpoint_returns_token_in_body | TC-CSRF-01-B | - |
| GetCSRFTokenEndpointTest | test_csrf_token_endpoint_sets_cookie | TC-CSRF-01-C | - |
| GetCSRFTokenEndpointTest | test_csrf_token_is_consistent_between_body_and_cookie | TC-CSRF-01-D | - |
| LoginLogoutLoginFlowTest | test_first_login_succeeds | TC-CSRF-02-A | - |
| LoginLogoutLoginFlowTest | test_logout_succeeds_after_first_login | TC-CSRF-02-B | - |
| LoginLogoutLoginFlowTest | test_old_token_invalid_after_logout | TC-CSRF-02-C | AC-3 |
| LoginLogoutLoginFlowTest | test_second_login_succeeds_after_logout | TC-CSRF-02-D | AC-1 |
| LoginLogoutLoginFlowTest | test_new_token_works_after_re_login | TC-CSRF-02-E | AC-2 |
| LoginLogoutLoginFlowTest | test_repeated_login_logout_cycle_stable | TC-CSRF-02-F | AC-4 |
| CSRFEnforcedLoginLogoutTest | test_login_is_csrf_exempt | TC-CSRF-03-A | - |
| CSRFEnforcedLoginLogoutTest | test_logout_returns_401_without_token | TC-CSRF-03-B | - |
| TokenRotationAfterLoginTest | test_second_login_produces_valid_token | TC-CSRF-04-A | AC-1, AC-2 |
| TokenRotationAfterLoginTest | test_token_deleted_on_logout_then_recreated_on_login | TC-CSRF-04-B | AC-3 |

**共 14 个测试用例**

### 2.2 原有测试（回归，不修改）

| 文件 | 测试类 | 覆盖内容 |
|------|-------|---------|
| `api/tests.py` | AuthAPITest | 基础登录/登出/获取当前用户 |
| `api/tests.py` | ChangePasswordAPITest | 修改密码（POST 接口，需认证） |
| `api/tests.py` | UserManagementAPITest | 用户管理（POST 接口，需认证+权限） |

---

## 3. 测试环境

| 项目 | 配置 |
|------|------|
| 数据库 | SQLite in-memory（test_settings.py） |
| Django settings | `freearkweb.test_settings` |
| CSRF 检查 | 部分用例使用 `enforce_csrf_checks=True` 的 Client |
| 测试框架 | Django TestCase + DRF APIClient |

---

## 4. 测试执行命令

```bash
cd FreeArkWeb/backend/freearkweb

# 仅运行新增的 CSRF 回归测试
python manage.py test api.tests.test_csrf_relogin \
    --settings=freearkweb.test_settings --verbosity=2

# 运行完整测试套件（含原有测试）
python manage.py test api.tests \
    --settings=freearkweb.test_settings --verbosity=2

# 运行单一文件原有测试（向后兼容验证）
python manage.py test api.tests.test_device_settings_integration \
    --settings=freearkweb.test_settings --verbosity=2
```

---

## 5. 通过标准

| 指标 | 阈值 |
|------|------|
| 新增测试通过率 | 100%（14/14） |
| 原有 AuthAPITest 通过率 | 100% |
| 无 CRITICAL finding | 满足（code_review_report.md 已确认）|
| TC-CSRF-02-D（核心回归）| PASS |

---

## 6. 不在自动化测试范围（需手动验证）

| 项目 | 说明 |
|------|------|
| 浏览器端 `cachedCSRFToken` 内存缓存清除 | JavaScript 单元测试需要浏览器环境，本次不配置 |
| 前端 `handleLogout` async 改造 | 前端无测试框架（Vitest 未配置），手工验证 |
| 实际浏览器 CSRF cookie 清除 | 通过 DevTools 手工验证 |

---

## 7. 手工验证清单

开发/测试人员在生产部署前应完成以下手工验证：

- [ ] 浏览器打开系统，首次登录成功
- [ ] 点击「退出登录」，Network 面板确认 `/api/auth/logout/` POST 请求成功（200）
- [ ] DevTools Application > Cookies 确认 `csrftoken` 已清除
- [ ] DevTools Application > Local Storage 确认 `userToken` 已清除
- [ ] 再次输入用户名密码，点击「登录」，确认登录成功，无 CSRF 错误
- [ ] 登录后执行任意 POST 操作（如修改密码），确认无 403 CSRF 错误
- [ ] 重复上述操作 3 次，确认无累积问题
