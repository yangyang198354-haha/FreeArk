import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
    from datacollection.mqtt_client import MQTTClient
    print("✅ 模块导入成功，缩进错误已修复！")
except Exception as e:
    print(f"❌ 模块导入失败：{str(e)}")