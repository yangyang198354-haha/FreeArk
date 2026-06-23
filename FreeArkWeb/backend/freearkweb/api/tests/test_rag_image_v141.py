"""
test_rag_image_v141.py — v1.4.1_rag_image_citation 特性测试套件

覆盖范围：
  US-IC-001 ~ US-IC-009（验收标准 AC-IC-*）

测试分层：
  TC-UNIT-001 ~ TC-UNIT-020  单元测试
  TC-INT-001  ~ TC-INT-003   集成测试

已知限制（WS 相关，见 test_report.md）：
  TC-UNIT-018 / TC-UNIT-019（_finalize_turn stream_end 载荷）使用 AsyncMock
  测试 _finalize_turn 内部逻辑，InMemory Channel Layer 可验证。
  WS 端到端（stream_end 经 Redis 到前端）需本地真 Redis 验证，
  已标注为"待人工验证"，不包含在本自动化套件中。

@feature v1.4.1_rag_image_citation
@author  sub_agent_test_engineer
"""

from __future__ import annotations

import asyncio
import json
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase, tag
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api.models_rag import RagDocument, RagChunk, RagImage
from api.rag_service import (
    _detect_image_format,
    MAX_IMAGE_BYTES,
    RagParser,
    RagVectorCache,
)
from django.contrib.auth import get_user_model

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username: str, password: str = "testpass123") -> object:
    return User.objects.create_user(username=username, password=password)


def _make_doc(user, file_name: str = "test.docx", status: str = "indexed") -> RagDocument:
    return RagDocument.objects.create(
        file_name=file_name,
        file_size=1024,
        uploaded_by=user,
        status=status,
    )


# ============================================================
# 1. RagImage 模型层测试
# ============================================================

@tag("unit")
class RagImageCascadeDeleteTest(TestCase):
    """TC-UNIT-001: 删除文档时 RagImage 被级联删除（AC-IC-006-01）"""

    def test_rag_image_cascade_delete(self):
        """
        TC-UNIT-001
        Given  创建 RagDocument 及关联的 RagImage
        When   删除 RagDocument
        Then   关联的 RagImage 记录也被删除（CASCADE）
        AC-IC-006-01
        """
        user = _make_user("tc_unit_001_user")
        doc = _make_doc(user)

        img = RagImage.objects.create(
            document=doc,
            image_index=0,
            page_or_section="第1页",
            image_format="png",
            image_data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
            file_size=24,
        )
        img_id = img.id
        self.assertTrue(RagImage.objects.filter(id=img_id).exists())

        doc.delete()
        self.assertFalse(RagImage.objects.filter(id=img_id).exists())


@tag("unit")
class RagChunkImageSetNullOnImageDeleteTest(TestCase):
    """TC-UNIT-002: 删除 RagImage 时 RagChunk.image_id 置 NULL（SET_NULL 语义）"""

    def test_rag_chunk_image_set_null_on_image_delete(self):
        """
        TC-UNIT-002
        Given  创建 RagImage 及关联的 RagChunk
        When   删除 RagImage
        Then   RagChunk.image_id 被置为 NULL（on_delete=SET_NULL）
        AC-IC-006-01（延伸：chunk 不被删除，仅 FK 置空）
        """
        user = _make_user("tc_unit_002_user")
        doc = _make_doc(user)

        img = RagImage.objects.create(
            document=doc,
            image_index=0,
            page_or_section="图片1",
            image_format="jpeg",
            image_data=b"\xff\xd8\xff\xe0" + b"\x00" * 16,
            file_size=20,
        )
        # 构造最小 chunk（embedding 是 float32 字节）
        dummy_vec = np.zeros(4, dtype=np.float32)
        chunk = RagChunk.objects.create(
            document=doc,
            chunk_index=0,
            content="图片 OCR 文字",
            embedding=dummy_vec.tobytes(),
            page_or_section="图片1",
            is_image_ocr=True,
            image=img,
        )
        chunk_id = chunk.id

        img.delete()

        chunk.refresh_from_db()
        self.assertIsNone(chunk.image_id)
        # chunk 本身未被删除
        self.assertTrue(RagChunk.objects.filter(id=chunk_id).exists())


