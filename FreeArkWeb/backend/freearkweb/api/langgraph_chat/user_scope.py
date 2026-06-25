"""
api.langgraph_chat.user_scope — 用户数据访问范围上下文（v1.8.0_miniprogram_owner_account）

UserScope 是在 LangGraph 会话生命周期内不可变的数据类，携带当前用户的角色和
绑定的专有部分集合。admin/operator 的 user_scope=None（无限制，全程直通）。
role=user 的 user_scope 在 MiniAppChatConsumer.connect() 时构造，经 adapter
注入 LangGraph State["user_scope"] 字段，供 ScopeEnforcer 在工具调用前使用。

设计约束（REQ-ISO-001 至 REQ-ISO-004，NFR-ISO-001）：
  - frozen=True 确保 scope 在会话内不可变
  - build_user_scope() 必须通过 sync_to_async 调用（在异步 Consumer 上下文中）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UserScope:
    """当前会话用户的数据访问范围。

    Attributes:
        role: 用户角色字符串（'user' / 'operator' / 'admin'）
        bound_specific_parts: 该用户当前 active 绑定的所有 specific_part 集合
        is_owner: role == 'user' 的快捷属性（frozen，初始化后不可变）
    """
    role: str
    bound_specific_parts: frozenset  # frozenset[str]

    # frozen dataclass 不能在 __init__ 后赋值，用 __post_init__ + object.__setattr__
    is_owner: bool = field(init=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, 'is_owner', self.role == 'user')

    def allows(self, specific_part: str) -> bool:
        """判断 specific_part 是否在当前用户的允许范围内。

        admin/operator（is_owner=False）：始终返回 True（无限制）。
        role=user：仅当 specific_part 在 bound_specific_parts 内时返回 True。
        """
        if not self.is_owner:
            return True
        return specific_part in self.bound_specific_parts

    def is_unbound(self) -> bool:
        """当前用户是 role=user 且没有任何 active 绑定。"""
        return self.is_owner and len(self.bound_specific_parts) == 0

    def is_multi_bound(self) -> bool:
        """当前用户绑定了超过一个专有部分。"""
        return self.is_owner and len(self.bound_specific_parts) > 1


def build_user_scope(user) -> 'UserScope | None':
    """从 Django User 对象构造 UserScope。

    admin/operator 返回 None（无限制，ScopeEnforcer 对 None 全程直通）。
    role=user 查询 OwnerUserBinding active 绑定集，构造 UserScope。

    注意：此函数执行 ORM 查询（同步），在异步 Consumer 中必须用 sync_to_async 包装：
        self.user_scope = await sync_to_async(build_user_scope)(user)
    """
    if getattr(user, 'role', None) != 'user':
        return None
    # 延迟导入，避免 App Registry 未就绪时被 import
    from api.models import OwnerUserBinding
    parts = list(
        OwnerUserBinding.objects.filter(user=user, active=True)
        .select_related('owner')
        .values_list('owner__specific_part', flat=True)
    )
    return UserScope(role='user', bound_specific_parts=frozenset(parts))
