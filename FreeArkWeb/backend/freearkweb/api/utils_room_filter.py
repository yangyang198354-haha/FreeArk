"""
utils_room_filter.py — FreeArk v0.5.7

房型过滤工具：根据 device_room 表中已同步的房间信息，
确定某专有部分可显示/可采集的 DeviceConfig sub_type 集合与参数黑名单。

模块 M1（module_design_v0.5.7.md）
"""

import threading
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── 温控面板 sub_type → 房间关键词映射 ──────────────────────────────────────
#
# 关键词来源：seed_device_config.py 注释 + plc_config.json description 字段
# 匹配规则：device_room.ori_room_name 中包含列表中任意一个关键词即命中
#
# 映射语义（对照 plc_config.json description）：
#   panel_study_room      → 三房次卧 / 四房书房   → ori_room_name 含"次卧"或"书房"
#   panel_bedroom         → 三房主卧 / 四房次卧   → ori_room_name 含"主卧"
#                           （四房次卧由 panel_study_room 的"次卧"关键词处理）
#   panel_children_room   → 三房儿童房 / 四房主卧 → ori_room_name 含"儿童房"或"主卧"
#   panel_fourth_children → 四房儿童房（专属）   → ori_room_name 含"儿童房"，
#                           且满足四房户型判断（见 _match_panel_sub_types 注释）
#
# 注意：panel_bedroom 与 panel_children_room 均含"主卧"关键词。
# get_available_sub_types() 通过 _match_panel_sub_types() 处理：
#   - "主卧"命中 panel_bedroom（三房主卧）
#   - "主卧"也命中 panel_children_room（四房主卧）
#   - 两者均可激活是正确的：三房户型有主卧，对应 panel_bedroom；
#     四房户型的"四房主卧"ori_room_name 中含"主卧"，会同时命中 panel_children_room。
#   - panel_fourth_children 与 panel_children_room 均含"儿童房"关键词，
#     通过「四字提示」区分（见 _match_panel_sub_types）。

SUB_TYPE_TO_ROOM_KEYWORDS: dict = {
    'panel_study_room':      ['次卧', '书房'],
    'panel_bedroom':         ['主卧'],
    'panel_children_room':   ['儿童房', '主卧'],
    'panel_fourth_children': ['儿童房'],
}

# 不受房型约束的系统级 sub_type（始终可用，无需房间验证）
# 对应 plc_config.json 中 main_thermostat / fresh_air / energy_meter 等分组
SYSTEM_LEVEL_SUB_TYPES: frozenset = frozenset({
    'main_thermostat',
    'fresh_air',
    'energy_meter',
    'hydraulic_module',
    'air_quality',
})

# 所有温控面板 sub_type（用于 blocklist 计算）
ALL_PANEL_SUB_TYPES: frozenset = frozenset(SUB_TYPE_TO_ROOM_KEYWORDS.keys())

# ── 进程内缓存 ────────────────────────────────────────────────────────────────
# 格式：{specific_part: (available_sub_types: frozenset, cached_at: float)}
_room_filter_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS: int = 300  # 5 分钟


# ─────────────────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────────────────

def get_available_sub_types(specific_part: str) -> frozenset:
    """
    查询并缓存指定专有部分可用的 DeviceConfig sub_type 集合。

    返回值：
        frozenset[str]，包含该专有部分应显示/可采集的所有 sub_type。
        - 系统级 sub_type（SYSTEM_LEVEL_SUB_TYPES）始终包含。
        - 温控面板 sub_type 仅在 device_room 中存在对应房间时包含。
        - 若设备树未同步（device_floor 中无该 specific_part 记录），
          仅返回 SYSTEM_LEVEL_SUB_TYPES（降级策略方案 B，PM OQ-v0.5.7-02 锁定）。

    缓存：
        TTL = 300s，线程安全（_cache_lock 保护读写）。
        设备树同步后调用 invalidate_room_filter_cache(specific_part) 主动清除。
    """
    # 1. 检查缓存
    now = time.monotonic()
    with _cache_lock:
        cached = _room_filter_cache.get(specific_part)
        if cached is not None:
            available_sub_types, cached_at = cached
            if (now - cached_at) < _CACHE_TTL_SECONDS:
                logger.debug(
                    'utils_room_filter: 命中缓存 specific_part=%s, sub_types=%s',
                    specific_part, available_sub_types,
                )
                return available_sub_types

    # 2. 查询 device_room（延迟导入，避免循环依赖）
    from .models import DeviceFloor  # noqa: PLC0415
    try:
        floors = list(
            DeviceFloor.objects.filter(
                owner__specific_part=specific_part
            ).prefetch_related('rooms')
        )
    except Exception as e:
        logger.error(
            'utils_room_filter: 查询 DeviceFloor 失败 specific_part=%s: %s',
            specific_part, e,
        )
        # 查询异常时返回仅系统级（安全降级），不缓存（下次再尝试查询）
        return SYSTEM_LEVEL_SUB_TYPES

    # 3. 收集所有 ori_room_name
    all_ori_room_names: list = []
    for floor in floors:
        for room in floor.rooms.all():
            if room.ori_room_name:
                all_ori_room_names.append(room.ori_room_name)

    logger.debug(
        'utils_room_filter: specific_part=%s, 共 %d 个房间: %s',
        specific_part, len(all_ori_room_names), all_ori_room_names,
    )

    # 4. 若设备树未同步（floors 为空），降级为仅系统级面板（方案 B）
    if not floors:
        logger.info(
            'utils_room_filter: specific_part=%s 设备树未同步，降级为仅系统级面板（方案B）',
            specific_part,
        )
        result = SYSTEM_LEVEL_SUB_TYPES
        _update_cache(specific_part, result, now)
        return result

    # 5. 通过关键词匹配确定可用的 panel sub_type
    available_panels = _match_panel_sub_types(all_ori_room_names)
    result = SYSTEM_LEVEL_SUB_TYPES | available_panels

    logger.info(
        'utils_room_filter: specific_part=%s → available_sub_types=%s',
        specific_part, result,
    )

    _update_cache(specific_part, result, now)
    return result


