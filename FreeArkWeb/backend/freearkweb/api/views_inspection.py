"""api.views_inspection —— 巡检智能体按需触发 + 状态轮询 + 工作日志（v1.3.0-AOW）。

按需模式（不依赖 systemd 轮询，省 token、便于前期调试）：
  - 前端在故障/结露列表点「智能体巡检」→ POST trigger：原子置 IN_PROGRESS，后台线程跑
    `InspectionAgent.process_event`（复用现有九步决策，策略 B 转工单），立即返回 202。
  - 前端轮询 GET status，直到 DONE/SKIPPED。
  - 决策过程经 inspection_agent/audit.py 双写 InspectionLog，工作日志页 GET logs 查询。

并发保护（REQ-FUNC-IA-006）：全局同时最多 1 条 IN_PROGRESS（树莓派单核），超出 429。
权限：IsAuthenticated（REQ-NFR-008）。
"""

import datetime
import logging
import os
import threading

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import CondensationWarningEvent, FaultEvent, InspectionLog, WorkOrder

logger = logging.getLogger("api.views_inspection")

# 受支持的来源事件类型 → 模型
_EVENT_MODELS = {
    'fault_event': FaultEvent,
    'condensation_warning_event': CondensationWarningEvent,
}
# 全局并发上限（同时处于 IN_PROGRESS 的事件数）
_MAX_CONCURRENT = 1
# IN_PROGRESS 滞留超过此秒数即视为陈旧（进程崩溃/重启/被停用的旧自治 Agent 遗留），
# 触发时自动回收复位为 PENDING。须大于单事件决策超时（agent 默认 300s）并留足缓冲，
# 否则会误杀正在跑的巡检。可经 INSPECTION_STALE_RECLAIM_SECONDS 覆盖。
_STALE_IN_PROGRESS_SECONDS = 600


def _get_stale_seconds():
    """陈旧回收阈值秒；非法/非正值回退默认 600。"""
    try:
        value = int(os.environ.get('INSPECTION_STALE_RECLAIM_SECONDS', ''))
    except (TypeError, ValueError):
        return _STALE_IN_PROGRESS_SECONDS
    return value if value > 0 else _STALE_IN_PROGRESS_SECONDS


def _reclaim_stale_in_progress():
    """回收陈旧 IN_PROGRESS → PENDING，使全局并发闸门自愈。

    判定为陈旧：inspection_started_at 早于阈值，或为空（IN_PROGRESS 必随认领原子写入
    started_at，为空即状态不一致的孤儿）。防止单条卡死/遗留记录永久堵死按需巡检触发。
    返回回收条数。
    """
    cutoff = timezone.now() - datetime.timedelta(seconds=_get_stale_seconds())
    stale = Q(inspection_started_at__isnull=True) | Q(inspection_started_at__lt=cutoff)
    reclaimed = 0
    for model in _EVENT_MODELS.values():
        reclaimed += model.objects.filter(inspection_status='IN_PROGRESS').filter(stale).update(
            inspection_status='PENDING', inspection_started_at=None)
    if reclaimed:
        logger.warning("回收陈旧 IN_PROGRESS 巡检 %d 条（疑似进程崩溃/重启/旧自治Agent遗留）",
                       reclaimed)
    return reclaimed


def _get_event(event_type, event_id):
    """返回 (model, event|None)；event_type 非法时 model 为 None。"""
    model = _EVENT_MODELS.get(event_type)
    if model is None:
        return None, None
    try:
        return model, model.objects.get(pk=event_id)
    except model.DoesNotExist:
        return model, None


def _count_in_progress():
    return (FaultEvent.objects.filter(inspection_status='IN_PROGRESS').count()
            + CondensationWarningEvent.objects.filter(inspection_status='IN_PROGRESS').count())


def _latest_work_order(event_type, event_id):
    return (WorkOrder.objects
            .filter(source_event_type=event_type, source_event_id=event_id)
            .order_by('-created_at').first())


def _latest_work_order_ticket(event_type, event_id):
    wo = _latest_work_order(event_type, event_id)
    return wo.ticket_id if wo else None


def _build_completion_summary(event_type, event_id, event):
    """组装 PROCESS_COMPLETED 的结论摘要：工单号/是否清障/写提案/诊断节选。

    供工作日志页一行看清"如何处理、结果如何"，不必再翻工单。
    """
    summary = {'fault_cleared': not bool(getattr(event, 'is_active', True))}
    wo = _latest_work_order(event_type, event_id)
    if wo is not None:
        summary['work_order_ticket'] = wo.ticket_id
        summary['work_order_status'] = wo.status
        summary['proposed_write'] = wo.proposed_tool or None
        # 诊断/建议节选：取 recommended_action 首个非空行，便于一眼看到结论
        excerpt = next((ln.strip() for ln in (wo.recommended_action or '').splitlines()
                        if ln.strip()), '')
        if excerpt:
            summary['conclusion'] = excerpt[:120]
    return summary


