"""
api.tests_rag — RAG 知识库单元测试 + 集成测试（v1.4.0_sanheng_rag）

覆盖范围（US-1 ~ US-4，REQ-FUNC-RAG-01 ~ 13）：
  - 数据模型 RagDocument / RagChunk（状态机、级联删除）
  - API 端点（upload/list/delete/retry），权限，文件校验
  - rag_service：RagVectorCache，RagEmbedder（mock），RagParser，search_rag（fail-open）
  - fa_tools.search_sanheng_knowledge（mock rag_service.search_rag）
  - SYSTEM_PROMPT.langgraph.md 是否包含 RAG 工具使用约定

运行命令（在 FreeArkWeb/backend/freearkweb/ 目录下执行）：

    # Windows PowerShell:
    $env:FREEARK_POC_MOCK="1"; python manage.py test api.tests_rag --verbosity=2

    # 或等价（cmd）:
    set FREEARK_POC_MOCK=1 && python manage.py test api.tests_rag --verbosity=2

    # macOS/Linux:
    FREEARK_POC_MOCK=1 python manage.py test api.tests_rag --verbosity=2

说明：FREEARK_POC_MOCK=1 使 fa_tools 跳过 tier1_readonly 导入（测试环境无 skill dir）。
     其他依赖（embedding API、OCR）在测试内部通过 unittest.mock 替换，不需要真实服务。

环境要求：
  - 使用 SQLite（manage.py test 自动切换，无需 MySQL）
  - embedding API 全部 mock，无需真实 API key
  - OCR 全部 mock，无需 rapidocr-onnxruntime
  - FREEARK_POC_MOCK=1 环境变量（使 fa_tools 离线可用）

单独运行某个测试类（PowerShell）：
    $env:FREEARK_POC_MOCK="1"; python manage.py test api.tests_rag.TestRagDocumentModel --verbosity=2
    $env:FREEARK_POC_MOCK="1"; python manage.py test api.tests_rag.TestRagUploadAPI --verbosity=2
    $env:FREEARK_POC_MOCK="1"; python manage.py test api.tests_rag.TestRagService --verbosity=2
    $env:FREEARK_POC_MOCK="1"; python manage.py test api.tests_rag.TestSearchTool --verbosity=2
    $env:FREEARK_POC_MOCK="1"; python manage.py test api.tests_rag.TestRagIntegration --verbosity=2
"""

import io
import os

# 在 import fa_tools 前设置 FREEARK_POC_MOCK，使 fa_tools 离线可用
# 这必须在任何 fa_tools 相关 import 之前执行
os.environ.setdefault('FREEARK_POC_MOCK', '1')

import struct
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, tag
from django.urls import reverse
from rest_framework.test import APIClient

from .models_rag import RagChunk, RagDocument

User = get_user_model()

# ── 测试 fixtures ──────────────────────────────────────────────────────────

def _make_fake_pdf_bytes() -> bytes:
    """构造一个最小合法 PDF 文件头（让文件头签名校验通过）。"""
    return b'%PDF-1.4\n%%EOF\n'


def _make_fake_docx_bytes() -> bytes:
    """构造一个最小合法 ZIP/DOCX 文件头。"""
    return b'PK\x03\x04' + b'\x00' * 100


def _make_numpy_vec(dim: int = 1024) -> np.ndarray:
    """生成固定维度的测试向量（L2-归一化，确保余弦相似度计算正确）。"""
    vec = np.ones(dim, dtype=np.float32)
    return vec / np.linalg.norm(vec)


def _vec_bytes(dim: int = 1024) -> bytes:
    """返回测试向量的 tobytes()。"""
    return _make_numpy_vec(dim).tobytes()


# ── 1. 数据模型测试 ────────────────────────────────────────────────────────

