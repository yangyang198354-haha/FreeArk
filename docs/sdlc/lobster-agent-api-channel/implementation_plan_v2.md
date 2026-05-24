# 实现计划 v2 — 方舟龙虾 API 通道（第三轮）

```
file_header:
  document_id: IMPL-LOBSTER-002
  project: FreeArk — lobster-agent-api-channel
  version: 2.0.0
  status: IN_PROGRESS
  author_agent: pm-orchestrator + software-developer (SDLC 第三轮)
  created_at: 2026-05-25
  supersedes: IMPL-LOBSTER-001
  depends_on: ARCH-LOBSTER-002, MOD-LOBSTER-002, PROBES-LOBSTER-001
  decisions_locked:
    CONFIRM-A: Python CLI 执行体（复用 FreeArk venv + requests）
    CONFIRM-B: git rm v1 Node.js 文件（合并进 PoC 提交，不单独 commit）
    CONFIRM-C: 接受 PASS_WITH_CONDITIONS 架构，PoC 为首个里程碑
  milestone_gate: PoC 5 条 PASS 才能进入 Step 4（硬条件，不可绕过）
```

---

## 阶段一：probes §6 补测（Step 1，阻塞 SKILL.md 最终化）

### 执行方式

SSH 到 Pi，运行 `scripts/run_probes.sh`，将输出追加到 `openclaw_schema_probes.md §7`：

```bash
bash /home/yangyang/Freeark/FreeArk/scripts/run_probes.sh 2>&1 \
  | tee /tmp/probe_results.txt
```

### 待确认问题清单（追加到 §8）

| 编号 | 问题 | 对应命令 | 影响 |
|------|------|---------|------|
| PENDING-A | SKILL.md frontmatter 精确字段名（name/exec/tools/parameters/env） | 命令 D/E/F | 决定 freeark-skill/SKILL.md 写法 |
| PENDING-B | agent 段关联 Skill 字段格式（agent.main.skills 数组？还是其他字段？） | 命令 A/I | 决定 openclaw.json 修改方式 |
| PENDING-C | Token 注入方式（secrets 段？env 段？还是 systemd env？） | 命令 A | 决定 FREEARK_AGENT_TOKEN 安全存储 |
| PENDING-D | CLI 调用协议（stdin JSON？argv？长驻进程？） | 命令 D/E/F | 决定使用 freeark_get_dashboard_summary.py 的哪种调用模式 |
| PENDING-E | openclaw skills list / info 命令格式 | 命令 B/C/H | 决定 PoC 验证步骤 2/3 的确切命令 |

### §7 结果写入后的必要 SKILL.md 更新

probes §7 结果出来后，需要更新以下文件中的 [PROBE-CONFIRM] 标注项：
- `agents/freeark-skill/SKILL.md`：exec 字段名/格式，env 段字段名，tools 段格式

---

## 阶段二：git rm v1 文件（Step 2，与 PoC 合并提交）

### 文件处理清单

| 文件 | 动作 | 执行时机 |
|------|------|---------|
| `agents/freeark-skill/package.json` | `git rm` | PoC commit 前 |
| `agents/freeark-skill/client.js` | `git rm` | PoC commit 前 |
| `agents/freeark-skill/index.js` | `git rm` | PoC commit 前 |
| `agents/freeark-skill/tools/tier1_readonly.js` | `git rm` | PoC commit 前 |
| `agents/freeark-skill/tools/tier2_write.js` | `git rm` | PoC commit 前 |
| `agents/freeark-skill/tools/` (目录) | 删空目录（若 git rm 后为空） | PoC commit 前 |

### 执行命令（在 Pi 上执行）

```bash
cd /home/yangyang/Freeark/FreeArk
git rm agents/freeark-skill/package.json
git rm agents/freeark-skill/client.js
git rm agents/freeark-skill/index.js
git rm agents/freeark-skill/tools/tier1_readonly.js
git rm agents/freeark-skill/tools/tier2_write.js
# 验证剩余文件
ls -la agents/freeark-skill/
ls -la agents/freeark-skill/scripts/
ls -la agents/freeark-skill/lib/
```

**注**：此步骤仅 stage，不 commit。等 PoC 实现完成后统一 commit。