def get_panel_param_blocklist(specific_part: str) -> frozenset:
    """
    获取该专有部分不应写入 DB 的 param_name 集合（不存在房间的参数黑名单）。

    用于 PLCLatestDataHandler 的落库过滤（模块 M4）。

    返回：
        frozenset[str]，包含所有不可用 panel sub_type 下的全部 param_name。
        若所有房间均存在，返回空 frozenset。
    """
    available_sub_types = get_available_sub_types(specific_part)
    unavailable_panels = ALL_PANEL_SUB_TYPES - available_sub_types

    if not unavailable_panels:
        return frozenset()  # 全部房间存在，无需过滤

    # 延迟导入
    from .models import DeviceConfig  # noqa: PLC0415
    blocked_params = DeviceConfig.objects.filter(
        sub_type__in=unavailable_panels,
        is_active=True,
    ).values_list('param_name', flat=True)

    result = frozenset(blocked_params)
    logger.debug(
        'utils_room_filter: specific_part=%s, blocklist 共 %d 个参数 (unavailable_panels=%s)',
        specific_part, len(result), unavailable_panels,
    )
    return result


def get_allowed_param_names(specific_part: str) -> Optional[list]:
    """
    获取该专有部分按需采集应读取的参数名白名单。

    用于 device_ondemand_refresh（M7-A）在 MQTT payload 中注入 allowed_params。

    返回：
        list[str] — 白名单参数名列表（非空时注入 payload）。
        None — 计算失败或异常（调用方降级为全量采集）。
    """
    try:
        available_sub_types = get_available_sub_types(specific_part)
        from .models import DeviceConfig  # noqa: PLC0415
        allowed = list(
            DeviceConfig.objects.filter(
                is_active=True,
                sub_type__in=available_sub_types,
            ).values_list('param_name', flat=True)
        )
        logger.debug(
            'utils_room_filter: get_allowed_param_names specific_part=%s, 共 %d 个参数',
            specific_part, len(allowed),
        )
        return allowed if allowed else None
    except Exception as e:
        logger.error(
            'utils_room_filter: get_allowed_param_names 失败 specific_part=%s: %s',
            specific_part, e,
        )
        return None


def invalidate_room_filter_cache(specific_part: str = None) -> None:
    """
    主动清除房型过滤缓存。

    Args:
        specific_part: 若提供，仅清除该专有部分的缓存；若为 None，清除全部缓存。

    调用时机：设备树同步成功后（device_tree_sync.py 中的 sync_one_specific_part
              以及批量同步完成回调）。
    """
    with _cache_lock:
        if specific_part is None:
            _room_filter_cache.clear()
            logger.info('utils_room_filter: 已清除全部房型过滤缓存')
        else:
            _room_filter_cache.pop(specific_part, None)
            logger.info('utils_room_filter: 已清除 %s 的房型过滤缓存', specific_part)


# ─────────────────────────────────────────────────────────────────────────────
# 内部实现
# ─────────────────────────────────────────────────────────────────────────────

def _match_panel_sub_types(ori_room_names: list) -> frozenset:
    """
    根据房间名称列表，确定哪些 panel sub_type 可用。

    规则：
    1. panel_study_room：任意房间名含"次卧"或"书房"
    2. panel_bedroom：任意房间名含"主卧"
    3. panel_children_room：任意房间名含"儿童房"或"主卧"
    4. panel_fourth_children：任意房间名含"儿童房"，且满足以下任一条件：
       - 该房间名同时含"四"（明确的四房户型标识）
       - 或房间总数 >= 4（间接推断四房户型）

    说明：
    - panel_children_room 与 panel_fourth_children 均含"儿童房"关键词。
      panel_children_room 覆盖三房儿童房，panel_fourth_children 覆盖四房儿童房。
      三房户型的 ori_room_name 如"儿童房"（无"四"字），不含四房判断 → 仅命中 panel_children_room。
      四房户型的 ori_room_name 如"四房儿童房"（含"四"字）→ 同时命中两者（panel_children_room 和
      panel_fourth_children），这是正确的：四房户型既有 panel_children_room 对应的参数组，
      也有 panel_fourth_children 对应的参数组。
    """
    available: set = set()
    all_names_joined = ' '.join(ori_room_names)

    for sub_type, keywords in SUB_TYPE_TO_ROOM_KEYWORDS.items():
        if sub_type == 'panel_fourth_children':
            # 四房儿童房：需要有"儿童房"关键词，且至少一个房间名含"四"或房间总数 >= 4
            has_fourth_children = any(
                '儿童房' in name and ('四' in name or len(ori_room_names) >= 4)
                for name in ori_room_names
            )
            if has_fourth_children:
                available.add(sub_type)
        else:
            if any(kw in all_names_joined for kw in keywords):
                available.add(sub_type)

    return frozenset(available)


def _update_cache(specific_part: str, result: frozenset, timestamp: float) -> None:
    """线程安全地更新缓存。"""
    with _cache_lock:
        _room_filter_cache[specific_part] = (result, timestamp)
