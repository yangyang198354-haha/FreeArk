**特性**：三恒知识库 RAG 图片引用回溯（Image Citation）
**版本**：v1.4.1_rag_image_citation
**状态**：DRAFT
**日期**：2026-06-23
**依赖**：requirements_spec.md (APPROVED), user_stories.md (APPROVED)

---

# 技术选型表 — v1.4.1 三恒知识库 RAG 图片引用回溯

**文档编号**：ARCH-TECH-RAG-v141-001
**项目名称**：FreeArk 三恒知识库 RAG 图片引用回溯（v1.4.1_rag_image_citation）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-23

---

## 1. 核心结论

**本特性无新增外部 Python 依赖**。所有功能使用以下既有技术实现：

- Django `BinaryField`（图片 BLOB 存储）
- Python 标准库 `contextvars.ContextVar`（side-channel 传递 related_images）
- Python 标准库 `hashlib.md5`（图片去重 key 生成，非密码学用途）
- DRF `APIView` + `HttpResponse`（取图端点）
- Vue 3 `el-image`（前端缩略图/大图浏览，已有 Element Plus 依赖）
- JavaScript `URL.createObjectURL`（Blob URL，浏览器标准 API，无需额外库）

---

## 2. 技术选型表

### 2.1 后端技术（无新增）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 图片存储 | Django BinaryField（DB BLOB） | Django 4.x（现有） | ADR-IC-001：Pi 5 单机部署无需文件系统管理；CASCADE 删除自动清理；备份一体化；取图端点实现简单 | REQ-FUNC-001, REQ-FUNC-006, REQ-NFR-001 | RISK-IC-001：DB 文件体积增大，SD 卡写入寿命；缓解：10MB 上限 + 监控 + VACUUM 策略（见 architecture_design.md §5.1） | DB BLOB 而非文件系统（OQ-IC-001 PM 决策锁定） |
| Side-channel 传递 | Python contextvars.ContextVar | Python 3.10+（现有） | ADR-IC-002：asyncio Task 自动 copy context，天然隔离，无需额外同步原语；比 threading.local 在 async 代码中更安全 | REQ-FUNC-003, C-003 | 低：若未来引入多 event loop 需要注意 context 传播，当前单 Daphne worker 无此问题 | Python 3.7+ 标准库，零额外依赖 |
| 图片格式检测 | 内置字节签名检测 | Python 标准库 | 无需引入 python-magic 或 filetype 库；PNG/JPEG 头字节特征明确（PNG: 8B, JPEG: 2B），覆盖三恒文档的主要图片格式 | REQ-FUNC-001 | 低：'other' 格式兜底处理，不识别时用 application/octet-stream，可接受 | 已有 v1.4.0 文件上传的类似模式（_ALLOWED_MIME_SIGNATURES） |
| 图片去重 key | hashlib.md5（首 256 字节） | Python 标准库 | 同文档中同一图片可被 parse_docx 多次引用（rels 遍历），需去重避免重复写入 DB；md5 非密码学场景下计算速度快 | REQ-FUNC-001 | 低：极小概率 hash 碰撞（不同图片前 256 字节相同），实际场景中可忽略；碰撞时最多少存一张图片（fail-open） | 仅用于 ingest 阶段内存去重，不用于安全场景 |
| 取图 HTTP 端点 | DRF APIView + HttpResponse | djangorestframework（现有） | 现有项目已用 DRF，`APIView` 复用 TokenAuthentication/IsAuthenticated 权限类；`HttpResponse(bytes)` 直接返回图片字节流 | REQ-FUNC-004, REQ-NFR-004 | 低：HttpResponse 返回 BinaryField bytes，Django 不做额外序列化 | 不用 DRF Response（避免 JSON 序列化），直接 HttpResponse |
| DB 迁移 | 手写 Migration（0039） | Django migrations | C-006（TD-MIGRATION-001）：不运行 makemigrations，手写遵循 0036_add_rag_tables.py 风格；确保 migration 链路清晰可审计 | REQ-NFR-005 | 低：手写需人工验证字段定义正确性；mitigation：代码评审 + migrate --check 在 CI 中验证 | 编号 0039，依赖 ('api', '0038_chatsession_title') |

