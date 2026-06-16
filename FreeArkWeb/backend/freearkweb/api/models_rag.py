"""
api.models_rag — RAG 知识库数据模型（v1.4.0_sanheng_rag）

RagDocument: 文档台账，状态机 pending→parsing→indexed/failed
RagChunk:    向量块，embedding 以 numpy float32 BLOB 存储

Migration: 0036_add_rag_tables.py（依赖 0035_workorder_proposed_write）
"""

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class RagDocument(models.Model):
    """
    文档台账。每份上传文档对应一条记录，跟踪解析/向量化状态。

    状态机转换：
        pending → parsing  (后台线程启动)
        parsing → indexed  (所有 chunk 写入成功)
        parsing → failed   (任何步骤抛出异常)
        failed  → parsing  (管理员触发重试，重置为 pending)
    """

    STATUS_PENDING = 'pending'
    STATUS_PARSING = 'parsing'
    STATUS_INDEXED = 'indexed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PARSING, 'Parsing'),
        (STATUS_INDEXED, 'Indexed'),
        (STATUS_FAILED, 'Failed'),
    ]

    file_name = models.CharField(max_length=255, verbose_name='文件名')
    file_size = models.BigIntegerField(verbose_name='文件大小（字节）')
    uploaded_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name='rag_documents',
        verbose_name='上传人',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name='状态',
    )
    error_message = models.TextField(
        blank=True,
        default='',
        verbose_name='失败原因',
    )
    chunk_count = models.IntegerField(
        default=0,
        verbose_name='Chunk 数量',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'rag_document'
        verbose_name = 'RAG 文档'
        verbose_name_plural = 'RAG 文档'
        ordering = ['-created_at', '-id']  # -id 次级键：秒级 DATETIME 同秒并列时保证确定性
        indexes = [
            models.Index(fields=['status'], name='rag_doc_status_idx'),
            models.Index(fields=['-created_at'], name='rag_doc_created_idx'),
        ]

    def __str__(self):
        return f"RagDocument({self.id}, {self.file_name}, {self.status})"


class RagChunk(models.Model):
    """
    向量块。每个 chunk 对应文档的一段文字（或图片 OCR 文字），
    embedding 为 numpy float32 数组序列化（tobytes/frombuffer）。
    """

    document = models.ForeignKey(
        RagDocument,
        on_delete=models.CASCADE,
        related_name='chunks',
        verbose_name='所属文档',
    )
    chunk_index = models.IntegerField(verbose_name='块序号（0-based）')
    content = models.TextField(verbose_name='chunk 文字内容')
    embedding = models.BinaryField(verbose_name='向量（float32 BLOB）')
    page_or_section = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='来源定位',
    )
    is_image_ocr = models.BooleanField(
        default=False,
        verbose_name='是否来自图片 OCR',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'rag_chunk'
        verbose_name = 'RAG Chunk'
        verbose_name_plural = 'RAG Chunks'
        indexes = [
            models.Index(fields=['document'], name='rag_chunk_doc_idx'),
        ]

    def __str__(self):
        return f"RagChunk({self.id}, doc={self.document_id}, idx={self.chunk_index})"
