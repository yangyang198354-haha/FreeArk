import json
import os
from datetime import datetime

# 设置资源目录路径
resource_dir = "c:/Users/yanggyan/TRAE/FreeArk/resource"
all_onwer_path = os.path.join(resource_dir, "all_onwer.json")

# 获取所有以_data.json结尾的文件
json_files = [f for f in os.listdir(resource_dir) if f.endswith('_data.json')]

# 初始化合并结果
merged_data = {
    "total_files": len(json_files),
    "collection_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "buildings": []
}

# 遍历所有data.json文件
for json_file in json_files:
    file_path = os.path.join(resource_dir, json_file)
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
        
        # 添加到buildings数组
        merged_data["buildings"].append({
            "file_name": json_file,
            "content": file_data
        })
        
        print(f"成功读取文件: {json_file}")
    except Exception as e:
        print(f"读取文件 {json_file} 时出错: {str(e)}")

# 按照文件名排序buildings数组（按照楼栋号排序）
def sort_key(building):
    # 提取文件名中的数字部分作为排序依据
    file_name = building["file_name"]
    try:
        # 匹配如 "1#_data.json" 中的数字
        import re
        match = re.match(r'(\d+)#', file_name)
        if match:
            return int(match.group(1))
        return 999  # 非标准文件名排在后面
    except:
        return 999

merged_data["buildings"].sort(key=sort_key)

# 写入合并结果到all_onwer.json
try:
    with open(all_onwer_path, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)
    print(f"成功生成 {all_onwer_path}")
    print(f"总共合并了 {len(json_files)} 个文件")
except Exception as e:
    print(f"写入文件时出错: {str(e)}")