SWITCH_LABELS = {"0": "关", "1": "开"}

PARAM_VALUE_LABELS = {
    "_switch": SWITCH_LABELS,
    "_mode": {"0": "制冷", "1": "制热", "2": "通风", "3": "除湿"},
}

# v0.5.0: 精确参数名到标签的映射（优先级高于后缀匹配，REQ-FUNC-003, ADR-09 §4）
PARAM_EXACT_VALUE_LABELS = {
    'away_energy_saving': {"0": "未启用离家节能", "1": "启用离家节能"},
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
            return mapping.get(raw_str, raw_str)
    unit = ""
    for suffix, u in PARAM_UNITS.items():
        if param_name.endswith(suffix):
            unit = f" {u}"
            break
    return f"{raw_str}{unit}"
