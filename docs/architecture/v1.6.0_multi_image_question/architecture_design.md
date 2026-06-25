**特性**：多图提问——最多5张图片批量上传与分析（Multi-Image Question）
**版本**：v1.6.0_multi_image_question
**状态**：DRAFT
**日期**：2026-06-24
**作者**：system-architect
**依赖**：
- `docs/requirements/v1.6.0_multi_image_question/requirements_spec.md` (APPROVED，用户确认)
- `docs/architecture/v1.5.0_multimodal_question/architecture_design.md` (DRAFT，基线)
- `docs/architecture/v1.5.0_multimodal_question/module_design.md` (DRAFT，基线)

---

# 系统架构设计 — v1.6.0 多图提问（基于 v1.5.0 增量）

**文档编号**：ARCH-DES-MI-v160-001
**项目名称**：FreeArk 方舟智能体多图提问（v1.6.0_multi_image_question）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-24

---

## 1. 架构概览

### 1.1 背景与本期增量定位

v1.5.0 已实现单图提问能力，建立了"REST 预上传 → upload_id → WS 携带 → adapter VLM 前置调用 → 增强消息注入"的完整链路。

v1.6.0 以**最小侵入增量原则**在该链路上扩展多图能力（最多5张），核心约束：

- **向后兼容硬约束**：旧客户端发送 `image_upload_id`（单数字段）的行为必须与 v1.5.0 完全一致，零退化。
- **容错优先（OQ-MI-001 = 方案A）**：2~5 张图中部分 VLM 失败时，成功的图正常注入，失败的图占位标注，非阻塞。
- **无 DB migration**：沿用进程内存储，各 upload_id 独立存储，无需改变存储结构。

### 1.2 本版本变更层

基于 v1.5.0，本版本变更集中在以下层面：

| 变更层 | 变更内容 | 影响范围 | 变更类型 |
|--------|---------|---------|---------|
| 前端 | 单图 state 扩展为列表（selectedImages）、超5张拦截、并发上传、多图预览与删除 | `ChatView.vue`、`api.js` | 修改（增量）|
| WS 协议层 | 新增 `image_upload_ids`（列表字段），与旧 `image_upload_id` 共存，新字段优先 | WS 帧协议 | 扩展（向后兼容）|
| WS 消费者层 | 读取 `image_upload_ids`，向后兼容解析，多图默认文案，多张 vision_progress | `consumers.py` | 修改（增量）|
| 编排适配器层 | `stream_chat` 签名扩展 `upload_ids: list[str]`，串行或并发 VLM 多图批处理 | `adapter.py` | 修改（增量）|
| VLM 服务层 | 新增 `analyze_images_batch()` 函数，逐图独立调用，聚合有序结果 | `vision_service.py` | 修改（新增函数）|

**不变项**（继承 v1.5.0 全部不变约束）：
- `HumanMessage(content=...)` 的 content 永远是 `str`，多图分析结果合并为单一字符串注入。
- `views_chat_image.py` REST 上传端点不变（单图上传接口，多图由前端多次调用）。
- LangGraph 编排图结构不变（无新增节点）。
- 进程内 dict 存储结构不变（各 upload_id 独立条目）。

### 1.3 架构风格

继承 v1.5.0 的**模块化单体（Modular Monolith）**架构风格。无新增进程、无新增外部消息队列、无跨进程共享存储。

关联需求：REQ-MI-NFR（Pi 5 资源约束、单 worker）、约束 C-008（单进程）。

---

## 2. 架构决策记录（ADRs）

### ADR-MI-001：VLM 调用策略 — 逐图独立调用 vs 一次多图调用

**Status**：Accepted

**Context**

REQ-MI-004 要求多图 VLM 分析结果有序，与上传顺序一致。
REQ-MI-007（OQ-MI-001 = 方案A）要求部分失败容错：单张图片 VLM 失败不阻断其余图片的分析，失败位置以占位标注 `[用户图片N分析：图片分析失败，已跳过]` 填充。
NFR 约束：整体 VLM 处理总计 ≤90s（RISK-MI-002）；每张开始分析前发送 vision_progress 帧。
v1.5.0 基线：`vision_service.analyze_image(image_bytes, user_text)` 是单图分析接口，已在生产验证可用。

**Options**

