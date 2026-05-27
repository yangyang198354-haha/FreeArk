# TODO(AB-001) Redis: 当部署扩展为多进程或出现第二个跨进程共享缓存需求时，
#              将 settings.py CACHES 迁移至 Redis；本模块所有 cache.get/set/delete 调用无需修改。
#              详见 architecture_design_v0.5.3_fault_count_column.md §12 AB-001。
# TODO(AB-002) MQTT 驱动失效: 未来如需更低延迟可在 PLCLatestDataHandler._bulk_upsert()
#              末尾追加 invalidate_fault_count_cache(specific_part)；本期保留钩子不调用。
#              详见 architecture_design_v0.5.3_fault_count_column.md §12 AB-002。
"""
fault_utils.py — 故障数量计算与缓存（v0.5.3-FCC）

集中定义故障字段识别规则、故障数量计算逻辑及缓存读写操作，
供 views.py 中的设备列表、故障详情及故障汇总视图调用。

数据来源：PLCLatestData 表（plc_latest_data）
严禁：查询 device_param_history 表（3766 万行 / 11.3 GB）

设计依据：
  - ADR-FC-001  缓存选型（LocMemCache，TTL=60s）
  - ADR-FC-002  后端 Python 集中定义故障判定规则
  - ADR-FC-003  fresh_air_fault_status 位域 popcount 处理
  - ADR-FC-005  短 TTL 定时刷新策略
  - ADR-FC-006  count_faults_for_row 单行故障贡献计算
  - REQ-FUNC-FC-03  故障判定规则
"""

import re
import logging
from collections import defaultdict
from typing import Optional, Iterable

from django.core.cache import cache
from django.db.models import Q

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量：故障字段集合（来自 DeviceCardsView.vue FAULT_PARAMS，后端权威副本）
# ---------------------------------------------------------------------------

#: 具名故障字段集合（共 26 个）：25 个 FAULT_PARAMS 字段 + comm_fault_timeout
#: 注意：不包含 fresh_air_fault_status（位域，由 count_faults_for_row 特殊处理）
FAULT_PARAM_NAMES: frozenset = frozenset([
    # 客厅温控面板（4 个）
    'living_room_temp_sensor_error',
    'living_room_humidity_sensor_error',
    'living_room_external_temp_sensor_error',
    'living_room_communication_error',
    # 书房温控面板（4 个）
    'study_room_temp_sensor_error',
    'study_room_humidity_sensor_error',
    'study_room_external_temp_sensor_error',
    'study_room_communication_error',
    # 主卧温控面板（4 个）
    'bedroom_temp_sensor_error',
    'bedroom_humidity_sensor_error',
    'bedroom_external_temp_sensor_error',
    'bedroom_communication_error',
    # 儿童房温控面板（4 个）
    'children_room_temp_sensor_error',
    'children_room_humidity_sensor_error',
    'children_room_external_temp_sensor_error',
    'children_room_communication_error',
    # 第四儿童房温控面板（4 个）
    'fourth_children_room_temp_sensor_error',
    'fourth_children_room_humidity_sensor_error',
    'fourth_children_room_external_temp_sensor_error',
    'fourth_children_room_communication_error',
    # 新风机（2 个）
    'fresh_air_unit_stop_error',
    'fresh_air_unit_communication_error',
    # 水利模块、能耗表、空气品质传感器（3 个）
    'hydraulic_module_low_temp_error',
    'energy_meter_status_communication_error',
    'air_quality_sensor_communication_error',
    # PLC 通信故障
    'comm_fault_timeout',
])

#: error_<N> 正则匹配模式（在 Python 层精确验证，DB 层用 LIKE 'error_%' 加速查询）
_ERROR_N_PATTERN = re.compile(r'^error_\d+$')

# ---------------------------------------------------------------------------
# 缓存配置（ADR-FC-001 / ADR-FC-005）
# ---------------------------------------------------------------------------

_FAULT_CACHE_PREFIX: str = 'fault_count:'
#: 缓存 TTL = 60 秒（ADR-FC-005 修订值；满足 US-FC-05 AC-FC-05-01 的 ≤60s 延迟要求）
_FAULT_CACHE_TTL: int = 60


