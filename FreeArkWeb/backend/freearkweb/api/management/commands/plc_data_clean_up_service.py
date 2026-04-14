import os
import schedule
import time
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from api.plc_data_cleaner import clean_old_plc_data
# 导入统一的日志工具
from .common import get_service_logger, log_service_start, log_service_stop, log_task_start, log_task_completion, log_error, log_warning

# 获取配置好的日志器
logger = get_service_logger('plc_cleanup_service')

class Command(BaseCommand):
    """
    Django管理命令，用于定时调度PLC数据清理任务
    可以配置运行频率，如每周日凌晨0点0分自动清理数据
    """
    help = '启动PLC数据定时清理服务，可以配置运行频率'

    def add_arguments(self, parser):
        # 添加可选参数
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='要保留的天数，超过此天数的数据将被删除（默认为7天）'
        )
        parser.add_argument(
            '--cron',
            type=str,
            default='0 2 * * 0',  # 默认每周日凌晨2点0分
            help='cron表达式，格式为 "分 时 日 月 周"（默认为 "0 2 * * 0"，即每周日凌晨2点0分）'
        )
        parser.add_argument(
            '--interval',
            type=str,
            default=None,
            help='间隔时间，例如 "daily"、"weekly"、"monday" 等（优先级低于cron表达式）'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='仅执行一次清理任务后退出'
        )

    def handle(self, *args, **options):
        days = options['days']
        cron_expr = options['cron']
        interval = options['interval']
        run_once = options['once']
        
        logger.info('启动PLC数据清理服务...')
        logger.info(f'清理配置: 保留{days}天数据')
        # 使用统一的日志方法
        service_config = {
            'days_to_keep': f'{days}天',
        }
        log_service_start(logger, 'PLC数据清理服务', service_config)
        
        # 如果指定了--once参数，则立即执行一次清理并退出
        if run_once:
            log_task_start(logger, '执行一次性清理任务')
            self.run_cleanup_task(days)
            return
        
        # 配置定时任务
        logger.info('⏰ 正在配置定时任务...')
        self.setup_schedule(cron_expr, interval, days)
        
        # 启动调度循环
        try:
            logger.info('调度服务已启动，按Ctrl+C退出')
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            log_task_start(logger, 'PLC数据清理服务停止')
            logger.info('收到终止信号，服务正在停止...')
        finally:
            log_task_completion(logger, 'PLC数据清理服务停止')
            logger.info('PLC数据清理服务已停止')
    
    def run_cleanup_task(self, days):
        """
        执行清理任务
        """
        try:
            log_task_start(logger, f'PLC数据清理任务，保留{days}天数据')
            
            result = clean_old_plc_data(days)
            log_task_completion(logger, 'PLC数据清理', {"message": result["message"]})
            self.stdout.write(f'{datetime.now()} - {result["message"]}')
        except Exception as e:
            log_error(logger, '执行PLC数据清理任务时出错', e)
            self.stderr.write(f'执行PLC数据清理任务时出错: {str(e)}')
    
    def setup_schedule(self, cron_expr, interval, days):
        """
        配置定时任务
        支持cron表达式和简单的时间间隔
        """
        # 优先使用cron表达式
        if cron_expr:
            try:
                logger.info(f'⏰ 尝试使用cron表达式: {cron_expr}')
                self._schedule_with_cron(cron_expr, days)
                logger.info(f'✅ 已配置cron表达式: {cron_expr}')
                self.stdout.write(f'✅ 已配置cron表达式: {cron_expr}')
                return
            except Exception as e:
                log_warning(logger, f'cron表达式解析失败: {str(e)}，尝试使用间隔时间配置')
            self.stdout.write(self.style.WARNING(f'⚠️ cron表达式解析失败: {str(e)}，尝试使用间隔时间配置'))
        
        # 使用简单的时间间隔
        if interval:
            logger.info(f'⏰ 尝试使用时间间隔: {interval}')
            self._schedule_with_interval(interval, days)
            logger.info(f'✅ 已配置时间间隔: {interval}')
            self.stdout.write(f'✅ 已配置时间间隔: {interval}')
        else:
            # 默认配置：每周日凌晨0点0分
            logger.info(f'⏰ 使用默认配置: 每周日凌晨00:00')
            schedule.every().sunday.at("00:00").do(self.run_cleanup_task, days=days)
            logger.info('✅ 已配置默认执行时间: 每周日凌晨00:00')
            self.stdout.write(f'✅ 已配置默认执行时间: 每周日凌晨00:00')
    
    def _schedule_with_cron(self, cron_expr, days):
        """
        根据cron表达式配置定时任务
        cron表达式格式: "分 时 日 月 周"
        """
        try:
            logger.info(f'🔍 解析cron表达式: {cron_expr}')
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                raise ValueError('cron表达式格式不正确，应为 "分 时 日 月 周"')
            
            minute, hour, day, month, weekday = parts
            logger.info(f'📝 解析结果: 分={minute}, 时={hour}, 日={day}, 月={month}, 周={weekday}')
            
            # 简单实现常用的cron格式
            # 这里只实现了基本的数字匹配，没有支持星号、逗号、连字符等复杂语法
            
            # 处理时间部分（小时和分钟）
            job = schedule.every()
            
            # 处理星期
            weekday_map = {
                '0': 'sunday', '1': 'monday', '2': 'tuesday', '3': 'wednesday',
                '4': 'thursday', '5': 'friday', '6': 'saturday', '7': 'sunday',
                'sun': 'sunday', 'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday',
                'thu': 'thursday', 'fri': 'friday', 'sat': 'saturday'
            }
            
            if weekday.lower() in weekday_map:
                weekday_name = weekday_map[weekday.lower()]
                logger.info(f'🔄 转换星期值: {weekday} -> {weekday_name}')
                job = getattr(job, weekday_name)
            elif weekday == '*':
                logger.info(f'🔄 使用通配符，设置为每天执行')
                job = job.day
            else:
                raise ValueError(f'无效的星期值: {weekday}')
            
            # 设置具体时间
            scheduled_time = f"{int(hour):02d}:{int(minute):02d}"
            job.at(scheduled_time).do(self.run_cleanup_task, days=days)
            logger.info(f'✅ 已配置定时任务在{weekday}的{scheduled_time}执行')
            
        except Exception as e:
            logger.error(f'❌ 解析cron表达式时出错: {str(e)}')
            raise ValueError(f'解析cron表达式时出错: {str(e)}')
    
    def _schedule_with_interval(self, interval, days):
        """
        根据简单的时间间隔配置定时任务
        """
        interval = interval.lower()
        job = schedule.every()
        scheduled_time = "00:00"
        
        if interval == 'daily':
            logger.info(f'📅 配置每日执行: 每天{scheduled_time}')
            job.day.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'weekly':
            logger.info(f'📅 配置每周执行: 每周{scheduled_time}')
            job.week.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'monday':
            logger.info(f'📅 配置周一执行: 每周一{scheduled_time}')
            job.monday.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'tuesday':
            logger.info(f'📅 配置周二执行: 每周二{scheduled_time}')
            job.tuesday.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'wednesday':
            logger.info(f'📅 配置周三执行: 每周三{scheduled_time}')
            job.wednesday.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'thursday':
            logger.info(f'📅 配置周四执行: 每周四{scheduled_time}')
            job.thursday.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'friday':
            logger.info(f'📅 配置周五执行: 每周五{scheduled_time}')
            job.friday.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'saturday':
            logger.info(f'📅 配置周六执行: 每周六{scheduled_time}')
            job.saturday.at(scheduled_time).do(self.run_cleanup_task, days=days)
        elif interval == 'sunday':
            logger.info(f'📅 配置周日执行: 每周日{scheduled_time}')
            job.sunday.at(scheduled_time).do(self.run_cleanup_task, days=days)
        else:
            log_warning(logger, f'未知的时间间隔: {interval}，使用默认配置')
            job.sunday.at(scheduled_time).do(self.run_cleanup_task, days=days)