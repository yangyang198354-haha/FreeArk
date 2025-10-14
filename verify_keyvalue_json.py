import os
import json

# 获取当前工作目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 构建resource文件夹路径
resource_dir = os.path.join(current_dir, 'resource')

# 查找所有的键值对格式JSON文件
keyvalue_files = [f for f in os.listdir(resource_dir) if f.endswith('_keyvalue.json')]

print(f"找到 {len(keyvalue_files)} 个键值对格式的JSON文件需要验证")

# 处理每个JSON文件
for json_file in keyvalue_files:
    json_path = os.path.join(resource_dir, json_file)
    
    try:
        # 读取JSON文件
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\n验证文件: {json_file}")
        print(f"  文件大小: {os.path.getsize(json_path)} 字节")
        print(f"  包含 {len(data)} 个键值对")
        
        # 显示前3个键
        if data:
            first_keys = list(data.keys())[:3]
            print(f"  前3个唯一键: {', '.join(first_keys)}")
            
            # 显示第一个键对应的完整数据
            first_key = first_keys[0]
            first_value = data[first_key]
            print(f"\n  第一个键 '{first_key}' 对应的数据:")
            
            # 确保字段名正确显示
            for field, value in first_value.items():
                print(f"    {field}: {value}")
            
    except Exception as e:
        print(f"  错误: 无法读取或处理文件 {json_file} - {str(e)}")

print("\n验证完成！")
print("键值对格式JSON文件的特点：")
print("1. 采用'楼栋-单元-楼层-户号'作为唯一标识符键，格式为纯数字+'-'（如'1-1-2-201'）")
print("2. 可以通过键直接访问对应住户信息，无需遍历整个文件")
print("3. 保留了原始数据的所有字段和值")
print("4. 方便快速查找和访问特定住户的信息")