| 维度 | Option A：逐图独立调用（asyncio.gather with exception handling） | Option B：一次多图 API 调用 |
|------|----------------------------------------------------------------|--------------------------|
| 部分失败语义 | 天然满足。每图 try/except 独立捕获，失败图占位，不影响其余图 | 不天然满足。一次调用失败=全失败（除非额外实现 per-image fallback，复杂度倍增）|
| REQ-MI-007 兼容性 | 直接满足容错优先（方案A）| 需要额外分析 API 响应中每张图的结果，若 API 不支持部分成功则需设计复杂 fallback |
| 网络延迟 | 并发（asyncio.gather）N 张总耗时 ≈ 最慢一张；不存在 N 倍延迟 | 理论上最快（一次网络往返），但 doubao-vision 不保证支持多图 batch 接口，需要额外验证 |
| doubao-vision API 兼容性 | 完全兼容。v1.5.0 已验证单图接口（`openai-compatible`），复用现有 `analyze_image` | 需要确认火山方舟 doubao-vision 是否支持单次请求多图（未验证）；无文档保证 |
| Pi 5 内存峰值 | asyncio.gather 并发时，5 张图 base64 编码同时在内存中（≤10MB 原图 → 缩放后 ≤2MB/张 → 5×2MB = 10MB）；低于 50MB 上限，可接受 | 单次更低，但同上风险 |
| 超时控制粒度 | 每张独立 asyncio.timeout(30s)；整体加 asyncio.timeout(90s) 兜底 | 单次超时控制需覆盖所有图片，超时粒度较粗 |
| 对现有 vision_service 侵入 | 低。在现有 `analyze_image` 基础上新增 `analyze_images_batch`，包装 gather 逻辑 | 需要新增完全不同的调用路径，可能需要重写 `analyze_image` 或新增独立函数 |
| vision_progress 帧（每张发一个）| 支持：逐图调用前可依次发送进度帧 | 难以实现：一次调用无法区分"正在分析第X张" |

**Decision**：选择 Option A（逐图独立调用，asyncio.gather with exception handling）。

**理由**：
1. REQ-MI-007（OQ-MI-001 = 方案A）的容错优先语义要求"单张失败不拖垮其余"，Option A 天然满足，Option B 需要额外复杂 fallback 设计。
2. doubao-vision API 仅验证了单图接口（v1.5.0 生产验证），一次多图 batch 接口未验证，贸然使用存在兼容性风险（[KE-ARCH-007]）。
3. asyncio.gather 并发时，Pi 5 内存峰值约 10MB（5张 ×2MB），远低于 50MB 上限（NFR 约束），内存压力可接受。
4. 每张图开始分析前独立发送 vision_progress 帧（NFR 要求"每张图片开始分析前发出"），Option A 支持精细进度，Option B 不支持。
5. 整体 90s 上限通过外层 asyncio.timeout(90) 保障（RISK-MI-002 缓解），与 Option A 无冲突。

**Consequences**：
- 正向：REQ-MI-007 容错语义零额外工作；doubao-vision 兼容性有生产基础；vision_progress 精确到每张图；实现只是现有 `analyze_image` 的 gather 包装，测试复用度高。
- 负向：并发 VLM 调用可能增加豆包 API 并发占用（不影响 Pi 5 本身，但需确认火山方舟账号并发配额）。若 5 张均为大图（缩放后仍 ≈2MB），并发编码 5 个 base64 字符串时有短暂内存峰值；实测5张压缩后合计≤10MB，影响极小。

---

### ADR-MI-002：前端多图上传策略 — 并发 POST vs 串行 POST

**Status**：Accepted

**Context**

REQ-MI-001 要求前端支持最多5张图片选择与预上传。
REQ-MI-002 要求超过5张时明确拦截，已有5张时禁用上传按钮。
v1.5.0 基线：`api.js::uploadChatImage(file)` 单图 POST，`views_chat_image.py` 单图接收端点不变。
Pi 5 网络环境：单图压缩后通常 ≤2MB，5张 ≤10MB；Pi 5 内存充裕（≥8GB），浏览器端并发无阻。
WS 发送时机：所有图片均上传完成、拿到全部 upload_id 后，才发送 WS chat_message 帧（防止 WS 消费时部分 upload_id 尚未入存储）。

**Options**

