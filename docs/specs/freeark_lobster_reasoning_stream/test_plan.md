# 测试计划 — 方舟智能体 Reasoning 流式展示

```
file_header:
  document_id: TP-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_test_engineer (PM-orchestrated, PARTIAL_FLOW GROUP_D)
  created_at: 2026-05-26
  depends_on:
    - US-REASONING-001 (user_stories.md)
    - MOD-REASONING-001 (module_design.md)
    - CR-REASONING-001 (code_review_report.md)
    - IMPL-REASONING-001 (implementation_plan.md)
```

---

## 0. 测试范围说明

### 0.1 GROUP_D 测试范围（本文档）

| US 编号 | 描述 | 测试层 | 在范围 | 说明 |
|---------|------|--------|--------|------|
| US-RSN-001 | OpenClaw 字段名实测探查 | 无 — 需生产环境 | **否** | 归属 GROUP_E，见 §5 |
| US-RSN-002 | Adapter yield 协议升级 | 单元测试 | **是** | |
| US-RSN-003 | Consumer 分类转发 + reasoning_end | 集成测试 | **是** | GROUP_C 已有 2 个 case，GROUP_D 补全 |
| US-RSN-004 | 统计日志 | 单元测试 | **是** | |
| US-RSN-005 | 前端气泡 reasoning 展示 | 契约测试 / manual checklist | **是** | 无真实 OpenClaw，mock WS 消息验证逻辑 |
| US-RSN-006 | reasoning 结束折叠，content 接续 | 契约测试 | **是** | 同上 |
| US-RSN-007 | 无 reasoning 降级 | 集成测试 | **是** | GROUP_C 已有 compat case |
| US-RSN-008 | reasoning_effort 环境变量配置 | 单元测试 | **是** | |
| US-RSN-009 | reasoning_effort 效果基线测量 | 无 — 需生产环境 | **否** | 归属 GROUP_E，见 §5 |
| US-RSN-010 | 旧前端兼容性回归 | 集成测试 | **是** | GROUP_C 已有，GROUP_D 执行确认 |

### 0.2 环境约束

- **本机数据库**：SQLite（`settings.py` `_RUNNING_TESTS` 自动切换，无需配置）
- **无生产访问**：不连接 Pi，不读 journalctl，不改 .env
- **WS 集成测试**：使用 `channels.testing.WebsocketCommunicator` + `TransactionTestCase`
- **前端测试**：无浏览器自动化（Vue 组件需真实浏览器），采用 WS 契约验证 + manual checklist 形式

---

## 1. 测试架构三层设计

```
层次一（单元测试）：TestCase，mock aiohttp
  ├─ AdapterYieldProtocolTest          — US-RSN-002 yield 协议
  ├─ AdapterReasoningFieldParseTest    — US-RSN-002 防御性双路解析
  ├─ AdapterReasoningEffortTest        — US-RSN-008 reasoning_effort 注入与验证
  ├─ AdapterStatLogTest                — US-RSN-004 统计日志格式与安全性
  └─ AdapterToWsUrlTest                — 工具函数回归

层次二（集成测试）：TransactionTestCase + WebsocketCommunicator
  ├─ ChatConsumerReasoningProtocolTest — US-RSN-003, US-RSN-010（GROUP_C 已有，GROUP_D 执行）
  ├─ ChatConsumerNoReasoningCompatTest — US-RSN-007, US-RSN-010（GROUP_C 已有，GROUP_D 执行）
  └─ ChatConsumerEdgeCasesTest         — US-RSN-003 场景 D（边界：reasoning 后再出现 reasoning）

层次三（前端契约 / manual checklist）：无 headless 浏览器
  ├─ WS 消息序列契约：GROUP_D 集成测试已覆盖后端侧消息顺序
  ├─ US-RSN-005/006/007 前端逻辑：manual checklist（见 §4）
  └─ 覆盖率豁免声明：前端 Vue 组件不纳入覆盖率统计，与 PM 确认
```

---

## 2. 单元测试详细设计

### 2.1 AdapterYieldProtocolTest（US-RSN-002）

**文件**：`FreeArkWeb/backend/freearkweb/api/tests.py`（追加）

