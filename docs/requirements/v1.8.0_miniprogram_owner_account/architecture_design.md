# 架构设计文档（Architecture Design）

**版本**：v1.8.0_miniprogram_owner_account  
**日期**：2026-06-25  
**状态**：DRAFT — 待主控门控评审通过后转 APPROVED  
**作者**：system-architect (SDLC Agent)  
**依赖**：requirements_spec.md (APPROVED)，user_stories.md (APPROVED)

---

## 目录

1. 架构总览
2. 架构决策记录（ADR）
3. 数据模型设计
4. API 层设计（命名空间与鉴权）
5. 数据隔离机制（最高风险）
6. 聊天 WS 通道改造
7. 微信登录流程
8. 零 web 回归边界
9. 迁移策略

---

## 1. 架构总览

### 1.1 新增组件全景

```
微信小程序（uni-app，miniprogram/）
    │
    ├── HTTP  →  /api/miniapp/         ← 新增命名空间（Django urls_miniapp.py）
    │              ├── auth/register/       新端点：账号密码注册
    │              ├── auth/wechat/         新端点：微信一键登录
    │              ├── bind/                新端点：绑定专有部分
    │              ├── unbind/              新端点：解绑
    │              └── bind/status/         新端点：查询绑定状态
    │
    └── WS   →  /ws/miniapp/chat/     ← 新增 MiniAppChatConsumer（继承 ChatConsumer，role=user 放行）
                   ↓
            LangGraph 编排图（Orchestrator）
                   ↓  ← 新增：user_scope 注入层（ScopedOrchestrator）
            工具调用层（fa_tools.py）
                   ↓  ← 新增：工具包装器（ScopedToolWrapper）强制过滤

新增数据模型（Django ORM）：
    OwnerUserBinding    User ↔ OwnerInfo 多对多绑定关系
    WechatBinding       User ↔ WeChat openid 关联

现有模型（只读引用，不改结构）：
    CustomUser          + 聊天 WS 鉴权逻辑改造（consumers.py）
    OwnerInfo           只读引用 unique_id、specific_part
    UserRoleApiGuard    中间件扩展（路径前缀放行）
```

### 1.2 核心设计原则

- **零侵入现有 web 路径**：所有 user 专属 API 在新命名空间 `/api/miniapp/`，不触碰 `/api/` 现有路由、序列化器、视图类。
- **数据隔离代码强制**：specific_part 范围过滤在工具包装层（Python 代码）强制注入，不依赖 LLM 提示词。
- **聊天 WS 改造最小化**：仅在 `ChatConsumer.connect()` 增加"小程序路径 + role=user 的通过条件"，其余逻辑不动。
- **迁移无破坏**：仅新增表和字段，不修改现有表结构，现有 1702 测试不新增失败。

---

## 2. 架构决策记录（ADR）

### ADR-180-01：API 命名空间隔离

**决策**：所有 role=user 专属接口放在 `/api/miniapp/` 命名空间，由独立的 `urls_miniapp.py` 文件注册，并在根 `urls.py`（`freearkweb/urls.py`）中 include。

**备选方案**：
- 方案 A（已选）：独立命名空间 `/api/miniapp/`。中间件对该前缀整体放行，各端点自配 `IsOwnerUser` 权限类。
- 方案 B：将 user 白名单精确追加到现有 `ALLOWLIST`（6 条 → N 条）。每新增端点都要手动维护白名单，易遗漏，维护成本高。

**理由**：方案 A 的"路径前缀 + 端点自守"比"全局精确白名单"更可维护，且安全边界更清晰（未配 IsOwnerUser 的端点默认对 user 不可访问）。

**风险**：端点忘记配权限类会导致越权。缓解：在 `urls_miniapp.py` 文件头加注释约束 + 代码审查检查。

---

### ADR-180-02：数据隔离注入机制

**决策**：在 `Orchestrator._expert()` 方法调用工具的那一行（`out = await t.ainvoke(tc["args"])`）之前，增加一个 `ScopeEnforcer` 拦截层，在 LangGraph State 中携带当前用户的绑定 `specific_parts` 集合，在工具调用前对参数强制校验/覆盖。

