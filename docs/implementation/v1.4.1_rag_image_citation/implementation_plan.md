<!--
@module MOD-141-01 ~ MOD-141-11
@author sub_agent_software_developer
status: WRITTEN
feature: v1.4.1_rag_image_citation（三恒知识库 RAG 图片引用回溯）
created: 2026-06-23
-->

# 实现计划 — v1.4.1 三恒知识库 RAG 图片引用回溯

**文档编号**：IMPL-PLAN-RAG-v141-001  
**基线架构文档**：ARCH-DES-RAG-v141-001 (DRAFT)，ARCH-MOD-RAG-v141-001 (DRAFT)  
**实现日期**：2026-06-23  

---

## 一、实现概览

| 项目 | 数量 |
|------|------|
| 涉及模块 | 11 个（MOD-141-01 ~ MOD-141-11）|
| 涉及文件 | 11 个（9 个后端 + 2 个前端）|
| 新增文件 | 2 个（migration 0039_rag_image.py；docs/implementation_plan.md）|
| 修改文件 | 9 个后端 + 2 个前端 |
| 新增 DB 表 | 1 个（api_ragimage）|
| 新增 DB 列 | 1 个（api_ragchunk.image_id）|

---

## 二、实现顺序（按拓扑排序）

依赖关系无循环，拓扑顺序如下：

```
MOD-141-01（models_rag.py）     — 无依赖，最先实现
    ↓
MOD-141-02（0039_rag_image.py） — 依赖 MOD-141-01 中的模型定义
MOD-141-03（rag_service.py）    — 依赖 MOD-141-01（RagImage ORM）
    ↓
MOD-141-04（fa_tools.py）       — 依赖 MOD-141-03（search_rag 返回 image_id）
    ↓
MOD-141-05（orchestrator.py）   — 依赖 MOD-141-04（get_last_search_images）
    ↓
MOD-141-06（adapter.py）        — 依赖 MOD-141-05（State.related_images）
    ↓
MOD-141-07（consumers.py）      — 依赖 MOD-141-06（related_images kind 流出）
MOD-141-08（views_rag.py）      — 依赖 MOD-141-01（RagImage ORM）
    ↓
MOD-141-09（urls.py）           — 依赖 MOD-141-08（RagImageView）

前端（独立依赖链）：
MOD-141-11（api.js）            — 无后端依赖
    ↓
MOD-141-10（ChatView.vue）      — 依赖 MOD-141-11（fetchRagImage）
```

---

## 三、模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-141-01 | models_rag.py | FreeArkWeb/backend/freearkweb/api/models_rag.py | — | M | PLANNED |
| 2 | MOD-141-02 | 0039_rag_image.py | FreeArkWeb/backend/freearkweb/api/migrations/0039_rag_image.py | MOD-141-01 | L | PLANNED |
| 3 | MOD-141-03 | rag_service.py | FreeArkWeb/backend/freearkweb/api/rag_service.py | MOD-141-01 | H | PLANNED |
| 4 | MOD-141-04 | fa_tools.py | FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py | MOD-141-03 | M | PLANNED |
| 5 | MOD-141-05 | orchestrator.py | FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py | MOD-141-04 | M | PLANNED |
| 6 | MOD-141-06 | adapter.py | FreeArkWeb/backend/freearkweb/api/langgraph_chat/adapter.py | MOD-141-05 | M | PLANNED |
| 7 | MOD-141-07 | consumers.py | FreeArkWeb/backend/freearkweb/api/consumers.py | MOD-141-06 | M | PLANNED |
| 8 | MOD-141-08 | views_rag.py | FreeArkWeb/backend/freearkweb/api/views_rag.py | MOD-141-01 | L | PLANNED |
| 9 | MOD-141-09 | urls.py | FreeArkWeb/backend/freearkweb/api/urls.py | MOD-141-08 | L | PLANNED |
| 10 | MOD-141-11 | api.js | FreeArkWeb/frontend/src/utils/api.js | — | L | PLANNED |
| 11 | MOD-141-10 | ChatView.vue | FreeArkWeb/frontend/src/views/ChatView.vue | MOD-141-11 | M | PLANNED |

---

## 四、每个文件的变更摘要

### MOD-141-01: models_rag.py

**变更类型**：修改（新增 + 追加字段）  
**关键变更**：
- 新增 `RagImage` 模型：BinaryField 存图片字节，CASCADE 级联删除，显式 `db_table='api_ragimage'`
- `RagChunk` 追加 `image` FK（`null=True, blank=True, on_delete=SET_NULL`）