#### TC-UNIT-001：reasoning + content 各自独立 yield 二元组

- **Given**：delta payload = `{'reasoningDelta': 'r1', 'deltaText': 'c1'}`
- **When**：adapter 处理该帧
- **Then**：先 yield `('reasoning', 'r1')`，再 yield `('content', 'c1')`（顺序断言）
- **覆盖 AC**：AC-009-01, AC-009-02, AC-009-03（同帧双 yield 顺序）

#### TC-UNIT-002：仅 content，无 reasoning 字段

- **Given**：payload = `{'deltaText': 'hello', 'state': 'delta'}`
- **When**：adapter 解析
- **Then**：yield `('content', 'hello')`；无 `('reasoning', ...)`

#### TC-UNIT-003：仅 reasoning，无 deltaText

- **Given**：payload = `{'reasoningDelta': 'think1'}`
- **When**：adapter 解析
- **Then**：yield `('reasoning', 'think1')`；无 `('content', ...)`

#### TC-UNIT-004：kind=='reasoning' 备用路径（Path 2）

- **Given**：payload = `{'kind': 'reasoning', 'deltaText': 'think2'}`（`_REASONING_FIELD` 不存在）
- **When**：adapter 解析
- **Then**：yield `('reasoning', 'think2')`；`delta_text = ''` 不 yield content

#### TC-UNIT-005：空文本不 yield

- **Given**：payload = `{'reasoningDelta': '', 'deltaText': ''}`
- **When**：adapter 解析
- **Then**：无任何 yield

#### TC-UNIT-006：yield 类型为 tuple[str, str]（类型契约）

- **Given**：任意有效 delta payload
- **When**：adapter yield
- **Then**：每个 yield 值 isinstance `tuple`，len == 2，两元素均为 `str`

### 2.2 AdapterReasoningEffortTest（US-RSN-008）

#### TC-UNIT-007：合法值 'low' 注入 params

- **Given**：`OPENCLAW_REASONING_EFFORT=low`（mock settings）
- **When**：`_build_chat_send_frame` 被调用，`reasoning_effort='low'`
- **Then**：返回帧 `params['reasoningEffort'] == 'low'`
- **覆盖 AC**：AC-012-01

#### TC-UNIT-008：合法值 'medium'/'high' 注入 params

- **Given**：`reasoning_effort='medium'` 和 `reasoning_effort='high'`
- **When**：`_build_chat_send_frame`
- **Then**：各自注入对应 camelCase key

#### TC-UNIT-009：非法值不注入（AC-012-03）

- **Given**：`OPENCLAW_REASONING_EFFORT=ultra`
- **When**：stream_chat 运行到 reasoning_effort 验证段
- **Then**：`logger.warning` 被调用一次；`reasoning_effort` 重置为 `''`；`_build_chat_send_frame` 的 `params` 中无 `reasoningEffort` key
- **覆盖 AC**：AC-012-03, AC-012-04

#### TC-UNIT-010：未设置时不注入（AC-012-03）

- **Given**：`OPENCLAW_REASONING_EFFORT=''`（默认）
- **When**：`_build_chat_send_frame`，`reasoning_effort=''`
- **Then**：`params` 中无 `reasoningEffort` key（使用模型默认）

### 2.3 AdapterStatLogTest（US-RSN-004）

#### TC-UNIT-011：stream_complete 日志格式（AC-NFR-008-01）

- **Given**：mock WS 流，发送 reasoning×2 + content×3 + state:final
- **When**：adapter 处理到 state:final
- **Then**：`logger.info` 被调用，message 包含 `stream_complete`、`reasoning_tokens=2`、`content_tokens=3`；不含任何 token 文本本身
- **覆盖 AC**：AC-NFR-008-01, AC-NFR-007-01（日志安全）

#### TC-UNIT-012：stream_incomplete 日志（aborted）

- **Given**：mock 发送 state:aborted
- **When**：adapter 处理
- **Then**：`logger.info` message 含 `stream_incomplete` 和 `reason=aborted`；同时抛出 `OpenClawUnavailableError`

#### TC-UNIT-013：stream_incomplete 日志（error）

