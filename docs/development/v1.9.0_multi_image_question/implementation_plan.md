# 实现计划 — v1.9.0 多图提问（Multi-Image Question）

**特性**：单次最多5张图片提问
**版本**：v1.9.0_multi_image_question
**状态**：IMPLEMENTED
**日期**：2026-06-24
**作者**：software-developer
**依赖**：
- `docs/architecture/v1.9.0_multi_image_question/architecture_design.md` (DRAFT, APPROVED)
- `docs/architecture/v1.9.0_multi_image_question/module_design.md` (DRAFT, APPROVED)

---

## 1. 实现范围

本期实现基于 v1.5.0 增量，严格遵循 ADR-MI-001/002/003/004 决策，保持向后兼容。

| 文件 | 变更类型 | 关键变更 |
|------|---------|---------|
| `api/vision_service.py` | 修改（新增函数）| 新增 `analyze_images_batch()`，扩展 `_get_vision_config()` |
| `api/consumers.py` | 修改（增量）| `receive` 多字段解析，`_handle_chat` 签名改名，`_pump` 新增 2 个 kind |
| `api/langgraph_chat/adapter.py` | 修改（增量）| `stream_chat` 签名扩展，多图 VLM 前置逻辑 |
| `frontend/src/utils/api.js` | 修改（新增函数）| 新增 `uploadChatImages()` |
| `frontend/src/views/ChatView.vue` | 修改（增量）| 多图 state，多图预览 UI，多图发送逻辑 |

**不变文件**：`views_chat_image.py`、`urls.py`、`orchestrator.py`

---

## 2. 后端实现细节

### 2.1 vision_service.py — analyze_images_batch()

- **位置**：文件末尾追加（v1.5.0 所有函数不变）
- **参数**：`image_bytes_list: list[bytes], user_text: str, on_progress=None`
- **实现**：
  1. 从 `_get_vision_config()` 读取 `batch_timeout`（新增字段，默认90s）
  2. 对每张图创建 `_task_wrapper`（先调用 on_progress，再调用 analyze_image）
  3. `asyncio.gather(*tasks, return_exceptions=True)` 并发执行
  4. 聚合结果：成功 → str；Exception → None
  5. 日志：仅记录 count/index/size/success/failed/elapsed，**无 base64 内容**

### 2.2 consumers.py — receive() 变更

- **ADR-MI-003 三路优先规则**：
  1. `image_upload_ids`（列表）→ 多图路径
  2. `image_upload_id`（字符串）→ 包装为单元素列表（向后兼容）
  3. 两者均不存在 → 纯文字路径
- **后端超5张拦截**：`len(upload_ids) > 5` → `IMAGE_TOO_MANY`
- **逐图 UUID 校验**：`for uid in upload_ids`
- **默认文案**：`len > 1` → "请帮我分析这些图片"，`len == 1` → 继承 v1.5.0

### 2.3 consumers.py — _handle_chat() 变更

- 参数名：`upload_id` → `upload_ids: list | None`
- TTL 预检：`for i, uid in enumerate(upload_ids)`，失败报告图片序号
- 不直接发 vision_progress（改由 adapter yield，_pump 透传）

### 2.4 consumers.py — _pump() 变更

新增两个 kind 处理（在 `persist_enhanced_message` 之前）：
- `kind == 'vision_progress'` → 透传 WS `vision_progress` 消息
- `kind == 'image_analysis_partial'` → 解析 JSON，发 `IMAGE_ANALYSIS_PARTIAL` 非阻塞错误帧

### 2.5 adapter.py — stream_chat() 变更

- 签名：新增 `upload_ids: Optional[list] = None`，保留 `upload_id: Optional[str] = None`
- 向后兼容：`if upload_ids is None and upload_id is not None: upload_ids = [upload_id]`
- 最简进度帧实现：先循环 yield 所有 vision_progress 帧，再 await analyze_images_batch
- 全部失败：`raise VisionServiceError`（与 v1.5.0 路径一致）
- 部分失败：`yield ("image_analysis_partial", json.dumps({...}))`
- 持久化：`yield ("persist_enhanced_message", persist_msg)`

---

## 3. 前端实现细节

### 3.1 api.js — uploadChatImages()

- 新增函数（不修改 uploadChatImage）
- `Promise.allSettled` 并发调用 `uploadChatImage`
- 返回成功的 upload_id 列表，部分失败 console.warn 不抛出

### 3.2 ChatView.vue — 多图 state

- 新增 `selectedImages: ref([])` — `{blob, previewDataURL}` 数组
- 新增 `visionProgressMsg: ref('')` — 多图进度文字
- 保留原有 `selectedImageBlob`/`previewDataURL` 供向后兼容（不直接使用）

### 3.3 ChatView.vue — onImageSelect()

- 支持 `event.target.files`（多文件）循环处理
- 超5张限制：`selectedImages.length >= 5` 时 alert 并 break
- 每张独立大小/MIME 校验、Canvas 压缩
- 追加到 `selectedImages` 列表

### 3.4 ChatView.vue — handleSend()

- 多图上传：`uploadChatImages(selectedImages.map(i => i.blob))`
- WS 发送：`image_upload_ids: upload_ids`（ADR-MI-003 新字段）
- 默认文案：`selectedImages.length > 1 ? "请帮我分析这些图片" : "请帮我分析这张图片"`
- 部分上传失败：继续发送剩余图片（容错精神）

### 3.5 ChatView.vue — 模板

- 多图预览区：`v-for="(img, idx) in selectedImages"` 循环，每张有 × 按钮
- 已达5张时显示「已达上限（5/5）」
- file input 新增 `multiple` 属性
- 上传按钮：`selectedImages.length >= 5` 时禁用
- 历史消息含图检测：正则 `/^\[图片(\d+)?描述：/` 覆盖单图和多图格式

---

## 4. 向后兼容验证

| 场景 | 行为 |
|------|------|
| 旧前端发 `image_upload_id`（单数）| consumers.receive 包装为单元素列表，走相同处理路径 ✓ |
| 纯文字消息 | `upload_ids = None`，走纯文字路径，行为与 v1.4.1 完全一致 ✓ |
| adapter.stream_chat(upload_id="uuid") | 旧参数仍有效，自动包装为 upload_ids=["uuid"] ✓ |
| v1.5.0 单图测试（48个）| 接口签名向后兼容，逻辑路径不变 ✓ |

---

## 5. 安全约束确认

- [x] base64 不进日志（`analyze_images_batch` 日志只记录 index/size）
- [x] base64 不进 WS 帧（WS 只传 upload_ids UUID 列表）
- [x] upload_id 绑定 user_id（`get_upload` 调用传 user_id，逐图校验）
- [x] UUID4 格式校验逐图执行（`receive` 中 `for uid in upload_ids`）
- [x] 超5张后端双重拦截（前端禁用按钮 + 后端 IMAGE_TOO_MANY）

---

## 6. 无 DB migration 确认

- vision_service 各 upload_id 独立 dict 条目，结构不变
- orchestrator State 字段不变（`vision_description` 继承，多图场景传 None）
- 无需 Django migration
