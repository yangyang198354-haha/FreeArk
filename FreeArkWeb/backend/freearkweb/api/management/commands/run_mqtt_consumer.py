import time
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from api.mqtt_consumer import start_mqtt_consumer, stop_mqtt_consumer

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    Django管理命令：运行MQTT消费者服务
    用于监听MQTT消息并将PLC数据保存到数据库
    """
    help = '启动MQTT消费者服务，监听PLC数据并保存到数据库'

    def handle(self, *args, **options):
        """命令处理函数"""
        self.stdout.write(self.style.SUCCESS('🚀 正在启动MQTT消费者服务...'))
        
        try:
            # 启动MQTT消费者
            if start_mqtt_consumer():
                self.stdout.write(self.style.SUCCESS('✅ MQTT消费者服务已成功启动'))
                self.stdout.write('📝 正在监听主题: /datacollection/plc/to/collector/#\n')
                self.stdout.write(self.style.WARNING('⚠️  按 Ctrl+C 停止服务'))
                
                # 保持命令运行
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    self.stdout.write('\n⏸️  收到停止信号...')
                finally:
                    # 停止MQTT消费者
                    self.stdout.write('🔄 正在停止MQTT消费者服务...')
                    if stop_mqtt_consumer():
                        self.stdout.write(self.style.SUCCESS('✅ MQTT消费者服务已成功停止'))
                    else:
                        self.stdout.write(self.style.ERROR('❌ MQTT消费者服务停止失败'))
            else:
                self.stdout.write(self.style.ERROR('❌ MQTT消费者服务启动失败'))
                exit_code = 1
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ 运行过程中发生错误: {str(e)}'))
            logger.error(f'运行MQTT消费者服务时发生错误: {str(e)}')
            exit_code = 1
        else:
            exit_code = 0
        
        return exit_code