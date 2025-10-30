import os
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from api.plc_data_cleaner import clean_old_plc_data

# 配置日志，确保日志目录存在
log_dir = os.path.join(settings.BASE_DIR, 'logs')
os.makedirs(log_dir, exist_ok=True)

# 配置logger
logger = logging.getLogger('clean_plc_data')
logger.setLevel(logging.INFO)

# 确保logger没有现有的handler
if not logger.handlers:
    # 添加文件handler
    log_file = os.path.join(log_dir, 'clean_plc_data.log')
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
    Django管理命令，用于清除PLC数据表中指定天数之前的记录
    """
    help = '清除PLC数据表中指定天数之前的记录'

    def add_arguments(self, parser):
        # 添加可选参数，指定要保留的天数
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='要保留的天数，超过此天数的数据将被删除（默认为7天）'
        )

    def handle(self, *args, **options):
        # 获取要保留的天数
        days = options['days']
        
        logger.info(f'开始清理 {days} 天前的PLC数据记录...')
        self.stdout.write(f'开始清理 {days} 天前的PLC数据记录...')
        
        try:
            # 调用清理函数
            logger.info(f'调用清理函数，保留{days}天数据')
            result = clean_old_plc_data(days)
            
            # 输出结果
            logger.info(result['message'])
            if result['deleted_count'] > 0:
                self.stdout.write(self.style.SUCCESS(result['message']))
            else:
                self.stdout.write(self.style.WARNING(result['message']))
        except Exception as e:
            logger.error(f'清理PLC数据过程中发生错误: {str(e)}')
            import traceback
            logger.error(traceback.format_exc())
            self.stdout.write(self.style.ERROR(f'清理过程中发生错误: {str(e)}'))