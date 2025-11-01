"""为improved_data_collection_manager.py添加main函数"""
import os
import argparse

def main():
    """主入口函数，供命令行调用"""
    parser = argparse.ArgumentParser(description='FreeArk 数据收集管理器')
    parser.add_argument('-f', '--file', type=str, required=False, default='all_owner.json', help='配置文件名')
    args = parser.parse_args()
    
    # 导入需要放在函数内部以避免循环导入
    from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager
    
    # 创建并启动管理器
    manager = ImprovedDataCollectionManager()
    manager.start()
    print(f"已启动数据收集管理器，配置文件：{args.file}")

# 确保模块被直接运行时也能工作
if __name__ == "__main__":
    main()
