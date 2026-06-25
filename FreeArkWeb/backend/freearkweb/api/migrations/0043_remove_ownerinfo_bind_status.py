"""
0042 — 移除 OwnerInfo.bind_status 死字段（"绑定状态列合并"清理）。

背景：OwnerInfo.bind_status（"已绑定/未绑定"）经全仓库调查确认为 vestigial 字段——
仅在业主管理页自显示+自过滤，无任何真实业务下游消费方（设备同步/巡检/看板/能耗均不读它）。
v1.8.0 起业主管理页改用 OwnerUserBinding（账号绑定）表达绑定状态，bind_status 列已合并移除。
本迁移删除该字段及其两个索引。生产 owner_info 现有数据全为"已绑定"，删除无业务损失。

本迁移**仅**移除 bind_status 相关结构，刻意不夹带 makemigrations 检出的其它历史漂移
（id 字段 AutoField/BigAutoField 标准化、索引自动重命名等）——那些是既有未迁移漂移，
不属本次范围，避免在生产 DB 上做计划外的索引重命名/字段变更。
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0042_rename_agent_user_to_energy_agent'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='ownerinfo',
            name='owner_info_bind_status_idx',
        ),
        migrations.RemoveIndex(
            model_name='ownerinfo',
            name='owner_info_bldg_unit_bind_idx',
        ),
        migrations.RemoveField(
            model_name='ownerinfo',
            name='bind_status',
        ),
    ]
