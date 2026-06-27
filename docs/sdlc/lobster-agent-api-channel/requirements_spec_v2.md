# 需求规格说明书 v2 — 方舟智能体 API 通道与知识增强

```
file_header:
  document_id: REQ-SPEC-LOBSTER-002
  project: FreeArk — lobster-agent-api-channel
  version: 2.0.0
  status: APPROVED
  author_agent: requirement-analyst (PM-orchestrated, SDLC 第二轮修订)
  created_at: 2026-05-25
  supersedes: REQ-SPEC-LOBSTER-001
  context_snapshot: OpenClaw 2026.5.20, FreeArk v0.5.9+lobster-partial, WS Gateway RPC v4
  depends_on: PROBES-LOBSTER-001, DEPLOYREP-LOBSTER-001
  change_summary: >
    v1 → v2 变更：
    (1) REQ-FUNC-005 Skill 实现方式从"Node.js npm 包"修订为"SKILL.md + CLI 子进程"
    (2) 新增 REQ-NFR-006 PoC 强制前置验证（防 RISK-001 复发）
    (3) 新增 REQ-NFR-007 Token 全文脱敏强制规范（RISK-3 复发预防）
    (4) CONFIRM-1 措辞更新（Skill 通道实现方式）
    (5) CONFIRM-8 作废，由"待架构决策"替代
    (6) 不涉及已上线的 Django 改动（不修改、不回退）
```

---

## 0. 文档说明

本文档是 v1 需求规格（REQ-SPEC-LOBSTER-001）的**修订版**，仅记录变更和新增内容，
其余不变条款通过引用 v1 复用，不重复抄写。

**v1 中以下内容完整复用（不变）**：
- §1.1 当前系统架构（ChatConsumer → OpenClawAdapter → WS Gateway 链路）
- §1.2 已暴露的 FreeArk REST API 清单（34 个端点分类，完整保留）
- REQ-FUNC-001（API 通道建立）— 无变化
- REQ-FUNC-002（Skill 定义与注册）— AC 不变，实现方式由架构决定
- REQ-FUNC-003（Agent 重写/知识增强）— 无变化
- REQ-FUNC-004（鉴权与身份）— 无变化（openclaw-agent 服务账号已上线）
- REQ-FUNC-006（与现有 WS Gateway RPC v4 的共存）— 无变化
- REQ-NFR-001（性能）— 无变化
- REQ-NFR-002（安全性，原文）— 基础要求不变，见新增 REQ-NFR-007
- REQ-NFR-003（可观测性）— 无变化
- REQ-NFR-004（可维护性）— 无变化
- REQ-NFR-005（可用性）— 无变化
- §4（约束与边界）— 更新 §4.1 一条（原"Node.js 原生"描述改为"待实测"）
- 附录 A（specific_part 格式）— 无变化
- 附录 B（写操作安全现状）— 无变化

---

## 1. 已上线内容确认（不在本次 v2 范围内）

以下改动已于 2026-05-25T00:41+08:00 生效，状态 DEPLOYED，**本文档不修改、不回退**：

| 已上线项 | 位置 | 状态 |
|---------|------|------|
| ChatConsumer `[__freeark_user__:<username>]` 前缀注入 | `api/consumers.py` | DEPLOYED |
| `operator_override` 字段 + `effective_operator` 落库 | `api/serializers_device_settings.py`, `api/views_device_settings.py` | DEPLOYED |
| `openclaw-agent` 服务账号 (id=8, role=user) | FreeArk DB | DEPLOYED |

---

## 2. 修订的功能需求

### REQ-FUNC-005（修订）：Skill 实现机制

**原 v1 描述**（已作废）：
> "Skill 实现方式：Node.js 包 + 19 个 tool 函数，通过 `package.json` 导出"

**v2 描述（基于 PROBES-LOBSTER-001 FACT-01 至 FACT-07）**：

Skill 实现方式为 **OpenClaw SKILL.md + CLI 子进程**：

- Skill 入口文件：`agents/freeark-skill/SKILL.md`（Markdown + YAML frontmatter）
- SKILL.md 描述 Agent 可调用的 tool/command 列表、参数 schema、执行规则
- 每个 tool 的执行体为 CLI 程序（语言由 system-architect 基于实测决定，可能是 Python 脚本或 Bash 脚本）
- OpenClaw 通过子进程（`exec`）调用 CLI，不在 OpenClaw 的 Node.js 进程内运行
- Token 注入方式：通过 OpenClaw 配置的 `secrets` 段或子进程环境变量（具体方式由 system-architect 基于实测的 config schema 决定）

