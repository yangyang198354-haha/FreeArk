**特性**：三恒知识库 RAG 图片引用回溯（Image Citation）
**版本**：v1.4.1_rag_image_citation
**状态**：DRAFT
**日期**：2026-06-23
**依赖**：requirements_spec.md (APPROVED), user_stories.md (APPROVED)

---

# 系统架构设计 — v1.4.1 三恒知识库 RAG 图片引用回溯

**文档编号**：ARCH-DES-RAG-v141-001
**项目名称**：FreeArk 三恒知识库 RAG 图片引用回溯（v1.4.1_rag_image_citation）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-23
**输入文档**：
- `docs/requirements/v1.4.1_rag_image_citation/requirements_spec.md` (APPROVED)
- `docs/requirements/v1.4.1_rag_image_citation/user_stories.md` (APPROVED)
- `docs/architecture/v1.4.0_sanheng_rag_architecture_design.md` (APPROVED，基线参考)

---

## 1. 架构概览

### 1.1 本特性在 v1.4.0 基础上的叠加变更

v1.4.0 已建立三恒知识库的完整 RAG 基线：文档上传、OCR 解析、向量检索、`search_sanheng_knowledge` 工具、进程内向量缓存。

v1.4.1 以**最小侵入原则**在该基线上叠加图片引用能力，变更集中在以下五个层面：

| 变更层 | 变更内容 | 影响范围 |
|--------|---------|---------|
| 数据模型 | 新增 `RagImage` 模型（DB BLOB 存图片字节）；`RagChunk` 新增 `image` FK | `models_rag.py`，`0039_rag_image.py` |
| 服务层 | `RagParser` 入库时持久化图片字节；`RagIngestor` 写 `RagImage`；`RagVectorCache._meta` 追加 `image_id`；`search_rag()` 返回值新增 `image_id` | `rag_service.py` |
| 工具/编排层 | `fa_tools` 提取 `related_images`（side-channel）；`State` 新增字段；`orchestrator._expert/_aggregate` 传递 `related_images` | `fa_tools.py`，`orchestrator.py` |
| 消费者层 | `consumers._finalize_turn` 向 `stream_end` 附加 `related_images` 字段 | `consumers.py` |
| API/前端层 | 新增取图端点 `GET /api/rag/images/{id}/`；`ChatView.vue` 渲染图片引用区 | `views_rag.py`，`urls.py`，`ChatView.vue`，`api.js` |

**不变原则**（来自 C-001、C-002）：
- 现有 OCR 文字检索逻辑不变
- 不引入多模态 embedding 或 VLM
- LLM 接收的工具结果字符串中不含 image_id（防幻觉，C-003）

### 1.2 架构风格

继承 v1.4.0 的**模块化单体（Modular Monolith）**架构风格，叠加的图片能力作为现有 RAG 服务层的一个扩展切面，无新增进程、无新增外部服务。

关联需求：REQ-NFR-002（不新增并发线程）、REQ-NFR-001（Pi 5 资源约束）。

---

## 2. 完整调用链变更影响图（CRITICAL — RISK-IC-002 缓解）

### 2.1 v1.4.0 现有链路（基线）

```
用户提问
  │
  ▼
consumers._handle_chat()
  │  stream_chat(message, session_key)
  ▼
adapter._drive()  ← graph.astream(stream_mode=["updates","messages"])
  │
  ▼  [route 节点路由到 sanheng-knowledge]
orchestrator._expert(name="sanheng-knowledge", query=...)
  │
  │  tool_map["search_sanheng_knowledge"].ainvoke({"query": ...})
  ▼
fa_tools.search_sanheng_knowledge(query)
  │  search_rag(query, k, threshold)
  ▼
rag_service.search_rag()
  │  rag_vector_cache.search(query_vec)
  ▼
[返回 list[dict]: {content, source, is_image_ocr, score}]
  │
  ▼  （fa_tools 把 chunks 拼成纯文本 str）
ToolMessage(content=str)  ──→  LLM 见纯文本作答
  │
  ▼
orchestrator._aggregate()
  │  {"expert_results": [{"expert": "sanheng-knowledge", "answer": str}]}
  ▼
State.messages.append(AIMessage(content=final))
  │
  ▼
adapter._drive() yield ('content', delta)
  │
  ▼
consumers._pump() 累积 accumulated_content
  │
  ▼
consumers._finalize_turn(accumulated_content)
  │
  ▼
await self.send(json.dumps({'type': 'stream_end'}))   ← L404（无图片字段）
```

