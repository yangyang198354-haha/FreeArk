SWITCH_LABELS = {"0": "关", "1": "开"}

PARAM_VALUE_LABELS = {
    "_switch": SWITCH_LABELS,
    # v0.5.1: 枚举从 1 起（REQ-FUNC-001）；key=0 历史兼容见 get_display_value
    "_mode": {"1": "制冷", "2": "制热", "3": "通风", "4": "除湿"},
}

# v0.5.0: 精确参数名到标签的映射（优先级高于后缀匹配，REQ-FUNC-003, ADR-09 §4）
PARAM_EXACT_VALUE_LABELS = {
    'away_energy_saving': {"0": "未启用离家节能", "1": "启用离家节能"},
    # v0.5.1: central_energy_supply 三值枚举（REQ-FUNC-003）
    'central_energy_supply': {"1": "制冷", "2": "制热", "3": "无"},
}

PARAM_UNITS = {
    "_temp_setting": "℃",
    "_temperature": "℃",
    "_humidity": "%RH",
}


def get_value_options(param_name: str) -> list:
    # v0.5.0: 精确名优先（REQ-FUNC-003）
    if param_name in PARAM_EXACT_VALUE_LABELS:
        return [{"raw": k, "label": v} for k, v in PARAM_EXACT_VALUE_LABELS[param_name].items()]
    # 后缀匹配降级
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return [{"raw": k, "label": v} for k, v in mapping.items()]
    return []


def get_display_value(param_name: str, raw_value) -> str:
    if raw_value is None:
        return "—"
    raw_str = str(raw_value)
    # v0.5.0: 精确名优先（REQ-FUNC-003）
    if param_name in PARAM_EXACT_VALUE_LABELS:
        return PARAM_EXACT_VALUE_LABELS[param_name].get(raw_str, raw_str)
    # 后缀匹配降级
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            result = mapping.get(raw_str)
            if result is not None:
                return result
            # v0.5.1: 历史旧值 0 的 operation_mode 兼容映射 → 制冷（REQ-NFR-001）
            if suffix == '_mode' and raw_str == '0':
                return '制冷'
            return raw_str
    # v0.6.0: _temp_setting 参数存储放大 10 倍的整数，展示时须 ÷10 保留一位小数
    if param_name.endswith("_temp_setting"):
        try:
            display_val = f"{float(raw_value) / 10:.1f}"
            return f"{display_val} ℃"
        except (TypeError, ValueError):
            # raw_value 非数字时安全兜底，按原逻辑返回带单位字符串
            return f"{raw_str} ℃"
    unit = ""
    for suffix, u in PARAM_UNITS.items():
        if param_name.endswith(suffix):
            unit = f" {u}"
            break
    return f"{raw_str}{unit}"
