<!--
@module MOD-141-01 ~ MOD-141-11
@author sub_agent_software_developer
status: WRITTEN
feature: v1.4.1_rag_image_citation（三恒知识库 RAG 图片引用回溯）
created: 2026-06-23
-->

# 代码评审报告 — v1.4.1 三恒知识库 RAG 图片引用回溯

**文档编号**：CODE-REVIEW-RAG-v141-001  
**评审日期**：2026-06-23  
**后端测试结果**：Ran 1802 tests in 282.352s — **OK (skipped=19)**，0 failures  

---

## 评审摘要

| 维度 | 总体平均分 |
|------|-----------|
| Correctness（正确性） | 8.5/10 |
| Security（安全性） | 9.0/10 |
| Performance（性能） | 8.0/10 |
| Maintainability（可维护性） | 8.5/10 |
| Test Coverage（可测试性） | 7.5/10 |

| 严重级别 | 发现数 | 已修复 | 遗留 |
|---------|--------|--------|------|
| CRITICAL | 2 | 2 | 0 |
| MAJOR | 3 | 1 | 2 |
| MINOR | 5 | 0 | 5（已记录）|

---

## 按模块评审详情

---

### MOD-141-01: RagImage 模型 + RagChunk.image FK
**文件**：`FreeArkWeb/backend/freearkweb/api/models_rag.py`

- Correctness: 9/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 9/10
- Test Coverage: 8/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-001 | MINOR | models_rag.py: RagImage | `image_data = models.BinaryField()` 无 `editable=False` 标注，Django Admin 可能尝试渲染 BLOB 字段。对该项目影响有限（无 Admin 页）。 | DOCUMENTED |
| FND-002 | MINOR | models_rag.py: RagImage | `image_format` 无 `choices` 约束，应用层约束 ('png'/'jpeg'/'other') 依赖 `_detect_image_format` 函数而非 DB 层 CHECK。可接受，但建议后续加 choices 枚举。 | DOCUMENTED |

---

### MOD-141-02: Migration 0039_rag_image
**文件**：`FreeArkWeb/backend/freearkweb/api/migrations/0039_rag_image.py`

- Correctness: 10/10
- Security: 10/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage: 9/10

无 finding。手写 migration，依赖 0038_chatsession_title，3 步操作顺序正确（先建表，后加索引，最后追加 FK 列）。

---

### MOD-141-03: RagParser + RagVectorCache + RagIngestor 图片扩展
**文件**：`FreeArkWeb/backend/freearkweb/api/rag_service.py`

- Correctness: 8/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-003 | CRITICAL | rag_service.py: ingest() Step 4a | 原实现 `for chunk, _vec in all_data:` 遗漏了 `img_only_data`（纯图片占位 chunk），导致这类 chunk 的 RagImage 行永远不会被写入。修复：改为 `for chunk, _vec in combined_for_images`（`= all_data_with_img_only + img_only_data`）。 | FIXED |
| FND-004 | CRITICAL | rag_service.py: ingest() Step 4 | 原 `for idx, (chunk, vec) in enumerate(all_data):` 带 `if not chunk.content: continue`，现统一改为仅遍历 `all_data_with_img_only`（已过滤掉纯图片占位 chunk），逻辑更清晰。 | FIXED |
| FND-005 | MAJOR | rag_service.py: _try_save_image_bytes | 函数内 `image_counter` 未更新（计数器在 ingest() 外层，`_try_save_image_bytes` 只返回 `(rag_image_obj, img_key)` 而不更新计数器）。实际 image_counter 在 Step 4a 循环内自增，逻辑已正确；此为代码阅读歧义。 | DOCUMENTED |
| FND-006 | MINOR | rag_service.py: parse_docx | 图片格式推断依赖文件扩展名 (`rel_type.split('/')[-1]`)；某些 DOCX 文件 rel_type 可能不规范。`_detect_image_format` 已作为兜底，风险可接受。 | DOCUMENTED |
| FND-007 | MINOR | rag_service.py: RagVectorCache.search | `'image_id': m.get('image_id')` 在 `image_id` 为 None 时仍写入结果 dict。调用方（fa_tools）已做 `if image_id is not None` 过滤，逻辑正确但轻微冗余。 | DOCUMENTED |

---

