**特性**：三恒知识库 RAG 图片引用回溯（Image Citation）
**版本**：v1.4.1_rag_image_citation
**状态**：DRAFT
**日期**：2026-06-23
**依赖**：requirements_spec.md (APPROVED), user_stories.md (APPROVED)

---

# 模块详细设计 — v1.4.1 三恒知识库 RAG 图片引用回溯

**文档编号**：ARCH-MOD-RAG-v141-001
**项目名称**：FreeArk 三恒知识库 RAG 图片引用回溯（v1.4.1_rag_image_citation）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-23
**输入文档**：ARCH-DES-RAG-v141-001 (DRAFT)，ARCH-MOD-RAG-v140-001 (APPROVED，基线参考)

---

## 模块总览

| MOD-ID | 模块名 | 变更类型 | 层级 | 职责摘要 | 依赖于 |
|--------|--------|---------|------|---------|--------|
| MOD-141-01 | models_rag.py | 修改 | 模型层 | 新增 RagImage 模型；RagChunk 新增 image FK | Django ORM |
| MOD-141-02 | 0039_rag_image.py | 新增 | 迁移层 | 创建 api_ragimage 表；RagChunk 新增 image 字段 | MOD-141-01 |
| MOD-141-03 | rag_service.py | 修改 | 服务层 | 图片持久化、向量缓存扩展、检索结果新增 image_id | MOD-141-01 |
| MOD-141-04 | fa_tools.py | 修改 | 工具层 | ContextVar side-channel；get_last_search_images() | MOD-141-03 |
| MOD-141-05 | orchestrator.py | 修改 | 编排层 | State 新增字段；_expert 提取；_aggregate 汇聚去重 | MOD-141-04 |
| MOD-141-06 | adapter.py | 修改 | 适配层 | 从最终 State 取 related_images 注入流 | MOD-141-05 |
| MOD-141-07 | consumers.py | 修改 | 消费者层 | _pump 接收 related_images；_finalize_turn 附加到 stream_end | MOD-141-06 |
| MOD-141-08 | views_rag.py | 修改 | API 层 | 新增 RagImageView（取图端点） | MOD-141-01 |
| MOD-141-09 | urls.py | 修改 | 路由层 | 注册取图路由 | MOD-141-08 |
| MOD-141-10 | ChatView.vue | 修改 | 前端层 | stream_end 处理；气泡图片引用区渲染 | MOD-141-11 |
| MOD-141-11 | api.js | 修改 | 前端层 | 新增 fetchRagImage() helper | — |

依赖关系图（无循环依赖，已验证）：

```
MOD-141-01（models_rag.py）
  ↑ 被依赖
MOD-141-02（0039_rag_image.py）
MOD-141-03（rag_service.py）
  ↑
MOD-141-04（fa_tools.py）
  ↑
MOD-141-05（orchestrator.py）
  ↑
MOD-141-06（adapter.py）
  ↑
MOD-141-07（consumers.py）

MOD-141-01 → MOD-141-08（views_rag.py）
MOD-141-08 → MOD-141-09（urls.py）

MOD-141-11（api.js）← MOD-141-10（ChatView.vue）依赖
```

循环依赖检查：MOD-141-01 ← MOD-141-03 ← MOD-141-04 ← MOD-141-05 ← MOD-141-06 ← MOD-141-07，均为单向依赖。前端模块间 MOD-141-10 → MOD-141-11，单向。无循环。

---

## MOD-141-01：models_rag.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/models_rag.py`
**变更类型**：修改（在 v1.4.0 基础上新增 RagImage 模型；RagChunk 新增字段）
**覆盖需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-006, REQ-NFR-001

### 新增：RagImage 模型

```python
# 类型注解（含字段约束说明）

class RagImage(models.Model):
    """三恒知识库图片存储（DB BLOB 方案，ADR-IC-001）。
    每条记录对应文档中的一张图片，图片字节以 BinaryField 直接存入主库。
    文档删除时 CASCADE 自动清理（REQ-FUNC-006）。
    """
    document: RagDocument       # FK(RagDocument, on_delete=CASCADE, related_name='images')
    image_index: int            # IntegerField — 同文档内图片序号（0 起，便于日志定位）
    page_or_section: str        # CharField(max_length=100, blank=True) — 来源页/节
    image_format: str           # CharField(max_length=20) — 'png'/'jpeg'/'other'
    image_data: bytes           # BinaryField — 原始图片字节（BLOB，不超过 10MB）
    file_size: int              # IntegerField — 字节大小（冗余存储，便于监控查询）
    created_at: datetime        # DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_ragimage'   # 显式声明，对齐 api_ragdocument / api_ragchunk 惯例
        indexes = [
            models.Index(fields=['document'], name='ragimage_document_idx'),
        ]
```

**关键约束**：
- `on_delete=CASCADE`：文档删除 → 图片行自动删除，无孤立数据（REQ-FUNC-006）
- `image_data` 为 `BinaryField`：存储 `bytes`，无 max_length（Django BinaryField 默认无限制，大小由应用层的 `MAX_IMAGE_BYTES=10MB` 约束）
- `file_size` 冗余存储：查总存储量时 `SELECT SUM(file_size)` 不需要读 BLOB 列

### 修改：RagChunk 新增字段

