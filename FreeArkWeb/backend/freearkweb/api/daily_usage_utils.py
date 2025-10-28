import logging
from datetime import datetime, date, timedelta
from django.db import transaction
from django.utils import timezone
from api.models import PLCData, UsageQuantityDaily

logger = logging.getLogger(__name__)

class DailyUsageCalculator:
    """
    每日用量计算工具类，包含共享的计算逻辑
    """
    # 不再使用硬编码的特定部分列表，改为动态从数据库获取
    
    @classmethod
    def calculate_daily_usage(cls, target_date, log_func=None):
        """
        计算指定日期的每日用量数据
        
        Args:
            target_date: 要计算的目标日期
            log_func: 日志记录函数，默认为logger.info
            
        Returns:
            dict: 包含处理结果统计的字典
        """
        # 如果没有提供日志函数，使用logger.info
        if log_func is None:
            log_func = logger.info
        
        try:
            # 使用带时区的datetime
            naive_start = datetime.combine(target_date, datetime.min.time())
            naive_end = datetime.combine(target_date, datetime.max.time())
            start_datetime = timezone.make_aware(naive_start)
            end_datetime = timezone.make_aware(naive_end)
            
            log_func(f"计算日期: {target_date}")
            log_func(f"时间范围: {start_datetime} - {end_datetime}")
            
            # 获取次日日期
            next_day = target_date + timedelta(days=1)
            
            processed_count = 0
            created_count = 0
            updated_count = 0
            next_day_count = 0
            
            # 动态获取指定日期前一个自然日的所有unique specific_part值
            specific_parts = PLCData.objects.filter(
                created_at__range=(start_datetime, end_datetime)
            ).values_list('specific_part', flat=True).distinct()
            
            log_func(f"从数据库获取到 {len(specific_parts)} 个特定部分需要处理")
            
            # 遍历所有特定部分
            for specific_part in specific_parts:
                # 处理制冷和制热两种模式
                for energy_mode in ['制冷', '制热']:
                    log_func(f"正在处理: specific_part={specific_part}, energy_mode={energy_mode}")
                    
                    # 获取该特定部分和模式的所有记录
                    plc_records = PLCData.objects.filter(
                        specific_part=specific_part,
                        energy_mode=energy_mode
                    ).order_by('created_at')
                    
                    log_func(f"找到 {plc_records.count()} 条PLC记录")
                    
                    if not plc_records.exists():
                        log_func(f"没有找到 specific_part={specific_part}, energy_mode={energy_mode} 的记录")
                        continue
                    
                    # 获取最早和最晚上报值
                    earliest_record = plc_records.first()
                    latest_record = plc_records.last()
                    
                    initial_energy = earliest_record.value
                    final_energy = latest_record.value
                    usage_quantity = final_energy - initial_energy
                    
                    log_func(f"初始值: {initial_energy}, 最终值: {final_energy}, 用量: {usage_quantity}")
                    
                    # 使用中文能源模式名称
                    mode_display = energy_mode
                    
                    # 解析specific_part获取building、unit、room_number
                    building, unit, room_number = cls.parse_specific_part(specific_part)
                    
                    # 使用事务处理，确保数据一致性
                    with transaction.atomic():
                        # 查找是否已有当日记录
                        daily_record, created = UsageQuantityDaily.objects.get_or_create(
                            time_period=target_date,
                            specific_part=specific_part,
                            energy_mode=mode_display,
                            defaults={
                                'building': building,
                                'unit': unit,
                                'room_number': room_number,
                                'initial_energy': initial_energy,
                                'final_energy': final_energy,
                                'usage_quantity': usage_quantity
                            }
                        )
                        
                        # 如果记录已存在，更新最终值和用量
                        if not created:
                            daily_record.final_energy = final_energy
                            daily_record.usage_quantity = final_energy - daily_record.initial_energy
                            daily_record.save()
                            updated_count += 1
                        else:
                            created_count += 1
                        
                        # 创建次日记录，初始值为当日最终值
                        next_record, created = UsageQuantityDaily.objects.get_or_create(
                            time_period=next_day,
                            specific_part=specific_part,
                            energy_mode=mode_display,
                            defaults={
                                'building': building,
                                'unit': unit,
                                'room_number': room_number,
                                'initial_energy': final_energy,
                                'final_energy': final_energy,  # 设置为与初始值相同，避免NULL错误
                                'usage_quantity': 0
                            }
                        )
                        
                        if created or not next_record.initial_energy:
                            next_record.initial_energy = final_energy
                            next_record.save()
                            next_day_count += 1
                        
                        processed_count += 1
            
            # 返回处理结果
            result = {
                'processed_count': processed_count,
                'created_count': created_count,
                'updated_count': updated_count,
                'next_day_count': next_day_count
            }
            
            # 输出处理结果
            log_func(f"📋 处理完成:")
            log_func(f"  ✅ 总共处理 {processed_count} 条特定部分记录")
            log_func(f"  ✅ 新增当日记录 {created_count} 条")
            log_func(f"  ✅ 更新当日记录 {updated_count} 条")
            log_func(f"  ✅ 创建次日记录 {next_day_count} 条")
            log_func("✅ 计算完成")
            
            return result
            
        except Exception as e:
            error_msg = f"❌ 计算过程中发生错误: {str(e)}"
            log_func(error_msg)
            logger.error(error_msg, exc_info=True)
            raise
    
    @staticmethod
    def parse_specific_part(specific_part):
        """
        解析specific_part获取building、unit、room_number
        假设格式为"building-unit-room_number"或直接是房间标识符
        """
        # 默认值
        building = ""
        unit = ""
        room_number = ""
        
        try:
            # 尝试解析格式"building-unit-room_number"
            parts = specific_part.split('-')
            if len(parts) == 3:
                building, unit, room_number = parts
            elif len(parts) == 4:
                # 如果是格式如"9-1-31-3104"
                building = parts[0]
                unit = parts[1]
                room_number = parts[2]
            else:
                # 如果无法解析，使用默认值，specific_part作为room_number
                room_number = specific_part
        except Exception:
            # 解析失败时使用默认值
            room_number = specific_part
        
        return building, unit, room_number