| 维度 | Option A：并发 POST（5张同时发起，Promise.all 等全部完成） | Option B：串行 POST（逐张等待响应后发下一张）|
|------|--------------------------------------------------------|---------------------------------------------|
| 用户等待时间 | 最短。5张并发时总耗时 ≈ 最慢一张（含网络往返）；Pi 5 局域网下单图上传约 50~200ms，5张并发合计 ≈ 200ms | 最长。5张串行时总耗时 ≈ 5 × 单图耗时；Pi 5 局域网下约 250~1000ms |
| Pi 5 服务端内存压力 | 并发时服务端同时接收5个 POST，5 张图片同时在内存中（≤10MB）；50MB 上限保护有效 | 服务端单次只处理1张，内存峰值更低，但用户等待更长 |
| 实现复杂度 | 低。`Promise.all(images.map(uploadChatImage))` 一行逻辑 | 低。`for...of + await` 循环 |
| 失败处理 | `Promise.all` 中任一失败则整体失败（Promise.allSettled 可实现部分成功）；与 OQ-MI-001 方案A 精神一致：前端尽力收集全部 upload_id | 串行时可逐张处理失败，但用户体验更差（整体更慢）|
| 服务端 `check_capacity` 竞争 | 5 个并发 POST 可能同时通过 `check_capacity()` 检查，理论上允许略超容量；但5张 ≤10MB 远低于50MB上限，实际无影响 | 无竞争，但无实际保护价值（容量裕量充足）|
| 与 Pi 5 单 worker 兼容性 | 兼容。单 worker ASGI（uvicorn）支持并发异步处理多个 REST 请求；`store_upload` 有 threading.Lock 保护 | 完全兼容，但无并发收益 |

**Decision**：选择 Option A（并发 POST，`Promise.allSettled` 等全部完成后发 WS 帧）。

**理由**：
1. 用户等待时间是最重要的 UX 指标：并发上传将5张图的上传等待时间从 O(N) 降至 O(1)（最慢一张），Pi 5 局域网环境实测改善约 4×（REQ-MI-001 含蓄的 UX 约束）。
2. Pi 5 内存压力：5张 ≤10MB 远低于 50MB 上限，并发无实际风险（[KE-ARCH-008]）。
3. 使用 `Promise.allSettled`（而非 `Promise.all`）：允许部分图片上传失败时仍继续——收集成功的 upload_id，对失败的图片前端提示用户并从发送列表中移除，不阻断整次提问（与 OQ-MI-001 方案A 容错精神一致）。
4. 实现简单（关联 REQ-MI-NFR Pi 5 约束——简单即健壮）。

**Consequences**：
- 正向：上传耗时降至单张级别，UX 显著改善；`Promise.allSettled` 提供部分失败容错，与后端容错策略一致。
- 负向：服务端 5 个并发 POST 同时到达，`_store_lock` 会有短暂串行化（threading.Lock），但由于每张操作极快（内存写入），锁争用时间 <1ms，无实际影响。

---

### ADR-MI-003：WS 协议扩展策略 — 新字段命名与旧字段共存规则

**Status**：Accepted

**Context**

REQ-MI-003 要求：旧 `image_upload_id`（单数字符串字段）继续工作，行为与 v1.5.0 完全一致（向后兼容硬约束）。新增 `image_upload_ids`（复数列表字段）用于多图场景，两者可同时存在，新字段优先。

**Options**

| 维度 | Option A：新增 `image_upload_ids` 列表字段，与旧 `image_upload_id` 共存，新字段优先 | Option B：复用 `image_upload_id` 但允许传列表（类型变更为 str 或 list[str]）| Option C：废弃旧字段，只用 `image_upload_ids`（breaking change）|
|------|------------------------------------------------------------------------------------|--------------------------------------------------------------------------|------------------------------------------------------------------|
| 向后兼容性 | 完全向后兼容。旧客户端只发 `image_upload_id`，新字段不存在，消费者走 v1.5.0 代码路径 | 不兼容。改变现有字段类型（str → str\|list[str]）可能破坏旧客户端，且消费者需类型判断，复杂且易错 | 完全不兼容。旧客户端发的 `image_upload_id` 被忽略，单图功能退化 |
| 实现清晰度 | 高。两个字段职责明确，消费者逻辑清晰：先检查 `image_upload_ids`，再检查 `image_upload_id` | 低。类型二义性（字段可为 str 或 list），消费者需 `isinstance` 判断，容易引入 bug | N/A（不满足 REQ-MI-003）|
| REQ-MI-003 满足度 | 完全满足（明确要求两字段共存，新字段优先）| 不满足（改变现有字段类型违反"旧字段继续工作"语义）| 不满足 |
| 命名规范 | 符合 REST/WS 约定（单数→字符串，复数→列表）| 违反语义（单数字段承载列表值）| N/A |

