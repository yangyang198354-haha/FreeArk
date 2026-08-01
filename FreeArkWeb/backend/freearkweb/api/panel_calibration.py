"""
panel_calibration.py — 温控面板 PLC 点位 ↔ 屏端设备 ↔ 真实房间 标定工具（共享逻辑）

背景（docs/analysis/plc_room_mapping_misalignment_rca.md）：
  Web 设备面板的房间标签来自全局静态表（DeviceConfig.sub_type_display），
  按 plc_config.json 的「四房」释义写死；而小程序参数设置页与故障管理走屏端体系
  （device_sn → DeviceRoom），端到端正确。3-1-702 实测证明该户 PLC 接线不符合
  plc_config 的任何一个（三房/四房）约定，故静态表与 plc_config 都不足以作为真值。

  本模块提供「用生产数据反推真值」的能力：PLC 与屏端对同一块面板都在连续上报
  温度/湿度/设定温度/开关，两侧数值应当近似相等。按数值一致度做一对一指派，
  即可推出 param_name 前缀 ↔ device_sn ↔ 房间 的配对关系。

设计约束：
  - 只读。本模块及配套命令不写任何业务表。
  - 不依赖稀疏事件（故障/凝露），用连续遥测，几小时数据即可收敛。
  - 屏端值不落库（后端不连厂端 broker），需由 panel_calib_capture 现场采集。

配套命令：
  panel_calib_snapshot   —— 只读快照，看某户 PLC 侧各槽位当前值 + 云端房间树
  panel_calib_capture    —— 订阅厂端 broker，采集屏端 DeviceStatusUpdate 到 JSONL
  panel_calib_correlate  —— 用 JSONL + DeviceParamHistory 做配对推断

参见：docs/analysis/plc_room_mapping_misalignment_rca.md
"""

import itertools
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PLC 侧槽位定义
# ---------------------------------------------------------------------------

# 四个温控面板在 PLC DB 中的槽位（偏移量步长 60）。
# description 逐字誊自 datacollection/resource/plc_config.json，仅作参考——
# 3-1-702 实测证明该标注对部分住户不成立，故本模块不以它为真值，只用于结果对照。
PANEL_SLOTS: tuple = (
    # (param_prefix,          sub_type,               switch_offset, plc_config 三房义, plc_config 四房义)
    ('children_room',         'panel_children_room',   1395, '儿童房', '主卧'),
    ('bedroom',               'panel_bedroom',         1455, '主卧',   '次卧'),
    ('study_room',            'panel_study_room',      1515, '次卧',   '书房'),
    ('fourth_children_room',  'panel_fourth_children', 1575, None,     '儿童房'),
)

PANEL_PREFIXES: tuple = tuple(s[0] for s in PANEL_SLOTS)

# 温控面板的屏端产品编码（DeviceNode.product_code）
PANEL_PRODUCT_CODE: str = '120003'

# ---------------------------------------------------------------------------
# 双侧信号对照表
# ---------------------------------------------------------------------------

# PLC param 后缀 ↔ 屏端 attrTag。两侧读的是同一个物理传感器，数值应近似相等。
#   tol       —— 判定「一致」的绝对误差容忍
#   weight    —— 该信号在总分中的权重
#   discrete  —— True 表示离散/二值信号，按精确相等判定，不用 tol
#
# ⚠ 容差必须小于「屏端上报分辨率」，否则同户各房间会互相匹配、margin 归零。
#   2026-08-01 生产实测（panel_calib_capture 抓包）：
#     temp / temp_set / dew_point_temp 分辨率 0.5（"24.5" "25.0" "25.5"）
#     humidity 分辨率 1.0（"53.0" "54.0"）
#   同一户四块面板的读数极为接近（3-1-7-702 实测：温度全为 25.0、湿度仅 53.0/54.0 之差），
#   故容差取「半个分辨率步长」，实质等价于定标后精确匹配，区分度全靠取值随时间的漂移轨迹。
CORRELATION_SIGNALS: tuple = (
    # (plc_suffix,           screen_attr_tag,   tol,   weight, discrete)
    ('_temperature',         'temp',            0.25,  3.0,    False),
    ('_humidity',            'humidity',        0.6,   2.5,    False),
    ('_temp_setting',        'temp_set',        0.25,  2.5,    False),
    ('_dew_point_setting',   'dew_point_temp',  0.25,  1.0,    False),
    ('_switch',              'switch',          0.0,   1.5,    True),
)

