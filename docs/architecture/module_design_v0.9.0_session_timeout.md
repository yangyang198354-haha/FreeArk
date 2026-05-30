# 模块设计文档

```
file_header:
  document_id: MOD-DESIGN-v0.9.0-SESSION-TIMEOUT
  title: 会话不活动超时 — 模块设计文档
  author_agent: System Architect (PARTIAL_FLOW, 架构阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.9.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT — 待架构门控
  references:
    - docs/architecture/architecture_design_v0.9.0_session_timeout.md
    - docs/requirements/v0.9.0_session_timeout/requirements_spec.md (v0.2.0)
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-30 | 初始模块设计，覆盖所有新增/变更模块 |

---

## 1. 模块清单

| 模块 ID | 名称 | 类型 | 文件路径 | 状态 |
|---------|------|------|---------|------|
| MOD-BE-AUTH-01 | 滑动窗口 Token 认证类 | 新建 | `api/authentication.py` | 新增 |
| MOD-BE-AUTH-02 | TokenActivity 模型 | 新建 | `api/models.py`（新增 class） | 新增 |
| MOD-BE-AUTH-03 | 登录视图 last_active_at 初始化 | 修改 | `api/views.py`（`user_login`） | 微改 |
| MOD-BE-AUTH-04 | settings 认证与超时配置 | 修改 | `freearkweb/settings.py` | 微改 |
| MOD-FE-AUTH-01 | authenticatedFetch 401 统一处理 | 修改 | `frontend/src/utils/api.js` | 微改 |

---

## 2. MOD-BE-AUTH-01：`SlidingWindowTokenAuthentication`

**文件**：`FreeArkWeb/backend/freearkweb/api/authentication.py`（新建）

**职责**：替换 DRF 默认 `TokenAuthentication`，在 token 验证通过后追加滑动窗口超时检查；同时以节流方式更新 `TokenActivity.last_active_at`。

### 2.1 接口说明

```python
class SlidingWindowTokenAuthentication(TokenAuthentication):
    """
    DRF TokenAuthentication 的滑动窗口超时扩展。

    超时阈值：settings.SESSION_INACTIVITY_TIMEOUT（秒，默认 1800）
    节流阈值：settings.ACTIVITY_THROTTLE_SECONDS（秒，默认 300）

    认证流程：
      1. 调用 super().authenticate_credentials(key) 验证 token 有效性
      2. 通过 TokenActivity 查询最后活动时间
         - 若记录不存在（如旧 token 迁移后首次访问），创建记录并放行
      3. 检查 now - last_active_at >= SESSION_INACTIVITY_TIMEOUT → 抛 AuthenticationFailed
      4. 节流检查：若距上次 DB 写入 > ACTIVITY_THROTTLE_SECONDS → UPDATE DB
         否则仅刷新进程内缓存
    """

    def authenticate_credentials(self, key: str):
        """
        Returns: (user, token) 或 raise AuthenticationFailed
        """
```

### 2.2 模块级节流缓存

```python
# 模块级字典：token_key -> last_db_write_time (datetime)
# 单进程安全；worker 重启后清空（降级：从 DB 重读）
_activity_cache: dict[str, datetime] = {}
```

### 2.3 超时检查逻辑（伪代码）

```
def authenticate_credentials(self, key):
    # Step 1: 验证 token 存在（调用父类）
    user, token = super().authenticate_credentials(key)
    
    # Step 2: 获取或创建 TokenActivity 记录
    now = django_now()  # 使用 Django 时间（与 USE_TZ 设置一致）
    activity, created = TokenActivity.objects.get_or_create(
        token=token,
        defaults={'last_active_at': now}
    )
    if created:
        # 首次访问（旧 token 迁移场景）：写入缓存并放行
        _activity_cache[key] = now
        return (user, token)
    
    # Step 3: 超时检查
    elapsed = (now - activity.last_active_at).total_seconds()
    if elapsed >= SESSION_INACTIVITY_TIMEOUT:
        raise AuthenticationFailed(_("会话已超时，请重新登录"))
    
    # Step 4: 节流更新
    last_db_write = _activity_cache.get(key)
    if last_db_write is None or (now - last_db_write).total_seconds() >= ACTIVITY_THROTTLE_SECONDS:
        # 触发 DB 写入
        TokenActivity.objects.filter(token=token).update(last_active_at=now)
        _activity_cache[key] = now
    else:
        # 仅刷新进程内时间（不写 DB）
        # 注意：_activity_cache 存的是 last_db_write_time，不需要更新
        pass
    
    return (user, token)
