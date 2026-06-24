**特性**：多模态提问——用户图片输入与豆包视觉模型理解（Image Question Input）
**版本**：v1.5.0_multimodal_question
**状态**：DRAFT
**日期**：2026-06-24
**作者**：system-architect
**依赖**：requirements_spec.md (APPROVED), user_stories.md (APPROVED)

---

# 系统架构设计 — v1.5.0 多模态提问

**文档编号**：ARCH-DES-MQ-v150-001
**项目名称**：FreeArk 方舟智能体多模态提问（v1.5.0_multimodal_question）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-24
**输入文档**：
- `docs/requirements/v1.5.0_multimodal_question/requirements_spec.md` (APPROVED)
- `docs/requirements/v1.5.0_multimodal_question/user_stories.md` (APPROVED)
- `docs/architecture/v1.4.1_rag_image_citation/architecture_design.md` (APPROVED，基线参考)

---

## 1. 架构概览

### 1.1 背景与本期变更定位

v1.4.x 已建立三恒知识库 RAG + 图片引用能力的基线。现有聊天链路为**纯字符串管道**：`consumers.receive` → `LangGraphAdapter.stream_chat(message: str)` → `HumanMessage(content=str)` → orchestrator 各节点。

v1.5.0 以**最小侵入原则**在该基线上叠加多模态提问能力，核心变更集中在以下五个层面：

| 变更层 | 变更内容 | 影响范围 |
|--------|---------|---------|
| 前端 | 图片选择、压缩、预览、预上传调用 | `ChatView.vue`、`api.js` |
| REST 接口层 | 新增图片预上传端点 | `views_chat_image.py`、`urls.py` |
| VLM 服务层（新增） | doubao-vision 调用封装、进程内临时存储 | `vision_service.py`（新建） |
| WS 消费者层 | 读取 `image_upload_id`，支持 `vision_progress` kind | `consumers.py` |
| 编排适配器层 | `stream_chat` 签名扩展，VLM 调用前置 | `adapter.py`、`orchestrator.py` |

**不变原则**（来自 C-006）：
- `HumanMessage(content=...)` 的 content 永远是 `str`，不变更为多模态 list
- orchestrator `_route`/`_fan_out`/`_expert` 的核心字符串处理逻辑不变
- LangGraph 编排图结构不变（无新增节点）

### 1.2 架构风格

继承 v1.4.x 的**模块化单体（Modular Monolith）**架构风格，叠加多模态能力作为现有链路的前置扩展切面。无新增进程、无新增外部消息队列、无跨进程共享存储。

关联需求：REQ-NFR-002（Pi 5 资源约束、单 worker）、C-008（单进程，无跨进程共享需求）。

---

## 2. 架构决策记录（ADRs）

### ADR-MQ-001：VLM 调用位置 — adapter 层外置 vs LangGraph 节点

**背景（Context）**

REQ-FUNC-004 要求对图片调用 doubao-vision 并将分析结果注入 LangGraph 上下文。
REQ-FUNC-005 要求视觉描述无损传递到所有专家节点，不被 `_route`/`_fan_out` 丢弃。
C-006 要求 `HumanMessage(content=str)` 的类型不得变更。
现有 `LangGraphAdapter.stream_chat(message: str, session_key: str)` 是启动 `graph.astream` 的入口。

**决策选项**

| 维度 | Option A：adapter 层外置（stream_chat 内，graph.astream 启动前） | Option B：LangGraph 独立节点（route 前置节点） |
|------|----------------------------------------------------------------|----------------------------------------------|
| 实现复杂度 | 低。仅修改 `stream_chat` 签名与函数体，不改编排图 | 高。需新增节点、修改图的 `add_edge`、处理节点条件路由 |
| 编排图结构变更 | 无（图结构不变）| 有（在 route 前插入条件节点） |
| LangGraph checkpointer 兼容性 | 无需考虑（VLM 结果在图外完成）| 需要 checkpointer 支持新节点的中间状态持久化 |
| VLM 失败降级位置 | adapter 层直接捕获 `VisionServiceError`，不进图 | 节点内捕获，需向图外传播错误信号 |
| 测试隔离性 | 好。`stream_chat` 可独立 mock VLM 调用 | 中。需要构造完整图执行环境 |
| 与 C-006 兼容性 | 完全兼容（HumanMessage 仍收 str 前缀） | 完全兼容（节点内仍构建 str） |
| orchestrator 修改量 | 仅 State 新增 `vision_description` 字段 | State 新增字段 + 节点定义 + 图结构 |

