import struct
import sys
import time
import threading
from typing import Optional, List, Dict, Tuple, Any
import concurrent.futures
import os
from collections import defaultdict

# 添加FreeArk目录到Python路径，确保模块可以正确导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger

# 尝试导入snap7模块
try:
    import snap7
    import sys
    snap7_available = True
except ImportError:
    snap7_available = False
    # 导入必要模块
    import logging
    
# 获取logger，日志级别从配置文件读取
logger = get_logger('multi_thread_plc_handler')

# 如果snap7模块未找到，记录警告
if not snap7_available:
    logger.warning("❌ snap7模块未找到，PLC读取功能将不可用")

class PLCReadWriter:
    def __init__(self, plc_ip: str, rack: int = 0, slot: int = 1):
        """初始化PLC读取器 - 线程安全版本"""
        if not snap7_available:
            logger.error("❌ snap7模块未找到，无法创建PLC读取器")
            raise ImportError("snap7模块未找到")
        
        self.plc_ip = plc_ip
        self.rack = rack
        self.slot = slot
        self.client = snap7.client.Client()
        self.connected = False
        self.connect_time = 0  # 连接建立时间
        self.lock = threading.RLock()  # 使用可重入锁保证线程安全

    def connect(self) -> bool:
        """连接到PLC - 线程安全版本，增强日志记录"""
        with self.lock:
            if self.connected:
                logger.debug(f"🔌 PLC {self.plc_ip} 已经处于连接状态，无需重复连接")
                return True
            
            try:
                start_time = time.time()
                self.client.connect(self.plc_ip, self.rack, self.slot)
                if self.client.get_connected():
                    self.connected = True
                    self.connect_time = time.time()
                    connect_duration = self.connect_time - start_time
                    logger.info(f"✅ 成功连接PLC：{self.plc_ip}, Rack: {self.rack}, Slot: {self.slot}, 连接耗时: {connect_duration:.3f}秒")
                    return True
                else:
                    logger.info(f"❌ PLC连接失败：{self.plc_ip}（未建立连接）, Rack: {self.rack}, Slot: {self.slot}")
                    return False
            except Exception as e:
                logger.info(f"❌ PLC连接异常：{self.plc_ip}, Rack: {self.rack}, Slot: {self.slot} - {str(e)}")
                return False

    def disconnect(self) -> None:
        """断开PLC连接 - 线程安全版本，增强日志记录"""
        with self.lock:
            try:
                if self.connected:
                    start_time = time.time()
                    self.client.disconnect()
                    disconnect_duration = time.time() - start_time
                    connection_duration = time.time() - self.connect_time if self.connect_time > 0 else 0
                    self.connected = False
                    logger.info(f"✅ 已断开PLC连接：{self.plc_ip}, 断开耗时: {disconnect_duration:.3f}秒, 连接持续时间: {connection_duration:.2f}秒")
                else:
                    logger.debug(f"🔌 PLC {self.plc_ip} 未连接，无需断开")
            except Exception as e:
                logger.error(f"❌ PLC断开连接失败：{self.plc_ip} - {str(e)}")

    def read_db_data(self, db_num: int, offset: int, length: int, data_type: str, max_retries: int = 2) -> Optional[Tuple[bool, str, any]]:
        """读取指定DB块、偏移量、长度和类型的数据，支持重试"""
        retries = 0
        while retries <= max_retries:
            try:
                if not self.connected:
                    return False, f"未连接到PLC：{self.plc_ip}", None

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
                retries += 1
                if retries > max_retries:
                    return False, f"读取异常（已重试{max_retries}次）：{str(e)}", None
                logger.info(f"⚠️  读取异常，第{retries}次重试：{str(e)}")
                time.sleep(0.1 * retries)  # 指数退避策略

    def _parse_data(self, raw_data: bytes, data_type: str) -> Optional[any]:
        """根据数据类型解析原始数据"""
        try:
            if data_type == "byte":
                if len(raw_data) != 1:
                    return None
                return struct.unpack('>B', raw_data)[0]  # 大端模式8位无符号整数
            elif data_type == "int8":
                if len(raw_data) != 1:
                    return None
                return struct.unpack('>b', raw_data)[0]  # 大端模式8位有符号整数
            elif data_type == "uint16":
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
            
    def _pack_data(self, value: any, data_type: str) -> Optional[bytes]:
        """根据数据类型打包原始数据"""
        try:
            if data_type == "int8":
                return struct.pack('>b', value)  # 大端模式8位有符号整数
            elif data_type == "uint16":
                return struct.pack('>H', value)  # 大端模式16位无符号整数
            elif data_type == "int16":
                return struct.pack('>h', value)  # 大端模式16位有符号整数
            elif data_type == "uint32":
                return struct.pack('>I', value)  # 大端模式32位无符号整数
            elif data_type == "int32":
                return struct.pack('>i', value)  # 大端模式32位有符号整数
            elif data_type == "float32":
                return struct.pack('>f', value)  # 大端模式32位浮点数
            elif data_type == "float64":
                return struct.pack('>d', value)  # 大端模式64位浮点数
            else:
                logger.info(f"❌ 不支持的数据类型：{data_type}")
                return None
        except Exception as e:
            logger.info(f"❌ 数据打包异常：{str(e)}")
            return None
    
    def write_db_data(self, db_num: int, offset: int, value: any, data_type: str, max_retries: int = 2) -> Optional[Tuple[bool, str]]:
        """写入指定DB块、偏移量、值和类型的数据，支持重试"""
        retries = 0
        while retries <= max_retries:
            try:
                if not self.connected:
                    return False, f"未连接到PLC：{self.plc_ip}"

                # 检查偏移量是否超出DB块最大范围（64KB限制）
                if offset > 65535:
                    return False, f"写入偏移量越界（最大允许偏移量≤65535）"

                # 根据数据类型打包数据
                packed_data = self._pack_data(value, data_type)
                if packed_data is None:
                    return False, f"数据类型打包失败：{data_type}"

                # 写入数据
                self.client.db_write(db_num, offset, packed_data)
                return True, "写入成功"
            except Exception as e:
                retries += 1
                if retries > max_retries:
                    return False, f"写入异常（已重试{max_retries}次）：{str(e)}"
                logger.info(f"⚠️  写入异常，第{retries}次重试：{str(e)}")
                time.sleep(0.1 * retries)  # 指数退避策略


    def write_multi(self, configs: List[Dict], max_retries: int = 2) -> List[Tuple[bool, str]]:
        """顺序写入多个参数，兼容所有 snap7 版本"""
        if not self.connected:
            return [(False, "未连接到PLC") for _ in configs]

        results = []
        for req in configs:
            result = self.write_db_data(
                req['db_num'], req['offset'], req['value'], req['data_type'], max_retries
            )
            if result is None:
                results.append((False, "写入返回None"))
            else:
                results.append(result)
        return results

    def read_multi(self, requests: List[Dict], max_retries: int = 2) -> List[Tuple[bool, str, any]]:
        """顺序读取多个参数，兼容所有 snap7 版本"""
        if not self.connected:
            return [(False, "未连接到PLC", None) for _ in requests]

        results = []
        for req in requests:
            result = self.read_db_data(
                req['db_num'], req['offset'], req['length'], req['data_type'], max_retries
            )
            if result is None:
                results.append((False, "读取返回None", None))
            else:
                results.append(result)
        return results

