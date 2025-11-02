import os
import sys
import time

# 处理PyInstaller打包后的资源文件路径
def get_resource_path(relative_path):
    """获取资源文件的绝对路径，支持PyInstaller打包环境"""
    try:
        # PyInstaller打包后的临时目录
        base_path = sys._MEIPASS
    except Exception:
        # 正常开发环境
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_path, relative_path)

# 添加FreeArk目录到Python路径，确保模块可以正确导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger
# 导入任务调度器
from datacollection.task_scheduler import TaskScheduler

# 获取logger
logger = get_logger('run_task_scheduler')


def main():
    """主函数"""
    print("🚀 任务调度器启动中...")
    print("📝 该程序将周期性调用ImprovedDataCollectionManager收集数据")
    print("💡 配置文件位于: resource/task_scheduler_config.json")
    print("🔄 按Ctrl+C停止程序")
    print("=" * 60)
    
    try:
        # 创建任务调度器实例
        scheduler = TaskScheduler()
        
        # 启动调度器
        scheduler.start()
        
        # 主循环，保持程序运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("📝 接收到用户中断，正在停止...")
    except Exception as e:
        logger.error(f"❌ 程序运行出错：{str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保调度器被停止
        if 'scheduler' in locals():
            scheduler.stop()
        print("📋 程序已退出")


if __name__ == "__main__":
    main()