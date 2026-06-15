"""inspection_agent.audit —— 结构化审计日志（ARCH §9）。

经 logger "freeark.inspection_agent.audit" 输出 JSON 行，systemd 下进 journald，可
`journalctl -u freeark-inspection-agent ... | grep WORKORDER_CREATED` 检索。

安全约束（ARCH §9.3，[[project_infrastructure]] 凭证红线）：
  - 接口不接受任何凭证类参数；
  - _scrub() 作为纵深防御，对 action_detail 中键名含 key/password/token/secret 的值
    做脱敏（即便误传也不落盘明文）。
"""

import json
import logging

from django.utils import timezone

audit_logger = logging.getLogger("freeark.inspection_agent.audit")

# 审计事件类型（记录在 JSON 的顶层 event_type 字段）
WRITE_EXECUTED = "WRITE_EXECUTED"
WRITE_BLOCKED_POLICY_B = "WRITE_BLOCKED_POLICY_B"
WRITE_BLOCKED_WHITELIST = "WRITE_BLOCKED_WHITELIST"
WORKORDER_CREATED = "WORKORDER_CREATED"
DELEGATION_CALLED = "DELEGATION_CALLED"
DELEGATION_ERROR = "DELEGATION_ERROR"

# 脱敏键名子串（大小写不敏感）
_SENSITIVE_SUBSTRINGS = ("key", "password", "passwd", "pwd", "token", "secret")
_REDACTED = "***REDACTED***"
# 写授权拦截原因 → 审计事件类型映射
_BLOCK_REASON_TO_EVENT = {
    "POLICY_B_NO_AUTO_WRITE": WRITE_BLOCKED_POLICY_B,
    "OUT_OF_WHITELIST": WRITE_BLOCKED_WHITELIST,
}


def _scrub(value):
    """递归脱敏：键名含敏感子串的值替换为 ***REDACTED***。"""
    if isinstance(value, dict):
        result = {}
        for key, val in value.items():
            if isinstance(key, str) and any(s in key.lower() for s in _SENSITIVE_SUBSTRINGS):
                result[key] = _REDACTED
            else:
                result[key] = _scrub(val)
        return result
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value


def _emit(event_type, *, source_event_id, source_event_type, specific_part,
          action_detail, result, level=logging.INFO) -> dict:
    """组装并输出一条审计 JSON 行；返回该 record（便于测试断言）。"""
    record = {
        "timestamp": timezone.now().isoformat(),
        "event_type": event_type,
        "source_event_id": source_event_id,
        "source_event_type": source_event_type,
        "specific_part": specific_part,
        "action_detail": _scrub(action_detail or {}),
        "result": result,
    }
    audit_logger.log(level, json.dumps(record, ensure_ascii=False, default=str))
    return record


def log_write_executed(source_event_id, source_event_type, specific_part,
                       tool_name, args, result_status) -> dict:
    """记录已执行的写操作（仅策略 A 白名单放行后可达）。result_status: SUCCESS/ERROR。"""
    level = logging.INFO if result_status == "SUCCESS" else logging.ERROR
    return _emit(
        WRITE_EXECUTED, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part,
        action_detail={"tool_name": tool_name, "args": args},
        result=result_status, level=level,
    )


def log_write_blocked(source_event_id, source_event_type, specific_part,
                      tool_name, args, policy_reason) -> dict:
    """记录被写授权层拦截的写提案（策略 B 全部拦截，或策略 A 越界）。"""
    event_type = _BLOCK_REASON_TO_EVENT.get(policy_reason, WRITE_BLOCKED_POLICY_B)
    return _emit(
        event_type, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part,
        action_detail={"tool_name": tool_name, "args": args, "policy_reason": policy_reason},
        result="BLOCKED", level=logging.WARNING,
    )


def log_workorder_created(source_event_id, source_event_type, specific_part,
                          ticket_id, severity=None) -> dict:
    """记录工单创建。"""
    return _emit(
        WORKORDER_CREATED, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part,
        action_detail={"ticket_id": ticket_id, "severity": severity},
        result="SUCCESS",
    )


def log_delegation_called(source_event_id, source_event_type, specific_part,
                          target_expert, query_summary) -> dict:
    """记录一次子专家委托调用（delegate_knowledge / delegate_read 等）。"""
    return _emit(
        DELEGATION_CALLED, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part,
        action_detail={"target_expert": target_expert, "query_summary": query_summary},
        result="SUCCESS",
    )


def log_delegation_error(source_event_id, source_event_type, specific_part,
                         target_expert, error_type, error_msg) -> dict:
    """记录子专家委托异常（不杜撰，原样回灌上层决策）。"""
    return _emit(
        DELEGATION_ERROR, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part,
        action_detail={"target_expert": target_expert,
                       "error_type": error_type, "error_msg": error_msg},
        result="ERROR", level=logging.ERROR,
    )
