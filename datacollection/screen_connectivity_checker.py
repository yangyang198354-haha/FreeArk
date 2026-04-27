# MOD-DC-01 — 大屏连通性 TCP 探测模块
# author_agent: sub_agent_software_developer
# project: FreeArk_DeviceManagement
# invocation_id: INVOKE-GROUP_C-001
"""
每分钟对所有 OwnerInfo.ip_address 非空的户执行 TCP 连通性探测，
结果发布到 MQTT topic /datacollection/screen/connectivity。

集成到 TaskScheduler：在 start() 中启动独立的 screen_connectivity 调度线程。
每条 MQTT 消息格式（JSON）：
{
    "specific_part": "3-1-7-702",
    "status": "online" | "offline",
    "checked_at": "2026-04-26T02:00:00"
}
"""

import json
import logging
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 探测配置（可通过外部传参覆盖）
# ---------------------------------------------------------------------------
DEFAULT_MAX_WORKERS = 20    # 最大并发探测线程数（ADR-002）
DEFAULT_TIMEOUT_SECS = 3    # 单 IP TCP 探测超时（秒）
DEFAULT_TCP_PORT = 80       # 探测端口
INTERVAL_SECONDS = 60       # 调度间隔（秒）


class ScreenConnectivityChecker:
    """大屏连通性探测器（MOD-DC-01）。

    方法：
      check_all(owner_list)  — 并发探测，返回结果列表
      probe_single(ip)       — 探测单个 IP，返回 bool

    owner_list 格式：
      [{"specific_part": "3-1-7-702", "ip_address": "192.168.1.100"}, ...]
    """

    def __init__(
        self,
        max_workers: int = DEFAULT_MAX_WORKERS,
        timeout: int = DEFAULT_TIMEOUT_SECS,
        tcp_port: int = DEFAULT_TCP_PORT,
    ):
        self.max_workers = max_workers
        self.timeout = timeout
        self.tcp_port = tcp_port

    def probe_single(self, ip: str, timeout: int = None) -> bool:
        """对单个 IP 执行 TCP port 80 连通性探测。

        Returns:
            True  — 可达（连接成功或连接被拒（端口关闭但主机存在））
            False — 不可达（超时或其他网络错误）
        """
        t = timeout if timeout is not None else self.timeout
        try:
            with socket.create_connection((ip, self.tcp_port), timeout=t):
                return True
        except ConnectionRefusedError:
            # 主机可达，但端口拒绝连接（设备存在但服务未开启），视为在线
            return True
        except (socket.timeout, OSError):
            return False

    def check_all(
        self,
        owner_list: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """并发探测所有条目，返回探测结果列表（跳过 ip_address 为空的条目）。

        Args:
            owner_list: [{"specific_part": str, "ip_address": str}, ...]

        Returns:
            [{"specific_part": str, "status": "online"|"offline", "checked_at": str}, ...]
            ip_address 为空字符串的条目不出现在结果中（AC-006-04）。
        """
        # 过滤掉 ip_address 为空的条目
        targets = [
            o for o in owner_list
            if o.get('ip_address', '').strip()
        ]

        if not targets:
            logger.info("ScreenConnectivityChecker.check_all: 无可探测 IP，跳过")
            return []

        results = []
        futures_map = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for entry in targets:
                specific_part = entry['specific_part']
                ip = entry['ip_address'].strip()
                future = executor.submit(self.probe_single, ip)
                futures_map[future] = specific_part

            for future in as_completed(futures_map):
                specific_part = futures_map[future]
                checked_at = datetime.now().isoformat(timespec='seconds')
                try:
                    is_online = future.result()
                except Exception as e:
                    logger.warning(
                        f"ScreenConnectivityChecker: 探测异常 specific_part={specific_part}, "
                        f"error={e}"
                    )
                    is_online = False

                results.append({
                    'specific_part': specific_part,
                    'status': 'online' if is_online else 'offline',
                    'checked_at': checked_at,
                })

        logger.info(
            f"ScreenConnectivityChecker.check_all: 探测完成，共 {len(targets)} 个 IP，"
            f"在线 {sum(1 for r in results if r['status'] == 'online')} 个"
        )
        return results


# ---------------------------------------------------------------------------
# TaskScheduler 集成点（由 task_scheduler.py 调用）
# ---------------------------------------------------------------------------

class ScreenConnectivityTask:
    """大屏连通性定时任务（每分钟），集成到 TaskScheduler。

    使用方式：
        task = ScreenConnectivityTask(mqtt_client, stop_event)
        thread = threading.Thread(target=task.run_loop, daemon=True)
        thread.start()

    mqtt_client：已连接的 paho MQTT client 实例（来自 datacollection 的 MQTTClient 封装）
    stop_event：threading.Event，调用 .set() 后任务循环退出
    """

    MQTT_TOPIC = '/datacollection/screen/connectivity'

    def __init__(self, mqtt_client, stop_event: threading.Event, interval: int = INTERVAL_SECONDS):
        self.mqtt_client = mqtt_client
        self.stop_event = stop_event
        self.interval = interval
        self.checker = ScreenConnectivityChecker()

    def _load_owner_list(self) -> List[Dict[str, str]]:
        """从数据库直接读取 OwnerInfo（避免 HTTP 依赖，ADR-002 MINOR 注记）。

        通过 Django ORM 直接访问 MySQL/SQLite（datacollection 进程复用同一 DB）。
        """
        try:
            import django
            import os
            # Django 已由调用方（main_datacollection.py）初始化，直接导入模型即可
            from api.models import OwnerInfo  # noqa: 若 ORM 未初始化，此处会抛出异常

            owners = list(
                OwnerInfo.objects.values('specific_part', 'ip_address')
            )
            logger.debug(f"ScreenConnectivityTask: 加载 {len(owners)} 条 OwnerInfo 记录")
            return owners
        except Exception as e:
            logger.error(
                f"ScreenConnectivityTask: 加载 OwnerInfo 失败，本轮跳过: {e}",
                exc_info=True,
            )
            return []

    def _publish_results(self, results: List[Dict[str, str]]) -> None:
        """将探测结果逐条发布到 MQTT（ADR-007：每户一条消息，共用 topic）。"""
        for item in results:
            payload = json.dumps(item, ensure_ascii=False)
            try:
                self.mqtt_client.publish(self.MQTT_TOPIC, payload, qos=1)
                logger.debug(
                    f"ScreenConnectivityTask: 发布 {item['specific_part']} "
                    f"→ {item['status']}"
                )
            except Exception as e:
                logger.error(
                    f"ScreenConnectivityTask: MQTT 发布失败 {item['specific_part']}: {e}"
                )

    def run_once(self) -> None:
        """执行单次探测并发布结果。"""
        owner_list = self._load_owner_list()
        if not owner_list:
            return
        results = self.checker.check_all(owner_list)
        if results:
            self._publish_results(results)

    def run_loop(self) -> None:
        """调度主循环：每 interval 秒执行一次探测，直到 stop_event 被设置。"""
        logger.info(
            f"ScreenConnectivityTask: 调度循环启动，间隔 {self.interval}s"
        )
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(
                    f"ScreenConnectivityTask: run_once 发生异常: {e}",
                    exc_info=True,
                )
            # 等待下一轮，同时支持 stop_event 中断
            if self.stop_event.wait(self.interval):
                break
        logger.info("ScreenConnectivityTask: 调度循环已停止")
