import logging
from datetime import date, timedelta
from django.db.models import Sum
from api.models import UsageQuantityDaily, UsageQuantityMonthly

# 获取logger
logger = logging.getLogger('monthly_usage_calculator')

class MonthlyUsageCalculator:
    """月度用量计算核心模块，负责从日用量数据聚合生成月度用量记录"""
    
    @staticmethod
    def calculate_monthly_usage(target_date):
        """计算指定月份的每月用量，从daily_quantity_usage表聚合数据并更新monthly_quantity_usage表
        
        Args:
            target_date: date类型，指定要计算的月份（通常是该月的第一天）
            
        Returns:
            dict: 包含处理结果的汇总信息
        """
        logger.info(f'🔍 开始月度用量计算流程 - 目标月份: {target_date.strftime("%Y-%m")}')
        
        try:
            # 验证目标日期格式
            if not isinstance(target_date, date):
                raise ValueError(f"目标日期必须是date类型，当前类型: {type(target_date)}")
            
            # 确定月份的开始和结束日期
            year = target_date.year
            month = target_date.month
            
            logger.debug(f'📊 正在处理年份: {year}, 月份: {month}')
            
            # 计算下个月的第一天
            if month == 12:
                next_month_start = date(year + 1, 1, 1)
            else:
                next_month_start = date(year, month + 1, 1)
            
            # 当前月的第一天
            month_start = date(year, month, 1)
            month_end = next_month_start - timedelta(days=1)
            
            logger.info(f'📅 计算时间范围: {month_start} 到 {month_end}')
            
            # 查询daily_quantity_usage表，按专有部分分组聚合
            try:
                logger.info('🔎 开始查询日用量数据表...')
                # 首先获取所有符合条件的日用量记录，用于后续处理
                all_daily_records = UsageQuantityDaily.objects.filter(
                    time_period__gte=month_start,
                    time_period__lt=next_month_start
                ).order_by('specific_part', 'building', 'unit', 'room_number', 'energy_mode', 'time_period')
                
                # 按专有部分分组聚合获取月度用量总量
                daily_records = UsageQuantityDaily.objects.filter(
                    time_period__gte=month_start,
                    time_period__lt=next_month_start
                ).values('specific_part', 'building', 'unit', 'room_number', 'energy_mode').annotate(
                    total_quantity=Sum('usage_quantity')
                )
                
                record_count = len(daily_records)
                logger.info(f'📋 查询完成，找到 {record_count} 个专有部分的日用量记录')
                
                if record_count == 0:
                    logger.warning(f'⚠️  未找到 {year}-{month} 月份的日用量记录，跳过计算')
                    return {"processed": 0, "created": 0, "updated": 0, "skipped": True}
                    
            except Exception as db_error:
                logger.error(f"❌ 数据库查询失败: {str(db_error)}")
                import traceback
                logger.error(f"数据库查询错误详情: {traceback.format_exc()}")
                raise
            
            # 处理每个专有部分的汇总数据
            processed_count = 0
            created_count = 0
            updated_count = 0
            
            logger.info(f'🔄 开始处理 {record_count} 条记录...')
            
            for record in daily_records:
                try:
                    specific_part = record['specific_part']
                    building = record['building']
                    unit = record['unit']
                    room_number = record['room_number']
                    energy_mode = record['energy_mode']
                    total_quantity = record['total_quantity']
                    
                    logger.debug(f'⚙️  处理{specific_part}、{energy_mode}，月度总量: {total_quantity}')
                    
                    # 获取该分组的最早日记录（用于初期能耗）和最晚日记录（用于末期能耗）
                    group_records = list(all_daily_records.filter(
                        specific_part=specific_part,
                        building=building,
                        unit=unit,
                        room_number=room_number,
                        energy_mode=energy_mode
                    ))
                    
                    # 从最早记录获取月度初期能耗，从最晚记录获取月度末期能耗
                    initial_energy = group_records[0].initial_energy if group_records else 0.0
                    final_energy = group_records[-1].final_energy if group_records else 0.0
                    
                    logger.debug(f'⚙️  处理{specific_part}、{energy_mode}，月度总量: {total_quantity}, 初期能耗: {initial_energy}, 末期能耗: {final_energy}')
                    
                    # 构建月度记录数据
                    monthly_data = {
                        'specific_part': specific_part,
                        'building': building,
                        'unit': unit,
                        'room_number': room_number,
                        'energy_mode': energy_mode,
                        'usage_quantity': total_quantity,
                        'usage_month': f"{year}-{month:02d}",
                        'initial_energy': initial_energy,  # 使用该分组最早日记录的初期能耗
                        'final_energy': final_energy      # 使用该分组最晚日记录的末期能耗
                    }
                    
                    # 查找或创建月度记录
                    monthly_record, created = UsageQuantityMonthly.objects.update_or_create(
                        specific_part=specific_part,
                        energy_mode=energy_mode,
                        usage_month=monthly_data['usage_month'],
                        defaults=monthly_data
                    )
                    
                    if not created:
                        # 更新现有记录
                        monthly_record.usage_quantity = total_quantity
                        monthly_record.save()
                        updated_count += 1
                        logger.info(f'✅ 更新了{specific_part}、{energy_mode}的月度用量记录: {total_quantity}')
                    else:
                        created_count += 1
                        logger.info(f'✅ 为{specific_part}、{energy_mode}创建了月度用量记录: {total_quantity}')
                    
                    processed_count += 1
                    
                except Exception as record_error:
                    logger.error(f"❌ 处理{specific_part}、{energy_mode}的记录时出错: {str(record_error)}")
                    import traceback
                    logger.error(f"记录处理错误详情: {traceback.format_exc()}")
                    # 继续处理下一条记录
                    continue
            
            # 记录汇总信息
            logger.info(f"📊 月度用量计算完成 - 处理总数: {processed_count}, 创建: {created_count}, 更新: {updated_count}")
            
            return {
                "processed": processed_count,
                "created": created_count,
                "updated": updated_count,
                "skipped": False
            }
            
        except ValueError as val_error:
            logger.error(f"❌ 参数错误: {str(val_error)}")
            return {"processed": 0, "created": 0, "updated": 0, "error": str(val_error)}
        except Exception as e:
            logger.error(f"❌ 月度用量计算过程中发生未预期错误: {str(e)}")
            import traceback
            logger.error(f"未预期错误详情: {traceback.format_exc()}")
            return {"processed": 0, "created": 0, "updated": 0, "error": str(e)}
        finally:
            logger.info(f'🏁 月度用量计算流程结束 - 目标月份: {target_date.strftime("%Y-%m")}')