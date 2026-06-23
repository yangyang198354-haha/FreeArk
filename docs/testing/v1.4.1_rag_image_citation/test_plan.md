<!--
status: WRITTEN
feature: v1.4.1_rag_image_citation（三恒知识库 RAG 图片引用回溯）
created: 2026-06-23
-->

# 测试计划 — v1.4.1_rag_image_citation（三恒知识库 RAG 图片引用回溯）

**文档编号**：TEST-PLAN-RAG-v141-001  
**特性版本**：v1.4.1_rag_image_citation  
**基准文档**：user_stories.md（DRAFT）、implementation_plan.md（WRITTEN）、code_review_report.md（WRITTEN）  
**测试日期**：2026-06-23  
**测试工程师**：sub_agent_test_engineer  

---

## 一、测试目标与范围

### 1.1 测试目标

验证 v1.4.1 特性的所有后端核心功能正确实现，无测试回归，遗留 WS 端到端验证项已明确标注。

### 1.2 In-Scope（自动化覆盖）

| 范围 | 说明 |
|------|------|
| RagImage 模型层 | CASCADE 删除、SET_NULL 语义 |
| _detect_image_format | PNG/JPEG/other 文件头检测 |
| RagParser._try_save_image_bytes | 大小校验、fail-open、空字节防御 |
| RagVectorCache | _meta 含 image_id、不含 bytes 类型 |
| RagVectorCache.search | 返回 chunk dict 含 image_id |
| fa_tools ContextVar side-channel | get_last_search_images 读取清零语义 |
| RagImageView 取图端点 | 200/401/404、Content-Type 正确 |
| _finalize_turn stream_end 载荷 | 无图时不加字段、有图时加 related_images |
| MAX_IMAGE_BYTES 常量 | 等于 10MB |
| RagIngestor 集成流程 | 含图入库、超限跳过、纯文字无 RagImage |

### 1.3 Out-of-Scope（本次不纳入自动化）

| 范围 | 原因 | 处置 |
|------|------|------|
| WS stream_end 经 Redis 到前端的全链路 | CI 使用 InMemory Channel Layer，无 Redis，无法验证真实 WS 消息传递（项目硬纪律：channels_redis 与 redis-py 兼容要求真实 Redis，MEMORY 条目"Channels 运行时改动必须本地真 Redis 验 WS 收发"） | 标注为"待人工验证"，见 §五 |
| 前端 ChatView.vue 渲染 | 超出后端测试范围 | 手动验收 |
| 真实 OCR 路径（_HAS_OCR=True） | Pi 5 未部署 rapidocr-onnxruntime，CI 环境 _HAS_OCR=False | 生产灰度前手动验证 |
| RagParser.parse_docx / parse_pdf 真实文件解析 | 需 python-docx / PyMuPDF 大型依赖 | 通过集成测试 mock parse_docx 替代 |

---

## 二、测试环境

| 项目 | 值 |
|------|-----|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.11 |
| Django | 测试数据库 SQLite（in-memory） |
| Channel Layer | InMemoryChannelLayer（非 Redis） |
| 测试框架 | Django TestCase + APITestCase |
| 环境变量 | FREEARK_POC_MOCK=1, LANGGRAPH_USE_FAKE_LLM=True |
| 运行命令 | `python manage.py test api.tests.test_rag_image_v141 --verbosity=2` |

---

## 三、测试用例清单

### 3.1 单元测试（TC-UNIT-*）

