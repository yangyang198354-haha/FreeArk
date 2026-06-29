"""
api.screen_param_config — 屏端（screen）MQTT 参数配置·单一权威（v1.10.0_miniprogram_param_settings）

小程序业主端通过屏端 MQTT 直连读写参数（DeviceWrite/DeviceStatusUpdate）。
本模块定义「可写 attrTag 白名单 + 控件/标签 + 值选项 + productCode 角色 + mode 联动」，
由 /api/miniapp/device-settings/config/ 下发给客户端，客户端不自带白名单（需求 C-04）。

可写集合对齐 web 版（views_device_settings.py 的 *_switch/*_temp_setting/*_mode/
away_energy_saving/central_energy_supply），但用屏端原生 attrTag 与语义串值
（实测见 docs/requirements/v1.10.0_miniprogram_param_settings/capture_findings_oq03.md）。
"""

# 屏端「可写」attrTag → 控件定义（值用屏端语义串；label/options 为展示层中文）
SCREEN_WRITABLE_ATTRS = {
    'switch': {
        'control': 'toggle', 'label': '开关',
        'options': [{'value': 'off', 'label': '关'}, {'value': 'on', 'label': '开'}],
    },
    'system_switch': {
        'control': 'toggle', 'label': '系统开关',
        'options': [{'value': 'off', 'label': '关'}, {'value': 'on', 'label': '开'}],
    },
    'temp_set': {
        'control': 'number', 'label': '温度设定', 'unit': '℃',
        'step': 0.5, 'min': 16, 'max': 30,
    },
    'out_temp_set': {
        'control': 'number', 'label': '出风温度设定', 'unit': '℃',
        'step': 0.5, 'min': 10, 'max': 30,
    },
    'mode': {
        'control': 'select', 'label': '运行模式',
        'options': [
            {'value': 'cold', 'label': '制冷'},
            {'value': 'hot', 'label': '制热'},
            {'value': 'wind', 'label': '通风'},
            {'value': 'dehumidification', 'label': '除湿'},
        ],
    },
    'energy_supply_mode': {
        'control': 'select', 'label': '能源供应',
        'options': [
            {'value': 'cold', 'label': '制冷'},
            {'value': 'hot', 'label': '制热'},
            {'value': 'no', 'label': '无'},
        ],
    },
    'energy_saving_sign': {
        'control': 'toggle', 'label': '离家节能',
        'options': [{'value': 'off', 'label': '未启用'}, {'value': 'on', 'label': '启用'}],
    },
    # 新风·风速 / 加湿（v1.12.0 #2）——实测在「面板控制器」productCode 10016 上（deviceSn 22153，房间 3-1-702）。
    # 2026-06-29 写抓包确认：wind_speed 写值 normal / high_speed；humidification_enable 写值 on / off（开关型）。
    # 用户确认风速仅两档（普通 / 高速），无低档。
    'wind_speed': {
        'control': 'select', 'label': '风速',
        'options': [
            {'value': 'normal', 'label': '普通'},      # ✅ 写确认
            {'value': 'high_speed', 'label': '高速'},  # ✅ 写确认
        ],
    },
    'humidification_enable': {
        'control': 'toggle', 'label': '加湿',
        'options': [{'value': 'off', 'label': '关'}, {'value': 'on', 'label': '开'}],
    },
}

