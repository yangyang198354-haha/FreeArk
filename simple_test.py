# 这是一个简单的测试文件，用于验证修复的模块是否可以导入

# 直接导入我们修复的两个模块
try:
    import sys
    import os
    
    # 添加FreeArk目录到Python路径
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    # 导入我们修复的模块
    from datacollection.log_config_manager import get_logger
    print("✅ 成功导入 log_config_manager 模块")
    
    # 创建一个logger实例来测试
    logger = get_logger('test_logger')
    logger.info("这是一条测试日志信息")
    print("✅ 成功创建并使用logger")
    
    # 测试是否可以导入修复的两个主要模块
    try:
        from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
        print("✅ 成功导入 improved_data_collection_manager 模块")
    except Exception as e:
        print(f"⚠️  导入 improved_data_collection_manager 模块失败：{str(e)}")
    
    try:
        from datacollection.mqtt_client import MQTTClient
        print("✅ 成功导入 mqtt_client 模块")
    except Exception as e:
        print(f"⚠️  导入 mqtt_client 模块失败：{str(e)}")
    
    print("✅ 测试完成，缩进错误修复验证结束")

except Exception as e:
    print(f"❌ 测试失败：{str(e)}")
    # 打印详细的错误信息，包括堆栈跟踪
    import traceback
    traceback.print_exc()