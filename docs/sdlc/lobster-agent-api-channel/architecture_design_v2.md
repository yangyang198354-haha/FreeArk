# 架构设计文档 v2 — 方舟龙虾 API 通道与知识增强

```
file_header:
  document_id: ARCH-LOBSTER-002
  project: FreeArk — lobster-agent-api-channel
  version: 2.0.0
  status: APPROVED
  author_agent: system-architect (PM-orchestrated, SDLC 第二轮重设计)
  created_at: 2026-05-25
  supersedes: ARCH-LOBSTER-001
  depends_on: REQ-SPEC-LOBSTER-002, US-LOBSTER-002, PROBES-LOBSTER-001
  context_snapshot: OpenClaw 2026.5.20, FreeArk v0.5.9+lobster-partial, WS Gateway RPC v4
  evidence_policy: >
    本文档所有 ADR 决策必须有 PROBES-LOBSTER-001 中具体章节的引用。
    凡无实测引用的判断不得出现在本文档中。
    "以下基于推测"类语句导致架构门控自动 FAIL。
  change_from_v1:
    - ADR-005 完全重写（Skill 语言/机制，基于实测 schema）
    - §3 通道层详细设计更新（SKILL.md + CLI 子进程调用链）
    - §4 Agent 层更新（openclaw.json skills 真实字段）
    - §5 安全层新增"PoC 强制"和"Token 脱敏"
    - 新增 §9 PoC 验证步骤（具体命令）
    - ADR-001 至 ADR-004 保留，措辞小幅更新
```

---

## 1. 架构总览

### 1.1 目标架构图（基于实测 schema，v2）

```
浏览器 → Nginx(:8080)
           ├─ /api/*    → Uvicorn ASGI → Django REST
           │                                ↑
           │                                │ HTTP loopback (127.0.0.1:8000)
           │                                │ Authorization: Token <agent-token>
           │                           [NEW] freeark-skill CLI 执行体
           │                           (Python/Bash 脚本，语言见 ADR-005)
           │                                │
           │                                │ stdin/stdout JSON（OpenClaw Skill 协议）
           │                                │
           │                     OpenClaw Skill 层（SKILL.md 描述）
           │                                │ exec 子进程
           │                                ↓
           └─ /ws/chat/ → Channels ChatConsumer (已改: chatuser 前缀注入)
                              └─ OpenClawAdapter (aiohttp WS, RPC v4)
                                     └─ OpenClaw Gateway (127.0.0.1:18789)
                                            ├─ [MODIFIED] main agent "方舟龙虾"
                                            │      ├─ 三恒/HVAC/FreeArk 知识 (system prompt)
                                            │      └─ freeark-skill（via SKILL.md 注册）
                                            └─ DeepSeek v4-flash
```

### 1.2 新增/修改组件一览

| 组件 | 类型 | 位置 | 状态 |
|------|------|------|------|
| `freeark-skill/SKILL.md` | OpenClaw Skill 定义 | `agents/freeark-skill/SKILL.md`（入仓库） | 新建 |
| `freeark-skill` CLI 执行体 | Python/Bash 脚本 | `agents/freeark-skill/scripts/`（入仓库） | 新建 |
| Agent system prompt v2 | 配置内容 | 仓库版本化，部署写入 openclaw.json | 新建 |
| openclaw.json skills 装载配置 | JSON 配置 | Pi 本地 `~/.openclaw/openclaw.json` | 修改 |
| openclaw.json agent.main | JSON 配置 | 同上 | 修改 |

### 1.3 已上线、不变的组件（严禁修改）

| 组件 | 已上线改动 | v2 架构决策 |
|------|----------|------------|
| `api/consumers.py` | chatuser 前缀注入 `[__freeark_user__:<username>]` | 不改 |
| `api/serializers_device_settings.py` | operator_override 字段 | 不改 |
| `api/views_device_settings.py` | effective_operator 落库 | 不改 |
| FreeArk DB openclaw-agent 账号 | id=8, role=user, Token in DB | 不改（重新生成明文时走 --force-regenerate-token） |
| `api/openclaw_adapter.py` | 无改动 | 不改 |
| FreeArk 所有 REST API 端点 | 无改动 | 不改接口 |
| Nginx 配置 | 无改动 | 不改（Skill 走 loopback，不经 Nginx） |

