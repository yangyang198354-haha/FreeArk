"""
api.views_rag — RAG 知识库 API 视图（v1.4.1_rag_image_citation）

端点：
  GET  /api/rag/documents/              列出所有文档（管理员）
  POST /api/rag/documents/              上传文档（管理员，异步入库）
  DELETE /api/rag/documents/{id}/       删除文档+向量（管理员）
  POST /api/rag/documents/{id}/retry/   失败文档重试（管理员）
  GET  /api/rag/images/{image_id}/      取图（所有已登录用户，v1.4.1 新增）

权限：
  文档管理端点：IsAdminUser（本项目自定义，校验 role=='admin'；非 DRF 内置的 is_staff）。
  取图端点：    IsAuthenticated（Bearer Token，所有已登录用户，REQ-NFR-004）。

安全：文件双重校验（扩展名 + 文件头字节签名）；原始文件不落盘。

@module MOD-141-08（RagImageView）
@implements IFC-141-801
@depends MOD-141-01（RagImage 模型）
@author sub_agent_software_developer
"""

from __future__ import annotations

import logging
import os

from django.db import transaction
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# 注意：用本项目 views.IsAdminUser（role=='admin'），不是 DRF 内置的 is_staff 版本。
# 本平台 admin 概念 = User.role=='admin'，与设备写授权/工单审批保持一致。
from .views import IsAdminUser
from .models_rag import RagDocument
from .rag_service import rag_vector_cache, start_ingest_thread
from .serializers_rag import RagDocumentSerializer

logger = logging.getLogger("api.views_rag")

# ── 常量 ──────────────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {'.pdf', '.docx'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# 文件头字节签名白名单（双重校验，防伪造扩展名）
_FILE_SIGNATURES = [
    (b'%PDF', '.pdf'),           # PDF
    (b'PK\x03\x04', '.docx'),   # ZIP/DOCX
]


def _validate_upload_file(f) -> str:
    """
    校验上传文件：扩展名、大小、文件头签名。
    返回小写扩展名（'.pdf' 或 '.docx'）。
    校验失败抛 ValidationError（DRF 会转为 400 响应）。
    """
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError("不支持的文件类型，仅接受 .docx 和 .pdf")

    if f.size > MAX_FILE_SIZE:
        raise ValidationError("文件超过 50MB 限制")

    # 读文件头（8字节）做签名校验，然后 seek 回起点
    header = f.read(8)
    f.seek(0)
    matched = any(header.startswith(sig) for sig, _ in _FILE_SIGNATURES)
    if not matched:
        raise ValidationError("不支持的文件类型，仅接受 .docx 和 .pdf")

    return ext


# ── ViewSet ───────────────────────────────────────────────────────────────

