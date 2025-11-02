import os
import time
import logging
import schedule
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
    支持一次性执行或定时调度执行
    """
    help = '清除PLC数据表中指定天数之前的记录（支持一次性执行或定时调度）'

    def add_arguments(self, parser):
        # 添加可选参数，指定要保留的天数
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='要保留的天数，超过此天数的数据将被删除（默认为7天）'
        )
        # 添加定时执行相关参数
        parser.add_argument(
            '--run-once',
            action='store_true',
            default=True,
            help='仅执行一次清理任务后退出（默认）'
        )
        parser.add_argument(
            '--schedule',
            action='store_true',
            help='启动定时调度模式'
        )
        parser.add_argument(
            '--schedule-time',
            type=str,
            default='00:00',
            help='每日执行时间(HH:MM)，默认为凌晨00:00'
        )

    def handle(self, *args, **options):
        # 获取参数
        days = options['days']
        run_once = options['run-once']
        schedule_mode = options['schedule']
        schedule_time = options['schedule-time']
        
        # 如果指定了调度模式，则忽略--run-once
        if schedule_mode:
            run_once = False
            logger.info('🚀 启动PLC数据清理定时服务...')
            self.stdout.write(self.style.SUCCESS('🚀 启动PLC数据清理定时服务...'))
            logger.info(f'🔧 清理配置: 保留{days}天数据，每日{schedule_time}执行')
            self.stdout.write(f'🔧 清理配置: 保留{days}天数据，每日{schedule_time}执行')
            
            # 设置定时任务
            schedule.every().day.at(schedule_time).do(self._run_cleanup, days)
            logger.info(f'⏰ 已设置每日{schedule_time}自动清理数据')
            
            # 立即执行一次
            logger.info('🔄 立即执行一次清理任务')
            self._run_cleanup(days)
            
            # 保持命令运行
            try:
                logger.info('🔄 服务已启动，按Ctrl+C停止')
                self.stdout.write(self.style.WARNING('⚠️  按 Ctrl+C 停止服务'))
                while True:
                    schedule.run_pending()
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info('🛑 收到停止信号...')
                self.stdout.write('\n🛑 收到停止信号...')
            finally:
                logger.info('✅ 服务已停止')
                self.stdout.write('✅ 服务已停止')
        else:
            # 一次性执行模式
            self._run_cleanup(days)
    
    def _run_cleanup(self, days):
        """
        执行清理任务的内部方法
        """
        logger.info(f'📊 开始清理 {days} 天前的PLC数据记录...')
        self.stdout.write(f'📊 开始清理 {days} 天前的PLC数据记录...')
        
        try:
            # 调用清理函数
            logger.info(f'🔄 调用清理函数，保留{days}天数据')
            result = clean_old_plc_data(days)
            
            # 输出结果
            logger.info(f'📋 {result["message"]}')
            if result['deleted_count'] > 0:
                self.stdout.write(self.style.SUCCESS(result['message']))
            else:
                self.stdout.write(self.style.WARNING(result['message']))
        except Exception as e:
            error_msg = f"清理PLC数据过程中发生错误: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            self.stdout.write(self.style.ERROR(f'❌ 清理过程中发生错误: {str(e)}'))