# 测试日志配置模块
from datacollection.log_config_manager import get_logger

# 获取测试logger
logger = get_logger('test')

# 测试不同级别的日志输出
logger.debug('这是一条调试信息')
logger.info('这是一条信息日志')
logger.warning('这是一条警告日志')
logger.error('这是一条错误日志')
logger.critical('这是一条严重错误日志')

print('日志测试完成，请查看log目录下的test_*.log文件')