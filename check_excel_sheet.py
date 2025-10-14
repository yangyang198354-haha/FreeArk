import xlrd

# 读取Excel文件
excel_path = 'c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource\\20221109成都乐府IP规划表最新(Plc程序更新问题).xls'

# 使用xlrd打开工作簿
workbook = xlrd.open_workbook(excel_path)

# 打印所有工作表名称，以便查看实际名称
print("所有工作表名称:")
for i, name in enumerate(workbook.sheet_names()):
    print(f"工作表{i+1}: {name}")

print("\n尝试查找包含'1栋'的工作表...")
# 查找包含'1栋'的工作表
sheet_found = False
for sheet_name in workbook.sheet_names():
    if '1栋' in sheet_name:
        print(f"找到工作表: {sheet_name}")
        sheet = workbook.sheet_by_name(sheet_name)
        
        # 打印前15行内容，查看数据结构
        print(f"\n工作表'{sheet_name}'前15行内容:")
        for row_idx in range(min(15, sheet.nrows)):
            row_data = []
            for col_idx in range(sheet.ncols):
                try:
                    cell_value = sheet.cell_value(row_idx, col_idx)
                    row_data.append(str(cell_value))
                except:
                    row_data.append('')
            print(f"行{row_idx+1}: {row_data}")
        
        sheet_found = True
        # 只查看第一个包含'1栋'的工作表
        break

if not sheet_found:
    print("未找到包含'1栋'的工作表")

print("\n脚本执行完毕")