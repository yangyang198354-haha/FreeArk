**特性**：多模态提问——用户图片输入与豆包视觉模型理解（Image Question Input）
**版本**：v1.5.0_multimodal_question
**状态**：DRAFT
**日期**：2026-06-24
**作者**：system-architect
**依赖**：requirements_spec.md (APPROVED), user_stories.md (APPROVED), architecture_design.md (DRAFT)

---

# 模块设计文档 — v1.5.0 多模态提问

**文档编号**：ARCH-MOD-MQ-v150-001
**项目名称**：FreeArk 方舟智能体多模态提问（v1.5.0_multimodal_question）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-24

---

## 1. 模块总览

| MOD-ID | 模块名 | 层级 | 变更类型 | 职责摘要 | 依赖于 |
|--------|--------|------|---------|---------|--------|
| MOD-MQ-01 | 前端多模态输入模块 | 前端 UI 层 | 修改 | 图片选择、压缩、预览、预上传、WS 携带 upload_id、vision_progress 提示渲染、历史含图标注 | MOD-MQ-02（REST 预上传接口） |
| MOD-MQ-02 | 图片预上传 REST 视图 | Django REST 层 | 新增 | 接收图片、MIME 校验、大小校验、调用 vision_service 存储、返回 upload_id | MOD-MQ-03（vision_service 存储接口） |
| MOD-MQ-03 | 视觉服务模块（vision_service） | Django 服务层 | 新增 | doubao-vision VLM 调用（含超时/重试/降级）、进程内临时图片存储（TTL/上限）、存储与检索接口 | 外部：doubao-vision API（火山方舟） |
| MOD-MQ-04 | WS 消费者扩展（consumers） | Django Channels 层 | 修改 | 读取 image_upload_id、纯图片消息默认文案注入、vision_progress WS 消息发送、降级 WS 错误发送、持久化增强消息 | MOD-MQ-03（get_upload）、MOD-MQ-05（adapter 扩展） |
| MOD-MQ-05 | LangGraph 适配器扩展（adapter） | LangGraph 适配层 | 修改 | stream_chat 签名扩展、VLM 调用前置（图外）、增强消息构建（VLM 前缀注入）、VisionServiceError 传播 | MOD-MQ-03（analyze_image）、MOD-MQ-06（orchestrator）|
| MOD-MQ-06 | LangGraph 编排图扩展（orchestrator） | LangGraph 编排层 | 修改（最小）| State 新增 vision_description 字段；_fan_out 传递含 VLM 前缀的 query | — （图结构不变）|
| MOD-MQ-07 | 配置与路由扩展（settings + urls） | 基础设施层 | 修改 | 新增 VLM 配置变量（DOUBAO_VISION_MODEL 等）、注册 /api/chat/image-upload/ 路由 | — |

---

## 2. 模块详情

### MOD-MQ-01：前端多模态输入模块

**文件**：`frontend/src/views/ChatView.vue`、`frontend/src/utils/api.js`

**职责**：提供完整的前端图片上传体验，包括图片选择、大小/格式校验、客户端压缩、预览、预上传、消息发送时携带 upload_id、VLM 进度提示、历史消息含图标注渲染。

**覆盖需求**：REQ-FUNC-001、REQ-FUNC-002（客户端侧）、REQ-FUNC-003（WS 帧构造）、REQ-FUNC-008、REQ-NFR-002（浏览器端压缩不占服务端资源）

**公开接口契约（前端函数/方法签名）**：

