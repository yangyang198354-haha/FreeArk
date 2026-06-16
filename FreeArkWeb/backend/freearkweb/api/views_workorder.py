"""api.views_workorder —— 巡检工单查看 + 写提案人工审批执行（v1.3.1-WO）。

按需巡检在策略 B（无人值守零自动写）下把 LLM 写提案拦截转工单。本模块给运维：
  - GET  list/detail   ：查看工单（含「来源故障是否已恢复」标记 source_active）。
  - POST approve-write ：管理员审批后经 fa_tools.execute_write 真下发被拦截的写提案
    （唯一新增的人工写出口）；成功→write_status=EXECUTED + 工单转 IN_PROGRESS。
  - POST resolve       ：管理员手动收单（RESOLVED）。

权限：查看 IsAuthenticated；执行/收单 IsAdmin（role=='admin'，与现有设备写授权一致）。
"""

import logging

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import CondensationWarningEvent, FaultEvent, WorkOrder

logger = logging.getLogger("api.views_workorder")

_EVENT_MODELS = {
    'fault_event': FaultEvent,
    'condensation_warning_event': CondensationWarningEvent,
}
_ACTIVE_WO_STATUSES = ('OPEN', 'IN_PROGRESS')


class IsAdmin(permissions.BasePermission):
    """仅管理员（role=='admin'）——与现有设备参数写操作授权一致。"""
    message = '仅管理员可执行该操作'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and getattr(request.user, 'role', None) == 'admin')


def _source_active_map(work_orders):
    """批量计算每条工单来源事件是否仍活跃（未恢复）。返回 {(type,id): bool|None}。"""
    ids_by_type = {}
    for wo in work_orders:
        ids_by_type.setdefault(wo.source_event_type, set()).add(wo.source_event_id)
    active = {}
    for etype, ids in ids_by_type.items():
        model = _EVENT_MODELS.get(etype)
        if model is None:
            continue
        rows = dict(model.objects.filter(pk__in=ids).values_list('pk', 'is_active'))
        for eid in ids:
            active[(etype, eid)] = rows.get(eid)   # None = 来源事件已不存在
    return active


def _serialize(wo, source_active, *, detail=False):
    data = {
        'id': wo.id,
        'ticket_id': wo.ticket_id,
        'severity': wo.severity,
        'source_event_type': wo.source_event_type,
        'source_event_id': wo.source_event_id,
        'affected_device': wo.affected_device,
        'symptom': wo.symptom,
        'status': wo.status,
        'status_display': wo.get_status_display(),
        'write_status': wo.write_status,
        'proposed_tool': wo.proposed_tool or '',
        'has_proposed_write': bool(wo.proposed_tool) and wo.write_status == 'PENDING',
        # source_active：True=故障仍在；False=已恢复（页面应标记）；None=来源事件已删除
        'source_active': source_active,
        'fault_cleared': source_active is False,
        'created_at': wo.created_at.isoformat() if wo.created_at else None,
        'updated_at': wo.updated_at.isoformat() if wo.updated_at else None,
        'resolved_at': wo.resolved_at.isoformat() if wo.resolved_at else None,
        'resolved_by': wo.resolved_by or '',
    }
    if detail:
        data.update({
            'diagnosis': wo.diagnosis or '',
            'recommended_action': wo.recommended_action or '',
            'proposed_args': wo.proposed_args or {},
            'write_executed_at': wo.write_executed_at.isoformat() if wo.write_executed_at else None,
            'write_executed_by': wo.write_executed_by or '',
            'write_result': wo.write_result or '',
        })
    return data


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def workorder_list(request):
    """GET /api/workorders/ —— 工单列表（过滤 + 分页 + source_active 标记）。"""
    qs = WorkOrder.objects.all()

    status_f = request.GET.get('status')
    if status_f:
        qs = qs.filter(status=status_f)
    etype = request.GET.get('source_event_type')
    if etype in _EVENT_MODELS:
        qs = qs.filter(source_event_type=etype)
    write_status = request.GET.get('write_status')
    if write_status:
        qs = qs.filter(write_status=write_status)
    ticket = request.GET.get('ticket_id')
    if ticket:
        qs = qs.filter(ticket_id__icontains=ticket)
    part = request.GET.get('specific_part')
    if part:
        qs = qs.filter(affected_device__icontains=part)
    date_from = request.GET.get('date_from')
    if date_from:
        qs = qs.filter(created_at__gte=date_from)
    date_to = request.GET.get('date_to')
    if date_to:
        qs = qs.filter(created_at__lte=date_to)

    qs = qs.order_by('-created_at')

    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(100, max(1, int(request.GET.get('page_size', 20))))
    except (TypeError, ValueError):
        page_size = 20

    total = qs.count()
    start = (page - 1) * page_size
    items = list(qs[start:start + page_size])
    active = _source_active_map(items)
    data = [_serialize(wo, active.get((wo.source_event_type, wo.source_event_id))) for wo in items]

    return Response({'success': True, 'data': data, 'total': total,
                     'page': page, 'page_size': page_size})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def workorder_detail(request, pk):
    """GET /api/workorders/{pk}/ —— 工单详情（含诊断报告全文 + 写提案结构）。"""
    try:
        wo = WorkOrder.objects.get(pk=pk)
    except WorkOrder.DoesNotExist:
        return Response({'success': False, 'message': '工单不存在'},
                        status=status.HTTP_404_NOT_FOUND)
    active = _source_active_map([wo]).get((wo.source_event_type, wo.source_event_id))
    return Response({'success': True, 'data': _serialize(wo, active, detail=True)})


