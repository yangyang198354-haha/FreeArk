from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_plclatestdata'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_id', models.CharField(max_length=100, unique=True, verbose_name='设备标识')),
                ('display_name', models.CharField(max_length=200, verbose_name='显示名称')),
                ('group', models.CharField(max_length=50, verbose_name='设备分组', db_index=True)),
                ('sub_type', models.CharField(max_length=50, verbose_name='设备子类型', db_index=True)),
                ('group_display', models.CharField(max_length=100, verbose_name='分组显示名称')),
                ('sub_type_display', models.CharField(max_length=100, verbose_name='子类型显示名称')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否激活', db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
            ],
            options={
                'verbose_name': '设备配置',
                'verbose_name_plural': '设备配置',
                'db_table': 'device_config',
                'ordering': ['group', 'sub_type', 'display_name'],
            },
        ),
        migrations.CreateModel(
            name='DeviceParamHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_id', models.CharField(max_length=100, verbose_name='设备标识', db_index=True)),
                ('param_name', models.CharField(max_length=100, verbose_name='参数名称')),
                ('value', models.TextField(null=True, blank=True, verbose_name='参数值')),
                ('collected_at', models.DateTimeField(verbose_name='采集时间', db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='记录创建时间')),
            ],
            options={
                'verbose_name': '设备参数历史',
                'verbose_name_plural': '设备参数历史',
                'db_table': 'device_param_history',
            },
        ),
        migrations.AddIndex(
            model_name='deviceparamhistory',
            index=models.Index(fields=['device_id', 'collected_at'], name='dev_hist_did_cat_idx'),
        ),
        migrations.AddIndex(
            model_name='deviceparamhistory',
            index=models.Index(fields=['device_id', 'param_name', 'collected_at'], name='dev_hist_did_pn_cat_idx'),
        ),
    ]