**实现机制**：
1. `State` TypedDict 新增字段 `user_scope: Optional[UserScope]`（`UserScope` = dataclass，含 `role`、`bound_specific_parts: frozenset[str]`、`is_owner: bool`）。
2. `ChatConsumer._handle_chat()` 在构造聊天 payload 时，若 `user.role == 'user'`，从 `OwnerUserBinding` 查出该用户所有 active 绑定并写入初始 State。
3. `Orchestrator._expert()` 在调用工具前，调用 `ScopeEnforcer.check_and_enforce(tool_name, args, user_scope)` 方法，对受限工具强制覆盖 / 拒绝参数。
4. `search_sanheng_knowledge` 豁免，不经过 ScopeEnforcer。

**备选方案**：
- 方案 A（已选）：State 携带 scope + 工具调用前拦截（进程内，零网络开销）。
- 方案 B：在工具函数内部（`fa_tools.py`）从 ContextVar 读 scope（类似 `_last_search_images_var` 的机制）。缺点：ContextVar 在 `ainvoke` 的 `copy_context` 副本中失效（已知坑，见 fa_tools.py 注释），不可靠。
- 方案 C：LLM 提示词约束。明确排除（NFR-ISO-001）。

**理由**：State 字段是 LangGraph 原生的跨节点传递机制，在 `_expert()` 同步调用路径中读取 State 是可靠的。方案 B 有已知的 ContextVar 失效问题。

---

### ADR-180-03：多绑定场景的"目标房间"确定

**决策**：user 绑多个 specific_part 时，系统无法自动猜测当前查询针对哪个房间。处理策略：

1. **单绑定**：直接注入唯一 specific_part，无需追问。
2. **多绑定 + 用户消息中明确提到房号/楼层/坐落**：路由器/专家从消息中提取并校验该 specific_part 是否在用户绑定集合内，在集合内则使用，不在集合内则拒绝并提示。
3. **多绑定 + 用户消息中无明确指向**：
   - 若查询是通用性的（如"我家温度"），系统询问用户"您绑定了多套房产，请告知您想查询哪套（列出 specific_part 列表）"，等待用户回复后再调用工具。
   - 实现：在 `ScopeEnforcer` 检测到 `specific_part` 参数不确定且 `len(bound_specific_parts) > 1` 时，**不调用工具**，改为生成一条澄清消息写入 `State.messages`，让 LLM 在下一步基于此澄清继续对话。
4. **写操作禁止批量**：`set_device_params` 和 `trigger_refresh` 的 `specific_part` 必须唯一、明确，`ScopeEnforcer` 对多绑定写操作强制要求用户先指定目标，否则拒绝执行并提示（不进入 interrupt 门）。

---

### ADR-180-04：ChatConsumer 聊天 WS 鉴权改造

**决策**：在 `ChatConsumer.connect()` 中，将现有的"role=user 一律拒绝"改为"role=user 且连接路径为 `/ws/miniapp/chat/`（小程序专属 WS 路径）则允许"。

**具体改动**：
- 新增 WS 路由 `/ws/miniapp/chat/` → `MiniAppChatConsumer`（继承 `ChatConsumer`，覆盖 `connect()` 鉴权逻辑）。
- 原有 `/ws/chat/` 路由不变，`ChatConsumer` 的 role=user 拦截逻辑不动。
- `MiniAppChatConsumer.connect()` 允许 role=user 连接，在构建 payload 时注入 `user_scope`。

**理由**：不修改现有 `ChatConsumer`，零影响 web 端聊天；两个 Consumer 并列，职责清晰。

---

### ADR-180-05：WechatBinding 与 OwnerUserBinding 表设计

**决策**：两个关联表均新建，不修改 `CustomUser` 或 `OwnerInfo` 表结构。

- `WechatBinding`：user FK + openid（unique）+ unionid（nullable）+ created_at
- `OwnerUserBinding`：user FK + owner FK + bound_at + active（bool）

**理由**：符合需求决策 1（多对多）和 2（零侵入 CustomUser）。active 标志允许解绑记录保留历史，支持未来审计。

---

## 3. 数据模型设计

