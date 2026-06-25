# 模块设计文档（Module Design）

**版本**：v1.8.0_miniprogram_owner_account  
**日期**：2026-06-25  
**状态**：DRAFT  
**作者**：system-architect (SDLC Agent)  
**依赖**：architecture_design.md (DRAFT)

---

## 模块索引

| 模块 ID | 模块名 | 文件位置 | 状态 |
|---------|--------|---------|------|
| MOD-180-01 | 数据模型：WechatBinding / OwnerUserBinding | `api/models.py`（追加） | 新建 |
| MOD-180-02 | 中间件改造：UserRoleApiGuardMiddleware | `api/middleware.py`（改动 3 行） | 改造 |
| MOD-180-03 | miniapp 视图层：views_miniapp.py | `api/views_miniapp.py` | 新建 |
| MOD-180-04 | miniapp 路由：urls_miniapp.py | `api/urls_miniapp.py` | 新建 |
| MOD-180-05 | 用户范围上下文：UserScope | `api/langgraph_chat/user_scope.py` | 新建 |
| MOD-180-06 | 隔离执行器：ScopeEnforcer | `api/langgraph_chat/scope_enforcer.py` | 新建 |
| MOD-180-07 | 编排图改造：State 扩展 + _expert/_gate 注入 | `api/langgraph_chat/orchestrator.py`（改动） | 改造 |
| MOD-180-08 | 工具扩展：get_plc_status / get_fault_summary | `api/langgraph_chat/fa_tools.py`（改动） | 改造 |
| MOD-180-09 | 小程序聊天 Consumer：MiniAppChatConsumer | `api/consumers.py`（追加） | 新建 |
| MOD-180-10 | adapter 扩展：user_scope 传参 | `api/langgraph_chat/adapter.py`（改动） | 改造 |
| MOD-180-11 | 小程序前端：注册/绑定/聊天页 | `miniprogram/`（新增页面） | 新建 |
| MOD-180-12 | web 端业主管理页：账号绑定列 | `frontend/src/views/OwnerManagementView.vue` | 改造 |
| MOD-180-13 | 数据库迁移 | `api/migrations/0041_*.py` | 新建 |

---

## MOD-180-01：数据模型

### 1.1 接口

```
WechatBinding
  Fields: id, user_id(FK→CustomUser), openid(unique), unionid(nullable), created_at
  Methods: get_by_openid(openid) → WechatBinding|None

OwnerUserBinding
  Fields: id, user_id(FK→CustomUser), owner_id(FK→OwnerInfo), active(bool), bound_at, unbound_at
  Methods:
    get_active_bindings(user) → QuerySet[OwnerUserBinding]
    get_bound_specific_parts(user) → list[str]   # 活跃绑定的 specific_part 列表
    bind(user, owner) → OwnerUserBinding         # 已存在 active 绑定时抛 AlreadyBound
    unbind(user, owner) → OwnerUserBinding       # 无 active 绑定时抛 NotBound
```

### 1.2 实现约束

- `bind()` 操作前必须检查 `filter(user=user, owner=owner, active=True).exists()`，存在则抛 `AlreadyBoundError`（不覆盖、不创建重复行）
- `unbind()` 将 `active=False`、写入 `unbound_at=now()`，不物理删除
- `get_bound_specific_parts(user)` 返回 `OwnerUserBinding.objects.filter(user=user, active=True).select_related('owner').values_list('owner__specific_part', flat=True)`
- 两个模型不得在 `OwnerInfo.bind_status` 字段上读写

---

## MOD-180-02：UserRoleApiGuardMiddleware 改造

### 2.1 改动范围

文件：`FreeArkWeb/backend/freearkweb/api/middleware.py`

仅在 `_should_block()` 方法中新增 2 行有效代码（1 行注释）：

