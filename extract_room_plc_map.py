import xlrd
import json
import os

# 读取Excel文件
excel_path = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource\\20221109成都乐府IP规划表最新(Plc程序更新问题).xls'

# 存储房间与PLC IP的对应关系
room_plc_map = {}

# 打开工作簿
workbook = xlrd.open_workbook(excel_path)

# 获取所有工作表名称
all_sheets = workbook.sheet_names()
print(f"Excel文件包含{len(all_sheets)}个工作表")

# 遍历所有工作表
for sheet_idx, sheet_name in enumerate(all_sheets):
    print(f"\n处理工作表: {sheet_name}")
    
    # 跳过包含'区口机'的工作表
    if '区口机' in sheet_name:
        print(f"  跳过工作表'{sheet_name}'，因为它包含'区口机'")
        continue
    
    sheet = workbook.sheet_by_index(sheet_idx)
    
    # 遍历所有行
    i = 0
    while i < sheet.nrows:
        try:
            # 检查当前行和下一行，寻找房间号和对应的大屏/PLC IP
            current_row_data = []
            
            # 收集当前行的数据
            for col_idx in range(sheet.ncols):
                try:
                    current_cell = sheet.cell_value(i, col_idx)
                    current_row_data.append(str(current_cell).strip())
                except:
                    current_row_data.append('')
            
            # 查找房间号
            room_number = ''
            for cell in current_row_data:
                if '-' in cell and cell.replace('-', '').isdigit():
                    room_number = cell
                    break
            
            # 如果找到了房间号
            if room_number:
                # 查找大屏IP（通常在房间号行）
                screen_ip = ''
                for cell in current_row_data:
                    if '.' in cell and len(cell) > 7:
                        parts = cell.split('.')
                        if len(parts) == 4 and all(part.isdigit() for part in parts):
                            screen_ip = cell
                            break
                
                # 查找PLC IP（通常在下一行）
                plc_ip = ''
                if i + 1 < sheet.nrows:
                    next_row_data = []
                    for col_idx in range(sheet.ncols):
                        try:
                            next_cell = sheet.cell_value(i + 1, col_idx)
                            next_row_data.append(str(next_cell).strip())
                        except:
                            next_row_data.append('')
                    
                    # 检查下一行是否包含'PLC'
                    if 'PLC' in ''.join(next_row_data).upper():
                        # 在下一行寻找IP地址
                        for cell in next_row_data:
                            if '.' in cell and len(cell) > 7:
                                parts = cell.split('.')
                                if len(parts) == 4 and all(part.isdigit() for part in parts):
                                    plc_ip = cell
                                    break
                
                # 如果找到了PLC IP地址
                if plc_ip:
                    # 格式化房间号为标准格式
                    formatted_room = room_number
                    # 添加映射关系
                    room_plc_map[formatted_room] = plc_ip
                    print(f"  找到映射: 房间{room_number} -> 大屏IP: {screen_ip}, PLC IP: {plc_ip}")
                    # 跳过下一行（PLC行）
                    i += 1
            
        except Exception as e:
            # 忽略处理单个行时的错误
            print(f"  处理行{i+1}时出错: {str(e)}")
        
        i += 1

# 重要修正：确保1栋1单元的特定房间有正确的PLC IP地址（根据用户提供的信息）
corrected_mappings = {
    '1-1-201': '192.168.1.5',  # 大屏IP: 192.168.1.4
    '1-1-202': '192.168.1.7',  # 大屏IP: 192.168.1.6
    '1-1-301': '192.168.1.9',  # 大屏IP: 192.168.1.8
    '1-1-302': '192.168.1.11', # 大屏IP: 192.168.1.10
    '1-1-401': '192.168.1.13'  # 大屏IP: 192.168.1.12
}

print("\n=== 应用修正的映射 ===")
for room, plc_ip in corrected_mappings.items():
    old_ip = room_plc_map.get(room, '未设置')
    room_plc_map[room] = plc_ip
    print(f"  修正房间{room}的PLC IP地址: 从{old_ip}改为{plc_ip}")

# 打印提取的房间与PLC IP对应关系中的前10条
print("\n=== 提取的房间与PLC IP对应关系（前10条）===")
count = 0
for room, plc_ip in room_plc_map.items():
    print(f"房间{room} -> PLC IP: {plc_ip}")
    count += 1
    if count >= 10:
        break

# 将结果保存为JSON文件
output_json_path = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource\\room_plc_map.json'
with open(output_json_path, 'w', encoding='utf-8') as f:
    json.dump(room_plc_map, f, ensure_ascii=False, indent=2)

print(f"\n房间与PLC IP对应关系已保存到: {output_json_path}")
print(f"共提取了{len(room_plc_map)}条房间与PLC IP映射关系")

print("\n脚本执行完毕")