```python
# 在现有 RagChunk 类中追加（保持现有字段顺序不变，REQ-NFR-005）：

class RagChunk(models.Model):
    # ── 现有字段（v1.4.0，不变）──────────────────────────────
    document: RagDocument       # FK(RagDocument, on_delete=CASCADE)
    chunk_index: int            # IntegerField
    content: str                # TextField
    embedding: bytes            # BinaryField — numpy float32 tobytes()
    page_or_section: str        # CharField(max_length=100, blank=True)
    is_image_ocr: bool          # BooleanField(default=False)
    created_at: datetime        # DateTimeField(auto_now_add=True)

    # ── 新增字段（v1.4.1）──────────────────────────────────────
    image: RagImage | None      # FK(RagImage, null=True, blank=True, on_delete=SET_NULL,
                                #    related_name='chunks')
                                # null=True: 纯文字 chunk 无关联图片
                                # on_delete=SET_NULL: 图片独立删除时 chunk 保留（防御性设计）
```

**关键约束**：
- `on_delete=SET_NULL`（非 CASCADE）：图片删除时 chunk 不删除，`image_id` 置 null——但业务上图片仅通过文档 CASCADE 删除，此路径为防御
- 现有 chunk 升级迁移后 `image_id=NULL`（向后兼容，REQ-NFR-005）

---

## MOD-141-02：0039_rag_image.py（Migration）

**文件路径**：`FreeArkWeb/backend/freearkweb/api/migrations/0039_rag_image.py`
**变更类型**：新增（手写，不运行 makemigrations，C-006）
**覆盖需求**：REQ-NFR-005（手写 migration，遵循现有风格）

### Migration 骨架（完整 operations）

```python
# 关键声明结构（实现时填入完整字段定义）

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0038_chatsession_title'),   # 项目硬约束：必须依赖 0038
    ]

    operations = [
        # Step 1：创建 RagImage 表
        migrations.CreateModel(
            name='RagImage',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID')),
                ('document', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='images',
                    to='api.ragdocument')),
                ('image_index', models.IntegerField(
                    help_text='同文档内图片序号（0 起）')),
                ('page_or_section', models.CharField(
                    blank=True, max_length=100)),
                ('image_format', models.CharField(
                    max_length=20,
                    help_text="图片格式：'png'/'jpeg'/'other'")),
                ('image_data', models.BinaryField(
                    help_text='原始图片字节（DB BLOB，上限 10MB）')),
                ('file_size', models.IntegerField(
                    help_text='字节大小，冗余存储用于监控')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'api_ragimage',
            },
        ),

        # Step 2：为 RagImage.document 添加索引
        migrations.AddIndex(
            model_name='ragimage',
            index=models.Index(
                fields=['document'],
                name='ragimage_document_idx'),
        ),

        # Step 3：RagChunk 新增 image FK（null=True，向后兼容）
        migrations.AddField(
            model_name='ragchunk',
            name='image',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='chunks',
                to='api.ragimage'),
        ),
    ]
```

**迁移执行顺序**：
1. 创建 `api_ragimage` 表（Step 1）
2. 创建 `ragimage_document_idx` 索引（Step 2）
3. `api_ragchunk` 追加 `image_id` 可空列（Step 3，现有行自动为 NULL，无数据迁移）

**零停机兼容性**：
- Step 3 在现有 `api_ragchunk` 表追加可空列，MySQL/SQLite 均支持在线 DDL（`ADD COLUMN NULL`），不锁表（MySQL 5.6+），不需要应用停机

---

## MOD-141-03：rag_service.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/rag_service.py`
**变更类型**：修改（在 v1.4.0 基础上扩展，不改动现有接口签名）
**覆盖需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-NFR-001, REQ-NFR-002, REQ-NFR-003

### 3.1 新增常量和 ParsedChunk 扩展

```python
# 新增常量（在文件顶部与现有常量一起）
MAX_IMAGE_BYTES: int = 10 * 1024 * 1024   # 10 MB，OQ-IC-002 决策

# ParsedChunk 扩展（在现有 dataclass 基础上新增字段）
@dataclass
class ParsedChunk:
    content: str
    page_or_section: str
    is_image_ocr: bool = False
    # ── v1.4.1 新增 ──────────────────────────────────────────────────────────
    img_bytes: bytes | None = None   # 原始图片字节（仅 is_image_ocr=True 时有值）
    img_format: str = 'png'          # 图片格式（'png'/'jpeg'/'other'）
    img_size: int = 0                # 字节大小（冗余，避免重复 len() 调用）
```

### 3.2 RagParser 修改

**新增内部方法 `_try_save_image_bytes()`**：提取图片字节时执行大小校验，返回 `(img_bytes, img_format)` 或 `(None, '')` 。

```python
# IFC-141-301
@staticmethod
def _try_save_image_bytes(
    img_bytes: bytes,
    img_format: str,
    source_hint: str,
) -> tuple[bytes | None, str]:
    """
    校验图片字节是否满足存储条件，通过则返回原字节，否则 WARNING + 返回 (None, '')。

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
```

**`parse_docx()` 修改**：在现有图片 OCR 逻辑中，提取 `img_bytes` 后附加到 `ParsedChunk`：