# ============================================================
# 2. _detect_image_format 测试
# ============================================================

@tag("unit")
class DetectImageFormatTest(TestCase):
    """TC-UNIT-003 ~ TC-UNIT-006: _detect_image_format 函数（AC-IC-004-01/02）"""

    def test_detect_png(self):
        """TC-UNIT-003: PNG 文件头 → 'png'"""
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        self.assertEqual(_detect_image_format(png_header), "png")

    def test_detect_jpeg(self):
        """TC-UNIT-004: JPEG 文件头 → 'jpeg'"""
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 16
        self.assertEqual(_detect_image_format(jpeg_header), "jpeg")

    def test_detect_other(self):
        """TC-UNIT-005: 非 PNG/JPEG 字节 → 'other'"""
        random_bytes = b"\x00\x01\x02\x03\x04\x05\x06\x07"
        self.assertEqual(_detect_image_format(random_bytes), "other")

    def test_detect_empty(self):
        """TC-UNIT-006: 空字节 → 'other'（防御）"""
        self.assertEqual(_detect_image_format(b""), "other")


# ============================================================
# 3. _try_save_image_bytes 测试
# ============================================================

@tag("unit")
class TrySaveImageBytesTest(TestCase):
    """TC-UNIT-007 ~ TC-UNIT-009: RagParser._try_save_image_bytes（AC-IC-005-02）"""

    def test_try_save_small_image(self):
        """TC-UNIT-007: 8字节图片（< MAX_IMAGE_BYTES）→ 返回 (bytes, fmt)（通过）"""
        img_bytes = b"\x89PNG\r\n\x1a\n"
        result_bytes, result_fmt = RagParser._try_save_image_bytes(
            img_bytes, "png", "第1页 图片1"
        )
        self.assertEqual(result_bytes, img_bytes)
        self.assertEqual(result_fmt, "png")

    def test_try_save_oversized_image(self):
        """TC-UNIT-008: 11MB 字节（> MAX_IMAGE_BYTES=10MB）→ 返回 (None, '')（跳过）
        AC-IC-005-02
        """
        oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024)
        result_bytes, result_fmt = RagParser._try_save_image_bytes(
            oversized, "png", "第2页 图片1"
        )
        self.assertIsNone(result_bytes)
        self.assertEqual(result_fmt, "")

    def test_try_save_empty_bytes(self):
        """TC-UNIT-009: 空字节 → 返回 (None, '')（防御）"""
        result_bytes, result_fmt = RagParser._try_save_image_bytes(
            b"", "png", "图片0"
        )
        self.assertIsNone(result_bytes)
        self.assertEqual(result_fmt, "")


# ============================================================
# 4. RagVectorCache 新增 image_id 测试
# ============================================================

@tag("unit")
class RagVectorCacheImageIdTest(TestCase):
    """TC-UNIT-010 ~ TC-UNIT-011: RagVectorCache _meta image_id（AC-IC-008-01）"""

    def setUp(self):
        self.user = _make_user("tc_unit_010_user")
        self.doc = _make_doc(self.user, file_name="cache_test.docx", status="indexed")
        self.img = RagImage.objects.create(
            document=self.doc,
            image_index=0,
            page_or_section="图片1",
            image_format="png",
            image_data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
            file_size=24,
        )
        dummy_vec = np.zeros(4, dtype=np.float32)
        # chunk 有 image
        self.chunk_with_img = RagChunk.objects.create(
            document=self.doc,
            chunk_index=0,
            content="图片 OCR 内容",
            embedding=dummy_vec.tobytes(),
            page_or_section="图片1",
            is_image_ocr=True,
            image=self.img,
        )
        # chunk 无 image
        self.chunk_no_img = RagChunk.objects.create(
            document=self.doc,
            chunk_index=1,
            content="纯文字内容",
            embedding=dummy_vec.tobytes(),
            page_or_section="第1页",
            is_image_ocr=False,
            image=None,
        )

    def test_vector_cache_meta_has_image_id(self):
        """
        TC-UNIT-010
        Given  RagVectorCache.load() 完成，包含含图和不含图的 chunk
        When   检查 _meta 各条目
        Then   每个 meta dict 均含 image_id 字段（值为整数 id 或 None）
        AC-IC-008-01
        """
        cache = RagVectorCache()
        cache.load()
        self.assertTrue(cache._loaded)
        self.assertGreater(len(cache._meta), 0)
        for m in cache._meta:
            self.assertIn("image_id", m, f"meta 条目缺少 image_id 字段: {m}")

    def test_vector_cache_no_image_bytes(self):
        """
        TC-UNIT-011
        Given  RagVectorCache 已 load()
        When   检查 _meta 列表每个条目
        Then   不含任何 bytes 类型字段（REQ-NFR-001 图片字节不进缓存）
        AC-IC-008-01
        """
        cache = RagVectorCache()
        cache.load()
        for m in cache._meta:
            for k, v in m.items():
                self.assertNotIsInstance(
                    v, (bytes, bytearray, memoryview),
                    f"_meta['{k}'] 包含 bytes 类型数据，违反 REQ-NFR-001: type={type(v)}"
                )