# ---------------------------------------------------------------------------
# 公共接口 — 故障字段识别
# ---------------------------------------------------------------------------

def is_fault_param(param_name: str) -> bool:
    """判断 param_name 是否属于故障字段。

    返回 True 的条件（任意一项）：
      1. param_name in FAULT_PARAM_NAMES（含 comm_fault_timeout）
      2. 匹配正则 ^error_\\d+$（PLC 故障码位字段，如 error_82、error_703）

    注意：fresh_air_fault_status 不在此函数覆盖范围内；
          它由 count_faults_for_row() 单独处理（位域 popcount）。
    """
    return param_name in FAULT_PARAM_NAMES or bool(_ERROR_N_PATTERN.match(param_name))


# ---------------------------------------------------------------------------
# 公共接口 — 单行故障贡献计算（ADR-FC-006）
# ---------------------------------------------------------------------------

def count_faults_for_row(param_name: str, value: Optional[int]) -> int:
    """计算单行 PLCLatestData 记录对故障总数的贡献（ADR-FC-006）。

    Args:
        param_name: PLCLatestData.param_name
        value: PLCLatestData.value（BigInteger | None）

    Returns:
        int: 该行的故障贡献值（0 或正整数）

    规则：
      - fresh_air_fault_status：popcount（每个置 1 的 bit 算 1 个故障）
        Python 3.10+ 用 int.bit_count()；兼容写法用 bin(int(v)).count('1')
      - is_fault_param(param_name) and value not None and value != 0 → 1
      - 其他（含 value is None 或 value == 0）→ 0
    """
    if value is None or value == 0:
        return 0

    if param_name == 'fresh_air_fault_status':
        # ADR-FC-006: 按位计数，每个置 1 的 bit 算一个独立故障
        # 与 DeviceCardsView.vue FRESH_AIR_FAULT_BITS 口径一致
        return bin(int(value)).count('1')

    if is_fault_param(param_name):
        return 1

    return 0


# ---------------------------------------------------------------------------
# 公共接口 — 批量故障数计算（count_faults_for_row 的批量包装）
# ---------------------------------------------------------------------------

def compute_fault_count_v2(records: Iterable) -> int:
    """计算一组记录的故障总数（count_faults_for_row 的批量包装）。

    Args:
        records: (param_name, value) 的可迭代对象

    Returns:
        int: 故障总数（≥0）

    此函数作为内部计算核心保留，供 _compute_from_db_batch 使用。
    """
    return sum(count_faults_for_row(pn, v) for pn, v in records)


def compute_fault_count_for_sections(specific_parts: list) -> dict:
    """批量计算多个 specific_part 的故障数量（单次 SQL，应用层 pivot 汇总；避免 N+1）。

    Args:
        specific_parts: specific_part 字符串列表

    Returns:
        dict: {specific_part: fault_count_or_none}
              - fault_count 为整数（≥0）：有 PLCLatestData 记录
              - None：该 specific_part 在 PLCLatestData 中无任何相关记录
    """
    return _compute_from_db_batch(specific_parts)


# ---------------------------------------------------------------------------
# 公共接口 — 缓存读写
# ---------------------------------------------------------------------------

def get_fault_count_cached(specific_part: str) -> Optional[int]:
    """获取单个 specific_part 的故障数量（带缓存）。

    缓存命中时直接返回；缓存未命中时调用 _compute_from_db_batch 计算并填充。

    Returns:
        int（≥0）：故障数量，或 None（PLCLatestData 无该 specific_part 记录）
    """
    key = f'{_FAULT_CACHE_PREFIX}{specific_part}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = _compute_from_db_batch([specific_part])
    count = result.get(specific_part)
    if count is not None:
        cache.set(key, count, _FAULT_CACHE_TTL)
    return count