```python
def _should_block(self, request):
    path = request.path
    if not path.startswith('/api/'):
        return False
    if path in self.ALLOWLIST:
        return False
    # ── v1.8.0 新增：/api/miniapp/ 整体放行，各端点自配 IsOwnerUser 权限类 ──
    if path.startswith('/api/miniapp/'):
        return False
    # ── 原有逻辑不变 ──
    user = self._resolve_token_user(request)
    return user is not None and getattr(user, 'role', None) == 'user'
```

### 2.2 不改动项

- `ALLOWLIST` 常量（6 条精确路径）：不改
- `__init__`、`__call__`、`_resolve_token_user`：不改
- 类文档字符串：追加一行 v1.8.0 变更说明

### 2.3 测试要求

需新增测试用例（在现有 `test_rbac_v160.py` 或新建 `test_rbac_v180.py`）：
- role=user Token 访问 `/api/miniapp/bind/`：预期 HTTP 200（不被中间件拦截，由 IsOwnerUser 放行）
- role=user Token 访问 `/api/owners/`（现有 web 端点）：预期 HTTP 403（中间件继续拦截）
- role=operator Token 访问 `/api/miniapp/bind/`：预期 HTTP 403（IsOwnerUser 权限类拒绝 operator）

---

## MOD-180-03：miniapp 视图层

### 3.1 文件：`api/views_miniapp.py`

所有视图遵循现有 views.py 风格（DRF APIView / api_view 装饰器），不引入新框架。

#### 3.1.1 miniapp_register

```
@api_view(['POST'])
@permission_classes([AllowAny])
def miniapp_register(request):
    """
    小程序账号密码注册（REQ-AUTH-001）。
    与 web /api/auth/register/ 行为一致，role 强制 user（复用 UserRegistrationSerializer）。
    独立端点保持 web 注册路径不变。
    
    Request Body: {username, password, password2, email(可选)}
    Response 201: {token, user: {id, username, role}}
    Response 400: {errors}
    
    频率限制: 10/min/IP（在 urls_miniapp.py 配置 throttle）
    """
```

**实现约束**：
- 复用 `UserRegistrationSerializer`（已有 `role='user'` 强制逻辑）
- 注册成功后自动创建 Token 并初始化 `TokenActivity`（与 web 注册一致，REQ-AUTH-001 满足 C-04）
- 不调用 `login(request, user)`（web 注册有，小程序端无 session，无需调用）

#### 3.1.2 miniapp_wechat_login

```
@api_view(['POST'])
@permission_classes([AllowAny])
def miniapp_wechat_login(request):
    """
    微信一键登录/注册（REQ-AUTH-002）。
    
    Request Body: {code: str}  # wx.login() 返回的临时 code
    Response 200: {token, user: {id, username, role}, is_new: bool}
    Response 400: {detail: "微信授权失败，请重试"}
    Response 503: {detail: "微信服务暂时不可用"}
    
    内部流程：
    1. 用 code 调微信 code2session API → 得到 openid (+ unionid)
    2. 查 WechatBinding.objects.filter(openid=openid).select_related('user')
    3. 存在 → user = binding.user；is_new = False
    4. 不存在 → 创建 CustomUser(username=f'wx_{openid[:8]}', role='user')
              → 创建 WechatBinding(user=user, openid=openid, unionid=unionid)
              → is_new = True
    5. Token.objects.get_or_create(user=user)
    6. TokenActivity.update_or_create(...)
    7. 返回 token + user info
    
    安全约束：
    - 超时时间 5s，微信服务器无响应 → 503
    - requests 异常 → 500（不暴露内部错误）
    - openid 不写入响应（REQ-NFR-SEC-002）
    """
```

**实现约束**：
- 调用微信 API 使用 `requests.get(..., timeout=5)`（进程内同步调用，DRF view 可接受）
- `WECHAT_MINIAPP_APPID` / `WECHAT_MINIAPP_SECRET` 从 `django.conf.settings` 读取（`.env` 注入）
- openid 不加密存储，不在任何 response body、URL 参数中暴露

