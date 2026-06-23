# 用户故事清单

**特性**：三恒知识库 RAG 图片引用回溯（Image Citation）
**版本**：v1.4.1_rag_image_citation
**状态**：DRAFT — 等待产品负责人确认
**日期**：2026-06-23
**关联**：requirements_spec.md v1.4.1_rag_image_citation

---

## 用户故事总览

| 编号 | 角色 | 一句话描述 | 关联需求 | 优先级 |
|------|------|---------|---------|-------|
| US-IC-001 | 住户/业主 | 问答中看到图片引用 | REQ-FUNC-003, REQ-FUNC-005 | Must Have |
| US-IC-002 | 住户/业主 | 点击缩略图查看大图 | REQ-FUNC-005 | Must Have |
| US-IC-003 | 住户/业主 | 图片加载失败时仍能看到文字答案 | REQ-NFR-003 | Must Have |
| US-IC-004 | 知识库管理员 | 上传含图文档后图片自动入库 | REQ-FUNC-001 | Must Have |
| US-IC-005 | 知识库管理员 | 上传文档时图片提取失败不阻断整体 | REQ-NFR-003, REQ-FUNC-001 | Must Have |
| US-IC-006 | 知识库管理员 | 删除文档时图片数据一并清理 | REQ-FUNC-006 | Must Have |
| US-IC-007 | 住户/业主 | 纯文字问答不出现空白图片区域 | REQ-FUNC-005 | Must Have |
| US-IC-008 | 平台运维 | 图片不占用进程内存缓存 | REQ-NFR-001 | Should Have |
| US-IC-009 | 平台运维 | OCR 未启用时系统正常运行无报错 | REQ-NFR-003 | Must Have |

---

## US-IC-001 问答中看到图片引用

**As** 住户/业主（最终用户），
**I want** 当智能体回答中命中了知识库内嵌图片的 OCR 内容时，在回答气泡下方看到对应的原始图片缩略图，
**So that** 我能直观核对工程图纸、设备参数表等图形信息，而不只是看 OCR 识别出的文字。

### 验收标准

**AC-IC-001-01 — 正常命中含图片的 OCR chunk**
```
Given 知识库中已索引一份包含图片的三恒手册（图片已持久化，chunk 已建立关联）
When  用户提问，问题触发了该手册中来自图片 OCR 的 chunk 命中
Then  WS 收到的 stream_end 消息中 related_images 数组非空，含对应图片的 image_id
And   回答气泡下方渲染出缩略图区域，缩略图可正常加载显示
And   回答的文字部分正常显示，不受图片区域影响
```

**AC-IC-001-02 — 命中多个含图片的 chunk（去重）**
```
Given 一次问答命中了同一张图片对应的多个 OCR chunk（同图文字被分成多个 chunk）
When  stream_end 消息到达前端
Then  related_images 中同一 image_id 只出现一次（后端或前端去重均可，但不重复展示相同缩略图）
```

**AC-IC-001-03 — 命中多张不同图片的 chunk**
```
Given 一次问答命中了来自不同图片的多个 OCR chunk（如第 2 页图片 1 和第 3 页图片 2）
When  stream_end 消息到达前端
Then  related_images 包含两张图片的 image_id
And   气泡下方展示两张缩略图，各自可独立加载
```

**AC-IC-001-04 — 降级：图片不在本期范围内的 OCR chunk**
```
Given is_image_ocr=True 的 chunk，但其 image_id 为 None（图片存储时被跳过，如超大图片）
When  该 chunk 被检索命中
Then  related_images 中不包含该 image_id（None 不加入数组）
And   回答气泡下方不出现该图片的缩略图
And   文字答案正常展示
```

---

## US-IC-002 点击缩略图查看大图

**As** 住户/业主，
**I want** 点击回答气泡中的缩略图后能查看原图大图，
**So that** 我能看清图纸细节和参数表中的数字。

### 验收标准