- **Given**：mock 发送 state:error
- **When**：adapter 处理
- **Then**：`logger.info` message 含 `stream_incomplete` 和 `reason=error`

#### TC-UNIT-014：日志不含 token 文本（REQ-NFR-007）

- **Given**：reasoning_text = 'SENSITIVE_THINKING'，delta_text = 'SENSITIVE_CONTENT'
- **When**：adapter 处理，stream_complete 日志生成
- **Then**：所有 logger 调用的参数序列化后不含 'SENSITIVE_THINKING' 或 'SENSITIVE_CONTENT'
- **覆盖**：REQ-NFR-007

### 2.4 AdapterToWsUrlTest（工具函数回归）

#### TC-UNIT-015 ~ TC-UNIT-019：URL 转换（现有功能回归）

- `http://host:18789` → `ws://host:18789/`
- `https://host:443` → `wss://host:443/`
- `ws://host/` → `ws://host/`（不变）
- 无协议前缀 `host:port` → `ws://host:port/`
- 已有 trailing slash 不重复添加

---

## 3. 集成测试详细设计

### 3.1 GROUP_C 已有 cases（GROUP_D 执行并确认）

以下 3 个 TransactionTestCase 由 GROUP_C 编写，GROUP_D 执行并将结果纳入报告：

| 测试类 | 测试方法 | 覆盖 AC | 预期结论 |
|--------|---------|---------|---------|
| `ChatConsumerReasoningProtocolTest` | `test_reasoning_then_content_message_sequence` | AC-010-01/02/03/04 | PASS |
| `ChatConsumerReasoningProtocolTest` | `test_reasoning_end_sent_only_once` | ARCH-C-004 | PASS |
| `ChatConsumerNoReasoningCompatTest` | `test_no_reasoning_sequence_is_compat` | AC-010-05, AC-NFR-005-01 | PASS |

### 3.2 GROUP_D 新增集成 cases

#### TC-INTG-001：reasoning 后再出现 reasoning（US-RSN-003 场景 D）

- **Given**：adapter mock yield 序列：`('reasoning','r1')`, `('content','c1')`, `('reasoning','r2')`, `('content','c2')`
- **When**：consumer 处理（`_reasoning_ended=True` 后再遇 reasoning）
- **Then**：消息序列 = `reasoning_token(r1)`, `reasoning_end`, `stream_token(c1)`, `reasoning_token(r2)`, `stream_token(c2)`, `stream_end`
  — 第二段 reasoning 仍发送 reasoning_token，但不重复发送 reasoning_end（因为 `_reasoning_ended` 已 True）
- **说明**：US-RSN-003 场景 D 的防御性处理

#### TC-INTG-002：空 reasoning text 不发送 reasoning_token

- **Given**：adapter mock yield `('reasoning', '')` （空文本，理论上 adapter 不应 yield，但防御性测试）
- **When**：consumer 解包
- **Then**：若 kind='reasoning' 但 text='' 到达 consumer，consumer 仍会 send（这是 adapter 侧的防御，consumer 按 kind 路由）
  — 测试文档说明：此 case 记录 consumer 行为（不过滤空 text），作为技术债登记

---

## 4. 前端 Manual Checklist（US-RSN-005/006/007）

> 由于无 headless 浏览器且不连接生产 OpenClaw，前端验收采用 manual checklist 形式。
> 由开发者在本地起前端 dev server，模拟 WS 消息进行验证。
> Manual checklist 不纳入自动化覆盖率统计，但作为 GROUP_D 测试报告附件。

### MAN-001：首个 reasoning_token 触发 details 展示

- 步骤：打开 ChatView，打开 DevTools，在 WS 层手动发送 `{"type":"reasoning_token","token":"思考中..."}`
- 期望：助手气泡出现 `<details open>` 块，内含 "思考中..."，浅灰斜体

### MAN-002：reasoning_end 自动折叠

- 步骤：接上，发送 `{"type":"reasoning_end"}`
- 期望：`<details>` 的 `open` 属性移除，折叠

### MAN-003：stream_token 在 details 下方渲染

- 步骤：接上，发送 `{"type":"stream_token","token":"回答..."}`
- 期望：`<details>` 下方出现 "回答..."（正式回答区）

