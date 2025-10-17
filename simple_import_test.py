import sys
import os

# 添加FreeArk目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("开始测试模块导入...")

try:
    # 测试导入log_config_manager
    from datacollection.log_config_manager import get_logger
    print("✅ 成功导入 log_config_manager 模块")
    
    # 测试导入improved_data_collection_manager
    from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
    print("✅ 成功导入 improved_data_collection_manager 模块")
    
    # 测试导入mqtt_client
    from datacollection.mqtt_client import MQTTClient
    print("✅ 成功导入 mqtt_client 模块")
    
    print("🎉 所有模块导入成功！")

except Exception as e:
    print(f"❌ 模块导入失败：{str(e)}")
    import traceback
    traceback.print_exc()