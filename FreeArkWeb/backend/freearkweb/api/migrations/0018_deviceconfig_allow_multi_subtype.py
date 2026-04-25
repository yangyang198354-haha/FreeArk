from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_rename_device_id_fields'),
    ]

    operations = [
        # 先去掉 param_name 的单列唯一约束
        migrations.AlterField(
            model_name='deviceconfig',
            name='param_name',
            field=models.CharField(max_length=100, verbose_name='参数名'),
        ),
        # 再加 (param_name, sub_type) 联合唯一约束
        migrations.AlterUniqueTogether(
            name='deviceconfig',
            unique_together={('param_name', 'sub_type')},
        ),
    ]
