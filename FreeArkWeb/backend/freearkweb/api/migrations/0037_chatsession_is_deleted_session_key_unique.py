# @module MOD-BE-01
# @author sub_agent_software_developer
# Generated migration: add is_deleted field to ChatSession + unique=True on session_key

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_add_rag_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatsession',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False, verbose_name='是否已删除'),
        ),
        migrations.AlterField(
            model_name='chatsession',
            name='session_key',
            field=models.CharField(max_length=36, unique=True),
        ),
    ]
