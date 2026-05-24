# 生产部署报告 — 方舟龙虾 API 通道与知识增强

```
deployment_report:
  document_id: DEPLOYREP-LOBSTER-001
  project: FreeArk — lobster-agent-api-channel
  status: PARTIAL_SUCCESS
  deployed_at: 2026-05-25T00:22+08:00
  rolled_back_at: 2026-05-25T00:44+08:00
  deployed_by: claude-code (CONFIRM-PRODUCTION-EXEC by user)
  pre_deploy_head: 5c76c90
  post_deploy_head: 5115d64
  rollback_layer: openclaw.json only (Django code retained)
  next_action: SDLC redesign of Skill mechanism
```

---

## 1. 部署结论速览

| 模块 | 状态 | 说明 |
|------|------|------|
| Git 推送（dev → origin） | ✅ COMMITTED | `5115d64 feat(lobster-agent): ...` 已推 origin/main |
| Pi `git pull` | ✅ DEPLOYED | fast-forward `5c76c90..5115d64`, 13 文件落地 |
| FreeArk backend (Django) | ✅ DEPLOYED | 新代码已上线 + 服务重启 + healthy |
| `openclaw-agent` 服务账号 (DB) | ✅ DEPLOYED | id=8, role=user, Token 在 DB |
| Token 写入 openclaw.json | ❌ ROLLED BACK | 因 Skill 配置错误连同 skills 段一起回滚 |
| Skill 19 个 tool (Tier-1+Tier-2) | ❌ NOT ACTIVE | OpenClaw Skill schema 不接受我们的 JS 包格式 |
| Agent 身份 "方舟龙虾" + systemPrompt | ❌ NOT ACTIVE | 与 Skill 配置一起回滚 |

**整体状态：PARTIAL_SUCCESS** — 后端面（ChatConsumer chatuser 注入、`operator_override` 字段、`openclaw-agent` 服务账号）已上线并独立工作；Skill 层和 Agent 自定义层因架构设计错误未生效，配置已回滚到部署前。生产对外功能无中断。

---

## 2. 时间线

| 时刻 | 阶段 | 事件 |
|------|------|------|
| 00:15 | §0 | dev 提交 `5115d64`，推 origin/main |
| 00:22 | §1 | Pi 前置检查 7 项全 PASS |
| 00:22 | §2 | openclaw.json 备份为 `openclaw.json.bak.20260525002210` |
| 00:25 | §3 | git pull fast-forward 完成，3 个非预期 commit 也一并拉入（service 文件 + requirements + skill 文档） |
| 00:28 | §4.1 | `create_openclaw_agent_user` 首次执行 — **Token 泄露事件**（详见 §4） |
| 00:29 | §4.3 | `--force-regenerate-token` 轮换；旧 Token 验证 401 失效；新 Token 存 `/tmp/.fa_token` |
| 00:37 | §5 | staging `openclaw.json` 构建并通过 JSON 校验，sanitized diff 预览 |
| 00:38 | §5.5 | 原子 mv 完成，openclaw.json 更新（22520 字节，600 权限） |
| 00:41 | §6.1 | `sudo systemctl restart freeark-backend` ✅ PASS（PID 21178，uvicorn 启动完整） |
| 00:41 | §6.2 | `systemctl --user restart openclaw-gateway` ❌ FAIL — `Invalid config at openclaw.json. skills: Invalid input` |
| 00:42 | §6.2b | systemd auto-restart 循环 4 次全失败，CPU 烧 ~12s |
| 00:42 | §6.X | `systemctl --user stop openclaw-gateway` 阻断 auto-restart |
| 00:44 | §9.3 | 恢复 `openclaw.json.bak.20260525002210` → 重启 gateway ✅ HEALTHY |
| 00:50 | §诊断 | 通过 `openclaw config schema` + bundled `skills/<name>/SKILL.md` 确认 **OpenClaw Skill 是 markdown 驱动，非 npm 包** |
| 00:55 | §收尾 | 删除 `/tmp/.fa_token`；Django 部分留产；写部署报告 |

---

## 3. 已生效的产物（不需要回滚）

### 3.1 Django 代码（PID 21178 已运行此版本）