### 2.2 v1.4.1 目标链路

```
用户提问
  │
  ▼
consumers._handle_chat()
  │  stream_chat(message, session_key)
  ▼
adapter._drive()  ← graph.astream(stream_mode=["updates","messages"])
  │
  ▼  [route 节点路由到 sanheng-knowledge]
orchestrator._expert(name="sanheng-knowledge", query=...)
  │
  │  (1) 工具调用：tool_map["search_sanheng_knowledge"].ainvoke({"query": ...})
  ▼
fa_tools.search_sanheng_knowledge(query)
  │  search_rag(query, k, threshold)
  ▼
rag_service.search_rag()
  │  rag_vector_cache.search(query_vec)
  ▼
[返回 list[dict]: {content, source, is_image_ocr, score, image_id}]  ← 新增 image_id
  │
  ├──→ (A) 纯文本 str（给 LLM，image_id 不进此路径）
  │         ToolMessage(content=str)  ──→  LLM 见纯文本作答（不变）
  │
  └──→ (B) related_images: list[dict]（side-channel，不进 LLM）
             从 ToolMessage 中提取图片 id（调用 _extract_related_images()）

  (2) _expert 执行完工具后，调用 _extract_related_images(ToolMessage.content_raw_chunks)
      将非 None 的 image_id 收集为 related_images 列表追加到 expert_results：
      {"expert": "sanheng-knowledge", "answer": str, "related_images": list[dict]}

  (3) orchestrator._aggregate()
      在合并 expert_results 时，同时从所有 result 中收集 related_images（去重）
      返回：{"messages": [AIMessage(final)], "related_images": list[dict]}（State 新增字段）

  (4) State.related_images 字段（新增，operator.add reducer，前端去重）

  (5) adapter._drive()
      从 graph 的最终 updates 中取 aggregate 节点输出的 related_images
      作为 ('related_images', json_str) 在 stream_end 之前 yield 给 consumers

  ─── 或者（更简单的替代方案，见 ADR-IC-002） ───
      adapter._drive() 在 astream 完成后，从 graph.aget_state().values.related_images 读取

  (6) consumers._pump()
      接收到 ('related_images', json_str) kind → 存入 self._related_images

  (7) consumers._finalize_turn(accumulated_content, related_images)
      await self.send(json.dumps({
          'type': 'stream_end',
          'related_images': related_images   ← 新增字段（可选，缺失等同空数组）
      }))

前端 ChatView.vue
  │  收到 stream_end.related_images（非空时）
  ▼
  气泡下方渲染图片缩略图区
  │  GET /api/rag/images/{image_id}/  (通过 api.js)
  ▼
  views_rag.RagImageView → DB 查询 RagImage → 返回图片字节流
```

### 2.3 关键设计决策：side-channel 实现方式（选用方案 B-1）

**问题**：`search_sanheng_knowledge` 作为 LangChain `@tool` 必须返回 `str`（LangGraph 把返回值包装为 `ToolMessage.content`，LLM 需要看到纯文本）。如何同时把 `related_images` 传递给 orchestrator？

**选用方案 B-1：在 _expert 节点中调用内部帮助函数**

在 `orchestrator._expert` 执行工具调用后，对 `sanheng-knowledge` 专家的 ToolMessage 结果，额外调用 `fa_tools._get_last_related_images()` 内部函数（非 `@tool`，不暴露给 LLM），该函数从线程局部存储（`threading.local()`）中读取 `search_rag()` 最近一次调用的 `related_images` 列表。

