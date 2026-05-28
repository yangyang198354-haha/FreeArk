"""
fault_consumer/constants.py — 故障消费者常量定义（MOD-BE-FM-01，v0.6.3-FM）

集中定义：
  - 故障类型映射（精确 + 后缀模式）
  - 位域故障正则
  - sub_type → fault_code 反向映射（供 API 过滤）
  - sub_type → (product_codes, room_keywords) 房间过滤规则（BUG-FM-006 修复）
  - 设备名称覆盖字典（BUG-FM-007 修复）
  - 故障码中文描述映射（BUG-FM-008 修复）
  - 标签字典（供 fault-event-categories 接口）

严禁修改 api/fault_utils.py（v0.5.3-FCC 模块，只读引用）。

变更记录：
  v0.6.3-FM（BUG-FM-006）：新增 SUB_TYPE_ROOM_FILTER，替代 v0.6.2 的
    SUB_TYPE_TO_PRODUCT_CODES。通过 device_node JOIN device_room 的
    ori_room_name 关键词匹配，在 error_N 通用码场景下按房间区分温控面板。
    living_room_thermostat（product_code=260001）天然无需房间过滤；
    study_room/bedroom/children_room/fourth_children_room 各自携带房间关键词。
    参见：docs/troubleshooting/BUG-FM-006_room_filter_by_device_join.md

  v0.6.3-FM（BUG-FM-007）：新增 DEVICE_NAME_OVERRIDE，在 serializer 层覆盖
    特定 product_code 的设备名称。130004（新风机）DeviceNode.device_name="新风"
    统一归一化为"新风机"，不修改 DB 和 device_tree_sync。
    参见：docs/troubleshooting/BUG-FM-007_fresh_air_device_name_normalization.md

  v0.6.3-FM（BUG-FM-008）：新增 ERROR_CODE_LABELS，为 error_N 及命名型
    fault_code 提供中文描述查表。get_fault_message() 优先字典查表，
    未映射的 error_N 走通用兜底"设备故障 (错误码 N)"，其余保持原逻辑。
    参见：docs/troubleshooting/BUG-FM-008_fault_message_zh_translation.md

  v0.6.2-FM（BUG-FM-005）：新增 SUB_TYPE_TO_PRODUCT_CODES（已被 v0.6.3 替代）。
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
# sub_type → (product_codes, room_keywords) 房间过滤规则（BUG-FM-006 修复）
# ADR-FM-06-ROOM-FILTER：通过 device_node JOIN device_room 的 ori_room_name
# 关键词匹配，在 error_N 通用码场景下按房间区分温控面板 sub_type。
#
# 数据结构：dict[str, tuple[list[str], list[str]]]
#   key   → sub_type 名称
#   value → (product_codes, room_keywords)
#           product_codes:  设备 product_code 列表
#           room_keywords:  ori_room_name 关键词列表（OR 匹配；空列表=不过滤房间）
#
# 房间过滤逻辑（views_fault.py 实现）：
#   - room_keywords 非空 → 子查询 device_node JOIN device_room（ori_room_name__regex）
#     取满足 (product_code, room_keyword) 的 device_sn 集合，q |= Q(device_sn__in=sns)
#   - room_keywords 为空 → 直接 q |= Q(product_code__in=product_codes)（无房间过滤）
#   - 同时保留 Q(fault_code__in=fault_codes)（命名型 fault_code 兼容路径）
#   - 同时保留 fresh_air_unit 的 fault_code__startswith='fresh_air_fault_bit_' 前缀分支
#
# 生产设备分布（device_node JOIN device_room 实测，2026-05）：
#   product_code=260001（主温控）  ori_room_name='客厅'  634 户
#   product_code=120003（温控面板）ori_room_name='次卧'  634 户
#   product_code=120003（温控面板）ori_room_name='主卧'  634 户
#   product_code=120003（温控面板）ori_room_name='儿童房' 634 户
#   product_code=120003（温控面板）ori_room_name='书房'  418 户
#
# 注意（维护人员必读）：
#   - living_room_thermostat 的 product_code=260001 天然=客厅，room_keywords=[]（不过滤）
#   - study_room_thermostat 映射书房+次卧（utils_room_filter v0.5.7 历史语义延续）
#   - fourth_children_room_thermostat 保留（用户决定不删），房间关键词等同 children_room，
#     device_room 中无独立"第四儿童房"，只能映射到"儿童房"关键词；UI 可见，行为与
#     children_room_thermostat 等价（四房户型第二个儿童房，同一 device_room 分组）
#   - 替代已废弃的 SUB_TYPE_TO_PRODUCT_CODES（v0.6.2）
# ---------------------------------------------------------------------------

SUB_TYPE_ROOM_FILTER: dict = {
    # (product_codes, room_keywords)；room_keywords 为空表示不过滤房间
    'living_room_thermostat':           (['260001'], []),
    'study_room_thermostat':            (['120003'], ['书房', '次卧']),
    'bedroom_thermostat':               (['120003'], ['主卧']),
    'children_room_thermostat':         (['120003'], ['儿童房']),
    'fourth_children_room_thermostat':  (['120003'], ['儿童房']),
    'fresh_air_unit':                   (['130004'], []),
    'hydraulic_module':                 (['270001'], []),
    'energy_meter':                     (['250001'], []),
    'air_quality_sensor':               (['100007'], []),
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

# ---------------------------------------------------------------------------
# 设备名称强制覆盖（BUG-FM-007 修复，v0.6.3-FM）
# 在 serializer 层（serializers_fault.py）覆盖 DeviceNode.device_name，
# 最局部、最可逆，不修改 DB 和 device_tree_sync.py。
#
# 背景：130004（新风机）的 DeviceNode.device_name 全部 = "新风"（634 条统一），
#       但 device_tree_sync.py:248 会用屏侧 deviceName 覆盖，直接改 DB 无效。
#       改 sync 逻辑风险大，选择在 serializer 边界归一化显示名。
#
# 格式：product_code（str）→ 强制显示名（str）
# ---------------------------------------------------------------------------

DEVICE_NAME_OVERRIDE: dict = {
    '130004': '新风机',
}

# ---------------------------------------------------------------------------
# 故障码中文描述映射（BUG-FM-008 修复，v0.6.3-FM）
# 来源：监听数据包含的内容.docx 解析整理
#
# 使用场景：fault_classifier.get_fault_message() 优先字典查表；
#   未在此字典的 error_N 走通用兜底"设备故障 (错误码 N)"；
#   未在此字典的命名码走原 _.replace('_',' ').capitalize() 逻辑。
#
# 严禁修改 fault_utils.py（v0.5.3-FCC 模块，只读引用）。
# ---------------------------------------------------------------------------

ERROR_CODE_LABELS: dict = {
    # ── 通用 ──
    'comm_fault_timeout': '通信超时',

    # ── 水力模块 (product_code=270001) ──
    'error_140': '低温故障',
    'error_82':  '新风机停机故障',

    # ── 主温控（客厅 product_code=260001 sn=22001）──
    'error_673': '内置温度传感器故障',
    'error_674': '内置湿度传感器故障',
    'error_675': '外置温度传感器故障',
    'error_679': '通信故障',

    # ── 儿童房温控面板 (120003 sn=22549) ──
    'error_703': '内置温度传感器故障',
    'error_704': '内置湿度传感器故障',
    'error_705': '外置温度传感器故障',
    'error_709': '通信故障',

    # ── 主卧温控面板 (120003 sn=22550) ──
    'error_733': '内置温度传感器故障',
    'error_734': '内置湿度传感器故障',
    'error_735': '外置温度传感器故障',
    'error_739': '通信故障',

    # ── 次卧温控面板 (120003 sn=22551) ──
    'error_763': '内置温度传感器故障',
    'error_764': '内置湿度传感器故障',
    'error_765': '外置温度传感器故障',
    'error_769': '通信故障',

    # ── 空气品质 (100007) 位域复合故障 ──
    'error_194': '空气品质设备故障',

    # ── 命名型 fault_code（已存在于 EXACT_FAULT_MAP）──
    'fresh_air_unit_stop_error':               '新风机停机故障',
    'fresh_air_unit_communication_error':      '新风机通信故障',
    'hydraulic_module_low_temp_error':         '水力模块低温故障',
    'energy_meter_status_communication_error': '能耗表通信故障',
    'air_quality_sensor_communication_error':  '空气品质传感器通信故障',
}
