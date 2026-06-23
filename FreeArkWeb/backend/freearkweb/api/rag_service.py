"""
api.rag_service — RAG 核心服务模块（v1.4.1_rag_image_citation）

组件：
  RagVectorCache  — 进程内向量缓存单例（threading.Lock 保护）
  RagEmbedder     — langchain-openai OpenAIEmbeddings 封装，带 fail-open
  RagParser       — .docx（python-docx）+ .pdf（PyMuPDF）解析 + 图片 OCR
  RagIngestor     — 后台线程入库调度（解析→向量化→写DB→刷缓存）
  search_rag()    — 对外检索入口（fail-open，供 fa_tools 调用）

v1.4.1 新增：
  MAX_IMAGE_BYTES          — 单图存储上限（10MB，OQ-IC-002）
  ParsedChunk              — 新增 img_bytes/img_format/img_size 字段
  _detect_image_format()   — PNG/JPEG 文件头检测
  RagParser._try_save_image_bytes() — 大小校验 + fail-open
  RagParser.parse_docx()   — 附加 img_bytes 到 OCR chunk
  RagParser.parse_pdf()    — 路径 1/2/3 均附加 img_bytes
  RagIngestor.ingest()     — Step 4a 写 RagImage，建立 hash→RagImage 映射
  RagVectorCache.load()    — select_related('image')，meta 追加 image_id
  RagVectorCache.search()  — result dict 追加 image_id

aarch64 纪律：rapidocr-onnxruntime / onnxruntime 须在 Pi 5 真装真验证后方可使用。
              代码以 _HAS_OCR 标志防御，未验证时 OCR 跳过（不抛出）。

@module MOD-141-03
@implements IFC-141-301, IFC-141-302, IFC-141-303, IFC-141-304, IFC-141-305
@depends MOD-141-01
@author sub_agent_software_developer
"""

from __future__ import annotations

import hashlib
import http.client
import json
import logging
import os
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
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

# OCR 引擎懒加载单例：RapidOCR() 实例化会加载 ONNX 模型，原 _ocr_image 每张图重建一次
# （Pi 实测约 0.2s/次）浪费且占内存；此处全局缓存，首张图触发、后续复用。线程安全。
_ocr_engine = None
_ocr_engine_lock = threading.Lock()


def _get_ocr_engine():
    """返回进程内唯一的 RapidOCR 实例（仅在 _HAS_OCR 为真时调用）。"""
    global _ocr_engine
    if _ocr_engine is None:
        with _ocr_engine_lock:
            if _ocr_engine is None:
                _ocr_engine = _RapidOCR()
    return _ocr_engine


# ── v1.4.1 常量（MOD-141-03）──────────────────────────────────────────────
MAX_IMAGE_BYTES: int = 10 * 1024 * 1024   # 10 MB，单图存储上限（OQ-IC-002 决策）


