"""inspection_agent.work_order —— 工单创建与防重复建单（ARCH §7）。

工单是 freeark-inspection-agent 的人工处置出口（本期仅落库 + Django Admin）。
防重复建单：同一来源事件在 OPEN/IN_PROGRESS 下只允许一条活跃工单——代码层先查后建 +
DB 条件唯一约束 uniq_active_workorder_per_event 兜底（ARCH §7.3）。
ticket_id 规则：WO-YYYYMMDD-NNNNNN（当天序号左补零至 6 位，ARCH §7.2）。
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from api.models import CondensationWarningEvent, FaultEvent, WorkOrder

logger = logging.getLogger("freeark.inspection_agent.work_order")

# 视为"活跃工单"的状态：同一来源事件在这些状态下只允许存在一条
ACTIVE_STATUSES = ('OPEN', 'IN_PROGRESS')
_MAX_TICKET_RETRY = 3


def generate_ticket_id(now=None, offset: int = 0) -> str:
    """生成人可读工单编号 WO-YYYYMMDD-NNNNNN（当天已有数 + 1 + offset）。

    offset 供 ticket_id 唯一冲突重试时递增序号使用。
    """
    now = now or timezone.now()
    prefix = f"WO-{now.strftime('%Y%m%d')}-"
    count = WorkOrder.objects.filter(ticket_id__startswith=prefix).count()
    seq = count + 1 + offset
    return f"{prefix}{seq:06d}"


def _describe_event(event) -> dict:
    """从来源事件实例抽取工单字段（severity / symptom / affected_device 等）。"""
    if isinstance(event, FaultEvent):
        return dict(
            source_event_type='fault_event',
            source_event_id=event.pk,
            severity=event.severity,
            symptom=event.fault_message,
            affected_device=f"{event.device_sn} / {event.specific_part}",
        )
    if isinstance(event, CondensationWarningEvent):
        return dict(
            source_event_type='condensation_warning_event',
            source_event_id=event.pk,
            # CW 无 severity 字段，用 warning_type 作为级别（ARCH §5 步骤7）
            severity=event.warning_type,
            symptom=event.warning_message,
            affected_device=f"{event.device_sn} / {event.specific_part}",
        )
    raise TypeError(f"不支持的来源事件类型: {type(event).__name__}")


def find_active_work_order(source_event_type: str, source_event_id: int):
    """查同一来源事件的活跃工单（OPEN/IN_PROGRESS），无则返回 None。"""
    return WorkOrder.objects.filter(
        source_event_type=source_event_type,
        source_event_id=source_event_id,
        status__in=ACTIVE_STATUSES,
    ).first()


def create_work_order(*, source_event_type, source_event_id, severity, affected_device,
                      symptom, diagnosis='', recommended_action='',
                      proposed_tool='', proposed_args=None):
    """创建工单（先查后建 + 约束兜底）。

    返回 (work_order, created)：
      - 已存在活跃工单 → 返回该工单，created=False（不重复建单）；
      - 否则新建 → created=True；
      - 并发下命中 DB 约束/编号冲突 → 重查活跃工单返回，或递增编号重试。

    proposed_tool/proposed_args（v1.3.1-WO）：被写授权策略拦截的结构化写提案，供工单页
    管理员审批后 execute_write 真执行；提供 tool 即把 write_status 标 PENDING，否则 NONE。
    """
    existing = find_active_work_order(source_event_type, source_event_id)
    if existing is not None:
        logger.info("工单已存在，跳过建单: ticket_id=%s source=%s/%s",
                    existing.ticket_id, source_event_type, source_event_id)
        return existing, False

    write_status = 'PENDING' if proposed_tool else 'NONE'
    last_exc = None
    for attempt in range(_MAX_TICKET_RETRY):
        ticket_id = generate_ticket_id(offset=attempt)
        try:
            with transaction.atomic():
                work_order = WorkOrder.objects.create(
                    ticket_id=ticket_id,
                    severity=severity,
                    source_event_type=source_event_type,
                    source_event_id=source_event_id,
                    affected_device=affected_device,
                    symptom=symptom,
                    diagnosis=diagnosis,
                    recommended_action=recommended_action,
                    proposed_tool=proposed_tool or '',
                    proposed_args=proposed_args or {},
                    write_status=write_status,
                )
            return work_order, True
        except IntegrityError as exc:
            last_exc = exc
            # 可能是 ticket_id 唯一冲突，或 uniq_active_workorder_per_event 并发命中。
            # 先看是否已有活跃工单（后者）：有则直接返回，避免重复建单。
            existing = find_active_work_order(source_event_type, source_event_id)
            if existing is not None:
                logger.info("并发命中活跃工单约束，返回已有工单: ticket_id=%s", existing.ticket_id)
                return existing, False
            # 否则按 ticket_id 冲突处理：递增序号重试
            logger.warning("建单 ticket_id 冲突，重试（attempt=%d, ticket_id=%s）",
                           attempt, ticket_id)
    # 重试耗尽：抛出最后一次异常，交由上层兜底（不静默吞掉）
    raise last_exc


def create_from_event(event, *, diagnosis='', recommended_action='',
                      proposed_tool='', proposed_args=None):
    """从来源事件实例（FaultEvent / CondensationWarningEvent）建单。

    返回 (work_order, created)，字段由 _describe_event 推导。
    proposed_tool/proposed_args 透传给 create_work_order（v1.3.1-WO 结构化写提案）。
    """
    fields = _describe_event(event)
    return create_work_order(diagnosis=diagnosis, recommended_action=recommended_action,
                             proposed_tool=proposed_tool, proposed_args=proposed_args,
                             **fields)
