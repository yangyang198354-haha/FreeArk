# 需求规格说明书 — v1.4.0 三恒知识专家 RAG 检索增强

**文档编号**: REQ-SPEC-RAG-v140-001
**项目名称**: FreeArk 三恒知识专家 RAG 检索增强（v1.4.0_sanheng_rag）
**版本**: 1.0.0
**状态**: DRAFT（待门控评审）
**创建日期**: 2026-06-16
**作者**: requirement-analyst (via pm-orchestrator)
**来源锁定**: 用户简报（2026-06-16，架构决策已由用户确认锁定，不得推翻）

---

## 版本历史

| 版本  | 日期       | 变更摘要                   |
|-------|------------|----------------------------|
| 1.0.0 | 2026-06-16 | 初始草稿，基于用户锁定简报 |

---

## 0. 问题陈述

### 0.1 背景现状

FreeArk 三恒知识专家 `sanheng-knowledge` 当前实现（代码锚定）：

- `api/langgraph_chat/prompts.py`（L89–100）将 `agents/sanheng-knowledge/KNOWLEDGE.md` 的静态文本整体拼入系统提示，无检索。
- `api/langgraph_chat/fa_tools.py`（L249）：`SANHENG_TOOLS: list = []`，三恒专家工具表为空，不调用任何工具。
- `agents/sanheng-knowledge/KNOWLEDGE.md` 文件头注明"通用行业知识草稿"，大量条目标注「待 FreeArk 补充」，不含项目专属知识。

痛点：
1. 专家只能依赖静态草稿知识，无法访问用户上传的真实三恒系统手册、参数表、故障码文档。
2. 需要更新知识时需修改代码或文件，无管理界面。
3. 无法根据具体提问检索最相关片段，上下文窗口浪费严重。

### 0.2 本版本目标

1. 为 FreeArk 建立 RAG 知识库（MySQL 两张表，进程内向量检索，无独立服务）。
2. 提供知识库管理页面，允许管理员上传 Word/PDF 文档，解析文字及图片 OCR，自动向量化入库。
3. 三恒知识专家通过 `search_sanheng_knowledge` 工具查询 RAG，先检索后作答，标注来源，无结果时明确说明不杜撰。
4. 保持 fail-open：RAG 不可达时聊天不报错，退回通用知识。

---

## 1. 范围与边界

### 1.1 本版本纳入范围

| 编号 | 功能域 | 摘要 |
|------|--------|------|
| REQ-FUNC-RAG-01 | 知识库数据模型 | MySQL 新增 RagDocument + RagChunk 两表，含 migration |
| REQ-FUNC-RAG-02 | 文档上传 API | POST /api/rag/documents/ 仅管理员，异步解析，状态机流转 |
| REQ-FUNC-RAG-03 | 文档列表 API | GET /api/rag/documents/ 仅管理员，返回文档台账含状态/chunk数 |
| REQ-FUNC-RAG-04 | 文档删除 API | DELETE /api/rag/documents/{id}/ 仅管理员，台账+向量一并删 |
| REQ-FUNC-RAG-05 | 文档解析引擎 | python-docx（.docx）+ PyMuPDF（.pdf），提取文字+图片 |
| REQ-FUNC-RAG-06 | 图片 OCR | rapidocr-onnxruntime（aarch64 验证后启用），图片全量 OCR 入分块 |
| REQ-FUNC-RAG-07 | 向量化入库 | 调用外部 embedding API（BAAI/bge-m3 via 硅基流动），向量 BLOB 存 RagChunk |
| REQ-FUNC-RAG-08 | 进程内向量检索 | 启动时加载向量入内存，numpy 余弦相似度 top-k，同进程零网络跳转 |
| REQ-FUNC-RAG-09 | 专家工具集成 | fa_tools.py 新增 @tool search_sanheng_knowledge，置入 SANHENG_TOOLS |
| REQ-FUNC-RAG-10 | 专家提示改写 | SYSTEM_PROMPT.langgraph.md：先检索后作答，标注来源，无结果明确说明 |
| REQ-FUNC-RAG-11 | fail-open 降级 | embedding/检索失败时退回通用知识并提示"未接入资料库" |
| REQ-FUNC-RAG-12 | 前端知识库管理页 | KnowledgeBaseView.vue，管理员可见，上传/列表/删除/重试 |
| REQ-FUNC-RAG-13 | 环境变量配置 | RAG_EMBEDDING_BASE_URL / RAG_EMBEDDING_MODEL / RAG_EMBEDDING_API_KEY 走 .env |

