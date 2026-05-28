"""
fault_consumer/constants.py — 故障消费者常量定义（MOD-BE-FM-01，v0.6.2-FM）

集中定义：
  - 故障类型映射（精确 + 后缀模式）
  - 位域故障正则
  - sub_type → fault_code 反向映射（供 API 过滤）
  - sub_type → product_code 反向映射（BUG-FM-005 修复，供 OR 联合过滤）
  - 标签字典（供 fault-event-categories 接口）

严禁修改 api/fault_utils.py（v0.5.3-FCC 模块，只读引用）。

变更记录：
  v0.6.2-FM（BUG-FM-005）：新增 SUB_TYPE_TO_PRODUCT_CODES，用于在生产数据库中
    fault_code 为通用 error_N 格式时，通过 product_code 识别设备类型。
    背景：生产 fault_event 表中命名型 fault_code（如 study_room_*）实际上不存在，
    几乎所有故障码均为 error_N 格式，导致 sub_type 过滤 100% 失效。
    设计权衡：error_N 故障码不携带房间维度信息，因此多个温控 sub_type
    （living_room/study_room/bedroom/children_room 等）均映射到相同 product_code
    集合（260001/120003）。用户若需要按房间筛选，应同时使用 specific_part 筛选器。
    参见：docs/troubleshooting/BUG-FM-005_sub_type_filter_breaks_on_generic_error_codes.md
"""

import re

# ---------------------------------------------------------------------------
# 故障类型映射：精确匹配（优先级高于后缀匹配）
# ---------------------------------------------------------------------------

# (fault_type, severity)
EXACT_FAULT_MAP: dict = {
    'comm_fault_timeout':                       ('comm',        'error'),
    'fresh_air_unit_stop_error':                ('fresh_air',   'error'),
    'fresh_air_unit_communication_error':       ('comm',        'error'),
    'hydraulic_module_low_temp_error':          ('other_error', 'error'),
    'energy_meter_status_communication_error':  ('comm',        'error'),
    'air_quality_sensor_communication_error':   ('comm',        'error'),
}

# ---------------------------------------------------------------------------
# 故障类型映射：后缀模式匹配（按声明顺序，先匹配先生效）
# ---------------------------------------------------------------------------

# list of (suffix, fault_type, severity)
SUFFIX_FAULT_RULES: list = [
    ('_communication_error',        'comm',        'error'),
    ('_temp_sensor_error',          'sensor',      'error'),
    ('_humidity_sensor_error',      'sensor',      'error'),
    ('_external_temp_sensor_error', 'sensor',      'error'),
]

# ---------------------------------------------------------------------------
# 位域故障正则
# ---------------------------------------------------------------------------

# fresh_air_fault_bit_<N>（v0.6.0 新增，MQTT 上报单个位字段）
_FRESH_AIR_BIT_PATTERN = re.compile(r'^fresh_air_fault_bit_\d+$')

# error_<N>（与 fault_utils._ERROR_N_PATTERN 一致，此处独立定义避免循环引用）
_ERROR_N_PATTERN = re.compile(r'^error_\d+$')

# ---------------------------------------------------------------------------
# sub_type → product_code 列表（BUG-FM-005 修复，供 API 查询参数 sub_type 过滤）
# ADR-FM-05-SUBTYPE-v2：当 fault_code 为通用 error_N 格式时，通过 product_code 识别设备类型。
#
# 设计权衡（重要，维护人员必读）：
#   - error_N 故障码不携带房间维度，因此温控类 sub_type（如 living_room_thermostat、
#     study_room_thermostat 等）均映射到相同的 product_code 集合 ['260001', '120003']。
#     这意味着这些 sub_type 过滤出的结果集是相同的——这是数据模型层面的限制，非 BUG。
#   - 用户若需按房间区分，应配合 specific_part（房号）筛选器组合使用。
#   - 本映射不替代 SUB_TYPE_TO_FAULT_CODES，两者在 views_fault.py 中 OR 联合使用。
#
# product_code 来源（生产分布，2026-05 实测）：
#   260001 → 主温控（529 条故障记录）
#   120003 → 温控面板（486 条故障记录）
#   130004 → 新风机（201 条故障记录）
#   270001 → 水力模块（122 条故障记录）
#   250001 → 能耗表（206 条故障记录）
#   100007 → 空气品质传感器（360 条故障记录）
# ---------------------------------------------------------------------------

