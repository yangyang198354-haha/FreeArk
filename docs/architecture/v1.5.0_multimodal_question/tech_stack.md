**特性**：多模态提问——用户图片输入与豆包视觉模型理解（Image Question Input）
**版本**：v1.5.0_multimodal_question
**状态**：DRAFT
**日期**：2026-06-24
**作者**：system-architect
**依赖**：requirements_spec.md (APPROVED), user_stories.md (APPROVED), architecture_design.md (DRAFT)

---

# 技术选型文档 — v1.5.0 多模态提问

**文档编号**：ARCH-TECH-MQ-v150-001
**项目名称**：FreeArk 方舟智能体多模态提问（v1.5.0_multimodal_question）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-24

---

## 1. 技术选型总览

本版本技术选型原则：
1. **优先复用现有栈**：凡现有代码已引入的库，不重复安装，直接复用。
2. **最小新增原则**：新增依赖必须有明确的功能缺口对应，且无法用现有库替代。
3. **Pi 5 兼容性**：所有新增依赖须支持 ARM64（Python 包 wheel 或源码编译），与 Raspberry Pi OS（Debian Bookworm）兼容。

---

## 2. 技术选型表

### 2.1 VLM 调用层

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| VLM 接口调用 SDK | `openai` Python SDK | 现有（已在 requirements.txt） | doubao-vision 火山方舟端点暴露 openai-compatible 接口（`/v3/chat/completions`），`openai.AsyncOpenAI` 天然支持 base_url 切换；rag_service 已有完整的豆包 API 调用经验（含超时/退避），避免引入新 SDK 学习成本 | REQ-FUNC-004、C-002 | 低。openai SDK 的 openai-compatible 模式已在 rag_service 实证可用 | 使用 `AsyncOpenAI(base_url=settings.DOUBAO_VISION_BASE_URL, api_key=settings.DOUBAO_API_KEY)`；不引入 volcengine-python-sdk |
| VLM 异步超时控制 | `asyncio.timeout` | Python 3.11+ 标准库 | Pi 5 Raspberry Pi OS Bookworm 预装 Python 3.11，`asyncio.timeout` 是 3.11 新增上下文管理器，替代 `asyncio.wait_for`，语义更清晰；与现有 async consumer 环境一致 | REQ-NFR-001（超时保护）、REQ-NFR-004 | 低。Python 3.11 已稳定，asyncio.timeout 行为明确 | 若运行时为 Python 3.10（旧镜像），改用 `asyncio.wait_for`，逻辑等价 |
| VLM 模型型号（默认） | doubao-vision-lite-32k | 火山方舟当前可用版本 | OQ-MQ-001 已决策：默认 lite，P90 ≤8s；可通过 `DOUBAO_VISION_MODEL` env 切换 pro，无需改代码；lite 在铭牌 OCR + 设备状态描述场景满足 MVP 质量要求 | REQ-FUNC-004、REQ-NFR-001 | 中。doubao-vision-lite 识别复杂工程图纸/手写铭牌效果可能不足（RISK-MQ-003）；缓解：开发阶段真实铭牌样本抽检 | 模型接入点：`https://ark.cn-beijing.volces.com/api/v3`（与 rag_service 使用相同域名/账号） |

### 2.2 图片处理层

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| 客户端图片压缩 | 浏览器原生 Canvas API + Blob API | Web 标准（无版本） | REQ-FUNC-001 要求客户端压缩，避免服务端 CPU 消耗（Pi 5 约束）；Canvas 压缩无需引入 npm 包（减少 bundle 体积）；现代浏览器（Chrome 80+、Firefox 75+、Safari 14+、iOS Safari 14+）均支持 | REQ-FUNC-001、REQ-NFR-002 | 低。Canvas/Blob API 兼容性已成熟；iOS Safari 有少量 API 差异（RISK-MQ-006）；缓解：前端 try/catch 降级为直接上传 | 压缩参数：最大尺寸 1920×1920px，JPEG quality=0.85（OQ-MQ-006 建议值，含图标注可用）|
| 服务端 MIME 类型验证 | `python-magic` | 0.4.x（最新稳定版） | REQ-NFR-003 SC-006 要求基于文件头魔数的 MIME 验证，而非信任 Content-Type 头（可伪造）；python-magic 封装 libmagic，读取文件头识别真实格式 | REQ-NFR-003（SC-006）| 中。python-magic 依赖系统库 `libmagic1`（Debian 包），Pi 5 需要 `sudo apt install libmagic1`；若生产环境未安装则 ImportError；**缓解**：部署文档中明确记录依赖；若不可接受，降级为手动检查文件头魔数字节（见备注） | 备选方案（零依赖）：手动检查文件头 bytes：JPEG=`FF D8 FF`，PNG=`89 50 4E 47`，WebP=`52 49 46 46`。若 python-magic 安装有阻力，可改用手动魔数检查，牺牲 HEIC 支持 |
| 服务端图片处理 | 无（本版本不做服务端压缩/转换） | — | REQ-FUNC-002 只要求存储和转发图片字节；客户端压缩已在前端完成；服务端不需要 Pillow/PIL | — | — | 若未来需要服务端缩略图或格式转换，再引入 Pillow |

