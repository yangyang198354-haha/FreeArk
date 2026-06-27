# 技术栈说明 — 方舟智能体语音输入

```
file_header:
  document_id: TECH-VOICE-001
  project: FreeArk — freeark_lobster_voice_input
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  depends_on: ARCH-VOICE-001
```

---

## 0. 说明

本文档描述语音输入功能涉及的技术栈，重点标注**新增依赖**、**版本约束**和**不确定项（待探查）**。

---

## 1. 后端技术栈（现有，不变）

| 组件 | 版本 | 状态 |
|------|------|------|
| Python | 3.11（生产） | 现有，不变 |
| Django | 5.2.8 | 现有，不变 |
| Channels | 4.3.2 | 现有，不变 |
| Uvicorn | 0.47 | 现有，不变 |
| aiohttp | 3.13.5 | **现有可复用**，用于 VolcASRClient 的 WS 客户端 |
| asgiref | 现有版本 | 现有，不变 |
| mysqlclient | 现有版本 | 现有，不变 |

**关键说明**：aiohttp 3.13.5 已在项目中作为 OpenClaw adapter 的 WS 客户端使用（`api/openclaw_adapter.py`），VolcASRClient 可复用相同的 aiohttp 异步 WS 客户端模式，**无需新增 WS 客户端库**。

---

## 2. 后端新增依赖

### 2.1 无需新增 Python 包（期望）

| 功能 | 使用现有组件 | 说明 |
|------|------------|------|
| 火山 ASR WSS 连接 | aiohttp 3.13.5（ClientSession + ws_connect） | 与 OpenClawAdapter 相同模式 |
| 音频帧转发 | bytes 操作（标准库） | 不需要音频解码库（方案 A 原始透传） |
| 鉴权签名（若需 HMAC） | hmac + hashlib（标准库） | Python 标准库，无需安装 |
| 环境变量读取 | os.environ.get（标准库）| 现有模式，无需新增 |

**前提**：ADR-015 选择方案 A（原始 webm/opus 透传）且 ADR-017 不需要特殊签名库。若 VERIFY-VOICE-003/005 确认需要转码或特定签名库，此节须更新。

### 2.2 可能新增的包（待 VERIFY 确认）

| 场景 | 可能需要的包 | 版本要求 | 条件 |
|------|------------|---------|------|
| 若火山 ASR 要求 PCM（ADR-015 方案 B/C） | audioop（标准库，3.11 含）或 soundfile 0.12+ | — | VERIFY-VOICE-003 确认 |
| 若 VAD 走后端分析（ADR-019 方案 B） | numpy（已可能装）| ≥1.24 | ADR-019 选方案 B |
| 若火山 ASR 有官方 Python SDK | volcengine-python-sdk（字节官方） | 待查 | VERIFY-VOICE-005 确认 |

**注**：**禁止**引入 ffmpeg 系统依赖（增加生产运维复杂度）、**禁止**引入 Docker（强制纪律）。

---

## 3. 前端技术栈（现有，不变）

| 组件 | 版本 | 状态 |
|------|------|------|
| Vue 3 | 现有版本 | 现有，不变 |
| Vite | 现有版本 | 现有，不变 |
| Pinia | 现有版本 | 现有，不变 |
| Element Plus | 现有版本 | 现有，不变 |

---

## 4. 前端新增 Web API（浏览器原生，无需 npm 包）

| API | 用途 | 兼容性约束 |
|-----|------|-----------|
| `navigator.mediaDevices.getUserMedia()` | 麦克风权限请求 + 音频流获取 | Chrome 55+, Firefox 52+, Safari 11+，iOS Safari 11+（需 HTTPS） |
| `MediaRecorder` | 将音频流编码为 chunk | Chrome 47+, Firefox 25+, Safari 14.1+（有限）；**iOS Safari <14.1 不支持**（VERIFY-VOICE-001） |
| `AudioContext` / `AnalyserNode` | VAD（P1，ADR-019 方案 A） | Chrome 35+, Firefox 25+, Safari 14.1+ |
| `WebSocket`（浏览器原生） | 连接 /ws/stt/ | 现有，已在 ChatView.vue 中使用 |

**关键说明**：**无需新增 npm 包**。所有音频相关功能均使用浏览器原生 Web API，不引入 recorder.js、opus-recorder 等第三方音频库（避免许可证和维护风险）。

---

## 5. 火山引擎 ASR 服务

| 项目 | 值 | 状态 |
|------|---|------|
| 服务商 | 字节火山引擎 | 用户已申请 |
| 服务类型 | 大模型语音识别（推测：实时流式） | **待 VERIFY-VOICE-002/003/005 确认** |
| 接入方式 | WSS endpoint（推测） | **待 VERIFY-VOICE-005 确认鉴权方式** |
| secret key 变量名 | `VOLC_ASR_APP_KEY`（后端 .env） | 约定变量名，用户部署时注入 |
| secret key 额外变量 | `VOLC_ASR_APP_ID`（如火山 ASR 需要 APP_ID 额外参数） | 视 VERIFY-VOICE-005 结论而定 |
| 音频格式 | 待 VERIFY-VOICE-003 确认 | **OPEN** |
| 并发限制 | 待 VERIFY-VOICE-004 确认 | **OPEN** |
| 单次最大时长 | 待 VERIFY-VOICE-002 确认 | **OPEN** |

**关键说明**：secret key 和 app_id 仅通过 `.env` 注入，通过 `os.environ.get('VOLC_ASR_APP_KEY')` 读取，**绝不**硬编码、**绝不**出现在任何 HTTP/WS 响应、**绝不**记录在日志中。

---

## 6. 运行环境约束

| 约束 | 说明 |
|------|------|
| HTTPS 要求 | `getUserMedia` 在非 localhost 环境下必须在 HTTPS/WSS 下运行。生产已有反向代理（参考 ALLOWED_HOSTS 含域名 `et116374mm892.vicp.fun`），需确认 TLS 终止配置 |
| aiohttp WS client 模式 | 与 OpenClawAdapter 相同：`async with aiohttp.ClientSession() as session: async with session.ws_connect(url) as ws:` |
| --workers 1 约束 | 现有 uvicorn 启动参数 `--workers 1`（InMemoryChannelLayer 不支持多进程），STTConsumer 同受此约束，不引入状态共享问题 |
| 生产 Pi 5 资源 | 树莓派 Pi 5，避免引入 CPU 密集型音频处理（无转码，传输原始编码帧） |

---

## 7. 技术选型确定性状态汇总

| 组件 | 确定性 | 说明 |
|------|--------|------|
| aiohttp WS client（VolcASRClient） | 确定 | 现有依赖，模式成熟 |
| MediaRecorder API（前端） | 确定 | 浏览器原生，无需安装 |
| WebSocket（/ws/stt/）| 确定 | 依赖现有 Channels 栈 |
| 火山 ASR 音频格式 | **OPEN — VERIFY-VOICE-003** | 影响 ADR-015 |
| 火山 ASR 鉴权方式 | **OPEN — VERIFY-VOICE-005** | 影响 ADR-017 |
| 火山 ASR 时长/并发限制 | **OPEN — VERIFY-VOICE-002/004** | 影响 REQ-FUNC-021 参数 |
| VAD 实现（P1） | **OPEN — ADR-019** | P0 阶段跳过 |
| volcengine Python SDK | **OPEN — VERIFY-VOICE-005** | 视鉴权方式是否需要 |
