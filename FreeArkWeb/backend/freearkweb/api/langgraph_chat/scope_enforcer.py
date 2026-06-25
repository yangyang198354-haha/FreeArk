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
    'set_device_params',
    'trigger_refresh',
})

# 全局汇总工具（对 user 屏蔽，OQ-09 决策）
GLOBAL_SUMMARY_TOOLS: frozenset = frozenset({'get_dashboard_summary'})

# 带 building/unit 过滤的全局列表工具（需注入 _owner_specific_parts）
FILTERED_SUMMARY_TOOLS: frozenset = frozenset({'get_fault_summary', 'get_plc_status'})

# 写工具集（_gate 二次校验用，REQ-ISO-003）
WRITE_TOOLS: frozenset = frozenset({'set_device_params', 'trigger_refresh'})


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
    # admin/operator：无限制，全程直通
    if user_scope is None or not user_scope.is_owner:
        return args, None

    # 豁免工具：三恒知识库，直通
    if tool_name in SCOPE_EXEMPT_TOOLS:
        return args, None

    # 未绑定用户：提示先绑定（三恒专家外所有工具）
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

    # 带 specific_part 参数的工具（能耗/实时/写操作）
    if tool_name in SCOPED_SINGLE_PART_TOOLS:
        args = dict(args or {})
        sp = args.get('specific_part', '')

        if sp:
            # LLM 填了某个 specific_part：校验是否在范围内
            if sp not in bound:
                if tool_name in WRITE_TOOLS:
                    raise ScopeViolationError(
                        f'写操作越权：{sp} 不在用户绑定范围 {sorted(bound)} 内'
                    )
                # 只读工具：提示并拒绝
                return None, (
                    f'您无权访问专有部分 {sp} 的数据。'
                    f'您可以查询的专有部分为：{sorted(bound)}。'
                )
            # sp 在范围内：直通（args 不变）
            return args, None
        else:
            # LLM 未填 specific_part
            if len(bound) == 1:
                # 单绑定：自动注入
                args['specific_part'] = next(iter(bound))
                return args, None
            else:
                # 多绑定：需要用户澄清，不调工具
                return None, (
                    f'您绑定了多套专有部分：{sorted(bound)}，'
                    '请告知您想查询哪一套（如"3-1-7-702"）？'
                )

    # 全局列表工具（get_fault_summary / get_plc_status）：注入 _owner_specific_parts
    if tool_name in FILTERED_SUMMARY_TOOLS:
        args = dict(args or {})
        args['_owner_specific_parts'] = list(bound)
        return args, None

    # 未知工具：保守直通（不阻塞，避免未来新增工具因漏分类而中断）
    return args, None


def verify_write_scope(specific_part: str, user_scope: 'UserScope | None') -> None:
    """_gate 节点 execute_write 前的二次校验（REQ-ISO-003）。

    仅对 is_owner=True 的 user_scope 执行校验；None 或非 owner 直通。
    越权时抛 ScopeViolationError，调用方捕获后向用户报错并 continue 跳过写操作。
    """
    if user_scope is None or not user_scope.is_owner:
        return
    if not user_scope.allows(specific_part):
        raise ScopeViolationError(
            f'写操作二次校验失败：{specific_part} 不在用户绑定范围 '
            f'{sorted(user_scope.bound_specific_parts)} 内'
        )
