import json
import os
from django.core.management.base import BaseCommand
from api.models import OwnerInfo


class Command(BaseCommand):
    """
    将 resource/all_owner.json 中的业主信息导入 owner_info 数据库表。
    支持幂等执行：已存在的记录执行 update，不存在则 create。

    用法：
        python manage.py import_all_owners
    """
    help = 'Import owner data from resource/all_owner.json into the owner_info database table (idempotent)'

    def handle(self, *args, **options):
        # 定位 all_owner.json
        # 当前文件路径：.../api/management/commands/import_all_owners.py
        # 向上 6 级到达 FreeArk 根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.abspath(
            os.path.join(current_dir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir)
        )
        json_file_path = os.path.join(base_dir, 'resource', 'all_owner.json')

        self.stdout.write(f"读取文件：{json_file_path}")

        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"文件不存在：{json_file_path}"))
            raise SystemExit(1)
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f"JSON 解析失败：{e}"))
            raise SystemExit(1)

        total = len(data)
        self.stdout.write(f"共发现 {total} 条业主记录，开始导入...")

        created_count = 0
        updated_count = 0
        error_count = 0

        for specific_part, val in data.items():
            try:
                _, created = OwnerInfo.objects.update_or_create(
                    specific_part=specific_part,
                    defaults={
                        'location_name': val.get('专有部分坐落', ''),
                        'building': val.get('楼栋', ''),
                        'unit': val.get('单元', ''),
                        'floor': val.get('楼层', ''),
                        'room_number': str(val.get('户号', '')),
                        'bind_status': val.get('绑定状态', ''),
                        'ip_address': val.get('IP地址', ''),
                        'unique_id': val.get('唯一标识符', ''),
                        'plc_ip_address': val.get('PLC IP地址', ''),
                    }
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

                if (created_count + updated_count) % 100 == 0:
                    self.stdout.write(f"  已处理 {created_count + updated_count} 条...")

            except Exception as e:
                error_count += 1
                self.stderr.write(self.style.WARNING(f"  处理 {specific_part} 时出错：{e}"))

        self.stdout.write(self.style.SUCCESS(
            f"\n导入完成！\n"
            f"  JSON 总记录数：{total}\n"
            f"  新建：{created_count}\n"
            f"  更新：{updated_count}\n"
            f"  错误：{error_count}"
        ))

        if error_count > 0:
            self.stderr.write(self.style.WARNING(f"有 {error_count} 条记录处理失败，请检查上方警告信息。"))
            raise SystemExit(1)
