"""
Management command: seed_device_config
用途：初始化暖通系统的 DeviceConfig 元数据

用法：
  python manage.py seed_device_config           # 创建缺失条目，跳过已存在
  python manage.py seed_device_config --reset   # 先删除全部再重建

device_id 说明：
  device_id 必须与 MQTT 消息中实际发送的设备标识一致，
  才能与 PLCLatestData.specific_part 正确关联。
  请根据实际 MQTT 消息格式修改下方 HVAC_DEVICES 列表。
"""

from django.core.management.base import BaseCommand
from api.models import DeviceConfig

HVAC_DEVICES = [
    # ── 主温控器 ─────────────────────────────────────────────────────────
    {
        'device_id': 'hvac-main-ctrl',
        'display_name': '主温控',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    # ── 温控面板 ─────────────────────────────────────────────────────────
    {
        'device_id': 'hvac-panel-study',
        'display_name': '书房-温控面板',
        'group': 'hvac',
        'sub_type': 'room_panel',
        'group_display': '暖通',
        'sub_type_display': '温控面板',
    },
    {
        'device_id': 'hvac-panel-secondary-bed',
        'display_name': '次卧-温控面板',
        'group': 'hvac',
        'sub_type': 'room_panel',
        'group_display': '暖通',
        'sub_type_display': '温控面板',
    },
    {
        'device_id': 'hvac-panel-master-bed',
        'display_name': '主卧-温控面板',
        'group': 'hvac',
        'sub_type': 'room_panel',
        'group_display': '暖通',
        'sub_type_display': '温控面板',
    },
    {
        'device_id': 'hvac-panel-children',
        'display_name': '儿童房-温控面板',
        'group': 'hvac',
        'sub_type': 'room_panel',
        'group_display': '暖通',
        'sub_type_display': '温控面板',
    },
    # ── 新风 ─────────────────────────────────────────────────────────────
    {
        'device_id': 'hvac-fresh-air',
        'display_name': '新风',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    # ── 能耗表 ───────────────────────────────────────────────────────────
    {
        'device_id': 'hvac-energy-meter',
        'display_name': '能耗表',
        'group': 'hvac',
        'sub_type': 'energy_meter',
        'group_display': '暖通',
        'sub_type_display': '能耗表',
    },
    # ── 水力模块 ─────────────────────────────────────────────────────────
    {
        'device_id': 'hvac-hydraulic',
        'display_name': '水力模块',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
]


class Command(BaseCommand):
    help = '初始化暖通设备 DeviceConfig 元数据'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='先删除全部 DeviceConfig 记录再重建（谨慎使用）',
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted, _ = DeviceConfig.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'已删除 {deleted} 条 DeviceConfig 记录'))

        created_count = 0
        skipped_count = 0

        for device in HVAC_DEVICES:
            obj, created = DeviceConfig.objects.get_or_create(
                device_id=device['device_id'],
                defaults={
                    'display_name': device['display_name'],
                    'group': device['group'],
                    'sub_type': device['sub_type'],
                    'group_display': device['group_display'],
                    'sub_type_display': device['sub_type_display'],
                    'is_active': True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f'  [created] {device["device_id"]} -> {device["display_name"].encode("utf-8")}')
            else:
                skipped_count += 1
                self.stdout.write(f'  [skipped] {device["device_id"]} already exists')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: created {created_count}, skipped {skipped_count}'
        ))
        self.stdout.write(self.style.WARNING(
            '\nWARNING: Verify device_id values match actual MQTT message identifiers, '
            'otherwise device cards will show empty params.'
        ))
