"""run_inspection_agent —— 自治巡检 Agent 入口（freeark-inspection-agent，方案 B，ARCH §3.3）。

由 systemd 服务 freeark-inspection-agent 拉起，常驻进程：
  1) 配置 logging → stdout（systemd StandardOutput=journal 收进 journald）；
  2) 启动重建：把残留 IN_PROGRESS 事件原子重置为 PENDING（零漏单/零重单，ARCH §10.4）；
  3) 构造 InspectionAgent 并 run_forever()；
  4) 收到 SIGTERM/SIGINT 优雅退出。

运行：python manage.py run_inspection_agent
配置经 settings.py 的 load_dotenv() 从 .env 注入 os.environ（AUTO_WRITE_POLICY /
INSPECTION_POLL_INTERVAL / INSPECTION_BATCH_SIZE / INSPECTION_WRITE_WHITELIST /
DEEPSEEK_API_KEY 等，均不入 git）。
"""

import logging
import signal
import sys

from django.core.management.base import BaseCommand

from inspection_agent.agent import InspectionAgent
from inspection_agent.event_poller import EventPoller

# 整个 inspection_agent.* 日志树（agent/auth/event_poller/work_order/audit）的根
_LOGGER_ROOT = "freeark.inspection_agent"


class Command(BaseCommand):
    help = "运行自治巡检 Agent（freeark-inspection-agent，方案 B）"

    def handle(self, *args, **options):
        self._configure_logging()
        logger = logging.getLogger(_LOGGER_ROOT)
        logger.info("freeark-inspection-agent 启动")

        reset = EventPoller.reset_in_progress()
        logger.info("启动重建完成：重置 %d 条 IN_PROGRESS → PENDING", reset)

        agent = InspectionAgent()
        self._install_signal_handlers(agent, logger)
        try:
            agent.run_forever()
        finally:
            logger.info("freeark-inspection-agent 已退出")

    @staticmethod
    def _configure_logging():
        """把 inspection_agent.* 日志直送 stdout（→ journald），不依赖 settings.LOGGING。"""
        root = logging.getLogger(_LOGGER_ROOT)
        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s"))
            root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False  # 不再向 Django root 冒泡，避免重复/被 NullHandler 吞

    @staticmethod
    def _install_signal_handlers(agent, logger):
        def _handler(signum, _frame):
            logger.info("收到信号 %s，请求优雅退出", signum)
            agent.stop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):  # 非主线程等场景：忽略
                pass