### MOD-141-04: fa_tools — ContextVar side-channel
**文件**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py`

- Correctness: 9/10
- Security: 10/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage: 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-008 | MINOR | fa_tools.py: search_sanheng_knowledge | `_last_search_images_var.set([])` 在 degraded/empty 路径调用，与非 degraded 路径代码重复（4次）。可抽取为内联 helper，但不影响正确性。 | DOCUMENTED |

**安全合规确认**：返回给 LLM 的 str 中不含 image_id（C-003 满足）。ContextVar 在 asyncio.Task 边界自动隔离。

---

### MOD-141-05: orchestrator — State.related_images + _expert/_aggregate 扩展
**文件**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py`

- Correctness: 9/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-009 | MAJOR | orchestrator.py: State.related_images | `related_images` 字段无 reducer（`operator.add` 等），依赖 `_aggregate` 一次性写入覆盖。当多个 expert 并行时 LangGraph 不会自动合并，可能有并发写覆盖风险。架构文档 ADR-IC-001 已确认"不使用 reducer，由 aggregate 统一汇聚"，属于知情偏差，风险在 _aggregate 的全局去重逻辑中已控制。 | DOCUMENTED（架构已知偏差）|

**OQ-IC-004 合规确认**：`related_images` 未被传入 `chat_memory.append_message`，仅在 State 中驻留，随 stream_end 发出。

---

