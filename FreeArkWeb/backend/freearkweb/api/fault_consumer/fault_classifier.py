"""
fault_consumer/fault_classifier.py — 故障字段识别与分类（MOD-BE-FM-02，v0.6.3-FM）

提供三个纯函数：
  - is_fault_candidate(param_name) → bool
  - is_fault_active(param_name, value) → bool
  - get_fault_type_and_severity(param_name) → (fault_type, severity)
  - get_fault_message(param_name) → str

复用 fault_utils.FAULT_PARAM_NAMES 和 _ERROR_N_PATTERN（只读引用，不修改 fault_utils）。
扩展支持 fresh_air_fault_bit_* 位域字段（v0.6.0 新增）。
"""

import re as _re

from .constants import (
    EXACT_FAULT_MAP,
    SUFFIX_FAULT_RULES,
    _FRESH_AIR_BIT_PATTERN,
    _ERROR_N_PATTERN,
    ERROR_CODE_LABELS,
)

# error_N 数字提取（仅用于 get_fault_message 兜底，不依赖 fault_utils）
_ERROR_N_DIGITS = _re.compile(r'^error_(\d+)$')

# 从 fault_utils 只读引用具名故障字段集合
try:
    from api.fault_utils import FAULT_PARAM_NAMES
except ImportError:
    # 单元测试独立运行时的降级
    FAULT_PARAM_NAMES = frozenset()


def is_fault_candidate(param_name: str) -> bool:
    """判断 param_name 是否可能是故障相关字段。

    覆盖范围：
      - fault_utils.FAULT_PARAM_NAMES 中所有具名字段（含 comm_fault_timeout）
      - error_<N> 模式字段（正则 ^error_\\d+$）
      - fresh_air_fault_bit_<N> 模式字段（正则 ^fresh_air_fault_bit_\\d+$）

    不覆盖：
      - fresh_air_fault_status（位域整体字段，由 PLC 拉取路径处理，非 MQTT 直接上报的位字段）
    """
    return (
        param_name in FAULT_PARAM_NAMES
        or bool(_ERROR_N_PATTERN.match(param_name))
        or bool(_FRESH_AIR_BIT_PATTERN.match(param_name))
    )


def is_fault_active(param_name: str, value) -> bool:
    """判断某参数的当前值是否处于故障态。

    判定规则（ADR-FM-03）：
      - comm_fault_timeout:   value != "normal" 且 value 非 None
      - error_<N>:            value 不等于 "0"（str）且不等于 0（int）且非 None
      - 其他具名故障字段:      value != 0 且非 None
      - fresh_air_fault_bit_*:value != 0 且非 None

    Returns:
        True  → 当前为故障态
        False → 当前为正常态（或 value 无法判断）
    """
    if value is None:
        return False

    if param_name == 'comm_fault_timeout':
        return str(value) != 'normal'

    if bool(_ERROR_N_PATTERN.match(param_name)):
        # error_N 上报为字符串 "0" 或整数 0 时为正常
        try:
            return int(value) != 0
        except (TypeError, ValueError):
            return str(value) not in ('0', '')

    if bool(_FRESH_AIR_BIT_PATTERN.match(param_name)):
        try:
            return int(value) != 0
        except (TypeError, ValueError):
            return False

    # 其他具名故障字段：非零即故障
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return bool(value)


def get_fault_type_and_severity(param_name: str) -> tuple:
    """根据 param_name 返回 (fault_type, severity) 元组。

    优先级：精确匹配 > 后缀匹配 > fresh_air_fault_bit_* > error_N > 默认

    Returns:
        tuple: (fault_type, severity)，例如 ('comm', 'error'), ('fresh_air', 'warning')
    """
    # 1. 精确匹配
    if param_name in EXACT_FAULT_MAP:
        return EXACT_FAULT_MAP[param_name]

    # 2. 后缀模式匹配
    for suffix, fault_type, severity in SUFFIX_FAULT_RULES:
        if param_name.endswith(suffix):
            return (fault_type, severity)

    # 3. fresh_air_fault_bit_* 位域
    if bool(_FRESH_AIR_BIT_PATTERN.match(param_name)):
        return ('fresh_air', 'warning')

    # 4. error_N 通用 PLC 故障码
    if bool(_ERROR_N_PATTERN.match(param_name)):
        return ('other_error', 'error')

    # 5. 默认兜底
    return ('other_error', 'error')


def get_fault_message(param_name: str) -> str:
    """生成 fault_event.fault_message 可读描述（BUG-FM-008 修复，v0.6.3-FM）。

    优先级：
      1. ERROR_CODE_LABELS 字典查表（中文描述，覆盖 error_N 和命名型 fault_code）
      2. error_N 通用兜底："设备故障 (错误码 N)"
      3. 其他（fresh_air_fault_bit_N 等）：下划线→空格，首字母大写（原逻辑保留）

    Returns:
        str: 故障描述文本，最长 255 字符
    """
    # 1. 优先字典查表
    if param_name in ERROR_CODE_LABELS:
        return ERROR_CODE_LABELS[param_name][:255]
    # 2. error_N 通用兜底
    m = _ERROR_N_DIGITS.match(param_name)
    if m:
        return f'设备故障 (错误码 {m.group(1)})'[:255]
    # 3. 其他（fresh_air_fault_bit_N 等）维持原逻辑
    msg = param_name.replace('_', ' ').capitalize()
    return msg[:255]
