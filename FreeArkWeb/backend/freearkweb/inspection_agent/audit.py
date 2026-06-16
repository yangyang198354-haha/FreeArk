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
# v1.3.0-AOW：生命周期/兜底步骤（供工作日志展示完整决策过程）
PROCESS_STARTED = "PROCESS_STARTED"
EVENT_SKIPPED = "EVENT_SKIPPED"
WORKORDER_EXISTED = "WORKORDER_EXISTED"
DECISION_TIMEOUT = "DECISION_TIMEOUT"
DECISION_ERROR = "DECISION_ERROR"
PROCESS_COMPLETED = "PROCESS_COMPLETED"
WRITE_PROPOSAL = "WRITE_PROPOSAL"

# 脱敏键名子串（大小写不敏感）
_SENSITIVE_SUBSTRINGS = ("key", "password", "passwd", "pwd", "token", "secret")
_REDACTED = "***REDACTED***"
# 写授权拦截原因 → 审计事件类型映射
_BLOCK_REASON_TO_EVENT = {
    "POLICY_B_NO_AUTO_WRITE": WRITE_BLOCKED_POLICY_B,
    "OUT_OF_WHITELIST": WRITE_BLOCKED_WHITELIST,
}
# 审计事件类型 → InspectionLog.step（v1.3.0 工作日志入库）。
# 未列出的 event_type 直接作为 step 落库。
_EVENT_TO_STEP = {
    WRITE_BLOCKED_POLICY_B: "WRITE_BLOCKED",
    WRITE_BLOCKED_WHITELIST: "WRITE_BLOCKED",
}
_EVENT_TYPE_DISPLAY = {
    "fault_event": "故障事件",
    "condensation_warning_event": "结露预警事件",
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


def _persist_to_db(record):
    """v1.3.0：把一条审计记录双写入 InspectionLog（journald 之外的网页可查源）。

    失败绝不抛出（REQ-NFR-006）：DB 不可用/未迁移/无连接时仅 warning，不阻断决策主流程。
    惰性 import 模型，避免 app registry 未就绪时的导入问题。
    """
    try:
        from api.models import InspectionLog
        event_type = record.get("event_type", "")
        detail = record.get("action_detail") or {}
        ticket = detail.get("ticket_id", "") if isinstance(detail, dict) else ""
        InspectionLog.objects.create(
            source_event_type=record.get("source_event_type") or "",
            source_event_id=record.get("source_event_id") or 0,
            specific_part=record.get("specific_part") or "",
            event_type_display=_EVENT_TYPE_DISPLAY.get(record.get("source_event_type"), ""),
            step=_EVENT_TO_STEP.get(event_type, event_type),
            step_detail=detail if isinstance(detail, dict) else {"value": detail},
            result=record.get("result") or "INFO",
            work_order_ticket=ticket or "",
        )
    except Exception as exc:  # noqa: BLE001 — 决策主流程不可因日志入库失败而中断
        audit_logger.warning("InspectionLog 入库失败（已忽略，不影响决策）：%s", exc)


def _emit(event_type, *, source_event_id, source_event_type, specific_part,
          action_detail, result, level=logging.INFO) -> dict:
    """组装并输出一条审计记录：journald JSON 行 + 双写 InspectionLog；返回 record。"""
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
    _persist_to_db(record)
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


# ── v1.3.0-AOW 生命周期/兜底步骤（供「巡检智能体工作日志」展示完整过程）──────────

def log_process_started(source_event_id, source_event_type, specific_part, trigger="on_demand") -> dict:
    """记录开始处理一条事件（按需触发 / 轮询）。"""
    return _emit(
        PROCESS_STARTED, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part, action_detail={"trigger": trigger}, result="INFO",
    )


def log_event_skipped(source_event_id, source_event_type, specific_part, reason="event_inactive") -> dict:
    """记录事件已恢复(inactive)被跳过。"""
    return _emit(
        EVENT_SKIPPED, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part, action_detail={"reason": reason}, result="SKIPPED",
    )


def log_workorder_existed(source_event_id, source_event_type, specific_part, ticket_id) -> dict:
    """记录活跃工单已存在、未重复建单。"""
    return _emit(
        WORKORDER_EXISTED, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part, action_detail={"ticket_id": ticket_id}, result="INFO",
    )


def log_decision_fallback(source_event_id, source_event_type, specific_part,
                          error_type, error_msg, timeout=False) -> dict:
    """记录决策超时/异常 → 兜底建单路径。"""
    event = DECISION_TIMEOUT if timeout else DECISION_ERROR
    return _emit(
        event, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part,
        action_detail={"error_type": error_type, "error_msg": error_msg},
        result="ERROR", level=logging.ERROR,
    )


def log_process_completed(source_event_id, source_event_type, specific_part, outcome="") -> dict:
    """记录一条事件处置完成（最终态）。"""
    return _emit(
        PROCESS_COMPLETED, source_event_id=source_event_id, source_event_type=source_event_type,
        specific_part=specific_part, action_detail={"outcome": outcome}, result="SUCCESS",
    )