### 1.2 本版本不纳入范围

- 向量数据库（Chroma、Qdrant、Pinecone 等独立服务）—— 架构已锁定为 MySQL BLOB
- Docker 容器化 —— 禁止（物理机部署约束）
- DeepSeek embedding 接口 —— DeepSeek 无此接口，使用硅基流动
- 非管理员用户的知识库管理权限
- 文档版本控制（同名文档覆盖或多版本管理）—— 本期不纳入
- 向量索引（HNSW/IVF）—— 语料量级几百~千 chunk，余弦暴力搜索够用
- 实时流式 chunk 状态推送（WebSocket）—— 前端轮询状态即可

---

## 2. 功能需求

### 2.1 数据模型（REQ-FUNC-RAG-01）

#### 2.1.1 RagDocument — 文档台账

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BigAutoField | PK | |
| file_name | VARCHAR(255) | NOT NULL | 原始文件名 |
| file_size | BigIntegerField | NOT NULL | 字节数 |
| uploaded_by | FK → User | NOT NULL, ON DELETE SET NULL 改 SET_NULL | 上传人 |
| status | VARCHAR(20) | NOT NULL, DEFAULT='pending' | 状态机：pending / parsing / indexed / failed |
| error_message | TextField | BLANK=True | 失败时可读原因 |
| chunk_count | IntegerField | DEFAULT=0 | 成功入库的 chunk 数量 |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

状态机转换：
```
pending → parsing  (上传完成，后台任务启动)
parsing → indexed  (所有 chunk 写入成功)
parsing → failed   (任何步骤抛出异常)
failed  → parsing  (管理员触发重试)
```

索引：`status`（过滤用）、`created_at DESC`（列表排序用）

#### 2.1.2 RagChunk — 向量块

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BigAutoField | PK | |
| document | FK → RagDocument | NOT NULL, ON DELETE CASCADE | |
| chunk_index | IntegerField | NOT NULL | 块在文档中的序号（0-based）|
| content | TextField | NOT NULL | chunk 文字内容 |
| embedding | BinaryField | NOT NULL | numpy float32 序列化 BLOB |
| page_or_section | VARCHAR(100) | BLANK=True | 来源定位（如"第3页"/"第2节"）|
| is_image_ocr | BooleanField | DEFAULT=False | True = 来自图片 OCR |
| created_at | DateTimeField | auto_now_add | |

索引：`document_id`（DELETE 级联时效率）

**Migration 编号**: 0036（依赖 0035_workorder_proposed_write）

### 2.2 文档上传 API（REQ-FUNC-RAG-02）

**端点**: `POST /api/rag/documents/`
**权限**: `IsAdminUser`（复用 DRF `permissions.IsAdminUser`，非管理员返回 403）
**请求**: multipart/form-data，字段 `file`（单文件）
**前端校验**（在浏览器侧，不依赖后端）：
- 文件类型：`.docx` 或 `.pdf`（MIME 类型白名单）
- 文件大小：≤ 50 MB

**后端行为**:
1. 校验文件类型（扩展名 + MIME 双重校验）不合法返回 400。
2. 校验大小不合法返回 400。
3. 创建 `RagDocument`（status=pending）。
4. 启动后台异步任务（`threading.Thread` 守护线程，或 Django `transaction.on_commit` + 线程）执行解析+向量化入库。
5. 立即返回 201 + 文档台账（含 id、status=pending）。

**响应 201**:
```json
{
  "id": 1,
  "file_name": "三恒系统维保手册.pdf",
  "file_size": 2048000,
  "status": "pending",
  "chunk_count": 0,
  "created_at": "2026-06-16T10:00:00Z"
}
```

**错误响应**:
- 400: `{"error": "不支持的文件类型，仅接受 .docx 和 .pdf"}`
- 400: `{"error": "文件超过 50MB 限制"}`
- 403: `{"detail": "Authentication credentials were not provided."}` (DRF 默认)

### 2.3 文档列表 API（REQ-FUNC-RAG-03）

**端点**: `GET /api/rag/documents/`
**权限**: `IsAdminUser`
**响应 200**（按 `created_at DESC` 排序）:
```json
[
  {
    "id": 1,
    "file_name": "三恒系统维保手册.pdf",
    "file_size": 2048000,
    "uploaded_by": "admin",
    "status": "indexed",
    "chunk_count": 47,
    "error_message": "",
    "created_at": "2026-06-16T10:00:00Z",
    "updated_at": "2026-06-16T10:02:30Z"
  }
]
```

