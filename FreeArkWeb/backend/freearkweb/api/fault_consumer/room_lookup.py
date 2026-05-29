"""
fault_consumer/room_lookup.py — device_sn 反查 DeviceRoom 辅助（MOD-BE-FM-v0.6.4）

职责：为 T1 INSERT 提供 room_name + room_id 填充数据。

设计约束：
  - 无进程内缓存（DeviceRoom 同步频率低，但变更不可预测，简单直查 DB）
  - 查找失败时返回 (None, None)，不抛异常，不影响 T1 主路径
  - 只在 T1 路径调用（新故障首次出现），不在 T2/T3 调用（不写 room 字段）

类型说明：
  - fault_event.device_sn 是 VARCHAR/CHAR（字符串）
  - device_node.device_sn 是 IntegerField（整数）
  - 本模块负责将字符串 device_sn 转为 int 后查 DeviceNode

参见：docs/architecture/architecture_design_v0.6.4_fault_mgmt_room_column.md 附录 E
"""

import logging

logger = logging.getLogger(__name__)


def get_room_for_device(device_sn: str) -> tuple[str | None, int | None]:
    """从 device_sn 反查 DeviceRoom，返回 (ori_room_name, room_id)。

    查找失败（DeviceNode 不存在 / room 未关联）时返回 (None, None)，不抛异常。

    Args:
        device_sn: FaultEvent.device_sn（字符串型，如 "22549"）

    Returns:
        (ori_room_name, room_id) 或 (None, None)
    """
    try:
        from api.models import DeviceNode
        sn_int = int(device_sn)
        dn = (
            DeviceNode.objects
            .select_related('room')
            .filter(device_sn=sn_int)
            .first()
        )
        if dn and dn.room:
            return dn.room.ori_room_name, dn.room_id
        return None, None
    except (ValueError, TypeError):
        # device_sn 不是有效整数（如脏数据 sn="abc"）
        logger.debug('get_room_for_device: device_sn 无法转为 int: %s', device_sn)
        return None, None
    except Exception as exc:
        logger.error('get_room_for_device 异常: %s device_sn=%s', exc, device_sn)
        return None, None
