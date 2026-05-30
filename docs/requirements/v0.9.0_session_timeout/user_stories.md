# 用户故事与验收标准

```
file_header:
  document_id: US-v0.9.0-SESSION-TIMEOUT
  title: 会话不活动超时与 last_login 刷新 — 用户故事
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.9.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT — 待用户确认（需求门控等待中）
  references:
    - docs/requirements/v0.9.0_session_timeout/requirements_spec.md
```

---

## US-001：长时间不操作后须重新登录（对应 REQ-AUTH-001）

**As** 已登录的用户（管理员或业主），  
**I want** 系统在我连续 30 分钟没有任何操作后自动使我的凭证失效，  
**So that** 在我离开屏幕期间，其他人无法在未经授权的情况下继续使用我的账号访问监控平台。

### 验收标准

**AC-001-1（30 分钟内活动不超时）**
- Given 用户已登录，并在最近 29 分钟内发起过至少一次有效 API 请求
- When 用户发起下一次 API 请求
- Then 请求成功（后端返回 2xx 或业务正常响应），不触发 401，用户无感知

**AC-001-2（超过 30 分钟无活动后请求被拒绝）**
- Given 用户已登录，且距其最后一次有效 API 请求已过去 30 分钟以上（未发起任何 API 请求）
- When 用户发起任意需要认证的 API 请求
- Then 后端返回 HTTP 401；该用户的 token 被判定为超时失效

**AC-001-3（滑动窗口——活动刷新计时）**
- Given 用户在 T+0 登录，T+25 分钟时发起了一次有效 API 请求（计时重置为 T+25）
- When 用户在 T+50 分钟（即距上次活动仅 25 分钟）发起 API 请求
- Then 请求成功（因为距上次活动 25 分钟 < 30 分钟阈值），不超时

> 此验收标准明确区分"滑动窗口"与"绝对过期"：用户只要保持活跃，会话可无限续期；**超时计时从最后一次有效活动开始**，而非从登录时刻开始。

**AC-001-4（超时后重新登录可恢复访问）**
- Given 用户 token 已因 30 分钟不活动而失效
- When 用户在登录页输入正确的用户名和密码并提交
- Then 用户获得新 token，可正常访问受保护页面；旧 token 不可继续使用

**AC-001-5（主动登出不受超时机制影响）**
- Given 用户在未超时的情况下点击"退出登录"
- When 退出流程完成
- Then 用户 token 立即失效（原有逻辑），行为与超时失效无关联

**AC-001-6（超时阈值为后端配置项，不硬编码）**
- Given 开发者查看后端代码
- When 检查超时阈值的定义位置
- Then 阈值通过配置项（如 `settings.py` 中的命名常量或环境变量）定义，值为 30 分钟；不在认证逻辑或视图代码中以魔法数字出现

---

## US-002：登录成功后 last_login 字段被刷新（对应 REQ-AUTH-002）

**As** 系统管理员，  
**I want** 每次用户成功登录后，数据库中该用户的 `last_login` 字段被更新为本次登录时间，  
**So that** 我在后台管理界面能看到用户的真实最近登录时间，准确判断账号活跃度。

### 验收标准

**AC-002-1（成功登录后 last_login 刷新）**
- Given 用户已存在，且 `api_customuser.last_login` 为某历史时间 T_old
- When 用户通过 `POST /api/auth/login/` 以正确的用户名和密码成功登录
- Then 数据库中 `api_customuser.last_login` 被更新为本次登录的服务器时间 T_new，T_new > T_old，且 T_new 与实际登录时刻的误差不超过 5 秒

**AC-002-2（登录失败时 last_login 不变）**
- Given 用户已存在，`api_customuser.last_login` 为 T_old
- When 用户提交了错误的密码，登录接口返回认证失败响应
- Then `api_customuser.last_login` 保持 T_old 不变

**AC-002-3（超时后重新登录刷新 last_login）**
- Given 用户在 T1 登录（last_login = T1），随后 token 因 30 分钟不活动超时失效
- When 用户在 T2 重新登录（T2 > T1 + 30 分钟）
- Then `api_customuser.last_login` 被更新为 T2，不再停留在 T1