#### 3.1.3 miniapp_bind

```
@api_view(['POST'])
@permission_classes([IsOwnerUser])
def miniapp_bind(request):
    """
    扫码/输入 MAC 地址绑定专有部分（REQ-BIND-001 / REQ-BIND-002）。
    
    Request Body: {unique_id: str}  # screenMAC / MAC 地址
    Response 200: {specific_part, location_name, bound_at}
    Response 400: {detail: "MAC 地址格式不正确"}（格式校验失败）
    Response 404: {detail: "未找到对应的专有部分，请确认二维码是否有效"}
    Response 409: {detail: "您已绑定该专有部分"}（同一用户重复绑定同一 owner）
    
    内部流程：
    1. 校验 unique_id 格式（非空，长度 <= 50）
    2. OwnerInfo.objects.filter(unique_id=unique_id).first()
       → 无记录 → 404
    3. 检查 OwnerUserBinding.objects.filter(user=request.user, owner=owner, active=True).exists()
       → 已绑定 → 409
    4. OwnerUserBinding.objects.create(user=request.user, owner=owner, active=True)
    5. 返回 200
    
    频率限制: 10/min/user（REQ-NFR-SEC-001）
    """
```

#### 3.1.4 miniapp_unbind

```
@api_view(['POST'])
@permission_classes([IsOwnerUser])
def miniapp_unbind(request):
    """
    业主自助解绑（REQ-BIND-003 解绑）。
    
    Request Body: {unique_id: str}  OR  {specific_part: str}
    Response 200: {detail: "解绑成功"}
    Response 404: {detail: "未找到有效绑定记录"}（无 active 绑定）
    
    内部流程：
    1. 根据 unique_id 或 specific_part 查 OwnerInfo
    2. filter(user=request.user, owner=owner, active=True) → 无记录 → 404
    3. binding.active = False; binding.unbound_at = now(); binding.save()
    4. 返回 200
    """
```

#### 3.1.5 miniapp_bind_status

```
@api_view(['GET'])
@permission_classes([IsOwnerUser])
def miniapp_bind_status(request):
    """
    查询当前用户绑定状态（REQ-BIND-004 / US-AUTH-003）。
    
    Response 200:
    {
      "bound": true/false,
      "bindings": [
        {"specific_part": "3-1-7-702", "location_name": "...", "bound_at": "ISO8601"},
        ...
      ]
    }
    bound=false 时 bindings=[]
    """
```

#### 3.1.6 owner_binding_list（web 端管理页数据源）

```
@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])
def owner_binding_list(request):
    """
    web 端业主管理页"账号绑定"列数据源（REQ-OWNER-001）。
    权限：IsOperatorOrAbove（admin/operator 可见，user 不可见）。
    
    Response 200: {
      "results": [
        {
          "owner_id": int,
          "specific_part": "3-1-7-702",
          "bound_users": [
            {"username": "wx_abc12345", "bound_at": "ISO8601"}
          ]
        },
        ...
      ]
    }
    
    查询逻辑：
    OwnerInfo.objects.prefetch_related('user_bindings__user')
    每个 owner 的 user_bindings.filter(active=True) → 展示已绑定用户
    """
```

---

## MOD-180-04：miniapp 路由

### 4.1 文件：`api/urls_miniapp.py`

```python
"""
api/urls_miniapp.py — /api/miniapp/ 命名空间路由

安全约束：本文件内每个端点必须显式配置权限类（IsOwnerUser 或 AllowAny 或 IsOperatorOrAbove）。
禁止使用 IsAuthenticated（过于宽泛，operator 也会通过）。
新增端点时必须同步在本文件注释中说明权限类选择理由。
"""
from django.urls import path
from . import views_miniapp

urlpatterns = [
    path('auth/register/',   views_miniapp.miniapp_register,      name='miniapp-register'),
    path('auth/wechat/',     views_miniapp.miniapp_wechat_login,   name='miniapp-wechat-login'),
    path('bind/',            views_miniapp.miniapp_bind,           name='miniapp-bind'),
    path('unbind/',          views_miniapp.miniapp_unbind,         name='miniapp-unbind'),
    path('bind/status/',     views_miniapp.miniapp_bind_status,    name='miniapp-bind-status'),
    path('admin/owner-bindings/', views_miniapp.owner_binding_list, name='miniapp-owner-binding-list'),
]
```