---

## 阶段三：PoC 实现（Step 3）

### 已完成的实现文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `agents/freeark-skill/lib/freeark_client.py` | WRITTEN | HTTP 客户端封装，Token 从 FREEARK_AGENT_TOKEN 环境变量读取 |
| `agents/freeark-skill/lib/__init__.py` | WRITTEN | Python 包标记 |
| `agents/freeark-skill/scripts/freeark_get_dashboard_summary.py` | WRITTEN | PoC 单 tool 独立脚本 |
| `agents/freeark-skill/scripts/freeark_tool.py` | WRITTEN | 统一 dispatch 入口（PoC 通过后激活） |
| `agents/freeark-skill/scripts/tier1_readonly.py` | WRITTEN | 14 个只读 tool（Python 移植自 v1 JS） |
| `agents/freeark-skill/scripts/tier2_write.py` | WRITTEN | 5 个写操作 tool（Python 移植自 v1 JS） |
| `agents/freeark-skill/SKILL.md` | WRITTEN（含 PROBE-CONFIRM 标注） | PoC 版（1 tool），SKILL.md 格式待 §7 结果确认 |

### SKILL.md 字段更新流程（probes §7 出来后执行）

```
1. 读 §7 中 PROBE-D/E/F 的实测 SKILL.md 示例（healthcheck/diagram-maker/taskflow）
2. 对比 agents/freeark-skill/SKILL.md 中各 [PROBE-CONFIRM] 标注项
3. 逐一更新字段名（exec → 实测字段名，env 格式，tools 格式，parameters 格式）
4. 删除所有 [PROBE-CONFIRM] 注释
5. 确认 openclaw.json 变更模板（agent.main.skills 格式，skills.load.extraDirs）
```

### Token 注入（待 PENDING-C 解决）

当前 `freeark_client.py` 从 `FREEARK_AGENT_TOKEN` 环境变量读取。

注入方式取决于 probes §7 PENDING-C 结论：

| 若 PENDING-C 结论 | 操作 |
|-----------------|------|
| openclaw.json 有 secrets 段 | 在 secrets 段添加 FREEARK_AGENT_TOKEN，引用到 Skill 环境变量 |
| SKILL.md env 段支持从 openclaw.json 引用 | 在 openclaw.json 对应段添加，SKILL.md env 段引用 |
| 仅支持 systemd env | 在 openclaw-gateway.service 的 systemd unit 添加 Environment= |
| 仅支持在 SKILL.md env 段硬配置（最低优先） | 在 openclaw.json 中存储，写入到 Skill 目录（gitignored .env 文件），SKILL.md 中不硬编码 |

**无论哪种方式，Token 明文不得出现在 Claude 对话上下文（REQ-NFR-007）。**

### Token 重新生成（PoC 部署前）

openclaw-agent 账号 Token 明文已销毁（部署报告 §3.2）。需重新生成：

```bash
SSH="ssh -o BatchMode=yes -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -i /c/fa-home/.ssh/id_ed25519 -p 57279 -o ConnectTimeout=20 \
  yangyang@et116374mm892.vicp.fun"

# 重新生成并脱敏（REQ-NFR-007：全文正则脱敏）
$SSH '/home/yangyang/Freeark/FreeArk/venv/bin/python \
  /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py \
  create_openclaw_agent_user --force-regenerate-token 2>&1 \
  | sed -E "s/[a-f0-9]{40}/[REDACTED-40HEX]/g"'

# Token 明文存 Pi 本地临时文件（单独 SSH 命令，输出不传到 Claude）
$SSH 'TOKEN=$(/home/yangyang/Freeark/FreeArk/venv/bin/python \
  /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py \
  create_openclaw_agent_user --force-regenerate-token --output-token-only 2>/dev/null); \
  echo "$TOKEN" > /tmp/.fa_token && chmod 600 /tmp/.fa_token && \
  echo "Token stored ($(wc -c < /tmp/.fa_token) chars)"'
```

### PoC 部署步骤（probes §7 结果出来后执行）

