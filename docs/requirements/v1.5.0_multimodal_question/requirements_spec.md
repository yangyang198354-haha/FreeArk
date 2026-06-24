# 需求规格说明书

**特性**：多模态提问——用户图片输入与豆包视觉模型理解（Image Question Input）
**版本**：v1.5.0_multimodal_question
**状态**：APPROVED — OQ-MQ-001/003/004/005 已决策，可进入架构阶段
**日期**：2026-06-24
**作者**：pm-orchestrator（代 requirement-analyst 编写，基于用户提供的业务目标与代码事实）

---

## 1. 背景与问题陈述

### 1.1 现状

FreeArk 方舟智能体当前聊天链路是**纯字符串管道**：

- `consumers.py::receive` 取 `data.get('message')`（str）
- `LangGraphAdapter.stream_chat(message: str, session_key: str)`
- `HumanMessage(content=message)`（LangChain，content 为 str）
- `orchestrator._route(state)` 把 `m.content` 当纯字符串做意图分类
- `orchestrator._fan_out` 生成 `plan=[(name, text)]`
- `orchestrator._expert` 只收到 `query: str`

用户在现场遇到设备铭牌读取困难、报错屏截图、参数表格等需要「图文并提」的场景时，只能手动描述图片内容后再提问，效率极低且描述不准确。

### 1.2 问题

用户无法通过聊天界面直接提交图片，智能体也无法理解图片内容。现有主模型 DeepSeek v4-flash **API 层即拒绝**视觉输入（2026-06-23 生产实测，HTTP 400 `unknown variant 'image_url'`），故图像理解必须引入独立视觉语言模型（VLM）。

### 1.3 解决方向

**本期实施方案**：引入豆包视觉模型（doubao-vision）作为独立 VLM 节点，承担图像理解任务。用户上传图片后，doubao-vision 先对图片生成描述/OCR 结果/分析，再将视觉分析结论注入 LangGraph 编排图的上下文，主模型 deepseek-v4-flash 基于文字化的视觉分析结果作最终答复，实现「图文混合理解」。

此方案不要求主模型具备视觉能力，与当前架构完全兼容。

**明确排除**：
- 图片直接进入主模型（deepseek 不支持，API 已实证拒绝）
- 视频输入理解（后续演进）
- 纯离线 OCR 兜底替代视觉理解（OCR 可作可选降级，见 NFR 及范围外说明）
- 多图同时提交（后续演进，本期 MVP 只支持单张图）

---

## 2. 范围界定

### 2.1 本期范围（IN SCOPE）

| 编号 | 内容 |
|------|------|
| S-001 | 前端聊天界面新增图片上传入口（单张），支持预览与删除 |
| S-002 | 图片通过 REST 预上传接口获取临时 `upload_id`，WS 帧只传 `upload_id`（不传 base64） |
| S-003 | 后端接收图片，存入临时存储，关联 `upload_id` |
| S-004 | 消息构建层将 `upload_id` 解析为图片字节，传入 doubao-vision VLM |
| S-005 | doubao-vision 模型调用（豆包多模态端点，火山方舟），含超时/重试/降级 |
| S-006 | VLM 输出（视觉分析文本）注入 LangGraph 编排图上下文，传递给专家节点 |
| S-007 | `orchestrator._route` 意图分类收到文字化视觉描述，路由逻辑不受影响 |
| S-008 | 图片+文字混合消息的持久化策略：文字内容存 `api_chat_session` 历史，图片引用以元数据形式存储（不存原图 blob） |
| S-009 | 会话历史展示：历史消息中图片问题显示图片占位/缩略图（若技术可行）或标注「含图提问」 |
| S-010 | 错误与降级 UX：doubao-vision 超时/不可用时告知用户并允许纯文字重试 |
| S-011 | 安全约束：图片字节不进 WS 帧、不进 uvicorn access 日志；API key 仅走 .env |
| S-012 | 客户端压缩：前端在发送前对超大图片进行压缩，适配 Pi WiFi 带宽限制 |

### 2.2 本期明确排除（OUT OF SCOPE）

