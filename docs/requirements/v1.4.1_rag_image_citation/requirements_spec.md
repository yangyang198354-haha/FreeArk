# 需求规格说明书

**特性**：三恒知识库 RAG 图片引用回溯（Image Citation）
**版本**：v1.4.1_rag_image_citation
**状态**：DRAFT — 等待产品负责人确认
**日期**：2026-06-23
**作者**：pm-orchestrator（代 requirement-analyst 编写，基于用户提供的业务目标与代码事实）

---

## 1. 背景与问题陈述

### 1.1 现状

`v1.4.0_sanheng_rag` 已实现三恒知识库的文档上传、OCR 解析与向量检索。当文档（docx/pdf）内含图片时，`RagParser.parse_docx` / `parse_pdf` 会对内嵌图片执行 OCR，将识别出的文字写入 `RagChunk.content`（`is_image_ocr=True`），但**图片原始字节在 OCR 完成后即被丢弃，从未持久化**。

检索结果经 `fa_tools.search_sanheng_knowledge` 拼成纯文本后喂给 LLM，回答气泡中没有任何图片引用。

### 1.2 问题

用户提问「某设备参数图示是什么」时，智能体只能给出 OCR 识别出的文字，无法展示原始图片——对于三恒工程图纸、设备标牌、参数表格图，这一体验明显不足。

### 1.3 解决方向

**A 方案（本期实施）**：保持现有 OCR 文字检索逻辑不变，额外把命中 OCR chunk 的**原始图片**作为引用附件带回，在回答气泡下以缩略图展示、可点开看大图。

**B 方案（明确排除，未来演进）**：多模态向量检索 + VLM 看图回答。本期不做，不引入多模态 embedding，不引入 VLM。

---

## 2. 范围界定

### 2.1 本期范围（IN SCOPE）

- 图片原字节持久化（入库时同步存储，新增 `RagImage` 模型或等价存储）
- `RagChunk`（`is_image_ocr=True`）与来源图片建立关联
- 检索结果在后端透传图片引用（id / url），不经 LLM 处理
- 新增鉴权图片取图 HTTP 端点
- 聊天回答气泡下展示引用图缩略图，支持点开大图
- 降级处理：OCR 未启用、图片提取失败、图片超大等边界场景

### 2.2 本期明确排除（OUT OF SCOPE）

- 多模态向量检索（不替换现有 BGE/豆包 embedding）
- VLM 看图生成回答（B 方案）
- 知识库管理页面的图片预览（管理侧，不在本期 UI 范围）
- 图片 OCR 质量提升（超出本特性边界）
- 原始文档文件持久化（`RagDocument` 无 FileField 是已决策现状，不在本期推翻）

---

## 3. 利益相关方与用户角色

| 角色 | 描述 | 核心关切 |
|------|------|---------|
| 住户/业主（最终用户） | 通过聊天界面提问 | 回答中图片引用直观、可信 |
| 知识库管理员（Admin） | 上传 docx/pdf 文档 | 上传流程不变；存储开销可知 |
| 平台运维（Pi 5 管理者） | 维护树莓派 5 生产节点 | 存储/内存资源可控；降级行为明确 |

---

## 4. 功能需求

### REQ-FUNC-001 图片持久化

**描述**：解析文档（docx/pdf）时，凡提取出图片字节（无论 OCR 是否成功识别出文字），均将图片原字节持久化到系统中。

**当前代码锚定**：
- `RagParser.parse_docx`（L357-370 / `rag_service.py`）：`img_bytes = rel.target_part.blob`——此处有字节，OCR 后即丢失
- `RagParser.parse_pdf`（L406-419）：`img_bytes = base_image["image"]`——同上
- pdf 扫描件 fallback（L433-460）：整页栅格化 `png_bytes`——同上

