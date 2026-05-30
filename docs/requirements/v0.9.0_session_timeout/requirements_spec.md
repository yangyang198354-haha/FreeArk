# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.9.0-SESSION-TIMEOUT
  title: 会话不活动超时与 last_login 刷新 — 需求规格说明书
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.9.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: APPROVED — 需求门控已通过；v0.9.0-r2 追加 REQ-NFR-AUTH-001
  references:
    - FreeArkWeb/backend/freearkweb/api/views.py（user_login / user_logout 视图，已阅）
    - FreeArkWeb/backend/freearkweb/freearkweb/settings.py（REST_FRAMEWORK 配置，已阅）
    - FreeArkWeb/frontend/src/utils/api.js（authenticatedFetch / getAuthToken / logout，已阅）
    - FreeArkWeb/frontend/src/router/index.js（路由守卫，已阅）
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-30 | 初始草稿，涵盖 R1 会话不活动超时（滑动窗口）和 R2 last_login 刷新两条主线需求 |
| 0.2.0 | 2026-05-30 | 用户确认后追加 REQ-NFR-AUTH-001（性能约束：禁止每请求同步写 DB，要求节流/缓存方案）；更新需求汇总表 |

---

## 1. 背景与现状分析

### 1.1 背景

FreeArk 是内网/公网双栖的住宅能耗/暖通监控平台（Django + DRF 后端，Vue 前端）。当前版本没有会话超时机制，管理员或业主登录一次后可永久保持登录状态，存在以下安全隐患：

1. 未锁屏的终端被他人操作时，无自动保护。
2. 旧 token 无限期有效，泄露风险随时间积累。
3. `last_login` 字段长期不更新，管理后台的用户活跃度信息失真。

用户明确提出以下改进需求：

- **R1**：用户登录后，若连续 30 分钟无活动，凭证失效，须重新登录。
- **R2**：用户成功登录时，`api_customuser.last_login` 刷新为本次登录时间。

### 1.2 当前认证机制（代码实证）

以下现状基于对实际代码文件的逐行阅读，作为本次需求的基线：

#### 1.2.1 后端 Token 机制

- `settings.py` 中 `REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` 配置了：
  1. `rest_framework.authentication.TokenAuthentication`（主认证方式）
  2. `rest_framework.authentication.SessionAuthentication`（辅助）
- `views.py` 的 `user_login` 视图通过 `Token.objects.get_or_create(user=user)` 签发 DRF 原生 Token。
- **DRF 原生 Token（`authtoken_token` 表）没有 `created_at` 以外的时效字段，设计上永不过期**。用户只要持有 token，无论多久不登录，token 均可继续使用。

#### 1.2.2 前端 Token 存储与路由守卫

- `api.js` 的 `getAuthToken()` 优先读 cookie 中的 `auth_token`，否则读 `localStorage.getItem('userToken')`。
- `localStorage` 在浏览器关闭后依然保留，换设备/换网络后同样有效，无任何自动清除逻辑。
- `router/index.js` 的路由守卫仅检查 `localStorage.getItem('userToken') !== null`，即"存在即通过"，不校验 token 是否真实有效（不发网络请求）。
- 当后端 API 返回 401 时，`api.js` 抛出 `Error('认证失败(401): Token 无效或已过期，请重新登录')`，但**不自动跳转到登录页**——需要各调用方自行处理，当前大多数视图并未统一处理该错误。

#### 1.2.3 last_login 的当前刷新时机

- `user_login` 视图调用了 `login(request, user)`（Django 内置函数），该函数会触发 `user_logged_in` 信号，信号处理器 `update_last_login` 会将 `user.last_login` 更新为当前时间。
- **问题**：由于 token 永不过期，用户极少再次调用登录接口；因此 `last_login` 在首次登录后就几乎不再更新，长期显示为初次登录时间。

### 1.3 目标与现状差距

| 维度 | 现状 | 目标（本版本） |
|------|------|-------------|
| Token 有效期 | 永久 | 30 分钟不活动后失效 |
| "不活动"语义 | 不适用 | 滑动窗口：每次有效 API 请求重置计时 |
| last_login 刷新 | 仅在登录接口被调用时刷新 | 每次成功登录即刷新（本版本覆盖 R2；R1 本身不再触发新登录，故 last_login 的刷新语义以登录事件为准，不扩展到每次 API 活动） |
| 前端 401 处理 | 各视图零散、不统一 | 任意 API 返回 401 时，自动清除本地凭证并跳转登录页 |

