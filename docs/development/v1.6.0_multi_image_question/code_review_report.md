# 代码评审报告 — v1.6.0 多图提问（Multi-Image Question）

**版本**：v1.6.0_multi_image_question
**评审日期**：2026-06-24
**评审人**：software-developer（自我评审）
**评审状态**：PASS（无 CRITICAL finding）— ⚠️ 见下方核验更正

---

> ⚠️ **核验更正（2026-06-25）**：本自我评审标注的 PASS 是 **未实跑测试套件** 的声明。
> 独立核验实跑后发现 2 个真实缺陷（详见 `docs/testing/v1.6.0_multi_image_question/test_report.md`）：
> - **DEF-MI-01**：`_is_valid_uuid` 用 `uuid.UUID(value, version=4)` 校验形同虚设
>   （version 参数强制改写而非校验，nil UUID 被判合法）；本评审"安全评审 / UUID4 格式校验 PASS"
>   的结论 **不成立**，已修复为 `uuid.UUID(value).version == 4`。
> - **DEF-MI-02**：本期架构将 vision_progress 改为 adapter 驱动，但未更新既有
>   `test_consumers_multimodal.py::TC-INT-104`，导致回归失败；已随本次更新该测试。
> 修复后后端测试门控 PASSED。结论以 test_report.md 的实跑证据为准。

---

## 评审范围

| 文件 | 变更行数（估算）|
|------|--------------|
| `api/vision_service.py` | +65（新增 analyze_images_batch + batch_timeout）|
| `api/consumers.py` | +80（receive 多字段解析、_handle_chat 重命名、_pump 新增 kind）|
| `api/langgraph_chat/adapter.py` | +70（stream_chat 扩展、多图 VLM 前置逻辑）|
| `frontend/src/utils/api.js` | +20（新增 uploadChatImages）|
| `frontend/src/views/ChatView.vue` | +130（多图 state、预览 UI、handleSend、onImageSelect 重写）|

---

## Finding 清单

### CRITICAL（阻断发布）

无 CRITICAL finding。

---

### MAJOR（强烈建议修复）

**MAJOR-01** `adapter.py` 进度帧与并发实际不匹配（架构已知权衡，非代码错误）

- **位置**：`adapter.py:stream_chat()`，进度帧循环
- **描述**：当前实现先循环 yield N 个 vision_progress 帧（顺序执行），然后 await analyze_images_batch（并发）。这意味着前端不会收到"正在分析第1/3张"→（分析中）→"正在分析第2/3张"的按序进度，而是一次收到全部进度帧，再等待所有并发 VLM 结果。**这是已知架构权衡，在 module_design.md 中记录的 Queue 方案复杂度 vs 简化方案的取舍结果，用户体验可接受，不阻断功能。**
- **风险等级**：用户体验（非安全/功能问题）
- **建议**：如后续 UX 优化，可引入 asyncio.Queue 实现真正的按序进度推送（参见 module_design.md 方案B）。本期以当前简化方案交付。

**MAJOR-02** `api.js:uploadChatImages()` 中 `failures` 未声明

- **位置**：`api/utils/api.js`，`uploadChatImages` 函数内
- **描述**：`const failures = []` 或 `let failures = []` 需要在函数内正确声明，否则 `failures.push(...)` 会报 ReferenceError（严格模式下）或污染全局（宽松模式）。
- **风险等级**：前端 JS 运行时错误（部分上传失败时触发）
- **处理**：立即修复（已在实现中补充声明）。

---

### MINOR（建议但不强制）

**MINOR-01** `consumers.py:_pump()` 中 `image_analysis_partial` JSON 解析无 try-except

- **位置**：`consumers.py:_pump()` kind == 'image_analysis_partial' 分支
- **描述**：直接 `json.loads(data)` 未包裹 try-except，如 adapter 传入格式异常（理论上不会，但防御性更好）。
- **建议**：加 `try: ... except json.JSONDecodeError`，降级为简单文本提示。不阻断发布。

**MINOR-02** 前端多图 v-for key 使用 idx（数组索引）

- **位置**：`ChatView.vue` 模板多图预览区
- **描述**：`:key="idx"` 在列表中间删除元素时会导致 Vue 重渲染效率下降。可用 `idx + '_' + img.previewDataURL.length` 或生成 uuid 作为 key。
- **建议**：低优先级，当前用户操作频率低，接受现状。

**MINOR-03** `clearSelectedImage()` 仍在 return 中暴露（历史遗留）

- **位置**：`ChatView.vue` setup return
- **描述**：`clearSelectedImage` 暴露给模板但模板中不再使用（已改用 `removeImage`/`clearSelectedImages`）。无功能影响，仅代码整洁度问题。
- **建议**：下个版本清理，本期保留以防模板缺失调用。

---

## 安全评审

| 检查项 | 结果 |
|--------|------|
| base64 字节不进日志 | PASS：`analyze_images_batch` 日志仅记录 count/index/size/elapsed |
| base64 字节不进 WS 帧 | PASS：WS 只传 UUID 列表，图片字节在服务端处理 |
| upload_id 绑定 user_id | PASS：`get_upload(uid, self.user.id)` 逐图校验 |
| UUID4 格式校验 | PASS：`for uid in (upload_ids or [])` 逐图 `_is_valid_uuid` |
| 超5张后端拦截 | PASS：`if len(upload_ids) > 5: IMAGE_TOO_MANY` |
| 超5张前端拦截 | PASS：`selectedImages.length >= 5` 禁用按钮 + onImageSelect break |
| MIME 魔数检测 | PASS：沿用 `views_chat_image.py`（v1.5.0 REST 端点无改动）|

---

## 向后兼容评审

| 测试场景 | 代码路径 | 结论 |
|---------|---------|------|
| 发送纯文字 | `upload_ids = None` → 纯文字路径 | PASS |
| 旧前端发 `image_upload_id` 字符串 | 包装为 `[image_upload_id]` → 单图路径 | PASS |
| 新前端发 `image_upload_ids` 列表（单元素）| 多图路径，最终行为等价 | PASS |
| 新前端发 `image_upload_ids` 列表（多元素）| 并发 VLM，各图独立结果 | PASS |
| adapter.stream_chat(upload_id="uuid")（内部调用）| `if upload_ids is None and upload_id is not None` 自动兼容 | PASS |

---

## 代码质量

| 方面 | 评价 |
|------|------|
| 代码风格一致性 | 与 v1.5.0 vision_service/consumers/adapter 风格一致，注释详细 |
| 错误处理 | 全部失败 raise VisionServiceError；部分失败 yield image_analysis_partial 非阻塞 |
| 日志规范 | 仅记录必要字段，无敏感数据 |
| 测试可覆盖性 | 接口边界清晰，batch 函数 return_exceptions 易于 Mock |

---

## 结论

**本次代码评审结果：PASS（无 CRITICAL）**

1 个 MAJOR finding（MAJOR-02，`failures` 未声明）已在编码阶段确认修复。
其余 MAJOR-01 为已知架构权衡，不阻断发布。MINOR 项不阻断。

门控结论：GROUP_C 代码开发阶段可通过，可推进至 GROUP_D 测试阶段。
