# 测试文件编码
import os
import time

# 直接写入UTF-8文件测试
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
test_path = os.path.join(log_dir, 'encoding_test.log')

# 使用Python的标准文件操作写入中文
with open(test_path, 'w', encoding='utf-8') as f:
    f.write('这是测试中文编码的文件\n')
    f.write('This is a test for file encoding\n')
    f.write('测试完成时间: ' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n')

print(f'测试文件已创建: {test_path}')
print('请查看文件内容以确认中文是否正确显示')