# ============================================================
# 5. search_rag 返回 image_id 测试
# ============================================================

@tag("unit")
class SearchRagReturnsImageIdTest(TestCase):
    """TC-UNIT-012: search_rag() 返回 chunk dict 含 image_id（AC-IC-001-01/04）"""

    def setUp(self):
        self.user = _make_user("tc_unit_012_user")
        self.doc = _make_doc(self.user, file_name="search_test.docx", status="indexed")
        self.img = RagImage.objects.create(
            document=self.doc,
            image_index=0,
            page_or_section="图片1",
            image_format="png",
            image_data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
            file_size=24,
        )
        # 构造一个固定向量 chunk（用已知向量，检索时 mock embedding）
        self.test_vec = np.ones(4, dtype=np.float32)
        self.chunk = RagChunk.objects.create(
            document=self.doc,
            chunk_index=0,
            content="三恒空调参数说明",
            embedding=self.test_vec.tobytes(),
            page_or_section="图片1",
            is_image_ocr=True,
            image=self.img,
        )

    def test_search_rag_returns_image_id_field(self):
        """
        TC-UNIT-012
        Given  向量缓存已加载，含有 image_id 的 chunk
        When   调用 search_rag()（mock embedding 返回匹配向量）
        Then   返回的 chunk dict 中含 image_id 字段
        AC-IC-001-01（返回包含 image_id 的 chunk 给 fa_tools 聚合用）
        """
        # 直接测试 RagVectorCache.search 返回 image_id
        cache = RagVectorCache()
        cache.load()
        # 使用与 chunk 相同的向量查询（余弦相似度=1.0，必中）
        results = cache.search(self.test_vec, k=5, threshold=0.0)
        self.assertGreater(len(results), 0, "期望检索到至少1条结果")
        first = results[0]
        self.assertIn("image_id", first, "结果 dict 中缺少 image_id 字段")
        # 验证 image_id 值正确
        self.assertEqual(first["image_id"], self.img.id)


# ============================================================
# 6. fa_tools ContextVar side-channel 测试
# ============================================================

@tag("unit")
class FaToolsContextVarTest(TestCase):
    """TC-UNIT-013 ~ TC-UNIT-014: get_last_search_images ContextVar（AC-IC-001-01/04）"""

    def test_get_last_search_images_empty(self):
        """
        TC-UNIT-013
        Given  未调用 search_sanheng_knowledge
        When   调用 get_last_search_images()
        Then   返回 []（ContextVar 默认空列表）
        AC-IC-001-04
        """
        from api.langgraph_chat.fa_tools import get_last_search_images, _last_search_images_var
        # 确保 ContextVar 处于默认空状态
        _last_search_images_var.set([])
        result = get_last_search_images()
        self.assertEqual(result, [])

    def test_get_last_search_images_clears_after_read(self):
        """
        TC-UNIT-014
        Given  ContextVar 中已写入 related_images 数据
        When   第一次调用 get_last_search_images()
        Then   返回数据，第二次调用返回 []（清零语义）
        AC-IC-001-01（防跨 tool-call 轮次残留）
        """
        from api.langgraph_chat.fa_tools import get_last_search_images, _last_search_images_var
        test_data = [{"image_id": 42, "source": "test_doc · 图片1"}]
        _last_search_images_var.set(test_data)

        first_call = get_last_search_images()
        self.assertEqual(first_call, test_data)

        second_call = get_last_search_images()
        self.assertEqual(second_call, [])