```

**关键细节说明：**

- `_activity_cache` 存储的是"上次写入 DB 的时间"，不是"最新活动时间"。这样节流判断可以精确计算"距上次 DB 写入已过多久"。
- 超时判断基于 `activity.last_active_at`（DB 值），而非缓存值。这保证了：即使进程内缓存无记录（worker 刚重启），也能从 DB 正确判断超时状态。
- `SESSION_INACTIVITY_TIMEOUT` 和 `ACTIVITY_THROTTLE_SECONDS` 从 `django.conf.settings` 读取，在模块 import 时解析一次（不支持热更新，符合 Django 配置惯例）。

### 2.4 与现有认证链路的兼容性

- `SlidingWindowTokenAuthentication` 是 `TokenAuthentication` 的子类，完全兼容 DRF 权限体系。
- `request.user` 和 `request.auth` 的行为与原来一致（`auth` 仍为 `Token` 实例）。
- `SessionAuthentication`（`DEFAULT_AUTHENTICATION_CLASSES` 的第二项）保持不变，用于 Django admin 等需要 session 的场景。

---

## 3. MOD-BE-AUTH-02：`TokenActivity` 模型

**文件**：`FreeArkWeb/backend/freearkweb/api/models.py`（追加 class）

```python
class TokenActivity(models.Model):
    """
    记录 DRF Token 的最后有效活动时间，用于滑动窗口超时判断。

    表名：api_token_activity
    与 authtoken_token 为 OneToOne 关系，Token 删除时级联删除（on_delete=CASCADE）。
    """
    token = models.OneToOneField(
        'authtoken.Token',
        on_delete=models.CASCADE,
        related_name='activity',
        primary_key=True,
    )
    last_active_at = models.DateTimeField(
        verbose_name='最后活动时间',
        db_index=True,
    )

    class Meta:
        db_table = 'api_token_activity'
        verbose_name = 'Token 活动记录'
        verbose_name_plural = 'Token 活动记录'

    def __str__(self):
        return f"TokenActivity(token={self.token_id[:8]}..., last_active={self.last_active_at})"
```

**Migration 要点：**
- `primary_key=True` 使 `token_id`（varchar 40）直接作为主键，无需额外 `id` 自增列。
- `CASCADE` 确保 `user_logout` 删除 `Token` 时 `TokenActivity` 自动清理，无需额外代码。
- `db_index=True` 加在 `last_active_at`，为将来管理员查询"N 分钟无活动用户"提供索引支持。

---

## 4. MOD-BE-AUTH-03：`user_login` 视图修改

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`

**变更内容**：在 `Token.objects.get_or_create(user=user)` 之后，追加 `TokenActivity` 初始化逻辑。

**变更前（关键片段）**：
```python
token, created = Token.objects.get_or_create(user=user)
return Response({
    'success': True,
    'token': token.key,
    ...
})
```

**变更后**：
```python
token, created = Token.objects.get_or_create(user=user)

# REQ-AUTH-001: 登录时初始化/重置活动时间戳（绕过节流，强制写入）
from django.utils.timezone import now as django_now
from .models import TokenActivity
TokenActivity.objects.update_or_create(
    token=token,
    defaults={'last_active_at': django_now()},
)

return Response({
    'success': True,
    'token': token.key,
    ...
})
```

**说明：**
- `update_or_create` 是原子 upsert，无竞态风险。
- 登录时强制绕过节流写入（确保新登录 token 立即有有效时间戳）。
- `django_now()` 与 `USE_TZ = False` 环境下返回 naive datetime（与 `last_login` 的时区处理一致）。

**需同步验证**：`user_register` 视图也调用了 `Token.objects.get_or_create`，应同样追加 `TokenActivity` 初始化（避免注册后直接使用时 `TokenActivity` 不存在）。

---

## 5. MOD-BE-AUTH-04：`settings.py` 变更

**文件**：`FreeArkWeb/backend/freearkweb/freearkweb/settings.py`