**AC-002-4（last_login 使用服务器 UTC 时间）**
- Given Django 时区配置为 UTC（或 Asia/Shanghai，以 settings.py 实际配置为准）
- When 用户成功登录
- Then `last_login` 存储的时区与 Django `TIME_ZONE` 设置一致，不因客户端时区差异而偏移

---

## US-003：token 过期后前端自动跳转登录页（对应 REQ-AUTH-003）

**As** 已登录的用户，  
**I want** 在我的会话因超时而过期后，系统自动将我引导回登录页面，并告知我会话已过期，  
**So that** 我不会因为看到奇怪的错误信息或空白页面而困惑，而是清楚地知道需要重新登录。

### 验收标准

**AC-003-1（任意 API 收到 401 后清除凭证并跳转）**
- Given 用户正在使用平台，其 token 已在后端因超时失效
- When 前端 `authenticatedFetch` 收到后端返回的 HTTP 401 响应
- Then：(a) `localStorage` 中的 `userToken` 被清除；(b) cookie 中的 `auth_token`（若存在）被清除；(c) CSRF token 缓存被清除；(d) 页面跳转到 `/login` 路由

**AC-003-2（跳转前展示过期提示）**
- Given 前端收到 401 响应并准备跳转
- When 跳转动作触发
- Then 在跳转前或跳转后（进入登录页时）向用户展示可见提示（如 Element Plus `ElMessage.warning`），提示文案含"会话已过期"或"请重新登录"等语义明确的文字

**AC-003-3（跳转使用 replace 而非 push）**
- Given 用户因 401 被跳转到登录页
- When 用户在登录页点击浏览器"后退"按钮
- Then 浏览器不返回到超时前的受保护页面（因为使用了 `router.replace`，历史栈中不留下该受保护页面的记录）

**AC-003-4（已在登录页时不循环重定向）**
- Given 用户当前已在 `/login` 路由
- When 任何请求（如登录接口本身）返回 401
- Then 前端不触发重复跳转，不产生路由死循环

**AC-003-5（统一处理，无需各视图单独捕获）**
- Given 平台有 20 个以上受保护视图（Home、UsageQuery、DeviceCards 等）
- When 其中任意一个视图中的 API 请求收到 401
- Then 跳转逻辑由 `api.js` 的 `authenticatedFetch` 统一处理，无需各视图单独实现 401 跳转逻辑

**AC-003-6（非 401 错误不触发跳转）**
- Given 某 API 请求因网络超时（无响应）或后端 500 错误而失败
- When 错误冒泡到调用方
- Then 不触发 `/login` 跳转；错误处理行为与当前版本一致（由各视图自行处理）

---

## 待确认项汇总

本版本需求文档中无歧义或笔误类待确认项。以下事项留给用户在确认需求时一并表态（非阻塞项，均为可选优化）：

| ID | 关联需求 | 问题 | 选项 |
|----|---------|------|------|
| Q-001 | REQ-AUTH-001 / US-001 | 超时时长是否有调整为非 30 分钟的需求？ | A) 固定 30 分钟（按用户原话）/ B) 需要其他时长（请指定） |
| Q-002 | REQ-AUTH-003 / US-003 | 用户在表单页（如设备设置页）填写到一半时 token 过期，跳转前是否需要保护机制（如提示"操作未保存，是否继续退出"）？ | A) 不需要，直接跳转 / B) 需要（本版本或后续版本实现） |
| Q-003 | REQ-AUTH-003 / AC-003-1 | `api.js` 中 `getAuthToken()` 优先读 cookie 中的 `auth_token`，其次才读 `localStorage.userToken`。cookie 路径何时使用？是否有单独的 cookie 写入逻辑？若有，清除逻辑需对称。 | 请说明 cookie 路径的使用场景，或确认"可忽略 cookie 路径，只清 localStorage 即可" |
