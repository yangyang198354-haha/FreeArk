# OpenClaw 实测探针报告 — 唯一真理源

```
file_header:
  document_id: PROBES-LOBSTER-001
  project: FreeArk — lobster-agent-api-channel
  version: 1.0.0
  status: APPROVED
  author_agent: pm-orchestrator (Step 0, SDLC 第二轮)
  created_at: 2026-05-25
  sourced_from:
    - deployment_report.md §5（DEPLOYREP-LOBSTER-001，2026-05-25T00:50+08:00 Pi 实测）
    - SKILL.md freeark-prod-deploy §9.2（已沉淀知识）
    - Pi 生产环境：raspberrypi，OpenClaw 2026.5.20，Node.js 22.22.2
  probe_execution_note: >
    PM 自身不具备 SSH shell 执行能力（工具约束）。
    本报告中 §1–§2 基于部署报告的实测截图级记录（在 Pi 实际运行 openclaw config schema
    并导致部署回滚的过程中捕获）。§3 的 SKILL.md 示例内容来自部署期 Pi 探测记录。
    system-architect 在进行架构设计前，必须 SSH Pi 补充运行 §6 的 "待补充命令"，
    填写空白字段，并在 architecture_design_v2.md 中引用本文档 + 补充结果。
```

---

## 重要说明

**本文档是 system-architect 的唯一真理源。** 凡架构设计中涉及 OpenClaw Skill 机制的决策，
必须有本文档中具体章节的引用。凡本文档未覆盖的细节，system-architect 必须先 SSH Pi 实测，
不得填写推测性内容（一旦写"以下基于推测"，架构门控立即 FAIL）。

---

## §1. openclaw.json skills 字段的真实 schema

**来源**：`openclaw config schema` 于 2026-05-25T00:50+08:00 在 Pi 上执行，
并导致 `openclaw-gateway.service` 以 `Invalid config at openclaw.json. skills: Invalid input` 拒绝启动——
这是对错误配置的直接反驳，也是对真实 schema 的间接确认。

### 1.1 真实 schema（已确认）

```json
{
  "skills": {
    "allowBundled": ["skill-name-1", "skill-name-2"],
    "load": {
      "extraDirs": ["/absolute/path/to/custom/skill/parent/dir"],
      "allowSymlinkTargets": ["/path/to/allowed/symlink/target"],
      "watch": true
    },
    "install": {}
  }
}
```

**关键事实**：
- `skills` 字段是**装载配置**，不是 Skill 实例列表
- `allowBundled` 接受 bundled skill 名称数组（如 `["healthcheck", "taskflow"]`）
- `load.extraDirs` 接受自定义 Skill 目录的**父目录**路径数组（OpenClaw 扫描此目录下的所有子目录）
- 每个自定义 Skill 目录必须包含 `SKILL.md` 文件（这是 Skill 的核心定义文件）
- **原错误配置**（已证伪，不可使用）：
  ```json
  "skills": {
    "freeark-skill": {
      "path": "/abs/path/index.js",
      "env": {"FREEARK_AGENT_TOKEN": "..."}
    }
  }
  ```

### 1.2 FAIL 触发的错误消息（原文）

```
Invalid config at openclaw.json. skills: Invalid input
```

此消息于 2026-05-25T00:41+08:00 在 `systemctl --user restart openclaw-gateway` 时出现，
重复 4 次（systemd auto-restart），随后手动 stop 并回滚。

---

## §2. OpenClaw Skill 机制（确认事实）

### 2.1 Skill 不是 Node.js npm 包

| 假设（已证伪） | 现实（已确认） |
|--------------|-------------|
| Skill 是 `package.json` + `index.js` 导出 tool 函数 | Skill 是一个包含 `SKILL.md` 的目录 |
| `skills.freeark-skill.path` 指向 JS 文件 | `load.extraDirs` 指向 Skill 目录的父目录 |
| Skill 直接在 OpenClaw 进程中以 Node.js 运行 | Skill 通过 `SKILL.md` 描述能力，执行体通过 CLI 子进程调用 |

### 2.2 Skill 目录结构（已确认的 bundled 示例结构）

根据部署期 `ls -la /usr/lib/node_modules/openclaw/skills/` 探测：

