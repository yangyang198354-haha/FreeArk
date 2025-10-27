import os
import sys
import django
import random
from datetime import datetime, timedelta

# 设置Django环境
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

from api.models import PLCData

def insert_simulation_data():
    """
    在plc_data表中插入模拟数据：
    - 针对9-1-31-3104
    - 连续60天，每天10条记录
    - 制冷或制热模式
    - 每次值递增1-10的随机数
    """
    # 固定参数
    specific_part = "3104"
    plc_ip = "192.168.31.97"
    building = "9"
    unit = "1"
    room_number = "31"
    energy_modes = ["制冷", "制热"]
    
    # 先删除现有数据
    PLCData.objects.filter(
        specific_part=specific_part,
        building=building,
        unit=unit,
        room_number=room_number
    ).delete()
    print(f"已删除现有数据")
    
    # 起始日期（从60天前开始）
    start_date = datetime.now() - timedelta(days=60)
    
    # 当前值（用于递增）
    current_value = 0
    
    # 记录插入的数量
    inserted_count = 0
    
    print(f"开始插入模拟数据，目标：{building}-{unit}-{room_number}-{specific_part}，共{60}天，每天{10}条记录")
    
    try:
        for day in range(60):
            # 计算当前日期
            current_date = start_date + timedelta(days=day)
            print(f"正在处理日期: {current_date.strftime('%Y-%m-%d')}")
            
            for record in range(10):
                # 随机选择制冷或制热模式
                energy_mode = random.choice(energy_modes)
                
                # 随机递增1-10
                increment = random.randint(1, 10)
                current_value += increment
                
                # 随机时间（当天内）
                hour = random.randint(0, 23)
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                # 确保created_at是datetime对象
                created_at = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    hour,
                    minute,
                    second
                )
                
                # 创建记录
                plc_data = PLCData(
                    specific_part=specific_part,
                    plc_ip=plc_ip,
                    building=building,
                    unit=unit,
                    room_number=room_number,
                    energy_mode=energy_mode,
                    value=current_value,
                    created_at=created_at
                )
                plc_data.save()
                inserted_count += 1
                
                # 显示进度
                if inserted_count % 100 == 0:
                    print(f"已插入{inserted_count}条记录...")
        
        print(f"✅ 成功插入{inserted_count}条模拟数据！")
        
    except Exception as e:
        print(f"❌ 插入数据时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    insert_simulation_data()