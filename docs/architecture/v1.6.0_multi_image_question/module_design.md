**特性**：多图提问——最多5张图片批量上传与分析（Multi-Image Question）
**版本**：v1.6.0_multi_image_question
**状态**：DRAFT
**日期**：2026-06-24
**作者**：system-architect
**依赖**：
- `docs/requirements/v1.6.0_multi_image_question/requirements_spec.md` (APPROVED，用户确认)
- `docs/architecture/v1.6.0_multi_image_question/architecture_design.md` (DRAFT)
- `docs/architecture/v1.5.0_multimodal_question/module_design.md` (DRAFT，基线)

---

# 模块设计文档 — v1.6.0 多图提问（基于 v1.5.0 增量）

**文档编号**：ARCH-MOD-MI-v160-001
**项目名称**：FreeArk 方舟智能体多图提问（v1.6.0_multi_image_question）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-24

---

## 1. 模块总览

本文档仅描述相对于 v1.5.0 的**变更与新增内容**。v1.5.0 已有且本版本不变的模块（MOD-MQ-02 图片预上传 REST 视图、MOD-MQ-06 orchestrator 扩展、MOD-MQ-07 配置路由）不重复记录。

| MOD-ID | 模块名 | 层级 | 变更类型 | 职责摘要（增量）| 依赖于 |
|--------|--------|------|---------|----------------|--------|
| MOD-MI-01 | 前端多图输入模块 | 前端 UI 层 | 修改（基于 MOD-MQ-01）| 单图 state 扩展为列表、超5张拦截、并发上传、多图预览删除、新 WS 字段、多图 vision_progress 渲染 | MOD-MQ-02（REST 预上传接口，不变）|
| MOD-MI-03 | 视觉服务模块扩展（vision_service）| Django 服务层 | 修改（基于 MOD-MQ-03）| 新增 `analyze_images_batch()` 批量分析函数（逐图独立调用，返回有序结果列表）| 外部：doubao-vision API（火山方舟）|
| MOD-MI-04 | WS 消费者扩展（consumers）| Django Channels 层 | 修改（基于 MOD-MQ-04）| 多字段解析（image_upload_ids 优先）、超5张拦截、多图默认文案、逐图 TTL 预检 | MOD-MI-03（vision_service 扩展）、MOD-MI-05（adapter 扩展）|
| MOD-MI-05 | LangGraph 适配器扩展（adapter）| LangGraph 适配层 | 修改（基于 MOD-MQ-05）| stream_chat 签名扩展 upload_ids 参数、批量 VLM 前置调用、多图增强消息构建、部分失败 kind 回传 | MOD-MI-03（analyze_images_batch）、MOD-MQ-06（orchestrator，不变）|

**不变模块（继承 v1.5.0，本版本零改动）**：
- MOD-MQ-02（views_chat_image.py：REST 单图上传端点，不变）
- MOD-MQ-06（orchestrator.py：图结构和 State 不变，vision_description 字段已在 v1.5.0 新增）
- MOD-MQ-07（settings.py + urls.py：配置路由不变）

---

## 2. 模块详情

### MOD-MI-01：前端多图输入模块

**文件**：`FreeArkWeb/frontend/src/views/ChatView.vue`（修改）、`FreeArkWeb/frontend/src/utils/api.js`（修改）

**职责**：在 v1.5.0 单图能力基础上，扩展为最多5张图片的选择、预览、删除、并发上传、WS 多图字段发送、多张 vision_progress 进度渲染。

**覆盖需求**：REQ-MI-001、REQ-MI-002、REQ-MI-003（前端侧）、REQ-MI-NFR（OQ-MI-004 默认文案）

**公开接口契约（相对 v1.5.0 变更项）**：