`search_rag()` 在返回结果时，将 `image_id` 非 None 的 chunks 的 image 信息写入线程局部存储，供同一调用链上层读取。

**理由**：
- `@tool` 返回类型契约不变（str），LangGraph 行为不变
- 无需修改 adapter.py 的流式驱动逻辑
- 线程安全：每个工具调用在 asyncio event loop 的同一 task 上下文中串行执行，`asyncio.get_event_loop()` 的 task-local storage 可替代 threading.local（见 ADR-IC-002）

此方案的完整调用链（精确版本）：

```
orchestrator._expert:
  while tool_calls:
      for tc in tcs:
          if tc["name"] == "search_sanheng_knowledge":
              out = await t.ainvoke(tc["args"])     # 返回 str（给 LLM）
              # side-channel：同步读取刚才 search_rag() 存入 task-local 的 related_images
              imgs = fa_tools.get_last_search_images()   # 新增内部函数（非 @tool）
              accumulated_images.extend(imgs)
          msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
  return {"expert_results": [{
      "expert": name,
      "answer": ai.content,
      "related_images": deduplicate(accumulated_images),  # 同文档内去重
  }]}

orchestrator._aggregate:
  all_images = []
  for r in results:
      all_images.extend(r.get("related_images", []))
  # 去重（同一 image_id 只保留一次）
  seen_ids = set()
  unique_images = []
  for img in all_images:
      if img["image_id"] not in seen_ids:
          seen_ids.add(img["image_id"])
          unique_images.append(img)
  return {
      "messages": [AIMessage(content=final)],
      "related_images": unique_images,   # State 新增字段
  }
```

### 2.4 State 新增字段

```
class State(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: List[Tuple[str, str]]
    expert_results: Annotated[List[dict], operator.add]
    name: str
    query: str
    related_images: List[dict]   # 新增：[{image_id: int, source: str}, ...]
                                  # reducer: 不用 operator.add（aggregate 节点统一赋值）
```

`related_images` 字段在 State 中不使用 `operator.add` reducer，而是由 `_aggregate` 节点统一收集并一次性写入，避免 fan-out 分支的多次部分写入导致竞态。

### 2.5 consumers.py 变更点

**修改范围**（最小化）：`_finalize_turn` 方法签名新增 `related_images` 参数，以及 adapter 将 `related_images` 从最终 State 取出后通过 `_pump` 传递。

```
consumers._pump() 新增处理：
  elif kind == 'related_images':
      self._related_images = json.loads(text)  # 存入实例变量

consumers._handle_chat() 变更：
  status, accumulated_content = await self._pump(...)
  ...
  await self._finalize_turn(accumulated_content,
                            related_images=getattr(self, '_related_images', []))

consumers._finalize_turn(accumulated_content, related_images=None):
  payload = {'type': 'stream_end'}
  if related_images:
      payload['related_images'] = related_images
  await self.send(json.dumps(payload))
  # DB 写入逻辑不变（related_images 不持久化，对齐 OQ-IC-004 决策）
```

adapter._drive() 新增（在 seen_any 判断之前）：

```
# 在 astream 循环结束后，从最终 State 取 related_images yield 给 consumer
snap = await orch.graph.aget_state(config)
related_images = (snap.values or {}).get("related_images", []) if snap else []
if related_images:
    yield ("related_images", json.dumps(related_images, ensure_ascii=False))
```

**WS 验证要求**（来自项目硬约束7）：consumers.py 任何修改须本地真 Redis 验 WS 收发，不可仅用 InMemoryChannelLayer 测试。

---

## 3. 数据模型架构

### 3.1 新增模型：RagImage

关联需求：REQ-FUNC-001、REQ-FUNC-002、REQ-NFR-001