### 2.2 LangGraph 编排层（最小改动，现有技术）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| State 传递 | LangGraph TypedDict State | langgraph（现有） | State.related_images 新增字段（total=False 可选），无 reducer（由 _aggregate 一次性写入），符合现有 State 设计风格 | REQ-FUNC-003, REQ-FUNC-005 | 中（RISK-IC-002）：返回类型变更牵动调用链；缓解：architecture_design.md §2 完整影响图 + 分层测试 | related_images 字段无 operator.add reducer |
| 编排器状态读取 | graph.aget_state(config) | langgraph（现有） | adapter._drive() 在 astream 完成后从快照读取 related_images，确保 _aggregate 已执行完毕；零额外网络调用（MemorySaver 进程内） | REQ-FUNC-005 | 低：aget_state 依赖 MemorySaver，重启后 State 丢失（与现有行为一致）；OQ-IC-004 决策：历史会话不复现图片 | MemorySaver 进程内，无 DB/Redis 开销 |

### 2.3 前端技术（现有依赖，新用法）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 图片展示组件 | Element Plus el-image | 现有（Element Plus 2.x） | `preview-src-list` 属性开箱即用支持多图弹层浏览（US-IC-002 AC-IC-002-02）；`#error` slot 支持自定义加载失败占位（US-IC-003） | REQ-FUNC-005 | 低：el-image 内置懒加载（loading="lazy"），减少首屏请求 | 无需引入 lightbox 等额外库 |
| 鉴权取图 | api.js Blob 请求 + URL.createObjectURL | 浏览器标准 API | C-004：取图必须走 api.js（Bearer Token）；浏览器 `<img src>` 无法携带 Authorization 头；通过 axios responseType:'blob' + createObjectURL 桥接 | REQ-FUNC-004, C-004 | 中（RISK-IC-005）：开发者容易忘记走 api.js 直接用裸 axios 或 img src；缓解：代码评审检查点；IFC-141-1101 明确约束 | 组件销毁时须 revokeObjectURL 防内存泄漏（MOD-141-10） |
| 前端路由 | Vue Router（现有） | vue-router 4.x（现有） | 无新增路由，ChatView.vue 原地修改 | — | 低 | 不涉及路由变更 |

---

## 3. 依赖变更汇总

### 3.1 Python 后端（requirements.txt）

**本特性无新增行**。所有功能通过现有依赖实现：

| 类型 | 依赖 | 来源 | 说明 |
|------|------|------|------|
| 不变 | Django | 现有 | BinaryField 为内置字段类型 |
| 不变 | djangorestframework | 现有 | APIView、IsAuthenticated、HttpResponse |
| 不变 | PyMuPDF | 现有（v1.4.0） | `base_image["ext"]` 已提供图片格式；`get_pixmap().tobytes("png")` 已有 |
| 不变 | python-docx | 现有（v1.4.0） | `rel.target_part.blob` 已有图片字节 |
| 不变 | langchain-openai | 现有 | 未修改 |
| 不变 | langgraph | 现有 | aget_state()、TypedDict State、ContextVar |
| 标准库 | contextvars | Python 3.7+ 内置 | ContextVar，无需安装 |
| 标准库 | hashlib | Python 内置 | md5 用于图片去重，无需安装 |

### 3.2 JavaScript 前端（package.json）

**本特性无新增行**。

| 类型 | 依赖 | 来源 | 说明 |
|------|------|------|------|
| 不变 | element-plus | 现有 | el-image 组件已在项目中使用 |
| 不变 | axios | 现有（通过 api.js） | responseType:'blob' 为 axios 内置功能 |
| 浏览器 API | URL.createObjectURL | 浏览器标准 | 无需库，现代浏览器原生支持 |

---

## 4. Migration 编号确认

| 项目 | 值 | 说明 |
|------|----|------|
| 当前最新 migration | 0038_chatsession_title.py | 依赖 0037_chatsession_is_deleted_session_key_unique |
| 本特性 migration 编号 | **0039** | 确认无冲突 |
| 本特性 migration 文件名 | `0039_rag_image.py` | 遵循现有命名惯例 |
| 依赖声明 | `('api', '0038_chatsession_title')` | 项目硬约束，必须 |
| 新增表名 | `api_ragimage` | Django 自动前缀 `api_` + 模型名 `ragimage`，与 `api_ragdocument`/`api_ragchunk` 一致 |

---

## 5. Pi 5 存储影响评估

### 5.1 存储预算计算