### 2.3 临时存储层

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| 进程内临时图片存储 | Python 标准库 `dict` + `datetime` + `threading.Lock` | Python 3.11 标准库 | ADR-MQ-002 决策：进程内 dict 最简单，零依赖；C-008 单 worker 无跨进程共享需求；TTL 惰性清理（get 时判断）实现简单；50MB 上限通过字节计数实现 | REQ-FUNC-002、REQ-NFR-002、REQ-NFR-004 | 低。dict 在单 worker 环境下线程安全（GIL 保护基础操作，Lock 保护复合操作）；重启丢失数据可接受（RISK-MQ-005）| 无需 Django CACHES 配置；也无需 Redis（不跨进程）|

### 2.4 API 与 WS 层（现有，无变更）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| REST 接口框架 | Django REST Framework (DRF) | 现有版本 | 现有体系，`APIView` + `IsAuthenticated` + `MultiPartParser` 完整支持图片上传场景 | REQ-FUNC-002 | 无 | 无变更，复用现有 `TokenAuthentication` |
| WebSocket 消费者 | Django Channels | 现有版本 | 现有体系，ChatConsumer 做最小扩展 | REQ-FUNC-003 | 无 | 无新增 channels 配置 |
| 前端 HTTP 调用 | 现有 `api.js`（`authenticatedFetch` 封装） | 现有 | C-010 硬约束：禁止裸 axios；`uploadChatImage` 函数通过 `authenticatedFetch` 调用，确保 Bearer Token 自动附加 | REQ-FUNC-002（客户端）、REQ-NFR-003 SC-004 | 低 | 参考 freeark-frontend-bare-axios-session-trap 历史教训 |

### 2.5 LangGraph 编排层（现有，最小变更）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|-----------|-----------|-----------|------|------|
| LangGraph 编排框架 | LangGraph | 现有版本（生产已运行）| ADR-MQ-001 决策：VLM 外置调用，图结构不变；只在 State 新增 `vision_description` 字段 | REQ-FUNC-005 | 低。State 新增可选字段不影响现有节点 | C-005：不可回退 OpenClaw，LangGraph 是唯一选择 |
| LangChain OpenAI 适配器 | `langchain_openai.ChatOpenAI` | 现有版本 | 现有 deepseek 主模型调用使用此适配器，不变 | REQ-FUNC-005 | 无 | VLM 调用（doubao-vision）不经 LangChain，直接用 openai SDK 的 AsyncOpenAI |

---

## 3. 依赖变更清单

### 3.1 确认需要新安装的包

| 包名 | 版本约束 | 安装理由 | Pi 5 兼容性 | 安装命令 |
|------|---------|---------|------------|---------|
| `python-magic` | `>=0.4.27` | MIME 白名单验证（REQ-NFR-003 SC-006），读文件头魔数 | 需要系统库 `libmagic1`；ARM64 支持良好（Debian 官方包）| `apt install libmagic1` + `pip install python-magic` |

**备注**：若 `libmagic1` 安装存在阻力（生产环境管理限制），可降级为手动魔数字节检查（在 `views_chat_image.py` 中实现，读文件头前 12 字节匹配 JPEG/PNG/WebP 特征），**无需安装任何新包**。HEIC/HEIF 格式在手动检查方案中需放宽为前端校验。

### 3.2 现有包（无需新安装，直接复用）

| 包名 | 当前版本（参考）| 复用方式 | 关联模块 |
|------|---------------|---------|---------|
| `openai` | 现有版本（已在 requirements.txt）| `AsyncOpenAI` 调用 doubao-vision endpoint | MOD-MQ-03 |
| `langchain_openai` | 现有版本 | 现有主模型调用，不变 | MOD-MQ-05/06 |
| `djangorestframework` | 现有版本 | `APIView`、`IsAuthenticated`、`MultiPartParser` | MOD-MQ-02 |
| `channels` | 现有版本 | ChatConsumer | MOD-MQ-04 |
| Python 标准库（`uuid`, `datetime`, `asyncio`, `threading`, `base64`, `logging`）| Python 3.11 内置 | vision_service.py 全部实现所需 | MOD-MQ-03 |

---

## 4. doubao-vision API 调用方式说明

### 4.1 端点配置

doubao-vision 通过火山方舟的 openai-compatible 端点调用，与 `rag_service._DoubaoMultimodalEmbeddings` 使用相同账号和网络链路（已打通，无额外网络开通需求）。

```
base_url: https://ark.cn-beijing.volces.com/api/v3
api_key: settings.DOUBAO_API_KEY（从 .env 读取）
model: settings.DOUBAO_VISION_MODEL（默认 doubao-vision-lite-32k）
```

### 4.2 调用格式（vision_service.analyze_image 内部）

