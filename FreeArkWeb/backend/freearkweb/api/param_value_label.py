SWITCH_LABELS = {"0": "关", "1": "开"}

PARAM_VALUE_LABELS = {
    "_switch": SWITCH_LABELS,
    "_mode": {"0": "制冷", "1": "制热", "2": "通风", "3": "除湿"},
}

PARAM_UNITS = {
    "_temp_setting": "℃",
    "_temperature": "℃",
    "_humidity": "%RH",
}


def get_value_options(param_name: str) -> list:
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return [{"raw": k, "label": v} for k, v in mapping.items()]
    return []


def get_display_value(param_name: str, raw_value) -> str:
    if raw_value is None:
        return "—"
    raw_str = str(raw_value)
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return mapping.get(raw_str, raw_str)
    unit = ""
    for suffix, u in PARAM_UNITS.items():
        if param_name.endswith(suffix):
            unit = f" {u}"
            break
    return f"{raw_str}{unit}"
