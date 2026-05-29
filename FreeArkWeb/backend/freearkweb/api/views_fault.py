"""
views_fault.py — 故障管理 REST API 视图（MOD-BE-FM-08，v0.6.3-FM）

提供两个 API 端点：
  GET /api/devices/fault-events/           — 故障事件分页查询（FR-FM-05）
  GET /api/devices/fault-event-categories/ — 故障分类常量（供前端过滤下拉）

安全：所有接口要求 IsAuthenticated（与现有接口风格一致）。
性能：默认时间范围最近 7 天，利用 idx_fault_time_active 索引；
      不缓存（直查 fault_event 表，表规模可控）。
SQL 注入防护：所有过滤均使用 Django ORM QuerySet，无原生 SQL 字符串拼接。
"""

import logging
import re
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
    SUB_TYPE_ROOM_FILTER,
    VALID_ROOM_NAMES,
    _FRESH_AIR_BIT_PATTERN,
)
from .models import FaultEvent, DeviceNode
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
      room_name         string/多值   按房间名过滤，可重复传递（白名单：客厅/主卧/次卧/儿童房/书房）
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

    # --- specific_part 匹配（BUG-FM-004 修复，v0.6.2-FM）---
    # 背景：前端 building_data.js 房号格式为 3 段（栋-单元-房号，如 "9-1-604"），
    #       而生产 DB 的 specific_part 为 4 段（栋-单元-楼层-房号，如 "9-1-6-604"）。
    #       旧逻辑用 icontains 子串匹配，"9-1-604" 不是 "9-1-6-604" 的连续子串，导致全量失效。
    # 修复：对 3 段格式做"前缀=栋-单元- + 后缀=-房号"的组合匹配，兼容 4 段精确匹配及遗留格式。
    # 边界说明：startswith('9-1-') 不会错误匹配 '9-10-...'，因为 '9-10-' 不以 '9-1-' 开头
    #           （'9-10-'[3] == '0'，而 '9-1-' 要求第 4 个字符为段分隔符后的下一内容，
    #            startswith 精确匹配前缀字节，不存在误匹配）。
    sp = request.query_params.get('specific_part', '').strip()
    if sp:
        parts = sp.split('-')
        if len(parts) == 3:
            # 3 段格式：栋-单元-房号（如 "9-1-604"）
            # 匹配 4 段 DB 值：specific_part 以 "栋-单元-" 开头，且以 "-房号" 结尾
            prefix = f"{parts[0]}-{parts[1]}-"   # "9-1-"
            suffix = f"-{parts[2]}"               # "-604"
            qs = qs.filter(
                specific_part__startswith=prefix,
                specific_part__endswith=suffix,
            )
        else:
            # 4 段格式或其他格式：icontains 保持兼容（4 段精确匹配 + 遗留子串匹配）
            # ORM 自动转义特殊字符，防 SQL 注入
            qs = qs.filter(specific_part__icontains=sp)

    # --- fault_type 多值过滤 ---
    fault_types = request.query_params.getlist('fault_type')
    if fault_types:
        # 仅保留合法的 fault_type 值，防止注入无效值
        valid_fault_types = [ft for ft in fault_types if ft in FAULT_TYPE_LABELS]
        if valid_fault_types:
            qs = qs.filter(fault_type__in=valid_fault_types)

    # --- sub_type 过滤（BUG-FM-006 修复，v0.6.3-FM）---
    # v0.6.2 旧逻辑：通过 product_code__in 过滤（SUB_TYPE_TO_PRODUCT_CODES），
    #   温控类 sub_type 无法按房间区分（所有温控 sub_type 返回相同结果集）。
    # v0.6.3 新逻辑：通过 SUB_TYPE_ROOM_FILTER 的 (product_codes, room_keywords) 二元组：
    #   - room_keywords 非空 → device_node JOIN device_room（ori_room_name 正则 OR 匹配）
    #     取满足条件的 device_sn 集合，q |= Q(device_sn__in=sns)；实现按房间区分。
    #   - room_keywords 为空 → 直接 q |= Q(product_code__in=product_codes)（无房间过滤）。
    # 兼容保留：
    #   - Q(fault_code__in=fault_codes)：命名型 fault_code 向后兼容路径（OR 联合）
    #   - fresh_air_unit 的 fault_code__startswith='fresh_air_fault_bit_' 前缀分支
    # 性能说明：device_node 行数 ~5000，Subquery < 5ms；不引入缓存（第一版简单策略）。
    # 参见：docs/troubleshooting/BUG-FM-006_room_filter_by_device_join.md
    sub_types = request.query_params.getlist('sub_type')
    if sub_types:
        fault_codes = []
        include_fresh_air_bits = False
        device_sns: list = []  # 通过 device_node JOIN device_room 收集到的 device_sn 字符串
        direct_product_codes: list = []  # room_keywords 为空时直接走 product_code 过滤

        for st in sub_types:
            if st not in SUB_TYPE_LABELS:
                # 忽略非法 sub_type 值（防止注入无效查询条件）
                continue
            fault_codes.extend(SUB_TYPE_TO_FAULT_CODES.get(st, []))
            if st == 'fresh_air_unit':
                include_fresh_air_bits = True

            room_filter = SUB_TYPE_ROOM_FILTER.get(st)
            if room_filter:
                product_codes, room_keywords = room_filter
                if room_keywords:
                    # 有房间关键词：通过 device_node JOIN device_room 取 device_sn 集合
                    # OR 模式匹配 ori_room_name（如 '书房|次卧'）
                    regex_pattern = '|'.join(map(re.escape, room_keywords))
                    sn_qs = DeviceNode.objects.filter(
                        product_code__in=product_codes,
                        room__ori_room_name__regex=regex_pattern,
                    ).values_list('device_sn', flat=True)
                    # FaultEvent.device_sn 是 VARCHAR；DeviceNode.device_sn 是 IntegerField
                    device_sns.extend(str(s) for s in sn_qs)
                else:
                    # 无房间关键词：直接 product_code 过滤（living_room/非温控类）
                    direct_product_codes.extend(product_codes)

        if fault_codes or device_sns or direct_product_codes or include_fresh_air_bits:
            q = Q()
            if fault_codes:
                # 命名型 fault_code 精确匹配（向后兼容旧数据/未来命名型故障码）
                q |= Q(fault_code__in=fault_codes)
            if device_sns:
                # 房间过滤路径：匹配特定房间的 device_sn 集合
                q |= Q(device_sn__in=device_sns)
            if direct_product_codes:
                # 无房间约束的 product_code 过滤（living_room/新风/水力/能耗/空气品质）
                q |= Q(product_code__in=direct_product_codes)
            if include_fresh_air_bits:
                # fresh_air_fault_bit_* 前缀匹配（ADR-FM-05-SUBTYPE，保持原有逻辑）
                q |= Q(fault_code__startswith='fresh_air_fault_bit_')
            qs = qs.filter(q)

    # --- room_name 过滤（FR-FM-009-filter，v0.6.4-FM-ROOM）---
    # 直接过滤 fault_event.room_name 冗余列，无需 JOIN。
    # VALID_ROOM_NAMES 白名单防止注入无效查询条件。
    room_names = request.query_params.getlist('room_name')
    if room_names:
        valid_room_names = [r for r in room_names if r in VALID_ROOM_NAMES]
        if valid_room_names:
            qs = qs.filter(room_name__in=valid_room_names)

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
