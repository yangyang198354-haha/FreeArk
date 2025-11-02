import os
import logging
import schedule
import time
from datetime import datetime, date, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from api.daily_usage_utils import DailyUsageCalculator

# 配置日志，确保日志目录存在
log_dir = os.path.join(settings.BASE_DIR, 'logs')
os.makedirs(log_dir, exist_ok=True)

# 配置logger
logger = logging.getLogger('calculate_daily_usage')
logger.setLevel(logging.INFO)

# 确保logger没有现有的handler
if not logger.handlers:
    # 添加文件handler
    log_file = os.path.join(log_dir, 'calculate_daily_usage.log')
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
        logger.info('🚀 正在启动每日用量计算服务...')
        self.stdout.write(self.style.SUCCESS('🚀 正在启动每日用量计算服务...'))
        
        # 解析参数
        target_date_str = options.get('date')
        run_once = options.get('run_once', False)
        schedule_time = options.get('schedule-time', '00:01')
        
        logger.info(f'🔧 服务配置: date={target_date_str}, run_once={run_once}, schedule_time={schedule_time}')
        
        # 解析目标日期
        if target_date_str:
            try:
                logger.info(f'📅 解析指定日期: {target_date_str}')
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
                logger.info(f'✅ 成功解析日期: {target_date}')
            except ValueError:
                error_msg = '❌ 日期格式错误，请使用YYYY-MM-DD格式'
                logger.error(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
                return 1
        else:
            # 默认计算昨天的数据
            target_date = date.today() - timedelta(days=1)
            logger.info(f'📅 使用默认日期: {target_date} (昨天)')
        
        # 如果只运行一次
        if run_once:
            logger.info(f'📊 开始计算{target_date.strftime("%Y-%m-%d")}的用量数据...')
            self.stdout.write(f'📊 开始计算{target_date.strftime("%Y-%m-%d")}的用量数据...')
            self.calculate_daily_usage(target_date)
            logger.info('✅ 计算完成')
            self.stdout.write(self.style.SUCCESS('✅ 计算完成'))
            return 0
        
        # 设置定时任务
        logger.info(f'⏰ 已设置每日{schedule_time}自动计算用量数据')
        self.stdout.write(f'⏰ 已设置每日{schedule_time}自动计算用量数据')
        self.stdout.write(self.style.WARNING('⚠️  按 Ctrl+C 停止服务'))
        
        schedule.every().day.at(schedule_time).do(self.run_daily_job)
        logger.info(f'✅ 定时任务已配置: 每天{schedule_time}执行')
        
        # 立即执行一次
        logger.info('🔄 立即执行一次计算任务')
        self.run_daily_job()
        
        # 保持命令运行
        try:
            logger.info('🔄 服务已启动，进入调度循环')
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info('🛑 收到停止信号...')
            self.stdout.write('\n🛑 收到停止信号...')
        finally:
            logger.info('✅ 服务已停止')
            self.stdout.write('✅ 服务已停止')
        
        return 0
    
    def run_daily_job(self):
        """运行每日任务"""
        yesterday = date.today() - timedelta(days=1)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f'📊 [{current_time}] 开始计算{yesterday.strftime("%Y-%m-%d")}的用量数据...')
        self.stdout.write(f'📊 [{current_time}] 开始计算{yesterday.strftime("%Y-%m-%d")}的用量数据...')
        self.calculate_daily_usage(yesterday)
        logger.info(f'✅ [{current_time}] 计算完成')
        self.stdout.write(self.style.SUCCESS(f'✅ [{current_time}] 计算完成'))
    
    def calculate_daily_usage(self, target_date):
        """
        计算指定日期的每日用量数据
        """
        try:
            logger.info(f'🔄 开始调用DailyUsageCalculator计算{target_date}的用量数据')
            # 使用工具类进行计算，传入logger.info作为日志函数
            result = DailyUsageCalculator.calculate_daily_usage(
                target_date, 
                log_func=logger.info
            )
            
            # 记录处理结果
            logger.info(f'📊 处理完成 - 总共处理 {result["processed_count"]} 条特定部分记录')
            logger.info(f'📊 处理完成 - 新增当日记录 {result["created_count"]} 条')
            logger.info(f'📊 处理完成 - 更新当日记录 {result["updated_count"]} 条')
            logger.info(f'📊 处理完成 - 创建次日记录 {result["next_day_count"]} 条')
            
            # 输出详细处理结果到控制台
            self.stdout.write(f'📋 处理完成:')
            self.stdout.write(f'  ✅ 总共处理 {result["processed_count"]} 条特定部分记录')
            self.stdout.write(f'  ✅ 新增当日记录 {result["created_count"]} 条')
            self.stdout.write(f'  ✅ 更新当日记录 {result["updated_count"]} 条')
            self.stdout.write(f'  ✅ 创建次日记录 {result["next_day_count"]} 条')
            
        except Exception as e:
            error_msg = f"计算每日用量时发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            import traceback
            logger.error(traceback.format_exc())
            self.stdout.write(self.style.ERROR(f'❌ 计算过程中发生错误: {str(e)}'))
            raise