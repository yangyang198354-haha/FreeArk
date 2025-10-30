from datetime import datetime, timedelta
from .models import PLCData
from django.db.models import Q

def clean_old_plc_data(days: int = 7) -> dict:
    """
    清除PLC数据表中指定天数之前的记录
    
    Args:
        days: 要保留的天数，超过此天数的数据将被删除，默认为7天
    
    Returns:
        dict: 包含操作结果的字典，格式为 {"deleted_count": 删除的记录数, "message": 操作消息}
    """
    try:
        # 计算截止日期
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 统计要删除的记录数
        records_to_delete = PLCData.objects.filter(created_at__lt=cutoff_date)
        deleted_count = records_to_delete.count()
        
        # 执行删除操作
        if deleted_count > 0:
            records_to_delete.delete()
            return {
                "deleted_count": deleted_count,
                "message": f"成功删除 {deleted_count} 条 {days} 天前的PLC数据记录"
            }
        else:
            return {
                "deleted_count": 0,
                "message": f"没有找到 {days} 天前的PLC数据记录"
            }
    except Exception as e:
        return {
            "deleted_count": 0,
            "message": f"删除PLC数据时出错: {str(e)}"
        }