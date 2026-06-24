"""
test_chat_image_upload.py — POST /api/chat/image-upload/ REST 集成测试（v1.5.0）

覆盖 AC-MQ-*：
  AC-MQ-001-01（正常上传 PNG → 200，含 upload_id 和 expires_in）
  AC-MQ-004-02（未认证 → 401）
  AC-MQ-007-02（超过 10MB → 413；非图片文件 → 400；存储满 → 503）
  AC-MQ-008-02（上传成功后 upload_id 可在 vision_service 中查到）

测试命名规则：TC-INT-NNN（REST 层集成测试）
测试级别：集成测试（跨 REST 视图 + vision_service 模块）

依赖：
  - Django test client（APITestCase）
  - SQLite（_RUNNING_TESTS 自动切换）
  - 不需要真实 doubao-vision（不涉及 analyze_image）

@module test_chat_image_upload
@covers MOD-MQ-02 (views_chat_image), MOD-MQ-03 (vision_service.store_upload/check_capacity)
@author sub_agent_test_engineer
"""

import io
from unittest.mock import patch

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

import api.vision_service as vs_module

User = get_user_model()


# ── 最小合法测试图像数据 ──────────────────────────────────────────────────────────
# 最小合法 PNG（1×1 像素，26 字节，含正确 PNG magic bytes）
MINIMAL_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
    b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
    b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01'
    b'\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)

# 最小合法 JPEG（JPEG SOI + APP0 标记 + EOI）
MINIMAL_JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 12 + b'\xff\xd9'

# 非图片文件（text 内容，扩展名可伪造为 .jpg）
FAKE_IMAGE_TEXT = b'This is not an image file, just plain text content.'

# 用于 URI
IMAGE_UPLOAD_URL = '/api/chat/image-upload/'


def _clear_store():
    """清空全局 vision_service 存储状态。"""
    with vs_module._store_lock:
        vs_module._upload_store.clear()
        vs_module._total_size = 0


class TestChatImageUpload(APITestCase):
    """TC-INT-001 ~ TC-INT-008：POST /api/chat/image-upload/ REST 集成测试。"""

    def setUp(self):
        _clear_store()
        self.user = User.objects.create_user(
            username='img_test_user', password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def tearDown(self):
        _clear_store()

    def _make_png_file(self, size_bytes=None, filename='test.png'):
        """构造 PNG 文件对象（InMemoryUploadedFile 行为）。"""
        if size_bytes is None:
            data = MINIMAL_PNG
        else:
            # 前 8 字节是 PNG magic，其余填充
            data = MINIMAL_PNG[:8] + b'\x00' * (size_bytes - 8)
        return io.BytesIO(data)

    def _make_jpeg_file(self):
        return io.BytesIO(MINIMAL_JPEG)

    def test_TC_INT_001_valid_png_upload_returns_200_with_upload_id(self):
        """TC-INT-001 (AC-MQ-001-01): 合法 PNG 上传 → 200，响应含 upload_id（UUID）和 expires_in。"""
        png_file = self._make_png_file()
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {'image': png_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('upload_id', data)
        self.assertIn('expires_in', data)

        # upload_id 应为有效 UUID 格式
        import uuid
        try:
            uuid.UUID(data['upload_id'])
        except ValueError:
            self.fail(f"upload_id={data['upload_id']!r} 不是合法 UUID")

        # expires_in 应为正整数
        self.assertIsInstance(data['expires_in'], int)
        self.assertGreater(data['expires_in'], 0)

    def test_TC_INT_002_valid_jpeg_upload_returns_200(self):
        """TC-INT-002 (AC-MQ-001-01): 合法 JPEG 上传 → 200。"""
        jpeg_file = self._make_jpeg_file()
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {'image': jpeg_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_TC_INT_003_unauthenticated_request_returns_401(self):
        """TC-INT-003 (AC-MQ-004-02): 未认证请求 → 401。"""
        self.client.credentials()  # 清除凭证
        png_file = self._make_png_file()
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {'image': png_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_TC_INT_004_oversized_file_returns_413(self):
        """TC-INT-004 (AC-MQ-007-02): 超过 10MB 文件 → 413。"""
        # 构造 PNG magic + 超过 10MB 的数据
        large_data = MINIMAL_PNG[:8] + b'\x00' * (11 * 1024 * 1024)
        large_file = io.BytesIO(large_data)
        # 需要设置 size 属性（Django InMemoryUploadedFile 有 .size 属性）
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {'image': large_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    def test_TC_INT_005_non_image_file_returns_400(self):
        """TC-INT-005 (AC-MQ-007-02): 非图片内容（魔数检测失败） → 400。"""
        fake_file = io.BytesIO(FAKE_IMAGE_TEXT)
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {'image': fake_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)

    def test_TC_INT_006_missing_image_field_returns_400(self):
        """TC-INT-006 (AC-MQ-001-01): 缺少 image 字段 → 400。"""
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_TC_INT_007_upload_id_stored_in_vision_service(self):
        """TC-INT-007 (AC-MQ-001-01): 上传成功后，upload_id 在 vision_service._upload_store 中可查到。"""
        png_file = self._make_png_file()
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {'image': png_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        upload_id = response.json()['upload_id']

        with vs_module._store_lock:
            self.assertIn(upload_id, vs_module._upload_store)
            entry = vs_module._upload_store[upload_id]
            self.assertEqual(entry['user_id'], self.user.id)

    def test_TC_INT_008_storage_full_returns_503(self):
        """TC-INT-008 (AC-MQ-007-02): 存储满时 → 503。"""
        png_file = self._make_png_file()
        with patch('api.views_chat_image.vision_service.check_capacity', return_value=False):
            response = self.client.post(
                IMAGE_UPLOAD_URL,
                {'image': png_file},
                format='multipart',
            )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        data = response.json()
        self.assertIn('error', data)

    def test_TC_INT_009_response_does_not_contain_image_bytes(self):
        """TC-INT-009 (AC-MQ-008-02): 响应体不含图片 bytes 或 base64 字符串。"""
        import base64
        png_file = self._make_png_file()
        response = self.client.post(
            IMAGE_UPLOAD_URL,
            {'image': png_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode('utf-8')

        # 不应含 base64 编码的图片内容
        b64_png = base64.b64encode(MINIMAL_PNG).decode('utf-8')
        self.assertNotIn(b64_png, body)

    def test_TC_INT_010_concurrent_upload_ids_are_unique(self):
        """TC-INT-010 (AC-MQ-001-01): 多次上传产生不同的 upload_id（唯一性）。"""
        ids = set()
        for _ in range(5):
            png_file = self._make_png_file()
            response = self.client.post(
                IMAGE_UPLOAD_URL,
                {'image': png_file},
                format='multipart',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            ids.add(response.json()['upload_id'])

        self.assertEqual(len(ids), 5, "多次上传应产生不同的 upload_id")


if __name__ == '__main__':
    import unittest
    unittest.main()