# 屏端「只读」attrTag → 展示定义（仅小程序「详细」tab 用，不可写）。v1.12.1
#
# 关键背景（2026-06-29 抓包定性）：屏端 DeviceStatusUpdate 是**自描述**的，值按屏端
#   自己的短 attrTag 对齐（temp / humidity / mode …），与数据库 DeviceConfig.param_name
#   （PLC/S7 采集管线命名，如 living_room_temperature / operation_mode）**是两套词表**。
#   旧「详细」tab 用 DB param_name 去 MQTT attrs 里查，永远查不到 → 永久「采集中」。
#   故「详细」tab 改为：直接遍历屏端实推 attrTag，命中「可写 ∪ 本表」白名单才展示；
#   未命中者（error_* / comm_fault_timeout / plc_* / 空 tag）一律不显示。
# 值为屏端语义/数字串；options 用于把状态码转中文（如 condensation_alarm 0/1）。
# 标注「单位/语义待核实」的项先按推荐展示原值（值真实），后续再校准。
SCREEN_READONLY_ATTRS = {
    # 温控（主温控 260001 / 末端 120003）通用
    'temp': {'label': '当前温度', 'unit': '℃'},
    'humidity': {'label': '当前湿度', 'unit': '%'},
    'dew_point_temp': {'label': '露点温度', 'unit': '℃'},
    'NTC_temp': {'label': '探头温度(NTC)', 'unit': '℃'},
    'condensation_alarm': {
        'label': '结露报警',
        'options': [{'value': '0', 'label': '正常'}, {'value': '1', 'label': '报警'}],
    },
    # 主机 270001
    '2nd_inwater_temp_detect': {'label': '二次进水温度', 'unit': '℃'},
    '2nd_outwater_temp_detect': {'label': '二次出水温度', 'unit': '℃'},
    'primary_valve_opening': {'label': '一次阀开度', 'unit': '%'},  # 单位待核实
    # 新风 130004
    'fan_speed': {'label': '风机转速', 'unit': 'rpm'},
    'newwind_inlet_temp': {'label': '新风进风温度', 'unit': '℃'},
    'pau_out_temp': {'label': '送风温度', 'unit': '℃'},
    'pau_through_temp': {'label': '盘管温度', 'unit': '℃'},
    'pau_in_temp': {'label': '回风温度', 'unit': '℃'},  # 实测样例 101.2，疑似探头/缩放异常，待核实
    'one_water_valve_opening': {'label': '水阀开度', 'unit': '%'},
    'humi_lower_limit': {'label': '加湿下限', 'unit': '%'},
    'humi_upper_limit': {'label': '加湿上限', 'unit': '%'},
    'filter_max_life': {'label': '滤网寿命', 'unit': 'h'},
    'filter_working_time': {'label': '滤网已运行', 'unit': 'h'},
    # 能量计 250001（单位待核实）
    'total_cold_quantity': {'label': '累计冷量'},
    'total_hot_quantity': {'label': '累计热量'},
    'work_duration': {'label': '工作时长'},
    # 空气品质 100007
    'co2': {'label': 'CO₂', 'unit': 'ppm'},
    'pm25': {'label': 'PM2.5', 'unit': 'µg/m³'},
    'hcho': {'label': '甲醛', 'unit': 'mg/m³'},
    'tvoc': {'label': 'TVOC', 'unit': 'mg/m³'},
}

# productCode → 设备角色显示名（小程序按设备分组展示用）
PRODUCT_CODE_ROLE = {
    260001: '主温控器',
    120003: '末端温控',
    270001: '系统/能源主机',
    130004: '新风',
    250001: '能量计',
    100007: '空气质量',
    10016: '面板',
}

# 系统/能源主机改 mode 时，联动下发的 energy_supply_mode（复刻原厂 App 实测行为，ADR-08）
MODE_ENERGY_LINK = {
    'cold': 'cold',
    'hot': 'hot',
    'wind': 'no',
    'dehumidification': 'cold',
}

# 触发 mode↔energy_supply_mode 联动的设备 productCode（系统/能源主机）
LINK_PRODUCT_CODES = [270001]


def is_writable_attr(attr_tag: str) -> bool:
    """attr_tag 是否在屏端可写白名单内。"""
    return attr_tag in SCREEN_WRITABLE_ATTRS


def get_screen_param_config() -> dict:
    """供 config 接口下发的完整配置块。"""
    return {
        'writable_attrs': SCREEN_WRITABLE_ATTRS,
        'readonly_attrs': SCREEN_READONLY_ATTRS,
        'product_code_role': PRODUCT_CODE_ROLE,
        'mode_energy_link': MODE_ENERGY_LINK,
        'link_product_codes': LINK_PRODUCT_CODES,
    }