# S7 PDU 限制：单次 read_multi 请求最多携带的参数数量
# 每个请求项约占 12 字节请求头 + 数据长度；保守取 12 个参数/请求确保不超 240 字节有效载荷
PDU_CHUNK_SIZE = 12


class PLCManager:
    def __init__(self, max_workers: int = 5):
        """初始化PLC管理器，配置线程池大小"""
        self.max_workers = max_workers
        self.thread_pool = None
        self.clients_cache = {}  # 客户端缓存，按IP存储
        self.clients_lock = threading.RLock()  # 用于保护clients_cache的锁
        self.connection_stats = defaultdict(lambda: {'total_connections': 0, 'active_connections': 0})  # 连接统计
        self.stats_lock = threading.Lock()  # 用于保护统计数据的锁
        self.start_time = 0  # 管理器启动时间

    def start(self):
        """启动线程池"""
        if self.thread_pool is None:
            self.start_time = time.time()
            self.thread_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="PLCReader"
            )
            logger.info(f"✅ PLC管理器已启动，线程池大小：{self.max_workers}, 线程池ID: {id(self.thread_pool)}")
        else:
            logger.info(f"✅ PLC管理器已经启动，当前线程池大小：{self.max_workers}")

    def stop(self):
        """关闭线程池并清理所有连接"""
        if self.thread_pool:
            # 首先清理所有缓存的客户端连接
            self._cleanup_all_connections()
            
            # 然后关闭线程池
            shutdown_start = time.time()
            self.thread_pool.shutdown(wait=True)
            shutdown_duration = time.time() - shutdown_start
            self.thread_pool = None
            
            # 打印停止信息
            total_runtime = time.time() - self.start_time if self.start_time > 0 else 0
            logger.info(f"✅ PLC管理器已停止，线程池已关闭，关闭耗时: {shutdown_duration:.3f}秒, 总运行时间: {total_runtime:.2f}秒")
        else:
            logger.info("✅ PLC管理器未启动，无需停止")
    
    def _cleanup_all_connections(self) -> None:
        """清理所有缓存的PLC连接"""
        with self.clients_lock:
            for ip, reader in list(self.clients_cache.items()):
                try:
                    reader.disconnect()
                    del self.clients_cache[ip]
                except Exception as e:
                    logger.error(f"❌ 清理PLC {ip}连接时出错: {str(e)}")
            logger.info(f"🧹 已清理所有PLC连接，清理数量: {len(self.clients_cache)}")
            
    def set_max_workers(self, max_workers: int):
        """动态调整线程池大小"""
        if max_workers <= 0:
            logger.error(f"❌ 线程池大小必须为正数，当前值: {max_workers}")
            return False
            
        if self.max_workers == max_workers:
            logger.info(f"🔧 PLC管理器线程池大小已经是: {self.max_workers}，无需调整")
            return True
            
        logger.info(f"🔧 PLC管理器线程池大小正在从 {self.max_workers} 调整为: {max_workers}")
        
        if self.thread_pool and not self.thread_pool._shutdown:
            old_thread_pool = self.thread_pool
            # 创建新的线程池
            self.thread_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="PLCReader"
            )
            # 记录新线程池信息
            logger.info(f"🔧 PLC管理器已创建新线程池，大小: {max_workers}, ID: {id(self.thread_pool)}")
            # 关闭旧的线程池，但不等待，让其在后台结束
            old_thread_pool.shutdown(wait=False)
            logger.info(f"🔧 PLC管理器已安排关闭旧线程池，ID: {id(old_thread_pool)}")
        
        self.max_workers = max_workers
        logger.info(f"✅ PLC管理器线程池大小已成功调整为: {self.max_workers}")
        return True
        
    def _get_or_create_reader(self, plc_ip: str) -> PLCReadWriter:
        """获取或创建PLC读取器 - 线程安全的客户端缓存管理"""
        with self.clients_lock:
            if plc_ip not in self.clients_cache:
                # 创建新的读取器
                reader = PLCReadWriter(plc_ip)
                self.clients_cache[plc_ip] = reader
                logger.debug(f"🎯 创建新的PLC读取器: {plc_ip}, 当前缓存大小: {len(self.clients_cache)}")
            else:
                reader = self.clients_cache[plc_ip]
                logger.debug(f"🎯 复用缓存的PLC读取器: {plc_ip}, 当前缓存大小: {len(self.clients_cache)}")
        
        # 更新连接统计
        with self.stats_lock:
            self.connection_stats[plc_ip]['total_connections'] += 1
            
        return reader

    def read_multiple_plcs(self, plc_configs: List[Dict]) -> List[Dict]:
        """
        读取多个PLC的数据 - 优化版，使用线程安全的客户端缓存
        plc_configs: 包含多个PLC配置的列表，每个配置包含ip、db_num、offset、length、data_type
        """
        if not self.thread_pool:
            logger.info("❌ 线程池未启动，请先调用start()方法")
            return []
        
        # 按PLC IP对参数配置进行分组
        ip_to_configs = {}
        for config in plc_configs:
            plc_ip = config['ip']
            if plc_ip not in ip_to_configs:
                ip_to_configs[plc_ip] = []
            ip_to_configs[plc_ip].append(config)
        
        # 打印任务启动信息
        unique_ips = set(config.get('ip') for config in plc_configs if config.get('ip'))
        logger.info(f"🚀 开始读取PLC数据 - 任务总数: {len(plc_configs)}, 涉及PLC数量: {len(unique_ips)}, 线程池大小: {self.max_workers}")
        
        # 为每个PLC IP创建一个任务
        future_to_ip = {}
        for plc_ip, configs in ip_to_configs.items():
            future = self.thread_pool.submit(self._read_single_plc_multiple_params, plc_ip, configs)
            future_to_ip[future] = (plc_ip, configs)
        
        # 收集结果
        results = []
        start_time = time.time()
        
        for future in concurrent.futures.as_completed(future_to_ip):
            plc_ip, configs = future_to_ip[future]
            try:
                # 设置超时时间为30秒
                ip_results = future.result(timeout=30)
                results.extend(ip_results)
            except concurrent.futures.TimeoutError:
                logger.error(f"❌ PLC任务执行超时：{plc_ip}, 超时时间30秒")
                # 为该IP下的所有配置添加超时结果
                for config in configs:
                    results.append({
                        'ip': config['ip'],
                        'db_num': config['db_num'],
                        'offset': config['offset'],
                        'success': False,
                        'message': "任务执行超时（30秒）",
                        'value': None
                    })
            except Exception as e:
                logger.info(f"❌ PLC任务执行异常：{plc_ip} - {str(e)}")
                # 为该IP下的所有配置添加失败结果
                for config in configs:
                    results.append({
                        'ip': config['ip'],
                        'db_num': config['db_num'],
                        'offset': config['offset'],
                        'success': False,
                        'message': f"任务执行异常：{str(e)}",
                        'value': None
                    })
        
        # 打印完成信息
        total_duration = time.time() - start_time
        success_count = sum(1 for r in results if r.get('success', False))
        logger.info(f"✅ PLC数据读取任务已完成 - 总耗时: {total_duration:.2f}秒, 成功: {success_count}/{len(results)}个任务")
        
        # 打印连接统计信息
        self._print_connection_stats()
        
        return results
    
    def _print_connection_stats(self) -> None:
        """打印连接统计信息"""
        with self.stats_lock:
            if not self.connection_stats:
                return
            
            logger.info("\n📊 PLC连接统计信息")
            logger.info("=" * 60)
            logger.info(f"{'IP地址':<15} {'总连接次数':<12} {'活跃连接数':<12}")
            logger.info("-" * 60)
            
            for ip, stats in self.connection_stats.items():
                active_count = 1 if ip in self.clients_cache and self.clients_cache[ip].connected else 0
                logger.info(f"{ip:<15} {stats['total_connections']:<12} {active_count:<12}")
            
            logger.info("=" * 60)

    def _read_single_plc_multiple_params(self, plc_ip: str, configs: List[Dict]) -> List[Dict]:
        """读取单个PLC的多个参数 - 使用线程安全的客户端缓存，分块批量读取以遵守S7 PDU限制"""
        results = []

        # 获取或创建PLC读取器（连接复用）
        reader = self._get_or_create_reader(plc_ip)

        try:
            # 确保已连接
            if not reader.connect():
                for config in configs:
                    results.append({
                        'ip': plc_ip,
                        'db_num': config['db_num'],
                        'offset': config['offset'],
                        'success': False,
                        'message': "PLC连接失败",
                        'value': None,
                        'read_time': 0
                    })
                return results

            # 更新活跃连接统计
            with self.stats_lock:
                self.connection_stats[plc_ip]['active_connections'] = 1

            # 将参数列表分成若干块，每块不超过 PDU_CHUNK_SIZE 个参数
            chunks = [configs[i:i + PDU_CHUNK_SIZE] for i in range(0, len(configs), PDU_CHUNK_SIZE)]
            logger.debug(f"🔧 PLC {plc_ip}: 共{len(configs)}个参数，分{len(chunks)}块读取（每块≤{PDU_CHUNK_SIZE}个）")

            start_read_time = time.time()
            all_read_results: List[Tuple[bool, str, any]] = []

            for chunk_idx, chunk in enumerate(chunks):
                try:
                    chunk_results = reader.read_multi(chunk)
                    all_read_results.extend(chunk_results)
                    logger.debug(f"🔧 PLC {plc_ip}: 第{chunk_idx + 1}/{len(chunks)}块读取完成，{len(chunk)}个参数")
                except Exception as chunk_err:
                    logger.info(f"❌ PLC {plc_ip} 第{chunk_idx + 1}块读取异常：{str(chunk_err)}")
                    # 该块所有参数标记失败，继续下一块
                    for _ in chunk:
                        all_read_results.append((False, f"分块读取异常：{str(chunk_err)}", None))

            total_read_time = time.time() - start_read_time
            read_duration_per_param = total_read_time / len(configs) if configs else 0

            # 处理所有块的结果
            for i, (success, message, value) in enumerate(all_read_results):
                config = configs[i]
                db_num = config['db_num']
                offset = config['offset']
                data_type = config['data_type']

                result = {
                    'ip': plc_ip,
                    'db_num': db_num,
                    'offset': offset,
                    'success': success,
                    'message': message,
                    'value': value,
                    'read_time': read_duration_per_param
                }
                results.append(result)

                if success:
                    logger.debug(f"✅ 成功读取PLC数据: {plc_ip}, DB{db_num}, 偏移量{offset}, 类型:{data_type}")
                else:
                    logger.debug(f"❌ 读取PLC数据失败: {plc_ip}, DB{db_num}, 偏移量{offset}, 原因: {message}")

            return results
        except Exception as e:
            logger.info(f"❌ PLC多参数读取异常：{plc_ip} - {str(e)}")
            for config in configs:
                results.append({
                    'ip': plc_ip,
                    'db_num': config['db_num'],
                    'offset': config['offset'],
                    'success': False,
                    'message': f"读取异常：{str(e)}",
                    'value': None,
                    'read_time': 0
                })
            return results

    def _read_single_plc(self, config: Dict) -> Dict:
        """读取单个PLC的数据 - 使用线程安全的客户端缓存"""
        plc_ip = config['ip']
        db_num = config['db_num']
        offset = config['offset']
        length = config['length']
        data_type = config['data_type']

        # 获取或创建PLC读取器
        reader = self._get_or_create_reader(plc_ip)
        try:
            if not reader.connect():
                return {
                    'ip': plc_ip,
                    'db_num': db_num,
                    'offset': offset,
                    'success': False,
                    'message': "PLC连接失败",
                    'value': None,
                    'read_time': 0
                }

            # 读取数据
            start_read_time = time.time()
            success, message, value = reader.read_db_data(db_num, offset, length, data_type)
            read_duration = time.time() - start_read_time
            
            return {
                'ip': plc_ip,
                'db_num': db_num,
                'offset': offset,
                'success': success,
                'message': message,
                'value': value,
                'read_time': read_duration
            }
        except Exception as e:
            logger.error(f"❌ 读取单个PLC数据异常: {plc_ip}, DB{db_num}, 偏移量{offset} - {str(e)}")
            return {
                'ip': plc_ip,
                'db_num': db_num,
                'offset': offset,
                'success': False,
                'message': f"读取异常: {str(e)}",
                'value': None,
                'read_time': 0
            }

    def print_results(self, results: List[Dict]) -> None:
        """打印读取结果 - 增强版，显示读取耗时"""
        if not results:
            logger.info("📊 没有PLC数据读取结果可供显示")
            return
            
        logger.info("\n" + "=" * 85)
        logger.info(f"📊 PLC数据读取结果汇总 - 总任务数: {len(results)}")
        logger.info("=" * 85)
        # 增加了读取耗时的显示
        logger.info(f"{'IP地址':<15} {'DB块':<6} {'偏移量':<8} {'结果':<8} {'数据值':<15} {'读取耗时(ms)':<12} {'消息':<20}")
        logger.info("-" * 85)
        
        success_count = 0
        total_read_time = 0
        
        for result in results:
            success_str = "✅ 成功" if result.get('success', False) else "❌ 失败"
            value_str = str(result.get('value')) if result.get('value') is not None else "-"
            read_time_str = f"{result.get('read_time', 0) * 1000:.1f}" if 'read_time' in result else "-"
            
            if result.get('success', False):
                success_count += 1
                total_read_time += result.get('read_time', 0)
            
            message = result.get('message', '')
            # 限制消息长度，避免日志过长
            message = message[:20] + '...' if len(message) > 20 else message
            
            logger.info(f"{result.get('ip', '未知'):<15} {result.get('db_num', '未知'):<6} {result.get('offset', '未知'):<8} {success_str:<8} {value_str:<15} {read_time_str:<12} {message:<20}")
        
        avg_read_time = (total_read_time / success_count) * 1000 if success_count > 0 else 0
        logger.info("=" * 85)
        logger.info(f"📋 统计：成功 {success_count}/{len(results)} 个任务, 平均读取耗时: {avg_read_time:.1f}ms")
        logger.info("=" * 85)
    
    def write_single_plc_param(self, config: Dict, value: Any) -> Dict:
        """写入单个PLC参数 - 使用线程安全的客户端缓存
        
        Args:
            config: PLC配置字典，包含ip、db_num、offset和data_type
            value: 要写入的值
            
        Returns:
            写入结果字典
        """
        plc_ip = config['ip']
        db_num = config['db_num']
        offset = config['offset']
        data_type = config['data_type']
        
        # 获取或创建PLC读取器
        reader = self._get_or_create_reader(plc_ip)
        try:
            # 确保已连接
            if not reader.connect():
                return {
                    'ip': plc_ip,
                    'db_num': db_num,
                    'offset': offset,
                    'value': value,
                    'data_type': data_type,
                    'success': False,
                    'message': "PLC连接失败"
                }
            
            # 更新活跃连接统计
            with self.stats_lock:
                self.connection_stats[plc_ip]['active_connections'] = 1
            
            # 写入数据
            start_write_time = time.time()
            success, message = reader.write_db_data(db_num, offset, value, data_type)
            write_duration = time.time() - start_write_time
            
            result = {
                'ip': plc_ip,
                'db_num': db_num,
                'offset': offset,
                'value': value,
                'data_type': data_type,
                'success': success,
                'message': message,
                'write_time': write_duration
            }
            
            # 记录详细的写入日志
            if success:
                logger.debug(f"✅ 成功写入PLC数据: {plc_ip}, DB{db_num}, 偏移量{offset}, 值: {value}, 数据类型: {data_type}, 耗时: {write_duration:.3f}秒")
            else:
                logger.debug(f"❌ 写入PLC数据失败: {plc_ip}, DB{db_num}, 偏移量{offset}, 原因: {message}")
            
            return result
        except Exception as e:
            logger.error(f"❌ 写入单个PLC数据异常: {plc_ip}, DB{db_num}, 偏移量{offset} - {str(e)}")
            return {
                'ip': plc_ip,
                'db_num': db_num,
                'offset': offset,
                'value': value,
                'data_type': data_type,
                'success': False,
                'message': f"写入异常: {str(e)}",
                'write_time': 0
            }

    def _write_single_plc_multiple_params(self, plc_ip: str, configs: List[Dict]) -> List[Dict]:
        """写入单个PLC的多个参数 - 使用线程安全的客户端缓存"""
        results = []
        
        # 获取或创建PLC读取器
        reader = self._get_or_create_reader(plc_ip)
        
        try:
            # 确保已连接
            if not reader.connect():
                # 连接失败，为所有配置添加失败结果
                for config in configs:
                    results.append({
                        'ip': plc_ip,
                        'db_num': config['db_num'],
                        'offset': config['offset'],
                        'value': config['value'],
                        'data_type': config['data_type'],
                        'success': False,
                        'message': "PLC连接失败"
                    })
                return results
            
            # 更新活跃连接统计
            with self.stats_lock:
                self.connection_stats[plc_ip]['active_connections'] = 1
            
            # 批量写入所有参数
            start_write_time = time.time()
            write_results = reader.write_multi(configs)
            total_write_time = time.time() - start_write_time
            
            # 处理批量写入结果
            for i, (success, message) in enumerate(write_results):
                config = configs[i]
                db_num = config['db_num']
                offset = config['offset']
                value = config['value']
                data_type = config['data_type']
                
                result = {
                    'ip': plc_ip,
                    'db_num': db_num,
                    'offset': offset,
                    'value': value,
                    'data_type': data_type,
                    'success': success,
                    'message': message,
                    'write_time': total_write_time / len(configs)  # 平均分配总耗时
                }
                
                # 记录详细的写入日志
                if success:
                    logger.debug(f"✅ 成功写入PLC数据: {plc_ip}, DB{db_num}, 偏移量{offset}, 值: {value}, 数据类型: {data_type}, 耗时: {result['write_time']:.3f}秒")
                else:
                    logger.debug(f"❌ 写入PLC数据失败: {plc_ip}, DB{db_num}, 偏移量{offset}, 原因: {message}")
                
                results.append(result)
            
            return results
        except Exception as e:
            logger.error(f"❌ 写入单个PLC的多个参数异常: {plc_ip} - {str(e)}")
            # 为所有配置添加失败结果
            for config in configs:
                results.append({
                    'ip': plc_ip,
                    'db_num': config['db_num'],
                    'offset': config['offset'],
                    'value': config['value'],
                    'data_type': config['data_type'],
                    'success': False,
                    'message': f"写入异常：{str(e)}"
                })
            return results

    def write_multiple_plc_params(self, plc_write_configs: List[Dict]) -> List[Dict]:
        """批量写入多个PLC的参数 - 优化版，使用线程安全的客户端缓存"""
        if not self.thread_pool:
            logger.info("❌ 线程池未启动，请先调用start()方法")
            return []
        
        # 按PLC IP对参数配置进行分组
        ip_to_configs = {}
        for config in plc_write_configs:
            plc_ip = config['ip']
            if plc_ip not in ip_to_configs:
                ip_to_configs[plc_ip] = []
            ip_to_configs[plc_ip].append(config)
        
        # 打印任务启动信息
        unique_ips = set(config.get('ip') for config in plc_write_configs if config.get('ip'))
        logger.info(f"🚀 开始写入PLC数据 - 任务总数: {len(plc_write_configs)}, 涉及PLC数量: {len(unique_ips)}, 线程池大小: {self.max_workers}")
        
        # 为每个PLC IP创建一个任务
        future_to_ip = {}
        for plc_ip, configs in ip_to_configs.items():
            future = self.thread_pool.submit(self._write_single_plc_multiple_params, plc_ip, configs)
            future_to_ip[future] = (plc_ip, configs)
        
        # 收集结果
        results = []
        start_time = time.time()
        
        for future in concurrent.futures.as_completed(future_to_ip):
            plc_ip, configs = future_to_ip[future]
            try:
                # 设置超时时间为30秒
                ip_results = future.result(timeout=30)
                results.extend(ip_results)
            except concurrent.futures.TimeoutError:
                logger.error(f"❌ PLC写入任务执行超时：{plc_ip}, 超时时间30秒")
                # 为该IP下的所有配置添加超时结果
                for config in configs:
                    results.append({
                        'ip': config['ip'],
                        'db_num': config['db_num'],
                        'offset': config['offset'],
                        'value': config['value'],
                        'data_type': config['data_type'],
                        'success': False,
                        'message': "任务执行超时（30秒）",
                        'value': None
                    })
            except Exception as e:
                logger.info(f"❌ PLC写入任务执行异常：{plc_ip} - {str(e)}")
                # 为该IP下的所有配置添加失败结果
                for config in configs:
                    results.append({
                        'ip': config['ip'],
                        'db_num': config['db_num'],
                        'offset': config['offset'],
                        'value': config['value'],
                        'data_type': config['data_type'],
                        'success': False,
                        'message': f"任务执行异常：{str(e)}",
                        'value': None
                    })
        
        # 打印完成信息
        total_duration = time.time() - start_time
        success_count = sum(1 for r in results if r.get('success', False))
        logger.info(f"✅ PLC数据写入任务已完成 - 总耗时: {total_duration:.2f}秒, 成功: {success_count}/{len(results)}个任务")
        
        # 打印连接统计信息
        self._print_connection_stats()
        
        return results
    
    def print_write_results(self, results: List[Dict]) -> None:
        """打印写入结果 - 显示写入耗时"""
        if not results:
            logger.info("📊 没有PLC数据写入结果可供显示")
            return
            
        logger.info("\n" + "=" * 85)
        logger.info(f"📊 PLC数据写入结果汇总 - 总任务数: {len(results)}")
        logger.info("=" * 85)
        logger.info(f"{'IP地址':<15} {'DB块':<6} {'偏移量':<8} {'结果':<8} {'写入值':<15} {'数据类型':<10} {'写入耗时(ms)':<12} {'消息':<20}")
        logger.info("-" * 85)
        
        success_count = 0
        total_write_time = 0
        
        for result in results:
            success_str = "✅ 成功" if result.get('success', False) else "❌ 失败"
            value_str = str(result.get('value')) if result.get('value') is not None else "-"
            data_type = result.get('data_type', '-')
            write_time_str = f"{result.get('write_time', 0) * 1000:.1f}" if 'write_time' in result else "-"
            
            if result.get('success', False):
                success_count += 1
                total_write_time += result.get('write_time', 0)
            
            message = result.get('message', '')
            # 限制消息长度，避免日志过长
            message = message[:20] + '...' if len(message) > 20 else message
            
            logger.info(f"{result.get('ip', '未知'):<15} {result.get('db_num', '未知'):<6} {result.get('offset', '未知'):<8} {success_str:<8} {value_str:<15} {data_type:<10} {write_time_str:<12} {message:<20}")
        
        avg_write_time = (total_write_time / success_count) * 1000 if success_count > 0 else 0
        logger.info("=" * 85)
        logger.info(f"📋 统计：成功 {success_count}/{len(results)} 个任务, 平均写入耗时: {avg_write_time:.1f}ms")
        logger.info("=" * 85)


# 示例用法
if __name__ == "__main__":
    # 创建PLC管理器，设置线程池大小为3
    plc_manager = PLCManager(max_workers=3)
    plc_manager.start()
    
    try:
        # 示例：动态调整线程池大小
        plc_manager.set_max_workers(5)
        
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