### 3.1 WechatBinding

```python
# api/models.py 末尾新增（不修改现有任何模型）

class WechatBinding(models.Model):
    """微信账号与 FreeArk User 的绑定关系。
    每个 openid 对应唯一一个 User（unique=True），但一个 User 可有多个 openid（
    不同小程序 appid 场景，当前仅单 appid，故实际也唯一，保留扩展余地）。
    """
    user = models.ForeignKey(
        'api.CustomUser',
        on_delete=models.CASCADE,
        related_name='wechat_bindings',
        verbose_name='FreeArk 用户',
    )
    openid = models.CharField(
        max_length=128, unique=True, db_index=True, verbose_name='微信 openid',
    )
    unionid = models.CharField(
        max_length=128, blank=True, null=True, verbose_name='微信 unionid（可选）',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='绑定时间')

    class Meta:
        db_table = 'wechat_binding'
        verbose_name = '微信账号绑定'
        verbose_name_plural = '微信账号绑定'
        indexes = [
            models.Index(fields=['user'], name='wechat_bind_user_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} → openid:{self.openid[:8]}..."
```

### 3.2 OwnerUserBinding

```python
class OwnerUserBinding(models.Model):
    """业主专有部分与 FreeArk User 的多对多绑定关系（含活跃/解绑状态）。
    
    多对多：一个 user 可绑多个 owner（多套房产），一个 owner 可被多个 user 绑定（家庭成员）。
    active=False 表示已解绑（保留历史记录，不物理删除）。
    active=True 的记录构成当前用户的数据访问范围。
    """
    user = models.ForeignKey(
        'api.CustomUser',
        on_delete=models.CASCADE,
        related_name='owner_bindings',
        verbose_name='FreeArk 用户',
    )
    owner = models.ForeignKey(
        'api.OwnerInfo',
        on_delete=models.PROTECT,          # OwnerInfo 不允许被级联删除（数据资产）
        related_name='user_bindings',
        verbose_name='专有部分',
    )
    active = models.BooleanField(
        default=True, db_index=True, verbose_name='是否有效',
    )
    bound_at = models.DateTimeField(auto_now_add=True, verbose_name='绑定时间')
    unbound_at = models.DateTimeField(
        null=True, blank=True, verbose_name='解绑时间',
    )

    class Meta:
        db_table = 'owner_user_binding'
        verbose_name = '业主账号绑定'
        verbose_name_plural = '业主账号绑定'
        indexes = [
            models.Index(fields=['user', 'active'], name='oub_user_active_idx'),
            models.Index(fields=['owner', 'active'], name='oub_owner_active_idx'),
        ]
        # 同一用户对同一 owner 同时最多一条 active 记录（解绑后可重绑，但不重叠）
        # 不用 unique_together(user, owner)：允许先绑、解绑、再绑（历史多条）
        # 注意：应用层在绑定前先 filter(user=u, owner=o, active=True) 判断是否已绑

    def __str__(self):
        status = 'ACTIVE' if self.active else 'UNBOUND'
        return f"{self.user.username} → {self.owner.specific_part} [{status}]"
```

### 3.3 与现有表的关系图

```
CustomUser (api_customuser)
    │ FK (CASCADE)
    ├── WechatBinding (wechat_binding)          [新]
    │       openid (unique) → 微信一键登录
    │
    └── OwnerUserBinding (owner_user_binding)   [新]
            │ FK (PROTECT)
            └── OwnerInfo (owner_info)          [现有，只读引用]
                    specific_part ← 数据隔离过滤键
                    unique_id     ← screenMAC，绑定时校验输入
                    bind_status   ← 设备绑定状态，不改语义，不写入
```

### 3.4 现有 OwnerInfo 字段语义保护

`OwnerInfo.bind_status`（"已绑定"/"未绑定"）：本版本不读不写，业务逻辑完全不引用，web 页面原有展示不变。账号绑定状态通过 `OwnerUserBinding.active` 字段体现，web 展示层通过 JOIN 查询独立列呈现。

---

## 4. API 层设计

### 4.1 新增文件结构