根路由（`freearkweb/urls.py`）新增：
```python
path('api/miniapp/', include('api.urls_miniapp')),
```
放置在现有 `path('api/', include('api.urls'))` 之后，避免路由遮蔽。

---

## MOD-180-05：UserScope

### 5.1 文件：`api/langgraph_chat/user_scope.py`（新建）

完整接口见 architecture_design.md 第 5.2 节。

### 5.2 构造函数

```python
def build_user_scope(user) -> 'UserScope | None':
    """
    从 Django User 对象构造 UserScope。
    admin/operator 返回 None（无限制，工具调用直通）。
    role=user 查询 OwnerUserBinding 活跃绑定集。
    
    注意：此函数在 consumers.py 中异步调用（sync_to_async 包装）。
    """
    from api.models import OwnerUserBinding
    if getattr(user, 'role', None) != 'user':
        return None
    parts = list(
        OwnerUserBinding.objects.filter(user=user, active=True)
        .select_related('owner')
        .values_list('owner__specific_part', flat=True)
    )
    return UserScope(role='user', bound_specific_parts=frozenset(parts))
```

---

## MOD-180-06：ScopeEnforcer

### 6.1 文件：`api/langgraph_chat/scope_enforcer.py`（新建）

完整实现见 architecture_design.md 第 5.3 节。

### 6.2 接口约定

```python
def check_and_enforce(
    tool_name: str,
    args: dict,
    user_scope: 'UserScope | None'
) -> tuple[dict | None, str | None]:
    """
    Returns:
      (new_args, None)    → 调用工具（args 可能已被 scope 修改）
      (None, message)     → 不调工具，将 message 作为 ToolMessage 回灌 LLM
    Raises:
      ScopeViolationError → 写操作越权（_gate 节点捕获）
    """
```

### 6.3 工具行为矩阵（user_scope.is_owner=True 时）

| 工具名 | 有 specific_part 且在范围内 | 有 specific_part 但越权 | 无 specific_part（单绑定） | 无 specific_part（多绑定） | 未绑定 |
|-------|---------------------------|------------------------|--------------------------|--------------------------|--------|
| `search_sanheng_knowledge` | 直通 | 直通 | 直通 | 直通 | 直通 |
| `get_dashboard_summary` | 屏蔽(返回提示) | 屏蔽 | 屏蔽 | 屏蔽 | 屏蔽 |
| `get_usage_daily` | 直通 | 拒绝+提示 | 自动注入 | 澄清追问 | 提示绑定 |
| `get_realtime_params` | 直通 | 拒绝+提示 | 自动注入 | 澄清追问 | 提示绑定 |
| `set_device_params` | 直通（进入 gate） | ScopeViolationError | 自动注入（进入 gate） | 澄清追问（不进 gate） | 提示绑定 |
| `trigger_refresh` | 直通（进入 gate） | ScopeViolationError | 自动注入（进入 gate） | 澄清追问（不进 gate） | 提示绑定 |
| `get_plc_status` | N/A | N/A | 注入 `_owner_specific_parts` | 注入 `_owner_specific_parts` | 提示绑定 |
| `get_fault_summary` | N/A | N/A | 注入 `_owner_specific_parts` | 注入 `_owner_specific_parts` | 提示绑定 |

---

## MOD-180-07：orchestrator.py 改造

### 7.1 State 扩展

