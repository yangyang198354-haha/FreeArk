# 测试简化版日志模块
from datacollection.simple_logger import get_logger

# 获取测试logger
logger = get_logger('simple_test')

# 测试不同级别的日志输出
logger.debug('这是一条调试信息 - Debug message')
logger.info('这是一条信息日志 - Info message')
logger.warning('这是一条警告日志 - Warning message')
logger.error('这是一条错误日志 - Error message')
logger.critical('这是一条严重错误日志 - Critical message')

print('简化版日志模块测试完成，请查看log目录下的simple_test_*.log文件')