```
FreeArkWeb/backend/freearkweb/api/
    ├── views_miniapp.py          # 新建：所有 /api/miniapp/ 视图
    ├── urls_miniapp.py           # 新建：miniapp 路由表
    └── (现有文件只改动 middleware.py、consumers.py、urls.py 的 include 行)

FreeArkWeb/backend/freearkweb/freearkweb/
    └── urls.py                   # 根路由：新增 include('api.urls_miniapp')
                                  # 和 /ws/miniapp/chat/ WS 路由
```

### 4.2 urls_miniapp.py 结构

```python
# api/urls_miniapp.py
from django.urls import path
from . import views_miniapp

urlpatterns = [
    # 注册与微信登录（AllowAny，但视图层强制 role=user）
    path('auth/register/',   views_miniapp.miniapp_register,    name='miniapp-register'),
    path('auth/wechat/',     views_miniapp.miniapp_wechat_login, name='miniapp-wechat-login'),

    # 绑定操作（IsOwnerUser）
    path('bind/',            views_miniapp.miniapp_bind,         name='miniapp-bind'),
    path('unbind/',          views_miniapp.miniapp_unbind,       name='miniapp-unbind'),
    path('bind/status/',     views_miniapp.miniapp_bind_status,  name='miniapp-bind-status'),

    # 业主管理页"账号绑定"数据（IsOperatorOrAbove，供 web admin/operator 查询）
    path('admin/owner-bindings/', views_miniapp.owner_binding_list, name='miniapp-owner-binding-list'),
]
```

根路由注册：`path('api/miniapp/', include('api.urls_miniapp'))`

### 4.3 鉴权类 IsOwnerUser

```python
# api/views.py 末尾新增（与现有 IsAdminUser、IsOperatorOrAbove 并列）

class IsOwnerUser(permissions.BasePermission):
    """v1.8.0: 仅允许 role='user'（普通业主）且已登录的用户访问。
    用于 /api/miniapp/ 端点的精细权限控制。"""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) == 'user'
        )
```

### 4.4 UserRoleApiGuardMiddleware 最小改动

仅在 `_should_block()` 方法中新增一行路径前缀判断：

```python
def _should_block(self, request):
    path = request.path
    if not path.startswith('/api/'):
        return False
    if path in self.ALLOWLIST:
        return False
    # v1.8.0 新增：/api/miniapp/ 前缀整体放行，各端点自配权限类
    if path.startswith('/api/miniapp/'):
        return False
    user = self._resolve_token_user(request)
    return user is not None and getattr(user, 'role', None) == 'user'
```

**改动量**：3 行代码（1 行注释 + 2 行 if），不改动 `ALLOWLIST`，不影响现有 6 条精确白名单，不影响 web 端任何路径。

### 4.5 端点规格

| 端点 | 方法 | 权限类 | 频率限制 | 说明 |
|------|------|--------|---------|------|
| `/api/miniapp/auth/register/` | POST | AllowAny | 10/min/IP | 账号密码注册，role 强制 user |
| `/api/miniapp/auth/wechat/` | POST | AllowAny | 20/min/IP | code → openid → Token |
| `/api/miniapp/bind/` | POST | IsOwnerUser | 10/min/user | 扫码/MAC 绑定 |
| `/api/miniapp/unbind/` | POST | IsOwnerUser | 10/min/user | 自助解绑 |
| `/api/miniapp/bind/status/` | GET | IsOwnerUser | 60/min/user | 查询绑定状态 |
| `/api/miniapp/admin/owner-bindings/` | GET | IsOperatorOrAbove | 30/min/user | web 端管理页数据源 |

---

## 5. 数据隔离机制（最高风险，核心设计）

### 5.1 隔离架构全局图

