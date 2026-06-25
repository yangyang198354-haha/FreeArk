**特性**：多图提问——最多5张图片批量上传与分析（Multi-Image Question）
**版本**：v1.9.0_multi_image_question
**状态**：DRAFT
**日期**：2026-06-24
**作者**：system-architect
**依赖**：
- `docs/requirements/v1.9.0_multi_image_question/requirements_spec.md` (APPROVED，用户确认)
- `docs/architecture/v1.9.0_multi_image_question/architecture_design.md` (DRAFT)
- `docs/architecture/v1.5.0_multimodal_question/tech_stack.md` (DRAFT，基线，本文档增量于其上)

---

# 技术选型文档 — v1.9.0 多图提问（基于 v1.5.0 增量）

**文档编号**：ARCH-TECH-MI-v160-001
**项目名称**：FreeArk 方舟智能体多图提问（v1.9.0_multi_image_question）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-24

---

## 1. 版本说明

本文档为增量文档，仅记录相对于 v1.5.0 `tech_stack.md` 的**新增、变更项**。v1.5.0 已选定且本版本无变化的技术（openai SDK、asyncio.timeout、doubao-vision-lite-32k、Canvas API、python-magic、进程内 dict 存储、DRF、Django Channels、LangGraph 等）不重复记录。

v1.5.0 基线文档路径：`docs/architecture/v1.5.0_multimodal_question/tech_stack.md`

---

## 2. 技术选型表（v1.9.0 新增/变更项）

### 2.1 VLM 并发调用层（v1.9.0 新增）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| 多图 VLM 并发调用 | `asyncio.gather(return_exceptions=True)` | Python 3.11 标准库 | ADR-MI-001 选定逐图独立调用方案；`asyncio.gather` 并发执行多个 `analyze_image` 协程，总耗时 ≈ 最慢一张而非 N 倍；`return_exceptions=True` 天然实现部分失败语义（失败图返回 Exception 对象而非中断整批），直接满足 REQ-MI-007（OQ-MI-001 方案A）；Pi 5 单 worker asyncio 事件循环天然支持，无额外依赖 | REQ-MI-004、REQ-MI-007、REQ-MI-NFR | 中。Pi 5 并发发出5个 VLM HTTP 请求；豆包火山方舟账号若有并发配额限制（如并发1）会触发 429；缓解：开发阶段验证账号配额，若受限则改用 asyncio.Semaphore 限制并发数 [OQ-MI-006] | 不引入任何新包；`asyncio.gather` 为 Python 内置；与现有 `asyncio.timeout` 组合使用 |
| 整体 VLM 批处理超时 | `asyncio.timeout(VISION_BATCH_TIMEOUT_SECONDS)` | Python 3.11 标准库 | RISK-MI-002：串行5张×30s极端情形=150s；并发时取最慢一张但仍需上限保护；整体90s上限（P90目标内）通过 `asyncio.timeout(90)` 包裹 `analyze_images_batch` 整个调用实现 | REQ-MI-NFR（RISK-MI-002 缓解）| 低。timeout 行为已在 v1.5.0 单图场景验证（[KE-ARCH-007]）；90s 超时后走全失败降级路径（IMAGE_ANALYSIS_FAILED）| 新增 Django settings 变量 `VISION_BATCH_TIMEOUT_SECONDS`（默认90），可按需调整 |