- `FreeArkWeb/backend/freearkweb/api/consumers.py`：所有 ChatConsumer 收到的用户消息现在前缀 `[__freeark_user__:<username>]`。未来 Agent（重写后）可解析此前缀获取 chatuser。
- `FreeArkWeb/backend/freearkweb/api/serializers_device_settings.py`：`DeviceParamWriteRequestSerializer` 新增可选 `operator_override` 字段。
- `FreeArkWeb/backend/freearkweb/api/views_device_settings.py`：`device_settings/write/` 端点支持 `operator_override`，仅 `openclaw-agent` 用户名能使用；其他用户传该字段返回错误。`operator` 字段改用 `effective_operator` 落库。

### 3.2 Django 服务账号

- 用户：`openclaw-agent`
- id: 8
- role: user
- is_active: True
- 部门/职位：`AI Agent / Service Account`
- Token：DB hash 仍在，明文已销毁（**重新使用需 `--force-regenerate-token`**）

### 3.3 文件已 push 到 origin/main 但未在 Pi 上"激活"

| 文件 | 位置 | 状态 |
|------|------|------|
| `agents/freeark-skill/{package.json,client.js,index.js,tools/*.js}` | Pi git tree | 文件存在，OpenClaw 不识别此格式 |
| `docs/sdlc/lobster-agent-api-channel/agent_system_prompt_v1.md` | Pi git tree | 文件存在，未注入 openclaw.json |

---

## 4. 关键 INCIDENT：Token 泄露（已闭环处置）

### 4.1 事件经过

- 执行 `create_openclaw_agent_user`（首次），按 SOP 应通过 sed 脱敏 stdout
- 当时脱敏规则只过滤 `FREEARK_AGENT_TOKEN = <hex>` 行
- management command 的"下一步操作"段里**第二次**打印 Token 为 `"FREEARK_AGENT_TOKEN": "<hex>"`（JSON instruction 形式），脱敏没覆盖
- 完整 Token `1afca7388e29ced12f1393c9489dd15073f2290e` 进入 Claude 对话上下文

### 4.2 闭环处置

| 时刻 | 动作 | 结果 |
|------|------|------|
| 00:29 | `--force-regenerate-token` 轮换 | 新 Token 生成 |
| 00:29 | 改进 sanitization：`sed -E "s/[a-f0-9]{40}/[REDACTED-40HEX]/g"` 全文 sed | 新 Token 全程无泄露 |
| 00:29 | 验证旧 Token | `curl -H "Authorization: Token 1afca738..." /api/auth/me/` → **HTTP 401 "Invalid token"** ✓ 死亡确认 |

### 4.3 残留风险评估

- 旧 Token 在 DB 已删除（force-regenerate 是 DELETE + CREATE）
- Claude 对话上下文是临时数据，不入仓库/日志
- **结论：无残留风险**

### 4.4 部署计划修订建议

应在 `deployment_plan.md §4` 添加：
- "管理命令的所有 token 引用必须经统一 `[a-f0-9]{40}` 正则脱敏"
- "脱敏先于显示，且适用于命令的所有 stdout/stderr 输出，不仅是单行"

---

## 5. 关键 INCIDENT：Skill 架构设计错误（导致部署回滚）

### 5.1 错误本质

`module_design.md MOD-SK-01` 与 `architecture_design.md ADR-005` 假设 OpenClaw Skill 注册格式为：
```json
"skills": {
  "freeark-skill": {
    "path": "/abs/path/index.js",
    "env": {"FREEARK_AGENT_TOKEN": "..."}
  }
}
```

并据此让 software-developer 实现 Node.js 包（`package.json` + `index.js` 导出 tool 函数）。

实际 OpenClaw 2026.5.20 的设计：
- `skills` 在 openclaw.json 里是**装载配置**，不是 Skill 列表
- 实际 schema 为：
  ```json
  "skills": {
    "allowBundled": ["..."],
    "load": {
      "extraDirs": ["..."],
      "allowSymlinkTargets": ["..."],
      "watch": true
    },
    "install": {...}
  }
  ```
- Skill 本身是 markdown 驱动：`<skill-dir>/SKILL.md` 描述 skill 能力 + 调用方式
- 参考 bundled 示例：`/usr/lib/node_modules/openclaw/skills/{spike,taskflow,diagram-maker}/SKILL.md`

### 5.2 RISK-001 命中

代码评审报告（`code_review_report.md`）将 OpenClaw Skill 注册格式实测列为 **RISK-001 (MEDIUM)**：
> "module_design.md 的 SKILL_REGISTRATION 是基于 OpenClaw 推测文档结构，部署期必须实测确认"