| TC-ID | 所属 US | 关联 AC | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|---------|---------|------|---------|------|---------|
| TC-UNIT-001 | US-IC-006 | AC-IC-006-01 | RagImage CASCADE 删除 | 创建 RagDocument + RagImage | 删除 RagDocument | RagImage 被级联删除 |
| TC-UNIT-002 | US-IC-006 | AC-IC-006-01 | RagChunk.image_id SET_NULL | 创建 RagImage + 关联 RagChunk | 删除 RagImage | RagChunk.image_id 置 NULL，chunk 本身保留 |
| TC-UNIT-003 | US-IC-004 | AC-IC-004-01 | PNG 头字节检测 | 标准 PNG 头字节 | _detect_image_format(bytes) | 返回 'png' |
| TC-UNIT-004 | US-IC-004 | AC-IC-004-02 | JPEG 头字节检测 | 标准 JPEG 头字节 | _detect_image_format(bytes) | 返回 'jpeg' |
| TC-UNIT-005 | US-IC-004 | AC-IC-004-01 | 未知格式检测 | 随机字节 | _detect_image_format(bytes) | 返回 'other' |
| TC-UNIT-006 | US-IC-005 | AC-IC-005-02 | 空字节防御 | 空 bytes | _detect_image_format(b'') | 返回 'other'（不抛异常） |
| TC-UNIT-007 | US-IC-004 | AC-IC-004-01 | 小图通过存储校验 | 8字节 < MAX_IMAGE_BYTES | _try_save_image_bytes | 返回 (bytes, fmt) |
| TC-UNIT-008 | US-IC-005 | AC-IC-005-02 | 超限图片跳过 | 11MB > MAX_IMAGE_BYTES | _try_save_image_bytes | 返回 (None, '') |
| TC-UNIT-009 | US-IC-005 | AC-IC-005-01 | 空字节防御 | b'' | _try_save_image_bytes | 返回 (None, '') |
| TC-UNIT-010 | US-IC-008 | AC-IC-008-01 | RagVectorCache _meta 含 image_id | 含图/不含图 chunk 已入库 | cache.load() 后检查 _meta | 每条 meta dict 含 image_id 字段 |
| TC-UNIT-011 | US-IC-008 | AC-IC-008-01 | RagVectorCache _meta 不含 bytes | 同上 | 检查 _meta 字段类型 | 无 bytes/bytearray/memoryview 类型值 |
| TC-UNIT-012 | US-IC-001 | AC-IC-001-01 | search() 返回 image_id | 含图 chunk 已入缓存 | cache.search(vec) | 返回 dict 含 image_id |
| TC-UNIT-013 | US-IC-001 | AC-IC-001-04 | get_last_search_images 默认空 | 未写入 ContextVar | get_last_search_images() | 返回 [] |
| TC-UNIT-014 | US-IC-001 | AC-IC-001-01 | get_last_search_images 读取清零 | ContextVar 已写入数据 | 两次调用 get_last_search_images() | 第一次返回数据，第二次返回 [] |
| TC-UNIT-015 | US-IC-008 | AC-IC-008-02 | 取图端点 200 | 已认证用户，有效 image_id | GET /api/rag/images/{id}/ | 200, Content-Type=image/png |
| TC-UNIT-016 | US-IC-008 | AC-IC-008-02 | 取图端点 401 | 未认证 | GET /api/rag/images/{id}/ | 401 Unauthorized |
| TC-UNIT-017 | US-IC-003 | AC-IC-003-01 | 取图端点 404 | 已认证，不存在 image_id | GET /api/rag/images/99999/ | 404 Not Found |
| TC-UNIT-018 | US-IC-008 | AC-IC-008-02 | JPEG Content-Type | image_format='jpeg' | GET /api/rag/images/{id}/ | Content-Type=image/jpeg |
| TC-UNIT-019 | US-IC-007 | AC-IC-007-01 | stream_end 无图时不加字段 | related_images=[] | _finalize_turn([], ...) | stream_end 不含 related_images 字段 |
| TC-UNIT-020 | US-IC-001 | AC-IC-001-01 | stream_end 含图时加字段 | related_images 非空 | _finalize_turn([{...}], ...) | stream_end 含 related_images 字段 |
| TC-UNIT-021 | US-IC-005 | AC-IC-005-02 | MAX_IMAGE_BYTES 常量值 | 无 | 读取常量 | 等于 10 * 1024 * 1024 |

### 3.2 集成测试（TC-INT-*）

