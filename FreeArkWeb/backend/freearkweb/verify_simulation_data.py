import os
import sys
import django
from datetime import datetime, timedelta

# 设置Django环境
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

from api.models import PLCData

def verify_simulation_data():
    """
    验证模拟数据是否正确插入
    """
    # 查询条件
    specific_part = "3104"
    building = "9"
    unit = "1"
    room_number = "31"
    
    # 查询所有模拟数据
    records = PLCData.objects.filter(
        specific_part=specific_part,
        building=building,
        unit=unit,
        room_number=room_number
    )
    
    total_count = records.count()
    print(f"找到{total_count}条记录")
    
    if total_count > 0:
        # 检查数据范围
        min_date = records.earliest('created_at').created_at
        max_date = records.latest('created_at').created_at
        date_range_days = (max_date - min_date).days + 1
        print(f"数据时间范围: {min_date.strftime('%Y-%m-%d')} 至 {max_date.strftime('%Y-%m-%d')} (共{date_range_days}天)")
        
        # 检查模式分布
        cooling_count = records.filter(energy_mode="制冷").count()
        heating_count = records.filter(energy_mode="制热").count()
        print(f"制冷记录: {cooling_count}条, 制热记录: {heating_count}条")
        
        # 显示部分数据样本
        print("\n数据样本:")
        sample_records = records.order_by('-created_at')[:5]
        for record in sample_records:
            print(f"  日期: {record.created_at.strftime('%Y-%m-%d %H:%M:%S')}, 模式: {record.energy_mode}, 值: {record.value}")
        
        # 验证值的递增趋势
        sorted_records = records.order_by('created_at')
        increasing = True
        prev_value = None
        for record in sorted_records[:50]:  # 检查前50条记录
            if prev_value is not None and record.value <= prev_value:
                increasing = False
                break
            prev_value = record.value
        print(f"\n值是否呈递增趋势: {increasing}")
    
    print(f"\n验证完成！{'数据符合要求' if total_count == 600 else '数据数量不符'}")

if __name__ == "__main__":
    verify_simulation_data()