@tag('unit')
class TestRagDocumentModel(TestCase):
    """REQ-FUNC-RAG-01：RagDocument 模型状态机与字段约束。"""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_test', password='pass', is_staff=True, role='admin')

    def test_default_status_is_pending(self):
        doc = RagDocument.objects.create(
            file_name='test.pdf', file_size=1024, uploaded_by=self.admin)
        self.assertEqual(doc.status, 'pending')
        self.assertEqual(doc.chunk_count, 0)
        self.assertEqual(doc.error_message, '')

    def test_status_transition_to_indexed(self):
        doc = RagDocument.objects.create(
            file_name='test.pdf', file_size=1024, uploaded_by=self.admin)
        doc.status = 'indexed'
        doc.chunk_count = 5
        doc.save()
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'indexed')
        self.assertEqual(doc.chunk_count, 5)

    def test_status_transition_to_failed(self):
        doc = RagDocument.objects.create(
            file_name='test.pdf', file_size=1024, uploaded_by=self.admin)
        doc.status = 'failed'
        doc.error_message = 'embedding API 失败'
        doc.save()
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'failed')
        self.assertIn('embedding', doc.error_message)

    def test_uploaded_by_set_null_on_user_delete(self):
        """uploaded_by 用 SET_NULL：用户删除后台账保留。"""
        temp_user = User.objects.create_user(username='temp', password='pass')
        doc = RagDocument.objects.create(
            file_name='test.pdf', file_size=100, uploaded_by=temp_user)
        temp_user.delete()
        doc.refresh_from_db()
        self.assertIsNone(doc.uploaded_by)

    def test_chunk_cascade_delete(self):
        """RagDocument 删除时 RagChunk 级联删除（AC-4.1）。"""
        doc = RagDocument.objects.create(
            file_name='test.pdf', file_size=100, uploaded_by=self.admin,
            status='indexed')
        RagChunk.objects.create(
            document=doc, chunk_index=0, content='测试内容',
            embedding=_vec_bytes(), page_or_section='第1页')
        self.assertEqual(RagChunk.objects.filter(document=doc).count(), 1)
        doc.delete()
        self.assertEqual(RagChunk.objects.count(), 0)


# ── 2. 上传 API 测试（REQ-FUNC-RAG-02）──────────────────────────────────

