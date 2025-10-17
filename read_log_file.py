# 使用Python直接读取日志文件，避免Windows命令行编码问题
import os
import sys

# 读取日志文件
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
log_files = ['test_20251015.log', 'simple_test_20251015.log']

for log_file in log_files:
    log_path = os.path.join(log_dir, log_file)
    print(f'\n=== 查看文件: {log_file} ===')
    if os.path.exists(log_path):
        try:
            # 使用UTF-8编码读取文件
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                print(content)
        except Exception as e:
            print(f'读取文件失败: {e}')
    else:
        print(f'文件不存在: {log_path}')

print('\n读取完成，请检查输出内容是否正确显示中文')