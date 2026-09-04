"""
api.langgraph_chat.scope_enforcer — 工具调用前的数据范围强制检查器
（v1.8.0_miniprogram_owner_account，REQ-ISO-001 至 REQ-ISO-004，NFR-ISO-001）

调用时机：Orchestrator._expert() 中每次 tool.ainvoke() 之前。
调用方：orchestrator.py

设计约束：
  - 过滤由代码强制，不依赖 LLM 提示词（NFR-ISO-001）
  - user_scope=None（admin/operator）时直通所有工具，行为与 v1.7.0 逐字一致
  - search_sanheng_knowledge 豁免（REQ-ISO-004）
  - 写操作越权时抛 ScopeViolationError（_gate 节点捕获，REQ-ISO-003）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user_scope import UserScope

# ── 工具分类常量 ─────────────────────────────────────────────────────────────

# 豁免工具集：纯知识检索，无业主私有数据（REQ-ISO-004）
SCOPE_EXEMPT_TOOLS: frozenset = frozenset({'search_sanheng_knowledge'})

# 带 specific_part 参数的工具（需校验/覆盖）
SCOPED_SINGLE_PART_TOOLS: frozenset = frozenset({
    'get_usage_daily',
    'get_realtime_params',
    'get_device_params',       # v1.13.0 P0-2b：取设备可写参数白名单
    'set_device_params',
    'trigger_refresh',
})

# 全局汇总工具（对 user 屏蔽，OQ-09 决策）
GLOBAL_SUMMARY_TOOLS: frozenset = frozenset({'get_dashboard_summary'})

# 带 building/unit 过滤的全局列表工具（需注入 _owner_specific_parts）
FILTERED_SUMMARY_TOOLS: frozenset = frozenset({'get_fault_summary', 'get_plc_status'})

# 写工具集（_gate 二次校验用，REQ-ISO-003）
WRITE_TOOLS: frozenset = frozenset({
    'set_device_params',
    'trigger_refresh',
    'set_persona',   # v1.13.0 P0-3：写入 user 账号 persona，需走确认门
})

# ── v1.13.0 P0 新增 3 个分类 ─────────────────────────────────────────────────

# 1. SCOPED_QUERY_TOOLS：按查询主键（如 batch_request_id）返回结果，
#    但每条记录含 specific_part，需要：
#    (a) ScopeEnforcer 侧注入 args['_bound_specific_parts'] 供工具实现做
#        返回级二次过滤（即使 LLM 猜对邻居的 batch_request_id，records
#        也会被全部过滤掉，等价返回空集）；
#    (b) 若参数中显式填了 specific_part，也额外校验 ∈ bound（防绕）。
#    典型：get_write_status（P0-2a 修复：之前 ORM 直查无归属过滤）
SCOPED_QUERY_TOOLS: frozenset = frozenset({
    'get_write_status',
})

# 2. OWNER_SELF_TOOLS：不涉及 specific_part，作用于「当前登录 user 自己账号」
#    的设置类工具。仅 user_scope.is_owner=True 允许；admin/operator 也不放行
#    （admin 身份去调会把 admin 自己的账号 persona 改了，语义错）。
#    ScopeEnforcer 侧注入 args['_user_id']=user_scope.user_id 供工具实现
#    直接 ORM 读写 user.persona 等字段，不走 HTTP 权限类。
#    典型：get_persona / set_persona（P0-3）
OWNER_SELF_TOOLS: frozenset = frozenset({
    'get_persona',
    'set_persona',
})

# 3. FILTERED_OWNER_WORKORDER_TOOLS：工单/巡检/账单等「未来会按 owner 关联」
#    的域，沿用 FILTERED_SUMMARY_TOOLS 的 _owner_specific_parts 注入模式，
#    只是目前还没有工具填进来，先留分类框架，避免后续工具漏分类走保守直通。
#    与 FILTERED_SUMMARY_TOOLS 共享同一套检查分支实现。
FILTERED_OWNER_WORKORDER_TOOLS: frozenset = frozenset()
# TODO(v1.14): 工单/巡检/账单工具上线时填入此处，如
#   frozenset({'get_workorders', 'get_inspection_reports', 'get_bills'})

# 合并所有「走 _owner_specific_parts 注入」的分类，避免检查分支写两处
_ALL_FILTERED_TOOLS: frozenset = FILTERED_SUMMARY_TOOLS | FILTERED_OWNER_WORKORDER_TOOLS

# P1-3：所有需要编排层注入下划线前缀内部参数
# （_owner_specific_parts / _bound_specific_parts / _user_id）的工具。
# orchestrator 据此决定是否绕过 LangChain StructuredTool schema（会剔除 _ 前缀参数）
# 直接调 tool.func()。单一真源：新增此类工具只需在这里登记，不用改 orchestrator。
UNDERSCORE_PARAM_TOOLS: frozenset = (
    _ALL_FILTERED_TOOLS | SCOPED_QUERY_TOOLS | OWNER_SELF_TOOLS
)


# ── 异常 ─────────────────────────────────────────────────────────────────────

class ScopeViolationError(Exception):
    """写操作 specific_part 不在用户绑定范围内时抛出。
    由 _gate 节点捕获，不向用户暴露内部细节。
    """
    pass


# ── 主入口 ───────────────────────────────────────────────────────────────────

def check_and_enforce(
    tool_name: str,
    args: dict,
    user_scope: 'UserScope | None',
) -> tuple:
    """工具调用前的范围检查与参数强制。

    Returns:
        (new_args, None)        → 允许调用工具（args 可能已被 scope 修改）
        (None, message: str)    → 不调用工具，将 message 作为 ToolMessage 内容回灌 LLM

    Raises:
        ScopeViolationError     → 写操作越权（_gate 节点捕获后向用户报错）

    当 user_scope 为 None（admin/operator）时，所有工具直通，行为与修改前完全一致。
    """
    # admin/operator：绝大多数工具直通；但 OWNER_SELF_TOOLS 拒绝（没有业主个人设置语义）
    if user_scope is None or not user_scope.is_owner:
        if tool_name in OWNER_SELF_TOOLS:
            return None, (
                '该功能仅对普通业主（个人中心的副官自称/称呼/语气等偏好）开放。'
                '若您需要给业主账号进行运维调整，请通过小程序后台管理页面操作。'
            )
        return args, None

    # 豁免工具：三恒知识库，直通
    if tool_name in SCOPE_EXEMPT_TOOLS:
        return args, None

    # OWNER_SELF_TOOLS：仅业主本人可调用，注入受信任 _user_id
    # （放在 is_unbound 之前，因为个人设置与绑定房间无关）
    if tool_name in OWNER_SELF_TOOLS:
        args = dict(args or {})
        uid = getattr(user_scope, 'user_id', None)
        if not uid:
            return None, '当前会话未关联业主账号，请重新登录。'
        args['_user_id'] = uid
        return args, None

    # 未绑定用户：设备/房间相关工具需要先绑定；个人设置不受此限制。
    if user_scope.is_unbound():
        return None, (
            '您尚未绑定任何专有部分，无法查询设备数据。'
            '请先在小程序"我的"页面完成绑定。'
        )

    bound = user_scope.bound_specific_parts

    # 全局汇总工具：对 user 屏蔽
    if tool_name in GLOBAL_SUMMARY_TOOLS:
        return None, (
            '全局看板数据仅供运维人员查阅，'
            '您可以向我询问您自己专有部分的详细数据（能耗、实时参数等）。'
        )

    # 带 specific_part 参数的工具（能耗/实时/设备写白名单/写操作）
    if tool_name in SCOPED_SINGLE_PART_TOOLS:
        args = dict(args or {})
        sp = args.get('specific_part', '')

        if sp:
            if sp not in bound:
                if tool_name in WRITE_TOOLS:
                    raise ScopeViolationError(
                        f'写操作越权：{sp} 不在用户绑定范围 {sorted(bound)} 内'
                    )
                return None, (
                    f'您无权访问专有部分 {sp} 的数据。'
                    f'您可以查询的专有部分为：{sorted(bound)}。'
                )
            return args, None
        else:
            if len(bound) == 1:
                args['specific_part'] = next(iter(bound))
                return args, None
            else:
                return None, (
                    f'您绑定了多套专有部分：{sorted(bound)}，'
                    '请告知您想查询哪一套（如"3-1-7-702"）？'
                )

    # 全局列表工具 + 未来工单类：注入 _owner_specific_parts
    if tool_name in _ALL_FILTERED_TOOLS:
        args = dict(args or {})
        args['_owner_specific_parts'] = list(bound)
        return args, None

    # SCOPED_QUERY_TOOLS：注入 _bound_specific_parts 做结果级过滤；显式 sp 额外校验
    if tool_name in SCOPED_QUERY_TOOLS:
        args = dict(args or {})
        explicit_sp = args.get('specific_part', '')
        if explicit_sp and explicit_sp not in bound:
            return None, (
                f'您无权查询专有部分 {explicit_sp} 的写记录。'
                f'可查询范围：{sorted(bound)}。'
            )
        args['_bound_specific_parts'] = list(bound)
        return args, None

    # 未知工具：保守直通（不阻塞，避免未来新增工具因漏分类而中断）
    return args, None


def verify_write_scope(specific_part: str, user_scope: 'UserScope | None') -> None:
    """_gate 节点 execute_write 前的二次校验（REQ-ISO-003）。"""
    if user_scope is None or not user_scope.is_owner:
        return
    if not user_scope.allows(specific_part):
        raise ScopeViolationError(
            f'写操作二次校验失败：{specific_part} 不在用户绑定范围 '
            f'{sorted(user_scope.bound_specific_parts)} 内'
        )


def verify_owner_self_scope(user_scope: 'UserScope | None') -> int:
    """确认门执行个人设置前的第二道身份校验，返回受信任的 User.pk。"""
    if user_scope is None or not user_scope.is_owner:
        raise ScopeViolationError('个人设置仅允许普通业主本人修改')
    user_id = getattr(user_scope, 'user_id', None)
    if not isinstance(user_id, int) or user_id <= 0:
        raise ScopeViolationError('当前会话未关联有效业主账号')
    return user_id
