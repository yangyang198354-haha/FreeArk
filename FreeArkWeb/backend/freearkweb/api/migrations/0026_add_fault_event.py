"""
Migration 0026 — 新增 fault_event 表（v0.6.0-FM，ADR-FM-04）

兼容性：SQLite（测试）和 MySQL 9.4（生产）均支持 UniqueConstraint + Index。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0025_chat_session_message'),
    ]

    operations = [
        migrations.CreateModel(
            name='FaultEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specific_part', models.CharField(max_length=64, verbose_name='房号')),
                ('device_sn', models.CharField(max_length=64, verbose_name='设备序列号')),
                ('product_code', models.CharField(max_length=32, verbose_name='产品编码')),
                ('fault_code', models.CharField(max_length=64, verbose_name='故障码')),
                ('fault_type', models.CharField(
                    max_length=16,
                    choices=[
                        ('comm',        '通信故障'),
                        ('sensor',      '传感器故障'),
                        ('fresh_air',   '新风故障'),
                        ('other_error', '其他故障'),
                    ],
                    verbose_name='故障大类',
                )),
                ('fault_message', models.CharField(max_length=255, verbose_name='故障描述')),
                ('severity', models.CharField(
                    max_length=8,
                    choices=[('error', 'Error'), ('warning', 'Warning')],
                    verbose_name='严重级别',
                )),
                ('first_seen_at', models.DateTimeField(verbose_name='首次出现时间')),
                ('last_seen_at', models.DateTimeField(verbose_name='最后活跃时间')),
                ('recovered_at', models.DateTimeField(blank=True, null=True, verbose_name='恢复时间')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否活跃')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '故障事件',
                'verbose_name_plural': '故障事件',
                'db_table': 'fault_event',
            },
        ),
        migrations.AddConstraint(
            model_name='faultevent',
            constraint=models.UniqueConstraint(
                fields=['specific_part', 'device_sn', 'fault_code', 'first_seen_at'],
                name='uq_fault_event_key_time',
            ),
        ),
        migrations.AddIndex(
            model_name='faultevent',
            index=models.Index(
                fields=['specific_part', 'is_active'],
                name='idx_fault_sp_active',
            ),
        ),
        migrations.AddIndex(
            model_name='faultevent',
            index=models.Index(
                fields=['first_seen_at', 'is_active'],
                name='idx_fault_time_active',
            ),
        ),
    ]
