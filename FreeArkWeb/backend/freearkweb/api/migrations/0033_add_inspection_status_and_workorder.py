"""
Migration 0033 — 自治巡检 Agent（v1.1.0-AIA，方案 B）地基

依赖：0032_token_activity_extended_session
操作：
  1) FaultEvent / CondensationWarningEvent 各新增 inspection_status + inspection_started_at
     —— 巡检处置状态机（OD-02 事件接入 / OD-03 状态持久化）。
     现有 fault_consumer / condensation_consumer 不读写这两个字段，新增对其零影响。
  2) CreateModel WorkOrder（表 inspection_work_order，ARCH §7）
     + 条件唯一约束 uniq_active_workorder_per_event（同一来源事件 OPEN/IN_PROGRESS
       下只允许一条活跃工单，防重复建单）
     + 索引 wo_status_time_idx / wo_source_idx

非破坏性 / MySQL·SQLite 双兼容：
  - 全部为 AddField（带 default / 可空）+ 新建表，不锁现有表，不触及现有约束与索引
    （fault_event 的 uq_fault_event_key_time、idx_fault_*；cw 的 uniq_cw_*、idx_cw_* 均不受影响）。
  - 条件唯一约束（partial unique index）：MySQL 8.0+/9.4 与 SQLite(Django 4.1+) 均支持；
    本仓 requirements 锁定 django>=5.2.0（OQ-01 已核实），双环境可用。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0032_token_activity_extended_session'),
    ]

    operations = [
        migrations.AddField(
            model_name='faultevent',
            name='inspection_status',
            field=models.CharField(
                choices=[('PENDING', '待巡检'), ('IN_PROGRESS', '巡检处理中'),
                         ('DONE', '已处置'), ('SKIPPED', '已跳过')],
                db_index=True, default='PENDING', max_length=16,
                verbose_name='巡检处置状态',
            ),
        ),
        migrations.AddField(
            model_name='faultevent',
            name='inspection_started_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='巡检开始时间'),
        ),
        migrations.AddField(
            model_name='condensationwarningevent',
            name='inspection_status',
            field=models.CharField(
                choices=[('PENDING', '待巡检'), ('IN_PROGRESS', '巡检处理中'),
                         ('DONE', '已处置'), ('SKIPPED', '已跳过')],
                db_index=True, default='PENDING', max_length=16,
                verbose_name='巡检处置状态',
            ),
        ),
        migrations.AddField(
            model_name='condensationwarningevent',
            name='inspection_started_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='巡检开始时间'),
        ),
        migrations.CreateModel(
            name='WorkOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ticket_id', models.CharField(help_text='人可读编号，格式 WO-YYYYMMDD-NNNNNN', max_length=32, unique=True, verbose_name='工单编号')),
                ('severity', models.CharField(max_length=16, verbose_name='严重级别')),
                ('source_event_type', models.CharField(choices=[('fault_event', '故障事件'), ('condensation_warning_event', '结露预警事件')], max_length=32, verbose_name='来源事件类型')),
                ('source_event_id', models.BigIntegerField(db_index=True, verbose_name='来源事件ID')),
                ('affected_device', models.CharField(help_text='格式 "{device_sn} / {specific_part}"', max_length=100, verbose_name='受影响设备')),
                ('symptom', models.TextField(help_text='来自事件 fault_message / warning_message', verbose_name='症状')),
                ('diagnosis', models.TextField(blank=True, help_text='来自 delegate_knowledge 分析摘要', verbose_name='诊断')),
                ('recommended_action', models.TextField(blank=True, help_text='来自 LLM 结论或被拦截的写提案', verbose_name='建议处置')),
                ('status', models.CharField(choices=[('OPEN', '待处理'), ('IN_PROGRESS', '处理中'), ('RESOLVED', '已解决'), ('CANCELLED', '已取消')], db_index=True, default='OPEN', max_length=16, verbose_name='工单状态')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='解决时间')),
                ('resolved_by', models.CharField(blank=True, max_length=100, verbose_name='解决人')),
            ],
            options={
                'verbose_name': '巡检工单',
                'verbose_name_plural': '巡检工单',
                'db_table': 'inspection_work_order',
            },
        ),
        migrations.AddConstraint(
            model_name='workorder',
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=['OPEN', 'IN_PROGRESS']),
                fields=['source_event_type', 'source_event_id'],
                name='uniq_active_workorder_per_event',
            ),
        ),
        migrations.AddIndex(
            model_name='workorder',
            index=models.Index(fields=['status', 'created_at'], name='wo_status_time_idx'),
        ),
        migrations.AddIndex(
            model_name='workorder',
            index=models.Index(fields=['source_event_type', 'source_event_id'], name='wo_source_idx'),
        ),
    ]
