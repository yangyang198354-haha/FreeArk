"""
api.views_chat_image — 图片预上传 REST 端点（v1.5.0 多模态提问）

端点：POST /api/chat/image-upload/
权限：IsAuthenticated（DRF TokenAuthentication，现有体系）
解析：MultiPartParser（multipart/form-data，字段名 image）

安全约束（REQ-NFR-003）：
  SC-002：日志绝不记录 image_bytes 或 base64 内容
  SC-004：IsAuthenticated 强制鉴权
  SC-005：upload_id 由 vision_service.store_upload 生成（UUID4）
  SC-006：MIME 白名单验证（魔数字节检测，不依赖 python-magic）

@module MOD-MQ-02
@implements IFC-MQ-02-001 (ChatImageUploadView.post)
@depends MOD-MQ-03 (vision_service.store_upload, vision_service.check_capacity)
@author sub_agent_software_developer
"""

import logging

from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import vision_service
from .vision_service import StorageCapacityError

logger = logging.getLogger("api.views_chat_image")

# MIME 白名单（魔数检测后与此集合比对）
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

# 服务端文件大小上限：10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024


def _detect_mime(data: bytes) -> str:
    """
    从文件头魔数字节检测 MIME 类型，不依赖 libmagic。

    检测规则：
      JPEG  : 首 3 字节 == b'\\xff\\xd8\\xff'
      PNG   : 首 8 字节 == b'\\x89PNG\\r\\n\\x1a\\n'
      WebP  : 首 4 字节 == b'RIFF' 且 字节 8-12 == b'WEBP'
      HEIC  : 字节 4-8 == b'ftyp' 且 字节 8-12 在 HEIC 品牌列表中
      其他  : 'application/octet-stream'（被白名单拒绝）
    """
    if len(data) < 12:
        return "application/octet-stream"

    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    # HEIC/HEIF：字节偏移 4-8 为 'ftyp'，偏移 8-12 为品牌标识
    _HEIC_BRANDS = {
        b"heic", b"heis", b"heix", b"hevc", b"hevx",
        b"heim", b"hemi", b"hefm", b"hevm",
        b"MiHE", b"MiHS", b"MiHM", b"MiHB", b"MiPB",
    }
    if data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
        return "image/heic"

    return "application/octet-stream"


class ChatImageUploadView(APIView):
    """
    图片预上传端点。

    校验顺序（与 module_design.md IFC-MQ-02-001 一致）：
      1. 取文件（字段名 image），不存在 → 400
      2. 读取文件头用于 MIME 检测（最多读 12 字节）
      3. MIME 白名单校验 → 不在列表 → 400
      4. 文件大小校验 → > 10MB → 413
      5. 容量检查 → 存储满 → 503
      6. 读取完整字节
      7. 存储并返回 upload_id

    日志：记录 user_id、size（bytes）、MIME 类型、upload_id；
    绝不记录 image_bytes 内容。
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        # 1. 取文件
        image_file = request.FILES.get("image")
        if image_file is None:
            return Response(
                {"error": "缺少图片文件，请在 form-data 中使用字段名 image 上传"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. 读文件头（用于 MIME 检测，不依赖 Content-Type 头）
        header_bytes = image_file.read(12)
        detected_mime = _detect_mime(header_bytes)
        image_file.seek(0)  # 重置读取位置

        # 3. MIME 白名单校验（魔数检测结果，防文件伪装）
        if detected_mime not in ALLOWED_MIME_TYPES:
            logger.info(
                "views_chat_image: 拒绝非图片文件 user_id=%s detected_mime=%s",
                request.user.id, detected_mime,
            )
            return Response(
                {"error": "不支持的文件格式，请上传 JPEG/PNG/WebP 图片"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. 文件大小校验（服务端二次校验，前端已有客户端限制）
        file_size = image_file.size
        if file_size > MAX_FILE_SIZE:
            logger.info(
                "views_chat_image: 文件过大 user_id=%s size=%d",
                request.user.id, file_size,
            )
            return Response(
                {"error": "文件过大，最大 10MB"},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # 5. 容量检查（进程内临时存储总量）
        if not vision_service.check_capacity():
            logger.warning(
                "views_chat_image: 临时存储已满，拒绝上传 user_id=%s",
                request.user.id,
            )
            return Response(
                {"error": "服务繁忙，请稍后重试"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # 6. 读取完整图片字节
        image_bytes = image_file.read()

        # 7. 存储并返回 upload_id
        try:
            upload_id = vision_service.store_upload(
                image_bytes=image_bytes,
                user_id=request.user.id,
            )
        except StorageCapacityError:
            # check_capacity 通过后极少发生（并发竞争场景），降级为 503
            return Response(
                {"error": "服务繁忙，请稍后重试"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        finally:
            # 帮助 GC：不在本 view 中持有图片引用
            del image_bytes

        logger.info(
            "views_chat_image: 上传成功 user_id=%s size=%d mime=%s upload_id=%s",
            request.user.id, file_size, detected_mime, upload_id,
        )

        from django.conf import settings
        ttl = getattr(settings, "VISION_UPLOAD_TTL", 600)

        return Response(
            {"upload_id": upload_id, "expires_in": ttl},
            status=status.HTTP_200_OK,
        )