def get_fault_count_batch_cached(specific_parts: list) -> dict:
    """批量获取多个 specific_part 的故障数量（带缓存）。

    优先从缓存读取，未命中的 specific_part 批量查 DB 后填充缓存。

    Args:
        specific_parts: specific_part 字符串列表

    Returns:
        dict: {specific_part: fault_count_or_none}
    """
    result = {}
    miss_list = []

    for sp in specific_parts:
        key = f'{_FAULT_CACHE_PREFIX}{sp}'
        val = cache.get(key)
        if val is not None:
            result[sp] = val
        else:
            miss_list.append(sp)

    if miss_list:
        db_counts = _compute_from_db_batch(miss_list)
        for sp, count in db_counts.items():
            result[sp] = count
            if count is not None:
                cache.set(f'{_FAULT_CACHE_PREFIX}{sp}', count, _FAULT_CACHE_TTL)

    return result


def invalidate_fault_count_cache(specific_part: str) -> None:
    """（备用）主动清除指定 specific_part 的故障数量缓存条目。

    OQ-01 裁决后，mqtt_handlers.py 不调用此函数（缓存由 TTL=60s 自动过期）。
    保留供未来切换至写入端钩子（ADR-FC-005 方案 B / AB-002）时直接启用，无需修改接口。
    """
    cache.delete(f'{_FAULT_CACHE_PREFIX}{specific_part}')


# ---------------------------------------------------------------------------
# 公共接口 — 故障详情（用于 /api/devices/fault-count/ 响应）
# ---------------------------------------------------------------------------

def get_fault_details(specific_part: str) -> list:
    """获取处于故障状态的参数列表（仅当前非正常字段）。

    Hotfix BUG-FCC-001：与 _compute_from_db_batch 同样按 sub_type 过滤，
    避免详情列出"户型不存在房型的故障"。

    Returns:
        list: [{"param_name": str, "value": int}, ...]，按 param_name 升序
    """
    from .models import PLCLatestData

    fault_param_names_list = list(FAULT_PARAM_NAMES) + ['fresh_air_fault_status']

    qs = PLCLatestData.objects.filter(
        specific_part=specific_part,
    ).filter(
        Q(param_name__in=fault_param_names_list) |
        Q(param_name__startswith='error_')
    ).values('param_name', 'value')

    param_to_subtypes = _get_param_to_subtypes()

    details = []
    for rec in qs:
        pn = rec['param_name']
        val = rec['value']
        if val is None or val == 0:
            continue
        # error_ 前缀字段：精确正则验证（排除 error_xxx_status 等非数字后缀）
        if pn.startswith('error_') and not _ERROR_N_PATTERN.match(pn):
            continue
        # hotfix BUG-FCC-001: 跳过该专有部分户型不存在的 sub_type 字段
        if not _is_param_visible_for_section(pn, specific_part, param_to_subtypes):
            continue
        details.append({'param_name': pn, 'value': val})

    details.sort(key=lambda x: x['param_name'])
    return details


def get_fault_details_updated_at(specific_part: str):
    """获取该 specific_part 故障相关字段的最新 updated_at 时间戳。

    Returns:
        datetime | None
    """
    from .models import PLCLatestData
    from django.db.models import Max

    fault_param_names_list = list(FAULT_PARAM_NAMES) + ['fresh_air_fault_status']

    result = PLCLatestData.objects.filter(
        specific_part=specific_part,
    ).filter(
        Q(param_name__in=fault_param_names_list) |
        Q(param_name__startswith='error_')
    ).aggregate(latest=Max('updated_at'))

    return result.get('latest')


# ---------------------------------------------------------------------------
# 内部函数 — DeviceConfig 映射缓存（hotfix BUG-FCC-001）
# ---------------------------------------------------------------------------

_PARAM_SUBTYPE_CACHE_KEY: str = 'fault_count:param_to_subtypes'
_PARAM_SUBTYPE_CACHE_TTL: int = 60


def _get_param_to_subtypes() -> dict:
    """获取 {param_name: frozenset[sub_type]} 映射。

    同一 param_name 可能在多个 sub_type 下激活（unique_together=(param_name, sub_type)），
    所以值是 sub_type 集合。

    缓存 60s（与故障数缓存对齐），DeviceConfig 极少变更。
    """
    cached = cache.get(_PARAM_SUBTYPE_CACHE_KEY)
    if cached is not None:
        return cached

    from .models import DeviceConfig
    mapping: dict = defaultdict(set)
    for pn, st in DeviceConfig.objects.filter(is_active=True).values_list('param_name', 'sub_type'):
        mapping[pn].add(st)
    result = {k: frozenset(v) for k, v in mapping.items()}
    cache.set(_PARAM_SUBTYPE_CACHE_KEY, result, _PARAM_SUBTYPE_CACHE_TTL)
    return result