```python
class State(TypedDict, total=False):
    # 原有字段（不变）
    messages: Annotated[List[BaseMessage], operator.add]
    plan: List[Tuple[str, str]]
    expert_results: Annotated[List[dict], operator.add]
    name: str
    query: str
    related_images: List[dict]
    vision_description: Optional[str]

    # v1.8.0 新增：用户数据访问范围上下文（Optional，None=无限制）
    user_scope: Optional[object]  # UserScope instance
```

### 7.2 _expert() 改造注入点

在 `_expert()` 方法中，定位到工具调用执行行（当前约第 332 行）：

```python
# 原代码（需保留上下文，精确定位）：
out = await t.ainvoke(tc["args"]) if t else {"error": "no tool"}

# 改为（完整替换该块）：
if t:
    _user_scope = state.get("user_scope")
    try:
        from .scope_enforcer import check_and_enforce, ScopeViolationError
        enforced_args, clarification = check_and_enforce(
            tc["name"], tc.get("args", {}), _user_scope)
    except ScopeViolationError as scope_err:
        enforced_args = None
        clarification = f"权限拒绝：您无权对该专有部分执行写操作。（{scope_err}）"
    if enforced_args is not None:
        out = await t.ainvoke(enforced_args)
    else:
        # 返回澄清/拒绝消息，ToolMessage 回灌 LLM，LLM 据此生成用户可见回复
        out = {"clarification": clarification, "scope_blocked": True}
else:
    out = {"error": "no tool"}
```

**注意**：`search_sanheng_knowledge` 工具的 `prepare_search_images_sink()` 调用（第 330-331 行）在 ScopeEnforcer 调用之前，因为 `search_sanheng_knowledge` 必然豁免，ScopeEnforcer 对其直通，不影响现有逻辑。

### 7.3 _gate() 写操作二次校验（REQ-ISO-003）

在 `_gate()` 方法的 `if approved:` 分支（当前约第 444 行）之前插入：

```python
# v1.8.0 新增：写操作执行前二次校验 specific_part 归属
_user_scope = state.get("user_scope")
if _user_scope is not None and _user_scope.is_owner:
    _sp = pw["args"].get("specific_part", "")
    if not _user_scope.allows(_sp):
        ans = (f"⚠️ 安全拦截：专有部分 {_sp} 不在您的绑定范围内，"
               f"写操作已中止。如有问题请联系管理员。")
        new_results.append({"expert": r["expert"], "answer": ans})
        continue  # 跳过后续的 execute_write 和 else 分支
```

### 7.4 _fan_out() State 传递

`_fan_out()` 构造 `Send` 时，需将 `user_scope` 传入子节点 State：

```python
def _fan_out(self, state: State):
    return [Send("expert", {
        "name": name,
        "query": q,
        "messages": [],
        "user_scope": state.get("user_scope"),  # v1.8.0 新增：透传 scope
    }) for name, q in state["plan"]]
```

---

## MOD-180-08：fa_tools.py 工具扩展

### 8.1 get_plc_status 扩展

```python
@tool
def get_plc_status(_owner_specific_parts: list = None) -> dict:
    """查询 PLC 在线/离线状态。
    _owner_specific_parts: 内部参数（不暴露给 LLM schema），非 None 时按列表过滤。
    无参数时（None）查询全部（admin/operator 路径，行为不变）。
    """
    return _call("freeark_get_plc_status", {
        "_owner_specific_parts": _owner_specific_parts
    })
```

**注意**：`@tool` 装饰器生成的 LLM schema 依赖函数签名；`_owner_specific_parts` 以下划线开头，LLM 通常不会填此参数（符合"不暴露给 LLM"的设计意图）。但为安全起见，ScopeEnforcer 在注入该参数时由代码强制写入，不依赖 LLM。

对应的 skill handler（`freeark_get_plc_status`）需在 skill 层识别 `_owner_specific_parts` 参数并执行 `specific_part IN (...)` 过滤。（skill 改动在 module_design 中标记为实现约束，由 software-developer 实现）。

### 8.2 get_fault_summary 扩展