**决策**：选择 Option A（adapter 层外置）。

**理由**：
1. REQ-NFR-002 要求不增加处理复杂度（Pi 5 资源受限）。adapter 层外置不改图结构，实现最简单。
2. REQ-NFR-004 要求降级路径清晰。Option A 中 VLM 失败在 adapter 层即可捕获处理，不需要在图节点内部传播错误状态。
3. C-008（单进程）使 checkpointer 无实质收益，Option B 的优势（checkpointer 持久化中间状态）在本项目中不成立。
4. REQ-NFR-006 要求 VLM 逻辑封装为独立模块。Option A 中 `vision_service.py` 被 adapter 调用，职责清晰。

**状态**：Accepted

**后果**：
- 正向：`LangGraphAdapter.stream_chat` 增加 `upload_id: Optional[str]` 参数，调用 `vision_service.analyze_image`，将 VLM 描述以文字前缀注入，再启动 `graph.astream`，不改图结构。`orchestrator.py` 仅新增 `State.vision_description` 字段。
- 负向：VLM 调用发生在 adapter 层，不在 LangGraph checkpointer 的保存范围内；若未来需要从 VLM 失败点断点续跑，需重新设计。此为已知权衡（OQ-MQ-002）。

---

### ADR-MQ-002：临时图片存储 — 进程内 dict vs Django cache vs /tmp 文件

**背景（Context）**

REQ-FUNC-002 要求图片预上传后以 `upload_id` 作为索引存入临时存储，TTL ≥ 10 分钟，不落 DB，不跨 worker。
REQ-NFR-002 要求进程内总临时图片占用 ≤ 50MB；单 worker 部署（C-008）。
REQ-NFR-004 要求 `upload_id` TTL 超期后返回 `IMAGE_EXPIRED`，不影响纯文字聊天。

**决策选项**

| 维度 | Option A：进程内 dict + TTL 惰性清理 | Option B：Django cache（locmem:// 或 file://） | Option C：/tmp 临时文件 |
|------|--------------------------------------|----------------------------------------------|------------------------|
| 实现复杂度 | 最低。Python dict + datetime，零依赖 | 中。需配置 CACHES，cache.set/get API，bytes 序列化 | 中。需 uuid 文件名管理 + 清理 cron/TTL |
| 依赖引入 | 无新依赖 | 无新包，但需 Django CACHES 配置 | 无新依赖，但需文件路径管理 |
| TTL 实现 | 惰性（get 时判断过期）+ 周期性全量扫描 | Django cache 原生 TTL（locmem 支持） | 需手写 TTL 判断或 cron 清理 |
| 字节大小限制（50MB） | 需手写计数逻辑 | locmem 无原生总量限制（需 MAX_ENTRIES 近似） | 需手写文件大小累计逻辑 |
| 跨 worker 共享 | 不支持（符合 C-008 要求）| locmem 不支持（符合）；file:// 支持但不需要 | 支持（超出 C-008 要求）|
| 重启后数据 | 丢失（REQ 可接受）| locmem 丢失；file:// 重启后保留 | 保留（超出需求，带来回收复杂度）|
| 内存使用 | 图片字节直接在堆上 | 同上（locmem 亦在内存） | 不占内存（磁盘 IO）；Pi 5 磁盘 IO 慢 |
| 安全性 | upload_id 绑定 user_id，内存中不可被枚举 | 同 Option A（locmem 同进程） | /tmp 文件权限需额外加固，filename 即可枚举 |