```
// api.js 新增函数
uploadChatImage(file: File | Blob) → Promise<{upload_id: string, expires_in: number}>
  - 构造 FormData，字段名 image
  - 通过 authenticatedFetch（现有 api.js 封装）调用 POST /api/chat/image-upload/
  - 禁止使用裸 axios（C-010）
  - 返回：服务端响应体解析结果
  - 异常：fetch 失败或服务端非 2xx 时 throw Error（含 HTTP 状态码）

// ChatView.vue 内部处理函数（架构约束，不对外暴露 API）
onImageSelect(event: Event) → void
  - 从 event.target.files[0] 读取文件
  - 校验：file.size > 10MB → alert 提示，不选中
  - 校验：MIME 类型不在白名单 → alert 提示，不选中
  - 压缩：尺寸超过 1920×1920 → Canvas 等比缩放 + toBlob(quality=0.85, 'image/jpeg')
  - 设置组件状态：selectedImageBlob, previewDataURL

compressImage(blob: Blob, maxDimension: number, quality: number) → Promise<Blob>
  - 使用 Canvas API + FileReader 实现
  - 若原始尺寸 ≤ maxDimension 则直接返回原 Blob（不压缩）
  - 返回压缩后的 JPEG Blob

clearSelectedImage() → void
  - 清空 selectedImageBlob, previewDataURL
  - 重置 file input 的 value（允许重复选同一文件）

sendMessage() → void（现有函数扩展）
  - 若 selectedImageBlob 非空：
      ① 调用 uploadChatImage(selectedImageBlob) 获得 upload_id
      ② WS 发送 {type: "chat_message", message: userText, image_upload_id: upload_id}
  - 若 selectedImageBlob 为空：
      WS 发送 {type: "chat_message", message: userText}（无变化，向后兼容）
  - 发送后调用 clearSelectedImage()
```

**WS 消息处理扩展（接收）**：

```
// 新增 kind 处理（onWsMessage 现有 switch 中新增 case）
case "vision_progress":
  - 显示进度提示「正在分析图片，请稍候…」
  - 在收到 stream_token / stream_end / error 时自动隐藏

case "error" with code "IMAGE_EXPIRED" / "IMAGE_ANALYSIS_FAILED" / "IMAGE_INVALID":
  - 渲染友好错误提示气泡（使用现有 error 消息渲染逻辑）
  - WS 连接保持（不断开）
```

**历史消息含图标注**：

```
// 消息气泡渲染逻辑扩展
renderUserMessage(message: {content: string, ...}) → VNode
  - 若 message.content 以 "[图片描述：" 开头 → 渲染「含图提问」图标标注
  - 不渲染 <img> 标签（无图片字节，防破图 icon）
  - 纯文字消息不渲染标注（无变化）
```

**依赖模块**：
- MOD-MQ-02（`POST /api/chat/image-upload/` REST 接口）

**外部依赖**：
- 浏览器原生 Canvas API、Blob API、FileReader API（无新 npm 包）
- 现有 `api.js` 的 `authenticatedFetch` 封装

---

### MOD-MQ-02：图片预上传 REST 视图

**文件**：`FreeArkWeb/backend/freearkweb/api/views_chat_image.py`（新建）、`api/urls.py`（修改）

**职责**：接收前端图片文件，执行服务端安全校验（MIME 白名单、文件大小），将图片字节委托 vision_service 存入临时存储，返回 upload_id。

**覆盖需求**：REQ-FUNC-002、REQ-NFR-003（SC-001/004/005/006）

**公开接口契约**：

```
// REST 端点
POST /api/chat/image-upload/
  权限类：IsAuthenticated（DRF TokenAuthentication，现有体系）
  请求：multipart/form-data，字段 image（InMemoryUploadedFile）
  
  服务端校验顺序：
  1. file = request.FILES.get('image') → 不存在则 400
  2. MIME 白名单：使用 python-magic 检查文件头魔数
     允许：image/jpeg, image/png, image/webp, image/heic, image/heif
     失败 → 400，{"error": "不支持的文件格式，请上传 JPEG/PNG/WebP 图片"}
  3. file.size > 10 * 1024 * 1024 → 413，{"error": "文件过大，最大 10MB"}
  4. vision_service.check_capacity() 返回 False（存储已满）→ 503，{"error": "服务繁忙，请稍后重试"}
  5. image_bytes = file.read()
  6. upload_id = vision_service.store_upload(image_bytes, user_id=request.user.id)
  
  响应 200：{"upload_id": "<uuid4>", "expires_in": 600}
  
  日志约束：
  - INFO 级记录：用户 ID、文件大小（bytes）、MIME 类型、upload_id
  - 绝不记录 image_bytes 或 base64 编码内容

// views_chat_image.py 内部类结构
class ChatImageUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]
    
    def post(self, request) → Response
```

**依赖模块**：
- MOD-MQ-03（`vision_service.store_upload`、`vision_service.check_capacity`）

**外部依赖**：
- `python-magic`（服务端 MIME 验证，见 tech_stack.md 关于是否需要新安装）
- DRF `APIView`、`IsAuthenticated`、`MultiPartParser`（现有）

---

