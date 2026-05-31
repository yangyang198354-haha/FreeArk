"""
condensation_consumer/state_machine.py — 进程内结露预警状态机（MOD-BE-CW-02，v0.7.0-CW）

镜像 fault_consumer/state_machine.py，差异对照见 ADR-CW-03/ADR-CW-04。

维护进程内状态机字典 _cw_state_machine，实现三条状态转移规则：
  T1: UNKNOWN + 预警报文  → INSERT condensation_warning_event(is_active=True) + 更新内存
  T2: ACTIVE  + 预警报文  → 仅更新内存 last_seen_at（不写 DB）
  T3: ACTIVE  + 正常报文  → UPDATE condensation_warning_event(is_active=False, recovered_at) + 更新内存

状态机 key 设计（ADR-CW-03）：
  key: (specific_part: str, device_sn: str)  ← 二元组，无 fault_code 维度

system_switch 字段来源（ADR-CW-01/RISK-CW-ARCH-01 已闭环）：
  优先级1：触发报文同 deviceSn 的 items[] 中的 system_switch attrValue（MQTT 直取）
           → attrValue 已是 "on"/"off" 字符串（生产抓包 sniff_2860fae9a34ab8a9_20260525_235217.ndjson
             已核实：260001 等同报文的 system_switch attrValue 实测为字符串 "off"/"on"，非数字）
           → 消费侧做 lower() 容错；非 "off" 非空 → "on"
  优先级2：_get_system_switch_for_specific_part → PLCLatestData 直查（方案 A）
           → PLCLatestData.value 是 BigIntegerField（整数 0=关/非0=开），需转换为 "on"/"off"
  均无    → "unknown"

RISK-CW-ARCH-01 闭环说明（OD-CW-ARCH-01 已确认）：
  - MQTT items[] 中 system_switch 的 attrValue 实测为字符串 "on"/"off"（非 "0"/"1"）
  - PLCLatestData.value 为整数（0=关/非0=开）
  - 两路来源格式不同，已在各自处理路径中分别处理，统一输出 "on"/"off"/"unknown"

设计约束（ADR-CW-06）：
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

from api.fault_consumer.room_lookup import get_room_for_device

logger = logging.getLogger(__name__)

# T2 节流落库阈值（秒）：预警持续期间，last_seen_at 默认只在内存维护，
# 距离上次落库超过该阈值才写一次 DB，避免每条上报都写库。
# 设为 0 表示每次 T2 都落库（不节流）；可经 settings.CW_T2_PERSIST_THROTTLE_SECONDS 调整。
# 镜像 fault_consumer 的 FAULT_T2_PERSIST_THROTTLE_SECONDS。
_CW_T2_PERSIST_THROTTLE_SECONDS: int = int(
    getattr(settings, 'CW_T2_PERSIST_THROTTLE_SECONDS', 300)
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class CondensationState:
    """进程内结露预警状态条目。"""
    event_id: int        # condensation_warning_event.id，用于 UPDATE 定位行
    is_active: bool      # True=活跃，False=已恢复
    last_seen_at: datetime  # 最近一次 MQTT 上报（内存中维护）
    # 已落库的 last_seen_at 值，用于 T2 节流判断；初始等于 INSERT/重建时的 last_seen_at
    last_persisted_at: datetime = None


# 进程内状态机（模块级单例字典）
# key: (specific_part: str, device_sn: str)
# value: CondensationState
_cw_state_machine: dict = {}


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------

def rebuild_from_db() -> int:
    """进程启动时从 DB 重建状态机（镜像 fault_consumer 重建策略）。

    查询 condensation_warning_event WHERE is_active=True LIMIT 10000，
    填充 _cw_state_machine。

    调用时机：condensation_consumer Management Command 的 handle() 启动时，
              Django setup() 完成后（ORM 可用）。

    Returns:
        int: 加载的记录数
    """
    global _cw_state_machine
    _cw_state_machine = {}

    close_old_connections()
    try:
        from api.models import CondensationWarningEvent
        qs = CondensationWarningEvent.objects.filter(is_active=True)[:10000]
        count = 0
        for cwe in qs:
            key = (cwe.specific_part, cwe.device_sn)
            _cw_state_machine[key] = CondensationState(
                event_id=cwe.id,
                is_active=True,
                last_seen_at=cwe.last_seen_at,
                last_persisted_at=cwe.last_seen_at,  # DB 当前值即已落库值
            )
            count += 1
        logger.info('结露预警状态机重建完成，共加载 %d 条活跃预警', count)
        return count
    except Exception as exc:
        logger.error('结露预警状态机重建失败，从空状态启动: %s', exc)
        return 0


def process_condensation_alarm(
    specific_part: str,
    device_sn: str,
    product_code: str,
    is_active_now: bool,
    received_at: datetime,
    # T1 快照字段（仅在 T1 路径使用）
    condensation_alarm_value: 'str | None' = None,
    dew_point_temp: 'str | None' = None,
    ntc_temp: 'str | None' = None,
    humidity: 'str | None' = None,
    system_switch: 'str | None' = None,
) -> None:
    """状态机核心入口，处理单个设备的 condensation_alarm 状态变化（T1/T2/T3）。

    此函数在 on_message 回调中调用，需尽量快；
    仅在 T1/T3 路径执行 DB 操作，T2 只更新内存。

    Args:
        specific_part:            房号标识，如 "1-1-16-1601"
        device_sn:                设备序列号字符串
        product_code:             产品编码字符串
        is_active_now:            当前报文是否处于预警态（condensation_alarm != 0）
        received_at:              报文接收时间（datetime，aware）
        condensation_alarm_value: 触发时 condensation_alarm 原始值字符串（T1 快照）
        dew_point_temp:           露点温度快照（T1 快照，可 None）
        ntc_temp:                 NTC 温度快照（T1 快照，可 None）
        humidity:                 湿度快照（T1 快照，可 None）
        system_switch:            系统开关快照 "on"/"off"/"unknown"（T1 快照，可 None）
    """
    key = (specific_part, device_sn)
    state = _cw_state_machine.get(key)

    if is_active_now:
        if state is None or not state.is_active:
            # T1: 首次出现预警，INSERT
            _t1_insert(
                key, specific_part, device_sn, product_code, received_at,
                condensation_alarm_value, dew_point_temp, ntc_temp, humidity, system_switch,
            )
        else:
            # T2: 预警持续。先更新内存 last_seen_at；再按节流策略低频写回 DB，
            # 使活跃预警的 last_seen_at 不至于长期停留在 first_seen_at（修复"发生=最后活跃"）。
            st = _cw_state_machine[key]
            st.last_seen_at = received_at
            last_persisted = st.last_persisted_at
            if (last_persisted is None
                    or (received_at - last_persisted).total_seconds() >= _CW_T2_PERSIST_THROTTLE_SECONDS):
                _t2_persist_last_seen(key, st, received_at)
    else:
        if state is not None and state.is_active:
            # T3: 预警恢复，UPDATE DB
            _t3_recover(key, state, received_at)
        # else: 状态机 miss 且收到正常报文，无需操作


def get_state(key: tuple) -> 'CondensationState | None':
    """获取指定 key 的当前状态（仅供测试/日志使用）。"""
    return _cw_state_machine.get(key)


def get_state_machine_size() -> int:
    """返回当前状态机条目数（仅供日志/监控使用）。"""
    return len(_cw_state_machine)


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

def _t1_insert(
    key: tuple,
    specific_part: str,
    device_sn: str,
    product_code: str,
    received_at: datetime,
    condensation_alarm_value: 'str | None',
    dew_point_temp: 'str | None',
    ntc_temp: 'str | None',
    humidity: 'str | None',
    system_switch: 'str | None',
) -> None:
    """T1 转移：INSERT condensation_warning_event(is_active=True)。

    同时调用 _get_system_switch_for_specific_part 兜底（若 caller 未提供 system_switch）。
    IntegrityError 兜底：改为 UPDATE last_seen_at + 更新内存。

    system_switch 优先级（ADR-CW-01/RISK-CW-ARCH-01）：
      1. 入参 system_switch 非 None → 直接使用（来自 MQTT 直取路径，已规范化为 on/off/unknown）
      2. 入参 system_switch 为 None → 调用 _get_system_switch_for_specific_part（PLCLatestData 路径）
    """
    # system_switch 兜底（PLCLatestData 方案 A）
    if system_switch is None:
        system_switch = _get_system_switch_for_specific_part(specific_part)

    close_old_connections()
    try:
        from api.models import CondensationWarningEvent
        room_name, room_id = get_room_for_device(device_sn)
        cwe = CondensationWarningEvent.objects.create(
            specific_part=specific_part,
            device_sn=device_sn,
            product_code=product_code,
            room_name=room_name,
            room_id_id=room_id,
            warning_type='结露预警',
            warning_message='结露报警',
            condensation_alarm_value=condensation_alarm_value,
            dew_point_temp=dew_point_temp,
            ntc_temp=ntc_temp,
            humidity=humidity,
            system_switch=system_switch,
            first_seen_at=received_at,
            last_seen_at=received_at,
            recovered_at=None,
            is_active=True,
        )
        _cw_state_machine[key] = CondensationState(
            event_id=cwe.id,
            is_active=True,
            last_seen_at=received_at,
            last_persisted_at=received_at,  # INSERT 已写入 last_seen_at=received_at
        )
        logger.debug('T1 INSERT condensation_warning_event id=%d key=%s system_switch=%s',
                     cwe.id, key, system_switch)
    except IntegrityError:
        # 竞态（如重启重建窗口）：改为 UPDATE last_seen_at
        logger.warning('T1 IntegrityError，fallback to UPDATE last_seen_at: key=%s', key)
        _t1_fallback_update(key, specific_part, device_sn, received_at)
    except OperationalError as exc:
        logger.error('T1 OperationalError（DB 连接问题）: %s key=%s', exc, key)
    except Exception as exc:
        logger.exception('T1 未预期异常: %s key=%s', exc, key)


def _t1_fallback_update(
    key: tuple,
    specific_part: str,
    device_sn: str,
    received_at: datetime,
) -> None:
    """T1 IntegrityError 兜底：更新已有行的 last_seen_at，并同步内存。"""
    try:
        from api.models import CondensationWarningEvent
        cwe = CondensationWarningEvent.objects.filter(
            specific_part=specific_part,
            device_sn=device_sn,
            is_active=True,
        ).order_by('-first_seen_at').first()
        if cwe:
            cwe.last_seen_at = received_at
            cwe.save(update_fields=['last_seen_at', 'updated_at'])
            _cw_state_machine[key] = CondensationState(
                event_id=cwe.id,
                is_active=True,
                last_seen_at=received_at,
                last_persisted_at=received_at,  # 兜底 UPDATE 已写入 last_seen_at=received_at
            )
    except Exception as exc:
        logger.error('T1 fallback UPDATE 失败: %s', exc)


def _t2_persist_last_seen(key: tuple, state: CondensationState, received_at: datetime) -> None:
    """T2 节流落库：低频 UPDATE condensation_warning_event.last_seen_at。

    仅在距上次落库超过 _CW_T2_PERSIST_THROTTLE_SECONDS 时调用，避免每条上报都写库。
    只更新仍活跃的行；失败不更新 state.last_persisted_at，下次 T2 越阈值会重试。
    """
    close_old_connections()
    try:
        from api.models import CondensationWarningEvent
        CondensationWarningEvent.objects.filter(id=state.event_id, is_active=True).update(
            last_seen_at=received_at,
        )
        state.last_persisted_at = received_at
        logger.debug('T2 PERSIST last_seen_at id=%d key=%s', state.event_id, key)
    except OperationalError as exc:
        logger.error('T2 PERSIST OperationalError（DB 连接问题）: %s key=%s', exc, key)
    except Exception as exc:
        logger.exception('T2 PERSIST 未预期异常: %s key=%s', exc, key)


def _t3_recover(key: tuple, state: CondensationState, received_at: datetime) -> None:
    """T3 转移：UPDATE condensation_warning_event SET is_active=False, recovered_at。"""
    close_old_connections()
    try:
        from api.models import CondensationWarningEvent
        CondensationWarningEvent.objects.filter(id=state.event_id).update(
            is_active=False,
            recovered_at=received_at,
            last_seen_at=state.last_seen_at,  # 写回内存中的最后活跃时间
        )
        _cw_state_machine[key].is_active = False
        logger.debug('T3 RECOVER condensation_warning_event id=%d key=%s',
                     state.event_id, key)
    except OperationalError as exc:
        logger.error('T3 OperationalError（DB 连接问题）: %s key=%s', exc, key)
    except Exception as exc:
        logger.exception('T3 未预期异常: %s key=%s', exc, key)


def _get_system_switch_for_specific_part(specific_part: str) -> str:
    """ADR-CW-01 方案 A：查 PLCLatestData(specific_part, param_name='system_switch')。

    数据来源说明（RISK-CW-ARCH-01 闭环）：
      PLCLatestData.value 是 BigIntegerField（PLC 数采侧写入整数）：
        - value == 0   → "off"（系统关闭）
        - value != 0   → "on"（系统开启）
        - 无记录/异常  → "unknown"

    注意：这与 MQTT 直取路径不同，MQTT attrValue 已是字符串 "on"/"off"，
    本函数仅处理 PLCLatestData 整数值到字符串的转换。

    Args:
        specific_part: 房号标识，如 "1-1-16-1601"

    Returns:
        "on" / "off" / "unknown"
    """
    close_old_connections()
    try:
        from api.models import PLCLatestData
        row = PLCLatestData.objects.filter(
            specific_part=specific_part,
            param_name='system_switch',
            value__isnull=False,
        ).order_by('-updated_at').first()
        if row is None:
            logger.debug('_get_system_switch: specific_part=%s 无记录，返回 unknown', specific_part)
            return 'unknown'
        # PLCLatestData.value 是整数：0=关，非0=开（ADR-CW-01/ADR-CW-04）
        return 'on' if row.value != 0 else 'off'
    except Exception as exc:
        logger.error('_get_system_switch 异常: %s specific_part=%s', exc, specific_part)
        return 'unknown'
