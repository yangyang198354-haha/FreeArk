"""
Migration 0029 — 新增 condensation_warning_event 表（v0.7.0-CW，DB-CW-01）

依赖：0028_fault_event_backfill_room
操作：CreateModel CondensationWarningEvent（DDL only，无历史数据回填）

MySQL/SQLite 双兼容：
  - VARCHAR/DATETIME/BOOLEAN/BigAutoField 均兼容两者
  - UniqueConstraint + Index 通过 Django ORM 自动适配
  - ForeignKey ON DELETE SET NULL 两者均支持

生产执行注意：
  - 新表 DDL 不锁现有表，可在服务运行期间执行
  - 推荐：停 condensation-consumer 后再 migrate（此时 consumer 尚未部署，无需顾虑）
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_fault_event_backfill_room'),
    ]

    operations = [
        migrations.CreateModel(
            name='CondensationWarningEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specific_part', models.CharField(db_index=True, max_length=64, verbose_name='房号')),
                ('device_sn', models.CharField(max_length=64, verbose_name='设备序列号')),
                ('product_code', models.CharField(max_length=32, verbose_name='产品编码')),
                ('room_name', models.CharField(blank=True, max_length=50, null=True, verbose_name='房间名')),
                ('warning_type', models.CharField(default='结露预警', max_length=32, verbose_name='预警类型')),
                ('warning_message', models.CharField(default='结露报警', max_length=255, verbose_name='预警内容')),
                ('condensation_alarm_value', models.CharField(blank=True, max_length=16, null=True, verbose_name='触发时 condensation_alarm 原始值')),
                ('dew_point_temp', models.CharField(blank=True, max_length=16, null=True, verbose_name='露点温度快照')),
                ('ntc_temp', models.CharField(blank=True, max_length=16, null=True, verbose_name='NTC温度快照')),
                ('humidity', models.CharField(blank=True, max_length=16, null=True, verbose_name='湿度快照')),
                ('system_switch', models.CharField(blank=True, max_length=8, null=True, verbose_name='系统开关状态快照（on/off/unknown）')),
                ('first_seen_at', models.DateTimeField(db_index=True, verbose_name='预警首次出现时间')),
                ('last_seen_at', models.DateTimeField(verbose_name='最近活跃时间（进程内维护）')),
                ('recovered_at', models.DateTimeField(blank=True, null=True, verbose_name='恢复时间')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='是否活跃')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('room_id', models.ForeignKey(
                    blank=True,
                    db_column='room_id',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='condensation_warning_events',
                    to='api.deviceroom',
                    verbose_name='房间外键',
                )),
            ],
            options={
                'verbose_name': '结露预警事件',
                'verbose_name_plural': '结露预警事件',
                'db_table': 'condensation_warning_event',
            },
        ),
        migrations.AddConstraint(
            model_name='condensationwarningevent',
            constraint=models.UniqueConstraint(
                fields=['specific_part', 'device_sn', 'first_seen_at'],
                name='uniq_cw_sp_sn_first_seen',
            ),
        ),
        migrations.AddIndex(
            model_name='condensationwarningevent',
            index=models.Index(fields=['specific_part', 'is_active'], name='idx_cw_sp_active'),
        ),
        migrations.AddIndex(
            model_name='condensationwarningevent',
            index=models.Index(fields=['first_seen_at', 'is_active'], name='idx_cw_time_active'),
        ),
    ]
