"""
panel_calib_correlate — 温控面板标定 · 阶段 2：配对推断

用途：
  把阶段 1 采到的屏端遥测（按 device_sn）与 PLC 侧遥测（按 param_name 前缀）
  按数值一致度做一对一指派，推出每户真实的
      PLC 槽位 ↔ device_sn ↔ 房间
  配对关系，并与「Web 现行标签」「plc_config 标注」逐一对照，标出不一致的住户。

原理：
  两侧读的是同一块面板上的同一个传感器，温度/湿度/设定温度/开关的数值应当近似相等。
  对每个 (PLC 槽位, 屏端设备) 组合算加权一致度，再穷举全部一对一指派取最优
  （n ≤ 4，最多 24 种）。margin（最优与次优之差）作为可信度指标。

只读保证：
  只 SELECT DeviceParamHistory / PLCLatestData / DeviceNode / DeviceConfig，不写任何表。

用法：
  python manage.py panel_calib_correlate --capture /tmp/panel_calib.jsonl
  python manage.py panel_calib_correlate --capture /tmp/panel_calib.jsonl \
      --specific-part 3-1-7-702 --verbose
  python manage.py panel_calib_correlate --capture /tmp/panel_calib.jsonl \
      --json-out /tmp/panel_binding.json

参见：api/panel_calibration.py
"""

import json
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand

from api.panel_calibration import (
    PANEL_SLOTS,
    PANEL_PREFIXES,
    PANEL_PRODUCT_CODE,
    CORRELATION_SIGNALS,
    plc_param,
    to_float,
    score_pair,
    best_assignment,
    load_capture,
)

logger = logging.getLogger(__name__)

# 屏端采集窗口向两侧各外扩这么久，用于框定 PLC 侧的历史区间
_WINDOW_PAD = timedelta(minutes=10)

# margin 低于此值视为「配对不可信」，需要更长采集时间
_MARGIN_WARN = 0.15


