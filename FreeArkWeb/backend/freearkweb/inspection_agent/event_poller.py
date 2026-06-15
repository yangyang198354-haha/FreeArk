"""inspection_agent.event_poller —— DB 轮询事件接入（OD-02 落地，ARCH §4）。

consumer 禁改（OOS-03）、禁引中间件（OOS-06），故以 DB 轮询感知新待巡检事件：
每轮取 fault_event / condensation_warning_event 中 is_active=True 且
inspection_status='PENDING' 的记录，按 first_seen_at 升序、最多 BATCH_SIZE 条，
随即原子乐观锁置为 IN_PROGRESS（防未来并发重复取用），仅返回**本进程成功认领**的事件。

重启零漏单/零重单（REQ-NFUNC-002，ARCH §10.4）：服务启动时 reset_in_progress()
把残留 IN_PROGRESS 重置为 PENDING，下轮重新取用；DONE/SKIPPED 不动。
"""

import logging
import os

from django.utils import timezone

from api.models import CondensationWarningEvent, FaultEvent

logger = logging.getLogger("freeark.inspection_agent.event_poller")

_DEFAULT_BATCH_SIZE = 5
# 轮询的事件模型（两张事件表共享 inspection_status 状态机）
_EVENT_MODELS = (FaultEvent, CondensationWarningEvent)


def get_batch_size() -> int:
    """每轮最多取用事件数（INSPECTION_BATCH_SIZE，默认 5）；非法值回退默认。"""
    raw = os.environ.get("INSPECTION_BATCH_SIZE", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_BATCH_SIZE
    return value if value > 0 else _DEFAULT_BATCH_SIZE


class EventPoller:
    """DB 轮询器：取 PENDING 事件并原子认领为 IN_PROGRESS。"""

    def __init__(self, batch_size: int = None):
        self.batch_size = batch_size if batch_size and batch_size > 0 else get_batch_size()

    def poll(self) -> list:
        """取至多 batch_size 条待巡检事件，原子认领，返回成功认领的实例列表。

        返回的事件按 first_seen_at 升序；其内存态已同步为 IN_PROGRESS。
        未能认领（被其他执行抢先/状态已变）的事件不返回，避免重复处理。
        """
        candidates = self._fetch_pending()
        claimed = []
        now = timezone.now()
        for event in candidates:
            updated = type(event).objects.filter(
                pk=event.pk, inspection_status='PENDING',
            ).update(inspection_status='IN_PROGRESS', inspection_started_at=now)
            if updated == 1:
                event.inspection_status = 'IN_PROGRESS'
                event.inspection_started_at = now
                claimed.append(event)
        if claimed:
            logger.info("巡检轮询认领 %d 条事件（candidates=%d）", len(claimed), len(candidates))
        return claimed

    def _fetch_pending(self) -> list:
        """两张表各取前 batch_size 条 PENDING，合并按 first_seen_at 升序截断。"""
        merged = []
        for model in _EVENT_MODELS:
            merged.extend(
                model.objects.filter(
                    is_active=True, inspection_status='PENDING',
                ).order_by('first_seen_at')[:self.batch_size]
            )
        merged.sort(key=lambda e: e.first_seen_at)
        return merged[:self.batch_size]

    @staticmethod
    def reset_in_progress() -> int:
        """启动重建：把残留 IN_PROGRESS 原子重置为 PENDING（ARCH §10.4）。返回重置总数。

        IN_PROGRESS→PENDING：重新处理中途中断的事件（零漏单）；
        DONE/SKIPPED 不受影响（零重单）。
        """
        total = 0
        for model in _EVENT_MODELS:
            total += model.objects.filter(inspection_status='IN_PROGRESS').update(
                inspection_status='PENDING', inspection_started_at=None,
            )
        if total:
            logger.info("启动重建：重置 %d 条 IN_PROGRESS → PENDING", total)
        return total