**AC-IC-002-01 — 点击缩略图展开大图**
```
Given 回答气泡下方有一张缩略图已正常加载
When  用户点击该缩略图
Then  大图以弹层（modal / el-image preview）形式展示，可在当前页面查看
And   不跳转到新标签页或新路由
And   弹层可通过点击蒙层或关闭按钮关闭
```

**AC-IC-002-02 — 多图时可逐张浏览**
```
Given 回答气泡下方有两张或以上缩略图
When  用户点击其中一张
Then  大图弹层支持左右翻页（使用 el-image preview-src-list 或等价交互）
```

---

## US-IC-003 图片加载失败时仍能看到文字答案

**As** 住户/业主，
**I want** 即使图片暂时无法加载（网络抖动、图片记录丢失），文字答案仍然完整可读，
**So that** 图片问题不会破坏我的聊天体验。

### 验收标准

**AC-IC-003-01 — 图片 HTTP 加载失败**
```
Given 回答气泡有图片引用，但取图端点返回 404 或 5xx
When  前端尝试加载缩略图
Then  缩略图位置显示友好占位（如「图片暂时无法显示」文字或图标），而非空白或破图 icon
And   回答的文字内容正常显示，不受影响
And   控制台不出现未捕获的 JS 错误
```

**AC-IC-003-02 — stream_end 中 related_images 为空数组**
```
Given 本次问答未命中含图片的 OCR chunk
When  前端收到 stream_end，related_images=[] 或字段缺失
Then  气泡下方不渲染图片区域（无空白 div，无占位图）
And   与无图片功能前的气泡渲染行为一致（无副作用）
```

---

## US-IC-004 上传含图文档后图片自动入库

**As** 知识库管理员，
**I want** 上传一份含内嵌图片的 docx 或 pdf 后，图片原始字节自动入库，无需额外操作，
**So that** 以后的问答可以引用这些图片，不需要我重新处理文档。

### 验收标准

**AC-IC-004-01 — docx 含图片上传入库**
```
Given 一份含 3 张内嵌图片的 docx 已通过管理页面上传
When  文档状态变为 indexed
Then  数据库中存在 3 条（或更少，视 OCR 及图片提取结果）与该文档关联的 RagImage 记录
And   每条 RagImage 记录的图片字节非空
And   is_image_ocr=True 的 RagChunk 中，与图片 OCR 文字关联的 chunk 有非 None 的 image_id
```

**AC-IC-004-02 — pdf 含 XObject 图片上传入库**
```
Given 一份含内嵌 XObject 图片的 pdf
When  入库完成，状态为 indexed
Then  该 pdf 的内嵌图片对应 RagImage 记录存在，字节非空
```

**AC-IC-004-03 — 纯文字文档无图片记录**
```
Given 一份不含任何图片的纯文字 docx/pdf
When  入库完成，状态为 indexed
Then  数据库中无该文档关联的 RagImage 记录
And   文档入库照常成功，chunk_count 正常
```

---

## US-IC-005 上传文档时图片提取失败不阻断整体

**As** 知识库管理员，
**I want** 上传文档时即使某张图片无法提取或存储失败，文档整体入库仍然成功，
**So that** 单张图片的问题不会让整个手册的文字内容也无法使用。

### 验收标准

**AC-IC-005-01 — 单图提取异常**
```
Given 一份 pdf，其中有一张图片 xref 损坏，extract_image 抛出异常
When  入库流程处理到该图片
Then  系统记录一条 WARNING 级别日志，包含文档 id、图片序号、异常信息
And   该图片跳过存储，其余图片和文字 chunk 照常处理
And   文档最终状态为 indexed，chunk_count 为正常数量（不含失败图片）
```

**AC-IC-005-02 — 图片超过存储大小上限**
```
Given 一份文档含一张超过存储上限的超大图片（如扫描件整页 png_bytes > 上限阈值）
When  入库流程尝试存储该图片
Then  跳过该图片的存储，记录 WARNING 日志
And   该图对应 OCR chunk 的 image_id 为 None（前端无缩略图，但有文字）
And   其余内容正常入库，文档状态为 indexed
```

