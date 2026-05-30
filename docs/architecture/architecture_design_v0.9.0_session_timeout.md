# 架构设计文档

```
file_header:
  document_id: ARCH-DESIGN-v0.9.0-SESSION-TIMEOUT
  title: 会话不活动超时 — 架构设计文档
  author_agent: System Architect (PARTIAL_FLOW, 架构阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.9.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT — 待架构门控
  references:
    - docs/requirements/v0.9.0_session_timeout/requirements_spec.md (v0.2.0)
    - docs/requirements/v0.9.0_session_timeout/user_stories.md
    - FreeArkWeb/backend/freearkweb/freearkweb/settings.py
    - FreeArkWeb/backend/freearkweb/api/views.py
    - FreeArkWeb/backend/freearkweb/api/consumers.py
    - FreeArkWeb/frontend/src/utils/api.js
    - FreeArkWeb/frontend/src/router/index.js
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-30 | 初始架构设计，覆盖 OQ-001~OQ-005 决策、ADR-001~ADR-005 |

---

## 1. 背景与设计目标

本文档是 v0.9.0 迭代的架构层决策记录，对应需求文档第 5 节列出的 5 个开放问题（OQ-001~OQ-005）。设计目标如下：

1. 在 DRF 原生 Token 认证链路基础上，以最小侵入性实现 30 分钟滑动窗口超时（REQ-AUTH-001）。
2. 满足 REQ-NFR-AUTH-001：活动时间刷新须带节流，绝不每请求同步写数据库。
3. 不引入 Redis 或其他新中间件；复用现有 MySQL 数据库（仅新增一张轻量表）。
4. 前端 401 统一处理逻辑集中在 `api.js` 的 `authenticatedFetch`（REQ-AUTH-003）。
5. WebSocket 连接鉴权（`consumers.py`）在本版本维持现状，不受超时机制影响。

---

## 2. 开放问题决策（OQ-001 ~ OQ-005）

### OQ-001 — 后端超时判定方案

**决策：方案 C — 自定义 `TokenAuthentication` 子类，在 `authenticate()` 中检查活动时间戳**

**决策理由：**

| 候选方案 | 评估 | 结论 |
|---------|------|------|
| A. 自定义 Token 模型增加 `last_active_at` 字段 | 需替换 `authtoken_token` 模型，迁移成本高；DRF 的 `Token` 模型有 `OneToOne` 约束，扩展需 proxy 或替换，改动链路宽 | 不选 |
| B. djangorestframework-simplejwt | 引入新依赖、JWT 机制与现有链路完全不同、前端须改存储/刷新逻辑；迁移成本最高 | 不选 |
| C. 自定义 `TokenAuthentication` 子类 | **复用现有 DRF Token 链路**；只在 `authenticate()` 末尾追加时效检查；对现有视图零侵入；通过 `settings.py` 替换 `DEFAULT_AUTHENTICATION_CLASSES` 即可生效 | **选定** |
| D. Django Session 框架 `SESSION_COOKIE_AGE` | 当前前端主路径使用 `Authorization: Token` header，不依赖 session；切换需前端改造；与 WebSocket token 鉴权不兼容 | 不选 |

**实现要点：**
- 新建 `api/authentication.py`，类 `SlidingWindowTokenAuthentication(TokenAuthentication)`。
- 重写 `authenticate_credentials(key)` 方法：调用 `super()` 验证 token 存在性，再查 `TokenActivity` 表（见 OQ-002）判断是否超时，超时抛出 `AuthenticationFailed("会话已超时，请重新登录")`。
- `settings.py` 的 `REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` 中将 `rest_framework.authentication.TokenAuthentication` 替换为 `api.authentication.SlidingWindowTokenAuthentication`。

---

### OQ-002 — "活动"时间戳的存储介质

**决策：独立数据库表 `api_token_activity` + 进程内节流（5 分钟写一次）**

**决策理由（满足 REQ-NFR-AUTH-001）：**

| 候选方案 | 对 DB 写压力 | 可靠性 | 与环境适配 | 结论 |
|---------|------------|--------|-----------|------|
| 每请求同步写 DB | 极高（禁止，REQ-NFR-AUTH-001 明确排除） | 高 | N/A | 不选 |
| 纯 LocMemCache | 无 DB 写压力 | 低（worker 重启全丢，超时保护失效） | 单 worker 可用 | 不选（可靠性不足） |
| DB + 进程内节流（本方案） | 低（每用户每 5 分钟最多 1 次 UPDATE） | 高（持久化）；worker 重启后缓存重建，保守判定为超时 | 单 worker 完全适配 | **选定** |
| Redis 缓存 | 低 | 高 | 需新引入 Redis，违反 C-04 约束（不强制排除但需确认） | 不选（本版本避免引入新组件） |

**实现方案（DB + 节流）：**

1. 新建 Django 模型 `TokenActivity`（表名 `api_token_activity`）：
   ```
   token (OneToOneField → authtoken_token, primary_key)
   last_active_at (DateTimeField)
   ```
2. 进程内节流缓存：在 `authentication.py` 模块级别维护一个 `dict`，键为 token key，值为上次写入 DB 的时间戳。
   - 认证成功时，先用缓存中的时间判断超时。
   - 若未超时，检查"距上次 DB 写入是否超过 `ACTIVITY_THROTTLE_SECONDS`（默认 300 秒 / 5 分钟）"，是则更新 DB 并刷新缓存；否则只刷新内存值。
3. `ACTIVITY_THROTTLE_SECONDS` 作为 `settings.py` 的命名常量，可通过环境变量覆盖。
4. **Worker 重启后缓存清空的降级行为**：重启后首次请求读 DB 中的 `last_active_at`，若距当前时间超过 30 分钟则判定超时（保守，满足 AC-NFR-001-3）；若在窗口内则重建缓存并正常放行。这意味着节流丢失的时间窗口最大为 `ACTIVITY_THROTTLE_SECONDS`，即最多提前 5 分钟超时，属于可接受的安全偏差。
5. 写入时序（在节流通过时）：使用 `TokenActivity.objects.update_or_create(token=token_obj, defaults={'last_active_at': now})` 单条 upsert，避免 SELECT+UPDATE 两次查询。

**数据库写入量估算：**
- 生产场景：假设同时在线 2~5 名用户，每人每 5 分钟最多 1 次 UPDATE → 每小时最多 60 次 UPDATE（远低于 device_param_history 的写入量）。

---

### OQ-003 — 前端是否需要主动续期心跳

**决策：纯被动方案（等待 401），不实现前端心跳**

**决策理由：**

- FreeArk 是内部管理工具，不存在"用户长时间阅读但不操作"的典型场景（大屏展示由独立的屏侧心跳机制维持，非本 Web 管理端）。
- 主动心跳增加无效请求量，与 REQ-NFR-AUTH-001 的减少 DB 写压力方向冲突。
- 业务场景分析：管理员在 Web 端的核心操作（查询报表、查看状态、修改配置）均伴随 API 调用；真正"填写表单但超时"的场景仅在 DeviceSettings、CreateUser 等少数视图，接受度在 OQ-005 中单独决策。
- 30 分钟阈值提供了充足的容忍窗口。

**OQ-005 关联决策（"当前操作保护"）：本版本不实现 `next` 参数回跳或表单保存提示。** 理由：
  - FreeArk 的设备设置、创建用户等操作是管理台低频操作，不是高风险数据录入场景。
  - 实现 beforeunload 拦截或 `?next=` 回跳会引入较多前端状态管理复杂度，与"前端不引入全局 store"的约束（C-05）存在张力。
  - 超时场景下直接跳转 /login，用户重新登录后可重新操作；接受此用户体验折衷。
  - 若后续版本有需求，可单独立项迭代。

---

### OQ-004 — last_login 更新路径

**决策：保留现有 `login(request, user)` 调用路径，依赖 `user_logged_in` 信号自动更新 `last_login`**

**决策理由：**

- `user_login` 视图（`views.py:87`）已调用 `login(request, user)`，Django 内置的 `user_logged_in` 信号处理器 `update_last_login` 会自动将 `last_login` 设置为当前时间。
- 本方案（方案 C：自定义 `TokenAuthentication` 子类）不替换 `login()` 调用，因此无需额外代码改动即可满足 REQ-AUTH-002。
- 验证路径：`user_login` → `login(request, user)` → 触发 `user_logged_in` → `update_last_login(sender, user, request)` → `user.last_login = now()` → `user.save(update_fields=['last_login'])`。
- 唯一需要确认的是 `settings.py` 中 `USE_TZ = False`，这意味着 Django 不使用 UTC 时区感知 datetime，`last_login` 存储的是服务器本地时间（`Asia/Shanghai`），与 AC-002-4 一致，无需修正。

---

### OQ-005 — 前端跳转时的"当前操作保护"

**决策：本版本不实现，直接跳转（见 OQ-003 中的说明）**

---

## 3. 架构决策记录（ADR）

### ADR-v090-001：使用自定义 `SlidingWindowTokenAuthentication` 子类

- **状态**：已批准
- **背景**：需要在 DRF Token 认证链路上叠加滑动窗口超时，不替换现有 token 机制。
- **决策**：新建 `api/authentication.py`，继承 `TokenAuthentication`，重写 `authenticate_credentials`。
- **影响**：`settings.py` 中 `DEFAULT_AUTHENTICATION_CLASSES` 一行改动；现有所有视图的认证行为不变（超时前）；超时后返回标准 DRF 401 响应。
- **替代方案**：simplejwt（迁移成本过高，排除）。
- **回滚方案**：将 `settings.py` 中的 `SlidingWindowTokenAuthentication` 改回 `TokenAuthentication` 即可完全回滚，零数据迁移风险。

---

### ADR-v090-002：新建 `api_token_activity` 表存储活动时间戳

- **状态**：已批准
- **背景**：DRF 原生 `authtoken_token` 表只有 `created` 字段，无法记录最后活动时间；不扩展该表（避免影响 DRF 内部机制）。
- **决策**：新建独立模型 `TokenActivity`，与 `Token` 建立 `OneToOneField` 关系；`last_active_at` 字段加索引。
- **影响**：需要一次 Django migration；表结构极轻量（每个活跃 token 一行，2 列）。
- **替代方案**：存 LocMemCache（可靠性不足）；存 Redis（引入新组件）；扩展 Token 模型（改动 DRF 内部表，风险高）。

---

### ADR-v090-003：进程内节流字典（Throttle Dict）

- **状态**：已批准
- **背景**：满足 REQ-NFR-AUTH-001，必须避免每请求写 DB。
- **决策**：在 `authentication.py` 模块级别维护 `_activity_cache: dict[str, datetime]`，在认证类实例间共享（单进程模式下安全）。节流阈值 `ACTIVITY_THROTTLE_SECONDS = 300`（5 分钟，可配置）。
- **多 worker 限制**：当前生产部署为 `--workers 1`（`CHANNEL_LAYERS` 使用 `InMemoryChannelLayer`，已明确单 worker 约束），本方案在此约束下完全适配。若未来扩展为多 worker，需将节流层迁移至 Redis/数据库侧，但本版本无此需求。
- **影响**：`_activity_cache` 是进程内状态，worker 重启后清空；降级行为为从 DB 重新读取（保守判定），安全。

---

### ADR-v090-004：`authenticatedFetch` 中统一拦截 401

- **状态**：已批准
- **背景**：`api.js` 当前在 401 时只抛出错误冒泡，前端各视图处理不一致。
- **决策**：在 `authenticatedFetch` 函数内，response 返回后检查 `response.status === 401`；若是，则执行以下操作并抛出特定错误：
  1. 清除 `localStorage.userToken`。
  2. 清除 cookie 中的 `auth_token`（通过 `document.cookie` 写入过期值）。
  3. 调用 `clearCSRFToken()`。
  4. 使用 Element Plus `ElMessage.warning` 展示"会话已过期，请重新登录"。
  5. 检查当前路由是否已是 `/login`；若不是，调用 `router.replace({ name: 'Login' })`。
- **`router` 引入方式**：在 `api.js` 中通过 `import router from '../router/index.js'` 引入（Vue 3 router 实例可在组合式 API 外直接导入）。
- **循环重定向防护**：在执行跳转前检查 `router.currentRoute.value.name === 'Login'`，若已在登录页则跳过跳转。
- **`api.get`/`api.post` 等方法**：保留原有的 401 `throw` 路径，但 `authenticatedFetch` 层已在 throw 前执行清理和跳转；各调用方捕获到的 error 为统一的 `SessionExpiredError`（或直接使用现有 Error 类型），不再需要各自处理 401 跳转。
- **影响**：`api.js` 修改约 20 行；无需修改任何业务视图组件；`router/index.js` 路由守卫逻辑不变。

---

### ADR-v090-005：WebSocket 连接（`consumers.py`）本版本不纳入超时机制

- **状态**：已批准
- **背景**：`ChatConsumer.connect()` 通过 `_get_user_by_token(token_key)` 查询 `Token.objects.get(key=token_key)` 做鉴权；一旦连接建立，后续 receive() 不再重新验证 token。
- **决策**：本版本 WebSocket 连接建立时不检查 `TokenActivity`（超时状态）；已建立的 WS 连接不因 HTTP API 侧的 token 超时而中断。
- **理由**：
  1. WS 连接是长连接，用户在聊天时持续有操作，不符合"30 分钟无活动"的语义。
  2. 修改 `consumers.py` 的鉴权链路会引入 `sync_to_async` 包装的 `TokenActivity` 查询，增加连接建立延迟。
  3. WS 连接的使用场景（智能助手聊天）是主动操作，超时风险极低。
- **后续版本可考虑**：WS `connect()` 时检查 `TokenActivity` 状态；或在 WS 连接期间定期从前端发送心跳消息以刷新 HTTP 侧的 `last_active_at`。
- **影响**：`consumers.py` 本版本零改动。

---

## 4. 整体数据流设计

### 4.1 正常 API 请求（未超时）

```
前端 authenticatedFetch
    → HTTP 请求 + Authorization: Token <key>
    → DRF 认证层：SlidingWindowTokenAuthentication.authenticate_credentials(key)
        ① Token.objects.get(key=key)   — 验证 token 存在
        ② TokenActivity.get(token=token_obj)   — 读取 last_active_at
        ③ now - last_active_at < SESSION_TIMEOUT_SECONDS(1800)?
              是 → 认证通过，进入节流判断
                  now - _activity_cache[key] > ACTIVITY_THROTTLE_SECONDS(300)?
                      是 → UPDATE api_token_activity SET last_active_at=now WHERE token_id=...
                           更新 _activity_cache[key] = now
                      否 → 仅更新 _activity_cache[key] = now（不写 DB）
              否 → raise AuthenticationFailed("会话已超时")
    → 视图处理 → 返回 2xx
