import os
import json
import time
from typing import Dict, List, Any
import concurrent.futures
import logging

# 导入已有的PLC读取相关类
from multi_thread_plc_reader import PLCReader, PLCManager

# 配置日志
def setup_logger():
    # 创建logger对象
    logger = logging.getLogger('data_collection')
    logger.setLevel(logging.INFO)
    
    # 检查是否已经存在处理器，避免重复添加
    if not logger.handlers:
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 创建文件处理器，日志存储在log目录下
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'log')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 为日志文件添加日期
        log_filename = f"data_collection_{time.strftime('%Y%m%d')}.log"
        log_path = os.path.join(log_dir, log_filename)
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # 添加处理器到logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    
    return logger

# 初始化日志记录器
logger = setup_logger()

class DataCollectionManager:
    def __init__(self, max_workers: int = 10):
        """初始化数据收集管理器"""
        self.max_workers = max_workers
        self.plc_manager = PLCManager(max_workers=max_workers)
        self.resource_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource')
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')
        # 确保output目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self.results = {}

    def start(self):
        """启动数据收集管理器"""
        self.plc_manager.start()
        logger.info(f"✅ 数据收集管理器已启动，线程池大小：{self.max_workers}")

    def stop(self):
        """停止数据收集管理器"""
        self.plc_manager.stop()
        logger.info("✅ 数据收集管理器已停止")

    def load_building_json(self, building_file: str) -> Dict[str, Dict[str, Any]]:
        """加载楼栋的JSON文件"""
        file_path = os.path.join(self.resource_dir, building_file)
        if not os.path.exists(file_path):
            logger.info(f"❌ 楼栋JSON文件不存在：{file_path}")
            return {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ 成功加载楼栋JSON文件：{building_file}，共{len(data)}条记录")
                return data
        except Exception as e:
            logger.info(f"❌ 加载楼栋JSON文件失败：{str(e)}")
            return {}

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

    def collect_data_for_building(self, building_file: str) -> Dict[str, Dict[str, Any]]:
        """为指定楼栋收集数据"""
        # 加载楼栋数据和PLC配置
        building_data = self.load_building_json(building_file)
        if not building_data:
            return {}
        
        plc_config = self.load_plc_config()
        if not plc_config:
            return {}
        
        # 创建PLC读取配置列表
        plc_read_configs = []
        ip_to_device_map = {}
        
        # 为每个设备的每个参数创建读取配置
        for device_id, device_info in building_data.items():
            ip = device_info.get('IP地址')
            if not ip:
                continue
            
            # 为每个参数创建配置
            for param_key, param_info in plc_config.items():
                config = {
                    'ip': ip,
                    'db_num': param_info.get('db_num'),
                    'offset': param_info.get('offset'),
                    'length': param_info.get('length'),
                    'data_type': param_info.get('data_type'),
                    'device_id': device_id,
                    'param_key': param_key
                }
                plc_read_configs.append(config)
                
                # 记录IP到设备的映射
                if ip not in ip_to_device_map:
                    ip_to_device_map[ip] = device_id
        
        logger.info(f"🚀 开始为楼栋 {building_file} 收集数据，共{len(plc_read_configs)}个读取任务...")
        start_time = time.time()
        
        # 读取所有PLC数据
        results = self._read_all_plc_data(plc_read_configs)
        
        # 组织结果
        organized_results = self._organize_results(results, building_data, plc_config)
        
        elapsed_time = time.time() - start_time
        logger.info(f"⏱️  数据收集完成，耗时：{elapsed_time:.2f} 秒")
        
        # 保存结果
        self.results[building_file] = organized_results
        
        # 调用save_results_to_json保存结果到output目录
        self.save_results_to_json(building_file)
        
        return organized_results

    def _read_all_plc_data(self, plc_read_configs: List[Dict]) -> List[Dict]:
        """读取所有PLC数据"""
        # 提交所有任务到线程池
        future_to_config = {}
        for config in plc_read_configs:
            future = self.plc_manager.thread_pool.submit(self._read_single_plc_with_param, config)
            future_to_config[future] = config
        
        # 收集结果
        results = []
        for future in concurrent.futures.as_completed(future_to_config):
            config = future_to_config[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.info(f"❌ PLC任务执行异常：{config['ip']} - {config['param_key']} - {str(e)}")
                results.append({
                    'ip': config['ip'],
                    'device_id': config.get('device_id'),
                    'param_key': config.get('param_key'),
                    'success': False,
                    'message': f"任务执行异常：{str(e)}",
                    'value': None
                })
        
        return results

    def _read_single_plc_with_param(self, config: Dict) -> Dict:
        """读取单个PLC的单个参数"""
        plc_ip = config['ip']
        db_num = config['db_num']
        offset = config['offset']
        length = config['length']
        data_type = config['data_type']
        device_id = config.get('device_id')
        param_key = config.get('param_key')
        
        # 创建PLC读取器并连接
        reader = PLCReader(plc_ip)
        try:
            if not reader.connect():
                return {
                    'ip': plc_ip,
                    'device_id': device_id,
                    'param_key': param_key,
                    'success': False,
                    'message': "PLC连接失败",
                    'value': None
                }
            
            # 读取数据
            success, message, value = reader.read_db_data(db_num, offset, length, data_type)
            return {
                'ip': plc_ip,
                'device_id': device_id,
                'param_key': param_key,
                'success': success,
                'message': message,
                'value': value
            }
        finally:
            # 确保断开连接
            reader.disconnect()

    def _organize_results(self, results: List[Dict], building_data: Dict, plc_config: Dict) -> Dict[str, Dict[str, Any]]:
        """组织结果数据"""
        organized_results = {}
        success_count = 0
        total_count = len(results)
        
        # 初始化所有设备的结果
        for device_id, device_info in building_data.items():
            organized_results[device_id] = {
                **device_info,  # 复制原始设备信息
                'data': {},  # 添加数据字段
                'status': 'pending'  # 初始状态
            }
        
        # 处理每个结果
        for result in results:
            device_id = result.get('device_id')
            param_key = result.get('param_key')
            
            if device_id and device_id in organized_results and param_key:
                # 存储参数结果
                organized_results[device_id]['data'][param_key] = {
                    'value': result.get('value'),
                    'success': result.get('success'),
                    'message': result.get('message')
                }
                
                # 更新设备状态
                if result.get('success'):
                    organized_results[device_id]['status'] = 'success'
                    success_count += 1
                else:
                    organized_results[device_id]['status'] = 'partial_success' if organized_results[device_id]['status'] == 'success' else 'failed'
        
        logger.info(f"📊 数据收集结果统计：成功 {success_count}/{total_count} 个参数读取任务")
        
        return organized_results

    def save_results_to_json(self, building_file: str, output_file: str = None) -> bool:
        """保存结果到JSON文件"""
        if building_file not in self.results:
            logger.info(f"❌ 没有找到楼栋 {building_file} 的结果数据")
            return False
        
        # 确定输出文件名
        if not output_file:
            base_name = os.path.splitext(building_file)[0]
            # 添加时间戳信息，格式为：YYYYMMDD_HHMMSS
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            output_file = f"{base_name}_data_collected_{timestamp}.json"
        
        # 保存到output目录
        output_path = os.path.join(self.output_dir, output_file)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.results[building_file], f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 结果已保存到：{output_path}")
            return True
        except Exception as e:
            logger.info(f"❌ 保存结果失败：{str(e)}")
            return False

    def collect_data_for_all_buildings(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """为所有楼栋收集数据"""
        # 获取所有楼栋JSON文件
        building_files = []
        for file in os.listdir(self.resource_dir):
            if file.endswith('_data_keyvalue.json'):
                building_files.append(file)
        
        logger.info(f"🚀 开始为所有楼栋收集数据，共{len(building_files)}个楼栋")
        
        # 为每个楼栋收集数据
        all_results = {}
        for building_file in building_files:
            logger.info(f"\n🔄 处理楼栋：{building_file}")
            building_results = self.collect_data_for_building(building_file)
            if building_results:
                all_results[building_file] = building_results
                # collect_data_for_building方法内部已经调用了save_results_to_json
                # 此处不再重复调用
        
        logger.info(f"\n✅ 所有楼栋数据收集完成，共处理{len(all_results)}/{len(building_files)}个楼栋")
        
        return all_results

# 示例用法
if __name__ == "__main__":
    # 创建数据收集管理器，设置线程池大小
    manager = DataCollectionManager(max_workers=10)
    manager.start()
    
    try:
        # 使用测试文件进行数据收集
        building_file = '3#_data_keyvalue_test.json'
        logger.info(f"🔍 开始测试数据收集：使用测试文件 {building_file}")
        results = manager.collect_data_for_building(building_file)
        
        if results:
            logger.info("📋 收集到的数据:")
            for device_id, device_data in results.items():
                logger.info(f"  设备ID: {device_id}")
                logger.info(f"  基本信息: {device_data['专有部分坐落']}, IP: {device_data['IP地址']}")
                logger.info(f"  收集状态: {device_data['status']}")
                logger.info(f"  数据内容: {device_data['data']}")
                logger.info("  ----------")
        
    except KeyboardInterrupt:
        logger.info("\n✅ 用户手动终止程序")
    except Exception as e:
        logger.info(f"\n❌ 程序异常：{str(e)}")
    finally:
        # 确保停止线程池
        manager.stop()