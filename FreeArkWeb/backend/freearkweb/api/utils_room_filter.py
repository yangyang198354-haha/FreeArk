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

# ── 面板房间标签真值表（v1.14.0，2026-08-01 生产标定实测）────────────────────
#
# 来源：panel_calib_capture + panel_calib_correlate 生产实测
#   采集 30 分钟 / 28838 条屏端记录 / 399 户，成功标定 355 户，
#   其中 253 户 high 置信度，只呈现 2 种配对模式、零例外。
#
# ⚠ 本表**不是**照抄 plc_config.json —— 实测证明该文件的
#   「四房」分支把「主卧」与「书房」标反了（233 户实证）：
#     plc_config 称 offset 1395=四房主卧、1515=四房书房；
#     实测为        offset 1395=四房书房、1515=四房主卧。
#   「三房」分支则与 plc_config 完全一致（120 户实证）。
#   修改本表前请重跑 panel_calib_correlate 复核，勿以 plc_config 为据。
#
# 等价表述：真实配对 = 云端 deviceSn 升序 ↔ PLC 偏移量升序
#   （书房 22552→1395、次卧 22553→1455、主卧 22554→1515、儿童房 22555→1575）
#
# 展示序按房间重要性排列：主卧 → 次卧 → 书房 → 儿童房
#
# 格式：sub_type -> (三房房间名, 三房展示序, 四房房间名, 四房展示序)
#       房间名为 None 表示该户型下不存在此面板
PANEL_ROOM_TABLE: dict = {
    #                        PLC offset   三房            四房
    'panel_children_room':   ('儿童房', 3,   '书房',   3),   # 1395
    'panel_bedroom':         ('主卧',   1,   '次卧',   2),   # 1455
    'panel_study_room':      ('次卧',   2,   '主卧',   1),   # 1515
    'panel_fourth_children': (None,     None, '儿童房', 4),   # 1575
}

# 温控面板的屏端产品编码（用于按面板数判定户型）
_PANEL_PRODUCT_CODE: str = '120003'

# 户型标识
HOUSE_TYPE_THREE: str = 'three'
HOUSE_TYPE_FOUR: str = 'four'

# 排在所有面板之后的兜底展示序（户型未知/表中无该 sub_type 时）
_ORDER_FALLBACK: int = 99

# ── 进程内缓存 ────────────────────────────────────────────────────────────────
# 格式：{specific_part: (available_sub_types: frozenset, cached_at: float)}
_room_filter_cache: dict = {}
# 格式：{specific_part: (house_type: str|None, cached_at: float)}
_house_type_cache: dict = {}
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


def get_house_type(specific_part: str) -> Optional[str]:
    """判定该专有部分的户型，返回 HOUSE_TYPE_THREE / HOUSE_TYPE_FOUR / None。

    主判据：屏厂云端设备树中温控面板（product_code=120003）的**数量**
        4 块 → 四房；3 块 → 三房。
        采集实证（2026-08-01，399 户）：全部住户均为 3 或 4 块，判据干净。
        面板计数比房间命名鲁棒——业主把儿童房叫成书房不会骗过它。

    交叉校验：房间名含"书房" 应当对应四房。两者不一致时记 WARNING
        并以面板计数为准；该告警可自动暴露既不像三房也不像四房的异常户。

    返回 None 的情形：设备树未同步、无面板、或面板数既非 3 也非 4。
        调用方应据此回退到全局默认标签（保持既有行为，不做臆测）。

    缓存：TTL 300s，与 get_available_sub_types 共用锁与失效入口。
    """
    now = time.monotonic()
    with _cache_lock:
        cached = _house_type_cache.get(specific_part)
        if cached is not None:
            house_type, cached_at = cached
            if (now - cached_at) < _CACHE_TTL_SECONDS:
                return house_type

    from .models import DeviceNode  # noqa: PLC0415
    try:
        rooms = list(
            DeviceNode.objects
            .filter(
                room__floor__owner__specific_part=specific_part,
                product_code=_PANEL_PRODUCT_CODE,
            )
            .values_list('room__ori_room_name', flat=True)
        )
    except Exception as e:
        logger.error(
            'utils_room_filter: get_house_type 查询失败 specific_part=%s: %s',
            specific_part, e,
        )
        return None  # 异常不缓存，下次重试

    panel_count = len(rooms)
    if panel_count == 4:
        house_type = HOUSE_TYPE_FOUR
    elif panel_count == 3:
        house_type = HOUSE_TYPE_THREE
    else:
        house_type = None
        if panel_count:
            logger.warning(
                'utils_room_filter: specific_part=%s 面板数=%d（既非3也非4），'
                '户型无法判定，回退全局默认标签。房间=%s',
                specific_part, panel_count, rooms,
            )

    # 交叉校验：含"书房"应为四房
    has_study = any(r and '书房' in r for r in rooms)
    if house_type is not None:
        expected = HOUSE_TYPE_FOUR if has_study else HOUSE_TYPE_THREE
        if expected != house_type:
            logger.warning(
                'utils_room_filter: specific_part=%s 户型判据冲突——'
                '面板计数=%d→%s，但房间名%s"书房"→%s。以面板计数为准。房间=%s',
                specific_part, panel_count, house_type,
                '含' if has_study else '不含', expected, rooms,
            )

    with _cache_lock:
        _house_type_cache[specific_part] = (house_type, now)
    return house_type


