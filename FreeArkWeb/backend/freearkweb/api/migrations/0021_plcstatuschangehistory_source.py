from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_screen_heartbeat_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='plcstatuschangehistory',
            name='source',
            field=models.CharField(
                choices=[('mqtt', 'MQTT实时'), ('monitor', '超时巡检')],
                default='mqtt',
                max_length=10,
                verbose_name='来源',
            ),
        ),
    ]
