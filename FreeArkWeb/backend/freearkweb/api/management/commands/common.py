import logging
from django.conf import settings


def get_service_logger(service_name):
    """
    获取服务专用的日志器
    
    Args:
        service_name (str): 服务名称，会用作logger名称和日志文件标识
        
    Returns:
        logging.Logger: 配置好的日志器实例
    """
    logger = logging.getLogger(service_name)
    return logger


def log_service_start(logger, service_name, config_info=None):
    """
    记录服务启动日志
    
    Args:
        logger (logging.Logger): 日志器实例
        service_name (str): 服务名称
        config_info (dict, optional): 配置信息字典，会被格式化为日志
    """
    logger.info(f'🚀 {service_name} 服务启动')
    if config_info:
        config_str = ', '.join([f'{k}={v}' for k, v in config_info.items()])
        logger.info(f'🔧 服务配置: {config_str}')


def log_service_stop(logger, service_name):
    """
    记录服务停止日志
    
    Args:
        logger (logging.Logger): 日志器实例
        service_name (str): 服务名称
    """
    logger.info(f'🛑 {service_name} 服务已停止')


def log_task_start(logger, task_name, task_info=None):
    """
    记录任务开始日志
    
    Args:
        logger (logging.Logger): 日志器实例
        task_name (str): 任务名称
        task_info (dict, optional): 任务信息字典
    """
    if task_info:
        task_info_str = ', '.join([f'{k}={v}' for k, v in task_info.items()])
        logger.info(f'📊 开始执行{task_name}... {task_info_str}')
    else:
        logger.info(f'📊 开始执行{task_name}...')


def log_task_completion(logger, task_name, result_info=None):
    """
    记录任务完成日志
    
    Args:
        logger (logging.Logger): 日志器实例
        task_name (str): 任务名称
        result_info (dict, optional): 结果信息字典
    """
    if result_info:
        result_str = ', '.join([f'{k}={v}' for k, v in result_info.items()])
        logger.info(f'✅ {task_name} 完成: {result_str}')
    else:
        logger.info(f'✅ {task_name} 完成')


def log_error(logger, message, exception=None):
    """
    记录错误日志
    
    Args:
        logger (logging.Logger): 日志器实例
        message (str): 错误消息
        exception (Exception, optional): 异常对象，会记录traceback
    """
    if exception:
        logger.error(f'❌ {message}: {str(exception)}')
        import traceback
        logger.error(traceback.format_exc())
    else:
        logger.error(f'❌ {message}')


def log_warning(logger, message):
    """
    记录警告日志
    
    Args:
        logger (logging.Logger): 日志器实例
        message (str): 警告消息
    """
    logger.warning(f'⚠️  {message}')


def log_info(logger, message):
    """
    记录信息日志
    
    Args:
        logger (logging.Logger): 日志器实例
        message (str): 信息消息
    """
    logger.info(f'ℹ️  {message}')
