# 简化的日志管理模块
import os
import sys
import logging
import time
import json

# 确保中文显示正常
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

# 定义日志级别映射
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# 全局缓存的logger实例
global_loggers = {}

def setup_logger(name):
    """创建并配置logger实例"""
    # 检查是否已经创建过该logger
    if name in global_loggers:
        return global_loggers[name]
    
    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # 默认设置为最低级别，让处理器控制输出
    
    # 清除已有的处理器（如果有）
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # 控制台默认显示INFO级别以上的日志
    
    # 创建文件处理器
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'log')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = f"{name}_{time.strftime('%Y%m%d')}.log"
    log_path = os.path.join(log_dir, log_filename)
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别的日志
    
    # 设置日志格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    # 添加处理器到logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # 缓存logger实例
    global_loggers[name] = logger
    
    return logger

# 提供便捷的函数
def get_logger(name):
    """获取配置好的logger实例"""
    return setup_logger(name)