```
// api.js 新增函数（v1.6.0 新增，基于 v1.5.0 uploadChatImage 复用）
uploadChatImages(files: (File | Blob)[]) → Promise<string[]>
  - 使用 Promise.allSettled 并发调用 uploadChatImage(f) 处理每个文件（ADR-MI-002）
  - 收集 fulfilled 的 upload_id 列表；rejected 的记录为上传失败（前端 UI 提示用户移除）
  - 返回：成功上传的 upload_id 数组（长度可能 < files.length，若部分失败）
  - 异常：不抛出（allSettled 保证全部 settled），失败项通过 Promise.allSettled 结果的 rejected 状态处理
  - 安全约束：同 uploadChatImage，通过 authenticatedFetch 调用，禁止裸 axios [KE-ARCH-005]

// api.js 保留函数（v1.5.0 已有，不变）
uploadChatImage(file: File | Blob) → Promise<{upload_id: string, expires_in: number}>
  - 不变，uploadChatImages 内部逐张调用此函数

// ChatView.vue state 变更（v1.6.0 修改）
// 旧（v1.5.0）：
//   selectedImageBlob: Blob | null
//   previewDataURL: string | null
// 新（v1.6.0）：
selectedImages: Array<{blob: Blob, previewDataURL: string}>  // 最多5个元素
  - 替换 selectedImageBlob/previewDataURL（单图 state 废弃）
  - 长度 0 表示无图（等同 v1.5.0 的 selectedImageBlob=null）

// ChatView.vue 函数变更（v1.6.0 修改）
onImageSelect(event: Event) → void
  - v1.5.0：读取单个文件，设置 selectedImageBlob/previewDataURL
  - v1.6.0：读取 event.target.files（可多选），逐个处理：
    * 若 selectedImages.length >= 5 → 提示"最多5张图片"，忽略额外文件（REQ-MI-002）
    * 每个文件执行大小/MIME 校验（同 v1.5.0）
    * 压缩后追加到 selectedImages 列表
    * 超5张时禁用上传按钮（REQ-MI-002 方案A）

removeImage(index: number) → void
  - v1.6.0 新增（REQ-MI-001）
  - 从 selectedImages 中移除下标 index 的图片
  - 若移除后 selectedImages.length < 5，重新启用上传按钮
  - 重置对应的 file input（允许重选）

sendMessage() → void（修改）
  - v1.5.0：若 selectedImageBlob 非空 → uploadChatImage → 发 WS image_upload_id
  - v1.6.0：
    若 selectedImages.length > 0 →
      ① 调用 uploadChatImages(selectedImages.map(i => i.blob))
         收集成功的 upload_ids 列表
      ② WS 发送：
         {
           type: "chat_message",
           message: userText 或 defaultText,
           image_upload_ids: upload_ids    // 新字段，复数列表（REQ-MI-003，ADR-MI-003）
         }
         注意：不再发送旧的 image_upload_id 单数字段（新前端只发新字段）
    若 selectedImages 为空 →
      WS 发送：{type:"chat_message", message: userText}（无图，与 v1.4.x 完全一致）
    发送后调用 clearSelectedImages()

clearSelectedImages() → void（替换 clearSelectedImage）
  - v1.6.0 新增
  - 清空 selectedImages 数组
  - 重置 file input 的 value
  - 重新启用上传按钮

// OQ-MI-004 默认文案逻辑（在 sendMessage 中）
defaultText 判断规则：
  selectedImages.length > 1 且 userText 为空 → "请帮我分析这些图片"（多图默认文案）
  selectedImages.length === 1 且 userText 为空 → "请帮我分析这张图片"（单图默认文案，v1.5.0 不变）
  userText 非空 → 使用用户输入的文字
```

**WS 消息处理扩展（接收，相对 v1.5.0 变更）**：

```
// vision_progress 消息处理扩展（v1.6.0）
case "vision_progress":
  - v1.5.0：显示单一进度提示"正在分析图片，请稍候…"
  - v1.6.0：直接显示服务端传来的 message 文字（"正在分析第N/T张图片，请稍候…"）
  - 在收到 stream_token / stream_end / error 时自动隐藏（行为不变）

// 新增 error code 处理（v1.6.0）
case "error" with code "IMAGE_TOO_MANY":
  - 渲染友好错误提示："最多支持5张图片，请删除多余图片后重新发送"
case "error" with code "IMAGE_ANALYSIS_PARTIAL":
  - 渲染非阻塞提示气泡（不挡内容区，作为通知而非错误）
  - 示例："部分图片分析失败，已用占位文字替代"
  - WS 连接保持，stream_token 正常继续（非阻塞）
```

**历史消息含图标注（v1.6.0 扩展）**：

```
renderUserMessage(message: {content: string, ...}) → VNode
  - v1.5.0：content 以 "[图片描述：" 开头 → 渲染「含图提问」图标标注
  - v1.6.0：content 以 "[图片1描述：" / "[图片2描述：" 等多图格式开头，同样渲染「含图提问」标注
  - 正则匹配：/^\[图片\d+描述：/ 覆盖多图和单图格式（兼容 v1.5.0 旧格式 "[图片描述："）
```

