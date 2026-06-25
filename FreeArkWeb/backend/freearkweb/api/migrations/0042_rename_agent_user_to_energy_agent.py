"""
服务账号改名：openclaw-agent → energy-agent。

背景：OpenClaw 网关那套已退役（v1.7.0），但后台 agent 写设备参数仍以该数据库
服务账号身份调内部 API。账号名沿用 OpenClaw 时代的 'openclaw-agent' 已名实不符，
改名为 'energy-agent'（与当前 energy-expert 写链路对应）。

幂等：仅当存在 username='openclaw-agent' 时改名；全新环境（CI/测试库无此账号）不做任何事。
可回滚：energy-agent → openclaw-agent。

注意：本迁移只改 username，不动 token——FREEARK_AGENT_TOKEN 的值不变，认证不受影响。
代码侧（authentication 服务账号白名单 / fa_direct 读身份 / orchestrator+视图 operator_override
前缀 / 龙虾 skill tier2_write）已同步改为 energy-agent，须与本迁移一同部署。
"""
from django.db import migrations


def rename_openclaw_to_energy(apps, schema_editor):
    CustomUser = apps.get_model('api', 'CustomUser')
    CustomUser.objects.filter(username='openclaw-agent').update(username='energy-agent')


def reverse_energy_to_openclaw(apps, schema_editor):
    CustomUser = apps.get_model('api', 'CustomUser')
    CustomUser.objects.filter(username='energy-agent').update(username='openclaw-agent')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0041_owner_user_wechat_binding'),
    ]

    operations = [
        migrations.RunPython(rename_openclaw_to_energy, reverse_energy_to_openclaw),
    ]