```python
@tool
def get_fault_summary(
    building: Optional[str] = None,
    unit: Optional[str] = None,
    _owner_specific_parts: list = None,  # 内部参数
) -> dict:
    """查询有故障的专有部分汇总（按故障数降序）。
    building/unit 可选过滤（admin/operator 路径）。
    _owner_specific_parts 非 None 时（user 路径），忽略 building/unit，
    按精确 specific_part 列表过滤（更严格）。
    """
    return _call("freeark_get_fault_summary", {
        "building": building,
        "unit": unit,
        "_owner_specific_parts": _owner_specific_parts,
    })
```

### 8.3 向后兼容保证

- 两个工具新增参数均有默认值 `None`，现有调用（不传该参数）行为完全不变
- `TOOLS_BY_EXPERT` 中的工具引用无需更新（Python 函数对象本身不变）
- 现有单测若直接调用这两个工具（不传 `_owner_specific_parts`），行为不变

---

## MOD-180-09：MiniAppChatConsumer

### 9.1 文件：`api/consumers.py`（末尾追加新类）

```python
# ── v1.8.0：微信小程序业主端聊天 Consumer ────────────────────────────────────
class MiniAppChatConsumer(ChatConsumer):
    """
    小程序业主端聊天 Consumer。
    
    与父类 ChatConsumer 的差异：
    1. connect()：允许 role='user' 连接（小程序业主有聊天权限）
    2. connect()：连接时预查 OwnerUserBinding，构造 self.user_scope
    3. _handle_chat()：stream_chat 调用时附带 user_scope
    
    所有其他逻辑（receive、disconnect、_pump、_ensure_session_created、
    _send_error 等）完全继承，零改动。
    
    WS 路由：/ws/miniapp/chat/
    """
    
    async def connect(self):
        # 初始化所有父类属性（复制父类 connect 开头的属性初始化块）
        self.chat_session = None
        self._pending_assistant_content = ''
        self._session_created = False
        self._first_round_done = False
        self._vision_persist_message = ''
        self.user_scope = None  # v1.8.0 新增

        query_string = self.scope.get('query_string', b'')
        params = parse_qs(query_string)
        token_bytes = params.get(b'token', [None])[0]

        if token_bytes is None:
            logger.warning('MiniAppChatConsumer: 缺少 token，拒绝')
            await self.close(code=4001)
            return

        token_key = token_bytes.decode('utf-8', errors='replace')
        user = await self._get_user_by_token(token_key)
        if user is None:
            logger.warning('MiniAppChatConsumer: token 无效，拒绝')
            await self.close(code=4001)
            return

        # 与父类不同：role=user 允许连接（小程序业主端专属）
        # role=admin/operator 也可连接（兼容管理员测试场景）
        # （不加 role=user 强制，允许 admin/operator 也用 miniapp ws 测试）

        self.user = user

        # 解析 session_key
        session_key_param_bytes = params.get(b'session_key', [None])[0]
        session_key_param = (
            session_key_param_bytes.decode('utf-8', errors='replace')
            if session_key_param_bytes else None
        )
        self.session_key = session_key_param or str(uuid.uuid4())

        # v1.8.0：预查绑定集合，构造 user_scope（DB 查询异步化）
        from .langgraph_chat.user_scope import build_user_scope
        self.user_scope = await sync_to_async(build_user_scope)(user)

        await self.accept()
        logger.info(
            'MiniAppChatConsumer: 连接接受 user=%s role=%s scope=%s',
            user.username, user.role,
            'owner' if self.user_scope else 'full',
        )

    async def _handle_chat(self, user_message: str, upload_id=None):
        """覆盖 _handle_chat：stream_chat 时附带 user_scope。"""
        # 与父类实现基本一致，仅在 adapter.stream_chat 调用处新增 user_scope 参数
        # 为避免重复大量代码，此处调用父类实现的辅助方法，仅修改关键调用点
        # [完整实现由 software-developer 参照父类 _handle_chat 实现，新增 user_scope 参数传递]
        ...
```