### 2.2 前端并发上传（v1.9.0 新增）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| 前端并发 POST | `Promise.allSettled` | Web 标准（ES2020，无版本）| ADR-MI-002 选定并发上传方案；`Promise.allSettled`（优于 `Promise.all`）：任一图片上传失败时不中断其余，收集成功的 upload_id，失败的图片 UI 提示用户移除——与后端容错精神（OQ-MI-001 方案A）一致；Pi 5 局域网并发5个 POST 总耗时 ≈ 单张（~100~200ms），比串行5张（~500~1000ms）快约4倍 | REQ-MI-001、REQ-MI-NFR（UX 等待时间）| 低。`Promise.allSettled` 兼容所有现代浏览器（Chrome 76+、Firefox 71+、Safari 13+）；Pi 5 单 worker ASGI 支持并发 POST；`store_upload` 有 `threading.Lock` 保护（v1.5.0 已有）| 无需引入任何 npm 包；现有 `uploadChatImage` 函数不变，`uploadChatImages` 是其 allSettled 包装 |
| 前端多图 state 管理 | Vue 3 响应式（`ref<Array>`）| Vue 3 现有版本 | 将 v1.5.0 的单图 `selectedImageBlob: Ref<Blob\|null>` 替换为 `selectedImages: Ref<Array<{blob, previewDataURL}>>`；Vue 3 响应式数组天然支持 push/splice/watch，无需额外状态管理库；现有 ChatView.vue 已使用 Vue 3 Composition API | REQ-MI-001 | 低 | 无新 npm 包；现有 Vue 3 Composition API 完全支持 |

### 2.3 WS 协议层（v1.9.0 变更）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| WS 多图字段协议 | `image_upload_ids: list[str]`（JSON 数组）| WS 应用层协议扩展 | ADR-MI-003 选定新字段与旧字段共存方案；JSON 原生支持数组类型，无额外序列化需求；旧字段 `image_upload_id`（字符串）继续支持，消费者 if-elif 分支解析，零额外依赖 | REQ-MI-003 | 低。JSON 数组序列化已被所有客户端支持；向后兼容性通过旧字段兜底保证 | 无代码框架变更，仅新增字段名 |
| 多图进度通知 kind | `'vision_progress'` WS 消息（内容变更）| 自定义应用协议 | v1.5.0 已有 `vision_progress` kind，v1.9.0 扩展 `message` 字段内容为"正在分析第N/T张图片…"；前端直接显示 `message` 文字，无需前端版本更新即可展示多图进度（向后兼容）| REQ-MI-NFR（每张图前发 progress 帧）| 低 | kind 不变，仅 message 内容变化；前端无需修改 case 分支 |
| 部分失败 kind | `'image_analysis_partial'`（新增内部 kind）| 自定义内部协议（adapter→consumers）| adapter 通过此 kind 通知 consumers 有部分失败，consumers 转换为 `IMAGE_ANALYSIS_PARTIAL` WS 错误帧；与 `persist_enhanced_message` kind 设计模式一致（v1.5.0 已有先例）；消费者 `_pump` 识别后发非阻塞通知，不中断 stream | REQ-MI-009（IMAGE_ANALYSIS_PARTIAL）| 低 | 仅在 adapter→consumers 内部传递，不暴露给前端（前端只收标准 WS 错误帧）|

---

## 3. 依赖变更清单（v1.9.0 增量）

### 3.1 无新增包安装

v1.9.0 所有新功能均通过 Python 标准库（asyncio.gather、asyncio.timeout、asyncio.Queue）和现有 npm/pip 包实现，**无需新安装任何依赖**。

| 复用来源 | 具体 API | 用途 | 关联模块 |
|---------|---------|------|---------|
| Python 3.11 标准库 | `asyncio.gather(return_exceptions=True)` | 多图 VLM 并发调用 | MOD-MI-03 |
| Python 3.11 标准库 | `asyncio.timeout(90)` | 整体批处理超时 | MOD-MI-03 |
| Python 3.11 标准库 | `asyncio.Queue` | progress_cb 与 stream_chat async generator 协调 | MOD-MI-05 |
| Python 3.11 标准库 | `asyncio.create_task` | 将 analyze_images_batch 作为独立 task 运行 | MOD-MI-05 |
| Web 标准（无 npm）| `Promise.allSettled` | 前端并发上传 | MOD-MI-01 |
| Web 标准（无 npm）| `Array`（Vue 3 ref）| 前端多图 state | MOD-MI-01 |

### 3.2 v1.5.0 依赖（不变，继续使用）