### MOD-MQ-03：视觉服务模块（vision_service）

**文件**：`FreeArkWeb/backend/freearkweb/api/vision_service.py`（新建）

**职责**：封装 doubao-vision VLM 调用（含超时/重试/异常）、管理进程内临时图片存储（TTL/容量上限）、提供存储与 VLM 分析的完整接口。

**覆盖需求**：REQ-FUNC-002（临时存储）、REQ-FUNC-004（VLM 调用）、REQ-NFR-001（超时保护）、REQ-NFR-002（50MB 上限）、REQ-NFR-003（SC-003）、REQ-NFR-004（降级）、REQ-NFR-005（可观测性）、REQ-NFR-006（独立模块）

**公开接口契约**：

```python
# 异常类
class VisionServiceError(Exception):
    """VLM 调用最终失败（超时/5xx，2次均失败）"""
    pass

class ImageExpiredError(Exception):
    """upload_id 对应的图片已过期或不存在"""
    pass

class ImageAccessDeniedError(Exception):
    """upload_id 存在但 user_id 不匹配"""
    pass

# 存储接口（同步）
def store_upload(image_bytes: bytes, user_id: int) -> str:
    """
    将图片字节存入进程内临时存储，返回 upload_id（UUID4 字符串）。
    
    前置检查：
    - 当前总存储量 + len(image_bytes) > VISION_UPLOAD_MAX_TOTAL_MB * 1024 * 1024
      → raise StorageCapacityError（由 views_chat_image 转换为 503）
    
    存储结构（进程内 dict，模块级变量）：
    _upload_store: dict[str, UploadEntry]
    UploadEntry = {
        "user_id": int,
        "bytes": bytes,
        "expire_at": datetime (UTC),
        "size": int
    }
    
    TTL：expire_at = utcnow() + timedelta(seconds=VISION_UPLOAD_TTL)
    _total_size 计数器同步更新（+= len(image_bytes)）
    
    返回：upload_id (str, UUID4 格式)
    日志：INFO - upload_id, user_id, size（不含图片内容）
    """

def get_upload(upload_id: str, user_id: int) -> bytes:
    """
    从临时存储取回图片字节。
    
    - upload_id 不在 _upload_store 中 → raise ImageExpiredError
    - entry["expire_at"] < utcnow() → 惰性清理该条目，raise ImageExpiredError
    - entry["user_id"] != user_id → raise ImageAccessDeniedError
    - 成功取回后不从存储中删除（TTL 惰性清理，允许同一 upload_id 在 TTL 内多次取用）
    
    返回：bytes（图片原始字节）
    """

def check_capacity() -> bool:
    """
    返回 True 表示有剩余容量可接受新上传；False 表示已满（≥ 50MB 上限）。
    同时执行惰性过期清理（清理已过期条目，释放计数）。
    """

def delete_upload(upload_id: str) -> None:
    """
    手动删除指定 upload_id（VLM 调用完成后释放，可选调用）。
    若不存在或已过期，静默忽略。
    """

# VLM 分析接口（异步）
async def analyze_image(image_bytes: bytes, user_text: str) -> str:
    """
    调用 doubao-vision VLM 分析图片，返回文字描述。
    
    调用参数：
    - model: settings.DOUBAO_VISION_MODEL（默认 doubao-vision-lite）
    - base_url: settings.DOUBAO_VISION_BASE_URL（火山方舟 endpoint）
    - api_key: settings.DOUBAO_API_KEY
    - messages: [{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,<b64>"}},{"type":"text","text":user_text or "请描述这张图片"}]}]
    
    超时与重试：
    - 单次调用 asyncio.timeout(settings.DOUBAO_VISION_TIMEOUT)（默认 30s）
    - 超时/5xx 时等待 2s（指数退避起始值），重试 1 次（最多重试次数 settings.DOUBAO_VISION_MAX_RETRIES，默认 1）
    - 4xx 不重试
    - 2 次均失败 → raise VisionServiceError
    
    内存管理：
    - base64 编码字符串在 payload 构造完成后不另存引用
    - 调用完成后 image_bytes 引用由调用方（adapter）负责释放（不在本函数中持有）
    
    可观测性（REQ-NFR-005）：
    - 调用开始 → INFO: "vision_analyze start user_id={uid} size={size}bytes"
    - 调用成功 → INFO: "vision_analyze success elapsed={elapsed:.2f}s"
    - 超时重试 → WARNING: "vision_analyze timeout attempt={n} elapsed={elapsed:.2f}s, retrying"
    - 最终失败 → ERROR: "vision_analyze failed after {n} attempts: {error_type}"
    
    返回：VLM 描述文字（str），非空
    日志约束：绝不记录 image_bytes、base64 字符串或 API key
    """
```