**来源引用**：PROBES-LOBSTER-001 §1, §2, FACT-01 至 FACT-07；DEPLOYREP-LOBSTER-001 §5.1/§5.4

**AC-005-01**（Skill 加载验证）

- Given：`agents/freeark-skill/SKILL.md` 已按正确格式写入，且目录路径已在 openclaw.json 正确注册
- When：`systemctl --user restart openclaw-gateway.service`
- Then：Gateway 正常启动（无 "Invalid config" 错误），`openclaw skills list` 或等效命令可列出 freeark-skill，且 Agent 在对话中可触发该 Skill

**AC-005-02**（CLI 执行体调用）

- Given：Agent 决定查询一个 FreeArk 只读端点
- When：Agent 通过 Skill 调用对应 tool
- Then：OpenClaw 以子进程方式调用 CLI 执行体，CLI 发出 HTTP GET 请求到 `127.0.0.1:8000/api/<path>/`，并以标准 I/O 格式将结果返回给 OpenClaw

---

## 3. 修订的技术约束

### §4.1 技术约束（更新条目）

**原 v1**：
> "OpenClaw 原生 Skill 机制使用 Node.js；如需 Python Skill，需确认 OpenClaw 是否支持"

**v2 替换为**：
> "OpenClaw 2026.5.20 的 Skill 机制使用 SKILL.md 描述能力，执行体为 CLI 子进程，
>  与执行体语言（Python/Bash/Node.js 均可）无关；执行体语言由 system-architect
>  基于 PROBES-LOBSTER-001 §3 中的 bundled 示例分析后决定，不得凭空假设。"

---

## 4. 新增非功能需求

### REQ-NFR-006（新增）：PoC 强制前置验证

**来源**：DEPLOYREP-LOBSTER-001 §5.3/§5.4（RISK-001 REALIZED 教训），PROBES-LOBSTER-001 §6

**描述**：
在 Skill 层进入完整开发之前，**必须**先在 Pi 上完成一个最小可行 Skill 的 PoC 验证：

- PoC 范围：仅实现 1 个只读 tool（建议 `freeark_get_realtime_params`），
  使 OpenClaw 能够成功加载该 Skill 并在对话中触发调用
- PoC 通过标准：`openclaw-gateway.service` 正常启动 + Agent 对话中实际调用 Skill 返回数据
- PoC 是开发阶段的**第一个里程碑**，PoC 未通过则不得扩展到 19 个 tool

**验收标准**：

- Given：`agents/freeark-skill/SKILL.md` 已实现一个最小 tool（1个）
- When：在 Pi 上部署并重启 openclaw-gateway
- Then：Gateway 正常启动，Agent 对话中触发该 tool，返回 FreeArk API 的真实数据
- Then：开发人员明确记录"PoC 通过，SKILL.md 格式与 CLI 协议已验证"后，再继续实现其余 18 个 tool

**约束**：
- PoC 验证必须在 Pi 上真实运行（不允许纯本地 mock）
- PoC 通过记录必须写入 code_review_report_v2.md（作为门控证据）

---

### REQ-NFR-007（新增）：Token 脱敏强制规范

**来源**：DEPLOYREP-LOBSTER-001 §4（Token 泄露事件）

**描述**：
凡涉及生成、显示、传递 40 位 hex Token（DRF Token 格式 `[a-f0-9]{40}`）的所有操作，
**必须**在显示之前经过全文正则脱敏：

```bash
# 标准脱敏命令（适用于所有 stdout/stderr 管道）
command_that_may_print_token | sed -E 's/[a-f0-9]{40}/[REDACTED-40HEX]/g'
```

**适用范围**：
- management command 输出（`create_openclaw_agent_user` 等）
- deployment 脚本中所有打印 Token 的操作
- 任何会在对话上下文中显示 Token 的操作

**约束**：
- 脱敏适用于命令的所有 stdout **和** stderr 输出（不只过滤特定行）
- 单行 grep 过滤（`grep -v "TOKEN = "`）不满足本要求
- deployment_plan_v2.md 必须在 §4（账号配置段）强制引用本规范

**验收标准**：

- Given：执行任意 management command 且该命令输出中包含 Token
- When：命令输出经管道传递
- Then：所有 40 字符 hex 字符串被替换为 `[REDACTED-40HEX]`，Claude 对话上下文中不出现明文 Token