**需求细节**：
- 图片存储实体须记录：所属文档（外键 `RagDocument`）、页码或来源标注（对齐现有 `page_or_section` 格式）、图片序号（同页多图时区分）、图片格式（png/jpeg/其他）、字节大小。
- 存储方式（DB BLOB vs 文件系统）为架构阶段决策，需求仅约束：Pi 5 存储有限（SD 卡/SSD 典型配置 32~128 GB，已有 DB 与日志），单张图片存储不应无上限；建议在架构阶段评估单图大小上限（参考现有 `_SCAN_MAX_IMG_BYTES = 50MB` 作为解析防御上限，实际存储上限可更低）。
- 图片存储与 `RagChunk` 写入在同一入库事务/流程中完成，**不得**因图片存储失败导致整文档入库失败（降级：图片存储失败则记录 WARNING、跳过该图，文字 chunk 照常入库）。

**验收标准**：
- 上传一份含内嵌图片的 docx/pdf 后，数据库中可查到与文档关联的图片记录，图片字节非空。
- 上传不含图片的纯文字文档，图片记录为零，入库照常成功。
- 图片提取抛出异常时，文档整体状态最终为 `indexed`（不因图片失败变 `failed`），异常以 WARNING 级别记录。

---

### REQ-FUNC-002 chunk 与图片关联

**描述**：`is_image_ocr=True` 的 `RagChunk` 须能反查到产生该 OCR 文字的原始图片。

**当前代码锚定**：`RagChunk` 有 `is_image_ocr: BooleanField` 和 `page_or_section: CharField`，但无任何字段指向图片实体。

**需求细节**：
- 关联关系建立时机：入库阶段，`RagChunk` 写入时同步建立关联，不做事后补全。
- 关联关系类型：一个 chunk 对应最多一张原图（一张图 OCR 文字可能被 `_split_text` 分成多个 chunk，每个 chunk 均指向同一张原图）。
- 关联字段在架构阶段决策（外键 or 冗余 image_id），需求仅要求：给定一个 `RagChunk.id`，能在 O(1) 或单次 JOIN 内查到对应图片。

**验收标准**：
- 对任一 `is_image_ocr=True` 的 chunk，通过关联可取到非空图片字节。
- 纯文字 chunk（`is_image_ocr=False`）无图片关联，查询时返回空/None，不报错。
- 同一图片 OCR 文字被分成多个 chunk 时，每个 chunk 均正确指向同一张图片。

---

### REQ-FUNC-003 检索结果透传图片引用

**描述**：`search_rag()` 返回的 chunk 列表中，凡 `is_image_ocr=True` 的条目须携带图片引用（可被前端用于取图的标识符，如图片 id 或预签名 URL path）。该引用经 `fa_tools.search_sanheng_knowledge` 向上传递到 consumer，不经 LLM 处理。

**当前代码锚定**：
- `RagVectorCache.search()` 返回 `{'content', 'source', 'is_image_ocr', 'score'}` dict 列表
- `search_rag()` 原样返回 `{"chunks": [...], "degraded": bool}`
- `fa_tools.search_sanheng_knowledge` 把 chunks 拼成纯文本字符串返回给 LangGraph 节点

**需求细节**：
- `search_rag()` 返回的每个 chunk dict，当 `is_image_ocr=True` 且存在关联图片时，新增 `image_id` 字段（整型 or None）。
- `fa_tools.search_sanheng_knowledge` 返回给 LLM 的**文本内容不变**（避免 LLM 看到 image_id 并尝试自己拼 URL 造成幻觉）；但同时以结构化形式向上返回 `related_images` 列表（见 REQ-FUNC-005）。
- LangGraph 编排图 / consumer 的调用链须把 `related_images` 带到 `stream_end` 消息中，作为独立字段而非文本内容的一部分。

**验收标准**：
- 命中含图片的 OCR chunk 时，`search_rag()` 返回的该 chunk dict 中 `image_id` 为正整数。
- 未命中含图片 chunk 或图片关联缺失时，`image_id` 为 None 或字段缺失，不报错。
- LLM 接收到的工具结果字符串中**不含** image_id 或 URL（防止幻觉）。

---

### REQ-FUNC-004 鉴权图片取图端点

**描述**：新增 HTTP GET 端点，供前端按图片 id 取原图字节，要求登录认证。

