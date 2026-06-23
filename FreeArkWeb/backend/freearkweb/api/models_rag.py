"""
api.models_rag — RAG 知识库数据模型（v1.4.1_rag_image_citation）

RagDocument: 文档台账，状态机 pending→parsing→indexed/failed
RagChunk:    向量块，embedding 以 numpy float32 BLOB 存储
RagImage:    图片存储（DB BLOB 方案，ADR-IC-001），每条对应文档中一张图片

Migration:
  0036_add_rag_tables.py（依赖 0035_workorder_proposed_write）— 基线
  0039_rag_image.py（依赖 0038_chatsession_title）            — v1.4.1 新增

@module MOD-141-01
@implements IFC-141-301（通过 RagImage 模型 BinaryField）
@author sub_agent_software_developer
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

    # ── v1.4.1 新增字段（MOD-141-01）──────────────────────────────────────────
    image = models.ForeignKey(
        'RagImage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chunks',
        verbose_name='关联图片',
        help_text='仅 is_image_ocr=True 的 chunk 可能有关联图片；null=True 表示纯文字 chunk 或图片存储失败',
    )

    def __str__(self):
        return f"RagChunk({self.id}, doc={self.document_id}, idx={self.chunk_index})"


class RagImage(models.Model):
    """
    三恒知识库图片存储（DB BLOB 方案，ADR-IC-001）。

    每条记录对应文档中的一张图片，图片字节以 BinaryField 直接存入主库。
    文档删除时 CASCADE 自动清理关联图片行（REQ-FUNC-006）。

    约束：
    - image_data 上限由应用层 MAX_IMAGE_BYTES（10MB）约束，BinaryField 本身无 max_length
    - file_size 冗余存储：SELECT SUM(file_size) 不需要读 BLOB 列，便于运维监控
    - 取图端点（GET /api/rag/images/{id}/）从本表直接读取 image_data，不经向量缓存

    @module MOD-141-01
    @implements IFC-141-801（存储端）
    @author sub_agent_software_developer
    """

    document = models.ForeignKey(
        RagDocument,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='所属文档',
        help_text='文档删除时 CASCADE 自动清理图片行（REQ-FUNC-006）',
    )
    image_index = models.IntegerField(
        verbose_name='图片序号（0 起）',
        help_text='同文档内图片序号（0 起），便于日志定位',
    )
    page_or_section = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='来源定位',
        help_text='来源页/节，对齐现有 RagChunk.page_or_section 格式',
    )
    image_format = models.CharField(
        max_length=20,
        verbose_name='图片格式',
        help_text="图片格式：'png'/'jpeg'/'other'",
    )
    image_data = models.BinaryField(
        verbose_name='图片字节（BLOB）',
        help_text='原始图片字节（DB BLOB，应用层约束上限 10MB）',
    )
    file_size = models.IntegerField(
        verbose_name='字节大小',
        help_text='字节大小，冗余存储，便于 SUM(file_size) 监控不读 BLOB 列',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'api_ragimage'   # 显式声明（架构设计 ADR-IC-001，与 api_ragdocument/api_ragchunk 对齐命名意图）
        verbose_name = 'RAG 图片'
        verbose_name_plural = 'RAG 图片'
        indexes = [
            models.Index(fields=['document'], name='ragimage_document_idx'),
        ]

    def __str__(self):
        return f"RagImage({self.id}, doc={self.document_id}, idx={self.image_index}, fmt={self.image_format})"
