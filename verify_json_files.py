import os
import json

# 获取当前工作目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 构建resource文件夹路径
resource_dir = os.path.join(current_dir, 'resource')

# 查找所有的JSON文件
json_files = [f for f in os.listdir(resource_dir) if f.endswith('_data.json')]

print(f"找到 {len(json_files)} 个JSON文件：")

# 检查每个JSON文件
for json_file in json_files:
    json_path = os.path.join(resource_dir, json_file)
    
    try:
        # 读取JSON文件
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\n文件: {json_file}")
        print(f"  包含 {len(data)} 条记录")
        
        # 检查是否有记录，显示第一条记录的字段名
        if data:
            first_record = data[0]
            print(f"  字段名: {', '.join(first_record.keys())}")
            
            # 显示第一条记录的内容摘要
            print("  第一条记录示例:")
            for key, value in list(first_record.items())[:3]:  # 只显示前3个字段
                print(f"    {key}: {value}")
                
    except Exception as e:
        print(f"  错误: 无法读取或解析文件 {json_file} - {str(e)}")

print("\n验证完成！")