---

## 5. CONFIRM 决策修订汇总

### 保留的 CONFIRM 决策（不变）

以下第一轮用户确认的决策在 v2 中**继续有效**：

| 决策编号 | 原内容摘要 | v2 状态 |
|---------|----------|---------|
| CONFIRM-2 | Skill 分层：Tier-1 只读无需确认，Tier-2 写操作需二次确认 | 保留有效 |
| CONFIRM-3 | 全部高危写操作纳入 Skill，且全部需要二次确认 | 保留有效 |
| CONFIRM-4 | 知识注入：System Prompt MVP，RAG 不在本次范围 | 保留有效 |
| CONFIRM-5 | 8 个知识模块完整实施 | 保留有效 |
| CONFIRM-6 | 专属服务账号 openclaw-agent（已上线，不变） | 保留有效 |
| CONFIRM-7 | operator 字段格式 openclaw-agent::<chatuser>（已上线，不变） | 保留有效 |

### 修订的 CONFIRM 决策

**CONFIRM-1（措辞更新）**：

| 项目 | v1 | v2 |
|------|----|----|
| 通道架构 | Skill HTTP loopback 直调（OpenClaw Node.js Skill 调用） | Skill HTTP loopback 直调（从 SKILL.md exec 的 CLI 工具发起 HTTP 请求到 FreeArk REST） |
| 实现载体 | Node.js index.js 内调用 fetch | Python/Bash CLI 脚本（语言由 system-architect 基于实测决定），由 SKILL.md 的 exec 字段调用 |
| Token 读取 | process.env.FREEARK_AGENT_TOKEN | CLI 子进程环境变量或 OpenClaw secrets 段（由 system-architect 确定） |

### 作废的 CONFIRM 决策

**CONFIRM-8（作废）**：

| 项目 | 原决策 | 状态 |
|------|-------|------|
| Skill 代码语言 | Node.js（OpenClaw 原生） | **作废** — OpenClaw Skill 机制不是 Node.js 包，该决策基于错误前提 |

**新决策（替代 CONFIRM-8，待 system-architect 实测后提出）**：
- system-architect 在读取至少 3 个 bundled SKILL.md 示例并分析 CLI 执行协议后，
  提出 CLI 执行体语言选择（Python / Bash / 其他）的建议 ADR
- 用户在 architecture_design_v2.md 门控评审时确认该 ADR

---

## 6. 变更影响分析

### 不受影响的已上线代码（禁止修改）

| 文件 | 已上线改动 | 本次 v2 不涉及 |
|------|----------|--------------|
| `api/consumers.py` | chatuser 前缀注入 | 不改 |
| `api/serializers_device_settings.py` | operator_override 字段 | 不改 |
| `api/views_device_settings.py` | effective_operator 落库 | 不改 |
| FreeArk DB | openclaw-agent 服务账号 id=8 | 不改 |

### 需要重做的产物（第一轮报废）

| 报废产物 | 原因 | 替代 |
|---------|------|------|
| `agents/freeark-skill/index.js` | 错误架构（Node.js 包）| 由 system-architect 决定是否归档或删除 |
| `agents/freeark-skill/client.js` | 同上 | 同上 |
| `agents/freeark-skill/tools/tier1_readonly.js` | 同上 | 同上 |
| `agents/freeark-skill/tools/tier2_write.js` | 同上 | 同上 |
| `agents/freeark-skill/package.json` | 同上 | 同上 |
| `architecture_design.md ADR-005` | 基于错误前提（Node.js Skill）| `architecture_design_v2.md` 新 ADR |
| `module_design.md MOD-SK-01` | 基于错误架构（Node.js 包结构）| `module_design_v2.md` 新 MOD-SK-01 |

---

## 附录 C：RISK 登记更新

| 风险 ID | 状态变更 | 说明 |
|---------|---------|------|
| RISK-001 | REALIZED → MITIGATED（通过 REQ-NFR-006 PoC 强制验证） | 下一轮开发必须先 PoC 再扩展 |
| RISK-002 | OPEN（未变） | System Prompt token 长度，架构阶段复核 |
| RISK-003 | OPEN（未变） | Tier-2 LLM 二次确认机制 |
| RISK-004 | OPEN（未变） | Token 意外打印，REQ-NFR-007 降低概率 |
| RISK-3 (TOKEN 泄露) | REALIZED → CLOSED（已轮换 + REQ-NFR-007 预防复发） | 闭环处置完成 |
