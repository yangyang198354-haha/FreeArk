"""
0044 — PLCWriteRecord 新增 channel 字段（v1.10.0_miniprogram_param_settings）。

背景：小程序业主端通过屏端 MQTT 直连写参数后，尽力上报审计落 PLCWriteRecord。
新增 channel 区分写入通道来源：
  's7'         —— web → datacollection → S7（历史默认，旧数据自动取默认值）
  'screen-mqtt' —— 小程序直连屏端 MQTT（v1.10.0 新增）

本迁移**仅**新增 channel 字段（可空、默认 's7'），刻意不夹带 makemigrations
检出的其它历史漂移（既有未迁移漂移，不属本次范围）。
旧 web S7 链路读写不受影响（需求 C-01 零回归）。
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0043_remove_ownerinfo_bind_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='plcwriterecord',
            name='channel',
            field=models.CharField(blank=True, default='s7', max_length=16, null=True),
        ),
    ]