| 编号 | 内容 | 理由/后续版本 |
|------|------|------------|
| NS-001 | 多张图片同时提交 | MVP 控制复杂度；多图会使 VLM token 成本与延迟成倍增加 |
| NS-002 | 纯 OCR 离线兜底替代 doubao-vision | OCR 只取字，不等于图像理解；若要降级应明确告知用户体验差异。**是否纳入可选降级为开放问题 OQ-MQ-004，待用户拍板** |
| NS-003 | 视频/音频输入 | 与当前技术路线无关 |
| NS-004 | 图片持久化为知识库文档（RAG 入库） | 这是独立的知识库管理功能，非聊天提问流程 |
| NS-005 | 主模型直接处理多模态输入 | 生产已证实 DeepSeek API 不支持（C-001） |
| NS-006 | 前端图片历史大图预览（类似 RAG 图片引用的弹层） | 本期仅做标注，详细展示后续版本可补 |

---

## 3. 利益相关方与用户角色

| 角色 | 描述 | 核心关切 |
|------|------|---------|
| 住户/业主（最终用户） | 通过聊天界面提问，现场有设备图片需要理解 | 图片上传便捷；智能体能理解图片内容；等待时间可接受 |
| 平台运维（Pi 5 管理者） | 维护树莓派 5 生产节点，网络/内存/存储受限 | VLM 调用不拖垮进程；超时有保护；base64 不进日志 |
| 系统管理员（知识库） | 暂无特殊关切 | — |

---

## 4. 功能需求

### REQ-FUNC-001 前端图片上传入口

**描述**：在聊天输入框旁新增图片上传按钮，用户可选择本地图片并预览；选图后可删除重选；点击发送时图片随文字消息一起提交。

**约束**：
- 支持格式：JPEG、PNG、WebP、HEIC（iOS 常见）；其他格式提示「请上传 JPEG/PNG/WebP 格式图片」
- 客户端文件大小限制：原始文件不超过 10MB（超过则拒绝选择，提示用户压缩）
- 客户端压缩：原始尺寸超过 1920×1920 像素时，前端自动等比例压缩到该尺寸上限，并以 JPEG 格式重新编码（quality=80），压缩后保留浏览器 Blob，不再限制字节大小
- 本期只支持单张图片（多图禁用，若用户尝试多选则取第一张）
- 预览图在输入框上方展示缩略图（最大高度 80px），可点 × 删除
- 已选图片发送后，图片预览自动清空（不保留到下一轮）

**当前代码锚定**：`frontend/src/views/ChatView.vue`——输入区 DOM，需在此处增加 `<input type="file" accept="...">` 及对应控制逻辑。

**验收标准**：
- 用户在文件选择对话框中选择一张 PNG 图片后，聊天输入框上方出现该图片缩略图预览
- 点击预览图旁的 × 按钮，图片被清除，输入框恢复纯文字状态
- 选择超过 10MB 的文件，弹出提示「图片文件过大（>10MB），请压缩后上传」，图片不被选中
- 选择超过 1920px 的图片，前端静默压缩后预览图仍可正常显示（用户无感）
- 只允许同时携带一张图片

---

### REQ-FUNC-002 图片预上传 REST 接口

**描述**：前端在发送聊天消息前，先通过 HTTP POST 将图片字节上传至后端，后端存入临时存储后返回 `upload_id`（短期有效，建议 TTL ≥ 10 分钟）。WS 帧中只传递 `upload_id`，不传 base64，以满足安全约束（SC-001：base64 不进 WS 帧或日志）。

**接口约束**（架构阶段细化，需求给出边界）：
- 路径：`POST /api/chat/image-upload/`
- 权限：`IsAuthenticated`（Bearer Token，与聊天鉴权模式一致）
- 请求：multipart/form-data，字段名 `image`
- 响应：`{"upload_id": "<uuid>", "expires_in": 600}`（TTL 单位秒）
- 服务端验证：Content-Type 为图片格式（MIME 白名单）、字节大小 ≤ 10MB（服务端二次验证，前端已有客户端限制）
- 存储后端：架构阶段决策（本地临时目录 vs Django cache vs Redis binary），需求只约束：不落 DB、TTL 后自动清理、不跨 worker 持久化（单进程，单 worker，无此需求）
- 失败：文件格式不合法 → 400；文件过大 → 413；服务端错误 → 500

**安全约束**：
- 图片字节不写入任何日志（Django logger、uvicorn access log 均不含 base64 或图片数据）
- 上传端点不返回图片字节，仅返回 `upload_id`
- `upload_id` 为服务端生成的随机 UUID，不可被枚举

