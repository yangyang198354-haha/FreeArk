import os
import sys
import json
import time
import copy
from typing import Dict, Any, List, Optional
import pandas as pd

# 添加FreeArk目录到Python路径，确保模块可以正确导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger

# 导入已有的PLC读取相关类
from datacollection.multi_thread_plc_reader import PLCReader

# 获取logger，日志级别从配置文件读取
logger = get_logger('room_data_collector')

# PLCReader类已从multi_thread_plc_reader.py导入，无需重复定义

class RoomDataCollector:
    """房间数据收集器，根据户号自动获取PLC地址并读取数据"""
    def __init__(self):
        self.resource_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource')
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')
        self.results: Dict[str, Dict[str, Any]] = {}
        
        # 确保output目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        logger.info(f"✅ 房间数据收集器已初始化，资源目录：{self.resource_dir}，输出目录：{self.output_dir}")
    
    def find_room_in_building_files(self, room_number: str) -> Optional[tuple]:
        """在所有楼栋数据文件中查找指定房间"""
        logger.info(f"🔍 开始在楼栋数据文件中查找房间 {room_number}")
        # 遍历所有楼栋数据文件
        for filename in os.listdir(self.resource_dir):
            if filename.endswith('_data.json'):
                file_path = os.path.join(self.resource_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        building_data = json.load(f)
                    
                    # 检查房间是否在当前文件中
                    if room_number in building_data:
                        logger.info(f"✅ 在文件 {filename} 中找到房间 {room_number}")
                        return filename, building_data[room_number]
                    
                    # 检查是否能通过"专有部分坐落"字段匹配
                    for device_id, device_info in building_data.items():
                        if '专有部分坐落' in device_info and room_number in device_info['专有部分坐落']:
                            logger.info(f"✅ 在文件 {filename} 中找到房间 {room_number}（通过专有部分坐落匹配）")
                            return filename, device_info
                except Exception as e:
                    logger.info(f"⚠️  读取文件 {filename} 时出错: {str(e)}")
        
        logger.info(f"❌ 未找到房间 {room_number} 的信息")
        return None
    

    
    def load_plc_config(self) -> Dict[str, Dict[str, Any]]:
        """加载PLC配置文件"""
        config_path = os.path.join(self.resource_dir, 'plc_config.json')
        
        if not os.path.exists(config_path):
            logger.info(f"❌ PLC配置文件不存在: {config_path}")
            return {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 获取parameters字段
            if 'parameters' in config:
                params = config['parameters']
                logger.info(f"✅ 成功加载PLC配置，参数数量: {len(params)}")
                
                # 为每个参数添加默认的length值（如果不存在）
                for param_key, param_info in params.items():
                    if 'length' not in param_info:
                        # 根据数据类型设置默认长度
                        if param_info.get('data_type') in ['int32', 'uint32', 'float']:
                            param_info['length'] = 4
                        else:
                            param_info['length'] = 2  # 默认为16位数据
                
                return params
            else:
                logger.info(f"❌ PLC配置文件中未找到parameters字段")
                return {}
        except Exception as e:
            logger.info(f"❌ 加载PLC配置文件失败: {str(e)}")
            return {}
    
    def get_plc_ip_for_room(self, room_info: Dict[str, Any]) -> Optional[str]:
        """获取房间对应的PLC IP地址"""
        # 优先从房间信息中获取PLC IP地址
        if 'PLC IP地址' in room_info:
            plc_ip = room_info['PLC IP地址']
            logger.info(f"✅ 从房间信息中获取PLC IP地址: {plc_ip}")
            return plc_ip
        
        # 如果没有PLC IP地址，尝试使用设备IP地址
        if 'IP地址' in room_info:
            plc_ip = room_info['IP地址']
            logger.info(f"⚠️  未找到PLC IP地址，使用设备IP地址: {plc_ip}")
            return plc_ip
        
        logger.info("❌ 未找到PLC IP地址或设备IP地址")
        return None
    
    def load_plc_config(self) -> Dict[str, Dict[str, Any]]:
        """加载PLC配置文件"""
        config_path = os.path.join(self.resource_dir, 'plc_config.json')
        if not os.path.exists(config_path):
            logger.info(f"❌ PLC配置文件不存在：{config_path}")
            return {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"✅ 成功加载PLC配置文件，包含{len(config.get('parameters', {}))}个参数")
                return config.get('parameters', {})
        except Exception as e:
            logger.info(f"❌ 加载PLC配置文件失败：{str(e)}")
            return {}
    
    def load_output_config(self) -> Dict[str, Any]:
        """加载输出配置文件"""
        config_path = os.path.join(self.resource_dir, 'output_config.json')
        # 默认配置
        default_config = {
            "output": {
                "type": "Excel",
                "excel": {
                    "file_name": "累计用量",
                    "directory": self.output_dir,
                    "include_all_params": True
                },
                "json": {
                    "enabled": True
                },
                "mqtt": {
                    "enabled": False,
                    "server": {
                        "host": "localhost",
                        "port": 1883,
                        "username": "",
                        "password": "",
                        "tls_enabled": False
                    },
                    "topic": {
                        "prefix": "/datacollection/plc/to/collector/"
                    },
                    "qos": 1,
                    "retain": False
                }
            }
        }
        
        if not os.path.exists(config_path):
            logger.info(f"⚠️  输出配置文件不存在，使用默认配置：{config_path}")
            return default_config
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"✅ 成功加载输出配置文件")
                # 合并默认配置和文件配置
                if 'output' not in config:
                    config['output'] = default_config['output']
                else:
                    if 'excel' not in config['output']:
                        config['output']['excel'] = default_config['output']['excel']
                    else:
                        config['output']['excel'] = {**default_config['output']['excel'], **config['output']['excel']}
                    if 'json' not in config['output']:
                        config['output']['json'] = default_config['output']['json']
                    else:
                        config['output']['json'] = {**default_config['output']['json'], **config['output']['json']}
                    if 'mqtt' not in config['output']:
                        config['output']['mqtt'] = default_config['output']['mqtt']
                    else:
                        # 合并MQTT配置，确保所有必需的子项都存在
                        if 'server' not in config['output']['mqtt']:
                            config['output']['mqtt']['server'] = default_config['output']['mqtt']['server']
                        else:
                            config['output']['mqtt']['server'] = {**default_config['output']['mqtt']['server'], **config['output']['mqtt']['server']}
                        if 'topic' not in config['output']['mqtt']:
                            config['output']['mqtt']['topic'] = default_config['output']['mqtt']['topic']
                        else:
                            config['output']['mqtt']['topic'] = {**default_config['output']['mqtt']['topic'], **config['output']['mqtt']['topic']}
                        # 合并其他MQTT配置项
                        config['output']['mqtt'] = {**default_config['output']['mqtt'], **config['output']['mqtt']}
                return config
        except Exception as e:
            logger.info(f"❌ 加载输出配置文件失败，使用默认配置：{str(e)}")
            return default_config
    
    def read_room_data(self, room_number: str) -> Dict[str, Any]:
        """读取指定房间的数据"""
        logger.info(f"🚀 开始收集房间 {room_number} 的数据")
        start_time = time.time()
        
        # 查找房间信息
        room_info_result = self.find_room_in_building_files(room_number)
        if not room_info_result:
            return {}
        
        filename, room_info = room_info_result
        
        # 获取PLC IP地址
        plc_ip = self.get_plc_ip_for_room(room_info)
        if not plc_ip:
            return {}
        
        # 加载PLC配置
        plc_config = self.load_plc_config()
        if not plc_config:
            return {}
        
        # 连接PLC并读取数据
        reader = PLCReader(plc_ip)
        try:
            if not reader.connect():
                logger.info(f"❌ 无法连接到PLC {plc_ip}")
                return {}
            
            # 读取所有参数
            data_results = {}
            success_count = 0
            total_count = len(plc_config)
            
            for param_key, param_info in plc_config.items():
                db_num = param_info['db_num']
                offset = param_info['offset']
                length = param_info['length']
                data_type = param_info['data_type']
                
                success, message, value = reader.read_db_data(db_num, offset, length, data_type)
                data_results[param_key] = {
                    'success': success,
                    'message': message,
                    'value': value,
                    'description': param_info.get('description', param_key)
                }
                
                if success:
                    success_count += 1
                    logger.info(f"✅ 设备 {room_number} 参数 {param_key} 读取成功，值：{value}")
                else:
                    logger.info(f"❌ 设备 {room_number} 参数 {param_key} 读取失败：{message}")
            
            # 组织结果
            # 获取当前格式化的时间字符串
            current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            
            result = {
                room_number: {
                    **room_info,  # 复制原始设备信息
                    'data': data_results,
                    'status': 'success' if success_count == total_count else 'partial_success' if success_count > 0 else 'failed',
                    'success_count': success_count,
                    'total_count': total_count,
                    'timestamp': current_time_str
                }
            }
            
            elapsed_time = time.time() - start_time
            logger.info(f"⏱️  房间 {room_number} 数据收集完成，耗时：{elapsed_time:.2f} 秒，成功 {success_count}/{total_count} 个参数")
            
            # 保存结果
            self.results[room_number] = result
            
            # 调用save_results方法保存结果
            self.save_results(room_number)
            
            return result
        finally:
            reader.disconnect()
    
    def save_results(self, room_number: str) -> None:
        """保存结果到文件"""
        if room_number not in self.results:
            logger.info(f"❌ 没有找到房间 {room_number} 的结果数据")
            return
        
        # 获取输出配置
        output_config = self.load_output_config()
        
        # 获取各种输出方式的enabled配置
        json_config = output_config['output'].get('json', {})
        json_enabled = json_config.get('enabled', True)
        
        excel_config = output_config['output'].get('excel', {})
        excel_enabled = excel_config.get('enabled', True)
        
        # 根据配置保存结果
        if json_enabled:
            self.save_results_to_json(room_number)
        
        if excel_enabled:
            self.save_results_to_excel(room_number)
    
    def save_results_to_json(self, room_number: str) -> bool:
        """保存结果到JSON文件"""
        # 获取输出配置
        output_config = self.load_output_config()
        json_config = output_config['output'].get('json', {})
        json_enabled = json_config.get('enabled', True)
        
        # 检查JSON输出是否启用
        if not json_enabled:
            logger.info(f"⚠️  JSON输出未启用")
            return False
            
        if room_number not in self.results:
            logger.info(f"❌ 没有找到房间 {room_number} 的结果数据")
            return False
        
        # 确定输出文件名
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        output_file = f"room_{room_number.replace('-', '_')}_data_collected_{timestamp}.json"
        
        # 保存到output目录
        output_path = os.path.join(self.output_dir, output_file)
        
        try:
            # 深拷贝结果数据，避免修改原始数据
            results_copy = copy.deepcopy(self.results[room_number])
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results_copy, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 结果已保存到JSON文件：{output_path}")
            return True
        except Exception as e:
            logger.info(f"❌ 保存JSON文件失败：{str(e)}")
            return False
    
    def save_results_to_excel(self, room_number: str) -> bool:
        """保存结果到Excel文件"""
        # 获取输出配置
        output_config = self.load_output_config()
        excel_config = output_config['output'].get('excel', {})
        excel_enabled = excel_config.get('enabled', True)
        
        # 检查Excel输出是否启用
        if not excel_enabled:
            logger.info(f"⚠️  Excel输出未启用")
            return False
        
        try:
            # 尝试导入pandas，如果没有安装则使用简单的CSV格式
            import pandas as pd
            
            if room_number not in self.results:
                logger.info(f"❌ 没有找到房间 {room_number} 的结果数据")
                return False
            
            # 获取输出配置
            file_name = excel_config.get('file_name', '累计用量')
            directory = excel_config.get('directory', self.output_dir)
            
            # 确保输出目录存在
            if not os.path.exists(directory):
                os.makedirs(directory)
            
            # 生成文件名，包含时间戳
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            output_file = f"{file_name}_{timestamp}.xlsx"
            output_path = os.path.join(directory, output_file)
            
            # 准备数据
            result = self.results[room_number]
            room_info = result[room_number]
            data_results = room_info.get('data', {})
            
            # 创建Excel数据
            rows = []
            for param_key, param_data in data_results.items():
                row = {
                    '房间号': room_number,
                    '参数名称': param_data.get('description', param_key),
                    '参数键名': param_key,
                    '数值': param_data.get('value'),
                    '状态': '成功' if param_data.get('success') else '失败',
                    '消息': param_data.get('message'),
                    '收集时间': room_info.get('timestamp')
                }
                # 添加基本信息（排除data字段）
                for key, value in room_info.items():
                    if key != 'data' and key not in row:
                        row[key] = value
                rows.append(row)
            
            # 创建DataFrame并保存
            df = pd.DataFrame(rows)
            df.to_excel(output_path, index=False)
            
            logger.info(f"✅ 结果已保存到Excel文件：{output_path}")
            return True
        except ImportError:
            # 如果pandas没有安装，使用简单的CSV格式
            logger.info("⚠️  pandas库未安装，使用CSV格式保存结果")
            output_file = f"room_{room_number.replace('-', '_')}_data_collected_{timestamp}.csv"
            output_path = os.path.join(self.output_dir, output_file)
            
            try:
                result = self.results[room_number]
                room_info = result[room_number]
                data_results = room_info.get('data', {})
                
                # 写入CSV文件
                with open(output_path, 'w', encoding='utf-8', newline='') as f:
                    # 写入标题行
                    headers = ['房间号', '参数名称', '参数键名', '数值', '状态', '消息', '收集时间']
                    # 添加基本信息标题（排除data字段）
                    for key in room_info:
                        if key != 'data' and key not in headers:
                            headers.append(key)
                    f.write(','.join(f'"{h}"' for h in headers) + '\n')
                    
                    # 写入数据行
                    for param_key, param_data in data_results.items():
                        row = {
                            '房间号': room_number,
                            '参数名称': param_data.get('description', param_key),
                            '参数键名': param_key,
                            '数值': param_data.get('value'),
                            '状态': '成功' if param_data.get('success') else '失败',
                            '消息': param_data.get('message'),
                            '收集时间': room_info.get('timestamp')
                        }
                        # 添加基本信息
                        for key, value in room_info.items():
                            if key != 'data' and key not in row:
                                row[key] = value
                        
                        # 写入行数据
                        values = [str(row.get(h, '')) for h in headers]
                        f.write(','.join(f'"{v}"' for v in values) + '\n')
                
                logger.info(f"✅ 结果已保存到CSV文件：{output_path}")
                return True
            except Exception as e:
                logger.info(f"❌ 保存CSV文件失败：{str(e)}")
            return False
        except Exception as e:
            logger.info(f"❌ 保存Excel文件失败：{str(e)}")
            return False
    
    def save_results(self, room_number: str) -> bool:
        """根据配置保存结果"""
        logger.info(f"💾 开始保存房间 {room_number} 的收集结果")
        
        # 获取输出配置
        output_config = self.load_output_config()
        
        success = True
        
        # 保存到JSON
        if output_config['output'].get('json', {}).get('enabled', True):
            json_success = self.save_results_to_json(room_number)
            success = success and json_success
        
        # 保存到Excel
        if output_config['output'].get('excel', {}).get('enabled', True):
            excel_success = self.save_results_to_excel(room_number)
            success = success and excel_success
        
        # 发送到MQTT（如果启用）
        mqtt_config = output_config['output'].get('mqtt', {})
        if mqtt_config.get('enabled', False):
            # MQTT发送暂不实现，仅记录日志
            logger.info(f"⚠️  MQTT输出已启用，但功能暂未实现")
        
        if success:
            logger.info(f"✅ 房间 {room_number} 的所有结果已成功保存")
        else:
            logger.info(f"❌ 房间 {room_number} 的部分结果保存失败")
        
        return success

if __name__ == "__main__":
    # 示例用法：根据户号收集数据
    import sys
    
    if len(sys.argv) > 1:
        room_number = sys.argv[1]
    else:
        # 默认使用示例房间号
        room_number = "3-1-7-702"
        logger.info(f"⚠️  未提供房间号参数，使用默认房间号：{room_number}")
    
    collector = RoomDataCollector()
    result = collector.read_room_data(room_number)
    
    if result:
        logger.info(f"✅ 房间 {room_number} 数据收集成功！")
    else:
        logger.info(f"❌ 房间 {room_number} 数据收集失败！")