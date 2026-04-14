import os
import sys
import time
from datetime import datetime, date, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import close_old_connections
import schedule
from api.monthly_usage_calculator import MonthlyUsageCalculator
# 导入统一的日志工具
from .common import get_service_logger, log_service_start, log_service_stop, log_task_start, log_task_completion, log_error

# 获取配置好的日志器
logger = get_service_logger('monthly_usage_service')

class Command(BaseCommand):
    help = '每月用量计算后台服务，可以周期性运行或手动执行'
    
    def add_arguments(self, parser):
        parser.add_argument('--day', type=int, default=1,
                          help='指定每月运行的日期，默认为1号')
        parser.add_argument('--time', type=str, default='00:00',
                          help='指定每天运行的时间，格式为HH:MM，默认为00:00')
        parser.add_argument('--run-once', action='store_true',
                          help='只运行一次，不启动持续服务')
        parser.add_argument('--month', type=str,
                          help='手动执行时指定计算月份，格式为YYYY-MM，默认为上个月')
    
    def handle(self, *args, **options):
        # 使用统一的日志方法
        service_config = {
            'day': options['day'],
            'time': options['time'],
            'run_once': options['run_once'],
            'month': options['month'] if options['month'] else '上个月(默认)'
        }
        log_service_start(logger, '每月用量计算后台服务', service_config)
        
        # 如果设置了只运行一次
        if options['run_once']:
            # 计算目标月份
            if options['month']:
                try:
                    # 解析月份字符串
                    year, month = map(int, options['month'].split('-'))
                    target_date = date(year, month, 1)
                except (ValueError, IndexError):
                    self.stdout.write(self.style.ERROR('月份格式错误，请使用YYYY-MM格式'))
                    return
            else:
                # 默认计算上个月的数据
                today = date.today()
                if today.month == 1:
                    target_date = date(today.year - 1, 12, 1)
                else:
                    target_date = date(today.year, today.month - 1, 1)
            
            log_task_start(logger, f'计算{target_date.strftime("%Y-%m")}的用量数据')
            self.calculate_monthly_usage(target_date)
            log_task_completion(logger, '单次计算')
            return
        
        # 设置定时任务
        run_day = options['day']
        run_time = options['time']
        logger.info(f'⏰ 服务已设置，每月 {run_day} 日 {run_time} 自动运行')
        
        # 由于schedule库不直接支持month，使用每天检查的方式实现每月执行
        # 每天检查是否是指定的日期，如果是则执行任务
        def check_and_run_monthly_task():
            today = date.today()
            if today.day == run_day:
                logger.info(f'📅 今天是每月{run_day}日，执行月度任务')
                self.monthly_job()
        
        # 每天定时检查
        schedule.every().day.at(run_time).do(check_and_run_monthly_task)
        
        # 立即运行一次
        log_task_start(logger, '首次计算任务')
        self.monthly_job()
        
        # 持续运行服务
        logger.info('🔄 服务已启动，按Ctrl+C停止')
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
        except KeyboardInterrupt:
            log_service_stop(logger, '每月用量计算后台服务')
            return
    
    def monthly_job(self):
        """每月定时任务，计算上个月的数据"""
        today = date.today()
        if today.month == 1:
            target_date = date(today.year - 1, 12, 1)
        else:
            target_date = date(today.year, today.month - 1, 1)
        
        log_task_start(logger, f'计算{target_date.strftime("%Y-%m")}的用量数据')
        self.calculate_monthly_usage(target_date)
    
    def calculate_monthly_usage(self, target_date):
        """计算指定月份的每月用量，从daily_quantity_usage表聚合数据并更新monthly_quantity_usage表
        
        调用外部模块MonthlyUsageCalculator来执行实际的计算逻辑
        """
        logger.info(f'🔍 开始月度用量计算流程 - 目标月份: {target_date.strftime("%Y-%m")}')
        
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 关闭旧的数据库连接，确保使用新的有效连接
            close_old_connections()
            
            # 调用外部模块进行计算
            result = MonthlyUsageCalculator.calculate_monthly_usage(target_date)
            
            # 计算耗时
            end_time = time.time()
            duration = end_time - start_time
            
            # 记录结果
            if 'error' in result:
                log_error(logger, f"计算过程中出错: {result['error']}, 耗时: {duration:.2f}秒")
            elif result.get('skipped', False):
                logger.info(f"⚠️  计算被跳过, 耗时: {duration:.2f}秒")
            else:
                result_info = {
                    "处理总数": result['processed'],
                    "创建": result['created'],
                    "更新": result['updated'],
                    "耗时": f"{duration:.2f}秒"
                }
                log_task_completion(logger, '月度用量计算', result_info)
                
        except Exception as e:
            log_error(logger, "调用计算模块时发生错误", e)
        finally:
            logger.info(f'🏁 月度用量计算流程结束 - 目标月份: {target_date.strftime("%Y-%m")}')

if __name__ == '__main__':
    # 允许直接运行此脚本
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
    django.setup()
    
    from django.core.management import execute_from_command_line
    execute_from_command_line(['django-admin', 'monthly_usage_service'])