**Decision**：选择 Option A（新增 `image_upload_ids` 列表字段，与旧 `image_upload_id` 共存，新字段优先）。

**优先级解析规则**（消费者 `receive` 方法中的冲突解决顺序）：

```
Step 1：检查 data.get('image_upload_ids')
  - 若存在且为非空 list → 使用 image_upload_ids（新路径，多图）
  - 若存在且为空 list → 视为无图，走纯文字路径
Step 2：否则检查 data.get('image_upload_id')
  - 若存在且非 None → 使用 [image_upload_id]（兼容旧字段，单图包装为列表后走同一处理路径）
Step 3：两者均不存在 → 无图，纯文字路径（与 v1.4.x 完全一致）
```

**理由**：
1. REQ-MI-003 明确指定"两字段共存，新字段优先"，Option A 是直接实现，无歧义。
2. 字段命名的单复数约定（单数→标量，复数→列表）符合行业规范，降低维护成本。
3. 消费者代码复杂度最低：一个 if-elif-else 分支即可覆盖所有场景（[ASSUMPTION] 旧字段单图包装为单元素列表后复用相同的多图处理逻辑，无需维护两套路径）。

**Consequences**：
- 正向：完全向后兼容（REQ-MI-003 满足）；消费者逻辑清晰；新旧客户端可并存运行。
- 负向：需要在 consumers.py 中维护字段解析逻辑（约5行代码）；若未来废弃旧字段还需清理。此为已知权衡，可接受。

---

### ADR-MI-004：部分失败占位格式 — OQ-MI-001 方案A 的具体实现

**Status**：Accepted

**Context**

REQ-MI-007（OQ-MI-001 = 方案A）：部分 VLM 失败时，成功图正常注入，失败图占位标注，非阻塞通知用户。
REQ-MI-005：注入格式为 `[用户图片N分析：<descN>]\n...`，单图改为 `[用户图片1分析：<desc>]`（统一编号）。
REQ-MI-008：持久化格式为 `[图片1描述：<desc1>] [图片2描述：<desc2>] ... <原始文字>`。
REQ-MI-009：新增错误码 `IMAGE_ANALYSIS_PARTIAL`（部分失败）。

需要决策：
1. 失败图在注入消息中的占位文字。
2. 失败图在持久化消息中的占位文字。
3. 部分失败时的 WS 通知方式（阻塞式错误 vs 非阻塞通知）。

**Options**

| 维度 | Option A：占位文字 + 非阻塞 WS 通知帧（并行于 stream_token 流） | Option B：注入空字符串占位 + 失败后发阻塞错误帧（停止流）|
|------|---------------------------------------------------------------|--------------------------------------------------------|
| 用户体验 | 好。LLM 收到占位文字，知晓图N未能分析，可在回答中说明；用户同时看到非阻塞通知 | 差。阻塞错误意味着整次提问被中断，与 OQ-MI-001 方案A 精神矛盾 |
| REQ-MI-007 满足度 | 完全满足（成功图正常注入，失败图占位，非阻塞通知）| 不满足（阻塞中断整次提问）|
| 注入消息质量 | LLM 感知到"图3分析失败"，可在回答中智能处理（如忽略图3或提示用户重传）| LLM 收到空内容，行为不可预测 |
| 持久化可追溯 | 持久化记录包含占位标注，历史会话可判断哪张图分析失败 | 历史中无失败记录，可追溯性差 |
| 实现复杂度 | 低。try/except 捕获每张图失败，替换为占位字符串；流开始后发非阻塞通知帧 | 同等复杂度，但 UX 更差 |

**Decision**：选择 Option A（占位文字 + 非阻塞 WS 通知帧）。

**具体占位格式**（本 ADR 确定的格式规范）：

