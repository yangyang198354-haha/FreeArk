"""
Migration 0034 — 巡检智能体决策日志（v1.3.0-AOW，REQ-FUNC-WL-001）

依赖：0033_add_inspection_status_and_workorder
操作：CreateModel InspectionLog（表 inspection_log）+ 两个命名索引。
非破坏：全新表，与现有表名无冲突；不触及现有模型。
手写（仿 0033 风格）以规避本地 Django5.1 vs 生产 5.2 的既有迁移漂移
（TD-MIGRATION-001）误报——勿对本 app 跑全项目 makemigrations 自动生成。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0033_add_inspection_status_and_workorder'),
    ]

    operations = [
        migrations.CreateModel(
            name='InspectionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_event_type', models.CharField(choices=[('fault_event', '故障事件'), ('condensation_warning_event', '结露预警事件')], max_length=32, verbose_name='来源事件类型')),
                ('source_event_id', models.BigIntegerField(db_index=True, verbose_name='来源事件ID')),
                ('specific_part', models.CharField(db_index=True, max_length=64, verbose_name='房号')),
                ('event_type_display', models.CharField(blank=True, max_length=32, verbose_name='事件类型(人读)')),
                ('step', models.CharField(choices=[('PROCESS_STARTED', '开始处理'), ('EVENT_SKIPPED', '事件已恢复跳过'), ('DELEGATION_CALLED', '子专家委托'), ('DELEGATION_ERROR', '委托异常'), ('WRITE_PROPOSAL', 'LLM写提案'), ('WRITE_BLOCKED', '写提案被拦截'), ('WRITE_EXECUTED', '写操作执行'), ('WORKORDER_CREATED', '工单创建'), ('WORKORDER_EXISTED', '工单已存在'), ('DECISION_TIMEOUT', '决策超时兜底'), ('DECISION_ERROR', '决策异常兜底'), ('PROCESS_COMPLETED', '处置完成')], max_length=32, verbose_name='决策步骤')),
                ('step_detail', models.JSONField(blank=True, default=dict, verbose_name='步骤详情')),
                ('result', models.CharField(default='INFO', max_length=16, verbose_name='结果')),
                ('work_order_ticket', models.CharField(blank=True, max_length=32, verbose_name='关联工单编号')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='记录时间')),
            ],
            options={
                'verbose_name': '巡检决策日志',
                'verbose_name_plural': '巡检决策日志',
                'db_table': 'inspection_log',
            },
        ),
        migrations.AddIndex(
            model_name='inspectionlog',
            index=models.Index(fields=['source_event_type', 'source_event_id'], name='ilog_source_idx'),
        ),
        migrations.AddIndex(
            model_name='inspectionlog',
            index=models.Index(fields=['specific_part', 'created_at'], name='ilog_part_time_idx'),
        ),
    ]