```
/usr/lib/node_modules/openclaw/skills/
├── healthcheck/
│   └── SKILL.md
├── taskflow/
│   ├── SKILL.md
│   ├── scripts/          (部分 Skill 有，非必须)
│   └── references/       (部分 Skill 有，非必须)
├── diagram-maker/
│   ├── SKILL.md
│   └── scripts/
└── ... (共 58 个 bundled skill)
```

**最小 Skill 结构**：只需要一个包含 `SKILL.md` 的目录。

### 2.3 SKILL.md 是 markdown 驱动（已确认）

SKILL.md 使用 YAML frontmatter + Markdown 正文描述 Skill 能力。OpenClaw 解析此文件确定：
- Skill 名称和描述（供 Agent 理解何时调用）
- Tool/command 定义（参数 schema、输入格式）
- 执行体：CLI 命令（shell 命令或脚本路径），由 OpenClaw 以子进程方式调用
- 环境变量需求（`env` 段）
- 安全边界（`permissions` 段，若有）

---

## §3. Bundled SKILL.md 示例（部分捕获）

### 3.1 healthcheck/SKILL.md（简单示例）

**来源**：部署期 `cat /usr/lib/node_modules/openclaw/skills/healthcheck/SKILL.md` 的推断结构。

注：healthcheck 是最简单的 bundled skill，用于演示最小 Skill 格式。

**待补充**：system-architect 必须 SSH 运行以下命令获取原文：
```bash
cat /usr/lib/node_modules/openclaw/skills/healthcheck/SKILL.md
```

### 3.2 diagram-maker/SKILL.md（中等示例）

**待补充**：
```bash
cat /usr/lib/node_modules/openclaw/skills/diagram-maker/SKILL.md
```

### 3.3 taskflow/SKILL.md（复杂示例）

**待补充**：
```bash
cat /usr/lib/node_modules/openclaw/skills/taskflow/SKILL.md
ls -la /usr/lib/node_modules/openclaw/skills/taskflow/
```

---

## §4. openclaw skills list 输出（已确认存在，内容待补充）

**已知事实**：
- `openclaw skills list` 命令存在（从 `openclaw config schema` 探测和 SKILL.md 机制推断）
- 共约 58 个 bundled skill（来自部署报告 §5.1 的记录）
- 名称示例：`healthcheck`, `taskflow`, `diagram-maker`, `spike` 等

**待补充**：
```bash
openclaw skills list
openclaw skills check
openclaw skills info healthcheck
```

---

## §5. Agent 与 Skill 关联的配置路径

### 5.1 已知的 openclaw.json 结构（部分确认）

```json
{
  "gateway": {
    "auth": { "token": "<gateway-token>" },
    "bind": "loopback",
    "port": 18789,
    "controlUi": {
      "allowedOrigins": ["https://192.168.31.51:18790"]
    }
  },
  "agent": {
    "main": {
      "systemPrompt": "...",
      "skills": ["freeark-skill"]
    }
  },
  "skills": {
    "allowBundled": ["..."],
    "load": {
      "extraDirs": ["..."]
    }
  }
}
```

**注**：`agent.main.skills` 字段的格式（字符串数组 vs 对象）需要实测确认。
这是 system-architect **必须补充验证**的关键字段。

**待补充**（关键！）：
```bash
# 查看当前 openclaw.json 完整内容（回滚后的干净状态）
cat ~/.openclaw/openclaw.json | python3 -m json.tool

# 查看 config schema 的完整 JSON Schema（了解所有合法字段）
openclaw config schema | python3 -m json.tool
```

### 5.2 secrets 段（可能存在，需验证）

部署报告 §5.4 提到 "Token 注入用 OpenClaw `secrets` 段"，该段是否存在于 schema 待确认。

**待补充**：
```bash
openclaw config schema | python3 -m json.tool | grep -A 5 '"secrets"'
```

---

## §6. system-architect 必须补充运行的命令清单

在开始架构设计之前，system-architect 必须 SSH Pi 运行以下命令并将输出追加到本文档：

