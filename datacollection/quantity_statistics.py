import os
import json
import re
import pandas as pd
from collections import defaultdict
import glob
import os

# 设置编码以避免中文显示乱码
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
if sys.stderr.encoding != 'utf-8':
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

# 添加FreeArk目录到Python路径，确保模块可以正确导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger

# 获取logger，日志级别从配置文件读取
logger = get_logger('quantity_statistics')

class QuantityStatistics:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.data = defaultdict(lambda: defaultdict(dict))  # device_id -> metric_type -> {timestamp: value}
        self.timestamps = set()
        
    def extract_timestamp_from_filename(self, filename):
        # 从文件名中提取时间戳，例如：3#_data_improved_data_collected_20251014_214906.json
        match = re.search(r'_improved_data_collected_(\d{8}_\d{6})', filename)
        if match:
            timestamp_str = match.group(1)
            # 转换为更易读的格式：YYYY-MM-DD HH:MM:SS
            readable_timestamp = f"{timestamp_str[:4]}-{timestamp_str[4:6]}-{timestamp_str[6:8]} {timestamp_str[9:11]}:{timestamp_str[11:13]}:{timestamp_str[13:15]}"
            return timestamp_str, readable_timestamp
        return None, None
    
    def load_all_files(self):
        # 获取所有符合条件的JSON文件
        file_pattern = os.path.join(self.output_dir, '*_data_improved_data_collected_*.json')
        json_files = glob.glob(file_pattern)
        
        for file_path in json_files:
            filename = os.path.basename(file_path)
            raw_timestamp, readable_timestamp = self.extract_timestamp_from_filename(filename)
            if not raw_timestamp:
                logger.warning(f"无法从文件名 {filename} 中提取时间戳，跳过此文件")
                print(f"警告: 无法从文件名 {filename} 中提取时间戳，跳过此文件")
                continue
            
            self.timestamps.add((raw_timestamp, readable_timestamp))
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    
                for device_id, device_info in file_data.items():
                    # 检查device_id格式是否正确（楼栋-单元-楼层-户号）
                    if re.match(r'^\d+-\d+-\d+-\d+$', device_id):
                        # 处理累计制热数据
                        if 'data' in device_info and 'total_hot_quantity' in device_info['data']:
                            hot_data = device_info['data']['total_hot_quantity']
                            if hot_data['success'] and hot_data['value'] is not None:
                                self.data[device_id]['累计制热'][raw_timestamp] = hot_data['value']
                            else:
                                self.data[device_id]['累计制热'][raw_timestamp] = '失败'
                        
                        # 处理累计制冷数据
                        if 'data' in device_info and 'total_cold_quantity' in device_info['data']:
                            cold_data = device_info['data']['total_cold_quantity']
                            if cold_data['success'] and cold_data['value'] is not None:
                                self.data[device_id]['累计制冷'][raw_timestamp] = cold_data['value']
                            else:
                                self.data[device_id]['累计制冷'][raw_timestamp] = '失败'
            except Exception as e:
                logger.error(f"处理文件 {filename} 时出错: {str(e)}")
                print(f"处理文件 {filename} 时出错: {str(e)}")
    
    def generate_summary_table(self):
        # 按时间戳排序（使用原始时间戳进行排序，但在表格中显示易读格式）
        sorted_timestamps = sorted(self.timestamps, key=lambda x: x[0])
        
        # 准备表格数据
        table_data = []
        for device_id in sorted(self.data.keys()):
            device_data = self.data[device_id]
            for metric_type in ['累计制热', '累计制冷']:
                if metric_type in device_data:
                    row = {
                        '设备编号': device_id,
                        '指标类型': metric_type
                    }
                    
                    # 填充各个时间戳的值，使用易读格式作为列名
                    for raw_timestamp, readable_timestamp in sorted_timestamps:
                        if raw_timestamp in device_data[metric_type]:
                            row[readable_timestamp] = device_data[metric_type][raw_timestamp]
                        else:
                            row[readable_timestamp] = ''  # 未查询到该device_id
                    
                    table_data.append(row)
        
        # 创建DataFrame
        columns = ['设备编号', '指标类型'] + [ts[1] for ts in sorted_timestamps]  # 使用易读格式作为列名
        df = pd.DataFrame(table_data, columns=columns)
        return df
    
    def save_to_excel(self, output_file):
        df = self.generate_summary_table()
        df.to_excel(output_file, index=False)
        logger.info(f"统计结果已保存至 {output_file}")
        print(f"统计结果已保存至 {output_file}")

if __name__ == "__main__":
    # 设置输出目录
    output_directory = "c:/Users/yanggyan/TRAE/FreeArk/output/"
    
    # 创建QuantityStatistics实例
    statistics = QuantityStatistics(output_directory)
    
    # 加载所有文件
    logger.info("正在加载所有数据文件...")
    print("正在加载所有数据文件...")
    statistics.load_all_files()
    
    if statistics.data:
        # 只保存为Excel文件，文件名为"用量统计"
        output_file = os.path.join(output_directory, "用量统计.xlsx")
        statistics.save_to_excel(output_file)
        logger.info(f"统计完成! 结果已保存到 {output_file}")
        print("统计完成!")
    else:
        logger.warning("未找到有效数据，请检查输出目录。")
        print("未找到有效数据，请检查输出目录。")