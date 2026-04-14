import logging
from datetime import datetime, date, timedelta
from django.db import transaction, close_old_connections
from django.utils import timezone
from api.models import PLCData, UsageQuantityDaily

# 注意：Django的时区处理 - 设置TIME_ZONE='Asia/Shanghai'且USE_TZ=True时，
# 数据库中存储UTC时间，但在Python代码中操作时会自动转换为本地时区

logger = logging.getLogger(__name__)

class DailyUsageCalculator:
    """
    每日用量计算工具类，包含共享的计算逻辑
    优化版本：针对大数据量场景优化了数据库查询和操作
    """
    
    # 批量处理的批次大小
    BATCH_SIZE = 100
    
    # 缓存已解析的specific_part结果，避免重复解析
    _specific_part_cache = {}

    @classmethod
    def calculate_daily_usage(cls, target_date, log_func=None, batch_size=None):
        """
        计算指定日期的每日用量数据（优化版）
        
        Args:
            target_date: 要计算的目标日期
            log_func: 日志记录函数，默认为logger.info
            batch_size: 批量处理的批次大小，默认使用类常量BATCH_SIZE
            
        Returns:
            dict: 包含处理结果统计的字典
        """
        # 如果没有提供日志函数，使用logger.info
        if log_func is None:
            log_func = logger.info
            
        # 使用提供的批次大小或默认值
        if batch_size is None:
            batch_size = cls.BATCH_SIZE
        
        try:
            # 关闭旧的数据库连接，确保使用新的有效连接
            close_old_connections()
            
            # 确保target_date带时区
            if isinstance(target_date, date) and not isinstance(target_date, datetime):
                # 如果是date对象，转换为带时区的datetime对象（当日的00:00:00）
                naive_datetime = datetime.combine(target_date, datetime.min.time())
                target_date = timezone.make_aware(naive_datetime)
            elif isinstance(target_date, datetime) and target_date.tzinfo is None:
                # 如果是不带时区的datetime对象，添加时区
                target_date = timezone.make_aware(target_date)
            
            log_func(f"计算日期: {target_date.date() if isinstance(target_date, datetime) else target_date}")
            
            # 获取次日日期
            if isinstance(target_date, datetime):
                next_day = (target_date + timedelta(days=1)).date()
            else:
                next_day = target_date + timedelta(days=1)
            
            processed_count = 0
            created_count = 0
            updated_count = 0
            next_day_count = 0
            
            # 使用target_date的日期部分
            target_date_value = target_date.date() if isinstance(target_date, datetime) else target_date
            
            # 缓存以提高性能
            cls._specific_part_cache.clear()
            
            # 优化：使用子查询和OuterRef获取每个(specific_part, energy_mode)组合的最新记录
            # 这样可以确保只获取每个组合的最新记录，避免重复数据
            log_func("获取每个特定部分和能源模式组合的最新记录")
            
            # 直接按目标日期过滤获取所有记录，因为每个 (specific_part, energy_mode) 在目标日期下只有一条记录
            latest_records_qs = PLCData.objects.filter(
                usage_date=target_date_value
            )
            
            # 批量处理结果
            total_records = latest_records_qs.count()
            log_func(f"共找到 {total_records} 条最新记录需要处理")
            
            # 分批处理以减少内存占用
            for i in range(0, total_records, batch_size):
                batch = latest_records_qs[i:i+batch_size]
                
                # 使用单个事务处理整个批次
                with transaction.atomic():
                    # 准备批量操作数据
                    daily_records_to_update = []
                    daily_records_to_create = []
                    next_day_records_to_create = []
                    next_day_records_to_update = []
                    
                    # 获取当前批次中所有specific_part和energy_mode的组合
                    batch_keys = [(record.specific_part, record.energy_mode) for record in batch]
                    
                    # 批量预取现有记录以减少数据库查询
                    # 预取目标日期的现有记录
                    current_day_existing_records = UsageQuantityDaily.objects.filter(
                        time_period=target_date_value,
                        specific_part__in=[key[0] for key in batch_keys],
                        energy_mode__in=[key[1] for key in batch_keys]
                    )
                    
                    # 创建现有记录的映射，用于O(1)查找
                    current_day_records_map = {(record.specific_part, record.energy_mode): record for record in current_day_existing_records}
                    
                    # 预取次日的现有记录
                    next_day_existing_records = UsageQuantityDaily.objects.filter(
                        time_period=next_day,
                        specific_part__in=[key[0] for key in batch_keys],
                        energy_mode__in=[key[1] for key in batch_keys]
                    )
                    
                    # 创建次日现有记录的映射
                    next_day_records_map = {(record.specific_part, record.energy_mode): record for record in next_day_existing_records}
                    
                    for latest_record in batch:
                        specific_part = latest_record.specific_part
                        energy_mode = latest_record.energy_mode
                        final_energy = latest_record.value
                        
                        log_func(f"处理: specific_part={specific_part}, energy_mode={energy_mode}, 值={final_energy}")
                        
                        # 使用缓存的解析结果
                        if specific_part not in cls._specific_part_cache:
                            cls._specific_part_cache[specific_part] = cls.parse_specific_part(specific_part)
                        building, unit, room_number = cls._specific_part_cache[specific_part]
                        
                        # 使用中文能源模式名称
                        mode_display = energy_mode
                        
                        # 查找是否已有当日记录
                        key = (specific_part, mode_display)
                        if key in current_day_records_map:
                            # 更新现有记录
                            daily_record = current_day_records_map[key]
                            daily_record.final_energy = final_energy
                            daily_record.usage_quantity = final_energy - daily_record.initial_energy
                            daily_records_to_update.append(daily_record)
                            updated_count += 1
                        else:
                            # 创建新记录
                            daily_records_to_create.append(UsageQuantityDaily(
                                time_period=target_date_value,
                                specific_part=specific_part,
                                energy_mode=mode_display,
                                building=building,
                                unit=unit,
                                room_number=room_number,
                                initial_energy=final_energy,
                                final_energy=final_energy,
                                usage_quantity=0
                            ))
                            created_count += 1
                        
                        # 处理次日记录
                        if key in next_day_records_map:
                            # 更新现有记录
                            next_record = next_day_records_map[key]
                            if not next_record.initial_energy:
                                next_record.initial_energy = final_energy
                                next_record.final_energy = None
                                next_record.usage_quantity = None
                                next_day_records_to_update.append(next_record)
                                next_day_count += 1
                        else:
                            # 创建次日新记录
                            next_day_records_to_create.append(UsageQuantityDaily(
                                time_period=next_day,
                                specific_part=specific_part,
                                energy_mode=mode_display,
                                building=building,
                                unit=unit,
                                room_number=room_number,
                                initial_energy=final_energy,
                                final_energy=None,
                                usage_quantity=None
                            ))
                            next_day_count += 1
                        
                        processed_count += 1
                    
                    # 批量保存记录（使用bulk_create和bulk_update提高性能）
                    if daily_records_to_create:
                        UsageQuantityDaily.objects.bulk_create(daily_records_to_create)
                    if daily_records_to_update:
                        UsageQuantityDaily.objects.bulk_update(
                            daily_records_to_update,
                            ['final_energy', 'usage_quantity']
                        )
                    if next_day_records_to_create:
                        UsageQuantityDaily.objects.bulk_create(next_day_records_to_create)
                    if next_day_records_to_update:
                        UsageQuantityDaily.objects.bulk_update(
                            next_day_records_to_update,
                            ['initial_energy', 'final_energy', 'usage_quantity']
                        )
            
            # 处理前一天有记录但final_energy为空的情况
            previous_day = target_date_value - timedelta(days=1)
            incomplete_records = UsageQuantityDaily.objects.filter(
                time_period=previous_day,
                final_energy__isnull=True
            )
            
            previous_day_updated = 0
            if incomplete_records.exists():
                log_func(f"处理前一天({previous_day})未完成记录，共 {incomplete_records.count()} 条")
                
                # 批量更新这些记录
                with transaction.atomic():
                    update_list = []
                    for record in incomplete_records:
                        # 打印未完成记录的明细
                        log_func(f"  处理未完成记录: specific_part={record.specific_part}, energy_mode={record.energy_mode}, initial_energy={record.initial_energy}")
                        record.final_energy = record.initial_energy
                        record.usage_quantity = 0
                        update_list.append(record)
                    if update_list:
                        UsageQuantityDaily.objects.bulk_update(
                            update_list,
                            ['final_energy', 'usage_quantity']
                        )
                        previous_day_updated = len(update_list)
                        log_func(f"  成功更新 {previous_day_updated} 条记录")
                log_func(f"已完成前一天未完成记录的处理")
            
            # 返回处理结果
            result = {
                'processed_count': processed_count,
                'created_count': created_count,
                'updated_count': updated_count + previous_day_updated,
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
    
    @classmethod
    def get_db_index_recommendations(cls):
        """
        获取数据库索引优化建议
        
        Returns:
            list: 索引创建SQL语句列表
        """
        return [
            # PLCData表索引优化
            "CREATE INDEX idx_plcdata_usage_date ON api_plcdata(usage_date);",
            "CREATE INDEX idx_plcdata_specific_part ON api_plcdata(specific_part);",
            "CREATE INDEX idx_plcdata_energy_mode ON api_plcdata(energy_mode);",
            "CREATE INDEX idx_plcdata_updated_at ON api_plcdata(updated_at);",
            "CREATE INDEX idx_plcdata_combined ON api_plcdata(usage_date, specific_part, energy_mode);",
            "CREATE INDEX idx_plcdata_combined_latest ON api_plcdata(usage_date, specific_part, energy_mode, updated_at);",
            
            # UsageQuantityDaily表索引优化
            "CREATE INDEX idx_usagequantitydaily_time_period ON api_usagequantitydaily(time_period);",
            "CREATE INDEX idx_usagequantitydaily_specific_part ON api_usagequantitydaily(specific_part);",
            "CREATE INDEX idx_usagequantitydaily_energy_mode ON api_usagequantitydaily(energy_mode);",
            "CREATE INDEX idx_usagequantitydaily_combined ON api_usagequantitydaily(time_period, specific_part, energy_mode);"
        ]
    
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
                # 如果是格式如"3-1-7-702" (楼栋-单元-楼层-房号)
                building = parts[0]
                unit = parts[1]
                room_number = parts[3]  # 第4部分是房号
            else:
                # 如果无法解析，使用默认值，specific_part作为room_number
                room_number = specific_part
        except Exception:
            # 解析失败时使用默认值
            room_number = specific_part
        
        return building, unit, room_number