import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入improved_data_collection_manager模块
from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager

if __name__ == "__main__":
    print("正在执行improved_data_collection_manager的测试...")
    
    try:
        # 创建数据收集管理器实例
        manager = ImprovedDataCollectionManager(max_workers=10)
        manager.start()
        
        # 使用测试文件进行数据收集
        building_file = '3#_data_test.json'
        print(f"开始测试数据收集：使用测试文件 {building_file}")
        results = manager.collect_data_for_building(building_file)
        
        if results:
            print(f"成功收集到{len(results)}个设备的数据")
        else:
            print("未收集到任何数据")
            
    except Exception as e:
        print(f"程序执行异常：{str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保停止线程池
        manager.stop()
        print("测试完成")