# ============================================================
# 6b. side-channel 经 ainvoke 回传（2026-06-23 回归）
# ============================================================

@tag("unit")
class SearchToolSideChannelAinvokeTest(TestCase):
    """回归：search_sanheng_knowledge 经 `.ainvoke()` 调用后，side-channel 仍能回传 related_images。

    背景：原实现工具体内 `_last_search_images_var.set(images)` 在 ainvoke 的 copy_context 副本里
    丢失，get_last_search_images() 恒空 → 图片从不回显。改为 prepare(放可变 sink)+原地 mutate 后修复。
    本测试**经真实 ainvoke 路径**断言（原有 FaToolsContextVarTest 只直接 set/get，测不出此回归）。
    """

    def test_side_channel_survives_ainvoke(self):
        from unittest.mock import patch
        from api.langgraph_chat.fa_tools import (
            search_sanheng_knowledge, prepare_search_images_sink, get_last_search_images)

        fake = {"degraded": False, "chunks": [
            {"content": "B.DW02/03/04PX 内部结构 ①上面板", "source": "DW.pdf · 第 7 页",
             "is_image_ocr": False, "score": 0.9, "image_id": 119},
        ]}

        async def run():
            with patch("api.rag_service.search_rag", return_value=fake):
                prepare_search_images_sink()                              # orchestrator 调用前置
                out = await search_sanheng_knowledge.ainvoke({"query": "DW 内部结构图"})
                imgs = get_last_search_images()
            return out, imgs

        out, imgs = asyncio.run(run())
        self.assertIn("检索到", out)
        self.assertEqual(len(imgs), 1, "经 ainvoke 后 side-channel 应回传 1 张图（修复前为空）")
        self.assertEqual(imgs[0]["image_id"], 119)
        # C-003：image_id 不得泄露进返回给 LLM 的文本
        self.assertNotIn("119", out)
        self.assertNotIn("image_id", out)


# ============================================================
# 7. RagImageView 端点测试
# ============================================================