class RagDocumentViewSet(viewsets.GenericViewSet):
    """
    RAG 文档管理 ViewSet。
    仅支持 GET（list）、POST（create）、DELETE（destroy）、
    POST（retry 自定义 action）。
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = RagDocumentSerializer
    # -id 次级排序键：MySQL DATETIME 默认秒级精度，同一秒上传的文档 created_at 相等，
    # 仅按 -created_at 排序在生产上不稳定（列表乱跳），加 -id 保证确定性。
    queryset = RagDocument.objects.order_by('-created_at', '-id')

    # ── GET /api/rag/documents/ ───────────────────────────────────────────
    def list(self, request):
        """列出所有文档（按创建时间倒序）。"""
        docs = self.get_queryset()
        serializer = self.get_serializer(docs, many=True)
        return Response(serializer.data)

    # ── POST /api/rag/documents/ ──────────────────────────────────────────
    def create(self, request):
        """
        上传文档：校验→创建 RagDocument(pending)→异步启动入库线程→立即返回 201。
        原始文件读入内存后释放，不落盘。
        """
        f = request.FILES.get('file')
        if f is None:
            return Response(
                {"error": "缺少 file 字段"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            file_ext = _validate_upload_file(f)
        except ValidationError as e:
            return Response(
                {"error": e.detail[0] if isinstance(e.detail, list) else str(e.detail)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 一次性读入内存（不落盘），释放文件对象
        file_bytes = f.read()
        file_name = f.name
        file_size = len(file_bytes)

        # 创建台账记录
        doc = RagDocument.objects.create(
            file_name=file_name,
            file_size=file_size,
            uploaded_by=request.user,
            status=RagDocument.STATUS_PENDING,
        )

        # transaction.on_commit：确保 DB 写完后再启动线程（防竞态）
        doc_id = doc.id
        transaction.on_commit(
            lambda: start_ingest_thread(doc_id, file_bytes, file_ext)
        )

        logger.info("views_rag: 文档 %s（id=%s）已入台账，等待异步入库", file_name, doc.id)
        serializer = self.get_serializer(doc)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ── DELETE /api/rag/documents/{id}/ ───────────────────────────────────
    def destroy(self, request, pk=None):
        """
        删除文档：删除 RagDocument → RagChunk 级联删除 → 触发缓存刷新。
        """
        try:
            doc = RagDocument.objects.get(pk=pk)
        except RagDocument.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        doc_name = doc.file_name
        doc.delete()
        # 缓存刷新（异步，不阻塞响应）
        rag_vector_cache.refresh()
        logger.info("views_rag: 文档 %s（id=%s）已删除，缓存刷新中", doc_name, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── POST /api/rag/documents/{id}/retry/ ───────────────────────────────
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """
        重试失败文档：仅 status=failed 可重试，重置为 pending，重新启动入库线程。
        注意：重试需重新上传文件（原始文件未落盘）。
        若请求中包含 file 字段，使用新文件；否则返回 400 提示重新上传。
        """
        try:
            doc = RagDocument.objects.get(pk=pk)
        except RagDocument.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if doc.status != RagDocument.STATUS_FAILED:
            return Response(
                {"error": f"仅 failed 状态的文档可重试，当前状态: {doc.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 重试需要重新提供文件（原始文件不持久化，见 OQ-03 决策）
        f = request.FILES.get('file')
        if f is None:
            return Response(
                {"error": "重试需要重新上传文件（原始文件未保存），请在重试时附带 file 字段"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            file_ext = _validate_upload_file(f)
        except ValidationError as e:
            return Response(
                {"error": e.detail[0] if isinstance(e.detail, list) else str(e.detail)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_bytes = f.read()

        # 重置状态
        doc.status = RagDocument.STATUS_PENDING
        doc.error_message = ''
        doc.chunk_count = 0
        doc.save(update_fields=['status', 'error_message', 'chunk_count', 'updated_at'])

        # 删除旧 chunk（若有残留）
        doc.chunks.all().delete()

        doc_id = doc.id
        transaction.on_commit(
            lambda: start_ingest_thread(doc_id, file_bytes, file_ext)
        )

        logger.info("views_rag: 文档 %s（id=%s）重试已触发", doc.file_name, doc.id)
        serializer = self.get_serializer(doc)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ── v1.4.1 新增：RagImageView（IFC-141-801，MOD-141-08）─────────────────────

class RagImageView(APIView):
    """
    GET /api/rag/images/<image_id>/

    返回图片二进制内容（image/png 或 image/jpeg）。
    权限：IsAuthenticated — 所有已登录用户（前端 Bearer Token 认证）。
    前端必须使用 authenticatedFetch 获取 Blob 后创建 blob: URL（REQ-FUNC-004/005）；
    直接请求 URL 会因无 Bearer Token 而 401（REQ-NFR-004 认证不绕过）。

    响应：
      200  图片字节（Content-Type: image/png 或 image/jpeg）
      404  image_id 不存在
    """

    permission_classes = [IsAuthenticated]

    # MIME 映射（按 RagImage.image_format，IFC-141-801 规范：仅 png/jpeg/other）
    _FORMAT_TO_MIME: dict = {
        'png': 'image/png',
        'jpeg': 'image/jpeg',
        'jpg': 'image/jpeg',
        'other': 'application/octet-stream',
    }

    def get(self, request, image_id: int):
        """
        返回指定 image_id 的原始图片字节。
        BinaryField 在 Python 层返回 memoryview（MySQL）或 bytes（SQLite），
        需调用 bytes() 转换后再写响应体（IFC-141-801 注意事项）。
        """
        from .models_rag import RagImage   # 延迟 import（与 ViewSet 放同文件，避免 import 序）
        try:
            img = RagImage.objects.only('image_data', 'image_format').get(pk=image_id)
        except RagImage.DoesNotExist:
            return HttpResponse(status=404)

        # BinaryField 兼容：SQLite 返回 bytes，MySQL 返回 memoryview
        img_bytes = bytes(img.image_data)
        mime = self._FORMAT_TO_MIME.get(img.image_format, 'application/octet-stream')

        response = HttpResponse(
            img_bytes,
            content_type=mime,
            status=200,
        )
        # REQ-NFR-004 安全要求：
        # Content-Disposition: inline — 防止浏览器将图片误判为可下载/可执行文件
        # Cache-Control: no-store — 图片可能含设备参数等敏感信息，禁止浏览器缓存
        response['Content-Disposition'] = 'inline'
        response['Cache-Control'] = 'no-store'
        return response