**决策**：选择 Option A（进程内 dict + TTL 惰性清理）。

**理由**：
1. REQ-NFR-002（单 worker、Pi 5 内存约束）使得 Option A 与 Option B（locmem）的内存表现等价，但 Option A 无需 Django CACHES 配置，实现更简单。
2. C-008 明确不需跨进程共享，三个方案均可满足，Option A 最简单。
3. Option C 的磁盘 IO 在 Pi 5（SD 卡或 SSD）上比内存操作慢，且文件清理机制比 dict TTL 更复杂（REQ-NFR-002 资源约束）。
4. REQ-NFR-003 SC-004 要求 upload_id 绑定上传者 user_id，Option A 在 dict 中存储 `{upload_id: {user_id, bytes, expire_at}}` 即可满足，无需额外机制。

**状态**：Accepted

**后果**：
- 正向：零配置依赖，TTL 和 50MB 上限均在 `vision_service.py` 内实现，逻辑完全自包含，易于单元测试。
- 负向：图片字节驻留在 Python 堆上；大量上传（理论）会增加 GC 压力。但 Pi 5 单 worker 场景并发极低，50MB 上限保护充分。重启后 TTL 内的已上传图片失效，用户需重新上传（已知权衡，RISK-MQ-005，可接受）。

---

### ADR-MQ-003：图片持久化策略 — VLM 描述文字追加 vs 原图存储

**背景（Context）**

REQ-FUNC-007 要求含图聊天轮次须在 `api_chat_session` 历史中被识别，但原图字节不存入 DB。
C-007 明确约束：原图字节不存入 DB / 聊天历史，只存 VLM 描述文字。
REQ-FUNC-008 要求历史会话中含图消息有视觉标注（图标或「含图提问」文字）。
Pi 5 存储/DB 膨胀约束（REQ-NFR-002）。

**决策选项**

| 维度 | Option A：VLM 描述文字追加到 user 消息（已决策 OQ-MQ-005） | Option B：原图字节存入独立 DB 表/字段 |
|------|-----------------------------------------------------------|-------------------------------------|
| DB 存储量 | 极小（VLM 描述文字，通常 100~500 字符） | 大（原始图片 JPEG，通常 100KB ~ 2MB） |
| Pi 5 磁盘影响 | 可忽略 | 显著（每张图片 0.1~2MB，对话历史积累快速膨胀）|
| 历史会话质量 | VLM 描述文字可被 LangGraph 历史注入（多轮上下文有效）| 原图需 VLM 再次调用才能理解（成本高）|
| 实现复杂度 | 低。`consumers._handle_chat` 修改 `append_message` 参数 | 高。新增 DB 表、FK 关联、图片读写接口 |
| 安全性 | VLM 描述文字安全，可记录日志 | 原图字节敏感，需加密存储或额外权限控制 |
| REQ-FUNC-008 支持 | 通过 `[图片描述：...]` 前缀检测，前端渲染「含图」标注 | 可以，但需额外接口取图 |

**决策**：选择 Option A（VLM 描述文字追加）。

**理由**：
1. C-007 硬约束已排除 Option B。
2. REQ-NFR-002 Pi 5 存储约束进一步强化 Option A。
3. 追加格式 `[图片描述：<VLM输出>] <原始文字>` 既满足 REQ-FUNC-007（LangGraph 历史注入有效），也支持 REQ-FUNC-008（前端通过检测 `[图片描述：` 前缀来渲染含图标注）。

**状态**：Accepted

**后果**：
- 正向：DB 体积不膨胀；多轮对话历史注入后 LangGraph 仍感知前轮图片内容摘要；REQ-FUNC-008 前端标注低成本实现（检测前缀字符串）。
- 负向：历史会话加载后 LangGraph 感知的是 VLM 描述文字而非原图，若用户追问「刚才那张图里的...」，智能体依赖 VLM 描述质量作答，而非原图重新分析。此为已知权衡（NT-005）。

---

## 3. 完整数据流图