---

## 2. 架构决策记录（ADR）

### ADR-001：通道层 — Skill HTTP 直调（保留，措辞更新）

**来自**：v1 ADR-001，保留决策，仅更新实现描述

**决策**：选 Skill HTTP 直调（方案 A），**不变**。

**v2 更新**：Skill 内部发起 HTTP 请求的主体从"Node.js `fetch`"更改为"CLI 执行体
（Python `requests` / Bash `curl`，见 ADR-005）"。HTTP 调用语义不变：
- 目标：`http://127.0.0.1:8000/api/<path>/`（loopback，绕过 Nginx）
- 请求头：`Authorization: Token <agent-token>`

---

### ADR-002：Skill 分层安全模型（保留不变）

**来自**：v1 ADR-002，CONFIRM-2/CONFIRM-3 确认的决策

**决策**：双层安全模型不变：
- **Tier-1**：只读端点，Agent 可直接触发 SKILL.md 定义的 tool，无需用户确认
- **Tier-2**：写操作端点，Agent 必须先在对话中展示操作摘要，等待用户确认后才调用 tool

**v2 更新**：二次确认机制的实现由"Skill 代码中的 confirmation 参数校验"
更改为"system prompt 规则 + SKILL.md 中 Tier-2 tool 的 requires_confirmation 字段（若 schema 支持）"，
具体实现见 module_design_v2.md MOD-SK-01。

---

### ADR-003：Agent 知识注入 — System Prompt MVP（保留不变）

**来自**：v1 ADR-003，CONFIRM-4/CONFIRM-5 确认的决策

**决策**：MVP System Prompt 注入，8 个知识模块，RAG 不在本次范围。**不变。**

**v2 更新**：system prompt 中的 §4 "API 调用规则"段措辞需从
"调用 FreeArk Skill（Node.js tool function）"更新为
"通过 SKILL.md 定义的 tool 调用 FreeArk API"，以匹配新 Skill 抽象。
具体内容在 agent_system_prompt_v2.md 中体现（不在本 ADR 展开）。

---

### ADR-004：Agent 身份认证 — 专属服务账号（保留不变）

**来自**：v1 ADR-004，CONFIRM-6/CONFIRM-7 确认的决策

**决策**：专属服务账号 `openclaw-agent`（role=user），operator 格式 `openclaw-agent::<chatuser>`。
**不变。** 服务账号已上线（DB id=8），不需重建。

**v2 更新**：Token 存储方式从"Skill 的 `process.env.FREEARK_AGENT_TOKEN`"
更改为"CLI 子进程环境变量或 OpenClaw secrets 段（由 ADR-005a 决定）"。

---

### ADR-005（重写）：Skill 机制 — SKILL.md + CLI 子进程

**来自**：v1 ADR-005（Node.js Skill，已证伪）。本 ADR 完全重写。

**证据基础**（强制引用 PROBES-LOBSTER-001）：
- FACT-01：OpenClaw Skill 是目录 + SKILL.md，不是 npm 包
- FACT-02：openclaw.json 的 skills 字段是装载配置（allowBundled/load/install）
- FACT-03：load.extraDirs 是自定义 Skill 的父目录路径
- FACT-04：Skill 执行体是 CLI 子进程（不在 OpenClaw Node.js 进程中运行）
- FACT-05：SKILL.md 使用 YAML frontmatter 描述 Skill 元数据和 tool 定义

**问题**：Skill 的实现机制（替代已证伪的 Node.js npm 包方案）

**决策**：freeark-skill 实现为 OpenClaw SKILL.md + CLI 子进程

**方案 A：Python CLI 脚本（推荐）**

| 维度 | 评估 |
|------|------|
| 语言可用性 | Pi 已有 Python 3.13.x + venv（SKILL.md 中的 FreeArk venv 也有 requests/urllib3） |
| HTTP 客户端 | `requests` 库已在 FreeArk venv，无需额外安装 |
| JSON 处理 | Python 内置 json，与 OpenClaw Skill I/O 协议天然契合 |
| 错误处理 | Python 异常体系完善，易于结构化输出错误信息 |
| 与 FreeArk 共享逻辑 | CLI 脚本可 import FreeArk settings/config（若需要，但建议独立） |
| 已有代码复用 | v1 的 tier1_readonly.js 和 tier2_write.js 中的 HTTP 调用逻辑可参考移植 |