**接口设计约束**（架构阶段细化，需求给出边界）：
- 路径形如 `GET /api/rag/images/{image_id}/`
- 权限：`IsAuthenticated`（所有已登录用户均可取图，对齐现有知识库检索的权限模型）
- 响应：Content-Type 为图片实际格式（image/png, image/jpeg 等），字节流
- 图片不存在：404
- 图片过大或格式异常：安全降级，返回 404 或 500（不 panic）

**关键约束 — 前端取图必须走 api.js（历史教训）**：

> 前端**禁止**用裸 `import axios from 'axios'` 取图。KnowledgeBaseView.vue 当前已使用裸 axios（L195, L238 等），这是历史遗留，本特性新增的取图调用**必须**通过项目统一的 `api.js`（已封装 Token 认证头）。如果未来移除 `SessionAuthentication`，裸 axios 页面将 401 静默空白。本需求将此约束写入验收标准，实现阶段必须遵守。

**验收标准**：
- 已登录用户请求存在的图片，返回 200 + 正确 Content-Type + 非空图片字节。
- 未登录（无 Token）请求返回 401。
- 不存在的 image_id 返回 404。
- 前端取图代码路径：使用 `api.js` 封装，不使用裸 axios，代码评审时检查。

---

### REQ-FUNC-005 回答气泡图片引用展示

**描述**：聊天回答中命中了含图片的 OCR chunk 时，回答气泡下方以缩略图方式展示原始图片引用，用户可点开查看大图。图片 URL **不经 LLM 生成**，由后端以结构化字段 `related_images` 带外返回。

**禁止的实现方式**：
- 禁止让 LLM 在回答文本中自行输出 markdown 图片链接（`![](url)`）——LLM 不知道真实 image_id，会幻觉 URL
- 禁止前端从回答文本中解析/提取图片 URL

**正确的实现方式**：
- WS 协议：`stream_end` 消息新增可选字段 `related_images: [{image_id: number, source: string}]`
- 前端在收到 `stream_end` 时，若 `related_images` 非空，在气泡下方渲染图片引用区
- 图片引用区展示缩略图（CSS 控制尺寸，建议最大宽 160px / 高 120px），点击后以弹层（el-image 的 preview-src-list 或 el-dialog）展示原图

**当前代码锚定**：
- `consumers.py` L404：`await self.send(json.dumps({'type': 'stream_end'}))` — 本期在此处新增 `related_images` 字段
- `ChatView.vue` L86-108：气泡渲染区 — 本期在气泡 `.chat-bubble` 内、文字渲染块之后新增图片引用区

**验收标准（Given/When/Then 见 user_stories.md）**：
- 命中含图片 OCR chunk 的问答，气泡下方出现图片缩略图区域，图片可正常加载。
- 未命中含图片 chunk 的普通问答，气泡下不出现图片区域（无空白占位符）。
- 点击缩略图，大图可在弹层或新区域展示，不跳转到新标签页。
- 图片加载失败（网络抖动、图片记录缺失）时，气泡下方显示友好文案（如「图片暂时无法显示」），不影响文字答案的正常展示。
- `stream_end` 消息中 `related_images` 为空数组或缺失时，气泡渲染行为与无图片情况相同（无副作用）。

---

### REQ-FUNC-006 文档删除时级联清理图片

**描述**：删除 `RagDocument` 时，关联的 `RagImage` 数据须同步清理（含存储在文件系统的图片文件，如架构选择文件系统存储）。

**当前代码锚定**：`views_rag.py` L143-149：`doc.delete()` 触发 `RagChunk` 级联删除。本期需把图片实体纳入同一清理链路。

**验收标准**：
- 删除文档后，数据库中无孤立的 `RagImage` 记录（关联 document 为 null 或不存在）。
- 若使用文件系统存储，文件也同步删除（不泄漏磁盘空间）。

---

## 5. 非功能需求

### REQ-NFR-001 存储资源约束（Pi 5 平台）