```
RagImage
  id               — AutoField (PK)
  document         — FK(RagDocument, on_delete=CASCADE)  [REQ-FUNC-006 级联清理]
  image_index      — IntegerField  [同文档内图片序号，0 起，便于日志定位]
  page_or_section  — CharField(max_length=100)  [来源页/节，对齐现有 RagChunk 格式]
  image_format     — CharField(max_length=20)  ['png'/'jpeg'/'other']
  image_data       — BinaryField  [原始图片字节，DB BLOB，见 ADR-IC-001]
  file_size        — IntegerField  [字节大小，便于监控查询]
  created_at       — DateTimeField(auto_now_add=True)

  class Meta:
    db_table = 'api_ragimage'
    indexes: [document_id]  [RagChunk 查关联图片 JOIN 走索引]
```

存储设计约束（对应 OQ-IC-001 决策：DB BLOB）：
- `image_data` 使用 Django `BinaryField`，字节直接写入主库（MySQL/SQLite）
- `file_size` 冗余存储，避免每次查存储总量时读 BLOB 字段：`SELECT SUM(file_size) FROM api_ragimage`

### 3.2 RagChunk 新增字段

关联需求：REQ-FUNC-002

```
RagChunk（在 v1.4.0 基础上新增一个字段）：
  image   — FK(RagImage, null=True, blank=True, on_delete=SET_NULL)
           [null=True: 纯文字 chunk 无关联图片；on_delete=SET_NULL: 图片删除后 chunk 仍存在]
```

注意：`RagImage.on_delete=CASCADE`（文档删除 → 图片删除）与 `RagChunk.image.on_delete=SET_NULL`（图片独立删除 → chunk 的 image_id 置 null）逻辑方向不同，两者均正确：
- 文档删除 → RagImage CASCADE 删除 → RagChunk 也 CASCADE 删除（RagChunk.document 是主 FK）
- 不存在单独删除图片的业务场景，`SET_NULL` 是防御性设计

### 3.3 向量缓存 RagVectorCache._meta 结构变更

关联需求：REQ-NFR-001（图片字节不进内存缓存）、REQ-NFR-005（向后兼容）

v1.4.0：`{'doc_name', 'source', 'is_image_ocr', 'content'}`

v1.4.1：`{'doc_name', 'source', 'is_image_ocr', 'content', 'image_id'}` — 仅追加 `image_id`（整型 id 或 None）

**约束**：`image_id` 存整型 id，不存图片字节，不存 URL。图片字节按需从 DB 读取（US-IC-008）。

### 3.4 search_rag() 返回值变更

关联需求：REQ-FUNC-003

v1.4.0：`{"chunks": [{"content", "source", "is_image_ocr", "score"}], "degraded": bool}`

v1.4.1：`{"chunks": [{"content", "source", "is_image_ocr", "score", "image_id"}], "degraded": bool}`

每个 chunk dict 新增 `image_id` 字段（`int | None`）：
- 有关联图片且 `is_image_ocr=True`：`image_id` 为正整数
- 纯文字 chunk 或图片存储被跳过（超限等）：`image_id` 为 None

---

## 4. API 架构

### 4.1 新增端点：取图接口

关联需求：REQ-FUNC-004、REQ-NFR-004

```
GET /api/rag/images/{image_id}/
权限:     IsAuthenticated（Bearer Token，对齐现有知识库检索权限，不是 IsAdminUser）
响应成功: 200 + Content-Type: image/{format} + Content-Disposition: inline + 图片字节流
响应失败: 404（图片不存在或 image_id 非法）
```

**权限说明**：取图权限为 `IsAuthenticated`（所有已登录用户），与 `RagDocumentViewSet` 的 `IsAdminUser`（仅管理员可上传/删除）有意区分：知识库检索面向所有登录用户，图片引用同理（REQ-NFR-004）。

**安全约束**：
- `Content-Disposition: inline`：防止浏览器将图片字节误解为可执行下载内容（REQ-NFR-004）
- 不缓存（`Cache-Control: no-store`）：图片内容可能涉及设备参数等敏感信息
- 图片字节从 DB 直接读取，不经 `RagVectorCache`（US-IC-008）

### 4.2 路由注册

在现有 `urls.py` 追加（不改动现有 rag_router）：

```
path('rag/images/<int:image_id>/', views_rag.RagImageView.as_view(), name='rag-image-detail')
```