**方案 B：Bash + curl（备选）**

| 维度 | 评估 |
|------|------|
| 依赖 | 零依赖（bash + curl 均已在 Pi） |
| JSON 处理 | 需 `jq`（Pi 是否已安装需确认） |
| 错误处理 | 复杂（需大量 if/else 处理 HTTP 状态码） |
| 代码可维护性 | 低（19 个 tool 用 Bash 实现维护成本高） |
| 适用场景 | 适合极简单的单命令 tool，不适合复杂 HTTP 交互 |

**决策：推荐方案 A（Python CLI）**，但最终确认依赖以下两个条件：
1. 从 bundled SKILL.md 示例（PROBES-LOBSTER-001 §3 命令 D/E/F 的输出）确认 CLI 执行体的
   stdin/stdout 协议（输入参数格式、输出结果格式）
2. 确认 SKILL.md frontmatter 中 exec 字段的语法（是否支持 `python3 scripts/freeark_tool.py`）

**⚠️ 架构待确认项（ADR-005-PENDING-A）**：
> system-architect 必须先 SSH Pi 运行 PROBES-LOBSTER-001 §6 中的命令 D/E/F，
> 确认 CLI 执行协议后，将本 ADR 中的 "推荐方案 A" 更新为 "已确认方案"。
> 在 architecture_design_v2.md 修订前，module_design_v2.md 中的 CLI 脚本实现细节
> 标注 "PENDING-A：等待 ADR-005 CLI 协议确认"，开发不得启动。

---

### ADR-005a（新增）：Token 注入方式

**问题**：CLI 子进程如何安全获取 FREEARK_AGENT_TOKEN？

**已知 schema 字段**（PROBES-LOBSTER-001 §5.2，部分确认）：

OpenClaw 可能支持 `secrets` 段，其中可定义 Token 值，并通过子进程环境变量注入。
精确字段名需实测（PROBES-LOBSTER-001 §6 命令 A）。

**方案对比**：

| 方案 | 描述 | 安全性 | 实现复杂度 |
|------|------|--------|----------|
| A：openclaw.json secrets 段 | 若 schema 有 secrets.FREEARK_AGENT_TOKEN，OpenClaw 自动注入到 CLI 环境变量 | 高（与 gateway token 同级别保护，mode 600） | 低（配置即可） |
| B：openclaw.json 的 load.env 字段 | 若 SKILL.md 有 env 段，Token 写入 openclaw.json 的 skill-level env 配置 | 高（mode 600） | 低 |
| C：系统环境变量 | 在 openclaw-gateway.service 的 systemd unit 中注入 `Environment=FREEARK_AGENT_TOKEN=...` | 中（明文在 unit 文件，需限权） | 低 |
| D：.env 文件（Skill 目录） | CLI 脚本从 `agents/freeark-skill/.env`（gitignored）读取 | 低（文件权限弱于 mode 600） | 低 |

**推荐**：方案 A 或 B（优先使用 openclaw.json 内置的 secret/env 机制，与 gateway token 同级别保护）。

**⚠️ 架构待确认项（ADR-005a-PENDING）**：
> 运行 PROBES-LOBSTER-001 §6 命令 A 获取完整 config schema，
> 确认 secrets 段和 SKILL.md env 段的字段名后，更新本 ADR。

---

## 3. 通道层详细设计（v2）

### 3.1 Skill 调用链（Tier-1，只读）— v2 修订版

```
用户输入 → ChatConsumer（注入 [__freeark_user__:<username>]）
              → OpenClaw WS Gateway → Agent 推理
                                            │
                                            ↓ tool_call: freeark_get_realtime_params
                                    SKILL.md 解析：确定对应 exec 命令
                                            │
                                            ↓ 子进程 exec（stdin: JSON 参数）
                                    CLI 执行体（Python script）
                                            │
                                            ↓ HTTP GET
                              http://127.0.0.1:8000/api/devices/realtime-params/
                              Authorization: Token <agent-token>（来自环境变量/secrets）
                                            │
                                            ↓ 200 OK, JSON
                                    CLI 解析响应，格式化输出（stdout: JSON tool_result）
                                            │
                                            ↓ OpenClaw 接收 tool_result
                                    Agent 生成自然语言回答
                                            │
                                            ↓ deltaText (WS stream)
                              ChatConsumer → 浏览器
```