| 场景 | 格式 |
|------|------|
| 注入 LangGraph 的增强消息（成功图N） | `[用户图片N分析：<descN>]` |
| 注入 LangGraph 的增强消息（失败图N） | `[用户图片N分析：图片分析失败，已跳过]` |
| 注入 LangGraph 的多图合并格式 | `[用户图片1分析：<desc1>]\n[用户图片2分析：图片分析失败，已跳过]\n[用户图片3分析：<desc3>]\n\n<原始文字>` |
| 持久化消息（成功图N） | `[图片N描述：<descN>]` |
| 持久化消息（失败图N） | `[图片N描述：图片分析失败]` |
| 持久化消息（多图合并） | `[图片1描述：<desc1>] [图片2描述：图片分析失败] [图片3描述：<desc3>] <原始文字>` |
| 部分失败 WS 通知帧 | `{"type":"error","code":"IMAGE_ANALYSIS_PARTIAL","message":"图片N分析失败，已用占位文字替代，其余图片分析正常"}` |
| 全部失败 WS 通知帧 | `{"type":"error","code":"IMAGE_ANALYSIS_FAILED","message":"全部图片分析失败，请重试或用文字描述图片内容"}` |

**理由**：
1. REQ-MI-007 明确指定"非阻塞提示用户"，阻塞错误违反需求。
2. 占位文字 `[用户图片N分析：图片分析失败，已跳过]` 给 LLM 提供明确信号，比空字符串更安全（防 LLM 幻觉）（REQ-MI-005 的扩展）。
3. REQ-MI-009 `IMAGE_ANALYSIS_PARTIAL` 错误码通过非阻塞通知帧实现，与 v1.5.0 已有的 WS 错误帧格式一致（复用 `_send_error` 基础设施）。
4. 全部失败时（所有图均无法分析）仍发 `IMAGE_ANALYSIS_FAILED`（与 v1.5.0 行为一致，保持用户预期稳定）。

**Consequences**：
- 正向：部分失败场景 LLM 仍能产生有意义的回答；历史记录包含失败占位，可追溯；WS 连接保持（用户可继续聊天）。
- 负向：注入消息中包含失败占位文字，LLM 可能提及"图3分析失败"——这是预期行为而非缺陷；全部失败时需单独判断并发 `IMAGE_ANALYSIS_FAILED`（条件判断逻辑需在 adapter 层处理，约5行）。

---

## 3. 数据流图（多图路径）

### 3.1 多图提问完整链路