**依赖模块**：MOD-MQ-02（REST 预上传接口，不变）

**外部依赖**：浏览器原生 Canvas API、Blob API、FileReader API（不变，无新 npm 包）

---

### MOD-MI-03：视觉服务模块扩展（vision_service.py）

**文件**：`FreeArkWeb/backend/freearkweb/api/vision_service.py`（修改）

**职责**：在 v1.5.0 MOD-MQ-03 基础上，新增 `analyze_images_batch()` 批量分析函数，实现逐图独立 VLM 调用（asyncio.gather，return_exceptions=True），返回有序结果列表（含成功描述或 VisionServiceError 异常对象）。

**覆盖需求**：REQ-MI-004（有序结果）、REQ-MI-007（部分失败容错）、REQ-MI-NFR（每张前 progress）、RISK-MI-002（整体 90s 超时）

**新增接口契约**（v1.6.0 新增，v1.5.0 已有接口不变）：

```python
# 新增函数（v1.6.0）
async def analyze_images_batch(
    image_bytes_list: list[bytes],
    user_text: str,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[str | None]:
    """
    批量分析多张图片，逐图独立调用 analyze_image，返回有序结果列表。

    参数：
      image_bytes_list: 图片字节列表，顺序与 upload_ids 保持一致（REQ-MI-004）
                        安全约束：不进任何 logger 调用，日志只记录 index 和 size
      user_text: 用户原始文字（可为空）；对每张图使用相同的 user_text
      on_progress: 可选的进度回调（异步），每张图开始分析前调用，参数 (index: int, total: int)
                   供 adapter 层通过此回调向 consumers yield vision_progress 帧

    行为：
      1. 整体用 asyncio.timeout(VISION_BATCH_TIMEOUT_SECONDS) 包裹（默认90s，RISK-MI-002）
      2. 若 on_progress 非空，对每张图调用 on_progress(i, len(image_bytes_list)) 后再发起 VLM
      3. 使用 asyncio.gather(*tasks, return_exceptions=True) 并发调用
         每个 task = analyze_image(image_bytes_list[i], user_text)（ADR-MI-001）
         注意：asyncio.gather 并发时 vision_progress 帧在各协程启动前按顺序发出（见实现说明）
      4. 聚合结果：
         - 成功（str）→ results[i] = description（str）
         - 失败（Exception）→ results[i] = None（表示失败，由调用方决定占位文字）

    实现说明（vision_progress 与 asyncio.gather 的协调）：
      gather 并发时无法保证"每张开始前发 progress"的时序。
      推荐实现：将 progress 发送包裹在每个 task 的 wrapper 协程中：
        async def task_with_progress(i, img):
            if on_progress:
                await on_progress(i, total)
            return await analyze_image(img, user_text)
      通过 asyncio.gather(*[task_with_progress(i, img) for i, img in enumerate(image_bytes_list)],
                          return_exceptions=True) 执行
      由于 gather 是并发的，进度帧可能近乎同时发出（Pi 5 网络延迟低，用户体验可接受）

    返回：list[str | None]，长度等于 image_bytes_list 长度，顺序对应（REQ-MI-004）
      - 每个元素为成功的 VLM 描述字符串，或 None（VLM 调用失败）

    异常：
      - asyncio.TimeoutError（整体90s超时）→ 直接抛出（由 adapter 包装为 VisionServiceError）
      - 不抛 VisionServiceError（单图失败通过 return_exceptions=True 收集为 None，不中止整批）

    日志约束（继承 v1.5.0 SC-002）：
      - INFO: "vision_service.analyze_images_batch: start count={N}"
      - INFO: "vision_service.analyze_images_batch: index={i} size={size}bytes"（每图，不含内容）
      - INFO: "vision_service.analyze_images_batch: done success={S} failed={F} elapsed={t:.2f}s"
      - 绝不记录 image_bytes、base64 字符串
    """

# 新增配置变量（settings.py 新增）
VISION_BATCH_TIMEOUT_SECONDS: int = 90  # 整体多图 VLM 批处理超时（默认90s，RISK-MI-002）
# 读取方式（在 _get_vision_config() 中扩展）：
# "batch_timeout": getattr(settings, "VISION_BATCH_TIMEOUT_SECONDS", 90)
```

