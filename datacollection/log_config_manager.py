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
                # 获取配置文件路径，兼容PyInstaller打包后的环境
                try:
                    # 优先尝试从当前工作目录获取
                    current_dir = os.getcwd()
                    config_path = os.path.join(current_dir, 'resource', 'log_config.json')
                    if not os.path.exists(config_path):
                        # 尝试从当前目录直接获取
                        config_path = os.path.join(current_dir, 'log_config.json')
                    # 最后尝试从传统路径获取
                    if not os.path.exists(config_path):
                        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        config_path = os.path.join(base_dir, 'resource', 'log_config.json')
                    cls._instance._config_path = config_path
                except Exception:
                    # 如果获取路径失败，使用默认路径
                    cls._instance._config_path = os.path.join(os.getcwd(), 'log_config.json')
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
                # fallback 默认：生产 ERROR，PLC 相关豁免到 WARNING（与 resource/log_config.json v2.0 对齐）
                self._config = {
                    'log_levels': {
                        'global': {'level': 'ERROR'},
                        'improved_data_collection': {'level': 'ERROR'},
                        'plc_reader': {'level': 'WARNING'},
                        'multi_thread_plc_handler': {'level': 'WARNING'},
                        'mqtt_client': {'level': 'ERROR'},
                        'quantity_statistics': {'level': 'ERROR'},
                        'plc_data_viewer': {'level': 'ERROR'},
                        'plc_write_manager': {'level': 'ERROR'}
                    }
                }

    def get_log_level(self, logger_name):
        """获取指定 logger 的日志级别。

        优先级（高 -> 低）：
          1. 环境变量 APP_LOG_LEVEL（运维排障 escape hatch，覆盖所有 logger）
          2. JSON 文件中该 logger 的 per-logger level（豁免名单）
          3. JSON 文件中的 global level
          4. 兜底 INFO
        """
        # 1. 环境变量优先：设置后所有 logger 一律采用该级别（便于运维排障）
        env_level = os.environ.get('APP_LOG_LEVEL', '').upper()
        if env_level in LOG_LEVELS:
            return LOG_LEVELS[env_level]

        # 2/3/4. 走 JSON 配置链路
        self._load_config()
        log_levels = self._config.get('log_levels', {})
        per_logger = log_levels.get(logger_name, {}).get('level', '').upper()
        if per_logger in LOG_LEVELS:
            return LOG_LEVELS[per_logger]
        global_default = log_levels.get('global', {}).get('level', 'INFO').upper()
        return LOG_LEVELS.get(global_default, logging.INFO)

    def get_logger(self, name):
        """获取配置好的logger实例"""
        # 获取logger
        logger = logging.getLogger(name)

        # 关闭向根 logger 冒泡（避免被其他进程的 root handler 重复抓走，US-B Q7）
        logger.propagate = False

        # 如果logger已经配置过处理器，则直接返回
        if logger.handlers:
            return logger

        # 设置日志级别
        log_level = self.get_log_level(name)
        logger.setLevel(log_level)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # 创建文件处理器，日志存储在可写的位置，兼容PyInstaller打包后的环境
        # 优先使用当前工作目录下的log目录（确保可写）
        log_dir = os.path.join(os.getcwd(), 'logs')
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
        except Exception as e:
            # 如果无法在当前目录创建，尝试使用用户目录
            user_home = os.path.expanduser('~')
            log_dir = os.path.join(user_home, 'PLC_Viewer_Logs')
            try:
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
            except Exception:
                # 如果都失败，至少输出到控制台，不创建文件日志
                print(f"警告: 无法创建日志目录，仅输出到控制台。错误: {str(e)}")
                logger.addHandler(console_handler)
                return logger
        
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