```
[前端 ChatView.vue]
  │
  ① 用户选择多张图片（最多5张）
  │   - selectedImages: array（最多5个元素，超5张禁用上传按钮，REQ-MI-002）
  │   - 逐张显示预览缩略图，可逐个删除（REQ-MI-001）
  │   - 客户端压缩（同 v1.5.0：Canvas 等比缩放，JPEG quality=0.85）
  │   - 纯文字为空时默认文案：多图「请帮我分析这些图片」（OQ-MI-004，REQ-MI-NFR）
  │
  ② 用户点击发送 → api.js::uploadChatImages(files: File[])
  │   并发（Promise.allSettled）对每张图调用 POST /api/chat/image-upload/
  │   （复用 v1.5.0 uploadChatImage，循环调用，ADR-MI-002）
  │   收集成功的 upload_id 列表；上传失败的图片前端提示用户并排除
  │
  [后端 views_chat_image.py — 不变，单图上传端点]
  │   每图独立接收、校验、存储 → 返回 upload_id
  │   （5个 POST 并发到达，store_upload 有 threading.Lock 保护）
  │
  [前端收到全部 upload_ids 列表]
  │
  ③ WS 发送 chat_message 帧（REQ-MI-003，ADR-MI-003）
  │   {
  │     "type": "chat_message",
  │     "message": "<用户文字或空>",
  │     "image_upload_ids": ["<uuid1>", "<uuid2>", ..., "<uuid5>"]
  │   }
  │
  [后端 consumers.py::ChatConsumer.receive — v1.6.0 扩展]
  │   - 字段解析（ADR-MI-003 优先规则）：
  │       检查 image_upload_ids → 存在且非空列表 → 使用多图路径
  │       否则检查 image_upload_id → 存在 → 包装为 [id] 走相同路径（向后兼容）
  │   - 逐个 UUID 格式校验（REQ-MI-NFR）
  │   - 超5个拦截 → 发送 IMAGE_TOO_MANY 错误帧（REQ-MI-009）
  │   - TTL 预检（逐图调用 vision_service.get_upload，任一过期 → 发 IMAGE_EXPIRED 错误，return）
  │   - 多图时默认文案注入（OQ-MI-004）
  │   - 调用 _handle_chat(user_message, upload_ids=upload_ids)
  │
  [consumers._handle_chat]
  │   ④ 逐图发送 vision_progress 帧（每张开始分析前）：
  │       {"type":"vision_progress","message":"正在分析第1/N张图片，请稍候…"}
  │       …
  │       {"type":"vision_progress","message":"正在分析第N/N张图片，请稍候…"}
  │       （注：progress 帧由 adapter 通过 yield ("vision_progress", text) 回传给 consumers）
  │   
  [adapter.py::LangGraphAdapter.stream_chat — v1.6.0 扩展]
  │   upload_ids 非空时：
  │   ⑤ image_bytes_list = [vision_service.get_upload(uid, user_id) for uid in upload_ids]
  │   ⑥ vision_service.analyze_images_batch(image_bytes_list, user_text, progress_cb)
  │      → 内部对每张图：
  │         yield vision_progress 帧
  │         asyncio.gather（并发，return_exceptions=True）调用 analyze_image
  │         失败图 → 占位字符串（ADR-MI-004）
  │      → 返回 results: list[str]（有序，含成功描述或占位字符串）
  │   ⑦ 构建增强消息（REQ-MI-005）：
  │      enhanced_message = "[用户图片1分析：desc1]\n[用户图片2分析：desc2]\n...\n\n<原始文字>"
  │   ⑧ 若有失败图 → yield ("image_analysis_partial", partial_info)
  │      consumers 收到后发 IMAGE_ANALYSIS_PARTIAL 非阻塞通知帧
  │   ⑨ 若全部失败 → raise VisionServiceError（与 v1.5.0 全失败降级路径一致）
  │   ⑩ 释放 image_bytes_list 引用（del）
  │   ⑪ vision_service.delete_upload（逐图清理）
  │   ⑫ 构建持久化消息（REQ-MI-008）：
  │      persist_msg = "[图片1描述：desc1] [图片2描述：desc2] ... <原始文字>"
  │   ⑬ 启动 graph.astream({"messages":[HumanMessage(content=enhanced_message)], ...})
  │
  [orchestrator.py — 结构不变]
  │   enhanced_message（含多图 VLM 前缀）→ _route 意图分类 → _expert 调用
  │
  ⑭ 图流式输出 → adapter._drive → consumers._pump
  │   - kind=reasoning_token / stream_token / stream_end 正常输出（不变）
  │   - kind=persist_enhanced_message → consumers 存入 _vision_persist_message
  │   - kind=image_analysis_partial → consumers 发送非阻塞 WS 错误帧
  │
  [consumers._handle_chat 图流完成后]
  ⑮ 持久化：chat_memory.append_message(session, 'user', persist_msg)
     （格式：[图片1描述：<desc1>] [图片2描述：<desc2>] ... <原始文字>）
```

### 3.2 全部失败降级链路

```
[adapter.stream_chat — VLM 批量分析]
  │   - 5张全部 VisionServiceError / 超时
  │   → raise VisionServiceError（与 v1.5.0 单图全失败行为一致）
  │
[consumers._handle_chat — 捕获 VisionServiceError]
  │   - 发送 WS IMAGE_ANALYSIS_FAILED 错误帧（v1.5.0 已有路径，零改动）
  │   - WS 连接保持
```

### 3.3 旧客户端（v1.5.0）向后兼容链路

```
[旧前端] WS 帧: {"type":"chat_message","message":"...","image_upload_id":"<uuid>"}
  │
[consumers.receive v1.6.0]
  │   image_upload_ids = data.get('image_upload_ids')  → None（旧字段不存在）
  │   upload_id = data.get('image_upload_id')          → "<uuid>"（旧字段存在）
  │   → 包装为 upload_ids = ["<uuid>"]
  │   → 走相同的多图处理路径（单元素列表）
  │   → 行为与 v1.5.0 完全一致（REQ-MI-003 满足）
```

---

## 4. 安全架构（基于 v1.5.0 继承，多图场景补充）

### 4.1 base64 隔离策略（继承 v1.5.0 第 4.1 节，补充多图说明）

多图场景所有安全约束与单图一致（[KE-ARCH-009]）：

| 层次 | base64 处理规则（多图说明）|
|------|--------------------------|
| 前端 | 多图各自以 Blob 对象存储，通过各自独立的 multipart/form-data POST 上传，每次 POST 只含一张图的字节 |
| REST 上传端点 | 与 v1.5.0 完全相同，接收二进制流，不写入日志；每张图独立 upload_id |
| vision_progress 帧 | 只含进度文字（"正在分析第X/N张图片…"），**不含任何图片信息** |
| WS chat_message 帧 | 只含 `image_upload_ids: [uuid, uuid, ...]`，**不含 base64 或图片字节** |
| VLM 并发调用 | 每张图独立 base64 编码在各自协程局部作用域内；base64 字符串在 analyze_image 内部使用后 del |
| 日志 | `analyze_images_batch` 只记录批次数量、索引、耗时；不记录任何图片内容 |