```python
# 现有逻辑（v1.4.0 基线，不改变 OCR 分支结构）：
for shape_idx, rel in enumerate(doc.part.rels.values()):
    if "image" in rel.target_ref:
        img_bytes_raw = rel.target_part.blob
        # ── v1.4.1 新增 ──────────────────────────────────────────────────
        img_format = _detect_image_format(img_bytes_raw)   # 新增辅助函数
        saved_bytes, saved_fmt = RagParser._try_save_image_bytes(
            img_bytes_raw, img_format, f"图片 {shape_idx + 1}")
        # ─────────────────────────────────────────────────────────────────
        ocr_text = self._ocr_image(img_bytes_raw)   # 不变：无论能否存储都 OCR
        if ocr_text:
            for chunk in self._split_text(ocr_text, f"图片 {shape_idx + 1}"):
                # ── v1.4.1：同一图片的所有 split_text chunk 共享同一份 img_bytes
                chunk.is_image_ocr = True
                chunk.img_bytes = saved_bytes    # None 表示超限或提取失败
                chunk.img_format = saved_fmt
                chunk.img_size = len(saved_bytes) if saved_bytes else 0
                chunks.append(chunk)
        # ── v1.4.1：即使 OCR 无文字，图片仍存储（US-IC-005 AC-IC-005-03）
        elif saved_bytes is not None:
            # 无 OCR 文字但有图片：创建一个无文字内容的 chunk 承载图片引用
            # 不加入文字 chunk，仅在 RagIngestor 存图时用到
            # 注：此处设计为在 RagIngestor 中处理，不在 ParsedChunk 中表达
            pass
```

**`parse_pdf()` 修改**：同上逻辑，针对 XObject 图片（路径1/2）和整页栅格化（路径3）：

```python
# 路径 1/2：XObject 图片 OCR
for img_idx, img_info in enumerate(page.get_images(full=True)):
    try:
        xref = img_info[0]
        base_image = doc.extract_image(xref)
        img_bytes_raw = base_image["image"]
        img_format = base_image.get("ext", "png")          # PyMuPDF 提供格式
        saved_bytes, saved_fmt = RagParser._try_save_image_bytes(
            img_bytes_raw, img_format,
            f"第 {page_num} 页 图片{img_idx + 1}")
    except Exception as e:
        logger.warning("图片提取失败，跳过（文档继续入库）: %s", e)   # fail-open
        saved_bytes, saved_fmt = None, ''
    ocr_text = self._ocr_image(img_bytes_raw) if img_bytes_raw else ""
    if ocr_text:
        for chunk in self._split_text(ocr_text, f"第 {page_num} 页 图片{img_idx + 1}"):
            chunk.is_image_ocr = True
            chunk.img_bytes = saved_bytes
            chunk.img_format = saved_fmt
            chunk.img_size = len(saved_bytes) if saved_bytes else 0
            chunks.append(chunk)

# 路径 3：扫描件整页栅格化（OQ-IC-003：存储，受 10MB 上限约束）
page_mat = fitz.Matrix(150/72, 150/72)
png_bytes = page.get_pixmap(matrix=page_mat).tobytes("png")
saved_bytes, saved_fmt = RagParser._try_save_image_bytes(
    png_bytes, 'png', f"第 {page_num} 页 扫描件")
ocr_text = self._ocr_image(png_bytes)
if ocr_text:
    for chunk in self._split_text(ocr_text, f"第 {page_num} 页 扫描件"):
        chunk.is_image_ocr = True
        chunk.img_bytes = saved_bytes   # 可能为 None（若扫描件大图超 10MB）
        chunk.img_format = saved_fmt
        chunk.img_size = len(saved_bytes) if saved_bytes else 0
        chunks.append(chunk)
```

**新增辅助函数 `_detect_image_format()`**：

```python
# IFC-141-302
def _detect_image_format(img_bytes: bytes) -> str:
    """
    根据文件头字节检测图片格式。

    参数：img_bytes — 图片原始字节
    返回：'png' | 'jpeg' | 'other'

    检测规则：
      - PNG: 首 8 字节 == b'\\x89PNG\\r\\n\\x1a\\n'
      - JPEG: 首 2 字节 == b'\\xff\\xd8'
      - 其他：'other'
    """
```

### 3.3 RagIngestor 修改

**`ingest()` 方法新增图片存储步骤**，在写入 `RagChunk` 之前先批量写入 `RagImage`，建立映射关系：

