import os
import json

# 获取当前工作目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 构建resource文件夹路径
resource_dir = os.path.join(current_dir, 'resource')

# 查找所有的原始JSON文件
json_files = [f for f in os.listdir(resource_dir) if f.endswith('_data.json')]

print(f"找到 {len(json_files)} 个JSON文件需要转换为键值对格式")

# 处理每个JSON文件
for json_file in json_files:
    json_path = os.path.join(resource_dir, json_file)
    
    try:
        # 读取原始JSON文件
        with open(json_path, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
        
        print(f"\n处理文件: {json_file}")
        print(f"  原始数据包含 {len(data_list)} 条记录")
        
        # 创建新的键值对格式数据
        key_value_data = {}
        
        for item in data_list:
            try:
                # 构建唯一键：楼栋-单元-楼层-户号
                # 从楼栋名称中提取数字部分（例如从"1栋"提取"1"）
                building_number = item.get('楼栋', '').replace('栋', '').strip()
                # 获取单元、楼层、户号信息
                unit = item.get('单元', '').replace('单元', '').strip()
                # 移除楼层中的'楼'字
                floor_str = str(item.get('楼层', '')).strip()
                # 确保彻底移除'楼'字
                floor = floor_str.replace('楼', '').strip()
                household = str(item.get('户号', '')).strip()
                
                # 构建唯一标识符键（不包含'楼'字）
                unique_key = f"{building_number}-{unit}-{floor}-{household}"
                
                # 调试输出，验证键的格式
                if '楼' in unique_key:
                    print(f"  警告：键中仍包含'楼'字 - {unique_key}，原始楼层值：{floor_str}")
                
                # 将当前item添加到键值对数据中
                key_value_data[unique_key] = item
                
            except Exception as e:
                print(f"  警告：处理某条记录时出错 - {str(e)}")
        
        # 构建新的JSON文件路径
        new_json_file = json_file.replace('.json', '_keyvalue.json')
        new_json_path = os.path.join(resource_dir, new_json_file)
        
        # 保存新的键值对格式JSON文件
        with open(new_json_path, 'w', encoding='utf-8') as f:
            json.dump(key_value_data, f, ensure_ascii=False, indent=2)
        
        print(f"  已成功转换为键值对格式，保存到：{new_json_file}")
        print(f"  转换后数据包含 {len(key_value_data)} 个键值对")
        
        # 显示几个示例键
        if key_value_data:
            example_keys = list(key_value_data.keys())[:3]  # 显示前3个键
            print(f"  示例键: {', '.join(example_keys)}")
            
    except Exception as e:
        print(f"  错误: 无法读取或处理文件 {json_file} - {str(e)}")

print("\n转换完成！")
print("现在每个楼栋JSON文件都有对应的键值对格式版本，特点：")
print("1. 使用'楼栋-单元-楼层-户号'作为唯一键")
print("2. 可以通过键直接访问对应的住户信息，无需遍历整个文件")
print("3. 保留了原始数据的所有字段和值")