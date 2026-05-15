# 设备树同步 — 新建 5 张表
# DeviceFloor / DeviceRoom / DeviceNode / DeviceAttrDef / DeviceAttrBinding
# 来源：屏侧 floor-room-device/list 接口
# 关系：OwnerInfo 1:N DeviceFloor 1:N DeviceRoom 1:N DeviceNode N:M DeviceAttrDef

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_plcstatuschangehistory_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceAttrDef',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_code', models.CharField(max_length=20, verbose_name='产品编码')),
                ('attr_tag', models.CharField(max_length=50, verbose_name='属性标签')),
                ('attr_value_type', models.SmallIntegerField(verbose_name='取值类型')),
                ('attr_constraint', models.SmallIntegerField(verbose_name='约束')),
                ('select_values_json', models.TextField(blank=True, default='', verbose_name='枚举值JSON')),
                ('num_value_json', models.TextField(blank=True, default='', verbose_name='数值范围JSON')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='最后同步时间')),
            ],
            options={
                'verbose_name': '设备属性定义',
                'verbose_name_plural': '设备属性定义',
                'db_table': 'device_attr_def',
            },
        ),
        migrations.AddConstraint(
            model_name='deviceattrdef',
            constraint=models.UniqueConstraint(fields=('product_code', 'attr_tag'), name='uniq_attr_def_prod_tag'),
        ),
        migrations.AddIndex(
            model_name='deviceattrdef',
            index=models.Index(fields=['product_code'], name='dad_product_code_idx'),
        ),
        migrations.AddIndex(
            model_name='deviceattrdef',
            index=models.Index(fields=['attr_tag'], name='dad_attr_tag_idx'),
        ),

        migrations.CreateModel(
            name='DeviceFloor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('floor_no', models.IntegerField(verbose_name='楼层号')),
                ('floor_name', models.CharField(max_length=20, verbose_name='楼层名')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='最后同步时间')),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='floors',
                    to='api.ownerinfo',
                    verbose_name='所属业主',
                )),
            ],
            options={
                'verbose_name': '设备楼层',
                'verbose_name_plural': '设备楼层',
                'db_table': 'device_floor',
            },
        ),
        migrations.AddConstraint(
            model_name='devicefloor',
            constraint=models.UniqueConstraint(fields=('owner', 'floor_no'), name='uniq_floor_owner_no'),
        ),
        migrations.AddIndex(
            model_name='devicefloor',
            index=models.Index(fields=['owner'], name='df_owner_idx'),
        ),

        migrations.CreateModel(
            name='DeviceRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=50, verbose_name='房间名')),
                ('ori_room_name', models.CharField(max_length=50, verbose_name='原始房间名')),
                ('room_type', models.IntegerField(verbose_name='房间类型')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='最后同步时间')),
                ('floor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rooms',
                    to='api.devicefloor',
                    verbose_name='所属楼层',
                )),
            ],
            options={
                'verbose_name': '设备房间',
                'verbose_name_plural': '设备房间',
                'db_table': 'device_room',
            },
        ),
        migrations.AddConstraint(
            model_name='deviceroom',
            constraint=models.UniqueConstraint(fields=('floor', 'ori_room_name'), name='uniq_room_floor_oriname'),
        ),
        migrations.AddIndex(
            model_name='deviceroom',
            index=models.Index(fields=['floor'], name='dr_floor_idx'),
        ),
        migrations.AddIndex(
            model_name='deviceroom',
            index=models.Index(fields=['room_type'], name='dr_room_type_idx'),
        ),

        migrations.CreateModel(
            name='DeviceNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_sn', models.IntegerField(verbose_name='设备SN')),
                ('device_name', models.CharField(max_length=50, verbose_name='设备名')),
                ('system_flag', models.SmallIntegerField(verbose_name='系统标识')),
                ('related_device_sn', models.IntegerField(blank=True, null=True, verbose_name='所属主机SN')),
                ('product_code', models.CharField(max_length=20, verbose_name='产品编码')),
                ('category_code', models.IntegerField(verbose_name='品类编码')),
                ('protocol', models.SmallIntegerField(blank=True, null=True, verbose_name='通信协议')),
                ('address_code', models.SmallIntegerField(blank=True, null=True, verbose_name='总线地址')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='最后同步时间')),
                ('room', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='devices',
                    to='api.deviceroom',
                    verbose_name='所属房间',
                )),
            ],
            options={
                'verbose_name': '设备节点',
                'verbose_name_plural': '设备节点',
                'db_table': 'device_node',
            },
        ),
        migrations.AddConstraint(
            model_name='devicenode',
            constraint=models.UniqueConstraint(fields=('room', 'device_sn'), name='uniq_node_room_sn'),
        ),
        migrations.AddIndex(
            model_name='devicenode',
            index=models.Index(fields=['room'], name='dn_room_idx'),
        ),
        migrations.AddIndex(
            model_name='devicenode',
            index=models.Index(fields=['device_sn'], name='dn_device_sn_idx'),
        ),
        migrations.AddIndex(
            model_name='devicenode',
            index=models.Index(fields=['product_code'], name='dn_product_code_idx'),
        ),
        migrations.AddIndex(
            model_name='devicenode',
            index=models.Index(fields=['related_device_sn'], name='dn_related_sn_idx'),
        ),

        migrations.CreateModel(
            name='DeviceAttrBinding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='attr_bindings',
                    to='api.devicenode',
                    verbose_name='设备',
                )),
                ('attr_def', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='bindings',
                    to='api.deviceattrdef',
                    verbose_name='属性定义',
                )),
            ],
            options={
                'verbose_name': '设备属性绑定',
                'verbose_name_plural': '设备属性绑定',
                'db_table': 'device_attr_binding',
            },
        ),
        migrations.AddConstraint(
            model_name='deviceattrbinding',
            constraint=models.UniqueConstraint(fields=('device', 'attr_def'), name='uniq_binding_dev_def'),
        ),
        migrations.AddIndex(
            model_name='deviceattrbinding',
            index=models.Index(fields=['device'], name='dab_device_idx'),
        ),
        migrations.AddIndex(
            model_name='deviceattrbinding',
            index=models.Index(fields=['attr_def'], name='dab_attr_def_idx'),
        ),

        migrations.AddField(
            model_name='devicenode',
            name='attrs',
            field=models.ManyToManyField(
                related_name='devices',
                through='api.DeviceAttrBinding',
                to='api.deviceattrdef',
                verbose_name='设备属性',
            ),
        ),
    ]
