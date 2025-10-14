import struct
import time
from typing import Optional, List, Dict, Tuple
import concurrent.futures
import logging
import os
import struct 

# 尝试导入snap7模块
try:
    import snap7
    snap7_available = True
    # 配置独立的logger
    logger = logging.getLogger('plc_reader')
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
        
        log_filename = f"plc_reader_{time.strftime('%Y%m%d')}.log"
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
except ImportError:
    snap7_available = False
    # 创建简单的logger
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('plc_reader')
    logger.warning("❌ snap7模块未找到，PLC读取功能将不可用")

class PLCReader:
    def __init__(self, plc_ip: str, rack: int = 0, slot: int = 1):
        """初始化PLC读取器"""
        if not snap7_available:
            logger.error("❌ snap7模块未找到，无法创建PLC读取器")
            raise ImportError("snap7模块未找到")
        
        self.plc_ip = plc_ip
        self.rack = rack
        self.slot = slot
        self.client = snap7.client.Client()
        self.connected = False

    def connect(self) -> bool:
        """连接到PLC"""
        try:
            self.client.connect(self.plc_ip, self.rack, self.slot)
            if self.client.get_connected():
                self.connected = True
                logger.info(f"✅ 成功连接PLC：{self.plc_ip}")
                return True
            else:
                logger.info(f"❌ PLC连接失败：{self.plc_ip}（未建立连接）")
                return False
        except Exception as e:
            logger.info(f"❌ PLC连接异常：{self.plc_ip} - {str(e)}")
            return False

    def disconnect(self) -> None:
        """断开PLC连接"""
        if self.connected:
            self.client.disconnect()
            self.connected = False
            logger.info(f"✅ 已断开PLC连接：{self.plc_ip}")

    def read_db_data(self, db_num: int, offset: int, length: int, data_type: str) -> Optional[Tuple[bool, str, any]]:
        """读取指定DB块、偏移量、长度和类型的数据"""
        if not self.connected:
            return False, f"未连接到PLC：{self.plc_ip}", None

        try:
            # 检查偏移量+长度是否超出DB块最大范围（64KB限制）
            max_possible_offset = offset + length - 1
            if max_possible_offset > 65535:
                return False, f"读取范围越界（最大允许偏移量+长度≤65535）", None

            # 读取原始数据
            raw_data = self.client.db_read(db_num, offset, length)
            if len(raw_data) != length:
                return False, f"数据长度不匹配（预期{length}字节，实际{len(raw_data)}字节）", None

            # 根据数据类型解析
            parsed_value = self._parse_data(raw_data, data_type)
            if parsed_value is None:
                return False, f"数据类型解析失败：{data_type}", None

            return True, "读取成功", parsed_value
        except Exception as e:
            return False, f"读取异常：{str(e)}", None

    def _parse_data(self, raw_data: bytes, data_type: str) -> Optional[any]:
        """根据数据类型解析原始数据"""
        try:
            if data_type == "uint16":
                if len(raw_data) != 2:
                    return None
                return struct.unpack('>H', raw_data)[0]  # 大端模式16位无符号整数
            elif data_type == "int16":
                if len(raw_data) != 2:
                    return None
                return struct.unpack('>h', raw_data)[0]  # 大端模式16位有符号整数
            elif data_type == "uint32":
                if len(raw_data) != 4:
                    return None
                return struct.unpack('>I', raw_data)[0]  # 大端模式32位无符号整数
            elif data_type == "int32":
                if len(raw_data) != 4:
                    return None
                return struct.unpack('>i', raw_data)[0]  # 大端模式32位有符号整数
            elif data_type == "float32":
                if len(raw_data) != 4:
                    return None
                return round(struct.unpack('>f', raw_data)[0], 4)  # 大端模式32位浮点数
            elif data_type == "float64":
                if len(raw_data) != 8:
                    return None
                return round(struct.unpack('>d', raw_data)[0], 6)  # 大端模式64位浮点数
            else:
                logger.info(f"❌ 不支持的数据类型：{data_type}")
                return None
        except Exception as e:
            logger.info(f"❌ 数据解析异常：{str(e)}")
            return None