### 3.1 图文混合提问完整链路（从前端点击发送到收到 stream_token）

```
[前端 ChatView.vue]
  │
  ① 用户选择图片 → onChange 事件
  │   - 文件大小校验（>10MB 拒绝）
  │   - Canvas 压缩（>1920px 等比缩放，JPEG quality=85）
  │   - 生成 Blob，显示预览缩略图（max-height: 80px）
  │
  ② 用户点击发送 → api.js::uploadChatImage(blob)
  │   POST /api/chat/image-upload/
  │   multipart/form-data，字段名 image
  │   Authorization: Bearer <token>
  │
  [后端 views_chat_image.py::ChatImageUploadView]
  │   - IsAuthenticated 鉴权
  │   - MIME 白名单验证（image/jpeg, image/png, image/webp, image/heic）
  │   - 字节大小 ≤ 10MB 校验
  │   - vision_service.store_upload(image_bytes, user_id) → upload_id (UUID)
  │   - 进程内 dict 存储 {upload_id → {user_id, bytes, expire_at}}
  │   响应：{"upload_id": "<uuid>", "expires_in": 600}
  │
  [前端收到 upload_id]
  │
  ③ WS 发送 chat_message 帧
  │   {"type":"chat_message","message":"<用户文字>","image_upload_id":"<uuid>"}
  │
  [后端 consumers.py::ChatConsumer.receive]
  │   - 读取 user_message = data.get('message','').strip()
  │   - 读取 upload_id = data.get('image_upload_id')
  │   - 若 message 为空且有 upload_id：注入默认文案「请帮我分析这张图片」
  │   - 调用 _handle_chat(user_message, upload_id=upload_id)
  │
  [consumers._handle_chat]
  │   - 发送 WS kind=vision_progress（若有 upload_id）
  │     → 前端显示「正在分析图片，请稍候…」
  │
  [adapter.py::LangGraphAdapter.stream_chat(message, session_key, upload_id)]
  │   - 若 upload_id 非空：
  │     ④ vision_service.get_upload(upload_id, user_id) → image_bytes
  │        - upload_id 不存在或已过期 → raise ImageExpiredError
  │        - user_id 不匹配 → raise ImageAccessDeniedError
  │     ⑤ vision_service.analyze_image(image_bytes, user_text) → description (str)
  │        - asyncio.timeout(30s)
  │        - 失败 1 次 → 指数退避 2s → 重试 1 次
  │        - 2 次均失败 → raise VisionServiceError
  │        - 调用完成后立即释放 image_bytes 引用
  │     ⑥ 构建增强消息：
  │        enhanced_message = f"[用户图片分析：{description}]\n\n{message}"
  │   - 若 upload_id 为空：enhanced_message = message（不变）
  │   - 启动 graph.astream({"messages":[HumanMessage(content=enhanced_message)], ...})
  │
  [orchestrator.py — 图内节点，结构不变]
  │   - _route(state)：对 enhanced_message（含 VLM 前缀）做意图分类，路由到专家
  │   - _fan_out(state)：生成 plan=[(name, enhanced_message)]
  │   - _expert(name, query=enhanced_message)：调用专家工具，query 含 VLM 描述
  │   - State.vision_description 记录 VLM 描述文字（用于调试/观测）
  │
  ⑦ 图流式输出 → adapter._drive → consumers._pump
  │   - kind=reasoning_token / stream_token / stream_end 正常输出
  │
  [consumers._handle_chat 图流式完成后]
  ⑧ 持久化：chat_memory.append_message(session, 'user', enhanced_message)
  │   - 存入格式：「[图片描述：<VLM输出>] <原始文字>」（用于历史会话加载）
  │
  [前端]
  ⑨ 收到 stream_token 流式内容，渲染回答
     收到 stream_end，图片预览清空，下一轮默认纯文字状态
```

### 3.2 降级链路（VLM 调用失败）