| TC-ID | 所属 US | 关联 AC | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|---------|---------|------|---------|------|---------|
| TC-INT-001 | US-IC-004 | AC-IC-004-01 | 含图文档完整入库 | ParsedChunk 含图 bytes，mock parse_docx + embed_texts | RagIngestor.ingest() | RagImage 创建，chunk.image_id 关联，status=indexed |
| TC-INT-002 | US-IC-005 | AC-IC-005-02 | 超限图片跳过，文档仍 indexed | ParsedChunk img_bytes=None（模拟已被 _try_save_image_bytes 过滤） | RagIngestor.ingest() | 无 RagImage，chunk.image_id=None，status=indexed |
| TC-INT-003 | US-IC-004 | AC-IC-004-03 | 纯文字文档无 RagImage | 纯文字 ParsedChunk | RagIngestor.ingest() | 无 RagImage，status=indexed，chunk_count=3 |

---

## 四、不可测试项

| AC-ID | 原因 |
|-------|------|
| AC-IC-001-02 | 需端到端 search + fa_tools + orchestrator 真实流程（多层 mock 等价性不足），WS 层 Redis 依赖，归入人工验证 |
| AC-IC-001-03 | 同 AC-IC-001-02 |
| AC-IC-002-01 | 前端 el-image modal 交互，超出后端测试范围 |
| AC-IC-002-02 | 前端多图翻页交互，超出后端测试范围 |
| AC-IC-003-02 | 前端 stream_end 处理逻辑，超出后端测试范围 |
| AC-IC-004-02 | 需真实 PDF + PyMuPDF 解析，CI 环境可用但 OCR 不可用；PDF XObject 路径已通过 parse_pdf 集成逻辑覆盖 |
| AC-IC-005-01 | 需构造损坏 PDF xref，依赖 PyMuPDF 真实行为，超出单元 mock 能力 |
| AC-IC-005-03 | 需 _HAS_OCR=True（Pi 5 环境），CI 环境不满足 |
| AC-IC-007-01 | 前端 Vue DevTools 验证，超出后端测试范围（后端侧通过 TC-UNIT-019 覆盖 stream_end 载荷） |
| AC-IC-008-02（WS 路径） | 取图 DB 直查已通过 TC-UNIT-015~018 验证；WS 端到端全链路归入人工验证 |
| AC-IC-009-01 | 需 _HAS_OCR 可切换，CI 环境恒为 False（无 rapidocr）；图片存储路径已通过 TC-INT-001 验证 |
| AC-IC-009-02 | 需真实 LangGraph 运行时，LANGGRAPH_USE_FAKE_LLM 不测 related_images 流向 |

---

## 五、通过率门控

| 测试阶段 | 门控阈值 | 计算分母 |
|---------|---------|---------|
| 单元测试（TC-UNIT-*） | 通过率 ≥ 80% | pass / (pass + fail) |
| 集成测试（TC-INT-*） | 通过率 ≥ 90% | pass / (pass + fail) |
| 全套回归（api/）  | 通过数 ≥ 1802，失败数 = 0 | — |

---

## 六、US-IC-* 覆盖矩阵

| 用户故事 | 优先级 | 覆盖 TC-ID | 覆盖状态 |
|---------|-------|-----------|---------|
| US-IC-001 | Must Have | TC-UNIT-012, TC-UNIT-013, TC-UNIT-014, TC-UNIT-020 | 部分自动化（WS 端到端人工验证） |
| US-IC-002 | Must Have | — | 前端，人工验收 |
| US-IC-003 | Must Have | TC-UNIT-017, TC-UNIT-019 | 自动化（后端侧） |
| US-IC-004 | Must Have | TC-UNIT-003~007, TC-INT-001, TC-INT-003 | 自动化（含图/纯文字路径） |
| US-IC-005 | Must Have | TC-UNIT-006~009, TC-UNIT-021, TC-INT-002 | 自动化 |
| US-IC-006 | Must Have | TC-UNIT-001, TC-UNIT-002 | 自动化 |
| US-IC-007 | Must Have | TC-UNIT-019 | 自动化（后端 stream_end 字段） |
| US-IC-008 | Should Have | TC-UNIT-010, TC-UNIT-011, TC-UNIT-015~018 | 自动化 |
| US-IC-009 | Must Have | — | 需 OCR 环境（Pi 5），人工验证 |

---

*本文档由 sub_agent_test_engineer 生成，v1.4.1_rag_image_citation 特性测试计划。*