### 2.4 文档删除 API（REQ-FUNC-RAG-04）

**端点**: `DELETE /api/rag/documents/{id}/`
**权限**: `IsAdminUser`
**行为**:
1. 删除 `RagDocument` → 因 FK ON DELETE CASCADE，`RagChunk` 级联删除。
2. 触发内存向量缓存刷新（重新从 DB 加载已 indexed 的 chunk 向量）。
3. 返回 204 No Content。
**错误**: 404（文档不存在）

### 2.5 文档重试 API（REQ-FUNC-RAG-05）

**端点**: `POST /api/rag/documents/{id}/retry/`
**权限**: `IsAdminUser`
**条件**: 仅 status=failed 的文档可重试
**行为**: 重置 status=pending，清空 error_message，重启后台解析任务。
**错误**: 400（status 非 failed 时）、404（文档不存在）

### 2.6 文档解析引擎（REQ-FUNC-RAG-05 / REQ-FUNC-RAG-06）

**解析流程**（后台线程执行）:

```
文档入库(status=pending)
    ↓ 更新 status=parsing
    ↓
[扩展名判断]
  .docx → python-docx 逐段提取：
          - 段落文字 → chunk（按段落或按字数窗口合并，见 §2.6.1）
          - 图片对象（InlineShape）→ 提取图片字节 → rapidocr OCR → 作为独立 chunk（is_image_ocr=True）
  .pdf  → PyMuPDF 逐页提取：
          - 页面文字块 → chunk（按页或按字数窗口，见 §2.6.1）
          - 页面图片列表 → 各图片 → rapidocr OCR → 独立 chunk（is_image_ocr=True）
    ↓
[向量化]
  每个 chunk 调用 embedding API（langchain-openai OpenAIEmbeddings，endpoint/model/key 来自 .env）
  → 向量 float32 数组 → numpy.array.tobytes() 存 BinaryField
    ↓
全部成功 → status=indexed，chunk_count=N
任一步骤异常 → status=failed，error_message=可读异常文本（含步骤名称）
```

#### 2.6.1 分块策略

- **默认 chunk 大小**：500 中文字符（约 250 Token），重叠 50 字符。
- **分块单位**：以段落/文字块为分割基础，不在段落中间强制切断，若段落超过 500 字则按 500 字滑动窗口切分。
- **来源元数据**：
  - `.docx`：`page_or_section = "段落 {n}"` （段落序号）
  - `.pdf`：`page_or_section = "第 {n} 页"` （页码 1-based）
  - 图片 OCR：`page_or_section = "第 {n} 页 图片{m}"` 或 `"段落 {n} 图片{m}"`，`is_image_ocr=True`

#### 2.6.2 OCR 纪律（aarch64 约束）

- OCR 仅在文档入库（冷路径）执行，不在查询路径执行。
- `rapidocr-onnxruntime` 与 `onnxruntime` **必须先在树莓派 Pi 5（aarch64）上真装、真 import、真跑一次 OCR 验证**，确认 wheel 可安装且产出正确结果后方可在生产启用。
- devops 阶段须将"Pi 上验证 rapidocr-onnxruntime/onnxruntime aarch64 可用"列为部署前置任务（阻塞性，未验证通过则不上线）。
- requirements.txt 中 rapidocr-onnxruntime / onnxruntime 须附注释，说明 aarch64 纪律来源。

### 2.7 进程内向量检索（REQ-FUNC-RAG-08）

**加载机制**:
- Django 启动时（AppConfig.ready() 或首次 search 调用时懒加载），从 DB 读取所有 status=indexed 的 `RagChunk`，将 embedding BinaryField → numpy float32 数组加载入内存（进程级变量）。
- 文档删除或新文档 indexed 后，触发缓存刷新（重载）。
- 向量语料量级：几百~千 chunk，内存占用约 1~5 MB（dim=1024，float32），不构成 Pi 内存压力。

**检索逻辑（search_sanheng_knowledge tool 内部）**:
```
query_text → embedding API → query_vector (float32 array, dim=1024)
all_chunk_vectors (内存) → 逐一计算余弦相似度
top-k (k=5, 可配置) 按相似度降序
返回 [{"content": ..., "source": "文件名 · 第X页", "is_image_ocr": bool, "score": float}]
```

**相似度阈值**（可配置）：score < 0.3 的结果丢弃（避免无关内容入答）。