**注意**：现有 `RagDocument` 的 `db_table = 'rag_document'`，`RagChunk` 的 `db_table = 'rag_chunk'`。新增的 `RagImage` 按照架构设计使用 `db_table = 'api_ragimage'`（架构文档明确指定），与现有表命名风格不同，属于架构决策，无需偏差标注。

### MOD-141-02: 0039_rag_image.py

**变更类型**：新增（手写迁移）  
**关键变更**：
- Step 1：CreateModel RagImage（含所有字段）
- Step 2：AddIndex（ragimage_document_idx）
- Step 3：AddField RagChunk.image（FK，null=True）
- `dependencies = [('api', '0038_chatsession_title')]`

**注意**：迁移中 `to='api.ragdocument'` 需要与 ORM 层面的模型引用一致（Django 使用 `app_label.ModelName`，与 `db_table` 无关）。

### MOD-141-03: rag_service.py

**变更类型**：修改（多处扩展，不改现有接口签名）  
**关键变更**：
- 新增常量 `MAX_IMAGE_BYTES = 10 * 1024 * 1024`
- `ParsedChunk` 新增 3 个字段：`img_bytes`, `img_format`, `img_size`
- 新增 `_detect_image_format(img_bytes)` 辅助函数
- 新增 `RagParser._try_save_image_bytes()` 方法（大小校验 + fail-open）
- 修改 `RagParser.parse_docx()`：附加 img_bytes 到 OCR chunk
- 修改 `RagParser.parse_pdf()`：路径 1/2/3 均附加 img_bytes
- 修改 `RagIngestor.ingest()`：Step 4a 写 RagImage，建立 hash→RagImage 映射
- 修改 `RagVectorCache.load()`：select_related('image')，meta 追加 image_id
- 修改 `RagVectorCache.search()`：result dict 追加 image_id

### MOD-141-04: fa_tools.py

**变更类型**：修改（新增 ContextVar + 辅助函数；扩展 search_sanheng_knowledge 内部逻辑）  
**关键变更**：
- 新增 `import contextvars`
- 新增 `_last_search_images_var: ContextVar[list]`
- 新增 `get_last_search_images() -> list`（读取并清零）
- 修改 `search_sanheng_knowledge`：收集 related_images 写入 ContextVar，但 str 返回值不含 image_id

### MOD-141-05: orchestrator.py

**变更类型**：修改（State 新增字段；_expert 提取 side-channel；_aggregate 汇聚去重）  
**关键变更**：
- `State` 新增 `related_images: List[dict]`（无 reducer）
- 新增 `from .fa_tools import get_last_search_images`
- `_expert()`：工具循环中对 `search_sanheng_knowledge` 额外调 `get_last_search_images()`，收集到 `accumulated_images`；return 时带 `"related_images"` 字段
- `_aggregate()`：收集所有 related_images，全局去重，return 时带 `"related_images"` 字段

### MOD-141-06: adapter.py

**变更类型**：修改（`_drive()` 结尾新增 related_images yield，合并 aget_state 调用）  
**关键变更**：
- `_drive()` astream 循环结束后：`aget_state(config)` 读 `related_images`，yield `("related_images", json_str)`
- 与 `seen_any` 兜底的 `aget_state` 调用合并为一次（避免两次 DB round-trip）

### MOD-141-07: consumers.py

**变更类型**：修改（最小化变更：3 处）  
**关键变更**：
- `connect()` 初始化块末尾追加 `self._related_images: list = []`
- `_pump()` 新增 `elif kind == 'related_images':` 分支（存实例变量，不转发 WS）
- `_finalize_turn()` 签名新增 `related_images: list | None = None`，stream_end 载荷条件附加；`_handle_chat()` 和 `_handle_confirm()` 相应调整

**WS 验证要求**：本文件修改后须本地真 Redis 验 WS 收发（不可仅用 InMemoryChannelLayer）。在无真实 Redis 的 CI 环境中此项无法自动验证，已在 code_review_report.md 中明确标注。

### MOD-141-08: views_rag.py

**变更类型**：修改（新增 RagImageView 类）  
**关键变更**：
- 新增 `RagImageView(APIView)`：IsAuthenticated 权限、GET 方法、DB 直查 `RagImage.objects.only(...).get(id=image_id)`、动态 Content-Type、`Content-Disposition: inline`、`Cache-Control: no-store`、404 降级