关联需求：REQ-NFR-001，单图上限 10 MB（OQ-IC-002 决策）

| 场景 | 文档数 | 图片数/文档 | 平均图片大小 | 预计总存储 |
|------|--------|-----------|------------|-----------|
| 最小（纯文字手册为主） | 50 份 | 5 张/份 | 0.5 MB | **125 MB** |
| 典型（三恒操作手册） | 100 份 | 10 张/份 | 2 MB | **2 GB** |
| 中等（含工程图纸） | 150 份 | 15 张/份 | 3 MB | **6.75 GB** |
| 上限（大量扫描件，受 10MB 约束） | 200 份 | 20 张/份 | 5 MB | **20 GB** |

**Pi 5 参考配置**：
- SD 卡：32~128 GB（典型）
- SSD（推荐）：128~512 GB
- 现有 DB + 日志基线：约 2~5 GB

**结论**：
- 典型场景（2 GB 图片）+ 现有基线（5 GB）= 7 GB，在 32 GB SD 卡（22%），可接受
- 上限场景（20 GB 图片）：建议使用 SSD，SD 卡 128 GB 配置（约 20%），仍可接受
- **监控触发阈值**：图片总存储超过 5 GB 时建议运维介入评估

### 5.2 存储预算监控 SQL

```sql
-- 实时查询图片总存储（Pi 5 MySQL）
SELECT
    COUNT(*) AS image_count,
    SUM(file_size) / 1024 / 1024 AS total_mb,
    MAX(file_size) / 1024 / 1024 AS max_single_mb,
    AVG(file_size) / 1024 AS avg_kb
FROM api_ragimage;

-- 按文档分组（找存储占用最大的文档）
SELECT
    d.file_name,
    COUNT(i.id) AS image_count,
    SUM(i.file_size) / 1024 / 1024 AS mb
FROM api_ragimage i
JOIN api_ragdocument d ON i.document_id = d.id
GROUP BY d.id
ORDER BY mb DESC
LIMIT 10;
```

### 5.3 存储减缩建议（运维操作，非代码约束）

| 操作 | 场景 | 执行时机 |
|------|------|---------|
| `PRAGMA incremental_vacuum` | SQLite 场景，回收 CASCADE 删除后的碎片空间 | 每周 cron（低峰期） |
| `OPTIMIZE TABLE api_ragimage` | MySQL InnoDB 场景，整理 BLOB 碎片 | 每月或图片总量大幅减少后 |
| 删除冗余文档 | 知识库管理员清理过期文档 | 按需，现有 DELETE 端点支持 |
| 启用 MySQL 压缩表 | 文档极多、存储紧张时 | 需 DBA 评估，本期不做 |

---

## 6. 技术风险汇总

| 风险编号 | 描述 | 等级 | 缓解措施 |
|---------|------|------|---------|
| RISK-IC-001 | DB BLOB 导致 Pi 5 数据库体积膨胀，SD 卡写入寿命风险 | High | 10MB/张上限（代码层约束）；监控 SUM(file_size)；SQLite VACUUM / MySQL OPTIMIZE 策略；推荐 SSD 部署 |
| RISK-IC-002 | search_sanheng_knowledge 调用链变更，orchestrator/consumer 联动可能引入回归 | Medium | architecture_design.md §2 完整调用链影响图；分层测试（rag_service 单测 → fa_tools 单测 → orchestrator 集成测试 → WS 端到端）；现有 1778 测试基线保护 |
| RISK-IC-003 | 向量缓存 _meta 新增 image_id，DB 数据不一致（图片写入失败时 image_id=None 但 chunk 仍存在） | Low | fail-open 降级（前端取图 404 → el-image error slot 友好提示）；AC-IC-003-01 验收覆盖 |
| RISK-IC-004 | consumers._finalize_turn 修改引入 stream_end 回归，影响不关心图片的问答 | Low | stream_end.related_images 为可选字段（缺失等同空数组）；AC-IC-007-01 专项验收；WS 真 Redis 验证 |
| RISK-IC-005 | 前端开发者取图时使用裸 axios 或 img src，Token 鉴权失效（401 静默） | Medium | 代码评审强制检查点（IFC-141-1101 约束）；fetchRagImage helper 封装降低误用概率；C-004 约束明确写入验收标准 |

---

*文档状态：DRAFT。等待 PM 门控评审通过后进入 APPROVED 状态。*
