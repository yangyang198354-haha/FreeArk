# Generated for v0.9.0 session timeout feature (REQ-AUTH-001, ADR-v090-002)
# Creates api_token_activity table to store per-token last activity timestamp.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0029_add_condensation_warning_event'),
        ('authtoken', '0003_tokenproxy'),
    ]

    operations = [
        migrations.CreateModel(
            name='TokenActivity',
            fields=[
                ('token', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True,
                    related_name='activity',
                    serialize=False,
                    to='authtoken.token',
                    verbose_name='关联 Token',
                )),
                ('last_active_at', models.DateTimeField(
                    db_index=True,
                    verbose_name='最后活动时间',
                )),
            ],
            options={
                'verbose_name': 'Token 活动记录',
                'verbose_name_plural': 'Token 活动记录',
                'db_table': 'api_token_activity',
            },
        ),
    ]