**进程内存储实现细节**：

```
模块级状态（非类，简单全局变量）：
_upload_store: dict[str, UploadEntry] = {}
_total_size: int = 0  # 字节数累计
_store_lock: asyncio.Lock（或 threading.Lock，根据 consumers 异步环境选择）

配置读取（来自 Django settings，在模块 import 时读取一次）：
VISION_UPLOAD_TTL = getattr(settings, 'VISION_UPLOAD_TTL', 600)  # 秒
VISION_UPLOAD_MAX_TOTAL_MB = getattr(settings, 'VISION_UPLOAD_MAX_TOTAL_MB', 50)  # MB

注意：store_upload/get_upload 被 WS consumer（async）和 REST view（sync）调用，
实现时需确保线程安全。推荐使用 threading.Lock（ASGI 环境下 Daphne/Uvicorn 单线程
消费 coroutine 时安全，但 REST 视图可能在 sync 线程池中运行）。
```

**依赖模块**：
- 无内部模块依赖

**外部依赖**：
- `openai` SDK（`AsyncOpenAI`，通过 openai-compatible 端点调用 doubao-vision）
- `django.conf.settings`（读取 VLM 配置）
- Python 标准库：`uuid`、`datetime`、`asyncio`、`base64`、`threading`、`logging`

---

### MOD-MQ-04：WS 消费者扩展（consumers）

**文件**：`FreeArkWeb/backend/freearkweb/api/consumers.py`（修改）

**职责**：扩展 ChatConsumer 以支持图文混合消息——读取 upload_id、注入纯图片默认文案、发送 vision_progress 进度通知、捕获 VisionServiceError/ImageExpiredError 并发送降级 WS 消息、持久化增强消息（含 VLM 描述前缀）。

**覆盖需求**：REQ-FUNC-003、REQ-FUNC-006、REQ-FUNC-007、REQ-NFR-004

**接口变更（现有函数签名扩展）**：

```python
# receive 扩展（现有方法，新增 upload_id 读取）
async def receive(self, text_data: str) -> None:
    data = json.loads(text_data)
    user_message = data.get('message', '').strip()
    upload_id = data.get('image_upload_id')  # 新增读取
    
    # upload_id 格式校验（若存在）
    if upload_id is not None:
        if not _is_valid_uuid(upload_id):
            await self._send_error("IMAGE_INVALID", "图片引用无效")
            return
    
    # 纯图片消息默认文案注入（OQ-MQ-003）
    if upload_id and not user_message:
        user_message = "请帮我分析这张图片"
    
    await self._handle_chat(user_message, upload_id=upload_id)

# _handle_chat 扩展（新增 upload_id 参数）
async def _handle_chat(self, user_message: str, upload_id: str | None = None) -> None:
    """
    新增逻辑（在调用 adapter.stream_chat 前）：
    1. 若 upload_id 非空，调用 vision_service.get_upload(upload_id, self.user.id)
       - ImageExpiredError → await self._send_error("IMAGE_EXPIRED", "图片已过期，请重新上传"); return
       - ImageAccessDeniedError → await self._send_error("IMAGE_INVALID", "图片引用无效"); return
    2. 若 upload_id 非空，发送 vision_progress：
       await self.send(json.dumps({"type":"vision_progress","message":"正在分析图片，请稍候…"}))
    3. 调用 adapter.stream_chat(message=user_message, session_key=..., upload_id=upload_id)
       注意：image_bytes 的传递通过 upload_id 延迟到 adapter 层（adapter 再次调用 get_upload）
       原因：降低 consumers 与 vision_service 的耦合（consumers 只做 TTL 检查，不传 bytes）
    4. 捕获 VisionServiceError：
       await self._send_error("IMAGE_ANALYSIS_FAILED",
           "图片分析暂时不可用，您可以用文字描述图片内容后重试")
       self._is_streaming = False; return
    
    持久化变更：
    - adapter.stream_chat 完成后，获取 enhanced_message（含 VLM 前缀的完整文字）
    - chat_memory.append_message(self.chat_session, 'user', enhanced_message)
      （enhanced_message 由 adapter 返回，格式：[图片描述：<VLM输出>] <原始文字>）
    - 若无图片：enhanced_message = user_message（行为与 v1.4.x 完全一致）
    """

# 新增辅助方法
async def _send_error(self, code: str, message: str) -> None:
    await self.send(json.dumps({"type": "error", "code": code, "message": message}))

def _is_valid_uuid(value: str) -> bool:
    """校验字符串是否为合法 UUID4 格式"""

# _pump 扩展（新增 vision_progress kind 透传）
async def _pump(self, generator) -> str:
    """
    现有 _pump 处理 reasoning_token / stream_token / stream_end。
    新增：若收到 kind="vision_progress" 事件（adapter 产生），透传给前端。
    注意：vision_progress 实际由 _handle_chat 在调用 adapter 前发送，
    _pump 不需额外处理，此处备注以说明 kind 的来源。
    """
```

