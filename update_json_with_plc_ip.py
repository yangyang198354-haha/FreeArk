import json
import os

# 定义文件路径
resource_dir = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource\\'
plc_map_file = os.path.join(resource_dir, 'building_plc_map.json')

# 读取楼栋与PLC IP的对应关系
try:
    with open(plc_map_file, 'r', encoding='utf-8') as f:
        building_plc_map = json.load(f)
    
    print(f"成功读取楼栋与PLC IP映射关系，共{len(building_plc_map)}条记录")
    print("映射关系如下：")
    for building_num, plc_ip in building_plc_map.items():
        print(f"楼栋{building_num} -> PLC IP: {plc_ip}")
    
except Exception as e:
    print(f"读取楼栋与PLC IP映射关系文件时出错：{e}")
    exit(1)

# 遍历resource目录下的所有JSON文件
print("\n开始处理resource目录下的JSON文件...")

try:
    for filename in os.listdir(resource_dir):
        # 只处理形如X#_data.json和X#_data_test.json的文件
        if ((filename.endswith('_data.json') or filename.endswith('_data_test.json')) and '#' in filename) and not (filename.endswith('_improved_data_collected_') and filename.endswith('.json')):
            # 提取楼栋号
            building_num = filename.split('#')[0]
            
            # 检查该楼栋是否有对应的PLC IP地址
            if building_num in building_plc_map:
                plc_ip = building_plc_map[building_num]
                file_path = os.path.join(resource_dir, filename)
                
                try:
                    # 读取JSON文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 检查是否为字典类型
                    if isinstance(data, dict):
                        updated = False
                        
                        # 遍历JSON文件中的每个条目
                        for key, value in data.items():
                            # 检查value是否为字典
                            if isinstance(value, dict):
                                # 如果PLC IP地址不存在或与新地址不同，则更新
                                if 'PLC IP地址' not in value or value['PLC IP地址'] != plc_ip:
                                    value['PLC IP地址'] = plc_ip
                                    updated = True
                        
                        # 如果有更新，保存文件
                        if updated:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            print(f"已成功更新文件 {filename}，添加PLC IP地址: {plc_ip}")
                        else:
                            print(f"文件 {filename} 中已包含正确的PLC IP地址，无需更新")
                    else:
                        print(f"警告：文件 {filename} 的内容不是字典类型，无法处理")
                    
                except Exception as e:
                    print(f"处理文件 {filename} 时出错：{e}")
            else:
                print(f"警告：楼栋{building_num}没有对应的PLC IP地址映射，跳过文件 {filename}")
except Exception as e:
    print(f"处理文件时出错：{e}")

print("\n所有文件处理完成！")