**不变接口（v1.5.0 已有，本版本保持不变）**：

- `store_upload(image_bytes: bytes, user_id: int) -> str`
- `get_upload(upload_id: str, user_id: int) -> bytes`
- `check_capacity() -> bool`
- `delete_upload(upload_id: str) -> None`
- `analyze_image(image_bytes: bytes, user_text: str) -> str`（`analyze_images_batch` 内部调用）
- `_downscale_for_vlm(image_bytes: bytes) -> bytes`（`analyze_image` 内部调用，每张独立缩）
- 全部异常类：`VisionServiceError`、`ImageExpiredError`、`ImageAccessDeniedError`、`StorageCapacityError`

**依赖模块**：无内部模块依赖（不变）

**外部依赖**：`openai` SDK（`AsyncOpenAI`，不变）；Python 标准库 `asyncio`（`gather`、`timeout`）

---

### MOD-MI-04：WS 消费者扩展（consumers.py）

**文件**：`FreeArkWeb/backend/freearkweb/api/consumers.py`（修改）

**职责**：在 v1.5.0 MOD-MQ-04 基础上，扩展 WS 帧解析以支持 `image_upload_ids` 列表字段（向后兼容 `image_upload_id` 单数字段）、超5张拦截、逐图 UUID 校验、逐图 TTL 预检、多图默认文案。

**覆盖需求**：REQ-MI-002（超5张拦截）、REQ-MI-003（向后兼容，ADR-MI-003）、REQ-MI-009（IMAGE_TOO_MANY）、REQ-MI-NFR（UUID 校验逐图执行）

**接口变更（相对 v1.5.0 的增量变更）**：