### 4.3 现有端点不变

v1.4.0 的文档管理端点（`GET/POST/DELETE /api/rag/documents/`，`POST /api/rag/documents/{id}/retry/`）签名、权限、行为均不变。

---

## 5. 存储架构

### 5.1 DB BLOB 方案（ADR-IC-001 决策：已锁定）

图片字节存储在主库（`api_ragimage.image_data`，BinaryField）。

**表存储构成**（MySQL InnoDB / SQLite）：
- 元数据行（id, document_id, image_index, page_or_section, image_format, file_size, created_at）：约 100-200 bytes/行
- BLOB 字节：`file_size` bytes/行

**Pi 5 存储预估**（对应 REQ-NFR-001）：
- 典型三恒工程图纸（A4 PNG，150DPI）：1~5 MB/张
- 典型操作手册（含设备标牌照片，JPEG）：0.2~1 MB/张
- 每份文档含图片数量：5~20 张（三恒手册典型范围）
- 保守预估：100 份文档 × 15 张/份 × 平均 2 MB = 3 GB
- 激进预估（大量扫描件）：300 份文档 × 20 张/份 × 3 MB = 18 GB
- Pi 5 SD 卡/SSD 典型配置：32~128 GB；3~18 GB 的图片存储在现有 DB 文件基础上增加约 10%~30%，可接受，但需监控。

**缓解措施（对应 RISK-IC-001）**：

(1) **单图 10MB 上限**（OQ-IC-002 决策）：

```
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
# 实施点：RagParser._try_save_image() 方法中
# len(img_bytes) > MAX_IMAGE_BYTES → 记录 WARNING → 返回 None（跳过存储）
```

(2) **SQLite 自动 VACUUM 建议**：

```sql
-- SQLite 场景：在 settings.py 或 AppConfig.ready() 中执行（每次启动）
PRAGMA auto_vacuum = INCREMENTAL;
-- 可选：定期执行（运维脚本）
PRAGMA incremental_vacuum(1000);
```

(3) **MySQL 监控与清理建议**：

```sql
-- 监控：查图片总占用（无需扫 BLOB 字段）
SELECT COUNT(*), SUM(file_size)/1024/1024 AS total_mb FROM api_ragimage;
-- 监控：按文档查图片存储
SELECT d.file_name, COUNT(i.id), SUM(i.file_size)/1024/1024 AS mb
FROM api_ragimage i JOIN api_ragdocument d ON i.document_id=d.id
GROUP BY d.id ORDER BY mb DESC LIMIT 20;
-- 清理：删除文档会 CASCADE 清理图片（已有端点，无需额外脚本）
-- 运维：定期 OPTIMIZE TABLE api_ragimage（MySQL，回收 BLOB 碎片空间）
```

(4) **监控告警建议**：图片总存储超过 5 GB 时向运维发出告警（可通过 cron 脚本 + 上述 SQL 查询实现）。

### 5.2 图片字节生命周期

```
入库阶段（后台线程）：
  RagParser 提取 img_bytes
    ├── len(img_bytes) > MAX_IMAGE_BYTES → WARNING + 跳过（fail-open）
    ├── 提取失败 → WARNING + 跳过（fail-open）
    └── 成功 → RagIngestor 写入 api_ragimage（BinaryField）

使用阶段（请求时）：
  检索路径：rag_vector_cache.search() 返回 image_id（整型）→ 不读 BLOB
  取图路径：GET /api/rag/images/{id}/ → RagImage.objects.get(id=id) → 返回 image_data

删除阶段：
  DELETE /api/rag/documents/{id}/ → doc.delete()
    → RagImage.document FK CASCADE → 自动删除关联图片行
    → RagChunk.document FK CASCADE → 自动删除关联 chunk 行
  无孤立数据（REQ-FUNC-006）
```

---

## 6. 安全架构

### 6.1 鉴权

关联需求：REQ-NFR-004，C-004