### 5.1 认证类替换

```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        # REQ-AUTH-001: 替换为滑动窗口超时认证类（v0.9.0）
        'api.authentication.SlidingWindowTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}
```

### 5.2 新增配置常量

```python
# ===========================================================================
# 会话超时配置（v0.9.0, REQ-AUTH-001, REQ-NFR-AUTH-001）
# ===========================================================================
# 会话不活动超时阈值（秒）。默认 30 分钟 = 1800 秒。
# 通过环境变量 SESSION_INACTIVITY_TIMEOUT 可覆盖（整数，秒）。
SESSION_INACTIVITY_TIMEOUT = int(os.environ.get('SESSION_INACTIVITY_TIMEOUT', 1800))

# 活动时间写入 DB 的节流阈值（秒）。默认 5 分钟 = 300 秒。
# 同一 token 在此时间内的多次请求只触发一次 DB UPDATE。
# 须满足：ACTIVITY_THROTTLE_SECONDS < SESSION_INACTIVITY_TIMEOUT
# 通过环境变量 ACTIVITY_THROTTLE_SECONDS 可覆盖（整数，秒）。
ACTIVITY_THROTTLE_SECONDS = int(os.environ.get('ACTIVITY_THROTTLE_SECONDS', 300))
```

---

## 6. MOD-FE-AUTH-01：`authenticatedFetch` 401 统一处理

**文件**：`FreeArkWeb/frontend/src/utils/api.js`

### 6.1 改动概述

在 `authenticatedFetch` 函数返回 fetch response 之前，插入 401 检查逻辑。

### 6.2 新增辅助函数

在 `api.js` 顶部或 `authenticatedFetch` 之前，新增以下辅助：

```javascript
// 清除认证 cookie（与 clearCSRFToken 对称）
function clearAuthCookie() {
  // 覆盖写入过期 cookie 来清除
  document.cookie = 'auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
}
```

### 6.3 `authenticatedFetch` 改动

在函数末尾 `return fetch(...)` 改为：

```javascript
async function authenticatedFetch(endpoint, options = {}) {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('未登录或登录已过期');
  }
  
  // ... (CSRF 部分不变) ...
  
  const response = await fetch(getApiUrl(endpoint), mergedOptions);
  
  // REQ-AUTH-003: 统一拦截 401，清理本地凭证并跳转登录页
  if (response.status === 401) {
    // 防止循环重定向：若已在登录页则跳过跳转和弹窗
    const isOnLoginPage = router.currentRoute.value.name === 'Login';
    
    // 清理本地凭证
    localStorage.removeItem('userToken');
    clearAuthCookie();
    clearCSRFToken();
    
    if (!isOnLoginPage) {
      // 展示过期提示（动态导入 ElMessage，避免全局污染）
      try {
        const { ElMessage } = await import('element-plus');
        ElMessage.warning('会话已过期，请重新登录');
      } catch (_) {
        // ElMessage 不可用时静默继续（不阻断跳转）
      }
      // 使用 replace 而非 push，避免浏览器后退回到无权限页面
      router.replace({ name: 'Login' });
    }
    
    // 抛出特定错误，使调用方 catch 块可识别（不需要各自再处理跳转）
    throw new Error('SESSION_EXPIRED');
  }
  
  return response;
}
```

**关键设计决策：**

1. **`router` 引入**：在 `api.js` 顶部 `import router from '../router/index.js'`。Vue 3 中 router 实例在模块导出后可直接在非组件文件中使用，无循环依赖（`router/index.js` 不 import `api.js`，已确认）。
2. **`ElMessage` 动态导入**：避免 `api.js` 对 Element Plus 产生静态依赖；即使 Element Plus 未加载也不影响跳转。
3. **错误类型**：抛出 `'SESSION_EXPIRED'` 消息的 Error；现有业务视图的 catch 块通常只展示错误信息或忽略，不会与 401 跳转冲突（因为跳转在 throw 之前已触发）。
4. **`api.get`/`api.post` 等方法**：不变。这些方法调用 `authenticatedFetch` 获取 response 后检查 `response.ok`；由于 `authenticatedFetch` 在 401 时会 throw，这些方法的 `if (!response.ok)` 分支不会被执行，符合预期。

### 6.4 `api.logout()` 确认（不需要额外修改）

