#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
导出SQLite数据库中的所有表数据到JSON文件
"""

import os
import json
import django
import sqlite3
from pathlib import Path
import sys

# 添加Django项目路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)  # 添加backend目录到路径
sys.path.append(os.path.join(backend_dir, 'freearkweb'))  # 添加freearkweb目录到路径

# 设置Django环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

from django.apps import apps
from django.conf import settings

# 获取SQLite数据库路径
sqlite_db_path = settings.DATABASES['default']['NAME']
if isinstance(sqlite_db_path, Path):
    sqlite_db_path = str(sqlite_db_path)

# 导出目录
export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'export_data')
os.makedirs(export_dir, exist_ok=True)

print(f"开始从SQLite数据库 {sqlite_db_path} 导出数据...")

# 连接到SQLite数据库
conn = sqlite3.connect(sqlite_db_path)
cursor = conn.cursor()

# 获取所有表名
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
tables = [table[0] for table in cursor.fetchall()]

print(f"找到 {len(tables)} 个表:")
for table in tables:
    print(f"  - {table}")

# 导出每个表的数据
export_data = {}
for table_name in tables:
    print(f"正在导出表: {table_name}")
    
    # 获取表结构
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]
    
    # 获取表数据
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    
    # 将数据转换为字典列表
    table_data = []
    for row in rows:
        row_dict = {}
        for i, value in enumerate(row):
            # 处理特殊类型
            if value is None:
                row_dict[columns[i]] = None
            else:
                row_dict[columns[i]] = value
        table_data.append(row_dict)
    
    export_data[table_name] = {
        'columns': columns,
        'data': table_data
    }
    print(f"  导出了 {len(table_data)} 条记录")

# 保存导出的数据到JSON文件
export_file = os.path.join(export_dir, 'sqlite_export.json')
with open(export_file, 'w', encoding='utf-8') as f:
    json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)

print(f"\n导出完成!")
print(f"数据已保存到: {export_file}")
print(f"总共导出了 {len(tables)} 个表的数据")

# 关闭数据库连接
cursor.close()
conn.close()