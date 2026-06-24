# 用户故事清单

**特性**：多模态提问——用户图片输入与豆包视觉模型理解（Image Question Input）
**版本**：v1.5.0_multimodal_question
**状态**：APPROVED — OQ-MQ-001/003/004/005 已决策，可进入架构阶段
**日期**：2026-06-24
**关联**：requirements_spec.md v1.5.0_multimodal_question

---

## 用户故事总览

| 编号 | 角色 | 一句话描述 | 关联需求 | 优先级 |
|------|------|---------|---------|-------|
| US-MQ-001 | 住户/业主 | 上传设备铭牌图片并提问，智能体能识别铭牌内容作答 | REQ-FUNC-001~005 | Must Have |
| US-MQ-002 | 住户/业主 | 只发图片不写文字，智能体仍能分析图片 | REQ-FUNC-003, REQ-FUNC-004 | Must Have |
| US-MQ-003 | 住户/业主 | 图片上传前能看到预览并可以撤销 | REQ-FUNC-001 | Must Have |
| US-MQ-004 | 住户/业主 | 图文混合问答的回答与纯文字问答体验一致 | REQ-FUNC-005, REQ-NFR-001 | Must Have |
| US-MQ-005 | 住户/业主 | 图片视觉分析失败时收到明确提示，可继续使用 | REQ-FUNC-006, REQ-NFR-004 | Must Have |
| US-MQ-006 | 住户/业主 | 重新打开历史会话，含图消息有标注 | REQ-FUNC-008 | Should Have |
| US-MQ-007 | 住户/业主 | 上传超大图片时收到提示 | REQ-FUNC-001 | Must Have |
| US-MQ-008 | 平台运维 | 图片字节不出现在任何日志 | REQ-NFR-003 | Must Have |
| US-MQ-009 | 平台运维 | doubao-vision 超时有保护，不拖垮 WS 连接 | REQ-NFR-001, REQ-NFR-004 | Must Have |
| US-MQ-010 | 平台运维 | 纯文字聊天在图片功能不可用时不受影响 | REQ-NFR-004 | Must Have |

---

## US-MQ-001 上传设备铭牌图片提问，智能体识别并作答

**As** 住户/业主（现场有设备），
**I want** 拍一张设备铭牌照片，在聊天界面上传并附带文字问「这是什么型号，怎么维护？」，
**So that** 我不需要手动抄写铭牌上的所有参数，智能体能直接识别图片告诉我答案。

### 验收标准

**AC-MQ-001-01 — 图文混合消息完整处理**
```
Given 用户已登录，聊天界面正常显示
When  用户选择一张含设备铭牌的 JPEG 图片，输入文字「这是什么型号，怎么维护？」，点击发送
Then  前端先调用 POST /api/chat/image-upload/，获得 upload_id（≤2s 内返回）
And   WS 发出 {"type":"chat_message","message":"这是什么型号，怎么维护？","image_upload_id":"<uuid>"}
And   后端调用 doubao-vision，State 中存在非空 vision_description
And   LangGraph 专家节点收到含 vision_description 的增强 query
And   前端收到 stream_token 流式内容，最终展示包含型号信息的回答
And   从点击发送到第一个 stream_token 到达不超过 20s（P90）
```

**AC-MQ-001-02 — 铭牌文字识别质量**
```
Given 用户上传一张清晰的三恒空调铭牌照片（含型号、额定电压等信息）
When  doubao-vision 完成分析，专家给出回答
Then  回答中包含铭牌上的关键信息（型号、主要参数中的至少 2 项）
Note  此标准通过人工抽检 3~5 个样本验证，非自动化测试
```

**AC-MQ-001-03 — 图文混合消息写入历史**
```
Given 上述对话完成，用户刷新页面重新打开历史会话
When  历史消息加载
Then  该轮 user 消息记录包含 VLM 描述文字（非空），LangGraph 历史注入有效
And   数据库中该消息记录无图片字节字段（只有文字）
```

---