```
调用方式：AsyncOpenAI.chat.completions.create（非流式，await 等待完整响应）

消息格式（openai-compatible multimodal）：
[
  {
    "role": "user",
    "content": [
      {
        "type": "image_url",
        "image_url": {
          "url": "data:image/jpeg;base64,<base64_encoded_image>"
        }
      },
      {
        "type": "text",
        "text": "<user_text 或 '请描述这张图片中的关键信息，包括文字、型号、状态等'>"
      }
    ]
  }
]
```

### 4.3 与 rag_service 可复用经验

| 经验 | rag_service 来源 | 在 vision_service.py 中的应用 |
|------|-----------------|------------------------------|
| 豆包偶发 >15s（8 次约 1 次）| `_DoubaoMultimodalEmbeddings` 注释 | 超时设 30s（C-003），单次调用使用 asyncio.timeout |
| 指数退避重试 | rag_service 实测经验 | 超时后等待 2s 再重试 1 次 |
| base_url 端点格式 | rag_service 代码 | 完全复用相同配置格式 |
| API key 从 settings 读取 | rag_service 模式 | 同一 DOUBAO_API_KEY 变量名 |

---

## 5. 技术风险汇总

| 风险级别 | 风险描述 | 来源 | 缓解措施 |
|---------|---------|------|---------|
| **High** | `python-magic` 依赖 `libmagic1` 系统包，生产 Pi 5 未安装时 `ImportError` 导致服务启动失败 | REQ-NFR-003 SC-006 实现 | 部署文档明确列出依赖；或采用零依赖的手动魔数字节检查降级方案（见第 3.1 节备注）|
| **Medium** | doubao-vision-lite 识别效果不足（复杂工程图纸、手写/印刷铭牌）导致 VLM 描述质量差，影响专家回答质量 | RISK-MQ-003 | 开发阶段用真实设备铭牌图片（≥5 个样本）手动抽检 AC-MQ-001-02；效果不足时通过 `DOUBAO_VISION_MODEL=doubao-vision-pro-32k` 切换，无需改代码 |
| **Medium** | Pi WiFi 抖动导致 doubao-vision 偶发 >15s（历史实测 8 次约 1 次），P90 时延可能超 20s | RISK-MQ-001、REQ-NFR-001 | 30s 超时 + 1 次重试保护；前端 vision_progress 进度提示避免用户误判为无响应；时延目标 P90 而非 P99（需求已明确）|
| **Medium** | _route 意图分类收到含 VLM 描述前缀的 enhanced_message，LLM 路由可能漂移（RISK-MQ-002） | REQ-FUNC-005 | 前缀格式使用明确分隔符 `[用户图片分析：...]\n\n`，与用户文字明显区分；开发阶段抽检 5 个路由用例（AC-MQ-004-02）|
| **Low** | 图片字节意外进入 Django DEBUG 日志（开发者 logger.debug 误用） | RISK-MQ-004、REQ-NFR-003 SC-002 | vision_service.py 代码评审检查点：任何 logger 调用不得含 image_bytes/base64 参数；US-MQ-008 自动化测试用 grep 覆盖 |
| **Low** | 临时 upload 存储在 Pi 5 重启或异常退出后丢失，TTL 内用户需重新上传 | RISK-MQ-005、ADR-MQ-002 后果 | IMAGE_EXPIRED 错误消息引导用户重新上传；前端在 IMAGE_EXPIRED 时提示用户重选图片 |
| **Low** | iOS Safari Canvas/Blob API 兼容性（部分 API 行为与 Chrome 差异）| RISK-MQ-006 | compressImage 函数有 try/catch：压缩失败时降级为直接上传原 Blob（若原文件 ≤10MB 仍可正常上传）|

---

## 6. 不引入的技术（及原因）

| 排除技术 | 排除原因 |
|---------|---------|
| `volcengine-python-sdk` | openai SDK 的 openai-compatible 接口已足够，rag_service 已验证，无需额外 SDK |
| `Pillow / PIL` | 本版本服务端不做图片处理（存储和转发原始字节），无需引入 |
| `RapidOCR` | NS-002 明确排除离线 OCR 兜底，本期不实现 |
| Redis（用于临时存储）| C-008 单 worker，无跨进程需求；ADR-MQ-002 选定进程内 dict |
| Django CACHES（locmem/file）| ADR-MQ-002 选定进程内 dict，比 CACHES 更简单且等价 |
| `langchain_openai.ChatOpenAI`（用于 VLM）| VLM 调用不走 LangChain，直接用 openai SDK；避免 langchain 吞 reasoning_content（参考 freeark-deepseek-reasoning-stream 历史教训——DeepSeek reasoning 流被 langchain 吞）|
| WebSocket multipart（直接传图片）| SC-001/C-004 硬约束：base64/图片字节不进 WS 帧 |

---

*文档状态：DRAFT（2026-06-24）。待 PM 门控通过后更新为 APPROVED。*
