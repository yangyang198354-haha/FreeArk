"""
0045 — CustomUser 新增 avatar_url 和 nickname 字段（v1.12.0）。

背景：小程序个人中心展示头像和昵称。微信用户通过 chooseAvatar + type="nickname"
组件设置后，后端将头像上传至 MEDIA_ROOT/avatars/ 并持久化 avatar_url，
昵称写入 nickname 字段。两个字段均可空（存量用户默认 NULL），前端按降级逻辑展示。

已确认：本迁移仅含 AddField ×2，刻意不夹带 makemigrations 检出的历史漂移
（RenameIndex / BigAutoField），与 0044 的"最小改动"策略一致。
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0044_plcwriterecord_channel'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='avatar_url',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='头像URL'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='nickname',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='昵称'),
        ),
    ]
