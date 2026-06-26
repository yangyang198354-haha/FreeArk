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
        'product_code_role': PRODUCT_CODE_ROLE,
        'mode_energy_link': MODE_ENERGY_LINK,
        'link_product_codes': LINK_PRODUCT_CODES,
    }