### 4.2 upload_id 逐图安全校验

REQ-MI-NFR（UUID4 校验逐图执行）：
- `receive` 中对 `image_upload_ids` 中每个元素执行 `_is_valid_uuid` 校验。
- 任一 UUID 格式非法 → 发送 `IMAGE_INVALID` 错误帧，整批拒绝（快速失败）。
- `get_upload(upload_id, user_id)` 的 user_id 绑定校验逐图执行（防跨用户）。

### 4.3 超5张拦截

REQ-MI-009 `IMAGE_TOO_MANY`：
- 前端：已有5张时禁用上传按钮（REQ-MI-002 方案A，主动拦截）。
- 后端：`consumers.receive` 检查 `len(upload_ids) > 5` → 发送 `IMAGE_TOO_MANY` 错误帧（防前端绕过）。
- 无需服务端感知前端拦截状态，两层防御互相独立。

---

## 5. 向后兼容保证矩阵

| 场景 | v1.5.0 行为 | v1.6.0 行为 | 兼容性 |
|------|------------|------------|-------|
| 旧前端发 `image_upload_id`（单数）| 读取单字段，走单图路径 | 检测不到 `image_upload_ids`，fallback 读 `image_upload_id`，包装为单元素列表，走相同逻辑 | 完全兼容 |
| 旧前端发纯文字（无图）| 走纯文字路径 | 同上，两字段均不存在，走纯文字路径 | 完全兼容 |
| adapter.stream_chat(upload_id=None) 调用 | 跳过 VLM，enhanced_message = message | 新签名 upload_ids=None 时等价，行为不变 | 完全兼容 |
| adapter.stream_chat(upload_id=uuid) 单图调用（若有外部调用方）| 单图 VLM 调用 | 新签名保留 upload_id 参数（向后兼容），或包装为 upload_ids=[uuid] 路径 | 完全兼容 |
| vision_service.analyze_image() 单图接口 | 存在 | 不变，`analyze_images_batch` 在其基础上新增，不修改原函数 | 完全兼容 |
| 纯文字聊天 WS 链路 | 完全独立，不受影响 | 同上，代码路径完全分离 | 完全兼容 |

---

## 6. 降级策略（基于 v1.5.0 继承，多图场景补充）

```
Level 0（新增）：超5张拦截
  → 前端禁用上传按钮（REQ-MI-002，主动防线）
  → 后端发 IMAGE_TOO_MANY 错误帧（二道防线，WS 连接保持）

Level 1：upload_id 过期
  → 与 v1.5.0 一致。任一 upload_id 过期 → IMAGE_EXPIRED，整批拒绝（快速失败），引导用户重新上传全部图片
  （[ASSUMPTION] 多图场景下若仅部分过期，当前选择快速失败整批重传，而非复杂的部分续传——需 PM 确认是否可接受）

Level 2：部分 VLM 失败（新增）
  → 成功图正常注入，失败图占位 [用户图片N分析：图片分析失败，已跳过]（ADR-MI-004）
  → 发送非阻塞 IMAGE_ANALYSIS_PARTIAL 通知帧（REQ-MI-009）
  → WS 连接保持，LLM 继续处理

Level 3：全部 VLM 失败
  → 与 v1.5.0 一致：发 IMAGE_ANALYSIS_FAILED，WS 保持，用户可继续纯文字聊天

Level 4：整体超时（90s，RISK-MI-002）
  → asyncio.timeout(90) 包裹整个 analyze_images_batch 调用
  → 超时触发 VisionServiceError → 走 Level 3 路径

Level 5：预上传端点故障
  → 前端 Promise.allSettled 收集失败图，UI 提示用户部分图片上传失败（对应图片移除）
  → 仅上传成功的图片 upload_ids 进入 WS 帧；若全部失败则以纯文字发送
```

### 降级 WS 消息规范（v1.6.0 新增/变更项）

