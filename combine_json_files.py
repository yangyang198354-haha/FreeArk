import os
import json
import glob
from datetime import datetime

# 设置输出目录路径
output_dir = "c:/Users/yanggyan/TRAE/FreeArk/output"
all_owners_file = os.path.join(output_dir, "all_onwer.json")

def combine_json_files():
    """合并所有data.json文件到一个all_onwer.json文件"""
    # 查找所有匹配的json文件
    json_files = glob.glob(os.path.join(output_dir, "*data_improved_data_collected*.json"))
    
    if not json_files:
        print(f"在目录 {output_dir} 中没有找到匹配的data.json文件")
        return
    
    print(f"找到 {len(json_files)} 个data.json文件，开始合并...")
    
    # 初始化合并结果
    combined_data = {
        "total_files": len(json_files),
        "collection_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "buildings": []
    }
    
    # 读取并合并每个文件
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 提取文件名作为建筑标识符
                file_name = os.path.basename(file_path)
                
                # 将该文件的数据添加到合并结果
                building_data = {
                    "file_name": file_name,
                    "content": data
                }
                combined_data["buildings"].append(building_data)
                
                print(f"已处理: {file_name}")
                
        except json.JSONDecodeError as e:
            print(f"解析文件 {file_path} 时出错: {e}")
        except Exception as e:
            print(f"处理文件 {file_path} 时出错: {e}")
    
    # 保存合并后的结果
    try:
        with open(all_owners_file, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n合并完成！结果已保存到: {all_owners_file}")
        print(f"总共有 {len(combined_data['buildings'])} 个建筑的数据被合并")
        
    except Exception as e:
        print(f"保存合并结果时出错: {e}")

if __name__ == "__main__":
    combine_json_files()