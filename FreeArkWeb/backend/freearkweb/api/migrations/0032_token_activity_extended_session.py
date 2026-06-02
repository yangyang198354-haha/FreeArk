# Adds extended_session flag to TokenActivity for the "7天内保持登录" feature.
# extended_session=True 时认证使用 SESSION_EXTENDED_TIMEOUT（默认 7 天）替代默认超时。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0031_drop_redundant_dph_specific_part_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='tokenactivity',
            name='extended_session',
            field=models.BooleanField(
                default=False,
                verbose_name='延长会话（7天保持登录）',
            ),
        ),
    ]