```
[adapter.stream_chat — VLM 调用]
  │   - 2 次调用均失败（超时/5xx）
  │   → raise VisionServiceError(message="图片分析暂时不可用，您可以用文字描述图片内容后重试")
  │
[consumers._handle_chat — 捕获 VisionServiceError]
  │   - 发送 WS：{"type":"error","code":"IMAGE_ANALYSIS_FAILED","message":"图片分析暂时不可用，..."}
  │   - _is_streaming 重置为 False
  │   - WS 连接保持，不触发系统级错误
  │   - 记录 ERROR 级日志（不含图片字节）
```

### 3.3 图片过期链路

```
[consumers.receive — 读取 upload_id]
  │   - vision_service.get_upload(upload_id, user_id) 返回 None（TTL 超期）
  │   → 发送 WS：{"type":"error","code":"IMAGE_EXPIRED","message":"图片已过期，请重新上传"}
  │   - 不继续处理（提前返回）
  │   - WS 连接保持
```

---

## 4. 安全架构说明

### 4.1 base64 隔离策略

遵循 REQ-NFR-003 SC-001/SC-002：

| 层次 | base64 处理规则 |
|------|----------------|
| 前端 | 图片以 Blob 对象在内存中处理，通过 `multipart/form-data` 上传，**不做 base64 编码** |
| REST 上传端点 | 接收二进制流（`request.FILES['image'].read()`），不写入任何日志；响应只含 `upload_id` |
| 进程内临时存储 | 存储原始字节（bytes），不编码为 base64 |
| VLM 调用（vision_service.py） | 调用 doubao-vision API 时，SDK 内部将 bytes 编码为 base64 后放入 payload；此操作在 SDK 内部，**不由业务代码手动构造 base64 字符串**，不记录到 logger |
| WS 帧 | 只传 `upload_id`（UUID 字符串），**绝不含 base64 或图片字节** |
| 日志 | `vision_service.py` 所有 logger 调用只记录调用时间、耗时、成功/失败状态；禁止记录 image_bytes 或 base64 参数 |

### 4.2 鉴权与 upload_id 安全

遵循 REQ-NFR-003 SC-004/SC-005：

- 预上传端点 `POST /api/chat/image-upload/` 使用 `IsAuthenticated` 鉴权（Bearer Token，与现有 WS 鉴权体系一致）
- `upload_id` 为服务端生成的 `uuid.uuid4()`，不可枚举（禁止自增整数）
- 进程内存储时绑定 `user_id`：`get_upload(upload_id, user_id)` 验证 user_id 匹配，防止跨用户取图
- 前端通过 `api.js`（`authenticatedFetch`）调用预上传接口，禁止裸 axios（C-010）

### 4.3 MIME 白名单

遵循 REQ-NFR-003 SC-006，服务端验证（前端限制仅为 UX 辅助）：

允许的 MIME 类型：`image/jpeg`、`image/png`、`image/webp`、`image/heic`、`image/heif`

验证方式：`python-magic` 读取文件头魔数（Magic Number），而非信任 `Content-Type` 头（可伪造）。

### 4.4 API Key 保护

遵循 REQ-NFR-003 SC-003：
- doubao-vision API key 仅从 `.env` → Django `settings.py` 读取
- 绝不写入 git（`.env` 在 `.gitignore` 中）、HTTP 响应、日志、前端变量
- `vision_service.py` 通过 `from django.conf import settings` 读取，不接受外部传入

---

## 5. 降级策略架构

### 5.1 降级层次（按优先级）

```
Level 1：图片过期降级（upload_id TTL 超期）
  → WS 发送 IMAGE_EXPIRED 错误，用户重新上传即可，WS 保持
  
Level 2：VLM 调用失败降级（超时/5xx，2次均失败）
  → WS 发送 IMAGE_ANALYSIS_FAILED 错误，友好提示，WS 保持
  → 本期不做 RapidOCR 兜底（NS-002 明确排除）
  
Level 3：预上传端点故障
  → 前端在 uploadChatImage 失败后允许降级为纯文字发送
  → 纯文字聊天 WS 链路完全不受影响（代码路径完全分离）
  
Level 4：临时存储满（超过 50MB 上限）
  → 预上传接口返回 503，提示「服务繁忙，请稍后重试」
  → 现有 WS 连接纯文字功能不受影响
```