---

## 2. 需求范围

### 2.1 本版本覆盖

| 编号 | 需求名称 | 类型 |
|------|---------|------|
| REQ-AUTH-001 | 会话不活动超时（滑动窗口 30 分钟） | 新增 |
| REQ-AUTH-002 | 登录时刷新 last_login | 缺陷修复/增强 |
| REQ-AUTH-003 | 前端 401 统一处理（自动跳转登录页） | 新增（支撑 REQ-AUTH-001 的用户体验闭环） |

### 2.2 不在本版本范围内

- 多设备并发会话管理（如"踢出旧设备"）
- 记住登录状态（"30天免登录"）功能
- 基于角色的差异化超时配置（所有用户统一 30 分钟）
- 强制 HTTPS（由基础设施迭代单独处理）
- 二次验证 / MFA

---

## 3. 需求详述

### REQ-AUTH-001：会话不活动超时（滑动窗口 30 分钟）

**来源**：用户原话"用户登录三十分钟不活动需要重新登录"

**优先级**：P0（核心安全需求）

#### 3.1.1 业务规则

1. **超时阈值**：连续 30 分钟无活动。阈值值在后端配置，不硬编码在业务逻辑中。
2. **"活动"的定义**：用户发起的、经过后端认证中间件处理的有效 API 请求（即携带有效 token 且后端返回非 401 响应的请求）。纯前端操作（本地路由跳转、页面滚动）不计入"活动"。
3. **滑动窗口语义**：每次有效活动将超时计时重置为当前时间 + 30 分钟。**不是**"从登录时刻起固定 30 分钟绝对过期"。
   - 示例：用户在 10:00 登录，10:29 发起一次 API 请求（有效活动），超时截止时间重置为 11:00（而非 10:30）。
4. **超时失效**：超时发生后，该 token 在后端被判定为无效，再次请求返回 HTTP 401。
5. **前端响应**：收到 401 后，前端自动清除本地存储的 token，并将用户重定向到登录页（见 REQ-AUTH-003）。

#### 3.1.2 现状差距

DRF 原生 Token 无时效字段，需要在架构阶段选择实现方案（见第 5 节开放问题）。

#### 3.1.3 验收标准摘要（详见 user_stories.md）

- 30 分钟内有活动 → token 持续有效，访问正常。
- 30 分钟内无活动 → 后续请求返回 401，前端跳转登录页。
- 最后一次活动后再次活动（但距上次未满 30 分钟）→ 计时窗口重置，不超时。
- 超时后重新登录 → 可正常访问。

---

### REQ-AUTH-002：登录时刷新 last_login

**来源**：用户原话"登录后 last_login 要刷新一下"

**优先级**：P1（配合 R1，确保登录时序完整）

#### 3.2.1 业务规则

1. 用户通过登录接口（`POST /api/auth/login/`）提交用户名和密码，认证成功后，`api_customuser.last_login` 必须被更新为本次登录的服务器时间（UTC，与 Django 时区设置一致）。
2. `last_login` 的更新必须在 token 签发前完成（或在同一事务内），确保登录响应返回时 `last_login` 已是最新值。
3. 登录失败（用户名/密码错误）时，`last_login` 不更新。

#### 3.2.2 现状分析

当前 `user_login` 视图调用了 `login(request, user)` 函数，Django 的 `user_logged_in` 信号处理器（`update_last_login`）在信号触发时会更新 `last_login`。此机制在代码路径上**本已覆盖**本需求——但由于 token 永不过期，用户几乎不再调用登录接口，导致 `last_login` 长期不刷新的现象。

**本需求的验收重点**：在 REQ-AUTH-001 引入超时后，每次用户因超时被迫重新登录时，`last_login` 确实被刷新；同时，首次登录时 `last_login` 也被正确刷新。

**如果架构方案保留了 `login(request, user)` 调用路径**，则现有信号机制可直接满足本需求，无需额外代码改动，仅需验证。