**AC-IC-005-03 — OCR 跳过但图片仍可入库**
```
Given OCR 未启用（_HAS_OCR=False），文档含图片
When  入库流程处理到图片
Then  图片字节照常存储（RagImage 记录写入）
And   由于 OCR 跳过，无 is_image_ocr=True 的 chunk 产生
And   文档状态为 indexed（无 OCR 文字是正常降级，非失败）
Note  此场景前端永远不会展示该图片（无 chunk 命中），但不影响系统正确性
```

---

## US-IC-006 删除文档时图片数据一并清理

**As** 知识库管理员，
**I want** 从知识库删除文档时，该文档的所有图片数据（DB 记录及文件系统文件，如有）也一并删除，
**So that** 磁盘空间得到正确回收，不产生孤立数据。

### 验收标准

**AC-IC-006-01 — 删除文档后无孤立图片记录**
```
Given 一份已 indexed 的含图文档，数据库中有 N 条关联 RagImage 记录
When  管理员通过 DELETE /api/rag/documents/{id}/ 删除文档
Then  响应为 204 No Content
And   数据库中无该文档关联的 RagImage 记录（CASCADE 或等价清理）
And   若使用文件系统存储，图片文件也不再存在
And   RagVectorCache 触发刷新（与现有逻辑相同）
```

---

## US-IC-007 纯文字问答不出现空白图片区域

**As** 住户/业主，
**I want** 普通文字类问答（未命中含图片的 OCR chunk）的回答气泡外观与现在完全一致，无新增的空白区域，
**So that** 引入图片功能后不影响已有的聊天 UX。

### 验收标准

**AC-IC-007-01 — 无图答案的气泡外观不变**
```
Given 一次问答，检索结果全为 is_image_ocr=False 的文字 chunk，或知识库未被命中
When  stream_end 消息到达（related_images=[] 或字段缺失）
Then  回答气泡的结构与 v1.4.0 完全一致，无额外 DOM 节点或样式变化
And   Vue DevTools 中可确认图片引用区 v-if 条件为 false，组件未挂载
```

---

## US-IC-008 图片不占用进程内存缓存

**As** 平台运维，
**I want** 图片字节不加载到 `RagVectorCache` 的进程内存中，
**So that** 树莓派 5 的 8GB 内存不因图片数据而耗尽，向量检索性能不受影响。

### 验收标准

**AC-IC-008-01 — 缓存不持有图片字节**
```
Given RagVectorCache 已 load() 完成，包含含图文档的 chunk
When  检查 _meta 列表的每个条目
Then  每个 meta dict 中只包含 doc_name / source / is_image_ocr / content / image_id（整型 id）
And   不含任何 bytes 类型字段（无图片字节数据）
```

**AC-IC-008-02 — 取图走 DB 查询，不过缓存**
```
Given 前端请求 GET /api/rag/images/{id}/
When  取图端点处理请求
Then  直接查询 DB（RagImage 表），不调用 RagVectorCache
And   响应为图片字节（Content-Type 正确）
```

---

## US-IC-009 OCR 未启用时系统正常运行

**As** 平台运维，
**I want** 在 OCR 未安装（`_HAS_OCR=False`）的部署环境下，图片引用功能的新代码路径不引入新的报错，
**So that** Pi 5 验证 OCR 前的生产环境不受影响。

### 验收标准

**AC-IC-009-01 — OCR 关闭时入库不报错**
```
Given 部署环境中 _HAS_OCR=False
When  上传含图片的文档并入库
Then  图片字节仍被提取并存储（图片存储不依赖 OCR 结果）
And   无 is_image_ocr=True 的 chunk 产生（与 v1.4.0 现有行为一致）
And   文档状态最终为 indexed，日志中无 ERROR 级别条目（WARNING 可有）
```

