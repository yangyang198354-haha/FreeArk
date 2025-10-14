import json
import os

# 读取房间与PLC IP的对应关系
room_plc_map_path = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource\\room_plc_map.json'
with open(room_plc_map_path, 'r', encoding='utf-8') as f:
    room_plc_map = json.load(f)

print(f"成功读取{len(room_plc_map)}条房间与PLC IP映射关系")

# 打印room_plc_map中的前几个条目，用于调试
print("\nroom_plc_map前5条记录:")
for i, (room, ip) in enumerate(room_plc_map.items()):
    if i < 5:
        print(f"  {room}: {ip}")

# 获取resource目录下的所有JSON文件
resource_dir = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource'
json_files = [f for f in os.listdir(resource_dir) if f.endswith('.json') and f != 'room_plc_map.json' and f != 'building_plc_map.json' and f != 'plc_config.json']

print(f"\n找到{len(json_files)}个JSON文件需要处理")

# 处理每个JSON文件
for json_file in json_files:
    json_path = os.path.join(resource_dir, json_file)
    
    try:
        # 读取JSON文件内容
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 统计更新数量
        update_count = 0
        total_entries = 0
        
        print(f"\n处理文件: {json_file}")
        
        # 遍历JSON文件中的每个条目
        if isinstance(data, dict):
            for key, entry in data.items():
                total_entries += 1
                # 检查条目是否为字典
                if isinstance(entry, dict):
                    # 从键名提取房间号（格式为1-1-2-201 -> 转换为1-1-201）
                    key_parts = key.split('-')
                    if len(key_parts) == 4 and all(part.isdigit() for part in key_parts):
                        room_number = f"{key_parts[0]}-{key_parts[1]}-{key_parts[3]}"
                    else:
                        room_number = None
                    
                    # 如果从键名没有提取到房间号，从'专有部分坐落'字段提取
                    if not room_number and '专有部分坐落' in entry:
                        location = entry['专有部分坐落']
                        location_parts = location.split('-')
                        if len(location_parts) >= 4:
                            room_number = f"{location_parts[1]}-{location_parts[2]}-{location_parts[3]}"
                    
                    # 如果找到了房间号
                    if room_number:
                        # 检查是否存在精确匹配
                        if room_number in room_plc_map:
                            plc_ip = room_plc_map[room_number]
                            # 更新PLC IP地址字段
                            entry['PLC IP地址'] = plc_ip
                            update_count += 1
                            # 特别打印1-1-201房间的更新信息
                            if room_number == '1-1-201':
                                print(f"  已更新房间{room_number}的PLC IP地址为: {plc_ip}")
                            # 打印其他一些示例
                            elif update_count % 50 == 0:
                                print(f"  更新房间{room_number}的PLC IP地址为: {plc_ip}")
        
        # 如果有更新，保存文件
        if update_count > 0:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  已更新{update_count}/{total_entries}个条目的PLC IP地址")
        
    except Exception as e:
        print(f"处理文件{json_file}时出错: {str(e)}")

print("\n所有文件处理完毕")