**fail-open**:
- embedding API 调用失败（网络/key 无效）→ 捕获异常，返回 `{"chunks": [], "degraded": True}`
- 内存向量为空（无文档入库）→ 直接返回 `{"chunks": [], "degraded": False}`
- 任何情况均不抛出到编排层，不打挂聊天。

### 2.8 专家工具集成（REQ-FUNC-RAG-09）

在 `api/langgraph_chat/fa_tools.py` 新增：

```python
@tool
def search_sanheng_knowledge(query: str) -> dict:
    """在三恒知识库中检索与 query 相关的文档片段，用于辅助原理/参数/故障码解答。
    返回最相关的 chunk 文本列表及来源；库为空或不可达时返回空列表（不报错）。"""
    ...
```

并在 `SANHENG_TOOLS = [search_sanheng_knowledge]` 中置入。

**工具返回格式**（给 LLM 的 ToolMessage content）:
```
[检索到 3 条相关内容]
[1] 来源: 三恒系统维保手册.pdf · 第5页
    冷凝水管道应定期检查，夏季制冷工况下...

[2] 来源: 三恒系统维保手册.pdf · 第5页 图片1（图片OCR）
    供回水温度设定范围：供水 7~12℃，回水...

[3] 来源: 三恒操作指南.docx · 段落18
    恒湿系统加湿量阈值...

或（无结果）：
[知识库中未找到与该问题相关的内容]
```

### 2.9 专家提示改写（REQ-FUNC-RAG-10）

修改 `agents/sanheng-knowledge/SYSTEM_PROMPT.langgraph.md`，新增行为约定：

1. **先检索后作答**：收到与三恒系统相关的具体问题（参数值、故障码、操作流程），调用 `search_sanheng_knowledge` 检索后再作答。
2. **据命中作答**：以检索到的 chunk 内容为主要依据，引用来源（文件名+位置）。
3. **无命中明确说明**：检索返回空时，明确告知"知识库中未找到相关内容"，不编造参数值/故障码/阈值。
4. **降级提示**：工具返回 degraded=True 时，告知用户"目前未接入知识资料库，以下仅为通用知识参考"，继续依赖 KNOWLEDGE.md 背景知识作答。
5. **KNOWLEDGE.md 保留**：作为原理级通用背景兜底，仍由 `prompts.py` 拼入，不删除。

### 2.10 前端知识库管理页（REQ-FUNC-RAG-12）

**新增文件**: `FreeArkWeb/frontend/src/views/KnowledgeBaseView.vue`

**路由**: `/admin/knowledge-base`，`meta: { requiresAuth: true, requiresAdmin: true }`

**页面功能**:
1. **文档列表**：表格展示（文件名、大小、上传人、状态、chunk 数、上传时间）。状态用 Element Plus `el-tag` 区分颜色（pending=info, parsing=warning, indexed=success, failed=danger）。
2. **上传入口**：`el-upload` 拖拽或点击选择，前端校验类型（.docx/.pdf）和大小（≤50MB），校验失败弹 `el-message` 错误，不调接口。
3. **删除操作**：列表操作列"删除"按钮，`el-popconfirm` 二次确认，确认后调 DELETE 接口，刷新列表。
4. **重试操作**：status=failed 的行显示"重试"按钮，调 POST retry 接口，刷新列表。
5. **失败原因**：status=failed 时，操作列显示"查看原因"按钮，点击弹 `el-dialog` 展示 error_message。
6. **状态轮询**：对 status=parsing 的文档，每 5 秒轮询列表接口，直到状态变为 indexed 或 failed。
7. **导航入口**：在 `DeviceManagementDeviceListView.vue`（或统一 Layout 导航）适当位置增加「知识库管理」导航项，仅 admin 用户可见。

**管理员路由守卫**（新增或复用现有机制）：非管理员访问 `/admin/knowledge-base` 时重定向至首页（不展示 404）。

### 2.11 环境变量配置（REQ-FUNC-RAG-13）

新增 `.env` 变量（绝不入 git / HTTP 响应 / 前端）：

| 变量名 | 必填 | 示例值 | 说明 |
|--------|------|--------|------|
| RAG_EMBEDDING_BASE_URL | 是 | `https://api.siliconflow.cn/v1` | embedding API 端点（OpenAI 兼容） |
| RAG_EMBEDDING_MODEL | 是 | `BAAI/bge-m3` | embedding 模型名 |
| RAG_EMBEDDING_API_KEY | 是 | `sk-...` | embedding API 密钥 |
| RAG_TOP_K | 否 | `5` | 检索返回 top-k，默认 5 |
| RAG_SCORE_THRESHOLD | 否 | `0.3` | 相似度过滤阈值，默认 0.3 |
| RAG_CHUNK_SIZE | 否 | `500` | 分块字符数，默认 500 |
| RAG_CHUNK_OVERLAP | 否 | `50` | 分块重叠字符数，默认 50 |