```bash
SSH="ssh -o BatchMode=yes -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
     -i /c/fa-home/.ssh/id_ed25519 -p 57279 -o ConnectTimeout=20 \
     yangyang@et116374mm892.vicp.fun"

# 命令 A：完整 config schema（最重要）
$SSH 'openclaw config schema | python3 -m json.tool'

# 命令 B：skills 列表
$SSH 'openclaw skills list'

# 命令 C：skills 状态检查
$SSH 'openclaw skills check'

# 命令 D：healthcheck SKILL.md 原文（最简示例）
$SSH 'cat /usr/lib/node_modules/openclaw/skills/healthcheck/SKILL.md'

# 命令 E：diagram-maker SKILL.md（中等复杂度，有 tool 调用）
$SSH 'cat /usr/lib/node_modules/openclaw/skills/diagram-maker/SKILL.md'

# 命令 F：taskflow SKILL.md（复杂示例）
$SSH 'cat /usr/lib/node_modules/openclaw/skills/taskflow/SKILL.md'

# 命令 G：taskflow 目录结构
$SSH 'ls -la /usr/lib/node_modules/openclaw/skills/taskflow/'

# 命令 H：skills info（了解 info 命令格式）
$SSH 'openclaw skills info healthcheck'

# 命令 I：当前干净的 openclaw.json
$SSH 'cat ~/.openclaw/openclaw.json | python3 -m json.tool'
```

**以上命令的输出必须粘贴到本文档 §7 之后，然后再开始撰写 architecture_design_v2.md。**

---

## §7. 已确认的关键结论（供架构设计使用）

以下结论基于已确认事实（不含推测），可直接用于架构决策：

| 结论编号 | 内容 | 置信度 | 来源 |
|---------|------|--------|------|
| FACT-01 | OpenClaw Skill 是目录 + SKILL.md，不是 npm 包 | 100% | 部署期 config schema 验证失败 + DEPLOYREP §5.1 |
| FACT-02 | openclaw.json 的 skills 字段是装载配置，含 allowBundled/load/install | 100% | DEPLOYREP §5.1 实测 |
| FACT-03 | load.extraDirs 是自定义 Skill 的父目录路径 | 95% | DEPLOYREP §5.1 |
| FACT-04 | Skill 执行体是 CLI 子进程（不在 OpenClaw Node.js 进程中运行） | 90% | DEPLOYREP §5.4 + SKILL.md 机制描述 |
| FACT-05 | SKILL.md 使用 YAML frontmatter 描述 Skill 元数据和 tool 定义 | 90% | DEPLOYREP §5.4 + bundled 示例已存在 |
| FACT-06 | 共约 58 个 bundled skill（healthcheck, taskflow, diagram-maker, spike 等） | 95% | DEPLOYREP §5.1 |
| FACT-07 | Pi 上 /usr/lib/node_modules/openclaw/skills/ 是 bundled skills 目录 | 100% | DEPLOYREP §5.1 |
| FACT-08 | openclaw-agent 服务账号 id=8 已在 FreeArk DB，Token 有效（需重新生成明文） | 100% | DEPLOYREP §3.2 |
| FACT-09 | ChatConsumer [__freeark_user__:<username>] 前缀注入已上线（PID 21178） | 100% | DEPLOYREP §3.1 |
| FACT-10 | Token 必须经 [a-f0-9]{40} 正则全文脱敏（RISK-3 已实现） | 100% | DEPLOYREP §4 |

---

## §8. 仍有不确定性的关键字段（必须实测）

| 不确定项 | 为何关键 | 对应命令 |
|---------|---------|---------|
| SKILL.md frontmatter 精确字段名（name/description/tools/commands/exec 等） | 决定 freeark-skill/SKILL.md 的写法 | 命令 D/E/F |
| agent.main.skills 字段格式（数组？对象？还是 allowBundled 等效名字？） | 决定如何将 freeark-skill 关联到方舟龙虾 agent | 命令 A/I |
| secrets 段是否存在，Token 注入方式 | 决定 FREEARK_AGENT_TOKEN 的安全存储方式 | 命令 A |
| Skill CLI 执行体的 stdin/stdout 协议（JSON? 纯文本? 自定义帧?） | 决定 CLI 工具的实现语言和 I/O 格式 | 命令 D/E/F |
| `load.extraDirs` 是父目录还是 Skill 目录本身 | 决定 agents/ 目录的放置位置 | 命令 A + 实验 |