### 5.2 降级 WS 消息规范

| 场景 | WS 消息格式 |
|------|-----------|
| 图片过期 | `{"type":"error","code":"IMAGE_EXPIRED","message":"图片已过期，请重新上传"}` |
| VLM 分析失败 | `{"type":"error","code":"IMAGE_ANALYSIS_FAILED","message":"图片分析暂时不可用，您可以用文字描述图片内容后重试"}` |
| 图片引用无效 | `{"type":"error","code":"IMAGE_INVALID","message":"图片引用无效"}` |
| 进度通知 | `{"type":"vision_progress","message":"正在分析图片，请稍候…"}` |

---

## 6. 需求覆盖矩阵

| 需求 ID | 描述摘要 | 覆盖模块/设计节点 |
|---------|---------|-----------------|
| REQ-FUNC-001 | 前端图片上传入口 | MOD-MQ-01（ChatView.vue 前端模块） |
| REQ-FUNC-002 | 图片预上传 REST 接口 | MOD-MQ-02（views_chat_image.py）+ MOD-MQ-03（vision_service.py 存储） |
| REQ-FUNC-003 | WS 协议扩展，携带 upload_id | MOD-MQ-04（consumers.py 扩展）|
| REQ-FUNC-004 | doubao-vision VLM 调用 | MOD-MQ-03（vision_service.py VLM 调用）+ ADR-MQ-001 |
| REQ-FUNC-005 | 视觉分析结果注入编排图 | MOD-MQ-05（adapter.py 扩展）+ MOD-MQ-06（orchestrator.py 扩展）|
| REQ-FUNC-006 | 超时/降级 UX | MOD-MQ-03（VisionServiceError）+ MOD-MQ-04（降级 WS 消息）+ 第 5 节 |
| REQ-FUNC-007 | 图片消息持久化（VLM 描述追加） | MOD-MQ-04（consumers append_message 修改）+ ADR-MQ-003 |
| REQ-FUNC-008 | 历史含图消息标注展示 | MOD-MQ-01（ChatView.vue 前缀检测渲染）+ ADR-MQ-003 |
| REQ-NFR-001 | 端到端时延 ≤20s P90 | ADR-MQ-001（adapter 外置减少图路径），VLM 30s 超时保护 |
| REQ-NFR-002 | Pi 5 资源约束（内存/CPU/存储）| ADR-MQ-002（50MB 上限）+ ADR-MQ-003（不存原图）|
| REQ-NFR-003 | 安全约束（base64/API key/鉴权）| 第 4 节安全架构 |
| REQ-NFR-004 | 降级与 fail-open | 第 5 节降级架构 |
| REQ-NFR-005 | 可观测性（VLM 调用日志）| MOD-MQ-03（logging 规范）|
| REQ-NFR-006 | 可维护性（独立模块、settings 注释）| MOD-MQ-03（独立 vision_service.py）+ MOD-MQ-07（settings 变量）|

**覆盖结论**：REQ-FUNC-001 ~ REQ-FUNC-008 全部覆盖，REQ-NFR-001 ~ REQ-NFR-006 全部覆盖。

---

## 7. 开放问题（架构阶段后遗留）

| OQ 编号 | 问题 | 影响 | 建议处理时机 |
|---------|------|------|------------|
| OQ-MQ-006 | 前端压缩参数 quality=80 vs 85（建议 85，实测 Pi WiFi 带宽可接受） | REQ-FUNC-001 压缩参数 | 开发阶段用真实铭牌样本实测；本文档采用 quality=85 |
| — | `python-magic` 是否需要新增安装包 | MIME 白名单验证实现 | 见 tech_stack.md；若不引入则改用文件头手动判断 |

---

*文档状态：DRAFT（2026-06-24）。待 PM 门控通过后更新为 APPROVED。*
