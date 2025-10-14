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

# 读取Excel文件中的所有sheet
print(f"正在读取文件：{excel_file}")
excel_data = pd.ExcelFile(excel_file)
sheet_names = excel_data.sheet_names

print(f"找到 {len(sheet_names)} 个sheet：{', '.join(sheet_names)}")

# 定义中文表头
chinese_headers = ["专有部分坐落", "楼栋", "单元", "楼层", "户号", "绑定状态", "IP地址", "唯一标识符"]

# 创建ExcelWriter对象来保存所有sheet
output_file = os.path.join(current_dir, 'resource', '大屏IP及MAC-20251005_with_chinese_header.xlsx')
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    # 处理每个sheet
    for sheet_name in sheet_names:
        # 读取sheet数据，不使用第一行作为表头
        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
        
        print(f"处理sheet '{sheet_name}'，共有 {len(df)} 行数据")
        
        # 检查数据列数是否足够
        if len(df.columns) >= len(chinese_headers):
            # 设置新的中文表头
            df.columns = chinese_headers + [f'其他列_{i}' for i in range(len(chinese_headers), len(df.columns))]
            # 保存当前sheet到新文件
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  已成功为sheet '{sheet_name}'添加中文表头")
        else:
            print(f"  警告：sheet '{sheet_name}'的列数({len(df.columns)})少于指定的表头数量({len(chinese_headers)})，已跳过")

print(f"\n操作完成！所有处理后的sheet已保存到：{output_file}")
print("注意：")
print("1. 原始文件保持不变")
print("2. 每个sheet都添加了指定的中文表头")
print("3. 表头包括：专有部分坐落、楼栋、单元、楼层、户号、绑定状态、IP地址、唯一标识符")