"""
Migration 0028 — fault_event 历史数据回填 room_name / room_id（v0.6.4-FM-ROOM）

回填路径：device_sn(str) → DeviceNode(device_sn=int) → DeviceRoom → ori_room_name + id

类型对齐说明：
  - fault_event.device_sn 是 CHAR/VARCHAR（字符串）
  - device_node.device_sn 是 INT（整数）
  - ORM 回填通过 str(dn.device_sn) 构建字典 key，直接与 fe.device_sn（字符串）匹配，
    无需额外 CAST（db_evidence.md 查询 3 反查已验证此路径）

性能说明：
  - 生产 fault_event 约 3094 行，批量 bulk_update chunk_size=500，预计 <=10 秒
  - 在 fault_consumer 停止期间执行，避免并发写入干扰

回滚：将所有 fault_event.room_name + room_id 重置为 NULL（reverse_backfill_room）

参见：docs/architecture/architecture_design_v0.6.4_fault_mgmt_room_column.md 附录 D §5.2
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def backfill_room(apps, schema_editor):
    """回填 fault_event.room_name + room_id，通过 device_sn 反查 DeviceNode -> DeviceRoom。"""
    FaultEvent = apps.get_model('api', 'FaultEvent')
    DeviceNode = apps.get_model('api', 'DeviceNode')

    # 构建 device_sn(str) -> (ori_room_name, room_id) 字典
    # str(dn.device_sn) 将 IntegerField 值转为字符串，与 FaultEvent.device_sn (VARCHAR) 对齐
    sn_to_room = {}
    for dn in DeviceNode.objects.select_related('room').all():
        sn_key = str(dn.device_sn)
        if sn_key not in sn_to_room:
            sn_to_room[sn_key] = (dn.room.ori_room_name, dn.room.id)

    # 批量更新 fault_event（分批避免大事务）
    total_updated = 0
    batch_size = 500
    qs = FaultEvent.objects.filter(room_name__isnull=True)
    batch = []
    for fe in qs.iterator(chunk_size=batch_size):
        room_info = sn_to_room.get(fe.device_sn)
        if room_info:
            fe.room_name = room_info[0]
            fe.room_id_id = room_info[1]
            batch.append(fe)
        if len(batch) >= batch_size:
            FaultEvent.objects.bulk_update(batch, ['room_name', 'room_id'])
            total_updated += len(batch)
            batch = []
    if batch:
        FaultEvent.objects.bulk_update(batch, ['room_name', 'room_id'])
        total_updated += len(batch)

    logger.info('[migration 0028] backfill complete, updated %d rows', total_updated)


def reverse_backfill_room(apps, schema_editor):
    """回滚：重置所有 fault_event 的 room_name 和 room_id 为 NULL。"""
    FaultEvent = apps.get_model('api', 'FaultEvent')
    FaultEvent.objects.all().update(room_name=None, room_id_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_fault_event_room_columns'),
    ]

    operations = [
        migrations.RunPython(backfill_room, reverse_code=reverse_backfill_room),
    ]