### MAN-004：stream_end 停止光标

- 步骤：发送 `{"type":"stream_end"}`
- 期望：光标消失，`isWaiting=false`

### MAN-005：无 reasoning 降级

- 步骤：直接发送 `{"type":"stream_token","token":"直接回答"}` 不发 reasoning_token
- 期望：无 `<details>` 渲染，"正在思考..." 先显示再被 content 替代

### MAN-006：用户点击展开折叠的 details

- 步骤：reasoning_end 后点击 `<summary>🧠 思考过程`
- 期望：details 重新展开，reasoning 文字完整显示

---

## 5. GROUP_E 输入项（生产环境相关，本文档不执行）

### 5.1 US-RSN-001 字段名探查（GROUP_E 执行步骤）

**触发条件**：生产部署后 `journalctl -u freeark-backend | grep stream_complete` 中 `reasoning_tokens=0`

**执行步骤**：
1. devops 在 `openclaw_adapter.py` `state == 'delta'` 分支内临时加入：
   ```python
   logger.info('PROBE delta payload keys: %s', list(payload.keys()))
   ```
2. 以 `APP_LOG_LEVEL=INFO` 重启后端
3. 从前端触发 1-2 次对话（建议问题："分析三恒系统的智能控制优化方向"以触发推理）
4. `sudo journalctl -u freeark-backend -n 100 | grep PROBE` 提取 payload keys
5. 根据实测结果更新 `_REASONING_FIELD` 常量（单行改动）
6. 移除临时 PROBE logger，重启后端
7. 再次检查 `stream_complete reasoning_tokens=N`（N > 0 即探查成功）
8. 更新 `architecture_design.md` ADR-006（标注"来源：GROUP_E 实测"）

**不需要重写任何其他代码。**

### 5.2 US-RSN-009 基线测量（GROUP_E 执行步骤）

**前置条件**：adapter v1.3 已部署，`APP_LOG_LEVEL=INFO` 已激活，且 reasoning_tokens > 0（字段名已确认）

**步骤 A：基线测量（OPENCLAW_REASONING_EFFORT 未设置）**

```bash
# Pi 上执行，连续 3 次发送相同问题：
# "介绍三恒系统的主要设备组成，包括新风机组、风机盘管和除湿机"
sudo journalctl -u freeark-backend -n 50 | grep stream_complete | grep reasoning_ms
# 记录每次 reasoning_ms 值 T1, T2, T3
# 计算 T0 = (T1+T2+T3)/3，写入 tech_stack.md NFR 基线表
```

**步骤 B：low 配置效果验证**

```bash
# 在生产 .env 追加：OPENCLAW_REASONING_EFFORT=low
# 重启后端：sudo systemctl restart freeark-backend
# 再次 3 次发同一问题，记录 T1', T2', T3'
# T0' = 均值
# 验证：(T0 - T0') / T0 >= 0.5（下降 ≥ 50%）
# 若不达标，上报 PM，由 PM 调整 NFR 阈值或调研 medium 配置
```

### 5.3 reasoning_tokens=0 上线后处置流程

若上线后首次发对话，`stream_complete reasoning_tokens=0` 但 DeepSeek 模型应有推理阶段：

1. 立即执行 5.1 字段名探查
2. 探查完毕后更新 `_REASONING_FIELD` 单行改动并重启
3. 功能退化期间（reasoning_tokens=0 期间）：前端不显示 `<details>` 折叠区，显示原版「正在思考...」，功能降级但不崩溃（ADR-006 防御性设计保证）

---

## 6. 测试执行命令

### 6.1 运行全部单元 + 集成测试

```bash
# 在 FreeArkWeb/backend/freearkweb/ 目录下
python manage.py test api.tests --settings=freearkweb.settings -v 2
```

### 6.2 仅运行 reasoning 相关测试（快速验证）

```bash
python manage.py test \
  api.tests.AdapterYieldProtocolTest \
  api.tests.AdapterReasoningEffortTest \
  api.tests.AdapterStatLogTest \
  api.tests.AdapterToWsUrlTest \
  api.tests.ChatConsumerReasoningProtocolTest \
  api.tests.ChatConsumerNoReasoningCompatTest \
  api.tests.ChatConsumerEdgeCasesTest \
  --settings=freearkweb.settings -v 2
```