@tag("unit")
class RagImageViewTest(APITestCase):
    """TC-UNIT-015 ~ TC-UNIT-018: GET /api/rag/images/<id>/ 端点（AC-IC-008-02）"""

    def setUp(self):
        self.user = _make_user("tc_unit_015_user")
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.doc = _make_doc(self.user, file_name="img_view_test.docx", status="indexed")
        self.png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        self.img = RagImage.objects.create(
            document=self.doc,
            image_index=0,
            page_or_section="图片1",
            image_format="png",
            image_data=self.png_bytes,
            file_size=len(self.png_bytes),
        )

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_image_view_returns_200(self):
        """
        TC-UNIT-015
        Given  已认证用户，有效 image_id
        When   GET /api/rag/images/<id>/
        Then   200 响应，Content-Type 为 image/png，Content-Disposition: inline，
               Cache-Control: no-store（REQ-NFR-004 安全要求）
        AC-IC-008-02（取图走 DB 直查，不过缓存）
        """
        url = f"/api/rag/images/{self.img.id}/"
        response = self.client.get(url, **self._auth_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(bytes(response.content), self.png_bytes)
        # REQ-NFR-004：安全响应头
        self.assertEqual(response.get("Content-Disposition"), "inline")
        self.assertEqual(response.get("Cache-Control"), "no-store")

    def test_image_view_401_unauthenticated(self):
        """
        TC-UNIT-016
        Given  未认证请求
        When   GET /api/rag/images/<id>/
        Then   401 Unauthorized
        AC-IC-008-02（REQ-NFR-004 认证强制）
        """
        url = f"/api/rag/images/{self.img.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_image_view_404_not_exist(self):
        """
        TC-UNIT-017
        Given  已认证用户，不存在的 image_id
        When   GET /api/rag/images/99999/
        Then   404 Not Found（fail-open 降级，AC-IC-003-01）
        AC-IC-003-01（图片 HTTP 加载失败返回 404）
        """
        url = "/api/rag/images/99999/"
        response = self.client.get(url, **self._auth_headers())
        self.assertEqual(response.status_code, 404)

    def test_image_view_jpeg_content_type(self):
        """
        TC-UNIT-018
        Given  已认证用户，image_format='jpeg' 的图片
        When   GET /api/rag/images/<id>/
        Then   Content-Type 为 image/jpeg
        AC-IC-008-02
        """
        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 16
        jpeg_img = RagImage.objects.create(
            document=self.doc,
            image_index=1,
            page_or_section="图片2",
            image_format="jpeg",
            image_data=jpeg_bytes,
            file_size=len(jpeg_bytes),
        )
        url = f"/api/rag/images/{jpeg_img.id}/"
        response = self.client.get(url, **self._auth_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")


# ============================================================
# 8. _finalize_turn stream_end 载荷测试
# ============================================================

@tag("unit")
class FinalizeTurnStreamEndTest(TestCase):
    """TC-UNIT-019 ~ TC-UNIT-020: _finalize_turn stream_end 载荷（AC-IC-007-01，AC-IC-001-01）

    注意：本测试在 InMemory Channel Layer 环境下测试 _finalize_turn 内部逻辑。
    WS 端到端（stream_end 经 Redis 传至前端）需本地真 Redis 验证
    （参考 MEMORY 条目"Channels 运行时改动必须本地真 Redis 验 WS 收发"）。
    """

    def _run_finalize(self, related_images):
        """
        通过 unbound method + mock consumer 调用 _finalize_turn。
        chat_session=None 规避 sync_to_async(chat_memory.append_message) 调用。
        """
        from api.consumers import ChatConsumer

        consumer = MagicMock()
        consumer.send = AsyncMock()
        consumer.chat_session = None  # 避免 DB IO
        consumer._pending_assistant_content = ""

        asyncio.run(
            ChatConsumer._finalize_turn(consumer, "测试内容", related_images=related_images)
        )
        # 取第一次 send() 调用的参数（stream_end 载荷）
        call_args = consumer.send.call_args_list[0][0][0]
        return json.loads(call_args)

    def test_finalize_turn_no_related_images(self):
        """
        TC-UNIT-019
        Given  related_images=[]（纯文字问答）
        When   _finalize_turn 执行
        Then   stream_end 载荷不含 related_images 字段（向后兼容，AC-IC-007-01）
        AC-IC-007-01（无图答案气泡外观不变，stream_end 不附加多余字段）
        """
        payload = self._run_finalize(related_images=[])
        self.assertEqual(payload.get("type"), "stream_end")
        self.assertNotIn(
            "related_images", payload,
            "related_images=[] 时 stream_end 不应包含 related_images 字段"
        )

    def test_finalize_turn_with_related_images(self):
        """
        TC-UNIT-020
        Given  related_images=[{"image_id": 1, "source": "来源"}]
        When   _finalize_turn 执行
        Then   stream_end 载荷含 related_images 字段，值正确
        AC-IC-001-01（WS stream_end 含 related_images 数组）
        """
        test_images = [{"image_id": 1, "source": "test_doc · 图片1"}]
        payload = self._run_finalize(related_images=test_images)
        self.assertEqual(payload.get("type"), "stream_end")
        self.assertIn(
            "related_images", payload,
            "related_images 非空时 stream_end 应包含 related_images 字段"
        )
        self.assertEqual(payload["related_images"], test_images)


# ============================================================
# 9. MAX_IMAGE_BYTES 常量校验
# ============================================================

@tag("unit")
class MaxImageBytesConstantTest(TestCase):
    """TC-UNIT-021: MAX_IMAGE_BYTES == 10MB（AC-IC-005-02 阈值确认）"""

    def test_max_image_bytes_is_10mb(self):
        """TC-UNIT-021: MAX_IMAGE_BYTES 等于 10 * 1024 * 1024"""
        self.assertEqual(MAX_IMAGE_BYTES, 10 * 1024 * 1024)


# ============================================================
# 9b. 方案1（图文同 chunk）：_inherit_page_image 单元测试
# ============================================================

@tag("unit")
class InheritPageImageTest(TestCase):
    """页面文字 chunk 继承本页代表图（方案1，修复"问图命中文字 chunk 却取不到图"）"""

    def _text_chunk(self, content="第7页 B.DW02/03/04PX 内部结构 ①上面板"):
        from api.rag_service import ParsedChunk
        return ParsedChunk(content=content, page_or_section="第 7 页", is_image_ocr=False)

    def test_inherit_largest_page_image(self):
        """有图有文字：文字 chunk 继承本页最大图字节，is_image_ocr 仍为 False，content 不变"""
        small = (b"\xff\xd8" + b"\x00" * 5000, "jpeg", 5002)
        large = (b"\xff\xd8" + b"\x01" * 80000, "jpeg", 80002)
        chunk = self._text_chunk()
        RagParser._inherit_page_image([chunk], [small, large], "第 7 页")
        self.assertEqual(chunk.img_bytes, large[0], "应继承本页最大的那张图")
        self.assertEqual(chunk.img_format, "jpeg")
        self.assertEqual(chunk.img_size, large[2])
        self.assertFalse(chunk.is_image_ocr, "继承图不改 is_image_ocr（这是页面文字，非 OCR）")
        self.assertIn("DW02", chunk.content, "content 不被破坏")

    def test_skip_when_largest_below_threshold(self):
        """本页最大图仍小于阈值（logo/分隔条）→ 不继承"""
        tiny = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "png", 108)
        chunk = self._text_chunk()
        RagParser._inherit_page_image([chunk], [tiny], "第 1 页")
        self.assertIsNone(chunk.img_bytes, "小于阈值的小图不应被继承")

    def test_no_overwrite_existing_img_bytes(self):
        """已自带 img_bytes 的 chunk（如扫描页文字）不被覆盖"""
        from api.rag_service import ParsedChunk
        own = b"\xff\xd8" + b"\x09" * 90000
        chunk = ParsedChunk(content="扫描页文字", page_or_section="第 2 页 扫描",
                            is_image_ocr=True, img_bytes=own, img_format="png", img_size=len(own))
        other = (b"\xff\xd8" + b"\x01" * 80000, "jpeg", 80002)
        RagParser._inherit_page_image([chunk], [other], "第 2 页")
        self.assertEqual(chunk.img_bytes, own, "已自带图字节的 chunk 不应被覆盖")

    def test_noop_without_images_or_text(self):
        """无图或无文字 chunk → 安全无操作"""
        chunk = self._text_chunk()
        RagParser._inherit_page_image([chunk], [], "第 7 页")   # 无图
        self.assertIsNone(chunk.img_bytes)
        RagParser._inherit_page_image([], [(b"x" * 80000, "png", 80000)], "第 7 页")  # 无文字（不抛）


# ============================================================
# 10. 集成测试
# ============================================================

@tag("integration")
class RagIngestorIntegrationTest(TestCase):
    """
    TC-INT-001 ~ TC-INT-003: RagIngestor 图片入库端到端集成测试
    （AC-IC-004-01, AC-IC-004-03, AC-IC-005-02, US-IC-004/005）

    注意：RagIngestor.ingest() 在守护线程中运行，测试中直接同步调用以便断言。
    embedding 通过 mock 绕过真实 API 调用。
    """

    def setUp(self):
        self.user = _make_user("tc_int_user")

    def _run_ingest(self, doc, parsed_chunks, mock_embed_return=None):
        """
        同步调用 ingest()，mock 掉 RagEmbedder.embed_texts 和 parse_docx。
        parsed_chunks: 模拟解析后的 ParsedChunk 列表。
        mock_embed_return: embedding 返回值（list of np.ndarray），None 时按 chunks 数量填 zeros。
        """
        from api.rag_service import RagIngestor, ParsedChunk
        from unittest.mock import patch
        import numpy as np

        text_chunks = [c for c in parsed_chunks if c.content]
        if mock_embed_return is None:
            mock_embed_return = [np.zeros(4, dtype=np.float32)] * len(text_chunks)

        ingestor = RagIngestor()
        with patch("api.rag_service.RagParser.parse_docx", return_value=parsed_chunks), \
             patch("api.rag_service.RagEmbedder.embed_texts", return_value=mock_embed_return):
            ingestor.ingest(doc.id, b"PK\x03\x04" + b"\x00" * 100, ".docx")

    def test_ingest_docx_with_images(self):
        """
        TC-INT-001
        Given  ParsedChunk 含模拟图片 bytes（img_bytes 非空，is_image_ocr=True）
        When   RagIngestor.ingest() 执行
        Then   RagImage 记录被创建，RagChunk.image_id 指向 RagImage，文档状态为 indexed
        AC-IC-004-01（docx 含图片上传入库）
        """
        from api.rag_service import ParsedChunk

        doc = _make_doc(self.user, file_name="with_img.docx", status="pending")
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        parsed = [
            ParsedChunk(
                content="图片OCR识别到的文字内容",
                page_or_section="图片1",
                is_image_ocr=True,
                img_bytes=png_bytes,
                img_format="png",
                img_size=len(png_bytes),
            ),
            ParsedChunk(
                content="普通文字段落内容",
                page_or_section="段落1",
                is_image_ocr=False,
                img_bytes=None,
                img_format="",
                img_size=0,
            ),
        ]

        self._run_ingest(doc, parsed)

        # 验证文档状态
        doc.refresh_from_db()
        self.assertEqual(doc.status, "indexed", f"文档状态应为 indexed，实际: {doc.status}（error: {doc.error_message}）")

        # 验证 RagImage 被创建
        images = RagImage.objects.filter(document=doc)
        self.assertEqual(images.count(), 1, "应创建 1 条 RagImage 记录")
        self.assertGreater(len(images.first().image_data), 0, "RagImage.image_data 不应为空")

        # 验证 RagChunk.image_id 关联
        ocr_chunks = RagChunk.objects.filter(document=doc, is_image_ocr=True)
        self.assertGreater(ocr_chunks.count(), 0, "应有 is_image_ocr=True 的 chunk")
        for c in ocr_chunks:
            self.assertIsNotNone(c.image_id, f"OCR chunk(id={c.id}) 的 image_id 应非 None")
            self.assertEqual(c.image_id, images.first().id)

    def test_ingest_oversized_image_skip(self):
        """
        TC-INT-002
        Given  ParsedChunk 含超过 MAX_IMAGE_BYTES（10MB）的 img_bytes
        When   RagIngestor.ingest() 执行
        Then   超限图片被跳过（无 RagImage 记录），文档状态仍为 indexed，chunk.image_id=None
        AC-IC-005-02（图片超过存储大小上限）
        """
        from api.rag_service import ParsedChunk

        doc = _make_doc(self.user, file_name="oversized_img.docx", status="pending")
        oversized_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024)

        # _try_save_image_bytes 会过滤超限图片，ParsedChunk 直接填原始大小
        # 模拟 parser 已调用 _try_save_image_bytes 后的结果（img_bytes=None）
        parsed = [
            ParsedChunk(
                content="超大图片的OCR文字",
                page_or_section="图片1",
                is_image_ocr=True,
                img_bytes=None,      # 已被 _try_save_image_bytes 过滤
                img_format="",
                img_size=0,
            ),
            ParsedChunk(
                content="正常文字内容",
                page_or_section="段落1",
                is_image_ocr=False,
                img_bytes=None,
                img_format="",
                img_size=0,
            ),
        ]

        self._run_ingest(doc, parsed)

        doc.refresh_from_db()
        self.assertEqual(doc.status, "indexed")

        # 无 RagImage 创建
        self.assertEqual(
            RagImage.objects.filter(document=doc).count(), 0,
            "超限图片不应创建 RagImage 记录"
        )

        # chunk.image_id 为 None
        ocr_chunks = RagChunk.objects.filter(document=doc, is_image_ocr=True)
        for c in ocr_chunks:
            self.assertIsNone(c.image_id, "超限图片 chunk 的 image_id 应为 None")

    def test_ingest_inherited_text_chunk_shares_one_image(self):
        """
        方案1：页面文字 chunk（继承本页图）与图片 OCR chunk 共享同一图字节
        → 只建 1 行 RagImage，两 chunk image_id 同指；继承文字 chunk is_image_ocr=False 仍可被检索带图。
        """
        from api.rag_service import ParsedChunk

        doc = _make_doc(self.user, file_name="inherit.pdf", status="pending")
        diagram = b"\xff\xd8" + b"\x07" * 80000   # 同一张图的字节

        parsed = [
            # 页面文字 chunk：继承了本页图字节（is_image_ocr=False，有 content）
            ParsedChunk(
                content="第7页 B.DW02/03/04PX 内部结构 ①上面板②下面板",
                page_or_section="第 7 页",
                is_image_ocr=False,
                img_bytes=diagram, img_format="jpeg", img_size=len(diagram),
            ),
            # 同一张图的 OCR 碎片 chunk（is_image_ocr=True，同一字节）
            ParsedChunk(
                content="12",
                page_or_section="第 7 页 图片1",
                is_image_ocr=True,
                img_bytes=diagram, img_format="jpeg", img_size=len(diagram),
            ),
        ]

        # parse_pdf 路径：mock parse_pdf 返回上述 chunk，走 .pdf 分支
        from api.rag_service import RagIngestor
        from unittest.mock import patch
        import numpy as np
        ingestor = RagIngestor()
        with patch("api.rag_service.RagParser.parse_pdf", return_value=parsed), \
             patch("api.rag_service.RagEmbedder.embed_texts",
                   return_value=[np.zeros(4, dtype=np.float32)] * 2):
            ingestor.ingest(doc.id, b"%PDF-1.4" + b"\x00" * 50, ".pdf")

        doc.refresh_from_db()
        self.assertEqual(doc.status, "indexed", f"error: {doc.error_message}")

        # 哈希去重：只建 1 行 RagImage
        images = RagImage.objects.filter(document=doc)
        self.assertEqual(images.count(), 1, "同一图字节应只建 1 行 RagImage")
        img_id = images.first().id

        # 两 chunk 都写入向量表，且 image_id 同指（关键：文字 chunk 也带图了）
        text_chunk = RagChunk.objects.get(document=doc, is_image_ocr=False)
        ocr_chunk = RagChunk.objects.get(document=doc, is_image_ocr=True)
        self.assertEqual(text_chunk.image_id, img_id, "页面文字 chunk 应链接到图（方案1 核心）")
        self.assertEqual(ocr_chunk.image_id, img_id, "图 OCR chunk 也链接到同一图")

    def test_ingest_no_image_doc(self):
        """
        TC-INT-003
        Given  ParsedChunk 全部为纯文字（img_bytes=None, is_image_ocr=False）
        When   RagIngestor.ingest() 执行
        Then   无 RagImage 记录，文档状态为 indexed，chunk_count 正常
        AC-IC-004-03（纯文字文档无图片记录）
        """
        from api.rag_service import ParsedChunk

        doc = _make_doc(self.user, file_name="text_only.docx", status="pending")
        parsed = [
            ParsedChunk(
                content=f"纯文字段落内容 {i}",
                page_or_section=f"段落{i}",
                is_image_ocr=False,
                img_bytes=None,
                img_format="",
                img_size=0,
            )
            for i in range(3)
        ]

        self._run_ingest(doc, parsed)

        doc.refresh_from_db()
        self.assertEqual(doc.status, "indexed")
        self.assertEqual(
            RagImage.objects.filter(document=doc).count(), 0,
            "纯文字文档不应创建 RagImage 记录"
        )
        self.assertEqual(doc.chunk_count, 3, "chunk_count 应为 3")