```python
# receive 方法变更（v1.6.0，基于 v1.5.0 扩展）
async def receive(self, text_data: str = None, bytes_data=None) -> None:
    """
    v1.6.0 变更（相对 v1.5.0）：
      1. 多字段解析（ADR-MI-003 优先规则）：
         upload_ids: list[str] | None = None

         image_upload_ids_raw = data.get('image_upload_ids')   # 新字段（列表）
         image_upload_id_raw  = data.get('image_upload_id')    # 旧字段（字符串，v1.5.0）

         if isinstance(image_upload_ids_raw, list) and len(image_upload_ids_raw) > 0:
             upload_ids = image_upload_ids_raw    # 新字段优先
         elif isinstance(image_upload_id_raw, str) and image_upload_id_raw:
             upload_ids = [image_upload_id_raw]  # 旧字段向后兼容（包装为单元素列表）
         else:
             upload_ids = None                    # 无图，纯文字路径

      2. 超5张后端拦截（REQ-MI-002，REQ-MI-009）：
         if upload_ids is not None and len(upload_ids) > 5:
             await self._send_error(
                 "IMAGE_TOO_MANY",
                 "最多支持5张图片，请删除多余图片后重新发送"
             )
             return

      3. 逐图 UUID 格式校验（REQ-MI-NFR，v1.5.0 单图校验扩展）：
         for uid in (upload_ids or []):
             if not isinstance(uid, str) or not _is_valid_uuid(uid):
                 await self._send_error("IMAGE_INVALID", "图片引用无效")
                 return

      4. 多图默认文案（OQ-MI-004）：
         if upload_ids and not user_message:
             if len(upload_ids) > 1:
                 user_message = "请帮我分析这些图片"   # 多图场景
             else:
                 user_message = "请帮我分析这张图片"   # 单图场景（与 v1.5.0 一致）

      5. 调用 _handle_chat(user_message, upload_ids=upload_ids)
         （参数名从 upload_id 改为 upload_ids，类型从 str|None 改为 list[str]|None）
    """

# _handle_chat 方法变更（v1.6.0，基于 v1.5.0 扩展）
async def _handle_chat(
    self,
    user_message: str,
    upload_ids: list[str] | None = None,  # v1.6.0：参数名改为 upload_ids（列表），默认 None
) -> None:
    """
    v1.6.0 变更（相对 v1.5.0）：

    1. 旧字段兼容重命名：
       函数签名中 upload_id 参数重命名为 upload_ids（list[str]|None）
       内部处理逻辑从单图扩展为多图列表迭代

    2. 逐图 TTL 预检（v1.5.0 单图扩展为多图循环）：
       if upload_ids is not None:
           for i, uid in enumerate(upload_ids):
               try:
                   vision_service.get_upload(uid, self.user.id)  # 仅 TTL 校验，不取 bytes
               except ImageExpiredError:
                   await self._send_error("IMAGE_EXPIRED",
                       f"图片 {i+1} 已过期，请重新上传全部图片后重试")
                   return
               except ImageAccessDeniedError:
                   await self._send_error("IMAGE_INVALID", "图片引用无效")
                   return

    3. vision_progress 帧：
       v1.5.0：发送单次 {"type":"vision_progress","message":"正在分析图片，请稍候…"}
       v1.6.0：不在 consumers 层发送 vision_progress（改由 adapter 通过 yield 回传）
               consumers._pump 识别 kind="vision_progress" → 转发 WS（见下方 _pump 变更）
               理由：多图进度文案（"正在分析第N/T张…"）在 adapter 层构建，consumers 不感知图片数量

    4. adapter.stream_chat 调用变更：
       v1.5.0：adapter.stream_chat(message=..., session_key=..., upload_id=upload_id, user_id=...)
       v1.6.0：adapter.stream_chat(message=..., session_key=..., upload_ids=upload_ids, user_id=...)
               （upload_id 参数替换为 upload_ids，adapter 签名同步更新）

    5. 部分失败处理（新增）：
       _pump 新增识别 kind="image_analysis_partial" →
       从 text 中解析失败图片索引，发送非阻塞 WS 错误帧：
         IMAGE_ANALYSIS_PARTIAL + 提示文字（ADR-MI-004）

    6. 持久化逻辑不变（v1.5.0 _vision_persist_message 机制继承）：
       _pump 识别 kind="persist_enhanced_message" → 存入 _vision_persist_message
       流结束后 chat_memory.append_message 写入多图持久化格式（REQ-MI-008）
    """

# _pump 方法变更（v1.6.0 新增 kind 处理）
async def _pump(self, agen, accumulated_prefix: str = '') -> tuple[str, str]:
    """
    v1.6.0 新增 kind 处理（在 v1.5.0 基础上追加）：

    elif kind == 'vision_progress':
        # v1.6.0 新增（ADR-MI-004 设计）：adapter 通过此 kind 传递多图进度文字
        # consumers 透传给前端（不累积到 accumulated，不落库）
        await self.send(json.dumps({'type': 'vision_progress', 'message': text}))

    elif kind == 'image_analysis_partial':
        # v1.6.0 新增（ADR-MI-004，REQ-MI-009）：
        # adapter 通过此 kind 通知有图片分析失败（但整体未中止）
        # consumers 发送非阻塞 WS 错误帧（IMAGE_ANALYSIS_PARTIAL）
        # text 格式：JSON 字符串 {"failed_indices": [1, 3], "total": 5}
        try:
            partial_info = json.loads(text)
            failed_indices = partial_info.get('failed_indices', [])
            total = partial_info.get('total', 0)
            if failed_indices:
                failed_str = "、".join(str(i+1) for i in failed_indices)
                await self._send_error(
                    "IMAGE_ANALYSIS_PARTIAL",
                    f"第{failed_str}张图片分析失败，已用占位文字替代，其余图片分析正常"
                )
        except (ValueError, TypeError, KeyError):
            # 解析失败静默忽略（非阻塞，不中断流）
            pass

    # 已有 kind 处理不变（v1.5.0 继承）：
    # - 'reasoning' → reasoning_token
    # - 'content' → stream_token + accumulated
    # - 'confirm' → confirm_required（return）
    # - 'status' → status_update
    # - 'related_images' → 存 _related_images
    # - 'persist_enhanced_message' → 存 _vision_persist_message
    """
```

**实例变量变更**（相对 v1.5.0）：

```python
# connect() 新增初始化（v1.6.0，在 v1.5.0 基础上无需新增 — upload_ids 为局部变量，不需要实例变量）
# 注：v1.5.0 已有的 _vision_persist_message 实例变量继续使用，语义不变（多图合并持久化消息）
```

**依赖模块**：
- MOD-MI-03（`vision_service.get_upload`，逐图 TTL 预检）
- MOD-MI-05（`adapter.stream_chat` 签名扩展）

---

