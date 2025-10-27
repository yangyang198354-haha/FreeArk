import os
import sys
import platform

# 设置Windows控制台编码
if platform.system() == 'Windows':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 创建修复后的验证脚本，避免使用f-string在文件中
verify_script = """
from api.models import PLCData
print('检查PLC数据...')
all_plc = PLCData.objects.all()
print('总记录数:', all_plc.count())

# 检查特定部分
parts = PLCData.objects.filter(specific_part__in=['9-1-31-3104', '9-1-31-3105'])
print('特定部分记录数:', parts.count())

# 打印这些记录的详情
if parts.exists():
    print('\n特定部分记录详情:')
    for p in parts:
        print('ID:', p.id)
        print('specific_part:', p.specific_part)
        print('energy_mode:', p.energy_mode)
        print('created_at:', p.created_at)
        print('value:', p.value)
        print('---')

# 检查能量模式
print('\n所有能量模式:')
modes = PLCData.objects.values_list('energy_mode', flat=True).distinct()
for mode in modes[:10]:
    print('-', mode)
"""

# 写入文件
with open('simple_verify.py', 'w', encoding='utf-8') as f:
    f.write(verify_script)

# 使用subprocess运行，避免编码问题
print("运行简单验证脚本...")
import subprocess
result = subprocess.run(
    'python manage.py shell < simple_verify.py',
    shell=True,
    capture_output=True,
    text=True,
    encoding='utf-8'
)

print(result.stdout)
if result.stderr:
    print("错误:", result.stderr)

# 清理
os.remove('simple_verify.py')