**adapter.stream_chat 返回值约定**（与 MOD-MQ-05 联合设计）：

```
adapter.stream_chat 改为返回 (enhanced_message: str) 或通过参数回传，
供 consumers 在 append_message 时使用。
实现选择：推荐 adapter.stream_chat 改为 async generator，最后 yield 一个
{"kind": "enhanced_message", "content": enhanced_message} 事件；
consumers._pump 识别该 kind 后记录 enhanced_message，不发送给前端。
```

**依赖模块**：
- MOD-MQ-03（`vision_service.get_upload`，仅 TTL 校验）
- MOD-MQ-05（`adapter.stream_chat` 签名扩展）

---

### MOD-MQ-05：LangGraph 适配器扩展（adapter）

**文件**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/adapter.py`（修改）

**职责**：`stream_chat` 签名扩展以接受 `upload_id`；在启动 `graph.astream` 前完成 VLM 调用并构建增强消息；向 consumers 回传 enhanced_message（用于持久化）。

**覆盖需求**：REQ-FUNC-004、REQ-FUNC-005、ADR-MQ-001（VLM 外置调用位置）

**接口变更**：

```python
# stream_chat 签名扩展
async def stream_chat(
    self,
    message: str,
    session_key: str,
    upload_id: str | None = None
) -> AsyncGenerator[dict, None]:
    """
    扩展逻辑（仅当 upload_id 非空时执行）：
    
    1. image_bytes = vision_service.get_upload(upload_id, self.user_id)
       - 若 ImageExpiredError/ImageAccessDeniedError → re-raise（由 consumers 捕获）
    
    2. description = await vision_service.analyze_image(image_bytes, message)
       - 若 VisionServiceError → re-raise（由 consumers 捕获）
       - analyze_image 调用完成后，本函数不再持有 image_bytes 引用：
         del image_bytes（显式释放，满足 REQ-NFR-002 内存约束）
    
    3. enhanced_message = f"[用户图片分析：{description}]\n\n{message}"
       注意：此格式用于 graph 内部（供 _route/_fan_out/_expert 使用）
    
    4. 持久化用格式（略有不同，前缀为「图片描述」供前端检测含图标注）：
       persist_message = f"[图片描述：{description}] {message}"
       → yield {"kind": "enhanced_message", "content": persist_message}（最后 yield）
    
    5. 若 upload_id 为空：enhanced_message = message（不变）
    
    6. 构建 HumanMessage(content=enhanced_message)（content 永远是 str，C-006）
    
    7. 启动 graph.astream(
          {"messages": [HumanMessage(content=enhanced_message)],
           "name": ..., "query": enhanced_message,
           "vision_description": description if upload_id else None},
          config={"configurable": {"thread_id": session_key}}
       )
    
    8. 通过 _drive(generator) yield 所有流式事件给 consumers（现有逻辑不变）
    
    backward compatibility：
    - 不含 upload_id 的调用行为与 v1.4.x 完全一致（upload_id=None 默认值）
    """
