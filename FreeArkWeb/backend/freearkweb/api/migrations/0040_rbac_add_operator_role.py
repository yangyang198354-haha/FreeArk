"""
v1.6.0 三角色 RBAC：新增 operator 角色 + 存量数据迁移。

变更：
  1. AlterField：CustomUser.role 的 choices 增加 ('operator', '运维人员')，
     'user' 标签改为 '普通业主/住户'，default 由 'user' 改为 'operator'。
     （choices/default 为应用层约束，不改变 DB 列类型 VARCHAR(20)。）
  2. RunPython：将所有 role='user' 的存量账号迁移为 role='operator'
     （含 openclaw-agent 等内部账号——旧 'user' 语义即运维侧）。可回滚。

确认依据：用户 2026-06-24 确认 OQ-04（无默认强制选择，模型层默认 operator）
与 OQ-05（存量 user 全量迁移为 operator）。
"""
from django.db import migrations, models


def migrate_user_to_operator(apps, schema_editor):
    """存量 role='user' → 'operator'（旧 user 语义即运维人员）。"""
    CustomUser = apps.get_model('api', 'CustomUser')
    CustomUser.objects.filter(role='user').update(role='operator')


def reverse_operator_to_user(apps, schema_editor):
    """回滚：role='operator' → 'user'。admin 不受影响。"""
    CustomUser = apps.get_model('api', 'CustomUser')
    CustomUser.objects.filter(role='operator').update(role='user')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0039_rag_image'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', '管理员'),
                    ('operator', '运维人员'),
                    ('user', '普通业主/住户'),
                ],
                default='operator',
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_user_to_operator, reverse_operator_to_user),
    ]