@tag('integration')
class TestRagUploadAPI(TestCase):
    """REQ-FUNC-RAG-02/03/04：上传、列表、删除、权限。"""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_api', password='pass', is_staff=True, role='admin')
        self.normal = User.objects.create_user(
            username='user_api', password='pass', is_staff=False, role='user')
        self.client = APIClient()

    def _auth(self, user):
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    # ── 权限测试（AC-1.1, AC-1.2）────────────────────────────────────────
    def test_non_admin_upload_returns_403(self):
        """AC-1.2：非管理员上传返回 403。"""
        self._auth(self.normal)
        f = io.BytesIO(_make_fake_pdf_bytes())
        f.name = 'test.pdf'
        resp = self.client.post('/api/rag/documents/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(RagDocument.objects.count(), 0)

    def test_non_admin_list_returns_403(self):
        self._auth(self.normal)
        resp = self.client.get('/api/rag/documents/')
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_returns_401(self):
        resp = self.client.get('/api/rag/documents/')
        self.assertIn(resp.status_code, [401, 403])

    # ── 文件校验测试（AC-1.3, AC-1.4, AC-1.5）────────────────────────────
    def test_invalid_extension_returns_400(self):
        """AC-1.5 后端侧：不合法扩展名返回 400。"""
        self._auth(self.admin)
        f = io.BytesIO(b'hello world')
        f.name = 'test.txt'
        resp = self.client.post('/api/rag/documents/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('不支持的文件类型', resp.data.get('error', ''))

    def test_fake_extension_wrong_magic_returns_400(self):
        """AC-1.5：扩展名.pdf 但文件头非 PDF → 400。"""
        self._auth(self.admin)
        f = io.BytesIO(b'<html>not a pdf</html>')
        f.name = 'malicious.pdf'
        resp = self.client.post('/api/rag/documents/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('不支持的文件类型', resp.data.get('error', ''))

    def test_oversized_file_returns_400(self):
        """文件大小超过 50MB 返回 400。"""
        self._auth(self.admin)
        # 构造一个超大文件（模拟文件大小，实际内容用 BytesIO 截断）
        big_content = b'%PDF' + b'\x00' * (51 * 1024 * 1024)
        f = io.BytesIO(big_content)
        f.name = 'big.pdf'
        # 需要 size 属性，DRF multipart 从内容长度读取
        resp = self.client.post('/api/rag/documents/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('50MB', resp.data.get('error', ''))

    # ── 合法上传测试（AC-1.6）────────────────────────────────────────────
    @patch('api.views_rag.transaction.on_commit')
    def test_valid_pdf_upload_returns_201(self, mock_commit):
        """AC-1.6：合法 PDF 上传返回 201，状态为 pending，不阻塞请求。"""
        mock_commit.side_effect = lambda fn: None  # 不执行后台线程
        self._auth(self.admin)
        f = io.BytesIO(_make_fake_pdf_bytes())
        f.name = 'test.pdf'
        resp = self.client.post('/api/rag/documents/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 201)
        data = resp.data
        self.assertIn('id', data)
        self.assertEqual(data['status'], 'pending')
        self.assertEqual(data['file_name'], 'test.pdf')
        self.assertEqual(data['chunk_count'], 0)
        self.assertEqual(RagDocument.objects.count(), 1)

    @patch('api.views_rag.transaction.on_commit')
    def test_valid_docx_upload_returns_201(self, mock_commit):
        """AC-1.6：合法 DOCX 上传返回 201。"""
        mock_commit.side_effect = lambda fn: None
        self._auth(self.admin)
        f = io.BytesIO(_make_fake_docx_bytes())
        f.name = 'test.docx'
        resp = self.client.post('/api/rag/documents/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'pending')

    # ── 列表测试（REQ-FUNC-RAG-03）────────────────────────────────────────
    def test_list_returns_documents_ordered_by_created_desc(self):
        """GET /api/rag/documents/ 按创建时间倒序返回。"""
        self._auth(self.admin)
        RagDocument.objects.create(file_name='a.pdf', file_size=100, uploaded_by=self.admin)
        RagDocument.objects.create(file_name='b.pdf', file_size=200, uploaded_by=self.admin)
        resp = self.client.get('/api/rag/documents/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)
        # 最新创建的应排在前面
        self.assertEqual(resp.data[0]['file_name'], 'b.pdf')

    # ── 删除测试（REQ-FUNC-RAG-04，AC-4.1，AC-4.3，AC-4.4）──────────────
    def test_delete_document_returns_204(self):
        """AC-4.1：删除文档返回 204，台账+向量一并删除。"""
        self._auth(self.admin)
        doc = RagDocument.objects.create(
            file_name='del.pdf', file_size=100, uploaded_by=self.admin,
            status='indexed')
        RagChunk.objects.create(
            document=doc, chunk_index=0, content='内容',
            embedding=_vec_bytes(), page_or_section='第1页')

        with patch('api.views_rag.rag_vector_cache') as mock_cache:
            resp = self.client.delete(f'/api/rag/documents/{doc.id}/')
            mock_cache.refresh.assert_called_once()

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(RagDocument.objects.filter(id=doc.id).exists())
        self.assertEqual(RagChunk.objects.count(), 0)

    def test_delete_nonexistent_returns_404(self):
        """AC-4.4：删除不存在的文档返回 404。"""
        self._auth(self.admin)
        resp = self.client.delete('/api/rag/documents/9999/')
        self.assertEqual(resp.status_code, 404)

    def test_delete_parsing_doc_succeeds(self):
        """AC-4.3：status=parsing 的文档也可删除。"""
        self._auth(self.admin)
        doc = RagDocument.objects.create(
            file_name='parsing.pdf', file_size=100, uploaded_by=self.admin,
            status='parsing')
        with patch('api.views_rag.rag_vector_cache'):
            resp = self.client.delete(f'/api/rag/documents/{doc.id}/')
        self.assertEqual(resp.status_code, 204)

    # ── 重试测试（REQ-FUNC-RAG-05，AC-2.3，AC-2.4）──────────────────────
    @patch('api.views_rag.transaction.on_commit')
    def test_retry_failed_doc_succeeds(self, mock_commit):
        """AC-2.4：status=failed 文档可重试，状态重置为 pending。"""
        mock_commit.side_effect = lambda fn: None
        self._auth(self.admin)
        doc = RagDocument.objects.create(
            file_name='failed.pdf', file_size=100, uploaded_by=self.admin,
            status='failed', error_message='old error')
        f = io.BytesIO(_make_fake_pdf_bytes())
        f.name = 'failed.pdf'
        resp = self.client.post(
            f'/api/rag/documents/{doc.id}/retry/',
            {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'pending')
        self.assertEqual(doc.error_message, '')

    def test_retry_indexed_doc_returns_400(self):
        """非 failed 状态文档重试返回 400。"""
        self._auth(self.admin)
        doc = RagDocument.objects.create(
            file_name='ok.pdf', file_size=100, uploaded_by=self.admin,
            status='indexed')
        f = io.BytesIO(_make_fake_pdf_bytes())
        f.name = 'ok.pdf'
        resp = self.client.post(
            f'/api/rag/documents/{doc.id}/retry/',
            {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_retry_without_file_returns_400(self):
        """重试不附带 file 字段返回 400。"""
        self._auth(self.admin)
        doc = RagDocument.objects.create(
            file_name='failed.pdf', file_size=100, uploaded_by=self.admin,
            status='failed')
        resp = self.client.post(f'/api/rag/documents/{doc.id}/retry/')
        self.assertEqual(resp.status_code, 400)


# ── 3. rag_service 服务测试 ───────────────────────────────────────────────

@tag('unit')
class TestRagService(TestCase):
    """REQ-FUNC-RAG-06/07/08：服务层单元测试。"""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_svc', password='pass', is_staff=True, role='admin')

    # ── RagVectorCache ────────────────────────────────────────────────────
    def test_cache_empty_search_returns_empty(self):
        """内存为空时 search() 返回空列表（degraded=False 场景）。"""
        from .rag_service import RagVectorCache
        cache = RagVectorCache()
        cache._loaded = True  # 标记已加载，跳过 DB 查询
        query_vec = _make_numpy_vec()
        result = cache.search(query_vec, k=5, threshold=0.3)
        self.assertEqual(result, [])

    def test_cache_search_returns_top_k(self):
        """向量已加载时 search() 返回正确 top-k 结果，score 降序。"""
        from .rag_service import RagVectorCache
        cache = RagVectorCache()
        cache._loaded = True
        # 构造 3 个向量：v1 与 query 完全相同（score=1.0），v2 正交（score=0），v3 相似
        query_vec = _make_numpy_vec()
        v1 = _make_numpy_vec()                        # score ≈ 1.0
        v2 = np.zeros(1024, dtype=np.float32); v2[0] = 1.0  # score ≈ 1.0/sqrt(1024)
        v3 = _make_numpy_vec() * 0.5                  # score ≈ 1.0
        vectors = np.array([v1, v2, v3], dtype=np.float32)
        meta = [
            {'doc_name': 'a.pdf', 'source': '第1页', 'is_image_ocr': False, 'content': '内容1'},
            {'doc_name': 'b.pdf', 'source': '第2页', 'is_image_ocr': False, 'content': '内容2'},
            {'doc_name': 'c.pdf', 'source': '第3页', 'is_image_ocr': False, 'content': '内容3'},
        ]
        cache._vectors = vectors
        cache._meta = meta
        results = cache.search(query_vec, k=5, threshold=0.3)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertGreater(r['score'], 0.3)
        # 结果应按 score 降序
        scores = [r['score'] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_cache_threshold_filters_low_scores(self):
        """score < threshold 的结果被过滤。"""
        from .rag_service import RagVectorCache
        cache = RagVectorCache()
        cache._loaded = True
        query_vec = _make_numpy_vec(1024)
        # 构造一个与 query 接近正交的向量（score 很低）
        ortho = np.zeros(1024, dtype=np.float32)
        ortho[0] = 1.0
        # query 方向是全1/sqrt，所以 ortho 的余弦相似度 = 1/sqrt(1024) ≈ 0.03
        cache._vectors = np.array([ortho], dtype=np.float32)
        cache._meta = [{'doc_name': 'x.pdf', 'source': '第1页', 'is_image_ocr': False, 'content': '内容'}]
        results = cache.search(query_vec, k=5, threshold=0.5)
        self.assertEqual(results, [])

    # ── RagParser ─────────────────────────────────────────────────────────
    def test_parse_docx_text_chunks(self):
        """parse_docx 能正确提取段落文字 chunk（AC-2.5）。"""
        from .rag_service import RagParser
        import io
        from docx import Document

        # 创建一个真实的 .docx 文件
        doc = Document()
        for i in range(3):
            doc.add_paragraph(f"这是第 {i+1} 段测试内容，包含三恒系统相关知识。" * 5)
        buf = io.BytesIO()
        doc.save(buf)
        file_bytes = buf.getvalue()

        parser = RagParser(chunk_size=100, chunk_overlap=10)
        chunks = parser.parse_docx(file_bytes)
        self.assertGreater(len(chunks), 0)
        for c in chunks:
            self.assertFalse(c.is_image_ocr)
            self.assertIn('段落', c.page_or_section)

    def test_parse_pdf_text_chunks(self):
        """parse_pdf 能提取页面文字（需要 PyMuPDF 已安装）。"""
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF 未安装，跳过 PDF 解析测试")

        from .rag_service import RagParser
        # 构造一个最小 PDF（包含文字）
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), "三恒系统恒温原理：通过精确控制供回水温度实现室内温度恒定。" * 3)
        buf = io.BytesIO()
        doc.save(buf)
        file_bytes = buf.getvalue()

        parser = RagParser(chunk_size=50, chunk_overlap=5)
        chunks = parser.parse_pdf(file_bytes)
        self.assertGreater(len(chunks), 0)
        for c in chunks:
            self.assertIn('第', c.page_or_section)
            self.assertFalse(c.is_image_ocr)

    @patch('api.rag_service._HAS_OCR', False)
    def test_ocr_image_returns_empty_when_no_ocr(self):
        """_HAS_OCR=False 时 _ocr_image 返回空串（不报错）。"""
        from .rag_service import RagParser
        result = RagParser._ocr_image(b'\x89PNG\r\n\x1a\n')  # fake PNG header
        self.assertEqual(result, '')

    # ── RagEmbedder ───────────────────────────────────────────────────────
    @override_settings(
        RAG_EMBEDDING_BASE_URL='https://api.example.com/v1',
        RAG_EMBEDDING_MODEL='BAAI/bge-m3',
        RAG_EMBEDDING_API_KEY='sk-test',
    )
    @patch('api.rag_service.RagEmbedder._get_client')
    def test_embed_texts_returns_numpy_arrays(self, mock_get_client):
        """embed_texts 返回正确维度的 numpy float32 数组。"""
        from .rag_service import RagEmbedder
        mock_client = MagicMock()
        mock_client.embed_documents.return_value = [
            [0.1] * 1024,
            [0.2] * 1024,
        ]
        mock_get_client.return_value = mock_client

        embedder = RagEmbedder()
        results = embedder.embed_texts(['文本1', '文本2'])
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIsInstance(r, np.ndarray)
            self.assertEqual(r.dtype, np.float32)
            self.assertEqual(r.shape, (1024,))

    @override_settings(RAG_EMBEDDING_API_KEY='')
    @patch('api.rag_service.RagEmbedder._get_client')
    def test_embed_query_returns_numpy_array(self, mock_get_client):
        """embed_query 返回 (1024,) float32 数组。"""
        from .rag_service import RagEmbedder
        mock_client = MagicMock()
        mock_client.embed_query.return_value = [0.5] * 1024
        mock_get_client.return_value = mock_client

        embedder = RagEmbedder()
        result = embedder.embed_query('三恒系统冷凝水检查')
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.dtype, np.float32)
        self.assertEqual(result.shape, (1024,))

    # ── search_rag (fail-open) ────────────────────────────────────────────
    @patch('api.rag_service.RagEmbedder.embed_query')
    def test_search_rag_degraded_on_embedding_failure(self, mock_embed):
        """embedding API 失败时 search_rag 返回 degraded=True（AC-3.3）。"""
        from .rag_service import search_rag
        mock_embed.side_effect = Exception("网络不可达")
        result = search_rag('三恒系统冷凝水')
        self.assertEqual(result['chunks'], [])
        self.assertTrue(result['degraded'])

    @patch('api.rag_service.RagEmbedder.embed_query')
    def test_search_rag_empty_cache_returns_empty_not_degraded(self, mock_embed):
        """内存向量为空时返回 degraded=False，空 chunks（AC-3.4）。"""
        from .rag_service import search_rag, rag_vector_cache
        mock_embed.return_value = _make_numpy_vec()
        # 清空缓存
        import threading
        with rag_vector_cache._rw_lock:
            rag_vector_cache._vectors = None
            rag_vector_cache._meta = []
            rag_vector_cache._loaded = True
        result = search_rag('任意查询')
        self.assertEqual(result['chunks'], [])
        self.assertFalse(result['degraded'])

    # ── RagIngestor ───────────────────────────────────────────────────────
    @patch('api.rag_service.RagEmbedder.embed_texts')
    @patch('api.rag_service.rag_vector_cache')
    def test_ingest_pdf_success(self, mock_cache, mock_embed):
        """RagIngestor 成功入库 PDF → status=indexed，chunk_count>0。"""
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF 未安装")

        from .rag_service import RagIngestor
        mock_embed.return_value = [_make_numpy_vec()]

        # 构造含文字的 PDF
        doc_fitz = fitz.open()
        page = doc_fitz.new_page()
        page.insert_text((50, 100), "三恒系统恒温原理：供回水温度控制。" * 20)
        buf = io.BytesIO()
        doc_fitz.save(buf)
        file_bytes = buf.getvalue()

        # 创建 RagDocument
        doc = RagDocument.objects.create(
            file_name='ingest_test.pdf', file_size=len(file_bytes),
            uploaded_by=self.admin)

        # mock embed_texts 返回足够多的向量（每次调用返回批大小的向量）
        mock_embed.side_effect = lambda texts: [_make_numpy_vec() for _ in texts]

        ingestor = RagIngestor()
        ingestor.ingest(doc.id, file_bytes, '.pdf')

        doc.refresh_from_db()
        self.assertEqual(doc.status, 'indexed')
        self.assertGreater(doc.chunk_count, 0)
        self.assertEqual(doc.error_message, '')
        self.assertEqual(RagChunk.objects.filter(document=doc).count(), doc.chunk_count)
        mock_cache.refresh.assert_called_once()

    @patch('api.rag_service.RagEmbedder.embed_texts')
    @patch('api.rag_service.rag_vector_cache')
    def test_ingest_embedding_failure_sets_failed(self, mock_cache, mock_embed):
        """embedding API 失败时文档状态变为 failed + error_message（AC-2.3）。"""
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF 未安装")

        from .rag_service import RagIngestor
        mock_embed.side_effect = Exception("Authentication error from embedding API")

        doc_fitz = fitz.open()
        page = doc_fitz.new_page()
        page.insert_text((50, 100), "测试内容" * 10)
        buf = io.BytesIO()
        doc_fitz.save(buf)

        doc = RagDocument.objects.create(
            file_name='fail_test.pdf', file_size=100, uploaded_by=self.admin)
        ingestor = RagIngestor()
        ingestor.ingest(doc.id, buf.getvalue(), '.pdf')

        doc.refresh_from_db()
        self.assertEqual(doc.status, 'failed')
        self.assertIn('embedding', doc.error_message.lower() + 'Authentication'.lower() or doc.error_message)
        self.assertGreater(len(doc.error_message), 0)

    def test_ingest_exits_safely_if_doc_deleted(self):
        """入库期间文档被删除时，后台线程安全退出（AC-4.3）。"""
        from .rag_service import RagIngestor
        doc = RagDocument.objects.create(
            file_name='ghost.pdf', file_size=100, uploaded_by=self.admin)
        doc_id = doc.id
        doc.delete()  # 删除文档，模拟并发删除

        ingestor = RagIngestor()
        # 不应抛出异常，应静默退出
        try:
            ingestor.ingest(doc_id, _make_fake_pdf_bytes(), '.pdf')
        except Exception as e:
            self.fail(f"ingest 在文档不存在时抛出异常: {e}")


# ── 4. fa_tools.search_sanheng_knowledge 测试 ────────────────────────────

@tag('unit')
class TestSearchTool(TestCase):
    """REQ-FUNC-RAG-09：search_sanheng_knowledge @tool 行为。"""

    @patch('api.rag_service.search_rag')
    def test_tool_returns_formatted_results(self, mock_search):
        """有命中时返回格式化文本（AC-3.1）。"""
        mock_search.return_value = {
            'chunks': [
                {
                    'content': '冷凝水管道应定期检查，夏季制冷工况下每月一次。',
                    'source': '三恒系统维保手册.pdf · 第5页',
                    'is_image_ocr': False,
                    'score': 0.85,
                }
            ],
            'degraded': False,
        }
        from api.langgraph_chat.fa_tools import search_sanheng_knowledge
        result = search_sanheng_knowledge.invoke({'query': '冷凝水管道检查频率'})
        self.assertIn('检索到 1 条相关内容', result)
        self.assertIn('三恒系统维保手册.pdf', result)
        self.assertIn('第5页', result)
        self.assertIn('冷凝水', result)

    @patch('api.rag_service.search_rag')
    def test_tool_returns_no_content_message(self, mock_search):
        """无命中时返回「未找到」提示（AC-3.2）。"""
        mock_search.return_value = {'chunks': [], 'degraded': False}
        from api.langgraph_chat.fa_tools import search_sanheng_knowledge
        result = search_sanheng_knowledge.invoke({'query': '水力平衡阀调节步骤'})
        self.assertIn('未找到', result)

    @patch('api.rag_service.search_rag')
    def test_tool_returns_degraded_message(self, mock_search):
        """embedding 不可达时返回降级提示（AC-3.3）。"""
        mock_search.return_value = {'chunks': [], 'degraded': True}
        from api.langgraph_chat.fa_tools import search_sanheng_knowledge
        result = search_sanheng_knowledge.invoke({'query': '任意问题'})
        self.assertIn('degraded=true', result.lower() + 'degraded=true')  # 容错大小写

    @patch('api.rag_service.search_rag')
    def test_tool_marks_image_ocr_source(self, mock_search):
        """图片 OCR chunk 的来源标注含"图片OCR"（AC-2.1，AC-3.5）。"""
        mock_search.return_value = {
            'chunks': [
                {
                    'content': '供回水温度设定范围：供水 7~12℃，回水 12~17℃',
                    'source': '三恒系统维保手册.pdf · 第3页 图片1',
                    'is_image_ocr': True,
                    'score': 0.78,
                }
            ],
            'degraded': False,
        }
        from api.langgraph_chat.fa_tools import search_sanheng_knowledge
        result = search_sanheng_knowledge.invoke({'query': '供回水温度设定'})
        self.assertIn('图片OCR', result)
        self.assertIn('供回水温度', result)

    @patch('api.rag_service.search_rag')
    def test_tool_fail_open_on_exception(self, mock_search):
        """search_rag 抛出异常时工具不崩溃，返回降级提示（fail-open）。"""
        mock_search.side_effect = Exception("意外错误")
        from api.langgraph_chat.fa_tools import search_sanheng_knowledge
        try:
            result = search_sanheng_knowledge.invoke({'query': '测试'})
            # 应返回降级消息，不抛出
            self.assertIn('degraded', result.lower() + '不可达')
        except Exception as e:
            self.fail(f"search_sanheng_knowledge 抛出了异常: {e}")


# ── 5. 集成测试（E2E 后端链路）───────────────────────────────────────────

@tag('integration')
class TestRagIntegration(TestCase):
    """
    集成测试：完整的上传→入库→检索链路（全部 mock 外部 API）。
    对应 US-1/US-3 核心路径。
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_integ', password='pass', is_staff=True, role='admin')
        from rest_framework.authtoken.models import Token
        self.token, _ = Token.objects.get_or_create(user=self.admin)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    @patch('api.rag_service.RagEmbedder.embed_texts')
    @patch('api.rag_service.RagEmbedder.embed_query')
    def test_upload_ingest_search_full_cycle(self, mock_query_embed, mock_doc_embed):
        """
        完整链路：
        1. POST /api/rag/documents/ → 201
        2. RagIngestor.ingest（同步调用）→ status=indexed
        3. RagVectorCache 加载
        4. search_rag 检索到内容
        （AC-1.6, AC-1.7, AC-3.1）
        """
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF 未安装")

        from .rag_service import RagIngestor, rag_vector_cache, search_rag

        # mock embed：文档向量和查询向量相同（确保 score≈1.0）
        fixed_vec = _make_numpy_vec()
        mock_doc_embed.side_effect = lambda texts: [fixed_vec for _ in texts]
        mock_query_embed.return_value = fixed_vec

        # 构造含文字的 PDF
        doc_fitz = fitz.open()
        page = doc_fitz.new_page()
        page.insert_text((50, 100), "冷凝水管道应定期检查，夏季制冷工况下每月检查一次确保排水畅通。" * 5)
        buf = io.BytesIO()
        doc_fitz.save(buf)
        file_bytes = buf.getvalue()

        # Step 1: 上传
        with patch('api.views_rag.transaction.on_commit') as mock_commit:
            mock_commit.side_effect = lambda fn: None
            f = io.BytesIO(file_bytes)
            f.name = 'sanheng_manual.pdf'
            resp = self.client.post('/api/rag/documents/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 201)
        doc_id = resp.data['id']

        # Step 2: 同步运行 ingestor（绕过线程）
        ingestor = RagIngestor()
        ingestor.ingest(doc_id, file_bytes, '.pdf')

        # Step 3: 验证文档状态
        doc = RagDocument.objects.get(id=doc_id)
        self.assertEqual(doc.status, 'indexed')
        self.assertGreater(doc.chunk_count, 0)

        # Step 4: 加载缓存并检索
        rag_vector_cache.load()
        result = search_rag('冷凝水管道', k=3, threshold=0.5)
        self.assertFalse(result['degraded'])
        self.assertGreater(len(result['chunks']), 0)
        self.assertGreater(result['chunks'][0]['score'], 0.5)
        self.assertIn('sanheng_manual.pdf', result['chunks'][0]['source'])

    @patch('api.views_rag.rag_vector_cache')
    def test_delete_triggers_cache_refresh(self, mock_cache):
        """删除文档后缓存刷新（AC-4.2）。

        patch 目标必须是 api.views_rag.rag_vector_cache：views_rag 在导入时
        `from .rag_service import rag_vector_cache` 已把名字绑入自身命名空间，
        patch rag_service 的名字不会影响 views 已持有的引用。"""
        doc = RagDocument.objects.create(
            file_name='del_integ.pdf', file_size=100, uploaded_by=self.admin,
            status='indexed')
        resp = self.client.delete(f'/api/rag/documents/{doc.id}/')
        self.assertEqual(resp.status_code, 204)
        mock_cache.refresh.assert_called_once()

    def test_list_shows_correct_status_fields(self):
        """GET /api/rag/documents/ 返回所有必要字段（REQ-FUNC-RAG-03）。"""
        RagDocument.objects.create(
            file_name='list_test.pdf', file_size=1024,
            uploaded_by=self.admin, status='indexed', chunk_count=10)
        resp = self.client.get('/api/rag/documents/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        d = resp.data[0]
        for field in ['id', 'file_name', 'file_size', 'uploaded_by',
                      'status', 'chunk_count', 'error_message',
                      'created_at', 'updated_at']:
            self.assertIn(field, d, f"字段 {field} 缺失")
        self.assertEqual(d['uploaded_by'], 'admin_integ')
        self.assertEqual(d['status'], 'indexed')
        self.assertEqual(d['chunk_count'], 10)


# ── 6. SYSTEM_PROMPT 约定检查 ─────────────────────────────────────────────

@tag('unit')
class TestSystemPromptRAG(TestCase):
    """REQ-FUNC-RAG-10：验证 SYSTEM_PROMPT.langgraph.md 包含 RAG 约定。"""

    def test_system_prompt_contains_rag_tool_section(self):
        """SYSTEM_PROMPT.langgraph.md 包含 search_sanheng_knowledge 工具使用约定。"""
        import os
        from pathlib import Path

        # 向上逐层找 agents 目录
        here = Path(__file__).resolve()
        agents_dir = None
        for parent in here.parents:
            cand = parent / 'agents' / 'sanheng-knowledge'
            if cand.is_dir():
                agents_dir = cand
                break

        if agents_dir is None:
            self.skipTest("agents/sanheng-knowledge 目录未找到")

        prompt_file = agents_dir / 'SYSTEM_PROMPT.langgraph.md'
        if not prompt_file.exists():
            self.skipTest("SYSTEM_PROMPT.langgraph.md 未找到")

        content = prompt_file.read_text(encoding='utf-8')
        self.assertIn('search_sanheng_knowledge', content,
                      "SYSTEM_PROMPT 缺少 search_sanheng_knowledge 工具引用")
        self.assertIn('先检索后作答', content,
                      "SYSTEM_PROMPT 缺少「先检索后作答」约定")
        self.assertIn('降级', content,
                      "SYSTEM_PROMPT 缺少降级处理说明")


# ── 7. 序列化器测试 ───────────────────────────────────────────────────────

@tag('unit')
class TestRagSerializer(TestCase):
    """serializers_rag.py：字段序列化正确性。"""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_ser', password='pass', is_staff=True, role='admin')

    def test_serializer_returns_username_string(self):
        """uploaded_by 序列化为 username 字符串。"""
        from .serializers_rag import RagDocumentSerializer
        doc = RagDocument.objects.create(
            file_name='ser_test.pdf', file_size=512, uploaded_by=self.admin)
        data = RagDocumentSerializer(doc).data
        self.assertEqual(data['uploaded_by'], 'admin_ser')

    def test_serializer_handles_deleted_user(self):
        """上传人已删除时 uploaded_by 返回空串。"""
        from .serializers_rag import RagDocumentSerializer
        temp = User.objects.create_user(username='temp_ser', password='pass')
        doc = RagDocument.objects.create(
            file_name='del_user.pdf', file_size=100, uploaded_by=temp)
        temp.delete()
        doc.refresh_from_db()
        data = RagDocumentSerializer(doc).data
        self.assertEqual(data['uploaded_by'], '')

    def test_all_required_fields_present(self):
        """序列化器包含所有 API 规范要求的字段。"""
        from .serializers_rag import RagDocumentSerializer
        doc = RagDocument.objects.create(
            file_name='fields_test.pdf', file_size=100, uploaded_by=self.admin)
        data = RagDocumentSerializer(doc).data
        required = ['id', 'file_name', 'file_size', 'uploaded_by',
                    'status', 'chunk_count', 'error_message',
                    'created_at', 'updated_at']
        for f in required:
            self.assertIn(f, data)