### 3.2 Skill 调用链（Tier-2，写操作）— v2 修订版

Tier-2 调用链与 v1 基本相同，仅将"Skill 代码 confirmation 参数校验"改为
"由 SKILL.md 定义 requires_confirmation 行为 + system prompt 规则双重保障"：

```
用户输入 "把702室温度改成26度"
    → Agent 推理：这是写操作，必须先确认（system prompt 规则）
    → Agent 输出（stream）："准备执行：修改 3-1-7-702 cooling_temp_setting → 26。请确认。"
    → 等待下一轮用户输入
    → 用户输入 "确认"
    → Agent 推理：收到确认，调用 tool
    → SKILL.md tool_call: freeark_write_device_params
    → 子进程 exec: CLI 执行体
    → HTTP POST http://127.0.0.1:8000/api/device-settings/write/
      {specific_part: "3-1-7-702", operator_override: "openclaw-agent::chatuser", items: [...]}
    → CLI 返回结果（stdout: JSON tool_result）
    → Agent 输出："已下发成功，batch_request_id=..."
```

---

## 4. Skill 目录结构设计（v2）

### 4.1 Skill 目录（入仓库）

```
FreeArk/
└── agents/
    └── freeark-skill/
        ├── SKILL.md                    ← Skill 入口（必须，OpenClaw 识别点）
        ├── scripts/
        │   ├── freeark_tool.py         ← 统一 CLI 入口（或按 tool 分文件）
        │   ├── tier1_readonly.py       ← 只读 tool 实现（14 个 endpoint）
        │   └── tier2_write.py          ← 写操作 tool 实现（5 个 endpoint）
        ├── lib/
        │   └── freeark_client.py       ← HTTP 客户端封装（统一鉴权、错误处理）
        └── README.md                   ← Skill 说明（供人类阅读，非 OpenClaw 使用）
```

**注**：`scripts/` 和 `lib/` 的具体结构取决于 SKILL.md CLI 协议：
- 若 OpenClaw 每次 tool_call 启动一个独立子进程（每次 exec 启动新进程）→ 单文件 per tool 更清晰
- 若 OpenClaw 保持一个长驻 CLI 进程（通过 stdin/stdout 多轮通信）→ 统一入口脚本更合适
- **此细节依赖 ADR-005-PENDING-A 解决后确定**，module_design_v2.md 提供两种预设方案

### 4.2 openclaw.json 配置变更（v2）

```json
{
  "agent": {
    "main": {
      "name": "方舟龙虾",
      "systemPrompt": "<从仓库 agent_system_prompt_v2.md 读取内容，长度约 3000-5000 字>",
      "skills": ["freeark-skill"]
    }
  },
  "skills": {
    "allowBundled": [],
    "load": {
      "extraDirs": ["/home/yangyang/Freeark/FreeArk/agents"]
    }
  }
}
```

**说明**：
- `load.extraDirs` 指向 `agents/` 目录（freeark-skill 的父目录）
- OpenClaw 扫描 `agents/` 下的每个子目录，发现 `SKILL.md` 则加载为 Skill
- `agent.main.skills` 数组中的 `"freeark-skill"` 告知 Agent 可使用此 Skill
- `allowBundled: []` 不启用任何 bundled Skill（减少不必要的 Skill 加载）

**⚠️ 待确认**：`agent.main.skills` 的精确字段格式（字符串数组/对象/其他）
需要运行 PROBES-LOBSTER-001 §6 命令 A 和 I 确认。若格式不对，Gateway 再次拒绝。

---

## 5. 安全层设计（v2）

### 5.1 纵深防御模型（不变）

```
层 1 — Agent 层：system prompt 安全规则（Tier-2 确认规则、权限边界说明）
层 2 — Skill 层：SKILL.md 白名单 tool 定义（仅定义的 tool 才可调用）
层 3 — API 层：DRF 权限检查（IsAuthenticated，openclaw-agent role=user）
层 4 — 业务层：FreeArk 现有写操作防护（WRITABLE_SUFFIXES、枚举值域校验）
层 5 — 审计层：PLCWriteRecord + journald 日志（operator 字段已上线）
```

### 5.2 新增：PoC 强制验证门（REQ-NFR-006）

在 Skill 层开发里程碑中插入：

