from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_device_tree_sync'),
    ]

    operations = [
        migrations.CreateModel(
            name='PLCWriteRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_id', models.CharField(max_length=64, unique=True)),
                ('specific_part', models.CharField(db_index=True, max_length=20)),
                ('param_name', models.CharField(max_length=100)),
                ('old_value', models.CharField(default='', max_length=50)),
                ('new_value', models.CharField(max_length=50)),
                ('operator', models.CharField(max_length=150)),
                ('status', models.CharField(
                    choices=[('pending', '待回执'), ('success', '写入成功'), ('failed', '写入失败'), ('timeout', '超时未回执')],
                    default='pending',
                    max_length=20,
                )),
                ('error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('acked_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'plc_write_record',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['specific_part', 'created_at'], name='plcwr_sp_cat_idx'),
                    models.Index(fields=['status', 'created_at'], name='plcwr_status_cat_idx'),
                    models.Index(fields=['operator'], name='plcwr_operator_idx'),
                ],
            },
        ),
    ]
