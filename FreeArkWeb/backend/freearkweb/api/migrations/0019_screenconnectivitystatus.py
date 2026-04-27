# MOD-BE-02 — ScreenConnectivityStatus 数据模型 Migration
# author_agent: sub_agent_software_developer
# project: FreeArk_DeviceManagement
# invocation_id: INVOKE-GROUP_C-001
# Note: renumbered from 0018 to 0019 to resolve conflict with 0018_deviceconfig_allow_multi_subtype

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    新建 ScreenConnectivityStatus 表（screen_connectivity_status），
    用于记录各户大屏 IP 连通性探测结果（每户一条，upsert）。
    依赖：('api', '0018_deviceconfig_allow_multi_subtype')
    """

    dependencies = [
        ('api', '0018_screenconnectivitystatus'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScreenConnectivityStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specific_part', models.CharField(
                    db_index=True,
                    max_length=20,
                    unique=True,
                    verbose_name='专有部分',
                )),
                ('status', models.CharField(
                    choices=[('online', '在线'), ('offline', '离线')],
                    max_length=10,
                    verbose_name='连通状态',
                )),
                ('last_checked_at', models.DateTimeField(verbose_name='最近检测时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='记录更新时间')),
            ],
            options={
                'verbose_name': '大屏连通性状态',
                'verbose_name_plural': '大屏连通性状态',
                'db_table': 'screen_connectivity_status',
            },
        ),
    ]
