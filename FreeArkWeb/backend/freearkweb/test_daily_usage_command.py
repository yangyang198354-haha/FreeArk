import os
import sys
import platform
from datetime import datetime, date, timedelta
import subprocess

# 修复Windows编码问题
if platform.system() == 'Windows':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 设置控制台编码
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except:
        pass

def run_django_command(command):
    """
    运行Django管理命令
    """
    cmd = f"python manage.py {command}"
    print(f"执行命令: {cmd}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        return result
    except Exception as e:
        print(f"执行命令时出错: {e}")
        return None

def create_test_data(test_date):
    """
    创建测试数据用于验证
    """
    date_str = test_date.strftime('%Y-%m-%d')
    print(f"\n创建测试数据 (日期: {date_str})...")
    
    # 创建测试数据的脚本，使用django.utils.timezone确保时区正确
    test_data_script = '''
import sys
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, date, time, timedelta
from django.utils import timezone
from api.models import PLCData

# 清理现有测试记录
print("开始清理现有测试数据...")
PLCData.objects.filter(
    created_at__date=date.fromisoformat('%s'),
    specific_part__in=['9-1-31-3104', '9-1-31-3105']
).delete()
print("已清理现有测试数据")

# 测试日期
TEST_DATE = date.fromisoformat('%s')

# 创建带时区的datetime
start_datetime = timezone.make_aware(datetime.combine(TEST_DATE, time.min))
end_datetime = timezone.make_aware(datetime.combine(TEST_DATE, time.max))
mid_datetime = start_datetime + timedelta(hours=12)

print(f"测试日期范围: {start_datetime} 到 {end_datetime}")

# 测试数据
test_data = [
    {"specific_part": "9-1-31-3104", "building": "9", "unit": "1", "room_number": "3104"},
    {"specific_part": "9-1-31-3105", "building": "9", "unit": "1", "room_number": "3105"}
]

energy_modes = ['heating', 'cooling']
created_count = 0

for data in test_data:
    for mode in energy_modes:
        # 初始值
        initial_value = 10000 + created_count * 1000
        
        # 确认时区处理
        print(f"创建记录: {{data['specific_part']}}, {{mode}}, 开始时间: {{start_datetime}}")
        
        # 创建最早记录
        early_record = PLCData.objects.create(
            specific_part=data["specific_part"],
            building=data["building"],
            unit=data["unit"],
            room_number=data["room_number"],
            energy_mode=mode,
            value=initial_value,
            created_at=start_datetime
        )
        print(f"创建最早记录: {{data['specific_part']}} - {{mode}}: {{initial_value}} - {{early_record.created_at}}")
        print(f"  记录日期部分: {{early_record.created_at.date()}}")
        
        # 创建中间记录
        mid_value = initial_value + 50
        mid_record = PLCData.objects.create(
            specific_part=data["specific_part"],
            building=data["building"],
            unit=data["unit"],
            room_number=data["room_number"],
            energy_mode=mode,
            value=mid_value,
            created_at=mid_datetime
        )
        print(f"创建中间记录: {{data['specific_part']}} - {{mode}}: {{mid_value}} - {{mid_record.created_at}}")
        
        # 创建最末记录
        final_value = initial_value + 100
        late_record = PLCData.objects.create(
            specific_part=data["specific_part"],
            building=data["building"],
            unit=data["unit"],
            room_number=data["room_number"],
            energy_mode=mode,
            value=final_value,
            created_at=end_datetime
        )
        print(f"创建最晚记录: {{data['specific_part']}} - {{mode}}: {{final_value}} - {{late_record.created_at}}")
        print(f"  记录日期部分: {{late_record.created_at.date()}}")
        
        created_count += 1

# 验证创建的记录
created_records = PLCData.objects.filter(
    created_at__date=TEST_DATE,
    specific_part__in=['9-1-31-3104', '9-1-31-3105']
)
print(f"总共创建了 {{created_records.count()}} 条测试数据")

# 验证过滤查询
filtered_count = PLCData.objects.filter(
    created_at__date=TEST_DATE,
    specific_part__in=['9-1-31-3104', '9-1-31-3105']
).count()
print(f"按日期和特定部分过滤的记录数: {{filtered_count}}")
'''.replace('%s', date_str)
    
    # 写入临时脚本
    with open('create_test_data.py', 'w', encoding='utf-8') as f:
        f.write(test_data_script)
    
    # 运行脚本
    result = run_django_command("shell < create_test_data.py")
    
    # 清理临时文件
    try:
        os.remove('create_test_data.py')
    except:
        pass
    
    return result

def verify_results(test_date):
    """
    验证计算结果
    """
    date_str = test_date.strftime('%Y-%m-%d')
    print(f"\n验证计算结果 (日期: {date_str})...")
    
    # 创建验证脚本，增加详细验证逻辑
    verify_script = '''
import sys
sys.stdout.reconfigure(encoding='utf-8')
from api.models import UsageQuantityDaily, PLCData
from datetime import date, timedelta
from django.utils import timezone

test_date = date.fromisoformat('%s')

# 再次检查PLC数据
plc_records = PLCData.objects.filter(
    created_at__date=test_date,
    specific_part__in=['9-1-31-3104', '9-1-31-3105']
)
print(f"验证时找到 {{plc_records.count()}} 条PLC记录")
for p in plc_records:
    print(f"  PLC记录: {{p.specific_part}} | {{p.energy_mode}} | {{p.created_at}} | {{p.value}}")
    print(f"  记录日期部分: {{p.created_at.date()}}")

# 查询每日用量记录
daily_records = UsageQuantityDaily.objects.filter(time_period=test_date)
next_day_records = UsageQuantityDaily.objects.filter(time_period=test_date + timedelta(days=1))

print(f"找到 {{daily_records.count()}} 条当日用量记录")
print(f"找到 {{next_day_records.count()}} 条次日初始记录")

if daily_records.exists():
    print("\n记录样例:")
    for record in daily_records:
        print(f"  记录ID: {{record.id}}")
        print(f"    日期: {{record.time_period}}")
        print(f"    特定部分: {{record.specific_part}}")
        print(f"    模式: {{record.energy_mode}}")
        print(f"    初始: {{record.initial_energy}}, 最终: {{record.final_energy}}, 用量: {{record.usage_quantity}}")
    
    # 验证数据准确性
    print("\n验证数据准确性:")
    for record in daily_records:
        # 获取原始PLC数据
        plc_records = PLCData.objects.filter(
            specific_part=record.specific_part,
            energy_mode=record.energy_mode,
            created_at__date=test_date
        ).order_by('created_at')
        
        print(f"  查询PLC记录: specific_part={{record.specific_part}}, energy_mode={{record.energy_mode}}, 日期={{test_date}}")
        print(f"  找到 {{plc_records.count()}} 条PLC记录")
        
        if plc_records.exists():
            earliest = plc_records.first()
            latest = plc_records.last()
            expected_initial = earliest.value or 0
            expected_final = latest.value or 0
            expected_usage = expected_final - expected_initial
            
            print(f"    预期初始: {{expected_initial}}, 实际: {{record.initial_energy}}")
            print(f"    预期最终: {{expected_final}}, 实际: {{record.final_energy}}")
            
            # 验证
            if (record.initial_energy == expected_initial and \
                record.final_energy == expected_final and \
                record.usage_quantity == expected_usage):
                print(f"  ✓ {{record.specific_part}} - {{record.energy_mode}}: 数据正确")
            else:
                print(f"  ✗ {{record.specific_part}} - {{record.energy_mode}}: 数据不一致")
                print(f"    预期: 初始={{expected_initial}}, 最终={{expected_final}}, 用量={{expected_usage}}")
                print(f"    实际: 初始={{record.initial_energy}}, 最终={{record.final_energy}}, 用量={{record.usage_quantity}}")

# 检查次日记录
next_day = test_date + timedelta(days=1)
print(f"次日({{next_day}})找到 {{next_day_records.count()}} 条记录")
for record in next_day_records:
    print(f"  次日记录: {{record.specific_part}} | {{record.energy_mode}} | 初始能量: {{record.initial_energy}}")
'''.replace('%s', date_str)
    
    # 写入临时脚本
    with open('verify_results.py', 'w', encoding='utf-8') as f:
        f.write(verify_script)
    
    # 运行脚本
    result = run_django_command("shell < verify_results.py")
    
    # 清理临时文件
    try:
        os.remove('verify_results.py')
    except:
        pass
    
    return result

def test_daily_usage_command():
    """
    测试每日用量计算管理命令
    """
    print("开始测试每日用量计算命令...")
    
    # 使用特定测试日期
    test_date = date.today() - timedelta(days=2)  # 使用前天作为测试日期，避免与实际数据冲突
    date_str = test_date.strftime('%Y-%m-%d')
    print(f"测试日期: {date_str}")
    
    # 清理该日期的现有记录
    print("\n清理现有记录...")
    cleanup_script = '''
from api.models import UsageQuantityDaily, PLCData
from datetime import date, timedelta

test_date = date.fromisoformat('%s')
# 清理当日和次日记录
UsageQuantityDaily.objects.filter(
    time_period__in=[test_date, test_date + timedelta(days=1)]
).delete()
print(f"已清理{test_date}及次日的用量记录")

# 清理PLC测试数据
plc_count = PLCData.objects.filter(
    created_at__date=test_date,
    specific_part__in=['9-1-31-3104', '9-1-31-3105']
).delete()[0]
print(f"已清理{plc_count}条PLC测试数据")
'''.replace('%s', date_str)
    
    with open('cleanup.py', 'w', encoding='utf-8') as f:
        f.write(cleanup_script)
    
    run_django_command("shell < cleanup.py")
    try:
        os.remove('cleanup.py')
    except:
        pass
    
    # 创建测试数据
    create_test_data(test_date)
    
    # 运行每日用量计算命令
    print("\n运行每日用量计算命令...")
    print(f"执行: python manage.py calculate_daily_usage --date {date_str} --run-once")
    result = run_django_command(f"calculate_daily_usage --date {date_str} --run-once")
    
    # 添加直接验证步骤
    print("\n直接验证UsageQuantityDaily记录是否存在:")
    check_script = '''
from api.models import UsageQuantityDaily, PLCData
from datetime import date

# 检查测试日期的记录
test_date = date.fromisoformat('%s')
records = UsageQuantityDaily.objects.filter(time_period=test_date)
print(f"UsageQuantityDaily记录数: {{records.count()}}")

# 检查PLC数据
plc_records = PLCData.objects.filter(
    specific_part__in=['9-1-31-3104', '9-1-31-3105'],
    created_at__date=test_date
)
print(f"PLC数据记录数: {{plc_records.count()}}")
for record in plc_records[:5]:
    print(f"  PLC: {{record.specific_part}} - {{record.energy_mode}} - {{record.value}} - {{record.created_at}}")
'''.replace('%s', date_str)
    
    with open('check_records.py', 'w', encoding='utf-8') as f:
        f.write(check_script)
    
    run_django_command("shell < check_records.py")
    try:
        os.remove('check_records.py')
    except:
        pass
    
    if result:
        print("\n命令输出:")
        print(result.stdout)
        
        if result.stderr:
            print("\n错误输出:")
            print(result.stderr)
        
        print(f"\n命令返回码: {result.returncode}")
        
        # 验证结果
        verify_results(test_date)
        
        return result.returncode
    
    return 1

if __name__ == "__main__":
    exit_code = test_daily_usage_command()
    print("\n测试完成!")
    sys.exit(exit_code)