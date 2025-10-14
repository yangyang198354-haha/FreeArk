import pandas as pd

try:
    # 读取最新的Excel文件
    df = pd.read_excel('output/累计用量_20251013_230136.xlsx')
    
    # 打印表头和前几行数据
    print("Excel文件列名:")
    print(list(df.columns))
    
    print("\nExcel文件前5行数据:")
    print(df.head())
    
    # 如果有timestamp列，特别打印该列内容
    if 'timestamp' in df.columns:
        print("\n时间戳列内容:")
        print(df['timestamp'].head())
    
    if 'timestamp_ms' in df.columns:
        print("\n毫秒时间戳列内容:")
        print(df['timestamp_ms'].head())

except Exception as e:
    print(f"读取Excel文件失败: {str(e)}")
    
    # 尝试列出output目录中的所有Excel文件
    import os
    excel_files = [f for f in os.listdir('output') if f.endswith('.xlsx')]
    print("\nOutput目录中的Excel文件:")
    for file in sorted(excel_files, reverse=True):
        print(f"- {file}")