1. Git pull（含新增的 SKILL.md 和 Python 脚本）
2. 确认 Python 脚本可执行：`python3 agents/freeark-skill/scripts/freeark_get_dashboard_summary.py`（需 Token 环境变量）
3. 更新 openclaw.json（skills.load.extraDirs + agent.main.skills + Token 注入，方式见 PENDING-C）
4. 验证 JSON：`python3 -m json.tool ~/.openclaw/openclaw.json`
5. 备份：`cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.poc-$(date +%Y%m%d%H%M%S)`
6. 重启：`systemctl --user restart openclaw-gateway.service`
7. 检查：`systemctl --user status openclaw-gateway.service --no-pager | head -20`

### PoC 验证 5 条标准（ARCH-LOBSTER-002 §9.4）

| # | 验证项 | 命令/方法 | PASS 判定 |
|---|--------|---------|---------|
| 1 | Gateway 启动成功，无 Invalid config | `systemctl --user status openclaw-gateway.service` | `active (running)`，无 Invalid config |
| 2 | freeark-skill 出现在 skills 列表 | `openclaw skills list`（实际命令待 §7 PROBE-E 确认） | freeark-skill 可见，状态 ready |
| 3 | skills info 能解析 SKILL.md | `openclaw skills info freeark-skill` | 显示 tool 列表 |
| 4 | Agent 对话触发 tool，返回真实数据 | 聊天界面发"查一下系统看板" | 日志有 Skill exec 记录，返回真实 JSON |
| 5 | 重启后 Skill 持续可用 | 停止再启动 openclaw-gateway | 再次验证 1+2 |

---

## 阶段四：扩展 19 个 tool（Step 4，阻塞于 PoC PASS）

**前提：PoC 全部 5 条 PASS，poc_report.md 记录 PoC_STATUS=PASS。**

### 扩展计划

PoC 证明了 SKILL.md 格式和 CLI 调用协议正确后：

1. 更新 `agents/freeark-skill/SKILL.md`：从 1 个 tool 扩展到 19 个 tool（使用 `freeark_tool.py` 作为 exec）
2. 更新 SKILL.md 中的 exec 字段：从 `freeark_get_dashboard_summary.py` 改为 `freeark_tool.py`
3. 将 14 个 Tier-1 tool 定义添加到 SKILL.md（基于 `tier1_readonly.py` 的函数签名）
4. 将 5 个 Tier-2 tool 定义添加到 SKILL.md（含 [Tier-2 写操作] description 标注）

### Tier-1 扩展顺序（每 5 个跑一次单元测试）

| 批次 | Tools | 单元测试 |
|------|-------|---------|
| 批次 1（PoC 已验证） | freeark_get_dashboard_summary | PASS（PoC 已跑） |
| 批次 2 | freeark_get_realtime_params, freeark_get_services_status, freeark_get_power_status, freeark_get_plc_status, freeark_get_plc_latest | 测试工程师跑 |
| 批次 3 | freeark_get_usage_daily, freeark_get_usage_period, freeark_get_usage_monthly, freeark_get_device_params, freeark_get_write_records | 测试工程师跑 |
| 批次 4 | freeark_get_device_tree, freeark_get_service_detail, freeark_get_plc_status_single（共 3 个） | 测试工程师跑 |
| 批次 5 | Tier-2: freeark_write_device_params, freeark_trigger_refresh, freeark_service_action, freeark_sync_device_tree, freeark_batch_sync_device_tree | 测试工程师跑（含 boolean 门控验证） |

### v1 JS → Python 移植对比（复用逻辑说明）

| v1 JS 文件 | Python 等价 | 主要差异 |
|-----------|-----------|--------|
| `client.js` | `lib/freeark_client.py` | Token 从环境变量注入，超时逻辑等价 |
| `tools/tier1_readonly.js` | `scripts/tier1_readonly.py` | URL/参数逻辑等价移植；freeark_get_plc_status_single 从 freeark_get_plc_status 拆分 |
| `tools/tier2_write.js` | `scripts/tier2_write.py` | confirmed 硬拦截移除（由 SKILL.md + system prompt 保障）；operator_override 参数逻辑保留 |

---

## 阶段五：测试（Step 5）

### 测试工程师任务清单