- 图片 BLOB 或文件落盘会增加存储开销。架构阶段须评估并给出存储预估（基于典型三恒文档图片数量/大小）。
- 建议设置单图存储上限（需求侧：不超过 10MB/张，架构阶段可收紧）；超限图片：记录 WARNING + 跳过存储，文字 chunk 照常入库（fail-open）。
- Pi 5 RAM 8GB；图片字节不应在内存向量缓存 `RagVectorCache` 中持有（缓存仅保留 embedding + meta，不缓存图片字节）。

### REQ-NFR-002 入库性能

- 图片持久化步骤在现有入库后台线程（`RagIngestor.ingest`）中串行执行，不新增并发线程。
- 图片写入操作不得使单文档入库耗时翻倍以上（参考基准：现有纯文本 docx 入库 P95 < 30s，含图片文档视图片数量线性增长可接受）。

### REQ-NFR-003 降级与 fail-open

延续现有 `_HAS_OCR` 防御风格：
- OCR 未启用（`_HAS_OCR=False`）：图片存储仍可执行（不依赖 OCR 成功），但此时 `is_image_ocr=False`，无 chunk 与图片关联——前端不展示引用图（无 chunk 命中）。此为合理降级，不需特殊提示。
- 图片提取失败（`extract_image` 异常）：跳过该图，WARNING 日志，不影响同文档其他 chunk 和图片。
- 图片超大（超过存储上限）：跳过存储，WARNING 日志，该图对应 OCR chunk 的 `image_id` 为 None（前端无缩略图，仅有文字）。
- 取图端点超时 / 网络抖动：前端图片加载失败，展示占位文案，不影响文字答案。

### REQ-NFR-004 安全

- 图片端点必须鉴权（Bearer Token），参照现有 RAG 文档端点的 `IsAuthenticated` 权限模式。
- 不得通过图片端点泄露与当前用户无关的图片（当前知识库无多租户隔离，所有已登录用户均可查看，与现有文档查询一致；如将来引入租户隔离，图片端点需同步跟进）。
- 图片字节响应时须设置 `Content-Disposition: inline`，禁止浏览器将其误判为可执行内容。

### REQ-NFR-005 可维护性

- 新增模型须手写 migration（不运行 `makemigrations`），遵循现有 `0036_add_rag_tables.py` 风格（TD-MIGRATION-001 约束）。
- 新增向量缓存条目（`_meta` dict）只追加 `image_id` 字段（可选，None 表示无图），不改变现有字段顺序，保持缓存加载向后兼容。

---

## 6. 约束与已决策事项

| 约束 | 描述 | 来源 |
|------|------|------|
| C-001 | 不改变现有 OCR 文字检索逻辑 | 业务目标（A 方案边界） |
| C-002 | 不引入多模态 embedding / VLM | 业务目标（B 方案排除） |
| C-003 | 图片 URL 不由 LLM 生成（防幻觉） | 业务目标第5点 |
| C-004 | 前端取图必须走 `api.js`，禁止裸 axios | 历史教训（freeark-frontend-bare-axios-session-trap） |
| C-005 | RagDocument 无 FileField，原文件不持久化 | 现有已决策（views_rag.py 注释，OQ-03） |
| C-006 | 新增 migration 手写，不跑 makemigrations | TD-MIGRATION-001 |
| C-007 | 图片字节不进入 `RagVectorCache` 内存 | REQ-NFR-001，Pi 5 内存约束 |
| C-008 | 图片存储失败 fail-open，不导致文档整体失败 | REQ-NFR-003 |
| C-009 | 取图端点须 IsAuthenticated 鉴权 | REQ-NFR-004 |

---

## 7. 非目标（明确排除，未来演进登记）

| 编号 | 内容 | 可能的未来版本 |
|------|------|-------------|
| NT-001 | 多模态向量检索（图文联合 embedding） | v1.5.x 或独立特性 |
| NT-002 | VLM 看图回答（B 方案） | v1.5.x 或独立特性 |
| NT-003 | 知识库管理页图片预览 | v1.4.2 或小版本 |
| NT-004 | 原始文档文件持久化 | 需重新评估存储策略 |
| NT-005 | 图片级检索（以图搜图） | 需多模态 embedding |
| NT-006 | 多租户图片隔离 | 随平台多租户演进 |

---

## 8. 开放问题（OQ）