```
ChatConsumer（MiniAppChatConsumer）
    │
    ├── connect()：Token 解析 → 确认 role=user → 查 OwnerUserBinding → 得到 bound_parts
    │
    └── _handle_chat()：构造初始 State
            {
              "messages": [HumanMessage(...)],
              "user_scope": UserScope(
                  role="user",
                  bound_specific_parts=frozenset({"3-1-7-702", ...}),
                  is_owner=True
              )
            }
                │
                ↓
        adapter.stream_chat(message, session_key, user_scope=user_scope)  # 新增参数
                │
                ↓
        graph.astream(payload, config)
                │
                ↓
        Orchestrator._expert()（节点函数，从 State 读取 user_scope）
                │
                ├── 调用工具前：ScopeEnforcer.check_and_enforce(tool_name, args, user_scope)
                │       ├── search_sanheng_knowledge → 豁免，直通
                │       ├── get_plc_status → 无 specific_part 参数，替换为按绑定集过滤的版本
                │       ├── get_fault_summary → 注入 specific_parts 过滤集
                │       ├── get_dashboard_summary → 对 user 屏蔽（OQ-09 决策）或限范围
                │       ├── get_usage_daily → 校验/覆盖 specific_part 必须在 bound_specific_parts 内
                │       ├── get_realtime_params → 同上
                │       ├── set_device_params → 严格校验；多绑定时必须明确指定且在集合内
                │       └── trigger_refresh → 同 set_device_params
                │
                └── interrupt 确认门（_gate 节点）：通过后执行 execute_write()
                        │
                        └── 执行前二次校验（REQ-ISO-003）：
                            verify_scope(pw["args"]["specific_part"], user_scope)
```

### 5.2 UserScope 数据类

```python
# api/langgraph_chat/user_scope.py（新建文件）

from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class UserScope:
    """当前会话用户的数据访问范围上下文。
    frozen=True 确保 scope 在会话生命周期内不可变。
    admin/operator 的 user_scope=None（无限制）。
    """
    role: str                                    # 'user' / 'operator' / 'admin'
    bound_specific_parts: frozenset              # frozenset[str]，active 绑定集合
    is_owner: bool = field(init=False)           # role == 'user'

    def __post_init__(self):
        object.__setattr__(self, 'is_owner', self.role == 'user')

    def allows(self, specific_part: str) -> bool:
        """判断 specific_part 是否在当前用户的允许范围内。"""
        if not self.is_owner:
            return True  # admin/operator 无限制（此方法对非 owner 不应被调用）
        return specific_part in self.bound_specific_parts

    def is_unbound(self) -> bool:
        return self.is_owner and len(self.bound_specific_parts) == 0

    def is_multi_bound(self) -> bool:
        return self.is_owner and len(self.bound_specific_parts) > 1
```

### 5.3 ScopeEnforcer

