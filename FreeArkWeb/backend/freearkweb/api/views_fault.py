"""
views_fault.py — 故障管理 REST API 视图（MOD-BE-FM-08，v0.6.0-FM）

提供两个 API 端点：
  GET /api/devices/fault-events/           — 故障事件分页查询（FR-FM-05）
  GET /api/devices/fault-event-categories/ — 故障分类常量（供前端过滤下拉）

安全：所有接口要求 IsAuthenticated（与现有接口风格一致）。
性能：默认时间范围最近 7 天，利用 idx_fault_time_active 索引；
      不缓存（直查 fault_event 表，表规模可控）。
SQL 注入防护：所有过滤均使用 Django ORM QuerySet，无原生 SQL 字符串拼接。
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .fault_consumer.constants import (
    FAULT_TYPE_LABELS,
    SUB_TYPE_LABELS,
    SUB_TYPE_TO_FAULT_CODES,
    _FRESH_AIR_BIT_PATTERN,
)
from .models import FaultEvent
from .serializers_fault import FaultEventSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 分页配置
# ---------------------------------------------------------------------------

class FaultEventPagination(PageNumberPagination):
    """故障事件分页：默认 20 条/页，最大 100 条/页。"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ---------------------------------------------------------------------------
# 视图：故障事件分页查询
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fault_event_list(request):
    """GET /api/devices/fault-events/

    查询参数：
      specific_part     string        模糊匹配房号（LIKE '%value%'）
      fault_type        string/多值   故障大类，可重复传递（逗号分隔不支持，请重复参数）
      sub_type          string/多值   设备子类型，翻译为 fault_code__in
      is_active         "true"/"false" 是否活跃（不传则不过滤）
      first_seen_after  ISO8601       首次时间下限（默认 now()-7d）
      first_seen_before ISO8601       首次时间上限
      page              int           页码（默认 1）
      page_size         int           每页行数（默认 20，最大 100）

    排序：-first_seen_at（最新在前）

    安全注意：
      - 所有参数值通过 Django ORM 参数绑定传递，防止 SQL 注入
      - specific_part 使用 icontains（不是 LIKE 原生拼接）
      - is_active 参数严格转为布尔值，拒绝非 true/false 值静默忽略
    """
    qs = FaultEvent.objects.all()

    # --- specific_part 模糊匹配 ---
    sp = request.query_params.get('specific_part', '').strip()
    if sp:
        # icontains 等价 LIKE '%value%'，ORM 自动转义特殊字符，防 SQL 注入
        qs = qs.filter(specific_part__icontains=sp)

    # --- fault_type 多值过滤 ---
    fault_types = request.query_params.getlist('fault_type')
    if fault_types:
        # 仅保留合法的 fault_type 值，防止注入无效值
        valid_fault_types = [ft for ft in fault_types if ft in FAULT_TYPE_LABELS]
        if valid_fault_types:
            qs = qs.filter(fault_type__in=valid_fault_types)

    # --- sub_type 过滤（翻译为 fault_code__in + fresh_air_fault_bit_* 前缀）---
    sub_types = request.query_params.getlist('sub_type')
    if sub_types:
        fault_codes = []
        include_fresh_air_bits = False
        for st in sub_types:
            if st not in SUB_TYPE_LABELS:
                # 忽略非法 sub_type 值（防止注入无效查询条件）
                continue
            fault_codes.extend(SUB_TYPE_TO_FAULT_CODES.get(st, []))
            if st == 'fresh_air_unit':
                include_fresh_air_bits = True

        if fault_codes or include_fresh_air_bits:
            q = Q()
            if fault_codes:
                q |= Q(fault_code__in=fault_codes)
            if include_fresh_air_bits:
                # fresh_air_fault_bit_* 前缀匹配（ADR-FM-05-SUBTYPE）
                q |= Q(fault_code__startswith='fresh_air_fault_bit_')
            qs = qs.filter(q)

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
    paginator = FaultEventPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = FaultEventSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# 视图：故障分类常量
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fault_event_categories(request):
    """GET /api/devices/fault-event-categories/

    返回故障类型和设备子类型的分类常量，供前端过滤下拉列表使用。
    数据来自 constants.py，无 DB 查询，响应极快。

    响应格式：
    {
      "fault_types": [{"value": "comm", "label": "通信故障"}, ...],
      "sub_types":   [{"value": "living_room_thermostat", "label": "客厅温控面板"}, ...]
    }
    """
    return Response({
        'fault_types': [
            {'value': k, 'label': v}
            for k, v in FAULT_TYPE_LABELS.items()
        ],
        'sub_types': [
            {'value': k, 'label': v}
            for k, v in SUB_TYPE_LABELS.items()
        ],
    })
