import pandas as pd
import os

# 获取Excel文件的完整路径
excel_file = os.path.join('c:\\Users\\yanggyan\\TRAE\\FreeArk\\resource', '大屏IP及MAC-20251005.xlsx')

# 检查文件是否存在
if not os.path.exists(excel_file):
    print(f"错误：找不到文件 '{excel_file}'")
    exit(1)

# 读取Excel文件
print(f"正在读取文件：{excel_file}")
df = pd.read_excel(excel_file)

# 获取当前列数
num_columns = df.shape[1]

# 根据列数设置表头
if num_columns == 3:
    df.columns = ['楼栋', '三恒系统控制柜主机IP地址', '唯一标识符(MAC)']
elif num_columns == 2:
    df.columns = ['楼栋', '三恒系统控制柜主机IP地址']
    # 如果只有两列，添加第三列
    df['唯一标识符(MAC)'] = ''
else:
    print(f"警告：Excel文件有 {num_columns} 列，而预期是3列")
    # 为所有列设置表头
    headers = []
    for i in range(num_columns):
        if i == 0:
            headers.append('楼栋')
        elif i == 1:
            headers.append('三恒系统控制柜主机IP地址')
        elif i == 2:
            headers.append('唯一标识符(MAC)')
        else:
            headers.append(f'列{i+1}')
    df.columns = headers

# 保存修改后的文件
print("正在保存修改后的文件...")
df.to_excel(excel_file, index=False, engine='openpyxl')

print("Excel文件表头添加完成！")
print(f"已在文件 '{excel_file}' 中添加表头：{list(df.columns)}")