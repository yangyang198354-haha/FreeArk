# @module MOD-141-02
# @author sub_agent_software_developer
# Migration 0039: 新增 RagImage 模型；RagChunk 追加 image FK
# Implements: REQ-FUNC-001（图片持久化）, REQ-FUNC-002（chunk 关联图片）, REQ-NFR-005（手写 migration）
# Depends on: ('api', '0038_chatsession_title')
#
# 执行顺序（3 步，零数据迁移）：
#   Step 1：创建 api_ragimage 表（BinaryField BLOB）
#   Step 2：创建 ragimage_document_idx 索引（document 列）
#   Step 3：api_ragchunk 追加 image_id 可空列（现有行自动 NULL，向后兼容）
#
# 注意：Step 3 在现有 api_ragchunk 追加 NULL 列，MySQL/SQLite 均支持在线 DDL，
#       不锁表（MySQL 5.6+），不需要应用停机。

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0038_chatsession_title'),   # 项目硬约束：必须依赖 0038
    ]

    operations = [
        # Step 1：创建 RagImage 表
        migrations.CreateModel(
            name='RagImage',
            fields=[
                ('id', models.AutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID',
                )),
                ('document', models.ForeignKey(
                    help_text='文档删除时 CASCADE 自动清理图片行（REQ-FUNC-006）',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='images',
                    to='api.ragdocument',
                    verbose_name='所属文档',
                )),
                ('image_index', models.IntegerField(
                    help_text='同文档内图片序号（0 起），便于日志定位',
                    verbose_name='图片序号（0 起）',
                )),
                ('page_or_section', models.CharField(
                    blank=True,
                    default='',
                    help_text='来源页/节，对齐现有 RagChunk.page_or_section 格式',
                    max_length=100,
                    verbose_name='来源定位',
                )),
                ('image_format', models.CharField(
                    help_text="图片格式：'png'/'jpeg'/'other'",
                    max_length=20,
                    verbose_name='图片格式',
                )),
                ('image_data', models.BinaryField(
                    help_text='原始图片字节（DB BLOB，应用层约束上限 10MB）',
                    verbose_name='图片字节（BLOB）',
                )),
                ('file_size', models.IntegerField(
                    help_text='字节大小，冗余存储，便于 SUM(file_size) 监控不读 BLOB 列',
                    verbose_name='字节大小',
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True,
                    verbose_name='创建时间',
                )),
            ],
            options={
                'verbose_name': 'RAG 图片',
                'verbose_name_plural': 'RAG 图片',
                'db_table': 'api_ragimage',
            },
        ),

        # Step 2：为 RagImage.document 添加索引（RagChunk 查关联图片 JOIN 走索引）
        migrations.AddIndex(
            model_name='ragimage',
            index=models.Index(
                fields=['document'],
                name='ragimage_document_idx',
            ),
        ),

        # Step 3：RagChunk 新增 image FK（null=True，向后兼容：现有行 image_id=NULL）
        migrations.AddField(
            model_name='ragchunk',
            name='image',
            field=models.ForeignKey(
                blank=True,
                help_text='仅 is_image_ocr=True 的 chunk 可能有关联图片；null=True 表示纯文字 chunk 或图片存储失败',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='chunks',
                to='api.ragimage',
                verbose_name='关联图片',
            ),
        ),
    ]
