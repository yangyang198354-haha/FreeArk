"""
Migration 0035 — 工单结构化写提案 + 人工审批执行字段（v1.3.1-WO）

依赖：0034_add_inspection_log
操作：向 inspection_work_order 表 AddField 6 列（proposed_tool/proposed_args/write_status/
      write_executed_at/write_executed_by/write_result），均有默认值，非破坏、可空安全。
手写（仿 0033/0034 风格）以规避本地 Django5.1 vs 生产 5.2 的既有迁移漂移
（TD-MIGRATION-001）——勿对本 app 跑全项目 makemigrations 自动生成。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0034_add_inspection_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='workorder',
            name='proposed_tool',
            field=models.CharField(blank=True, help_text='被拦截的写提案工具名（set_device_params/trigger_refresh）；空=无可执行写提案', max_length=32, verbose_name='建议写工具'),
        ),
        migrations.AddField(
            model_name='workorder',
            name='proposed_args',
            field=models.JSONField(blank=True, default=dict, help_text='写提案结构化参数，供人工审批后 execute_write 执行', verbose_name='建议写参数'),
        ),
        migrations.AddField(
            model_name='workorder',
            name='write_status',
            field=models.CharField(choices=[('NONE', '无写提案'), ('PENDING', '待审批执行'), ('EXECUTED', '已执行'), ('FAILED', '执行失败')], default='NONE', max_length=16, verbose_name='写提案状态'),
        ),
        migrations.AddField(
            model_name='workorder',
            name='write_executed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='写执行时间'),
        ),
        migrations.AddField(
            model_name='workorder',
            name='write_executed_by',
            field=models.CharField(blank=True, max_length=100, verbose_name='写执行人'),
        ),
        migrations.AddField(
            model_name='workorder',
            name='write_result',
            field=models.TextField(blank=True, verbose_name='写执行结果'),
        ),
    ]