class PLCManager:
    def __init__(self, max_workers: int = 5):
        """初始化PLC管理器，配置线程池大小"""
        self.max_workers = max_workers
        self.thread_pool = None

    def start(self):
        """启动线程池"""
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        logger.info(f"✅ PLC管理器已启动，线程池大小：{self.max_workers}")

    def stop(self):
        """关闭线程池"""
        if self.thread_pool:
            self.thread_pool.shutdown(wait=True)
            logger.info("✅ PLC管理器已停止，线程池已关闭")

    def read_multiple_plcs(self, plc_configs: List[Dict]) -> List[Dict]:
        """
        读取多个PLC的数据
        plc_configs: 包含多个PLC配置的列表，每个配置包含ip、db_num、offset、length、data_type
        """
        if not self.thread_pool:
            logger.info("❌ 线程池未启动，请先调用start()方法")
            return []

        # 提交所有任务到线程池
        future_to_config = {
            self.thread_pool.submit(self._read_single_plc, config): config 
            for config in plc_configs
        }

        # 收集结果
        results = []
        for future in concurrent.futures.as_completed(future_to_config):
            config = future_to_config[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.info(f"❌ PLC任务执行异常：{config['ip']} - {str(e)}")
                results.append({
                    'ip': config['ip'],
                    'db_num': config['db_num'],
                    'offset': config['offset'],
                    'success': False,
                    'message': f"任务执行异常：{str(e)}",
                    'value': None
                })

        return results

    def _read_single_plc(self, config: Dict) -> Dict:
        """读取单个PLC的数据"""
        plc_ip = config['ip']
        db_num = config['db_num']
        offset = config['offset']
        length = config['length']
        data_type = config['data_type']

        # 创建PLC读取器并连接
        reader = PLCReader(plc_ip)
        try:
            if not reader.connect():
                return {
                    'ip': plc_ip,
                    'db_num': db_num,
                    'offset': offset,
                    'success': False,
                    'message': "PLC连接失败",
                    'value': None
                }

            # 读取数据
            success, message, value = reader.read_db_data(db_num, offset, length, data_type)
            return {
                'ip': plc_ip,
                'db_num': db_num,
                'offset': offset,
                'success': success,
                'message': message,
                'value': value
            }
        finally:
            # 确保断开连接
            reader.disconnect()

    def print_results(self, results: List[Dict]) -> None:
        """打印读取结果"""
        logger.info("\n" + "=" * 80)
        logger.info(f"📊 PLC数据读取结果汇总 - 总任务数: {len(results)}")
        logger.info("=" * 80)
        logger.info(f"{'IP地址':<15} {'DB块':<6} {'偏移量':<8} {'结果':<8} {'数据值':<15} {'消息':<30}")
        logger.info("-" * 80)
        
        success_count = 0
        for result in results:
            success_str = "✅ 成功" if result['success'] else "❌ 失败"
            value_str = str(result['value']) if result['value'] is not None else "-"
            logger.info(f"{result['ip']:<15} {result['db_num']:<6} {result['offset']:<8} {success_str:<8} {value_str:<15} {result['message']:<30}")
            if result['success']:
                success_count += 1
        
        logger.info("=" * 80)
        logger.info(f"📋 统计：成功 {success_count}/{len(results)} 个任务")
        logger.info("=" * 80)


# 示例用法
if __name__ == "__main__":
    # 创建PLC管理器，设置线程池大小为3
    plc_manager = PLCManager(max_workers=3)
    plc_manager.start()
    
    try:
        # 定义要读取的多个PLC配置
        plc_configs = [
            {'ip': '192.168.3.27', 'db_num': 20, 'offset': 0, 'length': 2, 'data_type': 'uint16'},
            {'ip': '192.168.3.27', 'db_num': 20, 'offset': 2, 'length': 4, 'data_type': 'float32'},
            {'ip': '192.168.3.28', 'db_num': 20, 'offset': 0, 'length': 2, 'data_type': 'uint16'},  # 示例：不同IP
            {'ip': '192.168.3.27', 'db_num': 603, 'offset': 0, 'length': 4, 'data_type': 'float32'},
            {'ip': '192.168.3.27', 'db_num': 20, 'offset': 6, 'length': 8, 'data_type': 'float64'}
        ]
        
        # 开始计时
        start_time = time.time()
        
        # 读取多个PLC数据
        logger.info(f"🚀 开始读取 {len(plc_configs)} 个PLC数据项...")
        results = plc_manager.read_multiple_plcs(plc_configs)
        
        # 打印结果
        plc_manager.print_results(results)
        
        # 计算耗时
        elapsed_time = time.time() - start_time
        logger.info(f"⏱️  总耗时：{elapsed_time:.2f} 秒")
        
    except KeyboardInterrupt:
        logger.info("\n✅ 用户手动终止程序")
    except Exception as e:
        logger.info(f"\n❌ 程序异常：{str(e)}")
    finally:
        # 确保停止线程池
        plc_manager.stop()