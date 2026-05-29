"""
Migration 0027 — fault_event 新增 room_name / room_id 列（v0.6.4-FM-ROOM，ADR-v0.6.4-01）

DDL：
  ALTER TABLE fault_event ADD COLUMN room_name VARCHAR(50) NULL
  ALTER TABLE fault_event ADD COLUMN room_id INT NULL FK device_room(id) ON DELETE SET NULL

兼容性：SQLite（测试）和 MySQL 9.4（生产）均支持 AddField + ForeignKey SET_NULL。
回滚：migrate api 0026 执行 DROP COLUMN room_name, DROP COLUMN room_id。
注意：回滚前必须先回滚 migration 0028（如已执行），否则外键约束可能阻止 DROP COLUMN。
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0026_add_fault_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='faultevent',
            name='room_name',
            field=models.CharField(
                blank=True,
                help_text='冗余字段，存储 device_room.ori_room_name，fault_consumer T1 写入时填充',
                max_length=50,
                null=True,
                verbose_name='房间名称',
            ),
        ),
        migrations.AddField(
            model_name='faultevent',
            name='room_id',
            field=models.ForeignKey(
                blank=True,
                db_column='room_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fault_events',
                to='api.deviceroom',
                verbose_name='所属房间',
            ),
        ),
    ]