```python
# api/langgraph_chat/scope_enforcer.py（新建文件）

"""
ScopeEnforcer — 工具调用前的数据范围强制检查器（REQ-ISO-001 至 REQ-ISO-004）

调用时机：Orchestrator._expert() 中，out = await t.ainvoke(tc["args"]) 前
返回值：
  - (args_possibly_modified, None)       允许调用，args 可能已被覆盖
  - (None, "澄清消息文本")                不允许调用，返回澄清消息代替工具调用
  - raises ScopeViolationError           严重越权（写操作 specific_part 不在范围内）
"""

# 豁免工具集（无数据访问，仅知识检索）
SCOPE_EXEMPT_TOOLS = frozenset({"search_sanheng_knowledge"})

# 带 specific_part 参数的工具（需校验/覆盖）
SCOPED_SINGLE_PART_TOOLS = frozenset({
    "get_usage_daily", "get_realtime_params",
    "set_device_params", "trigger_refresh",
})

# 全局汇总工具（对 user 屏蔽）
GLOBAL_SUMMARY_TOOLS = frozenset({"get_dashboard_summary"})

# 带 building/unit 过滤的工具（需替换为 specific_parts 集过滤）
FILTERED_SUMMARY_TOOLS = frozenset({"get_fault_summary", "get_plc_status"})

# 写工具（execute_write 二次校验的目标集合，供 _gate 节点引用）
WRITE_TOOLS = frozenset({"set_device_params", "trigger_refresh"})


class ScopeViolationError(Exception):
    """写操作越权时抛出（specific_part 不在用户绑定集内）。"""
    pass


def check_and_enforce(tool_name: str, args: dict, user_scope) -> tuple:
    """
    返回 (new_args_or_None, clarification_message_or_None)
    - new_args 非 None → 允许调用（args 可能已被 scope 修改）
    - new_args 为 None → 不调用工具，clarification_message 作为 ToolMessage 内容回灌
    - 抛 ScopeViolationError → 写操作越权

    user_scope 为 None 时（admin/operator）直通所有工具。
    """
    if user_scope is None or not user_scope.is_owner:
        return args, None  # admin/operator：无限制，直通

    if tool_name in SCOPE_EXEMPT_TOOLS:
        return args, None  # 三恒知识：豁免

    if user_scope.is_unbound():
        return None, "您尚未绑定任何专有部分，无法查询设备数据。请先在小程序完成绑定。"

    bound = user_scope.bound_specific_parts

    # 全局汇总工具：对 user 屏蔽
    if tool_name in GLOBAL_SUMMARY_TOOLS:
        return None, "全局看板数据仅供运维人员查阅，您可以查询您自己专有部分的详细数据。"

    # 带 specific_part 参数的工具
    if tool_name in SCOPED_SINGLE_PART_TOOLS:
        sp = (args or {}).get("specific_part", "")
        if sp and sp not in bound:
            if tool_name in WRITE_TOOLS:
                raise ScopeViolationError(
                    f"写操作越权：{sp} 不在用户绑定范围 {bound} 内")
            # 只读工具：LLM 填了不在范围内的 specific_part，覆盖为提示
            return None, f"您无权访问 {sp} 的数据。您可以查询的专有部分为：{sorted(bound)}。"
        if not sp:
            if len(bound) == 1:
                # 单绑定：自动注入
                new_args = dict(args or {})
                new_args["specific_part"] = next(iter(bound))
                return new_args, None
            else:
                # 多绑定：需要澄清
                return None, (
                    f"您绑定了多套房产：{sorted(bound)}，请告知您想查询哪一套？"
                )
        return args, None  # sp 在范围内，直通

    # 全局汇总工具（get_fault_summary / get_plc_status）：注入绑定集过滤
    if tool_name in FILTERED_SUMMARY_TOOLS:
        # 工具当前接受 building/unit 参数；对 user 改为注入 specific_parts 集合
        # 注意：工具签名需在 fa_tools.py 中扩展（module_design.md 中定义）
        new_args = dict(args or {})
        new_args["_owner_specific_parts"] = list(bound)  # 扩展参数，工具层识别
        return new_args, None

    return args, None  # 未知工具：默认直通（保守）
```

### 5.4 State 扩展与 _expert 改造注入点

在 `orchestrator.py` 中：

1. `State` TypedDict 新增字段：
   ```python
   user_scope: Optional[object]  # UserScope instance or None
   ```

2. `_expert()` 方法中工具调用处（第 332 行附近）插入 ScopeEnforcer 调用：
   ```python
   # 原代码：
   out = await t.ainvoke(tc["args"]) if t else {"error": "no tool"}

   # 改为：
   if t:
       from .scope_enforcer import check_and_enforce, ScopeViolationError
       user_scope = state.get("user_scope")
       try:
           enforced_args, clarification = check_and_enforce(
               tc["name"], tc.get("args", {}), user_scope)
       except ScopeViolationError as e:
           out = {"error": f"权限拒绝：{e}"}
           enforced_args = None
       if enforced_args is not None:
           out = await t.ainvoke(enforced_args)
       elif clarification:
           out = {"clarification": clarification, "scope_blocked": True}
   else:
       out = {"error": "no tool"}
   ```

3. `_gate()` 节点（execute_write 前）的二次校验（REQ-ISO-003）：
   ```python
   # 在 execute_write 调用前插入：
   user_scope = state.get("user_scope")
   if user_scope and user_scope.is_owner:
       sp = pw["args"].get("specific_part", "")
       if not user_scope.allows(sp):
           ans = f"⚠️ 写操作越权（{sp} 不在您的绑定范围内），已中止。"
           new_results.append({"expert": r["expert"], "answer": ans})
           continue  # 跳过 execute_write
   out = await asyncio.to_thread(execute_write, ...)
   ```

### 5.5 巡检专家工具扩展（get_plc_status / get_fault_summary）

