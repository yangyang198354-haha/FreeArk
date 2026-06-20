"""
fault_consumer/state_machine.py — 进程内故障状态机（MOD-BE-FM-03，v0.6.0-FM）

维护进程内状态机字典 _state_machine，实现 ADR-FM-03 定义的三条状态转移规则：
  T1: UNKNOWN + 故障报文  → INSERT fault_event(is_active=True) + 更新内存
  T2: ACTIVE  + 故障报文  → 仅更新内存 last_seen_at（不写 DB）
  T3: ACTIVE  + 正常报文  → UPDATE fault_event(is_active=False, recovered_at) + 更新内存

设计约束（ADR-FM-02）：
  - 进程内 Python dict，无 TTL，重启后从 DB 重建（LIMIT 10000 保护）
  - 每次 DB 操作前调用 close_old_connections()（长进程连接保活）
  - IntegrityError 兜底：INSERT 冲突改为 UPDATE last_seen_at，不崩溃
  - OperationalError：记录 ERROR 日志，不崩溃（systemd 托管进程）
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import (
    close_old_connections,
    connection,
    IntegrityError,
    InterfaceError,
    OperationalError,
)

from .room_lookup import get_room_for_device

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 运行计数器（P0 防复发 / 可观测性）
#
# 背景：2026-06-16 fault-consumer 在进程未崩溃的情况下静默停止写入新故障，
# 长达 4 天无人察觉（旧代码几乎不打可诊断日志）。这里维护进程内计数器，
# 供命令层周期性 INFO 输出与看门狗判活使用。计数器是单调累加的快照值。
# ---------------------------------------------------------------------------

_counters: dict = {
    't1_attempt': 0,       # 进入 T1（首次故障）路径的次数
    't1_success': 0,       # T1 成功 INSERT 新故障行的次数
    't1_integrity': 0,     # T1 撞 IntegrityError 走兜底的次数
    't1_db_error': 0,      # T1 连接级错误（Operational/Interface）次数
    't1_unexpected': 0,    # T1 其它未预期异常次数
    't2_persist': 0,       # T2 节流落库成功次数
    't3_recover': 0,       # T3 恢复成功次数
}


def get_counters() -> dict:
    """返回运行计数器快照（命令层周期性日志 / 看门狗使用）。"""
    return dict(_counters)


def reset_counters() -> None:
    """清零计数器（仅供测试使用）。"""
    for k in _counters:
        _counters[k] = 0


def _force_close_connection() -> None:
    """连接级错误后强制关闭当前线程的 DB 连接，下次 ORM 操作自动重连。

    防御性措施：CONN_MAX_AGE=300 已会周期回收连接，这里在出错点立即丢弃，
    缩短"坏连接"的暴露窗口。关闭失败本身吞掉（连接可能已不可用）。
    """
    try:
        connection.close()
    except Exception:
        pass

# T2 节流落库阈值（秒）：故障持续期间，last_seen_at 默认只在内存维护，
# 距离上次落库超过该阈值才写一次 DB，避免每条上报都写库。
# 设为 0 表示每次 T2 都落库（不节流）；可经 settings.FAULT_T2_PERSIST_THROTTLE_SECONDS 调整。
_T2_PERSIST_THROTTLE_SECONDS: int = int(
    getattr(settings, 'FAULT_T2_PERSIST_THROTTLE_SECONDS', 300)
)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class FaultState:
    """进程内故障状态条目。"""
    event_id: int       # fault_event.id，用于 UPDATE 定位行
    is_active: bool     # True=活跃，False=已恢复
    last_seen_at: datetime  # 最近一次 MQTT 上报（内存中维护）
    # 已落库的 last_seen_at 值，用于 T2 节流判断；初始等于 INSERT/重建时的 last_seen_at
    last_persisted_at: datetime = None


# 进程内状态机（模块级单例字典）
# key: (specific_part: str, device_sn: str, fault_code: str)
# value: FaultState
_state_machine: dict = {}


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------

def rebuild_from_db() -> int:
    """进程启动时从 DB 重建状态机（ADR-FM-02 重建策略）。

    查询 fault_event WHERE is_active=True LIMIT 10000，填充 _state_machine。

    调用时机：fault_consumer Management Command 的 handle() 启动时，
              Django setup() 完成后（ORM 可用）。

    Returns:
        int: 加载的记录数
    """
    global _state_machine
    _state_machine = {}

    close_old_connections()
    try:
        from api.models import FaultEvent
        qs = FaultEvent.objects.filter(is_active=True)[:10000]
        count = 0
        for fe in qs:
            key = (fe.specific_part, fe.device_sn, fe.fault_code)
            _state_machine[key] = FaultState(
                event_id=fe.id,
                is_active=True,
                last_seen_at=fe.last_seen_at,
                last_persisted_at=fe.last_seen_at,  # DB 当前值即已落库值
            )
            count += 1
        logger.info('状态机重建完成，共加载 %d 条活跃故障', count)
        return count
    except Exception as exc:
        logger.error('状态机重建失败，从空状态启动: %s', exc)
        return 0


def process_fault_field(
    specific_part: str,
    device_sn: str,
    product_code: str,
    fault_code: str,
    fault_type: str,
    severity: str,
    fault_message: str,
    is_active_now: bool,
    received_at: datetime,
) -> None:
    """处理单个故障字段的状态变化（状态机核心入口）。

    实现 ADR-FM-03 的 T1/T2/T3 转移逻辑。
    此函数在 on_message 回调中调用，需尽量快；仅在 T1/T3 路径执行 DB 操作。

    Args:
        specific_part:  房号标识，如 "3-1-7-702"
        device_sn:      设备序列号
        product_code:   产品编码
        fault_code:     故障码（param_name）
        fault_type:     故障大类（comm/sensor/fresh_air/other_error）
        severity:       严重级别（error/warning）
        fault_message:  故障描述文本
        is_active_now:  当前报文中该字段是否处于故障态
        received_at:    报文接收时间（datetime，aware）
    """
    key = (specific_part, device_sn, fault_code)
    state = _state_machine.get(key)

    if is_active_now:
        if state is None or not state.is_active:
            # T1: 首次出现故障，INSERT
            _counters['t1_attempt'] += 1
            _t1_insert(key, specific_part, device_sn, product_code,
                       fault_code, fault_type, severity, fault_message, received_at)
        else:
            # T2: 故障持续。先更新内存 last_seen_at；再按节流策略低频写回 DB，
            # 使活跃故障的 last_seen_at 不至于长期停留在 first_seen_at（修复"首次=最后活跃"）。
            st = _state_machine[key]
            st.last_seen_at = received_at
            last_persisted = st.last_persisted_at
            if (last_persisted is None
                    or (received_at - last_persisted).total_seconds() >= _T2_PERSIST_THROTTLE_SECONDS):
                _t2_persist_last_seen(key, st, received_at)
    else:
        if state is not None and state.is_active:
            # T3: 故障恢复，UPDATE DB
            _t3_recover(key, state, received_at)
        # else: 状态机 miss 且收到正常报文，无需操作


def get_state(key: tuple) -> 'FaultState | None':
    """获取指定 key 的当前状态（仅供测试/日志使用）。"""
    return _state_machine.get(key)


def get_state_machine_size() -> int:
    """返回当前状态机条目数（仅供日志/监控使用）。"""
    return len(_state_machine)


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

def _t1_insert(
    key: tuple,
    specific_part: str,
    device_sn: str,
    product_code: str,
    fault_code: str,
    fault_type: str,
    severity: str,
    fault_message: str,
    received_at: datetime,
) -> None:
    """T1 转移：INSERT fault_event(is_active=True)。

    IntegrityError 兜底：改为 UPDATE last_seen_at + 更新内存。
    """
    close_old_connections()
    try:
        from api.models import FaultEvent
        room_name, room_id = get_room_for_device(device_sn)
        fe = FaultEvent.objects.create(
            specific_part=specific_part,
            device_sn=device_sn,
            product_code=product_code,
            fault_code=fault_code,
            fault_type=fault_type,
            fault_message=fault_message,
            severity=severity,
            first_seen_at=received_at,
            last_seen_at=received_at,
            recovered_at=None,
            is_active=True,
            room_name=room_name,
            room_id_id=room_id,
        )
        _state_machine[key] = FaultState(
            event_id=fe.id,
            is_active=True,
            last_seen_at=received_at,
            last_persisted_at=received_at,  # INSERT 已写入 last_seen_at=received_at
        )
        _counters['t1_success'] += 1
        logger.debug('T1 INSERT fault_event id=%d key=%s', fe.id, key)
    except IntegrityError:
        # 竞态（如重启重建窗口）：改为 UPDATE last_seen_at
        _counters['t1_integrity'] += 1
        logger.warning('T1 IntegrityError，fallback to UPDATE last_seen_at: key=%s', key)
        _t1_fallback_update(key, specific_part, device_sn, fault_code, received_at)
    except (OperationalError, InterfaceError) as exc:
        _counters['t1_db_error'] += 1
        logger.error('T1 DB 连接错误: %s key=%s（关闭连接以便重连）', exc, key)
        _force_close_connection()
    except Exception as exc:
        _counters['t1_unexpected'] += 1
        logger.exception('T1 未预期异常: %s key=%s', exc, key)


def _t1_fallback_update(
    key: tuple,
    specific_part: str,
    device_sn: str,
    fault_code: str,
    received_at: datetime,
) -> None:
    """T1 IntegrityError 兜底：更新已有行的 last_seen_at，并同步内存。"""
    try:
        from api.models import FaultEvent
        updated = FaultEvent.objects.filter(
            specific_part=specific_part,
            device_sn=device_sn,
            fault_code=fault_code,
            is_active=True,
        ).order_by('-first_seen_at').first()
        if updated:
            updated.last_seen_at = received_at
            updated.save(update_fields=['last_seen_at', 'updated_at'])
            _state_machine[key] = FaultState(
                event_id=updated.id,
                is_active=True,
                last_seen_at=received_at,
                last_persisted_at=received_at,  # 兜底 UPDATE 已写入 last_seen_at=received_at
            )
        else:
            # 异常信号：INSERT 撞唯一约束，却查不到任何活跃行。正常情况下
            # first_seen_at=now() 不可能与历史行相撞，出现即说明连接/进程态异常
            # （2026-06-16 静默停写事故的特征）。丢弃连接以便下次拿到干净连接重试。
            logger.warning(
                'T1 兜底未找到活跃行（IntegrityError 但无 active 行，异常信号）: key=%s，关闭连接以便重连',
                key,
            )
            _force_close_connection()
    except (OperationalError, InterfaceError) as exc:
        logger.error('T1 fallback DB 连接错误: %s（关闭连接以便重连）', exc)
        _force_close_connection()
    except Exception as exc:
        logger.error('T1 fallback UPDATE 失败: %s', exc)


def _t2_persist_last_seen(key: tuple, state: FaultState, received_at: datetime) -> None:
    """T2 节流落库：低频 UPDATE fault_event.last_seen_at。

    仅在距上次落库超过 _T2_PERSIST_THROTTLE_SECONDS 时调用，避免每条上报都写库。
    只更新仍活跃的行；失败不更新 state.last_persisted_at，下次 T2 越阈值会重试。
    """
    close_old_connections()
    try:
        from api.models import FaultEvent
        FaultEvent.objects.filter(id=state.event_id, is_active=True).update(
            last_seen_at=received_at,
        )
        state.last_persisted_at = received_at
        _counters['t2_persist'] += 1
        logger.debug('T2 PERSIST last_seen_at id=%d key=%s', state.event_id, key)
    except (OperationalError, InterfaceError) as exc:
        logger.error('T2 PERSIST DB 连接错误: %s key=%s（关闭连接以便重连）', exc, key)
        _force_close_connection()
    except Exception as exc:
        logger.exception('T2 PERSIST 未预期异常: %s key=%s', exc, key)


def _t3_recover(key: tuple, state: FaultState, received_at: datetime) -> None:
    """T3 转移：UPDATE fault_event SET is_active=False, recovered_at, last_seen_at。"""
    close_old_connections()
    try:
        from api.models import FaultEvent
        FaultEvent.objects.filter(id=state.event_id).update(
            is_active=False,
            recovered_at=received_at,
            last_seen_at=state.last_seen_at,  # 写回内存中的最后活跃时间
        )
        _state_machine[key].is_active = False
        _counters['t3_recover'] += 1
        logger.debug('T3 RECOVER fault_event id=%d key=%s', state.event_id, key)
    except (OperationalError, InterfaceError) as exc:
        logger.error('T3 DB 连接错误: %s key=%s（关闭连接以便重连）', exc, key)
        _force_close_connection()
    except Exception as exc:
        logger.exception('T3 未预期异常: %s key=%s', exc, key)
