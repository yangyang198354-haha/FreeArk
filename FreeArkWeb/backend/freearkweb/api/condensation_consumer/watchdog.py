"""
condensation_consumer/watchdog.py — 结露预警消费者自愈看门狗（P0 防复发）

与 fault_consumer/watchdog.py 同源、同结构（项目沿用 fault/condensation 并行双份
模块的惯例）。事故背景见 fault_consumer/watchdog.py：2026-06-16 两个消费者在同一
时刻静默停写，进程未崩溃却长期无人察觉。

策略（与机制无关）：持续多个窗口"有 T1 尝试、零 T1 成功"即判定卡死，记 CRITICAL
并令进程退出，交 systemd Restart=on-failure 拉起（新进程重建状态机 + 干净连接）。

纯判定逻辑复用 fault_consumer.watchdog.evaluate_stall（与本模块计数键名一致）。
"""

import logging
import os
import signal
import threading
import time

from django.conf import settings

from api.fault_consumer.watchdog import evaluate_stall

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = int(getattr(settings, 'CW_WATCHDOG_INTERVAL_SECONDS', 60))
_DEFAULT_MIN_ATTEMPTS = int(getattr(settings, 'CW_WATCHDOG_MIN_ATTEMPTS', 20))
_DEFAULT_STALL_LIMIT = int(getattr(settings, 'CW_WATCHDOG_STALL_LIMIT', 10))
_ENABLED = bool(getattr(settings, 'CW_WATCHDOG_ENABLED', True))


def _default_on_stall() -> None:
    """默认自愈动作：令进程退出，交给 systemd Restart=on-failure 拉起。"""
    logger.critical(
        'condensation-consumer 看门狗：检测到持续失速（有预警上报但零成功写入），'
        '主动退出以触发 systemd 重启'
    )
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        pass
    time.sleep(5)
    os._exit(1)


def run_watchdog(get_counters_fn, on_stall=None, *,
                 interval: int = None, min_attempts: int = None,
                 stall_limit: int = None, stop_event: threading.Event = None) -> None:
    """看门狗主循环（阻塞；通常放到 daemon 线程里跑）。详见 fault 版同名函数。"""
    interval = interval or _DEFAULT_INTERVAL
    min_attempts = min_attempts if min_attempts is not None else _DEFAULT_MIN_ATTEMPTS
    stall_limit = stall_limit if stall_limit is not None else _DEFAULT_STALL_LIMIT
    on_stall = on_stall or _default_on_stall

    logger.info(
        'condensation-consumer 看门狗启动：interval=%ds min_attempts=%d stall_limit=%d',
        interval, min_attempts, stall_limit,
    )
    prev = get_counters_fn()
    stall_streak = 0

    while not (stop_event and stop_event.is_set()):
        if stop_event:
            stop_event.wait(interval)
            if stop_event.is_set():
                break
        else:
            time.sleep(interval)

        curr = get_counters_fn()
        should_heal, stall_streak = evaluate_stall(
            prev, curr, stall_streak,
            min_attempts=min_attempts, stall_limit=stall_limit,
        )
        logger.info(
            'condensation-consumer 健康: t1_attempt=%d t1_success=%d t1_integrity=%d '
            't1_db_error=%d t2_persist=%d t3_recover=%d stall_streak=%d',
            curr.get('t1_attempt', 0), curr.get('t1_success', 0),
            curr.get('t1_integrity', 0), curr.get('t1_db_error', 0),
            curr.get('t2_persist', 0), curr.get('t3_recover', 0), stall_streak,
        )
        if should_heal:
            on_stall()
            return
        prev = curr


def start_watchdog_thread(get_counters_fn) -> threading.Thread | None:
    """按需启动看门狗 daemon 线程；CW_WATCHDOG_ENABLED=False 时返回 None。"""
    if not _ENABLED:
        logger.info('condensation-consumer 看门狗已禁用（CW_WATCHDOG_ENABLED=False）')
        return None
    t = threading.Thread(
        target=run_watchdog, args=(get_counters_fn,),
        name='condensation-consumer-watchdog', daemon=True,
    )
    t.start()
    return t