`settings.py` 读取：
```python
RAG_EMBEDDING_BASE_URL = os.environ.get('RAG_EMBEDDING_BASE_URL', '')
RAG_EMBEDDING_MODEL = os.environ.get('RAG_EMBEDDING_MODEL', 'BAAI/bge-m3')
RAG_EMBEDDING_API_KEY = os.environ.get('RAG_EMBEDDING_API_KEY', '')
RAG_TOP_K = int(os.environ.get('RAG_TOP_K', '5'))
RAG_SCORE_THRESHOLD = float(os.environ.get('RAG_SCORE_THRESHOLD', '0.3'))
RAG_CHUNK_SIZE = int(os.environ.get('RAG_CHUNK_SIZE', '500'))
RAG_CHUNK_OVERLAP = int(os.environ.get('RAG_CHUNK_OVERLAP', '50'))
```

---

## 3. 非功能需求

### 3.1 性能

- **入库延迟**：单文档（10页 PDF，含5张图片）完整解析+OCR+向量化端到端 ≤ 120秒（Pi 上）。可接受慢，不阻塞请求。
- **检索延迟**：进程内余弦搜索（1000 chunk 规模）≤ 10ms；embedding API 调用（网络）≤ 3秒（超时设 5秒）。
- **内存**：1000 chunk × 1024 dim × 4 bytes ≈ 4MB，可接受。

### 3.2 安全

- `RAG_EMBEDDING_API_KEY` 遵循与 `DEEPSEEK_API_KEY` 相同的纪律：仅走 `.env`，绝不入 git、HTTP 响应、日志、前端变量。
- 上传 API 双重校验文件类型（扩展名 + MIME），防止伪造扩展名上传恶意文件。
- 文件内容仅用于解析，不持久化原始文件到磁盘（提取文字后即释放内存）。
- 管理员鉴权复用 `IsAdminUser`，与现有角色体系一致。

### 3.3 可靠性

- 入库失败：状态机写入 failed + error_message，不影响已入库文档，支持重试。
- 检索降级：fail-open，不打挂聊天（与现有提示装载兜底哲学一致，见 `prompts.py` L106–108）。
- 重启安全：向量缓存在启动时从 DB 重建，重启不丢数据。

### 3.4 部署约束（aarch64 / 物理机）

- **禁 Docker**，物理机部署，生产=树莓派 Pi 5（aarch64）。
- `rapidocr-onnxruntime` + `onnxruntime` 必须先在 Pi 上验证 aarch64 wheel 可安装、可 import、可正确推理，验证通过后方可加入 requirements.txt 并上线。
- `python-docx`、`PyMuPDF`、`numpy` 均需确认 Pi 上可安装（numpy 已有依赖，需确认版本兼容性）。
- **langchain-openai 已是现有依赖**（requirements.txt L51），embedding 通过 `langchain_openai.OpenAIEmbeddings` 复用，零新增 ML 依赖。
- **部署一律 git pull**（plink + git pull + 重启服务），禁止 pscp 逐文件上传。

### 3.5 可维护性

- 新增文件聚焦于 `api/views_rag.py`、`api/serializers_rag.py`、`api/rag_service.py`（解析+向量化业务逻辑），不修改现有 `views.py`、`orchestrator.py`。
- 对 `fa_tools.py` 仅新增 `search_sanheng_knowledge` 函数和 `SANHENG_TOOLS` 修改，不改现有工具。
- 对 `urls.py` 仅追加 rag 路由段，不修改现有路由。

---

## 4. 开放决策（OQ）

以下为当前已知的开放问题，需在开发前确认或在架构阶段决策：

