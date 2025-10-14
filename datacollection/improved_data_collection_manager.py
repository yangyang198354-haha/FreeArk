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
    logger = logging.getLogger('improved_data_collection')
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
        log_filename = f"improved_data_collection_{time.strftime('%Y%m%d')}.log"
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

class ImprovedDataCollectionManager:
    def __init__(self, max_workers: int = 10):
        """初始化改进的数据收集管理器"""
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
        logger.info(f"✅ 改进版数据收集管理器已启动，线程池大小：{self.max_workers}")

    def stop(self):
        """停止数据收集管理器"""
        self.plc_manager.stop()
        logger.info("✅ 改进版数据收集管理器已停止")

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

    def load_room_plc_map(self) -> Dict[str, str]:
        """加载房间与PLC IP的映射关系"""
        map_path = os.path.join(self.resource_dir, 'room_plc_map.json')
        if not os.path.exists(map_path):
            logger.info(f"❌ 房间与PLC IP映射文件不存在：{map_path}")
            return {}
        
        try:
            with open(map_path, 'r', encoding='utf-8') as f:
                room_plc_map = json.load(f)
                logger.info(f"✅ 成功加载房间与PLC IP映射文件，共{len(room_plc_map)}条映射关系")
                return room_plc_map
        except Exception as e:
            logger.info(f"❌ 加载房间与PLC IP映射文件失败：{str(e)}")
            return {}

    def collect_data_for_building(self, building_file: str) -> Dict[str, Dict[str, Any]]:
        """为指定楼栋收集数据，使用PLC IP地址而不是设备IP地址"""
        # 加载楼栋数据和PLC配置
        building_data = self.load_building_json(building_file)
        if not building_data:
            return {}
        
        plc_config = self.load_plc_config()
        if not plc_config:
            return {}
        
        # 加载房间与PLC IP映射关系
        room_plc_map = self.load_room_plc_map()
        
        # 创建PLC读取配置列表
        plc_read_configs = []
        ip_to_device_map = {}
        
        # 为每个设备的每个参数创建读取配置
        for device_id, device_info in building_data.items():
            # 优先使用设备信息中的PLC IP地址
            plc_ip = device_info.get('PLC IP地址')
            
            # 如果设备信息中没有PLC IP，尝试从映射文件中获取
            if not plc_ip and room_plc_map:
                # 从device_id提取房间号（格式：X-X-X-XXX 或 X-X-XXX）
                room_number = device_id.replace('-', '')[-7:].replace('-', '')  # 提取最后7位数字作为房间标识
                # 尝试精确匹配或模糊匹配
                for key in room_plc_map:
                    if room_number in key.replace('-', ''):
                        plc_ip = room_plc_map[key]
                        logger.info(f"🔍 为设备 {device_id} 从映射文件中找到PLC IP: {plc_ip}")
                        break
            
            if not plc_ip:
                # 如果仍然没有PLC IP，使用设备的IP地址作为后备方案
                plc_ip = device_info.get('IP地址')
                if not plc_ip:
                    logger.info(f"⚠️  设备 {device_id} 没有可用的IP地址")
                    continue
                logger.info(f"⚠️  设备 {device_id} 没有PLC IP，使用设备IP: {plc_ip}")
            
            # 为每个参数创建配置
            for param_key, param_info in plc_config.items():
                config = {
                    'ip': plc_ip,
                    'db_num': param_info.get('db_num'),
                    'offset': param_info.get('offset'),
                    'length': param_info.get('length'),
                    'data_type': param_info.get('data_type'),
                    'device_id': device_id,
                    'param_key': param_key,
                    'original_device_ip': device_info.get('IP地址')
                }
                plc_read_configs.append(config)
                
                # 记录PLC IP到设备的映射
                if plc_ip not in ip_to_device_map:
                    ip_to_device_map[plc_ip] = []
                ip_to_device_map[plc_ip].append(device_id)
        
        logger.info(f"🚀 开始为楼栋 {building_file} 收集数据，共{len(plc_read_configs)}个读取任务，涉及{len(ip_to_device_map)}个PLC设备...")
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
        # 按PLC IP地址对参数配置进行分组
        ip_to_configs = {}
        for config in plc_read_configs:
            plc_ip = config['ip']
            if plc_ip not in ip_to_configs:
                ip_to_configs[plc_ip] = []
            ip_to_configs[plc_ip].append(config)
        
        # 提交所有任务到线程池（每个IP一个任务）
        future_to_ip = {}
        for plc_ip, configs in ip_to_configs.items():
            future = self.plc_manager.thread_pool.submit(self._read_single_plc_with_multiple_params, plc_ip, configs)
            future_to_ip[future] = plc_ip
        
        # 收集结果
        results = []
        for future in concurrent.futures.as_completed(future_to_ip):
            plc_ip = future_to_ip[future]
            try:
                ip_results = future.result()
                results.extend(ip_results)
            except Exception as e:
                logger.info(f"❌ PLC任务执行异常：{plc_ip} - {str(e)}")
                # 为该IP下的所有配置添加失败结果
                for config in ip_to_configs.get(plc_ip, []):
                    results.append({
                        'ip': config['ip'],
                        'device_id': config.get('device_id'),
                        'param_key': config.get('param_key'),
                        'success': False,
                        'message': f"任务执行异常：{str(e)}",
                        'value': None
                    })
        
        return results
    
    def _read_single_plc_with_multiple_params(self, plc_ip: str, configs: List[Dict]) -> List[Dict]:
        """读取单个PLC的多个参数"""
        results = []
        
        # 创建一个PLC读取器并连接
        reader = PLCReader(plc_ip)
        try:
            if not reader.connect():
                # 只连接PLC IP，如果失败直接标记为失败
                logger.info(f"❌ PLC IP连接失败: {plc_ip}")
                for config in configs:
                    results.append({
                        'ip': plc_ip,
                        'device_id': config.get('device_id'),
                        'param_key': config.get('param_key'),
                        'success': False,
                        'message': "PLC IP连接失败",
                        'value': None
                    })
                return results
            
            # 依次读取每个参数
            for config in configs:
                db_num = config['db_num']
                offset = config['offset']
                length = config['length']
                data_type = config['data_type']
                device_id = config.get('device_id')
                param_key = config.get('param_key')
                
                # 读取数据
                success, message, value = reader.read_db_data(db_num, offset, length, data_type)
                results.append({
                    'ip': plc_ip,
                    'device_id': device_id,
                    'param_key': param_key,
                    'success': success,
                    'message': message,
                    'value': value
                })
            
            return results
        finally:
            # 确保断开连接
            reader.disconnect()
    
    # 原有的_read_single_plc_with_param方法可以保留或删除，根据是否有其他地方调用决定
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
                # 只连接PLC IP，如果失败直接标记为失败
                logger.info(f"❌ PLC IP连接失败: {plc_ip}")
                return {
                    'ip': plc_ip,
                    'device_id': device_id,
                    'param_key': param_key,
                    'success': False,
                    'message': "PLC IP连接失败",
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
            output_file = f"{base_name}_improved_data_collected_{timestamp}.json"
        
        # 保存到output目录
        output_path = os.path.join(self.output_dir, output_file)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.results[building_file], f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 改进版结果已保存到：{output_path}")
            return True
        except Exception as e:
            logger.info(f"❌ 保存改进版结果失败：{str(e)}")
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
    manager = ImprovedDataCollectionManager(max_workers=10)
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
                logger.info(f"  PLC IP: {device_data.get('PLC IP地址', 'N/A')}")
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