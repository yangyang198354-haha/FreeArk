import pandas as pd
import os

# 获取当前工作目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 构建Excel文件的完整路径
excel_file = os.path.join(current_dir, 'resource', '大屏IP及MAC-20251005.xlsx')

# 检查文件是否存在
if not os.path.exists(excel_file):
    print(f"错误：找不到文件 {excel_file}")
    exit(1)

# 读取Excel文件，不使用第一行作为表头
df = pd.read_excel(excel_file, header=None)

print(f"成功读取文件，共有 {len(df)} 行数据")

# 添加英文表头
headers = ['Building', 'IP Address', 'MAC Address']

# 检查数据列数是否匹配表头数量
if len(df.columns) >= len(headers):
    # 设置新表头
    df.columns = headers + [f'Column_{i}' for i in range(len(headers), len(df.columns))]
    # 保存修改后的文件
    output_file = os.path.join(current_dir, 'resource', '大屏IP及MAC-20251005_with_header.xlsx')
    df.to_excel(output_file, index=False)
    print(f"已成功添加表头并保存到：{output_file}")
else:
    print(f"错误：数据列数({len(df.columns)})少于表头数量({len(headers)})")
    exit(1)

print("操作完成！")