**验收标准**：
- 已登录用户上传合法 PNG，响应 200，body 含 `upload_id`（UUID 格式）和 `expires_in`（正整数）
- 未登录请求返回 401
- 超过 10MB 的图片上传返回 413
- 非图片 MIME 类型上传返回 400
- Django 日志级别 DEBUG 下，日志文件中不出现 base64 字符串或图片字节十六进制（审查日志文件确认）

---

### REQ-FUNC-003 WS 协议扩展：携带 upload_id 的聊天消息

**描述**：现有 WS `chat_message` 类型的消息新增可选字段 `image_upload_id`，用于关联预上传的图片。图片和文字均可为空时的行为有明确定义（纯文字、纯图片、图文混合均须支持）。

**协议变更**（向后兼容：不含 `image_upload_id` 的消息行为与当前完全一致）：

```json
{
  "type": "chat_message",
  "message": "这个铭牌上的型号是什么？",
  "image_upload_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**纯图片消息**（无文字）：

```json
{
  "type": "chat_message",
  "message": "",
  "image_upload_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

纯图片消息（message 为空但有图）：后端补充默认提问文案**「请帮我分析这张图片」**（由后端注入，不在前端硬编码），避免 VLM 收到空提问。（OQ-MQ-003 已决策）

**当前代码锚定**：`consumers.py::receive` — `user_message = data.get('message', '').strip()` 在此处还需读取 `data.get('image_upload_id')` 并传入 `_handle_chat`。

**验收标准**：
- 发送不含 `image_upload_id` 的 `chat_message`，处理逻辑与当前完全一致（无回归）
- 发送含合法 `image_upload_id` 的消息，后端能取到对应图片字节
- `image_upload_id` 对应的图片已过期（TTL 超），后端向前端发送错误消息 `{"type": "error", "code": "IMAGE_EXPIRED", "message": "图片已过期，请重新上传"}`，不继续处理
- `image_upload_id` 存在但格式非 UUID，后端返回 `{"type": "error", "code": "IMAGE_INVALID", "message": "图片引用无效"}`

---

### REQ-FUNC-004 doubao-vision VLM 调用

**描述**：后端在编排图启动前（或作为专用 VLM 节点），调用豆包视觉模型（doubao-vision）对图片进行分析，产生文字化的视觉描述，再将其注入 LangGraph 上下文。

**模型调用约束**：
- 端点：火山方舟多模态接口（与 `rag_service._DoubaoMultimodalEmbeddings` 所用账号/密钥/网络相同，账号已打通）
- 具体模型型号：**通过 `.env` 可配置**（变量名 `VLM_MODEL`），**默认 doubao-vision-lite**；按实际识别效果可切换为 doubao-vision-pro 而不改代码（OQ-MQ-001 已决策：先 lite 后可切 pro）
- 调用方式：同步调用，在启动 LangGraph `graph.astream` 前完成（不在 ReAct 循环内）；或作为 LangGraph 中的独立节点（架构阶段决策）
- 输入：图片字节（base64 编码后放入 payload）+ 用户文字消息（作为提问上下文）
- 输出：文字描述（str），含图片中识别出的型号/文字/结构/状态等信息
- API key：仅从 Django settings / .env 读取，变量名建议 `DOUBAO_API_KEY`（或复用现有 `DOUBAO_VISION_API_KEY`，架构阶段确认），**绝不进入**日志、HTTP 响应、前端

**超时与重试约束**（来自可复用资产的实测经验）：
- 超时：单次调用超时设置 ≤ 30 秒（Pi WiFi 偶发劣化，实测豆包 vision 偶发 >15s，须有保护）
- 重试：超时或 5xx 时最多重试 1 次（指数退避，间隔 2s）；4xx 不重试（客户端错误）
- 失败处理：2 次均失败 → 触发降级策略（见 REQ-FUNC-006）

**调用链路安全**：
- 图片 base64 字节在调用完成后立即从内存中释放（不在 State 对象中留存）
- VLM 输出的文字描述才进入 LangGraph State 和日志（文字安全，可记录）

**验收标准**：
- 发送含有效图片的消息，后端调用 doubao-vision，LangGraph State 中存在 `vision_description`（非空字符串）
- 图片含设备铭牌文字，VLM 输出的描述包含铭牌上的关键文字（人工抽检 3~5 个样本）
- doubao-vision 超时（模拟：在测试中注入 sleep > 超时阈值），系统在超时期满 + 1 次重试后触发降级，不卡死
- API key 不出现在任何 Django 日志行或 HTTP 响应体中

---

### REQ-FUNC-005 视觉分析结果注入 LangGraph 编排图

**描述**：doubao-vision 的文字化分析结果须无损传递到 LangGraph 各专家节点，不被 `_route` 意图分类或 `_fan_out` 丢弃。

**当前问题锚定**：

现有 `_route` 取 `m.content`（str）做意图分类；`_fan_out` 生成 `plan=[(name, text)]`，text 即原始消息字符串；`_expert` 收到 `query: str`。**若 content 变成多模态 list，`_route` 的字符串操作会失败；即使不改 content 格式，VLM 描述若不显式穿透到 `query`，图片信息在专家处会丢失**。

**需求**：

- VLM 描述在组装消息前完成，以附加文本形式（如前缀或独立字段）注入给每个被路由到的专家
- 组装格式（参考，架构阶段可调整）：

  ```
  [用户图片分析：<VLM输出的描述文字>]
  
  <原始用户文字问题>
  ```

- `_route` 意图分类仍收到完整文字（含 VLM 描述前缀），路由逻辑无需改变
- `_fan_out` 的 `query` 字段携带完整文字（含 VLM 描述），不丢失图片信息
- `_expert` 内部工具调用（如 `search_sanheng_knowledge`）可利用 VLM 描述进行检索
- `State` 字典需新增字段记录 `vision_description: Optional[str]`（架构阶段设计）

**验收标准**：
- 用户上传含型号的铭牌图片并问「这个设备怎么维护」，专家节点收到的 `query` 包含 VLM 描述（可通过日志或测试断言验证）
- 三个专家（energy-expert / inspection-expert / sanheng-knowledge）均能正确收到携带 VLM 描述的 query
- `_route` 路由结果与纯文字消息路由结果一致（不因 VLM 前缀导致路由漂移，抽检 5 个用例对比）

---

### REQ-FUNC-006 超时/降级用户体验

**描述**：doubao-vision 不可用时，系统必须有明确的降级路径，不能让用户面对无响应的挂起状态。

**降级策略：选项 A（已决策，OQ-MQ-004 RESOLVED）**

VLM 2 次调用均失败后，向用户发送明确的降级提示文案（如「图片分析暂时不可用，您可以用文字描述图片内容后重新提问」），本轮含图请求终止，WS 连接保持，用户可继续发送纯文字消息。

**本期不做 RapidOCR 兜底**（选项 B 明确排除，已列入 NS-002 范围外，后续如有需要另立特性）。

**无论选哪个选项，必须满足**：
- 用户收到明确的文字提示（非空白、非静默失败）
- 不触发 `OPENCLAW_UNAVAILABLE` / `TIMEOUT` 等系统级错误消息（这类错误消息语义不匹配）
- 系统保持可用状态，用户可以继续发送纯文字消息

**验收标准**：
- 模拟 doubao-vision 端点不可达，用户发送含图消息，在 30s + 1 次重试后（≤70s）收到降级提示文字，WS 连接保持，可继续发纯文字消息
- 降级提示文字不包含技术术语（"502 Bad Gateway"、"timeout"等）

---

### REQ-FUNC-007 图片消息持久化

**描述**：含图片的聊天轮次须能在会话历史中被识别，但原图字节不存入 `api_chat_session` 历史（避免数据库膨胀，Pi 5 存储有限）。

**持久化策略（OQ-MQ-005 已决策：追加 VLM 描述）**：

| 持久化内容 | 存储位置 | 说明 |
|-----------|---------|------|
| 用户文字消息 | `api_chat_session` messages 历史 | 现有逻辑，不变 |
| VLM 生成的图片描述文字 | 追加到 user 消息记录（拼接格式：`[图片描述：<VLM输出>] <原始文字>`） | 历史加载时 LangGraph 仍能感知本轮图片内容的文字摘要 |
| 图片原始字节 | **不存储**（TTL 到期后临时存储自动清理） | 避免 DB/磁盘膨胀 |
| 图片元数据标记 | user 消息记录中增加 `has_image=True` 标注（可选，架构阶段决定是否实现） | 供前端历史列表展示「含图」标记 |

**当前代码锚定**：`consumers.py::_handle_chat` 中 `chat_memory.append_message(self.chat_session, 'user', user_message)` — 需修改为传入含 VLM 描述的增强文字。

**验收标准**：
- 发送含图消息后，`api_chat_session` 对应的 user 消息记录存在且包含 VLM 描述文字（非空）
- 重新打开同一会话，历史加载时能取到含 VLM 描述的 user 消息（LangGraph 历史注入有效）
- 数据库中无图片字节存储（检查所有新增的消息记录字段）

---

### REQ-FUNC-008 聊天历史中的图片标注展示

**描述**：用户重新打开历史会话时，含图片的历史消息在前端有视觉标识，说明该条消息原本包含图片（即使图片已无法复原）。

**约束**：
- 本期不要求历史消息中重现图片大图（图片字节未持久化，无法复原）
- 最低要求：含图消息的气泡显示一个图片图标或文字标注「📷 含图提问」（不依赖图片字节）
- 具体实现形式（架构/实现阶段设计）；本期需求只约束：**不显示破图 icon**（img src 为空时前端不挂 img 标签）

**验收标准**：
- 重新打开历史会话，含图轮次的 user 消息气泡显示图片标注（图标或文字）
- 不含图的历史消息气泡无标注（无多余 UI 元素）
- 页面不出现加载失败的破图 icon

---

## 5. 非功能需求

### REQ-NFR-001 端到端时延（Pi 5 平台）

- **目标**：图文混合提问的端到端时延（从用户点击发送到收到第一个 stream_token）≤ 20 秒（P90）
- **分解参考**（仅估算，实测后调整；以 doubao-vision-lite 为基线）：
  - 图片预上传：≤ 2s（LAN/WiFi，Pi 5）
  - doubao-vision-lite 调用：≤ 8s（P90 基线；切 pro 时 P90 可升至 ~15s，为可接受上限弹性）
  - LangGraph 路由 + 专家首 token：≤ 5s（现有单专家路径参考值 8.3s 总时长）
- **总时延超过 20s 时的 UX**：前端需有进度指示（「正在分析图片…」提示），避免用户误以为无响应

### REQ-NFR-002 Pi 5 资源约束

- **内存**：图片字节（base64 解码后最大 ~7.5MB/张，原始 10MB 经前端压缩后通常 ≤ 2MB）在 VLM 调用完成后立即释放，不持有在 LangGraph State 中
- **进程模型**：`uvicorn --workers 1`，所有操作在同一进程内串行处理（无并发图片处理压力）
- **存储**：临时图片存储 TTL 10 分钟，到期自动清理；设置进程内总临时图片占用上限 ≤ 50MB（超过则拒绝新上传）
- **CPU**：doubao-vision 调用为网络 IO 密集型（await），不消耗 CPU；前端压缩在浏览器端执行，不占服务端

### REQ-NFR-003 安全约束（来自已验证的业务约束）

| 编号 | 约束 | 来源 |
|------|------|------|
| SC-001 | 图片 base64 字节**绝不**进入 WS 帧 | freeark-ws-token-query-string-leak 历史教训 |
| SC-002 | 图片 base64 字节**绝不**出现在任何日志（uvicorn access log、Django logger 任何级别） | 同上；uvicorn 会完整打印请求内容 |
| SC-003 | doubao-vision API key 仅从 `.env` / Django settings 读取，**绝不**进入 git、HTTP 响应、日志、前端变量 | 密钥管理基线要求 |
| SC-004 | 图片预上传端点必须 `IsAuthenticated` 鉴权，`upload_id` 只对上传者本人有效 | 防止未认证访问或跨用户图片取用 |
| SC-005 | `upload_id` 为服务端生成随机 UUID，禁止使用递增整数（可枚举） | 安全设计基线 |
| SC-006 | 图片 MIME 类型白名单验证（服务端），拒绝非图片文件（防文件伪装） | 上传安全 |

### REQ-NFR-004 降级与 fail-open

- doubao-vision 调用失败（超时/5xx）：触发 REQ-FUNC-006 描述的降级策略，整个聊天 WS 连接保持，不触发 `OPENCLAW_UNAVAILABLE`
- 图片预上传失败：不影响纯文字聊天功能（前端允许在上传失败后降级为纯文字发送）
- 临时存储满（超过 50MB 上限）：新上传返回 503，提示「服务繁忙，请稍后重试」；当前 WS 连接纯文字功能不受影响
- `upload_id` 过期（TTL 超）：WS 收到消息时检测并发回 `IMAGE_EXPIRED` 错误，不继续处理，用户重新上传即可

### REQ-NFR-005 可观测性

- doubao-vision 调用须记录：调用开始时间、耗时、成功/失败、是否触发降级；日志级别 INFO（调用成功）/ WARNING（超时重试）/ ERROR（最终失败触发降级）
- 图片预上传须记录：上传成功（含文件大小、MIME 类型）、失败原因；不记录图片内容或 base64 数据
- 日志格式与现有日志风格一致（`log_config.json` 全局 ERROR；开发时用 `APP_LOG_LEVEL=INFO` 临时拉高）

### REQ-NFR-006 可维护性

- 新增 Django settings 变量须有注释（`DOUBAO_VISION_MODEL`、`DOUBAO_VISION_TIMEOUT`、`DOUBAO_VISION_MAX_RETRIES` 等）
- 新增模型（如临时上传记录模型）须手写 migration，遵循现有 migration 风格（TD-MIGRATION-001）
- VLM 调用逻辑封装为独立模块（不内联进 consumers.py 或 orchestrator.py），便于单独测试和替换模型

---

## 6. 约束与已决策事项

| 编号 | 约束 | 来源 |
|------|------|------|
| C-001 | DeepSeek v4-flash 不支持视觉输入，API 层已实证拒绝（HTTP 400）；禁止尝试绕过 | 2026-06-23 生产实测 |
| C-002 | 图像理解必须引入独立 VLM，本期选定 doubao-vision（火山方舟） | 业务决策 |
| C-003 | 豆包视觉偶发 >15s（8 次约 1 次），须设超时（≤30s）+ 重试（1 次） | `rag_service._DoubaoMultimodalEmbeddings` 注释实测记录 |
| C-004 | 图片 base64 不进 WS 帧；图片走 REST 预上传，WS 只传 upload_id | SC-001/002 |
| C-005 | 聊天后端为 LangGraph（CHAT_BACKEND=langgraph），不可回退 OpenClaw 兜底 | freeark-chat-backend-langgraph-gray |
| C-006 | 输入链路全为字符串，VLM 输出也必须是字符串，不得修改 `HumanMessage(content=str)` 接口 | 架构约束：避免修改 LangGraph State 核心 messages 类型 |
| C-007 | 原图字节不存入 DB / 聊天历史；只存 VLM 描述文字 | Pi 5 存储/DB 膨胀约束 |
| C-008 | 临时存储单进程管理（uvicorn workers=1），无跨进程共享需求 | 生产环境约束 |
| C-009 | 新增 migration 手写，不跑 makemigrations | TD-MIGRATION-001 |
| C-010 | 前端新增 API 调用（图片预上传）必须通过 `api.js`，不使用裸 axios | freeark-frontend-bare-axios-session-trap 历史教训 |

---

## 7. 非目标（明确排除，未来演进登记）

| 编号 | 内容 | 可能的未来版本 |
|------|------|------------|
| NT-001 | 多张图片同时提问 | v1.5.1 或独立特性 |
| NT-002 | 视频/GIF 动图理解 | 无计划 |
| NT-003 | 主模型（deepseek）直接视觉输入（需等 DeepSeek API 支持） | 待 DeepSeek 产品支持 |
| NT-004 | 图片 OCR 兜底（纯取字降级）——是否纳入为 OQ-MQ-004 开放问题 | 用户确认后决定 |
| NT-005 | 聊天历史图片大图复现（重新打开历史时显示原图） | 需图片持久化支持 |
| NT-006 | 知识库图片检索（以图搜图） | 需多模态 embedding |
| NT-007 | 多 worker 部署下的临时图片共享存储 | 需外部存储（Redis/OSS） |

---

## 8. 开放问题（OQ）

| OQ 编号 | 问题 | 影响 | 建议决策时机 |
|--------|------|------|------------|
| **OQ-MQ-001** | ~~doubao-vision 模型型号：doubao-vision-pro 还是 doubao-vision-lite？~~ **RESOLVED**：默认 doubao-vision-lite，通过 `VLM_MODEL` 环境变量可切换为 pro，不改代码。时延基线按 lite（P90 ≤8s）。 | 已锁入 REQ-FUNC-004、REQ-NFR-001 | 已决策 |
| **OQ-MQ-002** | VLM 调用位置：在 LangGraph 编排图**外部**（adapter 层，启动 graph 前）还是作为 LangGraph 的**独立节点**（route 前置节点）？外部方案实现简单；节点方案可利用 LangGraph checkpointer | 影响 orchestrator.py 修改范围与架构设计 | 架构阶段决策（需求不强制，但前者更简单） |
| **OQ-MQ-003** | ~~纯图片消息默认提问文案~~ **RESOLVED**：后端注入文案为**「请帮我分析这张图片」**，由后端硬编码，不在前端配置。 | 已锁入 REQ-FUNC-003 | 已决策 |
| **OQ-MQ-004** | ~~doubao-vision 不可用时的降级策略~~ **RESOLVED**：**选项 A**。VLM 2 次失败后明确告知用户本轮无法处理图片、WS 连接保持、可继续纯文字重试。本期不做 RapidOCR 兜底（列入 NS-002 范围外）。 | 已锁入 REQ-FUNC-006 | 已决策 |
| **OQ-MQ-005** | ~~图片消息持久化~~ **RESOLVED**：**追加 VLM 描述文字**到 user 消息记录（格式：`[图片描述：<VLM输出>] <原始文字>`），原图字节不入库。多轮对话历史注入有效。 | 已锁入 REQ-FUNC-007 | 已决策 |
| **OQ-MQ-006** | 客户端压缩阈值：建议 1920×1920 / JPEG quality=80。是否可接受？若用户上传低质量图片（如 150DPI 铭牌扫描），压缩后文字是否仍可被 VLM 识别？ | 影响 REQ-FUNC-001 的压缩参数；质量过低会降低 VLM 识别率 | 开发阶段可用样本图片实测验证；建议提高至 quality=85 |
| **OQ-MQ-007** | 临时图片存储：本地内存（进程内 dict，简单但重启丢失）vs Django cache（`locmem://` 或 `file://`）vs 临时文件（`/tmp`）？Pi 5 单 worker，重启后 TTL 内的上传即失效可接受 | 影响 REQ-FUNC-002 实现；均可行，选简单的 | 架构阶段决策 |

---

## 9. 影响范围矩阵

| 组件 | 变更类型 | 描述 |
|------|---------|------|
| `frontend/src/views/ChatView.vue` | 修改 | 新增图片选择按钮、预览、压缩逻辑；发送时携带 `upload_id` |
| `frontend/src/utils/api.js` | 修改 | 新增 `uploadChatImage(file)` helper（图片预上传接口调用） |
| `api/views.py` 或新建 `api/views_chat_image.py` | 新增 | 图片预上传端点 `POST /api/chat/image-upload/` |
| `api/urls.py` | 修改 | 注册预上传端点路由 |
| 新建 `api/vision_service.py`（或等价模块名） | 新增 | doubao-vision VLM 调用封装；临时存储管理；超时/重试逻辑 |
| `api/consumers.py` | 修改 | `receive` 读取 `image_upload_id`；`_handle_chat` 传入 upload_id；`_pump` 支持新 kind |
| `api/langgraph_chat/adapter.py` | 修改 | `stream_chat` 签名扩展支持可选 `upload_id`；调用 vision_service 完成 VLM 分析后注入消息 |
| `api/langgraph_chat/orchestrator.py` | 修改 | `State` 新增 `vision_description: Optional[str]`；`_route`/`_fan_out`/`_expert` 传递 VLM 描述 |
| `api/settings.py` 和 `.env` | 修改 | 新增 `DOUBAO_VISION_MODEL`、`DOUBAO_VISION_TIMEOUT`、`DOUBAO_VISION_MAX_RETRIES` 等配置 |
| `api/migrations/0040_chat_image_upload.py`（手写）| 新增（可选） | 若选择 DB 存储临时上传记录（架构阶段决策） |
| `docs/requirements/v1.5.0_multimodal_question/` | 新增 | 本文件及 user_stories.md |

---

*文档状态：APPROVED（2026-06-24）。OQ-MQ-001/003/004/005 已由产品负责人决策，已锁入对应需求条目。OQ-MQ-006/007 为开发/架构阶段决策，不阻塞架构推进。*
