"""
Migration 0036 — RAG 知识库两表（v1.4.0_sanheng_rag）

依赖：0035_workorder_proposed_write
操作：
  - CreateModel RagDocument（文档台账，含状态机字段）
  - CreateModel RagChunk（向量块，含 BinaryField embedding）
  - AddIndex（status, -created_at, document）

手写（仿 0035 风格）以规避本地 vs 生产 Django 版本迁移漂移（TD-MIGRATION-001）。
勿对本 app 跑全项目 makemigrations 自动生成。
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0035_workorder_proposed_write'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RagDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('file_name', models.CharField(max_length=255, verbose_name='文件名')),
                ('file_size', models.BigIntegerField(verbose_name='文件大小（字节）')),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('parsing', 'Parsing'),
                        ('indexed', 'Indexed'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=20,
                    verbose_name='状态',
                )),
                ('error_message', models.TextField(blank=True, default='',
                                                   verbose_name='失败原因')),
                ('chunk_count', models.IntegerField(default=0, verbose_name='Chunk 数量')),
                ('created_at', models.DateTimeField(auto_now_add=True,
                                                    verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True,
                                                    verbose_name='更新时间')),
                ('uploaded_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='rag_documents',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='上传人',
                )),
            ],
            options={
                'verbose_name': 'RAG 文档',
                'verbose_name_plural': 'RAG 文档',
                'db_table': 'rag_document',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='RagChunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('chunk_index', models.IntegerField(verbose_name='块序号（0-based）')),
                ('content', models.TextField(verbose_name='chunk 文字内容')),
                ('embedding', models.BinaryField(verbose_name='向量（float32 BLOB）')),
                ('page_or_section', models.CharField(
                    blank=True, default='', max_length=100,
                    verbose_name='来源定位',
                )),
                ('is_image_ocr', models.BooleanField(default=False,
                                                      verbose_name='是否来自图片 OCR')),
                ('created_at', models.DateTimeField(auto_now_add=True,
                                                    verbose_name='创建时间')),
                ('document', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='chunks',
                    to='api.ragdocument',
                    verbose_name='所属文档',
                )),
            ],
            options={
                'verbose_name': 'RAG Chunk',
                'verbose_name_plural': 'RAG Chunks',
                'db_table': 'rag_chunk',
            },
        ),
        migrations.AddIndex(
            model_name='ragdocument',
            index=models.Index(fields=['status'], name='rag_doc_status_idx'),
        ),
        migrations.AddIndex(
            model_name='ragdocument',
            index=models.Index(fields=['-created_at'], name='rag_doc_created_idx'),
        ),
        migrations.AddIndex(
            model_name='ragchunk',
            index=models.Index(fields=['document'], name='rag_chunk_doc_idx'),
        ),
    ]