| 场景 | WS 消息格式 |
|------|-----------|
| 超5张 | `{"type":"error","code":"IMAGE_TOO_MANY","message":"最多支持5张图片，请删除多余图片后重新发送"}` |
| 部分 VLM 失败 | `{"type":"error","code":"IMAGE_ANALYSIS_PARTIAL","message":"第N张图片分析失败，已用占位文字替代，其余图片分析正常"}` |
| 多图进度（每张前）| `{"type":"vision_progress","message":"正在分析第N/T张图片，请稍候…"}` |
| 其余错误码 | 继承 v1.5.0：IMAGE_EXPIRED、IMAGE_ANALYSIS_FAILED、IMAGE_INVALID（不变）|

---

## 7. 需求覆盖矩阵

| 需求 ID | 描述摘要 | 覆盖设计节点 |
|---------|---------|------------|
| REQ-MI-001 | 前端最多5张图片选择、预览、删除 | ADR-MI-002（并发上传）；MOD-MI-01（ChatView.vue 扩展）|
| REQ-MI-002 | 超5张拦截（"最多5张"，已有5张禁用上传按钮）| 第 4.3 节（双层防御）；MOD-MI-01；MOD-MI-04（consumers 后端校验）|
| REQ-MI-003 | WS 向后兼容（旧字段继续工作，新字段优先）| ADR-MI-003；第 5 节向后兼容矩阵 |
| REQ-MI-004 | 多图 VLM 结果有序 | ADR-MI-001（逐图独立调用，结果按输入顺序聚合）|
| REQ-MI-005 | 注入格式 `[用户图片N分析：<descN>]` | ADR-MI-004（占位格式规范）；MOD-MI-05（adapter 增强消息构建）|
| REQ-MI-006 | 容量约束（每图≤10MB，5张总量≤存储上限）| 继承 v1.5.0：views_chat_image.py 单图 ≤10MB；vision_service check_capacity（50MB 上限）|
| REQ-MI-007 | 容错优先（部分失败占位，非阻塞通知）| ADR-MI-001（Option A）；ADR-MI-004（占位格式）|
| REQ-MI-008 | 持久化格式（多图占位标注）| ADR-MI-004（持久化格式规范）；MOD-MI-05（adapter persist_msg 构建）|
| REQ-MI-009 | 新增错误码 IMAGE_TOO_MANY、IMAGE_ANALYSIS_PARTIAL | 第 4.3 节；ADR-MI-004；第 6 节降级 WS 消息规范 |

**覆盖结论**：REQ-MI-001 ~ REQ-MI-009 全部覆盖。

---

## 8. 开放问题（架构阶段遗留）

| OQ 编号 | 问题 | 影响 | 建议处理时机 |
|---------|------|------|------------|
| OQ-MI-005 | 多图场景下若仅部分 upload_id 过期（其余有效），当前架构决策为整批快速失败（Level 1 降级）。若 PM 希望仅剔除过期图片继续提问，需在 consumers 层增加逐图 TTL 检查 + 部分降级逻辑，约增加10行代码。| REQ-MI-003（向后兼容）无影响；仅影响 UX 细节 | PM 确认；当前设计为整批重传（保守、实现简单）|
| OQ-MI-006 | analyze_images_batch 内部并发（asyncio.gather）还是串行（for 循环）取决于豆包账号并发配额。若账号限制并发1则 gather 会触发 429，需改为串行。当前 ADR-MI-001 选定 asyncio.gather，但未验证豆包并发配额。| RISK-MI-002（90s 总限）| 开发阶段验证豆包账号配额；若有限制，在 vision_service.py 中改为 asyncio.Semaphore 限流 |

---

## 9. [ASSUMPTION] 标注

| 标注 | 相关决策 | 需要 PM 确认 |
|------|---------|------------|
| [ASSUMPTION] OQ-MI-005 多图部分过期场景选择快速失败整批重传 | Level 1 降级策略 | 是否可接受？还是希望剔除过期图片继续 |
| [ASSUMPTION] 旧字段 `image_upload_id` 被 consumers 包装为单元素列表后走同一处理逻辑 | ADR-MI-003 | 已被 REQ-MI-003 隐含，无需额外确认 |
| [ASSUMPTION] asyncio.gather 并发 VLM 调用；若豆包账号有并发限制需改为 Semaphore 串行 | ADR-MI-001 | 开发阶段实测确认 |

---

*文档状态：DRAFT（2026-06-24）。基于 v1.5.0 增量，待 PM 门控通过后更新为 APPROVED。*