前端 authenticatedFetch → 正常处理响应
```

### 4.2 超时 API 请求

```
前端 authenticatedFetch
    → HTTP 请求 + Authorization: Token <key>
    → SlidingWindowTokenAuthentication: now - last_active_at >= 1800s
    → raise AuthenticationFailed → DRF 返回 HTTP 401
前端 authenticatedFetch 检测到 status === 401
    → clearLocalStorage('userToken')
    → clearCookie('auth_token')
    → clearCSRFToken()
    → ElMessage.warning('会话已过期，请重新登录')
    → router.replace({ name: 'Login' })
```

### 4.3 登录流程（REQ-AUTH-002）

```
POST /api/auth/login/
    → user_login(request)
        → UserLoginSerializer.is_valid() → authenticate(username, password)
        → login(request, user)   ← Django 内置，触发 user_logged_in 信号
            → update_last_login(sender, user, request)
                → user.last_login = now()
                → user.save(update_fields=['last_login'])
        → Token.objects.get_or_create(user=user)   ← 沿用，token key 不变
        → TokenActivity.objects.update_or_create(
              token=token_obj,
              defaults={'last_active_at': now()}
          )   ← 新增：登录时初始化/重置活动时间戳，无节流
    → 返回 {success: true, token: key, user: {...}}
