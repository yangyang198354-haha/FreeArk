#!/usr/bin/env python
import os
import sys
import django

# 设置Django环境
sys.path.append(r'c:\Users\yanggyan\TRAE\FreeArk\FreeArkWeb\backend\freearkweb')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

from api.models import PLCStatusChangeHistory
from django.db import connection

print("=" * 60)
print("PLCStatusChangeHistory 模型验证")
print("=" * 60)

# 检查模型
print(f"\n✓ 模型导入成功: {PLCStatusChangeHistory._meta.db_table}")
print(f"✓ 模型名称: {PLCStatusChangeHistory._meta.verbose_name}")
print(f"✓ 模型复数名称: {PLCStatusChangeHistory._meta.verbose_name_plural}")

# 检查字段
fields = PLCStatusChangeHistory._meta.get_fields()
print(f"\n✓ 字段数量: {len(fields)}")
print("字段列表:")
for field in fields:
    print(f"  - {field.name} ({field.__class__.__name__})")

# 检查数据库表
cursor = connection.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='plc_status_change_history'")
result = cursor.fetchone()
print(f"\n✓ 数据库表存在: {result[0] if result else False}")

# 检查表结构
cursor.execute('PRAGMA table_info(plc_status_change_history)')
columns = cursor.fetchall()
print(f"\n✓ 数据库表字段数量: {len(columns)}")
print("数据库表结构:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

# 检查索引
cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='plc_status_change_history'")
indexes = cursor.fetchall()
print(f"\n✓ 索引数量: {len(indexes)}")
print("索引列表:")
for idx in indexes:
    print(f"  - {idx[0]}")

# 检查记录数量
cursor.execute("SELECT COUNT(*) FROM plc_status_change_history")
count = cursor.fetchone()[0]
print(f"\n✓ 当前记录数量: {count}")

# 测试创建记录
print("\n" + "=" * 60)
print("测试创建状态变化记录")
print("=" * 60)

try:
    test_record = PLCStatusChangeHistory.objects.create(
        specific_part='9-1-3104',
        status='online',
        building='9',
        unit='1',
        room_number='3104'
    )
    print(f"✓ 测试记录创建成功: ID={test_record.id}")
    
    # 查询记录
    records = PLCStatusChangeHistory.objects.filter(specific_part='9-1-3104')
    print(f"✓ 查询记录成功: 找到 {records.count()} 条记录")
    
    # 删除测试记录
    test_record.delete()
    print("✓ 测试记录删除成功")
    
except Exception as e:
    print(f"✗ 操作失败: {e}")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)