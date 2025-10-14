import pandas as pd
import os
import json

# 获取当前工作目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 构建Excel文件的完整路径（使用已经添加了中文表头的文件）
excel_file = os.path.join(current_dir, 'resource', '大屏IP及MAC-20251005_with_chinese_header.xlsx')

# 检查文件是否存在
if not os.path.exists(excel_file):
    print(f"错误：找不到文件 {excel_file}")
    exit(1)

# 创建输出文件夹（如果不存在）
output_dir = os.path.join(current_dir, 'resource')
os.makedirs(output_dir, exist_ok=True)

# 读取Excel文件中的所有sheet
print(f"正在读取文件：{excel_file}")
excel_data = pd.ExcelFile(excel_file)
sheet_names = excel_data.sheet_names

print(f"找到 {len(sheet_names)} 个sheet：{', '.join(sheet_names)}")

# 处理每个sheet
for sheet_name in sheet_names:
    # 读取sheet数据
    df = pd.read_excel(excel_file, sheet_name=sheet_name)
    
    print(f"处理sheet '{sheet_name}'，共有 {len(df)} 行数据")
    
    # 将数据转换为字典列表
    data_list = df.to_dict('records')
    
    # 构建JSON文件路径，使用楼栋名称命名
    json_file_name = f"{sheet_name}_data.json"
    json_file_path = os.path.join(output_dir, json_file_name)
    
    # 将数据写入JSON文件
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)
    
    print(f"  已成功生成JSON文件：{json_file_path}")

print(f"\n操作完成！已为所有楼栋生成JSON文件。")
print(f"JSON文件保存在：{output_dir}")
print("每个文件包含对应楼栋的所有住户信息，包括专有部分坐落、楼栋、单元、楼层、户号、绑定状态、IP地址和唯一标识符等字段。")