现有 `api.logout()` 已调用 `authenticatedFetch('/api/auth/logout/', { method: 'POST' })`；若后端返回 401（token 已失效），catch 块有 `console.warn + continue` 逻辑，不阻断流程。`finally` 块中已调用 `clearCSRFToken()`。

**v0.9.0 追加**：logout() 需额外清理 `localStorage.userToken` 和 `auth_token` cookie（当前各调用方自行清理，集中到 `api.logout()` 更安全）：

```javascript
async logout() {
  try {
    await authenticatedFetch('/api/auth/logout/', { method: 'POST' });
  } catch (e) {
    console.warn('后端登出请求失败，继续本地清理:', e.message);
  } finally {
    clearCSRFToken();
    localStorage.removeItem('userToken');   // v0.9.0 新增
    clearAuthCookie();                       // v0.9.0 新增
  }
},
```

---

## 7. 模块间依赖关系

```
settings.py
    ↓ SESSION_INACTIVITY_TIMEOUT, ACTIVITY_THROTTLE_SECONDS
    ↓ DEFAULT_AUTHENTICATION_CLASSES
authentication.py (MOD-BE-AUTH-01)
    ↓ authenticate_credentials()
    ↓ TokenActivity.objects.get_or_create / update
models.py::TokenActivity (MOD-BE-AUTH-02)
    ↓ OneToOneField → authtoken.Token
    ↑ CASCADE DELETE ← user_logout (views.py)

views.py::user_login (MOD-BE-AUTH-03)
    → TokenActivity.objects.update_or_create (登录时强制初始化)

frontend/api.js::authenticatedFetch (MOD-FE-AUTH-01)
    → router (vue-router 实例)
    → ElMessage (element-plus，动态导入)
    ← 所有业务视图通过 api.get / api.post 调用
```

---

## 8. 验收对照（需求 → 模块）

| 需求 ID | 验收标准 | 负责模块 |
|---------|---------|---------|
| REQ-AUTH-001 | AC-001-1: 29 分钟内活动不超时 | MOD-BE-AUTH-01（时间窗口判断） |
| REQ-AUTH-001 | AC-001-2: 30+ 分钟无活动返回 401 | MOD-BE-AUTH-01（`raise AuthenticationFailed`） |
| REQ-AUTH-001 | AC-001-3: 滑动窗口重置 | MOD-BE-AUTH-01（更新 `last_active_at`） |
| REQ-AUTH-001 | AC-001-4: 超时后重登可恢复 | MOD-BE-AUTH-03（登录时重置 `TokenActivity`） |
| REQ-AUTH-001 | AC-001-6: 阈值走配置 | MOD-BE-AUTH-04（settings 常量） |
| REQ-AUTH-002 | AC-002-1/2/3/4: last_login 刷新 | 现有 `login(request, user)` 信号链路（无需改动） |
| REQ-AUTH-003 | AC-003-1: 401 时清凭证 | MOD-FE-AUTH-01 |
| REQ-AUTH-003 | AC-003-2: 展示过期提示 | MOD-FE-AUTH-01（ElMessage.warning） |
| REQ-AUTH-003 | AC-003-3: 使用 router.replace | MOD-FE-AUTH-01 |
| REQ-AUTH-003 | AC-003-4: 避免循环重定向 | MOD-FE-AUTH-01（`isOnLoginPage` 检查） |
| REQ-AUTH-003 | AC-003-5: 统一处理 | MOD-FE-AUTH-01（`authenticatedFetch` 单点） |
| REQ-AUTH-003 | AC-003-6: 非 401 不触发跳转 | MOD-FE-AUTH-01（`if (response.status === 401)` 精确判断） |
| REQ-NFR-AUTH-001 | AC-NFR-001-1: 每用户每 5 分钟最多 1 次 DB 写 | MOD-BE-AUTH-01（节流逻辑） |
| REQ-NFR-AUTH-001 | AC-NFR-001-2: 节流阈值走配置 | MOD-BE-AUTH-04（`ACTIVITY_THROTTLE_SECONDS`） |
| REQ-NFR-AUTH-001 | AC-NFR-001-3: 重启后保守判定超时 | MOD-BE-AUTH-01（重启后从 DB 读，无缓存时保守） |