def _is_param_visible_for_section(param_name: str, specific_part: str, param_to_subtypes: dict) -> bool:
    """判断某 param 在指定 specific_part 的设备面板上是否可见（hotfix BUG-FCC-001）。

    与 views.get_device_realtime_params 的 sub_type 过滤口径保持一致：
      - 若该 param 在 DeviceConfig 中无条目（如 comm_fault_timeout、error_<N>）→ 保留原行为，视为可见
      - 若该 param 的所有 sub_type 都不在 get_available_sub_types(specific_part) → 不可见，应跳过
    """
    sub_types_of_param = param_to_subtypes.get(param_name)
    if sub_types_of_param is None:
        # DeviceConfig 无此 param 条目 → 系统级/PLC 级字段，保留原行为
        return True
    from .utils_room_filter import get_available_sub_types
    available = get_available_sub_types(specific_part)
    return bool(sub_types_of_param & available)


# ---------------------------------------------------------------------------
# 内部函数 — DB 批量查询（单条 SQL，避免 N+1）
# ---------------------------------------------------------------------------

def _compute_from_db_batch(specific_parts: list) -> dict:
    """批量从 PLCLatestData DB 查询并计算故障数量（内部函数）。

    使用单条 SQL（Q 对象组合 OR 条件），避免 N+1 查询。

    DB 层使用 param_name__startswith='error_'（等价 LIKE 'error_%'，可利用前缀索引）
    Python 层用 _ERROR_N_PATTERN 精确过滤，排除 error_xxx_status 等非数字后缀字段。

    Hotfix BUG-FCC-001（2026-05-27）：与设备面板 (views.get_device_realtime_params)
    的 sub_type 过滤口径对齐——某字段的 sub_type 不在该 specific_part 的
    available_sub_types 集合时跳过，避免列表统计了"户型不存在房型的故障"。

    Args:
        specific_parts: 待查询的 specific_part 列表（可为空列表）

    Returns:
        dict: {specific_part: fault_count_or_none}
              - None 表示该 specific_part 在 PLCLatestData 无任何相关记录
    """
    if not specific_parts:
        return {}

    from .models import PLCLatestData

    # 故障字段名列表（含 fresh_air_fault_status）
    fault_param_names_list = list(FAULT_PARAM_NAMES) + ['fresh_air_fault_status']

    # 单条 SQL：(param_name IN <FAULT_PARAM_NAMES+fresh_air_fault_status>) OR (param_name LIKE 'error_%')
    qs = PLCLatestData.objects.filter(
        specific_part__in=specific_parts,
    ).filter(
        Q(param_name__in=fault_param_names_list) |
        Q(param_name__startswith='error_')   # LIKE 'error_%' 可利用前缀索引
    ).values('specific_part', 'param_name', 'value')

    # hotfix BUG-FCC-001: 加载 param → sub_types 映射用于过滤
    param_to_subtypes = _get_param_to_subtypes()

    # 按 specific_part 分组，Python 层 pivot 汇总
    groups: dict = defaultdict(list)
    for rec in qs:
        sp = rec['specific_part']
        pn = rec['param_name']
        # error_ 前缀字段在 Python 层精确验证（排除 error_xxx_status 等非数字后缀）
        if pn.startswith('error_') and not _ERROR_N_PATTERN.match(pn):
            continue
        # hotfix BUG-FCC-001: 跳过该专有部分户型不存在的 sub_type 字段
        if not _is_param_visible_for_section(pn, sp, param_to_subtypes):
            continue
        groups[sp].append((pn, rec['value']))

    result = {}
    for sp in specific_parts:
        if sp in groups:
            result[sp] = compute_fault_count_v2(groups[sp])
        else:
            result[sp] = None  # 该 specific_part 无任何 PLCLatestData 相关记录

    return result