def _run_inspection_thread(event_type, event_id):
    """后台线程：跑单事件决策。异常退出时重置 PENDING（REQ-NFR-007）；末尾关闭线程 DB 连接。"""
    from django.db import connection
    from inspection_agent import audit
    from inspection_agent.agent import InspectionAgent

    model = _EVENT_MODELS[event_type]
    try:
        try:
            event = model.objects.get(pk=event_id)
        except model.DoesNotExist:
            logger.warning("按需巡检线程：事件不存在 %s/%s", event_type, event_id)
            return
        specific_part = getattr(event, 'specific_part', '') or ''
        try:
            audit.log_process_started(event_id, event_type, specific_part, trigger='on_demand')
            InspectionAgent().process_event(event)
            event.refresh_from_db(fields=['inspection_status', 'is_active'])
            audit.log_process_completed(
                event_id, event_type, specific_part, outcome=event.inspection_status,
                summary=_build_completion_summary(event_type, event_id, event))
        except Exception as exc:  # noqa: BLE001
            logger.exception("按需巡检线程处置异常: %s", exc)
            # 兜底：仍处于 IN_PROGRESS 的事件重置 PENDING，供再次手动触发
            model.objects.filter(pk=event_id, inspection_status='IN_PROGRESS').update(
                inspection_status='PENDING', inspection_started_at=None)
    finally:
        connection.close()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def inspection_trigger(request, event_type, event_id):
    """POST /api/inspection/trigger/{event_type}/{event_id}/ —— 按需触发单事件巡检。"""
    model, event = _get_event(event_type, event_id)
    if model is None:
        return Response({'success': False, 'message': f'未知事件类型: {event_type}'},
                        status=status.HTTP_400_BAD_REQUEST)
    if event is None:
        return Response({'success': False, 'message': '事件不存在'},
                        status=status.HTTP_404_NOT_FOUND)
    # 自愈：先回收崩溃/重启/旧自治 Agent 遗留的陈旧 IN_PROGRESS，避免孤儿永久堵死全局闸门，
    # 再复读本事件状态（本事件若正是被回收对象，刷新后即为 PENDING，可继续认领）。
    _reclaim_stale_in_progress()
    event.refresh_from_db(fields=['inspection_status'])
    if event.inspection_status == 'IN_PROGRESS':
        return Response({'status': 'IN_PROGRESS', 'message': '该事件正在巡检中'},
                        status=status.HTTP_409_CONFLICT)
    # 并发保护：全局同时最多 1 条 IN_PROGRESS
    if _count_in_progress() >= _MAX_CONCURRENT:
        return Response({'message': '当前有巡检任务正在执行，请稍后再试'},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)
    # 原子认领（允许对 PENDING/DONE/SKIPPED 触发；DONE 可重新巡检，OQ-4）
    claimed = model.objects.filter(
        pk=event_id, inspection_status__in=['PENDING', 'DONE', 'SKIPPED'],
    ).update(inspection_status='IN_PROGRESS', inspection_started_at=timezone.now())
    if not claimed:
        return Response({'status': 'IN_PROGRESS', 'message': '该事件正在巡检中'},
                        status=status.HTTP_409_CONFLICT)

    threading.Thread(target=_run_inspection_thread, args=(event_type, event_id),
                     daemon=True).start()
    return Response({'status': 'IN_PROGRESS', 'message': '巡检已启动，预计 50~300 秒完成'},
                    status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def inspection_status_view(request, event_type, event_id):
    """GET /api/inspection/status/{event_type}/{event_id}/ —— 轮询巡检处置状态。"""
    model, event = _get_event(event_type, event_id)
    if model is None:
        return Response({'success': False, 'message': f'未知事件类型: {event_type}'},
                        status=status.HTTP_400_BAD_REQUEST)
    if event is None:
        return Response({'success': False, 'message': '事件不存在'},
                        status=status.HTTP_404_NOT_FOUND)
    started = event.inspection_started_at
    return Response({
        'inspection_status': event.inspection_status,
        'inspection_started_at': started.isoformat() if started else None,
        'work_order_id': _latest_work_order_ticket(event_type, event_id),
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def inspection_logs(request):
    """GET /api/inspection/logs/ —— 巡检智能体工作日志查询（过滤 + 分页）。"""
    qs = InspectionLog.objects.all()

    event_type = request.GET.get('event_type')
    if event_type in _EVENT_MODELS:
        qs = qs.filter(source_event_type=event_type)
    specific_part = request.GET.get('specific_part')
    if specific_part:
        qs = qs.filter(specific_part__icontains=specific_part)
    result = request.GET.get('result')
    if result:
        qs = qs.filter(result=result)
    step = request.GET.get('step')
    if step:
        qs = qs.filter(step=step)
    source_event_id = request.GET.get('source_event_id')
    if source_event_id:
        qs = qs.filter(source_event_id=source_event_id)
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
    items = list(qs[start:start + page_size].values(
        'id', 'source_event_type', 'source_event_id', 'specific_part', 'event_type_display',
        'step', 'step_detail', 'result', 'work_order_ticket', 'created_at'))

    return Response({
        'success': True,
        'data': items,
        'total': total,
        'page': page,
        'page_size': page_size,
    })