### MOD-141-09: urls.py

**变更类型**：修改（追加 1 条路由）  
**关键变更**：
- 追加 `path('rag/images/<int:image_id>/', views_rag.RagImageView.as_view(), name='rag-image-detail')`

### MOD-141-11: api.js

**变更类型**：修改（新增 fetchRagImage 导出函数）  
**关键变更**：
- 新增 `export async function fetchRagImage(imageId)`：调用 `authenticatedFetch`（带 Bearer Token），Blob 响应，返回 Blob 对象
- 使用 `authenticatedFetch` 而非 `api.get()`（因为 `api.get()` 强制 `.json()` 解析，Blob 需要直接返回 Response）

### MOD-141-10: ChatView.vue

**变更类型**：修改（stream_end 处理 + 气泡模板 + loadImageBlobUrl 方法 + onUnmounted 释放）  
**关键变更**：
- 助手消息 push 时新增 `relatedImages: []`, `imageUrls: {}`
- `handleSend()` 中新建助手消息 push 时追加这两个字段
- `mapHistoryToMessage()` 追加这两个字段
- `stream_end` case：读 `data.related_images`，调用 `loadImageBlobUrl()` 批量预加载 Blob URL
- 新增 `loadImageBlobUrl(imageId)` 方法（`fetchRagImage(imageId)`，`URL.createObjectURL`，失败 null）
- 气泡模板追加图片引用区（`v-if="msg.relatedImages && msg.relatedImages.length > 0"`，`el-image` + `#error` slot）
- `onUnmounted` 释放所有 Blob URL

---

## 五、关键接口定义

| 接口 ID | 签名 | 实现位置 |
|---------|------|---------|
| IFC-141-301 | `_try_save_image_bytes(bytes, str, str) -> (bytes|None, str)` | rag_service.RagParser |
| IFC-141-302 | `_detect_image_format(bytes) -> str` | rag_service（模块级函数）|
| IFC-141-401 | `get_last_search_images() -> list[dict]` | fa_tools |
| IFC-141-402 | ContextVar 写（search_sanheng_knowledge 内部） | fa_tools |
| IFC-141-801 | `RagImageView.get(request, image_id) -> HttpResponse` | views_rag |
| IFC-141-1101 | `fetchRagImage(imageId) -> Promise<Blob>` | api.js |

---

## 六、测试验证方法

### 后端单元测试

```bash
# Windows PowerShell 语法
cd C:\Users\胖子熊\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
$env:FREEARK_POC_MOCK="1"
$env:LANGGRAPH_USE_FAKE_LLM="True"
python manage.py test api --verbosity=2 2>&1 | tail -30
```

基线要求：通过数 >= 1778，失败数 = 0。

### WS / Channels 集成验证（需真 Redis，CI 不可自动化）

consumers.py 修改后，必须在本地开发环境（有 Redis）手动验证：
1. 知识专家问答流程：发送一条触发 `sanheng-knowledge` 路由的消息
2. 验证 `stream_end` 载荷中是否携带 `related_images` 字段（有相关文档入库时）
3. 验证无知识库内容时，`stream_end` 不含 `related_images` 字段（向后兼容）

### 前端端到端验证

1. 知识库上传一份含图片的 PDF/DOCX（通过管理员端点）
2. 触发一条触发知识专家的问题
3. 验证聊天气泡下方出现图片缩略图区
4. 验证图片能正常加载（通过 api.js fetchRagImage）
5. 验证加载失败时显示"图片暂时无法显示"占位

---

## 七、架构偏差记录

| 偏差ID | 偏差描述 | 原 ADR 决策 | 偏差原因 |
|--------|---------|-----------|---------|
| DEV-001 | api.js `fetchRagImage` 使用 `authenticatedFetch` 而非 `api.get()` | 模块设计建议通过 api 实例调用 | `api.get()` 强制 `.json()` 解析，Blob 响应无法用此路径；`authenticatedFetch` 是 `api.get()` 的底层实现，Bearer Token 行为等价，满足 C-004 约束 |
| DEV-002 | `_handle_confirm()` 调用 `_finalize_turn` 时传 `related_images=[]` | 架构文档说 confirm 路径可携带 related_images | confirm 路径（写确认门）不涉及知识专家，related_images 恒为空；此轮的 _related_images 在 _handle_chat() 已被重置，传空列表是正确且安全的行为 |

---

*本文档由 sub_agent_software_developer 生成，v1.4.1_rag_image_citation 特性实现。*
