# 技术栈文档（增量）— 方舟龙虾 Reasoning 流式展示

```
file_header:
  document_id: TECH-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-25
  depends_on: ARCH-REASONING-001, REQ-SPEC-REASONING-001
```

---

## 0. 增量说明

本文档仅记录**本期新增或变更**的技术栈条目。现有技术栈（Django 5.2、DRF、aiohttp、Vue 3、Element Plus、Vite、OpenClaw 2026.5.20、DeepSeek v4-flash 等）继承自 `docs/sdlc/lobster-agent-api-channel/tech_stack.md`，不重复列举。

---

## 1. 本期新增依赖

**结论：零新增依赖。**

| 层 | 现有技术 | 本期使用方式 | 是否新增 |
|----|---------|------------|---------|
| 后端 Python | `asyncio`, `json`, `logging`（stdlib） | adapter 计时（`asyncio.get_event_loop().time()`）、日志格式化 | 否 |
| 后端 Python | `aiohttp`（已有） | yield 协议扩展，不新增 API 调用 | 否 |
| 前端 JS | 原生 HTML `<details>/<summary>` | reasoning 折叠区 | 否（浏览器原生） |
| 前端 JS | Vue 3 响应式（已有） | `msg.reasoning`, `msg.reasoningStreaming` | 否 |
| 前端 CSS | 已有 CSS 变量 | `.reasoning-text` 样式（浅灰斜体） | 否（仅增加少量 CSS 规则） |

---

## 2. 环境变量（新增）

| 变量名 | 类型 | 默认值 | 说明 | 文件位置 |
|-------|------|--------|------|---------|
| `OPENCLAW_REASONING_EFFORT` | string | `""` (空，使用模型默认) | 控制 DeepSeek reasoning 深度，合法值：`low` / `medium` / `high` | `FreeArkWeb/backend/.env` |

Django `settings.py` 对应条目（在现有 OPENCLAW_* 变量后追加）：
```python
OPENCLAW_REASONING_EFFORT = env('OPENCLAW_REASONING_EFFORT', default='')
```

---

## 3. NFR 基线表（本期）

> 基线数据在 US-RSN-009 完成后填入。此表为占位结构，开发者必须在功能实现后补充实测数据。

| 指标 | 目标 | 基线（T0，实测前置） | 达标 |
|------|------|------------------|-----|
| 首个 reasoning_token 端到端延迟（FreeArk 链路） | ≤ 2s | [待 US-RSN-009 测量] | — |
| reasoning 阶段耗时（`reasoning_effort=low` vs 默认） | 下降 ≥ 50% | [待基线 + low 对比测量] | — |
| adapter INFO 日志是否包含分段统计 | 每次对话 1 行 | [待 US-RSN-004 实现后验证] | — |
| 旧前端兼容性（reasoning 帧被 default 忽略） | 无 JS 错误 | [待 US-RSN-010 测试] | — |

### 3.1 基线测量方法（US-RSN-009 执行指引）

```bash
# 环境准备（Pi 上）
# 1. 部署 v1.3 adapter（含统计日志，APP_LOG_LEVEL=INFO）
# 2. 确保 OPENCLAW_REASONING_EFFORT 未设置（空）

# 发送 3 次相同问题：
# "介绍三恒系统的主要设备组成，包括新风机组、风机盘管和除湿机"
# （选此问题因其需要推理总结，能稳定触发 reasoning）

# 从 journalctl 提取：
sudo journalctl -u freeark-backend --since "5 min ago" | grep stream_complete
# 预期输出示例：
# reasoning_tokens=142 content_tokens=387 reasoning_ms=8420 content_ms=4130 total_ms=12550
```

---

## 4. 模块版本映射

| 模块 | 文件 | v1.2（当前） | v1.3（本期目标） | 核心变更 |
|------|------|------------|----------------|---------|
| MOD-BE-02 | `openclaw_adapter.py` | yield str，只读 deltaText | yield (kind, text)，读 reasoning 字段 + reasoning_effort 参数 + 统计日志 | ADR-006, ADR-008 |
| MOD-BE-01 | `consumers.py` | 只发 stream_token | 发 reasoning_token + reasoning_end + stream_token | ADR-007 |
| MOD-FE-01 | `ChatView.vue` | 无（首次记录） | v1.1：`<details>` 折叠 + 消息结构扩展 | ADR-007 |
