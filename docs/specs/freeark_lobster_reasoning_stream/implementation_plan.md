# 实施计划 — 方舟龙虾 Reasoning 流式展示

```
file_header:
  document_id: IMPL-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_software_developer (PM-orchestrated, PARTIAL_FLOW GROUP_C)
  created_at: 2026-05-26
  depends_on:
    - ARCH-REASONING-001 (architecture_design.md)
    - MOD-REASONING-001 (module_design.md)
    - REQ-SPEC-REASONING-001 (requirements_spec.md)
    - US-REASONING-001 (user_stories.md)
```

---

## 0. 概述

本文档记录 GROUP_C（软件实现阶段）的实施步骤、文件改动清单、风险与部署说明。
本期改动涉及 **3 个源码文件** + **1 个 settings.py 追加**，零新增依赖，零架构变动。

**PM 决策（PM-DEC-001）：US-RSN-001 字段名探查采用走法 B**
- 不在 GROUP_C 阶段动生产，不申请临时生产授权。
- adapter v1.3 使用防御性双路解析（`_REASONING_FIELD='reasoningDelta'` + `kind=='reasoning'` 备用路径）覆盖所有候选字段名结构。
- 上线后若 INFO 日志显示 `reasoning_tokens=0`（字段名未命中），触发 GROUP_E 生产探查流程（见第 4 节）。

---

## 1. 实施批次与文件改动清单

### 批次 1：后端核心（US-RSN-001 走法 B + US-RSN-002 + US-RSN-003 + US-RSN-004 + US-RSN-008）

| 文件 | 类型 | 变更描述 |
|------|------|---------|
| `FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py` | 升级 v1.2→v1.3 | yield 协议升级 + 防御性 reasoning 解析 + reasoning_effort 透传 + 统计日志 |
| `FreeArkWeb/backend/freearkweb/api/consumers.py` | 升级 v1.1→v1.2 | _handle_chat 解包 (kind,text) + 路由 reasoning_token/reasoning_end/stream_token |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | 追加 1 行 | OPENCLAW_REASONING_EFFORT 读取（仅 settings.py，.env 由 devops 写入） |

**adapter v1.3 核心变更点**：
1. 新增模块级常量 `_REASONING_FIELD = 'reasoningDelta'`（含 TODO 注释）
2. `_get_config()` 新增 `reasoning_effort` 键
3. `_build_chat_send_frame()` 新增 `reasoning_effort` 参数，合法时注入 `params['reasoningEffort']`
4. `stream_chat()` 返回类型 `AsyncGenerator[tuple[str, str], None]`
5. state=='delta' 分支：防御性双路解析 + `yield ('reasoning', ...)` / `yield ('content', ...)`
6. 计时器（`time.monotonic()`）跟踪 reasoning/content 各阶段起止时间
7. state=='final' 前：`logger.info('stream_complete ...')` 含 reasoning_tokens/content_tokens/各阶段毫秒
8. state=='aborted'/'error' 前：`logger.info('stream_incomplete ...')`
9. 非法 reasoning_effort 值：`logger.warning` + 忽略（不传参数）
10. `import time` 追加

**consumer v1.2 核心变更点**：
1. `async for kind, text in OpenClawAdapter.stream_chat(...)` 解包二元组
2. 局部变量 `_in_reasoning = False`，`_reasoning_ended = False`
3. `kind == 'reasoning'` → `send({'type': 'reasoning_token', 'token': text})`，`_in_reasoning = True`
4. `kind == 'content'` 且 `_in_reasoning and not _reasoning_ended` → 先 `send({'type': 'reasoning_end'})`，再 `send({'type': 'stream_token', ...})`
5. 状态变量为局部变量（不跨请求持久化，满足 REQ-NFR-009）

**settings.py 追加**：
```python
OPENCLAW_REASONING_EFFORT = os.environ.get('OPENCLAW_REASONING_EFFORT', '')
```
位置：现有 OPENCLAW_CONNECT_TIMEOUT 变量之后，日志配置之前。

---

### 批次 2：前端（US-RSN-005 + US-RSN-006 + US-RSN-007）

| 文件 | 类型 | 变更描述 |
|------|------|---------|
| `FreeArkWeb/frontend/src/views/ChatView.vue` | 升级 v1.0→v1.1 | 消息结构扩展 + handleMessage 新 case + `<details>` 折叠区 + 样式追加 |

