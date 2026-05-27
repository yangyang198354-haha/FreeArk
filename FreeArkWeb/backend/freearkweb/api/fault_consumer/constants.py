"""
fault_consumer/constants.py — 故障消费者常量定义（MOD-BE-FM-01，v0.6.0-FM）

集中定义：
  - 故障类型映射（精确 + 后缀模式）
  - 位域故障正则
  - sub_type → fault_code 反向映射（供 API 过滤）
  - 标签字典（供 fault-event-categories 接口）

严禁修改 api/fault_utils.py（v0.5.3-FCC 模块，只读引用）。
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
# sub_type → fault_code 列表（供 API 查询参数 sub_type 过滤）
# ADR-FM-05-SUBTYPE：API 将 sub_type 翻译为 fault_code__in 集合
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