# PLC 侧整数存储可能带 ×10 定标（BigIntegerField 存 265 表示 26.5℃）。
# 逐信号自动探测，取一致度最高的定标。
CANDIDATE_SCALES: tuple = (1.0, 0.1)

# 屏端 switch 的取值形态（on/off 或 1/0）→ 归一化为 1.0/0.0
_SWITCH_TRUE = {'1', 'on', 'true', 'open', '开'}
_SWITCH_FALSE = {'0', 'off', 'false', 'close', 'closed', '关'}


def plc_param(prefix: str, suffix: str) -> str:
    """拼出 PLC param_name，如 ('study_room', '_temperature') → 'study_room_temperature'。"""
    return f'{prefix}{suffix}'


def all_plc_params() -> list:
    """本标定关心的全部 PLC param_name（4 槽位 × 5 信号）。"""
    return [
        plc_param(p, sfx)
        for p in PANEL_PREFIXES
        for sfx, _tag, _tol, _w, _d in CORRELATION_SIGNALS
    ]


def screen_attr_tags() -> list:
    """本标定关心的全部屏端 attrTag。"""
    return [tag for _sfx, tag, _tol, _w, _d in CORRELATION_SIGNALS]


# ---------------------------------------------------------------------------
# 取值归一化
# ---------------------------------------------------------------------------

