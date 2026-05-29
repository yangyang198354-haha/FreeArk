"""
views_condensation.py — 结露预警管理 REST API 视图（MOD-BE-CW-06，v0.7.0-CW）

提供接口：
  GET /api/devices/condensation-warning-events/ — 结露预警事件分页查询

镜像 views_fault.py（ADR-CW-06），差异：
  - 无 fault_type / sub_type / room_name 过滤参数（需求未要求，不过度实现）
  - 新增 _inject_screen_online（ADR-CW-05）：分页后对当前页所有 specific_part 执行
    一次 IN 查询 ScreenConnectivityStatus，注入 is_screen_online 字段
  - specific_part 段数映射逻辑完全复用 views_fault.py（BUG-FM-004 已验证）

安全：要求 IsAuthenticated，所有过滤使用 Django ORM，无原生 SQL 字符串拼接。
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import CondensationWarningEvent, ScreenConnectivityStatus
from .serializers_condensation import CondensationWarningEventSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 分页配置
# ---------------------------------------------------------------------------

class CondensationWarningPagination(PageNumberPagination):
    """结露预警事件分页：默认 20 条/页，最大 100 条/页。"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ---------------------------------------------------------------------------
# is_screen_online 注入（ADR-CW-05）
# ---------------------------------------------------------------------------

def _inject_screen_online(results: list) -> list:
    """对结果集注入 is_screen_online 字段（ADR-CW-05）。

    对当前页所有 specific_part 执行一次 IN 查询 ScreenConnectivityStatus，
    now()-last_seen_at <= 15min 则认为在线。

    ScreenConnectivityStatus 为小表（每户一行，约 634 行），
    IN 查询最多 100 条，预计 < 50ms，无性能问题。

    Args:
        results: 序列化后的 dict 列表（已是 list，非 QuerySet）

    Returns:
        注入 is_screen_online 字段后的 list
    """
    if not results:
        return results
    specific_parts = [r['specific_part'] for r in results]
    threshold = timezone.now() - timedelta(minutes=15)
    online_set = set(
        ScreenConnectivityStatus.objects
        .filter(specific_part__in=specific_parts, last_seen_at__gte=threshold)
        .values_list('specific_part', flat=True)
    )
    for r in results:
        r['is_screen_online'] = r['specific_part'] in online_set
    return results


# ---------------------------------------------------------------------------
# 视图：结露预警事件分页查询
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def condensation_warning_event_list(request):
    """GET /api/devices/condensation-warning-events/

    查询参数：
      specific_part     string        房号过滤，段数映射（3 段→startswith+endswith，其他→icontains）
      is_active         "true"/"false" 是否活跃（不传则不过滤）
      first_seen_after  ISO8601       首次时间下限（默认 now()-7d）
      first_seen_before ISO8601       首次时间上限
      page              int           页码（默认 1）
      page_size         int           每页行数（默认 20，最大 100）

    排序：-first_seen_at（最新在前）

    响应：标准 PageNumberPagination 格式（count/next/previous/results），
    results 每条数据注入 is_screen_online 字段（ADR-CW-05）。

    安全：
      - 所有参数值通过 Django ORM 参数绑定传递，防止 SQL 注入
      - specific_part 使用 startswith/endswith/icontains，均经 ORM 转义
      - is_active 参数严格转为布尔值，拒绝非 true/false 值静默忽略
    """
    qs = CondensationWarningEvent.objects.all()

    # --- specific_part 段数映射（完全复用 views_fault.py 的 BUG-FM-004 修复逻辑）---
    # 3 段格式（如 "9-1-604"）：startswith("9-1-") + endswith("-604") 匹配 4 段 DB 值
    # 其他格式（4 段精确 / 遗留子串）：icontains
    sp = request.query_params.get('specific_part', '').strip()
    if sp:
        parts = sp.split('-')
        if len(parts) == 3:
            prefix = f"{parts[0]}-{parts[1]}-"
            suffix = f"-{parts[2]}"
            qs = qs.filter(
                specific_part__startswith=prefix,
                specific_part__endswith=suffix,
            )
        else:
            qs = qs.filter(specific_part__icontains=sp)

    # --- is_active 过滤 ---
    is_active_param = request.query_params.get('is_active')
    if is_active_param is not None:
        is_active_lower = is_active_param.lower()
        if is_active_lower == 'true':
            qs = qs.filter(is_active=True)
        elif is_active_lower == 'false':
            qs = qs.filter(is_active=False)
        # 其他非法值：静默忽略，不过滤

    # --- 时间范围过滤（默认最近 7 天）---
    default_after = timezone.now() - timedelta(days=7)
    first_seen_after_param = request.query_params.get('first_seen_after', '').strip()
    first_seen_before_param = request.query_params.get('first_seen_before', '').strip()

    def _parse_dt(s):
        """解析 ISO8601；USE_TZ=False 时移除 tzinfo（SQLite 不接受 tz-aware datetime）。"""
        try:
            dt = parse_datetime(s)
        except (ValueError, TypeError):
            return None
        if dt is None:
            return None
        if not settings.USE_TZ and dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt

    parsed_after = _parse_dt(first_seen_after_param) if first_seen_after_param else None
    if parsed_after is not None:
        qs = qs.filter(first_seen_at__gte=parsed_after)
    else:
        if first_seen_after_param:
            logger.warning('first_seen_after 参数无效，使用默认值: %r', first_seen_after_param)
        qs = qs.filter(first_seen_at__gte=default_after)

    if first_seen_before_param:
        parsed_before = _parse_dt(first_seen_before_param)
        if parsed_before is not None:
            qs = qs.filter(first_seen_at__lte=parsed_before)
        else:
            logger.warning('first_seen_before 参数无效，忽略: %r', first_seen_before_param)

    # --- 排序 ---
    qs = qs.order_by('-first_seen_at')

    # --- 分页 ---
    paginator = CondensationWarningPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = CondensationWarningEventSerializer(page, many=True)

    # --- 注入 is_screen_online（ADR-CW-05，分页后执行）---
    data = list(serializer.data)
    data = _inject_screen_online(data)

    return paginator.get_paginated_response(data)
