# 测试计划 — v1.4.0 三恒知识专家 RAG 检索增强

**文档编号**: TEST-PLAN-RAG-v140-001
**版本**: 1.0.0
**状态**: APPROVED
**创建日期**: 2026-06-16
**作者**: sub_agent_test_engineer (via pm-orchestrator)

---

## 1. 测试概述

### 1.1 测试范围

| 用户故事 | 测试类 | 覆盖 AC |
|---------|--------|---------|
| US-1 管理员上传文档 | TestRagUploadAPI | AC-1.2, 1.5, 1.6 |
| US-2 文字+图片 OCR 解析 | TestRagService | AC-2.3, 2.4, 2.5 |
| US-3 专家检索增强作答 | TestSearchTool, TestRagIntegration | AC-3.1~3.4 |
| US-4 管理员删除文档 | TestRagUploadAPI, TestRagIntegration | AC-4.1~4.4 |
| 数据模型 | TestRagDocumentModel | REQ-FUNC-RAG-01 |
| 序列化器 | TestRagSerializer | REQ-FUNC-RAG-03 |
| 系统提示 | TestSystemPromptRAG | REQ-FUNC-RAG-10 |

### 1.2 不在测试范围

- 前端 Vue 组件（需浏览器 E2E 工具，本版本不纳入）
- rapidocr-onnxruntime 真实 OCR（aarch64 需 Pi 真机验证，测试中 mock）
- 外部 embedding API 真实调用（均 mock）
- 生产 MySQL 性能（测试用 SQLite）

---

## 2. 可直接执行的测试命令

**工作目录**: `C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb`

### 2.1 运行全部 RAG 测试

```
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api.tests_rag --verbosity=2
```

### 2.2 分组运行

```
# 数据模型测试
python manage.py test api.tests_rag.TestRagDocumentModel --verbosity=2

# 上传/列表/删除/重试 API 测试（权限+文件校验+状态机）
python manage.py test api.tests_rag.TestRagUploadAPI --verbosity=2

# rag_service 服务层（向量缓存、解析器、Embedder、Ingestor）
python manage.py test api.tests_rag.TestRagService --verbosity=2

# fa_tools.search_sanheng_knowledge @tool 行为
python manage.py test api.tests_rag.TestSearchTool --verbosity=2

# 集成测试（上传→入库→检索完整链路）
python manage.py test api.tests_rag.TestRagIntegration --verbosity=2

# SYSTEM_PROMPT RAG 约定检查
python manage.py test api.tests_rag.TestSystemPromptRAG --verbosity=2

# 序列化器
python manage.py test api.tests_rag.TestRagSerializer --verbosity=2
```

### 2.3 与现有测试一起运行（回归检查）

```
python manage.py test api --verbosity=2
```

### 2.4 生成覆盖率报告（需安装 coverage）

```
# 安装（若未安装）
pip install coverage

# 运行并生成报告
coverage run manage.py test api.tests_rag --verbosity=2
coverage report --include="*/api/models_rag.py,*/api/rag_service.py,*/api/views_rag.py,*/api/serializers_rag.py,*/api/langgraph_chat/fa_tools.py"
```

---

## 3. 测试环境配置

### 3.1 数据库

测试自动使用 SQLite（settings.py 中 `_RUNNING_TESTS` 检测）：
```python
# settings.py L144-146
_RUNNING_TESTS = 'test' in _sys.argv
DATABASES = {
    'default': SQLITE_DATABASE if (USE_SQLITE or _RUNNING_TESTS) else MYSQL_DATABASE
}
```
无需配置 MySQL 连接即可运行测试。

### 3.2 Mock 策略

| 外部依赖 | Mock 方式 | 位置 |
|---------|---------|------|
| embedding API（OpenAIEmbeddings） | `@patch('api.rag_service.RagEmbedder._get_client')` 返回 MagicMock | TestRagService |
| embedding API（search_rag 内部） | `@patch('api.rag_service.search_rag')` | TestSearchTool |
| rapidocr OCR | `@patch('api.rag_service._HAS_OCR', False)` | TestRagService |
| 后台入库线程 | `@patch('api.views_rag.transaction.on_commit', side_effect=lambda fn: None)` | TestRagUploadAPI |
| rag_vector_cache | `@patch('api.rag_service.rag_vector_cache')` | TestRagIntegration |

### 3.3 依赖安装

测试依赖（requirements.txt 中已有）：
```
# 测试需要 python-docx 和 PyMuPDF（用于构造测试文件）
# 若 PyMuPDF 未安装，PDF 相关测试自动 skipTest
python-docx>=1.1.0
PyMuPDF>=1.24.0
```

若在开发机上运行测试，先安装依赖：
```
pip install python-docx PyMuPDF
```

---

## 4. 测试用例清单

### 4.1 单元测试（TestRagDocumentModel - 5 用例）

| ID | 测试方法 | 覆盖点 | 预期结果 |
|----|---------|--------|---------|
| UT-01 | test_default_status_is_pending | REQ-FUNC-RAG-01 初始状态 | status='pending', chunk_count=0 |
| UT-02 | test_status_transition_to_indexed | 状态机 | status='indexed', chunk_count=5 |
| UT-03 | test_status_transition_to_failed | 状态机 | status='failed', error_message 非空 |
| UT-04 | test_uploaded_by_set_null_on_user_delete | SET_NULL 约束 | 用户删除后 uploaded_by=None |
| UT-05 | test_chunk_cascade_delete | ON DELETE CASCADE | 文档删除后 RagChunk.count=0 |