### 9.2 ASGI routing 注册

在 `freearkweb/routing.py`（或 `asgi.py` 中的 URL router）新增：

```python
from api.consumers import ChatConsumer, MiniAppChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/chat/$", ChatConsumer.as_asgi()),           # 现有，不变
    re_path(r"ws/miniapp/chat/$", MiniAppChatConsumer.as_asgi()),  # v1.8.0 新增
]
```

---

## MOD-180-10：adapter.py 扩展

### 10.1 stream_chat 签名扩展

```python
# 现有签名：
async def stream_chat(cls, message, session_key, upload_id=None, user_id=None)

# 扩展为：
async def stream_chat(cls, message, session_key, upload_id=None, user_id=None,
                      user_scope=None):  # v1.8.0 新增
    """
    user_scope: UserScope instance or None。
    非 None 时，注入到 LangGraph 初始 State payload 的 user_scope 字段。
    向后兼容：调用方不传则为 None（admin/operator 路径行为完全不变）。
    """
    orch = _get_orch()
    config = orch._cfg(session_key)

    # 构造初始 payload
    payload = {
        "messages": [HumanMessage(content=enhanced_message)],
        "vision_description": vision_description,
    }
    if user_scope is not None:  # v1.8.0 新增
        payload["user_scope"] = user_scope

    async for kind, text in _drive(orch, payload, config):
        yield (kind, text)
```

---

## MOD-180-11：小程序前端新增页面

### 11.1 新增页面/组件清单

| 页面/组件 | 路径 | 功能 |
|----------|------|------|
| 注册页 | `miniprogram/pages/register/register.vue` | 账号密码注册表单 |
| 微信登录页 | `miniprogram/pages/login/login.vue` | 现有页面扩展：新增"微信一键登录"按钮 |
| 绑定页 | `miniprogram/pages/bind/bind.vue` | 扫码/输入 MAC + 绑定状态展示 |
| 解绑页 | `miniprogram/pages/bind/unbind.vue` | 解绑操作 |

### 11.2 扫码实现

使用微信小程序原生 API `wx.scanCode()`，扫码结果 `result.result` 即为二维码内容（unique_id 字符串），直接传入绑定接口。

### 11.3 聊天页 WS 端点修改

`miniprogram/` 中聊天相关页面的 WS 连接地址：
- 原：`ws://${HOST}/ws/chat/?token=${token}`
- 改：`ws://${HOST}/ws/miniapp/chat/?token=${token}`

**仅小程序端修改**，web 端聊天页 WS 地址不变。

### 11.4 已有页面零影响说明

v1.5.0 已有页面（login、dashboard、monitoring、energy、maintenance、chat）：
- 不修改现有页面的业务逻辑
- 仅 login 页新增"微信登录"按钮选项（原有"账号密码登录"不变）
- 聊天页修改 WS 端点（字符串替换，无逻辑变化）

---

## MOD-180-12：web 端业主管理页

### 12.1 文件：`frontend/src/views/OwnerManagementView.vue`

**改动范围**：仅新增数据加载逻辑和一列表格列，现有所有列（specific_part、location_name、building、unit、floor、room_number、bind_status、ip_address、plc_ip_address、unique_id）不改动。

**新增内容**：
1. 在已有表格（`<el-table>`）末尾新增一列：
   ```html
   <el-table-column label="用户关联" width="120">
     <template #default="{ row }">
       <el-tag
         :type="getOwnerBindingTag(row.id).type"
         size="small"
       >{{ getOwnerBindingTag(row.id).text }}</el-tag>
     </template>
   </el-table-column>
   ```
2. 在 `data()` 中新增 `ownerBindings: {}`（Map: owner_id → [{username, bound_at}]）
3. 在 `mounted()` 中异步拉取 `GET /api/miniapp/admin/owner-bindings/`，填充 `ownerBindings`
4. 新增方法 `getOwnerBindingTag(ownerId)`：返回 `{type: 'success'|'info', text: '已关联'|'未关联'}`

