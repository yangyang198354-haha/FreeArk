import os
import sys
import json
import time
import threading
from typing import Dict, List, Optional, Set
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


class IntervalGroup:
    """表示一个频率分组：包含参数名集合与调度间隔"""

    def __init__(self, name: str, interval_seconds: int, param_names: List[str]):
        self.name = name
        self.interval_seconds = interval_seconds
        # param_names 含 "*" 时表示通配符（由 TaskScheduler 负责在运行时展开）
        self.param_names: List[str] = param_names

    def is_wildcard(self) -> bool:
        return "*" in self.param_names

    def __repr__(self):
        return (f"IntervalGroup(name={self.name!r}, interval={self.interval_seconds}s, "
                f"params={self.param_names!r})")


class TaskScheduler:
    def __init__(self):
        """初始化任务调度器"""
        self.config: Dict = {}
        self.stop_event = threading.Event()
        self.group_threads: List[threading.Thread] = []
        self.data_collection_manager: Optional[ImprovedDataCollectionManager] = None
        self.load_config()

        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        # 确保在程序退出时停止调度器
        atexit.register(self.stop)

    # ------------------------------------------------------------------
    # 配置相关
    # ------------------------------------------------------------------

    def _get_resource_dir(self) -> str:
        """获取资源目录，支持多种运行环境"""
        possible_dirs = [
            os.path.join(os.getcwd(), 'resource'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource'),
        ]
        for dir_path in possible_dirs:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                return dir_path
        return os.getcwd()

    def load_config(self):
        """加载任务调度器配置"""
        resource_dir = self._get_resource_dir()
        config_path = os.path.join(resource_dir, 'task_scheduler_config.json')

        default_config = {
            "scheduler": {
                "interval_seconds": 300,
                "building_files": [],
                "thread_pool_size": 10
            }
        }

        if not os.path.exists(config_path):
            logger.warning(f"配置文件不存在，使用默认配置：{config_path}")
            self.config = default_config
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                logger.info("成功加载任务调度器配置文件")
                sched = self.config.get('scheduler', {})
                if not sched:
                    logger.warning("配置文件缺少 scheduler 字段，使用默认配置")
                    self.config = default_config
                else:
                    # 填充缺失的默认值
                    sched.setdefault('interval_seconds', 300)
                    sched.setdefault('building_files', [])
                    sched.setdefault('thread_pool_size', 10)
        except Exception as e:
            logger.error(f"加载配置文件失败，使用默认配置：{str(e)}")
            self.config = default_config

    def _resolve_interval_groups(self) -> List[IntervalGroup]:
        """解析配置中的 interval_groups，返回 IntervalGroup 列表。

        若配置中不存在 interval_groups，则退化为单组（全部参数，使用 interval_seconds）。
        通配符 "*" 组：param_names 被替换为「所有参数中不属于其他具名组的参数集合」。
        """
        sched = self.config.get('scheduler', {})
        raw_groups = sched.get('interval_groups')

        if not raw_groups:
            # 向后兼容：单频率模式
            interval = sched.get('interval_seconds', 300)
            logger.info(f"未配置 interval_groups，使用单频率模式（{interval}s，全部参数）")
            return [IntervalGroup(name='default', interval_seconds=interval, param_names=['*'])]

        groups = [
            IntervalGroup(
                name=g.get('name', f'group_{i}'),
                interval_seconds=int(g.get('interval_seconds', 300)),
                param_names=list(g.get('param_names', ['*']))
            )
            for i, g in enumerate(raw_groups)
        ]

        # 展开通配符：先收集所有明确指定的参数名
        all_plc_params = self._load_all_param_names()
        named_params: Set[str] = set()
        for g in groups:
            if not g.is_wildcard():
                named_params.update(g.param_names)

        wildcard_params = all_plc_params - named_params

        for g in groups:
            if g.is_wildcard():
                g.param_names = list(wildcard_params)
                logger.info(
                    f"IntervalGroup '{g.name}' 通配符展开：{len(g.param_names)} 个参数"
                )

        # 过滤掉展开后为空的组
        valid_groups = [g for g in groups if g.param_names]
        if not valid_groups:
            logger.warning("所有 IntervalGroup 展开后均为空，退化为全参数单频率模式")
            interval = sched.get('interval_seconds', 300)
            return [IntervalGroup(name='default', interval_seconds=interval, param_names=list(all_plc_params))]

        for g in valid_groups:
            logger.info(f"  - {g}")

        return valid_groups

    def _load_all_param_names(self) -> Set[str]:
        """从 plc_config.json 加载所有参数名"""
        if self.data_collection_manager:
            params = self.data_collection_manager.load_plc_config()
            return set(params.keys())
        # data_collection_manager 还未初始化时，临时加载
        resource_dirs = [
            os.path.join(os.getcwd(), 'resource'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource'),
        ]
        for d in resource_dirs:
            p = os.path.join(d, 'plc_config.json')
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return set(data.get('parameters', {}).keys())
                except Exception:
                    pass
        logger.warning("无法加载 plc_config.json，param 集合为空")
        return set()

    # ------------------------------------------------------------------
    # 调度循环
    # ------------------------------------------------------------------

    def _run_group_task(self, group: IntervalGroup):
        """执行一个频率分组的数据采集任务"""
        sched = self.config.get('scheduler', {})
        building_files: List[str] = sched.get('building_files', [])

        if not building_files:
            logger.warning(f"[{group.name}] 没有配置楼栋文件，跳过数据收集")
            return

        param_filter: Set[str] = set(group.param_names) if group.param_names else None
        logger.info(
            f"[{group.name}] 开始数据收集，参数数量：{len(param_filter) if param_filter else '全部'}，"
            f"楼栋文件数：{len(building_files)}"
        )

        for building_file in building_files:
            try:
                logger.info(f"[{group.name}] 处理楼栋文件：{building_file}")
                results = self.data_collection_manager.collect_data_for_building(
                    building_file, param_filter=param_filter
                )
                if results:
                    logger.info(f"[{group.name}] 楼栋文件 {building_file} 处理完成")
                else:
                    logger.warning(f"[{group.name}] 楼栋文件 {building_file} 处理失败或无数据")
            except Exception as e:
                logger.error(f"[{group.name}] 处理楼栋文件 {building_file} 时发生错误：{str(e)}")

        logger.info(f"[{group.name}] 本轮任务执行完成")

    def _group_loop(self, group: IntervalGroup):
        """单个频率分组的调度主循环"""
        logger.info(f"[{group.name}] 调度循环启动，间隔：{group.interval_seconds}秒")

        while not self.stop_event.is_set():
            try:
                self._run_group_task(group)
                if self.stop_event.wait(group.interval_seconds):
                    break
            except Exception as e:
                logger.error(f"[{group.name}] 调度循环发生错误：{str(e)}")
                if self.stop_event.wait(30):
                    break

        logger.info(f"[{group.name}] 调度循环已停止")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def _signal_handler(self, sig, frame):
        signal_name = signal.Signals(sig).name
        logger.info(f"接收到信号 {signal_name}，正在停止调度器...")
        self.stop()

    def start(self):
        """启动任务调度器（为每个 IntervalGroup 启动独立线程）"""
        if self.group_threads and any(t.is_alive() for t in self.group_threads):
            logger.warning("任务调度器已经在运行")
            return

        # 初始化数据收集管理器
        sched = self.config.get('scheduler', {})
        pool_size = sched.get('thread_pool_size', 10)
        self.data_collection_manager = ImprovedDataCollectionManager(max_workers=pool_size)
        self.data_collection_manager.start()

        # 解析调度分组（需在 data_collection_manager 初始化后调用，以便读取 plc_config）
        groups = self._resolve_interval_groups()

        # 重置停止事件
        self.stop_event.clear()
        self.group_threads = []

        for group in groups:
            t = threading.Thread(
                target=self._group_loop,
                args=(group,),
                name=f"Scheduler-{group.name}",
                daemon=True
            )
            t.start()
            self.group_threads.append(t)
            logger.info(f"启动调度线程：{t.name}（间隔 {group.interval_seconds}s）")

        logger.info(f"任务调度器已启动，共 {len(self.group_threads)} 个调度分组")

    def stop(self):
        """停止所有调度线程"""
        if not self.group_threads or not any(t.is_alive() for t in self.group_threads):
            return

        self.stop_event.set()

        for t in self.group_threads:
            if t.is_alive():
                t.join(timeout=15)

        if self.data_collection_manager:
            self.data_collection_manager.stop()

        self.group_threads = []
        logger.info("任务调度器已停止")

    # ------------------------------------------------------------------
    # 兼容旧接口
    # ------------------------------------------------------------------

    def update_interval(self, interval_seconds: int) -> bool:
        """更新默认调度间隔（下次启动时生效）"""
        if interval_seconds <= 0:
            logger.error("调度间隔必须大于0")
            return False
        self.config['scheduler']['interval_seconds'] = interval_seconds
        logger.info(f"已更新默认调度间隔为：{interval_seconds}秒")
        return True

    def update_building_files(self, building_files: List[str]) -> bool:
        """更新楼栋文件列表（下次启动时生效）"""
        self.config['scheduler']['building_files'] = building_files
        logger.info(f"已更新楼栋文件列表，共{len(building_files)}个文件")
        return True


if __name__ == "__main__":
    scheduler = TaskScheduler()

    try:
        scheduler.start()
        logger.info("任务调度器正在运行，按Ctrl+C停止...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("接收到用户中断，正在停止...")
    finally:
        scheduler.stop()
        logger.info("程序已退出")
