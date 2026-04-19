from django.db import migrations, models


class Migration(migrations.Migration):
    """
    将 DeviceConfig.device_id 重命名为 param_name，
    将 DeviceParamHistory.device_id 重命名为 specific_part，
    并同步更新相关索引名称。
    """

    dependencies = [
        ('api', '0016_deviceconfig_deviceparamhistory'),
    ]

    operations = [
        # DeviceConfig: device_id → param_name
        migrations.RenameField(
            model_name='deviceconfig',
            old_name='device_id',
            new_name='param_name',
        ),
        migrations.AlterModelOptions(
            name='deviceconfig',
            options={
                'ordering': ['group', 'sub_type', 'param_name'],
                'verbose_name': '设备配置',
                'verbose_name_plural': '设备配置',
            },
        ),
        migrations.AlterField(
            model_name='deviceconfig',
            name='param_name',
            field=models.CharField(max_length=100, unique=True, verbose_name='参数名'),
        ),

        # DeviceParamHistory: 删除旧索引（包含 device_id 字段引用）
        migrations.RemoveIndex(
            model_name='deviceparamhistory',
            name='dev_hist_did_cat_idx',
        ),
        migrations.RemoveIndex(
            model_name='deviceparamhistory',
            name='dev_hist_did_pn_cat_idx',
        ),

        # DeviceParamHistory: device_id → specific_part
        migrations.RenameField(
            model_name='deviceparamhistory',
            old_name='device_id',
            new_name='specific_part',
        ),
        migrations.AlterField(
            model_name='deviceparamhistory',
            name='specific_part',
            field=models.CharField(db_index=True, max_length=50, verbose_name='专有部分'),
        ),

        # DeviceParamHistory: 用新字段名重建索引
        migrations.AddIndex(
            model_name='deviceparamhistory',
            index=models.Index(fields=['specific_part', 'collected_at'], name='dev_hist_sp_cat_idx'),
        ),
        migrations.AddIndex(
            model_name='deviceparamhistory',
            index=models.Index(fields=['specific_part', 'param_name', 'collected_at'], name='dev_hist_sp_pn_cat_idx'),
        ),
    ]
