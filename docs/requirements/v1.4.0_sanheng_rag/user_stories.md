# 用户故事 — v1.4.0 三恒知识专家 RAG 检索增强

**文档编号**: REQ-US-RAG-v140-001
**项目名称**: FreeArk 三恒知识专家 RAG 检索增强（v1.4.0_sanheng_rag）
**版本**: 1.0.0
**状态**: DRAFT（待门控评审）
**创建日期**: 2026-06-16
**作者**: requirement-analyst (via pm-orchestrator)
**来源锁定**: 用户简报（2026-06-16）中 US-1 ~ US-4，本文件扩展为 Given/When/Then 格式

---

## US-1 管理员上传文档

**作为**管理员（is_staff=True），  
**我希望**通过知识库管理页面上传三恒系统相关的 Word 或 PDF 文档，  
**以便**系统自动将其解析入库，供三恒知识专家检索作答使用。

### AC-1.1 非管理员无法访问知识库管理页面

```
Given 一个非管理员用户（is_staff=False）已登录
When  用户在浏览器直接访问 /admin/knowledge-base
Then  页面路由守卫将其重定向至首页（/home），不展示知识库管理内容
```

### AC-1.2 非管理员调用上传 API 返回 403

```
Given 一个非管理员用户（is_staff=False）已登录，持有有效 Token
When  用户对 POST /api/rag/documents/ 发起上传请求（携带合法 .pdf 文件）
Then  后端返回 HTTP 403 Forbidden
And   响应体包含 DRF 标准 403 错误结构
And   数据库未新增任何 RagDocument 记录
```

### AC-1.3 前端拦截非法文件类型

```
Given 管理员已进入知识库管理页面
When  管理员选择一个 .xlsx 文件（或 .jpg, .txt 等非 docx/pdf 文件）
Then  前端在浏览器侧弹出 el-message 错误提示："仅支持 .docx 和 .pdf 文件"
And   文件未被提交到后端上传接口
```

### AC-1.4 前端拦截超大文件

```
Given 管理员已进入知识库管理页面
When  管理员选择一个超过 50MB 的 .pdf 文件
Then  前端在浏览器侧弹出 el-message 错误提示："文件不能超过 50MB"
And   文件未被提交到后端上传接口
```

### AC-1.5 后端拦截伪造扩展名文件

```
Given 管理员已登录，持有有效 Token
When  管理员对 POST /api/rag/documents/ 上传一个扩展名为 .pdf 但 MIME 类型为 text/html 的文件
Then  后端返回 HTTP 400 Bad Request
And   响应体包含错误信息 "不支持的文件类型，仅接受 .docx 和 .pdf"
And   数据库未新增任何 RagDocument 记录
```

### AC-1.6 合法上传：文件立即入台账，状态为 pending/parsing

```
Given 管理员已登录，持有有效 Token
When  管理员对 POST /api/rag/documents/ 上传一个合法的 .pdf 文件（≤50MB）
Then  后端立即返回 HTTP 201 Created
And   响应体包含字段 {"id": <N>, "status": "pending", "file_name": <原始文件名>, "chunk_count": 0}
And   GET /api/rag/documents/ 响应列表中可见该文档（status=pending 或 parsing）
```

### AC-1.7 入库成功后状态变为 indexed 并显示 chunk 数

```
Given 管理员已上传一个包含文字的合法 .pdf 文件
When  后台解析+向量化任务完成（状态轮询最多等待 180 秒）
Then  GET /api/rag/documents/ 中该文档 status=indexed
And   chunk_count > 0
And   前端列表中该文档状态显示为绿色「已入库」标签，并展示 chunk 数
```

---

## US-2 文字与图片 OCR 解析入库

**作为**管理员，  
**我希望**系统能解析 PDF/Word 中的文字内容以及嵌入图片中的中文文字（通过 OCR），  
**以便**包含参数表截图等图片信息的技术文档也能被三恒专家检索到。

### AC-2.1 含中文图片的 PDF 入库后图文均可检索

```
Given 一个包含中文图片（如参数表截图）的 .pdf 文件已被管理员上传
When  后台解析任务完成，文档 status=indexed
Then  GET /api/rag/documents/{id}/（或列表）显示 chunk_count > 0
And   通过 search_sanheng_knowledge 工具以图片中出现的关键词查询
      得到命中结果，且该结果的 is_image_ocr=True
And   结果来源标注包含"图片OCR"字样（或等价标记）
```