def to_float(value, discrete: bool = False) -> Optional[float]:
    """把 PLC / 屏端的原始值转成 float。无法解析返回 None。

    离散信号额外接受 on/off、开/关 这类字符串形态。
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if discrete:
        low = s.lower()
        if low in _SWITCH_TRUE:
            return 1.0
        if low in _SWITCH_FALSE:
            return 0.0
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 配对打分
# ---------------------------------------------------------------------------

def score_pair(plc_series: dict, screen_series: dict) -> tuple:
    """给「一个 PLC 槽位」与「一台屏端设备」打配对分。

    Args:
        plc_series:    {plc_suffix: [float, ...]}     该槽位各信号的观测序列
        screen_series: {screen_tag: [float, ...]}     该设备各信号的观测序列

    Returns:
        (score, detail)
        score  —— 加权一致度，0.0 ~ 1.0；无任何可比信号时为 0.0
        detail —— {signal_tag: {'agree': 一致样本数, 'total': 可比样本数,
                                'scale': 采用的定标, 'rate': 一致率}}

    说明：
        两侧采样时刻不同步，本函数不做逐点时间对齐，而是比对「值分布」——
        对每个 PLC 观测值，只要屏端序列中存在容差内的值即算一致。
        面板温度在数分钟内变化极小，该近似对本用途足够稳健，且免去时钟偏差问题。
    """
    total_weight = 0.0
    hit_weight = 0.0
    detail = {}

    for suffix, tag, tol, weight, discrete in CORRELATION_SIGNALS:
        plc_vals = [v for v in plc_series.get(suffix, []) if v is not None]
        scr_vals = [v for v in screen_series.get(tag, []) if v is not None]
        if not plc_vals or not scr_vals:
            continue

        best_rate = 0.0
        best_scale = 1.0
        best_agree = 0
        scales = (1.0,) if discrete else CANDIDATE_SCALES
        for scale in scales:
            agree = 0
            for pv in plc_vals:
                target = pv * scale
                if discrete:
                    ok = any(abs(target - sv) < 1e-9 for sv in scr_vals)
                else:
                    ok = any(abs(target - sv) <= tol for sv in scr_vals)
                if ok:
                    agree += 1
            rate = agree / len(plc_vals)
            if rate > best_rate:
                best_rate, best_scale, best_agree = rate, scale, agree

        total_weight += weight
        hit_weight += weight * best_rate
        detail[tag] = {
            'agree': best_agree,
            'total': len(plc_vals),
            'scale': best_scale,
            'rate': round(best_rate, 4),
        }

    score = (hit_weight / total_weight) if total_weight > 0 else 0.0
    return round(score, 4), detail


def best_assignment(score_matrix: dict, plc_keys: list, screen_keys: list) -> tuple:
    """在 PLC 槽位与屏端设备之间求最优一对一指派（穷举，n ≤ 4）。

    Args:
        score_matrix: {(plc_key, screen_key): score}
        plc_keys:     PLC 槽位 key 列表
        screen_keys:  屏端设备 key 列表

    Returns:
        (assignment, total_score, margin)
        assignment  —— [(plc_key, screen_key, score), ...]，按 plc_keys 顺序
        total_score —— 该指派的分数和
        margin      —— 与次优指派的分数差（越大越可信；无次优时为 total_score）

    穷举全部排列取最大和。n ≤ 4 时最多 24 种，代价可忽略。
    """
    if not plc_keys or not screen_keys:
        return [], 0.0, 0.0

    n = min(len(plc_keys), len(screen_keys))
    results = []
    # 允许屏端设备多于/少于 PLC 槽位：对较长一侧取组合，较短一侧全用
    for scr_combo in itertools.permutations(screen_keys, n):
        for plc_combo in itertools.combinations(plc_keys, n):
            total = sum(
                score_matrix.get((p, s), 0.0)
                for p, s in zip(plc_combo, scr_combo)
            )
            results.append((total, list(zip(plc_combo, scr_combo))))

    if not results:
        return [], 0.0, 0.0

    results.sort(key=lambda x: x[0], reverse=True)
    top_total, top_pairs = results[0]
    margin = top_total - results[1][0] if len(results) > 1 else top_total

    assignment = [
        (p, s, score_matrix.get((p, s), 0.0))
        for p, s in top_pairs
    ]
    return assignment, round(top_total, 4), round(margin, 4)


# ---------------------------------------------------------------------------
# JSONL 采集记录
# ---------------------------------------------------------------------------

def write_capture_record(fh, specific_part: str, device_sn: str,
                         product_code: str, attr_tag: str,
                         attr_value, received_at_iso: str) -> None:
    """向采集文件追加一条屏端观测记录（JSONL，一行一条）。"""
    fh.write(json.dumps({
        'specific_part': specific_part,
        'device_sn': str(device_sn),
        'product_code': str(product_code),
        'attr_tag': attr_tag,
        'attr_value': attr_value,
        'received_at': received_at_iso,
    }, ensure_ascii=False) + '\n')


def load_capture(path: str, specific_part: Optional[str] = None) -> dict:
    """读回采集文件，聚合为 {specific_part: {device_sn: {attr_tag: [float, ...]}}}。

    Args:
        path:          JSONL 路径
        specific_part: 非 None 时只保留该户

    非面板设备（product_code != 120003）与不关心的 attrTag 一并丢弃。
    """
    wanted_tags = set(screen_attr_tags())
    discrete_tags = {
        tag for _s, tag, _t, _w, d in CORRELATION_SIGNALS if d
    }
    out: dict = {}

    with open(path, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                logger.warning('load_capture: 第 %d 行 JSON 解析失败，跳过', line_no)
                continue

            if str(rec.get('product_code', '')) != PANEL_PRODUCT_CODE:
                continue
            tag = rec.get('attr_tag')
            if tag not in wanted_tags:
                continue
            sp = rec.get('specific_part')
            if specific_part is not None and sp != specific_part:
                continue

            val = to_float(rec.get('attr_value'), discrete=(tag in discrete_tags))
            if val is None:
                continue

            sn = str(rec.get('device_sn'))
            out.setdefault(sp, {}).setdefault(sn, {}).setdefault(tag, []).append(val)

    return out