```python
# IFC-141-303：RagIngestor.ingest() 核心变更（在 DB 写入阶段）

# 在步骤 4（写入 DB）前，新增步骤 4a：写入 RagImage
# ── v1.4.1 Step 4a：写入 RagImage，建立 chunk.image_id 映射 ──────────
from .models_rag import RagImage

# 收集所有有图片字节的 chunk，去重（同一张图片可能对应多个 chunk）
# 去重 key：(page_or_section, img_bytes 的前 64 字节 hash)  避免大 bytes 直接做 key
img_key_to_rag_image: dict[str, RagImage] = {}   # key → 已写入的 RagImage 对象

image_write_errors = 0
for chunk_data_pair in all_chunks_data:
    chunk, vec = chunk_data_pair
    if chunk.img_bytes is None:
        continue   # 无图片，跳过
    # 生成去重 key：用 page_or_section + 前 64 字节 hash（避免同一文档多次提取同一图片）
    import hashlib
    img_key = hashlib.md5(chunk.img_bytes[:256]).hexdigest()   # 快速 hash，非密码学用途
    if img_key in img_key_to_rag_image:
        continue   # 已写入，跳过（同一图片的多个 OCR chunk 共享一个 RagImage 行）
    try:
        rag_image = RagImage.objects.create(
            document_id=doc_id,
            image_index=len(img_key_to_rag_image),
            page_or_section=chunk.page_or_section,
            image_format=chunk.img_format,
            image_data=chunk.img_bytes,
            file_size=chunk.img_size,
        )
        img_key_to_rag_image[img_key] = rag_image
    except Exception as e:
        image_write_errors += 1
        logger.warning(
            "文档 %s 图片写入失败（跳过，文档继续入库）: %s", doc_id, e)
        # fail-open：图片写入失败不阻断文档入库（REQ-NFR-003、C-008）

# 步骤 4：写入 RagChunk（新增 image_id 字段赋值）
chunk_objs = []
for idx, (chunk, vec) in enumerate(all_chunks_data):
    # 查找本 chunk 对应的 RagImage（按 img_bytes hash 匹配）
    image_obj = None
    if chunk.img_bytes is not None:
        import hashlib
        img_key = hashlib.md5(chunk.img_bytes[:256]).hexdigest()
        image_obj = img_key_to_rag_image.get(img_key)   # 可能为 None（写入失败时）
    chunk_objs.append(RagChunk(
        document_id=doc_id,
        chunk_index=idx,
        content=chunk.content,
        embedding=vec.tobytes(),
        page_or_section=chunk.page_or_section,
        is_image_ocr=chunk.is_image_ocr,
        image=image_obj,    # v1.4.1 新增：可为 None（纯文字 chunk 或图片写入失败）
    ))
RagChunk.objects.bulk_create(chunk_objs)

if image_write_errors > 0:
    logger.warning(
        "文档 %s 共 %d 张图片写入失败，对应 chunk 的 image_id 为 None",
        doc_id, image_write_errors)
```

### 3.4 RagVectorCache.load() 修改

```python
# IFC-141-304：load() 方法中 meta dict 新增 image_id 字段

# 查询变更：需要 select_related('image') 以避免 N+1
chunks = (RagChunk.objects
          .filter(document__status='indexed')
          .select_related('document', 'image')   # v1.4.1 新增 'image'
          .order_by('id'))

# meta dict 构造变更（在现有字段之后追加，不改变现有字段顺序，REQ-NFR-005）：
meta.append({
    'doc_name': c.document.file_name,
    'source': c.page_or_section,
    'is_image_ocr': c.is_image_ocr,
    'content': c.content,
    'image_id': c.image_id,    # v1.4.1 新增：int | None（整型 FK id，不存图片字节）
})
```

**约束**：`image_id` 存整型 id（`c.image_id`，Django 的 `_id` 属性，无需 JOIN 读图片行），不存图片字节（C-007、REQ-NFR-001）。

### 3.5 RagVectorCache.search() 修改

```python
# IFC-141-305：search() 返回的每个 result dict 新增 image_id

results.append({
    'content': m['content'],
    'source': f"{m['doc_name']} · {m['source']}",
    'is_image_ocr': m['is_image_ocr'],
    'score': float(scores[i]),
    'image_id': m.get('image_id'),    # v1.4.1 新增：int | None
})
```

### 3.6 search_rag() 无需修改

`search_rag()` 调用 `rag_vector_cache.search()`，search() 的返回值已包含 `image_id`，search_rag() 的返回结构 `{"chunks": results, "degraded": bool}` 自动携带了 `image_id`，无需修改 search_rag() 本身。

---

## MOD-141-04：fa_tools.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py`
**变更类型**：修改（新增 ContextVar、内部辅助函数；`search_sanheng_knowledge` `@tool` 内部逻辑扩展）
**覆盖需求**：REQ-FUNC-003, C-003（LLM 不见 image_id）

### 新增：ContextVar 和辅助函数

```python
import contextvars

# ── v1.4.1：side-channel ContextVar，用于向 orchestrator._expert 传递 related_images ──
# 每个 asyncio Task 有独立的 context 副本，天然线程安全（ADR-IC-002 选用方案 B）
_last_search_images_var: contextvars.ContextVar[list] = contextvars.ContextVar(
    '_last_search_images_var', default=[])

# IFC-141-401
def get_last_search_images() -> list:
    """
    读取并清空本 Task context 中最近一次 search_rag() 产生的 related_images 列表。

    调用方：orchestrator._expert（在调用 search_sanheng_knowledge tool 后）
    返回：list[dict]，格式为 [{"image_id": int, "source": str}, ...]
          若无图片命中，返回 []

    副作用：清空 ContextVar（防止跨 tool-call 轮次的数据残留）
    """
    images = _last_search_images_var.get([])
    _last_search_images_var.set([])
    return images
```

### 修改：search_sanheng_knowledge