**如果架构方案替换为纯 Token 方案（不调用 Django `login()`）**，则需要在 `user_login` 视图中显式执行 `user.last_login = now(); user.save(update_fields=['last_login'])` 或等效操作。**此决策留至架构阶段。**

#### 3.2.3 验收标准摘要

- 调用登录接口并认证成功后，数据库 `api_customuser.last_login` 字段值等于本次登录的服务器时间（允许 ±5 秒误差）。
- 登录失败时，`last_login` 不变。
- 若用户在 10:00 登录，随后因超时在 10:45 再次登录，则 `last_login` 更新为 10:45（而非停留在 10:00）。

---

### REQ-AUTH-003：前端 401 统一处理（自动跳转登录页）

**来源**：REQ-AUTH-001 的用户体验闭环需求（超时后前端必须给出可操作的提示并跳转）

**优先级**：P1（REQ-AUTH-001 的必要配套）

#### 3.3.1 业务规则

1. 当任意 API 请求收到后端返回的 HTTP 401 响应时，前端应：
   a. 清除 `localStorage` 中的 `userToken`（以及 cookie 中的 `auth_token`，若存在）。
   b. 清除 CSRF token 缓存（已有 `clearCSRFToken()` 函数）。
   c. 向用户展示简短提示（如"会话已过期，请重新登录"），可使用 Element Plus `ElMessage.warning`。
   d. 将页面跳转到 `/login` 路由，且不保留历史记录中的当前页（使用 `router.replace` 而非 `router.push`，避免用户按"后退"回到已无权限的页面）。
2. 上述处理逻辑应在 `api.js` 的 `authenticatedFetch` 封装中统一实现，不依赖各业务视图单独捕获。
3. 若当前页面已是登录页，则收到 401 时不再重复跳转（防止循环重定向）。

#### 3.3.2 现状差距

当前 `api.js` 在 401 时仅 `throw new Error(...)` 并将错误冒泡给调用方；路由守卫仅检查 `localStorage` 是否有值，不发网络请求；各业务视图对 401 的处理不统一（有的有提示，有的静默失败）。

---

---

## 3.4 REQ-NFR-AUTH-001：会话活动时间刷新不得显著增加数据库写压力

**来源**：用户在需求确认时追加的非功能约束（2026-05-30）

**优先级**：P0（与 REQ-AUTH-001 并列，是其实现方案的硬性约束）

**与 OQ-002 的关系**：本需求直接决定 OQ-002 的选型方向。

### 3.4.1 业务规则

1. **明确禁止**：每个受认证 API 请求同步写一次数据库（例如在认证中间件中对每个请求执行 `UPDATE authtoken_token SET last_active_at=now()`），无论写入行是否变化。
2. **理由**：生产 MySQL 的 `device_param_history` 表已膨胀至约 3766 万行 / 11.3 GB，历史上发生过因高写入并发导致的 `Lost connection` 和连接超时问题（`read_timeout=60s`）；在此基础上叠加高频认证写入会加剧风险。
3. **可接受方案方向**（架构阶段确认具体选型）：
   - **带节流（throttle）的数据库写入**：在认证中间件或自定义认证类中，仅当距上次 DB 写入已超过 N 分钟（如 5 分钟，此值应为可配置项）时才触发一次 `UPDATE`；否则只在内存/缓存中更新时间戳。
   - **内存缓存层**：将 `last_active_at` 存储在进程内缓存（Django `LocMemCache` 或等效方案），定期或在超时临界时回写数据库。
4. 所选方案必须在架构文档中明确说明在单 worker（`--workers 1`）场景下的一致性保证，以及在 worker 重启后的数据可靠性（缓存丢失时的降级行为）。
5. 本约束不排斥数据库方案，但排斥**无节流的同步高频写**。

### 3.4.2 验收标准

- **AC-NFR-001-1**：在正常使用场景（用户每分钟发起约 5~10 次 API 请求）下，`authtoken_token`（或等效活动时间记录表）每 5 分钟内的 `UPDATE` 操作次数不超过 1 次（每用户）。
- **AC-NFR-001-2**：架构文档中明确标注活动时间写入的节流逻辑和节流阈值，该阈值通过配置项（settings.py 命名常量）定义，不硬编码。
- **AC-NFR-001-3**：在 worker 重启（进程内缓存丢失）后，最坏情况下用户会话被提前超时（保守判定），而非绕过超时保护继续有效。

