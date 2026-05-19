from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_plcwriterecord'),
    ]

    operations = [
        migrations.AddField(
            model_name='plcwriterecord',
            name='batch_request_id',
            field=models.CharField(
                max_length=64,
                null=True,
                blank=True,
                db_index=True,
                verbose_name='批量请求ID',
            ),
        ),
    ]