v1.9.0 继承 v1.5.0 的全部依赖，无任何版本变更或新增。参见 `docs/architecture/v1.5.0_multimodal_question/tech_stack.md` 第 3 节。

---

## 4. asyncio.gather 用于多图 VLM 并发 — 技术决策记录

本节记录 ADR-MI-001 选定 asyncio.gather 的技术要点，供开发实现参考。

### 4.1 调用形式

```
asyncio.gather 用于多图 VLM 并发（ADR-MI-001 选定方案）

调用签名（逻辑描述，非代码）：
  results = await asyncio.gather(
      *[analyze_image_task(i, img) for i, img in enumerate(image_bytes_list)],
      return_exceptions=True
  )
  # 每个元素为成功描述字符串（str）或 Exception 对象（失败）
  # return_exceptions=True 保证部分失败不中断整批（REQ-MI-007 容错语义）

整体超时包裹：
  async with asyncio.timeout(VISION_BATCH_TIMEOUT_SECONDS):
      results = await asyncio.gather(...)
  # 超时时所有并发任务被取消，抛出 asyncio.TimeoutError
  # adapter 捕获后 raise VisionServiceError（全失败降级路径，Level 4）
```

### 4.2 内存安全

Pi 5 并发时5张图片 base64 编码同时存在于内存：
- 每张图 `_downscale_for_vlm` 后通常 ≤2MB（最长边 ≤1536px，JPEG quality=85）
- 5张并发：base64 编码字节约 5 × 2MB × 4/3 ≈ 13MB（base64 膨胀约1.33倍）
- 加上 image_bytes_list 原始字节约 10MB，峰值约 23MB
- 远低于50MB上限（ADR-MQ-002），Pi 5 内存（8GB）裕量充足

### 4.3 与 vision_progress 帧的时序协调

asyncio.gather 并发启动时，多个协程几乎同时开始，导致 progress 帧（"正在分析第N/T张..."）可能近乎同时发出，而非严格串行的"第1张→完成→第2张→..."时序。

**接受此权衡的理由**（关联 ADR-MI-001）：
1. NEP（Non-functional Expectation）约束仅要求 ">10s 须显示进度"，并未要求严格串行时序。
2. 近乎同时的多帧 progress 前端收到后依次更新显示文字，最终显示"正在分析第5/5张..."，用户感知为"正在处理全部5张"，UX 可接受。
3. 若 PM 要求严格串行显示，可改为串行 for 循环（牺牲并发收益），通过 `VISION_BATCH_TIMEOUT_SECONDS` 配置保护整体超时。

### 4.4 豆包账号并发配额问题（OQ-MI-006）

若火山方舟 doubao-vision 账号有并发请求配额限制，asyncio.gather 同时发出5个请求可能触发 429 Too Many Requests。

缓解方案（开发阶段需验证后选择）：
- 方案A：asyncio.Semaphore(N) 限制最大并发数（N=1 退化为串行，N=2~3 折中）
- 方案B：串行 for 循环（最保守，总耗时约 N×单图耗时，但确保不触发 429）

选择权在开发阶段实测后确定，架构上两方案均兼容现有设计（仅 `analyze_images_batch` 内部实现差异，接口不变）。

---

## 5. 技术风险汇总（v1.9.0 新增项）