---

## 4. 约束与假设

| ID | 类型 | 内容 |
|----|------|------|
| C-01 | 约束 | 超时阈值固定为 30 分钟，本版本不提供用户自定义入口 |
| C-02 | 约束 | 后端运行环境为树莓派（ARM 物理机）+ Waitress WSGI，无 Docker；方案不得引入需要容器化的组件 |
| C-03 | 约束 | 生产数据库为 MySQL 8.x（192.168.31.98:3306），方案若需新建数据表或字段，须提供 Django migration |
| C-04 | 约束 | 不引入 Redis 等额外中间件（非强制排除，但需在架构阶段确认可行性后才能纳入） |
| C-05 | 约束 | 前端不使用 Vuex/Pinia；前端状态管理沿用 Vue 2 Options API 或 Vue 3 Composition API（当前代码混用），不引入全局 store |
| A-01 | 假设 | 所有受保护 API 端点均经过 `authenticatedFetch` 封装调用；如有直接使用原生 `fetch` 的场景，需在架构阶段排查 |
| A-02 | 假设 | 超时判定在后端执行（不依赖前端定时器）；前端定时器仅作为辅助手段（可选，架构阶段决策） |
| A-03 | 假设 | 单用户单 token 场景（不存在同一账号多设备同时在线需差异化处理的业务需求） |

---

## 5. 开放问题（留给架构阶段决策）

以下问题**不在本需求阶段解答**，但需要在架构文档中明确选型并给出决策理由：

| ID | 问题 | 背景 |
|----|------|------|
| OQ-001 | **后端超时判定方案**：如何在 DRF 原生 Token 框架下实现滑动窗口超时？候选方案包括但不限于：(A) 自定义 Token 模型增加 `last_active_at` 字段；(B) 替换为 `djangorestframework-simplejwt` 并配置 refresh token；(C) 自定义 `TokenAuthentication` 子类，在 `authenticate()` 中检查活动时间戳；(D) 利用 Django Session 框架的 `SESSION_COOKIE_AGE` 替代 token。各方案需评估对现有 DRF token 兼容性和迁移成本的影响。 | REQ-AUTH-001 |
| OQ-002 | **"活动"时间戳的存储介质**：用数据库记录 `last_active_at`（高可靠、高写入压力）还是用内存/缓存（低延迟、需持久化层）？需结合生产 DB 现有性能压力（`device_param_history` 已 3766 万行）评估写入频率影响。 | REQ-AUTH-001 |
| OQ-003 | **前端是否需要主动续期心跳**：纯被动（等待 401）vs 前端定时轮询续期。纯被动方案在用户临界操作（30 分钟整点恰好提交）时存在丢失操作的风险；主动心跳会增加无效请求量。 | REQ-AUTH-001 |
| OQ-004 | **last_login 更新路径**：若架构方案替换 Django `login()` 调用，需确认是否保留 `user_logged_in` 信号或改为显式 `user.save()`。 | REQ-AUTH-002 |
| OQ-005 | **前端跳转时的"当前操作保护"**：若用户在表单填写到一半时 token 过期，401 跳转会丢失填写内容。是否需要在跳转前提示用户保存或在 URL 中携带 `next` 参数回跳？ | REQ-AUTH-003 |

---

## 6. 需求汇总表

| 需求 ID | 描述 | 类型 | 涉及端 | 优先级 | 依赖 |
|---------|------|------|--------|--------|------|
| REQ-AUTH-001 | 会话不活动超时（滑动窗口 30 分钟） | 新增 | 后端 | P0 | 无 |
| REQ-AUTH-002 | 登录时刷新 last_login | 增强 | 后端 | P1 | 无（与 REQ-AUTH-001 并行可实现） |
| REQ-AUTH-003 | 前端 401 统一处理与自动跳转登录页 | 新增 | 前端 | P1 | REQ-AUTH-001（超时触发 401 是主要触发场景） |
| REQ-NFR-AUTH-001 | 活动时间刷新不得显著增加数据库写压力（禁止每请求同步写 DB，须节流/缓存） | 非功能约束 | 后端 | P0 | REQ-AUTH-001（OQ-002 选型约束） |