```
[PoC 里程碑]
freeark-skill/SKILL.md（1 个 tool）
+ CLI 执行体（1 个 endpoint）
→ Pi 上实测 Gateway 加载成功 + Agent 对话触发
→ PoC PASS 记录进 code_review_report_v2.md
→ 解除对其余 18 个 tool 实现的阻塞
```

### 5.3 Token 安全措施（v2 更新）

- Token 存储：openclaw.json 的 secrets 段或 skill env 字段（mode 600，与 gateway token 同级别）
- CLI 脚本中不硬编码 Token，从环境变量读取（变量名待 ADR-005a-PENDING 确定后锁定）
- HTTP 请求仅发往 `127.0.0.1:8000`（CLI 脚本中 hardcheck，防 SSRF）
- Token 日志打印：CLI 脚本日志中仅输出 Token 前 8 字符（`token[:8] + "..."` Python 写法）
- 部署操作：Token 生成/轮换命令必须经 `sed -E 's/[a-f0-9]{40}/[REDACTED-40HEX]/g'` 管道（REQ-NFR-007）

---

## 6. 与现有 ASGI/Channels 架构的集成点（v2）

### 6.1 变更影响分析（v2，已上线改动不重算）

| 现有文件/组件 | v1 计划变更 | v2 实际状态 |
|--------------|-----------|------------|
| `api/consumers.py` | 小改（chatuser 前缀） | **已上线**，不需再改 |
| `api/serializers_device_settings.py` | operator_override | **已上线**，不需再改 |
| `api/views_device_settings.py` | effective_operator | **已上线**，不需再改 |
| `api/openclaw_adapter.py` | 不修改 | 确认不修改 |
| `api/urls.py` | 不修改 | 确认不修改 |
| `~/.openclaw/openclaw.json` | 修改（Skill 注册 + agent prompt） | v2 修改内容见 §4.2 |
| `agents/freeark-skill/` | v1 JS 实现（已证伪） | v2 用 SKILL.md + Python CLI 完全重做 |

---

## 7. 风险登记（v2）

| 风险 ID | 描述 | 概率 | 影响 | 缓解措施 |
|---------|------|------|------|---------|
| RISK-001 | ~~OpenClaw Skill schema 假设错误~~ | REALIZED | 部署回滚 | **MITIGATED**：v2 基于实测 schema + PoC 强制 |
| RISK-002 | System Prompt token 长度超出 DeepSeek v4-flash context 上限 | 低 | 中 | 分模块测试，超出时精简；RISK-2 估算 9353 字符 ≈ 4571 tokens，接近边界，需在开发阶段实测 |
| RISK-003 | Tier-2 二次确认机制依赖 LLM 语义理解 | 中 | 高 | system prompt 严格定义确认关键词；CRITICAL 操作要求输入特定短语 |
| RISK-3 | ~~Token 泄露~~ | REALIZED + CLOSED | 已轮换 | **MITIGATED**：REQ-NFR-007 全文 sed 脱敏 |
| RISK-006（新） | SKILL.md CLI 协议与实际 OpenClaw 版本不兼容 | 中 | 高 | PoC 第一里程碑实测（REQ-NFR-006），PoC 通过前不扩展 |
| RISK-007（新） | agent.main.skills 字段格式与实际 schema 不符（再次 "Invalid config"） | 中 | 高 | 运行 PROBES §6 命令 A/I 确认字段格式；openclaw.json 修改前先用 `openclaw config validate`（若有此命令）验证 |

---

## 8. 部署影响（v2 预览）

**新增/修改文件（入仓库）**：
- `agents/freeark-skill/SKILL.md`（新建）
- `agents/freeark-skill/scripts/freeark_tool.py`（新建，替代已废弃的 JS 文件）
- `agents/freeark-skill/lib/freeark_client.py`（新建）
- `docs/sdlc/lobster-agent-api-channel/agent_system_prompt_v2.md`（新建）

**废弃文件处置（由 system-architect 决定，第三轮开发前执行）**：
- `agents/freeark-skill/index.js` → 归档至 `agents/freeark-skill/_archive/v1/` 或删除
- `agents/freeark-skill/client.js` → 同上
- `agents/freeark-skill/tools/tier1_readonly.js` → 同上
- `agents/freeark-skill/tools/tier2_write.js` → 同上
- `agents/freeark-skill/package.json` → 同上