```

注意：登录时强制写 `TokenActivity`（绕过节流），确保新登录的 token 立即有有效的活动时间戳。

### 4.4 登出流程（无变更）

```
POST /api/auth/logout/
    → user_logout(request)
        → Token.objects.filter(user=request.user).delete()   ← 已有逻辑
        → TokenActivity 通过 CASCADE 自动删除（外键约束）
        → logout(request)
    → 返回 200
前端 api.logout()
    → (已有) clearCSRFToken()
    → (新增) clearLocalStorage('userToken')   ← api.logout() 调用方原本已做，核查后确认
```

---

## 5. 超时阈值配置设计

在 `settings.py` 中增加以下命名常量（满足 AC-001-6 和 AC-NFR-001-2）：

```python
# REQ-AUTH-001: 会话不活动超时阈值（秒），默认 30 分钟
SESSION_INACTIVITY_TIMEOUT = int(os.environ.get('SESSION_INACTIVITY_TIMEOUT', 1800))

# REQ-NFR-AUTH-001: 活动时间写入 DB 的节流阈值（秒），默认 5 分钟
ACTIVITY_THROTTLE_SECONDS = int(os.environ.get('ACTIVITY_THROTTLE_SECONDS', 300))
```

- `SESSION_INACTIVITY_TIMEOUT` 必须 > `ACTIVITY_THROTTLE_SECONDS`（否则节流写入的时间粒度会导致误判超时）。当前比例：1800 / 300 = 6，裕量充足。
- 两个值均可通过环境变量覆盖，无需修改代码。

---

## 6. 数据库变更说明

### 6.1 新增表：`api_token_activity`

| 列名 | 类型 | 说明 |
|------|------|------|
| token_id | varchar(40) PK | FK → authtoken_token.key（OneToOne），级联删除 |
| last_active_at | datetime(6) NOT NULL | 最后有效活动时间，带索引 |

Django Migration 文件：`api/migrations/0XXX_add_token_activity.py`（开发阶段生成）。

### 6.2 无其他表结构变更

- `authtoken_token` 表不变。
- `api_customuser` 表不变（`last_login` 更新依赖现有信号机制）。

---

## 7. 改动范围汇总

| 文件/路径 | 变更类型 | 内容摘要 |
|---------|---------|---------|
| `api/authentication.py` | 新建 | `SlidingWindowTokenAuthentication`；`_activity_cache` 模块级 dict；节流写 DB 逻辑 |
| `api/models.py` | 新增模型 | `TokenActivity`（2 字段） |
| `api/migrations/0XXX_add_token_activity.py` | 新建 | 对应 migration 文件 |
| `api/views.py` | 微改 | `user_login` 中追加 `TokenActivity.objects.update_or_create(...)` 一行 |
| `freearkweb/settings.py` | 修改 | `DEFAULT_AUTHENTICATION_CLASSES` 替换；新增 `SESSION_INACTIVITY_TIMEOUT`、`ACTIVITY_THROTTLE_SECONDS` |
| `frontend/src/utils/api.js` | 修改 | `authenticatedFetch` 中拦截 401，执行清理 + 跳转逻辑 |
| `api/consumers.py` | **不变** | WebSocket 鉴权不受本次变更影响 |
| `frontend/src/router/index.js` | **不变** | 路由守卫逻辑不变 |

---

## 8. 风险与缓解措施

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| Worker 重启导致 `_activity_cache` 清空，用户被提前超时 | 低（Pi 稳定运行，重启频率低） | 低（最多提前 5 分钟超时，用户重登即可） | 接受；属于安全偏差（保守判定）；AC-NFR-001-3 明确允许 |
| `TokenActivity` 查询成为每次请求的额外 DB 读取 | 中（每个认证请求均需读一次） | 低（单行 PK 查找，极快）| 加 `select_related` 或利用 ORM 缓存；可在后续优化中考虑将 `TokenActivity` 嵌入认证 token 查询（`Token.objects.select_related('tokenactivity').get(key=key)`） |
| `api.js` 中 `router` 循环引用（api.js import router，router 中 import api） | 中 | 高（循环依赖导致 undefined） | 架构上明确：`router/index.js` **不** import `api.js`（当前已是如此）；`api.js` 单向依赖 `router`，无循环 |
| 登录接口自身返回 401 触发跳转循环 | 低（登录接口用 `AllowAny`，不经过认证类） | 高 | 登录接口不带 `Authorization` header，`authenticatedFetch` 首行 `if (!token) throw ...`，不会触发 401 拦截逻辑；AC-003-4 的防护是额外兜底 |
