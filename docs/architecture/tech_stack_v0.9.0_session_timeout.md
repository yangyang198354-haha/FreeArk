# 技术栈说明文档

```
file_header:
  document_id: TECH-STACK-v0.9.0-SESSION-TIMEOUT
  title: 会话不活动超时 — 技术栈说明
  author_agent: System Architect (PARTIAL_FLOW, 架构阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.9.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT — 待架构门控
  references:
    - docs/architecture/architecture_design_v0.9.0_session_timeout.md
    - docs/architecture/module_design_v0.9.0_session_timeout.md
```

---

## 1. 本次迭代技术选型原则

v0.9.0 遵循"最小侵入、零新依赖"原则：所有新增能力均基于已有技术栈实现，不引入任何新的 Python 包或 npm 包。

---

## 2. 后端技术栈

### 2.1 认证层

| 组件 | 版本/来源 | 使用方式 | 本次变更 |
|------|---------|---------|---------|
| djangorestframework `TokenAuthentication` | 已安装（DRF） | 作为父类，被 `SlidingWindowTokenAuthentication` 继承 | 不直接使用，改为子类 |
| `SlidingWindowTokenAuthentication` | 新建，`api/authentication.py` | `DEFAULT_AUTHENTICATION_CLASSES` 第一项 | **新增** |
| Django `AuthenticationFailed` | DRF 内置 | 在认证类中抛出超时错误，DRF 框架转换为 HTTP 401 | 沿用 |
| Django `request.user` / `request.auth` | DRF 内置 | 认证后视图获取用户和 token 对象 | 不变 |

### 2.2 数据库层

| 组件 | 版本/来源 | 使用方式 | 本次变更 |
|------|---------|---------|---------|
| Django ORM | 已有 | `TokenActivity` 模型的 CRUD 操作 | 新增模型 |
| MySQL 8.x（生产） | 192.168.31.98:3306 | `api_token_activity` 表存储活动时间戳 | 新增一张表（两列） |
| SQLite（测试） | Django 内置 | 单元测试自动使用（settings.py `_RUNNING_TESTS` 逻辑已有） | 兼容，无额外配置 |
| `update_or_create` / `filter().update()` | Django ORM 内置 | upsert 操作（登录初始化）和节流更新 | 沿用 API |

### 2.3 进程内缓存（节流层）

| 组件 | 版本/来源 | 使用方式 | 本次变更 |
|------|---------|---------|---------|
| Python `dict`（模块级） | Python 内置 | `_activity_cache: dict[str, datetime]`，存储"上次 DB 写入时间" | **新增（无第三方依赖）** |

**说明**：未使用 Django `LocMemCache`。原因：`LocMemCache` 有序列化开销和 LRU 驱逐机制，对于 token-key → datetime 这类极轻量的映射，直接使用 Python dict 更高效且可控。在单 worker（`--workers 1`）场景下无线程安全问题（Uvicorn 单 worker 的 ASGI 事件循环是单线程处理同步 Django 视图；Python GIL 在 dict 读写上保证原子性）。

### 2.4 信号机制（REQ-AUTH-002）

| 组件 | 版本/来源 | 使用方式 | 本次变更 |
|------|---------|---------|---------|
| Django `user_logged_in` 信号 | Django 内置 | `login(request, user)` 触发信号 → `update_last_login` 更新 `last_login` | **不变（依赖现有机制）** |

---

## 3. 前端技术栈

### 3.1 API 层

| 组件 | 版本/来源 | 使用方式 | 本次变更 |
|------|---------|---------|---------|
| `frontend/src/utils/api.js` | 已有 | `authenticatedFetch` 新增 401 拦截逻辑 | **微改** |
| Vue Router（`vue-router` v4） | 已安装 | `router.replace({ name: 'Login' })` 跳转；`router.currentRoute.value.name` 读取当前路由 | 新增使用方式（api.js 中 import router） |
| Element Plus `ElMessage` | 已安装 | `ElMessage.warning('会话已过期，请重新登录')` | 新增使用点（动态 import） |
| `localStorage` | 浏览器内置 | `localStorage.removeItem('userToken')` | 沿用（已有 `setItem`，本次新增 `removeItem` 调用点） |
| `document.cookie` | 浏览器内置 | 清除 `auth_token` cookie（通过写入过期值） | 新增用法 |

### 3.2 路由层

| 组件 | 版本/来源 | 使用方式 | 本次变更 |
|------|---------|---------|---------|
| `frontend/src/router/index.js` | 已有 | 路由守卫 `beforeEach` 检查 `localStorage.userToken` | **不变** |

---

## 4. 不引入的技术（排除清单）

| 技术 | 排除原因 |
|------|---------|
| Redis | 生产环境已有 `InMemoryChannelLayer`（单 worker 约束），引入 Redis 增加运维复杂度；本版本的节流需求通过进程内 dict 满足 |
| `djangorestframework-simplejwt` | 迁移成本过高，需替换前端 token 存储和刷新逻辑；本次需求可在 DRF 原生 Token 框架内满足 |
| `django-axes` / 其他第三方认证库 | 功能过重，超出本版本需求范围 |
| Vue 全局 store（Pinia/Vuex） | 明确约束（C-05）不引入 |
| 前端定时器心跳（`setInterval`） | OQ-003 决策排除 |
| `djangorestframework-expiring-tokens` | 维护状态不活跃，且其实现为绝对过期（非滑动窗口），不满足需求 |

---

## 5. 版本兼容性确认

| 技术 | 当前版本（推断） | 本次用法 | 兼容性 |
|------|--------------|---------|--------|
| Django | 5.2.7（settings.py 注释） | `OneToOneField`、`update_or_create`、信号机制 | 完全兼容 |
| DRF（djangorestframework） | 与 Django 5.2 兼容的版本 | 继承 `TokenAuthentication`，重写 `authenticate_credentials` | 完全兼容（该方法签名自 DRF 3.x 未变） |
| Vue 3 + vue-router v4 | 已有（createRouter + createWebHistory） | 在非组件文件中 import router 实例 | 完全支持（Vue 3 router 是普通 JS 模块，可在任何地方 import） |
| Element Plus | 已有（项目中已使用 ElMessage） | 动态 import ElMessage | 完全兼容 |
| MySQL 8.x | 192.168.31.98:3306 | 新增 `api_token_activity` 表（标准 InnoDB） | 完全兼容 |

---

## 6. 新增文件/模块清单

| 文件路径 | 说明 | 新建/修改 |
|---------|------|---------|
| `FreeArkWeb/backend/freearkweb/api/authentication.py` | `SlidingWindowTokenAuthentication` 认证类 | 新建 |
| `FreeArkWeb/backend/freearkweb/api/migrations/0XXX_add_token_activity.py` | `TokenActivity` 模型 migration | 新建（`makemigrations` 自动生成） |
| `FreeArkWeb/backend/freearkweb/api/models.py` | 追加 `TokenActivity` class | 修改（追加） |
| `FreeArkWeb/backend/freearkweb/api/views.py` | `user_login` 追加 `TokenActivity.update_or_create`；`user_register` 同步追加 | 修改（追加约 5 行） |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | `DEFAULT_AUTHENTICATION_CLASSES` 替换；新增 2 个配置常量 | 修改（约 6 行） |
| `FreeArkWeb/frontend/src/utils/api.js` | `authenticatedFetch` 新增 401 拦截；`api.logout()` 补全清理；新增 `clearAuthCookie` | 修改（约 25 行） |