**ChatView.vue v1.1 核心变更点**：
1. 助手消息创建（`handleSend`）：新增 `reasoning: ''`，`reasoningStreaming: false` 字段
2. `handleMessage` switch 新增两 case：
   - `'reasoning_token'`：`last.reasoning += token; last.reasoningStreaming = true`
   - `'reasoning_end'`：`last.reasoningStreaming = false`
3. 模板助手气泡内：
   - `<details v-if="msg.reasoning || msg.reasoningStreaming" :open="msg.reasoningStreaming">` 折叠区
   - `thinking-indicator` 的 `v-if` 新增 `&& !msg.reasoning && !msg.reasoningStreaming` 条件（降级兼容）
4. 样式新增：`.reasoning-details`，`.reasoning-summary`，`.reasoning-text`
5. 无新增 JS 依赖，无新增 Element Plus 组件（满足 C-010）
6. `{{ msg.reasoning }}` 使用 Vue 插值（HTML 转义），不用 `v-html`（安全约束）

---

### 批次 3：兼容性回归测试（US-RSN-010）

| 文件 | 类型 | 变更描述 |
|------|------|---------|
| `FreeArkWeb/backend/freearkweb/api/tests.py` | 追加 | `ChatConsumerReasoningProtocolTest` + `ChatConsumerNoReasoningCompatTest` |

**测试类说明**：
- `ChatConsumerReasoningProtocolTest.test_reasoning_then_content_message_sequence`：
  mock adapter 返回 reasoning×2 + content×2，断言消息序列：
  `reasoning_token`×2 → `reasoning_end`×1 → `stream_token`×2 → `stream_end`×1
- `ChatConsumerReasoningProtocolTest.test_reasoning_end_sent_only_once`：
  mock adapter 返回 reasoning×3 + content×1，断言 `reasoning_end` 恰好出现 1 次（ARCH-C-004）
- `ChatConsumerNoReasoningCompatTest.test_no_reasoning_sequence_is_compat`：
  mock adapter 只返回 content×3，断言序列无 `reasoning_token`/`reasoning_end`，
  只有 `stream_token`×3 + `stream_end`（向后兼容 AC-NFR-005-01）

测试运行方式（本机 SQLite）：
```bash
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests.ChatConsumerReasoningProtocolTest api.tests.ChatConsumerNoReasoningCompatTest --settings=freearkweb.settings
```

---

### 批次 4：P1 功能（US-RSN-004 已含于批次 1；US-RSN-008 已含于批次 1）

US-RSN-009（基线测量）属于生产环境操作，**不在 GROUP_C 范围**，由 devops 在 GROUP_E 执行（见第 4 节）。

---

## 2. 部署约束

### 2.1 同批次部署要求（ARCH-C-002）

**adapter v1.3 和 consumer v1.2 必须同批次部署，禁止单独部署 adapter。**

原因：adapter v1.3 的 `stream_chat()` 返回类型从 `str` 变为 `tuple[str, str]`，若 consumer 未同步升级，`async for token in ...` 会将 tuple 作为 token 整体传递，前端收到 `"('reasoning', '...')"` 字符串，不会崩溃但行为错误。

部署步骤（GROUP_E 执行）：
1. `git pull` 拉取包含两文件变更的 commit
2. 重启 `freeark-backend` systemd 服务（一次重启同时加载两文件）
3. 验证：从前端发一条消息，查看 journalctl INFO 日志是否出现 `stream_complete`

### 2.2 前端独立部署可行

`ChatView.vue` 可在后端部署前或后独立部署（`npm run build` + nginx 静态文件刷新）。
旧后端（v1.1 consumer）不发送 `reasoning_token`/`reasoning_end`，前端 v1.1 的新 case 永远不触发，行为与 v1.0 完全一致。

### 2.3 OPENCLAW_REASONING_EFFORT 环境变量

- settings.py 已添加读取逻辑，默认空字符串（不传 reasoning_effort，使用模型默认值）
- 生产 .env 写入由 devops 在 GROUP_E 执行：
  ```
  # 生产 .env 追加（可选，留空则使用 DeepSeek 默认 reasoning depth）
  OPENCLAW_REASONING_EFFORT=low
  ```
- 非法值（如 `ultra`）adapter 会输出 WARNING 并忽略，不影响功能

---

## 3. 走法 B 风险说明与处置路径

### 3.1 风险描述

