from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_delete_specificpartinfo'),
    ]

    operations = [
        migrations.CreateModel(
            name='PLCLatestData',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specific_part', models.CharField(db_index=True, max_length=20, verbose_name='专有部分')),
                ('param_name', models.CharField(max_length=100, verbose_name='参数名称')),
                ('value', models.BigIntegerField(blank=True, null=True, verbose_name='参数值')),
                ('collected_at', models.DateTimeField(blank=True, null=True, verbose_name='采集时间')),
                ('plc_ip', models.CharField(blank=True, default='', max_length=50, verbose_name='PLC IP地址')),
                ('building', models.CharField(blank=True, default='', max_length=10, verbose_name='楼栋')),
                ('unit', models.CharField(blank=True, default='', max_length=10, verbose_name='单元')),
                ('room_number', models.CharField(blank=True, default='', max_length=10, verbose_name='房号')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='记录更新时间')),
            ],
            options={
                'verbose_name': 'PLC最新参数数据',
                'verbose_name_plural': 'PLC最新参数数据',
                'db_table': 'plc_latest_data',
            },
        ),
        migrations.AlterUniqueTogether(
            name='plclatestdata',
            unique_together={('specific_part', 'param_name')},
        ),
        migrations.AddIndex(
            model_name='plclatestdata',
            index=models.Index(fields=['specific_part'], name='plc_latest__specifi_idx'),
        ),
        migrations.AddIndex(
            model_name='plclatestdata',
            index=models.Index(fields=['param_name'], name='plc_latest__param_n_idx'),
        ),
        migrations.AddIndex(
            model_name='plclatestdata',
            index=models.Index(fields=['specific_part', 'param_name'], name='plc_latest__sp_pn_idx'),
        ),
        migrations.AddIndex(
            model_name='plclatestdata',
            index=models.Index(fields=['collected_at'], name='plc_latest__collect_idx'),
        ),
    ]