### MOD-141-06: adapter — _drive() 图片 yield
**文件**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/adapter.py`

- Correctness: 9/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage: 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-010 | MINOR | adapter.py: _drive | `aget_state` 异常仅打 warning 后 `snap=None`，此时 related_images 静默跳过。若 interrupted=True 则完全不调用 aget_state——中断流程不产生 related_images，符合预期（写确认门场景无 RAG 查询）。 | DOCUMENTED |

---

### MOD-141-07: consumers — _pump + _finalize_turn 扩展
**文件**：`FreeArkWeb/backend/freearkweb/api/consumers.py`

- Correctness: 9/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage: 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-011 | MINOR | consumers.py: _pump | `self._related_images = []` 重置发生在 `_handle_chat` 而非 `_pump` 内部，若 `_handle_chat` 异常提前返回，`_related_images` 可能残留到下一轮。当前代码结构不会触发此路径，但属于防御性可改进点。 | DOCUMENTED |

**WS/Redis 验证需求标注**（架构约束 IFC-141-704）：  
consumers.py 改动涉及 WS 消息协议变更（stream_end 新增 related_images 字段），必须在本地真实 Redis 环境验证 WS 消息收发。当前 CI 环境使用 InMemory channel layer，无法覆盖 Redis 路径。**需在生产灰度前人工执行本地 WS 收发验证**（参考：MEMORY 条目"WS consumer 测试腐烂"和"Channels 运行时改动必须本地真 Redis 验 WS 收发"）。

---

### MOD-141-08: RagImageView
**文件**：`FreeArkWeb/backend/freearkweb/api/views_rag.py`

- Correctness: 9/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 9/10
- Test Coverage: 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-012 | MINOR | views_rag.py: RagImageView.get | `only('image_data', 'image_format')` 避免了无谓列加载，但 `image_data` 为大 BLOB，无分块流式传输（直接 `bytes(img.image_data)`）。对当前上限 10MB 可接受；若未来图片增大，建议换 `StreamingHttpResponse`。 | DOCUMENTED |

**认证合规确认**：`permission_classes = [IsAuthenticated]`，Bearer Token 认证（REQ-NFR-004 满足）。不使用 SessionAuthentication，不绕过 Token 鉴权。

---

### MOD-141-09: urls.py 路由注册
**文件**：`FreeArkWeb/backend/freearkweb/api/urls.py`

- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage: 10/10

无 finding。路由已正确注册，路径参数 `<int:image_id>` 类型安全。

---

### MOD-141-10: ChatView.vue — 前端图片引用渲染
**文件**：`FreeArkWeb/frontend/src/views/ChatView.vue`

- Correctness: 8/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-013 | MAJOR | ChatView.vue: loadImageBlobUrl | `msg.imageUrls[imageId] = blobUrl` 直接在响应式对象上添加新属性；Vue3 Proxy 可正确响应此操作（原生属性追踪），但需确认 `msg.imageUrls` 初始化为 `{}` 而非 `null`。已确认 handleSend 和 mapHistoryToMessage 均初始化为 `{}`，正确。此 MAJOR 在代码层面已自洽，标注供审查确认。 | DOCUMENTED（已自洽）|
| FND-014 | MINOR | ChatView.vue: stream_end handler | `data.related_images.forEach(img => loadImageBlobUrl(last, img.image_id))` 中 `last` 为响应式对象的直接引用，函数内赋值 `msg.imageUrls[imageId] = blobUrl` 依赖引用有效性。组件卸载前引用有效，`onUnmounted` 阶段才失效；当前无竞态风险。 | DOCUMENTED |

**前端认证陷阱合规确认**：  
`fetchRagImage` 使用 `authenticatedFetch`（在 `api.js` 中定义），不使用裸 `import axios`（前端认证陷阱规避，MEMORY 条目"前端裸 axios 偷用 session 陷阱"满足）。  
`api.js` 中 `fetchRagImage` 为命名导出（`export async function fetchRagImage`），ChatView.vue 通过 `import api, { fetchRagImage } from '../utils/api.js'` 引入。

---

### MOD-141-11: api.js — fetchRagImage
**文件**：`FreeArkWeb/frontend/src/utils/api.js`

- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 9/10
- Test Coverage: 8/10

无 finding。设计决策（DEV-001）：不使用 `api.get()`（其内部调用 `.json()` 无法处理二进制响应），直接使用 `authenticatedFetch` + `response.blob()`，符合项目认证规范。

---

## 未解决的 CRITICAL 问题

**无**。FND-003、FND-004 均已在本次实现中修复（分别对应 Step 4a 遍历范围扩展、Step 4 过滤逻辑清理）。

---

## 遗留 MAJOR 问题说明

共 2 条遗留 MAJOR（FND-009、FND-013），原因说明：

**FND-009**（orchestrator State.related_images 无 reducer）：  
架构文档 ADR-IC-001 明确决策"由 `_aggregate` 统一汇聚，不用 operator.add reducer"。变更此决策需修改架构层设计，超出本实现范围。风险已通过 `_expert` 和 `_aggregate` 两层去重控制。

**FND-013**（Vue3 响应式属性追踪确认）：  
代码自洽性已在评审中确认（`imageUrls` 初始化为 `{}`，Vue3 Proxy 正确响应新属性赋值）。此 MAJOR 属于"需要审查确认的已知安全点"，实际无缺陷。

---

## 架构合规性确认

| 约束 ID | 约束描述 | 合规状态 |
|---------|---------|---------|
| C-003 | LLM 防幻觉：search_sanheng_knowledge 返回 str 不含 image_id | PASS — ContextVar side-channel 隔离 |
| OQ-IC-004 | related_images 不持久化到 chat_memory | PASS — 仅随 stream_end 实时发送 |
| REQ-NFR-001 | 图片字节不进向量缓存（仅存 image_id） | PASS — RagVectorCache._meta 仅追加 image_id |
| REQ-NFR-004 | 取图 API 需认证 | PASS — IsAuthenticated + Bearer Token |
| ADR-IC-001 | 图片字节存 DB BLOB | PASS — BinaryField，db_table='api_ragimage' |
| ADR-IC-002 | ContextVar side-channel | PASS — contextvars.ContextVar，asyncio Task 边界隔离 |
| Fail-open | 单图存储失败不阻断文档入库 | PASS — _try_save_image_bytes 捕获所有异常 |
| Migration | 手写 0039_rag_image.py，依赖 0038 | PASS — 已手写，`dependencies = [('api', '0038_chatsession_title')]` |
| 前端认证陷阱 | 取图前端调用走 api.js authenticatedFetch | PASS — fetchRagImage 通过 authenticatedFetch，无裸 axios |

---

## WS 验证需求（无法在 CI 环境自动覆盖）

根据项目架构约束（MEMORY 条目"Channels 运行时改动必须本地真 Redis 验 WS 收发"），consumers.py 的 stream_end 新字段变更需要本地真实 Redis 环境验证。

**验证清单（人工，灰度前必做）**：
1. 启动本地 Redis，配置 `CHANNEL_LAYERS` 使用 channels_redis（固定 redis-py 5.x）
2. 发送含 RAG 查询的消息，确认 WS stream_end 消息中包含 `related_images` 字段
3. 确认无 related_images 时 stream_end 不含该字段（向后兼容验证）
4. 确认前端 blob: URL 加载后 el-image 正常渲染