实际部署期实测就发现根本不兼容。RISK-001 现在标记为 **REALIZED**。

### 5.3 SDLC 阶段问题溯源

- ❌ requirement-analyst 未要求 system-architect 提供 Skill schema 的来源证据（开发文档/源码引用）
- ❌ system-architect 在 `tech_stack.md` 把 OpenClaw Skill 注册写成假设方案，未跑探针
- ❌ software-developer 接到设计直接实现，没有"先 PoC 一个最小 Skill 注册"
- ❌ test-engineer 单元测试覆盖 19 个 tool 内部逻辑，但**没有集成测试覆盖 OpenClaw 真实加载流程**（被 module_design 的"无法本地模拟 OpenClaw"理由掩盖）

### 5.4 修订方向（下一轮 SDLC）

新一轮 system-architect 应该：
1. 先在 Pi 上读 `openclaw config schema` + `/usr/lib/node_modules/openclaw/skills/*/SKILL.md` 至少 3 个示例
2. 把 Skill 重新设计为：
   - `agents/freeark-skill/SKILL.md`：描述 19 个 tool 的能力、参数 schema、二次确认规则、env 需求（Markdown + frontmatter）
   - `agents/freeark-skill/scripts/<tool>.py` 或 `<tool>.sh`：Agent 通过 shell exec 调用，stdin/stdout 交互（标准格式 JSON）
3. Token 注入用 OpenClaw `secrets` 段（schema 有这一节，可能更安全），不直接放 skill env
4. `agents.defaults.skills` 或 `agents.list[<id>].skills` 字段定义 Agent 用哪些 Skill
5. PoC 阶段：把现有 `index.js` 改写成 `freeark-skill-cli` 单文件可执行，先实现 1 个 read tool 通过 SKILL.md 接入，部署到 Pi 实测"OpenClaw 真的能调用并解析返回值"，再扩展到 19 个

---

## 6. Pi 当前状态快照（部署后 00:50）

```
host: raspberrypi
git HEAD: 5115d64  (post-deploy, fast-forward from 5c76c90)
local mods: 3 protected files (.env, package-lock.json, heartbeat_broker_config.json)

services:
  freeark-backend:    active, PID 21178, uvicorn freearkweb.asgi:application :8000, since 00:41:19
  openclaw-gateway:   active, PID 21416, /health=live, since 00:44:03 (restored config)

health endpoints:
  http://127.0.0.1:8000/api/health/ → {"status":"ok"}
  http://127.0.0.1:18789/health     → {"ok":true,"status":"live"}

openclaw.json:
  path: ~/.openclaw/openclaw.json
  mode: 600
  size: 5243 bytes
  agent.main: {} (empty - rolled back)
  skills field: NOT PRESENT (rolled back)
  backups:
    openclaw.json.bak (5035 bytes, May 24 22:25)
    openclaw.json.bak.1 (3976 bytes, May 24 11:07)
    openclaw.json.bak.20260525002210 (5243 bytes, May 25 00:22) ← restored from

Django DB (openclaw-agent):
  id: 8
  role: user
  is_active: True
  Token: in DB, plaintext destroyed locally
  ChatConsumer prefix injection: ACTIVE for all new chat messages
  device_settings/write operator_override: ACTIVE

cleanup:
  /tmp/.fa_token: removed
  /tmp/.fa_openclaw_new.json: consumed by mv (gone)
  /tmp/.fa_cmd_out.log: removed
```

---

## 7. SOP 实际 vs 计划偏差汇总