@api_view(['POST'])
@permission_classes([IsAdmin])
def workorder_approve_write(request, pk):
    """POST /api/workorders/{pk}/approve-write/ —— 管理员审批并执行被拦截的写提案。

    仅 write_status=PENDING 且有 proposed_tool 时可执行；经 fa_tools.execute_write 真下发，
    成功→EXECUTED + 工单转 IN_PROGRESS，失败→FAILED（状态不变）。审计双写 InspectionLog。
    """
    try:
        wo = WorkOrder.objects.get(pk=pk)
    except WorkOrder.DoesNotExist:
        return Response({'success': False, 'message': '工单不存在'},
                        status=status.HTTP_404_NOT_FOUND)
    if not wo.proposed_tool or wo.write_status != 'PENDING':
        return Response({'success': False, 'message': '该工单无待执行的写提案'},
                        status=status.HTTP_400_BAD_REQUEST)

    operator = request.user.username
    from inspection_agent import audit                       # 惰性：复用审计双写
    from api.langgraph_chat.fa_tools import execute_write     # 惰性：需 langchain
    try:
        out = execute_write(wo.proposed_tool, wo.proposed_args or {}, operator)
    except Exception as exc:  # noqa: BLE001
        logger.exception("工单写执行异常: ticket=%s tool=%s", wo.ticket_id, wo.proposed_tool)
        out = {'success': False, 'error': f'{type(exc).__name__}: {exc}'}

    ok = isinstance(out, dict) and out.get('success')
    specific_part = wo.affected_device.split('/')[-1].strip() if wo.affected_device else ''
    audit.log_write_executed(wo.source_event_id, wo.source_event_type, specific_part,
                             wo.proposed_tool, wo.proposed_args or {},
                             'SUCCESS' if ok else 'ERROR')
    if ok:
        wo.write_status = 'EXECUTED'
        wo.write_executed_at = timezone.now()
        wo.write_executed_by = operator
        wo.write_result = (out.get('summary') or '执行成功')[:500]
        wo.status = 'IN_PROGRESS'   # 写已下发，待故障消失再收单（OQ 决策）
        wo.save(update_fields=['write_status', 'write_executed_at', 'write_executed_by',
                               'write_result', 'status', 'updated_at'])
        logger.info("工单写执行成功: ticket=%s tool=%s by=%s", wo.ticket_id, wo.proposed_tool, operator)
        return Response({'success': True, 'message': '写操作已下发执行',
                         'data': {'write_status': wo.write_status, 'status': wo.status,
                                  'summary': wo.write_result}})
    wo.write_status = 'FAILED'
    wo.write_result = (out.get('error') if isinstance(out, dict) else str(out)) or '执行失败'
    wo.write_result = wo.write_result[:500]
    wo.save(update_fields=['write_status', 'write_result', 'updated_at'])
    logger.warning("工单写执行失败: ticket=%s tool=%s err=%s",
                   wo.ticket_id, wo.proposed_tool, wo.write_result)
    return Response({'success': False, 'message': f'写操作执行失败：{wo.write_result}',
                     'data': {'write_status': wo.write_status}},
                    status=status.HTTP_502_BAD_GATEWAY)


@api_view(['POST'])
@permission_classes([IsAdmin])
def workorder_resolve(request, pk):
    """POST /api/workorders/{pk}/resolve/ —— 管理员手动收单（RESOLVED）。"""
    try:
        wo = WorkOrder.objects.get(pk=pk)
    except WorkOrder.DoesNotExist:
        return Response({'success': False, 'message': '工单不存在'},
                        status=status.HTTP_404_NOT_FOUND)
    if wo.status == 'RESOLVED':
        return Response({'success': True, 'message': '工单已是已解决状态',
                         'data': {'status': wo.status}})
    wo.status = 'RESOLVED'
    wo.resolved_at = timezone.now()
    wo.resolved_by = request.user.username
    wo.save(update_fields=['status', 'resolved_at', 'resolved_by', 'updated_at'])
    return Response({'success': True, 'message': '工单已标记为已解决',
                     'data': {'status': wo.status, 'resolved_by': wo.resolved_by}})
