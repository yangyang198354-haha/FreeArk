import json
import os
from django.core.management.base import BaseCommand
from api.models import SpecificPartInfo

class Command(BaseCommand):
    """导入all_owner.json文件中的数据到specific_part_info表"""
    help = 'Import owner data from all_owner.json to specific_part_info table'
    
    def handle(self, *args, **options):
        """处理导入逻辑"""
        # 构建文件路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上遍历6级目录，到达FreeArk根目录
        base_dir = os.path.abspath(os.path.join(current_dir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir))
        json_file_path = os.path.join(base_dir, 'resource', 'all_owner.json')
        
        self.stdout.write(f"Reading data from: {json_file_path}")
        
        try:
            # 读取JSON文件
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 统计要导入的数据量
            total_records = len(data)
            self.stdout.write(f"Found {total_records} records in the JSON file")
            
            # 导入数据
            imported_count = 0
            skipped_count = 0
            
            for specific_part, owner_info in data.items():
                # 从owner_info中获取唯一标识符作为screenMAC
                screenMAC = owner_info.get('唯一标识符', '')
                
                if not screenMAC:
                    self.stdout.write(f"Skipping record {specific_part}: No 唯一标识符 found")
                    skipped_count += 1
                    continue
                
                # 检查是否已存在
                try:
                    existing_record = SpecificPartInfo.objects.get(screenMAC=screenMAC)
                    self.stdout.write(f"Skipping record {specific_part}: screenMAC {screenMAC} already exists")
                    skipped_count += 1
                except SpecificPartInfo.DoesNotExist:
                    # 创建新记录
                    SpecificPartInfo.objects.create(
                        screenMAC=screenMAC,
                        specific_part=specific_part
                    )
                    imported_count += 1
                    if imported_count % 100 == 0:
                        self.stdout.write(f"Imported {imported_count} records so far...")
            
            # 输出结果
            self.stdout.write(self.style.SUCCESS(f"Import completed successfully!"))
            self.stdout.write(f"Total records in JSON: {total_records}")
            self.stdout.write(f"Imported: {imported_count}")
            self.stdout.write(f"Skipped: {skipped_count}")
            
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {json_file_path}"))
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f"Invalid JSON file: {e}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error during import: {e}"))