```

**依赖模块**：
- MOD-MQ-03（`vision_service.get_upload`、`vision_service.analyze_image`）
- MOD-MQ-06（orchestrator State 新增 `vision_description` 字段）

---

### MOD-MQ-06：LangGraph 编排图扩展（orchestrator）

**文件**：`FreeArkWeb/backend/freearkweb/api/langgraph_chat/orchestrator.py`（最小修改）

**职责**：State TypedDict 新增 `vision_description` 字段，记录 VLM 描述文字（用于调试/观测）；其余节点逻辑、图结构、边定义均不变。

**覆盖需求**：REQ-FUNC-005

**接口变更**：

```python
# State TypedDict 扩展（唯一变更）
class State(TypedDict):
    messages: list          # 现有字段，不变
    plan: list              # 现有字段，不变
    expert_results: dict    # 现有字段，不变
    name: str               # 现有字段，不变
    query: str              # 现有字段，不变
    related_images: list    # 现有字段（v1.4.1 新增），不变
    vision_description: Optional[str]  # 新增字段，默认 None

# 注意：
# - _route、_fan_out、_expert 均不需要修改
# - _fan_out 生成 plan=[(name, query)] 时，query 已是 enhanced_message（adapter 传入），
#   天然携带 VLM 前缀，无需额外处理
# - vision_description 字段仅作为状态记录，各节点可忽略（Optional[str]）
```

**依赖模块**：无（图结构不变，无新依赖）

---

### MOD-MQ-07：配置与路由扩展

**文件**：
- `FreeArkWeb/backend/freearkweb/freearkweb/settings.py`（修改）
- `.env`（修改，不入 git）
- `FreeArkWeb/backend/freearkweb/api/urls.py`（修改）

**职责**：新增 VLM 相关配置变量（含注释）、注册图片预上传 REST 路由。

**覆盖需求**：REQ-NFR-006（可维护性，settings 变量须有注释）

**配置变量清单**：

```python
# settings.py 新增配置（每项须有注释，REQ-NFR-006）

# doubao-vision VLM 模型名称，默认 doubao-vision-lite；可切换为 doubao-vision-pro，无需改代码
DOUBAO_VISION_MODEL = env('DOUBAO_VISION_MODEL', default='doubao-vision-lite-32k')

# doubao-vision API 端点（火山方舟 openai-compatible endpoint）
# 与 rag_service._DoubaoMultimodalEmbeddings 使用相同账号/网络，已打通
DOUBAO_VISION_BASE_URL = env('DOUBAO_VISION_BASE_URL', default='https://ark.cn-beijing.volces.com/api/v3')

# doubao-vision API Key，仅从 .env 读取，绝不入 git 或日志
DOUBAO_API_KEY = env('DOUBAO_API_KEY', default='')

# doubao-vision 单次调用超时（秒），实测偶发 >15s，建议 30s
DOUBAO_VISION_TIMEOUT = env.int('DOUBAO_VISION_TIMEOUT', default=30)

# doubao-vision 最大重试次数（首次失败后重试，超时/5xx 触发）
DOUBAO_VISION_MAX_RETRIES = env.int('DOUBAO_VISION_MAX_RETRIES', default=1)

# 临时图片存储 TTL（秒），默认 10 分钟
VISION_UPLOAD_TTL = env.int('VISION_UPLOAD_TTL', default=600)

# 进程内临时图片存储总上限（MB），超过则拒绝新上传
VISION_UPLOAD_MAX_TOTAL_MB = env.int('VISION_UPLOAD_MAX_TOTAL_MB', default=50)
```

**.env 新增变量（示例，注意不入 git）**：

```
DOUBAO_VISION_MODEL=doubao-vision-lite-32k
DOUBAO_VISION_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_API_KEY=<实际密钥>
DOUBAO_VISION_TIMEOUT=30
DOUBAO_VISION_MAX_RETRIES=1
VISION_UPLOAD_TTL=600
VISION_UPLOAD_MAX_TOTAL_MB=50
```

**路由注册（urls.py 新增）**：

```python
# api/urls.py 新增（在现有 urlpatterns 列表中追加）
from api.views_chat_image import ChatImageUploadView

