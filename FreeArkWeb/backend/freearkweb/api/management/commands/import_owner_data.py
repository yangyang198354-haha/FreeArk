"""
此命令已废弃，请使用 import_all_owners 代替。

specific_part_info 表已于 migration 0014 中删除（DROP TABLE specific_part_info）。
业主数据请通过 import_all_owners 命令导入到 owner_info 表。
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '[已废弃] 请使用 import_all_owners 命令代替'

    def handle(self, *args, **options):
        self.stderr.write(
            self.style.ERROR(
                'import_owner_data 命令已废弃。'
                'specific_part_info 表已删除，业主数据请使用 import_all_owners 命令导入到 owner_info 表。'
            )
        )
