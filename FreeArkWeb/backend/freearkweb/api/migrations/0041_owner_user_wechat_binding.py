"""
Migration 0041 — v1.8.0_miniprogram_owner_account

新增两张表（纯 CreateModel，不修改任何现有表结构）：
  - wechat_binding        : User ↔ WeChat openid 关联（零侵入 CustomUser）
  - owner_user_binding    : User ↔ OwnerInfo 多对多绑定关系（含 active 标志）
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0040_rbac_add_operator_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='WechatBinding',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='wechat_bindings',
                    to='api.customuser',
                    verbose_name='FreeArk 用户',
                )),
                ('openid', models.CharField(
                    db_index=True, max_length=128, unique=True,
                    verbose_name='微信 openid',
                )),
                ('unionid', models.CharField(
                    blank=True, max_length=128, null=True,
                    verbose_name='微信 unionid（可选）',
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='绑定时间',
                )),
            ],
            options={
                'verbose_name': '微信账号绑定',
                'verbose_name_plural': '微信账号绑定',
                'db_table': 'wechat_binding',
            },
        ),
        migrations.CreateModel(
            name='OwnerUserBinding',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='owner_bindings',
                    to='api.customuser',
                    verbose_name='FreeArk 用户',
                )),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='user_bindings',
                    to='api.ownerinfo',
                    verbose_name='专有部分',
                )),
                ('active', models.BooleanField(
                    db_index=True, default=True, verbose_name='是否有效',
                )),
                ('bound_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='绑定时间',
                )),
                ('unbound_at', models.DateTimeField(
                    blank=True, null=True, verbose_name='解绑时间',
                )),
            ],
            options={
                'verbose_name': '业主账号绑定',
                'verbose_name_plural': '业主账号绑定',
                'db_table': 'owner_user_binding',
            },
        ),
        migrations.AddIndex(
            model_name='wechatbinding',
            index=models.Index(fields=['user'], name='wechat_bind_user_idx'),
        ),
        migrations.AddIndex(
            model_name='owneruserbinding',
            index=models.Index(fields=['user', 'active'], name='oub_user_active_idx'),
        ),
        migrations.AddIndex(
            model_name='owneruserbinding',
            index=models.Index(fields=['owner', 'active'], name='oub_owner_active_idx'),
        ),
    ]