## US-MQ-002 只发图片不写文字，智能体仍能分析

**As** 住户/业主，
**I want** 有时只想发一张图让智能体看看，不想想文字怎么说，
**So that** 即使我不知道该怎么描述这张图，智能体也能给出分析。

### 验收标准

**AC-MQ-002-01 — 纯图片消息处理**
```
Given 用户选择一张图片，输入框文字为空，点击发送
Then  前端仍执行图片预上传，获得 upload_id
And   WS 发出 {"type":"chat_message","message":"","image_upload_id":"<uuid>"}
And   后端检测到 message 为空，注入默认提问文案「请帮我分析这张图片」（OQ-MQ-003 已决策，文案固定）
And   doubao-vision 被调用，返回非空分析文字
And   智能体给出有实质内容的回答（非拒绝回答）
```

**AC-MQ-002-02 — 默认提问文案不暴露给用户**
```
Given 用户发送纯图片消息（无文字）
When  智能体给出回答
Then  回答内容不包含「请帮我分析这张图片」原文（后端注入文案不透传到回答里）
And   回答直接针对图片内容（如「图片显示的是……」）
```

---

## US-MQ-003 图片上传前能预览并可撤销

**As** 住户/业主，
**I want** 选完图片后能在发送前看到预览图，如果选错了还能删掉重选，
**So that** 我不会误发错误的图片给智能体。

### 验收标准

**AC-MQ-003-01 — 选图后出现预览**
```
Given 用户在聊天界面点击图片上传按钮
When  用户在文件选择对话框中选择一张合法图片
Then  输入框上方出现该图片的缩略图预览（最大高度约 80px）
And   缩略图旁有删除按钮（×）
And   发送按钮可用（用户可选择仅发图片或再加文字）
```

**AC-MQ-003-02 — 删除预览图**
```
Given 已有一张图片在预览状态
When  用户点击预览图旁的 × 按钮
Then  预览图消失，输入框恢复纯文字状态
And   再次点击发送按钮（若有文字），发出的消息不含 image_upload_id
```

**AC-MQ-003-03 — 发送后预览自动清空**
```
Given 用户已选图并输入文字，点击发送
When  WS 消息发出（无论后端处理结果如何）
Then  预览图自动清空
And   下一条消息默认为纯文字状态
```

---

## US-MQ-004 图文混合问答回答体验与纯文字一致

**As** 住户/业主，
**I want** 含图片的问答在界面上与普通问答的呈现方式相同（流式输出、思考过程折叠框等），
**So that** 引入图片功能后我的聊天体验不变差。

### 验收标准

**AC-MQ-004-01 — 流式输出正常**
```
Given 用户发送含图片的消息
When  后端处理完成开始返回
Then  前端收到 reasoning_token 流（「正在分析图片…」或「正在理解你的问题…」）
And   收到 content 流式 token（逐字显示回答）
And   stream_end 正常到达，回答气泡完整显示
And   以上流程与纯文字问答的 UX 行为一致
```

**AC-MQ-004-02 — 纯文字问答无回归**
```
Given 用户发送不含图片的普通文字消息（无 image_upload_id）
When  WS 处理流程
Then  处理路径与 v1.4.1 完全一致
And   stream_end 不包含与图片相关的字段（向后兼容）
And   响应时延无统计显著退化（P50 不超过 v1.4.1 基线 +10%）
```

**AC-MQ-004-03 — 进度提示可见**
```
Given 用户发送含图片的消息，VLM 分析需要超过 5s
When  等待期间
Then  前端显示进度提示文案（如「正在分析图片，请稍候…」）
And   用户界面不出现超过 5s 的无反馈静默
```

---

## US-MQ-005 图片视觉分析失败时收到明确提示

**As** 住户/业主，
**I want** 当智能体无法分析我的图片时，能告诉我为什么以及我该怎么做，
**So that** 我不会对着一个没有响应的界面无所适从。

### 验收标准