def _detect_image_format(img_bytes: bytes) -> str:
    """
    根据文件头字节检测图片格式（IFC-141-302）。

    参数：img_bytes — 图片原始字节
    返回：'png' | 'jpeg' | 'other'

    检测规则：
      - PNG : 首 8 字节 == b'\\x89PNG\\r\\n\\x1a\\n'
      - JPEG: 首 2 字节 == b'\\xff\\xd8'
      - 其他：'other'
    """
    if not img_bytes:
        return 'other'
    if img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if img_bytes[:2] == b'\xff\xd8':
        return 'jpeg'
    return 'other'


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
            # v1.4.1：追加 select_related('image') 以避免 N+1（IFC-141-304）
            qs = (RagChunk.objects
                  .filter(document__status='indexed')
                  .select_related('document', 'image')
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
                    'image_id': c.image_id,   # v1.4.1 新增：整型 FK id 或 None（不存图片字节，IFC-141-304）
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
                'image_id': m.get('image_id'),   # v1.4.1 新增：int | None（IFC-141-305）
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
            except (OSError, http.client.HTTPException) as e:
                # 瞬时网络错误，全部可重试。OSError 覆盖 TimeoutError/ConnectionError/
                # socket.timeout 及 urllib.error.URLError（URLError 是 OSError 子类）；
                # http.client.HTTPException 覆盖 IncompleteRead（响应体被中途截断，
                # Pi WiFi 抖动常见，实测"少最后几百字节"）。
                last_err = e
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
    # ── v1.4.1 新增（MOD-141-03）──────────────────────────────────────────
    img_bytes: bytes | None = field(default=None)   # 原始图片字节（仅 is_image_ocr=True 或存图时有值）
    img_format: str = 'png'                          # 图片格式（'png'/'jpeg'/'other'）
    img_size: int = 0                                # 字节大小（冗余，避免重复 len() 调用）


# ── RagParser ─────────────────────────────────────────────────────────────

class RagParser:
    """
    文档解析器。支持 .docx（python-docx）和 .pdf（PyMuPDF）。
    图片 OCR 通过 _ocr_image()，失败时跳过（记录 WARNING）。

    v1.4.1 新增：
    - _try_save_image_bytes()：大小校验 + fail-open（IFC-141-301）
    - parse_docx() / parse_pdf()：附加 img_bytes 到 OCR chunk
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @staticmethod
    def _try_save_image_bytes(
        img_bytes: bytes,
        img_format: str,
        source_hint: str,
    ) -> tuple:
        """
        校验图片字节是否满足存储条件（IFC-141-301）。

        参数：
          img_bytes   — 原始图片字节
          img_format  — 格式字符串（'png'/'jpeg'/'other'）
          source_hint — 日志定位用（如 "第3页 图片2"）

        返回：
          (img_bytes, img_format) — 通过大小校验，可入库
          (None, '')             — 超过 MAX_IMAGE_BYTES 或字节为空，跳过

        约束：
          - 超限时记录 WARNING 日志，包含 source_hint 和 file_size
          - 不抛出异常（fail-open，REQ-NFR-003）
        """
        if not img_bytes:
            return (None, '')
        size = len(img_bytes)
        if size > MAX_IMAGE_BYTES:
            logger.warning(
                "rag_service: %s 图片超过 %d MB 上限（实际 %.1f MB），跳过存储（文档仍继续入库）",
                source_hint,
                MAX_IMAGE_BYTES // 1024 // 1024,
                size / 1024 / 1024,
            )
            return (None, '')
        return (img_bytes, img_format)

    # ── 方案1（图文同 chunk）：页面文字 chunk 继承本页代表图 ────────────────────
    # 继承图片的最小尺寸阈值（字节）。工程图纸/示意图导出通常数十 KB 以上；过滤掉
    # logo/页眉小图/扫描分隔条等"伪图"，避免文字 chunk 继承到无意义小图。
    # （生产实证 doc31：真实图纸 21KB~310KB，垃圾碎片 <1KB；阈值 4KB 全部命中且滤掉碎片。）
    _MIN_INHERIT_IMG_BYTES = 4096

    @staticmethod
    def _inherit_page_image(
        text_chunks: List['ParsedChunk'],
        page_images: List[tuple],
        page_label: str,
    ) -> None:
        """让本页「页面文字 chunk」继承本页代表图片的字节，使「描述图的文字」与「图」落到同一可检索 chunk。

        动机（生产实证）：PDF 解析的 路径1(页面文字层) 与 路径2(图片OCR) 产出**两条独立 chunk**——
        描述详尽的文字（如 "B.DW02/03/04PX 内部结构 ①上面板…"）在文字 chunk（image_id=NULL），
        而图自身 OCR 多为碎片（"12"/"al"），用户"问图"时语义命中文字 chunk 却取不到图。
        令文字 chunk 继承本页图片后，命中描述文字即可回显原图。亦可救回"OCR 空、仅占位"的孤儿图。

        选图规则：取本页**最大**的一张已存图片（图纸通常远大于 logo），且需 ≥ 阈值。受 RagChunk.image
        单 FK 约束，每 chunk 只继承一张；一页多图时其余图仍由各自 OCR chunk 承载（命中其碎片文字才出，
        概率低，属已知局限）。

        不改 is_image_ocr（保持 False：这是页面文字，非图片 OCR），不覆盖已自带 img_bytes 的 chunk
        （路径3 扫描页文字本就源自整页图）。依赖 RagIngestor 的 img_bytes 哈希去重：文字 chunk 与图
        OCR chunk 共享同一图字节 → 只建一行 RagImage，二者 image_id 指向同一图。
        """
        if not text_chunks or not page_images:
            return
        primary = max(page_images, key=lambda t: t[2])   # 取本页最大图作代表
        p_bytes, p_fmt, p_size = primary
        if p_size < RagParser._MIN_INHERIT_IMG_BYTES:
            return   # 仅 logo/分隔条等小图，不继承
        inherited = 0
        for c in text_chunks:
            if c.img_bytes is None:   # 不覆盖已自带图字节的 chunk（如扫描页文字）
                c.img_bytes = p_bytes
                c.img_format = p_fmt
                c.img_size = p_size
                inherited += 1
        if inherited:
            logger.info(
                "rag_service: %s 文字 chunk 继承本页代表图（%d 字节）×%d 条（方案1 图文同 chunk）",
                page_label, p_size, inherited)

    def _split_text(self, text: str, source: str,
                    is_image_ocr: bool = False) -> List[ParsedChunk]:
        """
        滑动窗口分块，不在段落中间强制切断超过 chunk_size 的文本。
        重叠量 chunk_overlap 字符。
        is_image_ocr：标记产出的全部 chunk 来源于图片 OCR（整页扫描/内嵌图片的
        OCR 文本同样可能超过 chunk_size，需走此处分块，避免单个超大 chunk 拖累检索粒度）。
        """
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [ParsedChunk(content=text, page_or_section=source,
                                is_image_ocr=is_image_ocr)]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(ParsedChunk(
                content=text[start:end].strip(),
                page_or_section=source,
                is_image_ocr=is_image_ocr,
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

        # 图片 OCR + v1.4.1：附加 img_bytes 到 OCR chunk（MOD-141-03）
        img_idx = 0
        for rel in doc.part.rels.values():
            if "image" in (rel.target_ref or ""):
                try:
                    img_bytes_raw = rel.target_part.blob
                    img_idx += 1
                    source_hint = f"图片 {img_idx}"

                    # v1.4.1：检测格式 + 大小校验（fail-open：超限时 saved_bytes=None）
                    img_fmt = _detect_image_format(img_bytes_raw)
                    saved_bytes, saved_fmt = self._try_save_image_bytes(
                        img_bytes_raw, img_fmt, source_hint)

                    ocr_text = self._ocr_image(img_bytes_raw)   # 无论能否存储都 OCR
                    if ocr_text:
                        split_chunks = self._split_text(ocr_text, source_hint)
                        for c in split_chunks:
                            # v1.4.1：同一图片的所有 split_text chunk 共享一份 img_bytes
                            c.is_image_ocr = True
                            c.img_bytes = saved_bytes   # None 表示超限或提取失败
                            c.img_format = saved_fmt
                            c.img_size = len(saved_bytes) if saved_bytes else 0
                        chunks.extend(split_chunks)
                    elif saved_bytes is not None:
                        # 无 OCR 文字但有图片：创建空内容 chunk 承载图片（US-IC-005 AC-IC-005-03）
                        # 注意：空 content chunk 不加入文字检索，仅在 RagIngestor 写 RagImage 时使用
                        placeholder = ParsedChunk(
                            content='',
                            page_or_section=source_hint,
                            is_image_ocr=True,
                            img_bytes=saved_bytes,
                            img_format=saved_fmt,
                            img_size=len(saved_bytes),
                        )
                        chunks.append(placeholder)
                except Exception as e:
                    logger.warning("rag_service: docx 图片提取失败，跳过: %s", e)

        return chunks

    # 扫描件 PDF 整页渲染配置
    # DPI=150：对 A0~A1 大图纸（约 1189×841mm）渲染后约 7000×5000px，rapidocr 可处理；
    # 更高 DPI（300）会使单页 pixmap 超过 200MB，Pi 5（8GB RAM）在多页图纸时有 OOM 风险。
    # 若 OCR 结果太少（大尺寸图纸文字密度低），可适当提高至 200。
    _SCAN_RENDER_DPI = 150
    # 整页渲染后图片字节大小上限（防止超大图纸耗尽内存）：50MB
    _SCAN_MAX_IMG_BYTES = 50 * 1024 * 1024

    def parse_pdf(self, file_bytes: bytes) -> List[ParsedChunk]:
        """
        PyMuPDF 解析 .pdf（AGPL v3，内部平台合规，见 ADR-003）：
        - 页面文字按 chunk_size 分块，来源标注"第 N 页"
        - 页面内嵌图片 XObject OCR，来源标注"第 N 页 图片M"
        - 扫描件/图纸 fallback：若整页既无文本层又无可提取 XObject 图片，
          则将该页光栅化（get_pixmap）后整体 OCR，来源标注"第 N 页 扫描"。
          此 fallback 覆盖"整页内容编码为页面位图流而非 XObject"的扫描 PDF。

        方案1（图文同 chunk）：页末令本页「页面文字 chunk」继承本页代表图片字节
        （见 _inherit_page_image），使"描述图的文字"与"图"落到同一可检索 chunk——
        修复"问图时命中文字 chunk 却取不到图"（图自身 OCR 多为碎片，语义匹配不上）。
        """
        import io
        import fitz  # PyMuPDF

        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        chunks: List[ParsedChunk] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_label = f"第 {page_num + 1} 页"
            # 方案1（图文同 chunk）：按页收集，便于页末让文字 chunk 继承本页代表图。
            page_text_chunks: List[ParsedChunk] = []
            page_image_chunks: List[ParsedChunk] = []
            page_images: List[tuple] = []   # 本页已存图片 [(bytes, fmt, size)]，供文字 chunk 继承

            # ── 路径1：页面文字层 ──────────────────────────────────────────
            text = page.get_text().strip()
            if text:
                page_text_chunks.extend(self._split_text(text, page_label))

            # ── 路径2：页面内嵌 XObject 图片 OCR ──────────────────────────
            img_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(img_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_bytes_raw = base_image["image"]
                    # v1.4.1：PyMuPDF 提供 ext 字段（格式字符串），兜底用 _detect
                    raw_ext = (base_image.get("ext") or "").lower().strip(".")
                    if raw_ext in ("png", "jpeg", "jpg"):
                        img_fmt = "jpeg" if raw_ext == "jpg" else raw_ext
                    else:
                        img_fmt = _detect_image_format(img_bytes_raw)
                    source_hint = f"{page_label} 图片{img_idx + 1}"
                    saved_bytes, saved_fmt = self._try_save_image_bytes(
                        img_bytes_raw, img_fmt, source_hint)
                    if saved_bytes is not None:
                        # 方案1：登记本页图片，供页末文字 chunk 继承
                        page_images.append((saved_bytes, saved_fmt, len(saved_bytes)))

                    ocr_text = self._ocr_image(img_bytes_raw)
                    if ocr_text:
                        split_chunks = self._split_text(ocr_text, source_hint)
                        for c in split_chunks:
                            c.is_image_ocr = True
                            c.img_bytes = saved_bytes
                            c.img_format = saved_fmt
                            c.img_size = len(saved_bytes) if saved_bytes else 0
                        page_image_chunks.extend(split_chunks)
                    elif saved_bytes is not None:
                        # 无 OCR 文字但有图片（OQ-IC-003）
                        placeholder = ParsedChunk(
                            content='',
                            page_or_section=source_hint,
                            is_image_ocr=True,
                            img_bytes=saved_bytes,
                            img_format=saved_fmt,
                            img_size=len(saved_bytes),
                        )
                        page_image_chunks.append(placeholder)
                except Exception as e:
                    logger.warning("rag_service: pdf 图片 OCR 失败，跳过: %s", e)

            # ── 路径3：扫描件 fallback — 整页栅格化 OCR ───────────────────
            # 触发条件：该页既无可提取文本，也无 XObject 图片（典型扫描件/图纸 PDF）。
            # 原理：将整页渲染为 PNG pixmap，直接对 PNG bytes 调 rapidocr。
            # get_text() 对扫描件始终返回 ""，get_images() 对"页面流位图"扫描件返回 []，
            # 两者均为假时说明本页内容完全在光栅化页面流中，需此 fallback 才能提取文字。
            if not text and not img_list:
                if not _HAS_OCR:
                    logger.warning(
                        "rag_service: 第 %d 页为扫描件但 OCR 未启用，跳过该页",
                        page_num + 1,
                    )
                else:
                    try:
                        mat = fitz.Matrix(
                            self._SCAN_RENDER_DPI / 72,
                            self._SCAN_RENDER_DPI / 72,
                        )
                        pixmap = page.get_pixmap(matrix=mat, alpha=False)
                        png_bytes = pixmap.tobytes("png")
                        pixmap = None  # 及时释放，防止大图纸多页 OOM

                        if len(png_bytes) > self._SCAN_MAX_IMG_BYTES:
                            logger.warning(
                                "rag_service: 第 %d 页渲染后 %.1f MB，超过 %d MB 上限，跳过",
                                page_num + 1,
                                len(png_bytes) / 1024 / 1024,
                                self._SCAN_MAX_IMG_BYTES // 1024 // 1024,
                            )
                        else:
                            logger.info(
                                "rag_service: 第 %d 页为扫描件，整页渲染 %.1f MB，执行 OCR",
                                page_num + 1,
                                len(png_bytes) / 1024 / 1024,
                            )
                            # v1.4.1：扫描件整页大图也纳入存储（OQ-IC-003），受 10MB 上限约束
                            scan_source = f"{page_label} 扫描"
                            saved_bytes, saved_fmt = self._try_save_image_bytes(
                                png_bytes, 'png', scan_source)
                            if saved_bytes is not None:
                                # 方案1：登记本页整页图，供文字 chunk 继承（路径3 文字本就源自整页图，
                                # 其文字 chunk 已自带 img_bytes，_inherit_page_image 不会覆盖）
                                page_images.append((saved_bytes, saved_fmt, len(saved_bytes)))

                            ocr_text = self._ocr_image(png_bytes)
                            if ocr_text:
                                split_chunks = self._split_text(ocr_text, scan_source)
                                for c in split_chunks:
                                    c.is_image_ocr = True
                                    c.img_bytes = saved_bytes   # 可能为 None（超 10MB）
                                    c.img_format = saved_fmt
                                    c.img_size = len(saved_bytes) if saved_bytes else 0
                                page_image_chunks.extend(split_chunks)
                            elif saved_bytes is not None:
                                # 扫描件 OCR 空 + 图片可存：创建占位 chunk（OQ-IC-003）
                                placeholder = ParsedChunk(
                                    content='',
                                    page_or_section=scan_source,
                                    is_image_ocr=True,
                                    img_bytes=saved_bytes,
                                    img_format=saved_fmt,
                                    img_size=len(saved_bytes),
                                )
                                page_image_chunks.append(placeholder)
                                logger.warning(
                                    "rag_service: 第 %d 页扫描件 OCR 返回空（图纸无可识别文字或图像质量不足），图片仍存储",
                                    page_num + 1,
                                )
                            else:
                                logger.warning(
                                    "rag_service: 第 %d 页扫描件 OCR 返回空（图纸无可识别文字或图像质量不足）",
                                    page_num + 1,
                                )
                    except Exception as e:
                        logger.warning(
                            "rag_service: 第 %d 页扫描件整页 OCR 失败，跳过: %s",
                            page_num + 1, e,
                        )

            # ── 方案1（图文同 chunk）：本页文字 chunk 继承本页代表图，再按"文字先、图后"汇入 ──
            self._inherit_page_image(page_text_chunks, page_images, page_label)
            chunks.extend(page_text_chunks)
            chunks.extend(page_image_chunks)

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
            ocr = _get_ocr_engine()
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

            # v1.4.1：分离有内容的 chunk（需向量化）与纯图片占位 chunk（不向量化）
            text_chunks = [c for c in parsed if c.content]   # 有文字内容，需向量化
            image_only_chunks = [c for c in parsed if not c.content and c.img_bytes]  # 纯图片占位

            if not text_chunks and not image_only_chunks:
                raise ValueError("文档解析后无任何文字内容")
            if not text_chunks:
                logger.warning(
                    "rag_service: 文档 %s 解析后无文字 chunk（仅有纯图片），仍继续存储图片",
                    doc_id)

            # 中途检查：文档是否已被删除
            if not RagDocument.objects.filter(id=doc_id).exists():
                logger.info("rag_service: 文档 %s 入库期间被删除，安全退出", doc_id)
                return

            # Step 3: 批量向量化（仅针对有文字内容的 chunk，跳过纯图片占位 chunk）
            embedder = RagEmbedder()
            all_data: List[tuple] = []  # [(ParsedChunk, np.ndarray)]
            for i in range(0, len(text_chunks), self.BATCH_SIZE):
                batch = text_chunks[i:i + self.BATCH_SIZE]
                texts = [c.content for c in batch]
                try:
                    vecs = embedder.embed_texts(texts)
                except Exception as e:
                    raise RuntimeError(f"向量化失败（批次 {i // self.BATCH_SIZE + 1}）: {e}") from e
                for chunk, vec in zip(batch, vecs):
                    all_data.append((chunk, vec))

            # v1.4.1：将纯图片占位 chunk 也加入 all_data（用于 Step 4a 写 RagImage），
            # 但不写向量（Step 4 过滤 content='' 的 chunk 不进 RagChunk 向量表）
            # 用 None 作为向量占位（Step 4 中显式跳过 content='' 的 chunk）
            all_data_with_img_only = list(all_data)   # 含向量的有文字 chunk
            img_only_data = [(c, None) for c in image_only_chunks]  # 纯图片占位，无向量

            # 中途再次检查
            if not RagDocument.objects.filter(id=doc_id).exists():
                return

            # ── v1.4.1 Step 4a：写入 RagImage，建立 chunk.image_id 映射（IFC-141-303）──
            from .models_rag import RagImage   # 延迟 import 避免循环（与 RagDocument 同模块）
            # 去重 key：img_bytes 前 256 字节 MD5（快速 hash，非密码学用途）
            # 同一图片可能对应多个 split_text chunk，只写一次 RagImage 行
            img_key_to_rag_image: dict = {}   # md5_hex → RagImage 对象
            image_write_errors = 0
            image_counter = 0

            # 遍历所有含图片字节的 chunk（有文字 chunk + 纯图片占位 chunk）
            combined_for_images = all_data_with_img_only + img_only_data
            for chunk, _vec in combined_for_images:
                if chunk.img_bytes is None:
                    continue   # 无图片（纯文字 chunk 或超限跳过）
                img_key = hashlib.md5(chunk.img_bytes[:256]).hexdigest()
                if img_key in img_key_to_rag_image:
                    continue   # 已写入（同一图片多个 OCR chunk 共享一个 RagImage 行）
                try:
                    rag_image = RagImage.objects.create(
                        document_id=doc_id,
                        image_index=image_counter,
                        page_or_section=chunk.page_or_section,
                        image_format=chunk.img_format,
                        image_data=chunk.img_bytes,
                        file_size=chunk.img_size,
                    )
                    img_key_to_rag_image[img_key] = rag_image
                    image_counter += 1
                except Exception as e:
                    image_write_errors += 1
                    logger.warning(
                        "rag_service: 文档 %s 图片写入失败（跳过，文档继续入库，fail-open）: %s",
                        doc_id, e)
                    # fail-open：图片写入失败不阻断文档入库（REQ-NFR-003，C-008）

            if image_write_errors > 0:
                logger.warning(
                    "rag_service: 文档 %s 共 %d 张图片写入失败，对应 chunk 的 image_id 为 None",
                    doc_id, image_write_errors)
            if image_counter > 0:
                logger.info("rag_service: 文档 %s 成功写入 %d 张图片", doc_id, image_counter)
            # ──────────────────────────────────────────────────────────────────────────

            # Step 4: 写入 RagChunk DB（bulk_create，仅有文字内容的 chunk）
            # 纯图片占位 chunk（content=''）已在 Step 4a 存了 RagImage，不进向量表
            chunk_objs = []
            for idx, (chunk, vec) in enumerate(all_data_with_img_only):
                # v1.4.1：查找本 chunk 对应的 RagImage（按 img_bytes hash 匹配）
                image_obj = None
                if chunk.img_bytes is not None:
                    img_key = hashlib.md5(chunk.img_bytes[:256]).hexdigest()
                    image_obj = img_key_to_rag_image.get(img_key)   # 可能为 None（写入失败时）

                chunk_objs.append(RagChunk(
                    document_id=doc_id,
                    chunk_index=idx,
                    content=chunk.content,
                    embedding=vec.tobytes(),
                    page_or_section=chunk.page_or_section,
                    is_image_ocr=chunk.is_image_ocr,
                    image=image_obj,   # v1.4.1 新增：可为 None（纯文字 chunk 或图片写入失败）
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
