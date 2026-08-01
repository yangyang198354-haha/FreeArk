"""
panel_calib_snapshot — 温控面板标定 · 阶段 0：只读快照

用途：
  一眼看清某户「PLC 侧四个槽位当前各是什么值」与「屏厂云端设备树里有哪些房间/设备」，
  以及现行静态标签表会把每个槽位显示成什么。用于人工比对现场实况。

只读保证：
  只 SELECT PLCLatestData / DeviceFloor / DeviceRoom / DeviceNode / DeviceConfig，
  不写任何表，不连 MQTT。

用法：
  python manage.py panel_calib_snapshot --specific-part 3-1-7-702
  python manage.py panel_calib_snapshot --specific-part 3-1-7-702 --all-params
  python manage.py panel_calib_snapshot --all-owners      # 全量扫描，只打印开关状态

参见：api/panel_calibration.py、docs/analysis/plc_room_mapping_misalignment_rca.md
"""

from django.core.management.base import BaseCommand

from api.panel_calibration import (
    PANEL_SLOTS,
    PANEL_PRODUCT_CODE,
    CORRELATION_SIGNALS,
    plc_param,
    to_float,
)


class Command(BaseCommand):
    help = '温控面板标定阶段 0：只读打印某户 PLC 槽位现值 + 云端房间树 + 现行标签'

    def add_arguments(self, parser):
        parser.add_argument(
            '--specific-part',
            help='专有部分，如 3-1-7-702（与 --all-owners 二选一）',
        )
        parser.add_argument(
            '--all-owners',
            action='store_true',
            help='扫描全部业主，仅打印四个开关的值与云端面板房间数',
        )
        parser.add_argument(
            '--all-params',
            action='store_true',
            help='打印全部信号（默认只打印 switch/temperature/humidity）',
        )

    def handle(self, *args, **options):
        from api.models import OwnerInfo

        sp = options.get('specific_part')
        if options.get('all_owners'):
            for owner in OwnerInfo.objects.order_by('specific_part'):
                self._brief(owner.specific_part)
            return

        if not sp:
            self.stderr.write('必须提供 --specific-part 或 --all-owners')
            return

        self._detail(sp, all_params=options.get('all_params', False))

    # -----------------------------------------------------------------
    # 全量简报
    # -----------------------------------------------------------------

    def _brief(self, specific_part: str):
        from api.models import PLCLatestData, DeviceNode

        switches = {
            r.param_name: r.value
            for r in PLCLatestData.objects.filter(
                specific_part=specific_part,
                param_name__in=[plc_param(p, '_switch') for p, *_ in PANEL_SLOTS],
            )
        }
        panel_rooms = list(
            DeviceNode.objects
            .filter(
                room__floor__owner__specific_part=specific_part,
                product_code=PANEL_PRODUCT_CODE,
            )
            .select_related('room')
            .order_by('device_sn')
            .values_list('room__ori_room_name', 'device_sn')
        )

        on_slots = [
            prefix for prefix, *_ in PANEL_SLOTS
            if switches.get(plc_param(prefix, '_switch')) not in (None, 0)
        ]
        self.stdout.write(
            f'{specific_part:<14} 云端面板={len(panel_rooms)} '
            f'{[r for r, _ in panel_rooms]}  PLC开启槽位={on_slots or "无"}'
        )

    # -----------------------------------------------------------------
    # 单户详情
    # -----------------------------------------------------------------

    def _detail(self, specific_part: str, all_params: bool):
        from api.models import PLCLatestData, DeviceFloor, DeviceConfig

        self.stdout.write('')
        self.stdout.write('=' * 78)
        self.stdout.write(f'专有部分：{specific_part}')
        self.stdout.write('=' * 78)

        # ── 1. 屏厂云端设备树（权威房间来源）────────────────────────────
        self.stdout.write('')
        self.stdout.write('【屏厂云端设备树】DeviceFloor → DeviceRoom → DeviceNode')
        floors = (
            DeviceFloor.objects
            .filter(owner__specific_part=specific_part)
            .prefetch_related('rooms__devices')
        )
        found_any = False
        for floor in floors:
            for room in floor.rooms.all():
                for dev in room.devices.all():
                    found_any = True
                    mark = ' ← 温控面板' if str(dev.product_code) == PANEL_PRODUCT_CODE else ''
                    self.stdout.write(
                        f'  {room.ori_room_name:<8} sn={dev.device_sn:<8} '
                        f'{dev.device_name:<10} product={dev.product_code}{mark}'
                    )
        if not found_any:
            self.stdout.write('  （设备树未同步，无记录）')

        # ── 2. PLC 侧各槽位现值 ─────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write('【PLC 侧槽位现值】PLCLatestData')

        signals = CORRELATION_SIGNALS if all_params else (
            ('_switch', 'switch', 0.0, 0.0, True),
            ('_temperature', 'temp', 0.0, 0.0, False),
            ('_humidity', 'humidity', 0.0, 0.0, False),
        )

        display_map = {
            c.sub_type: c.sub_type_display
            for c in DeviceConfig.objects.filter(is_active=True)
        }

        wanted = [
            plc_param(prefix, sfx)
            for prefix, *_ in PANEL_SLOTS
            for sfx, *_ in signals
        ]
        rows = {
            r.param_name: r
            for r in PLCLatestData.objects.filter(
                specific_part=specific_part, param_name__in=wanted,
            )
        }

        for prefix, sub_type, offset, three_name, four_name in PANEL_SLOTS:
            label = display_map.get(sub_type, '(无配置)')
            self.stdout.write('')
            self.stdout.write(
                f'  槽位 offset={offset}  prefix={prefix}'
            )
            self.stdout.write(
                f'    Web 现行标签  : {label}'
            )
            self.stdout.write(
                f'    plc_config 标注: 三房={three_name or "—"} / 四房={four_name or "—"}'
            )
            for sfx, tag, *_rest in signals:
                pname = plc_param(prefix, sfx)
                rec = rows.get(pname)
                if rec is None:
                    self.stdout.write(f'    {tag:<14}: （无数据）')
                    continue
                collected = (
                    rec.collected_at.strftime('%Y-%m-%d %H:%M:%S')
                    if rec.collected_at else '—'
                )
                self.stdout.write(
                    f'    {tag:<14}: {rec.value!s:<10} @ {collected}'
                )

        # ── 3. 结论提示 ────────────────────────────────────────────────
        on = [
            (prefix, offset, display_map.get(sub_type, '?'))
            for prefix, sub_type, offset, _t, _f in PANEL_SLOTS
            if to_float(
                getattr(rows.get(plc_param(prefix, '_switch')), 'value', None)
            ) not in (None, 0.0)
        ]
        self.stdout.write('')
        self.stdout.write('【开关处于开启态的槽位】')
        if on:
            for prefix, offset, label in on:
                self.stdout.write(
                    f'  offset={offset} ({prefix}) → Web 会显示为「{label}」'
                )
            self.stdout.write('')
            self.stdout.write(
                '  请到现场/小程序参数设置页核对：实际开启的是哪个房间的面板。'
            )
            self.stdout.write(
                '  若与上面的 Web 标签不符，即为该户 PLC 接线偏离 plc_config 标注的直接证据。'
            )
        else:
            self.stdout.write('  当前无槽位处于开启态（无法据此比对，请改用 capture+correlate）')
        self.stdout.write('')
