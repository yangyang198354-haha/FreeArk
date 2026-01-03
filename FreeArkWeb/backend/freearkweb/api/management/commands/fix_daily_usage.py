"""
日用量数据修复命令

本命令用于修复 usage_quantity_daily 表中 final_energy 和 usage_quantity 字段为空的记录。
这通常发生在设备关机或数据采集异常后，系统无法获取到当天的能耗数据。

使用场景：
1. 设备关机后第二天没有 PLC 数据，导致当天的 final_energy 无法更新
2. 系统升级或数据迁移后，需要重新填充缺失的字段
3. 手动修复异常数据，确保数据完整性

修复逻辑：
- 对于 final_energy 为空的记录，使用 initial_energy 作为 final_energy 的值
- 将 usage_quantity 设为 0，表示当天设备未使用能源
- 使用事务确保修复过程的一致性

注意事项：
- 修复操作会修改数据库记录，请确保已备份重要数据
- 修复完成后建议重新计算月度用量数据
- 本命令只修复指定日期的记录，不影响其他日期
"""

import logging
from datetime import datetime, date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import UsageQuantityDaily
from .common import get_service_logger, log_service_start, log_service_stop, log_task_start, log_task_completion, log_error

# 获取配置好的日志器
logger = get_service_logger('fix_daily_usage')

class Command(BaseCommand):
    help = """
修复指定日期的日用量记录，将 final_energy 和 usage_quantity 字段填充完整

【使用场景】
当设备关机或数据采集异常时，PLCData 表中可能缺少某些 specific_part 的记录，
导致对应的 usage_quantity_daily 记录无法更新 final_energy 字段。
本命令用于修复这类数据完整性问题。

【使用示例】
python manage.py fix_daily_usage --date 2026-01-02

【修复逻辑】
- 查询指定日期下所有 final_energy 为空的记录
- 对于每条记录，使用 initial_energy 作为 final_energy
- 将 usage_quantity 设为 0（表示当天设备未使用能源）
- 批量更新这些记录

【注意事项】
- 修复操作会修改数据库记录，请确保已备份数据
- 修复完成后建议运行: python manage.py monthly_usage_service --month YYYY-MM --run-once
- 本命令只修复指定日期的记录，不影响其他日期的数据
"""
    
    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, required=True,
                          help='要修复的日期，格式为YYYY-MM-DD，例如：2026-01-02')
    
    def handle(self, *args, **options):
        fix_date_str = options['date']
        
        log_service_start(logger, '日用量数据修复服务')
        log_task_start(logger, f'修复{fix_date_str}的日用量记录')
        
        try:
            # 解析日期参数
            fix_date = datetime.strptime(fix_date_str, '%Y-%m-%d').date()
            
            # 查询指定日期下所有final_energy为空的记录
            incomplete_records = UsageQuantityDaily.objects.filter(
                time_period=fix_date,
                final_energy__isnull=True
            )
            
            total_records = incomplete_records.count()
            if total_records == 0:
                self.stdout.write(self.style.SUCCESS(f'✅ 未发现{fix_date_str}需要修复的记录'))
                log_task_completion(logger, '日用量数据修复', {
                    'success': True,
                    'affected_count': 0,
                    'message': f'未发现{fix_date_str}需要修复的记录'
                })
                return
            
            self.stdout.write(self.style.NOTICE(f'📋 发现{total_records}条需要修复的记录'))
            
            # 批量修复这些记录
            with transaction.atomic():
                update_list = []
                for record in incomplete_records:
                    # 打印修复记录的明细
                    self.stdout.write(f'   修复记录: specific_part={record.specific_part}, energy_mode={record.energy_mode}, initial_energy={record.initial_energy}')
                    logger.info(f'修复记录: specific_part={record.specific_part}, energy_mode={record.energy_mode}, initial_energy={record.initial_energy}')
                    
                    # 使用initial_energy作为final_energy，usage_quantity设为0
                    record.final_energy = record.initial_energy
                    record.usage_quantity = 0
                    update_list.append(record)
                
                if update_list:
                    UsageQuantityDaily.objects.bulk_update(
                        update_list,
                        ['final_energy', 'usage_quantity']
                    )
            
            # 输出修复结果
            self.stdout.write(self.style.SUCCESS(f'✅ 修复完成，共修复{len(update_list)}条记录'))
            self.stdout.write(self.style.SUCCESS(f'📊 修复日期: {fix_date_str}'))
            self.stdout.write(self.style.NOTICE('💡 修复完成后，建议运行以下命令重新计算月度用量:'))
            self.stdout.write(self.style.NOTICE(f'   python manage.py monthly_usage_service --month {fix_date_str[:7]} --run-once'))
            
            # 记录日志
            log_task_completion(logger, '日用量数据修复', {
                'success': True,
                'affected_count': len(update_list),
                'fix_date': fix_date_str
            })
            
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f'❌ 日期格式错误: {str(e)}'))
            self.stdout.write(self.style.NOTICE('💡 请使用YYYY-MM-DD格式的日期'))
            log_error(logger, '日期格式错误', e)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ 修复过程中发生错误: {str(e)}'))
            log_error(logger, '修复过程中发生错误', e)
        finally:
            log_service_stop(logger, '日用量数据修复服务')