- 取图端点：`IsAuthenticated`（Bearer Token），DRF TokenAuthentication
- 前端取图：**必须通过 `api.js`**（已封装 Authorization 头），禁止裸 `import axios from 'axios'`
- 项目硬约束：本特性新增的所有前端 HTTP 调用必须走 `api.js`，代码评审检查点

### 6.2 内容安全

- 响应头：`Content-Disposition: inline`（禁止浏览器下载执行）
- `Content-Type`：根据 `RagImage.image_format` 动态设置（`image/png`、`image/jpeg`、`application/octet-stream`）
- 图片字节不入日志（BinaryField 内容不序列化到 error log）

### 6.3 防 LLM 幻觉（C-003）

- `fa_tools.search_sanheng_knowledge` 返回给 LLM 的字符串中**不含** `image_id`、URL、或任何图片标识符
- `related_images` 通过 side-channel（task-local storage → State.related_images → stream_end 字段）传递，完全绕过 LLM 处理路径
- 前端图片引用区的 URL 由前端根据 `image_id` 构造（`/api/rag/images/{id}/`），不由 LLM 生成

### 6.4 多租户说明

当前知识库无多租户隔离，所有已登录用户均可查看任何图片（与现有文档检索一致）。如将来引入多租户，取图端点需同步增加 tenant 过滤（NT-006 未来演进登记）。

---

## 7. ADR 列表

### ADR-IC-001：图片存储方案选择

**Status**：Accepted（OQ-IC-001 PM 已决策锁定：DB BLOB）

**Context**：
REQ-FUNC-001 要求图片原字节持久化，REQ-NFR-001 要求 Pi 5 存储有限。需决定存储介质：DB BLOB vs 文件系统（Django MEDIA_ROOT）。

**Options**：

**Option A：DB BLOB（BinaryField 存入主库）**
- 优点：
  - 无额外文件系统管理：删除文档时 CASCADE 自动清理，无孤立文件风险
  - 事务一致性：图片写入与 RagChunk 写入在同一 DB 事务生命周期内，无部分成功状态
  - 部署简单：Pi 5 无需配置 MEDIA_ROOT 目录权限、无需 nginx 静态文件服务
  - 现有备份策略复用：DB 备份即包含图片
  - 取图端点实现简单：直接 ORM 查询 `RagImage.objects.get(id=id).image_data`
- 缺点：
  - DB 文件体积增大（RISK-IC-001）：SQLite WAL 文件、MySQL InnoDB 表空间膨胀
  - Pi 5 SD 卡写入寿命：频繁 BLOB 写入加速 SD 卡磨损（可用 SSD 缓解）
  - 大 BLOB 读写对 DB 连接池有一定冲击（10MB × 并发量）

**Option B：文件系统存储（Django MEDIA_ROOT / settings.MEDIA_ROOT）**
- 优点：
  - DB 体积不增大，DB 操作只存文件路径（CharField）
  - 大文件读写不占 DB 连接（nginx 可直接 serve 静态文件）
  - Pi 5 文件系统有独立的磨损均衡
- 缺点：
  - 删除逻辑复杂：需要 Django signal（`post_delete`）或 override `delete()` 手动清理文件，孤立文件风险高
  - Pi 5 需要额外配置 MEDIA_ROOT 目录权限、`settings.MEDIA_URL`、可能需要 nginx 配置
  - 文件路径与 DB 记录一致性需手工维护（文件丢失时 DB 记录仍存在）
  - 备份需同时备份 DB + MEDIA 目录，增加运维复杂度

**Decision**：选择 **Option A（DB BLOB）**

**理由**：Pi 5 是单机部署（无 CDN、无 nginx static serve 需求），MEDIA_ROOT 方案的额外运维成本在 Pi 5 场景不值得。DB BLOB 的删除一致性保证远优于文件系统方案。10MB 上限（OQ-IC-002）约束单图大小，降低 BLOB 冲击。RISK-IC-001 风险已知接受，缓解措施见第 5 章。