**改动限制**：
- 现有 `bind_status` 列（设备绑定状态）：不改动，列标题和数据来源不变
- 现有搜索/过滤/编辑/同步逻辑：不改动
- 新增列的数据加载失败时（API 异常）：该列显示空白，不影响其他列和功能

---

## MOD-180-13：数据库迁移

### 13.1 文件命名

`api/migrations/0041_owner_user_wechat_binding.py`

（实际编号以 `python manage.py showmigrations` 输出的当前最新编号 +1 为准）

### 13.2 内容

```python
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0040_user_role_operator_update'),  # 当前最新，需核实
    ]

    operations = [
        migrations.CreateModel(
            name='WechatBinding',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='wechat_bindings',
                    to='api.CustomUser',
                    verbose_name='FreeArk 用户',
                )),
                ('openid', models.CharField(
                    db_index=True, max_length=128, unique=True,
                    verbose_name='微信 openid',
                )),
                ('unionid', models.CharField(
                    blank=True, max_length=128, null=True,
                    verbose_name='微信 unionid（可选）',
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='绑定时间',
                )),
            ],
            options={
                'verbose_name': '微信账号绑定',
                'verbose_name_plural': '微信账号绑定',
                'db_table': 'wechat_binding',
            },
        ),
        migrations.CreateModel(
            name='OwnerUserBinding',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='owner_bindings',
                    to='api.CustomUser',
                    verbose_name='FreeArk 用户',
                )),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='user_bindings',
                    to='api.OwnerInfo',
                    verbose_name='专有部分',
                )),
                ('active', models.BooleanField(
                    db_index=True, default=True, verbose_name='是否有效',
                )),
                ('bound_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='绑定时间',
                )),
                ('unbound_at', models.DateTimeField(
                    blank=True, null=True, verbose_name='解绑时间',
                )),
            ],
            options={
                'verbose_name': '业主账号绑定',
                'verbose_name_plural': '业主账号绑定',
                'db_table': 'owner_user_binding',
            },
        ),
        migrations.AddIndex(
            model_name='wechatbinding',
            index=models.Index(fields=['user'], name='wechat_bind_user_idx'),
        ),
        migrations.AddIndex(
            model_name='owneruserbinding',
            index=models.Index(fields=['user', 'active'], name='oub_user_active_idx'),
        ),
        migrations.AddIndex(
            model_name='owneruserbinding',
            index=models.Index(fields=['owner', 'active'], name='oub_owner_active_idx'),
        ),
    ]
```

---

## 模块间依赖关系

```
MOD-180-13 (迁移)
    ↑ 依赖
MOD-180-01 (数据模型)
    ↑ 依赖
MOD-180-03 (views_miniapp)  ←  MOD-180-04 (urls)
MOD-180-05 (UserScope)
    ↑ 依赖
MOD-180-06 (ScopeEnforcer)
    ↑ 依赖
MOD-180-07 (orchestrator)   ←  MOD-180-08 (fa_tools)
    ↑ 依赖
MOD-180-10 (adapter)
    ↑ 依赖
MOD-180-09 (MiniAppChatConsumer)
    ↑ 依赖（平行）
MOD-180-02 (middleware)
MOD-180-11 (小程序前端)      ←  MOD-180-12 (web 前端)
```

**实现顺序建议**（由 software-developer 参考）：
1. MOD-180-01 → MOD-180-13（数据基础）
2. MOD-180-02（中间件，风险最低，最先验证）
3. MOD-180-03 → MOD-180-04（miniapp API）
4. MOD-180-05 → MOD-180-06 → MOD-180-07 → MOD-180-08 → MOD-180-10 → MOD-180-09（聊天隔离链，按依赖顺序）
5. MOD-180-11 → MOD-180-12（前端，最后）

---

*文档结束*
