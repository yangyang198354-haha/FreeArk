# Generated migration for OwnerInfo model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_specificpartinfo'),
    ]

    operations = [
        migrations.CreateModel(
            name='OwnerInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specific_part', models.CharField(db_index=True, max_length=20, unique=True, verbose_name='专有部分')),
                ('location_name', models.CharField(blank=True, max_length=100, verbose_name='专有部分坐落')),
                ('building', models.CharField(db_index=True, max_length=10, verbose_name='楼栋')),
                ('unit', models.CharField(db_index=True, max_length=10, verbose_name='单元')),
                ('floor', models.CharField(blank=True, max_length=10, verbose_name='楼层')),
                ('room_number', models.CharField(max_length=10, verbose_name='户号')),
                ('bind_status', models.CharField(blank=True, db_index=True, max_length=20, verbose_name='绑定状态')),
                ('ip_address', models.CharField(blank=True, max_length=50, verbose_name='IP地址')),
                ('unique_id', models.CharField(blank=True, db_index=True, max_length=50, verbose_name='唯一标识符')),
                ('plc_ip_address', models.CharField(blank=True, max_length=50, verbose_name='PLC IP地址')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='记录创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='记录更新时间')),
            ],
            options={
                'verbose_name': '业主信息',
                'verbose_name_plural': '业主信息',
                'db_table': 'owner_info',
                'indexes': [
                    models.Index(fields=['building'], name='owner_info_building_idx'),
                    models.Index(fields=['unit'], name='owner_info_unit_idx'),
                    models.Index(fields=['bind_status'], name='owner_info_bind_status_idx'),
                    models.Index(fields=['building', 'unit'], name='owner_info_building_unit_idx'),
                    models.Index(fields=['building', 'unit', 'bind_status'], name='owner_info_bldg_unit_bind_idx'),
                ],
            },
        ),
    ]