**Consequences**：
- 正向：删除逻辑零额外代码（CASCADE 覆盖）；取图端点简单（ORM 直查）；备份一体化
- 负向：DB 文件体积增大，需监控 `SUM(file_size)` 并建议定期 VACUUM；10MB 上限约束超限图片不存储（这些图片的 OCR 文字 chunk 仍可用，但无图可引）

---

### ADR-IC-002：related_images side-channel 传递机制

**Status**：Accepted

**Context**：
REQ-FUNC-003、C-003 要求 `related_images` 不经 LLM 处理（防幻觉），但 LangChain `@tool` 返回类型是 `str`，必须给 LLM 看到。需决定如何在不修改工具返回类型的前提下，把 `related_images` 从 `search_sanheng_knowledge` 传递到 `orchestrator._expert`。

**Options**：

**Option A：工具返回类型改为 dict（结构化），orchestrator._expert 解包**
- 优点：类型清晰，显式传递
- 缺点：LangGraph 工具调用时把工具返回值直接序列化为 `ToolMessage.content`（str）；如果返回 dict，LangGraph 会把它转为 `str(dict)` 或 JSON 字符串传给 LLM——LLM 会看到 `image_id` 字段，违反 C-003（防幻觉约束）。需要在 `_expert` 中拦截 `ToolMessage.content` 解析 dict，但此时 LLM 已被 bind 了这个工具，schema 会暴露 dict 结构给 LLM，不可接受。

**Option B：task-local storage side-channel**
- 优点：`@tool` 返回 `str` 不变（LLM 只见文本）；orchestrator._expert 通过内部帮助函数 `fa_tools.get_last_search_images()` 读取同一 asyncio task 上下文中最近一次 `search_rag()` 写入的 `related_images`
- 实现：`search_rag()` 在返回之前，将 image 信息写入 `contextvars.ContextVar`（Python 3.7+ 原生支持 asyncio task 隔离，比 threading.local 更安全）；`get_last_search_images()` 读取并清零
- 缺点：隐式传递，需要调用方主动调用 `get_last_search_images()`；ContextVar 在多 awaitable 交织时需注意 copy_context（但 asyncio.Task 自动 copy context，安全）

**Option C：修改 `_expert` 调用工具后直接再调 `search_rag()`（再查一次）**
- 优点：无需 side-channel，数据来源清晰
- 缺点：重复调用 embedding API（额外费用与延迟）；违反 REQ-NFR-002（不应显著增加耗时）

**Decision**：选择 **Option B（ContextVar side-channel）**

**理由**：asyncio 的 `contextvars.ContextVar` 天然与 asyncio Task 绑定（每个 Task 有独立 context 副本），比 `threading.local` 在 async 代码中更安全。无重复 API 调用，无 LLM schema 污染，`@tool` 接口契约不变。

**Consequences**：
- 正向：LLM 绝不见 image_id（C-003 严格满足）；工具返回类型不变（现有 orchestrator 逻辑最小改动）；无额外 embedding API 调用
- 负向：隐式传递增加代码理解负担；若未来有人直接调 `search_sanheng_knowledge` 而不调 `get_last_search_images()`，图片引用会丢失（需在 orchestrator._expert 中对 `sanheng-knowledge` 专家专项处理）

---

### ADR-IC-003：历史会话图片引用持久化

**Status**：Accepted（OQ-IC-004 PM 已决策锁定：本期不复现）

**Context**：
REQ-FUNC-005 要求 `stream_end` 带 `related_images`，但 `chat_memory.append_message` 只存文字。历史会话加载时，是否需要复现图片引用？

**Options**：

**Option A：本期不持久化 related_images，历史消息只显示文字**
- 优点：实现简单，不改动 chat_memory 模块，不新增 DB 字段
- 缺点：历史会话中含图片的回答，重新加载后看不到图片缩略图

**Option B：持久化 related_images 到 ChatMessage（新增 JSON 字段）**
- 优点：历史会话体验完整
- 缺点：需改动 chat_memory 模块和 ChatMessage 模型（超出本特性边界）；需关联 image_id 的长期有效性（图片若后续被删，历史引用悬空）