1. **单元测试**（每批次 5 个 tool 完成后）：
   - mock FreeArk HTTP 响应（requests-mock 或 unittest.mock）
   - 验证正常路径、缺少必要参数、HTTP 500、Token 未设置 4 种情况
   - 覆盖率目标 ≥ 80%

2. **集成测试**（全部 19 个 tool 实现后）：
   - 连接真实 Pi 上的 FreeArk API（需 Token）
   - 验证每个 Tier-1 tool 返回真实数据
   - 验证 Tier-2 boolean 门控（未确认时 Agent 层阻断）
   - 验证 operator_override 字段落库（查 PLCWriteRecord 表）
   - 集成测试通过率目标 ≥ 90%

3. **E2E 测试**（部署后）：
   - 聊天触发全部 Tier-1 tool
   - Tier-2 确认流程完整验证（含"取消"路径）
   - 覆盖率：所有 US-LOBSTER-* 用户故事至少 1 个 E2E 测试

---

## 阶段六：部署（Step 6）

### 部署 SOP 更新（来自用户 Step 6 指令）

在 `docs/sdlc/lobster-agent-api-channel/deployment_plan.md` 中更新以下项：

| 修复点 | 位置 | 变更内容 |
|-------|------|---------|
| Token 脱敏规则 | §4 | 全文正则 `sed -E 's/[a-f0-9]{40}/[REDACTED-40HEX]/g'`（已在本文档 Token 重新生成步骤中体现） |
| venv 路径 | §4.1 | 绝对路径 `/home/yangyang/Freeark/FreeArk/venv/bin/python` |
| prompt 提取正则 | §5.2 段 3 | 加行首锚点 `^` |
| 新增 staging 验证 | §3.5（新增） | 拉完后必跑 `openclaw config validate`（若命令存在），否则用 `python3 -m json.tool` 验证 JSON 合法性 |

### 部署顺序

1. git pull（Pi 端）
2. git rm v1 JS 文件（已在 Step 2 staged）
3. openclaw.json 更新（skills 装载配置 + agent.main.skills + Token 注入）
4. `systemctl --user restart openclaw-gateway.service`
5. 验证启动（无 Invalid config）
6. 完整 PoC 验证（5 条标准）
7. 提交 commit（含 git rm + 新增 Python 文件）
8. push 到 GitHub main

---

## 文件清单（第三轮产物）

### 新增文件

| 路径 | 类型 | 状态 |
|------|------|------|
| `agents/freeark-skill/SKILL.md` | Skill 入口 | WRITTEN（含 PROBE-CONFIRM 标注，待 §7 更新） |
| `agents/freeark-skill/lib/freeark_client.py` | HTTP 客户端 | WRITTEN |
| `agents/freeark-skill/lib/__init__.py` | Python 包 | WRITTEN |
| `agents/freeark-skill/scripts/freeark_get_dashboard_summary.py` | PoC 单 tool 脚本 | WRITTEN |
| `agents/freeark-skill/scripts/freeark_tool.py` | 统一 dispatch 入口 | WRITTEN |
| `agents/freeark-skill/scripts/tier1_readonly.py` | 14 个只读 tool | WRITTEN |
| `agents/freeark-skill/scripts/tier2_write.py` | 5 个写操作 tool | WRITTEN |
| `scripts/run_probes.sh` | SSH 探针脚本 | WRITTEN |
| `docs/sdlc/lobster-agent-api-channel/implementation_plan_v2.md` | 本文件 | IN_PROGRESS |
| `docs/sdlc/lobster-agent-api-channel/phase_status_v3.md` | PM 状态 | IN_PROGRESS |

### 待更新文件（probes §7 结果后）

| 路径 | 待更新内容 |
|------|---------|
| `agents/freeark-skill/SKILL.md` | [PROBE-CONFIRM] 标注项全部确认并更新 |
| `openclaw_schema_probes.md` | 追加 §7 实测结果 + §8 PENDING 解决 |

### 待删除文件（合并进 PoC commit）

- `agents/freeark-skill/package.json`
- `agents/freeark-skill/client.js`
- `agents/freeark-skill/index.js`
- `agents/freeark-skill/tools/tier1_readonly.js`
- `agents/freeark-skill/tools/tier2_write.js`