```python
# IFC-141-402：search_sanheng_knowledge 内部逻辑扩展
# @tool 签名、返回类型（str）、docstring 均不变（LLM schema 不变）

@tool
def search_sanheng_knowledge(query: str) -> str:
    """在三恒知识库中检索与 query 相关的文档片段，用于辅助原理/参数/故障码解答。
    返回最相关的 chunk 文本列表及来源；库为空或不可达时返回说明文字（不报错）。"""
    try:
        from django.conf import settings
        from api.rag_service import search_rag
        k = getattr(settings, 'RAG_TOP_K', 5)
        threshold = getattr(settings, 'RAG_SCORE_THRESHOLD', 0.3)
        result = search_rag(query, k=k, threshold=threshold)
    except Exception as e:
        logger.warning("fa_tools: search_sanheng_knowledge 异常（降级）: %s", e)
        _last_search_images_var.set([])   # 清空，防止残留
        return "[知识库暂时不可达，以下为通用知识参考。degraded=true]"

    if result.get('degraded'):
        _last_search_images_var.set([])
        return "[知识库暂时不可达，以下为通用知识参考。degraded=true]"

    chunks = result.get('chunks', [])
    if not chunks:
        _last_search_images_var.set([])
        return "[知识库中未找到与该问题相关的内容]"

    # ── v1.4.1 side-channel：收集 related_images，不进入返回的 str ──────
    related_images = []
    seen_image_ids: set[int] = set()
    for c in chunks:
        image_id = c.get('image_id')
        if image_id is not None and image_id not in seen_image_ids:
            seen_image_ids.add(image_id)
            related_images.append({
                "image_id": image_id,
                "source": c.get('source', ''),
            })
    _last_search_images_var.set(related_images)   # 写入 ContextVar，供 _expert 读取
    # ────────────────────────────────────────────────────────────────────────

    # 以下返回给 LLM 的文本不含 image_id（C-003 防幻觉，不变）
    lines = [f"[检索到 {len(chunks)} 条相关内容]"]
    for i, c in enumerate(chunks, 1):
        src_note = "（图片OCR）" if c.get('is_image_ocr') else ""
        content_preview = (c.get('content') or '')[:400]
        lines.append(
            f"\n[{i}] 来源: {c.get('source', '未知')}{src_note}\n    {content_preview}"
        )
    return "\n".join(lines)
```

---

## MOD-141-05：orchestrator.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py`
**变更类型**：修改（State 新增字段；`_expert` 调用工具后读取 side-channel；`_aggregate` 汇聚去重）
**覆盖需求**：REQ-FUNC-003, REQ-FUNC-005（调用链中间层）

### State 新增字段

```python
# IFC-141-501：State TypedDict 新增 related_images 字段

class State(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: List[Tuple[str, str]]
    expert_results: Annotated[List[dict], operator.add]
    name: str
    query: str
    # ── v1.4.1 新增 ──────────────────────────────────────────────────────
    related_images: List[dict]
    # 不使用 operator.add reducer：由 _aggregate 统一收集后一次性赋值
    # 格式：[{"image_id": int, "source": str}, ...]（已去重）
```

### _expert 修改

```python
# IFC-141-502：_expert 节点在处理 sanheng-knowledge 工具调用后提取 related_images

# 在现有 _expert() 方法的工具调用循环中，对 sanheng-knowledge 专家专项处理：
# （仅在 name == "sanheng-knowledge" 或工具名为 "search_sanheng_knowledge" 时触发）

from .fa_tools import get_last_search_images   # v1.4.1 新增 import

# 在工具调用循环内（现有结构）：
accumulated_images: list = []   # 收集本 expert 执行期间所有命中的图片
for tc in tcs:
    if allow_deleg and tc["name"] in READ_DELEGATION_NAMES:
        out, log = await self._handle_read_delegation(...)
        delegations.append(log)
    else:
        t = tool_map.get(tc["name"])
        out = await t.ainvoke(tc["args"]) if t else {"error": "no tool"}
        # ── v1.4.1：仅对 sanheng-knowledge 工具读取 side-channel ─────
        if tc["name"] == "search_sanheng_knowledge":
            imgs = get_last_search_images()   # 读取并清零 ContextVar
            accumulated_images.extend(imgs)
        # ──────────────────────────────────────────────────────────────
    msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))

# expert_results 返回值新增 related_images（工具循环结束后汇总）：
# （位于现有 return {"expert_results": [...]} 之前）
# 对 accumulated_images 做最终去重（同一专家多轮工具调用可能重复命中）
seen_ids: set[int] = set()
deduped_images: list = []
for img in accumulated_images:
    if img["image_id"] not in seen_ids:
        seen_ids.add(img["image_id"])
        deduped_images.append(img)

return {"expert_results": [
    {
        "expert": name,
        "answer": ai.content,
        "delegations": delegations,
        "related_images": deduped_images,   # v1.4.1 新增
    }
]}
```

### _aggregate 修改

```python
# IFC-141-503：_aggregate 节点汇聚所有专家的 related_images，全局去重后写入 State

async def _aggregate(self, state: State):
    results = [r for r in state.get("expert_results", []) if "answer" in r]
    if not results:
        final = "未获得有效答复，请重试。"
    elif len(results) == 1:
        final = results[0]["answer"]
    else:
        # 多专家融合（现有逻辑不变）
        digest = "\n".join(r["answer"] for r in results)
        ai = await self.llm.ainvoke([...])
        final = ai.content

    # ── v1.4.1：全局去重 related_images ──────────────────────────────
    all_images: list = []
    for r in results:
        all_images.extend(r.get("related_images", []))
    seen_ids: set[int] = set()
    unique_images: list = []
    for img in all_images:
        if img["image_id"] not in seen_ids:
            seen_ids.add(img["image_id"])
            unique_images.append(img)
    # ─────────────────────────────────────────────────────────────────

    return {
        "messages": [AIMessage(content=final)],
        "related_images": unique_images,   # v1.4.1 新增 State 字段
    }
```

