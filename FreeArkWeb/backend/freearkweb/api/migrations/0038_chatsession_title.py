# @module MOD-BE-MIG
# @author sub_agent_software_developer
# Migration 0038: Add title field to ChatSession
# Implements: REQ-NFR-003 (向后兼容，null=True)
# Depends on: 0037_chatsession_is_deleted_session_key_unique

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0037_chatsession_is_deleted_session_key_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatsession',
            name='title',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                verbose_name='会话标题',
            ),
        ),
    ]
