"""
更正 DeviceConfig 标签事实性错误：加湿上/下限是「湿度」不是「温度」。

背景：humidification_humidity_upper_limit / humidification_humidity_lower_limit
两个参数的底层是加湿湿度百分比（plc_config.json description 为「加湿湿度上/下限设置」，
屏端 attrTag humi_upper_limit / humi_lower_limit 单位 %），但 seed_device_config.py
播种时写成了「加湿温度上限」「加湿温度下限」，Web 参数页/设备面板据此展示，
用户会误以为在设温度。这是标签内容错误，不是措辞偏好。

为什么需要迁移：seed_device_config 对已存在行走 get_or_create，重跑不会更新
display_name，生产库里的旧值只能由本迁移改写。seed 文件已同步修正，
新环境播种即为正确值。

幂等：按 param_name + 旧 display_name 精确匹配更新，重复执行无副作用；
新环境（已是正确值）匹配不到行，不做任何事。
可回滚：改回旧的「温度」字样。
"""
from django.db import migrations

# param_name -> (错误旧值, 正确新值)
_FIXES = {
    'humidification_humidity_upper_limit': ('加湿温度上限', '加湿湿度上限'),
    'humidification_humidity_lower_limit': ('加湿温度下限', '加湿湿度下限'),
}


def _apply(apps, old_idx, new_idx):
    DeviceConfig = apps.get_model('api', 'DeviceConfig')
    for param_name, pair in _FIXES.items():
        DeviceConfig.objects.filter(
            param_name=param_name, display_name=pair[old_idx],
        ).update(display_name=pair[new_idx])


def fix_temperature_to_humidity(apps, schema_editor):
    _apply(apps, 0, 1)


def reverse_humidity_to_temperature(apps, schema_editor):
    _apply(apps, 1, 0)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0046_add_persona_to_customuser'),
    ]

    operations = [
        migrations.RunPython(fix_temperature_to_humidity, reverse_humidity_to_temperature),
    ]