def resolve_panel_room(specific_part: str, sub_type: str) -> Optional[str]:
    """按户型解析温控面板 sub_type 的**真实房间名**（PANEL_ROOM_TABLE 实测真值）。

    返回 None 表示无法解析——户型未知、非面板 sub_type、
    或该面板在此户型下不存在（如三房的 panel_fourth_children）。
    调用方应回退到 DeviceConfig.sub_type_display 全局默认值。
    """
    entry = PANEL_ROOM_TABLE.get(sub_type)
    if entry is None:
        return None
    house_type = get_house_type(specific_part)
    if house_type == HOUSE_TYPE_THREE:
        return entry[0]
    if house_type == HOUSE_TYPE_FOUR:
        return entry[2]
    return None


def resolve_panel_display(specific_part: str, sub_type: str,
                          fallback: str, suffix: str = '') -> str:
    """解析面板展示名，解析不出时原样返回 fallback。

    Args:
        fallback: 通常传 DeviceConfig.sub_type_display（全局默认值）
        suffix:   Web 端传 '-温控面板'；小程序端传 ''（纯房间名）
    """
    room = resolve_panel_room(specific_part, sub_type)
    return f'{room}{suffix}' if room else fallback


def get_panel_order(specific_part: str, sub_type: str) -> int:
    """面板展示序（主卧→次卧→书房→儿童房）。解析不出时排在最后。"""
    entry = PANEL_ROOM_TABLE.get(sub_type)
    if entry is None:
        return _ORDER_FALLBACK
    house_type = get_house_type(specific_part)
    order = entry[1] if house_type == HOUSE_TYPE_THREE else (
        entry[3] if house_type == HOUSE_TYPE_FOUR else None
    )
    return order if order is not None else _ORDER_FALLBACK


def resolve_sub_type_for_room(specific_part: str, ori_room_name: str) -> str:
    """真实房间名 → 面板 sub_type（PANEL_ROOM_TABLE 的**逆映射**，双射）。

    取代 `_match_panel_sub_types([room]) 取 next(iter(...))` 的旧做法——
    后者对单个房间名做关键词匹配，存在两个缺陷（v1.14.0 修复）：
      1. 坍缩：四房的「书房」与「次卧」都命中 panel_study_room，
         「主卧」与「儿童房」都命中 panel_children_room，
         四个房间只映射到两个 sub_type，且 panel_bedroom /
         panel_fourth_children 永远不可能被分配出来。
      2. 不确定：「主卧」同时命中 panel_bedroom 与 panel_children_room，
         next(iter(frozenset)) 的取值依赖字符串哈希，而 Python 默认随机化
         hash seed —— 后端每次重启，该房间挂的参数集就可能换一套。

    本函数按户型查表反解，一房一 sub_type，确定且无坍缩。
    房间名不在该户型模板内（如三房出现「书房」）时返回空字符串。
    """
    if not ori_room_name:
        return ''
    house_type = get_house_type(specific_part)
    if house_type == HOUSE_TYPE_THREE:
        idx = 0
    elif house_type == HOUSE_TYPE_FOUR:
        idx = 2
    else:
        return ''
    for sub_type, entry in PANEL_ROOM_TABLE.items():
        room = entry[idx]
        if room and room in ori_room_name:
            return sub_type
    return ''


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
            _house_type_cache.clear()
            logger.info('utils_room_filter: 已清除全部房型过滤缓存与户型缓存')
        else:
            _room_filter_cache.pop(specific_part, None)
            _house_type_cache.pop(specific_part, None)
            logger.info(
                'utils_room_filter: 已清除 %s 的房型过滤缓存与户型缓存', specific_part
            )


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
    4. panel_fourth_children（v0.5.7-fix2 校正）：同时满足以下核心条件：
       - 任意房间名含"书房"（has_study_room）—— 四房户型的决定性特征
       - 任意房间名含"儿童房"（has_children_keyword）
       OR（冗余识别）任意房间名同时含"儿童房"且含"四"字

    修复说明（fix2，2026-05-23）：
    原判断「含儿童房 AND 房间数 >= 4」中 len(ori_room_names) >= 4 为错误启发式。
    生产数据中三房户型（9-1-10-1002）房间总数为 5（含全屋/客厅等非卧室），
    全部误触发 panel_fourth_children，导致修复无效。
    根据生产全量 40 个专有部分扫描：「含书房 = 四房」，100% 吻合，无例外。
    核心判定规则改为「含书房 AND 含儿童房」，原「含'四'字」分支保留作冗余识别。

    说明：
    - panel_children_room 与 panel_fourth_children 均含"儿童房"关键词。
      panel_children_room 覆盖三房儿童房，panel_fourth_children 覆盖四房儿童房。
      三房户型（无书房）：仅命中 panel_children_room，不命中 panel_fourth_children。
      四房户型（有书房且有儿童房）：同时命中两者，这是正确的。
    """
    available: set = set()
    all_names_joined = ' '.join(ori_room_names)

    for sub_type, keywords in SUB_TYPE_TO_ROOM_KEYWORDS.items():
        if sub_type == 'panel_fourth_children':
            # fix2：核心判定改为「含书房 AND 含儿童房」
            # 冗余识别：房间名中含"四"且含"儿童房"（防御未来出现「四房儿童房」显式命名）
            has_study_room = any('书房' in name for name in ori_room_names)
            has_children_keyword = any('儿童房' in name for name in ori_room_names)
            has_explicit_fourth = any(
                '儿童房' in name and '四' in name for name in ori_room_names
            )
            if (has_study_room and has_children_keyword) or has_explicit_fourth:
                available.add(sub_type)
        else:
            if any(kw in all_names_joined for kw in keywords):
                available.add(sub_type)

    return frozenset(available)


def _update_cache(specific_part: str, result: frozenset, timestamp: float) -> None:
    """线程安全地更新缓存。"""
    with _cache_lock:
        _room_filter_cache[specific_part] = (result, timestamp)