**AC-IC-009-02 — OCR 关闭时问答不报错**
```
Given _HAS_OCR=False，问答触发知识库检索
When  search_sanheng_knowledge 执行
Then  related_images 返回空数组（因无 is_image_ocr=True chunk 命中）
And   WS stream_end 消息正常发出，气泡无图片区域
And   无异常抛出，聊天正常结束
```

---

## 附录 A：开放问题（OQ）— 需产品负责人在确认门决策

以下开放问题需在本确认门回复时一并决策，否则架构阶段无法推进：

| OQ 编号 | 问题描述 | 建议默认 | 对架构的影响 |
|--------|---------|---------|------------|
| **OQ-IC-001** | 图片存储方式：DB BLOB 还是文件系统（Django MEDIA_ROOT）？ | DB BLOB（Pi 5 已有 MySQL/SQLite，无需额外文件管理，简单但 DB 体积增大） | 决定 RagImage 模型字段类型、取图端点实现、删除逻辑 |
| **OQ-IC-002** | 单图存储大小上限是多少？需求侧建议 ≤10MB/张 | 10MB（可被架构阶段实测后调整） | 影响 REQ-FUNC-001 fail-open 阈值 |
| **OQ-IC-003** | 扫描件整页栅格化（parse_pdf 路径3）生成的 png_bytes 是否也存储？这类图片可达数十 MB，存储成本高 | 建议：存储，但受 OQ-IC-002 上限约束；超限则跳过，仍有文字 chunk | 影响 RagParser 路径3 的修改范围 |
| **OQ-IC-004** | 会话历史恢复时是否需要复现图片引用？（重新打开历史会话时，历史消息是否展示当时的图片缩略图） | 建议：本期不复现，只实时问答展示；历史消息只显示文字 | 影响 chat_memory / 历史加载逻辑 |
| **OQ-IC-005** | KnowledgeBaseView.vue 中现有裸 axios 调用（非本特性新增），是否本期一并整改？ | 建议：不在本期范围，另立 ticket；本特性只保证新增取图调用走 api.js | 影响开发工作量 |

---

## 附录 B：风险登记

| 风险编号 | 描述 | 可能性 | 影响 | 缓解措施 |
|---------|------|-------|------|---------|
| RISK-IC-001 | DB BLOB 方案导致 MySQL/SQLite 数据库文件膨胀，Pi 5 SD 卡写入寿命缩短 | 中 | 高（存储和寿命） | 架构阶段评估文件系统方案；设单图上限；监控 DB 大小 |
| RISK-IC-002 | `search_sanheng_knowledge` 改为结构化返回，影响现有 LangGraph 工具调用链（返回类型变化需 orchestrator 适配） | 中 | 中（需联动 orchestrator.py / adapter.py） | 架构阶段绘制完整调用链变更影响图；单独测试工具调用 |
| RISK-IC-003 | 向量缓存刷新时 `_meta` 结构新增 `image_id` 字段，若缓存与 DB 数据不一致（如图片记录写入失败）导致悬空 image_id | 低 | 低（前端取图 404，显示占位） | fail-open 降级（404 已有验收标准 AC-IC-003-01） |
| RISK-IC-004 | `consumers.py` `_finalize_turn` 修改引入回归：stream_end 附加字段可能影响不关心图片的其他前端逻辑 | 低 | 中（需确保 related_images 为可选字段，缺失时前端无副作用） | AC-IC-007-01 专项验收 |
| RISK-IC-005 | 前端取图用裸 axios（开发时忘记用 api.js），若移除 SessionAuthentication 后 401 静默 | 中 | 中 | 代码评审检查点：所有取图调用必须经 api.js（REQ-FUNC-004 验收标准已明确） |

---

*文档状态：DRAFT。等待产品负责人对 OQ-IC-001~005 的决策后进入 APPROVED 状态。*
