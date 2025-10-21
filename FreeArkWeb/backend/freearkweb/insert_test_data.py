#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
插入UsageQuantityDaily表的测试数据脚本
"""

import os
import sys
import random
from datetime import datetime, timedelta
import django

# 添加Django项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置Django环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

# 导入模型
from api.models import UsageQuantityDaily


def generate_random_data(count=10):
    """生成随机测试数据"""
    buildings = ['1', '2', '3', '4', '5']
    units = ['1', '2', '3']
    energy_modes = ['制冷', '制热']
    
    # 生成过去30天内的随机日期
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    data_list = []
    
    for i in range(count):
        building = random.choice(buildings)
        unit = random.choice(units)
        # 生成3位或4位的房间号（如702, 1203）
        floor = random.randint(1, 20)
        room_num = random.randint(1, 99)
        room_number = f"{floor:02d}{room_num:02d}" if room_num < 10 else f"{floor:02d}{room_num}"
        
        # 构建专有部分格式：楼栋-单元-房号
        specific_part = f"{building}-{unit}-{room_number}"
        
        energy_mode = random.choice(energy_modes)
        
        # 生成随机能耗值，初期能耗小于末期能耗
        initial_energy = random.randint(1000, 5000)
        final_energy = initial_energy + random.randint(10, 200)
        usage_quantity = final_energy - initial_energy
        
        # 生成随机日期
        delta_days = random.randint(0, 30)
        time_period = (start_date + timedelta(days=delta_days)).date()
        
        # 创建数据对象
        data = UsageQuantityDaily(
            specific_part=specific_part,
            building=building,
            unit=unit,
            room_number=room_number,
            energy_mode=energy_mode,
            initial_energy=initial_energy,
            final_energy=final_energy,
            usage_quantity=usage_quantity,
            time_period=time_period
        )
        data_list.append(data)
    
    return data_list


def insert_data(data_list):
    """批量插入数据"""
    try:
        UsageQuantityDaily.objects.bulk_create(data_list)
        print(f"成功插入 {len(data_list)} 条测试数据到 usage_quantity_daily 表")
        
        # 打印插入的数据以便查看
        print("\n插入的数据如下：")
        for data in UsageQuantityDaily.objects.order_by('-id')[:len(data_list)]:
            print(f"ID: {data.id}, 专有部分: {data.specific_part}, 时间段: {data.time_period}, ")
            print(f"  供能模式: {data.energy_mode}, 初期能耗: {data.initial_energy}kWh, ")
            print(f"  末期能耗: {data.final_energy}kWh, 使用量: {data.usage_quantity}kWh")
            print("---")
            
    except Exception as e:
        print(f"插入数据失败: {str(e)}")


if __name__ == "__main__":
    print("开始生成并插入测试数据...")
    test_data = generate_random_data(10)
    insert_data(test_data)
    print("数据插入操作完成。")