**AC-MQ-005-01 — VLM 不可用时的降级提示**
```
Given doubao-vision 服务不可达（模拟：在测试中注入连接失败）
When  用户发送含图片的消息
Then  后端在超时（≤30s 单次，最多 1 次重试）后触发降级
And   前端收到包含友好文案的错误消息（不含 502/timeout 等技术术语）
And   WS 连接保持，用户可以继续发送纯文字消息
And   错误消息明确引导用户（如「图片分析暂时不可用，您可以用文字描述图片内容后重试」）
```

**AC-MQ-005-02 — 降级后不触发系统级错误**
```
Given VLM 调用失败并触发降级
When  降级提示发送后
Then  后端不抛出 OpenClawUnavailableError（不进入系统级错误处理分支）
And   系统日志中出现 ERROR 级别条目（记录 VLM 失败原因）但不影响用户可用性
And   前端错误消息类型为用户级别错误（"code": "IMAGE_ANALYSIS_FAILED"）而非系统错误（"code": "OPENCLAW_UNAVAILABLE" / "INTERNAL_ERROR"）
```

**AC-MQ-005-03 — 图片过期重新上传**
```
Given 用户上传图片后等待超过 TTL（模拟：10 分钟）再发送消息
When  WS 消息处理
Then  前端收到 {"type":"error","code":"IMAGE_EXPIRED","message":"图片已过期，请重新上传"}
And   提示用户重新选择图片上传
And   WS 连接保持正常
```

---

## US-MQ-006 历史会话中含图消息有标注

**As** 住户/业主，
**I want** 重新打开一个历史对话时，能看到哪条消息是含图片的提问，
**So that** 我知道当时的上下文背景（有图），不会对智能体的回答感到困惑。

### 验收标准

**AC-MQ-006-01 — 含图历史消息有标注**
```
Given 用户曾发送含图消息，会话已保存到历史
When  用户重新打开该会话，历史消息加载完毕
Then  该条 user 消息气泡显示图片标注（图标或「含图提问」文字）
And   不出现任何加载失败的破图 icon（无 <img> 标签指向空 src）
```

**AC-MQ-006-02 — 纯文字历史消息无标注**
```
Given 同一会话中有若干纯文字历史消息
When  历史加载完毕
Then  纯文字消息气泡无图片标注，外观与 v1.4.1 完全一致
```

---

## US-MQ-007 上传超大图片时收到提示

**As** 住户/业主，
**I want** 当我选择的图片文件太大时，马上收到提示说明不行，而不是等待很久后超时，
**So that** 我能快速知道需要先压缩图片再上传。

### 验收标准

**AC-MQ-007-01 — 客户端大小校验**
```
Given 用户在文件选择对话框中选择一张超过 10MB 的图片文件
When  文件被前端 onChange 事件处理
Then  立即弹出提示「图片文件过大（>10MB），请压缩后上传」
And   该图片不被选中（预览区无图片显示）
And   不发出任何 HTTP 请求（纯前端拦截）
```

**AC-MQ-007-02 — 服务端二次校验**
```
Given 恶意/异常客户端跳过前端校验，直接上传超过 10MB 的图片到 POST /api/chat/image-upload/
When  服务端处理请求
Then  响应 HTTP 413，body 含错误描述
And   无图片字节写入任何存储
```

**AC-MQ-007-03 — 自动压缩超尺寸图片**
```
Given 用户选择一张尺寸为 3000×4000 像素、大小 3MB 的 PNG
When  前端完成压缩（等比缩放到 ≤1920×1920，JPEG quality=80~85）
Then  预览图正常显示（压缩后图片）
And   预上传接口收到的文件大小明显小于原始文件（预期 ≤1MB）
And   用户无需任何手动操作（压缩无感）
```

---

## US-MQ-008 图片字节不出现在任何日志

**As** 平台运维，
**I want** 确认图片内容（base64 字符串、图片字节）不会出现在任何日志文件（uvicorn access log、Django app log）中，
**So that** 避免用户图片数据意外泄露，以及日志文件膨胀。

