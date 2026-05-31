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
from django.db import close_old_connections, IntegrityError, OperationalError

from .room_lookup import get_room_for_device

logger = logging.getLogger(__name__)

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
        logger.debug('T1 INSERT fault_event id=%d key=%s', fe.id, key)
    except IntegrityError:
        # 竞态（如重启重建窗口）：改为 UPDATE last_seen_at
        logger.warning('T1 IntegrityError，fallback to UPDATE last_seen_at: key=%s', key)
        _t1_fallback_update(key, specific_part, device_sn, fault_code, received_at)
    except OperationalError as exc:
        logger.error('T1 OperationalError（DB 连接问题）: %s key=%s', exc, key)
    except Exception as exc:
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
        logger.debug('T2 PERSIST last_seen_at id=%d key=%s', state.event_id, key)
    except OperationalError as exc:
        logger.error('T2 PERSIST OperationalError（DB 连接问题）: %s key=%s', exc, key)
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
        logger.debug('T3 RECOVER fault_event id=%d key=%s', state.event_id, key)
    except OperationalError as exc:
        logger.error('T3 OperationalError（DB 连接问题）: %s key=%s', exc, key)
    except Exception as exc:
        logger.exception('T3 未预期异常: %s key=%s', exc, key)
