import logging
from datetime import datetime
from django.db import transaction
from api.models import PLCData

logger = logging.getLogger(__name__)

class PLCDataFixer:
    """
    PLC数据修复工具类，用于处理PLC数据缺失的情况
    """
    
    @staticmethod
    def insert_date_with_fixed_date(insert_date, fixed_date):
        """
        将指定fixed_date的所有专有部分的制冷、制热模式数据作为insert_date的数据插入
        
        Args:
            insert_date: 要插入的目标日期，格式为YYYY-MM-DD
            fixed_date: 要复制数据的源日期，格式为YYYY-MM-DD
            
        Returns:
            dict: 包含处理结果的字典
        """
        try:
            # 解析日期字符串
            insert_date_obj = datetime.strptime(insert_date, '%Y-%m-%d').date()
            fixed_date_obj = datetime.strptime(fixed_date, '%Y-%m-%d').date()
            
            logger.info(f"开始修复PLC数据：将{fixed_date}的数据复制到{insert_date}")
            
            # 查询fixed_date的所有制冷、制热模式数据
            fixed_data = PLCData.objects.filter(
                usage_date=fixed_date_obj,
                energy_mode__in=['制冷', '制热']
            )
            
            logger.info(f"找到{fixed_data.count()}条{fixed_date}的数据记录")
            
            if fixed_data.count() == 0:
                logger.warning(f"未找到{fixed_date}的制冷、制热模式数据")
                return {
                    "success": False,
                    "message": f"未找到{fixed_date}的制冷、制热模式数据",
                    "affected_count": 0
                }
            
            # 准备插入的数据
            insert_records = []
            for record in fixed_data:
                # 创建新的记录，复制所有字段，除了id、created_at、updated_at和usage_date
                new_record = PLCData(
                    specific_part=record.specific_part,
                    plc_ip=record.plc_ip,
                    building=record.building,
                    unit=record.unit,
                    room_number=record.room_number,
                    energy_mode=record.energy_mode,
                    value=record.value,
                    usage_date=insert_date_obj
                )
                insert_records.append(new_record)
            
            # 批量插入数据
            with transaction.atomic():
                PLCData.objects.bulk_create(insert_records)
            
            logger.info(f"成功插入{len(insert_records)}条{insert_date}的数据记录")
            
            return {
                "success": True,
                "message": f"成功将{fixed_date}的数据复制到{insert_date}",
                "affected_count": len(insert_records)
            }
            
        except Exception as e:
            logger.error(f"修复PLC数据失败：{str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"修复PLC数据失败：{str(e)}",
                "affected_count": 0
            }