SUB_TYPE_TO_PRODUCT_CODES: dict = {
    # 5 个温控 sub_type 均映射到主温控(260001) + 温控面板(120003)
    # （error_N 通用码丢失了房间维度，牺牲房间精度换取"能筛出来"）
    'living_room_thermostat':           ['260001', '120003'],
    'study_room_thermostat':            ['260001', '120003'],
    'bedroom_thermostat':               ['260001', '120003'],
    'children_room_thermostat':         ['260001', '120003'],
    'fourth_children_room_thermostat':  ['260001', '120003'],
    'fresh_air_unit':                   ['130004'],
    'hydraulic_module':                 ['270001'],
    'energy_meter':                     ['250001'],
    'air_quality_sensor':               ['100007'],
}

# ---------------------------------------------------------------------------
# sub_type → fault_code 列表（供 API 查询参数 sub_type 过滤）
# ADR-FM-05-SUBTYPE：API 将 sub_type 翻译为 fault_code__in 集合
# 注意：生产数据库中命名型 fault_code 实际上不存在（见 BUG-FM-005 RCA），
#       本映射保留用于兼容未来可能出现的命名型故障码，以及 OR 联合过滤时的精确匹配。
# ---------------------------------------------------------------------------

SUB_TYPE_TO_FAULT_CODES: dict = {
    'living_room_thermostat': [
        'living_room_temp_sensor_error',
        'living_room_humidity_sensor_error',
        'living_room_external_temp_sensor_error',
        'living_room_communication_error',
    ],
    'study_room_thermostat': [
        'study_room_temp_sensor_error',
        'study_room_humidity_sensor_error',
        'study_room_external_temp_sensor_error',
        'study_room_communication_error',
    ],
    'bedroom_thermostat': [
        'bedroom_temp_sensor_error',
        'bedroom_humidity_sensor_error',
        'bedroom_external_temp_sensor_error',
        'bedroom_communication_error',
    ],
    'children_room_thermostat': [
        'children_room_temp_sensor_error',
        'children_room_humidity_sensor_error',
        'children_room_external_temp_sensor_error',
        'children_room_communication_error',
    ],
    'fourth_children_room_thermostat': [
        'fourth_children_room_temp_sensor_error',
        'fourth_children_room_humidity_sensor_error',
        'fourth_children_room_external_temp_sensor_error',
        'fourth_children_room_communication_error',
    ],
    'fresh_air_unit': [
        'fresh_air_unit_stop_error',
        'fresh_air_unit_communication_error',
        # fresh_air_fault_bit_* 字段用前缀匹配，不在此列举（见 views_fault.py）
    ],
    'hydraulic_module': [
        'hydraulic_module_low_temp_error',
    ],
    'energy_meter': [
        'energy_meter_status_communication_error',
    ],
    'air_quality_sensor': [
        'air_quality_sensor_communication_error',
    ],
}

# ---------------------------------------------------------------------------
# 标签字典（供 /api/devices/fault-event-categories/ 接口）
# ---------------------------------------------------------------------------

SUB_TYPE_LABELS: dict = {
    'living_room_thermostat':           '客厅温控面板',
    'study_room_thermostat':            '书房温控面板',
    'bedroom_thermostat':               '主卧温控面板',
    'children_room_thermostat':         '儿童房温控面板',
    'fourth_children_room_thermostat':  '第四儿童房温控面板',
    'fresh_air_unit':                   '新风机',
    'hydraulic_module':                 '水力模块',
    'energy_meter':                     '能耗表',
    'air_quality_sensor':               '空气品质传感器',
}

FAULT_TYPE_LABELS: dict = {
    'comm':        '通信故障',
    'sensor':      '传感器故障',
    'fresh_air':   '新风故障',
    'other_error': '其他故障',
}

# ---------------------------------------------------------------------------
# product_code → 友好名映射（兜底一，MOD-BE-UX-02，v0.6.1-FM-UX）
# 主路径：device_node.device_name（进程内 dict 缓存）
# 兜底路径：此映射；基于生产 device_list API 分析（3-1-702 楼层设备清单）
# 维护方式：硬编码，由开发人员按需添加新 product_code
# OQ-05 裁决：硬编码在 constants.py，不引入新 DB 表
# ---------------------------------------------------------------------------

PRODUCT_CODE_LABELS: dict = {
    '10016':  '自由方舟（主机）',
    '270001': '水力模块',
    '130004': '新风机',
    '250001': '能耗表',
    '100007': '空气品质',
    '260001': '主温控',
    '120003': '温控面板',
    # 260002：生产实测有 3 条故障记录，product_code 未在设备清单中出现，
    # 疑似为主温控的另一型号或测试设备，待硬件团队确认后更新标签。
    '260002': '未知设备 260002',
}
