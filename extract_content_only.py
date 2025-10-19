import json
import os

# 设置资源目录路径
resource_dir = "c:/Users/yanggyan/TRAE/FreeArk/resource"
all_onwer_path = os.path.join(resource_dir, "all_onwer.json")

# 获取所有以_data.json结尾的文件
json_files = [f for f in os.listdir(resource_dir) if f.endswith('_data.json')]

# 初始化最终的合并结果（只包含content内容的平面对象）
content_only = {}

# 遍历所有data.json文件
for json_file in json_files:
    file_path = os.path.join(resource_dir, json_file)
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
        
        # 直接合并content内容到最终结果
        # 确保file_data是字典类型
        if isinstance(file_data, dict):
            # 将当前文件的所有键值对添加到content_only
            for key, value in file_data.items():
                if key not in content_only:  # 避免覆盖，如果有重复键
                    content_only[key] = value
                else:
                    print(f"警告: 键 {key} 在文件 {json_file} 中重复出现，已跳过")
        else:
            print(f"警告: 文件 {json_file} 的内容不是有效的JSON字典")
        
        print(f"成功处理文件: {json_file}")
    except Exception as e:
        print(f"处理文件 {json_file} 时出错: {str(e)}")

# 写入结果到all_onwer.json
try:
    with open(all_onwer_path, 'w', encoding='utf-8') as f:
        json.dump(content_only, f, ensure_ascii=False, indent=2)
    print(f"成功重写 {all_onwer_path}")
    print(f"总共合并了 {len(content_only)} 个住户数据")
except Exception as e:
    print(f"写入文件时出错: {str(e)}")