| 编号 | 问题 | 影响范围 | 默认方案（如无用户反馈） |
|------|------|----------|--------------------------|
| OQ-01 | 向量缓存刷新时机：新文档入库触发实时刷新 vs 定时重载 | 检索实时性 | 实时刷新（indexed 后立即重载缓存） |
| OQ-02 | 并发入库：多文档同时上传时线程安全策略（缓存锁） | 数据一致性 | threading.Lock 保护缓存写入 |
| OQ-03 | 文件存储：原始文件是否持久化到磁盘（供重试用） | 重试能力 | 不持久化原始文件；重试需重新上传（本期简化） |
| OQ-04 | PyMuPDF 许可证：AGPL v3（商业使用需购买商业许可或开源） | 合规 | 确认使用场景合规（内部运维平台，非公开分发） |
| OQ-05 | embedding dim：BAAI/bge-m3 实际输出维度（通常 1024） | BLOB 大小计算 | 1024 dim（4096 bytes/chunk，1000 chunk ≈ 4MB） |
| OQ-06 | 导航位置：「知识库管理」放在哪个菜单分组（设备管理/系统管理/独立） | 前端 UX | 放入「方舟智能体」分组（与 v1.3.0 巡检日志/工单一起） |
| OQ-07 | rapidocr 不可用时的兜底：跳过图片 OCR 继续入库 vs 整体失败 | 部分入库 | 跳过单张图片 OCR 并记录 warning，不导致整体 failed |

---

## 5. 文件影响范围汇总

### 5.1 后端新增文件

| 文件路径 | 说明 |
|----------|------|
| `FreeArkWeb/backend/freearkweb/api/models_rag.py` | RagDocument + RagChunk 模型 |
| `FreeArkWeb/backend/freearkweb/api/migrations/0036_add_rag_tables.py` | DB migration |
| `FreeArkWeb/backend/freearkweb/api/serializers_rag.py` | RagDocument 序列化器 |
| `FreeArkWeb/backend/freearkweb/api/views_rag.py` | 上传/列表/删除/重试 API |
| `FreeArkWeb/backend/freearkweb/api/rag_service.py` | 解析引擎 + 向量化 + 检索逻辑 |

### 5.2 后端修改文件

| 文件路径 | 改动摘要 |
|----------|----------|
| `FreeArkWeb/backend/freearkweb/api/urls.py` | 追加 rag/ 路由段 |
| `FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py` | 新增 search_sanheng_knowledge @tool，修改 SANHENG_TOOLS |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | 追加 RAG_* 配置项读取 |
| `FreeArkWeb/backend/requirements.txt` | 追加 python-docx, PyMuPDF, rapidocr-onnxruntime, onnxruntime（含 aarch64 警告注释） |

### 5.3 前端新增文件

| 文件路径 | 说明 |
|----------|------|
| `FreeArkWeb/frontend/src/views/KnowledgeBaseView.vue` | 知识库管理页 |

### 5.4 前端修改文件

| 文件路径 | 改动摘要 |
|----------|----------|
| `FreeArkWeb/frontend/src/router/index.js` | 追加 /admin/knowledge-base 路由 |
| `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` 或 Layout | 追加「知识库管理」导航项（admin only）|

### 5.5 Agents 修改文件

| 文件路径 | 改动摘要 |
|----------|----------|
| `agents/sanheng-knowledge/SYSTEM_PROMPT.langgraph.md` | 新增 search_sanheng_knowledge 工具使用约定 + 来源引用 + 降级提示 |

---

## 6. 验收标准（与用户故事对应）

详见 `user_stories.md`（Given/When/Then 格式）。

| 用户故事 | 核心 AC |
|----------|---------|
| US-1 管理员上传文档 | 非管理员 403；非法类型/超限前端拦截；上传后状态 parsing→indexed + chunk数 |
| US-2 文字+图片 OCR 解析 | 含中文图片 PDF 入库后图中文字被检索到并标「图片OCR」；失败时 failed + 可读原因 + 可重试 |
| US-3 专家检索增强作答 | 库中有答案时先检索后作答标来源；无内容明确说不杜撰；RAG 不可达时聊天不报错降级通用 |
| US-4 管理员删除文档 | 删除后台账+向量一并删，后续检索不再命中 |

---

## 附录 A：用户简报原文引用

本文档所有需求均来自用户 2026-06-16 提供的架构决策简报，关键锁定决策：

- B档轻量架构：MySQL BLOB + 进程内 numpy 余弦，不用向量数据库
- embedding: 硅基流动 BAAI/bge-m3，走 .env，复用 langchain-openai
- OCR: rapidocr-onnxruntime，aarch64 验证后方可启用
- 解析: python-docx + PyMuPDF
- 专家接入: SANHENG_TOOLS 新增 @tool，不改编排核心
- fail-open: 降级不打挂聊天
- 仅管理员可管理知识库
- 部署: git pull + 重启，禁止 pscp
