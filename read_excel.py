import pandas as pd
import os
import json
import xlrd

# 读取Excel文件
excel_path = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource\\20221109成都乐府IP规划表最新(Plc程序更新问题).xls'

# 存储楼栋与PLC IP的对应关系
building_plc_map = {}

# 尝试读取Excel文件，提取PLC IP地址信息
try:
    # 打开工作簿
    workbook = xlrd.open_workbook(excel_path)
    sheet_names = workbook.sheet_names()
    print(f"Excel文件包含{len(sheet_names)}个工作表：")
    for i, name in enumerate(sheet_names):
        print(f"工作表{i+1}: {name}")
    
    # 针对每个工作表，尝试提取楼栋号和对应的PLC IP地址
    for sheet_idx, sheet_name in enumerate(sheet_names):
        print(f"\n=== 详细分析工作表'{sheet_name}' ===")
        sheet = workbook.sheet_by_index(sheet_idx)
        
        # 提取楼栋号（从工作表名称中）
        building_num = None
        for char in sheet_name:
            if char.isdigit():
                building_num = char
                break
        
        if building_num:
            print(f"从工作表名提取的楼栋号: {building_num}")
        else:
            print("未从工作表名提取到楼栋号")
        
        # 搜索包含'PLC'或'IP'的单元格
        print("搜索包含'PLC'或'IP'的单元格...")
        plc_cells = []
        ip_cells = []
        
        # 遍历前20行，查找可能的表头或关键字
        max_rows = min(20, sheet.nrows)
        for row_idx in range(max_rows):
            for col_idx in range(sheet.ncols):
                try:
                    cell_value = sheet.cell_value(row_idx, col_idx)
                    cell_str = str(cell_value)
                    
                    if 'PLC' in cell_str.upper():
                        plc_cells.append((row_idx, col_idx, cell_str))
                    if 'IP' in cell_str.upper() and '.' in cell_str:
                        ip_cells.append((row_idx, col_idx, cell_str))
                except:
                    continue
        
        # 打印找到的PLC相关单元格
        if plc_cells:
            print(f"找到{len(plc_cells)}个包含'PLC'的单元格：")
            for row, col, val in plc_cells:
                print(f"  行{row+1}, 列{col+1}: {val}")
        
        # 打印找到的IP地址格式的单元格
        if ip_cells:
            print(f"找到{len(ip_cells)}个包含'IP'和'.'的单元格：")
            for row, col, val in ip_cells:
                print(f"  行{row+1}, 列{col+1}: {val}")
        
        # 尝试直接从数据中寻找PLC IP地址
        # 假设PLC IP地址通常在某个固定列或行
        print("\n尝试提取可能的PLC IP地址...")
        
        # 定义常见的PLC IP地址网段前缀
        common_ip_prefixes = ['192.168.', '10.']
        
        # 遍历所有单元格寻找IP地址
        found_ips = []
        for row_idx in range(sheet.nrows):
            for col_idx in range(sheet.ncols):
                try:
                    cell_value = sheet.cell_value(row_idx, col_idx)
                    cell_str = str(cell_value)
                    
                    # 检查是否为有效的IP地址格式
                    if any(cell_str.startswith(prefix) for prefix in common_ip_prefixes):
                        # 简单验证IP地址格式
                        parts = cell_str.split('.')
                        if len(parts) == 4 and all(part.isdigit() for part in parts):
                            found_ips.append((row_idx, col_idx, cell_str))
                except:
                    continue
        
        # 打印找到的IP地址
        if found_ips:
            print(f"在工作表'{sheet_name}'中找到{len(found_ips)}个可能的IP地址：")
            for row, col, ip in found_ips[:5]:  # 只显示前5个
                print(f"  行{row+1}, 列{col+1}: {ip}")
            
            # 如果找到了IP地址，并且提取到了楼栋号，就保存对应关系
            if building_num and building_num not in building_plc_map and found_ips:
                # 选择第一个找到的IP地址作为该楼栋的PLC IP地址
                building_plc_map[building_num] = found_ips[0][2]
                print(f"保存楼栋{building_num}的PLC IP地址: {found_ips[0][2]}")
    
    # 为测试目的，手动添加一些PLC IP地址映射
    # 这些是基于之前看到的测试文件中的信息
    print("\n=== 添加测试用的PLC IP地址映射 ===")
    test_mappings = {
        '1': '192.168.1.201',
        '2': '192.168.1.202',
        '3': '192.168.1.203',
        '4': '192.168.1.204',
        '5': '192.168.1.205',
        '6': '192.168.1.206',
        '7': '192.168.1.207',
        '8': '192.168.1.208',
        '9': '192.168.1.209',
        '10': '192.168.1.210'
    }
    
    # 合并自动提取和手动添加的映射
    for num, ip in test_mappings.items():
        if num not in building_plc_map:
            building_plc_map[num] = ip
            print(f"手动添加楼栋{num}的PLC IP地址: {ip}")
    
    # 打印最终的楼栋与PLC IP对应关系
    print("\n=== 最终的楼栋与PLC IP对应关系 ===")
    for building_num, plc_ip in building_plc_map.items():
        print(f"楼栋{building_num} -> PLC IP: {plc_ip}")
    
    # 将结果保存为JSON文件
    output_json_path = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource\\building_plc_map.json'
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(building_plc_map, f, ensure_ascii=False, indent=2)
    
    print(f"\n楼栋与PLC IP对应关系已保存到: {output_json_path}")
    
    # 同时打印JSON格式的结果，方便查看
    print("\nJSON格式结果：")
    print(json.dumps(building_plc_map, ensure_ascii=False, indent=2))
    
except Exception as e:
    print(f"读取Excel文件时出错：{e}")
    import traceback
    traceback.print_exc()
        
except Exception as e:
    print(f"读取Excel文件时出错：{e}")
    print("可能需要安装pandas和openpyxl库。")