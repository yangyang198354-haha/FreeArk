#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将导出的SQLite数据导入到MySQL数据库
"""

import os
import json
import django
import sys
from datetime import datetime

# 添加Django项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)  # 添加backend目录到路径
sys.path.append(os.path.join(backend_dir, 'freearkweb'))  # 添加freearkweb目录到路径

# 设置Django环境变量以使用MySQL配置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
os.environ['DB_ENGINE'] = 'django.db.backends.mysql'
os.environ['DB_NAME'] = 'freeark'
os.environ['DB_USER'] = 'root'
os.environ['DB_PASSWORD'] = 'root'
os.environ['DB_HOST'] = '192.168.31.97'
os.environ['DB_PORT'] = '3306'

# 初始化Django
django.setup()

from django.apps import apps
from django.conf import settings
from django.db import connection, transaction
from django.db.utils import OperationalError, ProgrammingError

print(f"当前数据库配置: {settings.DATABASES['default']}")

# 导入文件路径
export_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'export_data', 'sqlite_export.json')

if not os.path.exists(export_file):
    print(f"错误: 找不到导出文件 {export_file}")
    print("请先运行 export_sqlite_data.py 脚本导出SQLite数据")
    sys.exit(1)

print(f"开始从 {export_file} 导入数据到MySQL数据库...")

# 读取导出的数据
with open(export_file, 'r', encoding='utf-8') as f:
    export_data = json.load(f)

# 获取所有Django模型
all_models = apps.get_models()
model_dict = {model._meta.db_table: model for model in all_models}

# 清理函数: 将字符串转换为正确的数据类型
def convert_value(value, field_type):
    if value is None:
        return None
    
    # 处理日期时间类型
    if field_type in ['DateTimeField', 'DateField', 'TimeField'] and isinstance(value, str):
        try:
            # 尝试不同的日期时间格式
            formats = [
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d'
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
    
    # 处理布尔类型
    if field_type == 'BooleanField' and isinstance(value, str):
        if value.lower() in ('true', '1', 'yes', 'y'):
            return True
        elif value.lower() in ('false', '0', 'no', 'n'):
            return False
    
    # 处理数字类型
    if field_type in ['IntegerField', 'BigIntegerField', 'SmallIntegerField'] and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    
    if field_type in ['FloatField', 'DecimalField'] and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
    
    return value

# 首先执行数据库迁移
print("\n正在执行数据库迁移...")
try:
    # 尝试连接数据库
    connection.ensure_connection()
    print("成功连接到MySQL数据库")
    
    # 执行迁移命令
    from django.core.management import call_command
    
    # 确保所有应用都已注册
    call_command('makemigrations', interactive=False)
    call_command('migrate', interactive=False)
    print("数据库迁移完成")
    
except OperationalError as e:
    print(f"错误: 无法连接到MySQL数据库")
    print(f"错误信息: {str(e)}")
    print("请检查MySQL服务是否运行，以及连接配置是否正确")
    sys.exit(1)

# 导入数据
print("\n开始导入数据...")

total_imported = 0
tables_imported = 0
tables_skipped = 0

for table_name, table_data in export_data.items():
    print(f"\n处理表: {table_name}")
    
    # 检查是否有对应的Django模型
    if table_name in model_dict:
        model = model_dict[table_name]
        print(f"找到对应的Django模型: {model.__name__}")
        
        # 获取模型字段信息
        model_fields = {field.name: field.get_internal_type() for field in model._meta.fields}
        
        # 导入数据
        rows = table_data['data']
        if rows:
            print(f"准备导入 {len(rows)} 条记录")
            
            try:
                with transaction.atomic():
                    # 清空表数据（可选）
                    model.objects.all().delete()
                    print(f"已清空表 {table_name} 现有数据")
                    
                    # 批量创建记录
                    for i, row in enumerate(rows):
                        # 准备模型实例数据
                        model_data = {}
                        for field_name, value in row.items():
                            # 检查字段是否存在于模型中
                            if field_name in model_fields:
                                # 转换值为正确的数据类型
                                converted_value = convert_value(value, model_fields[field_name])
                                model_data[field_name] = converted_value
                        
                        # 创建模型实例
                        try:
                            model.objects.create(**model_data)
                        except Exception as e:
                            print(f"导入第 {i+1} 条记录时出错: {str(e)}")
                            print(f"数据: {model_data}")
                    
                    print(f"成功导入 {len(rows)} 条记录到表 {table_name}")
                    tables_imported += 1
                    total_imported += len(rows)
                    
            except Exception as e:
                print(f"导入表 {table_name} 时发生错误: {str(e)}")
                tables_skipped += 1
        else:
            print(f"表 {table_name} 没有数据，跳过")
            tables_skipped += 1
    else:
        print(f"警告: 没有找到表 {table_name} 对应的Django模型，跳过导入")
        tables_skipped += 1

print(f"\n数据导入完成!")
print(f"成功导入: {tables_imported} 个表，共 {total_imported} 条记录")
print(f"跳过: {tables_skipped} 个表")
print("\n注意: 如果有一些表被跳过，可能是因为这些表没有对应的Django模型。")
print("您可能需要手动处理这些表的数据迁移。")

# 执行必要的数据库维护命令
print("\n执行数据库优化...")
try:
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE TABLE " + ", ".join(model_dict.keys()))
    print("数据库优化完成")
except Exception as e:
    print(f"数据库优化时发生错误: {str(e)}")

print("\nMySQL数据库迁移和数据导入流程已完成!")