urlpatterns = [
    # ... 现有路由 ...
    path('chat/image-upload/', ChatImageUploadView.as_view(), name='chat-image-upload'),
]
```

---

## 3. 模块依赖关系图

```
[MOD-MQ-01 前端多模态输入]
  │
  ├── REST: POST /api/chat/image-upload/ ──→ [MOD-MQ-02 图片预上传 REST 视图]
  │                                               │
  │                                               └── store_upload() ──→ [MOD-MQ-03 vision_service]
  │
  └── WS: chat_message (with image_upload_id) ──→ [MOD-MQ-04 consumers 扩展]
                                                        │
                                                        ├── get_upload() ──→ [MOD-MQ-03 vision_service]
                                                        │   (TTL 校验，失败则发 IMAGE_EXPIRED 错误)
                                                        │
                                                        └── stream_chat(upload_id) ──→ [MOD-MQ-05 adapter 扩展]
                                                                                           │
                                                                                           ├── get_upload() ──→ [MOD-MQ-03]
                                                                                           │   (取图片字节)
                                                                                           │
                                                                                           ├── analyze_image() ──→ [MOD-MQ-03]
                                                                                           │   (VLM 调用，doubao-vision API)
                                                                                           │
                                                                                           └── graph.astream() ──→ [MOD-MQ-06 orchestrator 扩展]
                                                                                                                      (State.vision_description)

[MOD-MQ-07 配置+路由]
  └── 被 MOD-MQ-02、MOD-MQ-03 读取（settings.DOUBAO_VISION_*）
  └── urls.py 注册 MOD-MQ-02 端点路由

[外部服务]
  doubao-vision API（火山方舟）← 被 MOD-MQ-03 analyze_image() 调用
```

**循环依赖检查**：
- MOD-MQ-01 → MOD-MQ-02 → MOD-MQ-03（单向）
- MOD-MQ-01 → MOD-MQ-04 → MOD-MQ-03（单向）
- MOD-MQ-04 → MOD-MQ-05 → MOD-MQ-03（单向）
- MOD-MQ-05 → MOD-MQ-06（单向）
- **结论：无循环依赖，已验证。**

---

## 4. 数据库变更说明

### 4.1 migration 0040 决策

根据 ADR-MQ-002（临时图片存储采用进程内 dict），**临时图片上传记录不写入数据库**，因此：

- **`api/migrations/0040_chat_image_upload.py` 不需要创建**。
- 进程内 dict 完全自包含，TTL 后自动清理，无 DB 痕迹。

### 4.2 现有 DB 表变更

| 表名 | 变更内容 | 说明 |
|------|---------|------|
| `api_chat_session`（现有）| 无结构变更 | messages 历史字段存储内容会出现 `[图片描述：...]` 前缀文字（内容变化，无结构变化）|
| 其他所有表 | 无变更 | — |

**结论**：本版本无新增 migration，无需 `python manage.py migrate`。

---

## 5. REQ-FUNC-* 覆盖矩阵（完整映射）

| 需求 ID | 覆盖模块 | 覆盖方式 |
|---------|---------|---------|
| REQ-FUNC-001 | MOD-MQ-01 | ChatView.vue 图片选择、校验、压缩、预览、删除逻辑 |
| REQ-FUNC-002 | MOD-MQ-02 + MOD-MQ-03 | views_chat_image.py 接收上传 + vision_service.store_upload 存储 |
| REQ-FUNC-003 | MOD-MQ-01 + MOD-MQ-04 | 前端 WS 帧携带 upload_id；consumers.receive 读取并校验 |
| REQ-FUNC-004 | MOD-MQ-03 + MOD-MQ-05 | vision_service.analyze_image VLM 调用；adapter 触发调用并注入前缀 |
| REQ-FUNC-005 | MOD-MQ-05 + MOD-MQ-06 | adapter 构建 enhanced_message 并注入 State；orchestrator.query 天然携带 VLM 前缀 |
| REQ-FUNC-006 | MOD-MQ-03 + MOD-MQ-04 | VisionServiceError 定义在 vision_service；consumers 捕获并发降级 WS 消息 |
| REQ-FUNC-007 | MOD-MQ-04 + MOD-MQ-05 | adapter 回传 persist_message；consumers.append_message 存含 VLM 描述的增强文字 |
| REQ-FUNC-008 | MOD-MQ-01 | ChatView.vue 检测消息前缀 `[图片描述：` 渲染「含图」标注，不挂 img 标签 |

**结论：REQ-FUNC-001 ~ REQ-FUNC-008 全部覆盖，无遗漏。**

---

*文档状态：DRAFT（2026-06-24）。待 PM 门控通过后更新为 APPROVED。*