---

## MOD-141-06：adapter.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/adapter.py`
**变更类型**：修改（`_drive()` 函数在 astream 结束后从 State 取 related_images，作为新 kind 流出）
**覆盖需求**：REQ-FUNC-005（调用链传递 related_images 到 consumer）

### _drive() 修改

```python
# IFC-141-601：_drive() 函数结尾新增 related_images yield

# 在现有 astream 循环结束后、seen_any 判断之前，新增：

# ── v1.4.1：从最终 State 取 related_images，作为独立 kind yield 给 consumer ──
# 不在 astream 流中取（aggregate 节点的 updates 不含 State diff），
# 而是在 astream 完全结束后从快照读取（确保 aggregate 已执行完）
if not interrupted:
    try:
        snap = await orch.graph.aget_state(config)
        related_images = (
            (snap.values or {}).get("related_images", []) if snap else []
        )
        if related_images:
            yield ("related_images",
                   json.dumps(related_images, ensure_ascii=False))
    except Exception as e:   # noqa: BLE001 — 图片引用提取失败不影响主流程
        logger.warning("_drive: 提取 related_images 失败（非致命）: %s", e)
# ─────────────────────────────────────────────────────────────────────────

# 现有 seen_any 判断（不变）：
if not seen_any and not interrupted:
    snap = await orch.graph.aget_state(config)
    ...
```

**注意**：`aget_state` 被调用两次（related_images 取一次，非流式兜底取一次）。在实现时可合并为一次调用，共享 snap 对象，减少 DB round-trip。

---

## MOD-141-07：consumers.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/consumers.py`
**变更类型**：修改（最小化：新增实例变量；`_pump` 新增 kind 处理；`_finalize_turn` 新增参数）
**覆盖需求**：REQ-FUNC-005（stream_end 附加 related_images）

**WS 验证要求**：任何 consumers.py 改动须本地真 Redis 验 WS 收发（不可仅用 InMemoryChannelLayer）。

### connect() 修改

```python
# IFC-141-701：新增实例变量初始化（在现有 connect() 变量初始化块末尾追加）

self._related_images: list = []   # v1.4.1：存储本轮 related_images（实时，不持久化）
```

### _pump() 修改

```python
# IFC-141-702：_pump() 新增 'related_images' kind 处理

# 在现有 kind 处理链中追加（elif 链末尾，elif kind == 'status' 之后）：

elif kind == 'related_images':
    try:
        self._related_images = json.loads(text) or []
    except (ValueError, TypeError):
        self._related_images = []
        logger.warning(
            "ChatConsumer._pump: related_images 解析失败，忽略: %s", text[:200])
    # 不 yield 给前端（通过 _finalize_turn 的 stream_end 统一发送）
```

### _handle_chat() 修改

```python
# IFC-141-703：_handle_chat() 在 _finalize_turn 调用前重置 _related_images，
# 并在调用时传递

# 在 _pump() 返回后（现有 _finalize_turn 调用之前）：
# ── v1.4.1：取出本轮收集的 related_images，并立即重置（防下轮残留） ──
related_images = self._related_images
self._related_images = []   # 重置
# ────────────────────────────────────────────────────────────────────

await self._finalize_turn(accumulated_content, related_images=related_images)
```

### _finalize_turn() 修改

```python
# IFC-141-704：_finalize_turn() 新增 related_images 参数
# 签名变更（向后兼容：默认值 None，现有调用点无需修改）：

async def _finalize_turn(
    self,
    accumulated_content: str,
    related_images: list | None = None,   # v1.4.1 新增
):
    """结束一轮：发 stream_end（新增 related_images 字段），写入 assistant 记录。

    related_images 格式：[{"image_id": int, "source": str}, ...] 或 []
    OQ-IC-004 决策：related_images 不持久化到 chat_memory.append_message
    """
    # 构造 stream_end 载荷
    payload: dict = {'type': 'stream_end'}
    if related_images:
        payload['related_images'] = related_images   # 可选字段，空数组时不加
    await self.send(json.dumps(payload))

    # DB 写入（不变，不含 related_images）
    if self.chat_session is not None and accumulated_content:
        try:
            await sync_to_async(chat_memory.append_message)(
                self.chat_session, 'assistant', accumulated_content,
            )
            self._pending_assistant_content = ''
        except Exception as exc:
            self._pending_assistant_content = accumulated_content
            logger.error(
                'ChatConsumer: append_message(assistant) 失败，保存 pending: %s', exc)
    else:
        self._pending_assistant_content = ''
```

---

## MOD-141-08：views_rag.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/views_rag.py`
**变更类型**：修改（新增 RagImageView 类，其余端点不变）
**覆盖需求**：REQ-FUNC-004, REQ-NFR-004

### 新增：RagImageView

