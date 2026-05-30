# 删除 device_param_history.specific_part 上的冗余单列索引（2026-05-31 索引虚胖治理）。
#
# 背景：该单列索引（db_index=True 自动生成，生产实际名 device_param_history_device_id_db129413）
# 是以下两个复合索引的最左前缀，功能冗余：
#   - dev_hist_sp_cat_idx     (specific_part, collected_at)
#   - dev_hist_sp_pn_cat_idx  (specific_part, param_name, collected_at)
# 任何能命中单列 specific_part 索引的查询都能用复合索引的最左前缀替代。
# device_param_history 已达 ~745 万行、索引 4.75GB（删 3000 万行后虚胖），
# 删除此冗余索引永久减少索引体积。collected_at 单列索引（清理服务依赖）保留不动。
#
# 该迁移仅含一个 AlterField（db_index True→False），落到 MySQL/InnoDB 为
# 单条 DROP INDEX，属在线 DDL（ALGORITHM=INPLACE，不重建表），秒级完成、不阻塞读写。
#
# 注：本文件为手写的单一职责迁移。makemigrations 会顺带捕获仓库既有的
# 模型/迁移漂移（多张表的 RenameIndex、id→BigAutoField 等），那些与本次治理无关、
# 不应混入一次生产 DDL，故此处只保留 specific_part 这一项操作。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0030_add_token_activity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deviceparamhistory',
            name='specific_part',
            field=models.CharField(max_length=50, verbose_name='专有部分'),
        ),
    ]