### MOD-MI-05：LangGraph 适配器扩展（adapter.py）

**文件**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/adapter.py`（修改）

**职责**：在 v1.5.0 MOD-MQ-05 基础上，扩展 `stream_chat` 以接受 `upload_ids: list[str]`，调用 `vision_service.analyze_images_batch()`，构建多图增强消息和持久化消息，通过新增 kind（`vision_progress`、`image_analysis_partial`）向 consumers 传递进度和部分失败信息。

**覆盖需求**：REQ-MI-004（有序结果）、REQ-MI-005（注入格式）、REQ-MI-007（部分失败占位）、REQ-MI-008（持久化格式）、RISK-MI-002（90s 整体超时）

**接口变更（v1.6.0，相对 v1.5.0 增量）**：

```python
# stream_chat 签名变更（v1.6.0）
@classmethod
async def stream_chat(
    cls,
    message: str,
    session_key: str,
    upload_ids: list[str] | None = None,   # v1.6.0 新参数（替代 upload_id）
    upload_id: str | None = None,          # v1.5.0 旧参数（保留向后兼容）
    user_id: int | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """
    v1.6.0 变更（相对 v1.5.0）：

    向后兼容处理（旧参数 upload_id）：
      # 若外部调用传了旧参数 upload_id（单数），包装为 upload_ids（ADR-MI-003 对应）
      if upload_ids is None and upload_id is not None:
          upload_ids = [upload_id]

    多图 VLM 前置调用流程（upload_ids 非空时）：

    1. 逐图取字节：
       image_bytes_list = [vision_service.get_upload(uid, user_id) for uid in upload_ids]
       - ImageExpiredError / ImageAccessDeniedError → re-raise（由 consumers 捕获）
       安全约束：image_bytes_list 不进任何 logger 调用

    2. 构建 progress_cb（供 analyze_images_batch 回调）：
       async def progress_cb(index: int, total: int) -> None:
           yield ("vision_progress", f"正在分析第{index+1}/{total}张图片，请稍候…")
       注意：此处 yield 是伪代码，实际实现需要将 progress_cb 设计为
             AsyncQueue 或列表缓冲的异步通信机制（见实现说明）

    实现说明（progress_cb 与 async generator 协调）：
      stream_chat 是 async generator（yield），不能直接 await 内部的 yield。
      推荐实现：
        progress_queue: asyncio.Queue = asyncio.Queue()
        async def progress_cb(i: int, total: int):
            await progress_queue.put(f"正在分析第{i+1}/{total}张图片，请稍候…")
        
        # 启动 analyze_images_batch 为 Task，同时消费 queue：
        task = asyncio.create_task(
            vision_service.analyze_images_batch(image_bytes_list, message, progress_cb)
        )
        # 在 task 运行期间不断从 queue 取出 progress 消息并 yield：
        while not task.done():
            try:
                prog_msg = progress_queue.get_nowait()
                yield ("vision_progress", prog_msg)
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.05)   # 短暂让出事件循环
        results = await task   # 获取 analyze_images_batch 结果

    3. 获得 results: list[str | None]（有序，ADR-MI-001，REQ-MI-004）

    4. 构建增强消息（REQ-MI-005，ADR-MI-004 占位格式）：
       failed_indices: list[int] = []
       injections: list[str] = []
       for i, result in enumerate(results):
           if result is None:
               injections.append(f"[用户图片{i+1}分析：图片分析失败，已跳过]")
               failed_indices.append(i)
           else:
               injections.append(f"[用户图片{i+1}分析：{result}]")
       enhanced_message = "\n".join(injections) + f"\n\n{message}"

    5. 若全部失败（len(failed_indices) == len(results)）：
       → raise VisionServiceError("图片分析暂时不可用，请重试或用文字描述图片内容")
       → 由 consumers 捕获，发送 IMAGE_ANALYSIS_FAILED

    6. 若部分失败（0 < len(failed_indices) < len(results)）：
       → yield ("image_analysis_partial", json.dumps({
           "failed_indices": failed_indices,
           "total": len(results)
         }, ensure_ascii=False))
       （consumers._pump 识别后发非阻塞 WS 错误帧，ADR-MI-004，REQ-MI-009）

    7. 释放 image_bytes_list（del）：
       del image_bytes_list   # REQ-NFR-002 内存约束，多图时显式释放列表
       for uid in upload_ids:
           vision_service.delete_upload(uid)  # 逐图清理临时存储

    8. 构建持久化消息（REQ-MI-008，ADR-MI-004）：
       persist_parts: list[str] = []
       for i, result in enumerate(results):
           if result is None:
               persist_parts.append(f"[图片{i+1}描述：图片分析失败]")
           else:
               persist_parts.append(f"[图片{i+1}描述：{result}]")
       persist_msg = " ".join(persist_parts) + f" {message}"

    9. 启动 graph.astream（同 v1.5.0，enhanced_message 已合并所有图片描述）：
       async for kind, text in _drive(
           orch,
           {"messages": [HumanMessage(content=enhanced_message)],
            "vision_description": enhanced_message if upload_ids else None},
           config
       ):
           yield (kind, text)

    10. 流结束后回传持久化消息（同 v1.5.0，kind 不变）：
        if upload_ids:
            yield ("persist_enhanced_message", persist_msg)

    向后兼容（upload_ids=None 时）：
      行为与 v1.5.0 upload_id=None 完全一致，enhanced_message = message，不调用 VLM。

    安全约束（继承 v1.5.0 SC-002）：
      - image_bytes_list 中的 bytes 不进任何 logger 调用
      - 日志只记录 upload_ids 数量、每张分析耗时（不含内容）
    """
```

**`_drive` 函数变更**（v1.6.0，最小改动）：

```python
# _drive 函数不变（v1.5.0 逻辑完全保留）
# 唯一变化：orchestrator State 中 vision_description 字段现在传入的是
#            enhanced_message（包含所有图片描述的字符串），而非单张描述。
# State TypedDict 无需修改（vision_description: Optional[str] 字段已存在于 MOD-MQ-06）
```

**依赖模块**：
- MOD-MI-03（`vision_service.get_upload`、`vision_service.analyze_images_batch`、`vision_service.delete_upload`）
- MOD-MQ-06（orchestrator State，不变）

---

## 3. 错误码完整表

| 错误码 | 版本 | 触发条件 | WS 帧 `type` | 是否阻塞 | 处理方 |
|--------|------|---------|-------------|---------|-------|
| `BUSY` | v1.3+ | 正在流式响应中再次发消息 | `error` | 阻塞（忽略新消息）| consumers（不变）|
| `IMAGE_INVALID` | v1.5+ | upload_id UUID 格式非法，或 user_id 不匹配 | `error` | 阻塞（return）| consumers（不变）|
| `IMAGE_EXPIRED` | v1.5+ | upload_id TTL 超期或不存在 | `error` | 阻塞（return）| consumers（不变）|
| `IMAGE_ANALYSIS_FAILED` | v1.5+ | VLM 全部调用失败（单图/全图）| `error` | 阻塞（return，WS 保持）| consumers（不变）|
| `OPENCLAW_UNAVAILABLE` | v1.3+ | LangGraph 编排器不可用 | `error` | 阻塞 | consumers（不变）|
| `TIMEOUT` | v1.3+ | asyncio.TimeoutError | `error` | 阻塞 | consumers（不变）|
| `INTERNAL_ERROR` | v1.3+ | 未预期异常 | `error` | 阻塞 | consumers（不变）|
| `IMAGE_TOO_MANY` | **v1.6.0 新增** | upload_ids 长度 > 5 | `error` | 阻塞（return）| consumers（MOD-MI-04）|
| `IMAGE_ANALYSIS_PARTIAL` | **v1.6.0 新增** | 部分图片 VLM 失败（非全部）| `error` | **非阻塞**（stream 继续）| consumers._pump（MOD-MI-04）|

---

## 4. 模块依赖关系图（v1.6.0 增量，基于 v1.5.0）

```
[MOD-MI-01 前端多图输入]
  │
  ├── REST (并发): POST /api/chat/image-upload/ × N ──→ [MOD-MQ-02 图片预上传 REST 视图（不变）]
  │                                                          │
  │                                                          └── store_upload() ──→ [MOD-MI-03 vision_service 扩展]
  │
  └── WS: chat_message (image_upload_ids: list) ──→ [MOD-MI-04 consumers 扩展]
                                                          │
                                                          ├── get_upload() × N（逐图 TTL 预检）──→ [MOD-MI-03]
                                                          │
                                                          └── stream_chat(upload_ids=[...]) ──→ [MOD-MI-05 adapter 扩展]
                                                                                                    │
                                                                                                    ├── get_upload() × N ──→ [MOD-MI-03]
                                                                                                    │
                                                                                                    ├── analyze_images_batch() ──→ [MOD-MI-03]
                                                                                                    │     └── analyze_image() × N（并发，asyncio.gather）
                                                                                                    │         └── doubao-vision API（外部）
                                                                                                    │
                                                                                                    ├── delete_upload() × N ──→ [MOD-MI-03]
                                                                                                    │
                                                                                                    └── graph.astream() ──→ [MOD-MQ-06 orchestrator（不变）]

[MOD-MQ-07 配置+路由（不变）]
  └── VISION_BATCH_TIMEOUT_SECONDS 新增配置变量（供 MOD-MI-03 读取）
```

**循环依赖检查**：
- MOD-MI-01 → MOD-MQ-02 → MOD-MI-03（单向）
- MOD-MI-01 → MOD-MI-04 → MOD-MI-03（单向）
- MOD-MI-04 → MOD-MI-05 → MOD-MI-03（单向）
- MOD-MI-05 → MOD-MQ-06（单向）
- **结论：无循环依赖，已验证。**

---

## 5. 数据库变更说明

### 5.1 无新增 migration（继承 v1.5.0 设计）

多图 upload_id 沿用进程内 dict 存储（ADR-MQ-002，已决策），各 upload_id 各自独立存储为单独的 dict 条目。存储结构完全不变：

```
_upload_store: dict[str, UploadEntry] = {}
# 多图场景：5 个 upload_id 对应 5 个独立的 UploadEntry
# UploadEntry = {"user_id": int, "bytes": bytes, "expire_at": datetime, "size": int}
# 结构与 v1.5.0 完全相同，无需任何迁移
```

**结论**：本版本无新增 migration，无需 `python manage.py migrate`（与 v1.5.0 相同）。

### 5.2 现有 DB 表变更

| 表名 | 变更内容 | 说明 |
|------|---------|------|
| `api_chat_session`（现有）| 无结构变更 | messages 历史字段新增 `[图片1描述：...]` 多图格式前缀（内容变化，无结构变化）|
| 其他所有表 | 无变更 | — |

---

## 6. 需求覆盖矩阵（v1.6.0 新增需求）

| 需求 ID | 覆盖模块 | 覆盖方式 |
|---------|---------|---------|
| REQ-MI-001 | MOD-MI-01 | selectedImages 列表 state、逐张预览删除、多图选择 |
| REQ-MI-002 | MOD-MI-01（前端拦截）+ MOD-MI-04（后端拦截）| 前端禁用按钮 + consumers IMAGE_TOO_MANY 错误码 |
| REQ-MI-003 | MOD-MI-04（字段解析）+ 第 5 节向后兼容矩阵 | image_upload_ids 优先，image_upload_id 向后兼容包装 |
| REQ-MI-004 | MOD-MI-03（analyze_images_batch 有序返回）+ MOD-MI-05（enumerate 构建有序注入）| 结果顺序与 upload_ids 输入顺序一致 |
| REQ-MI-005 | MOD-MI-05（enhanced_message 构建）| `[用户图片N分析：<descN>]` 格式，逐图编号 |
| REQ-MI-006 | MOD-MQ-02（不变，单图 ≤10MB 校验）+ MOD-MI-03（check_capacity 50MB 上限）| 每图独立上传时校验，整体存储上限保持 |
| REQ-MI-007 | MOD-MI-03（return_exceptions=True）+ MOD-MI-05（占位字符串构建）| 逐图独立失败捕获，占位注入 LangGraph |
| REQ-MI-008 | MOD-MI-05（persist_msg 构建）+ MOD-MI-04（_vision_persist_message 写入）| 多图持久化格式含占位标注 |
| REQ-MI-009 | MOD-MI-04（IMAGE_TOO_MANY 发送）+ MOD-MI-04._pump（IMAGE_ANALYSIS_PARTIAL 发送）| 两个新错误码均有覆盖 |

**覆盖结论：REQ-MI-001 ~ REQ-MI-009 全部覆盖，无遗漏。**

---

*文档状态：DRAFT（2026-06-24）。基于 v1.5.0 增量，待 PM 门控通过后更新为 APPROVED。*