| 风险级别 | 风险描述 | 来源 | 缓解措施 |
|---------|---------|------|---------|
| **High** | doubao-vision 账号并发配额限制，5张并发发出5个 VLM 请求可能触发 429（OQ-MI-006）| ADR-MI-001 并发方案 | 开发阶段验证账号配额；若有限制则改用 asyncio.Semaphore(1) 串行，无接口变更 |
| **Medium** | 5张并发 VLM 调用，整体超时90s与单张30s×1次重试的关系：若5张都慢（各25s），并发时总耗时25s << 90s，安全；若5张都触发重试（各2×30s+2s退避），总耗时约62s，仍 < 90s；边界情形可接受 | RISK-MI-002 | asyncio.timeout(90) 兜底；vision_progress 帧消除用户焦虑 |
| **Medium** | 部分失败占位文字 `[用户图片N分析：图片分析失败，已跳过]` 可能引发 LLM 在回答中提及"图N无法分析"，影响答复质量 | ADR-MI-004 后果 | 专家 system prompt 可增加"遇到图片分析失败的占位标注时，无需向用户提及，直接基于可用信息作答"；此为提示工程优化，不影响架构 |
| **Low** | 前端并发5个 POST（Promise.allSettled）可能因 Pi 5 单 worker 消费队列延迟导致某张超时失败 | ADR-MI-002 | ASGI uvicorn 单 worker 可并发处理多个 HTTP 请求（asyncio 事件循环）；store_upload 为同步 + threading.Lock，每次锁占用 <1ms，无实际阻塞 |
| **Low** | asyncio.Queue 实现 progress_cb 与 async generator 协调，若 task 提前完成而 queue 未清空可能遗漏 progress 帧 | MOD-MI-05 实现细节 | 实现时在 task.done() 检查后加 `while not progress_queue.empty(): yield ...` 确保清空；或在 analyze_images_batch 完成后等待所有 progress 帧发出 |

**继承 v1.5.0 风险**（参见 v1.5.0 tech_stack.md 第 5 节，v1.9.0 无新变化）：
- python-magic libmagic1 依赖（High，v1.5.0 已记录）
- doubao-vision-lite 识别效果（Medium，v1.5.0 已记录）
- Pi WiFi 抖动导致单次 VLM >15s（Medium，v1.5.0 已记录）
- 图片字节意外进入日志（Low，v1.5.0 已记录）

---

## 6. 不引入的技术（v1.9.0 补充）

| 排除技术 | 排除原因 |
|---------|---------|
| doubao-vision 多图 batch API | 未验证 doubao-vision API 是否支持单次请求多图；且一次失败=全失败，不满足 REQ-MI-007 容错语义（ADR-MI-001）|
| `asyncio.Semaphore` | 默认方案直接使用 asyncio.gather 并发；若账号有并发配额再引入（OQ-MI-006 后置决策）|
| Celery / 任务队列 | 多图 VLM 批处理在 asyncio 协程内完成，90s 整体超时已足够；无需引入 Celery 增加复杂度（Pi 5 单 worker，REQ-MI-NFR）|
| Redis 多图缓存 | 沿用进程内 dict（ADR-MQ-002），各 upload_id 独立存储，无需 Redis |
| WebSocket 二进制帧（传图片字节）| 继承 v1.5.0 SC-001 硬约束：base64/图片字节不进 WS 帧 [KE-ARCH-009] |

---

## 7. settings.py 新增配置变量（v1.9.0 新增）

| 变量名 | 默认值 | 类型 | 用途 | 来源需求 |
|--------|--------|------|------|---------|
| `VISION_BATCH_TIMEOUT_SECONDS` | `90` | int | 多图 VLM 批处理整体超时上限（秒），覆盖 RISK-MI-002 极端情形 | RISK-MI-002（整体 VLM 处理总计 ≤90s）|

读取方式（在 `vision_service._get_vision_config()` 中扩展）：

```
# 逻辑描述（非代码）
"batch_timeout": getattr(settings, "VISION_BATCH_TIMEOUT_SECONDS", 90)
```

v1.5.0 已有配置变量不变（`DOUBAO_VISION_MODEL`、`DOUBAO_VISION_BASE_URL`、`DOUBAO_API_KEY`、`DOUBAO_VISION_TIMEOUT`、`DOUBAO_VISION_MAX_RETRIES`、`VISION_UPLOAD_TTL`、`VISION_UPLOAD_MAX_TOTAL_MB`）。

---

*文档状态：DRAFT（2026-06-24）。基于 v1.5.0 增量，待 PM 门控通过后更新为 APPROVED。*
