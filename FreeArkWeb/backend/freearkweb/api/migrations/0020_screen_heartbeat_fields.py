"""
Migration 0020: 大屏心跳方案字段改造

- RemoveField: ScreenConnectivityStatus.status
- RemoveField: ScreenConnectivityStatus.last_checked_at
- AddField:    ScreenConnectivityStatus.last_seen_at

依赖：0019_screenconnectivitystatus
"""
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_screenconnectivitystatus'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='screenconnectivitystatus',
            name='status',
        ),
        migrations.RemoveField(
            model_name='screenconnectivitystatus',
            name='last_checked_at',
        ),
        migrations.AddField(
            model_name='screenconnectivitystatus',
            name='last_seen_at',
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                verbose_name='最近心跳时间',
            ),
            preserve_default=False,
        ),
    ]