见 `user_stories.md` 附录"开放问题"节，或直接在本文后置汇总：

| OQ 编号 | 问题 | 影响 | 建议决策时机 |
|--------|------|------|------------|
| OQ-IC-001 | 图片存储：DB BLOB 还是文件系统（媒体目录）？ | 影响架构设计、migration 形式、取图端点实现、磁盘管理 | 架构阶段决策 |
| OQ-IC-002 | 单图存储大小上限：需求建议 10MB，架构阶段可调整。Pi 5 典型文档图片（工程图纸 PNG）单张可达数 MB，需实测确认合理上限 | 影响 REQ-FUNC-001 降级边界 | 架构阶段决策（可带数据） |
| OQ-IC-003 | 扫描件整页栅格化 fallback（parse_pdf 路径3）产生的 png_bytes 是否也存储？这类图片面积大（150DPI A4~A0），存储成本高，但不存则扫描件回答无图可引 | 影响 REQ-FUNC-001 范围 | 产品决策（本确认门可一并决定） |
| OQ-IC-004 | `stream_end` 消息新增 `related_images` 字段，是否与历史消息持久化对齐？（当前 `chat_memory.append_message` 只存文字，历史加载时图片引用是否需要复现？） | 影响会话历史 UX；复现需要额外存储 message 的 image refs | 产品决策（建议本期不复现历史图片，只在实时回答中展示） |
| OQ-IC-005 | KnowledgeBaseView.vue 当前使用裸 axios（L195 `fetchDocuments`、L238 `doUpload` 等）。本特性不要求修复已有裸 axios（超出范围），但需确认：本次新增的取图调用走 `api.js` 即满足要求，还是需要一并整改 KnowledgeBaseView 中的裸 axios？ | 影响开发范围 | 产品决策（建议本特性仅管自己的取图调用，KnowledgeBaseView 裸 axios 整改另立 ticket） |
| OQ-IC-006 | 向量缓存 `RagVectorCache` 目前进程重启才更新。取图端点直接走 DB 查询（不过缓存），是否需要考虑 image_id 在缓存与 DB 之间的一致性问题？（影响最小：缓存存 image_id，DB 存图片字节，两者通过 image_id 关联，cache miss 不影响取图端点） | 低风险，需架构确认 | 架构阶段确认 |

---

## 9. 影响范围矩阵

| 组件 | 变更类型 | 描述 |
|------|---------|------|
| `api/models_rag.py` | 新增模型 | 新增 `RagImage`；`RagChunk` 新增 image 外键/引用字段 |
| `api/migrations/0037_rag_image.py`（手写） | 新增 migration | 创建 `rag_image` 表，`RagChunk` 新增字段 |
| `api/rag_service.py` | 修改 | `ParsedChunk` 新增 `img_bytes` 字段；`RagParser` 解析时保存图片字节；`RagIngestor` 入库时写 `RagImage`、建立关联；`RagVectorCache` meta 新增 `image_id`；`search_rag()` 返回值新增 `image_id` |
| `api/langgraph_chat/fa_tools.py` | 修改 | `search_sanheng_knowledge` 从纯文本返回改为结构化（文本 + `related_images`）；或在 consumer 层消费 `search_rag()` 结构化结果 |
| `api/consumers.py` | 修改 | `_finalize_turn` 的 `stream_end` 消息新增 `related_images` 字段 |
| `api/views_rag.py` | 新增端点 | `GET /api/rag/images/{id}/` 取图接口 |
| `api/urls.py` | 修改 | 注册取图端点路由 |
| `frontend/src/views/ChatView.vue` | 修改 | 气泡下方新增图片引用渲染区；`stream_end` 处理逻辑读取 `related_images` |
| `frontend/src/utils/api.js` | 可能修改 | 新增 `fetchRagImage(imageId)` helper（保证走 Token 鉴权） |
| `docs/requirements/v1.4.1_rag_image_citation/` | 新增 | 本文件及 user_stories.md |

---

*文档状态：DRAFT。等待产品负责人确认所有 OQ 决策后进入 APPROVED 状态，方可进入架构阶段。*
