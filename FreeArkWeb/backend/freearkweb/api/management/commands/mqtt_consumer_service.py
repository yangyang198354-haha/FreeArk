import os
import time
import logging
import schedule
from django.core.management.base import BaseCommand
from django.conf import settings
from api.mqtt_consumer import start_mqtt_consumer, stop_mqtt_consumer

# 配置日志，确保日志目录存在
log_dir = os.path.join(settings.BASE_DIR, 'logs')
os.makedirs(log_dir, exist_ok=True)

# 配置logger
logger = logging.getLogger('mqtt_consumer_service')
logger.setLevel(logging.INFO)

# 确保logger没有现有的handler
if not logger.handlers:
    # 添加文件handler
    log_file = os.path.join(log_dir, 'mqtt_consumer_service.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 添加控制台handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

class Command(BaseCommand):
    """
    Django管理命令：运行MQTT消费者服务
    用于监听MQTT消息并将PLC数据保存到数据库
    使用schedule机制进行管理，保持服务持续运行
    """
    help = '启动MQTT消费者服务，监听PLC数据并保存到数据库（使用schedule机制）'

    def add_arguments(self, parser):
        # 添加监控间隔参数（秒）
        parser.add_argument(
            '--monitor-interval',
            type=int,
            default=60,
            help='服务监控间隔（秒），默认为60秒'
        )
        # 可选的自动重启功能
        parser.add_argument(
            '--auto-restart',
            action='store_true',
            default=False,
            help='当MQTT服务异常停止时自动重启'
        )

    def handle(self, *args, **options):
        """命令处理函数"""
        monitor_interval = options['monitor_interval']
        auto_restart = options['auto_restart']
        
        logger.info('🚀 正在启动MQTT消费者服务...')
        self.stdout.write(self.style.SUCCESS('🚀 正在启动MQTT消费者服务...'))
        logger.info(f'🔧 服务配置: monitor_interval={monitor_interval}秒, auto_restart={auto_restart}')
        
        exit_code = 0
        
        try:
            # 启动MQTT消费者
            logger.info('🔄 尝试启动MQTT消费者...')
            if start_mqtt_consumer():
                success_msg = '✅ MQTT消费者服务已成功启动'
                logger.info(success_msg)
                self.stdout.write(self.style.SUCCESS(success_msg))
                
                topic_msg = '📝 正在监听主题: /datacollection/plc/to/collector/#'
                logger.info(topic_msg)
                self.stdout.write(topic_msg + '\n')
                
                warning_msg = '⚠️  按 Ctrl+C 停止服务'
                logger.info(warning_msg)
                self.stdout.write(self.style.WARNING(warning_msg))
                
                # 设置监控任务（如果需要自动重启）
                if auto_restart:
                    schedule.every(monitor_interval).seconds.do(self._monitor_service)
                    logger.info(f'🔍 已设置服务监控，每{monitor_interval}秒检查一次')
                
                # 保持命令运行
                try:
                    logger.info('🔄 服务已启动，进入调度循环')
                    while True:
                        schedule.run_pending()
                        time.sleep(1)
                except KeyboardInterrupt:
                    stop_signal_msg = '🛑 收到停止信号...'
                    logger.info(stop_signal_msg)
                    self.stdout.write('\n' + stop_signal_msg)
                finally:
                    # 停止MQTT消费者
                    stopping_msg = '🔄 正在停止MQTT消费者服务...'
                    logger.info(stopping_msg)
                    self.stdout.write(stopping_msg)
                    
                    if stop_mqtt_consumer():
                        stop_success_msg = '✅ MQTT消费者服务已成功停止'
                        logger.info(stop_success_msg)
                        self.stdout.write(self.style.SUCCESS(stop_success_msg))
                    else:
                        stop_fail_msg = '❌ MQTT消费者服务停止失败'
                        logger.error(stop_fail_msg)
                        self.stdout.write(self.style.ERROR(stop_fail_msg))
                        exit_code = 1
            else:
                start_fail_msg = '❌ MQTT消费者服务启动失败'
                logger.error(start_fail_msg)
                self.stdout.write(self.style.ERROR(start_fail_msg))
                exit_code = 1
                
        except Exception as e:
            error_msg = f'❌ 运行过程中发生错误: {str(e)}'
            logger.error(f'运行MQTT消费者服务时发生错误: {str(e)}')
            import traceback
            logger.error(traceback.format_exc())
            self.stdout.write(self.style.ERROR(error_msg))
            exit_code = 1
        else:
            exit_code = 0
        
        logger.info(f'📋 服务退出，退出码: {exit_code}')
        return exit_code
    
    def _monitor_service(self):
        """
        监控MQTT服务状态的内部方法
        注意：实际实现可能需要根据api.mqtt_consumer模块提供的接口进行调整
        """
        # 这里仅作为示例，实际实现需要根据api.mqtt_consumer模块的接口调整
        # 例如，可以添加检查MQTT客户端连接状态的逻辑
        logger.debug('🔍 监控服务状态')
        # 假设有一个检查服务状态的函数
        # if not is_mqtt_consumer_running():
        #     logger.error('⚠️ MQTT消费者服务异常停止，尝试重启...')
        #     start_mqtt_consumer()