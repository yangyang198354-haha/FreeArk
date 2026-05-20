import os
import sys
import json
import time
from typing import Dict, List, Any, Optional
import concurrent.futures

# 处理PyInstaller打包后的资源文件路径
def get_resource_path(relative_path):
    """获取资源文件的绝对路径，支持PyInstaller打包环境"""
    try:
        # PyInstaller打包后的临时目录
        base_path = sys._MEIPASS
    except Exception:
        # 正常开发环境
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_path, relative_path)

# 添加FreeArk目录到Python路径，确保模块可以正确导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 尝试导入snap7模块，如果不存在则记录警告
SNAP7_AVAILABLE = False
try:
    import snap7
    SNAP7_AVAILABLE = True
except ImportError:
    # 模块不存在，记录警告
    pass

# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger

# 获取logger，日志级别从配置文件读取
logger = get_logger('plc_write_manager')

# 如果snap7模块不可用，记录警告
if not SNAP7_AVAILABLE:
    logger.warning("❌ snap7模块未找到，PLC读取功能将不可用")

# 导入PLC读取相关类（用于写入功能）
from datacollection.multi_thread_plc_handler import PLCReadWriter, PLCManager

class PLCWriteManager:
    # 运行模式常量定义（v0.5.1: 新增 MODE_DEHUMIDIFICATION，REQ-FUNC-001）
    MODE_COOLING = 1        # 制冷模式
    MODE_HEATING = 2        # 制热模式
    MODE_VENTILATION = 3    # 通风模式
    MODE_DEHUMIDIFICATION = 4  # 除湿模式（v0.5.1）
    
    def _get_resource_dir(self):
        """获取资源目录，支持多种运行环境"""
        # 尝试从多个位置获取资源目录
        possible_dirs = [
            os.path.join(os.getcwd(), 'resource'),  # 当前工作目录下的resource
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource'),  # 项目resource目录
        ]
        
        # 优先选择存在的目录
        for dir_path in possible_dirs:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                return dir_path
        
        # 如果都不存在，返回当前工作目录
        return os.getcwd()
    
    def __init__(self, max_workers: int = 10):
        """初始化PLC写入管理器"""
        self.max_workers = max_workers
        self.plc_manager = PLCManager(max_workers=max_workers)
        # 使用辅助方法获取资源目录
        self.resource_dir = self._get_resource_dir()
        self.write_results = {}
    
    def start(self):
        """启动PLC写入管理器"""
        self.plc_manager.start()
        logger.info(f"✅ PLC写入管理器已启动，线程池大小：{self.max_workers}")
    
    def stop(self):
        """停止PLC写入管理器"""
        self.plc_manager.stop()
        logger.info("✅ PLC写入管理器已停止")
    
    def load_building_json(self, building_file: str) -> Dict[str, Dict[str, Any]]:
        """加载楼栋的JSON文件"""
        # 尝试多种路径
        possible_paths = [
            os.path.join(self.resource_dir, building_file),  # 资源目录
            get_resource_path(building_file),  # 使用通用路径函数
            get_resource_path(os.path.join('resource', building_file)),  # resource子目录
            building_file  # 直接使用传入的路径
        ]
        
        # 尝试从可能的路径加载文件
        for file_path in possible_paths:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        logger.info(f"✅ 成功加载楼栋JSON文件：{building_file}，共{len(data)}条记录")
                        return data
                except Exception as e:
                    logger.info(f"❌ 从{file_path}加载楼栋JSON文件失败：{str(e)}")
                    continue
        
        logger.info(f"❌ 未找到楼栋JSON文件：{building_file}")
        return {}
    
    def load_plc_mode_update_config(self) -> Dict[str, Dict[str, Any]]:
        """加载PLC模式更新配置文件"""
        # 尝试多种路径
        possible_paths = [
            os.path.join(self.resource_dir, 'plc_mode_update_config.json'),  # 资源目录
            get_resource_path('plc_mode_update_config.json'),  # 使用通用路径函数
            get_resource_path(os.path.join('resource', 'plc_mode_update_config.json')),  # resource子目录
            os.path.join(os.getcwd(), 'plc_mode_update_config.json')  # 当前工作目录
        ]
        
        # 尝试从可能的路径加载文件
        for config_path in possible_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        logger.info(f"✅ 成功加载PLC模式更新配置文件，包含{len(config.get('parameters', {}))}个参数")
                        return config.get('parameters', {})
                except Exception as e:
                    logger.info(f"❌ 从{config_path}加载PLC模式更新配置文件失败：{str(e)}")
                    continue
        
        logger.info(f"❌ 未找到PLC模式更新配置文件")
        return {}
    
    def write_mode_for_building(self, building_file: str, mode: int) -> Dict[str, Dict[str, Any]]:
        """为指定楼栋的所有PLC写入运行模式（仅写 operation_mode，DB14 offset=89）

        v0.5.1: operation_mode 与 central_energy_supply 写入已解耦（REQ-FUNC-004）。
        本方法仅写 operation_mode，不再联动写 central_energy_supply。

        Args:
            building_file: 楼栋JSON文件名
            mode: 运行模式，1=制冷，2=制热，3=通风，4=除湿（v0.5.1 新增）

        Returns:
            写入结果字典
        """
        # v0.5.1: 有效值扩展为 [1,2,3,4]（REQ-FUNC-001）
        if mode not in [self.MODE_COOLING, self.MODE_HEATING, self.MODE_VENTILATION, self.MODE_DEHUMIDIFICATION]:
            logger.error(f"❌ 无效的模式值：{mode}，必须是1(制冷)、2(制热)、3(通风)或4(除湿)")
            return {}
        
        # 加载楼栋数据和PLC模式配置
        building_data = self.load_building_json(building_file)
        if not building_data:
            return {}
        
        plc_mode_config = self.load_plc_mode_update_config()
        if not plc_mode_config:
            return {}
        
        # 创建PLC写入配置列表
        plc_write_configs = []
        ip_to_device_map = {}
        
        # 为每个设备创建写入配置
        for device_id, device_info in building_data.items():
                # 优先使用设备信息中的PLC IP地址
                plc_ip = device_info.get('PLC IP地址')
                
                if not plc_ip:
                    # 如果仍然没有PLC IP，使用设备的IP地址作为后备方案
                    plc_ip = device_info.get('IP地址')
                    if not plc_ip:
                        logger.info(f"⚠️  设备 {device_id} 没有可用的IP地址")
                        continue
                    logger.info(f"⚠️  设备 {device_id} 没有PLC IP，使用设备IP: {plc_ip}")
                
                # v0.5.1: 仅写 operation_mode，跳过 central_energy_supply（REQ-FUNC-004 写入解耦）
                for param_name, param_config in plc_mode_config.items():
                    if param_name == 'central_energy_supply':
                        # central_energy_supply 独立写入，不随 operation_mode 联动
                        continue
                    value = mode

                    config = {
                        'ip': plc_ip,
                        'db_num': param_config.get('db_num'),
                        'offset': param_config.get('offset'),
                        'data_type': param_config.get('data_type'),
                        'value': value,
                        'device_id': device_id,
                        'param_name': param_name
                    }
                    plc_write_configs.append(config)
                
                # 记录PLC IP到设备的映射
                if plc_ip not in ip_to_device_map:
                    ip_to_device_map[plc_ip] = []
                ip_to_device_map[plc_ip].append(device_id)
        
        # 获取模式名称（v0.5.1: 含除湿）
        mode_names = {
            self.MODE_COOLING: "制冷",
            self.MODE_HEATING: "制热",
            self.MODE_VENTILATION: "通风",
            self.MODE_DEHUMIDIFICATION: "除湿",
        }
        mode_name = mode_names.get(mode, "未知模式")
        
        logger.info(f"🚀 开始为楼栋 {building_file} 写入{mode_name}模式，共{len(plc_write_configs)}个写入任务，涉及{len(ip_to_device_map)}个PLC设备...")
        start_time = time.time()
        
        # 写入所有PLC数据
        results = self._write_all_plc_data(plc_write_configs)
        
        # 组织结果
        organized_results = self._organize_write_results(results, building_data)
        
        elapsed_time = time.time() - start_time
        # 统计成功和失败的参数
        success_count = 0
        total_count = 0
        for device_info in organized_results.values():
            for result in device_info.get('results', {}).values():
                total_count += 1
                if result.get('success', False):
                    success_count += 1
        
        logger.info(f"⏱️  模式写入完成，耗时：{elapsed_time:.2f} 秒，成功: {success_count}/{total_count}")
        
        # 保存结果
        self.write_results[building_file] = organized_results
        
        return organized_results
    
    def _write_all_plc_data(self, plc_write_configs: List[Dict]) -> List[Dict]:
        """写入所有PLC数据"""
        # 按PLC IP地址对参数配置进行分组
        ip_to_configs = {}
        for config in plc_write_configs:
            plc_ip = config['ip']
            if plc_ip not in ip_to_configs:
                ip_to_configs[plc_ip] = []
            ip_to_configs[plc_ip].append(config)
        
        # 提交所有任务到线程池（每个IP一个任务）
        future_to_ip = {}
        for plc_ip, configs in ip_to_configs.items():
            # 直接传递plc_ip和configs参数，value从config中获取
            future = self.plc_manager.thread_pool.submit(self._write_single_plc_with_mode, plc_ip, configs)
            future_to_ip[future] = plc_ip
        
        # 收集结果
        results = []
        for future in concurrent.futures.as_completed(future_to_ip):
            plc_ip = future_to_ip[future]
            try:
                ip_results = future.result()
                results.extend(ip_results)
            except Exception as e:
                logger.error(f"❌ PLC写入任务执行异常：{plc_ip} - {str(e)}")
                # 为该IP下的所有配置添加失败结果
                for config in ip_to_configs.get(plc_ip, []):
                    results.append({
                        'ip': config['ip'],
                        'device_id': config.get('device_id'),
                        'success': False,
                        'message': f"任务执行异常：{str(e)}"
                    })
        
        return results
    
    def _write_single_plc_with_mode(self, plc_ip: str, configs: List[Dict]) -> List[Dict]:
        """为单个PLC写入模式参数
        
        Args:
            plc_ip: PLC的IP地址
            configs: PLC配置字典列表，每个字典包含db_num、offset、data_type和value信息
            
        Returns:
            写入结果列表
        """
        results = []
        
        # 创建一个PLC读取器并连接（用于写入）
        reader = PLCReadWriter(plc_ip)
        try:
            if not reader.connect():
                # 连接失败，为所有配置添加失败结果
                logger.error(f"❌ PLC IP连接失败: {plc_ip}")
                for config in configs:
                    results.append({
                        'ip': plc_ip,
                        'device_id': config.get('device_id'),
                        'value': config.get('value'),
                        'success': False,
                        'message': "PLC IP连接失败",
                        'param_name': config.get('param_name', 'mode')
                    })
                return results
            
            # 依次写入每个参数
            for config in configs:
                db_num = config['db_num']
                offset = config['offset']
                data_type = config['data_type']
                value = config['value']  # 直接从config中获取value
                device_id = config.get('device_id')
                param_name = config.get('param_name', 'mode')  # 获取参数名
                
                # 写入数据
                success, message = reader.write_db_data(db_num, offset, value, data_type)
                result = {
                    'ip': plc_ip,
                    'device_id': device_id,
                    'success': success,
                    'message': message,
                    'value': value,
                    'param_name': param_name  # 确保结果中包含参数名
                }
                results.append(result)
                
                # 记录详细日志
                if success:
                    logger.info(f"✅ 成功写入PLC参数: IP={plc_ip}, DB={db_num}, 偏移量={offset}, 参数={param_name}, 值={value}, 设备ID={device_id}")
                else:
                    logger.error(f"❌ 写入PLC参数失败: IP={plc_ip}, DB={db_num}, 偏移量={offset}, 参数={param_name}, 设备ID={device_id}, 原因: {message}")
            
            return results
        finally:
            # 确保断开连接
            reader.disconnect()
    
    def _organize_write_results(self, results: List[Dict], building_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """组织写入结果"""
        organized = {}
        
        # 按设备ID组织结果
        for result in results:
            device_id = result.get('device_id')
            if device_id and device_id in building_data:
                if device_id not in organized:
                    organized[device_id] = {
                        'device_info': building_data[device_id],
                        'results': {}
                    }
                
                # 按参数名组织结果
                param_name = result.get('param_name', 'mode')
                organized[device_id]['results'][param_name] = result
        
        return organized
    
    def get_mode_name(self, mode_value: int) -> str:
        """获取模式的中文名称（v0.5.1: 含除湿）"""
        mode_names = {
            self.MODE_COOLING: "制冷",
            self.MODE_HEATING: "制热",
            self.MODE_VENTILATION: "通风",
            self.MODE_DEHUMIDIFICATION: "除湿",
        }
        return mode_names.get(mode_value, f"未知模式({mode_value})")
    
    def print_write_summary(self, building_file: str):
        """打印写入结果摘要"""
        if building_file not in self.write_results:
            logger.info(f"❌ 未找到楼栋 {building_file} 的写入结果")
            return
        
        results = self.write_results[building_file]
        total_devices = len(results)
        total_params = 0
        success_count = 0
        
        # 统计成功和失败的参数
        for device_id, device_info in results.items():
            for param_name, result in device_info.get('results', {}).items():
                total_params += 1
                if result.get('success', False):
                    success_count += 1
        
        logger.info(f"📊 楼栋 {building_file} 写入结果摘要")
        logger.info(f"🔢 总设备数: {total_devices}")
        logger.info(f"📝 总参数数: {total_params}")
        logger.info(f"✅ 成功写入: {success_count}")
        logger.info(f"❌ 写入失败: {total_params - success_count}")
        
        # 打印失败的设备信息
        for device_id, device_info in results.items():
            failed_params = [param_name for param_name, result in device_info.get('results', {}).items() 
                           if not result.get('success', False)]
            
            if failed_params:
                logger.info(f"📝 设备 {device_id} 写入失败的参数:")
                for param_name in failed_params:
                    result = device_info['results'][param_name]
                    message = result.get('message', '未知错误')
                    logger.info(f"   - 参数: {param_name}, 原因: {message}")

# 示例用法
if __name__ == "__main__":
    # 创建PLC写入管理器实例
    write_manager = PLCWriteManager(max_workers=5)
    
    try:
        # 启动管理器
        write_manager.start()
        
        # 示例：为1#楼写入制冷模式
        building_file = "3#_data_test.json"
        mode = PLCWriteManager.MODE_VENTILATION  # 通风模式
        
        # 执行写入
        results = write_manager.write_mode_for_building(building_file, mode)
        
        # 打印摘要
        write_manager.print_write_summary(building_file)
        
    except Exception as e:
        logger.error(f"❌ 执行过程中发生异常: {str(e)}")
    finally:
        # 停止管理器
        write_manager.stop()