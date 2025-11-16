import os
import sys
import time
import logging
from datetime import datetime, date, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
import schedule
from api.daily_usage_calculator import DailyUsageCalculator

# 获取配置好的日志器
logger = logging.getLogger('daily_usage_service')

class Command(BaseCommand):
    help = '每日用量计算后台服务，可以周期性运行或手动执行'
    
    def add_arguments(self, parser):
        parser.add_argument('--time', type=str, default='00:00',
                          help='指定每天运行的时间，格式为HH:MM，默认为00:00')
        parser.add_argument('--run-once', action='store_true',
                          help='只运行一次，不启动持续服务')
        parser.add_argument('--date', type=str,
                          help='手动执行时指定计算日期，格式为YYYY-MM-DD，默认为昨天')
    
    def handle(self, *args, **options):
        # 直接打印到控制台，确保服务正常启动
        print('🚀 每日用量计算后台服务启动')
        logger.info('🚀 每日用量计算后台服务启动')
        
        # 如果设置了只运行一次
        if options['run_once']:
            # 计算目标日期
            if options['date']:
                try:
                    target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
                except ValueError:
                    self.stdout.write(self.style.ERROR('日期格式错误，请使用YYYY-MM-DD格式'))
                    return 1
            else:
                # 默认计算昨天的数据
                target_date = date.today() - timedelta(days=1)
            
            logger.info(f'📊 开始计算{target_date}的用量数据')
            self.calculate_daily_usage(target_date)
            logger.info('✅ 单次计算完成，服务退出')
            return 0
        
        # 设置定时任务
        run_time = options['time']
        logger.info(f'⏰ 服务已设置，每天 {run_time} 自动运行')
        
        # 每天定时运行
        schedule.every().day.at(run_time).do(self.daily_job)
        
        # 立即运行一次
        logger.info('📊 立即运行一次计算任务')
        self.daily_job()
        
        # 持续运行服务
        logger.info('🔄 服务已启动，按Ctrl+C停止')
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
        except KeyboardInterrupt:
            logger.info('🛑 服务已停止')
            return 0
    
    def daily_job(self):
        """每日定时任务，计算昨天的数据"""
        target_date = date.today() - timedelta(days=1)
        logger.info(f'📊 开始计算{target_date}的用量数据')
        self.calculate_daily_usage(target_date)
    
    def calculate_daily_usage(self, target_date):
        """计算指定日期的每日用量，生产环境使用"""
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 使用工具类进行计算，使用logger.info作为日志函数
            result = DailyUsageCalculator.calculate_daily_usage(
                target_date, 
                log_func=logger.info
            )
            
            # 计算耗时
            end_time = time.time()
            duration = end_time - start_time
            
            # 记录处理结果和耗时
            logger.info(f"✅ 计算完成，耗时: {duration:.2f}秒")
            logger.info(f"📊 处理数据条数: {result.get('processed_count', 0)}条")
            logger.info(f"📈 新增记录: {result.get('created_count', 0)}条")
            logger.info(f"🔄 更新记录: {result.get('updated_count', 0)}条")
            logger.info(f"🔮 次日记录: {result.get('next_day_count', 0)}条")
            
        except Exception as e:
            logger.error(f"❌ 计算过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

if __name__ == '__main__':
    # 允许直接运行此脚本
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
    django.setup()
    
    from django.core.management import execute_from_command_line
    execute_from_command_line(['django-admin', 'daily_usage_service'])