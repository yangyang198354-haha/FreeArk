import logging
import schedule
import time
from datetime import datetime, date, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from api.daily_usage_utils import DailyUsageCalculator

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    Django管理命令：计算每日用量数据
    - 读取plc_data表中一个自然日的数据
    - 按照specific_part分组，找到累计制热量和制冷量的最早和最晚上报值
    - 在usage_quantity_daily表中查找当日记录，根据情况创建或更新记录
    - 创建次日记录，设置初始值为当日最晚上报值
    """
    help = '计算并更新每日用量数据'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='指定日期(YYYY-MM-DD)，默认为昨天')
        parser.add_argument('--run-once', action='store_true', help='仅运行一次，不启动周期性任务')
        parser.add_argument('--schedule-time', type=str, default='00:01', help='每日执行时间(HH:MM)，默认为凌晨00:01')

    def handle(self, *args, **options):
        """命令处理函数"""
        self.stdout.write(self.style.SUCCESS('🚀 正在启动每日用量计算服务...'))
        
        # 解析参数
        target_date_str = options.get('date')
        run_once = options.get('run_once', False)
        schedule_time = options.get('schedule-time', '00:01')
        
        # 解析目标日期
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR('❌ 日期格式错误，请使用YYYY-MM-DD格式'))
                return 1
        else:
            # 默认计算昨天的数据
            target_date = date.today() - timedelta(days=1)
        
        # 如果只运行一次
        if run_once:
            self.stdout.write(f'📊 开始计算{target_date.strftime("%Y-%m-%d")}的用量数据...')
            self.calculate_daily_usage(target_date)
            self.stdout.write(self.style.SUCCESS('✅ 计算完成'))
            return 0
        
        # 设置定时任务
        self.stdout.write(f'⏰ 已设置每日{schedule_time}自动计算用量数据')
        self.stdout.write(self.style.WARNING('⚠️  按 Ctrl+C 停止服务'))
        
        schedule.every().day.at(schedule_time).do(self.run_daily_job)
        
        # 立即执行一次
        self.run_daily_job()
        
        # 保持命令运行
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            self.stdout.write('\n⏸️  收到停止信号...')
        finally:
            self.stdout.write('✅ 服务已停止')
        
        return 0
    
    def run_daily_job(self):
        """运行每日任务"""
        yesterday = date.today() - timedelta(days=1)
        self.stdout.write(f'📊 [{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] 开始计算{yesterday.strftime("%Y-%m-%d")}的用量数据...')
        self.calculate_daily_usage(yesterday)
        self.stdout.write(self.style.SUCCESS(f'✅ [{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] 计算完成'))
    
    def calculate_daily_usage(self, target_date):
        """
        计算指定日期的每日用量数据，开发测试用
        """
        try:
            # 使用工具类进行计算，传入self.stdout.write作为日志函数以便在命令行显示
            result = DailyUsageCalculator.calculate_daily_usage(
                target_date, 
                log_func=lambda msg: self.stdout.write(msg)
            )
            
            # 输出详细处理结果到控制台
            self.stdout.write(f'📋 处理完成:')
            self.stdout.write(f'  ✅ 总共处理 {result["processed_count"]} 条特定部分记录')
            self.stdout.write(f'  ✅ 新增当日记录 {result["created_count"]} 条')
            self.stdout.write(f'  ✅ 更新当日记录 {result["updated_count"]} 条')
            self.stdout.write(f'  ✅ 创建次日记录 {result["next_day_count"]} 条')
            
        except Exception as e:
            logger.error(f"计算每日用量时发生错误: {str(e)}", exc_info=True)
            self.stdout.write(self.style.ERROR(f'❌ 计算过程中发生错误: {str(e)}'))
            raise