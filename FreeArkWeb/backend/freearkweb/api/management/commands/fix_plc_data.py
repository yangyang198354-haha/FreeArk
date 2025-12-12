import logging
from django.core.management.base import BaseCommand
from api.plc_data_fix import PLCDataFixer
from .common import get_service_logger, log_service_start, log_service_stop, log_task_start, log_task_completion, log_error

# 获取配置好的日志器
logger = get_service_logger('fix_plc_data')

class Command(BaseCommand):
    help = '修复PLC数据，将指定日期的数据复制到缺失日期'
    
    def add_arguments(self, parser):
        parser.add_argument('--insert-date', type=str, required=True,
                          help='要插入数据的目标日期，格式为YYYY-MM-DD')
        parser.add_argument('--fixed-date', type=str, required=True,
                          help='要复制数据的源日期，格式为YYYY-MM-DD')
    
    def handle(self, *args, **options):
        insert_date = options['insert_date']
        fixed_date = options['fixed_date']
        
        log_service_start(logger, 'PLC数据修复服务')
        log_task_start(logger, f'将{fixed_date}的数据复制到{insert_date}')
        
        try:
            # 调用PLCDataFixer的方法进行数据修复
            result = PLCDataFixer.insert_date_with_fixed_date(insert_date, fixed_date)
            
            if result['success']:
                self.stdout.write(self.style.SUCCESS(f'✅ 数据修复成功: {result["message"]}'))
                self.stdout.write(self.style.SUCCESS(f'📊 影响记录数: {result["affected_count"]}'))
                self.stdout.write(self.style.NOTICE('💡 修复完成后，建议运行以下命令重新计算日用量:'))
                self.stdout.write(self.style.NOTICE(f'   python manage.py daily_usage_service --date {insert_date} --run-once'))
            else:
                self.stdout.write(self.style.ERROR(f'❌ 数据修复失败: {result["message"]}'))
            
            log_task_completion(logger, 'PLC数据修复', {
                'success': result['success'],
                'affected_count': result['affected_count'],
                'message': result['message']
            })
            
        except Exception as e:
            log_error(logger, 'PLC数据修复过程中发生错误', e)
            self.stdout.write(self.style.ERROR(f'❌ 数据修复过程中发生错误: {str(e)}'))
        
        log_service_stop(logger, 'PLC数据修复服务')