```python
# IFC-141-801：RagImageView 接口规格

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from .models_rag import RagImage

# Content-Type 映射
_FORMAT_TO_CONTENT_TYPE: dict[str, str] = {
    'png': 'image/png',
    'jpeg': 'image/jpeg',
    'jpg': 'image/jpeg',
}

class RagImageView(APIView):
    """
    GET /api/rag/images/{image_id}/
    权限：IsAuthenticated（Bearer Token，所有已登录用户，REQ-NFR-004）
    响应：200 + Content-Type: image/{format} + Content-Disposition: inline + 图片字节流
    404：图片不存在（不暴露内部错误，安全降级，REQ-NFR-003）

    约束：
    - 取图直接查 DB，不经 RagVectorCache（US-IC-008）
    - Content-Disposition: inline（REQ-NFR-004，防误解为可执行文件）
    - 不在 HTTP 响应中泄露 file_size、document_id 等内部字段
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, image_id: int) -> HttpResponse:
        """
        参数：
          image_id — 路径参数（int）

        返回值：
          HttpResponse(image_bytes, content_type=..., status=200)
          HttpResponse(status=404)  — 图片不存在

        内部逻辑：
          1. RagImage.objects.only('image_data', 'image_format').get(id=image_id)
             （only() 仅取必要字段，避免 ORM 拉取 document FK 等无用数据）
          2. 若 DoesNotExist → 返回 404
          3. 构造响应：
             content_type = _FORMAT_TO_CONTENT_TYPE.get(image_format, 'application/octet-stream')
             response = HttpResponse(image_data, content_type=content_type)
             response['Content-Disposition'] = 'inline'
             response['Cache-Control'] = 'no-store'
          4. 返回 response
        """
```

---

## MOD-141-09：urls.py 修改

**文件路径**：`FreeArkWeb/backend/freearkweb/api/urls.py`
**变更类型**：修改（追加取图路由，不改动现有路由）
**覆盖需求**：REQ-FUNC-004

### 路由新增

```python
# IFC-141-901：追加路由（在现有 rag_router.urls 注册之后）

from django.urls import path
from . import views_rag

# 追加到 urlpatterns（不改动现有路由）：
urlpatterns += [
    path('rag/images/<int:image_id>/',
         views_rag.RagImageView.as_view(),
         name='rag-image-detail'),
]
```

完整路径：`/api/rag/images/{image_id}/`（`api/` 前缀由 `freearkweb/urls.py` 的 `include('api.urls')` 提供）

---

## MOD-141-10：ChatView.vue 修改

**文件路径**：`FreeArkWeb/frontend/src/views/ChatView.vue`
**变更类型**：修改（新增 `stream_end` 中 `related_images` 处理；气泡新增图片引用区）
**覆盖需求**：REQ-FUNC-005, REQ-NFR-003（降级展示），US-IC-001~003, US-IC-007

### 组件状态扩展

```javascript
// IFC-141-1001：在现有 messages 数组的每个 message 对象中新增 relatedImages 字段

// 每条 assistant message 结构扩展：
// {
//   role: 'assistant',
//   content: str,
//   relatedImages: [{image_id: number, source: string}] | []   // v1.4.1 新增
// }
```

### stream_end 处理修改

```javascript
// IFC-141-1002：在现有 stream_end 处理处附加 relatedImages

// 在 WS message 处理函数中，stream_end case 扩展：
case 'stream_end': {
    // 现有逻辑（不变）：finalize assistant message content
    // ...

    // v1.4.1 新增：将 related_images 附加到当前 assistant message
    const related = data.related_images || []   // 缺失时等同空数组（US-IC-007）
    if (currentAssistantMsg) {
        currentAssistantMsg.relatedImages = related   // 可为 []
    }
    break
}
```

### 气泡模板修改

```html
<!-- IFC-141-1003：在现有 .chat-bubble 内，文字渲染块之后追加图片引用区 -->

<!-- 图片引用区：v-if 条件为 false 时不挂载 DOM（US-IC-007） -->
<div
  v-if="msg.relatedImages && msg.relatedImages.length > 0"
  class="chat-image-citations"
>
  <!-- 缩略图列表 -->
  <el-image
    v-for="img in msg.relatedImages"
    :key="img.image_id"
    :src="getImageUrl(img.image_id)"
    :preview-src-list="msg.relatedImages.map(i => getImageUrl(i.image_id))"
    fit="cover"
    style="width: 160px; height: 120px; margin: 4px; cursor: pointer;"
    loading="lazy"
  >
    <!-- 加载失败占位（US-IC-003 AC-IC-003-01） -->
    <template #error>
      <div class="image-error-placeholder">
        <el-text size="small" type="info">图片暂时无法显示</el-text>
      </div>
    </template>
  </el-image>
</div>
```

### 方法新增

```javascript
// IFC-141-1004：getImageUrl() helper

// 在 ChatView.vue 的 methods 中新增：
getImageUrl(imageId) {
    // 构造取图 URL，不走 api.js（因为 el-image 的 src 属性是直接由浏览器发 GET 请求）
    // 注意：el-image 直接使用 src 属性，不走 axios，因此需要额外的鉴权处理
    // 方案：在 el-image 组件前先通过 api.js 获取 Blob URL（见下方 loadImageBlob）
    return `/api/rag/images/${imageId}/`
    // 但此 URL 需要 Authorization 头，直接作为 src 不带头——
    // 改用 loadImageBlob 获取 Object URL（见 IFC-141-1005）
}
```