class Command(BaseCommand):
    help = '温控面板标定阶段 2：用屏端采集 + PLC 历史推断槽位↔设备↔房间配对'

    def add_arguments(self, parser):
        parser.add_argument('--capture', required=True,
                            help='阶段 1 产出的 JSONL 路径')
        parser.add_argument('--specific-part', default=None,
                            help='只分析该户')
        parser.add_argument('--verbose', action='store_true',
                            help='打印每个信号的逐项一致度明细')
        parser.add_argument('--json-out', default=None,
                            help='把配对结果写成 JSON（供后续生成绑定表）')

    def handle(self, *args, **options):
        capture_path = options['capture']
        only_sp = options.get('specific_part')
        verbose = options.get('verbose', False)
        json_out = options.get('json_out')

        screen = load_capture(capture_path, specific_part=only_sp)
        if not screen:
            self.stderr.write(
                f'采集文件无有效面板记录：{capture_path}\n'
                f'（检查 product_code 是否为 {PANEL_PRODUCT_CODE}、采集时长是否足够）'
            )
            return

        self.stdout.write(f'采集文件：{capture_path}')
        self.stdout.write(f'覆盖住户：{len(screen)} 户')

        window = self._capture_window(capture_path)
        if window:
            self.stdout.write(
                f'采集窗口：{window[0]:%Y-%m-%d %H:%M:%S} ~ {window[1]:%Y-%m-%d %H:%M:%S}'
            )

        results = {}
        for sp in sorted(screen.keys()):
            result = self._analyse(sp, screen[sp], window, verbose)
            if result:
                results[sp] = result

        self._summary(results)

        if json_out:
            with open(json_out, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            self.stdout.write('')
            self.stdout.write(f'配对结果已写入：{json_out}')

    # -----------------------------------------------------------------
    # PLC 侧取数
    # -----------------------------------------------------------------

    def _capture_window(self, path: str):
        """扫一遍采集文件，取 received_at 的最早/最晚，用于框定 PLC 历史区间。"""
        from django.utils.dateparse import parse_datetime
        lo = hi = None
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ts = parse_datetime(json.loads(line).get('received_at', ''))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if ts is None:
                    continue
                lo = ts if lo is None or ts < lo else lo
                hi = ts if hi is None or ts > hi else hi
        return (lo, hi) if lo and hi else None

    def _plc_series(self, specific_part: str, window) -> dict:
        """取该户 PLC 侧各槽位的观测序列 {prefix: {suffix: [float, ...]}}。

        优先用 DeviceParamHistory（时序，默认保留 7 天）并限制在采集窗口内；
        窗口内无历史数据时降级到 PLCLatestData（单点快照，只能给出弱证据）。
        """
        from api.models import DeviceParamHistory, PLCLatestData

        suffixes = [sfx for sfx, *_ in CORRELATION_SIGNALS]
        discrete = {sfx for sfx, _t, _tol, _w, d in CORRELATION_SIGNALS if d}
        wanted = [plc_param(p, s) for p in PANEL_PREFIXES for s in suffixes]

        series: dict = {p: {} for p in PANEL_PREFIXES}

        qs = DeviceParamHistory.objects.filter(
            specific_part=specific_part, param_name__in=wanted,
        )
        if window:
            qs = qs.filter(
                collected_at__gte=window[0] - _WINDOW_PAD,
                collected_at__lte=window[1] + _WINDOW_PAD,
            )

        count = 0
        for rec in qs.iterator(chunk_size=2000):
            for prefix in PANEL_PREFIXES:
                if not rec.param_name.startswith(prefix + '_'):
                    continue
                sfx = rec.param_name[len(prefix):]
                if sfx not in suffixes:
                    continue
                val = to_float(rec.value, discrete=(sfx in discrete))
                if val is not None:
                    series[prefix].setdefault(sfx, []).append(val)
                    count += 1
                break

        if count == 0:
            # 降级：用最新快照（单点，margin 会很低，仅作提示）
            for rec in PLCLatestData.objects.filter(
                specific_part=specific_part, param_name__in=wanted,
            ):
                for prefix in PANEL_PREFIXES:
                    if not rec.param_name.startswith(prefix + '_'):
                        continue
                    sfx = rec.param_name[len(prefix):]
                    if sfx in suffixes:
                        val = to_float(rec.value, discrete=(sfx in discrete))
                        if val is not None:
                            series[prefix].setdefault(sfx, []).append(val)
                            count += 1
                    break
            if count:
                logger.warning(
                    '%s: DeviceParamHistory 窗口内无数据，降级用 PLCLatestData 单点快照',
                    specific_part,
                )

        return series

    # -----------------------------------------------------------------
    # 单户分析
    # -----------------------------------------------------------------

    def _analyse(self, specific_part: str, screen_devices: dict, window, verbose: bool):
        from api.models import DeviceNode, DeviceConfig

        plc = self._plc_series(specific_part, window)
        active_prefixes = [p for p in PANEL_PREFIXES if plc.get(p)]
        screen_sns = sorted(screen_devices.keys())

        self.stdout.write('')
        self.stdout.write('=' * 78)
        self.stdout.write(f'{specific_part}')
        self.stdout.write('=' * 78)

        if not active_prefixes:
            self.stdout.write('  PLC 侧无可用观测（历史已清理或该户未采集），跳过。')
            return None
        if not screen_sns:
            self.stdout.write('  屏端无可用观测，跳过。')
            return None

        # device_sn → 房间名
        sn_to_room = {
            str(sn): room
            for sn, room in DeviceNode.objects
            .filter(
                room__floor__owner__specific_part=specific_part,
                product_code=PANEL_PRODUCT_CODE,
            )
            .values_list('device_sn', 'room__ori_room_name')
        }
        # sub_type → Web 现行标签
        display_map = {
            c.sub_type: c.sub_type_display
            for c in DeviceConfig.objects.filter(is_active=True)
        }

        # 打分矩阵
        matrix = {}
        details = {}
        for prefix in active_prefixes:
            for sn in screen_sns:
                score, detail = score_pair(plc[prefix], screen_devices[sn])
                matrix[(prefix, sn)] = score
                details[(prefix, sn)] = detail

        if verbose:
            self.stdout.write('')
            self.stdout.write('  【打分矩阵】行=PLC槽位  列=屏端device_sn')
            header = '    {:<22}'.format('') + ''.join(
                f'{sn + "/" + sn_to_room.get(sn, "?"):>18}' for sn in screen_sns
            )
            self.stdout.write(header)
            for prefix in active_prefixes:
                row = f'    {prefix:<22}' + ''.join(
                    f'{matrix[(prefix, sn)]:>18.4f}' for sn in screen_sns
                )
                self.stdout.write(row)

        assignment, total, margin = best_assignment(
            matrix, active_prefixes, screen_sns,
        )

        slot_meta = {s[0]: s for s in PANEL_SLOTS}
        pairs = []
        mismatches = 0

        self.stdout.write('')
        self.stdout.write(
            '  {:<22}{:<8}{:<10}{:<12}{:<8}{:<14}{}'.format(
                'PLC槽位', 'offset', 'device_sn', '推断房间',
                '一致度', 'Web现行标签', 'plc_config四房',
            )
        )
        self.stdout.write('  ' + '-' * 92)

        for prefix, sn, score in assignment:
            _p, sub_type, offset, three_name, four_name = slot_meta[prefix]
            room = sn_to_room.get(sn, '(设备树无此SN)')
            web_label = display_map.get(sub_type, '?')
            web_room = web_label.replace('-温控面板', '')
            ok = (room == web_room)
            if not ok:
                mismatches += 1
            flag = '' if ok else '   ← 不一致'
            self.stdout.write(
                '  {:<22}{:<8}{:<10}{:<12}{:<8.4f}{:<14}{}{}'.format(
                    prefix, offset, sn, room, score, web_label,
                    four_name or '—', flag,
                )
            )
            pairs.append({
                'param_prefix': prefix,
                'sub_type': sub_type,
                'plc_offset': offset,
                'device_sn': sn,
                'inferred_room': room,
                'score': score,
                'web_current_label': web_label,
                'plc_config_three_room': three_name,
                'plc_config_four_room': four_name,
                'matches_web': ok,
                'signals': details.get((prefix, sn), {}) if verbose else {},
            })

        confidence = self._confidence(assignment, margin)
        self.stdout.write('')
        self.stdout.write(
            f'  合计分={total}  margin={margin}  可信度={confidence}'
        )
        if margin < _MARGIN_WARN:
            self.stdout.write(
                '  ⚠ margin 偏低：最优与次优指派差距小，建议延长采集时间后重跑。'
            )
        if mismatches:
            self.stdout.write(
                f'  ⚠ 有 {mismatches} 个槽位的推断房间与 Web 现行标签不符 —— '
                f'该户即为错位户。'
            )
        else:
            self.stdout.write('  ✓ 推断结果与 Web 现行标签完全一致，该户显示正确。')

        return {
            'specific_part': specific_part,
            'total_score': total,
            'margin': margin,
            'confidence': confidence,
            'mismatch_count': mismatches,
            'pairs': pairs,
        }

    @staticmethod
    def _confidence(assignment, margin: float) -> str:
        if not assignment:
            return 'none'
        min_score = min(s for _p, _sn, s in assignment)
        if margin >= 0.4 and min_score >= 0.7:
            return 'high'
        if margin >= _MARGIN_WARN and min_score >= 0.4:
            return 'medium'
        return 'low'

    # -----------------------------------------------------------------

    def _summary(self, results: dict):
        self.stdout.write('')
        self.stdout.write('=' * 78)
        self.stdout.write('汇总')
        self.stdout.write('=' * 78)
        if not results:
            self.stdout.write('无有效结果。')
            return

        bad = [r for r in results.values() if r['mismatch_count'] > 0]
        low = [r for r in results.values() if r['confidence'] == 'low']

        self.stdout.write(f'  分析住户：{len(results)}')
        self.stdout.write(f'  存在错位：{len(bad)}')
        self.stdout.write(f'  可信度低（需延长采集）：{len(low)}')
        if bad:
            self.stdout.write('')
            self.stdout.write('  错位住户清单：')
            for r in sorted(bad, key=lambda x: x['specific_part']):
                rooms = ', '.join(
                    f"{p['plc_offset']}→{p['inferred_room']}(现显示{p['web_current_label'].replace('-温控面板','')})"
                    for p in r['pairs'] if not p['matches_web']
                )
                self.stdout.write(
                    f"    {r['specific_part']:<14} [{r['confidence']}] {rooms}"
                )