### 验收标准

**AC-MQ-008-01 — uvicorn access log 无 base64**
```
Given APP_LOG_LEVEL=DEBUG，uvicorn --access-log 开启
When  用户完成一次图文混合提问（含图片预上传 + WS 消息发送）
Then  uvicorn access log 中预上传请求行不包含 base64 字符串（请求体不被打印）
And   WS 帧日志（若有）不包含 base64 或图片字节数据
Note  验证方法：tail uvicorn access log，用 grep 检索常见 base64 前缀（如 "/9j/"、"iVBOR"）
```

**AC-MQ-008-02 — Django app log 无图片内容**
```
Given APP_LOG_LEVEL=DEBUG（最详细级别）
When  用户完成一次图文混合提问
Then  Django app log（api.consumers / api.vision_service 等 logger）中不含 base64 字符串
And   doubao-vision 调用日志只记录「调用开始」「耗时」「成功/失败」，不记录图片内容
```

---

## US-MQ-009 doubao-vision 超时有保护，不拖垮 WS 连接

**As** 平台运维，
**I want** 即使 doubao-vision 因 Pi WiFi 抖动而响应缓慢或不响应，WS 连接也不会无限期挂起，
**So that** 用户最终能收到一个明确的结果（成功或降级），Pi 5 的事件循环不被阻塞。

### 验收标准

**AC-MQ-009-01 — 单次调用超时保护**
```
Given doubao-vision 端点响应时间超过 30s（模拟注入）
When  后端等待 VLM 返回
Then  ≤30s 后触发超时异常（asyncio.timeout 或等价）
And   超时日志记录为 WARNING 级别
And   进入 1 次重试逻辑
```

**AC-MQ-009-02 — 重试后最终失败触发降级**
```
Given doubao-vision 端点持续不可用，2 次均超时
When  最后一次超时
Then  总等待时间 ≤70s（30s × 2 + 2s 间隔 + 处理开销）
And   触发 REQ-FUNC-006 降级策略，向前端发送降级提示
And   WS 连接保持，_is_streaming 标志正确重置为 False（用户可继续发消息）
```

**AC-MQ-009-03 — 超时期间 WS 心跳不中断**
```
Given VLM 调用超时等待期间（最多 70s）
When  前端发送 WebSocket ping 帧
Then  WS 连接不断开（pong 正常响应）
And   用户界面不出现「连接已断开」提示
```

---

## US-MQ-010 纯文字聊天在图片功能故障时不受影响

**As** 平台运维，
**I want** 即使图片预上传端点不可用或 doubao-vision 服务宕机，纯文字聊天仍然正常工作，
**So that** 图片功能的问题不会影响智能体的核心聊天能力。

### 验收标准

**AC-MQ-010-01 — 图片服务不可用时纯文字正常**
```
Given POST /api/chat/image-upload/ 端点返回 503（模拟宕机）
When  用户发送不含图片的纯文字消息
Then  WS 处理正常，adapter.stream_chat 正常调用，回答正常返回
And   无任何与图片功能相关的错误消息出现
```

**AC-MQ-010-02 — 代码路径隔离**
```
Given 任何新增的图片处理代码（vision_service.py、image-upload 端点等）
When  发生未预期异常（Exception）
Then  异常不向上传播到 ChatConsumer._handle_chat 的主流程
And   用户收到明确的图片相关错误提示，而非系统级 INTERNAL_ERROR
Note  实现约束：图片处理代码须有独立的 try/except，不可与主聊天流程共用 except 块
```

---

## 附录 A：开放问题（OQ）— 决策状态