当前 `get_plc_status()` 无参数，`get_fault_summary(building, unit)` 按楼单元过滤。两个工具需要在 `fa_tools.py` 中扩展，新增 `_owner_specific_parts` 私有参数（以下划线开头，不暴露给 LLM schema），工具体内识别该参数后执行 specific_part 级精确过滤：

- `get_plc_status(_owner_specific_parts=None)`：若非 None，只返回 `PLCConnectionStatus` 中 `specific_part IN _owner_specific_parts` 的记录。
- `get_fault_summary(_owner_specific_parts=None, building=None, unit=None)`：若非 None，过滤条件改为 `FaultEvent.specific_part IN _owner_specific_parts`，忽略 building/unit（building/unit 范围更宽，不安全）。

---

## 6. 聊天 WS 通道改造

### 6.1 新增 MiniAppChatConsumer

```python
# api/consumers.py 末尾新增（不修改现有 ChatConsumer）

class MiniAppChatConsumer(ChatConsumer):
    """v1.8.0：微信小程序业主端聊天 Consumer。
    
    与 ChatConsumer 的唯一差异：
    1. connect() 允许 role='user' 连接（小程序业主有聊天权限）
    2. _handle_chat() 在构造 payload 时注入 user_scope
    
    所有其他方法（receive、disconnect、_pump 等）完全继承，零改动。
    """

    async def connect(self):
        """覆盖 connect()：role=user 允许连接（小程序端专属）。"""
        # 复用父类初始化逻辑，但去掉 role=user 拦截
        # [详见 module_design.md 中完整实现]
        ...

    async def _handle_chat(self, user_message: str, upload_id=None):
        """覆盖 _handle_chat()：注入 user_scope 到 State。"""
        # 查询当前 user 的 active OwnerUserBinding
        # 构造 UserScope，附加到 stream_chat payload
        ...
```

### 6.2 WS 路由注册

在 `freearkweb/asgi.py`（或 `routing.py`）中新增：
```python
path("ws/miniapp/chat/", MiniAppChatConsumer.as_asgi())
```

原有 `ws/chat/` 路由不变。

### 6.3 小程序前端 WS 端点

小程序 `miniprogram/` 中聊天页面的 WS 连接从 `ws/chat/` 改为 `ws/miniapp/chat/`。

---

## 7. 微信登录流程

### 7.1 时序图

```
小程序前端                    后端 /api/miniapp/auth/wechat/         微信服务器
    │                                    │                               │
    │── wx.login() ────────────────────> │（小程序 JS SDK）               │
    │<── code ──────────────────────────│                               │
    │                                    │                               │
    │── POST {code} ────────────────────>│                               │
    │                                    │─ GET code2session(code) ─────>│
    │                                    │                               │
    │                                    │<─ {openid, session_key, [unionid]}─│
    │                                    │                               │
    │                                    │── 查 WechatBinding.openid      │
    │                                    │    存在 → 返回关联 User 的 Token  │
    │                                    │    不存在 → 创建 User + WechatBinding │
    │                                    │             → 返回 Token       │
    │                                    │                               │
    │<── {token, user: {username, role}} │                               │
```

### 7.2 微信 API 调用

微信 code2session 端点：  
`GET https://api.weixin.qq.com/sns/jscode2session?appid={APPID}&secret={SECRET}&js_code={code}&grant_type=authorization_code`

后端 settings 注入（`.env` 文件，不入 git）：
```
WECHAT_MINIAPP_APPID=wx...
WECHAT_MINIAPP_SECRET=...
```

Django settings 读取：
```python
WECHAT_MINIAPP_APPID = os.environ.get('WECHAT_MINIAPP_APPID', '')
WECHAT_MINIAPP_SECRET = os.environ.get('WECHAT_MINIAPP_SECRET', '')
```

### 7.3 Token 签发

微信登录成功后，与账号密码登录路径完全相同：
```python
token, _ = Token.objects.get_or_create(user=user)
TokenActivity.objects.update_or_create(token=token, defaults={'last_active_at': now()})
return Response({'token': token.key, 'user': {'username': user.username, 'role': user.role}})
```
复用现有 `rest_framework.authtoken.Token`，小程序 WS 连接鉴权路径不变（C-04 满足）。