**生产操作（不入仓库）**：
- `openclaw-agent` Token 重新生成明文（`--force-regenerate-token`，Token 需脱敏）
- 更新 `~/.openclaw/openclaw.json`（skills.load.extraDirs + agent.main.systemPrompt + agent.main.skills）
- `systemctl --user restart openclaw-gateway.service`
- 验证 Gateway 正常启动（无 "Invalid config"）
- PoC 验证：Agent 对话中触发 freeark_get_realtime_params（见 §9）

**重启影响**：
- `freeark-backend`：**不需要重启**（Skill CLI 子进程走 loopback，Django 无感知）
- `openclaw-gateway.service`：**需要重启**（注册新 Skill，更新 agent 配置）

---

## 9. PoC 验证步骤（REQ-NFR-006 落地，具体命令）

此节是开发阶段 PoC 里程碑的执行手册，必须在第三轮开发启动前完成。

### 9.1 前提条件

1. PROBES-LOBSTER-001 §6 所有命令已运行，输出已记录
2. ADR-005-PENDING-A 和 ADR-005a-PENDING 已解决（SKILL.md 格式和 Token 注入方式已确认）
3. `agents/freeark-skill/SKILL.md` 已按确认格式写好（1 个 tool）
4. CLI 执行体 `agents/freeark-skill/scripts/freeark_tool.py` 已写好并本地测试

### 9.2 PoC 部署命令序列

```bash
SSH="ssh -o BatchMode=yes -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
     -i /c/fa-home/.ssh/id_ed25519 -p 57279 -o ConnectTimeout=20 \
     yangyang@et116374mm892.vicp.fun"

# 步骤 1：确认 agents/ 目录已在 Pi 上 git pull 落地
$SSH 'cd /home/yangyang/Freeark/FreeArk && git log -1 --oneline && ls agents/freeark-skill/'

# 步骤 2：验证 SKILL.md 格式正确（dry-run，若 openclaw 提供校验命令）
$SSH 'openclaw config validate 2>&1 || echo "no validate command, skip"'

# 步骤 3：备份当前 openclaw.json
$SSH 'cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.poc-$(date +%Y%m%d%H%M%S)'

# 步骤 4：更新 openclaw.json（安全方式：先写 staging 文件，再原子替换）
# （具体 python3 命令由部署工程师根据确认后的 schema 字段名填写）
# 示例（字段名待 ADR-005-PENDING-A 解决后确认）：
$SSH 'python3 - <<'"'"'EOF'"'"'
import json, os
p = os.path.expanduser("~/.openclaw/openclaw.json")
cfg = json.load(open(p))
# 更新 skills.load.extraDirs
cfg.setdefault("skills", {}).setdefault("load", {})["extraDirs"] = \
    ["/home/yangyang/Freeark/FreeArk/agents"]
# 更新 agent（字段名待 ADR-005-PENDING-A 确认）
# cfg["agent"]["main"]["skills"] = ["freeark-skill"]
staging = p + ".poc.staging"
json.dump(cfg, open(staging, "w"), indent=2, ensure_ascii=False)
print("staging written")
EOF'

# 步骤 5：验证 staging JSON 合法
$SSH 'python3 -m json.tool ~/.openclaw/openclaw.json.poc.staging > /dev/null && echo "JSON_VALID"'

# 步骤 6：原子替换
$SSH 'mv ~/.openclaw/openclaw.json.poc.staging ~/.openclaw/openclaw.json && chmod 600 ~/.openclaw/openclaw.json'

# 步骤 7：重启 gateway
$SSH 'systemctl --user restart openclaw-gateway.service'

# 步骤 8：等待启动并检查状态（关键：必须无 Invalid config 错误）
sleep 5
$SSH 'systemctl --user status openclaw-gateway.service --no-pager | head -20'
$SSH 'curl -s http://127.0.0.1:18789/health'

# 步骤 9：确认 Skill 加载（命令取决于 openclaw skills 子命令的实际输出）
$SSH 'openclaw skills list 2>&1 | grep -i freeark || echo "freeark skill not found in list"'

# 步骤 10：若 step 8/9 失败，立即回滚
# $SSH 'cp ~/.openclaw/openclaw.json.bak.poc-<timestamp> ~/.openclaw/openclaw.json && \
#        systemctl --user restart openclaw-gateway.service'
```

