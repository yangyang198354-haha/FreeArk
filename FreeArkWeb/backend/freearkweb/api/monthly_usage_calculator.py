import logging
from datetime import date, timedelta
from django.db.models import Min, Max, Sum
from django.db import transaction
from api.models import UsageQuantityDaily, UsageQuantityMonthly

# 获取logger
logger = logging.getLogger('monthly_usage_calculator')

class MonthlyUsageCalculator:
    """月度用量计算核心模块，负责从日用量数据聚合生成月度用量记录"""
    
    # 批量处理的批次大小
    BATCH_SIZE = 1000
    
    @staticmethod
    @transaction.atomic
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
            
            # 使用单个数据库查询同时获取所有聚合数据，避免Python内存计算和多次查询
            try:
                logger.info('🔎 开始查询日用量数据表...')
                
                # 直接在数据库层面进行分组和聚合计算，获取所需的所有数据
                aggregated_data = UsageQuantityDaily.objects.filter(
                    time_period__gte=month_start,
                    time_period__lt=next_month_start
                ).values('specific_part', 'building', 'unit', 'room_number', 'energy_mode').annotate(
                    min_initial_energy=Min('initial_energy'),
                    max_final_energy=Max('final_energy')
                )
                
                # 获取记录总数
                record_count = aggregated_data.count()
                logger.info(f'📋 查询完成，找到 {record_count} 个专有部分的日用量记录')
                
                if record_count == 0:
                    logger.warning(f'⚠️  未找到 {year}-{month} 月份的日用量记录，跳过计算')
                    return {"processed": 0, "created": 0, "updated": 0, "skipped": True}
                    
            except Exception as db_error:
                logger.error(f"❌ 数据库查询失败: {str(db_error)}")
                import traceback
                logger.error(f"数据库查询错误详情: {traceback.format_exc()}")
                raise
            
            # 准备批量操作的数据
            monthly_data_list = []
            lookup_keys = []
            month_str = f"{year}-{month:02d}"
            
            logger.info(f'🔄 开始处理 {record_count} 条记录...')
            
            # 构建月度数据列表
            for record in aggregated_data:
                specific_part = record['specific_part']
                building = record['building']
                unit = record['unit']
                room_number = record['room_number']
                energy_mode = record['energy_mode']
                
                # 直接使用数据库聚合的结果
                initial_energy = record['min_initial_energy'] or 0
                final_energy = record['max_final_energy'] or 0
                total_quantity = final_energy - initial_energy
                
                # 构建月度记录数据
                monthly_data = {
                    'specific_part': specific_part,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number,
                    'energy_mode': energy_mode,
                    'usage_quantity': total_quantity,
                    'usage_month': month_str,
                    'initial_energy': initial_energy,
                    'final_energy': final_energy
                }
                
                monthly_data_list.append(monthly_data)
                # 构建查找键用于批量获取现有记录
                lookup_keys.append((specific_part, energy_mode, month_str))
            
            # 批量处理更新和创建
            return MonthlyUsageCalculator._bulk_process_monthly_records(monthly_data_list, lookup_keys)
            
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
    
    @staticmethod
    @transaction.atomic
    def _bulk_process_monthly_records(monthly_data_list, lookup_keys):
        """批量处理月度记录的创建和更新
        
        Args:
            monthly_data_list: 月度记录数据列表
            lookup_keys: 用于查找现有记录的键列表
            
        Returns:
            dict: 处理结果统计
        """
        # 批量获取现有记录，构建查找字典
        existing_records = UsageQuantityMonthly.objects.filter(
            usage_month=monthly_data_list[0]['usage_month']
        ).values('specific_part', 'energy_mode', 'usage_month', 'id')
        
        # 创建查找字典
        existing_dict = {(r['specific_part'], r['energy_mode'], r['usage_month']): r['id'] 
                        for r in existing_records}
        
        # 分离需要创建和更新的记录
        to_create = []
        to_update = []
        updated_ids = []
        
        for monthly_data in monthly_data_list:
            key = (monthly_data['specific_part'], monthly_data['energy_mode'], monthly_data['usage_month'])
            if key in existing_dict:
                # 准备更新
                monthly_data['id'] = existing_dict[key]
                to_update.append(monthly_data)
                updated_ids.append(existing_dict[key])
            else:
                # 准备创建
                to_create.append(UsageQuantityMonthly(**monthly_data))
        
        # 批量创建新记录
        created_count = 0
        if to_create:
            # 分批创建，避免大数据量下的内存问题
            for i in range(0, len(to_create), MonthlyUsageCalculator.BATCH_SIZE):
                batch = to_create[i:i + MonthlyUsageCalculator.BATCH_SIZE]
                UsageQuantityMonthly.objects.bulk_create(batch)
                created_count += len(batch)
            logger.info(f'✅ 批量创建了 {created_count} 条月度用量记录')
        
        # 批量更新现有记录
        updated_count = 0
        if to_update:
            # 获取现有记录
            existing_objects = list(UsageQuantityMonthly.objects.filter(id__in=updated_ids))
            object_dict = {obj.id: obj for obj in existing_objects}
            
            # 更新对象
            for update_data in to_update:
                obj = object_dict[update_data['id']]
                for field, value in update_data.items():
                    if field != 'id':
                        setattr(obj, field, value)
            
            # 分批更新
            for i in range(0, len(existing_objects), MonthlyUsageCalculator.BATCH_SIZE):
                batch = existing_objects[i:i + MonthlyUsageCalculator.BATCH_SIZE]
                UsageQuantityMonthly.objects.bulk_update(
                    batch, 
                    ['usage_quantity', 'initial_energy', 'final_energy', 'building', 'unit', 'room_number']
                )
                updated_count += len(batch)
            logger.info(f'✅ 批量更新了 {updated_count} 条月度用量记录')
        
        processed_count = created_count + updated_count
        logger.info(f"📊 月度用量批量处理完成 - 处理总数: {processed_count}, 创建: {created_count}, 更新: {updated_count}")
        
        return {
            "processed": processed_count,
            "created": created_count,
            "updated": updated_count,
            "skipped": False
        }
    
    @staticmethod
    def get_db_index_recommendations():
        """获取数据库索引优化建议
        
        Returns:
            list: 索引创建SQL语句列表
        """
        return [
            # UsageQuantityDaily表索引建议 (已在模型中配置)
            "-- UsageQuantityDaily表索引已优化",
            "-- 现有索引包括: time_period, specific_part, energy_mode, time_period+specific_part+energy_mode",
            
            # UsageQuantityMonthly表额外索引建议
            "CREATE INDEX IF NOT EXISTS idx_usage_monthly_energy_mode ON usage_quantity_monthly(energy_mode);",
            "CREATE INDEX IF NOT EXISTS idx_usage_monthly_updated_at ON usage_quantity_monthly(updated_at);",
            "CREATE INDEX IF NOT EXISTS idx_usage_monthly_comprehensive ON usage_quantity_monthly(specific_part, energy_mode, usage_month);"
        ]