### AC-2.2 图片 OCR 失败时：跳过该图片，整体入库不失败

```
Given 一个 PDF 包含一张 OCR 无法识别文字的图片（如纯图形/低分辨率模糊图）
When  后台解析任务运行，该图片 OCR 步骤失败（抛出异常或返回空字符串）
Then  系统跳过该图片（不创建对应 RagChunk），并在服务端记录 WARNING 日志
And   该文档的其余文字 chunk 正常入库
And   文档最终 status=indexed（非 failed）
And   chunk_count = 文字 chunk 数（不含无法 OCR 的图片 chunk）
```

### AC-2.3 某步骤关键失败：状态置 failed，错误原因可见且可重试

```
Given 管理员上传了一个合法的 .pdf 文件，但后台 embedding API 密钥无效
When  解析任务尝试调用向量化 API 失败（HTTP 401 或连接超时）
Then  文档 status 变为 failed
And   error_message 包含可读的失败原因（如 "向量化失败: Authentication error from embedding API"）
And   前端列表中该文档状态显示为红色「失败」标签
And   操作列出现「查看原因」按钮，点击后弹窗展示 error_message 全文
And   操作列同时出现「重试」按钮（仅 failed 状态下可见）
```

### AC-2.4 管理员触发重试后文档重新处理

```
Given 一个文档 status=failed（之前因 embedding API 故障导致）
And   embedding API 已恢复可用
When  管理员点击「重试」按钮，前端调用 POST /api/rag/documents/{id}/retry/
Then  后端返回 HTTP 200，文档 status 重置为 pending（或 parsing）
And   error_message 清空
And   后台重新执行解析+向量化任务
And   任务成功完成后 status=indexed，chunk_count > 0
```

### AC-2.5 .docx 文件文字 chunk 正确分块

```
Given 管理员上传一个包含多个段落的 .docx 文件（总字数 > 500 字）
When  文档 status=indexed
Then  chunk_count >= 1
And   各 chunk 的 page_or_section 字段包含段落序号信息（如"段落 3"）
And   is_image_ocr=False（纯文字段落）
```

---

## US-3 三恒专家检索增强作答

**作为**已登录用户，  
**我希望**通过与三恒知识专家对话获得基于知识库的精准回答，  
**以便**解决三恒系统的参数查询、故障排查、操作流程等实际问题。

### AC-3.1 知识库中有答案时：先检索后作答并标注来源

```
Given 知识库中已入库一份包含"冷凝水管道检查频率"内容的 PDF
When  用户在聊天界面发送"三恒系统冷凝水管道需要多久检查一次？"
Then  三恒专家节点（sanheng-knowledge）在内部调用 search_sanheng_knowledge 工具
And   工具返回命中 chunk（score ≥ 0.3）
And   专家回复包含命中内容中的关键信息
And   专家回复中包含来源标注（如"来源: 三恒系统维保手册.pdf · 第5页"）
And   整个过程对用户透明（来源可读，而非仅"根据知识库"的模糊表述）
```

### AC-3.2 知识库中无相关内容时：明确说明，不杜撰

```
Given 知识库已入库若干文档，但无任何关于"水力平衡阀调节步骤"的内容
When  用户在聊天界面发送"请问水力平衡阀怎么调节？步骤是什么？"
Then  三恒专家调用 search_sanheng_knowledge 后工具返回空列表（无命中）
And   专家回复中明确包含"知识库中未找到"或等价表述
And   专家不编造具体参数值、步骤、故障码
And   专家可基于 KNOWLEDGE.md 通用背景知识提供原理性参考，并明确说明这是通用知识
```

### AC-3.3 RAG embedding API 不可达时：聊天不报错，降级作答

```
Given embedding API 当前不可用（如网络断开或 RAG_EMBEDDING_API_KEY 未配置）
When  用户在聊天界面向三恒专家提问任意三恒相关问题
Then  search_sanheng_knowledge 工具内部捕获异常，返回 {"chunks": [], "degraded": True}
And   三恒专家收到降级信号，回复中包含提示："目前未接入知识资料库"或等价表述
And   专家继续基于 KNOWLEDGE.md 通用背景知识作答（不沉默，不报错）
And   聊天界面无任何错误弹窗或异常显示（对用户体验无影响）
```

### AC-3.4 知识库为空时（无任何已入库文档）：行为与 RAG 降级一致