### 4.2 API 测试（TestRagUploadAPI - 13 用例）

| ID | 测试方法 | 覆盖点 | 预期结果 |
|----|---------|--------|---------|
| AT-01 | test_non_admin_upload_returns_403 | AC-1.2 | 403，无 DB 记录 |
| AT-02 | test_non_admin_list_returns_403 | 权限 | 403 |
| AT-03 | test_unauthenticated_returns_401 | 权限 | 401/403 |
| AT-04 | test_invalid_extension_returns_400 | AC-1.5 | 400，错误信息含"不支持的文件类型" |
| AT-05 | test_fake_extension_wrong_magic_returns_400 | AC-1.5 文件头检测 | 400 |
| AT-06 | test_oversized_file_returns_400 | 大小校验 | 400，错误信息含"50MB" |
| AT-07 | test_valid_pdf_upload_returns_201 | AC-1.6 | 201，status=pending |
| AT-08 | test_valid_docx_upload_returns_201 | AC-1.6 | 201，status=pending |
| AT-09 | test_list_returns_documents_ordered_by_created_desc | REQ-03 | 200，按创建时间倒序 |
| AT-10 | test_delete_document_returns_204 | AC-4.1 | 204，台账+向量删除，cache.refresh 调用 |
| AT-11 | test_delete_nonexistent_returns_404 | AC-4.4 | 404 |
| AT-12 | test_delete_parsing_doc_succeeds | AC-4.3 | 204 |
| AT-13 | test_retry_failed_doc_succeeds | AC-2.4 | 200，status=pending |
| AT-14 | test_retry_indexed_doc_returns_400 | 状态校验 | 400 |
| AT-15 | test_retry_without_file_returns_400 | 必须重传文件 | 400 |

### 4.3 服务层测试（TestRagService - 10 用例）

| ID | 测试方法 | 覆盖点 | 预期结果 |
|----|---------|--------|---------|
| ST-01 | test_cache_empty_search_returns_empty | 空缓存 | [] |
| ST-02 | test_cache_search_returns_top_k | 余弦搜索 | 结果降序 |
| ST-03 | test_cache_threshold_filters_low_scores | 阈值过滤 | [] |
| ST-04 | test_parse_docx_text_chunks | AC-2.5 | chunk_count>0, is_image_ocr=False |
| ST-05 | test_parse_pdf_text_chunks | PDF 解析 | chunk 含"第"字 |
| ST-06 | test_ocr_image_returns_empty_when_no_ocr | aarch64 纪律 | '' |
| ST-07 | test_embed_texts_returns_numpy_arrays | 向量化 | float32 shape=(1024,) |
| ST-08 | test_embed_query_returns_numpy_array | 查询向量化 | float32 shape=(1024,) |
| ST-09 | test_search_rag_degraded_on_embedding_failure | AC-3.3 fail-open | degraded=True |
| ST-10 | test_search_rag_empty_cache_returns_empty_not_degraded | AC-3.4 | degraded=False |
| ST-11 | test_ingest_pdf_success | 入库成功 | status=indexed, chunk_count>0 |
| ST-12 | test_ingest_embedding_failure_sets_failed | AC-2.3 | status=failed |
| ST-13 | test_ingest_exits_safely_if_doc_deleted | AC-4.3 | 不抛出异常 |

### 4.4 工具测试（TestSearchTool - 5 用例）

| ID | 测试方法 | 覆盖点 | 预期结果 |
|----|---------|--------|---------|
| TT-01 | test_tool_returns_formatted_results | AC-3.1 来源标注 | 含文件名+页码 |
| TT-02 | test_tool_returns_no_content_message | AC-3.2 无命中 | 含"未找到" |
| TT-03 | test_tool_returns_degraded_message | AC-3.3 降级 | 含"degraded=true" |
| TT-04 | test_tool_marks_image_ocr_source | AC-3.5 图片OCR | 含"图片OCR" |
| TT-05 | test_tool_fail_open_on_exception | fail-open | 不抛出 |

### 4.5 集成测试（TestRagIntegration - 3 用例）

| ID | 测试方法 | 覆盖点 | 预期结果 |
|----|---------|--------|---------|
| IT-01 | test_upload_ingest_search_full_cycle | 完整链路 US-1+US-3 | status=indexed，检索命中 |
| IT-02 | test_delete_triggers_cache_refresh | AC-4.2 | cache.refresh 调用 |
| IT-03 | test_list_shows_correct_status_fields | REQ-FUNC-RAG-03 | 所有必要字段 |

---

## 5. 通过标准（门控）

- 单元测试通过率 ≥ 80%（所有测试类）
- 集成测试通过率 ≥ 90%（TestRagIntegration）
- US-1 ~ US-4 均有对应测试且通过
- 无测试因代码 BUG 失败（skipTest 因依赖缺失不计入失败）

---

## 6. 已知限制与跳过测试说明

| 条件 | 跳过的测试 | 原因 |
|------|---------|------|
| PyMuPDF 未安装 | test_parse_pdf_*, test_ingest_pdf_*, test_upload_ingest_search_full_cycle | 需安装 PyMuPDF |
| rapidocr 未安装 | test_ocr_* (当 _HAS_OCR=True 场景) | 测试用 _HAS_OCR=False mock，不跳过 |
| agents 目录结构变更 | TestSystemPromptRAG | 目录不存在时 skipTest |

跳过的测试不计入失败率。建议在安装了 PyMuPDF 的环境运行完整测试集。