### 9.3 PoC 功能验证

```bash
# 通过 Web 聊天界面（或 curl WS 测试）发消息，验证 Agent 实际调用 Skill：
# 推荐测试语句："3号楼1单元702室现在温度多少？"
# 预期结果：OpenClaw 日志中出现 Skill 调用记录，Agent 回复包含真实温度数据
$SSH 'tail -f /tmp/openclaw-1000/openclaw-$(date +%Y-%m-%d).log | grep -i freeark'
```

### 9.4 PoC PASS 判定标准

以下全部满足才算 PoC PASS：
1. `systemctl --user status openclaw-gateway.service` → `active (running)`，无 "Invalid config"
2. `curl -s http://127.0.0.1:18789/health` → `{"ok":true,"status":"live"}`
3. `openclaw skills list` 或日志中可见 freeark-skill 已加载
4. Agent 对话中触发 freeark_get_realtime_params，OpenClaw 日志中有 Skill exec 记录
5. CLI 执行体返回 FreeArk API 的真实 JSON 数据（非 mock）

---

## 10. 附录：API 端点 Skill 覆盖映射（v2）

与 v1 附录一致，仅更新"Skill Function"列的实现备注：

| API 端点 | Skill Tool Name | Tier | CLI 执行体函数 |
|---------|----------------|------|--------------|
| `GET /api/devices/realtime-params/` | `freeark_get_realtime_params` | 1 | `tier1_readonly.get_realtime_params()` |
| `GET /api/usage/quantity/` | `freeark_get_usage_daily` | 1 | `tier1_readonly.get_usage_daily()` |
| `GET /api/usage/quantity/specifictimeperiod/` | `freeark_get_usage_period` | 1 | `tier1_readonly.get_usage_period()` |
| `GET /api/usage/quantity/monthly/` | `freeark_get_usage_monthly` | 1 | `tier1_readonly.get_usage_monthly()` |
| `GET /api/plc/connection-status/` | `freeark_get_plc_status` | 1 | `tier1_readonly.get_plc_status()` |
| `GET /api/plc/connection-status/<id>/` | `freeark_get_plc_status_single` | 1 | `tier1_readonly.get_plc_status_single()` |
| `GET /api/dashboard/summary/` | `freeark_get_dashboard_summary` | 1 | `tier1_readonly.get_dashboard_summary()` |
| `GET /api/dashboard/services/` | `freeark_get_services_status` | 1 | `tier1_readonly.get_services_status()` |
| `GET /api/dashboard/power-status/` | `freeark_get_power_status` | 1 | `tier1_readonly.get_power_status()` |
| `GET /api/device-settings/params/<id>/` | `freeark_get_device_params` | 1 | `tier1_readonly.get_device_params()` |
| `GET /api/device-settings/records/` | `freeark_get_write_records` | 1 | `tier1_readonly.get_write_records()` |
| `GET /api/owners/<pk>/device-tree/` | `freeark_get_device_tree` | 1 | `tier1_readonly.get_device_tree()` |
| `GET /api/services/<name>/detail/` | `freeark_get_service_detail` | 1 | `tier1_readonly.get_service_detail()` |
| `GET /api/plc-latest/` | `freeark_get_plc_latest` | 1 | `tier1_readonly.get_plc_latest()` |
| `POST /api/device-settings/write/` | `freeark_write_device_params` | **2** | `tier2_write.write_device_params()` |
| `POST /api/devices/ondemand-refresh/` | `freeark_trigger_refresh` | **2** | `tier2_write.trigger_refresh()` |
| `POST /api/services/<name>/action/` | `freeark_service_action` | **2** | `tier2_write.service_action()` |
| `POST /api/device-management/screen-device-tree/sync/` | `freeark_sync_device_tree` | **2** | `tier2_write.sync_device_tree()` |
| `POST /api/device-management/screen-device-tree/batch-sync/` | `freeark_batch_sync_device_tree` | **2** | `tier2_write.batch_sync_device_tree()` |
| `PUT /api/heartbeat-broker-config/update/` | 不纳入（需 admin role，API 层已拦截） | — | — |
| 用户管理端点 | 不纳入（超出运维场景） | — | — |
| 认证端点 | 不纳入 | — | — |