| 项 | 计划 | 实际 | 原因 |
|----|------|------|------|
| §3.3 pip install | "若 requirements 变 → pip install" | 跳过 | requirements 改的是 `uvicorn[standard]` extras（已装齐），且 backend 进程在跑，无理由重启 venv |
| §4.1 venv 路径 | `cd <repo>/.../freearkweb && venv/bin/python` | 改用绝对路径 `/home/.../venv/bin/python` | SOP 假设 venv 在 freearkweb 下，实际在仓库根 |
| §4 token 脱敏 | `grep -v "FREEARK_AGENT_TOKEN = "` 单行过滤 | 改用全文 `sed -E "s/[a-f0-9]{40}/[REDACTED-40HEX]/g"` | 单行 grep 没覆盖 JSON instruction 段的二次打印，**触发实际 Token 泄露**，立即轮换补救 |
| §5.2 段 3 prompt 提取 | `r"---BEGIN SYSTEM PROMPT---(.*?)---END SYSTEM PROMPT---"` | 改用 `re.MULTILINE` + `^...$` 行首锚点 | markdown 第 18 行部署说明里 inline 引用了 marker，原正则非贪婪匹配到 5 字符空串 |
| §5 三段写入 | 段 1/2/3 三次写入 + 三次验证 | 合并到 staging 文件 + 一次原子 mv | 减少中间破损 JSON 风险 |
| §6.2 gateway 重启 | 预期 PASS | FAIL → 触发部分回滚 | RISK-001 命中（见 §5） |
| §7 实机验证 | 7 项全跑 | **未执行**（部署回滚前提下无意义） | Skill 没装好，端到端验证跳过 |
| §8 观察窗口 | 30 分钟主动 + 48 小时被动 | 不适用 | 部署目标功能未上线，观察对象不存在 |

---

## 8. 行动项（next sprint）

| # | 行动 | 责任 | 优先级 |
|---|------|------|------|
| AI-01 | 重启 system-architect 子代理，基于本报告 §5.4 重写 Skill 架构（SKILL.md + CLI 模式） | pm-orchestrator | P0 |
| AI-02 | requirement-analyst 把"OpenClaw Skill 实际 schema 实测"列为**强制 ADR 前置条件** | pm-orchestrator | P0 |
| AI-03 | 删除 `agents/freeark-skill/` 当前实现，或保留 JS 逻辑改造为 CLI 可执行（取决于 AI-01 决策） | software-developer | P1 |
| AI-04 | `agent_system_prompt_v1.md` 大部分内容可复用，但 Tier-1/Tier-2 调用规则要重写以匹配新 Skill 抽象 | software-developer | P1 |
| AI-05 | `deployment_plan.md §4` 增加"Token 全 hex 正则脱敏"硬规则 | pm-orchestrator | P1 |
| AI-06 | code-review 流程增加"OpenClaw Skill 必须有 PoC 验证才能进入开发"门控 | pm-orchestrator | P2 |
| AI-07 | 评估 `openclaw-agent` Token 是否短期重新分发给开发者用于手动 API 测试 | user | P2 |
| AI-08 | 把 OpenClaw 探针结果（schema + bundled skills 结构）落档到 `.claude/skills/freeark-prod-deploy/SKILL.md` 的"OpenClaw 知识"段 | claude-code | P3 |

---

## 9. 风险登记表更新

| 风险 ID | 原级别 | 实际命中 | 当前状态 | 处置 |
|---------|--------|---------|---------|------|
| RISK-001 | MEDIUM | ✅ REALIZED — Skill 注册格式完全不兼容 | 部署回滚 + SDLC 重做 | AI-01/AI-02/AI-06 |
| FINDING-001 | MEDIUM (boolean 类型门控) | ⏸ 未触发（验证未跑） | UNKNOWN | 重新设计 Skill 时不再适用 |
| FINDING-002 | MEDIUM (operator_override 防护) | ⏸ 未触发（验证未跑） | DEPLOYED 但未端到端测试 | Django 部分已上线，逻辑测试通过；需后续端到端验证 |
| RISK-2 | LOW (System Prompt token) | ⏸ 未触发（验证未跑） | UNKNOWN | 9353 字符 / ~4571 tokens，估算超过 4000 阈值，下一轮设计阶段需复核 |
| RISK-3 (TOKEN 泄露) | 未登记 | ✅ NEW — 部署期发生 | 闭环处置完成 | AI-05 |

---

## 10. 部署人结论

本次"端到端部署"实际证明了 SDLC 的一个根本性盲点：**整个 Skill 架构基于对 OpenClaw 注册机制的假设，从未做最小可行性验证**。所有上游门控（需求/架构/开发/测试）通过的前提是 module_design.md 描述的 Skill schema 为真，而该假设在部署期被外部系统直接证伪。

Django 后端层的所有改动（ChatConsumer 前缀注入、operator_override 字段、服务账号）逻辑独立、设计正确、已上线生效。这部分构成下一轮 Skill 实现的稳定基础。

新一轮 SDLC 必须**先以 Pi 上实际 OpenClaw schema 与 bundled SKILL.md 为唯一真理源**重新走需求 → 架构两个阶段，软件实现层等架构稳定再启。

— deployed_by claude-code @ 2026-05-25T00:55+08:00