### 6.3 覆盖率测量（需安装 coverage）

```bash
pip install coverage
coverage run --source=api.openclaw_adapter,api.consumers \
  manage.py test api.tests --settings=freearkweb.settings
coverage report -m
coverage html -d htmlcov/
```

---

## 7. 覆盖率目标

| 模块 | 目标 | 测量方式 |
|------|------|---------|
| `api/openclaw_adapter.py`（v1.3 delta lines） | ≥ 80% | `coverage report --include=api/openclaw_adapter.py` |
| `api/consumers.py`（v1.2 delta lines） | ≥ 90% | `coverage report --include=api/consumers.py` |
| US-RSN-002~008,010 验收标准（AC 条目） | ≥ 90% AC 覆盖 | 手工矩阵（见 §8） |
| 前端 ChatView.vue | 豁免（无自动化测试框架，manual checklist 替代） | — |

**注**：覆盖率门控以新增 delta 代码行为准（adapter v1.3 delta + consumer v1.2 delta）。
整个文件的覆盖率会受现有代码（WS 握手等未被 mock 覆盖的行）拉低，以 delta lines 覆盖率为准。

---

## 8. AC 覆盖矩阵

| AC 编号 | 描述摘要 | 测试 case | 测试层 |
|---------|---------|----------|--------|
| AC-008-01 | reasoning 字段名探查 | 归属 GROUP_E | 生产操作 |
| AC-009-01 | reasoning 增量 yield ('reasoning', text) | TC-UNIT-001/003 | 单元 |
| AC-009-02 | content 增量 yield ('content', text) | TC-UNIT-001/002 | 单元 |
| AC-009-03 | 同帧双字段先 reasoning 后 content | TC-UNIT-001 | 单元 |
| AC-009-04 | 分段统计日志 | TC-UNIT-011/012/013 | 单元 |
| AC-010-01 | reasoning_token WS 消息格式 | GROUP_C test_reasoning_then_content | 集成 |
| AC-010-02 | reasoning_end 信号 | GROUP_C test_reasoning_then_content | 集成 |
| AC-010-03 | stream_token WS 消息格式 | GROUP_C test_reasoning_then_content | 集成 |
| AC-010-04 | stream_end 信号 | GROUP_C test_reasoning_then_content | 集成 |
| AC-010-05 | 无 reasoning 时行为与 v1.1 一致 | GROUP_C test_no_reasoning_sequence | 集成 |
| AC-011-01 | 首个 reasoning_token 触发 details 显示 | MAN-001 | manual |
| AC-011-02 | reasoning_end 触发折叠 | MAN-002 | manual |
| AC-011-03 | content 接续在 details 下方 | MAN-003 | manual |
| AC-011-05 | 无 reasoning 时不渲染 details | MAN-005 | manual |
| AC-012-01 | reasoning_effort=low 注入 params | TC-UNIT-007 | 单元 |
| AC-012-03 | 非法值 WARNING 并忽略 | TC-UNIT-009 | 单元 |
| AC-012-04 | 未设置时不注入 | TC-UNIT-010 | 单元 |
| AC-NFR-005-01 | 旧前端 default 分支静默忽略 | GROUP_C test_no_reasoning_sequence | 集成 |
| AC-NFR-007-01 | 日志不含 token 文本 | TC-UNIT-014 | 单元 |
| AC-NFR-008-01 | stream_complete 日志含统计字段 | TC-UNIT-011 | 单元 |

---

## 9. 缺陷处理规则

- **CRITICAL**（功能崩溃、数据泄露）：GROUP_D 不放行，必须修复后重新执行
- **MAJOR**（核心 AC 不满足）：GROUP_D 不放行
- **MINOR**（格式、边界，已在 code_review 记录）：允许带入 GROUP_E，登记遗留问题
- **INFO**：文档记录，不阻塞

已知 MINOR（来自 code_review_report.md，CR-M-001/002/003）：均已有处置建议，不阻塞 GROUP_D 门控。
