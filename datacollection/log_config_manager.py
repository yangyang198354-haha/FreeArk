import os
import json
import logging
import time
import threading
import sys

# 定义日志级别映射
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

class LogConfigManager:
    _instance = None
    _lock = threading.Lock()
    _config = None
    _config_path = None
    _last_load_time = 0
    _cache_ttl = 300  # 配置缓存有效期（秒）

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LogConfigManager, cls).__new__(cls)
                # 获取配置文件路径
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                cls._instance._config_path = os.path.join(base_dir, 'resource', 'log_config.json')
                # 加载配置
                cls._instance._load_config()
            return cls._instance

    def _load_config(self):
        """从配置文件加载日志级别设置"""
        current_time = time.time()
        # 检查是否需要重新加载配置（缓存过期或首次加载）
        if self._config is None or (current_time - self._last_load_time > self._cache_ttl):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                self._last_load_time = current_time
            except Exception as e:
                # 如果配置文件加载失败，使用默认配置
                print(f"警告：无法加载日志配置文件 {self._config_path}，使用默认配置。错误: {str(e)}")
                self._config = {
                    'log_levels': {
                        'global': {'level': 'INFO'},
                        'improved_data_collection': {'level': 'INFO'},
                        'plc_reader': {'level': 'INFO'},
                        'mqtt_client': {'level': 'INFO'},
                        'quantity_statistics': {'level': 'INFO'}
                    }
                }

    def get_log_level(self, logger_name):
        """获取指定logger的日志级别"""
        # 确保配置已加载
        self._load_config()
        
        # 优先获取指定logger的级别，如果不存在则使用全局默认级别
        log_levels = self._config.get('log_levels', {})
        return LOG_LEVELS.get(
            log_levels.get(logger_name, {}).get('level', 'INFO'),
            LOG_LEVELS.get(log_levels.get('global', {}).get('level', 'INFO'), logging.INFO)
        )

    def get_logger(self, name):
        """获取配置好的logger实例"""
        # 获取logger
        logger = logging.getLogger(name)
        
        # 如果logger已经配置过处理器，则直接返回
        if logger.handlers:
            return logger
        
        # 设置日志级别
        log_level = self.get_log_level(name)
        logger.setLevel(log_level)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # 创建文件处理器，日志存储在log目录下
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'log')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 为日志文件添加日期
        log_filename = f"{name}_{time.strftime('%Y%m%d')}.log"
        log_path = os.path.join(log_dir, log_filename)
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(log_level)
        
        # 确保控制台输出的中文正常显示
        if hasattr(console_handler, 'setStream') and hasattr(sys.stdout, 'encoding'):
            console_handler.setStream(sys.stdout)
        
        # 设置日志格式，确保中文显示正常
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # 添加处理器到logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
        return logger

# 确保threading模块已导入
import threading

# 提供一个便捷的函数来获取logger
def get_logger(name):
    """获取配置好的logger实例"""
    return LogConfigManager().get_logger(name)