`_REASONING_FIELD = 'reasoningDelta'` 是基于 ADR-006 候选字段名的首选猜测值，
加上 `kind=='reasoning'` 备用路径，覆盖两类已知结构：
- 结构 A：`{'reasoningDelta': '...', 'deltaText': '...'}`（或 `thinkingDelta`）
- 结构 B：`{'kind': 'reasoning', 'deltaText': '...'}`

**若 OpenClaw 使用第三种未预期结构**（US-RSN-001 场景 C：完全无 reasoning 字段），
adapter 将：
- `reasoning_tokens` 始终为 0（INFO 日志可观测）
- `yield ('content', deltaText)` 正常工作（功能退化为 v1.2 行为，非崩溃）
- 前端不出现 `<details>` 折叠区，显示原版「正在思考...」行为

### 3.2 处置路径（GROUP_E 生产探查流程）

若生产部署后 `journalctl -u freeark-backend | grep stream_complete` 显示
`reasoning_tokens=0`（且 DeepSeek v4-flash 模型应有 reasoning 阶段），执行：

1. **有限生产授权**：devops 在 adapter.py 的 state=='delta' 分支内临时加入：
   ```python
   logger.info('PROBE delta payload keys: %s', list(payload.keys()))
   ```
2. 重启后端，触发 1-2 次对话，从 journalctl 获取 payload keys
3. 确认实际字段名后，更新 `_REASONING_FIELD` 常量（单行改动）
4. 移除临时 PROBE logger，重启后端
5. 更新 architecture_design.md ADR-006（标注"来源：GROUP_E 实测"）

**不需要重写任何其他代码。**

---

## 4. US-RSN-009 基线测量（GROUP_E 执行步骤）

在 adapter v1.3 + consumer v1.2 部署且 `APP_LOG_LEVEL=INFO` 激活后：

### 4.1 基线测量（OPENCLAW_REASONING_EFFORT 未设置）

```bash
# Pi 上执行，连续 3 次发送相同问题：
# "介绍三恒系统的主要设备组成，包括新风机组、风机盘管和除湿机"

# 从 journalctl 提取 reasoning_ms：
sudo journalctl -u freeark-backend -n 50 | grep stream_complete | grep reasoning_ms
# 预期输出形如：
# reasoning_tokens=N content_tokens=M reasoning_ms=T1 content_ms=T2 total_ms=T3
```

记录 T1、T2、T3 三次的 reasoning_ms，计算均值 T0 = (T1+T2+T3)/3，写入 tech_stack.md NFR 基线表。

### 4.2 low 配置效果验证

```bash
# 在生产 .env 追加：OPENCLAW_REASONING_EFFORT=low
# 重启后端，再次 3 次发送相同问题，记录 T1'、T2'、T3'
# 计算 T0' = 均值
# 验证：(T0 - T0') / T0 >= 0.5（下降 ≥ 50%）
```

若 T0' / T0 >= 50%，NFR 达标，更新 tech_stack.md。
若不达标，上报 PM，由 PM 调整 NFR 阈值或调研 medium 配置效果。

---

## 5. 测试覆盖说明（GROUP_D 参考）

| 测试类 | 覆盖范围 | 对应 US |
|--------|---------|---------|
| `ChatConsumerReasoningProtocolTest.test_reasoning_then_content_message_sequence` | AC-010-01/02/03/04 | US-RSN-003, US-RSN-010 |
| `ChatConsumerReasoningProtocolTest.test_reasoning_end_sent_only_once` | ARCH-C-004 | US-RSN-003 |
| `ChatConsumerNoReasoningCompatTest.test_no_reasoning_sequence_is_compat` | AC-010-05, AC-NFR-005-01 | US-RSN-007, US-RSN-010 |

adapter 单元测试（US-RSN-002 yield 协议）和前端测试（US-RSN-005/006/007 UI 行为）
归属 GROUP_D（test_engineer 负责），不在本期 GROUP_C 范围内。

---

## 6. 变更文件汇总

| 文件路径 | 变更类型 | 版本 | 对应 US |
|---------|---------|------|--------|
| `FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py` | 升级 | v1.2→v1.3 | US-RSN-002, US-RSN-004, US-RSN-008 |
| `FreeArkWeb/backend/freearkweb/api/consumers.py` | 升级 | v1.1→v1.2 | US-RSN-003 |
| `FreeArkWeb/frontend/src/views/ChatView.vue` | 升级 | v1.0→v1.1 | US-RSN-005, US-RSN-006, US-RSN-007 |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | 追加 | — | US-RSN-008 |
| `FreeArkWeb/backend/freearkweb/api/tests.py` | 追加 | — | US-RSN-010 |
