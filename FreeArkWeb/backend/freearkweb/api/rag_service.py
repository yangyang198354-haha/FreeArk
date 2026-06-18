"""
api.rag_service — RAG 核心服务模块（v1.4.0_sanheng_rag）

组件：
  RagVectorCache  — 进程内向量缓存单例（threading.Lock 保护）
  RagEmbedder     — langchain-openai OpenAIEmbeddings 封装，带 fail-open
  RagParser       — .docx（python-docx）+ .pdf（PyMuPDF）解析 + 图片 OCR
  RagIngestor     — 后台线程入库调度（解析→向量化→写DB→刷缓存）
  search_rag()    — 对外检索入口（fail-open，供 fa_tools 调用）

aarch64 纪律：rapidocr-onnxruntime / onnxruntime 须在 Pi 5 真装真验证后方可使用。
              代码以 _HAS_OCR 标志防御，未验证时 OCR 跳过（不抛出）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger("api.rag_service")

# ── OCR 可用性探测（aarch64 纪律）─────────────────────────────────────────
_HAS_OCR = False
try:
    from rapidocr_onnxruntime import RapidOCR as _RapidOCR
    _HAS_OCR = True
    logger.info("rag_service: rapidocr-onnxruntime 可用，OCR 功能启用")
except ImportError:
    logger.info("rag_service: rapidocr-onnxruntime 未安装，OCR 功能跳过（需 Pi 验证后启用）")
except Exception as _e:
    logger.warning("rag_service: rapidocr-onnxruntime 导入失败（%s），OCR 功能跳过", _e)


# ── RagVectorCache ─────────────────────────────────────────────────────────

class RagVectorCache:
    """
    进程内向量缓存单例。
    _vectors: shape=(N, 1024), float32，首次 search 时懒加载。
    threading.Lock 保护写操作（load/refresh），读操作（search）使用快照。
    """

    _instance: Optional['RagVectorCache'] = None
    _class_lock = threading.Lock()

    def __init__(self):
        self._vectors: Optional[np.ndarray] = None   # (N, dim)
        self._meta: List[dict] = []                   # [{doc_name, source, is_image_ocr, content}]
        self._loaded = False
        self._rw_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'RagVectorCache':
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """从 DB 全量加载所有 indexed 文档的 chunks。线程安全。"""
        from .models_rag import RagChunk
        try:
            qs = (RagChunk.objects
                  .filter(document__status='indexed')
                  .select_related('document')
                  .order_by('id'))
            vectors, meta = [], []
            for c in qs:
                raw = bytes(c.embedding)  # Django BinaryField 返回 memoryview，转 bytes
                vec = np.frombuffer(raw, dtype=np.float32).copy()
                vectors.append(vec)
                meta.append({
                    'doc_name': c.document.file_name,
                    'source': c.page_or_section,
                    'is_image_ocr': c.is_image_ocr,
                    'content': c.content,
                })
            with self._rw_lock:
                self._vectors = np.array(vectors, dtype=np.float32) if vectors else None
                self._meta = meta
                self._loaded = True
            logger.info("rag_service: 向量缓存加载完成，共 %d 条 chunk", len(vectors))
        except Exception as e:
            logger.error("rag_service: 向量缓存加载失败: %s", e)

    def refresh(self) -> None:
        """在后台线程中异步触发 load()。文档新增/删除后调用。"""
        t = threading.Thread(target=self.load, daemon=True, name="rag-cache-refresh")
        t.start()

    def _ensure_loaded(self) -> None:
        """懒加载：首次 search 时若未加载则同步加载（避免启动时拖慢冷启动）。"""
        if not self._loaded:
            self.load()

    def search(self, query_vec: np.ndarray, k: int = 5,
               threshold: float = 0.3) -> List[dict]:
        """
        余弦相似度 top-k 检索。
        返回按分数降序的 dict 列表，score < threshold 的结果丢弃。
        线程安全（读取快照）。
        """
        self._ensure_loaded()
        with self._rw_lock:
            if self._vectors is None or len(self._vectors) == 0:
                return []
            vectors = self._vectors.copy()
            meta = list(self._meta)

        # 余弦相似度计算
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
        normed = vectors / norms
        scores = normed @ query_norm    # shape=(N,)

        top_idx = np.argsort(scores)[::-1][:k]
        results = []
        for i in top_idx:
            if float(scores[i]) < threshold:
                break
            m = meta[i]
            results.append({
                'content': m['content'],
                'source': f"{m['doc_name']} · {m['source']}",
                'is_image_ocr': m['is_image_ocr'],
                'score': float(scores[i]),
            })
        return results


# 进程级单例
rag_vector_cache = RagVectorCache.get_instance()


# ── 豆包多模态 embedding 适配器 ─────────────────────────────────────────────

class _DoubaoMultimodalEmbeddings:
    """
    火山方舟多模态 embedding（doubao-embedding-vision 系列）适配器。

    多模态接口 POST {base_url}/embeddings/multimodal 一次只对“一个文档”
    （由若干 {type:text/image_url} 片段拼成）输出一个向量，**不支持多文档批量**
    （实测：input 传多个对象只回 1 个向量）。故 embed_documents 逐条调用。
    其 URL / 请求体 / 返回结构（data 为 dict 而非 list）与 OpenAI /embeddings 均不同，
    无法用 langchain OpenAIEmbeddings，这里用裸 HTTP 实现，接口对齐 embed_documents/embed_query。
    """

    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 20.0):
        self._url = (base_url or '').rstrip('/') + '/embeddings/multimodal'
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def _embed_one(self, text: str, attempts: int, timeout: float) -> List[float]:
        """
        单条向量化，带退避重试。
        豆包 vision 模型偏慢 + Pi WiFi 偶发劣化，单次读超时常见（实测 8 次 1 次 >15s）。
        瞬时错误（读超时 / 连接重置 / 5xx）退避重试；4xx（参数/模型错）立即抛（重试无意义）。
        """
        body = json.dumps({
            "model": self._model,
            "input": [{"type": "text", "text": text}],
        }).encode("utf-8")
        last_err = None
        for i in range(attempts):
            req = urllib.request.Request(
                self._url, data=body,
                headers={
                    "Authorization": "Bearer " + self._api_key,
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    d = json.loads(r.read())
                return d["data"]["embedding"]   # 多模态接口 data 为单对象（非列表）
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:          # 客户端错误，重试无意义
                    raise
                last_err = e                     # 5xx 服务端错误，可重试
            except (TimeoutError, ConnectionError, urllib.error.URLError) as e:
                last_err = e                     # 读超时 / 连接失败，瞬时可重试
            if i < attempts - 1:
                logger.warning("rag_service: 豆包 embedding 第 %d 次失败（%r），退避重试",
                               i + 1, last_err)
                time.sleep(min(2 ** i, 4))
        raise last_err

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 入库冷路径：重试多、超时长，优先可靠（单条慢调用不应整篇 failed）
        return [self._embed_one(t, attempts=4, timeout=max(self._timeout, 25.0))
                for t in texts]

    def embed_query(self, text: str) -> List[float]:
        # 查询热路径：重试少、超时短，优先有界延迟（失败由 search_rag fail-open 兜底）
        return self._embed_one(text, attempts=2, timeout=min(self._timeout, 12.0))


# ── RagEmbedder ───────────────────────────────────────────────────────────

class RagEmbedder:
    """
    embedding 封装，从 django.conf.settings 读取 RAG_EMBEDDING_* 配置（凭据仅走 .env）。
    按 RAG_EMBEDDING_API_STYLE 选择后端：
      'openai'            → langchain-openai OpenAIEmbeddings（标准 /embeddings，支持批量）
      'doubao_multimodal' → 火山方舟多模态 /embeddings/multimodal（逐条，非批量）
    """

    def _get_client(self):
        from django.conf import settings
        base_url = getattr(settings, 'RAG_EMBEDDING_BASE_URL', '')
        model = getattr(settings, 'RAG_EMBEDDING_MODEL', 'BAAI/bge-m3')
        api_key = getattr(settings, 'RAG_EMBEDDING_API_KEY', '') or 'sk-noop'
        style = getattr(settings, 'RAG_EMBEDDING_API_STYLE', 'openai')

        if style == 'doubao_multimodal':
            # 火山方舟多模态 embedding（doubao-embedding-vision）：逐条调用、非批量。
            return _DoubaoMultimodalEmbeddings(base_url, model, api_key, timeout=15.0)

        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            base_url=base_url or None,
            model=model,
            api_key=api_key,
            # 入库批量(20条)走 Pi→远端，5s 太紧易超时把文档误判 failed；
            # query 端 fail-open，最坏在 embedding 故障时阻塞至此上限，取 15s 折中。
            timeout=15.0,
            # 关键：第三方 OpenAI 兼容端点（豆包/火山方舟、硅基流动等）必须关掉客户端
            # tiktoken 切分，否则 langchain 会把文本编成 token-id 数组发送（非原始文本），
            # 第三方用自家分词器 → 语义错乱或直接报错。关掉后按原始字符串发送，服务端分词。
            check_embedding_ctx_length=False,
        )

    def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """批量 embed，返回 list[np.ndarray(float32, shape=(dim,))]。"""
        client = self._get_client()
        vecs = client.embed_documents(texts)
        return [np.array(v, dtype=np.float32) for v in vecs]

    def embed_query(self, text: str) -> np.ndarray:
        """单次 embed（检索 query 用）。"""
        client = self._get_client()
        v = client.embed_query(text)
        return np.array(v, dtype=np.float32)


# ── ParsedChunk ───────────────────────────────────────────────────────────

@dataclass
class ParsedChunk:
    content: str
    page_or_section: str
    is_image_ocr: bool = False


# ── RagParser ─────────────────────────────────────────────────────────────

class RagParser:
    """
    文档解析器。支持 .docx（python-docx）和 .pdf（PyMuPDF）。
    图片 OCR 通过 _ocr_image()，失败时跳过（记录 WARNING）。
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _split_text(self, text: str, source: str) -> List[ParsedChunk]:
        """
        滑动窗口分块，不在段落中间强制切断超过 chunk_size 的文本。
        重叠量 chunk_overlap 字符。
        """
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [ParsedChunk(content=text, page_or_section=source)]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(ParsedChunk(
                content=text[start:end].strip(),
                page_or_section=source,
            ))
            if end >= len(text):
                break
            start = end - self.chunk_overlap
        return [c for c in chunks if c.content]

    def parse_docx(self, file_bytes: bytes) -> List[ParsedChunk]:
        """
        python-docx 解析 .docx：
        - 段落文字合并后按 chunk_size 分块，来源标注"段落 N"
        - 图片对象提取后 OCR，来源标注"图片 N"
        """
        import io
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        chunks: List[ParsedChunk] = []

        # 段落文字
        text_buffer = ""
        para_idx = 0
        for para in doc.paragraphs:
            para_idx += 1
            text = para.text.strip()
            if not text:
                continue
            text_buffer += text + "\n"
            if len(text_buffer) >= self.chunk_size:
                chunks.extend(self._split_text(text_buffer, f"段落 {para_idx}"))
                # 保留末尾 overlap
                text_buffer = text_buffer[-self.chunk_overlap:] if self.chunk_overlap else ""
        if text_buffer.strip():
            chunks.extend(self._split_text(text_buffer.strip(), f"段落 {para_idx}"))

        # 图片 OCR
        img_idx = 0
        for rel in doc.part.rels.values():
            if "image" in (rel.target_ref or ""):
                try:
                    img_bytes = rel.target_part.blob
                    img_idx += 1
                    ocr_text = self._ocr_image(img_bytes)
                    if ocr_text:
                        chunks.append(ParsedChunk(
                            content=ocr_text,
                            page_or_section=f"图片 {img_idx}",
                            is_image_ocr=True,
                        ))
                except Exception as e:
                    logger.warning("rag_service: docx 图片提取失败，跳过: %s", e)

        return chunks

    def parse_pdf(self, file_bytes: bytes) -> List[ParsedChunk]:
        """
        PyMuPDF 解析 .pdf（AGPL v3，内部平台合规，见 ADR-003）：
        - 页面文字按 chunk_size 分块，来源标注"第 N 页"
        - 页面图片 OCR，来源标注"第 N 页 图片M"
        """
        import io
        import fitz  # PyMuPDF

        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        chunks: List[ParsedChunk] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_label = f"第 {page_num + 1} 页"

            # 页面文字
            text = page.get_text().strip()
            if text:
                chunks.extend(self._split_text(text, page_label))

            # 页面图片 OCR
            img_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(img_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_bytes = base_image["image"]
                    ocr_text = self._ocr_image(img_bytes)
                    if ocr_text:
                        chunks.append(ParsedChunk(
                            content=ocr_text,
                            page_or_section=f"{page_label} 图片{img_idx + 1}",
                            is_image_ocr=True,
                        ))
                except Exception as e:
                    logger.warning("rag_service: pdf 图片 OCR 失败，跳过: %s", e)

        return chunks

    @staticmethod
    def _ocr_image(img_bytes: bytes) -> str:
        """
        OCR 单张图片。
        aarch64 纪律：_HAS_OCR=False 时直接返回空串（跳过）。
        OCR 失败时记录 WARNING 并返回空串（不抛出，见 OQ-07 决策）。
        """
        if not _HAS_OCR:
            return ""
        try:
            ocr = _RapidOCR()
            result, _ = ocr(img_bytes)
            if result:
                return "\n".join(
                    line[1] for line in result
                    if len(line) > 1 and line[1]
                )
        except Exception as e:
            logger.warning("rag_service: OCR 推理失败，跳过: %s", e)
        return ""


# ── RagIngestor ───────────────────────────────────────────────────────────

class RagIngestor:
    """
    后台线程入库调度。
    调用方（views_rag.py）在 transaction.on_commit 中启动 ingest() 守护线程。
    全程捕获异常，失败写 status=failed + error_message，不让线程静默崩溃。
    """

    BATCH_SIZE = 20  # 每批向量化 chunk 数（控制单次 API 调用规模）

    def ingest(self, doc_id: int, file_bytes: bytes, file_ext: str) -> None:
        """
        入库主流程（在守护线程中运行）。
        file_ext: '.docx' 或 '.pdf'（小写）
        """
        from .models_rag import RagDocument, RagChunk
        from django.conf import settings

        # 安全获取文档（可能已被并发删除）
        try:
            doc = RagDocument.objects.get(id=doc_id)
        except RagDocument.DoesNotExist:
            logger.info("rag_service: 文档 %s 已被删除，入库任务退出", doc_id)
            return

        try:
            # Step 1: 更新状态为 parsing
            doc.status = RagDocument.STATUS_PARSING
            doc.error_message = ''
            doc.save(update_fields=['status', 'error_message', 'updated_at'])

            # Step 2: 解析文档
            chunk_size = getattr(settings, 'RAG_CHUNK_SIZE', 500)
            chunk_overlap = getattr(settings, 'RAG_CHUNK_OVERLAP', 50)
            parser = RagParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

            if file_ext == '.docx':
                parsed = parser.parse_docx(file_bytes)
            elif file_ext == '.pdf':
                parsed = parser.parse_pdf(file_bytes)
            else:
                raise ValueError(f"不支持的文件类型: {file_ext}")

            if not parsed:
                raise ValueError("文档解析后无任何文字内容")

            # 中途检查：文档是否已被删除
            if not RagDocument.objects.filter(id=doc_id).exists():
                logger.info("rag_service: 文档 %s 入库期间被删除，安全退出", doc_id)
                return

            # Step 3: 批量向量化
            embedder = RagEmbedder()
            all_data: List[tuple] = []  # [(ParsedChunk, np.ndarray)]
            for i in range(0, len(parsed), self.BATCH_SIZE):
                batch = parsed[i:i + self.BATCH_SIZE]
                texts = [c.content for c in batch]
                try:
                    vecs = embedder.embed_texts(texts)
                except Exception as e:
                    raise RuntimeError(f"向量化失败（批次 {i // self.BATCH_SIZE + 1}）: {e}") from e
                for chunk, vec in zip(batch, vecs):
                    all_data.append((chunk, vec))

            # 中途再次检查
            if not RagDocument.objects.filter(id=doc_id).exists():
                return

            # Step 4: 写入 DB（bulk_create）
            chunk_objs = []
            for idx, (chunk, vec) in enumerate(all_data):
                chunk_objs.append(RagChunk(
                    document_id=doc_id,
                    chunk_index=idx,
                    content=chunk.content,
                    embedding=vec.tobytes(),
                    page_or_section=chunk.page_or_section,
                    is_image_ocr=chunk.is_image_ocr,
                ))
            RagChunk.objects.bulk_create(chunk_objs)

            # Step 5: 更新状态为 indexed
            RagDocument.objects.filter(id=doc_id).update(
                status=RagDocument.STATUS_INDEXED,
                chunk_count=len(chunk_objs),
                error_message='',
            )
            # 手动更新 updated_at（update() 不触发 auto_now）
            from django.utils import timezone
            RagDocument.objects.filter(id=doc_id).update(updated_at=timezone.now())

            logger.info("rag_service: 文档 %s 入库成功，共 %d 条 chunk",
                        doc_id, len(chunk_objs))

            # Step 6: 刷新内存向量缓存
            rag_vector_cache.refresh()

        except Exception as e:
            error_text = f"{type(e).__name__}: {e}"
            logger.error(
                "rag_service: 文档 %s 入库失败: %s\n%s",
                doc_id, error_text, traceback.format_exc()
            )
            try:
                from django.utils import timezone
                RagDocument.objects.filter(id=doc_id).update(
                    status=RagDocument.STATUS_FAILED,
                    error_message=error_text[:1000],
                    updated_at=timezone.now(),
                )
            except Exception as db_e:
                logger.error("rag_service: 写 failed 状态失败: %s", db_e)


# 模块级单例
_ingestor = RagIngestor()


def start_ingest_thread(doc_id: int, file_bytes: bytes, file_ext: str) -> None:
    """
    在 transaction.on_commit 回调中调用本函数，启动守护线程执行入库。
    """
    t = threading.Thread(
        target=_ingestor.ingest,
        args=(doc_id, file_bytes, file_ext),
        daemon=True,
        name=f"rag-ingest-{doc_id}",
    )
    t.start()
    logger.info("rag_service: 已启动入库线程 rag-ingest-%s", doc_id)


# ── 对外检索入口 ──────────────────────────────────────────────────────────

def search_rag(query: str, k: int = 5, threshold: float = 0.3) -> dict:
    """
    对外检索入口，供 fa_tools.search_sanheng_knowledge 调用。

    返回格式：
      {"chunks": [...], "degraded": False}   — 正常（chunks 可为空列表）
      {"chunks": [], "degraded": True}        — embedding API 不可达或异常

    fail-open：任何异常均捕获，不抛出到调用方（不打挂聊天）。
    """
    try:
        embedder = RagEmbedder()
        query_vec = embedder.embed_query(query)
        results = rag_vector_cache.search(query_vec, k=k, threshold=threshold)
        return {"chunks": results, "degraded": False}
    except Exception as e:
        logger.warning("rag_service: search_rag 失败（降级）: %s", e)
        return {"chunks": [], "degraded": True}
