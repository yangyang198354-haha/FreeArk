import os
import sys
import json
import time
import threading
from typing import Dict, List
import signal
import atexit

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
# 导入改进的数据收集管理器
from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager

# 获取logger
logger = get_logger('task_scheduler')

class TaskScheduler:
    def __init__(self):
        """初始化任务调度器"""
        self.config = {}
        self.scheduler_thread = None
        self.stop_event = threading.Event()
        self.data_collection_manager = ImprovedDataCollectionManager()
        self.load_config()
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        # 确保在程序退出时停止调度器
        atexit.register(self.stop)
    
    def _get_resource_dir(self):
        """获取资源目录，支持多种运行环境"""
        # 尝试从多个位置获取资源目录
        possible_dirs = [
            os.path.join(os.getcwd(), 'resource'),  # 当前工作目录下的resource
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource'),  # 项目resource目录
        ]
        
        # 优先选择存在的目录
        for dir_path in possible_dirs:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                return dir_path
        
        # 如果都不存在，返回当前工作目录
        return os.getcwd()
    
    def load_config(self):
        """加载任务调度器配置"""
        resource_dir = self._get_resource_dir()
        config_path = os.path.join(resource_dir, 'task_scheduler_config.json')
        
        # 默认配置
        default_config = {
            "scheduler": {
                "interval_seconds": 300,  # 默认5分钟执行一次
                "building_files": []
            }
        }
        
        if not os.path.exists(config_path):
            logger.warning(f"⚠️  配置文件不存在，使用默认配置：{config_path}")
            self.config = default_config
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                logger.info(f"✅ 成功加载任务调度器配置文件")
                # 验证配置结构
                if 'scheduler' not in self.config:
                    logger.warning("⚠️  配置文件格式不正确，缺少scheduler字段，使用默认配置")
                    self.config = default_config
                elif 'interval_seconds' not in self.config['scheduler']:
                    logger.warning("⚠️  配置文件缺少interval_seconds字段，使用默认值300秒")
                    self.config['scheduler']['interval_seconds'] = 300
                elif 'building_files' not in self.config['scheduler']:
                    logger.warning("⚠️  配置文件缺少building_files字段，使用空列表")
                    self.config['scheduler']['building_files'] = []
        except Exception as e:
            logger.error(f"❌ 加载配置文件失败，使用默认配置：{str(e)}")
            self.config = default_config
    
    def _run_task(self):
        """运行数据收集任务"""
        scheduler_config = self.config.get('scheduler', {})
        building_files = scheduler_config.get('building_files', [])
        
        if not building_files:
            logger.warning("⚠️  没有配置楼栋文件，跳过数据收集")
            return
        
        logger.info(f"🚀 开始执行周期性数据收集任务，共{len(building_files)}个楼栋文件")
        
        for building_file in building_files:
            try:
                logger.info(f"📁 开始处理楼栋文件：{building_file}")
                # 调用数据收集管理器的方法
                results = self.data_collection_manager.collect_data_for_building(building_file)
                if results:
                    logger.info(f"✅ 楼栋文件 {building_file} 处理完成")
                else:
                    logger.warning(f"⚠️  楼栋文件 {building_file} 处理失败或无数据")
            except Exception as e:
                logger.error(f"❌ 处理楼栋文件 {building_file} 时发生错误：{str(e)}")
        
        logger.info("📋 本轮数据收集任务执行完成")
    
    def _scheduler_loop(self):
        """调度器主循环"""
        scheduler_config = self.config.get('scheduler', {})
        interval_seconds = scheduler_config.get('interval_seconds', 300)
        
        logger.info(f"⏰ 任务调度器启动，运行间隔：{interval_seconds}秒")
        
        while not self.stop_event.is_set():
            try:
                # 立即执行一次任务
                self._run_task()
                
                # 等待下一次执行，同时监听停止信号
                if self.stop_event.wait(interval_seconds):
                    break
            except Exception as e:
                logger.error(f"❌ 调度器循环发生错误：{str(e)}")
                # 出错后等待一段时间再继续，避免频繁出错
                if self.stop_event.wait(30):  # 等待30秒
                    break
        
        logger.info("✅ 任务调度器已停止")
    
    def _signal_handler(self, sig, frame):
        """处理信号"""
        signal_name = signal.Signals(sig).name
        logger.info(f"⚠️  接收到信号 {signal_name}，正在停止调度器...")
        self.stop()
    
    def start(self):
        """启动任务调度器"""
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            logger.warning("⚠️  任务调度器已经在运行")
            return
        
        # 启动数据收集管理器
        self.data_collection_manager.start()
        
        # 重置停止事件
        self.stop_event.clear()
        
        # 创建并启动调度器线程
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("✅ 任务调度器已启动")
    
    def stop(self):
        """停止任务调度器"""
        if not self.scheduler_thread or not self.scheduler_thread.is_alive():
            logger.warning("⚠️  任务调度器未在运行")
            return
        
        # 设置停止事件
        self.stop_event.set()
        
        # 等待调度器线程结束
        if self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=10)  # 最多等待10秒
        
        # 停止数据收集管理器
        self.data_collection_manager.stop()
        
        logger.info("✅ 任务调度器已停止")
    
    def update_interval(self, interval_seconds: int):
        """更新调度间隔（下次启动时生效）"""
        if interval_seconds <= 0:
            logger.error("❌ 调度间隔必须大于0")
            return False
        
        self.config['scheduler']['interval_seconds'] = interval_seconds
        logger.info(f"✅ 更新调度间隔为：{interval_seconds}秒")
        return True
    
    def update_building_files(self, building_files: List[str]):
        """更新楼栋文件列表（下次启动时生效）"""
        self.config['scheduler']['building_files'] = building_files
        logger.info(f"✅ 更新楼栋文件列表，共{len(building_files)}个文件")
        return True


if __name__ == "__main__":
    # 创建并启动任务调度器
    scheduler = TaskScheduler()
    
    try:
        scheduler.start()
        logger.info("📝 任务调度器正在运行，按Ctrl+C停止...")
        
        # 主线程保持运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("📝 接收到用户中断，正在停止...")
    finally:
        scheduler.stop()
        logger.info("📋 程序已退出")