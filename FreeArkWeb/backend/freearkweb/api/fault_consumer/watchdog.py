"""
fault_consumer/watchdog.py — 故障消费者自愈看门狗（P0 防复发）

事故背景（2026-06-16）：fault-consumer 进程未崩溃（systemd 显示 active），
却静默停止写入新故障长达 4 天——T1 路径持续被触发（有故障消息进来），
但 INSERT 条条失败，无人察觉。根因机制未能完全复原（证据已轮转、连接每
300s 已自动回收却仍无效），故采用"与机制无关"的判活策略：

  若在持续多个观察窗口里"T1 一直在尝试、却一次都没成功"，判定进程已卡死，
  记 CRITICAL 日志并令进程退出（systemd Restart=on-failure 会拉起新进程，
  新进程从 DB 重建状态机 + 干净连接，已验证可立即恢复写入）。

判定逻辑做成纯函数 evaluate_stall()，便于单元测试；线程循环 run_watchdog()
仅负责采样、计时与触发回调。
"""

import logging
import os
import signal
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# 默认参数（可经 settings 覆盖）
_DEFAULT_INTERVAL = int(getattr(settings, 'FAULT_WATCHDOG_INTERVAL_SECONDS', 60))
# 单个窗口内 t1_attempt 至少新增这么多，才把"零成功"视作一次失速窗口
# （避免故障稀少的安静时段误判）
_DEFAULT_MIN_ATTEMPTS = int(getattr(settings, 'FAULT_WATCHDOG_MIN_ATTEMPTS', 20))
# 连续这么多个失速窗口后触发自愈（interval=60 + limit=10 ≈ 10 分钟）
_DEFAULT_STALL_LIMIT = int(getattr(settings, 'FAULT_WATCHDOG_STALL_LIMIT', 10))
_ENABLED = bool(getattr(settings, 'FAULT_WATCHDOG_ENABLED', True))


def evaluate_stall(prev: dict, curr: dict, stall_streak: int,
                   *, min_attempts: int, stall_limit: int) -> tuple[bool, int]:
    """纯函数：根据相邻两次计数快照判定是否失速、更新连续失速计数。

    失速窗口定义：本窗口 t1_attempt 新增 >= min_attempts（确有故障消息在驱动
    T1），但 t1_success 完全没有新增（一条都没写成功）。

    Args:
        prev:         上一次计数快照（state_machine.get_counters()）
        curr:         本次计数快照
        stall_streak: 当前连续失速窗口数
        min_attempts: 构成失速窗口所需的最小 t1_attempt 增量
        stall_limit:  连续失速窗口达到此值即触发自愈

    Returns:
        (should_self_heal, new_stall_streak)
    """
    attempts_delta = curr.get('t1_attempt', 0) - prev.get('t1_attempt', 0)
    success_delta = curr.get('t1_success', 0) - prev.get('t1_success', 0)

    if attempts_delta >= min_attempts and success_delta <= 0:
        new_streak = stall_streak + 1
    else:
        new_streak = 0

    return new_streak >= stall_limit, new_streak


def _default_on_stall() -> None:
    """默认自愈动作：令进程退出，交给 systemd Restart=on-failure 拉起。"""
    logger.critical(
        'fault-consumer 看门狗：检测到持续失速（有故障上报但零成功写入），'
        '主动退出以触发 systemd 重启'
    )
    # 先发 SIGTERM 走优雅退出；保险起见短暂等待后硬退出。
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        pass
    time.sleep(5)
    os._exit(1)


def run_watchdog(get_counters_fn, on_stall=None, *,
                 interval: int = None, min_attempts: int = None,
                 stall_limit: int = None, stop_event: threading.Event = None) -> None:
    """看门狗主循环（阻塞；通常放到 daemon 线程里跑）。

    Args:
        get_counters_fn: 无参，返回计数快照 dict（state_machine.get_counters）
        on_stall:        触发自愈时调用，默认 _default_on_stall（进程退出）
        interval/min_attempts/stall_limit: 见模块级默认值
        stop_event:      可选，set() 后循环退出（测试/优雅停机用）
    """
    interval = interval or _DEFAULT_INTERVAL
    min_attempts = min_attempts if min_attempts is not None else _DEFAULT_MIN_ATTEMPTS
    stall_limit = stall_limit if stall_limit is not None else _DEFAULT_STALL_LIMIT
    on_stall = on_stall or _default_on_stall

    logger.info(
        'fault-consumer 看门狗启动：interval=%ds min_attempts=%d stall_limit=%d',
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
        # 周期性健康日志（便于事后诊断；这次事故正因缺这类日志而排查困难）
        logger.info(
            'fault-consumer 健康: t1_attempt=%d t1_success=%d t1_integrity=%d '
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
    """按需启动看门狗 daemon 线程；FAULT_WATCHDOG_ENABLED=False 时返回 None。"""
    if not _ENABLED:
        logger.info('fault-consumer 看门狗已禁用（FAULT_WATCHDOG_ENABLED=False）')
        return None
    t = threading.Thread(
        target=run_watchdog, args=(get_counters_fn,),
        name='fault-consumer-watchdog', daemon=True,
    )
    t.start()
    return t