```
Given 系统刚部署，未上传任何文档（或所有文档均为 failed 状态）
When  用户向三恒专家提问
Then  search_sanheng_knowledge 返回 {"chunks": [], "degraded": False}
And   专家正常作答（基于 KNOWLEDGE.md 通用背景），不报错
And   专家不主动提示"知识库为空"（沉默处理空库，与降级提示区分）
```

### AC-3.5 三恒专家图片 OCR 内容可被检索命中

```
Given 知识库已入库一份含温度设定参数表截图的 PDF，OCR 已提取该表格文字
When  用户提问"客厅温度设定范围是多少？"
Then  search_sanheng_knowledge 检索到来自图片 OCR 的 chunk（is_image_ocr=True）
And   专家回复引用该 chunk，来源标注包含"图片OCR"字样
```

---

## US-4 管理员删除知识库文档

**作为**管理员，  
**我希望**能删除已入库的知识库文档（台账+向量数据一并删除），  
**以便**下架过期或错误的文档，确保专家不再引用其中的内容。

### AC-4.1 删除后台账与向量一并删除

```
Given 知识库中存在一个 status=indexed 的文档（id=5），共 47 个 chunk
When  管理员在前端操作列点击「删除」并在 el-popconfirm 中确认
Then  前端调用 DELETE /api/rag/documents/5/，后端返回 HTTP 204 No Content
And   数据库中 id=5 的 RagDocument 记录被删除
And   所有 document_id=5 的 RagChunk 记录被级联删除（ON DELETE CASCADE）
And   前端列表中该文档消失
```

### AC-4.2 删除后后续检索不再命中已删除文档内容

```
Given 管理员已完成 AC-4.1 的删除操作（文档 id=5 已删除）
And   进程内向量缓存已刷新（删除触发缓存重载）
When  用户向三恒专家提问，且问题内容与已删除文档高度相关
Then  search_sanheng_knowledge 不返回任何来源为已删除文档的 chunk
And   专家如实反映"知识库中未找到相关内容"（不能凭旧缓存命中已删数据）
```

### AC-4.3 删除 parsing 或 failed 状态的文档也成功

```
Given 一个文档当前 status=parsing（后台任务正在运行）
When  管理员发起 DELETE /api/rag/documents/{id}/ 请求
Then  后端返回 HTTP 204 No Content
And   台账记录被删除
And   后台解析任务若此时检测到文档已被删除，安全退出（不崩溃）
```

### AC-4.4 删除不存在的文档返回 404

```
Given 管理员尝试删除一个不存在的文档（id=9999）
When  前端调用 DELETE /api/rag/documents/9999/
Then  后端返回 HTTP 404 Not Found
And   前端显示相应错误提示
```

---

## 附录：用户故事追踪矩阵

| 用户故事 | 关联需求编号 | 优先级 | 估算复杂度 |
|----------|-------------|--------|------------|
| US-1 管理员上传文档 | REQ-FUNC-RAG-01/02/03/12/13 | P0 | 高（含 DB 模型/API/前端/异步任务） |
| US-2 文字+图片 OCR 解析 | REQ-FUNC-RAG-05/06/07 | P0 | 高（含 OCR aarch64 验证约束） |
| US-3 专家检索增强作答 | REQ-FUNC-RAG-08/09/10/11 | P0 | 中（工具+提示改写，基础设施已有） |
| US-4 管理员删除文档 | REQ-FUNC-RAG-04 | P1 | 低（CASCADE 删除+缓存刷新） |

**优先级说明**：US-1、US-2 是基础设施（入库能力），US-3 是核心价值（专家检索），US-4 是管理能力。四个 US 相互依赖，US-3 依赖 US-1/US-2 完成，US-4 独立可并行。

---

## 附录：验收测试约束

- **测试环境**：`python manage.py test`（自动切 SQLite），不依赖生产 MySQL。
- **embedding API mock**：测试中需 mock `RAG_EMBEDDING_API_KEY` 环境变量 + 使用 `unittest.mock.patch` 替换 embedding API 调用，返回固定维度（1024）的 numpy 随机向量，避免测试依赖外部服务。
- **OCR mock**：rapidocr 调用在测试中 mock，返回固定中文字符串，避免 aarch64 依赖。
- **可复核**：test_engineer 必须提供可被主控直接复制执行的完整命令（含工作目录和环境变量设置），不得虚报通过。