**鉴权说明**：`el-image` 的 `src` 属性是浏览器原生 `<img>` 标签 GET 请求，不携带 `Authorization: Bearer` 头，只携带 cookie（sessionid）。

由于 FreeArk 当前的 DRF 认证包含 `TokenAuthentication` 和 `SessionAuthentication`，而取图端点为 `IsAuthenticated`，若用户通过 SPA 登录（Bearer Token），`<img src>` 方式无法携带 Token，会 401 失败。

**正确方案（IFC-141-1005）**：通过 `api.js` 获取 Blob URL，赋值给 `el-image` 的 `src`：

```javascript
// IFC-141-1005：loadImageBlob() — 通过 api.js 鉴权取图，获取 Blob URL
// 在 msg.relatedImages 赋值后，为每张图片预加载 Blob URL

import api from '@/api'   // 必须：走 api.js（C-004，前端鉴权陷阱约束）

async loadImageBlobUrl(imageId) {
    try {
        // api.js 封装的 Bearer Token 请求
        const response = await api.get(`/rag/images/${imageId}/`, {
            responseType: 'blob',
        })
        return URL.createObjectURL(response.data)
    } catch (e) {
        logger.warn('取图失败:', imageId, e)
        return null   // null 触发 el-image 的 error slot
    }
},

// 在 stream_end 处理中，赋值 relatedImages 后批量预加载：
async function finalizeRelatedImages(relatedImages, message) {
    const imageUrls = {}
    await Promise.all(relatedImages.map(async (img) => {
        const blobUrl = await loadImageBlobUrl(img.image_id)
        imageUrls[img.image_id] = blobUrl   // null 表示加载失败
    }))
    message.imageUrls = imageUrls
}
```

**组件销毁时**需要 `URL.revokeObjectURL()` 释放 Blob URL，防止内存泄漏：

```javascript
onUnmounted(() => {
    // 释放所有 Blob URL
    for (const msg of messages.value) {
        if (msg.imageUrls) {
            Object.values(msg.imageUrls).forEach(url => {
                if (url) URL.revokeObjectURL(url)
            })
        }
    }
})
```

---

## MOD-141-11：api.js 修改

**文件路径**：`FreeArkWeb/frontend/src/utils/api.js`（或项目实际路径）
**变更类型**：修改（新增 fetchRagImage helper）
**覆盖需求**：REQ-FUNC-004（前端取图必须走 api.js，C-004）

### 新增：fetchRagImage

```javascript
// IFC-141-1101：fetchRagImage(imageId) — 鉴权取图 helper

/**
 * 获取知识库图片字节（Blob）。
 *
 * 调用方：ChatView.vue（loadImageBlobUrl）
 * 返回：axios Response，response.data 为 Blob
 * 错误：HTTP 401（未鉴权）/ 404（图片不存在）/ 5xx
 *
 * 约束：
 *   - 必须通过本 helper，禁止裸 `import axios from 'axios'`（C-004）
 *   - Bearer Token 由 api 实例 interceptor 自动注入
 *
 * @param {number} imageId — RagImage.id
 * @returns {Promise<AxiosResponse>}
 */
export async function fetchRagImage(imageId) {
    return api.get(`/rag/images/${imageId}/`, {
        responseType: 'blob',
    })
}
```

---

## 接口汇总（所有模块间调用）

| 调用方 | 被调用方 | 接口 ID | 接口签名 | 类型 |
|--------|---------|---------|---------|------|
| RagParser | RagParser._try_save_image_bytes | IFC-141-301 | `(bytes, str, str) → (bytes\|None, str)` | 同步 |
| RagParser | _detect_image_format | IFC-141-302 | `(bytes) → str` | 同步 |
| RagIngestor.ingest | RagImage.objects.create | IFC-141-303 | ORM 写入 | 同步（DB） |
| RagVectorCache.load | RagChunk.select_related('image') | IFC-141-304 | ORM 读取 | 同步（DB） |
| RagVectorCache.search | — | IFC-141-305 | 返回 `image_id` 追加到 chunk dict | 同步 |
| orchestrator._expert | fa_tools.get_last_search_images | IFC-141-401 | `() → list[dict]` | 同步（ContextVar） |
| fa_tools.search_sanheng_knowledge | _last_search_images_var.set | IFC-141-402 | ContextVar 写 | 同步 |
| orchestrator._aggregate | State.related_images | IFC-141-503 | 写入 State 字段 | 同步 |
| adapter._drive | orch.graph.aget_state | IFC-141-601 | `(config) → StateSnapshot` | async（DB） |
| consumers._pump | self._related_images | IFC-141-702 | 实例变量赋值 | 同步 |
| consumers._finalize_turn | self.send | IFC-141-704 | `json.dumps({type:stream_end, related_images:[...]})` | async（WS） |
| RagImageView.get | RagImage.objects.only(...).get | IFC-141-801 | `(id=image_id) → RagImage` | 同步（DB） |
| ChatView.vue | api.js.fetchRagImage | IFC-141-1101 | `(imageId) → Promise<Blob>` | async（HTTP） |

---

*文档状态：DRAFT。等待 PM 门控评审通过后进入 APPROVED 状态。*