**Decision**：选择 **Option A（本期不持久化）**

**Consequences**：
- 正向：chat_memory 模块零改动；session 历史加载逻辑不变
- 负向：历史会话含图片的回答无图片区域（已知限制，向用户说明）

---

### ADR-IC-004：image_id 去重策略

**Status**：Accepted

**Context**：
US-IC-001 AC-IC-001-02 要求同一图片多个 OCR chunk 命中时，related_images 中同一 image_id 只出现一次。去重在后端还是前端？

**Options**：

**Option A：后端去重（_aggregate 节点）**
- 优点：前端无需关心去重逻辑；stream_end 载荷小（不含重复项）；单点维护
- 缺点：前端无法自行控制展示顺序（顺序由后端确定）

**Option B：前端去重（ChatView.vue 收到 stream_end 后处理）**
- 优点：后端逻辑简单（直接 extend 不去重）；前端可自定义展示顺序
- 缺点：重复的 image_id 占用 WS 传输带宽；前端需要额外逻辑

**Decision**：选择 **Option A（后端去重）**

**理由**：`_aggregate` 节点已经是各专家结果的汇聚点，在此统一去重是自然的架构位置。WS 消息体保持简洁，前端零去重逻辑。

**Consequences**：
- 正向：前端无去重代码；WS 载荷最小
- 负向：后端需维护 seen_ids 集合（O(n) 操作，n 为 related_images 数量，远小于 chunk 数量，可接受）

---

## 8. 依赖约束

### 8.1 Migration 编号

关联需求：REQ-NFR-005、C-006（手写 migration，不跑 makemigrations）

- 现有最新迁移：`0038_chatsession_title.py`（依赖 `0037_chatsession_is_deleted_session_key_unique`）
- 本特性 migration：编号 **0039**，文件名 `0039_rag_image.py`
- 依赖声明：`dependencies = [('api', '0038_chatsession_title')]`
- 表名：`api_ragimage`（Django 自动前缀 `api_` + 模型名 `ragimage`，符合现有惯例）

### 8.2 无新增外部依赖

DB BLOB 方案不需要文件系统库、对象存储 SDK 或任何新 Python 包。所有功能使用现有依赖实现：
- Django `BinaryField`：Django 内置
- `HttpResponse` 字节响应：DRF 内置
- `contextvars.ContextVar`：Python 3.7+ 标准库

### 8.3 无侵入现有依赖

- `langchain-openai`：版本不变
- `numpy`：不变（image_id 为整型，不入向量缓存）
- `PyMuPDF`、`python-docx`、`rapidocr-onnxruntime`：不变（已有入库依赖）

### 8.4 后端测试基线保护

关联约束：项目硬约束8（现有 1778 通过、0 失败）

- `search_rag()` 返回值新增 `image_id` 字段为**追加**（向后兼容），现有测试只检查 `chunks`/`degraded` 字段，不受影响
- `_finalize_turn` 签名新增 `related_images=None` 默认参数，向后兼容
- `State` 新增 `related_images` 字段（`total=False`，可选字段），不破坏现有状态操作

---

## 9. 开放问题（本文档内 ASSUMPTION 汇总）

以下决策均已由 PM 在调用指令中确认，无新增开放问题：

| OQ 编号 | 决策 | 影响 |
|--------|------|------|
| OQ-IC-001 | DB BLOB | ADR-IC-001 已落实 |
| OQ-IC-002 | 10MB 上限 | ADR-IC-001 Consequences 已落实 |
| OQ-IC-003 | 扫描件整页大图存储，受 10MB 上限约束 | RagParser 路径3 纳入 _try_save_image() 处理 |
| OQ-IC-004 | 历史会话不复现图片引用 | ADR-IC-003 已落实 |
| OQ-IC-005 | KnowledgeBaseView 裸 axios 不在本期范围 | 本特性新增取图调用走 api.js 即满足 |

[ASSUMPTION — requires PM confirmation]：无

---

*文档状态：DRAFT。等待 PM 门控评审通过后进入 APPROVED 状态。*