---

## 8. 零 web 回归边界

### 8.1 受影响现有文件清单及改动边界

| 文件 | 改动类型 | 改动内容 | 影响评估 |
|------|---------|---------|---------|
| `api/middleware.py` | 修改 | `_should_block()` 新增 3 行（路径前缀放行） | 低风险：仅新增 if 分支，现有 6 条白名单与拦截逻辑完全不变 |
| `api/consumers.py` | 新增 | 末尾新增 `MiniAppChatConsumer` 类（继承 ChatConsumer） | 零影响：不修改 ChatConsumer，仅追加新类 |
| `api/models.py` | 新增 | 末尾新增 `WechatBinding`、`OwnerUserBinding` 两个模型 | 零影响：新增模型不改现有 ORM |
| `api/langgraph_chat/orchestrator.py` | 修改 | State 新增 `user_scope` 字段（Optional，默认 None）；`_expert()` 工具调用处插入 scope 检查（约 15 行）；`_gate()` 插入写操作二次校验（约 8 行） | 低风险：user_scope=None 时（admin/operator）所有判断直通，行为与现在完全一致 |
| `api/langgraph_chat/fa_tools.py` | 修改 | `get_plc_status()`、`get_fault_summary()` 签名新增 `_owner_specific_parts=None` 可选参数（向后兼容） | 低风险：新参数默认 None，现有调用路径不传该参数，行为不变 |
| `freearkweb/urls.py` | 修改 | 新增 `include('api.urls_miniapp')` 和 WS 路由 | 低风险：仅追加路由，现有路由不动 |
| `frontend/src/views/OwnerManagementView.vue` | 修改 | 新增"账号绑定"列（从 `/api/miniapp/admin/owner-bindings/` 获取数据），现有列不动 | 低风险：新增列，不修改现有列的数据源或展示逻辑 |

### 8.2 不受影响的现有文件（明确排除）

- 所有现有 `views_*.py` 文件：不修改
- 所有现有 `serializers.py` 中的序列化器：不修改
- 所有现有 migrations（0001-0040）：不修改，本版本新增 migration 041
- 现有 EXPERT_PROMPTS（`prompts.py`）：不修改（admin/operator 路径无变化）
- 现有 `router.py`：不修改
- 现有 `adapter.py`：`stream_chat` 签名新增可选参数 `user_scope=None`（向后兼容）

### 8.3 NFR-COMPAT-001 验证策略

- **中间件改动**：`UserRoleApiGuardMiddleware` 的 3 行改动须通过现有 `test_rbac_v160.py` 中所有测试，确认 admin/operator 路径不受影响。
- **orchestrator 改动**：`user_scope=None` 时（现有 admin/operator 测试场景）所有判断条件 `if user_scope is None or not user_scope.is_owner` 直通，输出与修改前一致。
- **fa_tools 签名扩展**：`_owner_specific_parts=None` 默认参数，现有调用（不传参）行为完全不变。

---

## 9. 迁移策略

### 9.1 新增迁移：0041_owner_user_wechat_binding

```python
# api/migrations/0041_owner_user_wechat_binding.py

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0040_...'),  # 当前最新迁移号（实际以 git 上最新为准）
    ]

    operations = [
        migrations.CreateModel(
            name='WechatBinding',
            fields=[...],  # 按 3.1 节定义
        ),
        migrations.CreateModel(
            name='OwnerUserBinding',
            fields=[...],  # 按 3.2 节定义
        ),
        # 索引由 Meta.indexes 自动生成，无需显式 AddIndex
    ]
```

### 9.2 迁移安全保证

- 纯 `CreateModel` 操作，不修改任何现有表结构
- MySQL 生产环境：`CREATE TABLE` 操作不锁现有表，迁移耗时极短
- SQLite 测试环境：等价行为
- 失败回滚：`DROP TABLE wechat_binding; DROP TABLE owner_user_binding;` 即可，对现有数据零影响

---

*文档结束。下一步：参见 module_design.md 获取各模块的接口规格与实现约束。*