| OQ 编号 | 问题描述 | 决策结果 | 状态 |
|--------|---------|---------|------|
| **OQ-MQ-001** | doubao-vision 模型型号 | **先 lite 后可切 pro**。默认 doubao-vision-lite，通过 `VLM_MODEL` env 可配置切换 pro，不改代码。时延基线按 lite（P90 ≤8s）。 | RESOLVED |
| **OQ-MQ-002** | VLM 调用位置：adapter 层外置 vs LangGraph 节点 | 推荐外置（adapter 层），架构阶段确认 | 架构阶段 |
| **OQ-MQ-003** | 纯图片消息默认提问文案 | **「请帮我分析这张图片」**（固定，后端注入） | RESOLVED |
| **OQ-MQ-004** | doubao-vision 不可用时的降级策略 | **选项 A**：2 次失败后告知用户本轮无法处理，WS 连接保持，可纯文字重试。**本期不做 RapidOCR 兜底（排除在 NS-002）。** | RESOLVED |
| **OQ-MQ-005** | 含图消息历史持久化 | **追加 VLM 描述文字**到 user 消息记录（格式：`[图片描述：<VLM输出>] <原始文字>`），原图字节不入库 | RESOLVED |
| **OQ-MQ-006** | 客户端压缩参数：1920px + JPEG quality=80/85 | 开发阶段用真实铭牌图片实测验证；建议 quality=85 | 开发阶段 |
| **OQ-MQ-007** | 临时图片存储方式 | 推荐进程内 dict + TTL，架构阶段确认 | 架构阶段 |

---

## 附录 B：风险登记

| 风险编号 | 描述 | 可能性 | 影响 | 缓解措施 |
|---------|------|-------|------|---------|
| RISK-MQ-001 | Pi WiFi 抖动导致 doubao-vision 调用偶发 >15s（历史实测，8 次约 1 次）；用户等待体验差 | 高（已实测） | 中（等待时间长但有降级） | 前端进度提示（「正在分析…」）；超时设 30s + 1 次重试；REQ-NFR-001 时延目标为 P90 非 P99 |
| RISK-MQ-002 | `orchestrator._route` 收到含 VLM 描述前缀的增强 query，LLM 分类器路由可能漂移（原来纯问题意图明确，加了描述文字后意图变复杂） | 中 | 中（路由错专家导致回答质量下降） | 架构阶段设计前缀格式，使 VLM 描述与用户问题明显区分（如 XML 标签包裹）；抽检 5 个路由用例对比 AC-MQ-001/US-MQ-004 |
| RISK-MQ-003 | doubao-vision 的工程图纸/参数表理解效果不佳（图片模糊、印刷体复杂等），用户体验可能不如预期 | 中 | 中（智能体回答质量低）| 需求阶段 OQ-MQ-001 选择合适模型；开发阶段用真实设备图片样本验收（AC-MQ-001-02 人工抽检） |
| RISK-MQ-004 | 图片字节意外进入日志（开发者 debug 时用 logger.debug("data: %s", data) 等方式）| 中 | 高（隐私泄露 + 日志膨胀） | SC-001/002 为强约束；代码评审检查点：vision_service.py 任何日志调用不得含图片字节参数；US-MQ-008 自动化测试覆盖 |
| RISK-MQ-005 | 临时 upload_id 存储方案（进程内 dict）在 Pi 5 重启或异常退出后丢失，用户 TTL 内的上传失效；前端重试逻辑需覆盖 IMAGE_EXPIRED 错误 | 低（单 worker，重启不频繁） | 低（重新上传即可） | US-MQ-005 AC-MQ-005-03 覆盖过期处理；前端在 IMAGE_EXPIRED 时自动引导重新上传 |
| RISK-MQ-006 | 前端客户端压缩在低端手机/Safari iOS 上的 Canvas/Blob API 兼容性问题 | 低（现代浏览器支持良好） | 低（压缩失败时降级为原图上传，如原图 ≤10MB 仍可上传） | 开发阶段在 iOS Safari 实测；前端压缩失败时有 try/catch 降级为直接上传 |

---

*文档状态：APPROVED（2026-06-24）。OQ-MQ-001/003/004/005 已由产品负责人决策并锁入。OQ-MQ-006/007 为开发/架构阶段决策，不阻塞推进。*
