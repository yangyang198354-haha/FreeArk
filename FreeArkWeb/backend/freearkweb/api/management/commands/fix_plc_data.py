"""
PLC数据修复命令

本命令用于修复PLCData表中缺失的数据，通过将指定日期的完整数据复制到缺失日期来填补数据空白。

使用场景：
1. 设备在某个日期没有正常采集PLC数据，导致数据缺失
2. 系统维护或故障期间数据采集中断，需要用已知正常的数据进行填充
3. 数据迁移或恢复过程中，需要重建缺失的PLC数据记录
4. 调试和测试时需要模拟特定的数据场景

修复逻辑：
- 从源日期（--fixed-date）获取所有有效的PLCData记录
- 将这些记录复制到目标日期（--insert-date）
- 保持原有的specific_part、initial_energy、final_energy等字段值
- 使用事务确保数据复制过程的一致性

注意事项：
- 修复操作会向数据库插入新记录，请确保操作前已备份重要数据
- 仅复制源日期存在的specific_part数据，源日期没有的设备数据不会在目标日期创建
- 修复完成后建议运行日用量计算服务来更新相关的usage_quantity_daily记录
- 本命令不处理最终能耗计算，仅负责PLC数据的复制和插入
"""


import logging
from django.core.management.base import BaseCommand
from api.plc_data_fix import PLCDataFixer
from .common import get_service_logger, log_service_start, log_service_stop, log_task_start, log_task_completion, log_error

# 获取配置好的日志器
logger = get_service_logger('fix_plc_data')

class Command(BaseCommand):
    help = """
    修复PLC数据，将指定日期的完整数据复制到缺失日期
    
    【使用场景】
    当设备在某个日期未能正常采集PLC数据时，可以使用本命令从已知的正常日期复制数据来填补空白。
    这在设备维护、故障恢复或数据迁移场景中特别有用。
    
    【使用示例】
    python manage.py fix_plc_data --insert-date 2026-01-02 --fixed-date 2026-01-01
    
    【修复逻辑】
    - 从源日期（--fixed-date）获取所有有效的PLCData记录
    - 将记录复制到目标日期（--insert-date），保持原有字段值
    - 使用事务确保复制过程的一致性
    
    【参数说明】
    --insert-date: 目标日期，要插入数据的日期，格式为YYYY-MM-DD
    --fixed-date: 源日期，要复制数据的来源日期，格式为YYYY-MM-DD
    
    【注意事项】
    - 修复操作会插入新记录到数据库，请确保已备份数据
    - 仅复制源日期存在的设备数据，不会创建源日期中没有的设备记录
    - 修复完成后建议运行: python manage.py daily_usage_service --date YYYY-MM-DD --run-once
    - 本命令仅负责PLC数据复制，不处理能耗计算和日用量统计
    """
    
    def add_arguments(self, parser):
        parser.add_argument('--insert-date', type=str, required=True,
                          help='''
要插入数据的目标日期，格式为YYYY-MM-DD

这是数据缺失的日期，需要从源日期复制数据来填充。
例如：2026-01-02 表示要修复2026年1月2日缺失的PLC数据。
                          ''')
        parser.add_argument('--fixed-date', type=str, required=True,
                          help='''
要复制数据的源日期，格式为YYYY-MM-DD

这是数据完整的日期，将从这个日期复制所有有效的PLCData记录。
例如：2026-01-01 表示从2026年1月1日复制数据。

注意：源日期必须包含有效的PLCData记录，否则复制操作将无法进行。
                          ''')
    
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
